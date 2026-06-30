"""
Colocation engine: resample TROPOMI GeoTIFFs + ERA5 NetCDF + FIRMS CSV
to a common 0.05° × 0.05° India grid and write Zarr datacubes.
"""

import numpy as np
import xarray as xr
import pandas as pd
import rasterio
from pathlib import Path
from datetime import datetime, timedelta
from tqdm import tqdm

from etl.config import (
    INDIA_BBOX, GRID_RESOLUTION, TROPOMI_RAW, ERA5_RAW, FIRMS_RAW, AOD_RAW,
    ZARR_AQI, ZARR_HCHO, TROPOMI_BANDS,
)


def make_grid() -> tuple[np.ndarray, np.ndarray]:
    """Return (lats, lons) arrays for the 0.05° India grid."""
    west, south, east, north = INDIA_BBOX
    lons = np.arange(west, east, GRID_RESOLUTION)
    lats = np.arange(south, north, GRID_RESOLUTION)
    return lats, lons


def load_tropomi_tif(tif_path: Path, pollutant: str, lats, lons) -> np.ndarray:
    """Read a TROPOMI GeoTIFF and bilinearly interpolate to the target grid."""
    with rasterio.open(tif_path) as src:
        data = src.read(1).astype(np.float32)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan

        # Build source coordinate arrays
        transform = src.transform
        src_lons = np.array([transform.c + (j + 0.5) * transform.a for j in range(src.width)])
        src_lats = np.array([transform.f + (i + 0.5) * transform.e for i in range(src.height)])

    # Use xarray for interpolation to target grid
    da = xr.DataArray(
        data,
        coords={"lat": src_lats, "lon": src_lons},
        dims=["lat", "lon"],
    )
    da_interp = da.interp(lat=lats, lon=lons, method="linear")
    return da_interp.values


def load_era5_day(nc_path: Path, date: str, lats, lons) -> dict[str, np.ndarray]:
    """Extract ERA5 fields for a single day from a monthly NetCDF, interpolate to grid."""
    ds = xr.open_dataset(nc_path)
    date_dt = np.datetime64(date)

    # Select the day (daily mean)
    day_ds = ds.sel(time=slice(date, date)).mean("time")

    var_map = {
        "u10": "u10",
        "v10": "v10",
        "blh": "blh",
        "t2m": "t2m",
        "d2m": "d2m",
        "sp":  "sp",
    }

    result = {}
    for var_out, var_in in var_map.items():
        if var_in not in day_ds:
            continue
        da = day_ds[var_in]
        # ERA5 may use 'latitude'/'longitude' instead of 'lat'/'lon'
        rename = {}
        if "latitude" in da.dims:
            rename["latitude"] = "lat"
        if "longitude" in da.dims:
            rename["longitude"] = "lon"
        if rename:
            da = da.rename(rename)
        # ERA5 lon is 0–360, convert to -180–180 if needed
        if da.lon.max() > 180:
            da = da.assign_coords(lon=(da.lon - 360))
            da = da.sortby("lon")
        da_i = da.interp(lat=lats, lon=lons, method="linear")
        result[var_out] = da_i.values.astype(np.float32)

    ds.close()
    return result


def load_aod_day(date: str, lats, lons) -> np.ndarray:
    """Load MAIAC AOD GeoTIFF for a single day, interpolate to the India grid."""
    tif = AOD_RAW / f"aod_{date}.tif"
    if not tif.exists():
        return np.full((len(lats), len(lons)), np.nan, dtype=np.float32)
    try:
        return load_tropomi_tif(tif, "AOD", lats, lons)
    except Exception:
        return np.full((len(lats), len(lons)), np.nan, dtype=np.float32)


def load_firms_day(date: str, lats, lons) -> np.ndarray:
    """Load FIRMS gridded FRP for a single day and project onto India grid."""
    firms_parquet = FIRMS_RAW / "firms_gridded.parquet"
    if not firms_parquet.exists():
        return np.zeros((len(lats), len(lons)), dtype=np.float32)

    df = pd.read_parquet(firms_parquet)
    day = df[df["date"] == date]
    if day.empty:
        return np.zeros((len(lats), len(lons)), dtype=np.float32)

    # Pivot to grid
    lat_idx = np.searchsorted(lats, day["lat"].values)
    lon_idx = np.searchsorted(lons, day["lon"].values)
    grid = np.zeros((len(lats), len(lons)), dtype=np.float32)
    valid = (lat_idx < len(lats)) & (lon_idx < len(lons))
    np.add.at(grid, (lat_idx[valid], lon_idx[valid]), day["frp_sum"].values[valid])
    return grid


