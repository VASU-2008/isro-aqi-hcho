"""
CNN-LSTM model for surface AQI prediction.
Architecture: spatial CNN encoder per timestep → LSTM → MC-Dropout dense head → AQI sub-index
"""

import torch
import torch.nn as nn
from ml.obj1_aqi.dataset import N_FEATURES, LOOKBACK, PATCH_SIZE


class CNNEncoder(nn.Module):
    """Extracts spatial texture from a 3×3 patch for one timestep."""

    def __init__(self, in_channels: int = N_FEATURES, out_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.GELU(),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.GELU(),
            nn.AdaptiveAvgPool2d(1),   # → (B, 64, 1, 1)
            nn.Flatten(),              # → (B, 64)
            nn.Linear(64, out_dim),
            nn.GELU(),
        )

    def forward(self, x):
        return self.net(x)


class CNNLSTM(nn.Module):
    """
    Full CNN-LSTM model.

    Input shape:  (batch, time, patch_h, patch_w, features)
    Output shape: (batch, n_outputs) — AQI sub-index per pollutant
    """

    def __init__(
        self,
        n_outputs: int = 5,           # PM2.5, NO2, SO2, CO, O3
        cnn_out_dim: int = 128,
        lstm_hidden: int = 256,
        lstm_layers: int = 2,
        lstm_dropout: float = 0.3,
        fc_dropout: float = 0.2,
    ):
        super().__init__()
        self.encoder = CNNEncoder(in_channels=N_FEATURES, out_dim=cnn_out_dim)
        self.lstm = nn.LSTM(
            input_size=cnn_out_dim,
            hidden_size=lstm_hidden,
            num_layers=lstm_layers,
            batch_first=True,
            dropout=lstm_dropout if lstm_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Dropout(fc_dropout),
            nn.Linear(lstm_hidden, 256),
            nn.GELU(),
            nn.Dropout(fc_dropout),
            nn.Linear(256, n_outputs),
            nn.ReLU(),   # AQI sub-index ≥ 0
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T, H, W, C = x.shape
        # Encode each timestep independently
        x = x.reshape(B * T, H, W, C).permute(0, 3, 1, 2).contiguous()  # (B*T, C, H, W)
        enc = self.encoder(x)                              # (B*T, cnn_out_dim)
        enc = enc.view(B, T, -1)                          # (B, T, cnn_out_dim)
        lstm_out, _ = self.lstm(enc)                      # (B, T, lstm_hidden)
        return self.head(lstm_out[:, -1, :])               # (B, n_outputs)

    def predict_mc(self, x: torch.Tensor, n_passes: int = 10) -> tuple:
        """MC-Dropout inference: return (mean, std) over n_passes forward passes."""
        self.train()  # keep dropout active
        with torch.no_grad():
            preds = torch.stack([self(x) for _ in range(n_passes)], dim=0)
        self.eval()
        return preds.mean(0), preds.std(0)


def build_model(n_outputs: int = 5, **kwargs) -> CNNLSTM:
    return CNNLSTM(n_outputs=n_outputs, **kwargs)
