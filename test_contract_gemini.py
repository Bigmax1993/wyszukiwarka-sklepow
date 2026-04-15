import main


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_contractor_info_fallback_when_candidates_missing(monkeypatch):
    monkeypatch.setattr(main, "safe_request", lambda *args, **kwargs: DummyResponse({}))
    result = main.get_contractor_info("Adres 1", "gem-key")
    assert result["contractor_name"] is None
    assert result["confidence"] == 0.0


def test_get_contractor_info_fallback_when_parts_missing(monkeypatch):
    payload = {"candidates": [{"content": {}}]}
    monkeypatch.setattr(main, "safe_request", lambda *args, **kwargs: DummyResponse(payload))
    result = main.get_contractor_info("Adres 2", "gem-key")
    assert result["sources"] == []
    assert "Brak parsowalnej odpowiedzi Gemini" in result["reasoning"]


def test_get_contractor_info_valid_json_without_all_fields(monkeypatch):
    payload = {
        "candidates": [{"content": {"parts": [{"text": '{"contractor_name":"Firma Y"}'}]}}]
    }
    monkeypatch.setattr(main, "safe_request", lambda *args, **kwargs: DummyResponse(payload))
    result = main.get_contractor_info("Adres 3", "gem-key")
    assert result["contractor_name"] == "Firma Y"
