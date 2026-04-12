"""
URL sanitizer — strips credentials, tokens, and other secrets from tab URLs
before they are written to the Obsidian vault.

Three attack surfaces are covered:
  1. Embedded Basic-Auth credentials:  https://user:pass@host/
  2. Sensitive query parameters:       ?api_key=…&token=…&password=…
  3. OAuth tokens in the fragment:     #access_token=…&refresh_token=…
"""

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query-param / fragment-key names that are considered sensitive.
# Matched case-insensitively against the full parameter name.
_SENSITIVE_PARAMS = re.compile(
    r"""
    ^(
        # tokens & keys
        token | access[_-]token | refresh[_-]token | id[_-]token |
        api[_-]?key | apikey | client[_-]?secret | secret |
        jwt | bearer |
        # credentials
        password | passwd | pwd | pass |
        # auth codes & sessions
        auth | auth[_-]code | authorization | code |
        session[_-]?id? | sess |
        # signatures (AWS presigned URLs, etc.)
        sig | signature |
        x-amz-signature | x-amz-security-token | x-amz-credential |
        # catch-all patterns
        .*[_-]token | .*[_-]secret | .*[_-]key | .*[_-]password
    )$
    """,
    re.VERBOSE | re.IGNORECASE,
)

REDACTED = "[REDACTED]"


@dataclass
class SanitizeResult:
    url: str                          # possibly cleaned URL
    original_url: str                 # always the raw URL
    reasons: list[str] = field(default_factory=list)

    @property
    def was_changed(self) -> bool:
        return bool(self.reasons)


def sanitize_url(url: str) -> SanitizeResult:
    """
    Return a SanitizeResult with a scrubbed URL and a list of reasons
    describing what was removed (empty list = nothing changed).
    """
    result = SanitizeResult(url=url, original_url=url)

    try:
        parsed = urlparse(url)
    except Exception:
        return result  # unparseable — leave as-is

    changed = False

    # ------------------------------------------------------------------
    # 1. Embedded credentials in the netloc  (user:pass@host)
    # ------------------------------------------------------------------
    if parsed.username or parsed.password:
        result.reasons.append("embedded credentials (user:password@host)")
        # Rebuild netloc without the userinfo part
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        parsed = parsed._replace(netloc=host)
        changed = True

    # ------------------------------------------------------------------
    # 2. Sensitive query parameters
    # ------------------------------------------------------------------
    if parsed.query:
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        new_pairs = []
        redacted_keys = []
        for k, v in pairs:
            if _SENSITIVE_PARAMS.match(k):
                new_pairs.append((k, REDACTED))
                redacted_keys.append(k)
            else:
                new_pairs.append((k, v))
        if redacted_keys:
            result.reasons.append(f"query params: {', '.join(redacted_keys)}")
            parsed = parsed._replace(query=urlencode(new_pairs))
            changed = True

    # ------------------------------------------------------------------
    # 3. OAuth / token data in the URL fragment  (#access_token=…)
    # ------------------------------------------------------------------
    if parsed.fragment and "=" in parsed.fragment:
        pairs = parse_qsl(parsed.fragment, keep_blank_values=True)
        new_pairs = []
        redacted_keys = []
        for k, v in pairs:
            if _SENSITIVE_PARAMS.match(k):
                new_pairs.append((k, REDACTED))
                redacted_keys.append(k)
            else:
                new_pairs.append((k, v))
        if redacted_keys:
            result.reasons.append(f"fragment params: {', '.join(redacted_keys)}")
            parsed = parsed._replace(fragment=urlencode(new_pairs))
            changed = True

    if changed:
        result.url = urlunparse(parsed)

    return result


def sanitize_tabs(tabs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Sanitize a list of tab dicts in-place (url field only).

    Returns:
        (clean_tabs, flagged)  where flagged is a list of dicts:
            {"title": …, "original_url": …, "sanitized_url": …, "reasons": […]}
    """
    flagged = []
    clean_tabs = []

    for tab in tabs:
        sr = sanitize_url(tab["url"])
        new_tab = dict(tab)
        new_tab["url"] = sr.url
        clean_tabs.append(new_tab)
        if sr.was_changed:
            flagged.append(
                {
                    "title": tab["title"],
                    "original_url": sr.original_url,
                    "sanitized_url": sr.url,
                    "reasons": sr.reasons,
                }
            )

    return clean_tabs, flagged
