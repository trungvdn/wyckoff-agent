"""Dựng JSON cho dashboard từ kết quả phân tích + payload. Không tính thêm chỉ báo: mọi số lấy từ engine."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from wyckoff.detectors.models import EventType
from wyckoff.phases import Structure
from wyckoff.pipeline import AnalysisResult
from wyckoff.pnf import cause_effect_target

# API trả toàn bộ lịch sử đã phân tích; đây chỉ là khung nhìn mặc định khi mở biểu đồ
VIEW_BARS = {"1D": 160, "1W": 156}
VIEW_MAX_BARS = 400
VIEW_LEAD_BARS = 10           # số nến hiển thị trước điểm bắt đầu cấu trúc

PHASE_STEPS = ("A", "B", "C", "D", "E")
EVENT_TEXT = {
    EventType.PS.value: "Hỗ trợ sơ bộ sau nhịp giảm",
    EventType.SC.value: "Bán tháo cao trào",
    EventType.SC_FAILED.value: "Thủng đáy SC: vùng climax kéo dài",
    EventType.AR.value: "Hồi phục tự động, xác lập kháng cự",
    EventType.ST.value: "Kiểm định lại vùng đáy SC",
    EventType.SPRING.value: "Thủng hỗ trợ rồi đóng cửa quay lại",
    EventType.TEST.value: "Kiểm định Spring với volume thấp",
    EventType.SOS.value: "Phá kháng cự với volume cao",
    EventType.LPS.value: "Điều chỉnh nông, volume cạn",
    EventType.UTAD.value: "Phá đỉnh giả – cảnh báo phân phối",
    EventType.UT.value: "Phá đỉnh giả rồi yếu đi – cảnh báo nguồn cung",
}
RECLAIM_TEXT = "Lấy lại kháng cự với volume cao sau khi thoát xuống"
# Sự kiện gắn nhãn phía trên nến; còn lại phía dưới
EVENTS_ABOVE = {EventType.AR.value, EventType.SOS.value, EventType.UTAD.value, EventType.UT.value}


def _f(x: Any, d: int = 2) -> float | None:
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, d)


def _date(ts: pd.Timestamp | None) -> str | None:
    return None if ts is None else f"{ts:%Y-%m-%d}"


def current_structure(result: AnalysisResult) -> Structure | None:
    sid = result.phases.series["structure_id"].iloc[-1]
    return None if pd.isna(sid) else result.phases.structures[int(sid)]


def default_view_start(result: AnalysisResult, tf: str, s: Structure | None) -> int:
    """Nến đầu tiên của khung nhìn mặc định: N nến cuối, mở rộng để thấy trọn cấu trúc hiện tại."""
    n = len(result.df)
    first = max(0, n - VIEW_BARS.get(tf, 160))
    if s is not None:
        anchors = [e.idx for e in s.events] + ([s.rng.start_idx] if s.rng is not None else [])
        if anchors:
            first = min(first, max(0, min(anchors) - VIEW_LEAD_BARS))
    return max(first, n - VIEW_MAX_BARS, 0)


def phase_view(phase: str | None) -> dict[str, Any]:
    if phase is None:
        title = "Chưa có cấu trúc"
    elif phase == "invalid":
        title = "Cấu trúc vô hiệu"
    else:
        title = f"Pha {phase}"
    cur = PHASE_STEPS.index(phase) if phase in PHASE_STEPS else -1
    steps = [{"id": p, "status": "done" if i < cur else "current" if i == cur else "pending"}
             for i, p in enumerate(PHASE_STEPS)]
    return {"phase": phase, "title": title, "steps": steps}


def stage_view(current: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """Giai đoạn hiện tại cho dashboard. `current`, `history`: payload.current_stage, payload.stage_history."""
    last = history[-1] if history else None
    return {**current, "title": current["stage"] or "Chưa phân định",
            "last_resolved": None if last is None else {
                "range_id": last["range_id"], "label": last["structure_type"] or last["stage"], "date": last["resolved_date"]}}


def build_view(result: AnalysisResult, payload: dict[str, Any], symbol: str, tf: str,
               notices: list[str] | None = None) -> dict[str, Any]:
    df = result.df
    s = current_structure(result)
    bars = [
        {"t": _date(ts), "o": _f(r.open), "h": _f(r.high), "l": _f(r.low), "c": _f(r.close),
         "v": int(r.volume), "vr": _f(r.vol_ratio), "vma": None if pd.isna(r.vol_ma) else int(r.vol_ma)}
        for ts, r in df.iterrows()
    ]
    struct_ids = {(e.kind, e.idx) for e in s.events} if s is not None else set()
    chart_events = [
        {"kind": e.kind.value, "t": _date(e.date), "i": e.idx, "price": _f(e.high if e.kind.value in EVENTS_ABOVE else e.low),
         "above": e.kind.value in EVENTS_ABOVE, "current": (e.kind, e.idx) in struct_ids}
        for e in result.events if e.kind != EventType.SC_FAILED
    ]
    cur_rid = s.rng.range_id if s is not None and s.rng is not None else None
    ranges = [
        {"id": r.range_id, "support": _f(r.support), "resistance": _f(r.resistance),
         "i0": r.start_idx, "i1": r.end_idx, "active": r.end_confirmed_idx is None,
         "current": r.range_id == cur_rid, "context": r.context}
        for r in result.ranges
    ]
    cp = payload["current_phase"]
    events = [
        {"id": e["id"], "kind": e["kind"],
         "text": RECLAIM_TEXT if e["details"].get("reclaim") else EVENT_TEXT.get(e["kind"], e["kind"]), "date": e["date"],
         "confirmed_date": e["confirmed_date"], "close": e["close"], "vol_ratio": e["vol_ratio"],
         "spread_atr": e["spread_atr"], "close_pos": e["close_pos"]}
        for e in payload["evidence_events"]
    ]
    target = cause_effect_target(df, s, result.cfg.pnf, result.cfg.data.exchange) if s is not None else None
    market = payload.get("market")
    return {
        "symbol": symbol,
        "timeframe": tf,
        "as_of": payload["as_of"],
        "price_unit": payload["price_unit"],
        "notices": list(notices or []),
        "warnings": payload["warnings"],
        "bars": bars,
        "view_from": default_view_start(result, tf, s),
        "chart_events": chart_events,
        "ranges": ranges,
        "phase_segments": [{"phase": g.phase, "i0": g.start_idx, "i1": g.end_idx} for g in result.phases.segments],
        "stage": stage_view(payload["current_stage"], payload["stage_history"]),
        "phase": {**phase_view(cp["phase"]), "since": cp["since"], "reason": cp["reason"],
                  "support": cp["support"], "resistance": cp["resistance"], "atr": cp["atr"],
                  "range_context": cp["range_context"]},
        "confidence": payload["confidence"],
        "events": events,
        "levels": payload["levels"],
        "target": target,
        "market": None if not market else {
            "benchmark": market.get("benchmark"), "trend": market.get("trend"),
            "rs_change_60d_pct": (market.get("rs") or {}).get("rs_change_60d_pct"),
        },
        "last": payload["recent_bars"],
    }
