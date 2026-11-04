from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from wyckoff.data.cache import cache_path, load_cache
from wyckoff.data.fetcher import check_adjustment, drop_incomplete_today, normalize_ohlcv, validate_ohlcv
from wyckoff.data.loader import get_ohlcv

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _raw(start: str, periods: int, base: float = 20.0) -> pd.DataFrame:
    """Định dạng giống vnstock VCI: cột `time` + ohlcv."""
    dates = pd.bdate_range(start, periods=periods)
    close = [base + 0.1 * i for i in range(periods)]
    return pd.DataFrame({
        "time": dates, "open": close, "high": [c + 0.5 for c in close],
        "low": [c - 0.5 for c in close], "close": close, "volume": [1_000_000] * periods,
    })


class FakeSource:
    def __init__(self, full: pd.DataFrame) -> None:
        self.full = full
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        self.calls.append((symbol, start, end))
        t = pd.to_datetime(self.full["time"])
        return self.full[(t >= start) & (t <= end)].copy()


AFTER_CLOSE = datetime(2030, 1, 1, 16, 0, tzinfo=TZ)


def test_normalize_vnstock_format() -> None:
    raw = _raw("2024-01-01", 5).sample(frac=1, random_state=0)
    raw.columns = [c.upper() if c != "time" else c for c in raw.columns]
    out = normalize_ohlcv(raw)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out.index.name == "date" and out.index.is_monotonic_increasing


def test_normalize_requires_columns() -> None:
    with pytest.raises(ValueError):
        normalize_ohlcv(pd.DataFrame({"time": ["2024-01-01"], "close": [1.0]}))


def test_check_adjustment_flags_unadjusted_ex_right_gap() -> None:
    df = normalize_ohlcv(_raw("2024-01-01", 10))
    df.iloc[5:, :4] = df.iloc[5:, :4] * 0.75  # giảm 25% ngày GDKHQ chưa điều chỉnh
    v = check_adjustment(df, 0.07)
    assert list(v.index) == [df.index[5]]
    assert check_adjustment(normalize_ohlcv(_raw("2024-01-01", 10)), 0.07).empty


def test_validate_reports_bad_bar() -> None:
    df = normalize_ohlcv(_raw("2024-01-01", 5))
    df.iloc[2, df.columns.get_loc("high")] = 0
    assert validate_ohlcv(df)


def test_drop_incomplete_today() -> None:
    df = normalize_ohlcv(_raw("2026-11-02", 2))  # 2/11 và 3/11
    morning = datetime(2026, 11, 3, 10, 30, tzinfo=TZ)
    evening = datetime(2026, 11, 3, 15, 5, tzinfo=TZ)
    assert drop_incomplete_today(df, morning).index[-1] == pd.Timestamp("2026-11-02")
    assert drop_incomplete_today(df, evening).index[-1] == pd.Timestamp("2026-11-03")


