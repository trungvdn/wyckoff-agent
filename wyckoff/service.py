"""Dịch vụ dùng chung cho CLI và web: tải dữ liệu theo khung thời gian, phân tích, bối cảnh thị trường."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pandas as pd

from wyckoff.config import Config
from wyckoff.data.loader import get_ohlcv, warmup_start
from wyckoff.pipeline import AnalysisResult, analyze
from wyckoff.synthetic import make_wyckoff_accumulation

logger = logging.getLogger(__name__)

DEMO_SYMBOL = "DEMO"
# Khung ngày là khung gốc (ngưỡng hiệu chỉnh theo backtest); khung tuần dựng lại từ dữ liệu ngày.
# Khung trong ngày (15 phút, giờ) chưa hỗ trợ: chưa có dữ liệu cache và ngưỡng hiệu chỉnh.
TIMEFRAMES = ("1D", "1W")
DEFAULT_START = {"1D": "2020-01-01", "1W": "2018-01-01"}
WEEKLY_WARMUP_DAYS = 420          # ~60 tuần khởi động chỉ báo cho khung tuần


class DataUnavailable(RuntimeError):
    """Không tải được hoặc không có dữ liệu cho mã. `status`: mã HTTP gợi ý cho lớp web."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def resample_weekly(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Gộp nến ngày thành nến tuần (thứ 2 – thứ 6); nhãn = phiên giao dịch cuối của tuần."""
    if ohlcv.empty:
        return ohlcv
    week = ohlcv.index.to_period("W-FRI")
    g = ohlcv.groupby(week)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
    })
    out.index = pd.DatetimeIndex(ohlcv.index.to_series().groupby(week).max().values, name=ohlcv.index.name)
    return out


def load_ohlcv(symbol: str, tf: str, cfg: Config, *, start: str | None = None, end: str | None = None,
               cache_dir: str = "cache", refresh: bool = False) -> pd.DataFrame:
    """OHLCV của `symbol` ở khung `tf`, gồm cả phần khởi động chỉ báo trước `start`."""
    if tf not in TIMEFRAMES:
        raise ValueError(f"Khung thời gian không hỗ trợ: {tf}")
    start = start or DEFAULT_START[tf]
    if symbol == DEMO_SYMBOL:
        daily = make_wyckoff_accumulation()
    else:
        fetch_from = (warmup_start(start, cfg.data.warmup_bars) if tf == "1D"
                      else f"{pd.Timestamp(start) - timedelta(days=WEEKLY_WARMUP_DAYS):%Y-%m-%d}")
        try:
            daily = get_ohlcv(symbol, fetch_from, end, cache_dir=cache_dir, cfg=cfg.data, refresh=refresh)
        except Exception as exc:  # noqa: BLE001 - lỗi nguồn dữ liệu (mạng, hạn mức, mã sai)
            # Chi tiết (từng nguồn / cách gọi vnstock) chỉ ghi log; người dùng nhận thông báo ngắn
            logger.warning("Không tải được dữ liệu %s: %s", symbol, exc)
            if cfg.data.offline:
                raise DataUnavailable(f"Mã {symbol} chưa có trong dữ liệu đã đồng bộ lên máy chủ.", status=404) from exc
            if "không có mã" in str(exc).lower():
                raise DataUnavailable(f"Không tìm thấy mã {symbol} trên các nguồn dữ liệu. Kiểm tra lại mã cổ phiếu.",
                                      status=404) from exc
            raise DataUnavailable(f"Không tải được dữ liệu {symbol} từ nguồn vnstock (mạng hoặc hạn mức lượt gọi). "
                                  "Thử lại sau ít phút.") from exc
    if daily.empty:
        raise DataUnavailable(f"Không có dữ liệu cho mã {symbol}", status=404)
    return daily if tf == "1D" else resample_weekly(daily)


