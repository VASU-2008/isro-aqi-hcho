"""
HCHO Hotspot Detection: Getis-Ord Gi* + DBSCAN clustering.
Writes hotspot polygons to PostGIS and GeoJSON serving files.
"""

import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
from shapely.geometry import Point, MultiPolygon
from sklearn.cluster import DBSCAN
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
import os

from etl.config import ZARR_HCHO, DATA_SERVING

HOTSPOT_GEOJSON = DATA_SERVING / "hotspot_polygons.geojson"


def compute_gi_star(values: np.ndarray, lats: np.ndarray, lons: np.ndarray,
                    bandwidth: float = 1.0) -> np.ndarray:
    """
    Compute Getis-Ord Gi* statistic for a 2D spatial field.
    Returns z-score array of same shape.
    Vectorized 3×3 queen-contiguity (8-neighbor + self) implementation.
    """
    from scipy.ndimage import uniform_filter, generic_filter

    n_lat, n_lon = values.shape
    n = n_lat * n_lon

    # Replace NaN with mean for statistical computation
    mean_val = np.nanmean(values)
    std_val = np.nanstd(values)
    filled = np.where(np.isnan(values), mean_val, values).astype(np.float64)

    global_mean = filled.mean()

    if std_val <= 0:
        return np.zeros((n_lat, n_lon), dtype=np.float32)

    # Window sum of values (3×3) and count of cells per window (handles edges)
    win_sum = uniform_filter(filled, size=3, mode="constant", cval=0.0) * 9.0
    ones = np.ones((n_lat, n_lon), dtype=np.float64)
    win_count = uniform_filter(ones, size=3, mode="constant", cval=0.0) * 9.0

    # Getis-Ord Gi* z-score (Ord & Getis 1995)
    numerator = win_sum - global_mean * win_count
    denominator = std_val * np.sqrt(
        (n * win_count - win_count ** 2) / (n - 1)
    )
    z_scores = numerator / (denominator + 1e-10)

    return z_scores.astype(np.float32)


def detect_hotspots_day(
    hcho: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    date: str,
    z_threshold: float = 2.58,   # p < 0.01
    dbscan_eps: float = 0.5,
    dbscan_min: int = 5,
) -> gpd.GeoDataFrame:
    """
    Run Gi* + DBSCAN on one day's HCHO grid.
    Returns GeoDataFrame of hotspot cluster polygons.
    """
    z = compute_gi_star(hcho, lats, lons)
    significant = z >= z_threshold

    if not significant.any():
        return gpd.GeoDataFrame()

    # Collect significant cell centroids
    lat_idx, lon_idx = np.where(significant)
    sig_lats = lats[lat_idx]
    sig_lons = lons[lon_idx]
    sig_z    = z[lat_idx, lon_idx]
    sig_hcho = hcho[lat_idx, lon_idx]

    coords = np.column_stack([sig_lons, sig_lats])
    labels = DBSCAN(eps=dbscan_eps, min_samples=dbscan_min).fit_predict(coords)

    rows = []
    for cluster_id in set(labels):
        if cluster_id == -1:
            continue
        mask = labels == cluster_id
        clat = sig_lats[mask]
        clon = sig_lons[mask]
        cz   = sig_z[mask]
        chcho = sig_hcho[mask]

        # Build convex hull polygon from cluster points
        from shapely.geometry import MultiPoint
        pts = MultiPoint([Point(lo, la) for la, lo in zip(clat, clon)])
        geom = pts.convex_hull.buffer(0.1)  # slight buffer to make polygon visible

        rows.append({
            "date": date,
            "cluster_id": int(cluster_id),
            "n_cells": int(mask.sum()),
            "mean_z": float(cz.mean()),
            "max_z": float(cz.max()),
            "mean_hcho": float(np.nanmean(chcho)),
            "centroid_lat": float(clat.mean()),
            "centroid_lon": float(clon.mean()),
            "geometry": geom,
        })

    return gpd.GeoDataFrame(rows, crs="EPSG:4326") if rows else gpd.GeoDataFrame()


def run_hotspot_detection(start: str, end: str) -> gpd.GeoDataFrame:
    """Run hotspot detection for all days, return combined GeoDataFrame."""
    ds = xr.open_zarr(str(ZARR_HCHO))
    times = pd.DatetimeIndex(ds.time.values)
    lats  = ds.lat.values
    lons  = ds.lon.values

    mask_start = times >= pd.Timestamp(start)
    mask_end   = times <= pd.Timestamp(end)
    sel_times  = times[mask_start & mask_end]

    gdfs = []
    for t in tqdm(sel_times, desc="Hotspot detection"):
        hcho = ds["HCHO"].sel(time=t).values
        gdf = detect_hotspots_day(hcho, lats, lons, str(t.date()))
        if not gdf.empty:
            gdfs.append(gdf)

    if not gdfs:
        print("No hotspots detected.")
        return gpd.GeoDataFrame()

    combined = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs="EPSG:4326")
    return combined


def save_hotspots(gdf: gpd.GeoDataFrame):
    """Save to GeoJSON file + optionally to PostGIS."""
    HOTSPOT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(HOTSPOT_GEOJSON, driver="GeoJSON")
    print(f"Saved {len(gdf)} hotspot polygons → {HOTSPOT_GEOJSON}")

    # Write to PostGIS if DATABASE_URL is set
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        try:
            from sqlalchemy import create_engine
            engine = create_engine(db_url)
            gdf.to_postgis("hotspot_polygons", engine, if_exists="replace", index=False)
            print(f"Written to PostGIS: hotspot_polygons ({len(gdf)} rows)")
        except Exception as e:
            print(f"PostGIS write failed (non-critical): {e}")


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-10-01")
    parser.add_argument("--end",   default="2022-11-30")
    args = parser.parse_args()

    gdf = run_hotspot_detection(args.start, args.end)
    if not gdf.empty:
        save_hotspots(gdf)
