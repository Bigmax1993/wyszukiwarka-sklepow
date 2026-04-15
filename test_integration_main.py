import csv
import json

import main


def test_process_and_export_writes_only_temporarily_closed_rows(monkeypatch, tmp_path):
    stores_by_chain = {
        "REWE": [
            {
                "place_id": "p1",
                "name": "REWE A",
                "formatted_address": "Adres 1",
                "business_status": "CLOSED_TEMPORARILY",
            },
            {
                "place_id": "p2",
                "name": "REWE B",
                "formatted_address": "Adres 2",
                "business_status": "OPERATIONAL",
            },
        ],
        "NETTO": [],
        "ALDI": [],
        "EDEKA": [],
        "PENNY": [],
    }

    def fake_get_required_env(name):
        return f"{name.lower()}-value"

    def fake_get_stores(chain, lat, lng, google_api_key, radius):
        return stores_by_chain.get(chain, [])

    def fake_get_contractor_info(address, gemini_api_key):
        return {
            "contractor_name": "Firma X",
            "confidence": 0.85,
            "sources": ["https://example.org/src"],
            "reasoning": f"Dla adresu {address}",
        }

    monkeypatch.setattr(main, "get_required_env", fake_get_required_env)
    monkeypatch.setattr(main, "get_stores", fake_get_stores)
    monkeypatch.setattr(main, "get_contractor_info", fake_get_contractor_info)
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    output_file = tmp_path / "result.csv"
    main.process_and_export(
        lat=52.52,
        lng=13.405,
        radius=30000,
        output_file=str(output_file),
        delay_seconds=0,
    )

    with output_file.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    row = rows[0]
    assert row["place_id"] == "p1"
    assert row["business_status"] == "CLOSED_TEMPORARILY"
    assert row["contractor_name"] == "Firma X"
    assert json.loads(row["sources"]) == ["https://example.org/src"]
