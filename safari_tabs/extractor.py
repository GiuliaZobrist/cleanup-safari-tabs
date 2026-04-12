import subprocess
from urllib.parse import urlparse

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


def get_safari_tabs() -> list[dict]:
    """
    Run AppleScript via osascript and return a list of tab dicts.
    Each dict has keys: 'title' (str), 'url' (str).

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

    tabs = []
    seen_urls: set[str] = set()

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t", maxsplit=1)
        if len(parts) != 2:
            continue

        title, url = parts[0].strip(), parts[1].strip()

        if not url or not url.startswith("http"):
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        if not title or title in ("", "Loading…", "Untitled"):
            try:
                title = urlparse(url).hostname or url
            except Exception:
                title = url

        tabs.append({"title": title, "url": url})

    if not tabs:
        raise ValueError("No tabs found. Make sure Safari is open with tabs.")

    return tabs
