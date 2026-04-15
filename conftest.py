import pytest

import main


class _DummyPostResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _NoopSMTP:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def send(self, *args, **kwargs):
        return None


@pytest.fixture(autouse=True)
def isolate_external_side_effects(monkeypatch):
    monkeypatch.setattr(
        main.requests,
        "post",
        lambda *args, **kwargs: _DummyPostResponse(kwargs.get("json", {}).get("messages", [{}])[-1].get("content", "")),
    )
    monkeypatch.setattr(main.yagmail, "SMTP", _NoopSMTP)
    main.google_requests_count = 0
    main.gemini_requests_count = 0
