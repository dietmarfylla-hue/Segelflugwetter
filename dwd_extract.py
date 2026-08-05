"""
DWD 3-Tages-Prognose Nord – Flugwetter / Segelflug Extraktor
=============================================================
"""

import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ================================================================
# KONFIGURATION
# ================================================================

URL = "https://www.dwd.de/DE/fachnutzer/luftfahrt/teaser/luftsportberichte/fbdl60_edzh_node.html"

# Relativer Ausgabeordner im Repo (statt Windows-Pfad)
BASE_DIR = Path("output")

LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


# ================================================================
# TEXT BEREINIGEN
# ================================================================

def clean_text(text):
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" +\n", "\n", text)
    text = re.sub(r"\n +", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ================================================================
# DWD-BERICHT IM HTML FINDEN
# ================================================================

def find_report_body(html_data):
    soup = BeautifulSoup(html_data, "html.parser")
    report = soup.find("div", class_="WordSection1")

    if report is None:
        raise ValueError(
            "\nDer eigentliche DWD-Flugwetterbericht wurde im HTML nicht gefunden.\n"
            "Gesucht wurde nach:\n"
            '<div class="WordSection1">'
        )
    return report


# ================================================================
# RELEVANTE ABSCHNITTE EXTRAHIEREN
# ================================================================

def extract_sections(html_data):
    report = find_report_body(html_data)

    blocks = []
    for element in report.find_all(["p", "pre"], recursive=True):
        text = element.get_text(separator="\n", strip=True)
        text = clean_text(text)
        if text:
            blocks.append(text)

    wanted_sections = {
        "WETTERLAGE DEUTSCHLAND": "Wetterlage Deutschland",
        "SICHTFLUGWETTER": "Sichtflugwetter",
        "SEGELFLUGWETTER": "Segelflugwetter",
        "NULLGRADGRENZE": "Nullgradgrenze",
    }

    all_sections = {
        "WETTERLAGE DEUTSCHLAND",
        "SICHTFLUGWETTER",
        "BALLONWETTER",
        "SEGELFLUGWETTER",
        "NULLGRADGRENZE",
    }

    result = {
        "kopf": [],
        "Wetterlage Deutschland": [],
        "Sichtflugwetter": [],
        "Segelflugwetter": [],
        "Nullgradgrenze": [],
    }

    current_section = "kopf"
    report_started = False

    for block in blocks:
        normalized = block.upper().strip().rstrip(":")

        if "3-TAGE-PROGNOSE FÜR SICHTFLUG UND LUFTSPORT" in normalized:
            report_started = True
            result["kopf"].append(block)
            continue

        if not report_started:
            continue

        found_heading = None
        for heading in all_sections:
            if normalized.startswith(heading):
                found_heading = heading
                break

        if found_heading:
            if found_heading in wanted_sections:
                current_section = wanted_sections[found_heading]
            else:
                current_section = None
            continue

        if normalized.startswith("BEMERKUNG"):
            break

        if current_section is not None:
            result[current_section].append(block)

    return result


# ================================================================
# VORHERSAGE-DATEN ERMITTELN
# ================================================================

def extract_forecast_dates(sections):
    kopf_text = "\n".join(sections.get("kopf", []))

    match = re.search(r"\bden\s+(\d{2}\.\d{2}\.\d{4})", kopf_text, flags=re.IGNORECASE)
    if not match:
        print("WARNUNG: Vorhersage-Startdatum konnte nicht erkannt werden.")
        return {}

    startdatum = datetime.strptime(match.group(1), "%d.%m.%Y")

    deutsche_wochentage = [
        "MONTAG", "DIENSTAG", "MITTWOCH", "DONNERSTAG",
        "FREITAG", "SAMSTAG", "SONNTAG",
    ]

    forecast_dates = {}
    for i in range(3):
        datum = startdatum + timedelta(days=i)
        weekday = deutsche_wochentage[datum.weekday()]
        forecast_dates[weekday] = datum.strftime("%d.%m.%Y")

    return forecast_dates


# ================================================================
# WOCHENTAGE MIT DATUM ERGÄNZEN
# ================================================================

def add_dates_to_weekdays(text, forecast_dates):
    for weekday, date_string in forecast_dates.items():
        pattern = rf"\b{weekday}\b(?!\s*,?\s*(?:den\s+)?\d{{2}}\.\d{{2}}\.\d{{4}})"
        replacement = f"{weekday}, {date_string}"
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ================================================================
# AUSGABETEXT ERZEUGEN
# ================================================================

def build_output_text(sections):
    output = ["=== DWD 3-TAGES-PROGNOSE NORD ===", "=== FLUGWETTER / SEGELFLUG ===", ""]

    section_titles = [
        ("kopf", "VORHERSAGE"),
        ("Wetterlage Deutschland", "WETTERLAGE DEUTSCHLAND"),
        ("Sichtflugwetter", "SICHTFLUGWETTER"),
        ("Segelflugwetter", "SEGELFLUGWETTER"),
        ("Nullgradgrenze", "NULLGRADGRENZE"),
    ]

    for key, title in section_titles:
        if sections[key]:
            output.append(f"--- {title} ---")
            output.append("")
            output.extend(sections[key])
            output.append("")

    output.append("=== ENDE DWD 3-TAGES-PROGNOSE NORD ===")

    text = clean_text("\n\n".join(output))

    forecast_dates = extract_forecast_dates(sections)
    text = add_dates_to_weekdays(text, forecast_dates)

    return text


# ================================================================
# HAUPTFUNKTION
# ================================================================

def extract_dwd_flight_weather(html_data):
    sections = extract_sections(html_data)
    return build_output_text(sections)


def fetch_html(url=URL):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def save_dwd_text(html_data, base_dir=BASE_DIR):
    base_dir.mkdir(parents=True, exist_ok=True)

    output_text = extract_dwd_flight_weather(html_data)

    now = datetime.now(LOCAL_TIMEZONE)
    date_string = now.strftime("%Y%m%d")
    filename = f"dwd_nord_3Tage_{date_string}.txt"
    output_file = base_dir / filename

    output_file.write_text(output_text, encoding="utf-8")

    print("====================================================")
    print("DWD 3-TAGES-PROGNOSE NORD ERFOLGREICH GESPEICHERT")
    print("====================================================")
    print(f"Dateiname:\n{filename}")
    print(f"Vollständiger Pfad:\n{output_file}")
    print(f"Dateigröße: {output_file.stat().st_size:,} Bytes")

    return output_file


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    html_data = fetch_html()
    save_dwd_text(html_data)
