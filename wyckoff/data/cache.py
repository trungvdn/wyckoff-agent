"""Đọc/ghi cache CSV."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from wyckoff.data.fetcher import OHLCV_COLUMNS


def cache_path(cache_dir: str | Path, symbol: str, interval: str = "1D") -> Path:
    return Path(cache_dir) / f"{symbol.upper()}_{interval}.csv"


def load_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return df[OHLCV_COLUMNS].astype(float).sort_index()


def save_cache(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df[OHLCV_COLUMNS].to_csv(tmp, index_label="date", date_format="%Y-%m-%d")
    tmp.replace(path)
