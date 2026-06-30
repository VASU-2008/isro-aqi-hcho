from fastapi import APIRouter, Query
from services import zarr_reader

router = APIRouter(prefix="/timeseries", tags=["Timeseries"])


@router.get("")
async def get_timeseries(
    lat:       float = Query(..., description="Latitude"),
    lon:       float = Query(..., description="Longitude"),
    pollutant: str   = Query("PM2.5", description="Pollutant: PM2.5, NO2, SO2, CO, O3"),
):
    """Return AQI time series for a point location."""
    return zarr_reader.timeseries(lat, lon, pollutant)
