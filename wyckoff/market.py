"""Bối cảnh thị trường: xu hướng chỉ số, sức mạnh tương đối (RS), phân kỳ đáy, đối chiếu sự kiện.

Mọi đại lượng tại phiên t chỉ dùng dữ liệu <= t. Chỉ số được căn theo ngày của cổ phiếu
(ffill tối đa 3 phiên nếu chỉ số thiếu ngày).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import MarketConfig
from wyckoff.detectors.models import Event
from wyckoff.fmt import vn_g, vn_num, vn_ts

TREND_LABEL = {"uptrend": "tăng", "downtrend": "giảm", "sideways": "đi ngang"}


def benchmark_for(exchange: str, cfg: MarketConfig | None = None) -> str:
    """Chỉ số so sánh theo sàn (dùng để đo lợi suất vượt)."""
    cfg = cfg or MarketConfig()
    try:
        return cfg.benchmarks[exchange.upper()]
    except KeyError as exc:
        raise ValueError(f"Không có chỉ số so sánh cho sàn {exchange}") from exc


def context_benchmark_for(exchange: str, cfg: MarketConfig | None = None) -> str:
    """Chỉ số dùng cho bối cảnh thị trường (xu hướng, RS, phân kỳ): `context_benchmark` nếu có, ngược lại theo sàn."""
    cfg = cfg or MarketConfig()
    return cfg.context_benchmark or benchmark_for(exchange, cfg)


def market_regime(index: pd.DataFrame, cfg: MarketConfig | None = None) -> pd.DataFrame:
    """Mỗi phiên: SMA nhanh/chậm, độ dốc SMA nhanh (%), nhãn xu hướng.
    uptrend: close > SMA50 > SMA200 và SMA50 cao hơn `slope_bars` phiên trước;
    downtrend: close < SMA50 < SMA200 và SMA50 thấp hơn; còn lại sideways (NaN khi thiếu lịch sử)."""
    cfg = cfg or MarketConfig()
    c = index["close"]
    fast = c.rolling(cfg.sma_fast, min_periods=cfg.sma_fast).mean()
    slow = c.rolling(cfg.sma_slow, min_periods=cfg.sma_slow).mean()
    slope = fast / fast.shift(cfg.slope_bars) - 1
    up = (c > fast) & (fast > slow) & (slope > 0)
    down = (c < fast) & (fast < slow) & (slope < 0)
    trend = pd.Series(np.where(up, "uptrend", np.where(down, "downtrend", "sideways")), index=index.index, dtype=object)
    trend[slow.isna() | slope.isna()] = None
    return pd.DataFrame({"sma_fast": fast, "sma_slow": slow, "slope_pct": slope * 100, "trend": trend})


def align_index(stock: pd.DataFrame, index: pd.DataFrame) -> pd.DataFrame:
    """Chỉ số căn theo ngày của cổ phiếu (ffill tối đa 3 phiên; không dùng ngày tương lai)."""
    return index.reindex(index.index.union(stock.index)).ffill(limit=3).reindex(stock.index)


def relative_strength(stock: pd.DataFrame, index: pd.DataFrame, cfg: MarketConfig | None = None) -> pd.DataFrame:
    """RS = close cổ phiếu / close chỉ số; thay đổi RS theo `rs_windows` (%), RS so với SMA của nó."""
    cfg = cfg or MarketConfig()
    idx = align_index(stock, index)
    rs = stock["close"] / idx["close"]
    out = pd.DataFrame({"rs": rs}, index=stock.index)
    for w in cfg.rs_windows:
        out[f"rs_chg_{w}"] = (rs / rs.shift(w) - 1) * 100
    out["rs_sma"] = rs.rolling(cfg.rs_sma, min_periods=cfg.rs_sma).mean()
    out["rs_above_sma"] = (rs > out["rs_sma"]).where(out["rs_sma"].notna())
    return out


def bullish_divergence(stock: pd.DataFrame, index: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Phân kỳ đáy tại t: đáy chỉ số trong `window` phiên gần nhất thấp hơn đáy `window` phiên trước đó
    (chỉ số tạo đáy mới), trong khi đáy cổ phiếu cùng kỳ KHÔNG thấp hơn đáy kỳ trước (cổ phiếu giữ được)."""
    idx = align_index(stock, index)
    i_recent = idx["low"].rolling(window, min_periods=window).min()
    i_prior = i_recent.shift(window)
    s_recent = stock["low"].rolling(window, min_periods=window).min()
    s_prior = s_recent.shift(window)
    idx_new_low = i_recent < i_prior
    stock_held = s_recent >= s_prior
    div = (idx_new_low & stock_held).where(i_prior.notna() & s_prior.notna())
    return pd.DataFrame({
        "index_recent_low": i_recent, "index_prior_low": i_prior,
        "stock_recent_low": s_recent, "stock_prior_low": s_prior,
        "index_new_low": idx_new_low, "stock_held": stock_held, "divergence": div,
    })


