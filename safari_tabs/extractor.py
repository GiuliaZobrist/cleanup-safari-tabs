import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

CLOUD_TABS_DBS = [
    Path.home() / "Library" / "Containers" / "com.apple.Safari" / "Data" / "Library" / "Safari" / "CloudTabs.db",
    Path.home() / "Library" / "Safari" / "CloudTabs.db",  # older macOS; may hold only stale data
]

APPLESCRIPT = """
tell application "Safari"
    set tabData to ""
    repeat with w in windows
        repeat with t in tabs of w
            set tabData to tabData & (name of t) & "\t" & (URL of t) & "\n"
        end repeat
    end repeat
    return tabData
end tell
"""


def get_icloud_tabs(db_path: Path | None = None) -> list[dict]:
    """
    Read tabs open on other devices (Safari iCloud Tabs) from CloudTabs.db.
    Each dict has keys: 'title' (str), 'url' (str), 'source' (str, the device).

    Raises:
        RuntimeError: if the database is missing or unreadable (usually because
            the terminal lacks Full Disk Access)
    """
    if db_path is None:
        db_path = next((p for p in CLOUD_TABS_DBS if p.exists()), CLOUD_TABS_DBS[0])
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            device_cols = [r[1] for r in conn.execute("PRAGMA table_info(cloud_tab_devices)")]
            name_col = next((c for c in device_cols if "name" in c.lower()), "device_uuid")
            rows = conn.execute(
                f"SELECT t.title, t.url, d.{name_col} FROM cloud_tabs t "
                "LEFT JOIN cloud_tab_devices d ON d.device_uuid = t.device_uuid"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(
            f"Could not read iCloud tabs ({e}). Grant your terminal Full Disk Access in "
            "System Settings → Privacy & Security → Full Disk Access."
        ) from e

    return [
        {"title": (title or "").strip(), "url": (url or "").strip(), "source": f"iCloud: {device or 'unknown device'}"}
        for title, url, device in rows
    ]


def get_safari_tabs(include_icloud: bool = True) -> list[dict]:
    """
    Run AppleScript via osascript and return a list of tab dicts.
    Each dict has keys: 'title' (str), 'url' (str).
    If include_icloud is True, tabs from other devices are added as well; if they
    cannot be read, a warning is printed and only local tabs are returned.

    Raises:
        RuntimeError: if Safari is not running or osascript fails
        ValueError: if no tabs are found
    """
    result = subprocess.run(
        ["osascript", "-e", APPLESCRIPT],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Application isn't running" in stderr or "Safari" in stderr:
            raise RuntimeError("Safari is not running. Please open Safari with your tabs and try again.")
        raise RuntimeError(f"AppleScript failed: {stderr}")

    raw_tabs = []
    for line in result.stdout.splitlines():
        parts = line.strip().split("\t", maxsplit=1)
        if len(parts) == 2:
            raw_tabs.append({"title": parts[0].strip(), "url": parts[1].strip(), "source": "This Safari"})

    if include_icloud:
        try:
            raw_tabs += get_icloud_tabs()
        except RuntimeError as e:
            print(f"Warning: {e}\nContinuing with local tabs only.", file=sys.stderr)

    tabs = []
    seen_urls: set[str] = set()
    per_source: dict[str, int] = {}

    for raw in raw_tabs:
        title, url = raw["title"], raw["url"]

        if not url or not url.startswith("http"):
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        if not title or title in ("", "Loading…", "Untitled"):
            try:
                title = urlparse(url).hostname or url
            except ValueError:
                title = url

        tabs.append({"title": title, "url": url})
        per_source[raw["source"]] = per_source.get(raw["source"], 0) + 1

    for source, count in per_source.items():
        print(f"  • {source}: {count} tab(s)")

    if not tabs:
        raise ValueError("No tabs found. Make sure Safari is open with tabs.")

    return tabs
