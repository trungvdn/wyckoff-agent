"""Dựng JSON cho dashboard từ kết quả phân tích + payload. Không tính thêm chỉ báo: mọi số lấy từ engine."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from wyckoff.detectors.models import EventType
from wyckoff.phases import Structure
from wyckoff.phases_distribution import DistStructure
from wyckoff.pipeline import AnalysisResult
from wyckoff.pnf import cause_effect_target, cause_effect_target_down
from wyckoff.revision import CONFIRMED, DEVELOPING, PHASE_POTENTIAL, POTENTIAL, REJECTED

# API trả toàn bộ lịch sử đã phân tích; đây chỉ là khung nhìn mặc định khi mở biểu đồ
VIEW_BARS = {"1D": 160, "1W": 156}
VIEW_MAX_BARS = 400
VIEW_LEAD_BARS = 10           # số nến hiển thị trước điểm bắt đầu cấu trúc

PHASE_STEPS = ("A", "B", "C", "D", "E")
TREND_STAGES = ("Markup", "Markdown")
STAGE_SHORT = {"Re-accumulation": "Re-acc", "Initial Accumulation": "Acc", "Initial Distribution": "Dist", "Re-distribution": "Re-dist",
               "Accumulation": "Acc", "Distribution": "Dist"}
# Sự kiện phía phân phối trên biểu đồ: chỉ của cấu trúc phân phối hiện tại
DIST_EVENTS_ABOVE = {EventType.BC.value, EventType.ST_D.value, EventType.LPSY.value}
H8_NOTE = ("Spring và UTAD chủ yếu cho biết giá đang ở sát biên nào của range, chưa cho biết thêm về hướng thoát. Trên 311 mã, range chỉ có "
           "Spring thoát lên 18%, chỉ có UTAD thoát lên 84%; dữ liệu đã xáo trộn thứ tự ngày cũng cho khoảng 23% và 84%. "
           "Xem pha C là mô tả sự kiện.")
EVENT_TEXT = {
    EventType.PS.value: "Hỗ trợ sơ bộ sau nhịp giảm",
    EventType.SC.value: "Bán tháo cao trào",
    EventType.SC_FAILED.value: "Thủng đáy SC: vùng climax kéo dài",
    EventType.AR.value: "Hồi phục tự động, xác lập kháng cự",
    EventType.ST.value: "Kiểm định lại vùng đáy SC",
    EventType.AR_D.value: "Phản ứng giảm sau BC, xác lập hỗ trợ",
    EventType.ST_D.value: "Kiểm định lại vùng đỉnh BC",
    EventType.SPRING.value: "Thủng hỗ trợ rồi đóng cửa quay lại",
    EventType.TEST.value: "Kiểm định Spring với volume thấp",
    EventType.SOS.value: "Phá kháng cự với volume cao",
    EventType.LPS.value: "Điều chỉnh nông, volume cạn",
    EventType.UTAD.value: "Phá đỉnh giả – cảnh báo phân phối",
    EventType.UT.value: "Phá đỉnh giả rồi yếu đi – cảnh báo nguồn cung",
}
RECLAIM_TEXT = "Lấy lại kháng cự với volume cao sau khi thoát xuống"
EXTENDED_SPRING_TEXT = "Xuyên hỗ trợ nhiều phiên rồi quay lại (Spring kéo dài)"
QUICK_SPRING_TEXT = "Xuyên hỗ trợ rồi hồi nhanh (Spring hồi phục nhanh)"
LPS_TEXT = "Điều chỉnh về hỗ trợ, cung yếu đi, cầu quay lại"
PHASE_POTENTIAL_TITLE = "Thoát xuống, chờ xác nhận"
STATUS_VN_LABEL = {POTENTIAL: " (tiềm năng)", DEVELOPING: " (đang hình thành)", CONFIRMED: "", REJECTED: " (đã bác bỏ)"}
# Sự kiện gắn nhãn phía trên nến; còn lại phía dưới
EVENTS_ABOVE = {EventType.AR.value, EventType.SOS.value, EventType.UTAD.value, EventType.UT.value}
REVISED_ABOVE = EVENTS_ABOVE | {EventType.ST_D.value}   # sự kiện của lớp đánh giá lại


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
    elif phase == PHASE_POTENTIAL:
        title = PHASE_POTENTIAL_TITLE
    else:
        title = f"Pha {phase}"
    cur = PHASE_STEPS.index(phase) if phase in PHASE_STEPS else -1
    steps = [{"id": p, "status": "done" if i < cur else "current" if i == cur else "pending"}
             for i, p in enumerate(PHASE_STEPS)]
    return {"phase": phase, "title": title, "steps": steps}


def stage_segments(result: AnalysisResult) -> list[dict[str, Any]]:
    """Các đoạn giai đoạn cho dải trên biểu đồ, đánh giá lại bằng dữ liệu đến phiên cuối (biểu đồ hồi cứu):
    range đã thoát ghi nhãn theo hướng thoát, thêm "?" khi còn tiềm năng, về "TR ?" khi hướng thoát bị bác bỏ.
    Markup / Markdown còn tiềm năng vẽ nhạt, bị bác bỏ thì không tô."""
    labels = {r.range_id: r for r in result.stages.ranges}
    hyp_by_start = {h.start_idx: h for h in result.revision.hypotheses}
    out = []
    for g in result.stages.segments:
        if g.range_id is not None:
            r = labels.get(g.range_id)
            name = None if r is None or r.resolved_idx is None else (r.structure_type or r.stage)
            h = result.revision.hypothesis_of_range(g.range_id)
            status = h.status if h is not None else None
            short = STAGE_SHORT.get(name, "TR ?") if status != REJECTED else "TR ?"
            # Nhãn tích lũy chỉ lấy từ mức Accumulation của range, không suy từ hướng thoát
            verdict = result.revision.primary_of(g.range_id)[0]
            if short in ("Acc", "Re-acc", "Dist"):
                short = "TR ?"
            kind, label = "range", f"{short}?" if status == POTENTIAL and short != "TR ?" else short
            if verdict is not None and verdict.status == POTENTIAL:
                label = "Dist?" if verdict.is_distribution else "Re-acc?" if verdict.is_reaccumulation else "Acc?"
        elif g.stage in TREND_STAGES:
            h = hyp_by_start.get(g.start_idx)
            status = h.status if h is not None else CONFIRMED
            side = "up" if g.stage == "Markup" else "down"
            if status == REJECTED:
                kind, label = "none", ""
            elif status in (POTENTIAL, DEVELOPING):
                kind, label = f"{side}_potential", f"{g.stage}?"
            else:
                kind, label = side, g.stage
        else:
            kind, label = "none", ""
        out.append({"kind": kind, "label": label, "i0": g.start_idx, "i1": g.end_idx})
    # Range đã xác nhận hoặc đang hình thành Accumulation: một đoạn liền từ đầu range đến trước Markup, đè lên các đoạn cũ
    # Giá đã rời range nhưng cấu trúc còn hiệu lực: đoạn kéo đến phiên cuối
    live = result.live_structure() if result.current_stage().range_id is None else None
    for rid in sorted(set(result.revision.range_verdicts) | set(result.revision.distribution_verdicts)):
        v = result.revision.primary_of(rid)[0]
        if v is None:
            continue
        name = "distribution" if v.is_distribution else "reaccumulation" if v.is_reaccumulation else "accumulation"
        end = len(result.df) - 1 if live is not None and live.range_id == rid else v.end_idx
        if v.status == CONFIRMED:
            out = _overlay_segment(out, {"kind": name, "label": v.structure_type, "i0": v.start_idx, "i1": end})
        elif v.status == DEVELOPING:
            out = _overlay_segment(out, {"kind": f"{name}_developing", "label": f"{v.structure_type.replace('Initial ', '')}?", "i0": v.start_idx, "i1": end})
    return out


def _overlay_segment(segments: list[dict[str, Any]], new: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in segments:
        if s["i1"] < new["i0"] or s["i0"] > new["i1"]:
            out.append(s)
            continue
        if s["i0"] < new["i0"]:
            out.append({**s, "i1": new["i0"] - 1})
        if s["i1"] > new["i1"]:
            out.append({**s, "i0": new["i1"] + 1})
    return sorted(out + [new], key=lambda s: s["i0"])


def current_distribution_structure(result: AnalysisResult) -> DistStructure | None:
    sid = result.distribution_phases.series["structure_id"].iloc[-1]
    return None if pd.isna(sid) else result.distribution_phases.structures[int(sid)]


def stage_view(current: dict[str, Any], history: list[dict[str, Any]], trend: dict[str, Any] | None = None,
               structure: dict[str, Any] | None = None) -> dict[str, Any]:
    """Giai đoạn hiện tại cho dashboard. `current`, `history`: payload.current_stage, payload.stage_history.
    `trend`: payload.revision.trend. Xu hướng bị bác bỏ hiển thị như chưa có xu hướng, nêu rõ lý do.
    `structure`: payload.revision.structure. Còn hiệu lực thì hiển thị là cấu trúc đó, kèm mức bằng chứng."""
    last = history[-1] if history else None
    in_range = current["range_id"] is not None
    status = trend["status"] if trend is not None and not in_range else None
    view = "range" if in_range else "trend" if current["stage"] in TREND_STAGES and status != REJECTED else "transition"
    trend_title = {POTENTIAL: f"{current['stage']} tiềm năng", DEVELOPING: f"{current['stage']} đang hình thành"}.get(status, current["stage"])
    title = {"range": " hoặc ".join(current["candidates"]), "trend": trend_title, "transition": "Chưa có xu hướng rõ"}[view]
    if structure is not None and view != "trend":
        view = "range"
        title = f"{structure['structure_type'].replace('Initial ', '')} đang hình thành" if structure["level"] == DEVELOPING else structure["structure_type"]
    dist = current.get("distribution_phase")
    dist_view = None if not dist else {**phase_view(dist["phase"]), "since": dist["since"], "reason": dist["reason"],
                                       "events": [e["kind"] for e in dist["events"]]}
    out = {**current, "view": view, "title": title, "distribution_phase": dist_view, "revision_status": status,
           "last_resolved": None if last is None else {
               "range_id": last["range_id"], "date": last["resolved_date"],
               "label": last.get("revised_type") or (last["structure_type"] or last["stage"] or "") + STATUS_VN_LABEL.get(last.get("revision_status"), "")}}
    out["evidence"] = structure["evidence"] if structure is not None and view == "range" else None
    out["trend_conditions"] = trend.get("conditions", []) if status is not None else []
    out["trend_supporting"] = trend.get("supporting", []) if status is not None else []
    out["trend_state"] = trend.get("state") if status is not None else None
    if status is not None:
        out["reason"] = trend["reason"]
    if status == REJECTED:
        out["strength"] = None
        out["structure_type"] = f"{current['stage']} đã bác bỏ"
    return out


def _chart_event(e: Any, above_set: set[str], current: bool, status: str) -> dict[str, Any]:
    above = e.kind.value in above_set
    return {"kind": e.kind.value, "t": _date(e.date), "i": e.idx, "price": _f(e.high if above else e.low),
            "above": above, "current": current, "status": status}


def _event_text(e: dict[str, Any]) -> str:
    details = e["details"]
    if details.get("spring_type") == "extended":
        return EXTENDED_SPRING_TEXT
    if details.get("spring_type") == "quick":
        return QUICK_SPRING_TEXT
    if details.get("lps_definition"):
        return LPS_TEXT
    return RECLAIM_TEXT if details.get("reclaim") else EVENT_TEXT.get(e["kind"], e["kind"])


def build_view(result: AnalysisResult, payload: dict[str, Any], symbol: str, tf: str,
               notices: list[str] | None = None) -> dict[str, Any]:
    df = result.df
    s = current_structure(result)
    bars = [
        {"t": _date(ts), "o": _f(r.open), "h": _f(r.high), "l": _f(r.low), "c": _f(r.close),
         "v": int(r.volume), "vr": _f(r.vol_ratio), "vma": None if pd.isna(r.vol_ma) else int(r.vol_ma)}
        for ts, r in df.iterrows()
    ]
    rv = result.revision
    struct_ids = {(e.kind, e.idx) for e in s.events} if s is not None else set()
    cur_rid = s.rng.range_id if s is not None and s.rng is not None else None
    # LPS của nhật ký không đạt định nghĩa mới thì không phải LPS: không vẽ (LPS mới trùng phiên được vẽ ở dưới)
    chart_events = [_chart_event(e, EVENTS_ABOVE, (e.kind, e.idx) in struct_ids, rv.status_of(e))
                    for e in result.events if e.kind not in (EventType.SC_FAILED, EventType.LPS, EventType.AR, EventType.ST, EventType.SPRING, EventType.TEST)]
    # Sự kiện mới của lớp đánh giá lại, và ứng viên đang chờ xác nhận (ứng viên đã hết hạn không vẽ).
    # SC, PS, AR, ST trùng phiên với nhật ký chỉ vẽ một lần.
    shown = {(c["kind"], c["i"]) for c in chart_events}
    for e in rv.events:
        if (e.kind.value, e.idx) not in shown:
            shown.add((e.kind.value, e.idx))
            chart_events.append(_chart_event(e, REVISED_ABOVE, e.range_id == cur_rid, rv.status_of(e)))
    for e in [x for x in result.candidates if x.kind != EventType.SPRING] + rv.candidates:
        if rv.status_of(e) == POTENTIAL and (e.kind.value, e.idx) not in shown:
            shown.add((e.kind.value, e.idx))
            chart_events.append(_chart_event(e, REVISED_ABOVE, e.range_id == cur_rid, POTENTIAL))
    d = current_distribution_structure(result)
    stage_name = payload["current_stage"]["stage"]
    if d is not None and stage_name != "Markup":
        seen = {(c["kind"], c["i"]) for c in chart_events}
        chart_events += [_chart_event(e, DIST_EVENTS_ABOVE, True, rv.status_of(e))
                         for e in d.events if e.kind not in (EventType.BC_FAILED, EventType.AR_D, EventType.ST_D) and (e.kind.value, e.idx) not in seen]
    # Range đã thoát nhưng vẫn là cấu trúc hiện tại: khung kéo đến phiên cuối
    reopened = result.reopened_range_id()
    ranges = [
        {"id": r.range_id, "support": _f(r.support), "resistance": _f(r.resistance),
         "i0": r.start_idx, "i1": len(df) - 1 if r.range_id == reopened else r.end_idx, "active": r.end_confirmed_idx is None,
         "current": r.range_id == cur_rid, "context": r.context}
        for r in result.ranges
    ]
    cp = payload["current_phase"]
    revision = payload["revision"]
    events = [
        {"id": e["uid"], "kind": e["kind"], "text": _event_text(e), "date": e["date"],
         "confirmed_date": e["confirmed_date"], "close": e["close"], "vol_ratio": e["vol_ratio"],
         "spread_atr": e["spread_atr"], "close_pos": e["close_pos"], "status": e["assessment"]}
        for e in {(x["kind"], x["date"]): x for x in revision["events"] + payload["evidence_events"]
                  if (x["kind"] != EventType.LPS.value or x["details"].get("lps_definition"))
                  and (x["kind"] not in (EventType.AR.value, EventType.AR_D.value) or x["details"].get("ar_definition"))
                  and (x["kind"] not in (EventType.ST.value, EventType.ST_D.value) or x["details"].get("st_definition"))
                  and (x["kind"] != EventType.SPRING.value or x["details"].get("spring_definition"))
                  and (x["kind"] != EventType.TEST.value or x["details"].get("test_definition"))}.values()
    ]
    events.sort(key=lambda e: e["date"])
    exchange = result.cfg.data.exchange
    target = cause_effect_target(df, s, result.cfg.pnf, exchange) if s is not None and stage_name != "Markdown" else None
    target_down = cause_effect_target_down(df, d, result.cfg.pnf, exchange) if d is not None and stage_name != "Markup" else None
    close = float(df["close"].iloc[-1])
    if target is not None:
        target = {**target, "reached": close >= target["conservative"]}
    if target_down is not None:
        target_down = {**target_down, "reached": close <= target_down["conservative"]}
    stage = stage_view(payload["current_stage"], payload["stage_history"], revision["trend"], revision["structure"])
    stage["accumulation"] = revision["accumulation"]
    stage["distribution"] = revision["distribution"]
    stage["market"] = revision["market"]
    phase_info = phase_view(revision["phase"]["phase"])
    if revision["phase"]["phase"] is None and stage["view"] == "range":
        phase_info["title"] = "Trading Range chưa xác định"
    dist_phase = (stage["distribution_phase"] or {}).get("phase")
    stage["note"] = H8_NOTE if stage["view"] == "range" and "C" in (cp["phase"], dist_phase) else None
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
        "phase_segments": [{"phase": g.phase, "i0": g.start_idx, "i1": g.end_idx} for g in rv.phase_segments],
        "stage_segments": stage_segments(result),
        "revision_changes": revision["changes"],
        "stage": stage,
        "phase": {**phase_info, "since": revision["phase"]["since"],
                  "reason": revision["phase"]["reason"] or "Chưa có bằng chứng về quá trình hấp thụ cung",
                  "support": cp["support"], "resistance": cp["resistance"], "atr": cp["atr"],
                  "range_context": cp["range_context"]},
        "confidence": payload["confidence"],
        "events": events,
        "levels": payload["levels"],
        "target": target,
        "target_down": target_down,
        "market": None if not market else {
            "benchmark": market.get("benchmark"), "trend": market.get("trend"),
            "rs_change_60d_pct": (market.get("rs") or {}).get("rs_change_60d_pct"),
        },
        "last": payload["recent_bars"],
    }
