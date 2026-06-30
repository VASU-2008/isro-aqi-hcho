"""
Batch inference: load trained CNN-LSTM, run over the full India grid, write AQI Zarr.
Output: data/processed/aqi_predictions.zarr — dims (time, lat, lon), vars per pollutant + uncertainty
"""

import pickle
import numpy as np
import xarray as xr
import torch
import pandas as pd
from pathlib import Path
from tqdm import tqdm

from ml.obj1_aqi.model import build_model
from ml.obj1_aqi.dataset import FEATURE_VARS, N_FEATURES, LOOKBACK, PATCH_SIZE, SPATIAL_FEATURES
from etl.config import ZARR_AQI, MODELS_DIR

POLLUTANT_NAMES = ["PM2.5", "NO2", "SO2", "CO", "O3"]
AQI_OUT = Path("data/processed/aqi_predictions.zarr")


def load_model(device: str) -> tuple:
    model = build_model(n_outputs=5)
    ckpt = MODELS_DIR / "cnn_lstm_best.pt"
    model.load_state_dict(torch.load(ckpt, map_location=device))
    model.to(device)
    model.eval()

    scaler_path = MODELS_DIR / "scaler.pkl"
    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)

    return model, scaler


def predict_grid(n_passes: int = 10, stride: int = 4):
    """Run grid inference. stride>1 predicts every Nth cell for speed (demo)."""
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Device: {device} | stride: {stride}")

    model, scaler = load_model(device)
    ds = xr.open_zarr(str(ZARR_AQI))
    times = pd.DatetimeIndex(ds.time.values)
    lats = ds.lat.values
    lons = ds.lon.values
    n_t, n_lat, n_lon = len(times), len(lats), len(lons)

    data_arr = {v: ds[v].values for v in FEATURE_VARS if v in ds}
    lat_arr = lats
    lon_arr = lons

    out_mean = np.full((n_t, n_lat, n_lon, 5), np.nan, dtype=np.float32)
    out_std  = np.full((n_t, n_lat, n_lon, 5), np.nan, dtype=np.float32)

    half = PATCH_SIZE // 2
    batch_size = 256

    for t in tqdm(range(LOOKBACK, n_t), desc="Time steps"):
        xs, ys, patches = [], [], []
        for i in range(half, n_lat - half, stride):
            for j in range(half, n_lon - half, stride):
                patch = np.stack(
                    [data_arr[v][t - LOOKBACK:t, i - half:i + half + 1, j - half:j + half + 1]
                     for v in FEATURE_VARS if v in data_arr],
                    axis=-1,
                ).astype(np.float32)

                # Skip only if the satellite bands (first 5: NO2,SO2,CO,O3,HCHO) are
                # mostly missing. ERA5 met fields may be absent (all-NaN) until the
                # CDS download lands; the scaler imputes those to 0, matching training.
                sat_patch = patch[..., :5]
                if np.isnan(sat_patch).mean() > 0.6:
                    continue

                T, P1, P2, _ = patch.shape
                lat_n = np.full((T, P1, P2, 1), (lat_arr[i] - 8) / 29, dtype=np.float32)
                lon_n = np.full((T, P1, P2, 1), (lon_arr[j] - 68) / 29, dtype=np.float32)
                doy_s = np.full((T, P1, P2, 1),
                                np.sin(2 * np.pi * times[t].day_of_year / 365), dtype=np.float32)
                patch = np.concatenate([patch, lat_n, lon_n, doy_s], axis=-1)
                np.nan_to_num(patch, copy=False, nan=0.0)

                flat = patch.reshape(-1, N_FEATURES)
                flat = scaler.transform(flat).astype(np.float32)
                patch = flat.reshape(T, P1, P2, N_FEATURES)

                xs.append(i)
                ys.append(j)
                patches.append(patch)

        if not patches:
            continue

        # Batch inference
        for b_start in range(0, len(patches), batch_size):
            batch = torch.tensor(np.stack(patches[b_start:b_start + batch_size])).to(device)
            with torch.no_grad():
                mean, std = model.predict_mc(batch, n_passes=n_passes)
            mean = mean.cpu().numpy()
            std  = std.cpu().numpy()
            for k, (i, j) in enumerate(zip(xs[b_start:b_start + batch_size],
                                           ys[b_start:b_start + batch_size])):
                out_mean[t, i, j] = mean[k]
                out_std[t, i, j]  = std[k]

    # Write output Zarr
    coords = {"time": times, "lat": lats, "lon": lons}
    ds_out = xr.Dataset(
        {f"{p}_mean": (["time", "lat", "lon"], out_mean[..., k])
         for k, p in enumerate(POLLUTANT_NAMES)} |
        {f"{p}_std":  (["time", "lat", "lon"], out_std[..., k])
         for k, p in enumerate(POLLUTANT_NAMES)},
        coords=coords,
    )
    AQI_OUT.parent.mkdir(parents=True, exist_ok=True)
    ds_out.to_zarr(str(AQI_OUT), mode="w")
    print(f"Saved AQI predictions: {AQI_OUT}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--n-passes", type=int, default=10)
    args = parser.parse_args()
    predict_grid(n_passes=args.n_passes, stride=args.stride)
