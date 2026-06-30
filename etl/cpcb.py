"""
CPCB ground AQ station data.

Primary:   load_cpcb_csvs()  — manual CSV export from cpcb.nic.in (preferred)
Fallback:  generate_synthetic_cpcb()  — realistic synthetic data using known
           CPCB CAAQMS station coordinates and Oct–Nov AQI climatology.
           Used when real CSVs are not available (e.g. hackathon setup).
"""

import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm

from etl.config import CPCB_RAW, CPCB_PARQUET

POLLUTANTS = ["PM2.5", "PM10", "NO2", "SO2", "CO", "O3"]

AQI_BREAKPOINTS = {
    "PM2.5": [(0, 30, 0, 50), (30, 60, 51, 100), (60, 90, 101, 200),
              (90, 120, 201, 300), (120, 250, 301, 400), (250, 500, 401, 500)],
    "PM10":  [(0, 50, 0, 50), (50, 100, 51, 100), (100, 250, 101, 200),
              (250, 350, 201, 300), (350, 430, 301, 400), (430, 600, 401, 500)],
    "NO2":   [(0, 40, 0, 50), (40, 80, 51, 100), (80, 180, 101, 200),
              (180, 280, 201, 300), (280, 400, 301, 400), (400, 800, 401, 500)],
    "SO2":   [(0, 40, 0, 50), (40, 80, 51, 100), (80, 380, 101, 200),
              (380, 800, 201, 300), (800, 1600, 301, 400), (1600, 2100, 401, 500)],
    "CO":    [(0, 1, 0, 50), (1, 2, 51, 100), (2, 10, 101, 200),
              (10, 17, 201, 300), (17, 34, 301, 400), (34, 50, 401, 500)],
    "O3":    [(0, 50, 0, 50), (50, 100, 51, 100), (100, 168, 101, 200),
              (168, 208, 201, 300), (208, 748, 301, 400), (748, 1000, 401, 500)],
}

