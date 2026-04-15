import argparse
import csv
import json
import logging
import os
import re
import time
from typing import Any, Dict, List

import requests
import yagmail


PLACES_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-pro:generateContent"
)
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

STORE_CHAINS = ["REWE", "NETTO", "ALDI", "EDEKA", "PENNY","KAUFLAND"]
TARGET_STATUS = "CLOSED_TEMPORARILY"
GOOGLE_MAX_REQUESTS = 300
GEMINI_MAX_REQUESTS = 300
GERMANY_ADDRESS_MARKERS = ("germany", "deutschland", ", de")
REPORT_RECIPIENT_EMAIL = "svinchak1993@gmail.com"

logger = logging.getLogger(__name__)


class ApiLimitExceeded(RuntimeError):
    pass


google_requests_count = 0
gemini_requests_count = 0


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Brak zmiennej srodowiskowej: {name}")
    return value


def get_openai_api_key() -> str:
    # Prefer OPEN_AI_API to match repository secrets naming.
    value = os.getenv("OPEN_AI_API")
    if value:
        return value
    return get_required_env("OPENAI_API_KEY")


def reserve_api_call(url: str) -> None:
    global google_requests_count, gemini_requests_count

    if "maps.googleapis.com" in url:
        if google_requests_count >= GOOGLE_MAX_REQUESTS:
            raise ApiLimitExceeded(
                f"Przekroczono limit Google API: {GOOGLE_MAX_REQUESTS} zapytan"
            )
        google_requests_count += 1
        return

    if "generativelanguage.googleapis.com" in url:
        if gemini_requests_count >= GEMINI_MAX_REQUESTS:
            raise ApiLimitExceeded(
                f"Przekroczono limit Gemini API: {GEMINI_MAX_REQUESTS} zapytan"
            )
        gemini_requests_count += 1


def safe_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    for attempt in range(3):
        try:
            reserve_api_call(url)
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
        "query": f"{chain} in Germany",
        "location": f"{lat},{lng}",
        "radius": radius,
        "region": "de",
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


def is_store_in_germany(store: Dict[str, Any]) -> bool:
    formatted_address = (store.get("formatted_address") or "").strip().lower()
    return any(marker in formatted_address for marker in GERMANY_ADDRESS_MARKERS)


def enforce_allowed_characters(text: str) -> str:
    # Final safety layer after OpenAI response with minimal restrictions:
    # remove only control characters and normalize whitespace.
    cleaned = re.sub(r"[\x00-\x1F\x7F]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def remove_special_chars_with_openai(text: str, openai_api_key: str) -> str:
    if not text:
        return ""

    prompt = (
        "Jestes funkcja czyszczaca dane do CSV.\n\n"
        "Zadanie:\n"
        "- Usun znaki specjalne.\n"
        "- Zachowaj sens tekstu.\n"
        "- Nie tlumacz, nie skracaj.\n\n"
        "Dozwolone znaki:\n"
        "- litery (A-Z, a-z, polskie znaki)\n"
        "- cyfry (0-9)\n"
        "- spacja\n"
        "- przecinek (,)\n"
        "- kropka (.)\n"
        "- myslnik (-)\n\n"
        "Reguly:\n"
        "1) Usun wszystkie inne znaki (np. @ # $ % ^ & * ( ) [ ] { } / \\ | : ; \" ' ? ! < > _ = + ~ `).\n"
        "2) Zastap wiele spacji jedna spacja.\n"
        "3) Przytnij spacje z poczatku i konca.\n"
        "4) Nie zmieniaj kolejnosci slow.\n"
        "5) Jesli po czyszczeniu nic nie zostanie, zwroc pusty string.\n\n"
        "Zwroc TYLKO wynik czyszczenia, bez komentarzy, bez JSON, bez cudzyslowow."
    )
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
    }

    try:
        response = requests.post(
            OPENAI_URL,
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        cleaned = response.json()["choices"][0]["message"]["content"].strip()
        return enforce_allowed_characters(cleaned)
    except Exception:
        # Fallback when OpenAI call fails: local sanitization to keep pipeline output valid.
        return enforce_allowed_characters(text)


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
    except ApiLimitExceeded:
        raise
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
    openai_api_key = get_openai_api_key()

    results: Dict[str, Dict[str, Any]] = {}

    for chain in STORE_CHAINS:
        logger.info("Pobieram sklepy: %s", chain)
        stores = get_stores(chain, lat, lng, google_api_key=google_api_key, radius=radius)
        stores = [store for store in stores if is_store_in_germany(store)]

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

            cleaned_name = remove_special_chars_with_openai(
                store.get("name", ""), openai_api_key
            )
            cleaned_address = remove_special_chars_with_openai(address, openai_api_key)
            cleaned_contractor_name = remove_special_chars_with_openai(
                str(contractor_info.get("contractor_name", "")),
                openai_api_key,
            )
            cleaned_reasoning = remove_special_chars_with_openai(
                contractor_info.get("reasoning", ""),
                openai_api_key,
            )

            results[place_id] = {
                "chain": chain,
                "name": cleaned_name,
                "address": cleaned_address,
                "business_status": business_status,
                "contractor_name": cleaned_contractor_name,
                "confidence": contractor_info.get("confidence"),
                "sources": json.dumps(contractor_info.get("sources", []), ensure_ascii=False),
                "reasoning": cleaned_reasoning,
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

    json_output_file = f"{os.path.splitext(output_file)[0]}.json"
    with open(json_output_file, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)

    logger.info("Zapisano plik CSV: %s", output_file)
    logger.info("Zapisano backup JSON: %s", json_output_file)
    logger.info("Liczba sklepow o statusie %s: %d", TARGET_STATUS, len(results))
    logger.info(
        "Wykorzystanie Google API: %d/%d",
        google_requests_count,
        GOOGLE_MAX_REQUESTS,
    )
    logger.info(
        "Wykorzystanie Gemini API: %d/%d",
        gemini_requests_count,
        GEMINI_MAX_REQUESTS,
    )
    send_csv_report_via_email(output_file, len(results))


def send_csv_report_via_email(csv_file_path: str, records_count: int) -> None:
    sender_email = get_required_env("SMTP_SENDER_EMAIL")
    sender_app_password = get_required_env("SMTP_SENDER_APP_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    run_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    subject = f"Raport pipeline - {run_timestamp}"
    body = (
        "Pipeline zakonczyl dzialanie.\n"
        f"Liczba rekordow: {records_count}\n"
        "CSV znajduje sie w zalaczniku."
    )

    with yagmail.SMTP(
        user=sender_email,
        password=sender_app_password,
        host=smtp_host,
        port=smtp_port,
    ) as yag:
        yag.send(
            to=REPORT_RECIPIENT_EMAIL,
            subject=subject,
            contents=body,
            attachments=[csv_file_path],
        )

    logger.info("Wyslano raport CSV na adres: %s", REPORT_RECIPIENT_EMAIL)


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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    process_and_export(
        lat=args.lat,
        lng=args.lng,
        radius=args.radius,
        output_file=args.output,
        delay_seconds=args.delay,
    )
