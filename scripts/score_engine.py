#!/usr/bin/env python3
"""
Scoring engine for the Undergraduate Researcher Leaderboard.

Pulls data from Semantic Scholar, GitHub, and Twitter (via ptwittercli),
then computes a composite score for each researcher.

Usage:
    python scripts/score_engine.py
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESEARCHERS_FILE = DATA / "researchers.json"
SCORES_FILE = DATA / "scores.json"
EVENTS_FILE = DATA / "events.json"
HISTORY_DIR = DATA / "history"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"

# Weights
W_PUB = 0.40
W_SOCIAL = 0.30
W_BUILDER = 0.30

# --- Data fetchers -----------------------------------------------------------

def fetch_semantic_scholar(scholar_id: str) -> dict:
    """Fetch publication stats from Semantic Scholar."""
    if not scholar_id:
        return {"paper_count": 0, "citation_count": 0, "h_index": 0, "top_venues": 0}

    url = f"{SEMANTIC_SCHOLAR_API}/author/{scholar_id}"
    params = {"fields": "paperCount,citationCount,hIndex,papers.venue,papers.year,papers.citationCount,papers.title"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            time.sleep(3)
            resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"  [semantic_scholar] HTTP {resp.status_code} for {scholar_id}")
            return {"paper_count": 0, "citation_count": 0, "h_index": 0, "top_venues": 0}
        data = resp.json()
    except Exception as e:
        print(f"  [semantic_scholar] Error for {scholar_id}: {e}")
        return {"paper_count": 0, "citation_count": 0, "h_index": 0, "top_venues": 0}

    top_venue_keywords = [
        "neurips", "nips", "icml", "iclr", "cvpr", "aaai", "acl", "emnlp",
        "ieee", "nature", "science", "arxiv", "icra", "iros", "usenix",
        "crypto", "eurocrypt", "siggraph", "chi", "kdd", "www"
    ]
    papers = data.get("papers", [])
    top_venues = sum(
        1 for p in papers
        if p.get("venue") and any(k in p["venue"].lower() for k in top_venue_keywords)
    )

    return {
        "paper_count": data.get("paperCount", 0),
        "citation_count": data.get("citationCount", 0),
        "h_index": data.get("hIndex", 0),
        "top_venues": top_venues,
        "papers": papers,
    }


def fetch_github(handle: str) -> dict:
    """Fetch GitHub stats."""
    if not handle:
        return {"total_stars": 0, "public_repos": 0, "contributions": 0}

    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    try:
        user_resp = requests.get(f"https://api.github.com/users/{handle}", headers=headers, timeout=10)
        if user_resp.status_code != 200:
            print(f"  [github] HTTP {user_resp.status_code} for {handle}")
            return {"total_stars": 0, "public_repos": 0, "contributions": 0}
        user = user_resp.json()

        # Get total stars across repos
        repos_resp = requests.get(
            f"https://api.github.com/users/{handle}/repos",
            headers=headers, params={"per_page": 100, "sort": "stars"}, timeout=10
        )
        repos = repos_resp.json() if repos_resp.status_code == 200 else []
        total_stars = sum(r.get("stargazers_count", 0) for r in repos if isinstance(r, dict))

        return {
            "total_stars": total_stars,
            "public_repos": user.get("public_repos", 0),
            "followers": user.get("followers", 0),
        }
    except Exception as e:
        print(f"  [github] Error for {handle}: {e}")
        return {"total_stars": 0, "public_repos": 0, "contributions": 0}


def fetch_twitter(handle: str) -> dict:
    """Fetch Twitter stats via ptwittercli."""
    if not handle:
        return {"followers": 0, "avg_engagement": 0, "viral_tweets": 0}

    try:
        result = subprocess.run(
            ["ptwittercli", "user", handle, "--json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            # Try without --json
            result = subprocess.run(
                ["ptwittercli", "user", handle],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                print(f"  [twitter] ptwittercli failed for {handle}")
                return {"followers": 0, "avg_engagement": 0, "viral_tweets": 0}

        # Parse output
        output = result.stdout
        followers = 0
        for line in output.split("\n"):
            if "followers" in line.lower():
                # Try to extract number
                import re
                nums = re.findall(r'[\d,]+', line)
                if nums:
                    followers = int(nums[-1].replace(",", ""))
                    break

        # Get recent tweets for engagement
        tweets_result = subprocess.run(
            ["ptwittercli", "timeline", handle, "-n", "20"],
            capture_output=True, text=True, timeout=30
        )
        viral_tweets = 0
        total_engagement = 0
        tweet_count = 0
        if tweets_result.returncode == 0:
            import re
            for line in tweets_result.stdout.split("\n"):
                likes_match = re.findall(r'(\d+)\s*(?:likes?|♥|❤)', line.lower())
                if likes_match:
                    likes = int(likes_match[0])
                    total_engagement += likes
                    tweet_count += 1
                    if likes >= 1000:
                        viral_tweets += 1

        avg_engagement = total_engagement / max(tweet_count, 1)

        return {
            "followers": followers,
            "avg_engagement": round(avg_engagement, 1),
            "viral_tweets": viral_tweets,
        }
    except FileNotFoundError:
        print("  [twitter] ptwittercli not found — skipping Twitter data")
        return {"followers": 0, "avg_engagement": 0, "viral_tweets": 0}
    except Exception as e:
        print(f"  [twitter] Error for {handle}: {e}")
        return {"followers": 0, "avg_engagement": 0, "viral_tweets": 0}


# --- Scoring ------------------------------------------------------------------

def score_publications(scholar_data: dict) -> float:
    """Score 0–100 for publication record."""
    paper_count = scholar_data.get("paper_count", 0)
    citations = scholar_data.get("citation_count", 0)
    h_index = scholar_data.get("h_index", 0)
    top_venues = scholar_data.get("top_venues", 0)

    # For an undergrad, even 1-2 papers is impressive
    paper_score = min(paper_count * 12, 30)       # max 30 pts from count
    citation_score = min(citations * 0.5, 25)      # max 25 pts from citations
    h_score = min(h_index * 10, 20)                # max 20 pts from h-index
    venue_score = min(top_venues * 8, 25)          # max 25 pts from top venues

    return min(round(paper_score + citation_score + h_score + venue_score, 1), 100)


def score_social(twitter_data: dict) -> float:
    """Score 0–100 for social media clout."""
    followers = twitter_data.get("followers", 0)
    avg_engagement = twitter_data.get("avg_engagement", 0)
    viral = twitter_data.get("viral_tweets", 0)

    follower_score = min(followers / 200, 40)       # 8k followers = max 40
    engagement_score = min(avg_engagement / 5, 30)   # 150 avg likes = max 30
    viral_score = min(viral * 10, 30)                # 3 viral tweets = max 30

    return min(round(follower_score + engagement_score + viral_score, 1), 100)


def score_builder(github_data: dict) -> float:
    """Score 0–100 for builder cred."""
    stars = github_data.get("total_stars", 0)
    repos = github_data.get("public_repos", 0)
    gh_followers = github_data.get("followers", 0)

    star_score = min(stars / 10, 40)                # 400 stars = max 40
    repo_score = min(repos * 1.5, 30)               # 20 repos = max 30
    follower_score = min(gh_followers / 5, 30)       # 150 gh followers = max 30

    return min(round(star_score + repo_score + follower_score, 1), 100)


def detect_events(name: str, scholar_data: dict, twitter_data: dict, prev_scores: dict) -> list:
    """Detect notable events that could influence rankings."""
    events = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    papers = scholar_data.get("papers", [])
    current_year = datetime.now().year
    for p in papers[:5]:  # Check recent papers
        if p.get("year") and p["year"] >= current_year - 1:
            venue = p.get("venue", "preprint")
            citations = p.get("citationCount", 0)
            if citations >= 10 or any(k in (venue or "").lower() for k in ["neurips", "icml", "iclr", "cvpr", "nature"]):
                events.append({
                    "date": now,
                    "researcher": name,
                    "type": "publication",
                    "description": f"Paper \"{p.get('title', 'Untitled')}\" at {venue} ({citations} citations)",
                })

    if twitter_data.get("viral_tweets", 0) > 0:
        events.append({
            "date": now,
            "researcher": name,
            "type": "viral_tweet",
            "description": f"{twitter_data['viral_tweets']} viral tweet(s) detected (1k+ likes)",
        })

    return events


# --- Main ---------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Undergraduate Researcher Leaderboard — Scoring Engine")
    print("=" * 60)

    researchers = json.loads(RESEARCHERS_FILE.read_text())
    print(f"\nLoaded {len(researchers)} researchers")

    # Load previous scores for delta detection
    prev_scores = {}
    if SCORES_FILE.exists():
        try:
            prev = json.loads(SCORES_FILE.read_text())
            prev_scores = {s["name"]: s for s in prev}
        except (json.JSONDecodeError, KeyError):
            pass

    # Load existing events
    existing_events = []
    if EVENTS_FILE.exists():
        try:
            existing_events = json.loads(EVENTS_FILE.read_text())
        except json.JSONDecodeError:
            pass

    all_scores = []
    new_events = []

    for i, r in enumerate(researchers):
        name = r["name"]
        print(f"\n[{i+1}/{len(researchers)}] Scoring {name} ({r.get('university', '?')})")

        scholar_data = fetch_semantic_scholar(r.get("semantic_scholar_id"))
        github_data = fetch_github(r.get("github_handle"))
        twitter_data = fetch_twitter(r.get("twitter_handle"))

        pub_score = score_publications(scholar_data)
        social_score = score_social(twitter_data)
        builder_score = score_builder(github_data)
        boost = min(r.get("manual_boost", 0), 20)

        composite = round(W_PUB * pub_score + W_SOCIAL * social_score + W_BUILDER * builder_score + boost, 1)
        composite = min(composite, 100)

        # Detect rank-changing events
        events = detect_events(name, scholar_data, twitter_data, prev_scores.get(name, {}))
        new_events.extend(events)

        # Calculate delta from previous week
        prev = prev_scores.get(name, {})
        prev_rank = prev.get("rank", None)
        prev_composite = prev.get("composite_score", None)

        score_entry = {
            "name": name,
            "university": r.get("university", ""),
            "grad_year": r.get("grad_year"),
            "fields": r.get("fields", []),
            "publication_score": pub_score,
            "social_score": social_score,
            "builder_score": builder_score,
            "manual_boost": boost,
            "composite_score": composite,
            "rank": 0,  # filled in after sorting
            "prev_rank": prev_rank,
            "score_delta": round(composite - prev_composite, 1) if prev_composite else None,
            "twitter_handle": r.get("twitter_handle"),
            "github_handle": r.get("github_handle"),
            "notes": r.get("notes", ""),
            "raw": {
                "scholar": {k: v for k, v in scholar_data.items() if k != "papers"},
                "github": github_data,
                "twitter": twitter_data,
            },
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }
        all_scores.append(score_entry)

        print(f"  Pub={pub_score}  Social={social_score}  Builder={builder_score}  Boost={boost}  → Composite={composite}")
        # Be kind to rate limits
        time.sleep(1)

    # Sort by composite score descending, assign ranks
    all_scores.sort(key=lambda x: x["composite_score"], reverse=True)
    for i, s in enumerate(all_scores):
        s["rank"] = i + 1

    # Save scores
    SCORES_FILE.write_text(json.dumps(all_scores, indent=2))
    print(f"\n✅ Scores written to {SCORES_FILE}")

    # Save snapshot to history
    HISTORY_DIR.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_file = HISTORY_DIR / f"{today}.json"
    snapshot_file.write_text(json.dumps(all_scores, indent=2))
    print(f"✅ Snapshot saved to {snapshot_file}")

    # Merge new events (keep last 200)
    all_events = new_events + existing_events
    all_events = all_events[:200]
    EVENTS_FILE.write_text(json.dumps(all_events, indent=2))
    print(f"✅ {len(new_events)} new events detected, {len(all_events)} total in feed")

    print("\n" + "=" * 60)
    print("LEADERBOARD")
    print("=" * 60)
    for s in all_scores:
        delta_str = ""
        if s["prev_rank"]:
            diff = s["prev_rank"] - s["rank"]
            if diff > 0:
                delta_str = f" ↑{diff}"
            elif diff < 0:
                delta_str = f" ↓{abs(diff)}"
        print(f"  #{s['rank']} {s['name']} ({s['university']}) — {s['composite_score']}{delta_str}")


if __name__ == "__main__":
    main()
