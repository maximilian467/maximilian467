"""Draws the README card as two SVGs (light and dark) in the design of maximilian467.github.io.

Inputs: data/profile.json (text), data/tokens.json (synced from my laptop by scripts/sync-tokens.mjs)
and public GitHub data (contribution calendar, star counts). Standard library only.

    GITHUB_TOKEN=... python scripts/generate_card.py
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# Same tokens as src/styles/tokens.css on the website.
THEMES = {
    "light": {"paper": "#f6f4ef", "ink": "#1c1b18", "muted": "#6a665e", "rule": "#dedad1", "accent": "#b4471d", "accent_ink": "#8f3614"},
    "dark": {"paper": "#151412", "ink": "#ece8df", "muted": "#9c978c", "rule": "#2e2c28", "accent": "#e0703f", "accent_ink": "#e88a5e"},
}
FONTS = {
    "Instrument Serif": "instrument-serif-latin-400-normal.woff2",
    "Geist": "geist-latin-wght-normal.woff2",
    "Geist Mono": "geist-mono-latin-wght-normal.woff2",
}
SERIF = "'Instrument Serif', Georgia, serif"
SANS = "Geist, 'Segoe UI', system-ui, sans-serif"
MONO = "'Geist Mono', ui-monospace, Consolas, monospace"

WIDTH, PAD, LABEL_W = 880, 44, 172


def graphql(query: str, variables: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set")
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "readme-card"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    return payload["data"]


def fetch_github(login: str, repos: list[str]) -> dict:
    repo_fields = "\n".join(f'r{i}: repository(owner: $login, name: "{name}") {{ stargazerCount }}' for i, name in enumerate(repos))
    query = f"""query($login: String!) {{
      user(login: $login) {{ contributionsCollection {{ contributionCalendar {{ weeks {{ contributionDays {{ date contributionCount }} }} }} }} }}
      {repo_fields}
    }}"""
    data = graphql(query, {"login": login})
    days = [d for week in data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"] for d in week["contributionDays"]]
    days = [d for d in days if d["date"] <= date.today().isoformat()]
    stars = {name: data[f"r{i}"]["stargazerCount"] for i, name in enumerate(repos)}
    return {"activity": [d["contributionCount"] for d in days[-30:]], "stars": stars}


def font_faces() -> str:
    rules = []
    for family, file in FONTS.items():
        encoded = base64.b64encode((ASSETS / "fonts" / file).read_bytes()).decode()
        rules.append(f"@font-face{{font-family:'{family}';src:url(data:font/woff2;base64,{encoded}) format('woff2');font-weight:100 900;}}")
    return "".join(rules)


def text(x: float, y: float, content: str, *, font: str, size: float, fill: str, weight: int = 400, anchor: str = "start", spacing: float = 0) -> str:
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{extra}>{escape(content)}</text>')


def rule(y: float, color: str) -> str:
    return f'<line x1="{PAD}" y1="{y:.1f}" x2="{WIDTH - PAD}" y2="{y:.1f}" stroke="{color}" stroke-width="1"/>'


def section_title(y: float, title: str, t: dict, x: float = PAD) -> str:
    # The website marks section titles with a thin accent bar on the left.
    return (f'<rect x="{x}" y="{y - 17:.1f}" width="2" height="22" fill="{t["accent"]}"/>'
            + text(x + 12, y, title, font=SERIF, size=22, fill=t["ink"]))


def activity_path(values: list[int], x: float, y: float, w: float, h: float) -> tuple[str, str]:
    """Line and area through the daily counts. Scaled to the busiest day, no axis values on purpose."""
    peak = max(values) or 1
    step = w / (len(values) - 1)
    points = [(x + i * step, y + h - (v / peak) * h) for i, v in enumerate(values)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
    area = f"{x:.1f},{y + h:.1f} {line} {x + w:.1f},{y + h:.1f}"
    return line, area


def format_since(day: str) -> str:
    return datetime.strptime(day, "%Y-%m-%d").strftime("%b %Y").lower()


def render(theme: str, profile: dict, github: dict, tokens: dict, synced: str) -> str:
    t = THEMES[theme]
    parts: list[str] = []
    y = PAD + 4

    # Header: path on the left, location on the right, then name and intro.
    parts.append(text(PAD, y, f"{profile['login']} / README", font=MONO, size=12, fill=t["muted"]))
    parts.append(text(WIDTH - PAD, y, profile["location"], font=MONO, size=12, fill=t["muted"], anchor="end"))
    y += 18
    parts.append(rule(y, t["rule"]))
    y += 66
    parts.append(text(PAD - 2, y, profile["name"], font=SERIF, size=56, fill=t["ink"], spacing=-0.5))
    y += 36
    for line in profile["intro"]:
        parts.append(text(PAD, y, line, font=SANS, size=16, fill=t["muted"]))
        y += 24
    y += 14
    parts.append(rule(y, t["rule"]))

    # Now
    y += 46
    parts.append(section_title(y, "Now", t))
    parts.append(text(PAD + LABEL_W, y - 2, profile["now"]["text"], font=SANS, size=15, fill=t["ink"]))
    parts.append(f'<circle cx="{PAD + LABEL_W + 4}" cy="{y + 17:.1f}" r="3" fill="{t["accent"]}"/>')
    parts.append(text(PAD + LABEL_W + 14, y + 21, profile["now"]["status"], font=MONO, size=12, fill=t["muted"]))
    y += 46
    parts.append(rule(y, t["rule"]))

    # Selected work: title, one line, and a stat on the right.
    y += 46
    parts.append(section_title(y, "Selected work", t))
    for i, item in enumerate(profile["work"]):
        row_y = y - 2 + i * 50
        stat = item["stat"]
        label = f"{github['stars'][stat['stars']]} stars" if "stars" in stat else stat["text"]
        color = t["accent_ink"] if stat.get("accent") else t["muted"]
        parts.append(text(PAD + LABEL_W, row_y, item["title"], font=SANS, size=15, fill=t["ink"], weight=600))
        parts.append(text(PAD + LABEL_W, row_y + 20, item["line"], font=SANS, size=13.5, fill=t["muted"]))
        parts.append(text(WIDTH - PAD, row_y, label, font=MONO, size=12, fill=color, weight=600 if stat.get("accent") else 400, anchor="end"))
    y += (len(profile["work"]) - 1) * 50 + 40
    parts.append(rule(y, t["rule"]))

    # Activity line (left) and Claude Code tokens (right).
    y += 46
    half = (WIDTH - 2 * PAD) / 2
    right = PAD + half + 28
    parts.append(section_title(y, "Activity", t))
    parts.append(section_title(y, "Tokens", t, x=right))
    chart_y, chart_h, chart_w = y + 26, 74, half - 36
    line, area = activity_path(github["activity"], PAD, chart_y, chart_w, chart_h)
    parts.append(f'<polygon points="{area}" fill="{t["accent"]}" fill-opacity="0.10"/>')
    parts.append(f'<polyline points="{line}" fill="none" stroke="{t["accent"]}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>')
    parts.append(f'<line x1="{PAD}" y1="{chart_y + chart_h:.1f}" x2="{PAD + chart_w:.1f}" y2="{chart_y + chart_h:.1f}" stroke="{t["rule"]}" stroke-width="1"/>')
    parts.append(text(PAD, chart_y + chart_h + 20, "contributions, last 30 days", font=MONO, size=11, fill=t["muted"]))
    parts.append(text(PAD + chart_w, chart_y + chart_h + 20, "today", font=MONO, size=11, fill=t["muted"], anchor="end"))
    parts.append(text(right, y + 66, f"{tokens['total']:,}", font=SERIF, size=46, fill=t["ink"], spacing=-0.5))
    parts.append(text(right, y + 92, "tokens processed with Claude Code", font=MONO, size=11.5, fill=t["muted"]))
    parts.append(text(right, y + 110, f"incl. cache reads, since {format_since(tokens['since'])}", font=MONO, size=11.5, fill=t["muted"]))
    y = chart_y + chart_h + 46
    parts.append(rule(y, t["rule"]))

    # Footer
    y += 24
    parts.append(text(PAD, y, "regenerated every 12 h by github actions", font=MONO, size=11, fill=t["muted"]))
    parts.append(text(WIDTH - PAD, y, f"tokens synced {synced}", font=MONO, size=11, fill=t["muted"], anchor="end"))
    height = y + PAD - 10

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height:.0f}" viewBox="0 0 {WIDTH} {height:.0f}" '
            f'role="img" aria-label="{escape(profile["name"])}: current work, selected projects, recent activity and Claude Code tokens">'
            f"<style>{font_faces()}</style>"
            f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1:.0f}" rx="8" fill="{t["paper"]}" stroke="{t["rule"]}"/>'
            + "".join(parts) + "</svg>\n")


def main() -> None:
    profile = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
    tokens = json.loads((ROOT / "data" / "tokens.json").read_text(encoding="utf-8"))
    repos = [item["stat"]["stars"] for item in profile["work"] if "stars" in item["stat"]]
    github = fetch_github(profile["login"], repos)
    # The footer shows when the token count was last synced, so the card only changes when data changes.
    synced = tokens["updated"][:10]
    for theme in THEMES:
        svg = render(theme, profile, github, tokens, synced)
        ElementTree.fromstring(svg)  # fail the run instead of publishing a broken image
        (ASSETS / f"card-{theme}.svg").write_text(svg, encoding="utf-8")
    print(f"Card written: {sum(github['activity'])} contributions in 30 days, stars {github['stars']}, {tokens['total']:,} tokens")


if __name__ == "__main__":
    main()
