"""Dịch vụ dùng chung cho CLI và web: tải dữ liệu theo khung thời gian, phân tích, bối cảnh thị trường."""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

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


CACHE_SUFFIX = "_1D.csv"


def index_symbols(cfg: Config) -> set[str]:
    return set(cfg.market.benchmarks.values())


def is_index(symbol: str, cfg: Config) -> bool:
    # VNSMALLCAP nằm trong cache từ kiểm định H1, không thuộc danh sách chỉ số so sánh
    return symbol in index_symbols(cfg) or symbol == "VNSMALLCAP"


def cached_symbols(cache_dir: str | Path) -> list[str]:
    """Mọi mã (kể cả chỉ số) đang có file nến ngày trong cache."""
    return sorted(p.name[: -len(CACHE_SUFFIX)] for p in Path(cache_dir).glob(f"*{CACHE_SUFFIX}"))


def update_symbol(symbol: str, cfg: Config, *, cache_dir: str | Path = "cache",
                  on_wait: Callable[[int, float, Exception], None] | None = None) -> None:
    """Cập nhật tăng dần nến ngày của một mã vào cache; hết hạn mức theo phút thì chờ rồi thử lại."""
    from wyckoff.data.cache import cache_path, load_cache
    from wyckoff.data.fetcher import vnstock_index_source
    from wyckoff.data.loader import with_rate_limit_retry

    cached = load_cache(cache_path(Path(cache_dir), symbol))
    # Giữ nguyên độ phủ đang có để không tải lại toàn bộ lịch sử
    start = (f"{cached.index[0]:%Y-%m-%d}" if cached is not None and not cached.empty
             else warmup_start(DEFAULT_START["1D"], cfg.data.warmup_bars))
    kw: dict[str, Any] = {}
    if is_index(symbol, cfg):
        kw = {"check_limits": False, "source_fn": vnstock_index_source(
            cfg.market.index_source, cfg.data.chunk_days, cfg.data.coverage_tolerance_days)}
    with_rate_limit_retry(lambda: get_ohlcv(symbol, start, cache_dir=Path(cache_dir), cfg=cfg.data, **kw), on_wait=on_wait)


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
    ind = cfg.indicators
    return {"symbol": bench, **market_overview(idx, cfg.market, ind.vol_ma_period, (ind.ema_fast, ind.ema_slow))}


def prepare_index(cfg: Config, *, start: str, cache_dir: str = "cache") -> tuple[pd.DataFrame, AnalysisResult, str]:
    """Chỉ số so sánh đã phân tích, để dùng lại cho nhiều mã (job quét thị trường)."""
    from wyckoff.market import benchmark_for

    bench = benchmark_for(cfg.data.exchange, cfg.market)
    idx = load_index(bench, cfg, start=start, cache_dir=cache_dir)
    return idx, analyze(idx, cfg), bench


def load_market(result: AnalysisResult, symbol: str, cfg: Config, *, start: str, end: str | None = None,
                cache_dir: str = "cache", refresh: bool = False, demo: bool = False,
                index: tuple[pd.DataFrame, AnalysisResult, str] | None = None):
    """Tải chỉ số so sánh, chạy detector trên chỉ số, dựng bối cảnh thị trường. Lỗi -> (None, None, None).
    `index`: kết quả của `prepare_index` khi đã có sẵn."""
    from wyckoff.agent.payload import current_structure_events
    from wyckoff.market import benchmark_for, build_market_context

    try:
        if index is not None:
            idx, idx_res, bench = index
        else:
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