# Known CPCB CAAQMS stations (name, state, city, lat, lon, base_aqi)
# base_aqi = typical Oct–Nov AQI; IGP stations elevated due to stubble burning
KNOWN_STATIONS = [
    ("Anand Vihar", "Delhi", "Delhi", 28.6469, 77.3159, 320),
    ("ITO", "Delhi", "Delhi", 28.6289, 77.2412, 280),
    ("RK Puram", "Delhi", "Delhi", 28.5638, 77.1854, 260),
    ("Punjabi Bagh", "Delhi", "Delhi", 28.6648, 77.1313, 300),
    ("Dwarka Sector 8", "Delhi", "Delhi", 28.5733, 77.0706, 240),
    ("IHBAS", "Delhi", "Delhi", 28.6758, 77.3095, 290),
    ("Patparganj", "Delhi", "Delhi", 28.6283, 77.2964, 270),
    ("Rohini", "Delhi", "Delhi", 28.7359, 77.1152, 285),
    ("Gurugram", "Haryana", "Gurugram", 28.4595, 77.0266, 220),
    ("Faridabad", "Haryana", "Faridabad", 28.4089, 77.3178, 210),
    ("Panipat", "Haryana", "Panipat", 29.3909, 76.9635, 230),
    ("Ambala", "Haryana", "Ambala", 30.3782, 76.7767, 200),
    ("Hisar", "Haryana", "Hisar", 29.1492, 75.7217, 195),
    ("Ludhiana", "Punjab", "Ludhiana", 30.9010, 75.8573, 240),
    ("Amritsar", "Punjab", "Amritsar", 31.6340, 74.8723, 210),
    ("Patiala", "Punjab", "Patiala", 30.3398, 76.3869, 225),
    ("Jalandhar", "Punjab", "Jalandhar", 31.3260, 75.5762, 205),
    ("Lucknow", "UP", "Lucknow", 26.8467, 80.9462, 250),
    ("Kanpur", "UP", "Kanpur", 26.4499, 80.3319, 265),
    ("Varanasi", "UP", "Varanasi", 25.3176, 82.9739, 245),
    ("Agra", "UP", "Agra", 27.1767, 78.0081, 230),
    ("Noida", "UP", "Noida", 28.5355, 77.3910, 255),
    ("Ghaziabad", "UP", "Ghaziabad", 28.6692, 77.4538, 275),
    ("Patna", "Bihar", "Patna", 25.5941, 85.1376, 220),
    ("Muzaffarpur", "Bihar", "Muzaffarpur", 26.1197, 85.3910, 200),
    ("Kolkata Rabindra Sarobar", "WB", "Kolkata", 22.5153, 88.3624, 160),
    ("Kolkata Ballygunge", "WB", "Kolkata", 22.5260, 88.3639, 155),
    ("Mumbai Bandra", "Maharashtra", "Mumbai", 19.0596, 72.8295, 120),
    ("Mumbai Chakala", "Maharashtra", "Mumbai", 19.1043, 72.8613, 130),
    ("Pune Katraj", "Maharashtra", "Pune", 18.4529, 73.8674, 110),
    ("Bengaluru BWSSB", "Karnataka", "Bengaluru", 12.9716, 77.5946, 105),
    ("Bengaluru Jayanagar", "Karnataka", "Bengaluru", 12.9250, 77.5938, 100),
    ("Chennai Manali", "Tamil Nadu", "Chennai", 13.1643, 80.2570, 115),
    ("Chennai Alandur", "Tamil Nadu", "Chennai", 13.0002, 80.2090, 108),
    ("Hyderabad ICRISAT", "Telangana", "Hyderabad", 17.5082, 78.2776, 112),
    ("Jaipur Shastri Nagar", "Rajasthan", "Jaipur", 26.9124, 75.8160, 180),
    ("Ahmedabad Bopal", "Gujarat", "Ahmedabad", 23.0258, 72.4692, 150),
    ("Surat", "Gujarat", "Surat", 21.1702, 72.8311, 140),
    ("Bhopal", "MP", "Bhopal", 23.2599, 77.4126, 145),
    ("Indore", "MP", "Indore", 22.7196, 75.8577, 140),
    ("Nagpur Civil Lines", "Maharashtra", "Nagpur", 21.1458, 79.0882, 130),
    ("Vishakhapatnam", "AP", "Vishakhapatnam", 17.6868, 83.2185, 120),
    ("Kochi", "Kerala", "Kochi", 9.9312, 76.2673, 95),
    ("Thiruvananthapuram", "Kerala", "Thiruvananthapuram", 8.5241, 76.9366, 90),
    ("Dehradun", "Uttarakhand", "Dehradun", 30.3165, 78.0322, 160),
    ("Chandigarh", "Chandigarh", "Chandigarh", 30.7333, 76.7794, 185),
    ("Guwahati", "Assam", "Guwahati", 26.1445, 91.7362, 130),
    ("Bhubaneswar", "Odisha", "Bhubaneswar", 20.2961, 85.8245, 125),
    ("Raipur", "Chhattisgarh", "Raipur", 21.2514, 81.6296, 155),
    ("Jodhpur", "Rajasthan", "Jodhpur", 26.2389, 73.0243, 165),
]

# Typical Oct–Nov concentrations per pollutant relative to AQI (µg/m³)
POLLUTANT_CONC = {
    "PM2.5": (0.5, 0.15),   # multiplier of base_aqi → concentration, noise
    "PM10":  (1.2, 0.20),
    "NO2":   (0.25, 0.25),
    "SO2":   (0.08, 0.30),
    "CO":    (0.004, 0.20),
    "O3":    (0.18, 0.20),
}


def concentration_to_aqi(value: float, pollutant: str) -> float:
    if pd.isna(value) or value < 0:
        return np.nan
    breakpoints = AQI_BREAKPOINTS.get(pollutant)
    if not breakpoints:
        return np.nan
    for c_low, c_high, i_low, i_high in breakpoints:
        if c_low <= value <= c_high:
            return i_low + (value - c_low) * (i_high - i_low) / (c_high - c_low)
    return 500.0


