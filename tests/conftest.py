from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.indicators.core import add_indicators  # noqa: E402
from wyckoff.synthetic import make_wyckoff_accumulation  # noqa: E402


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    return make_wyckoff_accumulation()


@pytest.fixture
def ind(ohlcv: pd.DataFrame) -> pd.DataFrame:
    return add_indicators(ohlcv)
