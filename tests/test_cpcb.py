import pandas as pd
import numpy as np
from etl.cpcb import concentration_to_aqi


def test_aqi_good():
    assert concentration_to_aqi(15, "PM2.5") == pytest.approx(25.0, abs=1.0)

def test_aqi_moderate():
    val = concentration_to_aqi(75, "PM2.5")
    assert 101 <= val <= 200

def test_aqi_nan():
    assert np.isnan(concentration_to_aqi(np.nan, "PM2.5"))

def test_aqi_unknown_pollutant():
    assert np.isnan(concentration_to_aqi(10, "UNKNOWN"))

import pytest
