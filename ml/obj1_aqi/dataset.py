"""
PyTorch Dataset for CNN-LSTM AQI model.
Samples a 3×3 spatial patch × 14-day window centered on each CPCB station location.
"""

import numpy as np
import pandas as pd
import xarray as xr
import torch
from torch.utils.data import Dataset
from pathlib import Path
from sklearn.preprocessing import StandardScaler
import pickle

from etl.config import ZARR_AQI, CPCB_PARQUET, MODELS_DIR

FEATURE_VARS = ["NO2", "SO2", "CO", "O3", "HCHO", "aod", "u10", "v10", "blh", "t2m", "d2m", "sp"]
PATCH_SIZE   = 3   # 3×3 spatial patch
LOOKBACK     = 14  # days

# One extra spatial feature derived: lat, lon, day-of-year
SPATIAL_FEATURES = 3  # lat_norm, lon_norm, doy_sin (added at runtime)
N_FEATURES = len(FEATURE_VARS) + SPATIAL_FEATURES  # 15


class AQIDataset(Dataset):
    """
    Each sample:
        X: (LOOKBACK, PATCH_SIZE, PATCH_SIZE, N_FEATURES) float32
        y: (n_pollutants,) float32 — AQI sub-index per pollutant
    """

    def __init__(
        self,
        zarr_path: Path = ZARR_AQI,
        cpcb_path: Path = CPCB_PARQUET,
        scaler: StandardScaler | None = None,
        fit_scaler: bool = False,
        station_ids: list[str] | None = None,
    ):
        self.ds = xr.open_zarr(str(zarr_path))
        self.cpcb = pd.read_parquet(cpcb_path)

        target_pollutants = ["PM2.5", "NO2", "SO2", "CO", "O3"]
        self.cpcb = self.cpcb[self.cpcb["pollutant"].isin(target_pollutants)]

        if station_ids is not None:
            self.cpcb = self.cpcb[self.cpcb["station"].isin(station_ids)]

        # Pivot to wide format: one row per (station, date)
        wide = self.cpcb.pivot_table(
            index=["station", "lat", "lon", "date"],
            columns="pollutant",
            values="aqi_sub",
        ).reset_index()
        wide.columns.name = None
        wide = wide.dropna(subset=["date"])
        wide["date"] = pd.to_datetime(wide["date"])
        self.wide = wide

        lats = self.ds.lat.values
        lons = self.ds.lon.values
        self.lat_step = float(lats[1] - lats[0])
        self.lon_step = float(lons[1] - lons[0])
        self.lat_min = float(lats.min())
        self.lon_min = float(lons.min())

        # Pre-load full arrays into memory (small enough for 2-month window)
        self._data = {v: self.ds[v].values for v in FEATURE_VARS if v in self.ds}

        # Build samples index: (station_lat, station_lon, date_idx)
        times = pd.DatetimeIndex(self.ds.time.values)
        self.samples = []
        for _, row in wide.iterrows():
            t_idx = times.get_loc(row["date"]) if row["date"] in times else None
            if t_idx is None or t_idx < LOOKBACK:
                continue
            lat_c = int(round((row["lat"] - self.lat_min) / self.lat_step))
            lon_c = int(round((row["lon"] - self.lon_min) / self.lon_step))
            half = PATCH_SIZE // 2
            lat_s, lat_e = lat_c - half, lat_c + half + 1
            lon_s, lon_e = lon_c - half, lon_c + half + 1
            n_lat = self._data[FEATURE_VARS[0]].shape[1]
            n_lon = self._data[FEATURE_VARS[0]].shape[2]
            if lat_s < 0 or lat_e > n_lat or lon_s < 0 or lon_e > n_lon:
                continue

            y_cols = [c for c in ["PM2.5", "NO2", "SO2", "CO", "O3"] if c in wide.columns]
            y = row[y_cols].values.astype(np.float32)
            if np.all(np.isnan(y)):
                continue

            self.samples.append({
                "t_idx": t_idx,
                "lat_s": lat_s, "lat_e": lat_e,
                "lon_s": lon_s, "lon_e": lon_e,
                "lat": row["lat"], "lon": row["lon"],
                "date": row["date"],
                "y": y,
                "station": row["station"],
            })

        # Fit or apply scaler
        if fit_scaler:
            flat = self._collect_flat_features()
            self.scaler = StandardScaler()
            self.scaler.fit(flat)
        else:
            self.scaler = scaler

    def _collect_flat_features(self) -> np.ndarray:
        """Collect flat feature matrix for scaler fitting (sampled subset)."""
        rows = []
        for s in self.samples[:500]:
            patch = self._extract_patch(s)
            rows.append(patch.reshape(-1, N_FEATURES))
        return np.vstack(rows)

    def _extract_patch(self, s: dict) -> np.ndarray:
        """Extract (LOOKBACK, P, P, N_FEATURES) array for one sample."""
        t0, t1 = s["t_idx"] - LOOKBACK, s["t_idx"]
        patch = np.stack(
            [self._data[v][t0:t1, s["lat_s"]:s["lat_e"], s["lon_s"]:s["lon_e"]]
             for v in FEATURE_VARS if v in self._data],
            axis=-1,
        ).astype(np.float32)  # (T, P, P, C)

        # Add spatial features: lat_norm, lon_norm, doy_sin
        T, P1, P2, _ = patch.shape
        lat_n = np.full((T, P1, P2, 1), (s["lat"] - 8) / 29, dtype=np.float32)
        lon_n = np.full((T, P1, P2, 1), (s["lon"] - 68) / 29, dtype=np.float32)
        doy = s["date"].day_of_year
        doy_s = np.full((T, P1, P2, 1), np.sin(2 * np.pi * doy / 365), dtype=np.float32)
        patch = np.concatenate([patch, lat_n, lon_n, doy_s], axis=-1)

        np.nan_to_num(patch, copy=False, nan=0.0)
        return patch

    def save_scaler(self, path: Path = None):
        path = path or (MODELS_DIR / "scaler.pkl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.scaler, f)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        s = self.samples[idx]
        x = self._extract_patch(s)  # (T, P, P, C)

        if self.scaler is not None:
            orig_shape = x.shape
            flat = x.reshape(-1, N_FEATURES)
            flat = self.scaler.transform(flat).astype(np.float32)
            x = flat.reshape(orig_shape)

        y = s["y"].copy()
        np.nan_to_num(y, copy=False, nan=-1.0)
        return torch.from_numpy(x), torch.from_numpy(y)
