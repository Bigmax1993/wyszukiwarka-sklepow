import pytest
import requests

import main


class DummyResponse:
    def __init__(self, payload, raise_error=False):
        self._payload = payload
        self._raise_error = raise_error

    def raise_for_status(self):
        if self._raise_error:
            raise requests.HTTPError("boom")

    def json(self):
        return self._payload


def test_get_required_env_returns_value(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "abc123")
    assert main.get_required_env("GOOGLE_API_KEY") == "abc123"


def test_get_required_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Brak zmiennej srodowiskowej: GOOGLE_API_KEY"):
        main.get_required_env("GOOGLE_API_KEY")


def test_safe_request_retries_and_succeeds(monkeypatch):
    calls = {"count": 0}
    sleep_calls = []

    def fake_request(method, url, timeout=30, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.RequestException("temporary")
        return DummyResponse({"ok": True})

    monkeypatch.setattr(main.requests, "request", fake_request)
    monkeypatch.setattr(main.time, "sleep", lambda value: sleep_calls.append(value))

    response = main.safe_request("GET", "https://example.com")
    assert response.json() == {"ok": True}
    assert calls["count"] == 3
    assert sleep_calls == [1, 2]


def test_get_contractor_info_returns_fallback_on_invalid_json(monkeypatch):
    bad_payload = {
        "candidates": [{"content": {"parts": [{"text": "to nie jest json"}]}}]
    }

    monkeypatch.setattr(main, "safe_request", lambda *args, **kwargs: DummyResponse(bad_payload))

    result = main.get_contractor_info("Test Address", gemini_api_key="key")
    assert result["contractor_name"] is None
    assert result["confidence"] == 0.0
    assert result["sources"] == []
    assert "Brak parsowalnej odpowiedzi Gemini" in result["reasoning"]


def test_enforce_allowed_characters_removes_control_chars():
    text = "Line1\x00\x1f\nLine2\tOK"
    assert main.enforce_allowed_characters(text) == "Line1 Line2 OK"


def test_safe_request_raises_on_google_limit(monkeypatch):
    main.google_requests_count = main.GOOGLE_MAX_REQUESTS

    with pytest.raises(main.ApiLimitExceeded, match="Przekroczono limit Google API"):
        main.safe_request("GET", main.PLACES_TEXTSEARCH_URL, params={"key": "x"})


def test_safe_request_raises_on_gemini_limit(monkeypatch):
    main.gemini_requests_count = main.GEMINI_MAX_REQUESTS

    with pytest.raises(main.ApiLimitExceeded, match="Przekroczono limit Gemini API"):
        main.safe_request("POST", main.GEMINI_URL, json={})
