"""Vòng đời event (quy chuẩn 04/11/2026, mục 1.2 và 11): ID ổn định, quan hệ, lịch sử trạng thái.

Lớp này chỉ GHI NHẬN, không đổi kết quả detector: pha, tin cậy và backtest vẫn dùng đúng tập
event đã xác nhận như trước (mốc `confirmed_idx`). Mọi trạng thái tại phiên t chỉ dùng dữ liệu <= t:
`Event.status_at(t)` trên dữ liệu đầy đủ trùng với trạng thái cuối khi chạy trên dữ liệu cắt tại t
(xem tests/test_lifecycle.py).

ID: `<LOẠI>-<yyyymmdd phiên event>[-TR<yyyymmdd bắt đầu range>][-SC|-SPRING|-SOS<yyyymmdd event gốc>][-RECLAIM]`
– chỉ dựa vào ngày, nên không đổi khi đổi ngày bắt đầu tải dữ liệu (range_id thì có thể đổi).

Quy tắc vô hiệu hóa sau xác nhận (trong `lifecycle.watch_bars` phiên):
- SC: có SC failed (quy tắc sẵn có) -> SC INVALIDATED; PS của SC đó INVALIDATED theo.
- Spring: close < đáy Spring - phase.spring_invalid_atr x ATR; Test của Spring đó INVALIDATED theo.
- SOS: close dưới mức vô hiệu pha D theo phase.d_invalid_mode (range_mid | support | lps_or_res_atr).
- LPS: close < đáy LPS - lifecycle.lps_invalid_atr x ATR.
AR, ST, UTAD, SC failed: chưa có quy tắc vô hiệu (giữ CONFIRMED).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

import numpy as np
import pandas as pd

from wyckoff.config import Config
from wyckoff.detectors.models import Event, EventStatus, EventType, StatusChange, TradingRange
from wyckoff.fmt import vn_g, vn_num, vn_ts

_EPS = 1e-9

_CODE = {
    EventType.SC: "SC", EventType.SC_FAILED: "SCFAIL", EventType.SPRING: "SPRING", EventType.TEST: "TEST",
    EventType.SOS: "SOS", EventType.PS: "PS", EventType.AR: "AR", EventType.ST: "ST", EventType.LPS: "LPS",
    EventType.UTAD: "UTAD",
}


def _ymd(ts: pd.Timestamp | str) -> str:
    return pd.Timestamp(ts).strftime("%Y%m%d")


def base_event_id(e: Event, ranges: dict[int, TradingRange]) -> str:
    parts = [_CODE[e.kind], _ymd(e.date)]
    if e.range_id is not None and e.range_id in ranges:
        parts.append(f"TR{_ymd(ranges[e.range_id].start_date)}")
    if "sc_date" in e.details:
        parts.append(f"SC{_ymd(e.details['sc_date'])}")
    if "spring_date" in e.details:
        parts.append(f"SPRING{_ymd(e.details['spring_date'])}")
    if "sos_date" in e.details:
        parts.append(f"SOS{_ymd(e.details['sos_date'])}")
    if e.kind == EventType.SOS and e.details.get("reclaim"):
        parts.append("RECLAIM")
    return "-".join(parts)


def _first_known(e: Event) -> int:
    return e.history[0].idx if e.history else e.confirmed_idx


def _assign_ids(events: list[Event], ranges: dict[int, TradingRange]) -> list[Event]:
    """ID cơ sở; trùng (hiếm) thì thêm hậu tố -2, -3 theo thứ tự biết đến (causal, ổn định)."""
    order = sorted(range(len(events)), key=lambda i: (_first_known(events[i]), events[i].idx, events[i].kind.value))
    seen: dict[str, int] = {}
    out = list(events)
    for i in order:
        base = base_event_id(events[i], ranges)
        n = seen.get(base, 0) + 1
        seen[base] = n
        out[i] = replace(events[i], event_id=base if n == 1 else f"{base}-{n}")
    return out


def _loc(df: pd.DataFrame, date: str | pd.Timestamp) -> int:
    return int(df.index.get_loc(pd.Timestamp(date)))


def _first_close_below(
    df: pd.DataFrame, start: int, watch: int, level: Callable[[int], float]
) -> int | None:
    close = df["close"].to_numpy(dtype=float)
    last = len(df) - 1
    for t in range(start + 1, min(start + watch, last) + 1):
        lv = level(t)
        if not np.isnan(lv) and close[t] < lv - _EPS:
            return t
    return None


def _confirmed_history(df: pd.DataFrame, e: Event) -> list[StatusChange]:
    """Các mốc trước xác nhận chỉ ghi cho loại có ghi cả candidate thất bại (SC, Spring, SOS follow-through) –
    nếu không, việc 'biết' DETECTED ở phiên event sẽ là nhìn trước kết quả."""
    ch = lambda s, i, r="": StatusChange(s, i, df.index[i], r)  # noqa: E731
    h: list[StatusChange] = []
    if e.kind == EventType.SC and e.confirmed_idx > e.idx:
        h.append(ch(EventStatus.DETECTED, e.idx, "climax đóng cửa thấp, chờ xác nhận vùng"))
    elif e.kind == EventType.SOS and "follow_through" in e.details:
        h.append(ch(EventStatus.DETECTED, e.idx, "breakout, chờ follow-through"))
    elif e.kind == EventType.SPRING:
        rec = _loc(df, e.details["recovery_date"])
        if rec > e.idx:
            h.append(ch(EventStatus.DETECTED, e.idx, "thủng support"))
        if e.details.get("spring_type") == "shakeout":
            h.append(ch(EventStatus.CANDIDATE, rec, "shakeout volume cao, chờ Test"))
    h.append(ch(EventStatus.CONFIRMED, e.confirmed_idx))
    return h


def annotate(
    df: pd.DataFrame, events: list[Event], candidates: list[Event], ranges: list[TradingRange], cfg: Config
) -> tuple[list[Event], list[Event]]:
    """Gán event_id, quan hệ, lịch sử trạng thái. Trả về (events, candidates) cùng thứ tự đầu vào."""
    rng_by_id = {r.range_id: r for r in ranges}
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    watch = cfg.lifecycle.watch_bars
    n = len(events)

    items = [replace(e, history=tuple(_confirmed_history(df, e))) for e in events] + list(candidates)
    items = _assign_ids(items, rng_by_id)
    evs, cands = items[:n], items[n:]

    # --- tra cứu để nối quan hệ (chỉ event đã xác nhận)
    sc_by_date = {e.date.strftime("%Y-%m-%d"): e for e in evs if e.kind == EventType.SC}
    spring_by = {(e.range_id, e.date.strftime("%Y-%m-%d")): e for e in evs if e.kind == EventType.SPRING}
    sos_by = {(e.range_id, e.date.strftime("%Y-%m-%d")): e for e in evs if e.kind == EventType.SOS}

    related: dict[str, list[str]] = {e.event_id: [] for e in evs}
    test_of: dict[str, str] = {}

    def link(child: Event, parent: Event | None, tested: bool = False) -> None:
        if parent is None:
            return
        related[child.event_id].append(parent.event_id)
        related[parent.event_id].append(child.event_id)
        if tested:
            test_of[child.event_id] = parent.event_id

    for e in evs:
        if e.kind in (EventType.PS, EventType.AR, EventType.SC_FAILED):
            link(e, sc_by_date.get(e.details.get("sc_date", "")))
        elif e.kind == EventType.ST:
            link(e, sc_by_date.get(e.details.get("sc_date", "")), tested=True)
        elif e.kind == EventType.TEST:
            link(e, spring_by.get((e.range_id, e.details.get("spring_date", ""))), tested=True)
        elif e.kind == EventType.LPS:
            link(e, sos_by.get((e.range_id, e.details.get("sos_date", ""))))

    # --- vô hiệu hóa sau xác nhận
    inval: dict[str, StatusChange] = {}

    def mark(e: Event, t: int, reason: str) -> None:
        if e.event_id not in inval and t >= e.confirmed_idx:
            inval[e.event_id] = StatusChange(EventStatus.INVALIDATED, t, df.index[t], reason)

    for e in evs:
        if e.kind == EventType.SC_FAILED:
            sc = sc_by_date.get(e.details.get("sc_date", ""))
            if sc is not None:
                mark(sc, e.idx, f"SC failed {vn_ts(e.date)}: close dưới đáy SC")
        elif e.kind == EventType.SPRING:
            k = cfg.phase.spring_invalid_atr
            low = e.details["lowest_low"]
            t = _first_close_below(df, e.confirmed_idx, watch, lambda j: low - k * atr_ref[j])
            if t is not None:
                mark(e, t, f"close {vn_num(df['close'].iloc[t])} < đáy Spring {vn_num(low)} - {vn_g(k)} ATR")
        elif e.kind == EventType.SOS and e.range_id in rng_by_id:
            rg = rng_by_id[e.range_id]
            mode = cfg.phase.d_invalid_mode
            if mode == "support":
                level, what = (lambda j: rg.support), f"support {vn_num(rg.support)}"
            elif mode == "lps_or_res_atr":
                k = cfg.phase.d_invalid_atr
                level, what = (lambda j: rg.resistance - k * atr_ref[j]), f"resistance {vn_num(rg.resistance)} - {vn_g(k)} ATR"
            else:
                mid = (rg.support + rg.resistance) / 2
                level, what = (lambda j: mid), f"giữa range {vn_num(mid)}"
            t = _first_close_below(df, e.confirmed_idx, watch, level)
            if t is not None:
                mark(e, t, f"close {vn_num(df['close'].iloc[t])} < {what}: breakout thất bại")
        elif e.kind == EventType.LPS:
            k = cfg.lifecycle.lps_invalid_atr
            t = _first_close_below(df, e.confirmed_idx, watch, lambda j: e.low - k * atr_ref[j])
            if t is not None:
                mark(e, t, f"close {vn_num(df['close'].iloc[t])} < đáy LPS {vn_num(e.low)} - {vn_g(k)} ATR")

    # --- lan truyền: PS theo SC, Test theo Spring
    by_id = {e.event_id: e for e in evs}
    for e in evs:
        parent_kind = {EventType.PS: EventType.SC, EventType.TEST: EventType.SPRING}.get(e.kind)
        if parent_kind is None:
            continue
        for pid in related[e.event_id]:
            p = by_id[pid]
            if p.kind == parent_kind and pid in inval:
                ch = inval[pid]
                mark(e, max(ch.idx, e.confirmed_idx), f"{p.kind.value} {vn_ts(p.date)} bị vô hiệu")

    out = []
    for e in evs:
        hist = e.history + ((inval[e.event_id],) if e.event_id in inval else ())
        out.append(replace(e, history=hist, related_event_ids=tuple(dict.fromkeys(related[e.event_id])),
                           test_of_event_id=test_of.get(e.event_id)))
    cands = sorted(cands, key=lambda c: (c.idx, c.kind.value))
    return out, cands


def snapshot(events: list[Event], candidates: list[Event], t: int) -> list[tuple[Event, EventStatus]]:
    """Mọi event / candidate đã biết tại phiên t với trạng thái lúc đó (không nhìn trước)."""
    out = [(e, s) for e in events + candidates if (s := e.status_at(t)) is not None]
    return sorted(out, key=lambda p: (p[0].idx, p[0].kind.value))
