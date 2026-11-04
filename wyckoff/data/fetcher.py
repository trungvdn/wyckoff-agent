"""Lấy dữ liệu OHLCV ngày từ vnstock và chuẩn hóa.

vnstock 5.x: `Quote(symbol, source).history(start, end, interval)` chuyển tiếp tới
`Market().equity(symbol).ohlcv(...)`. Phần lõi (`_core.pyd`, đã biên dịch) có thể trả về
ít lịch sử hơn yêu cầu (tuỳ cấp tài khoản / nguồn). Vì vậy `vnstock_source` thử lần lượt
nhiều chiến lược và chọn kết quả đầu tiên phủ đủ khoảng ngày; nếu không có, trả về kết
quả phủ xa nhất kèm cảnh báo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

# (symbol, start 'YYYY-MM-DD', end 'YYYY-MM-DD') -> DataFrame thô
OHLCVSource = Callable[[str, str, str], pd.DataFrame]

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
_DATE_ALIASES = ("time", "date", "tradingdate", "trading_date", "datetime")


# ------------------------------------------------------------------ chuẩn hóa

def normalize_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    """Chuẩn về index `date` (tz-naive, chuẩn hóa về 00:00) + cột open/high/low/close/volume."""
    df = raw.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if df.index.name and str(df.index.name).lower() in _DATE_ALIASES:
        df = df.reset_index()
        df.columns = [str(c).strip().lower() for c in df.columns]
    date_col = next((c for c in _DATE_ALIASES if c in df.columns), None)
    if date_col is None:
        raise ValueError(f"Không tìm thấy cột ngày trong {list(df.columns)}")
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Thiếu cột {missing}")
    dates = pd.to_datetime(df[date_col])
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    out = df[OHLCV_COLUMNS].astype(float)
    out.index = pd.DatetimeIndex(dates.dt.normalize(), name="date")
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def covers(df: pd.DataFrame, start: str, tolerance_days: int = 15) -> bool:
    """Dữ liệu có bắt đầu không muộn hơn `start` + tolerance_days (bù nghỉ Tết, lễ)?"""
    return len(df) > 0 and df.index[0] <= pd.Timestamp(start) + pd.Timedelta(days=tolerance_days)


# ------------------------------------------------------------ giới hạn lượt gọi

class RateLimitError(RuntimeError):
    """Hết hạn mức lượt gọi theo phút: chờ rồi thử lại sẽ được."""


class QuotaExhaustedError(RuntimeError):
    """Hết hạn mức theo ngày / tháng: chờ vài phút không giúp được."""


def classify_quota_error(exc: Exception) -> type[RuntimeError] | None:
    msg = str(exc).lower()
    if "hạn mức" in msg or "quota" in msg or "rate limit" in msg or "too many requests" in msg or " 429" in msg:
        if any(k in msg for k in ("theo ngày", "theo tháng", "per day", "per month", "daily", "monthly")):
            return QuotaExhaustedError
        return RateLimitError
    return None


# ------------------------------------------------------------ chiến lược tải

@dataclass(frozen=True)
class Strategy:
    name: str
    fetch: OHLCVSource


def fetch_with_fallback(
    symbol: str, start: str, end: str, strategies: list[Strategy], tolerance_days: int = 15
) -> pd.DataFrame:
    """Thử từng chiến lược; trả về kết quả đầu tiên phủ đủ, nếu không thì kết quả phủ xa nhất."""
    best: tuple[str, pd.DataFrame] | None = None
    errors: list[str] = []
    for st in strategies:
        try:
            df = normalize_ohlcv(st.fetch(symbol, start, end))
        except Exception as exc:  # noqa: BLE001 - ghi lại rồi thử chiến lược kế tiếp
            quota = classify_quota_error(exc)
            if quota is not None:   # các chiến lược khác cũng sẽ bị chặn và tốn thêm lượt gọi -> dừng ngay
                raise quota(f"{symbol}: {type(exc).__name__}: {str(exc).splitlines()[0]}") from exc
            errors.append(f"{st.name}: {type(exc).__name__}: {exc}")
            logger.info("Chiến lược '%s' lỗi: %s", st.name, exc)
            continue
        if df.empty:
            errors.append(f"{st.name}: rỗng")
            continue
        logger.info("Chiến lược '%s': %d phiên, %s -> %s", st.name, len(df), df.index[0].date(), df.index[-1].date())
        if covers(df, start, tolerance_days):
            return df
        if best is None or df.index[0] < best[1].index[0]:
            best = (st.name, df)
    if best is None:
        raise RuntimeError(f"Không lấy được dữ liệu {symbol}. " + " | ".join(errors))
    logger.warning(
        "%s: không chiến lược nào phủ từ %s; dùng '%s' (từ %s). Kiểm tra cấp tài khoản vnstock "
        "(`vnstock status`) và chạy `python scripts/check_vnstock.py %s`.",
        symbol, start, best[0], best[1].index[0].date(), symbol,
    )
    return best[1]


def _quote_history(source: str) -> OHLCVSource:
    def _fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
        try:
            from vnstock import Quote  # vnstock >= 3.2 (gồm 5.x)

            return Quote(symbol=symbol, source=source).history(start=start, end=end, interval="1D")
        except ImportError:
            from vnstock import Vnstock  # vnstock 3.0 - 3.1

            return Vnstock().stock(symbol=symbol, source=source).quote.history(start=start, end=end, interval="1D")

    return _fetch


def _market_ohlcv(source: str) -> OHLCVSource:
    """vnstock >= 4: gọi thẳng Market().equity().ohlcv với `limit` đủ lớn cho cả khoảng ngày."""

    def _fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
        from vnstock import Market

        bars = len(pd.bdate_range(start, end)) + 50
        return Market().equity(symbol).ohlcv(
            start=start, end=end, interval="1D", limit=bars, source=source.lower()
        )

    return _fetch


def chunked(fetch: OHLCVSource, chunk_days: int = 365, overlap_days: int = 7) -> OHLCVSource:
    """Tải theo từng đoạn `chunk_days` ngày (phòng khi nguồn giới hạn độ dài mỗi lần gọi)."""

    if chunk_days <= overlap_days:
        raise ValueError("chunk_days phải lớn hơn overlap_days")

    def _fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
        parts: list[pd.DataFrame] = []
        s, e_all = pd.Timestamp(start), pd.Timestamp(end)
        while s <= e_all:
            e = min(s + timedelta(days=chunk_days), e_all)
            raw = fetch(symbol, s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"))
            if raw is not None and len(raw):
                parts.append(normalize_ohlcv(raw))
            if e >= e_all:
                break
            s = e - timedelta(days=overlap_days)  # chồng lấn để kiểm tra giá nối giữa hai đoạn
        if not parts:
            return pd.DataFrame(columns=["time", *OHLCV_COLUMNS])
        for a, b in zip(parts, parts[1:]):
            common = a.index.intersection(b.index)
            if len(common) and ((a.loc[common, "close"] / b.loc[common, "close"] - 1).abs() > 1e-3).any():
                logger.warning("Giá ở vùng nối giữa hai đoạn không khớp (%s) -> kiểm tra điều chỉnh giá", common[0].date())
        out = pd.concat(parts)
        out = out[~out.index.duplicated(keep="last")].sort_index()
        return out.reset_index().rename(columns={"date": "time"})

    return _fetch


def vnstock_source(
    source: str = "VCI",
    fallback_sources: tuple[str, ...] = ("KBS",),
    chunk_days: int = 365,
    tolerance_days: int = 15,
) -> OHLCVSource:
    """Nguồn vnstock với chuỗi dự phòng (dừng ở chiến lược đầu tiên phủ đủ):
      1. Quote.history(start, end)                       — nguồn chính
      2. Market().equity().ohlcv(start, end, limit=N)    — nguồn chính, limit tường minh
      3. Quote.history chia đoạn theo năm               — nguồn chính
      4-6. như 1-3 với từng nguồn dự phòng
    Giá VCI/KBS tính bằng nghìn đồng và đã điều chỉnh; luôn chạy `check_adjustment` để tự kiểm tra.
    """
    strategies: list[Strategy] = []
    for src in (source, *[s for s in fallback_sources if s.upper() != source.upper()]):
        strategies += [
            Strategy(f"Quote.history[{src}]", _quote_history(src)),
            Strategy(f"Market.ohlcv(limit)[{src}]", _market_ohlcv(src)),
            Strategy(f"Quote.history chia đoạn {chunk_days} ngày[{src}]", chunked(_quote_history(src), chunk_days)),
        ]

    def _fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
        return fetch_with_fallback(symbol, start, end, strategies, tolerance_days)

    return _fetch


def _index_ohlcv(source: str) -> OHLCVSource:
    """vnstock >= 4: Market().index(symbol).ohlcv(...) cho chỉ số (VNINDEX, HNXINDEX, ...)."""

    def _fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
        from vnstock import Market

        bars = len(pd.bdate_range(start, end)) + 50
        return Market().index(symbol).ohlcv(start=start, end=end, interval="1D", limit=bars, source=source.lower())

    return _fetch


def vnstock_index_source(
    source: str = "KBS", chunk_days: int = 365, tolerance_days: int = 15
) -> OHLCVSource:
    """Nguồn dữ liệu chỉ số với chuỗi dự phòng:
      1. Market().index().ohlcv(start, end, limit=N)  — nguồn `source` (mặc định KBS)
      2. Quote(symbol, VCI).history(start, end)
      3. Market().index().ohlcv chia đoạn 365 ngày
    """
    strategies = [
        Strategy(f"Market.index.ohlcv[{source}]", _index_ohlcv(source)),
        Strategy("Quote.history[VCI]", _quote_history("VCI")),
        Strategy(f"Market.index.ohlcv chia đoạn {chunk_days} ngày[{source}]", chunked(_index_ohlcv(source), chunk_days)),
    ]

    def _fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
        return fetch_with_fallback(symbol, start, end, strategies, tolerance_days)

    return _fetch


# ------------------------------------------------------------ kiểm tra dữ liệu

def validate_ohlcv(df: pd.DataFrame) -> list[str]:
    """Trả về danh sách cảnh báo chất lượng dữ liệu (không sửa dữ liệu)."""
    issues: list[str] = []
    if df[OHLCV_COLUMNS].isna().any().any():
        issues.append(f"Có {int(df[OHLCV_COLUMNS].isna().any(axis=1).sum())} phiên chứa NaN")
    bad_hl = df["high"] < df["low"]
    if bad_hl.any():
        issues.append(f"high < low ở {list(df.index[bad_hl].strftime('%Y-%m-%d'))}")
    out_of_bar = (df["close"] > df["high"]) | (df["close"] < df["low"]) | (df["open"] > df["high"]) | (
        df["open"] < df["low"]
    )
    if out_of_bar.any():
        issues.append(f"open/close nằm ngoài [low, high] ở {int(out_of_bar.sum())} phiên")
    zero_vol = df["volume"] <= 0
    if zero_vol.any():
        issues.append(f"volume <= 0 ở {int(zero_vol.sum())} phiên")
    return issues


def check_adjustment(df: pd.DataFrame, price_limit: float = 0.07, tolerance: float = 0.005) -> pd.DataFrame:
    """Phát hiện dấu hiệu giá CHƯA điều chỉnh.

    Trên HOSE, |close_t / close_{t-1} - 1| không thể vượt biên độ 7% (giá tham chiếu = close
    phiên trước). Chuỗi đã điều chỉnh giữ nguyên tỉ lệ này. Vi phạm thường là ngày GDKHQ
    chưa được điều chỉnh (hoặc phiên đầu sau khi tạm ngừng giao dịch).
    """
    change = df["close"].pct_change()
    mask = change.abs() > price_limit + tolerance
    return pd.DataFrame({"prev_close": df["close"].shift(1)[mask], "close": df["close"][mask], "change": change[mask]})


def drop_incomplete_today(
    df: pd.DataFrame, now: datetime | None = None, close_hour: int = 15, tz: str = "Asia/Ho_Chi_Minh"
) -> pd.DataFrame:
    """Bỏ nến của ngày hôm nay nếu phiên chưa đóng cửa (tránh dùng nến dang dở)."""
    now = now or datetime.now(ZoneInfo(tz))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo(tz))
    now = now.astimezone(ZoneInfo(tz))
    today = pd.Timestamp(now.date())
    if now.hour < close_hour and len(df) and df.index[-1] >= today:
        logger.info("Bỏ nến %s vì phiên chưa kết thúc", today.date())
        return df[df.index < today]
    return df
