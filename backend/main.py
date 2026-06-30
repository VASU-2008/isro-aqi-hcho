import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from dotenv import load_dotenv

load_dotenv()

from db import postgres, redis_cache
from routers import aqi, hcho, timeseries, stations, tiles

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str | None = Security(API_KEY_HEADER)):
    expected = os.environ.get("API_KEY", "")
    if expected and key != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await postgres.close_pool()
    await redis_cache.close()


app = FastAPI(
    title="ISRO AQI & HCHO API",
    description="Surface AQI and HCHO hotspot data for India from satellite observations",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Register routers (all require API key in production)
for router in [aqi.router, hcho.router, timeseries.router, stations.router, tiles.router]:
    app.include_router(router, dependencies=[Depends(verify_api_key)])


@app.get("/health", tags=["Meta"])
async def health():
    """Health check — returns status of DB and Zarr availability."""
    from pathlib import Path
    import xarray as xr

    zarr_ok = Path("data/processed/aqi_predictions.zarr").exists()
    db_ok = False
    try:
        pool = await postgres.get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass

    return {"status": "ok", "zarr": zarr_ok, "db": db_ok}


@app.get("/", tags=["Meta"])
async def root():
    return {"message": "ISRO AQI & HCHO API", "docs": "/docs"}
