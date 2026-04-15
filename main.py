import argparse
import csv
import json
import os
import time
from typing import Any, Dict, List

import requests


PLACES_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-pro:generateContent"
)

STORE_CHAINS = ["REWE", "NETTO", "ALDI", "EDEKA", "PENNY","KAUFLAND"]
TARGET_STATUS = "CLOSED_TEMPORARILY"


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Brak zmiennej srodowiskowej: {name}")
    return value


def safe_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    for attempt in range(3):
        try:
            response = requests.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Nieoczekiwany blad requestu")


def get_stores(
    chain: str, lat: float, lng: float, google_api_key: str, radius: int = 30000
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "query": chain,
        "location": f"DE",
        "radius": radius,
        "key": google_api_key,
    }

    all_results: List[Dict[str, Any]] = []

    while True:
        response = safe_request("GET", PLACES_TEXTSEARCH_URL, params=params)
        data = response.json()
        all_results.extend(data.get("results", []))

        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break

        # Token paginacji Places API potrzebuje chwili zanim bedzie aktywny.
        time.sleep(2)
        params = {"pagetoken": next_page_token, "key": google_api_key}

    return all_results


def get_contractor_info(address: str, gemini_api_key: str) -> Dict[str, Any]:
    prompt = f"""
Podaj nazwe generalnego wykonawcy odpowiedzialnego za budowe lub remont sklepu
pod adresem: {address}.
Jesli brak jednoznacznych danych, podaj najbardziej prawdopodobne firmy wraz z uzasadnieniem.
Zwroc WYLACZNIE poprawny JSON:
{{
  "contractor_name": "string",
  "confidence": 0.0,
  "sources": ["url1", "url2"],
  "reasoning": "krotkie uzasadnienie"
}}
"""

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"},
    }

    try:
        response = safe_request(
            "POST",
            GEMINI_URL,
            headers={"Content-Type": "application/json"},
            params={"key": gemini_api_key},
            json=body,
        )
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception:
        return {
            "contractor_name": None,
            "confidence": 0.0,
            "sources": [],
            "reasoning": "Brak parsowalnej odpowiedzi Gemini",
        }


def process_and_export(
    lat: float,
    lng: float,
    radius: int,
    output_file: str,
    delay_seconds: float,
) -> None:
    google_api_key = get_required_env("GOOGLE_API_KEY")
    gemini_api_key = get_required_env("GEMINI_API_KEY")

    results: Dict[str, Dict[str, Any]] = {}

    for chain in STORE_CHAINS:
        print(f"Pobieram sklepy: {chain}")
        stores = get_stores(chain, lat, lng, google_api_key=google_api_key, radius=radius)

        for store in stores:
            business_status = store.get("business_status", "")
            if business_status != TARGET_STATUS:
                continue

            place_id = store.get("place_id")
            if not place_id:
                continue

            address = store.get("formatted_address", "")
            contractor_info = get_contractor_info(address, gemini_api_key=gemini_api_key)
            time.sleep(delay_seconds)

            results[place_id] = {
                "chain": chain,
                "name": store.get("name", ""),
                "address": address,
                "business_status": business_status,
                "contractor_name": contractor_info.get("contractor_name"),
                "confidence": contractor_info.get("confidence"),
                "sources": json.dumps(contractor_info.get("sources", []), ensure_ascii=False),
                "reasoning": contractor_info.get("reasoning", ""),
                "contractor_raw_json": json.dumps(contractor_info, ensure_ascii=False),
            }

    with open(output_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
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
        )

        for place_id, row in results.items():
            writer.writerow(
                [
                    place_id,
                    row["chain"],
                    row["name"],
                    row["address"],
                    row["business_status"],
                    row["contractor_name"],
                    row["confidence"],
                    row["sources"],
                    row["reasoning"],
                    row["contractor_raw_json"],
                ]
            )

    print(f"Zapisano plik: {output_file}")
    print(f"Liczba sklepow o statusie {TARGET_STATUS}: {len(results)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pobiera sklepy z Google Places, filtruje tylko CLOSED_TEMPORARILY i "
            "uzupelnia potencjalnego wykonawce przez Gemini."
        )
    )
    parser.add_argument("--lat", type=float, default=52.5200, help="Szerokosc geograficzna")
    parser.add_argument("--lng", type=float, default=13.4050, help="Dlugosc geograficzna")
    parser.add_argument("--radius", type=int, default=30000, help="Promien wyszukiwania w metrach")
    parser.add_argument(
        "--output",
        type=str,
        default="closed_stores_with_contractors.csv",
        help="Nazwa pliku wynikowego CSV",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Opoznienie miedzy zapytaniami Gemini w sekundach",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    process_and_export(
        lat=args.lat,
        lng=args.lng,
        radius=args.radius,
        output_file=args.output,
        delay_seconds=args.delay,
    )
