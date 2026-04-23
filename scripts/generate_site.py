#!/usr/bin/env python3
"""
Generates the static GitHub Pages site for the leaderboard.

Reads data/scores.json, data/events.json, and data/history/*.json
to produce docs/index.html with:
  - Sortable leaderboard table
  - Bump line chart (rank over time for top researchers)
  - Event feed
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"


def load_history() -> dict:
    """Load all historical snapshots, keyed by date."""
    history_dir = DATA / "history"
    history = {}
    if history_dir.exists():
        for f in sorted(history_dir.glob("*.json")):
            date = f.stem
            try:
                history[date] = json.loads(f.read_text())
            except json.JSONDecodeError:
                pass
    return history


def build_bump_chart_data(history: dict) -> str:
    """Build JSON data for the bump chart."""
    if not history:
        return "[]"

    # Collect all researcher names
    all_names = set()
    for date, scores in history.items():
        for s in scores:
            all_names.add(s["name"])

    # Build time series per researcher
    dates = sorted(history.keys())
    series = []
    for name in sorted(all_names):
        data_points = []
        for date in dates:
            rank = None
            for s in history[date]:
                if s["name"] == name:
                    rank = s["rank"]
                    break
            data_points.append({"date": date, "rank": rank})
        series.append({"name": name, "data": data_points})

    return json.dumps({"dates": dates, "series": series})


def generate_html(scores: list, events: list, bump_data: str) -> str:
    """Generate the full HTML page."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build leaderboard rows
    rows_html = ""
    for s in scores:
        delta_html = ""
        if s.get("prev_rank") is not None:
            diff = s["prev_rank"] - s["rank"]
            if diff > 0:
                delta_html = f'<span class="rank-up">▲{diff}</span>'
            elif diff < 0:
                delta_html = f'<span class="rank-down">▼{abs(diff)}</span>'
            else:
                delta_html = '<span class="rank-same">—</span>'

        fields_html = " ".join(f'<span class="field-tag">{f}</span>' for f in s.get("fields", []))

        twitter_link = f'<a href="https://x.com/{s["twitter_handle"]}" target="_blank">@{s["twitter_handle"]}</a>' if s.get("twitter_handle") else "—"
        github_link = f'<a href="https://github.com/{s["github_handle"]}" target="_blank">{s["github_handle"]}</a>' if s.get("github_handle") else "—"

        rows_html += f"""
        <tr>
            <td class="rank-cell">#{s['rank']} {delta_html}</td>
            <td><strong>{s['name']}</strong><br><small>{s.get('university', '')} '{str(s.get('grad_year', ''))[-2:]}</small></td>
            <td>{fields_html}</td>
            <td class="score-cell">{s['publication_score']}</td>
            <td class="score-cell">{s['social_score']}</td>
            <td class="score-cell">{s['builder_score']}</td>
            <td class="score-cell composite">{s['composite_score']}</td>
            <td>{twitter_link}</td>
            <td>{github_link}</td>
        </tr>"""

    # Build events feed
    events_html = ""
    for e in events[:30]:
        icon = "📄" if e.get("type") == "publication" else "🐦" if e.get("type") == "viral_tweet" else "⭐"
        events_html += f"""
        <div class="event-item">
            <span class="event-icon">{icon}</span>
            <span class="event-date">{e.get('date', '')}</span>
            <strong>{e.get('researcher', '')}</strong>: {e.get('description', '')}
        </div>"""

    if not events_html:
        events_html = '<div class="event-item"><em>No events yet — events will appear after the first scoring run with real data.</em></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Undergrad Researcher Leaderboard — Frontier Tech</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        :root {{
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #e6edf3;
            --text-muted: #8b949e;
            --accent: #58a6ff;
            --green: #3fb950;
            --red: #f85149;
            --yellow: #d29922;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 2rem; }}
        header {{
            text-align: center;
            padding: 3rem 0 2rem;
            border-bottom: 1px solid var(--border);
            margin-bottom: 2rem;
        }}
        header h1 {{ font-size: 2.2rem; margin-bottom: 0.5rem; }}
        header h1 span {{ color: var(--accent); }}
        header p {{ color: var(--text-muted); font-size: 1.1rem; }}
        .updated {{ color: var(--text-muted); font-size: 0.85rem; margin-top: 0.5rem; }}

        .section-title {{
            font-size: 1.4rem;
            margin: 2.5rem 0 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }}

        /* Leaderboard table */
        .table-wrapper {{ overflow-x: auto; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ background: var(--bg); color: var(--text-muted); font-weight: 600; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; cursor: pointer; }}
        th:hover {{ color: var(--accent); }}
        tr:hover {{ background: rgba(88, 166, 255, 0.05); }}
        .rank-cell {{ white-space: nowrap; }}
        .rank-up {{ color: var(--green); margin-left: 0.4rem; font-size: 0.85rem; }}
        .rank-down {{ color: var(--red); margin-left: 0.4rem; font-size: 0.85rem; }}
        .rank-same {{ color: var(--text-muted); margin-left: 0.4rem; font-size: 0.85rem; }}
        .score-cell {{ text-align: center; font-variant-numeric: tabular-nums; }}
        .score-cell.composite {{ font-weight: 700; color: var(--accent); font-size: 1.05rem; }}
        .field-tag {{
            display: inline-block;
            background: rgba(88, 166, 255, 0.15);
            color: var(--accent);
            padding: 0.15rem 0.5rem;
            border-radius: 12px;
            font-size: 0.75rem;
            margin: 0.1rem;
        }}
        a {{ color: var(--accent); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        small {{ color: var(--text-muted); }}

        /* Bump chart */
        .chart-container {{
            background: var(--surface);
            border-radius: 8px;
            padding: 1.5rem;
            border: 1px solid var(--border);
        }}
        canvas {{ max-height: 400px; }}

        /* Events feed */
        .events-feed {{
            background: var(--surface);
            border-radius: 8px;
            border: 1px solid var(--border);
            max-height: 500px;
            overflow-y: auto;
        }}
        .event-item {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.9rem;
        }}
        .event-item:last-child {{ border-bottom: none; }}
        .event-icon {{ margin-right: 0.5rem; }}
        .event-date {{ color: var(--text-muted); margin-right: 0.5rem; font-size: 0.8rem; }}

        /* Grid layout */
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
        }}
        @media (max-width: 900px) {{
            .grid-2 {{ grid-template-columns: 1fr; }}
        }}

        footer {{
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 0.85rem;
            border-top: 1px solid var(--border);
            margin-top: 3rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏆 Undergrad Researcher <span>Leaderboard</span></h1>
            <p>Tracking the most promising undergraduate researchers in AI, hardware, robotics, crypto & defense tech</p>
            <div class="updated">Last updated: {now}</div>
        </header>

        <h2 class="section-title">📊 Rankings</h2>
        <div class="table-wrapper">
            <table id="leaderboard">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Rank</th>
                        <th onclick="sortTable(1)">Researcher</th>
                        <th>Fields</th>
                        <th onclick="sortTable(3)">Pubs</th>
                        <th onclick="sortTable(4)">Social</th>
                        <th onclick="sortTable(5)">Builder</th>
                        <th onclick="sortTable(6)">Score</th>
                        <th>Twitter</th>
                        <th>GitHub</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>

        <div class="grid-2">
            <div>
                <h2 class="section-title">📈 Rank Trajectory (Bump Chart)</h2>
                <div class="chart-container">
                    <canvas id="bumpChart"></canvas>
                    <p id="bumpEmpty" style="color: var(--text-muted); text-align: center; padding: 2rem; display: none;">
                        Bump chart will populate after 2+ weeks of data.
                    </p>
                </div>
            </div>
            <div>
                <h2 class="section-title">🗞️ Event Feed</h2>
                <div class="events-feed">
                    {events_html}
                </div>
            </div>
        </div>
    </div>

    <footer>
        Paradigm · Updated weekly via GitHub Actions ·
        <a href="https://github.com/paradigm-operations/undergrad-researcher-leaderboard">Source</a>
    </footer>

    <script>
    // Sortable table
    let sortDir = {{}};
    function sortTable(col) {{
        const table = document.getElementById('leaderboard');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));

        sortDir[col] = !sortDir[col];

        rows.sort((a, b) => {{
            let aVal = a.cells[col].textContent.trim();
            let bVal = b.cells[col].textContent.trim();
            let aNum = parseFloat(aVal.replace(/[^\\d.-]/g, ''));
            let bNum = parseFloat(bVal.replace(/[^\\d.-]/g, ''));

            if (!isNaN(aNum) && !isNaN(bNum)) {{
                return sortDir[col] ? aNum - bNum : bNum - aNum;
            }}
            return sortDir[col] ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
        }});

        rows.forEach(r => tbody.appendChild(r));
    }}

    // Bump chart
    const bumpData = {bump_data};
    if (bumpData.dates && bumpData.dates.length >= 2) {{
        const colors = [
            '#58a6ff', '#3fb950', '#f85149', '#d29922', '#bc8cff',
            '#f778ba', '#79c0ff', '#56d364', '#ffa657', '#ff7b72'
        ];
        const datasets = bumpData.series.map((s, i) => ({{
            label: s.name,
            data: s.data.map(d => d.rank),
            borderColor: colors[i % colors.length],
            backgroundColor: colors[i % colors.length],
            tension: 0.3,
            pointRadius: 4,
            pointHoverRadius: 6,
        }}));

        new Chart(document.getElementById('bumpChart'), {{
            type: 'line',
            data: {{
                labels: bumpData.dates,
                datasets: datasets,
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ labels: {{ color: '#e6edf3' }} }},
                }},
                scales: {{
                    y: {{
                        reverse: true,
                        title: {{ display: true, text: 'Rank', color: '#8b949e' }},
                        ticks: {{ color: '#8b949e', stepSize: 1 }},
                        grid: {{ color: '#30363d' }},
                    }},
                    x: {{
                        ticks: {{ color: '#8b949e' }},
                        grid: {{ color: '#30363d' }},
                    }},
                }},
            }},
        }});
    }} else {{
        document.getElementById('bumpChart').style.display = 'none';
        document.getElementById('bumpEmpty').style.display = 'block';
    }}
    </script>
</body>
</html>"""


def main():
    print("Generating leaderboard site...")

    scores = json.loads((DATA / "scores.json").read_text()) if (DATA / "scores.json").exists() else []
    events = json.loads((DATA / "events.json").read_text()) if (DATA / "events.json").exists() else []
    history = load_history()
    bump_data = build_bump_chart_data(history)

    DOCS.mkdir(exist_ok=True)
    html = generate_html(scores, events, bump_data)
    (DOCS / "index.html").write_text(html)
    # Also write to repo root for GitHub Pages compatibility
    (ROOT / "index.html").write_text(html)
    print(f"✅ Site generated at {DOCS / 'index.html'} (and repo root)")


if __name__ == "__main__":
    main()