def _f(x: Any, d: int = 2) -> Any:
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    return round(float(x), d)


def event_alignment(events: list[Event], index: pd.DataFrame, regime: pd.DataFrame,
                    index_phase: pd.Series | None = None) -> list[dict[str, Any]]:
    """Với mỗi sự kiện: % thay đổi chỉ số trong phiên đó, xu hướng và pha (tham khảo) của chỉ số ngày đó."""
    chg = index["close"].pct_change() * 100
    out = []
    for e in events:
        d = e.date
        if d not in index.index:
            out.append({"event": e.kind.value, "date": f"{d:%Y-%m-%d}", "index_change_pct": None,
                        "index_trend": None, "index_phase": None})
            continue
        out.append({
            "event": e.kind.value, "date": f"{d:%Y-%m-%d}",
            "index_change_pct": _f(chg.loc[d]),
            "index_trend": regime["trend"].loc[d] if d in regime.index else None,
            "index_phase": (None if index_phase is None or d not in index_phase.index or pd.isna(index_phase.loc[d])
                            else index_phase.loc[d]),
        })
    return out


def build_market_context(
    stock: pd.DataFrame,
    index: pd.DataFrame,
    benchmark: str,
    events: list[Event],
    cfg: MarketConfig | None = None,
    index_phase: pd.Series | None = None,
    index_current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tóm tắt bối cảnh thị trường tại phiên cuối của `stock` (dữ liệu chỉ số sau ngày đó bị bỏ)."""
    cfg = cfg or MarketConfig()
    as_of = stock.index[-1]
    index = index.loc[:as_of]
    regime = market_regime(index, cfg)
    rs = relative_strength(stock, index, cfg)
    div = bullish_divergence(stock, index, cfg.divergence_window)
    warnings: list[str] = []
    if index.index[-1] < as_of:
        warnings.append(f"Dữ liệu {benchmark} chỉ đến {vn_ts(index.index[-1])}, cổ phiếu đến {vn_ts(as_of)}")

    c = index["close"]
    last = index.iloc[-1]
    returns = {f"return_{w}d_pct": _f((c.iloc[-1] / c.iloc[-1 - w] - 1) * 100, 1) if len(c) > w else None
               for w in cfg.return_windows}
    peak = index["high"].iloc[-cfg.drawdown_lookback:].max()
    rs_last = rs.iloc[-1]
    div_last = div.iloc[-1]
    ctx: dict[str, Any] = {
        "benchmark": benchmark,
        "index_last_date": f"{index.index[-1]:%Y-%m-%d}",
        "index_close": _f(last["close"]),
        "index_change_1d_pct": _f((c.iloc[-1] / c.iloc[-2] - 1) * 100) if len(c) > 1 else None,
        "trend": regime["trend"].iloc[-1],
        "sma_fast": _f(regime["sma_fast"].iloc[-1]),
        "sma_slow": _f(regime["sma_slow"].iloc[-1]),
        "sma_fast_slope_pct": _f(regime["slope_pct"].iloc[-1]),
        **returns,
        "drawdown_from_high_pct": _f((last["close"] / peak - 1) * 100, 1),
        "rs": {f"rs_change_{w}d_pct": _f(rs_last[f"rs_chg_{w}"], 1) for w in cfg.rs_windows}
        | {"rs_above_sma": _f(rs_last["rs_above_sma"])},
        "divergence": {
            "bullish_divergence": _f(div_last["divergence"]),
            "index_recent_low": _f(div_last["index_recent_low"]), "index_prior_low": _f(div_last["index_prior_low"]),
            "stock_recent_low": _f(div_last["stock_recent_low"]), "stock_prior_low": _f(div_last["stock_prior_low"]),
        },
        "event_alignment": event_alignment(events, index, regime, index_phase),
        "params": {"sma_fast": cfg.sma_fast, "sma_slow": cfg.sma_slow, "slope_bars": cfg.slope_bars,
                   "drawdown_lookback": cfg.drawdown_lookback, "rs_sma": cfg.rs_sma,
                   "divergence_window": cfg.divergence_window, "return_windows": list(cfg.return_windows),
                   "rs_windows": list(cfg.rs_windows)},
        "index_phase_reference": index_current,
        "warnings": warnings,
    }
    return ctx


def _condition(cid: str, label: str, op: str, value: float, threshold: float, met: bool,
               slope_pct: float | None = None) -> dict[str, Any]:
    """Một điều kiện của quy tắc xu hướng; `gap_*`: chỉ số cần đi thêm bao nhiêu để `value` chạm `threshold`."""
    return {"id": cid, "label": label, "op": op, "met": bool(met), "value": _f(value), "threshold": _f(threshold),
            "gap_pct": _f((threshold / value - 1) * 100), "gap_points": _f(abs(threshold - value)),
            "slope_pct": _f(slope_pct)}


def trend_conditions(close: float, fast: float, slow: float, fast_prior: float,
                     cfg: MarketConfig | None = None) -> dict[str, list[dict[str, Any]]]:
    """Ba điều kiện của `market_regime` cho từng chiều: đạt đủ cả ba thì xu hướng đúng là chiều đó."""
    cfg = cfg or MarketConfig()
    f, s, n = f"SMA{cfg.sma_fast}", f"SMA{cfg.sma_slow}", cfg.slope_bars
    slope = (fast / fast_prior - 1) * 100
    return {
        "up": [
            _condition("close_fast", f"Đóng cửa trên {f}", ">", close, fast, close > fast),
            _condition("fast_slow", f"{f} trên {s}", ">", fast, slow, fast > slow),
            _condition("slope", f"{f} cao hơn {n} phiên trước", ">", fast, fast_prior, slope > 0, slope),
        ],
        "down": [
            _condition("close_fast", f"Đóng cửa dưới {f}", "<", close, fast, close < fast),
            _condition("fast_slow", f"{f} dưới {s}", "<", fast, slow, fast < slow),
            _condition("slope", f"{f} thấp hơn {n} phiên trước", "<", fast, fast_prior, slope < 0, slope),
        ],
    }


def _trend_segments(trend: pd.Series) -> list[dict[str, Any]]:
    """Các đoạn liên tiếp cùng nhãn xu hướng, theo vị trí nến; bỏ phần chưa đủ lịch sử."""
    out: list[dict[str, Any]] = []
    for i, kind in enumerate(trend.tolist()):
        if kind is None or kind != kind:
            continue
        if out and out[-1]["kind"] == kind and out[-1]["i1"] == i - 1:
            out[-1]["i1"] = i
        else:
            out.append({"kind": kind, "i0": i, "i1": i})
    return out


def market_overview(index: pd.DataFrame, cfg: MarketConfig | None = None, volume_ma: int = 20) -> dict[str, Any]:
    """Số liệu trang thị trường tại phiên cuối của `index`. Xu hướng và mức giảm dùng cùng định nghĩa với
    `build_market_context` để trang thị trường và trang cổ phiếu không mâu thuẫn nhau."""
    cfg = cfg or MarketConfig()
    regime = market_regime(index, cfg)
    c = index["close"]
    sma_short = c.rolling(cfg.sma_chart, min_periods=cfg.sma_chart).mean()   # chỉ để vẽ, không dùng trong quy tắc xu hướng
    vma = index["volume"].rolling(volume_ma, min_periods=volume_ma).mean()
    dates = [f"{ts:%Y-%m-%d}" for ts in index.index]
    n = len(index)

    returns = []
    for w in cfg.return_windows:
        ok = n > w
        returns.append({"window": w, "pct": _f((c.iloc[-1] / c.iloc[-1 - w] - 1) * 100) if ok else None,
                        "from_close": _f(c.iloc[-1 - w]) if ok else None, "from_date": dates[-1 - w] if ok else None})

    window = index["high"].iloc[-cfg.drawdown_lookback:]
    peak_at = n - len(window) + int(window.to_numpy().argmax())

    last_trend = regime["trend"].iloc[-1]
    segments = _trend_segments(regime["trend"])
    conditions = None
    if last_trend is not None:
        conditions = trend_conditions(float(c.iloc[-1]), float(regime["sma_fast"].iloc[-1]), float(regime["sma_slow"].iloc[-1]),
                                      float(regime["sma_fast"].iloc[-1 - cfg.slope_bars]), cfg)
    return {
        "as_of": dates[-1],
        "close": _f(c.iloc[-1]),
        "change": _f(c.iloc[-1] - c.iloc[-2]) if n > 1 else None,
        "change_pct": _f((c.iloc[-1] / c.iloc[-2] - 1) * 100) if n > 1 else None,
        "trend": {
            "kind": last_trend,
            "since": dates[segments[-1]["i0"]] if last_trend is not None else None,
            "sessions": segments[-1]["i1"] - segments[-1]["i0"] + 1 if last_trend is not None else None,
            "sma_fast": _f(regime["sma_fast"].iloc[-1]),
            "sma_slow": _f(regime["sma_slow"].iloc[-1]),
            "required_bars": max(cfg.sma_slow, cfg.sma_fast + cfg.slope_bars),
        },
        "conditions": conditions,
        "returns": returns,
        "drawdown": {"pct": _f((c.iloc[-1] / index["high"].iloc[peak_at] - 1) * 100), "peak": _f(index["high"].iloc[peak_at]),
                     "peak_date": dates[peak_at], "sessions_since": n - 1 - peak_at, "lookback": cfg.drawdown_lookback},
        "sma_periods": [cfg.sma_fast, cfg.sma_slow],
        "sma_short_period": cfg.sma_chart,
        "volume_ma_period": volume_ma,
        "bars": [
            {"t": dates[i], "o": _f(r.open), "h": _f(r.high), "l": _f(r.low), "c": _f(r.close), "v": int(r.volume),
             "vma": None if pd.isna(vma.iloc[i]) else int(vma.iloc[i]),
             "sma_short": _f(sma_short.iloc[i]),
             "sma_fast": _f(regime["sma_fast"].iloc[i]), "sma_slow": _f(regime["sma_slow"].iloc[i])}
            for i, r in enumerate(index.itertuples())
        ],
        "trend_segments": segments,
    }


def market_confidence_factors(ctx: dict[str, Any] | None, cfg: MarketConfig | None = None) -> list[dict[str, Any]]:
    """Yếu tố tin cậy từ thị trường (2 yếu tố, mỗi yếu tố trong [-1, +1]):
    1. Xu hướng chỉ số: uptrend +1, downtrend -1, còn lại 0.
    2. Nhóm sức mạnh tương đối = clamp(RS + phân kỳ, -1, +1), với
       RS `confidence_rs_window` phiên > +band -> +1, < -band -> -1, trong ±band -> 0 (đi ngang);
       phân kỳ đáy -> +1. Gộp nhóm để không chấm hai lần cùng một hiện tượng
       (cổ phiếu giữ đáy khi chỉ số tạo đáy mới cũng làm RS tăng)."""
    cfg = cfg or MarketConfig()
    if not ctx:
        return []
    b = ctx["benchmark"]
    out: list[dict[str, Any]] = []
    trend = ctx.get("trend")
    ev_trend = (f"close {vn_num(ctx['index_close'])}, SMA{cfg.sma_fast} {vn_num(ctx['sma_fast'])}, "
                f"SMA{cfg.sma_slow} {vn_num(ctx['sma_slow'])}")
    w = cfg.confidence_rs_window
    rsv = ctx["rs"].get(f"rs_change_{w}d_pct")
    band = cfg.rs_neutral_band_pct
    if trend == "uptrend" and cfg.trend_up_requires_rs and not (rsv is not None and rsv > band):
        out.append({"factor": f"{b} xu hướng {TREND_LABEL[trend]} nhưng cổ phiếu không mạnh hơn thị trường "
                              f"(RS {w} phiên <= +{vn_g(band)}%): không cộng điểm", "points": 0,
                    "evidence": ev_trend, "key": "mkttrend"})
    elif trend in ("uptrend", "downtrend"):
        out.append({"factor": f"{b} xu hướng {TREND_LABEL[trend]}", "points": 1 if trend == "uptrend" else -1,
                    "evidence": ev_trend, "key": "mkttrend"})
    else:
        out.append({"factor": f"{b} xu hướng {TREND_LABEL.get(trend, 'chưa xác định')}", "points": 0, "evidence": ev_trend,
                    "key": "mkttrend"})
    parts: list[str] = []
    rs_pts = 0
    if rsv is not None:
        rs_pts = 1 if rsv > band else -1 if rsv < -band else 0
        label = {1: "mạnh hơn", -1: "yếu hơn", 0: "đi ngang so với"}[rs_pts]
        parts.append(f"RS {w} phiên {vn_num(rsv, 1)}% ({label} thị trường, ngưỡng ±{vn_g(band)}%)")
    d = ctx["divergence"]
    div_pts = 1 if d.get("bullish_divergence") else 0
    if div_pts:
        parts.append(f"phân kỳ đáy: {b} {vn_num(d['index_recent_low'])} < {vn_num(d['index_prior_low'])}, "
                     f"cổ phiếu {vn_num(d['stock_recent_low'])} >= {vn_num(d['stock_prior_low'])}")
    if parts:
        pts = max(-1, min(1, rs_pts + div_pts))
        out.append({"factor": f"Sức mạnh tương đối so với {b} (RS + phân kỳ, tối đa ±1)", "points": pts,
                    "evidence": "; ".join(parts), "key": "relstrength"})
    return out
