from __future__ import annotations

import pandas as pd
import pytest

from wyckoff.pipeline import analyze

pytest.importorskip("plotly")


def test_chart_html(ohlcv: pd.DataFrame, tmp_path) -> None:
    from wyckoff.charts.plot import build_figure, save_html

    fig = build_figure(analyze(ohlcv), "DEMO", show_swings=True)
    names = {t.name for t in fig.data}
    assert {"SC", "Spring", "SOS"} <= names
    path = save_html(fig, tmp_path / "demo.html")
    assert path.stat().st_size > 1000
