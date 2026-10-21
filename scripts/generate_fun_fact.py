#!/usr/bin/env python3
"""Pick one fact for the current UTC hour and render assets/fun-fact.svg.

The fact pool is local, so the README never depends on a third-party API at
render time. Selection is deterministic within an hour, which keeps repeated
workflow runs from producing noisy commits.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone

from lib import (
    BG,
    BORDER,
    DIM,
    FONT,
    GREEN,
    MONO,
    MUTED,
    PANEL,
    TEXT,
    read_json,
    svg_text,
    wrap_text,
    write_json,
    write_svg,
)

CARD_WIDTH = 860
CARD_HEIGHT = 186


def pick(pool: list[str], state: dict, prefix: str, hour: int) -> tuple[int, str]:
    index = random.Random(hour).randrange(len(pool))
    last_index = state.get(f"{prefix}_index")
    if last_index is not None and index == last_index and state.get(f"{prefix}_hour") != hour:
        index = (index + 1) % len(pool)
    state[f"{prefix}_hour"] = hour
    state[f"{prefix}_index"] = index
    return index, pool[index]


def render(text: str, updated_label: str) -> str:
    lines = wrap_text(text, 92)
    size = 18
    line_height = 26
    if len(lines) > 2:
        size = 16
        line_height = 24
        lines = wrap_text(text, 102)
    if len(lines) > 3:
        size = 14
        line_height = 22
        lines = wrap_text(text, 114)
    lines = lines[:3]

    region_top, region_bottom = 82, 150
    block_height = (len(lines) - 1) * line_height
    start_y = region_top + max(0, (region_bottom - region_top - block_height) // 2)

    body = "\n".join(
        f'<text x="28" y="{start_y + index * line_height}" font-family="{FONT}" '
        f'font-size="{size}" fill="{TEXT}">{svg_text(line)}</text>'
        for index, line in enumerate(lines)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-labelledby="factTitle factDesc">
  <title id="factTitle">Random fun fact</title>
  <desc id="factDesc">{svg_text(text)}</desc>
  <rect width="{CARD_WIDTH}" height="{CARD_HEIGHT}" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{CARD_WIDTH - 1}" height="{CARD_HEIGHT - 1}" rx="15.5" fill="none" stroke="{BORDER}"/>
  <text x="28" y="46" font-family="{MONO}" font-size="10.5" font-weight="700" letter-spacing="1.4" fill="{GREEN}">FUN FACT</text>
  <text x="832" y="46" text-anchor="end" font-family="{MONO}" font-size="10" fill="{DIM}">rotates every hour</text>
  <line x1="28" y1="60" x2="832" y2="60" stroke="#21262d"/>
  {body}
  <text x="832" y="{CARD_HEIGHT - 14}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{DIM}">updated {svg_text(updated_label)}</text>
</svg>"""


def main() -> None:
    payload = read_json("data/fun-facts.json")
    pool = (payload or {}).get("facts") or []
    if len(pool) < 500:
        raise SystemExit(f"Fun-fact pool is too small ({len(pool)}); expected at least 500.")

    hour = int(time.time() // 3600)
    state = read_json("data/state.json", {})
    _, fact = pick(pool, state, "fact", hour)
    updated = datetime.fromtimestamp(hour * 3600, tz=timezone.utc).strftime("%d %b %Y · %H:00 UTC")

    write_svg("assets/fun-fact.svg", render(fact, updated))
    write_json("data/state.json", state)
    print(f"Fun fact updated for {updated}: {fact[:80]}")


if __name__ == "__main__":
    main()
