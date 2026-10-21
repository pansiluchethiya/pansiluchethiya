#!/usr/bin/env python3
"""Render a compact WakaTime card when WAKATIME_API_KEY is configured.

WakaTime usernames cannot be discovered from GitHub, so this script uses the
authenticated `/users/current` endpoint. Add the API key as a repository secret
and the next scheduled run inserts the section automatically.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

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


def main() -> None:
    key = api_key()
    user_payload = get_json("/users/current", key)
    user = user_payload.get("data") or {}
    username = user.get("username") or ""
    print(f"WakaTime account: {username or 'unknown'} ({user.get('email') or 'no email on file'})")

    # Prefer the last seven days, but fall back to a longer window so the card
    # still shows real numbers for accounts that only code occasionally.
    range_name = "last 7 days"
    stats_payload = get_json("/users/current/stats/last_7_days", key)
    stats = stats_payload.get("data") or {}
    if float(stats.get("total_seconds") or 0) <= 0:
        stats = get_json("/users/current/stats/last_30_days", key).get("data") or {}
        range_name = "last 30 days"

    total_seconds = float(stats.get("total_seconds") or 0)
    daily_seconds = float(stats.get("daily_average") or 0)
    languages = stats.get("languages") or []
    editors = stats.get("editors") or []
    top_editor = editors[0]["name"] if editors else "—"
    print(
        f"WakaTime window: {range_name}, {total_seconds:.0f}s total, "
        f"{len(languages)} languages, {len(editors)} editors"
    )

    language_rows = []
    for index, language in enumerate(languages[:3]):
        y = 230 + index * 30
        percent = float(language.get("percent") or 0)
        width = max(3.0, 560 * percent / 100)
        language_rows.append(
            f"""
  <text x="28" y="{y + 10}" font-family="{FONT}" font-size="13" fill="{TEXT}">{svg_text(language.get('name', '—'))}</text>
  <rect x="200" y="{y}" width="560" height="9" rx="4.5" fill="#21262d"/>
  <rect x="200" y="{y}" width="{width:.1f}" height="9" rx="4.5" fill="{GREEN}"/>
  <text x="832" y="{y + 9}" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{MUTED}">{percent:.1f}%</text>"""
        )

    if not language_rows:
        language_rows.append(
            f'<text x="28" y="240" font-family="{FONT}" font-size="13" fill="{MUTED}">No language data in the {range_name}.</text>'
        )

    updated = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    handle = f"@{username}" if username else "WakaTime"
    no_activity = total_seconds <= 0
    coding_value = "0m" if no_activity else human_duration(total_seconds)
    average_value = "0m" if daily_seconds <= 0 else human_duration(daily_seconds)
    short_range = range_name.replace("last ", "")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-labelledby="wakaTitle wakaDesc">
  <title id="wakaTitle">WakaTime coding activity</title>
  <desc id="wakaDesc">Coding time in the {range_name}: {coding_value}. Daily average: {average_value}. Top editor: {svg_text(top_editor)}.</desc>
  <rect width="{CARD_WIDTH}" height="{CARD_HEIGHT}" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{CARD_WIDTH - 1}" height="{CARD_HEIGHT - 1}" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="40" font-family="{FONT}" font-size="20" font-weight="700" fill="{TEXT}">WakaTime</text>
  <text x="28" y="62" font-family="{FONT}" font-size="11.5" fill="{MUTED}">Coding activity for the {range_name}</text>
  <text x="832" y="40" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{DIM}">{svg_text(handle)}</text>

  <rect x="24" y="84" width="260" height="86" rx="10" fill="{PANEL}" stroke="#21262d"/>
  <text x="42" y="108" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{GREEN}">CODING TIME</text>
  <text x="42" y="146" font-family="{FONT}" font-size="30" font-weight="700" fill="{TEXT}">{svg_text(coding_value)}</text>
  <text x="42" y="162" font-family="{FONT}" font-size="10.5" fill="{DIM}">{'no activity recorded' if no_activity else short_range}</text>

  <rect x="300" y="84" width="260" height="86" rx="10" fill="{PANEL}" stroke="#21262d"/>
  <text x="318" y="108" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{BLUE}">DAILY AVERAGE</text>
  <text x="318" y="146" font-family="{FONT}" font-size="30" font-weight="700" fill="{TEXT}">{svg_text(average_value)}</text>
  <text x="318" y="162" font-family="{FONT}" font-size="10.5" fill="{DIM}">across the {short_range}</text>

  <rect x="576" y="84" width="260" height="86" rx="10" fill="{PANEL}" stroke="#21262d"/>
  <text x="594" y="108" font-family="{FONT}" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="{PURPLE}">TOP EDITOR</text>
  <text x="594" y="146" font-family="{FONT}" font-size="24" font-weight="700" fill="{TEXT}">{svg_text(top_editor)}</text>
  <text x="594" y="162" font-family="{FONT}" font-size="10.5" fill="{DIM}">most used in this period</text>

  <text x="28" y="204" font-family="{FONT}" font-size="12" font-weight="600" fill="{MUTED}">LANGUAGES</text>
  {''.join(language_rows)}
  <text x="28" y="{CARD_HEIGHT - 16}" font-family="{FONT}" font-size="10" fill="{DIM}">via the WakaTime API · refreshed every 6 hours</text>
  <text x="832" y="{CARD_HEIGHT - 16}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{DIM}">updated {svg_text(updated)}</text>
</svg>"""

    write_svg("assets/wakatime.svg", svg)
    print(f"WakaTime card generated for {handle}: {coding_value} in the {range_name}.")


if __name__ == "__main__":
    main()