def run_analysis(symbol: str, tf: str, cfg: Config, **kw: Any) -> AnalysisResult:
    """Phân tích trên toàn bộ dữ liệu đã tải (vị trí `idx` của sự kiện khớp với `result.df`)."""
    ohlcv = load_ohlcv(symbol, tf, cfg, **kw)
    min_bars = cfg.indicators.sma_period + cfg.swings.left + cfg.swings.right
    if len(ohlcv) < min_bars:
        raise DataUnavailable(f"{symbol}: chỉ có {len(ohlcv)} nến ở khung {tf}, cần ít nhất {min_bars}", status=422)
    return analyze(ohlcv, cfg)


def load_index(bench: str, cfg: Config, *, start: str, end: str | None = None, cache_dir: str = "cache",
               refresh: bool = False) -> pd.DataFrame:
    """OHLCV ngày của chỉ số `bench`, gồm phần khởi động đủ cho SMA dài."""
    from wyckoff.data.fetcher import vnstock_index_source

    src = vnstock_index_source(cfg.market.index_source, cfg.data.chunk_days, cfg.data.coverage_tolerance_days)
    return get_ohlcv(bench, warmup_start(start, max(cfg.data.warmup_bars, cfg.market.sma_slow)), end,
                     cache_dir=cache_dir, source_fn=src, cfg=cfg.data, refresh=refresh, check_limits=False)


def load_market_overview(cfg: Config, *, cache_dir: str = "cache", refresh: bool = False) -> dict[str, Any]:
    """Số liệu trang thị trường của chỉ số theo sàn cấu hình (HOSE -> VNINDEX)."""
    from wyckoff.market import benchmark_for, market_overview

    bench = benchmark_for(cfg.data.exchange, cfg.market)
    try:
        idx = load_index(bench, cfg, start=DEFAULT_START["1D"], cache_dir=cache_dir, refresh=refresh)
    except Exception as exc:  # noqa: BLE001 - lỗi nguồn dữ liệu (mạng, hạn mức); chi tiết chỉ ghi log
        logger.warning("Không tải được dữ liệu %s: %s", bench, exc)
        if cfg.data.offline:
            raise DataUnavailable(f"Chỉ số {bench} chưa có trong dữ liệu đã đồng bộ lên máy chủ.", status=404) from exc
        raise DataUnavailable(f"Không tải được dữ liệu {bench} từ nguồn vnstock (mạng hoặc hạn mức lượt gọi). "
                              "Thử lại sau ít phút.") from exc
    if idx.empty:
        raise DataUnavailable(f"Không có dữ liệu cho chỉ số {bench}", status=404)
    return {"symbol": bench, **market_overview(idx, cfg.market, cfg.indicators.vol_ma_period)}


def load_market(result: AnalysisResult, symbol: str, cfg: Config, *, start: str, end: str | None = None,
                cache_dir: str = "cache", refresh: bool = False, demo: bool = False):
    """Tải chỉ số so sánh, chạy detector trên chỉ số, dựng bối cảnh thị trường. Lỗi -> (None, None, None)."""
    from wyckoff.agent.payload import current_structure_events
    from wyckoff.market import benchmark_for, build_market_context

    try:
        bench = benchmark_for(cfg.data.exchange, cfg.market)
        if demo:
            from wyckoff.synthetic import make_market_index

            idx = make_market_index(result.df.index)
        else:
            idx = load_index(bench, cfg, start=start, end=end, cache_dir=cache_dir, refresh=refresh)
        idx_res = analyze(idx, cfg)
        cur = idx_res.current()
        ref = {"phase": cur.phase, "since": None if cur.since is None else f"{cur.since:%Y-%m-%d}", "reason": cur.reason,
               "note": "tham khảo – ngưỡng detector chưa hiệu chỉnh cho chỉ số"}
        ctx = build_market_context(result.df, idx, bench, current_structure_events(result), cfg.market,
                                   idx_res.phases.series["phase"], ref)
        return ctx, idx, bench
    except Exception as exc:  # noqa: BLE001 - thiếu dữ liệu thị trường không chặn báo cáo
        logger.warning("Không dựng được bối cảnh thị trường: %s", exc)
        return None, None, None
