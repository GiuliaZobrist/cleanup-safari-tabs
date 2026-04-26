import json
from urllib.parse import urlparse

import anthropic

SYSTEM_PROMPT = """You are an expert at organizing browser tabs into meaningful tags.

Each tab is shown as:  INDEX. [domain] Title — URL

Rules:
- Derive tag names from what is actually present in the tabs — do NOT use a fixed preset list
  - If several tabs share a service or site (e.g. claude.ai, github.com, booking.com), name the tag after it (e.g. "Claude", "GitHub", "Hotels")
  - If tabs share a topic across different sites (e.g. multiple recipe blogs), name the tag by topic (e.g. "Recipes")
  - For a single miscellaneous tab with no natural group, use a short descriptive label
- When a title is generic (e.g. "Sign In", "Home", "Loading", "403 Forbidden", "Untitled"), infer the topic from the domain and URL path instead
- Every tab must be assigned to exactly one tag
- Tag names should be short (1–3 words), title-cased
- Create between 3 and 15 tags total

Respond ONLY with valid JSON in this exact format:
{
  "tags": [
    {
      "name": "TagName",
      "tabs": [0, 3, 7]
    }
  ]
}

Where the tab indices refer to the 0-based position in the input list."""


def _domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.removeprefix("www.")
    except Exception:
        return ""


def categorize_tabs(
    tabs: list[dict],
    client: anthropic.Anthropic,
    model: str = "claude-sonnet-4-6",
    validated_tags: list[str] | None = None,
) -> tuple[dict[str, list[dict]], anthropic.types.Usage]:
    """
    Send all tabs to Claude in one call.
    Returns dict of {tag_name: [tab_dicts]}.
    Each tab_dict has 'title', 'url', and 'tag' keys.
    validated_tags: display names of already-validated tags; Claude will reuse
                    them exactly when content matches.
    """
    tab_lines = "\n".join(
        f"{i}. [{_domain(tab['url'])}] {tab['title']} — {tab['url']}"
        for i, tab in enumerate(tabs)
    )
    validated_hint = ""
    if validated_tags:
        names = ", ".join(f'"{n}"' for n in validated_tags)
        validated_hint = (
            f"\n\nIMPORTANT: The following tag names are already validated and stable. "
            f"If any tabs belong to one of these topics, use the EXACT same name: {names}."
        )
    user_message = (
        f"Here are {len(tabs)} open browser tabs to tag:\n\n{tab_lines}"
        f"{validated_hint}\n\nAssign each tab index to a tag. Return only JSON."
    )

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    usage = response.usage
    raw = response.content[0].text.strip()

    # Extract the JSON object — handles markdown fences, preamble, postamble
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[categorizer] JSON parse failed: {exc}\nRaw response:\n{raw[:500]}", flush=True)
        return {"Unsorted": [{**t, "tag": "Unsorted"} for t in tabs]}, usage

    result: dict[str, list[dict]] = {}
    assigned: set[int] = set()

    for entry in data.get("tags", []):
        name = entry.get("name", "Other")
        indices = entry.get("tabs", [])
        tag_tabs = []
        for idx in indices:
            if not isinstance(idx, int) or idx < 0 or idx >= len(tabs):
                continue
            if idx in assigned:
                continue
            assigned.add(idx)
            tag_tabs.append({**tabs[idx], "tag": name})
        if tag_tabs:
            result[name] = tag_tabs

    # Collect any unassigned tabs into "Other"
    unassigned = [
        {**tabs[i], "tag": "Other"}
        for i in range(len(tabs))
        if i not in assigned
    ]
    if unassigned:
        result.setdefault("Other", []).extend(unassigned)

    return result, usage
