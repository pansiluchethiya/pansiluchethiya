#!/usr/bin/env python3
"""Build the self-hosted GitHub stats, language, streak, and calendar cards."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from html import escape
from pathlib import Path

from lib import (
    BG,
    BLUE,
    BORDER,
    DIM,
    FONT,
    GREEN,
    MONO,
    MUTED,
    ORANGE,
    PANEL,
    PINK,
    PURPLE,
    TEXT,
    YELLOW,
    date_label,
    fmt_int,
    graphql,
    load_profile,
    svg_text,
    utc_now,
    write_json,
    write_svg,
)

QUERY = """
query ProfileStats($login: String!) {
  user(login: $login) {
    login
    name
    bio
    location
    websiteUrl
    twitterUsername
    createdAt
    followers { totalCount }
    following { totalCount }
    repositories(
      ownerAffiliations: [OWNER]
      privacy: PUBLIC
      first: 100
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      totalCount
      nodes {
        name
        description
        url
        homepageUrl
        stargazerCount
        forkCount
        isFork
        isArchived
        updatedAt
        primaryLanguage { name color }
        repositoryTopics(first: 20) { nodes { topic { name } } }
        languages(first: 100, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      restrictedContributionsCount
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount weekday }
        }
      }
    }
  }
}
"""

LEVEL_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
INFRA_LANGUAGES = {
    "Dockerfile",
    "Shell",
    "PowerShell",
    "Batchfile",
    "Makefile",
    "Procfile",
    "Roff",
}


def human_bytes(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} MB"
    if value >= 1_000:
        return f"{value / 1_000:.1f} kB"
    return f"{value} B"


def collect_contributions(collection: dict):
    weeks = collection["contributionCalendar"]["weeks"]
    by_date: dict[str, dict] = {}
    for week in weeks:
        for day in week["contributionDays"]:
            by_date[day["date"]] = day
    days = [by_date[key] for key in sorted(by_date)]
    if not days:
        return weeks, days, 0, 0, 0, {"date": "", "count": 0}, 0

    counts = {day["date"]: day["contributionCount"] for day in days}
    total = collection["contributionCalendar"]["totalContributions"]

    # GitHub keeps a streak alive until the end of the day, so if today is
    # empty, start counting from yesterday.
    cursor = date.fromisoformat(days[-1]["date"])
    if counts.get(cursor.isoformat(), 0) == 0:
        cursor -= timedelta(days=1)
    current = 0
    while counts.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    longest = run = 0
    for day in days:
        if day["contributionCount"] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    active_days = sum(1 for day in days if day["contributionCount"] > 0)
    best = max(days, key=lambda day: day["contributionCount"])
    return weeks, days, current, longest, active_days, best, total


def contribution_level(count: int, nonzero: list[int]) -> int:
    if count <= 0:
        return 0
    if len(set(nonzero)) <= 1:
        return 2
    rank = sum(1 for value in nonzero if value <= count) / len(nonzero)
    if rank <= 0.25:
        return 1
    if rank <= 0.50:
        return 2
    if rank <= 0.75:
        return 3
    return 4


def month_labels(weeks: list[dict]) -> str:
    out = []
    last_month = None
    last_x = -100.0
    for index, week in enumerate(weeks):
        first_day = week["contributionDays"][0]["date"]
        parsed = date.fromisoformat(first_day)
        if parsed.month == last_month:
            continue
        x = 58 + index * 14
        if x - last_x < 32:
            continue
        out.append(
            f'<text x="{x:.0f}" y="86" font-family="{FONT}" font-size="10" '
            f'fill="{MUTED}">{parsed.strftime("%b")}</text>'
        )
        last_month = parsed.month
        last_x = x
    return "\n".join(out)


def stats_svg(profile: dict, data: dict) -> str:
    login = svg_text(profile["login"])
    updated = utc_now().strftime("%d %b %Y · %H:%M UTC")
    best_day = data["best_day"]
    top = data["top_language"] or "—"
    top_pct = data["top_language_percent"]
    private = data["private_contributions"]
    tiles = [
        ("Repositories", fmt_int(data["repositories"]), "public · forks included", GREEN),
        ("Stars earned", fmt_int(data["stars"]), f"across {fmt_int(data['starred_repositories'])} repos", YELLOW),
        ("Contributions", fmt_int(data["contributions"]), "last 12 months", BLUE),
        (
            "Private contributions",
            fmt_int(private),
            "shared with GitHub" if private else "none shared",
            PURPLE,
        ),
        (
            "Best day",
            fmt_int(best_day["count"]),
            date_label(best_day["date"]) if best_day["date"] else "no activity yet",
            ORANGE,
        ),
        ("Top language", top, f"{top_pct:.1f}% of tracked code", PINK),
    ]

    tile_markup = []
    for index, (label, value, sub, accent) in enumerate(tiles):
        col = index % 3
        row = index // 3
        x = 24 + col * 274
        y = 86 + row * 96
        value_size = 30 if len(str(value)) <= 10 else 24
        tile_markup.append(
            f"""
  <g>
    <rect x="{x}" y="{y}" width="260" height="82" rx="10" fill="{PANEL}" stroke="#21262d"/>
    <text x="{x + 18}" y="{y + 24}" font-family="{FONT}" font-size="10.5" font-weight="600"
      letter-spacing="1.1" fill="{accent}">{svg_text(label.upper())}</text>
    <text x="{x + 18}" y="{y + 59}" font-family="{FONT}" font-size="{value_size}" font-weight="700"
      fill="{TEXT}">{svg_text(value)}</text>
    <text x="{x + 18}" y="{y + 75}" font-family="{FONT}" font-size="10.5"
      fill="{DIM}">{svg_text(sub)}</text>
  </g>"""
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="300" viewBox="0 0 860 300" role="img" aria-labelledby="statsTitle statsDesc">
  <title id="statsTitle">GitHub stats for {login}</title>
  <desc id="statsDesc">Repositories, stars earned, contributions, private contributions, best day, and top language for {login}.</desc>
  <rect width="860" height="300" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="859" height="299" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="40" font-family="{FONT}" font-size="20" font-weight="700" fill="{TEXT}">GitHub stats</text>
  <text x="28" y="62" font-family="{FONT}" font-size="11.5" fill="{MUTED}">@{login} · owned public repositories · last 12 months</text>
  <text x="832" y="40" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{DIM}">{svg_text(updated)}</text>
  {''.join(tile_markup)}
  <text x="28" y="286" font-family="{FONT}" font-size="10.5" fill="{DIM}">Rebuilt daily from the GitHub API · private contribution count only appears if shared</text>
</svg>"""


