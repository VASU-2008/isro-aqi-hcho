from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# India bounding box [west, south, east, north]
INDIA_BBOX = [68.0, 8.0, 97.0, 37.0]

# IGP (Indo-Gangetic Plain) bounding box for stubble analysis
IGP_BBOX = [73.0, 27.0, 88.0, 32.0]

# Grid resolution in degrees
GRID_RESOLUTION = 0.05

# Default date range (stubble burning season)
DEFAULT_START = "2022-10-01"
DEFAULT_END   = "2022-11-30"

# QA threshold for TROPOMI
QA_THRESHOLD = 0.5

# Paths
ROOT = Path(__file__).parent.parent
DATA_RAW        = ROOT / "data" / "raw"
DATA_PROCESSED  = ROOT / "data" / "processed"
DATA_SERVING    = ROOT / "data" / "serving"

TROPOMI_RAW  = DATA_RAW / "tropomi"
ERA5_RAW     = DATA_RAW / "era5"
FIRMS_RAW    = DATA_RAW / "firms"
CPCB_RAW     = DATA_RAW / "cpcb"
AOD_RAW      = DATA_RAW / "aod"

ZARR_AQI  = DATA_PROCESSED / "aqi_cube.zarr"
ZARR_HCHO = DATA_PROCESSED / "hcho_cube.zarr"
CPCB_PARQUET = DATA_PROCESSED / "cpcb_stations.parquet"

MODELS_DIR = DATA_SERVING / "models"

# API keys (from .env)
FIRMS_MAP_KEY   = os.getenv("FIRMS_MAP_KEY", "")
MOSDAC_TOKEN    = os.getenv("MOSDAC_TOKEN", "")
GEE_KEY_FILE    = os.getenv("GEE_KEY_FILE", "gee_key.json")
GEE_SERVICE_ACCOUNT = os.getenv("GEE_SERVICE_ACCOUNT", "")
OPENAQ_API_KEY  = os.getenv("OPENAQ_API_KEY", "")

# OpenAQ v3 (real CPCB ground data — last 90 days only)
OPENAQ_BASE      = "https://api.openaq.org/v3"
OPENAQ_INDIA_ID  = 9  # countries_id for India

# TROPOMI GEE collection IDs
TROPOMI_COLLECTIONS = {
    "NO2":  "COPERNICUS/S5P/OFFL/L3_NO2",
    "SO2":  "COPERNICUS/S5P/OFFL/L3_SO2",
    "CO":   "COPERNICUS/S5P/OFFL/L3_CO",
    "O3":   "COPERNICUS/S5P/OFFL/L3_O3",
    "HCHO": "COPERNICUS/S5P/OFFL/L3_HCHO",
}

TROPOMI_BANDS = {
    "NO2":  "tropospheric_NO2_column_number_density",
    "SO2":  "SO2_column_number_density",
    "CO":   "CO_column_number_density",
    "O3":   "O3_column_number_density",
    "HCHO": "tropospheric_HCHO_column_number_density",
}

# GEE L3 TROPOMI collections use cloud_fraction for QA (no qa_value band).
# CO has neither cloud_fraction nor qa_value — no QA mask applied.
TROPOMI_QA_BANDS = {
    "NO2":  "cloud_fraction",
    "SO2":  "cloud_fraction",
    "CO":   None,
    "O3":   "cloud_fraction",
    "HCHO": "cloud_fraction",
}

# MODIS MAIAC AOD (substitute for INSAT-3D AOD / MOSDAC)
AOD_COLLECTION = "MODIS/061/MCD19A2_GRANULES"
AOD_BAND       = "Optical_Depth_055"   # 550 nm AOD
AOD_SCALE      = 0.001                  # MCD19A2 scale factor → physical AOD

# ERA5 variables to download
ERA5_VARIABLES = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "boundary_layer_height",
    "2m_temperature",
    "2m_dewpoint_temperature",
    "surface_pressure",
]
