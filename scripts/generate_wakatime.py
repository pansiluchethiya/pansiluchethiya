#!/usr/bin/env python3
"""Render a compact WakaTime card when WAKATIME_API_KEY is configured.

The WakaTime statistics endpoints only report *human* coding time, so accounts
whose sessions are tracked as AI coding show zero there. The card is therefore
built from the raw durations endpoint, which contains every tracked session,
with the statistics endpoint used as a fallback.
"""

from __future__ import annotations

import base64
import collections
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from lib import (
    BG,
    BLUE,
    BORDER,
    DIM,
    FONT,
    GREEN,
    MONO,
    MUTED,
    PANEL,
    PURPLE,
    TEXT,
    svg_text,
    write_svg,
)

API_ROOT = "https://wakatime.com/api/v1"
CARD_WIDTH = 860
CARD_HEIGHT = 340
WINDOW_DAYS = 7


def api_key() -> str:
    key = os.environ.get("WAKATIME_API_KEY", "").strip()
    if not key:
        print("WAKATIME_API_KEY is not set; leaving the WakaTime section disabled.")
        sys.exit(0)
    return key


def get_json(path: str, key: str):
    url = API_ROOT + path
    req = urllib.request.Request(url)
    credential = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {credential}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "pansiluchethiya-profile-readme")

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise SystemExit(
                    "WakaTime rejected WAKATIME_API_KEY (401). Check the repository secret."
                ) from exc
            if exc.code < 500 or attempt == 2:
                raise SystemExit(f"WakaTime API error {exc.code} for {path}.") from exc
        except urllib.error.URLError as exc:
            if attempt == 2:
                raise SystemExit(f"WakaTime API request failed for {path}: {exc.reason}") from exc
        time.sleep(2 ** attempt)
    raise SystemExit(f"WakaTime API request failed for {path}.")


