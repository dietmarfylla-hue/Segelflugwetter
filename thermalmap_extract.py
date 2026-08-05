"""
Thermalmap Forecast Extraktor
=============================

Standort:
    Düsseldorf-Wolfsaap

Koordinaten:
    51.2645 N
    6.850662 E

Quelle:
    https://www.thermalmap.info/forecast/widget.php
"""

import re
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from bs4 import BeautifulSoup


# ================================================================
# KONFIGURATION
# ================================================================

LATITUDE = 51.2645
LONGITUDE = 6.850662

LOCATION_NAME = "Düsseldorf-Wolfsaap"
LOCATION_CODE = "Dues-W"
CLUB = "SFG"

DAYS = 5
INTERVAL = 1

TIMEZONE = ZoneInfo("Europe/Berlin")

# Relativer Ausgabeordner im Repo (statt Windows-Pfad)
BASE_DIR = Path("output")

URL = (
    "https://www.thermalmap.info/forecast/widget.php"
    f"?lat={LATITUDE}"
    f"&lon={LONGITUDE}"
    f"&interval={INTERVAL}"
    f"&days={DAYS}"
)


# ================================================================
# TEXT BEREINIGEN
# ================================================================

def clean_text(text):
    if text is None:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


# ================================================================
# THERMALMAP MIT SELENIUM LADEN
# ================================================================

def load_thermalmap():
    """
    Lädt das Thermalmap-Widget vollständig im Browser (headless).
    """

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)

    try:
        print()
        print("Thermalmap wird geladen ...")
        print(URL)

        driver.get(URL)

        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Zeit für JavaScript / Forecast-Inhalte
        time.sleep(5)

        return driver.page_source

    finally:
        driver.quit()


# ================================================================
# HTML ZUR KONTROLLE SPEICHERN
# ================================================================

def save_raw_html(html):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    output_file = BASE_DIR / "thermalmap_wolfsaap_raw.html"
    output_file.write_text(html, encoding="utf-8")
    return output_file


# ================================================================
# TABELLEN AUSLESEN
# ================================================================

def extract_tables(soup):
    result = []
    tables = soup.find_all("table")

    for table_number, table in enumerate(tables, start=1):
        rows = []

        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            values = [
                clean_text(cell.get_text(" ", strip=True))
                for cell in cells
            ]

            if values:
                rows.append(values)

        if rows:
            result.append({"number": table_number, "rows": rows})

    return result


# ================================================================
# SICHTBARE TEXTBLÖCKE AUSLESEN
# ================================================================

def extract_text_blocks(soup):
    blocks = []
    tags = soup.find_all(["h1", "h2", "h3", "h4", "p", "div", "span"])
    seen = set()

    for tag in tags:
        if tag.find_parent("table"):
            continue

        text = clean_text(tag.get_text(" ", strip=True))

        if not text or len(text) < 2 or text in seen:
            continue

        seen.add(text)
        blocks.append(text)

    return blocks


# ================================================================
# HEUTIGES DATUM
# ================================================================

def today_data():
    now = datetime.now(TIMEZONE)

    weekdays = [
        "Montag", "Dienstag", "Mittwoch", "Donnerstag",
        "Freitag", "Samstag", "Sonntag",
    ]

    return {
        "datetime": now,
        "date": now.strftime("%d.%m.%Y"),
        "date_filename": now.strftime("%Y%m%d"),
        "weekday": weekdays[now.weekday()],
    }


# ================================================================
# STÜNDLICHE TABELLEN FORMATIEREN
# ================================================================

def format_table(rows):
    if not rows:
        return []

    max_columns = max(len(row) for row in rows)
    normalized = [row + [""] * (max_columns - len(row)) for row in rows]

    widths = []
    for col in range(max_columns):
        width = max(len(str(row[col])) for row in normalized)
        widths.append(min(max(width, 4), 30))

    lines = []
    for row_index, row in enumerate(normalized):
        values = []
        for col_index, value in enumerate(row):
            value = str(value)
            if len(value) > widths[col_index]:
                value = value[:widths[col_index]]
            values.append(value.ljust(widths[col_index]))

        line = " | ".join(values)
        lines.append(line)

        if row_index == 0:
            lines.append("-" * len(line))

    return lines


# ================================================================
# THERMALMAP-DATEN STRUKTURIEREN
# ================================================================

def build_output_text(html):
    soup = BeautifulSoup(html, "html.parser")

    tables = extract_tables(soup)
    text_blocks = extract_text_blocks(soup)
    current = today_data()

    lines = []

    lines.append("=== THERMALMAP SEGELFLUG-DATEN ===")
    lines.append(f"Standort: {LOCATION_NAME}")
    lines.append(f"Code: {LOCATION_CODE}")
    lines.append(f"Verein: {CLUB}")
    lines.append(f"Koordinaten: {LATITUDE}, {LONGITUDE}")
    lines.append(f"Vorhersage für: {current['weekday']}, {current['date']}")
    lines.append("Quelle: Thermalmap.info")
    lines.append("")

    if text_blocks:
        lines.append("--- Allgemeine Angaben ---")
        lines.append("")

        unwanted = ["cookie", "privacy", "impressum", "contact", "copyright"]

        for text in text_blocks:
            if any(word in text.lower() for word in unwanted):
                continue
            lines.append(text)

        lines.append("")

    if tables:
        lines.append("--- Thermalmap Forecast ---")
        lines.append("")

        for table in tables:
            lines.append(f"Tabelle {table['number']}:")
            lines.append("")
            lines.extend(format_table(table["rows"]))
            lines.append("")
    else:
        lines.append("--- Thermalmap Forecast ---")
        lines.append("")
        lines.append("Keine HTML-Tabelle gefunden.")
        lines.append(
            "Die Daten könnten über JavaScript/Canvas "
            "oder eingebettete JSON-Daten dargestellt werden."
        )
        lines.append("")

    lines.append("=== ENDE THERMALMAP-DATEN ===")

    return "\n".join(lines)


# ================================================================
# TEXTDATEI SPEICHERN
# ================================================================

def save_output(text):
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    current = today_data()
    filename = f"thermalmap_wolfsaap_{current['date_filename']}.txt"
    output_file = BASE_DIR / filename

    output_file.write_text(text, encoding="utf-8")
    return output_file


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    print()
    print("============================================")
    print("THERMALMAP – WOLFS-AAP")
    print("============================================")
    print()

    html = load_thermalmap()
    print(f"HTML geladen: {len(html):,} Zeichen")

    raw_file = save_raw_html(html)

    output_text = build_output_text(html)
    output_file = save_output(output_text)

    print()
    print("============================================")
    print("THERMALMAP-DATEN GESPEICHERT")
    print("============================================")
    print()
    print(f"TXT-Datei:\n{output_file}")
    print()
    print(f"Roh-HTML:\n{raw_file}")
    print()
    print(f"Dateigröße: {output_file.stat().st_size:,} Bytes")
    print()
