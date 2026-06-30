import json
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from db import postgres, redis_cache

router = APIRouter(prefix="/hcho", tags=["HCHO"])

HOTSPOT_GEOJSON = Path("data/serving/hotspot_polygons.geojson")
CORR_JSON       = Path("data/serving/fire_hcho_correlation.json")


@router.get("/hotspots")
async def get_hotspots(date: str = Query(..., description="Date in YYYY-MM-DD format")):
    """Return HCHO hotspot polygons for a given date."""
    cache_key = f"hotspots:{date}"
    cached = await redis_cache.get_cached(cache_key)
    if cached:
        return cached

    # Try PostGIS first
    try:
        rows = await postgres.fetch(
            """
            SELECT cluster_id, n_cells, mean_z, max_z, mean_hcho,
                   centroid_lat, centroid_lon,
                   ST_AsGeoJSON(geom)::json AS geometry
            FROM hotspot_polygons
            WHERE date = $1::date
            """,
            date,
        )
        features = [
            {
                "type": "Feature",
                "geometry": r["geometry"],
                "properties": {k: v for k, v in r.items() if k != "geometry"},
            }
            for r in rows
        ]
    except Exception:
        # Fallback: read from GeoJSON file
        if not HOTSPOT_GEOJSON.exists():
            return {"type": "FeatureCollection", "features": []}
        data = json.loads(HOTSPOT_GEOJSON.read_text())
        features = [f for f in data.get("features", [])
                    if f["properties"].get("date") == date]

    result = {"type": "FeatureCollection", "features": features}
    await redis_cache.set_cached(cache_key, result, ttl=86400)
    return result


@router.get("/correlation")
async def get_correlation(region: str | None = None):
    """Return fire–HCHO lag correlation results, optionally filtered by region."""
    if not CORR_JSON.exists():
        raise HTTPException(status_code=404, detail="Correlation data not yet computed")
    data = json.loads(CORR_JSON.read_text())
    if region:
        data = {k: v for k, v in data.items() if k == region}
    return data
