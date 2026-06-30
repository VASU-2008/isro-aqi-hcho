import torch
from ml.obj1_aqi.model import build_model
from ml.obj1_aqi.dataset import N_FEATURES, LOOKBACK, PATCH_SIZE


def test_model_forward():
    model = build_model(n_outputs=5)
    model.eval()
    x = torch.randn(4, LOOKBACK, PATCH_SIZE, PATCH_SIZE, N_FEATURES)
    with torch.no_grad():
        out = model(x)
    assert out.shape == (4, 5)
    assert (out >= 0).all(), "AQI sub-index must be non-negative"


def test_mc_dropout():
    model = build_model(n_outputs=5)
    x = torch.randn(2, LOOKBACK, PATCH_SIZE, PATCH_SIZE, N_FEATURES)
    mean, std = model.predict_mc(x, n_passes=5)
    assert mean.shape == (2, 5)
    assert std.shape  == (2, 5)
    assert (std >= 0).all()
