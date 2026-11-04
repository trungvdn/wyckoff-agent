"""Gói dữ liệu (payload) cố định cho LLM + điểm tin cậy tính bằng quy tắc.

Mọi con số LLM được phép nhắc đến đều nằm trong payload. Mức giá có ID (confirm_0,
invalidate_0, ...) để LLM tham chiếu thay vì gõ lại số.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import ConfidenceConfig
from wyckoff.detectors.models import CTX_AFTER_DECLINE, CTX_AFTER_RISE, SPRING_TYPE_LABEL, Event, EventStatus, EventType
from wyckoff.fmt import vn_g, vn_num, vn_ts
from wyckoff.phases import CurrentPhase
from wyckoff.pipeline import AnalysisResult
from wyckoff.stages import MARKDOWN
from wyckoff.strength import STRONG, WEAK, TrendStrength

PAYLOAD_VERSION = "8"   # v8 (04/11/2026): current_stage.distribution_phase (pha theo sơ đồ phân phối khi đang trong range)


def _r(x: Any, d: int = 2) -> Any:
    if x is None:
        return None
    if isinstance(x, (float, np.floating)):
        return None if np.isnan(x) else round(float(x), d)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def _date(ts: pd.Timestamp | None) -> str | None:
    return None if ts is None else f"{ts:%Y-%m-%d}"


# ------------------------------------------------------------------ tin cậy

@dataclass(frozen=True)
class Factor:
    factor: str
    points: int
    evidence: str
    key: str = ""        # mã ổn định để thống kê (backtest): sc, st, spring, test, sos, lps, rangectx, warning, mkttrend, relstrength


def _note(pts: int, v1: int) -> str:
    return "" if pts == v1 else f" (v1: {'+' if v1 > 0 else ''}{v1}, hiệu chỉnh theo backtest)"


def _strength_points(s: TrendStrength | None) -> int:
    """H7a: cầu mạnh +1, cầu yếu đi -1, cung mạnh -1; còn lại 0 (cung yếu đi chưa phải cầu đã quay lại)."""
    if s is None:
        return 0
    if s.side == "demand":
        return {STRONG: 1, WEAK: -1}.get(s.level, 0)
    return -1 if s.level == STRONG else 0


def confidence(cur: CurrentPhase, events: list[Event], range_context: str | None,
               market_factors: list[dict[str, Any]] | None = None,
               cfg: ConfidenceConfig | None = None, strength: TrendStrength | None = None,
               prior_stage: str | None = None) -> dict[str, Any]:
    """Điểm tin cậy theo quy tắc (không phải xác suất). <= 0 thấp, 1-2 trung bình, >= 3 cao.
    Trọng số từng yếu tố trong `ConfidenceConfig` (v2). `market_factors`: xu hướng chỉ số ±1,
    sức mạnh tương đối (RS + phân kỳ) tối đa ±1. Yếu tố 0 điểm vẫn được ghi để minh bạch."""
    cfg = cfg or ConfidenceConfig()
    if cur.phase in (None, "invalid"):
        return {"level": "không áp dụng", "score": None, "factors": []}
    kinds = {e.kind for e in events}
    f: list[Factor] = []
    sc = next((e for e in events if e.kind == EventType.SC), None)
    if sc is not None:
        f.append(Factor("Có SC mở cấu trúc (pha A xác định)", cfg.sc, f"SC {vn_ts(sc.date)}, volume {vn_num(sc.vol_ratio)}x TB20", "sc"))
    else:
        f.append(Factor("Không có SC: pha A không xác định", 0, "range xác nhận không kèm climax", "sc"))
    if EventType.ST in kinds:
        f.append(Factor("Có ST xác nhận vùng đáy", cfg.st, "ST volume thấp hơn SC", "st"))
    spring = next((e for e in reversed(events) if e.kind == EventType.SPRING), None)
    if spring is not None:
        typ = SPRING_TYPE_LABEL.get(spring.details.get("spring_type", ""), "")
        f.append(Factor(f"Spring ({typ}) đã xác nhận{_note(cfg.spring, 1)}", cfg.spring,
                        f"Spring {vn_ts(spring.date)}, volume {vn_num(spring.vol_ratio)}x TB20", "spring"))
        test = next((e for e in reversed(events) if e.kind == EventType.TEST), None)
        if test is not None and test.details.get("volume_vs_shakeout", 1) < cfg.test_max_vol_vs_shakeout:
            f.append(Factor(f"Test volume < {vn_g(cfg.test_max_vol_vs_shakeout)}x phiên shakeout{_note(cfg.test, 1)}", cfg.test,
                            f"Test {vn_ts(test.date)}, {vn_num(test.details['volume_vs_shakeout'])}x volume shakeout", "test"))
    sos = next((e for e in reversed(events) if e.kind == EventType.SOS), None)
    if sos is not None and sos.details.get("reclaim"):
        f.append(Factor("SOS reclaim sau khi range thoát xuống (chưa có lợi thế riêng trong backtest)", cfg.sos_reclaim,
                        f"SOS {vn_ts(sos.date)}, volume {vn_num(sos.vol_ratio)}x TB20", "sos_reclaim"))
    elif sos is not None:
        f.append(Factor("Có SOS", cfg.sos, "nến tăng phá resistance với volume cao", "sos"))
    if EventType.LPS in kinds:
        f.append(Factor("Có LPS giữ trên resistance cũ", cfg.lps, "điều chỉnh volume thấp", "lps"))
    ctx_pts = {CTX_AFTER_DECLINE: cfg.after_decline, CTX_AFTER_RISE: cfg.after_rise}.get(range_context or "", 0)
    f.append(Factor(f"Bối cảnh range: {range_context or 'không có range'}", 0 if cfg.prior_stage else ctx_pts,
                    "đà giá 120 phiên trước range (không phải tích lũy / phân phối theo Wyckoff)", "rangectx"))
    if cfg.prior_stage:
        f.append(Factor(f"Xu hướng trước range: {prior_stage or 'không rõ'}", cfg.after_decline if prior_stage == MARKDOWN else 0,
                        "theo giai đoạn trước khi range hình thành", "priorstage"))
    if cfg.stage_strength:
        f.append(Factor(f"Sức mạnh cung cầu: {strength.headline if strength else 'không ở Markup / Markdown'}",
                        _strength_points(strength), "khối lượng, đỉnh đáy, nhịp điều chỉnh", "stagestrength"))
    for w in cur.warnings:
        pts = -2 if ("thất bại" in w or "quay lại" in w) else -1
        f.append(Factor("Cảnh báo", pts, w, "warning"))
    f += [Factor(**m) for m in (market_factors or [])]
    score = sum(x.points for x in f)
    level = "thấp" if score <= 0 else "trung bình" if score <= 2 else "cao"
    return {"level": level, "score": score, "factors": [x.__dict__ for x in f]}


# ------------------------------------------------------------------- payload

def _event_dict(i: int, e: Event) -> dict[str, Any]:
    details = {k: _r(v, 3) if isinstance(v, float) else v for k, v in e.details.items()}
    return {
        "id": f"ev_{i}", "kind": e.kind.value, "date": _date(e.date), "confirmed_date": _date(e.confirmed_date),
        "open": _r(e.open), "high": _r(e.high), "low": _r(e.low), "close": _r(e.close), "volume": int(e.volume),
        "vol_ratio": _r(e.vol_ratio), "spread_atr": _r(e.spread_atr), "close_pos": _r(e.close_pos),
        "range_id": e.range_id, "details": details,
        "uid": e.event_id, "status": e.status.value,
        "status_reason": e.history[-1].reason if e.history and e.status != EventStatus.CONFIRMED else None,
        "related": list(e.related_event_ids),
    }


def _recent(df: pd.DataFrame, sup: float | None, res: float | None, atr: float) -> dict[str, Any]:
    last = df.iloc[-1]
    win = df.iloc[-20:]
    out = {
        "last_date": _date(df.index[-1]), "last_open": _r(last["open"]), "last_high": _r(last["high"]),
        "last_low": _r(last["low"]), "last_close": _r(last["close"]), "last_volume": int(last["volume"]),
        "last_vol_ratio": _r(last["vol_ratio"]), "last_close_pos": _r(last["close_pos"]),
        "last_spread_atr": _r(last["spread_atr"]), "vol_ma20": int(last["vol_ma"]) if not np.isnan(last["vol_ma"]) else None,
        "change_20d_pct": _r((last["close"] / win["close"].iloc[0] - 1) * 100, 1),
        "high_20d": _r(win["high"].max()), "low_20d": _r(win["low"].min()),
        "avg_vol_ratio_5d": _r(df["vol_ratio"].iloc[-5:].mean()),
        "up_days_10d": int((df["close"].diff().iloc[-10:] > 0).sum()),
    }
    if sup is not None:
        out["distance_to_support_atr"] = _r((last["close"] - sup) / atr)
    if res is not None:
        out["distance_to_resistance_atr"] = _r((res - last["close"]) / atr)
    return out


def current_structure_events(result: AnalysisResult) -> list[Event]:
    """Sự kiện của cấu trúc đang theo dõi tại phiên cuối (rỗng nếu chưa có cấu trúc)."""
    sid = result.phases.series["structure_id"].iloc[-1]
    if pd.isna(sid):
        return []
    return list(result.phases.structures[int(sid)].events)


def build_payload(result: AnalysisResult, symbol: str, market: dict[str, Any] | None = None) -> dict[str, Any]:
    """`market`: kết quả `wyckoff.market.build_market_context` (None nếu không có dữ liệu chỉ số)."""
    from wyckoff.market import market_confidence_factors

    cfg = result.cfg
    df = result.df
    cur = result.current()
    struct_events: list[Event] = []
    rng = None
    if cur.phase is not None:
        sid = int(result.phases.series["structure_id"].iloc[-1])
        s = result.phases.structures[sid]
        struct_events = list(s.events)
        rng = s.rng

    levels = [
        {"id": f"confirm_{i}", "type": "confirm", "label": lv.label, "condition": lv.condition, "price": _r(lv.price)}
        for i, lv in enumerate(cur.confirm)
    ] + [
        {"id": f"invalidate_{i}", "type": "invalidate", "label": lv.label, "condition": lv.condition, "price": _r(lv.price)}
        for i, lv in enumerate(cur.invalidate)
    ]
    segs = result.phases.segments[-6:]
    recent_ranges = [r for r in result.ranges][-3:]
    stage = result.current_stage()
    strength = result.trend_strength()
    prior_stage = next((r.prior_stage for r in result.stages.ranges if r.range_id == cur.range_id), None)
    resolved = [r for r in result.stages.ranges if r.resolved_idx is not None][-6:]
    payload: dict[str, Any] = {
        "payload_version": PAYLOAD_VERSION,
        "symbol": symbol,
        "as_of": _date(cur.date),
        "price_unit": "nghìn đồng (giá đã điều chỉnh)",
        "data": {"bars": len(df), "first_date": _date(df.index[0]), "last_date": _date(df.index[-1])},
        "current_phase": {
            "phase": cur.phase, "since": _date(cur.since), "reason": cur.reason,
            "range_id": cur.range_id, "range_context": cur.range_context,
            "range_prior_return_pct": _r(rng.prior_return * 100, 1) if rng is not None and rng.prior_return is not None else None,
            "range_start": _date(rng.start_date) if rng is not None else None,
            "range_confirmed": _date(rng.confirmed_date) if rng is not None else None,
            "support": _r(cur.support), "resistance": _r(cur.resistance), "atr": _r(cur.atr),
        },
        "current_stage": {
            "stage": stage.stage, "structure_type": stage.structure_type, "since": _date(stage.since),
            "reason": stage.reason, "prior_stage": stage.prior_stage, "candidates": list(stage.candidates),
            "range_id": stage.range_id,
            "strength": None if strength is None else strength.to_dict(),
            "distribution_phase": result.current_distribution_phase().to_dict() if stage.range_id is not None else None,
        },
        "stage_history": [
            {"range_id": r.range_id, "prior_stage": r.prior_stage, "stage": r.stage, "structure_type": r.structure_type,
             "exit": r.exit_direction, "resolved_date": _date(r.resolved_date)}
            for r in resolved
        ],
        "levels": levels,
        "confidence": confidence(cur, struct_events, cur.range_context,
                                 market_confidence_factors(market, cfg.market) if market else None, cfg.confidence,
                                 strength=strength, prior_stage=prior_stage),
        "market": market,
        "evidence_events": [_event_dict(i, e) for i, e in enumerate(struct_events)],
        "recent_bars": _recent(df, cur.support, cur.resistance, cur.atr),
        "phase_history": [
            {"phase": g.phase, "start": _date(g.start_date), "end": _date(g.end_date), "range_id": g.range_id, "reason": g.reason}
            for g in segs
        ],
        "recent_ranges": [
            {"range_id": r.range_id, "start": _date(r.start_date), "end": _date(r.end_date), "support": _r(r.support),
             "resistance": _r(r.resistance), "context": r.context,
             "prior_return_pct": None if r.prior_return is None else _r(r.prior_return * 100, 1),
             "exit": r.exit_direction or "đang hoạt động"}
            for r in recent_ranges
        ],
        "warnings": list(cur.warnings),
        "rules": {
            "price_limit_pct": _r(cfg.data.price_limit * 100, 1),
            "sos": {"min_breakout_atr": cfg.sos.min_breakout_atr, "min_vol_ratio": cfg.sos.min_vol_ratio,
                    "min_spread_atr": cfg.sos.min_spread_atr, "min_close_pos": cfg.sos.min_close_pos,
                    "confirm_mode": cfg.sos.confirm_mode, "follow_through_bars": cfg.sos.follow_through_bars},
            "spring": {"max_vol_ratio_low_volume": cfg.spring.max_vol_ratio, "max_recovery_bars": cfg.spring.max_recovery_bars,
                       "test_vol_factor": cfg.spring.test_vol_factor, "invalid_atr": cfg.phase.spring_invalid_atr},
            "range_exit": {"exit_atr": cfg.ranges.exit_atr, "exit_bars": cfg.ranges.exit_bars},
            "atr_period": cfg.indicators.atr_period, "vol_ma_period": cfg.indicators.vol_ma_period,
            "context_lookback": cfg.ranges.context_lookback,
        },
    }
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))   # chuẩn hoá kiểu JSON


def payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)
