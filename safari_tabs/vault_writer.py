import re
from datetime import datetime
from pathlib import Path


def sanitize_filename(name: str) -> str:
    """Convert a string to a safe filesystem filename."""
    name = re.sub(r'[/:\\*?"<>|\x00]', "-", name)
    name = re.sub(r"[-\s]+", "-", name).strip("-")
    name = name[:200]
    return name or "untitled"


def sanitize_tag(name: str) -> str:
    """Convert a string to a valid Obsidian tag (no spaces, no special chars)."""
    name = name.replace("&", "and")
    name = re.sub(r"[^\w\s-]", "", name)   # keep word chars, spaces, hyphens
    name = re.sub(r"[\s]+", "-", name)      # spaces → hyphens
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "untagged"


def _write_tab_note(path: Path, tab: dict, saved_date: str, tag_folder: str) -> None:
    title = tab["title"].replace('"', '\\"')
    tag_note = sanitize_filename(tab["tag"])
    tag_link = f"[[{saved_date}/{tag_folder}/{tag_note}|{tab['tag']}]]"
    content = f"""---
url: {tab['url']}
title: "{title}"
saved: {saved_date}
tags:
  - {sanitize_tag(tab['tag'])}
---

# {tab['title']}

[Open →]({tab['url']})

{tag_link}
"""
    path.write_text(content, encoding="utf-8")


def _write_tag_index(
    tag_dir: Path,
    tag_name: str,
    tabs: list[dict],
    saved_date: str,
    tab_filenames: list[str],
) -> None:
    session_link = f"[[{saved_date}/_Index|{saved_date}]]"
    tab_lines = "\n".join(
        f"- [[{saved_date}/{sanitize_filename(tag_name)}/{name}|{tab['title']}]]"
        for tab, name in zip(tabs, tab_filenames)
    )
    content = f"""---
tags:
  - {sanitize_tag(tag_name)}
---

# {tag_name}

Session: {session_link}

## Tabs ({len(tabs)})
{tab_lines}
"""
    tag_note_name = sanitize_filename(tag_name)
    (tag_dir / f"{tag_note_name}.md").write_text(content, encoding="utf-8")


def _write_session_index(
    session_path: Path,
    tags: dict[str, list[dict]],
    saved_date: str,
) -> None:
    total = sum(len(tabs) for tabs in tags.values())
    k = len(tags)

    tag_lines = "\n".join(
        f"- [[{saved_date}/{sanitize_filename(name)}/{sanitize_filename(name)}|{name}]] ({len(tabs)} tabs)"
        for name, tabs in tags.items()
    )

    content = f"""# Safari Tabs — {saved_date}

Saved {total} tabs across {k} tags.

## Tags
{tag_lines}
"""
    (session_path / "_Index.md").write_text(content, encoding="utf-8")


def _update_root_index(vault_path: Path, saved_date: str, total_tabs: int) -> None:
    root_index = vault_path / "_Index.md"
    new_entry = f"- [[{saved_date}/_Index|{saved_date}]] — {total_tabs} tabs"

    if root_index.exists():
        existing = root_index.read_text(encoding="utf-8")
        if f"[[{saved_date}/_Index" in existing:
            return
        updated = existing.rstrip() + "\n" + new_entry + "\n"
        root_index.write_text(updated, encoding="utf-8")
    else:
        content = f"""# Safari Tabs Archive

## Sessions
{new_entry}
"""
        root_index.write_text(content, encoding="utf-8")


def write_vault(
    tags: dict[str, list[dict]],
    vault_path: Path,
    saved_date: str,
) -> None:
    """
    Create the Obsidian vault directory structure and write all files.

    vault_path: e.g. ~/Documents/safari-tabs-vault/
    saved_date: ISO date string e.g. "2026-04-11"
    """
    session_path = vault_path / saved_date
    if session_path.exists():
        stamp = datetime.now().strftime("%H%M")
        saved_date = f"{saved_date}-{stamp}"
        session_path = vault_path / saved_date
    session_path.mkdir(parents=True, exist_ok=True)

    for tag_name, tabs in tags.items():
        folder_name = sanitize_filename(tag_name)
        tag_dir = session_path / folder_name
        tag_dir.mkdir(exist_ok=True)

        seen_names: dict[str, int] = {}
        tab_filenames: list[str] = []

        for tab in tabs:
            base_name = sanitize_filename(tab["title"])
            if base_name in seen_names:
                seen_names[base_name] += 1
                file_name = f"{base_name}_{seen_names[base_name]}.md"
            else:
                seen_names[base_name] = 1
                file_name = f"{base_name}.md"

            tab_filenames.append(file_name[:-3])  # strip .md for wikilink
            _write_tab_note(tag_dir / file_name, tab, saved_date, folder_name)

        _write_tag_index(tag_dir, tag_name, tabs, saved_date, tab_filenames)

    _write_session_index(session_path, tags, saved_date)
    total_tabs = sum(len(tabs) for tabs in tags.values())
    _update_root_index(vault_path, saved_date, total_tabs)
