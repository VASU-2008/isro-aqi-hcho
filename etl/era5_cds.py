"""
Download ERA5 reanalysis meteorology from Copernicus CDS.
Requires ~/.cdsapirc with your CDS API key.
Downloads: BLH, u10, v10, T2m, Td2m, sp → NetCDF → data/raw/era5/
"""

import cdsapi
from pathlib import Path
from tqdm import tqdm
import calendar

from etl.config import ERA5_VARIABLES, ERA5_RAW


def download_era5_month(year: int, month: int, out_dir: Path = ERA5_RAW):
    """Download ERA5 single-level fields for one month over India."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"era5_{year}{month:02d}.nc"

    if out_file.exists():
        print(f"  Skip (exists): {out_file.name}")
        return out_file

    _, n_days = calendar.monthrange(year, month)
    days = [f"{d:02d}" for d in range(1, n_days + 1)]

    c = cdsapi.Client(quiet=True)
    c.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": ERA5_VARIABLES,
            "year": str(year),
            "month": f"{month:02d}",
            "day": days,
            "time": [f"{h:02d}:00" for h in range(0, 24)],
            "area": [37, 68, 8, 97],  # N, W, S, E
            "format": "netcdf",
        },
        str(out_file),
    )
    print(f"  Downloaded: {out_file.name}")
    return out_file


def download_era5_range(start: str, end: str):
    """Download ERA5 for all months in [start, end]."""
    from datetime import datetime

    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")

    months = []
    cur_year, cur_month = s.year, s.month
    while (cur_year, cur_month) <= (e.year, e.month):
        months.append((cur_year, cur_month))
        cur_month += 1
        if cur_month > 12:
            cur_month = 1
            cur_year += 1

    print(f"Downloading ERA5 for {len(months)} month(s)...")
    files = []
    for year, month in tqdm(months, desc="ERA5 months"):
        files.append(download_era5_month(year, month))
    return files


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download ERA5 reanalysis")
    parser.add_argument("--start", default="2022-10-01")
    parser.add_argument("--end",   default="2022-11-30")
    args = parser.parse_args()
    download_era5_range(args.start, args.end)
