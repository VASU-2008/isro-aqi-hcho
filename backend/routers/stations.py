from fastapi import APIRouter
from db import postgres

router = APIRouter(prefix="/stations", tags=["Stations"])


@router.get("")
async def get_stations():
    """Return all CPCB AQ station locations as GeoJSON."""
    rows = await postgres.fetch(
        "SELECT station_name, state, city, lat, lon FROM stations ORDER BY city"
    )
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
            "properties": {
                "name": r["station_name"],
                "state": r["state"],
                "city": r["city"],
            },
        }
        for r in rows
    ]
    return {"type": "FeatureCollection", "features": features}
