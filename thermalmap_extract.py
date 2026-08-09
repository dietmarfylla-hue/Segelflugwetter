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
# DATUM / UHRZEIT AUS TABELLEN ERKENNEN
# ================================================================

DATE_PATTERNS = [
    re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(?!\d)"),
]

TIME_PATTERN = re.compile(r"(?<!\d)([01]?\d|2[0-3])(?::|\.)([0-5]\d)(?!\d)")
HOUR_PATTERN = re.compile(r"^\s*([01]?\d|2[0-3])\s*(?:h|Uhr)?\s*$", re.IGNORECASE)


def parse_date_from_text(text, reference_datetime):
    """Erkennt ein Datum in einem Text und liefert ein date-Objekt zurück."""
    text = clean_text(text)

    match = DATE_PATTERNS[0].search(text)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None

    match = DATE_PATTERNS[1].search(text)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None

    match = DATE_PATTERNS[2].search(text)
    if match:
        day, month = map(int, match.groups())
        year = reference_datetime.year

        try:
            candidate = datetime(year, month, day).date()
        except ValueError:
            return None

        # Forecasts über den Jahreswechsel korrekt zuordnen.
        delta_days = (candidate - reference_datetime.date()).days
        if delta_days < -180:
            candidate = datetime(year + 1, month, day).date()
        elif delta_days > 180:
            candidate = datetime(year - 1, month, day).date()

        return candidate

    return None


def parse_time_from_text(text):
    """Erkennt HH:MM, HH.MM oder eine reine Stundenangabe."""
    text = clean_text(text)

    match = TIME_PATTERN.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))

    match = HOUR_PATTERN.match(text)
    if match:
        return int(match.group(1)), 0

    return None


def find_date_in_row(row, reference_datetime):
    for value in row:
        parsed = parse_date_from_text(value, reference_datetime)
        if parsed is not None:
            return parsed
    return None


def find_time_in_row(row):
    for value in row:
        parsed = parse_time_from_text(value)
        if parsed is not None:
            return parsed
    return None


# ================================================================
# TABELLEN-SCHEMA UND FORECAST-DATENSÄTZE
# ================================================================

def safe_field_name(value, index):
    """Erzeugt einen stabilen, gut lesbaren Feldnamen für eine Tabellenspalte."""
    value = clean_text(value).lower()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    value = value.replace("ß", "ss")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")

    if not value:
        return f"spalte_{index:02d}"

    return value[:50]


def looks_like_header(row, reference_datetime):
    """Heuristik: Kopfzeilen enthalten normalerweise keine konkrete Uhrzeit."""
    if not row:
        return False

    if find_time_in_row(row) is not None:
        return False

    text_cells = 0
    for value in row:
        value = clean_text(value)
        if not value:
            continue
        if parse_date_from_text(value, reference_datetime) is not None:
            continue
        if re.search(r"[A-Za-zÄÖÜäöüß]", value):
            text_cells += 1

    return text_cells >= max(1, len(row) // 2)


def infer_table_headers(rows, reference_datetime):
    """
    Liefert stabile Feldnamen für eine Tabelle.

    Wenn die erste sinnvolle Zeile wie eine Kopfzeile aussieht, werden deren
    Bezeichnungen genutzt. Andernfalls werden neutrale Spaltennamen verwendet.
    """
    max_columns = max((len(row) for row in rows), default=0)
    header_row = None

    for row in rows[:5]:
        if looks_like_header(row, reference_datetime):
            header_row = row
            break

    names = []
    used = set()

    for index in range(max_columns):
        if header_row is not None and index < len(header_row):
            base = safe_field_name(header_row[index], index + 1)
        else:
            base = f"spalte_{index + 1:02d}"

        name = base
        suffix = 2
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1

        used.add(name)
        names.append(name)

    return names, header_row


def extract_forecast_records(tables, reference_datetime):
    """
    Wandelt die HTML-Tabellen verlustfrei in sortierbare Datensätze um.

    Jeder Datensatz enthält einen eindeutigen Zeitstempel, die Quelltabelle,
    benannte Felder und zusätzlich die vollständige Originalzeile. Dadurch
    bleibt die Ausgabe auch dann analysierbar, wenn Thermalmap Tabellen oder
    Spalten zukünftig leicht verändert.
    """
    records = []
    table_schemas = {}

    for table in tables:
        headers, header_row = infer_table_headers(table["rows"], reference_datetime)
        table_schemas[table["number"]] = headers
        current_date = None

        for row_number, row in enumerate(table["rows"], start=1):
            if header_row is not None and row is header_row:
                continue

            row_date = find_date_in_row(row, reference_datetime)
            if row_date is not None:
                current_date = row_date

            row_time = find_time_in_row(row)

            # Nur Zeilen mit Datumskontext und Uhrzeit sind Stunden-Datensätze.
            if current_date is None or row_time is None:
                continue

            hour, minute = row_time
            timestamp = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                hour,
                minute,
                tzinfo=TIMEZONE,
            )

            normalized = list(row) + [""] * (len(headers) - len(row))
            fields = {
                headers[index]: clean_text(value)
                for index, value in enumerate(normalized[:len(headers)])
            }

            records.append({
                "timestamp": timestamp,
                "date": current_date,
                "table_number": table["number"],
                "row_number": row_number,
                "fields": fields,
                "values": [clean_text(value) for value in row],
            })

    records.sort(
        key=lambda record: (
            record["timestamp"],
            record["table_number"],
            record["row_number"],
        )
    )
    return records, table_schemas


