"""
ETL Pipeline Orchestrator
Usage: python -m etl.pipeline --start 2022-10-01 --end 2022-11-30 [--steps all|gee|era5|firms|cpcb|zarr]
"""

import argparse
import sys
from pathlib import Path

from etl.config import CPCB_PARQUET, ZARR_AQI, ZARR_HCHO


def run_gee(start, end):
    print("\n=== Step 1: TROPOMI via GEE ===")
    from etl.tropomi_gee import export_date_range
    tasks = export_date_range(start, end)
    print(f"Submitted {len(tasks)} GEE export tasks.")
    print("NOTE: Wait for GEE exports to complete in Google Drive, then download GeoTIFFs to data/raw/tropomi/")
    print("      Then re-run with --steps era5,firms,cpcb,zarr")


def run_aod(start, end):
    print("\n=== Step 1b: MODIS MAIAC AOD via GEE ===")
    from etl.aod_gee import download_aod_range
    download_aod_range(start, end)


def run_era5(start, end):
    print("\n=== Step 2: ERA5 Meteorology ===")
    from etl.era5_cds import download_era5_range
    download_era5_range(start, end)


def run_firms(start, end):
    print("\n=== Step 3: FIRMS Fire Counts ===")
    from etl.firms import load_firms_range, aggregate_to_grid
    from etl.config import FIRMS_RAW
    df = load_firms_range(start, end)
    if df.empty:
        print("  No FIRMS data downloaded. Check FIRMS_MAP_KEY in .env")
        return
    grid = aggregate_to_grid(df)
    out = FIRMS_RAW / "firms_gridded.parquet"
    grid.to_parquet(out, index=False)
    print(f"  Saved: {out}")


def run_cpcb(start="2022-10-01", end="2022-11-30"):
    print("\n=== Step 4: CPCB Station Data ===")
    if CPCB_PARQUET.exists():
        print(f"  Already exists: {CPCB_PARQUET}")
        return
    from etl.cpcb import load_cpcb, save_cpcb_parquet
    df = load_cpcb(start, end)
    save_cpcb_parquet(df)


def run_zarr(start, end):
    print("\n=== Step 5: Build Zarr Cubes ===")
    if ZARR_AQI.exists() and ZARR_HCHO.exists():
        print(f"  Already exists: {ZARR_AQI}, {ZARR_HCHO}")
        print("  Delete them manually to rebuild.")
        return
    from etl.collocate import build_zarr_cubes
    build_zarr_cubes(start, end)


def main():
    parser = argparse.ArgumentParser(description="ISRO AQI ETL pipeline")
    parser.add_argument("--start", default="2022-10-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   default="2022-11-30", help="End date YYYY-MM-DD")
    parser.add_argument(
        "--steps",
        default="all",
        help="Comma-separated steps: gee,era5,firms,cpcb,zarr  (default: all)",
    )
    args = parser.parse_args()

    steps = [s.strip() for s in args.steps.split(",")]
    if "all" in steps:
        steps = ["gee", "aod", "era5", "firms", "cpcb", "zarr"]

    print(f"Running ETL pipeline: {args.start} → {args.end}")
    print(f"Steps: {steps}")

    if "gee" in steps:
        run_gee(args.start, args.end)

    if "aod" in steps:
        run_aod(args.start, args.end)

    if "era5" in steps:
        run_era5(args.start, args.end)

    if "firms" in steps:
        run_firms(args.start, args.end)

    if "cpcb" in steps:
        run_cpcb(args.start, args.end)

    if "zarr" in steps:
        run_zarr(args.start, args.end)

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
