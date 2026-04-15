# Google Closed Stores Project

Skrypt pobiera sklepy sieci handlowych z Google Places na terenie Niemiec, wzbogaca dane przez Gemini/OpenAI (lub pomija AI w trybie `--no-ai`) i zapisuje wyniki do CSV/JSON wraz z metrykami i surowym exportem Google.

## Wymagania

- Python 3.10+
- Klucz Google Maps API z dostepem do Places API
- Klucz Gemini API
- Klucz OpenAI API
- Konto Gmail nadawcy i haslo aplikacji Google (do wysylki raportu CSV)

## Instalacja

1. Przejdz do katalogu projektu:
   - `cd wyszukiwarka-sklepow`
2. Zainstaluj zaleznosci:
   - `pip install -r requirements.txt`
3. Ustaw zmienne srodowiskowe (PowerShell):
   - `setx OOGLE_MAPS_API_KEY "twoj_google_maps_api_key"` (nazwa zgodna z obecnym workflow)
   - `setx GEMINI_API_KEY "twoj_gemini_api_key"`
   - `setx OPEN_AI_API "twoj_openai_api_key"`
   - `setx SMTP_SENDER_EMAIL "twoj_email@gmail.com"`
   - `setx SMTP_SENDER_APP_PASSWORD "twoje_haslo_aplikacji_google"`
   - opcjonalnie: `setx SMTP_HOST "smtp.gmail.com"`
   - opcjonalnie: `setx SMTP_PORT "465"`
4. Otworz nowy terminal po `setx`.

## Uruchomienie

Domyslnie skrypt wyszukuje okolice Berlina:

- `python main.py`

Przyklad z parametrami:

- `python main.py --lat 52.52 --lng 13.405 --radius 30000 --output wynik.csv --delay 1.0`
- tryb bez AI (maksymalna liczba rekordow z Google): `python main.py --no-ai`

## Co robi pipeline

- Wyszukuje sklepy tylko w Niemczech (`query: "<siec> in Germany"` oraz `region=de`).
- Uzywa wielopunktowego pokrycia (centrum miasta + offsety), oraz wariantow zapytan dla kazdej sieci.
- Deduplikuje sklepy po `place_id`, aby uniknac duplikatow z wielu punktow.
- Utrzymuje kolumne `status` dla kazdego sklepu (wartosc z Google, fallback `UNKNOWN`).
- W trybie domyslnym wzbogaca dane przez Gemini i sanitizuje wybrane pola przez OpenAI.
- W trybie `--no-ai` pomija Gemini/OpenAI i zapisuje tylko dane Google.
- Tworzy pliki: CSV, JSON backup, surowe wyniki Google oraz metryki runa.
- Probbuje wyslac CSV mailem; blad wysylki jest logowany jako warning i nie przerywa runa.

## Limity API

Skrypt posiada twarde limity wywolan:

- Google Places API: maksymalnie `300` zapytan
- Gemini API: maksymalnie `300` zapytan

Po osiagnieciu limitu Gemini pozostale rekordy sa zapisywane bez contractor info.

## Wyniki

Tworzone sa pliki:

- CSV (domyslnie `closed_stores_with_contractors.csv`, separator `;` pod Excel PL)
- JSON backup (np. `closed_stores_with_contractors.json`)
- Surowe wyniki Google (np. `closed_stores_with_contractors_google_raw.json`)
- Metryki runa (np. `closed_stores_with_contractors_metrics.json`)

CSV zawiera m.in.:

- `place_id`
- `chain`
- `name`
- `address` (pelny adres z Google `formatted_address`)
- `status`
- `source_query`
- `source_center_lat`
- `source_center_lng`
- `contractor_name`
- `confidence`
- `sources`
- `reasoning`
- `contractor_raw_json`

## Testy

Aby uruchomic wszystkie testy:

- `Set-Location "C:\Users\svinc\wyszukiwarka-sklepow"`
- `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"`
- `python -m pytest -q`
