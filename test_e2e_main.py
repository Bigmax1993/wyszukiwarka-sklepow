import csv
import json

import main


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_e2e_pipeline_creates_csv_json_and_sends_email(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STORE_CHAINS", ["REWE"])
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("SMTP_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_SENDER_APP_PASSWORD", "app-pass")
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    def fake_request(method, url, timeout=30, **kwargs):
        if "maps.googleapis.com" in url:
            return DummyResponse(
                {
                    "results": [
                        {
                            "place_id": "e2e-1",
                            "name": "REWE #1",
                            "formatted_address": "Berlin, Germany",
                            "business_status": "CLOSED_TEMPORARILY",
                        }
                    ]
                }
            )
        if "generativelanguage.googleapis.com" in url:
            return DummyResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": '{"contractor_name":"Firma-X","confidence":0.9,"sources":[],"reasoning":"OK"}'
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
        raise AssertionError(f"Unexpected URL in requests.request: {url}")

    def fake_openai_post(url, headers=None, json=None, timeout=30):
        return DummyResponse({"choices": [{"message": {"content": "CLEANED TEXT"}}]})

    sent_payload = {}

    class FakeSMTP:
        def __init__(self, user, password, host, port):
            self.user = user
            self.password = password
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def send(self, to, subject, contents, attachments):
            sent_payload["to"] = to
            sent_payload["subject"] = subject
            sent_payload["contents"] = contents
            sent_payload["attachments"] = attachments

    monkeypatch.setattr(main.requests, "request", fake_request)
    monkeypatch.setattr(main.requests, "post", fake_openai_post)
    monkeypatch.setattr(main.yagmail, "SMTP", FakeSMTP)

    output_file = tmp_path / "e2e.csv"
    main.process_and_export(52.52, 13.405, 30000, str(output_file), 0)

    json_file = tmp_path / "e2e.json"
    assert output_file.exists()
    assert json_file.exists()

    with output_file.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    assert rows[0]["place_id"] == "e2e-1"

    with json_file.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    assert "e2e-1" in payload

    assert sent_payload["to"] == "svinchak1993@gmail.com"
    assert sent_payload["attachments"] == [str(output_file)]