def group_records_by_day(records):
    grouped = {}
    for record in records:
        grouped.setdefault(record["date"], []).append(record)
    return grouped


def escape_value(value):
    """Macht Werte einzeilig und eindeutig lesbar."""
    value = clean_text(value)
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\n", "\\n")
    return value


def format_fields(record):
    """Formatiert alle Spalten stabil als key=\"value\"."""
    parts = []
    for key, value in record["fields"].items():
        parts.append(f'{key}="{escape_value(value)}"')
    return " | ".join(parts)


# ================================================================
# THERMALMAP-DATEN STRUKTURIEREN
# ================================================================

def build_output_text(html):
    soup = BeautifulSoup(html, "html.parser")

    tables = extract_tables(soup)
    current = today_data()
    execution_time = current["datetime"]

    records, table_schemas = extract_forecast_records(tables, execution_time)
    grouped_records = group_records_by_day(records)

    if records:
        window_start = records[0]["timestamp"]
        window_end = records[-1]["timestamp"]
        window_text = (
            f"{window_start.isoformat()} bis {window_end.isoformat()}"
        )
    else:
        window_text = "nicht_ermittelbar"

    lines = []

    # ------------------------------------------------------------
    # KOPFBEREICH: kompakt, stabil und maschinenlesbar
    # ------------------------------------------------------------
    lines.append("# THERMALMAP_FORECAST_V2")
    lines.append("# FORMAT: key=value; Tagesblöcke; Datensätze chronologisch")
    lines.append(f'# quelle="{escape_value(URL)}"')
    lines.append(f'# standort="{escape_value(LOCATION_NAME)}"')
    lines.append(f'# standort_code="{escape_value(LOCATION_CODE)}"')
    lines.append(f'# verein="{escape_value(CLUB)}"')
    lines.append(f"# latitude={LATITUDE}")
    lines.append(f"# longitude={LONGITUDE}")
    lines.append(f"# timezone={TIMEZONE.key}")
    lines.append(f"# ausfuehrung={execution_time.isoformat()}")
    lines.append(f'# datenzeitfenster="{window_text}"')
    lines.append(f"# forecast_tage={DAYS}")
    lines.append(f"# forecast_intervall_stunden={INTERVAL}")
    lines.append(f"# anzahl_tabellen={len(tables)}")
    lines.append(f"# anzahl_datensaetze={len(records)}")
    lines.append("")

    # ------------------------------------------------------------
    # SCHEMA: dokumentiert, wie die Tabellen interpretiert wurden
    # ------------------------------------------------------------
    lines.append("[SCHEMA]")
    lines.append("record_felder=timestamp | table | row | <quellspalten als key=value>")
    for table_number in sorted(table_schemas):
        fields = ", ".join(table_schemas[table_number])
        lines.append(f"table_{table_number}_felder={fields}")
    lines.append("")

    # ------------------------------------------------------------
    # DATENBEREICH
    # ------------------------------------------------------------
    if grouped_records:
        weekdays = [
            "Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag",
        ]

        for day in sorted(grouped_records):
            day_records = sorted(
                grouped_records[day],
                key=lambda record: (
                    record["timestamp"],
                    record["table_number"],
                    record["row_number"],
                ),
            )

            lines.append(
                f"[TAG {day.isoformat()} {weekdays[day.weekday()]}]"
            )

            for record in day_records:
                # ISO-8601 ist für automatische Analyse eindeutiger als nur HH:MM.
                timestamp = record["timestamp"].isoformat()
                lines.append(
                    f"timestamp={timestamp}"
                    f" | table={record['table_number']}"
                    f" | row={record['row_number']}"
                    f" | {format_fields(record)}"
                )

            lines.append("")
    else:
        lines.append("[KEINE_STRUKTURIERTEN_DATEN]")
        lines.append(
            "grund=Keine Tabellenzeilen mit eindeutig erkennbarem Datum und Uhrzeit gefunden."
        )
        lines.append("")
        lines.append("[ROHDATEN]" )

        # Verlustfreier Fallback, damit die Quelle trotzdem analysiert werden kann.
        for table in tables:
            for row_number, row in enumerate(table["rows"], start=1):
                values = " | ".join(
                    f'c{index:02d}="{escape_value(value)}"'
                    for index, value in enumerate(row, start=1)
                )
                lines.append(
                    f"table={table['number']} | row={row_number} | {values}"
                )

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
