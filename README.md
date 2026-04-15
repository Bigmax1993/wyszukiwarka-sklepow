# Google Closed Stores Project

Skrypt pobiera sklepy sieci handlowych z Google Places, filtruje tylko punkty ze statusem `CLOSED_TEMPORARILY`, a nastepnie pyta Gemini o potencjalnego generalnego wykonawce i zapisuje wynik do CSV.

## Wymagania

- Python 3.10+
- Klucz Google Maps API z dostepem do Places API
- Klucz Gemini API

## Instalacja

1. Przejdz do katalogu projektu:
   - `cd google-closed-stores-project`
2. Zainstaluj zaleznosci:
   - `pip install -r requirements.txt`
3. Ustaw zmienne srodowiskowe (PowerShell):
   - `setx GOOGLE_API_KEY "twoj_google_maps_api_key"`
   - `setx GEMINI_API_KEY "twoj_gemini_api_key"`
4. Otworz nowy terminal po `setx`.

## Uruchomienie

Domyslnie skrypt wyszukuje okolice Berlina:

- `python main.py`

Przyklad z parametrami:

- `python main.py --lat 52.52 --lng 13.405 --radius 30000 --output wynik.csv --delay 1.0`

## Wynik

Tworzony jest plik CSV (domyslnie `closed_stores_with_contractors.csv`) zawierajacy m.in.:

- `place_id`
- `chain`
- `name`
- `address`
- `business_status`
- `contractor_name`
- `confidence`
- `sources`
- `reasoning`
- `contractor_raw_json`
