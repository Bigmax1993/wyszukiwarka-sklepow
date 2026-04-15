import csv

import main


def test_duplicate_place_id_keeps_single_row(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STORE_CHAINS", ["REWE", "NETTO"])
    monkeypatch.setattr(main, "get_required_env", lambda name: "ok")
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    def fake_get_stores(chain, *args, **kwargs):
        if chain == "REWE":
            return [
                {
                    "place_id": "dup-1",
                    "name": "Store REWE",
                    "formatted_address": "Adres 1",
                    "business_status": "CLOSED_TEMPORARILY",
                }
            ]
        return [
            {
                "place_id": "dup-1",
                "name": "Store NETTO",
                "formatted_address": "Adres 1",
                "business_status": "CLOSED_TEMPORARILY",
            }
        ]

    monkeypatch.setattr(main, "get_stores", fake_get_stores)
    monkeypatch.setattr(
        main,
        "get_contractor_info",
        lambda *args, **kwargs: {
            "contractor_name": "Firma D",
            "confidence": 0.7,
            "sources": [],
            "reasoning": "ok",
        },
    )

    output_file = tmp_path / "dedupe.csv"
    main.process_and_export(52.52, 13.405, 30000, str(output_file), 0)

    with output_file.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["place_id"] == "dup-1"
    # Last write wins because results dict is keyed by place_id.
    assert rows[0]["chain"] == "NETTO"
