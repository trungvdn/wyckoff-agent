from __future__ import annotations

import numpy as np
import pandas as pd

from wyckoff.config import IndicatorConfig, SwingConfig
from wyckoff.detectors.swings import find_swings
from wyckoff.indicators.core import add_indicators, close_position, wilder_atr


def _df(rows: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                        index=pd.bdate_range("2024-01-01", periods=len(rows)))


def test_close_position_bounds_and_flat_bar() -> None:
    df = _df([(1, 2, 0, 2, 1), (1, 2, 0, 0, 1), (1, 1, 1, 1, 1)])
    assert close_position(df).tolist() == [1.0, 0.0, 0.5]


def test_wilder_atr_constant_range() -> None:
    df = _df([(10, 11, 9, 10, 1)] * 30)
    atr = wilder_atr(df, 14)
    assert atr.iloc[:13].isna().all()
    assert np.allclose(atr.iloc[13:], 2.0)


def test_vol_ma_excludes_current_bar() -> None:
    rows = [(10, 11, 9, 10, 100)] * 20 + [(10, 11, 9, 10, 1000)]
    out = add_indicators(_df(rows), IndicatorConfig(vol_ma_period=20))
    assert out["vol_ma"].iloc[-1] == 100
    assert out["vol_ratio"].iloc[-1] == 10


def test_swing_confirmation_delay() -> None:
    highs = [1, 2, 3, 4, 5, 9, 5, 4, 3, 2, 1, 1]
    df = _df([(h - 0.5, h, h - 1, h - 0.5, 1) for h in highs])
    sw = [s for s in find_swings(df, SwingConfig(left=5, right=5)) if s.kind == "high"]
    assert len(sw) == 1 and sw[0].idx == 5 and sw[0].confirmed_idx == 10 and sw[0].price == 9


def test_swings_need_right_window() -> None:
    highs = [1, 2, 3, 4, 5, 9, 5, 4]  # chưa đủ 5 phiên bên phải
    df = _df([(h - 0.5, h, h - 1, h - 0.5, 1) for h in highs])
    assert not [s for s in find_swings(df) if s.kind == "high"]
