# Google Closed Stores Project

Skrypt pobiera sklepy sieci handlowych z Google Places, filtruje tylko punkty ze statusem `CLOSED_TEMPORARILY` na terenie Niemiec, pyta Gemini o potencjalnego generalnego wykonawce, dodatkowo sanitizuje wybrane pola przez OpenAI i zapisuje wyniki do CSV oraz JSON.

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
   - `setx GOOGLE_API_KEY "twoj_google_maps_api_key"`
   - `setx GEMINI_API_KEY "twoj_gemini_api_key"`
   - `setx OPEN_AI_API "twoj_openai_api_key"`
   - `setx SMTP_SENDER_EMAIL "twoj_email@gmail.com"`
   - `setx SMTP_SENDER_APP_PASSWORD "twoje_haslo_aplikacji_google"`
   - opcjonalnie: `setx SMTP_HOST "smtp.gmail.com"`
   - opcjonalnie: `setx SMTP_PORT "587"`
4. Otworz nowy terminal po `setx`.

## Uruchomienie

Domyslnie skrypt wyszukuje okolice Berlina:

- `python main.py`

Przyklad z parametrami:

- `python main.py --lat 52.52 --lng 13.405 --radius 30000 --output wynik.csv --delay 1.0`

## Co robi pipeline

- Wyszukuje sklepy tylko w Niemczech (`query: "<siec> in Germany"` oraz `region=de`).
- Filtruje rekordy do `business_status = CLOSED_TEMPORARILY`.
- Pytaniem do Gemini uzupelnia dane o potencjalnym wykonawcy.
- Sanitizuje tekst przez OpenAI i dodatkowa lokalna walidacje.
- Tworzy dwa pliki wynikowe: CSV i JSON backup.
- Wysyla CSV mailem na `svinchak1993@gmail.com`.

## Limity API

Skrypt posiada twarde limity wywolan:

- Google Places API: maksymalnie `300` zapytan
- Gemini API: maksymalnie `300` zapytan

Po przekroczeniu limitu skrypt zatrzymuje sie z bledem.

## Wyniki

Tworzone sa pliki:

- CSV (domyslnie `closed_stores_with_contractors.csv`)
- JSON backup (np. `closed_stores_with_contractors.json`)

CSV zawiera m.in.:

- `place_id`
- `chain`
- `name`
- `address` (pelny adres z Google `formatted_address`)
- `business_status`
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
