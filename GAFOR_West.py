"""
DWD Flugwetterübersicht Bereich West – GAFOR-Tabelle + Volltext-Bulletin
=========================================================================
Parst die DWD-Seite "Flugwetterprognose für die Luftfahrt Bereich West"
(FBEU40 EDZE, RWZ Essen) und extrahiert daraus:
 
  1. die GAFOR-Übersichtstabelle (Gebiet, Name, GAFOR-Kategorie je
     Zeitfenster + ggf. Wetterzusatz wie "ISOL SHRA")
  2. den vollständigen Bulletin-Text aus dem <pre>-Block
     (FBEU40 EDZE ... Regionale Wetterberatungszentrale Essen/Ha)
 
und schreibt beides zusammen als eine lesbare .txt-Datei, die sich direkt
an einen KI-Agenten übergeben lässt.
 
Benutzung:
    from dwd_gafor_west_extract import extract_for_agent
    result = extract_for_agent(html_string)
    print(result["text_output"])
    print(result["json_data"])
"""
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
 
# ================================================================
# KONFIGURATION
# ================================================================
URL = "https://www.dwd.de/DE/fachnutzer/luftfahrt/teaser/luftsportberichte/fbeu40_edze_node.html"
 
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
# GAFOR-TABELLE PARSEN
# ================================================================
def parse_gafor_table(soup):
    """
    Findet die GAFOR-Tabelle ("GAFOR Bereich RWZ ...") und liefert ein
    Dict mit Titel + einer Liste von Gebieten samt ihrer Einstufung je
    Zeitfenster.
    """
    result = {"titel": None, "gebiete": []}
 
    h2 = soup.find("h2", string=lambda t: t and "GAFOR Bereich" in t)
    if h2:
        result["titel"] = h2.get_text(strip=True)
 
    table = soup.find("table")
    if not table:
        return result
 
    rows = table.find_all("tr")
    if not rows:
        return result
 
    # Kopfzeile: Gebiet | Name | Zeitfenster 1 | Zeitfenster 2 | ...
    header_cells = rows[0].find_all(["th", "td"])
    header_texts = [c.get_text(strip=True) for c in header_cells]
    zeitfenster_namen = header_texts[2:]  # alles nach "Gebiet"/"Name"
 
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
 
        gebiet_nr = cells[0].get_text(strip=True)
        name = cells[1].get_text(strip=True)
 
        zeitfenster = {}
        for i, cell in enumerate(cells[2:]):
            fenster_name = zeitfenster_namen[i] if i < len(zeitfenster_namen) else f"Spalte {i+3}"
 
            css_classes = cell.get("class", [])
            gafor_basis = None
            for cls in css_classes:
                if cls.startswith("gafor_"):
                    gafor_basis = cls.replace("gafor_", "")
                    break
 
            b_tag = cell.find("b")
            kategorie = b_tag.get_text(strip=True) if b_tag else None
 
            voller_text = cell.get_text(" ", strip=True).replace("\xa0", " ")
            zusatz = voller_text
            if kategorie:
                zusatz = voller_text.replace(kategorie, "", 1).strip()
 
            zeitfenster[fenster_name] = {
                "kategorie": kategorie,
                "gafor_basis": gafor_basis,
                "zusatz": zusatz or None,
            }
 
        result["gebiete"].append({
            "gebiet": gebiet_nr,
            "name": name,
            "zeitfenster": zeitfenster,
        })
 
    result["zeitfenster_namen"] = zeitfenster_namen
    return result
 
 
# ================================================================
# BULLETIN-VOLLTEXT (<pre>) PARSEN
# ================================================================
def parse_bulletin_text(soup):
    """
    Holt den vollständigen Freitext aus dem <pre>-Block
    (FBEU40 EDZE ... Flugwetterübersicht).
    """
    pre = soup.find("pre")
    if not pre:
        return ""
    text = pre.get_text()
    # Führende/abschließende Leerzeilen entfernen, interne Formatierung
    # (Tabellen, Einrückungen im Bulletin-Text) unverändert lassen.
    return text.strip("\n")
 
 
