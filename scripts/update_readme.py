#!/usr/bin/env python3
"""Render generated sections into README.md and keep asset URLs cache-fresh.

GitHub proxies README images through camo, which caches aggressively. Every
generated asset therefore gets a `?v=<content hash>` query string so a
regenerated card is visible immediately instead of after the cache expires.
"""

from __future__ import annotations

import hashlib
import re
from datetime import timezone
from pathlib import Path

from lib import ROOT, md_escape, read_json, replace_block, utc_now, write_text

PROJECTS_START = "<!-- PROJECTS:START -->"
PROJECTS_END = "<!-- PROJECTS:END -->"
WAKATIME_START = "<!-- WAKATIME:START -->"
WAKATIME_END = "<!-- WAKATIME:END -->"
SNAKE_START = "<!-- SNAKE:START -->"
SNAKE_END = "<!-- SNAKE:END -->"

SNAKE_BASE = "https://raw.githubusercontent.com/pansiluchethiya/pansiluchethiya/output"
SNAKE_SVG = f"{SNAKE_BASE}/github-contribution-grid-snake.svg"

ASSET_REF = re.compile(r'(src=")(assets/[\w.-]+\.svg)(")')


def render_projects() -> str:
    data = read_json("data/projects.json")
    if not data or not data.get("projects"):
        raise SystemExit("data/projects.json is missing. Run generate_projects.py first.")

    rows = [
        "| Project | Details |",
        "|:--|:--|",
    ]
    for project in data["projects"]:
        title = md_escape(project["title"])
        if project["private"]:
            heading = f"**{title}** <br/><sub>🔒 private</sub>"
        else:
            heading = f"**[{title}]({project['url']})**"
            meta = []
            if project.get("stars"):
                meta.append(f"★ {project['stars']}")
            if project.get("language"):
                meta.append(md_escape(project["language"]))
            if project.get("frontend_url"):
                meta.append(f"[frontend ↗]({project['frontend_url']})")
            if meta:
                heading += " <br/><sub>" + " · ".join(meta) + "</sub>"

        details = md_escape(project["description"])
        if project.get("live_url"):
            details += f" · [{project['live_label']} ↗]({project['live_url']})"
        if project["tech"]:
            tags = " · ".join(f"`{md_escape(tag)}`" for tag in project["tech"])
            details += f"<br/>{tags}"

        rows.append(f"| {heading} | {details} |")

    return "\n".join(rows)


def render_wakatime() -> str:
    if not (ROOT / "assets/wakatime.svg").exists():
        return """> **WakaTime stats are not connected yet.**
> Add a `WAKATIME_API_KEY` repository secret and the `wakatime.yml` workflow
> will fill this section automatically — no README editing required.
> See [`docs/AUTOMATION.md`](docs/AUTOMATION.md) for the setup steps."""
    return """<p align="center">
  <img src="assets/wakatime.svg" alt="WakaTime coding activity for the last seven days" width="100%" />
</p>"""


def render_snake() -> str:
    version = utc_now().astimezone(timezone.utc).strftime("%Y-%m-%d")
    return f"""<p align="center">
  <img src="{SNAKE_SVG}?v={version}" alt="Animated snake crawling across the contribution graph" width="100%" />
</p>"""


def asset_version(path: str) -> str:
    file = ROOT / path
    if not file.exists():
        return "0"
    return hashlib.sha1(file.read_bytes()).hexdigest()[:10]


def bust_asset_cache(text: str) -> str:
    """Append a content-hash query string to every local asset reference."""

    def replace(match: re.Match) -> str:
        prefix, asset, suffix = match.groups()
        return f"{prefix}{asset}?v={asset_version(asset)}{suffix}"

    return ASSET_REF.sub(replace, text)


def main() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme = replace_block(readme, PROJECTS_START, PROJECTS_END, render_projects())
    readme = replace_block(readme, WAKATIME_START, WAKATIME_END, render_wakatime())
    readme = replace_block(readme, SNAKE_START, SNAKE_END, render_snake())
    readme = bust_asset_cache(readme)
    write_text("README.md", readme)
    print("README generated blocks updated.")


if __name__ == "__main__":
    main()
