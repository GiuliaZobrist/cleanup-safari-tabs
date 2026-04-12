# cleanup-safari-tabs

Export all open Safari tabs to a tagged Obsidian vault using Claude AI.

## What it does

1. Reads every open tab from Safari (title + URL) via AppleScript
2. Sends them to Claude, which assigns each tab a tag derived from the actual content — e.g. `Claude`, `GitHub`, `Hotels`, `Recipes` — not a preset list
3. Creates a dated session folder inside `~/Documents/safari-tabs-vault/` with one Markdown note per tab, a tag index note per tag, and a session index

Running the tool a second time on the same day creates a timestamped folder (e.g. `2026-04-11-1430/`) so sessions are never overwritten.

## Output structure

```
~/Documents/safari-tabs-vault/
├── _Index.md                  ← archive of all sessions
├── 2026-04-11/
│   ├── _Index.md              ← session index, links to all tags
│   ├── Claude/
│   │   ├── Claude.md          ← tag index note (graph hub)
│   │   └── New-chat.md
│   └── Hotels/
│       ├── Hotels.md          ← tag index note (graph hub)
│       └── Sign-In.md
└── 2026-04-11-1430/           ← second run same day
    └── ...
```

Each tab note contains the page title, URL, a clickable "Open →" link, and a wikilink back to its tag index note — so the Obsidian graph view shows the full connection tree.

## Setup

```bash
poetry install
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

Get an API key at https://console.anthropic.com.

## Usage

Make sure Safari is open with your tabs, then:

> **(!) macOS Automation permission required** — the first time you run this, macOS may block AppleScript access to Safari. If you see an "unauthorized" error, go to **System Settings → Privacy & Security → Automation** and enable **Safari** under your terminal app.

```bash
poetry run python -m safari_tabs
```

Or use the installed script:

```bash
poetry run safari-tabs
```

## Requirements

- macOS (AppleScript is macOS-only)
- Safari open with tabs
- Python 3.11+
- An Anthropic API key
