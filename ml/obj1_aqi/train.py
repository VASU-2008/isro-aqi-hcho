"""
Training script for CNN-LSTM AQI model.
Designed to run on Google Colab (T4 GPU) — copy this file + dataset.py + model.py to Colab.
Usage:  python -m ml.obj1_aqi.train [--epochs 20] [--batch-size 64]
"""

import argparse
import json
import pickle
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from pathlib import Path
from sklearn.model_selection import GroupShuffleSplit

from ml.obj1_aqi.dataset import AQIDataset
from ml.obj1_aqi.model import build_model
from etl.config import MODELS_DIR


def train(
    epochs: int = 20,
    batch_size: int = 64,
    lr: float = 1e-3,
    device: str | None = None,
    hold_out_frac: float = 0.2,
):
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Device: {device}")

    # Build dataset with scaler fitted on training data
    dataset = AQIDataset(fit_scaler=True)
    dataset.save_scaler()
    print(f"Dataset: {len(dataset)} samples")

    # Leave-stations-out split
    stations = [s["station"] for s in dataset.samples]
    unique = list(set(stations))
    np.random.seed(42)
    np.random.shuffle(unique)
    n_val = max(1, int(len(unique) * hold_out_frac))
    val_stations = set(unique[:n_val])

    train_idx = [i for i, s in enumerate(dataset.samples) if s["station"] not in val_stations]
    val_idx   = [i for i, s in enumerate(dataset.samples) if s["station"] in val_stations]

    pin = device == "cuda"  # pin_memory unsupported on MPS
    train_loader = DataLoader(Subset(dataset, train_idx), batch_size=batch_size,
                              shuffle=True, num_workers=0, pin_memory=pin)
    val_loader   = DataLoader(Subset(dataset, val_idx),   batch_size=batch_size,
                              shuffle=False, num_workers=0, pin_memory=pin)
    print(f"Train: {len(train_idx)} | Val: {len(val_idx)}")

    model = build_model(n_outputs=5).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.HuberLoss(delta=25.0)  # AQI scale 0–500

    best_val_rmse = float("inf")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    best_path = MODELS_DIR / "cnn_lstm_best.pt"
    history = []

    for epoch in range(1, epochs + 1):
        # Train
        model.train()
        train_losses = []
        for X, y in train_loader:
            X, y = X.to(device), y.to(device)
            mask = y >= 0  # -1 flags missing targets
            if not mask.any():
                continue
            pred = model(X)
            loss = criterion(pred[mask], y[mask])
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_losses.append(loss.item())
        scheduler.step()

        # Validate
        model.eval()
        all_pred, all_true = [], []
        with torch.no_grad():
            for X, y in val_loader:
                X, y = X.to(device), y.to(device)
                pred = model(X)
                all_pred.append(pred.cpu())
                all_true.append(y.cpu())

        all_pred = torch.cat(all_pred).numpy()
        all_true = torch.cat(all_true).numpy()
        mask = all_true >= 0
        rmse = np.sqrt(np.mean((all_pred[mask] - all_true[mask]) ** 2))

        train_loss = np.mean(train_losses)
        history.append({"epoch": epoch, "train_loss": train_loss, "val_rmse": rmse})
        print(f"Epoch {epoch:03d} | train_loss={train_loss:.3f} | val_rmse={rmse:.2f}")

        if rmse < best_val_rmse:
            best_val_rmse = rmse
            torch.save(model.state_dict(), best_path)
            print(f"  Saved best model (RMSE={rmse:.2f})")

    # Save training history
    with open(MODELS_DIR / "train_history.json", "w") as f:
        json.dump([{k: float(v) for k, v in h.items()} for h in history], f, indent=2)
    print(f"\nBest val RMSE: {best_val_rmse:.2f}")
    print(f"Model saved: {best_path}")
    return model, history


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs",     type=int,   default=20)
    parser.add_argument("--batch-size", type=int,   default=64)
    parser.add_argument("--lr",         type=float, default=1e-3)
    parser.add_argument("--device",     type=str,   default=None)
    args = parser.parse_args()
    train(epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, device=args.device)
