#!/usr/bin/env python3
"""Refresh featured-project metadata from the GitHub API.

Private projects are represented by a title and a deliberately generic line.
No private repository metadata (slug, description, languages, URLs) is fetched
or written to disk.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from lib import load_profile, read_json, rest, utc_now, write_json


def clean_description(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s*\[?https?://\S+\]?\s*$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def fetch_public_repo(owner: str, name: str) -> dict:
    repo = rest(f"/repos/{owner}/{quote(name)}")
    if repo.get("private"):
        raise SystemExit(f"Refusing to publish private repository metadata: {name}")
    return repo


def dominant_language(owner: str, name: str) -> str:
    """Some forks report `language: null`; fall back to the byte counts."""
    languages = rest(f"/repos/{owner}/{quote(name)}/languages")
    if not languages:
        return ""
    return max(languages.items(), key=lambda item: item[1])[0]


def main() -> None:
    profile = load_profile()
    config = read_json("config/projects.json")
    if not config or not config.get("projects"):
        raise SystemExit("config/projects.json has no projects.")

    owner = config.get("owner") or profile["login"]
    projects = []

    for item in config["projects"]:
        entry = {
            "title": item["title"],
            "private": bool(item.get("private")),
            "description": item.get("description") or "",
            "tech": list(dict.fromkeys(item.get("tech") or [])),
            "url": None,
            "stars": 0,
            "language": "",
            "live_url": None,
            "live_label": "live",
            "frontend_url": None,
        }

        if entry["private"]:
            if not entry["description"]:
                entry["description"] = "Private project. Details available on request."
            projects.append(entry)
            continue

        repo_name = item.get("repo")
        if not repo_name:
            raise SystemExit(f"Project {item['title']} needs a repo or private: true.")

        repo = fetch_public_repo(owner, repo_name)
        description = clean_description(item.get("description") or repo.get("description") or "")
        if not description:
            description = "No description on GitHub yet."
        language = repo.get("language") or dominant_language(owner, repo_name)
        entry.update(
            {
                "url": repo["html_url"],
                "stars": int(repo.get("stargazers_count") or 0),
                "language": language,
                "description": description,
                "live_url": repo.get("homepage") or None,
            }
        )

        if item.get("live_label"):
            entry["live_label"] = item["live_label"]

        frontend = item.get("frontend_repo")
        if frontend:
            frontend_repo = fetch_public_repo(owner, frontend)
            entry["frontend_url"] = frontend_repo["html_url"]
            # The backend repo may have no homepage; fall back to the frontend app.
            if not entry["live_url"]:
                entry["live_url"] = frontend_repo.get("homepage") or None

        primary = entry["language"]
        if primary and primary not in entry["tech"]:
            entry["tech"].insert(0, primary)

        projects.append(entry)

    write_json(
        "data/projects.json",
        {"generated_at": utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z"), "projects": projects},
    )
    public = sum(1 for project in projects if not project["private"])
    print(f"Refreshed {len(projects)} featured projects ({public} public, {len(projects) - public} private).")


if __name__ == "__main__":
    main()
