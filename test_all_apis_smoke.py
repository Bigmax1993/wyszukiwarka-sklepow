import main


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_google_places_api_smoke(monkeypatch):
    captured = {}

    def fake_request(method, url, timeout=30, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return DummyResponse({"results": [{"place_id": "g-1"}]})

    monkeypatch.setattr(main.requests, "request", fake_request)

    stores = main.get_stores("REWE", 52.52, 13.405, "google-key", 5000)

    assert stores == [{"place_id": "g-1"}]
    assert captured["method"] == "GET"
    assert captured["url"] == main.PLACES_TEXTSEARCH_URL
    assert captured["params"]["key"] == "google-key"
    assert captured["params"]["region"] == "de"
    assert captured["params"]["radius"] == 50000


def test_gemini_api_smoke(monkeypatch):
    captured = {}

    def fake_safe_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return DummyResponse(
            {
                "candidates": [
                    {"content": {"parts": [{"text": '{"contractor_name":"Firma G"}'}]}}
                ]
            }
        )

    monkeypatch.setattr(main, "safe_request", fake_safe_request)

    data = main.get_contractor_info("Berlin, Germany", "gemini-key")

    assert data["contractor_name"] == "Firma G"
    assert captured["method"] == "POST"
    assert captured["url"] == main.GEMINI_URL
    assert captured["params"]["key"] == "gemini-key"


def test_openai_api_smoke(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=30):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return DummyResponse({"choices": [{"message": {"content": "ABC-123"}}]})

    monkeypatch.setattr(main.requests, "post", fake_post)

    cleaned = main.remove_special_chars_with_openai("A@B#C-123", "openai-key")

    assert cleaned == "ABC-123"
    assert captured["url"] == main.OPENAI_URL
    assert captured["headers"]["Authorization"] == "Bearer openai-key"


def test_email_api_smoke(monkeypatch, tmp_path):
    monkeypatch.setenv("SMTP_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_SENDER_APP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")

    sent = {}

    class FakeSMTP:
        def __init__(self, user, password, host, port):
            sent["user"] = user
            sent["password"] = password
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def send(self, to, subject, contents, attachments):
            sent["to"] = to
            sent["subject"] = subject
            sent["contents"] = contents
            sent["attachments"] = attachments

    monkeypatch.setattr(main.yagmail, "SMTP", FakeSMTP)

    csv_file = tmp_path / "report.csv"
    csv_file.write_text("id,name\n1,Store\n", encoding="utf-8")
    main.send_csv_report_via_email(str(csv_file), records_count=1)

    assert sent["to"] == "svinchak1993@gmail.com"
    assert sent["attachments"] == [str(csv_file)]
