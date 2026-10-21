#!/usr/bin/env python3
"""Render assets/hero.svg — the typographic banner at the top of the profile.

Everything in the banner comes from `config/profile.json`, so the wording stays
in sync with the rest of the automation.
"""

from __future__ import annotations

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
    TEXT,
    load_profile,
    svg_text,
    write_svg,
)

WIDTH = 1200
HEIGHT = 360


def render(profile: dict) -> str:
    name = profile.get("name") or profile["login"]
    headline = profile.get("headline") or ""
    message = profile.get("message") or ""
    handle = profile["login"]
    location = profile.get("location") or "localhost:5001"

    terminal_lines = [
        ("$", "whoami", GREEN),
        ("", handle, TEXT),
        ("$", "cat focus.txt", GREEN),
        ("", "build weird things that work", TEXT),
        ("$", "git push origin main", GREEN),
        ("", "shipped", DIM),
    ]

    term_rows = []
    y = 140
    for prompt, content, color in terminal_lines:
        if prompt:
            term_rows.append(
                f'<text x="792" y="{y}" font-family="{MONO}" font-size="13.5" fill="{GREEN}">'
                f'{svg_text(prompt)}</text>'
            )
            term_rows.append(
                f'<text x="806" y="{y}" font-family="{MONO}" font-size="13.5" fill="{color}">'
                f"{svg_text(content)}</text>"
            )
        else:
            term_rows.append(
                f'<text x="806" y="{y}" font-family="{MONO}" font-size="13.5" fill="{color}">'
                f"{svg_text(content)}</text>"
            )
        y += 26

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="heroTitle heroDesc">
  <title id="heroTitle">{svg_text(name)} — GitHub profile</title>
  <desc id="heroDesc">{svg_text(headline)}. {svg_text(message)}</desc>
  <defs>
    <linearGradient id="heroBg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#11161d"/>
      <stop offset="55%" stop-color="{BG}"/>
      <stop offset="100%" stop-color="#0a0d12"/>
    </linearGradient>
    <radialGradient id="heroGlow" cx="0.28" cy="0.22" r="0.7">
      <stop offset="0%" stop-color="#3fb950" stop-opacity="0.13"/>
      <stop offset="100%" stop-color="#3fb950" stop-opacity="0"/>
    </radialGradient>
    <pattern id="heroGrid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path d="M32 0H0V32" fill="none" stroke="#1c2128" stroke-width="1"/>
    </pattern>
  </defs>

  <rect width="{WIDTH}" height="{HEIGHT}" rx="18" fill="url(#heroBg)"/>
  <rect width="{WIDTH}" height="{HEIGHT}" rx="18" fill="url(#heroGrid)" opacity="0.55"/>
  <rect width="{WIDTH}" height="{HEIGHT}" rx="18" fill="url(#heroGlow)"/>
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="17.5" fill="none" stroke="{BORDER}"/>

  <text x="64" y="74" font-family="{MONO}" font-size="13" fill="{DIM}">@{svg_text(handle)}</text>
  <text x="64" y="146" font-family="{FONT}" font-size="62" font-weight="700" fill="{TEXT}">{svg_text(name)}</text>
  <rect x="64" y="170" width="46" height="3" rx="1.5" fill="{GREEN}"/>
  <text x="64" y="212" font-family="{FONT}" font-size="20" font-weight="600" fill="{GREEN}">{svg_text(headline.split('•')[0].strip())}</text>
  <text x="64" y="240" font-family="{FONT}" font-size="20" font-weight="600" fill="{BLUE}">{svg_text(' • '.join(part.strip() for part in headline.split('•')[1:]))}</text>

  <rect x="64" y="266" width="3" height="46" rx="1.5" fill="{BORDER}"/>
  <text x="84" y="284" font-family="{FONT}" font-size="16" font-style="italic" fill="{TEXT}">{svg_text('“' + message + '”')}</text>
  <text x="84" y="308" font-family="{MONO}" font-size="12" fill="{DIM}">{svg_text('location: ' + location)}</text>

  <g>
    <rect x="756" y="66" width="380" height="228" rx="14" fill="{PANEL}" stroke="#21262d"/>
    <text x="780" y="96" font-family="{MONO}" font-size="11.5" fill="{DIM}">~/projects</text>
    <line x1="780" y1="110" x2="1112" y2="110" stroke="#21262d"/>
    {''.join(term_rows)}
    <rect x="806" y="{y - 17}" width="8" height="15" fill="{GREEN}">
      <animate attributeName="opacity" values="1;1;0;0" dur="1.1s" repeatCount="indefinite"/>
    </rect>
  </g>
</svg>"""


def main() -> None:
    profile = load_profile()
    write_svg("assets/hero.svg", render(profile))
    print("Generated assets/hero.svg")


if __name__ == "__main__":
    main()
