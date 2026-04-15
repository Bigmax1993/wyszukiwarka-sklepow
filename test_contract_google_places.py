import main


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_stores_handles_missing_results_field(monkeypatch):
    monkeypatch.setattr(main, "safe_request", lambda *args, **kwargs: DummyResponse({}))
    stores = main.get_stores("REWE", 52.52, 13.405, "key")
    assert stores == []


def test_process_and_export_skips_rows_without_place_id(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STORE_CHAINS", ["REWE"])
    monkeypatch.setattr(main, "get_required_env", lambda name: "ok")
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        main,
        "get_stores",
        lambda *args, **kwargs: [
            {
                "name": "No Id Store",
                "formatted_address": "Munich, Germany",
                "business_status": "CLOSED_TEMPORARILY",
            }
        ],
    )
    monkeypatch.setattr(
        main,
        "get_contractor_info",
        lambda *args, **kwargs: {
            "contractor_name": "X",
            "confidence": 0.9,
            "sources": [],
            "reasoning": "ok",
        },
    )

    output_file = tmp_path / "google_contract.csv"
    main.process_and_export(52.52, 13.405, 30000, str(output_file), 0)

    content = output_file.read_text(encoding="utf-8")
    # only header should be present
    assert "No Id Store" not in content


def test_process_and_export_sets_unknown_when_status_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STORE_CHAINS", ["REWE"])
    monkeypatch.setattr(main, "get_required_env", lambda name: "ok")
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        main,
        "get_stores",
        lambda *args, **kwargs: [
            {
                "place_id": "x1",
                "name": "No Status Store",
                "formatted_address": "Munich, Germany",
            }
        ],
    )
    monkeypatch.setattr(
        main,
        "get_contractor_info",
        lambda *args, **kwargs: {
            "contractor_name": "X",
            "confidence": 0.9,
            "sources": [],
            "reasoning": "ok",
        },
    )

    output_file = tmp_path / "google_contract_status.csv"
    main.process_and_export(52.52, 13.405, 30000, str(output_file), 0)
    content = output_file.read_text(encoding="utf-8")
    assert "x1" in content
    assert "UNKNOWN" in content
