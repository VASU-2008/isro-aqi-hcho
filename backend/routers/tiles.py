"""
XYZ tile server: renders AQI / HCHO predictions as PNG tiles via rasterio + COG.
Tiles are generated on-demand from Zarr, then cached in Redis.
"""

import io
import math
import struct
import numpy as np
import xarray as xr
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from pathlib import Path

router = APIRouter(prefix="/tiles", tags=["Tiles"])

POLLUTANT_COLORMAPS = {
    # AQI: green → yellow → orange → red → maroon
    "aqi": [(0, (0, 128, 0)), (50, (0, 228, 0)), (100, (255, 255, 0)),
            (200, (255, 126, 0)), (300, (255, 0, 0)), (400, (143, 63, 151)), (500, (126, 0, 35))],
    "hcho": [(0, (255, 255, 255)), (5e-4, (255, 200, 100)), (1e-3, (255, 100, 0)), (2e-3, (180, 0, 0))],
}


def _aqi_to_rgb(val: float) -> tuple[int, int, int]:
    bp = POLLUTANT_COLORMAPS["aqi"]
    if np.isnan(val):
        return (0, 0, 0)
    val = max(0, min(500, val))
    for i in range(len(bp) - 1):
        lo_v, lo_c = bp[i]
        hi_v, hi_c = bp[i + 1]
        if lo_v <= val <= hi_v:
            t = (val - lo_v) / (hi_v - lo_v)
            r = int(lo_c[0] + t * (hi_c[0] - lo_c[0]))
            g = int(lo_c[1] + t * (hi_c[1] - lo_c[1]))
            b = int(lo_c[2] + t * (hi_c[2] - lo_c[2]))
            return (r, g, b)
    return bp[-1][1]


def _tile_bbox(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Convert XYZ tile coords to (west, south, east, north) in EPSG:4326."""
    n = 2 ** z
    west  = x / n * 360.0 - 180.0
    east  = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def _make_png(rgb: np.ndarray) -> bytes:
    """Create a minimal valid PNG from an (H, W, 3) uint8 array."""
    import zlib

    h, w, _ = rgb.shape
    raw_rows = []
    for row in rgb:
        raw_rows.append(b"\x00" + row.tobytes())
    raw = b"".join(raw_rows)
    compressed = zlib.compress(raw, 6)

    def chunk(name: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
        return length + name + data + crc

    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr_data)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    return png


@router.get("/{z}/{x}/{y}.png")
async def get_tile(
    z: int,
    x: int,
    y: int,
    date: str = Query(...),
    layer: str = Query("aqi", description="aqi or hcho"),
):
    """Render XYZ map tile as PNG for the given date and layer."""
    west, south, east, north = _tile_bbox(z, x, y)
    tile_size = 256

    zarr_path = (
        "data/processed/aqi_predictions.zarr" if layer == "aqi"
        else "data/processed/aqi_cube.zarr"
    )
    if not Path(zarr_path).exists():
        raise HTTPException(status_code=404, detail=f"{zarr_path} not found")

    ds = xr.open_zarr(zarr_path)
    sel_lats = np.linspace(north, south, tile_size)
    sel_lons = np.linspace(west,  east,  tile_size)

    import pandas as pd
    try:
        day = ds.sel(time=pd.Timestamp(date), method="nearest")
    except Exception:
        raise HTTPException(status_code=404, detail=f"No data for {date}")

    if layer == "aqi":
        # Use max sub-index across pollutants as composite AQI
        keys = [f"{p}_mean" for p in ["PM2.5", "NO2", "SO2", "CO", "O3"] if f"{p}_mean" in day]
        if not keys:
            raise HTTPException(status_code=404, detail="No AQI predictions available")
        stacked = np.stack([day[k].interp(lat=sel_lats, lon=sel_lons).values for k in keys], axis=0)
        values = np.nanmax(stacked, axis=0)
        rgb = np.zeros((tile_size, tile_size, 3), dtype=np.uint8)
        for i in range(tile_size):
            for j in range(tile_size):
                rgb[i, j] = _aqi_to_rgb(values[i, j])
    else:
        raise HTTPException(status_code=400, detail="Use layer=aqi (hcho tiles TBD)")

    png_bytes = _make_png(rgb)
    return Response(content=png_bytes, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})
