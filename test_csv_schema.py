import csv

import main


EXPECTED_HEADERS = [
    "place_id",
    "chain",
    "name",
    "address",
    "business_status",
    "contractor_name",
    "confidence",
    "sources",
    "reasoning",
    "contractor_raw_json",
]


def test_csv_headers_are_stable(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STORE_CHAINS", ["REWE"])
    monkeypatch.setattr(main, "get_required_env", lambda name: "ok")
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        main,
        "get_stores",
        lambda *args, **kwargs: [
            {
                "place_id": "h1",
                "name": "Header Test Store",
                "formatted_address": "Cologne, Germany",
                "business_status": "CLOSED_TEMPORARILY",
            }
        ],
    )
    monkeypatch.setattr(
        main,
        "get_contractor_info",
        lambda *args, **kwargs: {
            "contractor_name": "Firma H",
            "confidence": 0.8,
            "sources": ["https://example.org/h"],
            "reasoning": "ok",
        },
    )

    output_file = tmp_path / "schema.csv"
    main.process_and_export(52.52, 13.405, 30000, str(output_file), 0)

    with output_file.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        first_row = next(reader)

    assert first_row == EXPECTED_HEADERS
