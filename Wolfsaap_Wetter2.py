"""
Wolfsaap Wetter 2
=================

Zusätzliche stündliche Wetterdaten für die gemeinsame
Segelflug-Wetteranalyse Düsseldorf-Wolfsaap.

Datenquelle:
    Open-Meteo Forecast API

Wettermodell:
    DWD ICON Seamless

Standort:
    Düsseldorf-Wolfsaap

Koordinaten:
    51.266111 N
    6.853333 E

Ausgabe:
    output/wolfsaapwetter2_YYYYMMDD.txt

YYYYMMDD = lokales Datum des Datenabrufs in Europe/Berlin

Enthaltene Daten:
    - Temperatur 2 m
    - gefühlte Temperatur
    - Luftdruck MSL
    - Windgeschwindigkeit 10 m
    - Windrichtung 10 m
    - Windböen 10 m
    - Böendifferenz
    - Windgeschwindigkeit 180 m
    - Windrichtung 180 m
    - Regen
    - Schauer
    - Schneefall
    - Wettercode
    - Wetterbeschreibung
    - Tagesmaxima

Zeitraum:
    3 Tage, stündlich

Geeignet für:
    - lokale Ausführung
    - Jupyter
    - GitHub Actions
    - spätere gemeinsame GPT-Wetteranalyse
"""


# ================================================================
# IMPORTS
# ================================================================

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import math
import pandas as pd

import openmeteo_requests
import requests_cache

from retry_requests import retry


# ================================================================
# KONFIGURATION
# ================================================================

LATITUDE = 51.266111
LONGITUDE = 6.853333

LOCATION_NAME = "Düsseldorf-Wolfsaap"
LOCATION_CODE = "Dues-W"
CLUB = "SFG"

MODEL = "dwd_icon_seamless"

FORECAST_DAYS = 3

TIMEZONE_NAME = "Europe/Berlin"

LOCAL_TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)

# ------------------------------------------------------------
# GitHub-kompatibler Ausgabeordner
#
# Lokal entsteht:
#
# output/
#     wolfsaapwetter2_YYYYMMDD.txt
#
# ------------------------------------------------------------

BASE_DIR = Path("output")

BASE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ================================================================
# OPEN-METEO CLIENT
# ================================================================

cache_session = requests_cache.CachedSession(
    ".cache",
    expire_after=3600
)

retry_session = retry(
    cache_session,
    retries=5,
    backoff_factor=0.2
)

openmeteo = openmeteo_requests.Client(
    session=retry_session
)


# ================================================================
# WMO-WETTERCODES
# ================================================================

WMO_CODES = {

    0: "Klar",

    1: "Überwiegend klar",

    2: "Teilweise bewölkt",

    3: "Bedeckt",

    45: "Nebel",

    48: "Nebel mit Reifablagerung",

    51: "Leichter Nieselregen",

    53: "Mäßiger Nieselregen",

    55: "Starker Nieselregen",

    56: "Leichter gefrierender Nieselregen",

    57: "Starker gefrierender Nieselregen",

    61: "Leichter Regen",

    63: "Mäßiger Regen",

    65: "Starker Regen",

    66: "Leichter gefrierender Regen",

    67: "Starker gefrierender Regen",

    71: "Leichter Schneefall",

    73: "Mäßiger Schneefall",

    75: "Starker Schneefall",

    77: "Schneegriesel",

    80: "Leichte Regenschauer",

    81: "Mäßige Regenschauer",

    82: "Starke Regenschauer",

    85: "Leichte Schneeschauer",

    86: "Starke Schneeschauer",

    95: "Gewitter",

    96: "Gewitter mit leichtem Hagel",

    99: "Gewitter mit starkem Hagel",
}


# ================================================================
# WETTERCODE ALS TEXT
# ================================================================

