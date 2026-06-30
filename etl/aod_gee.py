"""
Download MODIS MAIAC Aerosol Optical Depth (AOD) from Google Earth Engine.

Substitutes for INSAT-3D AOD (MOSDAC), which requires authenticated MOSDAC
downloads. MODIS MCD19A2 MAIAC provides 1 km AOD at 550 nm over India and is
served directly by GEE, so it uses the same getDownloadURL path as TROPOMI —
no Drive, no token. Downloads daily-mean GeoTIFFs to data/raw/aod/.
"""

import ee
import io
import os
import time
import zipfile
import requests
from pathlib import Path
from datetime import datetime, timedelta
from tqdm import tqdm

from etl.config import INDIA_BBOX, AOD_RAW, AOD_COLLECTION, AOD_BAND, AOD_SCALE
from etl.tropomi_gee import init_gee, _date_range


def download_aod_day(date: str, out_dir: Path = AOD_RAW) -> Path | None:
    """
    Download one day's mean MAIAC AOD (550 nm) GeoTIFF for the India bbox.
    Returns the output Path, or None if no data that day.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"aod_{date}.tif"
    if out_file.exists():
        return out_file

    next_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    region = ee.Geometry.Rectangle(INDIA_BBOX)

    col = (
        ee.ImageCollection(AOD_COLLECTION)
        .filterDate(date, next_date)
        .filterBounds(region)
        .select(AOD_BAND)
    )
    if col.size().getInfo() == 0:
        return None

    # Daily mean, scaled to physical AOD units (MCD19A2 scale = 0.001)
    daily_mean = col.mean().multiply(AOD_SCALE).rename("AOD")

    url = daily_mean.getDownloadURL({
        "region": region,
        "scale": 5500,            # match TROPOMI grid (~0.05°)
        "crs": "EPSG:4326",
        "format": "GEO_TIFF",
    })

    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    if resp.content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            tif_name = next(n for n in zf.namelist() if n.endswith(".tif"))
            out_file.write_bytes(zf.read(tif_name))
    else:
        out_file.write_bytes(resp.content)

    return out_file


def download_aod_range(start: str, end: str):
    """Download MAIAC AOD GeoTIFFs for all days in [start, end)."""
    init_gee()
    results = []
    for date, _ in tqdm(list(_date_range(start, end)), desc="Downloading AOD days"):
        try:
            path = download_aod_day(date)
            results.append({"date": date, "status": "ok" if path else "no_data"})
        except Exception as e:
            results.append({"date": date, "status": "error", "error": str(e)})
        time.sleep(0.05)

    ok = sum(1 for r in results if r["status"] == "ok")
    no_data = sum(1 for r in results if r["status"] == "no_data")
    errors = sum(1 for r in results if r["status"] == "error")
    print(f"\nAOD downloaded: {ok} | No data: {no_data} | Errors: {errors}")
    print(f"Output: {AOD_RAW}")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download MODIS MAIAC AOD from GEE")
    parser.add_argument("--start", default="2022-10-01")
    parser.add_argument("--end",   default="2022-11-30")
    args = parser.parse_args()
    download_aod_range(args.start, args.end)
