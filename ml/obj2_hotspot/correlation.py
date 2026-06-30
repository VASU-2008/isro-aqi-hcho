"""
Fire-HCHO lagged correlation analysis.
Computes Pearson correlation between HCHO anomaly and FIRMS FRP at 0, 1, 2-day lags.
Outputs per-hotspot best-lag correlation JSON for API serving.
"""

import numpy as np
import pandas as pd
import xarray as xr
import json
from pathlib import Path
from scipy.stats import pearsonr
from tqdm import tqdm

from etl.config import ZARR_HCHO, DATA_SERVING, IGP_BBOX

CORRELATION_JSON = DATA_SERVING / "fire_hcho_correlation.json"


def compute_hcho_anomaly(ds: xr.Dataset, lat_bbox: tuple, lon_bbox: tuple) -> pd.Series:
    """Extract HCHO time series for a region and remove seasonal mean."""
    region = ds["HCHO"].sel(
        lat=slice(lat_bbox[0], lat_bbox[1]),
        lon=slice(lon_bbox[0], lon_bbox[1]),
    ).mean(["lat", "lon"])

    ts = pd.Series(region.values, index=pd.DatetimeIndex(ds.time.values))
    anomaly = ts - ts.rolling(14, center=True, min_periods=7).mean()
    return anomaly


def compute_frp_series(ds: xr.Dataset, lat_bbox: tuple, lon_bbox: tuple) -> pd.Series:
    """Extract daily FRP for a region."""
    region = ds["frp"].sel(
        lat=slice(lat_bbox[0], lat_bbox[1]),
        lon=slice(lon_bbox[0], lon_bbox[1]),
    ).sum(["lat", "lon"])
    return pd.Series(region.values, index=pd.DatetimeIndex(ds.time.values))


def best_lag_correlation(hcho_anom: pd.Series, frp: pd.Series, max_lag: int = 2) -> dict:
    """Find the lag (0–max_lag days) with highest Pearson r."""
    results = {}
    aligned = pd.DataFrame({"hcho": hcho_anom, "frp": frp}).dropna()

    for lag in range(0, max_lag + 1):
        shifted_frp = aligned["frp"].shift(lag)
        valid = aligned["hcho"].notna() & shifted_frp.notna()
        if valid.sum() < 10:
            continue
        r, p = pearsonr(aligned["hcho"][valid], shifted_frp[valid])
        results[lag] = {"r": round(float(r), 4), "p": round(float(p), 4)}

    if not results:
        return {"best_lag": 0, "r": 0.0, "p": 1.0, "all_lags": {}}

    best_lag = max(results, key=lambda k: abs(results[k]["r"]))
    return {
        "best_lag": best_lag,
        "r": results[best_lag]["r"],
        "p": results[best_lag]["p"],
        "all_lags": results,
    }


SOURCE_REGIONS = {
    "Punjab_Haryana": {
        "lat": (28.0, 32.0),
        "lon": (73.0, 77.5),
        "label": "Punjab/Haryana stubble burning",
    },
    "UP": {
        "lat": (24.0, 28.5),
        "lon": (77.5, 84.0),
        "label": "Uttar Pradesh",
    },
    "Rajasthan": {
        "lat": (23.0, 30.0),
        "lon": (69.0, 78.0),
        "label": "Rajasthan",
    },
    "Delhi_NCR": {
        "lat": (28.3, 29.0),
        "lon": (76.8, 77.5),
        "label": "Delhi NCR (receptor)",
    },
}


def run_correlation_analysis():
    ds = xr.open_zarr(str(ZARR_HCHO))
    results = {}

    for region_key, region_info in tqdm(SOURCE_REGIONS.items(), desc="Regions"):
        lat_bbox = region_info["lat"]
        lon_bbox = region_info["lon"]

        hcho_anom = compute_hcho_anomaly(ds, lat_bbox, lon_bbox)
        frp_series = compute_frp_series(ds, lat_bbox, lon_bbox)
        corr = best_lag_correlation(hcho_anom, frp_series)

        results[region_key] = {
            "label": region_info["label"],
            "lat_bbox": lat_bbox,
            "lon_bbox": lon_bbox,
            **corr,
        }
        print(f"  {region_key}: r={corr['r']:.3f} at lag={corr['best_lag']}d")

    CORRELATION_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(CORRELATION_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved correlation results: {CORRELATION_JSON}")
    return results


if __name__ == "__main__":
    run_correlation_analysis()