def weather_code_text(value):
    """
    Wandelt einen WMO-Wettercode in Klartext um.
    """

    if value is None:
        return "NV"

    try:

        if math.isnan(
            float(value)
        ):
            return "NV"

        code = int(
            round(
                float(value)
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return "NV"

    return WMO_CODES.get(
        code,
        f"Unbekannter Wettercode {code}"
    )


# ================================================================
# ZAHL FORMATIEREN
# ================================================================

def fmt(
    value,
    digits=1
):
    """
    Formatiert Fließkommazahlen.
    Nicht verfügbare Werte werden als NV ausgegeben.
    """

    try:

        if value is None:
            return "NV"

        if pd.isna(
            value
        ):
            return "NV"

        return (
            f"{float(value):.{digits}f}"
        )

    except (
        TypeError,
        ValueError
    ):

        return "NV"


# ================================================================
# GANZZAHL FORMATIEREN
# ================================================================

def fmt_int(
    value
):
    """
    Formatiert einen Wert als Ganzzahl.
    """

    try:

        if value is None:
            return "NV"

        if pd.isna(
            value
        ):
            return "NV"

        return str(
            int(
                round(
                    float(value)
                )
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return "NV"


# ================================================================
# WINDRICHTUNG IN KOMPASSRICHTUNG
# ================================================================

def wind_direction_text(
    degrees
):
    """
    Wandelt Windrichtung in Grad in eine
    16-teilige Kompassrichtung um.
    """

    try:

        if degrees is None:
            return "NV"

        if pd.isna(
            degrees
        ):
            return "NV"

        degrees = (
            float(degrees)
            % 360
        )

    except (
        TypeError,
        ValueError
    ):

        return "NV"

    directions = [

        "N",

        "NNO",

        "NO",

        "ONO",

        "O",

        "OSO",

        "SO",

        "SSO",

        "S",

        "SSW",

        "SW",

        "WSW",

        "W",

        "WNW",

        "NW",

        "NNW",
    ]

    index = int(
        (
            degrees
            + 11.25
        )
        / 22.5
    ) % 16

    return directions[
        index
    ]


# ================================================================
# ZEITREIHE IN EUROPE/BERLIN
# ================================================================

def create_local_datetime_index(
    start,
    end,
    interval_seconds
):
    """
    Erzeugt aus den Unix-Zeitstempeln eine lokale
    Zeitreihe für Europe/Berlin.
    """

    utc_index = pd.date_range(

        start=pd.to_datetime(
            start,
            unit="s",
            utc=True
        ),

        end=pd.to_datetime(
            end,
            unit="s",
            utc=True
        ),

        freq=pd.Timedelta(
            seconds=interval_seconds
        ),

        inclusive="left"
    )

    return utc_index.tz_convert(
        TIMEZONE_NAME
    )


# ================================================================
# API ABRUFEN
# ================================================================

def fetch_weather_data():
    """
    Ruft DWD ICON Seamless über die Open-Meteo API ab.
    """

    url = (
        "https://api.open-meteo.com/v1/forecast"
    )

    params = {

        # --------------------------------------------------------
        # Standort
        # --------------------------------------------------------

        "latitude": LATITUDE,

        "longitude": LONGITUDE,


        # --------------------------------------------------------
        # Wettermodell
        # --------------------------------------------------------

        "models": MODEL,


        # --------------------------------------------------------
        # Anzahl Vorhersagetage
        # --------------------------------------------------------

        "forecast_days": FORECAST_DAYS,


        # --------------------------------------------------------
        # Tagesdaten
        # --------------------------------------------------------

        "daily": [

            "weather_code"
        ],


        # --------------------------------------------------------
        # STÜNDLICHE DATEN
        #
        # ACHTUNG:
        #
        # Die Reihenfolge darf nur geändert werden,
        # wenn unten process_hourly() entsprechend
        # angepasst wird.
        # --------------------------------------------------------

        "hourly": [

            # 0
            "temperature_2m",

            # 1
            "wind_speed_10m",

            # 2
            "wind_gusts_10m",

            # 3
            "weather_code",

            # 4
            "pressure_msl",

            # 5
            "rain",

            # 6
            "apparent_temperature",

            # 7
            "snowfall",

            # 8
            "showers",

            # 9
            "wind_speed_180m",

            # 10
            "wind_direction_10m",

            # 11
            "wind_direction_180m",
        ],
    }

    responses = openmeteo.weather_api(
        url,
        params=params
    )

    if not responses:

        raise RuntimeError(
            "Open-Meteo hat keine Wetterdaten geliefert."
        )

    return responses[
        0
    ]


# ================================================================
# STÜNDLICHE DATEN VERARBEITEN
# ================================================================

def process_hourly(
    response
):
    """
    Verarbeitet alle stündlichen Wetterdaten.
    """

    hourly = response.Hourly()


    # ------------------------------------------------------------
    # 0 Temperatur 2 m
    # ------------------------------------------------------------

    temperature_2m = (
        hourly
        .Variables(0)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 1 Windgeschwindigkeit 10 m
    # ------------------------------------------------------------

    wind_speed_10m = (
        hourly
        .Variables(1)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 2 Böen 10 m
    # ------------------------------------------------------------

    wind_gusts_10m = (
        hourly
        .Variables(2)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 3 Wettercode
    # ------------------------------------------------------------

    weather_code = (
        hourly
        .Variables(3)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 4 Luftdruck MSL
    # ------------------------------------------------------------

    pressure_msl = (
        hourly
        .Variables(4)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 5 Regen
    # ------------------------------------------------------------

    rain = (
        hourly
        .Variables(5)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 6 Gefühlte Temperatur
    # ------------------------------------------------------------

    apparent_temperature = (
        hourly
        .Variables(6)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 7 Schneefall
    # ------------------------------------------------------------

    snowfall = (
        hourly
        .Variables(7)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 8 Schauer
    # ------------------------------------------------------------

    showers = (
        hourly
        .Variables(8)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 9 Windgeschwindigkeit 180 m
    # ------------------------------------------------------------

    wind_speed_180m = (
        hourly
        .Variables(9)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 10 Windrichtung 10 m
    # ------------------------------------------------------------

    wind_direction_10m = (
        hourly
        .Variables(10)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # 11 Windrichtung 180 m
    # ------------------------------------------------------------

    wind_direction_180m = (
        hourly
        .Variables(11)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # Zeitachse
    # ------------------------------------------------------------

    date_index = (
        create_local_datetime_index(

            hourly.Time(),

            hourly.TimeEnd(),

            hourly.Interval()
        )
    )


    # ------------------------------------------------------------
    # DataFrame erzeugen
    # ------------------------------------------------------------

    df = pd.DataFrame(
        {

            "date":
                date_index,

            "temperature_2m":
                temperature_2m,

            "apparent_temperature":
                apparent_temperature,

            "pressure_msl":
                pressure_msl,

            "wind_speed_10m":
                wind_speed_10m,

            "wind_gusts_10m":
                wind_gusts_10m,

            "wind_direction_10m":
                wind_direction_10m,

            "wind_speed_180m":
                wind_speed_180m,

            "wind_direction_180m":
                wind_direction_180m,

            "rain":
                rain,

            "showers":
                showers,

            "snowfall":
                snowfall,

            "weather_code":
                weather_code,
        }
    )


    # ------------------------------------------------------------
    # Böendifferenz
    #
    # Beispiel:
    #
    # Wind 10 m = 15 km/h
    # Böen      = 35 km/h
    #
    # Böen+     = 20 km/h
    # ------------------------------------------------------------

    df[
        "gust_difference"
    ] = (

        df[
            "wind_gusts_10m"
        ]

        -

        df[
            "wind_speed_10m"
        ]
    )


    # ------------------------------------------------------------
    # Wettercode Klartext
    # ------------------------------------------------------------

    df[
        "weather_text"
    ] = (

        df[
            "weather_code"
        ]

        .apply(
            weather_code_text
        )
    )


    # ------------------------------------------------------------
    # Windrichtung 10 m Klartext
    # ------------------------------------------------------------

    df[
        "wind_dir_10m_text"
    ] = (

        df[
            "wind_direction_10m"
        ]

        .apply(
            wind_direction_text
        )
    )


    # ------------------------------------------------------------
    # Windrichtung 180 m Klartext
    # ------------------------------------------------------------

    df[
        "wind_dir_180m_text"
    ] = (

        df[
            "wind_direction_180m"
        ]

        .apply(
            wind_direction_text
        )
    )


    # ------------------------------------------------------------
    # Lokales Datum
    # ------------------------------------------------------------

    df[
        "local_date"
    ] = (

        df[
            "date"
        ]

        .dt.date
    )

    return df


# ================================================================
# TAGESDATEN VERARBEITEN
# ================================================================

def process_daily(
    response
):
    """
    Verarbeitet den täglichen Wettercode.
    """

    daily = response.Daily()


    # ------------------------------------------------------------
    # Wettercode
    # ------------------------------------------------------------

    weather_code = (

        daily
        .Variables(0)
        .ValuesAsNumpy()
    )


    # ------------------------------------------------------------
    # Datumsachse
    # ------------------------------------------------------------

    date_index = (
        create_local_datetime_index(

            daily.Time(),

            daily.TimeEnd(),

            daily.Interval()
        )
    )


    # ------------------------------------------------------------
    # DataFrame
    # ------------------------------------------------------------

    df = pd.DataFrame(
        {

            "date":
                date_index,

            "weather_code":
                weather_code
        }
    )


    # ------------------------------------------------------------
    # Wetterbeschreibung
    # ------------------------------------------------------------

    df[
        "weather_text"
    ] = (

        df[
            "weather_code"
        ]

        .apply(
            weather_code_text
        )
    )

    return df


# ================================================================
# MAXIMALWERT MIT UHRZEIT
# ================================================================

def max_value_with_time(
    dataframe,
    column
):
    """
    Ermittelt Maximum und Zeitpunkt.
    """

    valid = dataframe[

        dataframe[
            column
        ].notna()
    ]

    if valid.empty:

        return (
            None,
            "NV"
        )

    idx = (
        valid[
            column
        ]
        .idxmax()
    )

    row = valid.loc[
        idx
    ]

    value = row[
        column
    ]

    time_text = (

        row[
            "date"
        ]

        .strftime(
            "%H:%M"
        )
    )

    return (
        value,
        time_text
    )


# ================================================================
# MINIMALWERT MIT UHRZEIT
# ================================================================

def min_value_with_time(
    dataframe,
    column
):
    """
    Ermittelt Minimum und Zeitpunkt.
    """

    valid = dataframe[

        dataframe[
            column
        ].notna()
    ]

    if valid.empty:

        return (
            None,
            "NV"
        )

    idx = (
        valid[
            column
        ]
        .idxmin()
    )

    row = valid.loc[
        idx
    ]

    value = row[
        column
    ]

    time_text = (

        row[
            "date"
        ]

        .strftime(
            "%H:%M"
        )
    )

    return (
        value,
        time_text
    )


# ================================================================
# OUTPUT-TEXT ERZEUGEN
# ================================================================

def create_output_text(
    response,
    hourly_df,
    daily_df,
    retrieval_time
):
    """
    Erstellt die strukturierte TXT-Datei.
    """

    lines = []


    # ============================================================
    # HEADER
    # ============================================================

    lines.append(
        "=== WOLFSAAP WETTER 2 ==="
    )

    lines.append(
        "Zusätzliche Wetterdaten für die Segelflug-Wetteranalyse"
    )

    lines.append("")

    lines.append(
        f"Standort: {LOCATION_NAME}"
    )

    lines.append(
        f"Code: {LOCATION_CODE}"
    )

    lines.append(
        f"Verein: {CLUB}"
    )

    lines.append(

        f"Angefragte Koordinaten: "
        f"{LATITUDE:.6f} N, "
        f"{LONGITUDE:.6f} E"
    )

    lines.append(

        f"API-Gitterkoordinaten: "
        f"{response.Latitude():.6f} N, "
        f"{response.Longitude():.6f} E"
    )

    lines.append(

        f"Geländehöhe API: "
        f"{response.Elevation():.0f} m AMSL"
    )

    lines.append(

        f"Datenabruf: "
        f"{retrieval_time.strftime('%d.%m.%Y %H:%M:%S')} "
        f"{TIMEZONE_NAME}"
    )

    lines.append(
        "Modell: DWD ICON Seamless"
    )

    lines.append(
        "Datenzugriff: Open-Meteo Forecast API"
    )

    lines.append(

        f"Vorhersagezeitraum: "
        f"{FORECAST_DAYS} Tage"
    )

    lines.append(
        "Zeitauflösung: stündlich"
    )

    lines.append(
        "Zeitangaben: Lokalzeit Europe/Berlin"
    )

    lines.append(
        "Windgeschwindigkeit: km/h"
    )

    lines.append(
        "Windrichtung: Grad meteorologisch / Kompassrichtung"
    )

    lines.append(
        "Luftdruck: hPa MSL"
    )

    lines.append(
        "Regen und Schauer: mm"
    )

    lines.append(
        "Schneefall: cm"
    )

    lines.append("")


    # ============================================================
    # TAGESÜBERSICHT
    # ============================================================

    lines.append(
        "--- Tagesübersicht ---"
    )

    lines.append("")

    german_weekdays = {

        0: "Montag",

        1: "Dienstag",

        2: "Mittwoch",

        3: "Donnerstag",

        4: "Freitag",

        5: "Samstag",

        6: "Sonntag",
    }

    for _, row in daily_df.iterrows():

        local_date = (
            row[
                "date"
            ].date()
        )

        weekday = german_weekdays[
            local_date.weekday()
        ]

        date_text = (
            local_date.strftime(
                "%d.%m.%Y"
            )
        )

        lines.append(

            f"{weekday}, {date_text}: "
            f"Wettercode "
            f"{fmt_int(row['weather_code'])} "
            f"({row['weather_text']})"
        )

    lines.append("")


    # ============================================================
    # EINZELNE TAGE
    # ============================================================

    dates = (

        hourly_df[
            "local_date"
        ]

        .drop_duplicates()

        .tolist()
    )

    for date_value in dates:

        day_df = hourly_df[

            hourly_df[
                "local_date"
            ]

            ==

            date_value

        ].copy()

        if day_df.empty:
            continue


        # --------------------------------------------------------
        # Tag / Datum
        # --------------------------------------------------------

        weekday = german_weekdays[
            date_value.weekday()
        ]

        date_display = (
            date_value.strftime(
                "%d.%m.%Y"
            )
        )


        # ========================================================
        # TAGESKOPF
        # ========================================================

        lines.append(
            "======================================================================"
        )

        lines.append(
            f"{weekday.upper()}, {date_display}"
        )

        lines.append(
            "======================================================================"
        )

        lines.append("")


        # ========================================================
        # MAXIMA / MINIMA
        # ========================================================

        max_temp, max_temp_time = (
            max_value_with_time(
                day_df,
                "temperature_2m"
            )
        )

        min_temp, min_temp_time = (
            min_value_with_time(
                day_df,
                "temperature_2m"
            )
        )

        max_gust, max_gust_time = (
            max_value_with_time(
                day_df,
                "wind_gusts_10m"
            )
        )

        max_wind_10, max_wind_10_time = (
            max_value_with_time(
                day_df,
                "wind_speed_10m"
            )
        )

        max_wind_180, max_wind_180_time = (
            max_value_with_time(
                day_df,
                "wind_speed_180m"
            )
        )

        max_gust_diff, max_gust_diff_time = (
            max_value_with_time(
                day_df,
                "gust_difference"
            )
        )


        # ========================================================
        # NIEDERSCHLAGSSUMMEN
        # ========================================================

        rain_sum = (
            day_df[
                "rain"
            ]
            .sum(
                min_count=1
            )
        )

        showers_sum = (
            day_df[
                "showers"
            ]
            .sum(
                min_count=1
            )
        )

        snowfall_sum = (
            day_df[
                "snowfall"
            ]
            .sum(
                min_count=1
            )
        )


        # ========================================================
        # LUFTDRUCK
        # ========================================================

        pressure_min = (
            day_df[
                "pressure_msl"
            ]
            .min()
        )

        pressure_max = (
            day_df[
                "pressure_msl"
            ]
            .max()
        )


        # ========================================================
        # TAGESZUSAMMENFASSUNG
        # ========================================================

        lines.append(
            "--- Tageszusammenfassung aus Stundenwerten ---"
        )

        lines.append("")

        lines.append(

            f"Maximum Temperatur: "
            f"{fmt(max_temp)} °C "
            f"um {max_temp_time}"
        )

        lines.append(

            f"Minimum Temperatur: "
            f"{fmt(min_temp)} °C "
            f"um {min_temp_time}"
        )

        lines.append(

            f"Maximum Wind 10 m: "
            f"{fmt(max_wind_10)} km/h "
            f"um {max_wind_10_time}"
        )

        lines.append(

            f"Maximum Böen 10 m: "
            f"{fmt(max_gust)} km/h "
            f"um {max_gust_time}"
        )

        lines.append(

            f"Maximum Böendifferenz: "
            f"{fmt(max_gust_diff)} km/h "
            f"um {max_gust_diff_time}"
        )

        lines.append(

            f"Maximum Wind 180 m: "
            f"{fmt(max_wind_180)} km/h "
            f"um {max_wind_180_time}"
        )

        lines.append(

            f"Luftdruck MSL: "
            f"{fmt(pressure_min)} bis "
            f"{fmt(pressure_max)} hPa"
        )

        lines.append(

            f"Regen Summe: "
            f"{fmt(rain_sum, 2)} mm"
        )

        lines.append(

            f"Schauer Summe: "
            f"{fmt(showers_sum, 2)} mm"
        )

        lines.append(

            f"Schneefall Summe: "
            f"{fmt(snowfall_sum, 2)} cm"
        )

        lines.append("")


        # ========================================================
        # STÜNDLICHE WERTE
        # ========================================================

        lines.append(
            "--- Stündliche Wetterdaten ---"
        )

        lines.append("")

        lines.append(

            "Zeit  | Temp°C | Gef°C | Druck hPa | "
            "Wind10 Ri/kmh | Böen | Böen+ | "
            "Wind180 Ri/kmh | Regen | Schauer | Schnee | Wetter"
        )

        lines.append(

            "-" * 140
        )

        for _, row in day_df.iterrows():

            time_text = (

                row[
                    "date"
                ]

                .strftime(
                    "%H:%M"
                )
            )


            # ----------------------------------------------------
            # Wind 10 m
            # ----------------------------------------------------

            wind10 = (

                f"{fmt_int(row['wind_direction_10m'])}°"

                f"{row['wind_dir_10m_text']}"

                f"/"

                f"{fmt(row['wind_speed_10m'], 0)}"
            )


            # ----------------------------------------------------
            # Wind 180 m
            # ----------------------------------------------------

            wind180 = (

                f"{fmt_int(row['wind_direction_180m'])}°"

                f"{row['wind_dir_180m_text']}"

                f"/"

                f"{fmt(row['wind_speed_180m'], 0)}"
            )


            # ----------------------------------------------------
            # Wettercode
            # ----------------------------------------------------

            weather = (

                f"{fmt_int(row['weather_code'])} "

                f"{row['weather_text']}"
            )


            # ----------------------------------------------------
            # Zeile
            # ----------------------------------------------------

            lines.append(

                f"{time_text:5} | "

                f"{fmt(row['temperature_2m']):>6} | "

                f"{fmt(row['apparent_temperature']):>5} | "

                f"{fmt(row['pressure_msl']):>10} | "

                f"{wind10:<14} | "

                f"{fmt(row['wind_gusts_10m'], 0):>4} | "

                f"{fmt(row['gust_difference'], 0):>5} | "

                f"{wind180:<15} | "

                f"{fmt(row['rain'], 2):>5} | "

                f"{fmt(row['showers'], 2):>7} | "

                f"{fmt(row['snowfall'], 2):>6} | "

                f"{weather}"
            )

        lines.append("")


    # ============================================================
    # ERLÄUTERUNGEN
    # ============================================================

    lines.append(
        "--- Erläuterungen ---"
    )

    lines.append("")

    lines.append(
        "Wind10 = Wind in 10 m über Grund."
    )

    lines.append(
        "Böen = maximale Windböe in 10 m über Grund."
    )

    lines.append(

        "Böen+ = Böengeschwindigkeit minus "
        "mittlere Windgeschwindigkeit in 10 m."
    )

    lines.append(
        "Wind180 = Wind in 180 m über Grund."
    )

    lines.append(

        "Ri = meteorologische Windrichtung; "
        "angegeben wird die Richtung, aus der der Wind kommt."
    )

    lines.append(

        "Druck = auf Meereshöhe reduzierter "
        "Luftdruck (MSL)."
    )

    lines.append(
        "Regen = großräumiger Regen."
    )

    lines.append(
        "Schauer = konvektiver Niederschlag."
    )

    lines.append(
        "NV = Wert nicht verfügbar."
    )

    lines.append("")

    lines.append(

        "Hinweis: Diese Daten sind Modellvorhersagen "
        "des DWD ICON-Systems über Open-Meteo und "
        "ersetzen keine amtlichen Flugwetterinformationen."
    )

    lines.append("")

    lines.append(
        "=== ENDE WOLFSAAP WETTER 2 ==="
    )

    return "\n".join(
        lines
    )


# ================================================================
# OUTPUT SPEICHERN
# ================================================================

def save_output(
    text,
    retrieval_time
):
    """
    Speichert die TXT-Datei.

    Dateiname:
        wolfsaapwetter2_YYYYMMDD.txt
    """

    date_string = (
        retrieval_time.strftime(
            "%Y%m%d"
        )
    )

    filename = (
        f"wolfsaapwetter2_{date_string}.txt"
    )

    output_file = (

        BASE_DIR
        /
        filename
    )

    output_file.write_text(
        text,
        encoding="utf-8"
    )

    return output_file


# ================================================================
# HAUPTPROGRAMM
# ================================================================

def main():

    # ------------------------------------------------------------
    # Zeitpunkt des Datenabrufs
    # ------------------------------------------------------------

    retrieval_time = datetime.now(
        LOCAL_TIMEZONE
    )


    # ------------------------------------------------------------
    # Startmeldung
    # ------------------------------------------------------------

    print()

    print(
        "=============================================="
    )

    print(
        "WOLFSAAP WETTER 2"
    )

    print(
        "DWD ICON Seamless via Open-Meteo"
    )

    print(
        "=============================================="
    )

    print()

    print(

        f"Datenabruf: "
        f"{retrieval_time.strftime('%d.%m.%Y %H:%M:%S')}"
    )

    print(

        f"Standort: "
        f"{LOCATION_NAME}"
    )

    print(

        f"Koordinaten: "
        f"{LATITUDE}, "
        f"{LONGITUDE}"
    )

    print()


    # ============================================================
    # DATEN ABRUFEN
    # ============================================================

    response = fetch_weather_data()

    print(
        "Open-Meteo-Daten erfolgreich empfangen."
    )

    print(

        f"API-Koordinaten: "
        f"{response.Latitude()} / "
        f"{response.Longitude()}"
    )

    print(

        f"API-Geländehöhe: "
        f"{response.Elevation()} m"
    )


    # ============================================================
    # DATEN VERARBEITEN
    # ============================================================

    hourly_df = process_hourly(
        response
    )

    daily_df = process_daily(
        response
    )


    # ============================================================
    # TEXTDATEI ERZEUGEN
    # ============================================================

    output_text = create_output_text(

        response=response,

        hourly_df=hourly_df,

        daily_df=daily_df,

        retrieval_time=retrieval_time
    )


    # ============================================================
    # DATEI SPEICHERN
    # ============================================================

    output_file = save_output(

        output_text,

        retrieval_time
    )


    # ============================================================
    # ERFOLGSMELDUNG
    # ============================================================

    print()

    print(
        "=============================================="
    )

    print(
        "DATEI ERFOLGREICH ERSTELLT"
    )

    print(
        "=============================================="
    )

    print()

    print(
        output_file.resolve()
    )

    print()

    print(

        f"Dateigröße: "
        f"{output_file.stat().st_size:,} Bytes"
    )

    print()


# ================================================================
# START
# ================================================================

if __name__ == "__main__":

    main()
