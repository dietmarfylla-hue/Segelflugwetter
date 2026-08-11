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
DAYS = 3
INTERVAL = 1
TIMEZONE = ZoneInfo("Europe/Berlin")

BASE_DIR = Path("output")

URL = (
    "https://www.thermalmap.info/forecast/widget.php"
    f"?lat={LATITUDE}"
    f"&lon={LONGITUDE}"
    f"&interval={INTERVAL}"
    f"&days={DAYS}"
)

WEEKDAYS_DE = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag",
]

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
    """Lädt das Thermalmap-Widget vollständig im Browser (headless)."""
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
# HTML-TABELLE -> RECHTECKIGES WERTE-GITTER
# ================================================================
def table_to_grid(table):
    """
    Wandelt eine HTML-Tabelle in ein Werte-Gitter (Liste von Zeilen) um.
    Zusammengefuehrte Zellen (colspan) werden nur in ihre erste Spalte
    geschrieben, die uebrigen ueberspannten Spalten bleiben leer. Das
    entspricht exakt der Darstellung von Thermalmap, z. B. bei den
    Tagesueberschriften und der Zeile "PFD [km]".
    Rowspan wird bewusst nicht behandelt, da Thermalmap es in dieser
    Tabelle nicht verwendet.
    """
    grid = []
    for tr in table.find_all("tr"):
        row_values = []
        for cell in tr.find_all(["th", "td"]):
            text = clean_text(cell.get_text(" ", strip=True))
            colspan = int(cell.get("colspan", 1) or 1)
            row_values.append(text)
            row_values.extend([""] * (colspan - 1))
        grid.append(row_values)
    return grid


# ================================================================
# KENNWERT-ZEILEN AUF FELDNAMEN ABBILDEN
# ================================================================
def map_metric_label(label):
    """
    Ordnet eine Zeilenbeschriftung der Thermalmap-Tabelle einem stabilen
    Ausgabe-Feldnamen zu. Gibt (None, None) zurueck, wenn die Zeile nicht
    zu den erwarteten Kennwerten gehoert (z. B. eine leere Trennzeile).
    """
    text = label.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")

    if "thermikstaerke" in text:
        return "thermik", "Thermik[m/s]"
    if "arbeitshoehe" in text:
        return "arbeitshoehe", "Arbhoehe[m]"
    if "pro stunde" in text:
        return "pfd_stunde", "PFD/h[km/h]"
    if text.strip().startswith("pfd"):
        return "pfd_gesamt", "__PFD_TOTAL__"
    if "hohe bewoelkung" in text:
        return "bew_hoch", "BewHoch[/8]"
    if "mittlere bewoelkung" in text:
        return "bew_mittel", "BewMittel[/8]"
    if "tiefe bewoelkung" in text:
        return "bew_tief", "BewTief[/8]"
    if "wind richtung" in text:
        return "wind_richtung", "WindRicht[°]"
    if text.strip().startswith("wind"):
        return "wind", "Wind[km/h]"
    if "temperature" in text or "temperatur" in text:
        return "temp", "Temp[°C]"
    if "taupunkt" in text:
        return "taupunkt", "Taupunkt[°C]"
    return None, None


# ================================================================
# TAGESLABEL ("Sonntag, 09.08") -> DATUM
# ================================================================
def parse_day_label(label, reference_date):
    match = re.search(r"(\d{1,2})\.(\d{1,2})", label)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    year = reference_date.year
    try:
        candidate = datetime(year, month, day).date()
    except ValueError:
        return None
    # Forecasts ueber den Jahreswechsel korrekt zuordnen.
    delta_days = (candidate - reference_date.date()).days
    if delta_days < -180:
        candidate = datetime(year + 1, month, day).date()
    elif delta_days > 180:
        candidate = datetime(year - 1, month, day).date()
    return candidate


# ================================================================
# GITTER -> STRUKTURIERTE TAGES-/STUNDENDATEN
# ================================================================
def extract_days(grid, reference_date):
    """
    Liest aus dem Werte-Gitter die Tagesbloecke aus. Jeder Tag liefert
    ein Datum, eine nach Stunden aufsteigend sortierte Liste von
    Datensaetzen sowie die PFD-Tagessumme.
    """
    if len(grid) < 3:
        raise RuntimeError("Tabelle hat zu wenige Zeilen fuer eine Auswertung.")

    day_header_row = grid[0]
    hour_row = grid[1]
    metric_rows = grid[2:]

    data_columns = len(hour_row) - 1  # Spalte 0 ist die Zeilenbeschriftung
    if data_columns <= 0 or data_columns % DAYS != 0:
        raise RuntimeError(
            f"Unerwartete Spaltenanzahl ({data_columns}) fuer {DAYS} Tage."
        )
    block_width = data_columns // DAYS

    days = []
    for day_index in range(DAYS):
        start_col = 1 + day_index * block_width

        day_label = day_header_row[start_col] if start_col < len(day_header_row) else ""
        day_date = parse_day_label(day_label, reference_date)

        hours = []
        for offset in range(block_width):
            col = start_col + offset
            raw = hour_row[col] if col < len(hour_row) else ""
            hours.append(int(raw)) if raw.strip().isdigit() else hours.append(None)

        records_by_hour = {}
        daily_total = ""

        for row in metric_rows:
            if not row:
                continue
            key, out_name = map_metric_label(row[0])
            if key is None:
                continue

            block_values = [
                row[start_col + offset] if start_col + offset < len(row) else ""
                for offset in range(block_width)
            ]

            if key == "pfd_gesamt":
                daily_total = next((v for v in block_values if v.strip()), "")
                continue

            for offset, value in enumerate(block_values):
                hour = hours[offset]
                if hour is None:
                    continue
                records_by_hour.setdefault(hour, {})[out_name] = value

        sorted_records = [
            {"hour": hour, "fields": records_by_hour[hour]}
            for hour in sorted(records_by_hour)
        ]

        days.append({
            "date": day_date,
            "label": day_label,
            "records": sorted_records,
            "pfd_total": daily_total,
        })

    return days


