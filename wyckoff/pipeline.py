"""Ghép các bước: chỉ báo -> swing -> range -> sự kiện -> pha."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from wyckoff.config import Config
from wyckoff.detectors.events import detect_selling_climax, detect_sos, detect_sos_reclaim, detect_spring
from wyckoff.detectors.distribution import detect_distribution
from wyckoff.detectors.lifecycle import annotate, annotate_distribution, snapshot
from wyckoff.detectors.models import Event, EventStatus, EventType, Swing, TradingRange
from wyckoff.detectors.structure import detect_ar, detect_lps, detect_ps, detect_st, detect_utad, sc_ar_anchors
from wyckoff.detectors.swings import find_swings
from wyckoff.detectors.trading_range import detect_trading_ranges
from wyckoff.indicators.core import add_indicators
from wyckoff.indicators.limits import add_limit_flags
from wyckoff.phases import CurrentPhase, PhaseResult, classify_phases, current_phase
from wyckoff.phases_distribution import CurrentDistributionPhase, classify_distribution_phases, current_distribution_phase
from wyckoff.stages import MARKDOWN, MARKUP, CurrentStage, StageResult, classify_stages, current_stage
from wyckoff.strength import TrendStrength, trend_strength


@dataclass
class AnalysisResult:
    df: pd.DataFrame
    swings: list[Swing]
    ranges: list[TradingRange]
    events: list[Event]
    phases: PhaseResult
    stages: StageResult
    cfg: Config
    candidates: list[Event] = field(default_factory=list)   # chưa/không xác nhận – không dùng cho pha/tin cậy
    distribution: list[Event] = field(default_factory=list) # BC, AR(d), ST(d), SOW, LPSY: chỉ ghi nhận, không dùng cho pha/tin cậy
    distribution_phases: PhaseResult | None = None          # pha theo sơ đồ phân phối, chạy song song, chỉ ghi nhận

    def structure_of(self) -> dict[str, int]:
        """event_id -> structure_id (cấu trúc của state machine pha)."""
        return {e.event_id: sid for sid, s in self.phases.structures.items() for e in s.events}

    def events_frame(self, include_candidates: bool = False) -> pd.DataFrame:
        sid = self.structure_of()
        rows = [{**e.to_dict(), "structure_id": sid.get(e.event_id)}
                for e in self.events + (self.candidates if include_candidates else [])]
        return pd.DataFrame(rows)

    def snapshot(self, t: int | str | pd.Timestamp | None = None) -> list[tuple[Event, EventStatus]]:
        """Event + candidate đã biết tại phiên t (mặc định phiên cuối) với trạng thái lúc đó."""
        i = len(self.df) - 1 if t is None else t if isinstance(t, int) else int(self.df.index.get_loc(pd.Timestamp(t)))
        return snapshot(self.events, self.candidates, i)

    def distribution_frame(self) -> pd.DataFrame:
        return pd.DataFrame([e.to_dict() for e in self.distribution])

    def ranges_frame(self) -> pd.DataFrame:
        return pd.DataFrame([r.__dict__ for r in self.ranges])

    def phases_frame(self) -> pd.DataFrame:
        return pd.DataFrame([s.__dict__ for s in self.phases.segments])

    def stages_frame(self) -> pd.DataFrame:
        return pd.DataFrame([s.__dict__ for s in self.stages.segments])

    def current(self) -> CurrentPhase:
        return current_phase(self.df, self.phases, self.cfg)

    def current_stage(self) -> CurrentStage:
        return current_stage(self.stages)

    def current_distribution_phase(self) -> CurrentDistributionPhase:
        return current_distribution_phase(self.distribution_phases)

    def distribution_phases_frame(self) -> pd.DataFrame:
        return pd.DataFrame([s.__dict__ for s in self.distribution_phases.segments])

    def trend_strength(self) -> TrendStrength | None:
        """Sức mạnh cung cầu tại phiên cuối; None khi không ở Markup / Markdown."""
        st = self.current_stage()
        if st.stage not in (MARKUP, MARKDOWN) or st.since is None:
            return None
        start = int(self.df.index.searchsorted(st.since))
        return trend_strength(self.df, self.swings, start, "up" if st.stage == MARKUP else "down", self.cfg.strength,
                              self.cfg.indicators.sma_period)

    def since(self, start: str | pd.Timestamp) -> "AnalysisResult":
        """Chỉ giữ phần từ `start` để báo cáo/vẽ. Phân tích đã chạy trên toàn bộ dữ liệu
        (gồm phần khởi động), nên chỉ báo, range và pha ở đầu kỳ đã đủ lịch sử."""
        ts = pd.Timestamp(start)
        ph = PhaseResult(
            series=self.phases.series.loc[ts:],
            segments=[g for g in self.phases.segments if g.end_date >= ts],
            structures=self.phases.structures,
        )
        kept = {r.range_id for r in self.ranges if r.end_date >= ts}
        st = StageResult(
            series=self.stages.series.loc[ts:],
            segments=[g for g in self.stages.segments if g.end_date >= ts],
            ranges=[r for r in self.stages.ranges if r.range_id in kept],
        )
        return AnalysisResult(
            df=self.df.loc[ts:],
            swings=[s for s in self.swings if s.date >= ts],
            ranges=[r for r in self.ranges if r.end_date >= ts],
            events=[e for e in self.events if e.date >= ts],
            phases=ph,
            stages=st,
            cfg=self.cfg,
            candidates=[e for e in self.candidates if e.date >= ts],
            distribution=[e for e in self.distribution if e.date >= ts],
            distribution_phases=PhaseResult(
                series=self.distribution_phases.series.loc[ts:],
                segments=[g for g in self.distribution_phases.segments if g.end_date >= ts],
                structures=self.distribution_phases.structures,
            ),
        )


def analyze(ohlcv: pd.DataFrame, cfg: Config | None = None) -> AnalysisResult:
    cfg = cfg or Config()
    df = add_limit_flags(add_indicators(ohlcv, cfg.indicators), cfg.data.price_limit, cfg.data.limit_tolerance,
                         cfg.data.exchange)
    swings = find_swings(df, cfg.swings)
    dec = cfg.indicators.ratio_decimals
    candidates: list[Event] = []
    sc_events = detect_selling_climax(
        df, cfg.sc, decimals=dec, price_limit=cfg.data.price_limit, limit_tolerance=cfg.data.limit_tolerance,
        candidates=candidates,
    )
    ar = detect_ar(df, sc_events, cfg.ar)
    anchors = sc_ar_anchors(sc_events, ar) if cfg.ranges.anchor_sc_ar else None
    ranges = detect_trading_ranges(df, swings, cfg.ranges, anchors)
    springs = detect_spring(df, ranges, cfg.spring, exchange=cfg.data.exchange, decimals=dec, candidates=candidates)
    sos = detect_sos(df, ranges, cfg.sos, decimals=dec, candidates=candidates) + detect_sos_reclaim(
        df, ranges, cfg.sos, window=cfg.phase.reclaim_window, decimals=dec, candidates=candidates
    )
    events = (
        sc_events + springs + sos + ar
        + detect_ps(df, sc_events, cfg.ps, decimals=dec)
        + detect_st(df, sc_events, ar, cfg.st)
        + detect_lps(df, ranges, sos, cfg.lps, decimals=dec)
        + detect_utad(df, ranges, cfg.utad, exchange=cfg.data.exchange, decimals=dec, candidates=candidates)
    )
    events.sort(key=lambda e: (e.idx, e.kind.value))
    events, candidates = annotate(df, events, candidates, ranges, cfg)
    phases = classify_phases(df, ranges, events, cfg.phase, cfg.ranges)
    stages = classify_stages(df, ranges, cfg.stage, cfg.indicators.sma_period)
    distribution = annotate_distribution(
        df, detect_distribution(df, ranges, cfg.distribution, dec, cfg.data.price_limit, cfg.data.limit_tolerance), ranges, cfg
    )
    return AnalysisResult(df=df, swings=swings, ranges=ranges, events=events, phases=phases, stages=stages, cfg=cfg,
                          candidates=candidates, distribution=distribution,
                          distribution_phases=classify_distribution_phases(df, ranges, distribution, events, cfg.phase))


__all__ = ["AnalysisResult", "analyze", "EventType"]
