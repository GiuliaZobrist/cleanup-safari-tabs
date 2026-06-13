import pytest
from safari_tabs.sanitizer import sanitize_url, sanitize_tabs, REDACTED


# ---------------------------------------------------------------------------
# sanitize_url — individual URL
# ---------------------------------------------------------------------------

class TestCleanUrls:
    def test_clean_url_unchanged(self):
        url = "https://example.com/path?q=hello&page=2"
        r = sanitize_url(url)
        assert r.url == url
        assert not r.was_changed
        assert r.reasons == []

    def test_clean_url_no_query(self):
        url = "https://example.com/article/123"
        r = sanitize_url(url)
        assert r.url == url
        assert not r.was_changed


class TestEmbeddedCredentials:
    def test_strips_user_and_password(self):
        r = sanitize_url("https://user:secret@example.com/path")
        assert "user" not in r.url
        assert "secret" not in r.url
        assert "example.com" in r.url
        assert r.was_changed
        assert any("credential" in reason for reason in r.reasons)

    def test_strips_user_only(self):
        r = sanitize_url("https://user@example.com/")
        assert "user" not in r.url
        assert r.was_changed

    def test_preserves_port_after_stripping_credentials(self):
        r = sanitize_url("https://user:pass@example.com:8080/path")
        assert "8080" in r.url
        assert "user" not in r.url


class TestSensitiveQueryParams:
    @pytest.mark.parametrize("param", [
        "token", "access_token", "refresh_token", "id_token",
        "api_key", "apikey", "client_secret", "secret",
        "password", "passwd", "pwd",
        "session_id", "sessionid",
        "x-amz-signature", "x-amz-security-token",
    ])
    def test_redacts_sensitive_param(self, param):
        url = f"https://example.com/page?{param}=supersecret&safe=yes"
        r = sanitize_url(url)
        assert "supersecret" not in r.url
        assert "safe=yes" in r.url
        assert r.was_changed
        assert r.reasons  # param was flagged

    def test_case_insensitive_matching(self):
        r = sanitize_url("https://example.com/?API_KEY=abc123")
        assert "abc123" not in r.url
        assert r.was_changed

    def test_safe_params_preserved(self):
        url = "https://example.com/?q=python&page=3&sort=asc"
        r = sanitize_url(url)
        assert not r.was_changed
        assert r.url == url

    def test_multiple_sensitive_params_all_redacted(self):
        url = "https://example.com/?token=abc&api_key=xyz&q=search"
        r = sanitize_url(url)
        assert "abc" not in r.url
        assert "xyz" not in r.url
        assert "search" in r.url
        assert r.was_changed

    def test_original_url_preserved(self):
        url = "https://example.com/?token=abc"
        r = sanitize_url(url)
        assert r.original_url == url


class TestFragmentTokens:
    def test_redacts_access_token_in_fragment(self):
        url = "https://example.com/callback#access_token=mytoken&state=xyz"
        r = sanitize_url(url)
        assert "mytoken" not in r.url
        assert r.was_changed

    def test_redacts_refresh_token_in_fragment(self):
        r = sanitize_url("https://example.com/#refresh_token=rt123&uid=42")
        assert "rt123" not in r.url
        assert "uid=42" in r.url

    def test_fragment_without_kv_pairs_untouched(self):
        url = "https://example.com/page#section-3"
        r = sanitize_url(url)
        assert not r.was_changed
        assert r.url == url


# ---------------------------------------------------------------------------
# sanitize_tabs — batch processing
# ---------------------------------------------------------------------------

class TestSanitizeTabs:
    def test_clean_tabs_return_unchanged(self):
        tabs = [
            {"title": "Python docs", "url": "https://docs.python.org/3/"},
            {"title": "GitHub", "url": "https://github.com/explore"},
        ]
        clean, flagged = sanitize_tabs(tabs)
        assert len(clean) == 2
        assert flagged == []

    def test_flagged_tab_reported(self):
        tabs = [{"title": "OAuth redirect", "url": "https://app.com/cb?token=abc"}]
        clean, flagged = sanitize_tabs(tabs)
        assert len(flagged) == 1
        assert flagged[0]["title"] == "OAuth redirect"
        assert "abc" not in clean[0]["url"]

    def test_mixed_tabs_only_dirty_flagged(self):
        tabs = [
            {"title": "Safe", "url": "https://example.com/"},
            {"title": "Dirty", "url": "https://example.com/?api_key=secret"},
        ]
        clean, flagged = sanitize_tabs(tabs)
        assert len(flagged) == 1
        assert flagged[0]["title"] == "Dirty"

    def test_output_length_matches_input(self):
        tabs = [{"title": f"Tab {i}", "url": f"https://example.com/{i}"} for i in range(10)]
        clean, _ = sanitize_tabs(tabs)
        assert len(clean) == 10
