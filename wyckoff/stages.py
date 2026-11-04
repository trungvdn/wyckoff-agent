"""Giai đoạn Wyckoff (tầng 1) và loại cấu trúc (tầng 2) bằng state machine causal. Chỉ ghi nhận: không đổi pha / tin cậy / backtest.

Duyệt từng phiên t, chỉ dùng close, SMA tại t và range đã xác nhận / đã kết thúc tại t.

Ngoài range:
    Trending Up (Markup)      enter_bars close liên tiếp trên SMA đang tăng, hoặc range thoát lên
    Trending Down (Markdown)  enter_bars close liên tiếp dưới SMA đang giảm, hoặc range thoát xuống
    Transition / Uncertain    chưa có xu hướng, hoặc exit_bars close liên tiếp nằm sai phía SMA

Trong range đã xác nhận: Transition / Uncertain, kèm hai giả thuyết theo xu hướng trước range.
Nhãn chỉ được chốt khi range thoát, vì hướng thoát không suy ra được từ xu hướng trước đó:

    Trước range   Thoát lên              Thoát xuống
    Markup        Re-accumulation        Initial Distribution
    Markdown      Initial Accumulation   Re-distribution

Nhãn đã chốt mô tả điều đã xảy ra, KHÔNG phải dự báo. Tầng 1 suy ra từ tầng 2 (`TYPE_TO_STAGE`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import StageConfig
from wyckoff.detectors.models import CTX_AFTER_DECLINE, CTX_AFTER_RISE, TradingRange
from wyckoff.fmt import vn_ts

ACCUMULATION = "Accumulation"
MARKUP = "Markup"
DISTRIBUTION = "Distribution"
MARKDOWN = "Markdown"
STAGES = (ACCUMULATION, MARKUP, DISTRIBUTION, MARKDOWN)

INITIAL_ACCUMULATION = "Initial Accumulation"
RE_ACCUMULATION = "Re-accumulation"
TRENDING_UP = "Trending Up"
INITIAL_DISTRIBUTION = "Initial Distribution"
RE_DISTRIBUTION = "Re-distribution"
TRENDING_DOWN = "Trending Down"
TRANSITION = "Transition / Uncertain"

TYPE_TO_STAGE: dict[str, str | None] = {
    INITIAL_ACCUMULATION: ACCUMULATION, RE_ACCUMULATION: ACCUMULATION, TRENDING_UP: MARKUP,
    INITIAL_DISTRIBUTION: DISTRIBUTION, RE_DISTRIBUTION: DISTRIBUTION, TRENDING_DOWN: MARKDOWN,
    TRANSITION: None,
}

_RESOLVE = {
    (MARKUP, "up"): RE_ACCUMULATION, (MARKUP, "down"): INITIAL_DISTRIBUTION,
    (MARKDOWN, "up"): INITIAL_ACCUMULATION, (MARKDOWN, "down"): RE_DISTRIBUTION,
}
_CANDIDATES = {
    MARKUP: (RE_ACCUMULATION, INITIAL_DISTRIBUTION),
    MARKDOWN: (INITIAL_ACCUMULATION, RE_DISTRIBUTION),
    None: (ACCUMULATION, DISTRIBUTION),
}
_TREND_STAGE = {"up": MARKUP, "down": MARKDOWN}
_TREND_TYPE = {"up": TRENDING_UP, "down": TRENDING_DOWN}
_EXIT_VN = {"up": "lên", "down": "xuống"}
_CONTEXT_PRIOR = {CTX_AFTER_DECLINE: MARKDOWN, CTX_AFTER_RISE: MARKUP}


@dataclass(frozen=True)
class RangeStage:
    """Nhãn của một range. Trước `resolved_idx` nhãn chưa được biết (stage, structure_type chỉ có sau khi range thoát)."""
    range_id: int
    prior_stage: str | None                # xu hướng trước range; None = không xác định
    prior_source: str | None               # "trend": từ state machine; "context": từ đà giá 120 phiên
    candidates: tuple[str, ...]
    confirmed_idx: int
    confirmed_date: pd.Timestamp
    resolved_idx: int | None = None
    resolved_date: pd.Timestamp | None = None
    exit_direction: str | None = None
    stage: str | None = None
    structure_type: str | None = None      # None khi đã thoát nhưng không rõ xu hướng trước range


@dataclass(frozen=True)
class StageSegment:
    stage: str | None
    structure_type: str
    range_id: int | None
    start_idx: int
    start_date: pd.Timestamp
    end_idx: int
    end_date: pd.Timestamp
    reason: str


@dataclass(frozen=True)
class CurrentStage:
    date: pd.Timestamp
    stage: str | None
    structure_type: str
    since: pd.Timestamp | None
    reason: str
    prior_stage: str | None
    candidates: tuple[str, ...]
    range_id: int | None

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "candidates": list(self.candidates)}


@dataclass
class StageResult:
    series: pd.DataFrame            # mỗi phiên: stage, structure_type, prior_stage, range_id, reason (như biết tại phiên đó)
    segments: list[StageSegment]
    ranges: list[RangeStage] = field(default_factory=list)


def _trend_before(trend_at: list[str | None], from_idx: int, max_bars: int) -> str | None:
    """Xu hướng gần nhất tính ngược từ `from_idx`, tối đa `max_bars` phiên."""
    for i in range(from_idx, max(from_idx - max_bars, 0) - 1, -1):
        if trend_at[i] is not None:
            return trend_at[i]
    return None


def classify_stages(df: pd.DataFrame, ranges: list[TradingRange], cfg: StageConfig | None = None,
                    sma_period: int = 50) -> StageResult:
    """`df` phải có cột `close`, `sma` (từ add_indicators)."""
    cfg = cfg or StageConfig()
    n = len(df)
    dates = df.index
    close = df["close"].to_numpy(dtype=float)
    sma = df["sma"].to_numpy(dtype=float)
    conf_at = {r.confirmed_idx: r for r in ranges}
    exit_at = {r.end_confirmed_idx: r for r in ranges if r.end_confirmed_idx is not None}

    trend: str | None = None
    trend_reason = "chưa đủ dữ liệu xác định xu hướng"
    trend_at: list[str | None] = [None] * n
    run_up = run_down = against = 0
    last_exit_idx: int | None = None
    active: RangeStage | None = None
    labels: dict[int, RangeStage] = {}
    stage_col: list[str | None] = []
    type_col: list[str] = []
    prior_col: list[str | None] = []
    rid_col: list[float] = []
    reason_col: list[str] = []

    for t in range(n):
        # 1. range thoát: chốt nhãn, xu hướng theo hướng thoát
        ended = exit_at.get(t)
        if ended is not None:
            d = ended.exit_direction
            label = labels[ended.range_id]
            typ = _RESOLVE.get((label.prior_stage, d))
            stage = TYPE_TO_STAGE[typ] if typ else (ACCUMULATION if d == "up" else DISTRIBUTION)
            labels[ended.range_id] = RangeStage(
                **{**label.__dict__, "resolved_idx": t, "resolved_date": dates[t], "exit_direction": d,
                   "stage": stage, "structure_type": typ}
            )
            trend = d
            trend_reason = f"TR#{ended.range_id} thoát {_EXIT_VN[d]} {vn_ts(dates[t])}, chốt {typ or stage}"
            run_up = run_down = against = 0
            active = None
            last_exit_idx = t

        # 2. range xác nhận: mở hai giả thuyết theo xu hướng trước range
        rng = conf_at.get(t)
        if rng is not None:
            look_from = rng.start_idx if last_exit_idx is None else max(rng.start_idx, last_exit_idx)
            prior_trend = _trend_before(trend_at, look_from, cfg.prior_max_bars)
            prior = _TREND_STAGE.get(prior_trend) if prior_trend else _CONTEXT_PRIOR.get(rng.context)
            source = "trend" if prior_trend else "context" if prior else None
            active = RangeStage(rng.range_id, prior, source, _CANDIDATES[prior], t, dates[t])
            labels[rng.range_id] = active
            trend = None
            run_up = run_down = against = 0

        # 3. ngoài range: cập nhật xu hướng
        if active is None and ended is None and not np.isnan(sma[t]) and t >= cfg.slope_bars \
                and not np.isnan(sma[t - cfg.slope_bars]):
            rising = sma[t] > sma[t - cfg.slope_bars]
            falling = sma[t] < sma[t - cfg.slope_bars]
            run_up = run_up + 1 if close[t] > sma[t] and rising else 0
            run_down = run_down + 1 if close[t] < sma[t] and falling else 0
            if trend is not None:
                wrong_side = close[t] < sma[t] if trend == "up" else close[t] > sma[t]
                against = against + 1 if wrong_side else 0
                if against >= cfg.exit_bars:
                    side = "dưới" if trend == "up" else "trên"
                    trend_reason = f"{cfg.exit_bars} close liên tiếp {side} SMA{sma_period}, mất xu hướng ({vn_ts(dates[t])})"
                    trend, against = None, 0
            if trend is None:
                if run_up >= cfg.enter_bars:
                    trend, against = "up", 0
                    trend_reason = f"{cfg.enter_bars} close liên tiếp trên SMA{sma_period} đang tăng ({vn_ts(dates[t])})"
                elif run_down >= cfg.enter_bars:
                    trend, against = "down", 0
                    trend_reason = f"{cfg.enter_bars} close liên tiếp dưới SMA{sma_period} đang giảm ({vn_ts(dates[t])})"

        if active is not None:
            prior_txt = f"sau {active.prior_stage}" if active.prior_stage else "chưa rõ xu hướng trước đó"
            stage_col.append(None)
            type_col.append(TRANSITION)
            prior_col.append(active.prior_stage)
            rid_col.append(active.range_id)
            reason_col.append(f"TR#{active.range_id} xác nhận {vn_ts(active.confirmed_date)}, {prior_txt}: "
                              f"chưa phân định, chốt khi range thoát")
        else:
            trend_at[t] = trend
            stage_col.append(_TREND_STAGE.get(trend) if trend else None)
            type_col.append(_TREND_TYPE[trend] if trend else TRANSITION)
            prior_col.append(None)
            rid_col.append(np.nan)
            reason_col.append(trend_reason)

    series = pd.DataFrame(
        {"stage": stage_col, "structure_type": type_col, "prior_stage": prior_col, "range_id": rid_col, "reason": reason_col},
        index=df.index,
    )
    return StageResult(series=series, segments=_segments(series), ranges=[labels[k] for k in sorted(labels)])


def _segments(series: pd.DataFrame) -> list[StageSegment]:
    segs: list[StageSegment] = []
    key = list(zip(series["structure_type"], series["range_id"].fillna(-1)))
    start = 0
    for i in range(1, len(key) + 1):
        if i == len(key) or key[i] != key[start]:
            rid = series["range_id"].iloc[start]
            st = series["stage"].iloc[start]
            segs.append(StageSegment(
                stage=None if pd.isna(st) else st, structure_type=series["structure_type"].iloc[start],
                range_id=None if np.isnan(rid) else int(rid), start_idx=start, start_date=series.index[start],
                end_idx=i - 1, end_date=series.index[i - 1], reason=series["reason"].iloc[start],
            ))
            start = i
    return segs


def current_stage(stages: StageResult) -> CurrentStage:
    """Giai đoạn tại phiên cuối, đúng như biết tại phiên đó."""
    row = stages.series.iloc[-1]
    rid = None if np.isnan(row["range_id"]) else int(row["range_id"])
    prior = None if pd.isna(row["prior_stage"]) else row["prior_stage"]
    label = next((r for r in stages.ranges if r.range_id == rid), None) if rid is not None else None
    return CurrentStage(
        date=stages.series.index[-1],
        stage=None if pd.isna(row["stage"]) else row["stage"],
        structure_type=row["structure_type"],
        since=stages.segments[-1].start_date if stages.segments else None,
        reason=row["reason"],
        prior_stage=prior,
        candidates=label.candidates if label is not None else (),
        range_id=rid,
    )
