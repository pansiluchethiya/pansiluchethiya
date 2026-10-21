"""Shared helpers for the profile README automation.

Only the Python standard library is used so the GitHub Actions runs stay fast
and dependency-free.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"
USER_AGENT = "pansiluchethiya-profile-readme"

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"

BG = "#0d1117"
PANEL = "#161b22"
PANEL_ALT = "#1c2128"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
DIM = "#6e7681"
GREEN = "#3fb950"
BLUE = "#58a6ff"
PURPLE = "#bc8cff"
ORANGE = "#f0883e"
YELLOW = "#d29922"
PINK = "#f778ba"


def token() -> str:
    value = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not value:
        sys.exit("GITHUB_TOKEN (or GH_TOKEN) is required for GitHub API access.")
    return value


def _api_request(url: str, *, method: str = "GET", data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token()}")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        req.add_header("Content-Type", "application/json")

    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            last_error = f"GitHub API {exc.code} for {url}: {detail}"
            if exc.code < 500 or attempt == 2:
                raise SystemExit(last_error) from exc
        except urllib.error.URLError as exc:
            last_error = f"GitHub API request failed for {url}: {exc.reason}"
            if attempt == 2:
                raise SystemExit(last_error) from exc
        time.sleep(2 ** attempt)
    raise SystemExit(last_error or f"GitHub API request failed for {url}")


def graphql(query: str, variables: dict):
    payload = _api_request(
        GRAPHQL_URL, method="POST", data={"query": query, "variables": variables}
    )
    if payload.get("errors"):
        raise SystemExit(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]


def rest(path: str):
    return _api_request(API + path)


def read_json(relative_path: str, default=None):
    path = ROOT / relative_path
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid JSON in {relative_path}: {exc}")


def write_json(relative_path: str, value) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    write_text(relative_path, text)


def write_text(relative_path: str, text: str) -> None:
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def write_svg(relative_path: str, content: str) -> None:
    """Write an SVG after checking that it is well-formed XML."""
    try:
        ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise SystemExit(f"Refusing to write invalid SVG to {relative_path}: {exc}") from exc
    write_text(relative_path, content)


def load_profile() -> dict:
    profile = read_json("config/profile.json")
    if not profile or not profile.get("login"):
        raise SystemExit("config/profile.json is missing a login.")
    return profile


def svg_text(value) -> str:
    return escape(str(value), quote=True)


def wrap_text(text: str, width: int) -> list[str]:
    """Wrap on word boundaries by character count (good enough for SVG cards)."""
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            while len(current) > width:
                lines.append(current[:width])
                current = current[width:]
    if current:
        lines.append(current)
    return lines


def fmt_int(value) -> str:
    return f"{int(value):,}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def date_label(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return iso_date


def md_escape(value: str) -> str:
    return (
        str(value)
        .replace("|", "\\|")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def replace_block(text: str, start_marker: str, end_marker: str, body: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1 or end < start:
        raise SystemExit(f"README markers not found or out of order: {start_marker}")
    start += len(start_marker)
    return f"{text[:start]}\n{body.strip()}\n{text[end:]}"