def generate_synthetic_cpcb(start: str = "2022-10-01", end: str = "2022-11-30",
                             seed: int = 42) -> pd.DataFrame:
    """
    Generate realistic synthetic CPCB daily station data for Oct–Nov 2022.
    Uses known CPCB CAAQMS station coordinates and empirical AQI climatology
    for the stubble burning season.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")

    rows = []
    for date in dates:
        # Day-of-season factor: AQI peaks mid-Oct to mid-Nov
        doy_frac = (date - pd.Timestamp(start)).days / len(dates)
        season_factor = 1.0 + 0.4 * np.sin(np.pi * doy_frac)  # peak in middle

        for station, state, city, lat, lon, base_aqi in KNOWN_STATIONS:
            aqi_today = base_aqi * season_factor

            for pollutant, (mult, noise_frac) in POLLUTANT_CONC.items():
                conc = aqi_today * mult * (1 + rng.normal(0, noise_frac))
                conc = max(0.0, conc)
                rows.append({
                    "station": station,
                    "state": state,
                    "city": city,
                    "lat": lat,
                    "lon": lon,
                    "date": date,
                    "pollutant": pollutant,
                    "value": round(conc, 2),
                    "aqi_sub": round(concentration_to_aqi(conc, pollutant), 1),
                })

    df = pd.DataFrame(rows)
    print(f"  Generated synthetic CPCB data: {len(df):,} rows, "
          f"{df['station'].nunique()} stations, {df['date'].nunique()} days")
    return df


# OpenAQ v3 parameter names → our pollutant labels
OPENAQ_PARAM_MAP = {
    "pm25": "PM2.5", "pm10": "PM10", "no2": "NO2",
    "so2": "SO2", "co": "CO", "o3": "O3",
}


def fetch_openaq_v3(date_from: str, date_to: str, api_key: str,
                    max_locations: int = 200) -> pd.DataFrame:
    """
    Fetch real Indian ground-station daily measurements from the OpenAQ v3 API.
    NOTE: OpenAQ serves only the last ~90 days, so date_from/date_to must be recent.
    Returns the same schema as generate_synthetic_cpcb(), or empty DataFrame.
    """
    import requests
    from etl.config import OPENAQ_BASE, OPENAQ_INDIA_ID, INDIA_BBOX

    headers = {"X-API-Key": api_key}
    west, south, east, north = INDIA_BBOX

    # 1. Page through Indian monitoring locations
    locations = []
    page = 1
    while len(locations) < max_locations:
        r = requests.get(f"{OPENAQ_BASE}/locations",
                         params={"countries_id": OPENAQ_INDIA_ID, "limit": 100, "page": page},
                         headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"  OpenAQ locations HTTP {r.status_code}: {r.text[:120]}")
            break
        results = r.json().get("results", [])
        if not results:
            break
        locations.extend(results)
        page += 1
        time.sleep(0.2)

    if not locations:
        return pd.DataFrame()
    print(f"  OpenAQ: {len(locations)} Indian locations found")

    rows = []
    for loc in tqdm(locations[:max_locations], desc="  OpenAQ sensors"):
        coords = loc.get("coordinates") or {}
        lat, lon = coords.get("latitude"), coords.get("longitude")
        if lat is None or lon is None:
            continue
        name = loc.get("name", f"loc_{loc.get('id')}")
        locality = loc.get("locality") or name

        for sensor in loc.get("sensors", []):
            pname = (sensor.get("parameter") or {}).get("name")
            pollutant = OPENAQ_PARAM_MAP.get(pname)
            if not pollutant:
                continue
            sid = sensor.get("id")
            try:
                mr = requests.get(f"{OPENAQ_BASE}/sensors/{sid}/measurements/daily",
                                  params={"date_from": date_from, "date_to": date_to, "limit": 366},
                                  headers=headers, timeout=30)
                if mr.status_code != 200:
                    continue
                for m in mr.json().get("results", []):
                    value = m.get("value")
                    period = m.get("period") or {}
                    dt = (period.get("datetimeFrom") or {}).get("utc")
                    if value is None or dt is None:
                        continue
                    rows.append({
                        "station": name, "state": loc.get("country", {}).get("name", "India"),
                        "city": locality, "lat": lat, "lon": lon,
                        "date": pd.Timestamp(dt).normalize().tz_localize(None),
                        "pollutant": pollutant, "value": round(float(value), 2),
                        "aqi_sub": round(concentration_to_aqi(float(value), pollutant), 1),
                    })
            except Exception:
                continue
            time.sleep(0.1)

    df = pd.DataFrame(rows)
    if not df.empty:
        print(f"  OpenAQ: fetched {len(df):,} real measurements "
              f"from {df['station'].nunique()} stations")
    return df


def load_cpcb(start: str, end: str, cpcb_dir: Path = CPCB_RAW) -> pd.DataFrame:
    """
    Dispatcher for CPCB ground data, in priority order:
      1. Real CSV exports in data/raw/cpcb/  (if present)
      2. OpenAQ v3 real data  (if OPENAQ_API_KEY set AND window within last ~90 days)
      3. Synthetic calibrated data  (fallback)
    """
    from etl.config import OPENAQ_API_KEY

    if list(cpcb_dir.glob("*.csv")):
        return load_cpcb_csvs(cpcb_dir)

    key_set = OPENAQ_API_KEY and not OPENAQ_API_KEY.startswith("your_")
    if key_set:
        print("  Trying OpenAQ v3 for real ground data...")
        df = fetch_openaq_v3(start, end, OPENAQ_API_KEY)
        if len(df) > 100:
            return df
        print("  OpenAQ returned too little data (window likely older than 90 days)"
              " — falling back to synthetic.")

    print("  Using synthetic calibrated station data.")
    return generate_synthetic_cpcb(start, end)


def load_cpcb_csvs(cpcb_dir: Path = CPCB_RAW) -> pd.DataFrame:
    """Load real CPCB CSV exports if present, otherwise generate synthetic data."""
    csv_files = list(cpcb_dir.glob("*.csv"))
    if not csv_files:
        print("  No CPCB CSVs found — using synthetic station data.")
        return generate_synthetic_cpcb()

    dfs = []
    for f in tqdm(csv_files, desc="Loading CPCB CSVs"):
        try:
            df = pd.read_csv(f, parse_dates=["Date"], dayfirst=True)
            dfs.append(df)
        except Exception as e:
            print(f"  Warning: {f.name}: {e}")

    combined = pd.concat(dfs, ignore_index=True)
    combined.columns = combined.columns.str.strip()
    col_map = {
        "Station": "station", "State": "state", "City": "city",
        "Latitude": "lat", "Longitude": "lon",
        "Pollutant": "pollutant", "Date": "date",
        "Value": "value", "Avg": "value", "Daily Max": "value",
    }
    combined = combined.rename(columns={k: v for k, v in col_map.items() if k in combined.columns})
    combined = combined[combined["pollutant"].isin(POLLUTANTS)].copy()
    combined["value"] = pd.to_numeric(combined["value"], errors="coerce")
    combined = combined.dropna(subset=["lat", "lon", "value", "date"])
    combined["aqi_sub"] = combined.apply(
        lambda r: concentration_to_aqi(r["value"], r["pollutant"]), axis=1
    )
    return combined


def save_cpcb_parquet(df: pd.DataFrame, out: Path = CPCB_PARQUET):
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"  Saved: {out} ({len(df):,} rows, {df['station'].nunique()} stations)")


def load_cpcb_parquet() -> pd.DataFrame:
    return pd.read_parquet(CPCB_PARQUET)


if __name__ == "__main__":
    df = load_cpcb_csvs()
    save_cpcb_parquet(df)
    print(df.head())
    print(f"\nDate range: {df['date'].min()} → {df['date'].max()}")
    print(f"Pollutants: {df['pollutant'].unique()}")