# ================================================================
# META-INFORMATIONEN
# ================================================================
def parse_meta(soup):
    meta = {}
    title_tag = soup.find("title")
    if title_tag:
        meta["seitentitel"] = title_tag.get_text(strip=True)
 
    breadcrumb = soup.find("strong")
    if breadcrumb:
        meta["bereich"] = breadcrumb.get_text(strip=True)
 
    return meta
 
 
# ================================================================
# TEXT-AUSGABE ERZEUGEN
# ================================================================
def build_text_output(data):
    lines = []
    meta = data.get("meta", {})
    gafor = data.get("gafor_tabelle", {})
    bulletin = data.get("bulletin_text", "")
 
    lines.append("=== DWD FLUGWETTERPROGNOSE BEREICH WEST ===")
    if meta.get("bereich"):
        lines.append(f"Bereich: {meta['bereich']}")
    if meta.get("seitentitel"):
        lines.append(f"Seitentitel: {meta['seitentitel']}")
    lines.append("")
 
    # --- GAFOR-Tabelle ---
    lines.append("--- GAFOR-Übersichtstabelle ---")
    if gafor.get("titel"):
        lines.append(gafor["titel"])
    lines.append("")
 
    zeitfenster_namen = gafor.get("zeitfenster_namen", [])
    gebiete = gafor.get("gebiete", [])
    if gebiete:
        col_gebiet_w = max(len("Gebiet"), max(len(g["gebiet"]) for g in gebiete))
        col_name_w = max(len("Name"), max(len(g["name"]) for g in gebiete))
        col_ws = [max(len(fn), 14) for fn in zeitfenster_namen]
 
        header = f"{'Gebiet':<{col_gebiet_w}} | {'Name':<{col_name_w}}"
        for fn, w in zip(zeitfenster_namen, col_ws):
            header += f" | {fn:<{w}}"
        lines.append(header)
        lines.append("-" * len(header))
 
        for g in gebiete:
            row = f"{g['gebiet']:<{col_gebiet_w}} | {g['name']:<{col_name_w}}"
            for fn, w in zip(zeitfenster_namen, col_ws):
                info = g["zeitfenster"].get(fn, {})
                kategorie = info.get("kategorie") or "-"
                zusatz = info.get("zusatz")
                zelle = f"{kategorie} {zusatz}".strip() if zusatz else kategorie
                row += f" | {zelle:<{w}}"
            lines.append(row)
    else:
        lines.append("(keine GAFOR-Daten gefunden)")
    lines.append("")
    lines.append(
        "Hinweis: Bedeutung der GAFOR-Kategorien (O/M/D/C/X) siehe "
        "offizielle DWD-GAFOR-Legende (gafor_legende.jpg auf der Quellseite)."
    )
    lines.append("")
 
    # --- Bulletin-Volltext ---
    lines.append("--- Flugwetterübersicht Bereich West (Volltext-Bulletin) ---")
    lines.append(bulletin)
    lines.append("")
 
    lines.append("=== ENDE DWD-DATEN ===")
    return "\n".join(lines)
 
 
# ================================================================
# HAUPTFUNKTION
# ================================================================
def extract_for_agent(html_data):
    """
    Parst HTML und gibt Dict zurück mit json_data, text_output, json_string.
    """
    soup = BeautifulSoup(html_data, "html.parser")
 
    data = {
        "meta": parse_meta(soup),
        "gafor_tabelle": parse_gafor_table(soup),
        "bulletin_text": parse_bulletin_text(soup),
    }
 
    text_output = build_text_output(data)
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
 
    return {
        "json_data": data,
        "text_output": text_output,
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
    filename = f"dwd_gafor_west_{date_string}.txt"
    output_file = base_dir / filename
    output_file.write_text(result["text_output"], encoding="utf-8")
 
    print("====================================================")
    print("DWD GAFOR BEREICH WEST ERFOLGREICH GESPEICHERT")
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
