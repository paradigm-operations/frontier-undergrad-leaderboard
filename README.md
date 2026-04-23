# 🏆 Undergraduate Researcher Leaderboard — Frontier Tech

A living leaderboard tracking the most promising undergraduate researchers across **AI, hardware, robotics, crypto, and defense tech**.

## 🔗 Live Leaderboard

👉 **[View the Leaderboard](https://paradigm-operations.github.io/undergrad-researcher-leaderboard/)**

## Scoring Methodology

Each researcher is scored across three dimensions (0–100 each), combined into a weighted composite:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| **Publications** | 40% | Paper count, citation velocity, venue prestige (NeurIPS, ICML, IEEE, etc.) |
| **Social Clout** | 30% | Twitter followers, avg engagement rate, viral tweets (1k+ likes) |
| **Builder Cred** | 30% | GitHub stars, open-source contributions, shipped projects, hackathon wins |

**Composite Score** = `0.4 × Publications + 0.3 × Social + 0.3 × Builder`

## Features

- **Weekly auto-refresh** via GitHub Actions (every Monday 9am PT)
- **Bump chart** showing rank changes over time — spot rapid risers
- **Event feed** tracking publications, viral tweets, and notable milestones that moved rankings
- **Persistent history** stored as JSON snapshots in `data/history/`

## Managing the Roster

### Add a researcher

Edit `data/researchers.json` and add an entry:

```json
{
  "name": "Jane Doe",
  "university": "MIT",
  "grad_year": 2026,
  "fields": ["AI", "robotics"],
  "twitter_handle": "janedoe",
  "github_handle": "janedoe",
  "scholar_id": "XXXXXX",
  "semantic_scholar_id": "XXXXXX",
  "notes": "Built XYZ framework, 2nd author on AlphaFoo paper"
}
```

### Manual score override

If automated scoring misses context (e.g., a stealth project, unpublished work), add a `manual_boost` field (0–20 points) with a `boost_reason`.

## Running Locally

```bash
pip install -r requirements.txt
python scripts/score_engine.py        # Re-score all researchers
python scripts/generate_site.py       # Rebuild the static site
```

## Data Sources

- **Semantic Scholar API** — publication counts, citations, venue data
- **Twitter/X API** (via `ptwittercli`) — follower counts, engagement
- **GitHub API** — stars, contributions, repos
- **Manual curation** — for context machines can't capture

## Repo Structure

```
├── data/
│   ├── researchers.json          # Roster of tracked researchers
│   ├── scores.json               # Latest computed scores
│   ├── events.json               # Notable events feed
│   └── history/                  # Weekly snapshots (YYYY-MM-DD.json)
├── scripts/
│   ├── score_engine.py           # Scoring pipeline
│   └── generate_site.py          # Builds the static HTML leaderboard
├── docs/
│   └── index.html                # GitHub Pages site
├── .github/
│   └── workflows/
│       └── weekly_update.yml     # Cron job: score + publish
└── requirements.txt
```