def date_range(start: str, end: str):
    cur = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while cur <= end_dt:
        yield cur.strftime("%Y-%m-%d")
        cur += timedelta(days=1)


def build_zarr_cubes(start: str, end: str):
    """
    Build aqi_cube.zarr and hcho_cube.zarr for the given date range.
    Requires TROPOMI GeoTIFFs already downloaded to data/raw/tropomi/.
    """
    lats, lons = make_grid()
    dates = list(date_range(start, end))
    n_t, n_lat, n_lon = len(dates), len(lats), len(lons)

    pollutants = ["NO2", "SO2", "CO", "O3", "HCHO"]
    era5_vars = ["u10", "v10", "blh", "t2m", "d2m", "sp"]

    # Pre-allocate arrays
    data = {p: np.full((n_t, n_lat, n_lon), np.nan, dtype=np.float32) for p in pollutants}
    era5 = {v: np.full((n_t, n_lat, n_lon), np.nan, dtype=np.float32) for v in era5_vars}
    frp = np.zeros((n_t, n_lat, n_lon), dtype=np.float32)
    aod = np.full((n_t, n_lat, n_lon), np.nan, dtype=np.float32)

    print(f"Building Zarr cubes for {start} → {end} ({n_t} days, {n_lat}×{n_lon} grid)")

    for i, date in enumerate(tqdm(dates, desc="Days")):
        year_month = date[:7].replace("-", "")

        # Load TROPOMI
        for pol in pollutants:
            tif = TROPOMI_RAW / f"tropomi_{pol}_{date}.tif"
            if tif.exists():
                try:
                    data[pol][i] = load_tropomi_tif(tif, pol, lats, lons)
                except Exception as e:
                    print(f"  Warning: TROPOMI {pol} {date}: {e}")

        # Load ERA5
        era5_nc = ERA5_RAW / f"era5_{year_month}.nc"
        if era5_nc.exists():
            try:
                day_era5 = load_era5_day(era5_nc, date, lats, lons)
                for v, arr in day_era5.items():
                    era5[v][i] = arr
            except Exception as e:
                print(f"  Warning: ERA5 {date}: {e}")

        # Load FIRMS FRP
        frp[i] = load_firms_day(date, lats, lons)

        # Load MAIAC AOD
        aod[i] = load_aod_day(date, lats, lons)

    # Gap-fill: linear interpolation along time axis for gaps ≤ 3 days
    time_coords = pd.DatetimeIndex(dates)
    for pol in pollutants:
        da = xr.DataArray(data[pol], dims=["time", "lat", "lon"],
                          coords={"time": time_coords})
        data[pol] = da.interpolate_na("time", max_gap="3D", method="linear").values

    # Gap-fill AOD too (clouds cause frequent gaps)
    aod_da = xr.DataArray(aod, dims=["time", "lat", "lon"], coords={"time": time_coords})
    aod = aod_da.interpolate_na("time", max_gap="3D", method="linear").values

    # Build AQI datacube (all pollutants + ERA5)
    coords = {
        "time": pd.DatetimeIndex(dates),
        "lat": lats,
        "lon": lons,
    }
    aqi_vars = {p: (["time", "lat", "lon"], data[p]) for p in pollutants}
    aqi_vars.update({v: (["time", "lat", "lon"], era5[v]) for v in era5_vars})
    aqi_vars["frp"] = (["time", "lat", "lon"], frp)
    aqi_vars["aod"] = (["time", "lat", "lon"], aod)

    aqi_ds = xr.Dataset(aqi_vars, coords=coords)
    aqi_ds.attrs = {
        "description": "ISRO AQI project: TROPOMI + ERA5 collocated cube",
        "grid_resolution_deg": GRID_RESOLUTION,
        "bbox": str(INDIA_BBOX),
        "created": datetime.utcnow().isoformat(),
    }

    # Build HCHO-specific cube (HCHO + FRP)
    hcho_ds = xr.Dataset(
        {
            "HCHO": (["time", "lat", "lon"], data["HCHO"]),
            "frp":  (["time", "lat", "lon"], frp),
            "u10":  (["time", "lat", "lon"], era5["u10"]),
            "v10":  (["time", "lat", "lon"], era5["v10"]),
        },
        coords=coords,
    )

    ZARR_AQI.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing {ZARR_AQI} ...")
    aqi_ds.to_zarr(str(ZARR_AQI), mode="w")

    print(f"Writing {ZARR_HCHO} ...")
    hcho_ds.to_zarr(str(ZARR_HCHO), mode="w")

    print("Done.")
    return aqi_ds, hcho_ds


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-10-01")
    parser.add_argument("--end",   default="2022-11-30")
    args = parser.parse_args()
    build_zarr_cubes(args.start, args.end)