def human_duration(seconds: float) -> str:
    total_minutes = int(seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def collect_durations(key: str) -> dict:
    """Sum every tracked session over the last seven days."""
    today = datetime.now(timezone.utc).date()
    languages: collections.Counter = collections.Counter()
    editors: collections.Counter = collections.Counter()
    projects: collections.Counter = collections.Counter()
    per_day: dict[str, float] = {}

    for offset in range(WINDOW_DAYS):
        day = (today - timedelta(days=offset)).isoformat()
        entries = get_json(f"/users/current/durations?date={day}", key).get("data") or []
        day_total = 0.0
        for entry in entries:
            duration = float(entry.get("duration") or 0)
            day_total += duration
            languages[entry.get("language") or "unknown"] += duration
            editors[entry.get("editor") or "unknown"] += duration
            projects[entry.get("project") or "unknown"] += duration
        per_day[day] = day_total

    return {
        "languages": languages,
        "editors": editors,
        "projects": projects,
        "per_day": per_day,
        "total": sum(per_day.values()),
    }


def main() -> None:
    key = api_key()
    user = get_json("/users/current", key).get("data") or {}
    username = user.get("username") or ""
    print(f"WakaTime account: {username or user.get('display_name') or 'unknown'}")

    data = collect_durations(key)
    total_seconds = data["total"]

    if total_seconds <= 0:
        # Fall back to the statistics endpoint for accounts that only report
        # aggregate numbers.
        stats = get_json(f"/users/current/stats/last_{WINDOW_DAYS}_days", key).get("data") or {}
        total_seconds = float(stats.get("total_seconds") or 0)
        languages = collections.Counter()
        for language in stats.get("languages") or []:
            languages[language.get("name") or "unknown"] = total_seconds * float(
                language.get("percent") or 0
            ) / 100
        editors = collections.Counter()
        for editor in stats.get("editors") or []:
            editors[editor.get("name") or "unknown"] = total_seconds * float(
                editor.get("percent") or 0
            ) / 100
        per_day: dict[str, float] = {}
        active_days = 0
        best_day = ("", 0.0)
    else:
        languages = data["languages"]
        editors = data["editors"]
        per_day = data["per_day"]
        active_days = sum(1 for value in per_day.values() if value > 0)
        best_day = max(per_day.items(), key=lambda item: item[1])

    average_seconds = total_seconds / active_days if active_days else 0.0
    no_activity = total_seconds <= 0
    coding_value = "0m" if no_activity else human_duration(total_seconds)
    average_value = "0m" if average_seconds <= 0 else human_duration(average_seconds)

    if no_activity:
        best_label = "—"
        best_sub = "no sessions tracked"
    else:
        best_date = datetime.strptime(best_day[0], "%Y-%m-%d")
        best_label = best_date.strftime("%d %b")
        best_sub = human_duration(best_day[1])

    known_languages = {name: value for name, value in languages.items() if name != "unknown"}
    language_rows = []
    top_languages = sorted(known_languages.items(), key=lambda item: item[1], reverse=True)[:3]
    for index, (name, value) in enumerate(top_languages):
        y = 212 + index * 28
        percent = (value / total_seconds * 100) if total_seconds else 0
        width = max(3.0, 500 * percent / 100)
        language_rows.append(
            f"""
  <text x="28" y="{y + 9}" font-family="{FONT}" font-size="13" fill="{TEXT}">{svg_text(name)}</text>
  <rect x="190" y="{y}" width="500" height="8" rx="4" fill="#21262d"/>
  <rect x="190" y="{y}" width="{width:.1f}" height="8" rx="4" fill="{GREEN}"/>
  <text x="832" y="{y + 8}" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{MUTED}">{percent:.1f}%</text>"""
        )

    if not language_rows:
        language_rows.append(
            f'<text x="28" y="226" font-family="{FONT}" font-size="13" fill="{MUTED}">'
            "No language breakdown for these sessions yet.</text>"
        )

    known_editors = {name: value for name, value in editors.items() if name != "unknown"}
    editors_summary = ", ".join(
        name for name, _ in sorted(known_editors.items(), key=lambda item: item[1], reverse=True)[:2]
    )

    editors_y = 212 + max(1, len(top_languages)) * 28 + 14
    footer_y = editors_y + 32
    card_height = footer_y + 18
    window_label = f"over {WINDOW_DAYS} days"
    active_label = f"across {active_days} active day" + ("s" if active_days != 1 else "")
    updated = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    handle = f"@{username}" if username else "wakatime"
    editors_text = f"Editors: {editors_summary}" if editors_summary else "Editors: not reported"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{card_height}" viewBox="0 0 {CARD_WIDTH} {card_height}" role="img" aria-labelledby="wakaTitle wakaDesc">
  <title id="wakaTitle">WakaTime coding activity</title>
  <desc id="wakaDesc">Coding time over the last {WINDOW_DAYS} days: {coding_value}. Daily average: {average_value}. Active days: {active_days}. Editors: {svg_text(editors_summary or 'not reported')}.</desc>
  <rect width="{CARD_WIDTH}" height="{card_height}" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{CARD_WIDTH - 1}" height="{card_height - 1}" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="42" font-family="{FONT}" font-size="20" font-weight="700" fill="{TEXT}">WakaTime</text>
  <text x="28" y="64" font-family="{FONT}" font-size="11.5" fill="{MUTED}">Coding activity over the last {WINDOW_DAYS} days</text>
  <text x="832" y="42" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{DIM}">{svg_text(handle)}</text>

  <rect x="24" y="84" width="260" height="86" rx="10" fill="{PANEL}" stroke="#21262d"/>
  <text x="42" y="108" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{GREEN}">CODING TIME</text>
  <text x="42" y="146" font-family="{FONT}" font-size="30" font-weight="700" fill="{TEXT}">{svg_text(coding_value)}</text>
  <text x="42" y="162" font-family="{FONT}" font-size="10.5" fill="{DIM}">{'no sessions tracked' if no_activity else window_label}</text>

  <rect x="300" y="84" width="260" height="86" rx="10" fill="{PANEL}" stroke="#21262d"/>
  <text x="318" y="108" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{BLUE}">DAILY AVERAGE</text>
  <text x="318" y="146" font-family="{FONT}" font-size="30" font-weight="700" fill="{TEXT}">{svg_text(average_value)}</text>
  <text x="318" y="162" font-family="{FONT}" font-size="10.5" fill="{DIM}">{svg_text(active_label)}</text>

  <rect x="576" y="84" width="260" height="86" rx="10" fill="{PANEL}" stroke="#21262d"/>
  <text x="594" y="108" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{PURPLE}">MOST ACTIVE DAY</text>
  <text x="594" y="146" font-family="{FONT}" font-size="24" font-weight="700" fill="{TEXT}">{svg_text(best_label)}</text>
  <text x="594" y="162" font-family="{FONT}" font-size="10.5" fill="{DIM}">{svg_text(best_sub)}</text>

  <text x="28" y="196" font-family="{FONT}" font-size="12" font-weight="600" fill="{MUTED}">LANGUAGES</text>
  {''.join(language_rows)}
  <text x="28" y="{editors_y}" font-family="{FONT}" font-size="11" fill="{DIM}">{svg_text(editors_text)}</text>
  <text x="28" y="{footer_y}" font-family="{FONT}" font-size="10" fill="{DIM}">via the WakaTime API · refreshed every 6 hours</text>
  <text x="832" y="{footer_y}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{DIM}">updated {svg_text(updated)}</text>
</svg>"""

    write_svg("assets/wakatime.svg", svg)
    print(
        f"WakaTime card generated: {coding_value} over {WINDOW_DAYS} days, "
        f"{active_days} active day(s), {len(top_languages)} languages."
    )


if __name__ == "__main__":
    main()
