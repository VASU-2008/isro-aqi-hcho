import pandas as pd
from etl.firms import aggregate_to_grid


def test_aggregate_empty():
    df = pd.DataFrame()
    result = aggregate_to_grid(df)
    assert result.empty


def test_aggregate_basic():
    df = pd.DataFrame({
        "lat": [28.12, 28.13, 29.55],
        "lon": [77.20, 77.21, 76.80],
        "frp": [10.0, 20.0, 5.0],
        "date": ["2022-10-15", "2022-10-15", "2022-10-15"],
    })
    result = aggregate_to_grid(df, resolution=0.05)
    assert not result.empty
    assert "frp_sum" in result.columns
    assert result["frp_sum"].sum() == pytest.approx(35.0, abs=0.1)


import pytest
