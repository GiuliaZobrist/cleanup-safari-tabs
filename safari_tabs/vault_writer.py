import re
import shutil
from datetime import datetime
from pathlib import Path

STABLE = "Stable"  # top-level folder for validated tags


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[/:\\*?"<>|\x00]', "-", name)
    name = re.sub(r"[-\s]+", "-", name).strip("-")
    name = name[:200]
    return name or "untitled"


def sanitize_tag(name: str) -> str:
    name = name.replace("&", "and")
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "untagged"


# ---------------------------------------------------------------------------
# Validation helpers — folder-based: presence in Stable/ is the signal
# ---------------------------------------------------------------------------

def find_validated_tags(vault_path: Path) -> dict[str, Path]:
    """Return {folder_name: tag_dir} for every subfolder of Stable/."""
    stable_dir = vault_path / STABLE
    if not stable_dir.exists():
        return {}
    return {d.name: d for d in stable_dir.iterdir() if d.is_dir()}


def get_validated_tag_names(vault_path: Path) -> list[str]:
    """Return display names of validated tags (from H1 of each index note)."""
    names = []
    stable_dir = vault_path / STABLE
    if not stable_dir.exists():
        return names
    for tag_dir in stable_dir.iterdir():
        if not tag_dir.is_dir():
            continue
        index_note = tag_dir / f"{tag_dir.name}.md"
        try:
            for line in index_note.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    names.append(line[2:].strip())
                    break
            else:
                names.append(tag_dir.name)
        except Exception:
            names.append(tag_dir.name)
    return names


def backfill_stable_tags(vault_path: Path) -> int:
    """Add 'stable' to the tags frontmatter of any note in Stable/ that's missing it."""
    stable_dir = vault_path / STABLE
    if not stable_dir.exists():
        return 0

    updated = 0
    for note in stable_dir.rglob("*.md"):
        try:
            text = note.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            fm_end = text.find("\n---", 3)
            if fm_end == -1:
                continue
            fm = text[3:fm_end]

            if re.search(r"^\s*-\s+stable\b", fm, re.MULTILINE):
                continue  # already has the tag

            def append_stable(m: re.Match) -> str:
                return m.group(0).rstrip("\n") + "\n  - stable\n"

            new_fm, n = re.subn(
                r"^tags:(?:\n[ \t]+-[ \t]+[^\n]+)+",
                append_stable,
                fm,
                flags=re.MULTILINE,
            )
            if not n:
                new_fm = fm + "\ntags:\n  - stable"

            note.write_text("---" + new_fm + text[fm_end:], encoding="utf-8")
            updated += 1
        except Exception:
            pass

    return updated


def deduplicate_stable(vault_path: Path, session_rel: str) -> int:
    """
    Merge folders in Stable/ that normalize to the same name.
    Normalization: lowercase, & → and, collapse non-word chars to space.
    Winner = folder with the most tab notes (ties broken by preferring the
    already-sanitized name, i.e. no spaces).
    Returns the number of folders removed.
    """
    stable_dir = vault_path / STABLE
    if not stable_dir.exists():
        return 0

    def _norm(name: str) -> str:
        name = name.lower().replace("&", "and")
        name = re.sub(r"[^\w]+", " ", name).strip()
        return name

    groups: dict[str, list[Path]] = {}
    for d in stable_dir.iterdir():
        if d.is_dir():
            groups.setdefault(_norm(d.name), []).append(d)

    removed = 0
    for dirs in groups.values():
        if len(dirs) <= 1:
            continue

        def _score(d: Path) -> tuple[int, bool]:
            count = sum(1 for f in d.glob("*.md") if f.stem != d.name)
            is_clean = " " not in d.name  # prefer hyphenated over space-separated
            return (count, is_clean)

        dirs.sort(key=_score, reverse=True)
        winner = dirs[0]
        winner_rel = f"{STABLE}/{winner.name}"

        # Read winner's display name from H1
        winner_index = winner / f"{winner.name}.md"
        tag_name = winner.name
        if winner_index.exists():
            try:
                for line in winner_index.read_text(encoding="utf-8").splitlines():
                    if line.startswith("# "):
                        tag_name = line[2:].strip()
                        break
            except Exception:
                pass

        existing_urls = _existing_urls(winner)

        for loser in dirs[1:]:
            for note in sorted(loser.glob("*.md")):
                if note.stem == loser.name:
                    continue  # skip old tag index
                try:
                    text = note.read_text(encoding="utf-8")
                    m = re.search(r"^url:\s*(\S+)", text, re.MULTILINE)
                    url = m.group(1).strip() if m else None
                except Exception:
                    continue

                if url and url in existing_urls:
                    continue  # duplicate URL, skip

                # Repoint wikilinks to the winner folder
                new_text = re.sub(
                    r"\[\[" + re.escape(f"{STABLE}/{loser.name}") + r"/",
                    f"[[{winner_rel}/",
                    text,
                )
                dest = winner / note.name
                if dest.exists():
                    stem, counter = note.stem, 1
                    while (winner / f"{stem}_{counter}.md").exists():
                        counter += 1
                    dest = winner / f"{stem}_{counter}.md"
                dest.write_text(new_text, encoding="utf-8")
                if url:
                    existing_urls.add(url)

            shutil.rmtree(loser)
            print(f"  Merged Stable/{loser.name} → Stable/{winner.name}")
            removed += 1

        # Rewrite winner's tag index to reflect merged notes
        all_notes = _tab_notes_in_folder(winner)
        _write_tag_index(winner, tag_name, all_notes, winner_rel, session_rel, validated=True)

    return removed


def deduplicate_urls_in_stable(vault_path: Path, session_rel: str) -> int:
    """Remove notes with duplicate URLs within each Stable/ tag folder. Returns count deleted."""
    stable_dir = vault_path / STABLE
    if not stable_dir.exists():
        return 0

    deleted = 0
    for tag_dir in stable_dir.iterdir():
        if not tag_dir.is_dir():
            continue

        seen_urls: dict[str, Path] = {}
        to_delete: list[Path] = []

        for note in sorted(tag_dir.glob("*.md")):
            if note.stem == tag_dir.name:
                continue
            try:
                m = re.search(r"^url:\s*(\S+)", note.read_text(encoding="utf-8"), re.MULTILINE)
                url = m.group(1).strip() if m else None
            except Exception:
                url = None

            if not url:
                continue
            if url in seen_urls:
                to_delete.append(note)
            else:
                seen_urls[url] = note

        for note in to_delete:
            note.unlink()
            deleted += 1

        if to_delete:
            tag_name = tag_dir.name
            index_note = tag_dir / f"{tag_dir.name}.md"
            if index_note.exists():
                try:
                    for line in index_note.read_text(encoding="utf-8").splitlines():
                        if line.startswith("# "):
                            tag_name = line[2:].strip()
                            break
                except Exception:
                    pass
            folder_rel = f"{STABLE}/{tag_dir.name}"
            _write_tag_index(tag_dir, tag_name, _tab_notes_in_folder(tag_dir), folder_rel, session_rel, validated=True)

    return deleted


def _existing_urls(tag_dir: Path) -> set[str]:
    urls: set[str] = set()
    for note in tag_dir.glob("*.md"):
        if note.stem == note.parent.name:
            continue
        try:
            m = re.search(r"^url:\s*(\S+)", note.read_text(encoding="utf-8"), re.MULTILINE)
            if m:
                urls.add(m.group(1).strip())
        except Exception:
            pass
    return urls


def _tab_notes_in_folder(tag_dir: Path) -> list[tuple[str, str]]:
    notes = []
    for note in sorted(tag_dir.glob("*.md")):
        if note.stem == note.parent.name:
            continue
        try:
            m = re.search(r'^title:\s*"?(.+?)"?\s*$', note.read_text(encoding="utf-8"), re.MULTILINE)
            title = m.group(1) if m else note.stem
        except Exception:
            title = note.stem
        notes.append((note.stem, title))
    return notes


# ---------------------------------------------------------------------------
# Note writers
# ---------------------------------------------------------------------------

def _write_tab_note(path: Path, tab: dict, folder_rel: str) -> None:
    title = tab["title"].replace('"', '\\"')
    tag_note = sanitize_filename(tab["tag"])
    tag_link = f"[[{folder_rel}/{tag_note}|{tab['tag']}]]"
    content = f"""---
url: {tab['url']}
title: "{title}"
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
    tab_notes: list[tuple[str, str]],
    folder_rel: str,
    session_rel: str,
    validated: bool = False,
) -> None:
    session_link = f"[[{session_rel}/{session_rel}|{session_rel}]]"
    tab_lines = "\n".join(
        f"- [[{folder_rel}/{stem}|{title}]]"
        for stem, title in tab_notes
    )
    # stable/new tag drives graph node color in Obsidian
    status_tag = "stable" if validated else "new"
    content = f"""---
tags:
  - {sanitize_tag(tag_name)}
  - {status_tag}
---

# {tag_name}

Session: {session_link}

## Tabs ({len(tab_notes)})
{tab_lines}
"""
    tag_note_name = sanitize_filename(tag_name)
    (tag_dir / f"{tag_note_name}.md").write_text(content, encoding="utf-8")


def _write_stable_index(vault_path: Path, stable_tags: dict[str, tuple[int, str]]) -> None:
    lines = "\n".join(
        f"- [[{folder_rel}/{sanitize_filename(name)}|{name}]] ({count} tabs)"
        for name, (count, folder_rel) in sorted(stable_tags.items())
    )
    content = f"""---
tags:
  - stable
---

# Stable — Validated Tags

{len(stable_tags)} validated tags.

## Tags
{lines}
"""
    (vault_path / STABLE / "Stable.md").write_text(content, encoding="utf-8")


def _write_session_index(
    session_path: Path,
    saved_date: str,
    new_tags: dict[str, tuple[str, int]],
    validated_tags: dict[str, tuple[str, int, int]],
) -> None:
    new_total = sum(c for _, c in new_tags.values())
    val_new = sum(n for _, n, _ in validated_tags.values())
    total = new_total + val_new
    k = len(new_tags) + len(validated_tags)

    tag_lines = "\n".join(
        f"- [[{folder_rel}/{sanitize_filename(name)}|{name}]] ({count} tabs)"
        for name, (folder_rel, count) in new_tags.items()
    )

    validated_section = ""
    if validated_tags:
        val_lines = "\n".join(
            f"- [[{folder_rel}/{sanitize_filename(name)}|{name}]] (+{new_count} new, {total_count} total)"
            for name, (folder_rel, new_count, total_count) in validated_tags.items()
        )
        validated_section = f"\n## Stable Tags\n{val_lines}\n"

    content = f"""# Safari Tabs — {saved_date}

Saved {total} tabs across {k} tags.

## New Tags
{tag_lines}
{validated_section}"""
    (session_path / f"{saved_date}.md").write_text(content, encoding="utf-8")


def _update_root_index(vault_path: Path, saved_date: str, total_tabs: int) -> None:
    root_index = vault_path / "Safari Tabs.md"
    new_entry = f"- [[{saved_date}/{saved_date}|{saved_date}]] — {total_tabs} tabs"

    if root_index.exists():
        existing = root_index.read_text(encoding="utf-8")
        if f"[[{saved_date}/{saved_date}" in existing:
            return
        updated = existing.rstrip() + "\n" + new_entry + "\n"
        root_index.write_text(updated, encoding="utf-8")
    else:
        content = f"""# Safari Tabs Archive

## Sessions
{new_entry}
"""
        root_index.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def write_vault(
    tags: dict[str, list[dict]],
    vault_path: Path,
    saved_date: str,
) -> None:
    """
    Write all tabs to the Obsidian vault.

    Validation is folder-based: any subfolder of Stable/ is treated as a
    validated tag. To validate a tag, simply move its folder into Stable/ in
    Obsidian or Finder — no frontmatter editing required.

    Validated tags get new tabs appended to Stable/{Tag}/ and are linked from
    the session index so they stay connected in the graph view.
    """
    session_path = vault_path / saved_date
    if session_path.exists():
        stamp = datetime.now().strftime("%H%M")
        saved_date = f"{saved_date}-{stamp}"
        session_path = vault_path / saved_date
    session_path.mkdir(parents=True, exist_ok=True)

    stable_path = vault_path / STABLE
    stable_path.mkdir(exist_ok=True)

    backfilled = backfill_stable_tags(vault_path)
    if backfilled:
        print(f"  Backfilled 'stable' tag into {backfilled} note(s) in Stable/")

    merged = deduplicate_stable(vault_path, saved_date)
    if merged:
        print(f"  Removed {merged} duplicate folder(s) from Stable/")

    deduped_urls = deduplicate_urls_in_stable(vault_path, saved_date)
    if deduped_urls:
        print(f"  Removed {deduped_urls} duplicate URL note(s) from Stable/")

    previously_validated = find_validated_tags(vault_path)
    if previously_validated:
        print(f"Stable tags: {', '.join(previously_validated.keys())}")
    else:
        print("No stable tags found.")

    new_tags: dict[str, tuple[str, int]] = {}
    validated_used: dict[str, tuple[str, int, int]] = {}

    for tag_name, tabs in tags.items():
        folder_name = sanitize_filename(tag_name)

        if folder_name in previously_validated:
            # ---- Stable tag: append new tabs to Stable/{Tag}/ ----
            tag_dir = stable_path / folder_name
            tag_dir.mkdir(exist_ok=True)
            folder_rel = f"{STABLE}/{folder_name}"

            existing_urls = _existing_urls(tag_dir)
            new_tabs = [t for t in tabs if t["url"] not in existing_urls]
            for tab in new_tabs:
                base = sanitize_filename(tab["title"])
                stem = base
                counter = 1
                while (tag_dir / f"{stem}.md").exists():
                    stem = f"{base}_{counter}"
                    counter += 1
                _write_tab_note(tag_dir / f"{stem}.md", tab, folder_rel)

            all_notes = _tab_notes_in_folder(tag_dir)
            _write_tag_index(tag_dir, tag_name, all_notes, folder_rel, saved_date, validated=True)
            validated_used[tag_name] = (folder_rel, len(new_tabs), len(all_notes))

        else:
            # ---- New tag: write to dated session folder ----
            tag_dir = session_path / folder_name
            tag_dir.mkdir(exist_ok=True)
            folder_rel = f"{saved_date}/{folder_name}"

            seen_names: dict[str, int] = {}
            tab_notes: list[tuple[str, str]] = []

            for tab in tabs:
                base_name = sanitize_filename(tab["title"])
                if base_name in seen_names:
                    seen_names[base_name] += 1
                    stem = f"{base_name}_{seen_names[base_name]}"
                else:
                    seen_names[base_name] = 1
                    stem = base_name
                tab_notes.append((stem, tab["title"]))
                _write_tab_note(tag_dir / f"{stem}.md", tab, folder_rel)

            _write_tag_index(tag_dir, tag_name, tab_notes, folder_rel, saved_date, validated=False)
            new_tags[tag_name] = (folder_rel, len(tabs))

    # Rebuild Stable/Stable.md
    all_stable: dict[str, tuple[int, str]] = {}
    for tag_dir in stable_path.iterdir():
        if tag_dir.is_dir():
            notes = _tab_notes_in_folder(tag_dir)
            if notes:
                all_stable[tag_dir.name] = (len(notes), f"{STABLE}/{tag_dir.name}")
    _write_stable_index(vault_path, all_stable)

    _write_session_index(session_path, saved_date, new_tags, validated_used)
    total_tabs = sum(c for _, c in new_tags.values()) + sum(n for _, n, _ in validated_used.values())
    _update_root_index(vault_path, saved_date, total_tabs)
