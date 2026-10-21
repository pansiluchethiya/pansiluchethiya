#!/usr/bin/env python3
"""Build the local fun-fact pool from Wikipedia's "Did you know" archive.

The pool is fetched once during setup and committed to the repository, so the
README never depends on a third-party API at render time.

Facts come from the vetted DYK archive: every entry was reviewed by Wikipedia
editors and carries citations in the original article. The archive text is
cleaned, filtered for tone/length, and de-duplicated before being written to
`data/fun-facts.json`.

Usage:
    python3 scripts/fetch_fun_facts.py            # default: recent months
    python3 scripts/fetch_fun_facts.py --months 2024/01 2024/02
    python3 scripts/fetch_fun_facts.py --target 500
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "pansiluchethiya-profile-readme/1.0 (facts pool builder; contact: pansiluch@proton.me)"
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Words that keep the pool light, clean and friendly for a public profile.
BANNED = (
    "raped",
    "rape",
    "sexual",
    "sexually",
    "murder",
    "murdered",
    "assassin",
    "assassinated",
    "suicide",
    "suicidal",
    "executed",
    "execution",
    "massacre",
    "massacred",
    "slaughter",
    "torture",
    "tortured",
    "genocide",
    "slave",
    "slavery",
    "slaves",
    "died",
    "death of",
    "killed",
    "murdered",
    "abuse",
    "abused",
    "abusive",
    "drug",
    "cocaine",
    "heroin",
    "nazi",
    "holocaust",
    "terrorist",
    "terrorism",
    "shooting",
    "bombing",
    "cancer",
    "disease",
    "suffering",
    "cripple",
    "disab",
    "cadaver",
    "corpse",
    "dead body",
    "obese",
    "fat people",
    "masturbat",
    "penis",
    "vagina",
    "breast",
    "nipple",
    "orgasm",
    "sperm",
    "fart",
    "flatulence",
    "feces",
    "vomit",
    "urine",
    "dung",
    "strip club",
    "adult film",
    "adult-film",
    "bawdy",
    "condom",
    "porn",
    "brothel",
    "sex worker",
    "escort",
    "sex",
    "hell",
    "devil",
    "satan",
    "witch",
    "suffer",
)

# Hooks that reference the accompanying image read oddly without it.
IMAGE_HOOKS = ("pictured", "image hook", "photograph of", "portrait of")

MIN_LENGTH = 60
MAX_LENGTH = 260


def fetch_page(title: str) -> str:
    params = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        }
    )
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            print(f"  ! failed {title}: {exc}")
            return ""
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            print(f"  ! failed {title}: {exc}")
            return ""
        if "error" in payload:
            print(f"  ! missing {title}")
            return ""
        return payload.get("parse", {}).get("text", "")
    return ""


def strip_references(text: str) -> str:
    """Remove citation superscripts, edit sections and other noise."""
    text = re.sub(r"<sup\b.*?</sup>", "", text, flags=re.S | re.I)
    text = re.sub(r"<style\b.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<span class=\"mw-editsection\".*?</span>", "", text, flags=re.S | re.I)
    text = re.sub(r"<table\b.*?</table>", "", text, flags=re.S | re.I)
    text = re.sub(r"<div class=\"dyk-img\".*?</div>\s*</div>", "", text, flags=re.S | re.I)
    return text


def to_plain(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    text = text.replace('\\"', '"').replace("\\'", "'")
    text = re.sub(r"\[\s*\d+\s*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_hooks(page_html: str) -> list[str]:
    """Pull the plain-text hook sentences out of a DYK archive page."""
    page_html = strip_references(page_html)
    hooks: list[str] = []
    # Every hook lives in a list item that starts with "... that".
    for match in re.finditer(
        r"<li>\s*(\.\.\.\s*that.*?)(?=<li>|</ul>)", page_html, flags=re.S
    ):
        text = to_plain(match.group(1))
        text = re.sub(r"^\.\.\.\s*that\s+", "", text, flags=re.I).strip()
        # DYK hooks are phrased as questions; convert them to statements.
        text = re.sub(r"\?\s*$", ".", text)
        if text:
            hooks.append(text)
    return hooks


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def acceptable(text: str) -> bool:
    lowered = text.lower()
    if any(re.search(rf"\b{re.escape(word)}", lowered) for word in BANNED):
        return False
    if any(word in lowered for word in IMAGE_HOOKS):
        return False
    if not text.endswith("."):
        return False
    if len(text) < MIN_LENGTH or len(text) > MAX_LENGTH:
        return False
    if text.count('"') % 2 or text.count("(") != text.count(")"):
        return False
    if re.search(r"\b(https?://|www\.)\S+", text):
        return False
    # Keep it to plain prose: no leftover wiki markup or list artefacts.
    if re.search(r"[\[\]{}<>|]", text):
        return False
    if not re.match(r"^[A-Z0-9]", text):
        return False
    if text.count(" ") < 8:
        return False
    return True


def month_titles(months: list[str]) -> list[str]:
    return [f"Wikipedia:Did you know archive/{year}/{month}" for year, month in months]


def default_months(count: int) -> list[str]:
    """Most recent `count` archive months, newest first (YYYY/MonthName)."""
    titles: list[str] = []
    year, index = 2026, 9  # archives are published for completed months
    while len(titles) < count:
        titles.append(f"{year}/{MONTH_NAMES[index]}")
        index -= 1
        if index < 0:
            index = 11
            year -= 1
    return titles


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local fun-fact pool.")
    parser.add_argument("--target", type=int, default=500)
    parser.add_argument("--months", nargs="*", default=None)
    parser.add_argument(
        "--out", default="data/fun-facts.json", help="Where to write the pool."
    )
    args = parser.parse_args()

    months = args.months or default_months(24)
    seen: set[str] = set()
    facts: list[str] = []
    fetched_pages = 0

    for month in months:
        title = f"Wikipedia:Did you know archive/{month}"
        print(f"→ {title}")
        page = fetch_page(title)
        if not page:
            continue
        fetched_pages += 1
        for hook in extract_hooks(page):
            if not acceptable(hook):
                continue
            key = normalise(hook)
            if key in seen:
                continue
            seen.add(key)
            facts.append(hook)
            if len(facts) >= args.target:
                break
        if len(facts) >= args.target:
            break
        time.sleep(1.2)

    if len(facts) < args.target:
        raise SystemExit(
            f"Only collected {len(facts)} acceptable facts; need {args.target}. "
            "Add more archive months to the request."
        )

    payload = {
        "source": "Wikipedia — Did you know archive (vetted, cited entries)",
        "source_note": (
            "Fetched once with scripts/fetch_fun_facts.py. Entries were reviewed by "
            "Wikipedia editors, then filtered for tone and length before being stored "
            "here. The README renders from this local copy only."
        ),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(facts),
        "facts": facts,
    }
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(facts)} facts from {fetched_pages} archive pages to {args.out}.")


if __name__ == "__main__":
    main()
