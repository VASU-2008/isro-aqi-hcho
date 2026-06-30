"""
Seed the (managed) Postgres/PostGIS database on container startup.

Idempotent: creates schema if missing and loads station + hotspot data from the
baked seed files. Safe to run every boot — it skips loading if data is already
present. Used in production (Railway) where init.sql is not auto-applied.
"""

import os
import json
from pathlib import Path

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, shape
from sqlalchemy import create_engine, text

SEED_DIR = Path(__file__).parent / "seed" / "serving"
HOTSPOTS = SEED_DIR / "hotspot_polygons.geojson"
STATIONS = SEED_DIR / "cpcb_stations.parquet"

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS stations (
    id SERIAL PRIMARY KEY, station_name VARCHAR(200) NOT NULL,
    state VARCHAR(100), city VARCHAR(100),
    lat DOUBLE PRECISION NOT NULL, lon DOUBLE PRECISION NOT NULL,
    geom GEOMETRY(Point, 4326)
);
CREATE INDEX IF NOT EXISTS stations_geom_idx ON stations USING GIST (geom);

CREATE TABLE IF NOT EXISTS hotspot_polygons (
    id SERIAL PRIMARY KEY, date DATE NOT NULL, cluster_id INTEGER NOT NULL,
    n_cells INTEGER, mean_z DOUBLE PRECISION, max_z DOUBLE PRECISION,
    mean_hcho DOUBLE PRECISION, centroid_lat DOUBLE PRECISION,
    centroid_lon DOUBLE PRECISION, geometry GEOMETRY(Geometry, 4326)
);
CREATE INDEX IF NOT EXISTS hotspot_date_idx ON hotspot_polygons (date);
CREATE INDEX IF NOT EXISTS hotspot_geom_idx ON hotspot_polygons USING GIST (geometry);
"""


def seed():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("seed_db: no DATABASE_URL set — skipping")
        return
    # SQLAlchemy needs postgresql:// (Railway sometimes gives postgres://)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)
    with engine.begin() as conn:
        for stmt in SCHEMA.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt + ";"))

    # Stations
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM stations")).scalar()
    if n == 0 and STATIONS.exists():
        df = pd.read_parquet(STATIONS)
        st = (df.groupby("station")
                .agg(state=("state", "first"), city=("city", "first"),
                     lat=("lat", "first"), lon=("lon", "first"))
                .reset_index().rename(columns={"station": "station_name"}))
        gdf = gpd.GeoDataFrame(
            st, geometry=[Point(lo, la) for lo, la in zip(st.lon, st.lat)],
            crs="EPSG:4326").rename_geometry("geom")
        gdf.to_postgis("stations", engine, if_exists="append", index=False)
        print(f"seed_db: loaded {len(gdf)} stations")
    else:
        print(f"seed_db: stations already present ({n}) — skip")

    # Hotspots
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM hotspot_polygons")).scalar()
    if n == 0 and HOTSPOTS.exists():
        gj = json.loads(HOTSPOTS.read_text())
        rows = []
        for f in gj["features"]:
            p = f["properties"]
            rows.append({**p, "geometry": shape(f["geometry"])})
        gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
        gdf.to_postgis("hotspot_polygons", engine, if_exists="append", index=False)
        print(f"seed_db: loaded {len(gdf)} hotspot polygons")
    else:
        print(f"seed_db: hotspots already present ({n}) — skip")


if __name__ == "__main__":
    seed()
