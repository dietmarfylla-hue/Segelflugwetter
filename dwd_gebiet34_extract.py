"""
DWD Segelflug-Daten Extraktor – GAFOR-Gebiet 34 (Niederrheinische Bucht)
=============================================================================
Parst die DWD GAFOR-Segelflug-Seite und erzeugt strukturierte Daten
(JSON-Dict) sowie einen kompakten Textblock, der direkt an einen
KI-Agenten übergeben werden kann.
"""
import json
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
 
# ================================================================
# KONFIGURATION
# ================================================================
URL = "https://www.dwd.de/DE/fachnutzer/luftfahrt/teaser/gebietsvorhersagen_segelflug/node_34"
 
# Relativer Ausgabeordner im Repo (statt Windows-Pfad)
BASE_DIR = Path("output")
 
LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")
 
# UTC-Offset wird automatisch aus LOCAL_TIMEZONE ermittelt (MEZ=1 im
# Winter, MESZ=2 im Sommer), damit er nicht mehr von Hand gepflegt werden
# muss und nicht (wie vorher) versehentlich auf MEZ stehen bleibt, während
# gerade MESZ gilt. Bei Bedarf kann UTC_OFFSET_OVERRIDE gesetzt werden, um
# die automatische Erkennung zu übersteuern.
UTC_OFFSET_OVERRIDE = None  # z.B. 1 oder 2, oder None für Auto-Erkennung
 
 
def get_utc_offset():
    if UTC_OFFSET_OVERRIDE is not None:
        return UTC_OFFSET_OVERRIDE
    now = datetime.now(LOCAL_TIMEZONE)
    return int(now.utcoffset().total_seconds() // 3600)
 
 
UTC_OFFSET = get_utc_offset()
 
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
# ZEITUMRECHNUNG UTC -> LOKAL
# ================================================================
def utc_to_local(utc_str, offset=None):
    """
    Wandelt DWD-UTC-Zeitstring in Lokalzeit um.
    Akzeptiert: 'Sa 13', '13:00', '13', '05:18'
    """
    if offset is None:
        offset = UTC_OFFSET
    s = utc_str.strip()
    if not s or s == "-":
        return s
    if " " in s and any(s.startswith(d) for d in ["Sa", "So", "Mo", "Di", "Mi", "Do", "Fr"]):
        parts = s.split()
        h = int(parts[-1])
        return f"{(h + offset) % 24:02d}:00"
    if ":" in s:
        parts = s.split(":")
        h = (int(parts[0]) + offset) % 24
        return f"{h:02d}:{parts[1]}"
    try:
        h = int(s)
        return f"{(h + offset) % 24:02d}:00"
    except ValueError:
        return s
 
 
# ================================================================
# HTML-TABELLEN PARSEN
# ================================================================
def parse_dwd_tables(html_data):
    """
    Parst alle Tabellen der DWD-Segelflug-Seite.
    """
    soup = BeautifulSoup(html_data, "html.parser")
    tables = soup.find_all("table")
    data = {}
 
    # ── Meta-Informationen ──
    meta = {}
    for h1 in soup.find_all("h1"):
        t = h1.get_text(strip=True)
        if "GAFOR-Gebiet" in t:
            meta["gebiet"] = t
        if "Vorhersagen für" in t:
            meta["vorhersage_fuer"] = t
    for h3 in soup.find_all("h3"):
        t = h3.get_text(strip=True)
        if "Vorhersage ausgegeben" in t:
            meta["vorhersage_ausgegeben"] = t
    data["meta"] = meta
 
    # ── Tabelle 0: Astronomische Angaben ──
    if len(tables) > 0:
        astro = {}
        for row in tables[0].find_all("tr"):
            cells = row.find_all("td")
            texts = [c.get_text(strip=True).replace("\xa0", " ") for c in cells]
            for i, t in enumerate(texts):
                if "Sonnenaufgang" in t and i + 1 < len(texts):
                    astro["sonnenaufgang_utc"] = texts[i + 1]
                    astro["sonnenaufgang_lokal"] = utc_to_local(texts[i + 1])
                if "Sonnenuntergang" in t and i + 1 < len(texts):
                    astro["sonnenuntergang_utc"] = texts[i + 1]
                    astro["sonnenuntergang_lokal"] = utc_to_local(texts[i + 1])
                if "Beginn" in t and "Dämmerung" in t and i + 1 < len(texts):
                    astro["daemmerung_beginn_utc"] = texts[i + 1]
                if "Ende" in t and "Dämmerung" in t and i + 1 < len(texts):
                    astro["daemmerung_ende_utc"] = texts[i + 1]
                if "Mondphase" in t and i + 1 < len(texts):
                    astro["mondphase"] = texts[i + 1]
        data["astronomie"] = astro
 
    # ── Tabelle 1: Thermik-Gebietsangaben ──
    if len(tables) > 1:
        therm = {"gebietsmittel": {}, "maximum": {}}
        rows = tables[1].find_all("tr")
        hdr_cells = rows[0].find_all("td")
        stunden = [c.get_text(strip=True) for c in hdr_cells[2:]]
        stunden_lokal = [utc_to_local(s) for s in stunden]
        therm["stunden_utc"] = stunden
        therm["stunden_lokal"] = stunden_lokal
        current_group = None
        for row in rows[1:]:
            cells = row.find_all("td")
            texts = [c.get_text(strip=True).replace("\xa0", " ") for c in cells]
            first = cells[0]
            rs = int(first.get("rowspan", 1))
            if rs > 1:
                current_group = "gebietsmittel" if "Gebietsmittel" in texts[0] else "maximum"
                param = texts[1]
                values = texts[2:]
            else:
                param = texts[0]
                values = texts[1:]
            if current_group:
                therm[current_group][param] = values
        data["thermik_gebiet"] = therm
 
    # ── Tabelle 2: Thermik Beginn/Ende/PFD ──
    if len(tables) > 2:
        summary = []
        rows = tables[2].find_all("tr")
        for row in rows[1:]:
            cells = row.find_all("td")
            texts = [c.get_text(strip=True).replace("\xa0", " ") for c in cells]
            if len(texts) >= 4:
                summary.append({
                    "kategorie": texts[0],
                    "beginn_utc": texts[1],
                    "beginn_lokal": utc_to_local(texts[1]),
                    "ende_utc": texts[2],
                    "ende_lokal": utc_to_local(texts[2]),
                    "pfd_tag_km": texts[3],
                })
        data["thermik_zusammenfassung"] = summary
 
    # ── Tabelle 3: Referenzstation ──
    if len(tables) > 3:
        ref = {}
        rows = tables[3].find_all("tr")
        hdr_cells = rows[0].find_all("td")
        stunden = [c.get_text(strip=True) for c in hdr_cells[1:]]
        stunden_lokal = [utc_to_local(s) for s in stunden]
        ref["stunden_utc"] = stunden
        ref["stunden_lokal"] = stunden_lokal
        params = {}
        for row in rows[1:]:
            cells = row.find_all("td")
            texts = [c.get_text(strip=True).replace("\xa0", " ") for c in cells]
            if texts:
                params[texts[0]] = texts[1:]
        ref["parameter"] = params
        hourly = []
        for idx in range(len(stunden)):
            record = {
                "stunde_utc": stunden[idx],
                "stunde_lokal": stunden_lokal[idx],
            }
            for param_name, values in params.items():
                if idx < len(values):
                    record[param_name] = values[idx]
            hourly.append(record)
        ref["stuendlich"] = hourly
        data["referenzstation"] = ref
 
    # ── Tabelle 4: Legenden ──
    if len(tables) > 4:
        legenden = {}
        for row in tables[4].find_all("tr"):
            cells = row.find_all("td")
            texts = [c.get_text(strip=True).replace("\xa0", " ") for c in cells]
            if texts:
                legenden[texts[0]] = texts[1:]
        data["legenden"] = legenden
    return data
 
 
# ================================================================
# PROMPT-TEXT ERZEUGEN
# ================================================================
def _format_thermik_gruppe(titel, gruppe, stunden_lokal, lines):
    """Formatiert eine vollständige Stundentabelle für eine Thermik-Gruppe
    (Gebietsmittel ODER Maximum im Gebiet). Jede Stunde bekommt IMMER eine
    Tabellenzeile, auch wenn alle Werte nur '-' sind (z.B. nachts/ohne
    Thermik) - es wird nichts stillschweigend weggelassen."""
    lines.append(f"{titel}:")
    if not gruppe or not stunden_lokal:
        lines.append("  (keine Daten in der Quelltabelle gefunden)")
        return
 
    ah = gruppe.get("Arbeitshöhe [m AMSL]", [])
    st = gruppe.get("Mittleres Steigen [m/s]", [])
    pfd = gruppe.get("PFD/1h [km]", [])
 
    header = (
        f"{'Stunde(Lok)':>11} | {'Arbeitshöhe [m AMSL]':>21} | "
        f"{'Mittl. Steigen [m/s]':>21} | {'PFD/1h [km]':>11}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for i, s in enumerate(stunden_lokal):
        a = ah[i] if i < len(ah) else "-"
        sv = st[i] if i < len(st) else "-"
        p = pfd[i] if i < len(pfd) else "-"
        lines.append(f"{s:>11} | {a:>21} | {sv:>21} | {p:>11}")
 
 
def build_prompt_text(data):
    """
    Baut einen kompakten, strukturierten Textblock für den KI-Prompt.
    """
    lines = []
    meta = data.get("meta", {})
    astro = data.get("astronomie", {})
    ref = data.get("referenzstation", {})
    therm_g = data.get("thermik_gebiet", {})
    therm_s = data.get("thermik_zusammenfassung", [])
 
    lines.append("=== DWD SEGELFLUG-DATEN ===")
    lines.append(f"Gebiet: {meta.get('gebiet', '?')}")
    lines.append(f"Vorhersage: {meta.get('vorhersage_ausgegeben', '?')}")
    lines.append(f"Gültig für: {meta.get('vorhersage_fuer', '?')}")
    lines.append("")
 
    lines.append("--- Astronomische Angaben ---")
    lines.append(
        f"Sonnenaufgang: {astro.get('sonnenaufgang_utc', '?')} UTC "
        f"= {astro.get('sonnenaufgang_lokal', '?')} Lokalzeit"
    )
    lines.append(
        f"Sonnenuntergang: {astro.get('sonnenuntergang_utc', '?')} UTC "
        f"= {astro.get('sonnenuntergang_lokal', '?')} Lokalzeit"
    )
    lines.append(f"Mondphase: {astro.get('mondphase', '?')}")
    lines.append("")
 
    # Thermik Gebiet - Zusammenfassung (Beginn/Ende/PFD Tagessumme)
    lines.append("--- Thermik-Gebietsangaben ---")
    if therm_s:
        for entry in therm_s:
            lines.append(
                f"  {entry['kategorie']}: Beginn {entry['beginn_lokal']}, "
                f"Ende {entry['ende_lokal']}, PFD/Tag {entry['pfd_tag_km']} km"
            )
    lines.append("")
 
    # Thermik Gebiet - stündliche Werte, Gebietsmittel UND Maximum
    gm = therm_g.get("gebietsmittel", {})
    mx = therm_g.get("maximum", {})
    therm_stunden = therm_g.get("stunden_lokal", [])
 
    _format_thermik_gruppe("Thermik Gebietsmittel", gm, therm_stunden, lines)
    lines.append("")
    _format_thermik_gruppe("Thermik Maximum im Gebiet", mx, therm_stunden, lines)
    lines.append("")
 
    # Referenzstation stündlich
    lines.append("--- Referenzstation (stündliche Werte) ---")
    lines.append("Alle Windangaben in km/h. Windrichtung in Grad.")
    lines.append("")
    hourly = ref.get("stuendlich", [])
    if hourly:
        lines.append(
            "Stunde(Lok) | Temp°C | Taupunkt°C | WindRi° | WindMittel | "
            "Böen | Wetter | BewTief/8 | BewMittel/8 | BewHoch/8 | "
            "Steigen m/s | ArbHöhe m"
        )
        lines.append("-" * 110)
        for h in hourly:
            lok = h.get("stunde_lokal", "?")
            temp = h.get("Temperatur [°C]", "?")
            tp = h.get("Taupunkt [°C]", "?")
            wd = h.get("Windrichtung [°]", "?")
            wm = h.get("Wind Mittel [km/h]", "?")
            wb = h.get("Wind Böen [km/h]", "?")
            wx = h.get("Wetter [ICAO Code]", "-")
            bt = h.get("Bedeckung tiefe Bewölkung [Achtel]", "?")
            bm = h.get("Bedeckung mittelhohe Bewölkung [Achtel]", "?")
            bh = h.get("Bedeckung hohe Bewölkung [Achtel]", "?")
            st = h.get("Mittleres Steigen [m/s]", "-")
            ah = h.get("Arbeitshöhe [m AMSL]", "-")
            lines.append(
                f"{lok:>10} | {temp:>5} | {tp:>9} | {wd:>6} | "
                f"{wm:>10} | {wb:>4} | {wx:>6} | {bt:>9} | "
                f"{bm:>11} | {bh:>9} | {st:>11} | {ah:>10}"
            )
    lines.append("")
 
    # Höhenwinde
    lines.append("--- Höhenwinde Referenzstation (Grad/km/h) ---")
    hoehen = [
        "Wind 1000 FT (305 m) AMSL [° km/h]",
        "Wind 2000 FT (610 m) AMSL [° km/h]",
        "Wind 3000 FT (914 m) AMSL [° km/h]",
        "Wind 5000 FT (1524 m) AMSL [° km/h]",
    ]
    params = ref.get("parameter", {})
    stunden_lok = ref.get("stunden_lokal", [])
    for hname in hoehen:
        vals = params.get(hname, [])
        if vals:
            relevant = []
            for i, v in enumerate(vals):
                if i < len(stunden_lok):
                    relevant.append(f"{stunden_lok[i]}={v}")
            lines.append(f"  {hname}:")
            lines.append(f"    {', '.join(relevant)}")
    lines.append("")
 
    lines.append("=== ENDE DWD-DATEN ===")
    return "\n".join(lines)
 
 
# ================================================================
# HAUPTFUNKTION
# ================================================================
def extract_for_agent(html_data):
    """
    Parst HTML und gibt Dict zurück mit json_data, prompt_text, json_string.
    """
    parsed = parse_dwd_tables(html_data)
    prompt = build_prompt_text(parsed)
    json_str = json.dumps(parsed, ensure_ascii=False, indent=2)
    return {
        "json_data": parsed,
        "prompt_text": prompt,
        "json_string": json_str,
    }
 
 
def fetch_html(url=URL):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text
 
 
def save_output(html_data, base_dir=BASE_DIR):
    base_dir.mkdir(parents=True, exist_ok=True)
    result = extract_for_agent(html_data)
 
    now = datetime.now(LOCAL_TIMEZONE)
    date_string = now.strftime("%Y%m%d")
    filename = f"dwd_34_{date_string}.txt"
    output_file = base_dir / filename
    output_file.write_text(result["prompt_text"], encoding="utf-8")
 
    print("====================================================")
    print("DWD-DATEN (GEBIET 34) ERFOLGREICH GESPEICHERT")
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
    save_output(html_data)
