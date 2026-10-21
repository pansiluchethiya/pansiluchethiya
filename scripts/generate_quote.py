#!/usr/bin/env python3
"""Pick one developer quote for the current UTC hour and render its SVG."""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone

from lib import (
    BG,
    BLUE,
    BORDER,
    DIM,
    FONT,
    MONO,
    MUTED,
    PANEL,
    PURPLE,
    TEXT,
    read_json,
    svg_text,
    wrap_text,
    write_json,
    write_svg,
)

CARD_WIDTH = 860
CARD_HEIGHT = 230


def main() -> None:
    payload = read_json("data/quotes.json")
    pool = (payload or {}).get("quotes") or []
    if len(pool) < 20:
        raise SystemExit(f"Quote pool is too small ({len(pool)}).")

    hour = int(time.time() // 3600)
    state = read_json("data/state.json", {})
    index = random.Random(hour + 7).randrange(len(pool))
    last_index = state.get("quote_index")
    if last_index is not None and index == last_index and state.get("quote_hour") != hour:
        index = (index + 1) % len(pool)
    state["quote_hour"] = hour
    state["quote_index"] = index
    quote = pool[index]

    text = " ".join(quote["text"].split())
    lines = wrap_text(text, 74)
    size = 19
    line_height = 27
    if len(lines) > 3:
        size = 17
        line_height = 24
        lines = wrap_text(text, 84)
    lines = lines[:4]
    author_y = 101 + max(0, len(lines) - 1) * line_height + 26

    body = "\n".join(
        f'<text x="42" y="{101 + line_index * line_height}" font-family="{FONT}" '
        f'font-size="{size}" font-style="italic" fill="{TEXT}">{svg_text(line)}</text>'
        for line_index, line in enumerate(lines)
    )

    updated = datetime.fromtimestamp(hour * 3600, tz=timezone.utc).strftime("%d %b %Y · %H:00 UTC")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-labelledby="quoteTitle quoteDesc">
  <title id="quoteTitle">Developer quote of the hour</title>
  <desc id="quoteDesc">{svg_text(text)} — {svg_text(quote['author'])}</desc>
  <rect width="{CARD_WIDTH}" height="{CARD_HEIGHT}" rx="16" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{CARD_WIDTH - 1}" height="{CARD_HEIGHT - 1}" rx="15.5" fill="none" stroke="{BORDER}"/>
  <path d="M0 16a16 16 0 0 1 16-16h828a16 16 0 0 1 16 16v22H0z" fill="{PANEL}"/>
  <line x1="0" y1="38" x2="{CARD_WIDTH}" y2="38" stroke="{BORDER}"/>
  <circle cx="22" cy="19" r="4" fill="#ff5f56"/>
  <circle cx="38" cy="19" r="4" fill="#ffbd2e"/>
  <circle cx="54" cy="19" r="4" fill="#27c93f"/>
  <text x="76" y="23" font-family="{MONO}" font-size="11" fill="{MUTED}">data/quotes.json</text>
  <text x="832" y="23" text-anchor="end" font-family="{MONO}" font-size="10" fill="{DIM}">hourly</text>
  <text x="800" y="112" font-family="{FONT}" font-size="100" font-weight="700" fill="#21262d">“</text>
  <text x="28" y="70" font-family="{MONO}" font-size="10.5" font-weight="700" letter-spacing="1.4" fill="{PURPLE}">DEVELOPER QUOTE</text>
  {body}
  <text x="42" y="{author_y}" font-family="{FONT}" font-size="12" fill="{BLUE}">— {svg_text(quote['author'])}</text>
  <text x="28" y="214" font-family="{FONT}" font-size="10" fill="{DIM}">↻ a new quote every hour</text>
  <text x="832" y="214" text-anchor="end" font-family="{MONO}" font-size="10" fill="{DIM}">updated {svg_text(updated)}</text>
</svg>"""

    write_svg("assets/developer-quote.svg", svg)
    write_json("data/state.json", state)
    print(f"Quote updated for {updated}: {text[:80]} — {quote['author']}")


if __name__ == "__main__":
    main()
