from fastapi import APIRouter, Query
from db import redis_cache
from services import zarr_reader

router = APIRouter(prefix="/aqi", tags=["AQI"])


@router.get("")
async def get_aqi(date: str = Query(..., description="Date in YYYY-MM-DD format")):
    """Return AQI prediction grid as GeoJSON for a given date."""
    cache_key = f"aqi:{date}"
    cached = await redis_cache.get_cached(cache_key)
    if cached:
        return cached

    result = zarr_reader.aqi_geojson(date)
    await redis_cache.set_cached(cache_key, result, ttl=86400)
    return result
