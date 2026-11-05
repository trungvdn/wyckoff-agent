"""Giả thuyết H8 (docs/h8-preregistration.md): điểm bằng chứng của range đang hoạt động. Chưa nối vào pipeline, payload, dashboard.

Tại phiên t trong range (từ phiên xác nhận đến trước phiên thoát), cộng điểm mọi sự kiện của range đó đã biết tại t và chưa
INVALIDATED tại t. Tổng >= +2: nghiêng tích lũy; <= -2: nghiêng phân phối; còn lại: chưa nghiêng. Chỉ dùng dữ liệu <= t.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from wyckoff.detectors.models import Event, EventStatus, EventType, TradingRange
from wyckoff.pipeline import AnalysisResult

Mode = Literal["h8a", "h8b"]
ACC, DIST = "acc", "dist"
THRESHOLD = 2

WEIGHTS_A = {EventType.SC: 1, EventType.ST: 1, EventType.SPRING: 1, EventType.TEST: 1,
             EventType.BC: -1, EventType.ST_D: -1, EventType.UT: -1, EventType.UTAD: -1}
WEIGHTS_B = {**WEIGHTS_A, EventType.SOS: 2, EventType.LPS: 1, EventType.SOW: -2, EventType.LPSY: -1}
WEIGHTS = {"h8a": WEIGHTS_A, "h8b": WEIGHTS_B}


@dataclass(frozen=True)
class RangeEvidence:
    range_id: int
    start: int                          # phiên đầu được chấm (range xác nhận)
    scores: tuple[int, ...]             # điểm từng phiên từ `start`
    states: tuple[str | None, ...]      # ACC, DIST hoặc None
    flips: tuple[tuple[int, str, int], ...]  # (phiên, chiều, điểm): mỗi lần đổi sang một trạng thái nghiêng

    @property
    def final_state(self) -> str | None:
        return self.states[-1] if self.states else None

    def first_of(self, state: str) -> int | None:
        """Phiên đầu tiên range nghiêng theo chiều `state`."""
        return next((t for t, s, _ in self.flips if s == state), None)


def range_events(result: AnalysisResult, rng: TradingRange, mode: Mode) -> list[Event]:
    """Sự kiện được chấm của range: SC, ST, BC, ST(d) lấy từ cấu trúc gắn với range; loại khác theo `range_id`."""
    weights = WEIGHTS[mode]
    out: list[Event] = []
    for s in result.phases.structures.values():
        if s.rng is not None and s.rng.range_id == rng.range_id:
            out += [e for e in s.events if e.kind in (EventType.SC, EventType.ST)]
    for s in result.distribution_phases.structures.values():
        if s.rng is not None and s.rng.range_id == rng.range_id:
            out += [e for e in s.events if e.kind in (EventType.BC, EventType.ST_D)]
    by_range = (EventType.SC, EventType.ST, EventType.BC, EventType.ST_D)
    out += [e for e in result.events + result.distribution
            if e.range_id == rng.range_id and e.kind in weights and e.kind not in by_range and not e.details.get("reclaim")]
    return [e for e in out if e.kind in weights]


def _state(score: int) -> str | None:
    return ACC if score >= THRESHOLD else DIST if score <= -THRESHOLD else None


def evidence_for_range(result: AnalysisResult, rng: TradingRange, mode: Mode) -> RangeEvidence:
    weights = WEIGHTS[mode]
    events = range_events(result, rng, mode)
    stop = rng.end_confirmed_idx if rng.end_confirmed_idx is not None else len(result.df)
    scores: list[int] = []
    states: list[str | None] = []
    flips: list[tuple[int, str, int]] = []
    prev: str | None = None
    for t in range(rng.confirmed_idx, stop):
        score = 0
        for e in events:
            status = e.status_at(t)
            if status is not None and status != EventStatus.INVALIDATED:
                score += weights[e.kind]
        state = _state(score)
        if state is not None and state != prev:
            flips.append((t, state, score))
        scores.append(score)
        states.append(state)
        prev = state
    return RangeEvidence(rng.range_id, rng.confirmed_idx, tuple(scores), tuple(states), tuple(flips))


def evidence(result: AnalysisResult, mode: Mode) -> list[RangeEvidence]:
    return [evidence_for_range(result, r, mode) for r in result.ranges]
