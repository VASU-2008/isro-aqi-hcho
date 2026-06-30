"""
Download FIRMS (MODIS/VIIRS) fire counts for India from NASA.
Requires FIRMS_MAP_KEY in .env.
Downloads daily CSV → data/raw/firms/
"""

import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from tqdm import tqdm

from etl.config import FIRMS_MAP_KEY, FIRMS_RAW, INDIA_BBOX


FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
PRODUCT = "MODIS_SP"  # Standard Processing archive — covers historical dates back to 2000


def download_firms_day(date: str, out_dir: Path = FIRMS_RAW) -> Path:
    """Download FIRMS fire CSV for one day over India bbox."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"firms_{date}.csv"

    if out_file.exists():
        return out_file

    west, south, east, north = INDIA_BBOX
    area = f"{west},{south},{east},{north}"

    url = f"{FIRMS_BASE}/{FIRMS_MAP_KEY}/{PRODUCT}/{area}/1/{date}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    out_file.write_text(resp.text)
    return out_file


def load_firms_range(start: str, end: str) -> pd.DataFrame:
    """Download and concatenate FIRMS CSVs for a date range."""
    cur = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")

    dfs = []
    for _ in tqdm(range((end_dt - cur).days + 1), desc="FIRMS days"):
        date_str = cur.strftime("%Y-%m-%d")
        try:
            path = download_firms_day(date_str)
            df = pd.read_csv(path)
            if not df.empty:
                df["date"] = date_str
                dfs.append(df)
        except Exception as e:
            print(f"  Warning: FIRMS {date_str}: {e}")
        cur += timedelta(days=1)

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    # keep relevant columns
    cols = [c for c in ["latitude", "longitude", "frp", "brightness", "date"] if c in combined.columns]
    return combined[cols].rename(columns={"latitude": "lat", "longitude": "lon"})


def aggregate_to_grid(df: pd.DataFrame, resolution: float = 0.05) -> pd.DataFrame:
    """Aggregate FIRMS point data to a regular grid (sum FRP per cell per day)."""
    if df.empty:
        return df

    df = df.copy()
    df["lat_grid"] = (df["lat"] / resolution).round() * resolution
    df["lon_grid"] = (df["lon"] / resolution).round() * resolution

    grid = (
        df.groupby(["date", "lat_grid", "lon_grid"])["frp"]
        .sum()
        .reset_index()
        .rename(columns={"lat_grid": "lat", "lon_grid": "lon", "frp": "frp_sum"})
    )
    return grid


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download FIRMS fire data")
    parser.add_argument("--start", default="2022-10-01")
    parser.add_argument("--end",   default="2022-11-30")
    args = parser.parse_args()

    df = load_firms_range(args.start, args.end)
    grid = aggregate_to_grid(df)
    out = FIRMS_RAW / "firms_gridded.parquet"
    grid.to_parquet(out, index=False)
    print(f"Saved gridded FIRMS data: {out} ({len(grid)} rows)")