def languages_svg(profile: dict, languages: list[dict], repo_count: int, total_bytes: int) -> str:
    rows = languages[:6]
    height = 96 + len(rows) * 30 + 34
    updated = utc_now().strftime("%d %b %Y")
    bars = []
    for index, language in enumerate(rows):
        y = 96 + index * 30
        width = max(3.0, 560 * (language["percent"] / 100))
        bars.append(
            f"""
  <g>
    <text x="28" y="{y + 10}" font-family="{FONT}" font-size="13" fill="{TEXT}">{svg_text(language['name'])}</text>
    <rect x="170" y="{y}" width="560" height="9" rx="4.5" fill="#21262d"/>
    <rect x="170" y="{y}" width="{width:.1f}" height="9" rx="4.5" fill="{language['color']}"/>
    <text x="832" y="{y + 9}" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{MUTED}">{language['percent']:.1f}%</text>
  </g>"""
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="{height}" viewBox="0 0 860 {height}" role="img" aria-labelledby="langTitle langDesc">
  <title id="langTitle">Top languages for {svg_text(profile['login'])}</title>
  <desc id="langDesc">Code volume by language across {repo_count} public repositories.</desc>
  <rect width="860" height="{height}" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="859" height="{height - 1}" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="40" font-family="{FONT}" font-size="20" font-weight="700" fill="{TEXT}">Top languages</text>
  <text x="28" y="62" font-family="{FONT}" font-size="11.5" fill="{MUTED}">By code volume across public repositories</text>
  <text x="832" y="40" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{DIM}">{updated}</text>
  {''.join(bars)}
  <text x="28" y="{height - 18}" font-family="{FONT}" font-size="10.5" fill="{DIM}">Aggregated from {repo_count} repositories · {human_bytes(total_bytes)} of tracked code · vendored and generated files included</text>
</svg>"""


def streak_svg(profile: dict, data: dict) -> str:
    login = svg_text(profile["login"])
    current = data["current_streak"]
    longest = data["longest_streak"]
    active = data["active_days"]
    tracked = data["tracked_days"]
    current_sub = "keep it going" if current else "no active streak"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="168" viewBox="0 0 860 168" role="img" aria-labelledby="streakTitle streakDesc">
  <title id="streakTitle">Contribution streak for {login}</title>
  <desc id="streakDesc">Current streak: {current} days. Longest streak: {longest} days. Active days: {active} of {tracked}.</desc>
  <rect width="860" height="168" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="859" height="167" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="40" font-family="{FONT}" font-size="20" font-weight="700" fill="{TEXT}">Contribution streak</text>
  <text x="28" y="61" font-family="{FONT}" font-size="11.5" fill="{MUTED}">Current run, personal best, and days that counted</text>
  <line x1="300" y1="82" x2="300" y2="146" stroke="{BORDER}"/>
  <line x1="580" y1="82" x2="580" y2="146" stroke="{BORDER}"/>
  <text x="28" y="91" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{GREEN}">CURRENT STREAK</text>
  <text x="28" y="125" font-family="{FONT}" font-size="30" font-weight="700" fill="{TEXT}">{current}</text>
  <text x="{28 + 20 + len(str(current)) * 17}" y="125" font-family="{FONT}" font-size="15" font-weight="500" fill="{MUTED}">days</text>
  <text x="28" y="145" font-family="{FONT}" font-size="10.5" fill="{DIM}">{current_sub}</text>
  <text x="324" y="91" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{BLUE}">LONGEST STREAK</text>
  <text x="324" y="125" font-family="{FONT}" font-size="30" font-weight="700" fill="{TEXT}">{longest}</text>
  <text x="{324 + 20 + len(str(longest)) * 17}" y="125" font-family="{FONT}" font-size="15" font-weight="500" fill="{MUTED}">days</text>
  <text x="324" y="145" font-family="{FONT}" font-size="10.5" fill="{DIM}">in the last 12 months</text>
  <text x="604" y="91" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{PURPLE}">ACTIVE DAYS</text>
  <text x="604" y="125" font-family="{FONT}" font-size="30" font-weight="700" fill="{TEXT}">{active}</text>
  <text x="{604 + 20 + len(str(active)) * 17}" y="125" font-family="{FONT}" font-size="15" font-weight="500" fill="{MUTED}">of {tracked}</text>
  <text x="604" y="145" font-family="{FONT}" font-size="10.5" fill="{DIM}">at least one contribution</text>
</svg>"""


def contributions_svg(profile: dict, weeks: list[dict], total: int, private: int) -> str:
    login = svg_text(profile["login"])
    nonzero = [
        day["contributionCount"]
        for week in weeks
        for day in week["contributionDays"]
        if day["contributionCount"] > 0
    ]
    cells = []
    for week_index, week in enumerate(weeks):
        for day in week["contributionDays"]:
            x = 58 + week_index * 14
            y = 96 + day["weekday"] * 14
            count = day["contributionCount"]
            level = contribution_level(count, nonzero)
            label = f"{count} contribution{'s' if count != 1 else ''} on {date_label(day['date'])}"
            cells.append(
                f'<rect x="{x}" y="{y}" width="11" height="11" rx="2" fill="{LEVEL_COLORS[level]}">'
                f"<title>{svg_text(label)}</title></rect>"
            )

    day_labels = []
    for weekday, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        day_labels.append(
            f'<text x="50" y="{96 + weekday * 14 + 9}" text-anchor="end" '
            f'font-family="{FONT}" font-size="9.5" fill="{MUTED}">{label}</text>'
        )

    legend_x = 686
    legend = [
        f'<text x="{legend_x}" y="205" text-anchor="end" font-family="{FONT}" font-size="9.5" fill="{MUTED}">Less</text>'
    ]
    for index, color in enumerate(LEVEL_COLORS):
        legend.append(
            f'<rect x="{legend_x + 8 + index * 14}" y="196" width="11" height="11" rx="2" fill="{color}"/>'
        )
    legend.append(
        f'<text x="{legend_x + 84}" y="205" font-family="{FONT}" font-size="9.5" fill="{MUTED}">More</text>'
    )

    note = (
        "Private contributions are included because they are shared with GitHub."
        if private
        else "Public contributions only. Private contributions are not shared."
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="220" viewBox="0 0 860 220" role="img" aria-labelledby="calTitle calDesc">
  <title id="calTitle">Contribution graph for {login}</title>
  <desc id="calDesc">{total} contributions in the last 12 months. {note}</desc>
  <rect width="860" height="220" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="859" height="219" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="40" font-family="{FONT}" font-size="20" font-weight="700" fill="{TEXT}">Contribution graph</text>
  <text x="832" y="40" text-anchor="end" font-family="{MONO}" font-size="11.5" fill="{MUTED}">{fmt_int(total)} contributions in the last year</text>
  <text x="28" y="62" font-family="{FONT}" font-size="11.5" fill="{MUTED}">Every green square is a day I showed up.</text>
  {month_labels(weeks)}
  {''.join(day_labels)}
  {''.join(cells)}
  <text x="28" y="205" font-family="{FONT}" font-size="9.5" fill="{DIM}">{svg_text(note)}</text>
  {''.join(legend)}
</svg>"""


def activity_svg(profile: dict, days: list[dict]) -> str:
    """Bar chart of the last 30 days of contributions."""
    login = svg_text(profile["login"])
    recent = days[-30:]
    if not recent:
        recent = []
    counts = [day["contributionCount"] for day in recent] or [0]
    peak = max(counts) or 1
    total = sum(counts)
    average = total / len(counts) if counts else 0

    bars = []
    for index, day in enumerate(recent):
        count = day["contributionCount"]
        height = 4 + (count / peak) * 88 if peak else 4
        x = 30 + index * 24
        y = 168 - height
        color = GREEN if count else "#21262d"
        bars.append(
            f'<rect x="{x}" y="{y:.1f}" width="15" height="{height:.1f}" rx="3" fill="{color}">'
            f"<title>{svg_text(f'{count} contribution' + ('s' if count != 1 else '') + ' on ' + date_label(day['date']))}</title></rect>"
        )

    labels = []
    for index, day in enumerate(recent):
        if index % 6 == 0:
            labels.append(
                f'<text x="{30 + index * 24 + 7}" y="188" text-anchor="middle" '
                f'font-family="{MONO}" font-size="9.5" fill="{DIM}">'
                f"{svg_text(date.fromisoformat(day['date']).strftime('%d %b'))}</text>"
            )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="220" viewBox="0 0 860 220" role="img" aria-labelledby="actTitle actDesc">
  <title id="actTitle">Contribution activity for {login}</title>
  <desc id="actDesc">{total} contributions in the last 30 days, averaging {average:.1f} per day.</desc>
  <rect width="860" height="220" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="859" height="219" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="40" font-family="{FONT}" font-size="20" font-weight="700" fill="{TEXT}">Contribution activity</text>
  <text x="28" y="62" font-family="{FONT}" font-size="11.5" fill="{MUTED}">Last 30 days, one bar per day</text>
  <text x="832" y="40" text-anchor="end" font-family="{MONO}" font-size="11" fill="{DIM}">{fmt_int(total)} in 30d · avg {average:.1f}/day</text>
  <text x="832" y="62" text-anchor="end" font-family="{MONO}" font-size="11" fill="{DIM}">peak {fmt_int(peak)} in one day</text>
  <line x1="30" y1="168" x2="756" y2="168" stroke="{BORDER}"/>
  {''.join(bars)}
  {''.join(labels)}
  <text x="28" y="206" font-family="{FONT}" font-size="10.5" fill="{DIM}">Pull requests, issues, reviews and commits are all counted.</text>
</svg>"""


def trophies_svg(profile: dict, data: dict) -> str:
    """Trophy-style summary of the account's public numbers."""
    login = svg_text(profile["login"])
    trophies = [
        ("Stars earned", fmt_int(data["stars"]), f"across {fmt_int(data['starred_repositories'])} repositories", YELLOW),
        ("Followers", fmt_int(data["followers"]), "people watching this account", BLUE),
        ("Commits", fmt_int(data["commits"]), "in the last 12 months", GREEN),
        ("Repositories", fmt_int(data["repositories"]), "public, forks included", PURPLE),
        ("Pull requests", fmt_int(data["pull_requests"]), "in the last 12 months", PINK),
        ("Issues", fmt_int(data["issues"]), "in the last 12 months", ORANGE),
    ]

    cells = []
    star = (
        "M0,-12 L3.4,-4.2 L11.8,-3.1 L5.4,2.9 L7.4,11.3 L0,6.7 L-7.4,11.3 "
        "L-5.4,2.9 L-11.8,-3.1 L-3.4,-4.2 Z"
    )
    for index, (label, value, sub, accent) in enumerate(trophies):
        col = index % 3
        row = index // 3
        x = 24 + col * 274
        y = 74 + row * 104
        cells.append(
            f"""
  <g>
    <rect x="{x}" y="{y}" width="260" height="90" rx="12" fill="{PANEL}" stroke="#21262d"/>
    <circle cx="{x + 40}" cy="{y + 45}" r="22" fill="none" stroke="{accent}" stroke-width="1.5" opacity="0.85"/>
    <path d="{star}" fill="{accent}" transform="translate({x + 40},{y + 45})"/>
    <text x="{x + 78}" y="{y + 34}" font-family="{FONT}" font-size="10.5" font-weight="600"
      letter-spacing="1" fill="{accent}">{svg_text(label.upper())}</text>
    <text x="{x + 78}" y="{y + 62}" font-family="{FONT}" font-size="26" font-weight="700" fill="{TEXT}">{svg_text(value)}</text>
    <text x="{x + 78}" y="{y + 79}" font-family="{FONT}" font-size="10.5" fill="{DIM}">{svg_text(sub)}</text>
  </g>"""
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="300" viewBox="0 0 860 300" role="img" aria-labelledby="troTitle troDesc">
  <title id="troTitle">Trophy summary for {login}</title>
  <desc id="troDesc">Stars, followers, commits, repositories, pull requests and issues for {login}.</desc>
  <defs>
    <linearGradient id="medalGold" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f0c674"/>
      <stop offset="100%" stop-color="#b8860b"/>
    </linearGradient>
  </defs>
  <rect width="860" height="300" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="859" height="299" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="40" font-family="{FONT}" font-size="20" font-weight="700" fill="{TEXT}">Trophies</text>
  <text x="28" y="62" font-family="{FONT}" font-size="11.5" fill="{MUTED}">Public numbers, rendered locally so they never go stale</text>
  <text x="832" y="40" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{DIM}">@{login}</text>
  {''.join(cells)}
  <text x="28" y="286" font-family="{FONT}" font-size="10.5" fill="{DIM}">Rebuilt daily from the GitHub GraphQL API</text>
</svg>"""


def main() -> None:
    profile = load_profile()
    login = profile["login"]
    payload = graphql(QUERY, {"login": login})
    user = payload["user"]
    if not user:
        raise SystemExit(f"GitHub user not found: {login}")

    repos = user["repositories"]["nodes"]
    language_totals: dict[str, int] = defaultdict(int)
    language_colors: dict[str, str] = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            language_totals[name] += int(edge["size"])
            language_colors[name] = edge["node"].get("color") or "#8b949e"

    total_bytes = sum(language_totals.values())
    language_rows = []
    for name, size in sorted(language_totals.items(), key=lambda item: item[1], reverse=True):
        if name in INFRA_LANGUAGES:
            continue
        language_rows.append(
            {
                "name": name,
                "bytes": size,
                "percent": (size / total_bytes * 100) if total_bytes else 0.0,
                "color": language_colors.get(name, "#8b949e"),
            }
        )

    top_language = language_rows[0] if language_rows else {"name": "—", "percent": 0.0, "bytes": 0}
    stars = sum(repo["stargazerCount"] for repo in repos)
    starred_repositories = sum(1 for repo in repos if repo["stargazerCount"] > 0)
    fork_count = sum(1 for repo in repos if repo["isFork"])
    collection = user["contributionsCollection"]
    weeks, days, current, longest, active_days, best, total = collect_contributions(collection)
    private = int(collection["restrictedContributionsCount"])

    data = {
        "generated_at": utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "login": login,
        "name": user.get("name") or profile.get("name") or login,
        "bio": user.get("bio") or "",
        "repositories": int(user["repositories"]["totalCount"]),
        "original_repositories": int(user["repositories"]["totalCount"]) - fork_count,
        "forks": fork_count,
        "stars": stars,
        "starred_repositories": starred_repositories,
        "followers": int(user["followers"]["totalCount"]),
        "following": int(user["following"]["totalCount"]),
        "contributions": int(total),
        "commits": int(collection["totalCommitContributions"]),
        "pull_requests": int(collection["totalPullRequestContributions"]),
        "issues": int(collection["totalIssueContributions"]),
        "private_contributions": private,
        "current_streak": current,
        "longest_streak": longest,
        "active_days": active_days,
        "tracked_days": len(days),
        "best_day": {"date": best["date"], "count": int(best["count"] if "count" in best else best["contributionCount"])},
        "top_language": top_language["name"],
        "top_language_percent": round(top_language["percent"], 1),
        "top_language_bytes": int(top_language["bytes"]),
        "total_language_bytes": total_bytes,
        "languages": [
            {
                "name": row["name"],
                "bytes": int(row["bytes"]),
                "percent": round(row["percent"], 1),
                "color": row["color"],
            }
            for row in language_rows[:8]
        ],
        "public_repositories": [
            {
                "name": repo["name"],
                "description": repo.get("description") or "",
                "url": repo["url"],
                "stars": int(repo["stargazerCount"]),
                "forks": int(repo["forkCount"]),
                "language": (repo.get("primaryLanguage") or {}).get("name") or "",
                "updated_at": repo["updatedAt"],
            }
            for repo in repos
        ],
        "recent_activity": [
            {"date": day["date"], "count": int(day["contributionCount"])} for day in days[-30:]
        ],
    }

    write_json("data/profile.json", data)
    write_svg("assets/github-stats.svg", stats_svg(profile, data))
    write_svg(
        "assets/top-languages.svg",
        languages_svg(profile, language_rows, int(user["repositories"]["totalCount"]), total_bytes),
    )
    write_svg("assets/streak.svg", streak_svg(profile, data))
    write_svg("assets/contributions.svg", contributions_svg(profile, weeks, total, private))
    write_svg("assets/activity.svg", activity_svg(profile, days))
    write_svg("assets/trophies.svg", trophies_svg(profile, data))

    print(
        f"Generated stats for {login}: {data['repositories']} repos, {data['stars']} stars, "
        f"{data['contributions']} contributions, {current}/{longest} day streaks."
    )


if __name__ == "__main__":
    main()
