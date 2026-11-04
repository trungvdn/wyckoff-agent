"""Event study cho một mã.

Tín hiệu gồm: mọi sự kiện (theo phiên xác nhận) và mọi lần mở pha (B, C, D, E, invalid).
Với mỗi tín hiệu tại phiên t:
- đo lợi suất vào ở open t+1 (metrics.forward_metrics);
- nếu `point_in_time`: chạy lại toàn bộ phân tích trên dữ liệu đến t (không nhìn trước) để lấy
  pha, mức tin cậy, bối cảnh thị trường và các mức xác nhận / vô hiệu đúng như tại ngày đó;
- theo dõi kịch bản: close vượt mức xác nhận (phía trên giá) hay thủng mức vô hiệu (phía dưới giá) trước.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.backtest.metrics import baseline_returns, forward_metrics, rolling_beta, scenario_race
from wyckoff.config import Config
from wyckoff.detectors.models import SPRING_TYPE_LABEL, Event, EventType
from wyckoff.market import align_index, build_market_context
from wyckoff.pipeline import analyze

logger = logging.getLogger(__name__)


@dataclass
class SymbolStudy:
    symbol: str
    signals: pd.DataFrame        # mỗi dòng một tín hiệu
    baseline: pd.DataFrame       # lợi suất nền mọi phiên


def period_label(d: pd.Timestamp, start: pd.Timestamp, split: pd.Timestamp) -> str:
    return f"{start.year}–{split.year - 1}" if d < split else f"{split.year}–nay"


def signal_kind(e: Event) -> str:
    if e.kind == EventType.SPRING:
        return f"Spring ({SPRING_TYPE_LABEL.get(e.details.get('spring_type', ''), '?')})"
    if e.kind == EventType.SOS and e.details.get("reclaim"):
        return "SOS (reclaim)"
    return e.kind.value


EVENT_ATTRS = {
    "penetration_atr": "pen_atr", "recovery_bars": "recovery_bars", "recovery_close_pos": "recovery_close_pos",
    "max_vol_ratio_below_support": "pen_max_vol_ratio", "breakout_atr": "breakout_atr",
    "volume_vs_shakeout": "test_vol_vs_shakeout", "rally_atr": "rally_atr", "decline_from_high": "sc_decline",
}


def event_attrs(e: Event) -> dict[str, Any]:
    """Thuộc tính định lượng của sự kiện (để chẩn đoán)."""
    out: dict[str, Any] = {"spring_type": e.details.get("spring_type"), "ev_vol_ratio": e.vol_ratio,
                           "ev_spread_atr": e.spread_atr, "ev_close_pos": e.close_pos}
    out.update({col: e.details.get(k) for k, col in EVENT_ATTRS.items()})
    return out


def _point_in_time(df: pd.DataFrame, index: pd.DataFrame | None, benchmark: str | None, t: int,
                   cfg: Config) -> dict[str, Any]:
    """Pha / tin cậy / mức giá tại phiên t chỉ từ dữ liệu <= t."""
    from wyckoff.agent.payload import build_payload, current_structure_events

    res = analyze(df.iloc[:t + 1], cfg)
    ctx = None
    if index is not None and benchmark:
        try:
            ctx = build_market_context(res.df, index.loc[:df.index[t]], benchmark, current_structure_events(res), cfg.market)
        except Exception as exc:  # noqa: BLE001
            logger.debug("market ctx lỗi tại %s: %s", df.index[t], exc)
    p = build_payload(res, "X", ctx)
    cur = res.current()
    factors: dict[str, Any] = {}
    for f in p["confidence"]["factors"]:
        k = f"f_{f.get('key') or 'other'}"
        factors[k] = factors.get(k, 0) + f["points"]
        factors[f"h_{f.get('key') or 'other'}"] = 1   # có mặt (kể cả yếu tố 0 điểm như Spring/Test v2)
    rng = next((r for r in res.ranges if r.range_id == cur.range_id), None) if cur.range_id is not None else None
    close_t = float(df["close"].iloc[t])
    ups = [lv.price for lv in cur.confirm if lv.price is not None and lv.price > close_t]
    downs = [lv.price for lv in cur.invalidate if lv.price is not None and lv.price < close_t]
    return {
        "pit_phase": cur.phase,
        "confidence_level": p["confidence"]["level"],
        "confidence_score": p["confidence"]["score"],
        "range_context": cur.range_context,
        "market_trend": None if ctx is None else ctx.get("trend"),
        "rs_60": None if ctx is None else ctx["rs"].get("rs_change_60d_pct"),
        "up_level": min(ups) if ups else None,
        "down_level": max(downs) if downs else None,
        "range_bars": None if rng is None else t - rng.start_idx,
        "range_height_atr": None if rng is None else round(rng.height / rng.atr_at_confirm, 2),
        "range_prior_return": None if rng is None or rng.prior_return is None else round(rng.prior_return * 100, 1),
        **factors,
    }


def study_symbol(
    symbol: str, df: pd.DataFrame, cfg: Config, index: pd.DataFrame | None = None, benchmark: str | None = None,
    start: str | None = None, context_index: pd.DataFrame | None = None, context_benchmark: str | None = None,
) -> SymbolStudy:
    """`index`/`benchmark`: đo lợi suất vượt và beta. `context_index`/`context_benchmark` (mặc định = index):
    chỉ số cho bối cảnh thị trường point-in-time (GT1: chỉ số cùng nhóm vốn hóa)."""
    bt = cfg.backtest
    if context_index is None:
        context_index, context_benchmark = index, benchmark
    start_ts = pd.Timestamp(start or bt.start)
    res = analyze(df, cfg)
    idx_al = align_index(df, index) if index is not None else None
    beta = rolling_beta(df, idx_al, bt.beta_window, bt.beta_min_periods) if idx_al is not None else None
    close = df["close"].to_numpy(dtype=float)
    split = pd.Timestamp(bt.split_date)

    raw: list[dict[str, Any]] = []
    for e in res.events:
        raw.append({"kind": signal_kind(e), "group": "event", "event_date": e.date, "t": e.confirmed_idx,
                    "range_id": e.range_id, **event_attrs(e)})
    for g in res.phases.segments:
        raw.append({"kind": f"pha {g.phase}", "group": "phase", "event_date": g.start_date, "t": g.start_idx,
                    "range_id": g.range_id})
    raw = [r for r in raw if df.index[r["t"]] >= start_ts]

    pit_cache: dict[int, dict[str, Any]] = {}
    rows = []
    for r in raw:
        t = r["t"]
        b = None if beta is None else float(beta.iloc[t])
        row = {"symbol": symbol, **r, "signal_date": df.index[t], "beta": b,
               "period": period_label(df.index[t], start_ts, split)}
        row.update(forward_metrics(df, idx_al, t, bt.horizons, bt.cost_pct, cfg.data.price_limit, cfg.data.limit_tolerance, beta=b))
        if bt.point_in_time:
            if t not in pit_cache:
                pit_cache[t] = _point_in_time(df, context_index, context_benchmark, t, cfg)
            row.update(pit_cache[t])
            outcome, bars = scenario_race(close, t, row["up_level"], row["down_level"], bt.scenario_max_bars)
            row["scenario"], row["scenario_bars"] = outcome, bars
        rows.append(row)
    signals = pd.DataFrame(rows)
    if not signals.empty:
        signals = signals.sort_values(["signal_date", "kind"]).reset_index(drop=True)

    first = max(int(np.searchsorted(df.index.values, start_ts.to_datetime64())), bt.min_history_bars)
    base = baseline_returns(df, idx_al, bt.horizons, bt.cost_pct, first_signal_idx=first,
                            beta=beta if beta is not None else None)
    base.insert(1, "period", [period_label(d, start_ts, split) for d in base.index])
    base.insert(0, "symbol", symbol)
    return SymbolStudy(symbol, signals, base)
