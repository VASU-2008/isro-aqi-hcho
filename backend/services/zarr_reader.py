"""
Read pre-computed Zarr datacubes for API serving.
All operations are read-only; no live inference.
"""

import xarray as xr
import numpy as np
import pandas as pd
from pathlib import Path
import os

_aqi_ds: xr.Dataset | None = None
_pred_ds: xr.Dataset | None = None


def _get_aqi_ds() -> xr.Dataset:
    global _aqi_ds
    if _aqi_ds is None:
        path = os.environ.get("ZARR_AQI_PATH", "data/processed/aqi_cube.zarr")
        _aqi_ds = xr.open_zarr(path)
    return _aqi_ds


def _get_pred_ds() -> xr.Dataset | None:
    global _pred_ds
    if _pred_ds is None:
        path = "data/processed/aqi_predictions.zarr"
        if Path(path).exists():
            _pred_ds = xr.open_zarr(path)
    return _pred_ds


def aqi_geojson(date: str) -> dict:
    """Return AQI prediction grid as GeoJSON for a given date."""
    pred_ds = _get_pred_ds()
    if pred_ds is None:
        return {"type": "FeatureCollection", "features": []}

    t = pd.Timestamp(date)
    try:
        day = pred_ds.sel(time=t, method="nearest")
    except KeyError:
        return {"type": "FeatureCollection", "features": []}

    lats = pred_ds.lat.values
    lons = pred_ds.lon.values
    pollutants = ["PM2.5", "NO2", "SO2", "CO", "O3"]

    # Stack pollutant means; find cells that actually have predictions
    # (the grid is sparse — only every Nth cell is populated by inference).
    arrs = {p: day[f"{p}_mean"].values for p in pollutants if f"{p}_mean" in day}
    if not arrs:
        return {"type": "FeatureCollection", "features": []}

    valid = np.zeros((len(lats), len(lons)), dtype=bool)
    for a in arrs.values():
        valid |= ~np.isnan(a)
    cells = np.argwhere(valid)

    features = []
    for i, j in cells:
        props = {}
        aqi_values = []
        for p, a in arrs.items():
            v = float(a[i, j])
            if not np.isnan(v):
                props[p] = round(v, 1)
                aqi_values.append(v)
        if not props:
            continue
        props["aqi"] = round(max(aqi_values), 1)  # CPCB AQI = max sub-index
        props["date"] = date
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(float(lons[j]), 4), round(float(lats[i]), 4)],
            },
            "properties": props,
        })

    return {"type": "FeatureCollection", "features": features}


def timeseries(lat: float, lon: float, pollutant: str = "PM2.5") -> list[dict]:
    """Return time series for a point location from the predictions Zarr."""
    pred_ds = _get_pred_ds()
    if pred_ds is None:
        return []

    key = f"{pollutant}_mean"
    if key not in pred_ds:
        return []

    da = pred_ds[key]
    lats = pred_ds.lat.values
    lons = pred_ds.lon.values

    # Among populated cells (not all-NaN over time), find the nearest to (lat, lon).
    populated = ~np.isnan(da.values).all(axis=0)  # (lat, lon)
    if not populated.any():
        return []
    pj, pk = np.where(populated)
    dist = (lats[pj] - lat) ** 2 + (lons[pk] - lon) ** 2
    nearest = int(np.argmin(dist))
    i, j = int(pj[nearest]), int(pk[nearest])

    ts = da.values[:, i, j]
    times = pd.DatetimeIndex(pred_ds.time.values)

    result = []
    for t, v in zip(times, ts):
        if not np.isnan(v):
            result.append({"date": str(t.date()), "value": round(float(v), 2)})
    return result
