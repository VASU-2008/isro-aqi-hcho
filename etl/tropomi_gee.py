"""
Pull Sentinel-5P TROPOMI data from Google Earth Engine.
Downloads daily-mean GeoTIFFs directly to data/raw/tropomi/ using
getDownloadURL — no Google Drive or GCS bucket required.
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

from etl.config import (
    INDIA_BBOX, QA_THRESHOLD, TROPOMI_RAW,
    TROPOMI_COLLECTIONS, TROPOMI_BANDS, TROPOMI_QA_BANDS,
    GEE_SERVICE_ACCOUNT, GEE_KEY_FILE,
)

# cloud_fraction threshold (lower = stricter cloud masking)
CLOUD_FRACTION_MAX = 0.5


def init_gee():
    key_path = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), GEE_KEY_FILE))
    if not key_path.exists():
        key_path = Path(GEE_KEY_FILE)
    if key_path.exists() and GEE_SERVICE_ACCOUNT:
        credentials = ee.ServiceAccountCredentials(GEE_SERVICE_ACCOUNT, str(key_path))
        ee.Initialize(credentials)
    else:
        ee.Initialize()


def _date_range(start: str, end: str):
    cur = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while cur < end_dt:
        nxt = cur + timedelta(days=1)
        yield cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d")
        cur = nxt


def download_tropomi_day(date: str, pollutant: str, out_dir: Path = TROPOMI_RAW) -> Path | None:
    """
    Download one day's QA-filtered TROPOMI image directly to a local GeoTIFF.
    Uses getDownloadURL — works with service account, no Drive needed.
    Returns the output Path, or None if no data for that day.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"tropomi_{pollutant}_{date}.tif"
    if out_file.exists():
        return out_file

    next_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    collection_id = TROPOMI_COLLECTIONS[pollutant]
    band = TROPOMI_BANDS[pollutant]
    qa_band = TROPOMI_QA_BANDS[pollutant]

    region = ee.Geometry.Rectangle(INDIA_BBOX)
    col = (
        ee.ImageCollection(collection_id)
        .filterDate(date, next_date)
        .filterBounds(region)
    )

    def apply_qa(img):
        if qa_band:
            mask = img.select(qa_band).lte(CLOUD_FRACTION_MAX)
            return img.updateMask(mask)
        return img

    col_qa = col.map(apply_qa)
    count = col_qa.size().getInfo()
    if count == 0:
        return None

    daily_mean = col_qa.select(band).mean().rename(pollutant)

    url = daily_mean.getDownloadURL({
        "region": region,
        "scale": 5500,
        "crs": "EPSG:4326",
        "format": "GEO_TIFF",
    })

    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    # getDownloadURL returns a ZIP containing the GeoTIFF
    if resp.content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            tif_name = next(n for n in zf.namelist() if n.endswith(".tif"))
            out_file.write_bytes(zf.read(tif_name))
    else:
        out_file.write_bytes(resp.content)

    return out_file


def export_date_range(start: str, end: str, pollutants: list[str] | None = None):
    """
    Download TROPOMI GeoTIFFs for all days in [start, end) directly to disk.
    """
    init_gee()
    if pollutants is None:
        pollutants = list(TROPOMI_COLLECTIONS.keys())

    date_pairs = list(_date_range(start, end))
    results = []

    for date, _ in tqdm(date_pairs, desc="Downloading TROPOMI days"):
        for pollutant in pollutants:
            try:
                path = download_tropomi_day(date, pollutant)
                results.append({"date": date, "pollutant": pollutant,
                                 "status": "ok" if path else "no_data"})
            except Exception as e:
                results.append({"date": date, "pollutant": pollutant,
                                 "status": "error", "error": str(e)})
            time.sleep(0.05)

    ok = sum(1 for r in results if r["status"] == "ok")
    no_data = sum(1 for r in results if r["status"] == "no_data")
    errors = sum(1 for r in results if r["status"] == "error")
    print(f"\nDownloaded: {ok} files | No data: {no_data} | Errors: {errors}")
    print(f"Output: {TROPOMI_RAW}")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download TROPOMI data from GEE")
    parser.add_argument("--start", default="2022-10-01")
    parser.add_argument("--end",   default="2022-11-30")
    parser.add_argument("--pollutants", nargs="+", default=None,
                        choices=list(TROPOMI_COLLECTIONS.keys()))
    args = parser.parse_args()

    export_date_range(args.start, args.end, args.pollutants)
