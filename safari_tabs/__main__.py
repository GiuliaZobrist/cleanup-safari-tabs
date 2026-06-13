import os
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from safari_tabs.categorizer import categorize_tabs
from safari_tabs.extractor import get_safari_tabs
from safari_tabs.sanitizer import sanitize_tabs
from safari_tabs.vault_writer import get_validated_tag_names, write_vault

DEFAULT_VAULT_PATH = Path.home() / "Documents" / "safari-tabs-vault"


def main() -> None:
    load_dotenv()

    vault_env = os.environ.get("SAFARI_TABS_VAULT")
    VAULT_PATH = Path(vault_env) if vault_env else DEFAULT_VAULT_PATH

    print("Extracting Safari tabs...")
    try:
        tabs = get_safari_tabs()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(tabs)} tabs.")

    tabs, flagged = sanitize_tabs(tabs)
    if flagged:
        print(f"\nWARNING: {len(flagged)} tab(s) contained sensitive data in their URL — redacted before saving:")
        for item in flagged:
            print(f"  • {item['title']}")
            for reason in item["reasons"]:
                print(f"      – {reason}")
        print()

    validated_names = get_validated_tag_names(VAULT_PATH)
    if validated_names:
        print(f"Stable tags (will be preserved): {', '.join(validated_names)}")

    print("Categorizing with Claude...")
    try:
        client = anthropic.Anthropic()
        clusters, usage = categorize_tabs(tabs, client, validated_tags=validated_names or None)
    except anthropic.AuthenticationError:
        print(
            "Error: Invalid or missing Anthropic API key.\n"
            "Set ANTHROPIC_API_KEY in a .env file or as an environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)
    except anthropic.APIStatusError as e:
        print(f"Error: Claude API returned status {e.status_code}: {e.message}", file=sys.stderr)
        sys.exit(1)

    tag_summary = ", ".join(
        f"{name} ({len(t)})" for name, t in clusters.items()
    )
    print(f"Tags: {tag_summary}")

    saved_date = date.today().isoformat()
    print(f"Writing vault to {VAULT_PATH}/{saved_date}/...")
    write_vault(clusters, VAULT_PATH, saved_date)

    total = sum(len(t) for t in clusters.values())
    print(f"\nDone. Saved {total} tabs across {len(clusters)} tags.")
    print(f"Vault: {VAULT_PATH}")
    print(f"Open 'Safari Tabs.md' or the {saved_date}/ folder in Obsidian to browse.")

    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    billed_input = usage.input_tokens - cache_read
    print(
        f"\nTokens: {usage.input_tokens} in ({cache_read} cached, {cache_write} written to cache)"
        f" / {usage.output_tokens} out"
        f" — billed input: {billed_input}"
    )

    print("\nReminder: close or clear your Safari tabs now that they've been saved.")


if __name__ == "__main__":
    main()
