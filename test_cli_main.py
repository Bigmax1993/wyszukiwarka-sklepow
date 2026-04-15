import sys

import pytest

import main


def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    args = main.parse_args()

    assert args.lat == 52.5200
    assert args.lng == 13.4050
    assert args.radius == 30000
    assert args.output == "closed_stores_with_contractors.csv"
    assert args.delay == 1.0


def test_parse_args_custom_values(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--lat",
            "50.0",
            "--lng",
            "20.1",
            "--radius",
            "15000",
            "--output",
            "my.csv",
            "--delay",
            "0.25",
        ],
    )
    args = main.parse_args()

    assert args.lat == 50.0
    assert args.lng == 20.1
    assert args.radius == 15000
    assert args.output == "my.csv"
    assert args.delay == 0.25


def test_parse_args_invalid_radius_type(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--radius", "not_int"])
    with pytest.raises(SystemExit):
        main.parse_args()
