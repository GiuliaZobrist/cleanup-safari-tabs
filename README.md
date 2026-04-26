# safari-tabs

CLI tool that exports all open Safari tabs to a categorized [Obsidian](https://obsidian.md) vault using Claude AI.

## What it does

1. Reads every open tab from Safari via AppleScript
2. Sends them to Claude, which groups them into named tags (3–15 per run) derived from the actual content — not a preset list
3. Writes each tab as a note inside `~/Documents/safari-tabs-vault/`, organized by date and tag
4. Maintains a `Stable/` folder for tags you've validated — those get new tabs appended rather than re-created each run

Running the tool a second time on the same day creates a timestamped folder (`2026-04-11-1430/`) so sessions are never overwritten.

## Setup

```bash
poetry install
```

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-...
# or add it to a .env file in the project root
```

> **(!) macOS Automation permission** — the first time you run this, macOS may block AppleScript access to Safari. If you see an "unauthorized" error, go to **System Settings → Privacy & Security → Automation** and enable **Safari** under your terminal app.
>
> ![macOS Automation permission screen showing Terminal with Safari enabled](assets/macos-automation-permission.png)

## Usage

```bash
poetry run safari-tabs
```

Each run prints a token usage summary at the end:

```
Tokens: 4821 in (3200 cached, 0 written to cache) / 312 out — billed input: 1621
```

## Validating tags (Stable folder)

To mark a tag as **stable** so it persists across runs:

1. Open the vault in Obsidian or Finder
2. Drag any tag folder (e.g. `2026-04-26/Claude-AI/`) into the `Stable/` folder
3. On the next run, the tool detects it automatically — new tabs for that topic are appended to `Stable/Claude-AI/` and linked from the session index

No frontmatter editing required. Presence in `Stable/` is the signal.

## Graph coloring in Obsidian

Tag index notes carry either `#stable` or `#new` in their frontmatter. To color them differently in the graph view:

1. Open **Settings → Graph view → Groups**
2. Add a group with query `tag:#stable` and assign it a color
3. Add a group with query `tag:#new` and assign it a different color

## Vault structure

```
~/Documents/safari-tabs-vault/
  Safari Tabs.md          ← root index of all sessions
  Stable/
    Stable.md             ← index of all validated tags
    Claude-AI/
      Claude-AI.md        ← tag index  (tags: [stable])
      some-tab.md
  2026-04-26/
    2026-04-26.md         ← session index (links to both new and stable tags)
    MCP-Servers/
      MCP-Servers.md      ← tag index  (tags: [new])
      some-tab.md
```

## Requirements

- macOS (AppleScript is macOS-only)
- Safari open with tabs
- Python 3.11+
- An Anthropic API key

## Todo / Next steps

- [ ] Run again and validate end-to-end behaviour in Obsidian graph view
- [ ] Study the code and write essential tests (categorizer, vault writer, dedup logic)
- [ ] Ask Claude to refactor for simplicity — reduce code, improve efficiency
- [ ] Take screenshots of the Obsidian graph and vault, and improve the README with visuals
- [ ] Security review and clean-up before making the repo public
- [ ] Extend to other tab sources: Safari bookmarks and Safari tabs on iPhone