def test_cache_full_then_incremental(tmp_path) -> None:
    full = _raw("2024-01-01", 60)
    src = FakeSource(full)
    a = get_ohlcv("hpg", "2024-01-01", "2024-02-15", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    assert cache_path(tmp_path, "HPG").exists() and len(src.calls) == 1
    b = get_ohlcv("HPG", "2024-01-01", "2024-03-22", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    assert len(src.calls) == 2 and src.calls[1][1] > "2024-02-01"   # chỉ tải phần mới
    assert len(b) == 60 and b.index[: len(a)].equals(a.index)
    pd.testing.assert_frame_equal(load_cache(cache_path(tmp_path, "HPG")), b, check_freq=False)


def test_cache_hit_no_fetch(tmp_path) -> None:
    src = FakeSource(_raw("2024-01-01", 30))
    get_ohlcv("HPG", "2024-01-01", "2024-02-09", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    get_ohlcv("HPG", "2024-01-05", "2024-01-31", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    assert len(src.calls) == 1


def test_cache_refetch_when_history_readjusted(tmp_path) -> None:
    src = FakeSource(_raw("2024-01-01", 40))
    get_ohlcv("HPG", "2024-01-01", "2024-01-31", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    adjusted = _raw("2024-01-01", 60)
    adjusted.loc[:, ["open", "high", "low", "close"]] *= 0.9  # chia cổ tức -> lịch sử bị điều chỉnh
    src.full = adjusted
    out = get_ohlcv("HPG", "2024-01-01", "2024-03-22", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    assert src.calls[-1][1] == "2024-01-01"  # tải lại toàn bộ
    assert out["close"].iloc[0] == pytest.approx(18.0)


# ---------------------------------------------------------- fallback vnstock 5.x

from wyckoff.data.fetcher import Strategy, chunked, covers, fetch_with_fallback  # noqa: E402


def _capped(full: pd.DataFrame, days: int):
    """Nguồn giả: mỗi lần gọi chỉ trả về tối đa `days` ngày gần `end` nhất (giống lỗi 1 năm)."""
    def _f(symbol: str, start: str, end: str) -> pd.DataFrame:
        t = pd.to_datetime(full["time"])
        lo = max(pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(days=days))
        return full[(t >= lo) & (t <= end)].copy()
    return _f


def test_covers_tolerance() -> None:
    df = normalize_ohlcv(_raw("2020-01-10", 5))
    assert covers(df, "2020-01-01", 15) and not covers(df, "2020-01-01", 5)


def test_fallback_picks_first_full_coverage() -> None:
    full = _raw("2020-01-01", 900)
    calls: list[str] = []

    def named(name, fn):
        def _f(*a):
            calls.append(name)
            return fn(*a)
        return Strategy(name, _f)

    strategies = [
        named("capped", _capped(full, 365)),
        named("chunked", chunked(_capped(full, 365), 365)),
        named("never", _capped(full, 10)),
    ]
    out = fetch_with_fallback("HPG", "2020-01-01", "2023-06-30", strategies)
    assert calls == ["capped", "chunked"]
    assert out.index[0] == pd.Timestamp("2020-01-01") and len(out) == 900
    assert out.index.is_unique


def test_fallback_returns_best_when_none_covers(caplog) -> None:
    full = _raw("2020-01-01", 900)
    strategies = [Strategy("a", _capped(full, 100)), Strategy("b", _capped(full, 300))]

    def boom(*_):
        raise RuntimeError("network")

    out = fetch_with_fallback("HPG", "2020-01-01", "2023-06-30", [Strategy("err", boom), *strategies])
    assert len(out) == len(normalize_ohlcv(_capped(full, 300)("HPG", "2020-01-01", "2023-06-30")))
    assert "không chiến lược nào phủ" in caplog.text


def test_fallback_raises_when_all_fail() -> None:
    def boom(*_):
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        fetch_with_fallback("HPG", "2020-01-01", "2021-01-01", [Strategy("a", boom)])


def test_loader_warns_on_short_history(tmp_path, caplog) -> None:
    src = FakeSource(_raw("2024-06-03", 30))
    get_ohlcv("HPG", "2020-01-01", "2024-07-12", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    assert "THIẾU LỊCH SỬ" in caplog.text


def test_cache_hit_when_start_is_weekend(tmp_path) -> None:
    """start rơi vào thứ Bảy, phiên đầu cache là thứ Hai -> vẫn dùng cache, không tải lại."""
    src = FakeSource(_raw("2024-01-08", 30))                       # thứ Hai
    get_ohlcv("HPG", "2024-01-06", "2024-02-16", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    get_ohlcv("HPG", "2024-01-06", "2024-02-16", cache_dir=tmp_path, source_fn=src, now=AFTER_CLOSE)
    assert len(src.calls) == 1


# ------------------------------------------------- hạn mức lượt gọi vnstock

from wyckoff.data.fetcher import QuotaExhaustedError, RateLimitError, classify_quota_error  # noqa: E402
from wyckoff.data.loader import with_rate_limit_retry  # noqa: E402

_MINUTE = "EntitlementError: Đã dùng hết hạn mức theo phút (60/60 lượt gọi)"


def test_classify_quota_error() -> None:
    assert classify_quota_error(RuntimeError(_MINUTE)) is RateLimitError
    assert classify_quota_error(RuntimeError("Đã dùng hết hạn mức theo ngày")) is QuotaExhaustedError
    assert classify_quota_error(RuntimeError("timeout")) is None


def test_fallback_stops_on_rate_limit() -> None:
    calls: list[str] = []

    def limited(*_):
        calls.append("a")
        raise RuntimeError(_MINUTE)

    def other(*_):
        calls.append("b")
        return _raw("2020-01-01", 5)

    with pytest.raises(RateLimitError):
        fetch_with_fallback("HPG", "2020-01-01", "2020-01-10", [Strategy("a", limited), Strategy("b", other)])
    assert calls == ["a"]                      # không đốt thêm lượt gọi vào chiến lược khác


def test_retry_waits_then_succeeds() -> None:
    n = {"i": 0}
    slept: list[float] = []

    def fn():
        n["i"] += 1
        if n["i"] < 3:
            raise RateLimitError("x")
        return "ok"

    assert with_rate_limit_retry(fn, retries=3, wait_s=65, sleep=slept.append) == "ok"
    assert slept == [65, 65]


def test_retry_gives_up_and_quota_not_retried() -> None:
    slept: list[float] = []

    def limited():
        raise RateLimitError("x")

    with pytest.raises(RateLimitError):
        with_rate_limit_retry(limited, retries=2, wait_s=1, sleep=slept.append)
    assert slept == [1, 1]

    def daily():
        raise QuotaExhaustedError("y")

    slept.clear()
    with pytest.raises(QuotaExhaustedError):
        with_rate_limit_retry(daily, retries=2, wait_s=1, sleep=slept.append)
    assert slept == []
