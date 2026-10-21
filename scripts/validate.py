#!/usr/bin/env python3
"""Validate everything that ends up in the profile repository.

Checks performed:
  * every JSON file parses
  * every SVG asset is well-formed XML and declares a namespace
  * every workflow is valid YAML with triggers, permissions and valid crons
  * README markers exist, are ordered and every local asset reference resolves
  * every README image has alt text
  * no private repository identifiers leak into tracked files
  * no token-shaped strings are committed
  * the fun fact and quote pools are large enough and well formed
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent

# Built from fragments so this validator never stores the literal identifiers.
PRIVATE_MARKERS = ("wells" + "hq", "wells" + "-health")
TOKEN_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]

errors: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
        names = [line for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        names = [
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("*")
            if path.is_file() and ".git/" not in str(path)
        ]
    return [ROOT / name for name in names]


def check_json() -> None:
    for path in sorted((ROOT / "config").glob("*.json")) + sorted((ROOT / "data").glob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
    notes.append("JSON files parsed")


def check_svg() -> None:
    for path in sorted((ROOT / "assets").glob("*.svg")):
        text = path.read_text(encoding="utf-8")
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as exc:
            fail(f"invalid SVG in {path.relative_to(ROOT)}: {exc}")
            continue
        if not root.tag.startswith("{http://www.w3.org/2000/svg}svg"):
            fail(f"{path.relative_to(ROOT)} is not an SVG root element")
        if len(text.strip()) < 200:
            fail(f"{path.relative_to(ROOT)} looks empty")
    notes.append("SVG assets parsed")


def valid_cron(expression: str) -> bool:
    """Accept the standard five field cron syntax used by GitHub Actions."""
    fields = expression.split()
    if len(fields) != 5:
        return False
    for field in fields:
        for part in field.split(","):
            value = part.split("/")[0]
            if value != "*" and not value.isdigit():
                return False
            if "/" in part:
                step = part.split("/", 1)[1]
                if not step.isdigit():
                    return False
    return True


def check_workflows() -> None:
    try:
        import yaml  # type: ignore
    except ImportError:
        notes.append("PyYAML not installed - workflow YAML check skipped")
        return

    workflow_dir = ROOT / ".github/workflows"
    for path in sorted(workflow_dir.glob("*.y*ml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            fail(f"invalid YAML in {path.relative_to(ROOT)}: {exc}")
            continue
        if not isinstance(data, dict):
            fail(f"{path.relative_to(ROOT)} does not contain a mapping")
            continue
        # PyYAML parses the `on:` key as the boolean True.
        triggers = data.get("on", data.get(True))
        if not triggers:
            fail(f"{path.relative_to(ROOT)} has no triggers")
        elif isinstance(triggers, dict) and "schedule" in triggers:
            for entry in triggers["schedule"] or []:
                cron = entry.get("cron") if isinstance(entry, dict) else None
                if not cron or not valid_cron(str(cron)):
                    fail(f"{path.relative_to(ROOT)} has an invalid cron expression: {cron!r}")
        if "permissions" not in data:
            fail(f"{path.relative_to(ROOT)} does not declare permissions")
        jobs = data.get("jobs") or {}
        if not jobs:
            fail(f"{path.relative_to(ROOT)} defines no jobs")
        for job_name, job in jobs.items():
            steps = (job or {}).get("steps") or []
            if not steps:
                fail(f"{path.relative_to(ROOT)}:{job_name} has no steps")
    notes.append("workflow YAML parsed")


def check_readme() -> None:
    readme_path = ROOT / "README.md"
    if not readme_path.exists():
        fail("README.md is missing")
        return
    text = readme_path.read_text(encoding="utf-8")

    markers = [
        "<!-- PROJECTS:START -->",
        "<!-- PROJECTS:END -->",
        "<!-- SNAKE:START -->",
        "<!-- SNAKE:END -->",
        "<!-- WAKATIME:START -->",
        "<!-- WAKATIME:END -->",
    ]
    positions = []
    for marker in markers:
        index = text.find(marker)
        if index == -1:
            fail(f"README is missing the marker {marker}")
            return
        positions.append(index)
    if positions != sorted(positions):
        fail("README markers are out of order")

    for match in re.finditer(r'(?:src|href)="([^"]+)"', text):
        target = match.group(1)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        local = target.split("?")[0]
        if not (ROOT / local).exists():
            fail(f"README references a missing local file: {target}")

    for match in re.finditer(r"<img\b[^>]*>", text):
        tag = match.group(0)
        if "alt=" not in tag:
            fail(f"README image without alt text: {tag[:80]}")

    if text.count("<p align=") != text.count("</p>"):
        fail("README has unbalanced <p> tags")
    notes.append("README structure checked")


def check_privacy_and_secrets() -> None:
    for path in tracked_files():
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lowered = text.lower()
        for marker in PRIVATE_MARKERS:
            if marker in lowered:
                fail(f"private repository identifier found in {path.relative_to(ROOT)}")
        for pattern in TOKEN_PATTERNS:
            if pattern.search(text):
                fail(f"possible committed token in {path.relative_to(ROOT)}")
    notes.append("privacy and secret scan done")


def check_pools() -> None:
    facts_path = ROOT / "data/fun-facts.json"
    if facts_path.exists():
        payload = json.loads(facts_path.read_text(encoding="utf-8"))
        facts = payload.get("facts") or []
        if len(facts) < 500:
            fail(f"fun fact pool has {len(facts)} facts, expected at least 500")
        if len(set(facts)) != len(facts):
            fail("fun fact pool contains duplicates")
        for fact in facts:
            if not isinstance(fact, str) or len(fact) < 40 or len(fact) > 300:
                fail(f"fun fact has an unexpected length: {fact[:60]!r}")
                break
            if not fact.endswith("."):
                fail(f"fun fact does not end with a full stop: {fact[:60]!r}")
                break

    quotes_path = ROOT / "data/quotes.json"
    if quotes_path.exists():
        payload = json.loads(quotes_path.read_text(encoding="utf-8"))
        quotes = payload.get("quotes") or []
        if len(quotes) < 20:
            fail(f"quote pool has {len(quotes)} quotes, expected at least 20")
        for quote in quotes:
            if not quote.get("text") or not quote.get("author"):
                fail("a quote is missing text or author")
                break
    notes.append("content pools checked")


def main() -> int:
    check_json()
    check_svg()
    check_workflows()
    check_readme()
    check_privacy_and_secrets()
    check_pools()

    for note in notes:
        print(f"  ok  {note}")
    if errors:
        print()
        for error in errors:
            print(f"  FAIL  {error}")
        print(f"\n{len(errors)} validation error(s).")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
