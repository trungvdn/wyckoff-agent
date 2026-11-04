"""Điểm vào duy nhất để lấy OHLCV: cache + cập nhật tăng dần + kiểm tra chất lượng."""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd

from wyckoff.config import DataConfig
from wyckoff.data.cache import cache_path, load_cache, save_cache
from wyckoff.data.fetcher import (
    OHLCVSource,
    RateLimitError,
    check_adjustment,
    covers,
    drop_incomplete_today,
    normalize_ohlcv,
    validate_ohlcv,
    vnstock_source,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _fmt(d: date | pd.Timestamp) -> str:
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def with_rate_limit_retry(
    fn: Callable[[], T], *, retries: int = 3, wait_s: float = 65.0,
    sleep: Callable[[float], None] = time.sleep, on_wait: Callable[[int, float, Exception], None] | None = None,
) -> T:
    """Gọi `fn`; nếu hết hạn mức theo phút (RateLimitError) thì chờ `wait_s` giây rồi thử lại, tối đa `retries` lần.
    QuotaExhaustedError (hết hạn mức ngày/tháng) và lỗi khác được ném ra ngay."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except RateLimitError as exc:
            if attempt == retries:
                raise
            if on_wait:
                on_wait(attempt + 1, wait_s, exc)
            sleep(wait_s)
    raise AssertionError("unreachable")


def warmup_start(start: str, warmup_bars: int) -> str:
    """Ngày bắt đầu tải để có thêm ~`warmup_bars` phiên trước `start` (x1.6 bù cuối tuần, lễ)."""
    return _fmt(pd.Timestamp(start) - timedelta(days=int(warmup_bars * 1.6) + 1))


def _overlap_matches(old: pd.DataFrame, new: pd.DataFrame, tol: float) -> bool:
    common = old.index.intersection(new.index)
    if len(common) == 0:
        return False
    diff = (old.loc[common, "close"] / new.loc[common, "close"] - 1).abs()
    return bool((diff <= tol).all())


def get_ohlcv(
    symbol: str,
    start: str,
    end: str | None = None,
    *,
    cache_dir: str | Path = "cache",
    source_fn: OHLCVSource | None = None,
    cfg: DataConfig | None = None,
    refresh: bool = False,
    now: datetime | None = None,
    check_limits: bool = True,
) -> pd.DataFrame:
    """Trả về OHLCV ngày (đã điều chỉnh) của `symbol` trong [start, end].

    - Cache toàn bộ lịch sử ở `<cache_dir>/<SYMBOL>_1D.csv`.
    - Lần sau chỉ tải từ (ngày cuối cache - overlap_days). Nếu close vùng chồng lấn lệch
      (có sự kiện quyền mới làm giá lịch sử bị điều chỉnh lại) thì tải lại toàn bộ.
    - `check_limits=False` cho chỉ số (không có biên độ trần/sàn).
    """
    cfg = cfg or DataConfig()
    source_fn = source_fn or vnstock_source(
        cfg.source, cfg.fallback_sources, cfg.chunk_days, cfg.coverage_tolerance_days
    )
    symbol = symbol.upper()
    end = end or _fmt(date.today())
    path = cache_path(cache_dir, symbol)
    cached = None if refresh else load_cache(path)

    def full_fetch() -> pd.DataFrame:
        logger.info("Tải toàn bộ %s %s -> %s", symbol, start, end)
        return normalize_ohlcv(source_fn(symbol, start, end))

    # Cache phủ từ start (dung sai coverage_tolerance_days: start có thể rơi vào cuối tuần / lễ)
    if cached is None or cached.empty or not covers(cached, start, cfg.coverage_tolerance_days):
        data = full_fetch()
    elif cached.index[-1] >= pd.Timestamp(end):
        data = cached
    else:
        inc_start = _fmt(cached.index[-1] - timedelta(days=cfg.overlap_days))
        logger.info("Cập nhật %s %s -> %s", symbol, inc_start, end)
        new = normalize_ohlcv(source_fn(symbol, inc_start, end))
        if _overlap_matches(cached, new, cfg.adjust_check_tolerance):
            data = pd.concat([cached[cached.index < new.index[0]], new])
        else:
            logger.warning("Giá vùng chồng lấn của %s đã thay đổi (sự kiện quyền?) -> tải lại toàn bộ", symbol)
            data = full_fetch()

    data = data[~data.index.duplicated(keep="last")].sort_index()
    data = drop_incomplete_today(data, now=now, close_hour=cfg.market_close_hour, tz=cfg.timezone)
    save_cache(data, path)

    for issue in validate_ohlcv(data):
        logger.warning("%s: %s", symbol, issue)
    violations = check_adjustment(data, cfg.price_limit, cfg.limit_tolerance) if check_limits else data.iloc[:0]
    if not violations.empty:
        logger.warning(
            "%s: %d phiên biến động vượt biên độ %.0f%% -> có thể giá CHƯA điều chỉnh: %s",
            symbol, len(violations), cfg.price_limit * 100,
            ", ".join(violations.index.strftime("%Y-%m-%d")[:10]),
        )
    if not covers(data, start, cfg.coverage_tolerance_days):
        logger.warning(
            "%s: THIẾU LỊCH SỬ - yêu cầu từ %s nhưng dữ liệu chỉ bắt đầu %s (%d phiên). "
            "Các detector cần đủ bối cảnh; xem `python scripts/check_vnstock.py %s`.",
            symbol, start, data.index[0].date() if len(data) else None, len(data), symbol,
        )
    return data.loc[pd.Timestamp(start):pd.Timestamp(end)]
