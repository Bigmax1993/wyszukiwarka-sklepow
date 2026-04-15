import argparse
import csv
import json
import logging
import math
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
GOOGLE_MAX_REQUESTS = 300
GEMINI_MAX_REQUESTS = 300
MIN_CITY_OUTER_RADIUS_METERS = 100000
SEARCH_OFFSET_KM = 50.0
CHAIN_QUERY_VARIANTS = ("{chain}", "{chain} supermarket")
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
    effective_radius = max(radius, MIN_CITY_OUTER_RADIUS_METERS)
    params: Dict[str, Any] = {
        "query": f"{chain} in Germany",
        "location": f"{lat},{lng}",
        "radius": effective_radius,
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


def build_search_centers(lat: float, lng: float) -> List[tuple[float, float]]:
    # Cross-shaped search grid: city center + 50km in each cardinal direction.
    lat_delta = SEARCH_OFFSET_KM / 111.0
    lat_cos = max(0.2, abs(math.cos(math.radians(lat))))
    lng_delta = SEARCH_OFFSET_KM / (111.0 * lat_cos)
    return [
        (lat, lng),
        (lat + lat_delta, lng),
        (lat - lat_delta, lng),
        (lat, lng + lng_delta),
        (lat, lng - lng_delta),
    ]


def build_query_variants(chain: str) -> List[str]:
    return [template.format(chain=chain) for template in CHAIN_QUERY_VARIANTS]


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
    no_ai: bool = False,
) -> None:
    started_at = time.time()
    google_api_key = get_required_env("GOOGLE_API_KEY")
    gemini_api_key = get_required_env("GEMINI_API_KEY")
    openai_api_key = get_openai_api_key()

    results: Dict[str, Dict[str, Any]] = {}
    raw_google_results: List[Dict[str, Any]] = []
    centers = build_search_centers(lat, lng)

    for chain in STORE_CHAINS:
        logger.info("Pobieram sklepy: %s", chain)
        chain_stores: Dict[str, Dict[str, Any]] = {}

        for query_text in build_query_variants(chain):
            for center_lat, center_lng in centers:
                stores = get_stores(
                    query_text,
                    center_lat,
                    center_lng,
                    google_api_key=google_api_key,
                    radius=radius,
                )
                logger.info(
                    "Google zwrocilo %d rekordow dla %s (query='%s', center=%.4f,%.4f)",
                    len(stores),
                    chain,
                    query_text,
                    center_lat,
                    center_lng,
                )
                for store in stores:
                    raw_google_results.append(
                        {
                            "chain": chain,
                            "query": query_text,
                            "center_lat": center_lat,
                            "center_lng": center_lng,
                            "store": store,
                        }
                    )
                    place_id = store.get("place_id")
                    if not place_id:
                        continue
                    if place_id not in chain_stores:
                        chain_stores[place_id] = {
                            "store": store,
                            "source_query": query_text,
                            "source_center_lat": center_lat,
                            "source_center_lng": center_lng,
                        }

        logger.info(
            "Po deduplikacji place_id dla %s pozostalo %d rekordow",
            chain,
            len(chain_stores),
        )
        gemini_limit_reached = False

        for entry in chain_stores.values():
            store = entry["store"]
            place_id = store.get("place_id")
            if not place_id:
                continue

            full_address = store.get("formatted_address", "")
            if no_ai:
                contractor_info = {
                    "contractor_name": None,
                    "confidence": 0.0,
                    "sources": [],
                    "reasoning": "Pominieto przez parametr --no-ai",
                }
            elif gemini_limit_reached:
                contractor_info = {
                    "contractor_name": None,
                    "confidence": 0.0,
                    "sources": [],
                    "reasoning": "Pominieto po osiagnieciu limitu Gemini API",
                }
            else:
                try:
                    contractor_info = get_contractor_info(
                        full_address, gemini_api_key=gemini_api_key
                    )
                    time.sleep(delay_seconds)
                except ApiLimitExceeded:
                    gemini_limit_reached = True
                    logger.warning(
                        "Osiagnieto limit Gemini API - pozostale rekordy zapisywane bez contractor info"
                    )
                    contractor_info = {
                        "contractor_name": None,
                        "confidence": 0.0,
                        "sources": [],
                        "reasoning": "Pominieto po osiagnieciu limitu Gemini API",
                    }

            if no_ai:
                cleaned_name = store.get("name", "")
                cleaned_contractor_name = str(contractor_info.get("contractor_name", ""))
                cleaned_reasoning = contractor_info.get("reasoning", "")
            else:
                cleaned_name = remove_special_chars_with_openai(
                    store.get("name", ""), openai_api_key
                )
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
                "address": full_address,
                "status": store.get("business_status", "UNKNOWN"),
                "source_query": entry["source_query"],
                "source_center_lat": f"{entry['source_center_lat']:.6f}",
                "source_center_lng": f"{entry['source_center_lng']:.6f}",
                "contractor_name": cleaned_contractor_name,
                "confidence": contractor_info.get("confidence"),
                "sources": json.dumps(contractor_info.get("sources", []), ensure_ascii=False),
                "reasoning": cleaned_reasoning,
                "contractor_raw_json": json.dumps(contractor_info, ensure_ascii=False),
            }

    with open(output_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(
            [
                "place_id",
                "chain",
                "name",
                "address",
                "status",
                "source_query",
                "source_center_lat",
                "source_center_lng",
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
                    row["status"],
                    row["source_query"],
                    row["source_center_lat"],
                    row["source_center_lng"],
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

    raw_output_file = f"{os.path.splitext(output_file)[0]}_google_raw.json"
    with open(raw_output_file, "w", encoding="utf-8") as file:
        json.dump(raw_google_results, file, ensure_ascii=False, indent=2)

    metrics_output_file = f"{os.path.splitext(output_file)[0]}_metrics.json"
    metrics_payload = {
        "stores_saved": len(results),
        "google_requests_used": google_requests_count,
        "google_requests_limit": GOOGLE_MAX_REQUESTS,
        "gemini_requests_used": gemini_requests_count,
        "gemini_requests_limit": GEMINI_MAX_REQUESTS,
        "duration_seconds": round(time.time() - started_at, 2),
    }
    with open(metrics_output_file, "w", encoding="utf-8") as file:
        json.dump(metrics_payload, file, ensure_ascii=False, indent=2)

    logger.info("Zapisano plik CSV: %s", output_file)
    logger.info("Zapisano backup JSON: %s", json_output_file)
    logger.info("Zapisano surowe wyniki Google: %s", raw_output_file)
    logger.info("Zapisano metryki runa: %s", metrics_output_file)
    logger.info("Liczba zapisanych sklepow: %d", len(results))
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
    try:
        send_csv_report_via_email(output_file, len(results))
    except Exception as exc:
        logger.warning("Wysylka email nie powiodla sie: %s", exc)


def send_csv_report_via_email(csv_file_path: str, records_count: int) -> None:
    sender_email = (os.getenv("SMTP_SENDER_EMAIL") or "").strip()
    if not sender_email or "@" not in sender_email or sender_email.startswith("@"):
        sender_email = REPORT_RECIPIENT_EMAIL
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
            "Pobiera sklepy z Google Places i uzupelnia potencjalnego "
            "wykonawce przez Gemini."
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
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Pomin wywolania Gemini i OpenAI, zapisujac tylko dane z Google",
    )
    parser.epilog = (
        "Skrypt wymusza minimalny promien 100000 m, aby objac takze obszar "
        "do 100 km od duzego miasta."
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
        no_ai=args.no_ai,
    )
