import main


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_stores_handles_pagination_and_merges_all_results(monkeypatch):
    recorded_params = []
    sleep_calls = []

    responses = [
        DummyResponse(
            {
                "results": [{"place_id": "one"}, {"place_id": "two"}],
                "next_page_token": "token-123",
            }
        ),
        DummyResponse({"results": [{"place_id": "three"}]}),
    ]

    def fake_safe_request(method, url, params):
        recorded_params.append(params.copy())
        return responses.pop(0)

    monkeypatch.setattr(main, "safe_request", fake_safe_request)
    monkeypatch.setattr(main.time, "sleep", lambda value: sleep_calls.append(value))

    results = main.get_stores(
        chain="REWE",
        lat=52.52,
        lng=13.405,
        google_api_key="google-key",
        radius=5000,
    )

    assert [item["place_id"] for item in results] == ["one", "two", "three"]
    assert recorded_params[0] == {
        "query": "REWE in Germany",
        "location": "52.52,13.405",
        "radius": 50000,
        "region": "de",
        "key": "google-key",
    }
    assert recorded_params[1] == {"pagetoken": "token-123", "key": "google-key"}
    assert sleep_calls == [2]


def test_regression_keeps_all_statuses(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STORE_CHAINS", ["REWE"])
    monkeypatch.setattr(main, "get_required_env", lambda name: "ok")
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        main,
        "get_stores",
        lambda *args, **kwargs: [
            {
                "place_id": "temp-1",
                "name": "A",
                "formatted_address": "Hamburg, Germany",
                "business_status": "CLOSED_TEMPORARILY",
            },
            {
                "place_id": "perm-1",
                "name": "B",
                "formatted_address": "Hamburg, Germany",
                "business_status": "CLOSED_PERMANENTLY",
            },
            {
                "place_id": "oper-1",
                "name": "C",
                "formatted_address": "Hamburg, Germany",
                "business_status": "OPERATIONAL",
            },
        ],
    )
    monkeypatch.setattr(
        main,
        "get_contractor_info",
        lambda address, gemini_api_key: {
            "contractor_name": "Firma",
            "confidence": 1.0,
            "sources": [],
            "reasoning": "ok",
        },
    )

    output_file = tmp_path / "regression.csv"
    main.process_and_export(
        lat=52.52,
        lng=13.405,
        radius=30000,
        output_file=str(output_file),
        delay_seconds=0,
    )

    content = output_file.read_text(encoding="utf-8")
    assert "temp-1" in content
    assert "perm-1" in content
    assert "oper-1" in content