# ================================================================
# AUSGABETEXT AUFBAUEN (KOPFBEREICH + DATENBEREICH)
# ================================================================
def build_output_text(html, execution_time):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise RuntimeError("Keine Tabelle im HTML gefunden.")

    grid = table_to_grid(table)
    days = extract_days(grid, execution_time)

    valid_days = [d for d in days if d["date"] is not None]
    if valid_days:
        window_start = min(d["date"] for d in valid_days)
        window_end = max(d["date"] for d in valid_days)
        window_text = (
            f"{window_start.strftime('%d.%m.%Y')} - {window_end.strftime('%d.%m.%Y')} "
            f"({len(days)} Tage)"
        )
    else:
        window_text = "nicht ermittelbar"

    hours_seen = sorted({
        r["hour"] for d in days for r in d["records"]
    })
    hour_range = (
        f"{hours_seen[0]:02d}:00 - {hours_seen[-1]:02d}:00 Uhr UTC"
        if hours_seen else "nicht ermittelbar"
    )

    lines = []
    lines.append("=" * 55)
    lines.append("THERMIK-PROGNOSE DATENEXPORT")
    lines.append("=" * 55)
    lines.append("Quelle:            Thermalmap.info")
    lines.append(f"                    {URL}")
    lines.append(f"Standort:           {LOCATION_NAME} ({LOCATION_CODE})")
    lines.append(f"Verein:             {CLUB}")
    lines.append(f"Koordinaten:        {LATITUDE} N / {LONGITUDE} E")
    lines.append(f"Ausfuehrung:        {execution_time.strftime('%d.%m.%Y %H:%M:%S')}")
    lines.append(f"Zeitfenster:        {window_text}")
    lines.append(f"Aufloesung:         stuendlich, {hour_range}")
    lines.append("=" * 55)
    lines.append("")

    for day in days:
        weekday = WEEKDAYS_DE[day["date"].weekday()] if day["date"] else "?"
        date_text = day["date"].strftime("%d.%m.%Y") if day["date"] else day["label"]
        lines.append(f"TAG: {weekday}, {date_text}")
        lines.append("-" * 55)

        if not day["records"]:
            lines.append("keine Datensaetze gefunden")
            lines.append("-" * 55)
            lines.append("")
            continue

        header_cols = list(day["records"][0]["fields"].keys())
        lines.append("Std(UTC) | " + " | ".join(header_cols))
        for record in day["records"]:
            values = [record["fields"].get(col, "") for col in header_cols]
            lines.append(f"{record['hour']:02d} | " + " | ".join(values))

        if day["pfd_total"]:
            lines.append(f"PFD Tagessumme: {day['pfd_total']} km")
        lines.append("-" * 55)
        lines.append("")

    lines.append("Ende des Exports.")
    lines.append("=" * 55)
    return "\n".join(lines)


# ================================================================
# TEXTDATEI SPEICHERN
# ================================================================
def save_output(text, execution_time):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"thermalmap_wolfsaap_{execution_time.strftime('%Y%m%d')}.txt"
    output_file = BASE_DIR / filename
    output_file.write_text(text, encoding="utf-8")
    return output_file


# ================================================================
# MAIN
# ================================================================
if __name__ == "__main__":
    print()
    print("============================================")
    print("THERMALMAP - WOLFS-AAP")
    print("============================================")
    print()

    html = load_thermalmap()
    print(f"HTML geladen: {len(html):,} Zeichen")

    raw_file = save_raw_html(html)

    execution_time = datetime.now(TIMEZONE)
    output_text = build_output_text(html, execution_time)
    output_file = save_output(output_text, execution_time)

    print()
    print("============================================")
    print("THERMALMAP-DATEN GESPEICHERT")
    print("============================================")
    print()
    print(f"TXT-Datei:\n{output_file}")
    print()
    print(f"Roh-HTML:\n{raw_file}")
    print()
    print(f"Dateigroesse: {output_file.stat().st_size:,} Bytes")
    print()
