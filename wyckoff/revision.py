"""Đánh giá lại nhãn bằng dữ liệu về sau: tiềm năng -> xác nhận -> bác bỏ.

Hai góc nhìn, không trộn lẫn:
- Nhật ký tại từng thời điểm: mỗi `Verdict.idx` là phiên thông tin đó đã biết, `status_at(t)` chỉ dùng dữ liệu <= t
  (trùng với trạng thái cuối khi chạy trên dữ liệu cắt tại t, xem tests/test_revision.py).
- Biểu đồ hồi cứu: dùng trạng thái cuối để sửa nhãn các phiên đã qua (`phase_segments`, `web.viewmodel.stage_segments`).

Lớp này CHỈ GHI NHẬN: `result.events`, `result.phases`, `result.stages`, điểm tin cậy và backtest không đọc từ đây.
Sự kiện theo định nghĩa mới (Spring kéo dài, SC, LPS) nằm riêng trong `RevisionResult.events`, không có điểm tin cậy.

Quy tắc (ngưỡng trong `RevisionConfig`, là khám phá trên mẫu H8, chưa phải kiểm định):
    Markdown (định nghĩa đầy đủ: docs/stage-definitions.md)
        tiềm năng tại phiên thoát xuống hoặc khi vào xu hướng giảm theo SMA50; xác nhận khi đủ cùng lúc 5 điều kiện:
        close dưới hỗ trợ, LH-LL sau khi thủng, nhịp hồi yếu, cung áp đảo cầu, không có cầu đủ mạnh.
        SOW, LPSY chỉ là sự kiện hỗ trợ; UT, UTAD thuộc Distribution, không phải điều kiện.
        Từ range: trước xác nhận close >= support -> bác bỏ; sau xác nhận close >= resistance hoặc SOS reclaim -> bác bỏ.
    Markup (định nghĩa đầy đủ: docs/stage-definitions.md) là trạng thái thị trường, không phải một sự kiện.
        Candidate: breakout khỏi range, cầu mở rộng, phá đỉnh cấu trúc. Developing: breakout duy trì, HH-HL, điều chỉnh yếu về cung.
        Confirmed: HH-HL qua nhiều nhịp, giữ hỗ trợ cấu trúc, cầu tiếp tục chiếm ưu thế. Sự kiện chỉ là bằng chứng.
        Từ range: close < support -> bác bỏ. Close quay lại dưới resistance chưa phải bác bỏ vì pullback sau breakout là bình thường.
    Markdown từ SMA50 (5 close liên tiếp)
        hỗ trợ là đáy swing gần nhất đã biết khi vào xu hướng; close qua lại SMA50 lúc vào xu hướng -> bác bỏ.
    Markup từ SMA50 (5 close liên tiếp)
        nền giá là range gần nhất đã kết thúc; không có nền thì chỉ là tiềm năng. Close dưới SMA50 lúc vào xu hướng -> bác bỏ.
    Xu hướng kết thúc mà chưa đủ điều kiện: giữ nguyên tiềm năng.
    Spring kéo dài
        range thoát xuống, trong 30 phiên có phiên close >= support + 1 tick với demand, Markdown chưa xác nhận.
        Sự kiện ở phiên close đầu tiên dưới support, xác nhận tại phiên demand. Volume và độ sâu khi thoát chỉ để mô tả.
        Đã có SC xác nhận tạo sau cú thủng -> không còn là Spring của range cũ.
    Spring hồi phục nhanh
        range đã thoát xuống, Markdown đang bị bác bỏ, chưa có range mới: low lại thủng support rồi trong 4 phiên có close >= support + 1 tick với demand.
        Không cần Test vì phiên hồi đã có demand. Close < đáy - 0,5 ATR -> bác bỏ.
    ST (định nghĩa đầy đủ: docs/event-definitions.md)
        ứng viên: sau SC + AR hoặc BC + AR, giá quay lại vùng cao trào với volume hoặc biên độ yếu hơn tương đối.
        xác nhận: không có áp lực tương đương cao trào, và giá phản ứng khỏi vùng kiểm tra.
        bác bỏ: xuyên sâu khỏi vùng, có áp lực tương đương cao trào, hoặc không có phản ứng. Chỉ bác bỏ lần ST đó, không làm mất cấu trúc.
    AR (định nghĩa đầy đủ: docs/event-definitions.md)
        ứng viên: sau SC hoặc BC, phản ứng ngược chiều với biên độ lớn, rời vùng cao trào tối thiểu 2 ATR. Volume không bắt buộc.
        xác nhận: nhịp phản ứng hoàn tất, tạo swing high (Accumulation) hoặc swing low (Distribution). Không cần ST.
        bác bỏ: mất vùng cao trào, hết thời gian mà chưa tạo swing, hoặc SC / BC bị bác bỏ.
    LPS (định nghĩa đầy đủ: docs/event-definitions.md)
        ứng viên: sau SOS hoặc SOS nội bộ, điều chỉnh về hỗ trợ, volume và biên độ giảm, hỗ trợ giữ hoặc chỉ thủng nhẹ.
        xác nhận: giá đảo chiều tăng vượt đỉnh phiên ứng viên, volume cao hơn phiên ứng viên (hoặc khóa trần).
        bác bỏ: close sâu quá 3% dưới hỗ trợ, quá 4 close liên tiếp dưới hỗ trợ, phiên giảm cung mạnh, khóa sàn, hoặc không có phản ứng.
    SC (định nghĩa đầy đủ: docs/event-definitions.md)
        ứng viên: bối cảnh giảm + biên độ giảm lớn + volume đột biến; hấp thụ cung cùng phiên là bằng chứng, không bắt buộc.
        xác nhận: giá không giảm đáng kể rồi phản ứng tăng mạnh, có AR, hoặc ổn định với volume giảm (chỉ khi có hấp thụ cùng phiên).
        bác bỏ: close thủng đáy ứng viên quá 1 ATR, hoặc hết hạn không có phản ứng. PS, AR, ST theo trạng thái của SC.
    Re-accumulation của range (định nghĩa đầy đủ: docs/stage-definitions.md)
        Candidate: có Markup trước đó (`_prior_markup`, dùng chung với Distribution), hình thành range, cấu trúc tăng chưa bị phá.
        Developing, Confirmed như Accumulation.
        Không mặc định Markup + range = Re-accumulation: `leaning` ghi nghiêng về Re-accumulation hay Distribution.
    Distribution của range (định nghĩa đầy đủ: docs/stage-definitions.md)
        Candidate: có Markup trước đó (`_prior_markup`), đà tăng yếu đi, cung xuất hiện. Developing: TR duy trì, nhịp tăng yếu, cung áp đảo, thất bại ở kháng cự.
        Confirmed: phá hỗ trợ có volume và spread xác nhận, LH-LL; không đồng nghĩa Markdown đã xác nhận. Sự kiện chỉ là bằng chứng.
    Accumulation của range (định nghĩa đầy đủ: docs/stage-definitions.md)
        Candidate: có Markdown trước đó, range hình thành, cung yếu đi. Developing: TR duy trì, hấp thụ cung, cầu tăng.
        Confirmed: SOS hoặc breakout, cầu chiếm ưu thế, giữ hỗ trợ hoặc có LPS, HH-HL. Sự kiện chỉ là bằng chứng.
    SOS (same_bar): tiềm năng tại breakout, xác nhận khi follow-through. Bác bỏ theo `lifecycle` sẵn có.
    UT/UTAD (mode v2): tiềm năng tại phiên vượt, xác nhận khi yếu dưới giữa range, close vượt đỉnh upthrust -> bác bỏ.
    Sự kiện khác: lấy từ lịch sử trạng thái sẵn có của `lifecycle`.
    Dải pha A đến E chỉ vẽ cho range đang là Accumulation; sự kiện chỉ định mốc khi có, xem `_accumulation_phases`.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import Config, RevisionConfig
from wyckoff.detectors.distribution import _bcs
from wyckoff.detectors.events import _candidate, _follow_through, _make_event, _rounded, floor_days
from wyckoff.detectors.lifecycle import base_event_id
from wyckoff.detectors.models import Event, EventStatus, EventType, StatusChange, Swing, TradingRange
from wyckoff.detectors.structure import _weakness, detect_ps
from wyckoff.detectors.swings import find_swings
from wyckoff.fmt import vn_g, vn_num, vn_ts
from wyckoff.indicators.ticks import tick_size
from wyckoff.phases import PhaseResult, PhaseSegment, _segments
from wyckoff.stages import MARKDOWN, MARKUP, StageResult

POTENTIAL = "potential"
CONFIRMED = "confirmed"
REJECTED = "rejected"
DEVELOPING = "developing"     # chỉ dùng cho Accumulation của range
PHASE_POTENTIAL = "potential"

STATUS_VN = {POTENTIAL: "tiềm năng", DEVELOPING: "đang hình thành", CONFIRMED: "xác nhận", REJECTED: "bác bỏ"}
_FROM_EVENT_STATUS = {
    EventStatus.DETECTED: POTENTIAL, EventStatus.CANDIDATE: POTENTIAL, EventStatus.CONFIRMED: CONFIRMED,
    EventStatus.INVALIDATED: REJECTED, EventStatus.REVISED: REJECTED,
}
_EPS = 1e-9


@dataclass(frozen=True)
class Verdict:
    status: str
    idx: int          # phiên trạng thái bắt đầu có hiệu lực (đã biết tại phiên này)
    date: pd.Timestamp
    reason: str = ""


def _final(history: tuple[Verdict, ...]) -> str:
    return history[-1].status


def _at(history: tuple[Verdict, ...], i: int) -> str | None:
    cur = None
    for v in history:
        if v.idx > i:
            break
        cur = v.status
    return cur


@dataclass(frozen=True)
class Condition:
    """Một điều kiện xác nhận Markdown, đánh giá tại một phiên bằng dữ liệu đến phiên đó."""
    key: str
    label: str
    met: bool
    detail: str


@dataclass(frozen=True)
class TrendHypothesis:
    """Một đoạn Markdown / Markup của `classify_stages`, kèm mức độ chắc chắn theo dữ liệu về sau."""
    stage: str
    source: str                   # range_exit | sma
    start_idx: int
    start_date: pd.Timestamp
    end_idx: int                  # phiên cuối của đoạn trong nhật ký
    end_date: pd.Timestamp
    range_id: int | None
    reference: float              # mốc đo khoảng cách xác nhận
    opposite: float | None        # biên đối diện của range
    history: tuple[Verdict, ...]
    conditions: tuple[Condition, ...] = ()   # điều kiện tại phiên xác nhận, hoặc phiên cuối đã xét
    supporting: tuple[str, ...] = ()         # Markdown: SOW, LPSY; Markup: SOS, LPS. Chỉ là sự kiện hỗ trợ
    state: str | None = None                 # Markup: Early, Established, Extended, Weakening; không phải pha Wyckoff

    @property
    def status(self) -> str:
        return _final(self.history)

    def status_at(self, i: int) -> str | None:
        return _at(self.history, i)

    @property
    def reason(self) -> str:
        return self.history[-1].reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage, "status": self.status, "source": self.source, "range_id": self.range_id,
            "since": f"{self.start_date:%Y-%m-%d}", "reason": self.reason, "reference": round(self.reference, 2),
            "conditions": [c.__dict__ for c in self.conditions], "supporting": list(self.supporting), "state": self.state,
            "history": [{"status": v.status, "date": f"{v.date:%Y-%m-%d}", "reason": v.reason} for v in self.history],
        }


@dataclass(frozen=True)
class RangeVerdict:
    """Mức Accumulation hoặc Re-accumulation của một range: tiềm năng (Candidate), developing, xác nhận, bác bỏ."""
    range_id: int
    structure_type: str           # Initial Accumulation | Accumulation | Re-accumulation
    start_idx: int
    end_idx: int                  # hồi cứu: phiên trước khi Markup bắt đầu, hoặc hết range / phiên xác nhận
    history: tuple[Verdict, ...]
    conditions: tuple[Condition, ...] = ()   # tại phiên xác nhận, hoặc phiên cuối đã xét
    supporting: tuple[str, ...] = ()         # sự kiện làm bằng chứng, không bắt buộc
    demand_idx: int | None = None            # phiên đầu tiên cầu bắt đầu kiểm soát, không cần SOS (mốc pha D)
    leaning: str | None = None               # chỉ với range sau Markup: Re-accumulation | Distribution | chưa rõ
    watch_end: pd.Timestamp | None = None    # phiên cuối còn đánh giá; sau đó `conditions` không còn cập nhật

    def active_on(self, date: pd.Timestamp) -> bool:
        return self.watch_end is None or date <= self.watch_end

    def evidence(self, rc: RevisionConfig) -> dict[str, Any]:
        """Độ đầy đủ của bằng chứng, không phải xác suất: tỷ lệ xác nhận theo mức này gần bằng dữ liệu xáo trộn (docs/stage-definitions.md)."""
        met, total = sum(c.met for c in self.conditions), len(self.conditions)
        ratio = met / total if total else 0.0
        level = "cao" if ratio >= rc.evidence_high else "trung bình" if ratio >= rc.evidence_medium else "thấp"
        return {"met": met, "total": total, "level": level}

    @property
    def is_reaccumulation(self) -> bool:
        return self.structure_type == "Re-accumulation"

    @property
    def is_distribution(self) -> bool:
        return self.structure_type == "Distribution"

    @property
    def status(self) -> str:
        return _final(self.history)

    def status_at(self, i: int) -> str | None:
        return _at(self.history, i)

    @property
    def label(self) -> str | None:
        """Tên hiển thị theo trạng thái; đã bác bỏ -> None."""
        return {CONFIRMED: self.structure_type, DEVELOPING: f"{self.structure_type} (đang hình thành)",
                POTENTIAL: f"{self.structure_type} (tiềm năng)"}.get(self.status)

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.status, "structure_type": self.structure_type, "label": self.label, "since": f"{self.history[0].date:%Y-%m-%d}",
                "reason": self.history[-1].reason, "conditions": [c.__dict__ for c in self.conditions], "supporting": list(self.supporting),
                "leaning": self.leaning}


@dataclass
class RevisionResult:
    hypotheses: list[TrendHypothesis]
    events: list[Event]                       # Spring kéo dài, Spring hồi phục nhanh, LPS, SC và PS / AR / ST của SC, đã từng xác nhận
    candidates: list[Event]                   # các trường hợp chưa / không xác nhận
    assessments: dict[str, tuple[Verdict, ...]]   # event_id -> lịch sử tiềm năng / xác nhận / bác bỏ
    phase_series: pd.DataFrame                # pha hồi cứu mỗi phiên
    phase_segments: list[PhaseSegment]
    labels: dict[str, str] = field(default_factory=dict)   # event_id -> tên hiển thị
    range_verdicts: dict[int, RangeVerdict] = field(default_factory=dict)
    distribution_verdicts: dict[int, RangeVerdict] = field(default_factory=dict)

    def primary_of(self, range_id: int | None) -> tuple[RangeVerdict | None, bool]:
        """Cấu trúc đại diện của range (Accumulation, Re-accumulation hoặc Distribution) và cờ đã phân định."""
        return _primary_verdict(self.range_verdicts.get(range_id), self.distribution_verdicts.get(range_id))

    def live_structure(self, range_id: int | None, date: pd.Timestamp) -> RangeVerdict | None:
        """Cấu trúc đại diện đã phân định, đang hình thành hoặc đã xác nhận, còn được đánh giá tại `date`."""
        v, decided = self.primary_of(range_id)
        return v if v is not None and decided and v.status in (DEVELOPING, CONFIRMED) and v.active_on(date) else None

    def market_view(self, range_id: int | None, in_range: bool, date: pd.Timestamp) -> dict[str, Any]:
        """Tách hai khái niệm: Market State (Accumulation, Markup, Distribution, Markdown) và Market Structure
        (Trading Range, Re-accumulation...). Re-accumulation là cấu trúc nằm trong trạng thái Markup."""
        live, decided = self.primary_of(range_id) if range_id is not None else (None, True)
        hyp = self.hypothesis_on(date)
        if in_range:
            if live is not None and not decided:
                return {"state": None, "structure": "Trading Range, chưa phân định Re-accumulation hay Distribution", "leaning": live.leaning}
            if live is not None and live.is_distribution:
                return {"state": "Distribution", "structure": "Trading Range", "leaning": live.leaning}
            if live is not None and live.is_reaccumulation:
                return {"state": MARKUP, "structure": live.label, "leaning": live.leaning}
            if live is not None:
                return {"state": "Accumulation", "structure": "Trading Range", "leaning": None}
            return {"state": None, "structure": "Trading Range", "leaning": None}
        if hyp is not None and hyp.status != REJECTED:
            return {"state": hyp.stage, "structure": None, "leaning": None}
        return {"state": None, "structure": None, "leaning": None}

    def accumulation_of(self, range_id: int | None) -> RangeVerdict | None:
        """Range đang được xác nhận là Accumulation theo dữ liệu đến phiên cuối (đã bác bỏ -> None)."""
        v = self.range_verdicts.get(range_id)
        return v if v is not None and v.status == CONFIRMED else None

    def status_of(self, e: Event) -> str:
        hist = self.assessments.get(e.event_id)
        return _final(hist) if hist else event_status(e)

    def hypothesis_of_range(self, range_id: int) -> TrendHypothesis | None:
        return next((h for h in self.hypotheses if h.range_id == range_id and h.source == "range_exit"), None)

    def hypothesis_on(self, date: pd.Timestamp) -> TrendHypothesis | None:
        return next((h for h in self.hypotheses if h.start_date <= date <= h.end_date), None)

    def changes(self, limit: int = 8) -> list[dict[str, Any]]:
        """Các lần nhãn được xác nhận hoặc bác bỏ gần nhất: xu hướng, sự kiện mới, và mọi sự kiện đã xác nhận rồi bị bác bỏ."""
        rows: list[tuple[pd.Timestamp, int, str, str, str]] = []
        for h in self.hypotheses:
            rows += [(v.date, v.idx, f"{h.stage} từ {vn_ts(h.start_date)}", v.status, v.reason)
                     for v in h.history if v.status != POTENTIAL or v.idx > h.start_idx]   # tiềm năng sau mốc đầu: giả thuyết được mở lại
        for rv in list(self.range_verdicts.values()) + list(self.distribution_verdicts.values()):
            rows += [(v.date, v.idx, f"TR#{rv.range_id} là {rv.structure_type}", v.status, v.reason) for v in rv.history]
        for e in self.events:
            rows += [(v.date, v.idx, f"{_event_name(e)} {vn_ts(e.date)}", v.status, v.reason)
                     for v in self.assessments.get(e.event_id, ()) if v.status != POTENTIAL]
        own = {e.event_id for e in self.events}
        for eid, hist in self.assessments.items():
            if eid in own or len(hist) < 2 or hist[-1].status != REJECTED or not any(v.status == CONFIRMED for v in hist):
                continue
            if hist[-1].reason.startswith("không đạt định nghĩa"):
                continue       # sự kiện của nhật ký không đạt định nghĩa mới: chưa từng là sự kiện đó, không phải một lần bác bỏ
            rows.append((hist[-1].date, hist[-1].idx, self.labels.get(eid, eid), REJECTED, hist[-1].reason))
        rows.sort(key=lambda r: (r[1], r[3]), reverse=True)
        return [{"date": f"{d:%Y-%m-%d}", "subject": s, "status": st, "reason": why} for d, _, s, st, why in rows[:limit]]


def event_status(e: Event) -> str:
    return _FROM_EVENT_STATUS[e.status]


def _event_name(e: Event) -> str:
    return {"extended": "Spring kéo dài", "quick": "Spring hồi phục nhanh"}.get(e.details.get("spring_type", ""), e.kind.value)


# ---------------------------------------------------------------- Markdown / Markup

class _MarkdownTest:
    """5 điều kiện xác nhận Markdown tại phiên t. `b`: phiên close đầu tiên dưới hỗ trợ. Chỉ dùng dữ liệu <= t."""

    def __init__(self, df: pd.DataFrame, swings: list[Swing], events: list[Event], cfg: Config) -> None:
        r = _rounded(df, cfg.indicators.ratio_decimals)
        self.rc = cfg.revision
        self.close = df["close"].to_numpy(dtype=float)
        self.open = df["open"].to_numpy(dtype=float)
        self.vr = r["vol_ratio"].to_numpy(dtype=float)
        self.spread = r["spread_atr"].to_numpy(dtype=float)
        self.cp = r["close_pos"].to_numpy(dtype=float)
        self.highs = sorted((s for s in swings if s.kind == "high"), key=lambda s: s.idx)
        self.lows = sorted((s for s in swings if s.kind == "low"), key=lambda s: s.idx)
        # confirmed_idx = idx + right nên cũng tăng dần: cắt bằng bisect thay vì lọc cả danh sách mỗi phiên
        self._high_conf = [s.confirmed_idx for s in self.highs]
        self._low_conf = [s.confirmed_idx for s in self.lows]
        self.sos_conf = sorted((e.confirmed_idx, e.date) for e in events if e.kind == EventType.SOS)
        self.cfg = cfg

    def _known_highs(self, t: int) -> list[Swing]:
        return self.highs[:bisect_right(self._high_conf, t)]

    def _known_lows(self, t: int) -> list[Swing]:
        return self.lows[:bisect_right(self._low_conf, t)]

    def last_low_before(self, t: int) -> float | None:
        known = self._known_lows(t)
        return known[-1].price if known else None

    def structure_ready(self, t: int, b: int | None, support: float) -> bool:
        """Lọc nhanh hai điều kiện đầu, tránh tính ba điều kiện còn lại ở mỗi phiên."""
        if b is None or self.close[t] >= support - _EPS:
            return False
        n_lh, seq_h = self._descending(self._known_highs(t), b)
        n_ll, _ = self._descending(self._known_lows(t), b)
        return n_lh >= self.rc.md_min_lower_highs and n_ll >= self.rc.md_min_lower_lows and self.close[t] <= seq_h[-1].price + _EPS

    def _descending(self, pivots: list[Swing], b: int) -> tuple[int, list[Swing]]:
        """Số pivot tạo từ phiên b trở đi, nếu cả chuỗi (kèm pivot ngay trước b) giảm dần; không giảm dần -> 0."""
        new = [s for s in pivots if s.idx >= b]
        before = [s for s in pivots if s.idx < b][-1:]
        seq = before + new
        ok = all(y.price < x.price - _EPS for x, y in zip(seq, seq[1:]))
        return (len(new) if ok else 0), seq

    def evaluate(self, t: int, b: int | None, support: float) -> tuple[Condition, ...]:
        c = self.close
        rc = self.rc
        if b is None:
            pending = "chưa có close dưới hỗ trợ"
            return (
                Condition("breakdown", "Phá vỡ hỗ trợ", False, f"chưa có close dưới {vn_num(support)}"),
                Condition("lh_ll", "Cấu trúc LH–LL", False, pending), Condition("weak_rally", "Nhịp hồi yếu", False, pending),
                Condition("supply", "Cung áp đảo cầu", False, pending), Condition("no_demand", "Không có cầu đủ mạnh", False, pending),
            )
        below = c[t] < support - _EPS
        breakdown = Condition("breakdown", "Phá vỡ hỗ trợ", bool(below),
                              f"close {vn_num(c[t])} so với hỗ trợ {vn_num(support)}, thủng từ {vn_num(c[b])}")
        highs = self._known_highs(t)
        lows = self._known_lows(t)
        n_lh, seq_h = self._descending(highs, b)
        n_ll, _ = self._descending(lows, b)
        last_high = seq_h[-1].price if n_lh else None
        intact = last_high is None or c[t] <= last_high + _EPS
        structure = Condition("lh_ll", "Cấu trúc LH–LL", n_lh >= rc.md_min_lower_highs and n_ll >= rc.md_min_lower_lows and intact,
                              f"{n_lh} đỉnh thấp hơn, {n_ll} đáy thấp hơn sau khi thủng" + ("" if intact else ", close đã vượt đỉnh gần nhất"))
        return breakdown, structure, self._weak_rally(highs, b, t), self._supply(b, t), self._no_demand(highs, b, t)

    def _weak_rally(self, highs: list[Swing], b: int, t: int) -> Condition:
        label = "Nhịp hồi yếu"
        new = [s for s in highs if s.idx >= b]
        prior = [s for s in highs if s.idx < new[0].idx][-1:] if new else []
        if not new or not prior:
            return Condition("weak_rally", label, False, "chưa có nhịp hồi hoàn tất sau khi thủng")
        peak = new[-1]
        top = ([s for s in highs if s.idx < peak.idx])[-1]
        c, vr = self.close, self.vr
        low_at = top.idx + 1 + int(np.argmin(c[top.idx + 1:peak.idx + 1]))
        if low_at >= peak.idx:
            return Condition("weak_rally", label, False, "chưa tách được nhịp giảm và nhịp hồi")
        drop = top.price - c[low_at]
        retrace = (peak.price - c[low_at]) / drop if drop > 0 else np.inf
        v_rally = float(np.nanmean(vr[low_at + 1:peak.idx + 1]))
        v_drop = float(np.nanmean(vr[top.idx + 1:low_at + 1]))
        met = retrace <= self.rc.md_max_retrace + _EPS and v_rally <= v_drop + _EPS and peak.price < top.price - _EPS
        return Condition("weak_rally", label, bool(met),
                         f"hồi {vn_g(round(retrace * 100, 1))}% nhịp giảm, volume nhịp hồi {vn_num(v_rally)}x so với nhịp giảm {vn_num(v_drop)}x")

    def _supply(self, b: int, t: int) -> Condition:
        label = "Cung áp đảo cầu"
        seg = np.arange(b, t + 1)
        down = seg[self.close[seg] < self.open[seg]]
        up = seg[self.close[seg] > self.open[seg]]
        if len(down) < self.rc.md_min_side_bars or len(up) < self.rc.md_min_side_bars:
            return Condition("supply", label, False, f"chưa đủ phiên để so sánh ({len(down)} giảm, {len(up)} tăng)")
        vd, vu = float(np.nanmean(self.vr[down])), float(np.nanmean(self.vr[up]))
        sd, su = float(np.nanmean(self.spread[down])), float(np.nanmean(self.spread[up]))
        return Condition("supply", label, bool(vd > vu + _EPS and sd > su + _EPS),
                         f"phiên giảm: volume {vn_num(vd)}x, biên độ {vn_num(sd)} ATR; phiên tăng: volume {vn_num(vu)}x, biên độ {vn_num(su)} ATR")

    def _no_demand(self, highs: list[Swing], b: int, t: int) -> Condition:
        label = "Không có cầu đủ mạnh"
        sos = next((d for i, d in self.sos_conf if b <= i <= t), None)
        if sos is not None:
            return Condition("no_demand", label, False, f"có SOS {vn_ts(sos)}")
        for i in range(b, t + 1):
            if not _is_demand(i, self.vr, self.cp, self.open, self.close, self.cfg):
                continue
            known = self._known_highs(i)
            if known and self.close[i] > known[-1].price + _EPS:
                return Condition("no_demand", label, False, f"phiên demand close {vn_num(self.close[i])} vượt đỉnh gần nhất")
        return Condition("no_demand", label, True, "không có SOS, không có phiên demand vượt đỉnh gần nhất")


class _SideStats:
    """Trung bình volume, biên độ của phiên tăng / phiên giảm trên đoạn [a, b], O(1) nhờ tổng tích lũy."""

    def __init__(self, df: pd.DataFrame, cfg: Config) -> None:
        r = _rounded(df, cfg.indicators.ratio_decimals)
        vr = np.nan_to_num(r["vol_ratio"].to_numpy(dtype=float))
        sa = np.nan_to_num(r["spread_atr"].to_numpy(dtype=float))
        o, c = df["open"].to_numpy(dtype=float), df["close"].to_numpy(dtype=float)
        self.min_bars = cfg.revision.md_min_side_bars
        self.tables: dict[tuple[str, str], np.ndarray] = {}
        for side, mask in (("up", c > o), ("down", c < o)):
            for what, values in (("n", np.ones(len(c))), ("vr", vr), ("sa", sa)):
                self.tables[(side, what)] = np.r_[0.0, np.cumsum(values * mask)]

    def mean(self, side: str, what: str, a: int, b: int) -> float | None:
        """Không đủ phiên -> None."""
        if a > b:
            return None
        n = self.tables[(side, "n")][b + 1] - self.tables[(side, "n")][a]
        return None if n < self.min_bars else float((self.tables[(side, what)][b + 1] - self.tables[(side, what)][a]) / n)


def _watch_stop(close: np.ndarray, x: int, support: float, resistance: float, window: int, limit: int) -> int:
    """Phiên cuối còn đánh giá range đã thoát xuống: `window` phiên kể từ phiên `x` hoặc phiên cuối close còn trong range.
    Giá còn trong range thì range còn được đánh giá. Chỉ dùng close đến phiên đang xét nên không nhìn trước."""
    deadline = x + window
    t = x
    while t <= min(deadline, limit):
        if support - _EPS <= close[t] <= resistance + _EPS:
            deadline = t + window
        t += 1
    return min(deadline, limit)


def _ascending_run(pivots: list[Swing], b: int) -> int:
    """Số pivot tăng dần liên tiếp tính từ pivot mới nhất, chỉ đếm pivot tạo từ phiên b trở đi, so với pivot ngay trước đó."""
    seq = [s for s in pivots if s.idx < b][-1:] + [s for s in pivots if s.idx >= b]
    run = 0
    for x, y in zip(reversed(seq[:-1]), reversed(seq[1:])):
        if y.price <= x.price + _EPS:
            break
        run += 1
    return run


class _MarkupTest:
    """Điều kiện Markup tại phiên t (docs/stage-definitions.md). `b`: phiên close đầu tiên trên kháng cự. Chỉ dùng dữ liệu <= t."""

    def __init__(self, df: pd.DataFrame, stats: _SideStats, cfg: Config) -> None:
        # Pivot ngắn hơn biên range: xu hướng tăng theo bậc thang có nhịp điều chỉnh ngắn, pivot dài bỏ sót các đỉnh, đáy đó
        k = cfg.revision.mk_pivot_bars
        swings = find_swings(df, replace(cfg.swings, left=k, right=k), source=cfg.ranges.pivot_source)
        self.c = df["close"].to_numpy(dtype=float)
        self.atr = df["atr"].to_numpy(dtype=float)
        self.stats = stats
        self.rc = cfg.revision
        self.window = cfg.revision.acc_window
        self.highs = sorted((s for s in swings if s.kind == "high"), key=lambda s: s.idx)
        self.lows = sorted((s for s in swings if s.kind == "low"), key=lambda s: s.idx)
        self._high_conf = [s.confirmed_idx for s in self.highs]
        self._low_conf = [s.confirmed_idx for s in self.lows]

    def known(self, t: int) -> tuple[list[Swing], list[Swing]]:
        return self.highs[:bisect_right(self._high_conf, t)], self.lows[:bisect_right(self._low_conf, t)]

    def evaluate(self, t: int, b: int | None, res: float | None, base: str | None) -> tuple[Condition, ...]:
        c, rc, st = self.c, self.rc, self.stats
        prior = Condition("prior_structure", "Có nền giá trước đó", base is not None, base or "chưa có Trading Range làm nền")
        if base is None or b is None or res is None:
            why = "chưa có nền giá" if base is None else f"chưa có close trên kháng cự {vn_num(res)}"
            return (prior, Condition("breakout", "Phá vỡ kháng cự", False, why))
        highs, lows = self.known(t)
        floor_b = res * (1 - rc.lps_max_depth)
        breakout = Condition("breakout", "Phá vỡ kháng cự", c[t] > floor_b - _EPS, f"từ close đầu tiên trên {vn_num(res)}, hiện {vn_num(c[t])}")
        a = max(b, t - self.window + 1)
        vu, vd, su, sd = st.mean("up", "vr", a, t), st.mean("down", "vr", a, t), st.mean("up", "sa", a, t), st.mean("down", "sa", a, t)
        text = "chưa đủ phiên tăng" if vu is None else (f"phiên tăng volume {vn_num(vu)}x, biên độ {vn_num(su)} ATR" + ("" if vd is None else f"; phiên giảm {vn_num(vd)}x, {vn_num(sd)} ATR"))
        expansion = Condition("demand", "Cầu mở rộng", bool(vu is not None and (vd is None or (vu >= vd - _EPS and su >= sd - _EPS))), text)
        before = [s.price for s in highs if s.idx < b]
        lh_ok = bool(before) and c[t] > before[-1] + _EPS
        breaks = Condition("breaks_lh", "Phá đỉnh cấu trúc trước đó", lh_ok, "chưa có đỉnh trước" if not before else f"đỉnh trước {vn_num(before[-1])}")
        low_b = c[b:t + 1].min()
        kept = Condition("maintained", "Breakout được duy trì", low_b >= floor_b - _EPS, f"close thấp nhất sau breakout {vn_num(low_b)}")
        n_hh, n_hl = _ascending_run(highs, b), _ascending_run(lows, b)
        pair = Condition("hh_hl", "Hình thành HH–HL", n_hh >= 1 and n_hl >= 1, f"{n_hh} đỉnh cao hơn, {n_hl} đáy cao hơn liên tiếp")
        supply = Condition("supply_weak", "Điều chỉnh yếu về cung", bool(vd is None or (vu is not None and vd <= vu + _EPS and sd <= su + _EPS)),
                           "rất ít phiên giảm" if vd is None else f"phiên giảm volume {vn_num(vd)}x, biên độ {vn_num(sd)} ATR")
        multi = Condition("hh_hl_multi", "HH–HL qua nhiều nhịp", n_hh >= rc.mk_min_swings and n_hl >= rc.mk_min_swings, f"cần tối thiểu {rc.mk_min_swings} đỉnh và {rc.mk_min_swings} đáy")
        last_low = lows[-1].price if lows and lows[-1].idx >= b else None
        holds = c[t] >= floor_b - _EPS and (last_low is None or c[t] >= last_low - _EPS)
        support = Condition("support", "Giữ hỗ trợ cấu trúc", bool(holds), "hỗ trợ " + vn_num(res if last_low is None else last_low))
        dominance = Condition("dominance", "Cầu tiếp tục chiếm ưu thế", bool(vu is not None and (vd is None or vu > vd + _EPS)), text)
        return prior, breakout, expansion, breaks, kept, pair, supply, multi, support, dominance

    def state(self, t: int, b: int | None, status: str) -> str | None:
        """Trạng thái vận động để phân tích, không phải pha Wyckoff. Chỉ có khi đã có breakout."""
        if b is None:
            return None
        if status not in (DEVELOPING, CONFIRMED):
            return "Early Markup"
        c, st = self.c, self.stats
        highs, lows = self.known(t)
        new_highs = [s for s in highs if s.idx >= b]
        lower_high = len(new_highs) >= 2 and new_highs[-1].price < new_highs[-2].price - _EPS
        lost_low = bool(lows) and lows[-1].idx >= b and c[t] < lows[-1].price - _EPS
        a = max(b, t - self.window + 1)
        vu, vd, su, sd = st.mean("up", "vr", a, t), st.mean("down", "vr", a, t), st.mean("up", "sa", a, t), st.mean("down", "sa", a, t)
        supply_up = None not in (vu, vd, su, sd) and vd > vu + _EPS and sd > su + _EPS
        if lower_high or lost_low or supply_up:
            return "Markup Weakening"
        if status != CONFIRMED:
            return "Early Markup"
        grown = not np.isnan(self.atr[b]) and self.atr[t] >= self.rc.mk_extended_atr * self.atr[b]
        return "Extended Markup" if t - b >= self.rc.mk_extended_bars or grown else "Established Markup"


def _trend_hypotheses(
    df: pd.DataFrame, stages: StageResult, ranges: list[TradingRange], events: list[Event], swings: list[Swing],
    distribution: list[Event], cfg: Config, later: list[Event] = (),
) -> list[TrendHypothesis]:
    rc = cfg.revision
    close = df["close"].to_numpy(dtype=float)
    sma = df["sma"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    dates = df.index
    last = len(df) - 1
    exit_at = {r.end_confirmed_idx: r for r in ranges if r.end_confirmed_idx is not None}
    reclaim_conf = {(e.range_id, e.confirmed_idx) for e in events if e.kind == EventType.SOS and e.details.get("reclaim")}
    md_test = _MarkdownTest(df, swings, events, cfg)
    mk_test = _MarkupTest(df, _SideStats(df, cfg), cfg)
    up_events = sorted((e for e in list(events) + list(later) if e.kind in (EventType.SOS, EventType.LPS)
                        and (e.kind != EventType.LPS or e.details.get("lps_definition"))), key=lambda e: e.confirmed_idx)
    support_events = sorted((e for e in distribution if e.kind in (EventType.SOW, EventType.LPSY)), key=lambda e: e.confirmed_idx)
    out: list[TrendHypothesis] = []
    for g in stages.segments:
        if g.stage not in (MARKDOWN, MARKUP) or g.range_id is not None:
            continue
        down = g.stage == MARKDOWN
        a, b = g.start_idx, g.end_idx
        rng = exit_at.get(a)
        from_range = rng is not None and rng.exit_direction == ("down" if down else "up")
        if from_range:
            ref, opp, rid = (rng.support, rng.resistance, rng.range_id) if down else (rng.resistance, rng.support, rng.range_id)
            opening = f"TR#{rid} thoát {'xuống' if down else 'lên'} {vn_ts(dates[a])}, chờ xác nhận"
        else:
            ref, opp, rid = (close[a] if np.isnan(sma[a]) else float(sma[a])), None, None
            opening = f"{g.stage} theo SMA từ {vn_ts(dates[a])}, chờ xác nhận"

        def rejected_before(t: int) -> str | None:
            if down and close[t] >= ref - _EPS:
                return f"close {vn_num(close[t])} quay lại {'support' if from_range else 'mốc SMA'} {vn_num(ref)}"
            if not down and from_range and close[t] < opp - _EPS:
                return f"close {vn_num(close[t])} thủng support {vn_num(opp)}"
            if not down and not from_range and close[t] < ref - _EPS:
                return f"close {vn_num(close[t])} dưới mốc SMA {vn_num(ref)}"
            return None

        def rejected_after(t: int) -> str | None:
            if not from_range or not down:
                return rejected_before(t)
            if close[t] >= opp - _EPS:
                return f"close {vn_num(close[t])} vượt resistance {vn_num(opp)}"
            if (rid, t) in reclaim_conf:
                return f"SOS reclaim {vn_ts(dates[t])}"
            return None

        # Markdown: hỗ trợ là support của range, hoặc đáy swing gần nhất đã biết khi vào xu hướng theo SMA
        support = (ref if from_range else md_test.last_low_before(a)) if down else None
        first_below: int | None = None
        if down and from_range:
            first_below = a
            while first_below > 0 and close[first_below - 1] < support - _EPS:
                first_below -= 1
        conditions: tuple[Condition, ...] = ()
        last_eval: int | None = None
        # Markup: nền giá là range vừa thoát lên, hoặc range gần nhất đã kết thúc khi vào xu hướng theo SMA
        base_rng = rng if not down and from_range else None
        if not down and base_rng is None:
            base_rng = next((r for r in reversed(ranges) if r.confirmed_idx < a and 0 <= a - r.end_idx <= rc.mk_base_lookback), None)
        base = None if base_rng is None else f"TR#{base_rng.range_id}, kháng cự {vn_num(base_rng.resistance)}"
        res_up = None if base_rng is None else base_rng.resistance
        # Breakout là close đầu tiên trên kháng cự kể từ khi range kết thúc, kể cả khi xu hướng trong nhật ký bắt đầu muộn hơn
        above: int | None = None
        if res_up is not None:
            above = next((j for j in range(base_rng.end_idx, a + 1) if close[j] > res_up + _EPS), None)
        mk_level = POTENTIAL

        hist = [Verdict(POTENTIAL, a, dates[a], opening)]
        conf: int | None = None
        waiting_exit = False     # Markdown từ range đã bị bác bỏ: chờ lần thủng tiếp theo
        exit_run = 0
        for t in range(a, last + 1):
            if waiting_exit:
                if t > b:
                    break
                # Thủng lại theo cùng tiêu chí thoát range: mở lại giả thuyết, đo lại từ cú thủng này
                exit_run = exit_run + 1 if close[t] < ref - cfg.ranges.exit_atr * atr[t] else 0
                if exit_run >= cfg.ranges.exit_bars:
                    waiting_exit = False
                    first_below = t
                    while first_below > 0 and close[first_below - 1] < support - _EPS:
                        first_below -= 1
                    hist.append(Verdict(POTENTIAL, t, dates[t], f"close thủng lại support {vn_num(ref)} {cfg.ranges.exit_bars} phiên liên tiếp, chờ xác nhận"))
                continue
            if conf is None:
                if t > b:
                    break
                why = rejected_before(t) if t > a else None
                if why:
                    hist.append(Verdict(REJECTED, t, dates[t], why))
                    if down and from_range:
                        waiting_exit, exit_run = True, 0
                        continue
                    break
                if down:
                    if support is None:
                        continue
                    if first_below is None and close[t] < support - _EPS:
                        first_below = t
                    last_eval = t
                    if md_test.structure_ready(t, first_below, support):
                        conditions = md_test.evaluate(t, first_below, support)
                        if all(x.met for x in conditions):
                            conf = t
                            hist.append(Verdict(CONFIRMED, t, dates[t], "đủ 5 điều kiện: thủng hỗ trợ, LH–LL, hồi yếu, cung áp đảo, không có cầu đủ mạnh"))
                else:
                    if above is None and res_up is not None and close[t] > res_up + _EPS:
                        above = t
                    last_eval = t
                    conditions = mk_test.evaluate(t, above, res_up, base)
                    met = {x.key: x.met for x in conditions}
                    if len(conditions) > 2:
                        if met["prior_structure"] and met["maintained"] and met["hh_hl_multi"] and met["support"] and met["dominance"]:
                            conf = t
                            hist.append(Verdict(CONFIRMED, t, dates[t], "HH–HL qua nhiều nhịp, giữ hỗ trợ cấu trúc, cầu tiếp tục chiếm ưu thế"))
                        elif mk_level == POTENTIAL and met["breakout"] and met["maintained"] and met["hh_hl"] and met["supply_weak"]:
                            mk_level = DEVELOPING
                            hist.append(Verdict(DEVELOPING, t, dates[t], "breakout được duy trì, có HH–HL, điều chỉnh yếu về cung"))
            else:
                if t > conf + rc.trend_watch_bars:
                    break
                why = rejected_after(t) if t > conf else None
                if why:
                    hist.append(Verdict(REJECTED, t, dates[t], why))
                    break
        if down and conf is None and last_eval is not None:
            conditions = md_test.evaluate(last_eval, first_below, support)
        pool = support_events if down else up_events
        supporting = tuple(f"{e.kind.value} {vn_ts(e.date)}" for e in pool if a <= e.confirmed_idx <= b)
        state = None if down or hist[-1].status == REJECTED else mk_test.state(min(b, last), above, hist[-1].status)
        out.append(TrendHypothesis(g.stage, "range_exit" if from_range else "sma", a, dates[a], b, dates[b], rid,
                                   float(ref), None if opp is None else float(opp), tuple(hist), conditions, supporting, state))
    return out


# ----------------------------------------------------------------- Sự kiện mới

def _is_demand(i: int, vr: np.ndarray, cp: np.ndarray, o: np.ndarray, c: np.ndarray, cfg: Config) -> bool:
    rc = cfg.revision
    return bool(vr[i] >= rc.demand_min_vol_ratio and cp[i] >= rc.demand_min_close_pos and c[i] > o[i])


def _first_close_below(close: np.ndarray, start: int, watch: int, level_fn: Any) -> int | None:
    for t in range(start + 1, min(start + watch, len(close) - 1) + 1):
        lv = level_fn(t)
        if not np.isnan(lv) and close[t] < lv - _EPS:
            return t
    return None


def _lps_break(close: np.ndarray, res: float, start: int, watch: int, cfg: Config) -> tuple[int, str] | None:
    """LPS đã xác nhận bị bác bỏ khi close sâu quá `lps_max_depth` dưới resistance, hoặc quá `lps_max_bars` close liên tiếp dưới resistance."""
    rc = cfg.revision
    run = 0
    for t in range(start + 1, min(start + watch, len(close) - 1) + 1):
        if close[t] >= res - _EPS:
            run = 0
            continue
        run += 1
        if (res - close[t]) / res > rc.lps_max_depth + _EPS:
            return t, f"close {vn_num(close[t])} sâu hơn {vn_g(rc.lps_max_depth * 100)}% dưới resistance {vn_num(res)}"
        if run > rc.lps_max_bars:
            return t, f"quá {rc.lps_max_bars} close liên tiếp dưới resistance {vn_num(res)}"
    return None


def _extended_springs(
    df: pd.DataFrame, ranges: list[TradingRange], hyps: list[TrendHypothesis], scs: list[Event], cfg: Config
) -> tuple[list[Event], list[Event]]:
    rc = cfg.revision
    r_ = _rounded(df, cfg.indicators.ratio_decimals)
    vr, cp = r_["vol_ratio"].to_numpy(dtype=float), r_["close_pos"].to_numpy(dtype=float)
    o, c, low = (df[k].to_numpy(dtype=float) for k in ("open", "close", "low"))
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    last = len(df) - 1
    dates = df.index
    range_conf = [r.confirmed_idx for r in ranges]
    rng_by_id = {r.range_id: r for r in ranges}
    events: list[Event] = []
    candidates: list[Event] = []
    for h in hyps:
        if h.stage != MARKDOWN or h.source != "range_exit":
            continue
        rng = rng_by_id[h.range_id]
        x, sup = h.start_idx, rng.support
        tick = tick_size(sup, cfg.data.exchange)
        conf_md = next((v.idx for v in h.history if v.status == CONFIRMED), None)
        b = x
        while b > 0 and c[b - 1] < sup:
            b -= 1
        limit = min(x + rc.spring_window, last)
        next_range = min((q for q in range_conf if q > x), default=last + 1)
        end_reason = f"không có phiên demand trong {rc.spring_window} phiên"
        found = None
        ended_at = limit if x + rc.spring_window <= last else None
        # SC mới tạo sau cú thủng: giá đã sang cấu trúc mới, cú thủng không còn là Spring của range cũ
        later_scs = sorted((s for s in scs if s.idx > b), key=lambda s: s.confirmed_idx)

        def new_sc_at(j: int) -> Event | None:
            return next((s for s in later_scs if s.confirmed_idx <= j and (s.invalidated is None or s.invalidated.idx > j)), None)

        for t in range(x + 1, limit + 1):
            if t >= next_range:
                ended_at, end_reason = t, "range mới đã xác nhận"
                break
            if conf_md is not None and t >= conf_md:
                ended_at, end_reason = t, "Markdown đã xác nhận"
                break
            sc_new = new_sc_at(t)
            if sc_new is not None:
                ended_at, end_reason = t, f"đã có SC mới {vn_ts(sc_new.date)}: cấu trúc mới, không phải Spring của range cũ"
                break
            if c[t] >= sup + cfg.spring.recovery_min_ticks * tick - _EPS and _is_demand(t, vr, cp, o, c, cfg):
                found = t
                break
        stop = found if found is not None else x
        below = c[b:stop + 1] < sup
        details: dict[str, Any] = {
            "spring_type": "extended", "support": round(sup, 4), "exit_date": f"{dates[x]:%Y-%m-%d}",
            "lowest_low": float(low[b:stop + 1].min()),
            "penetration_atr": round(float((sup - low[b:stop + 1].min()) / atr_ref[x]), 3),
            "depth_close_pct": round(float((sup - c[b:stop + 1].min()) / sup * 100), 2),
            "bars_below_support": int(below.sum()),
            "mean_vol_ratio_below_support": round(float(np.nanmean(vr[b:stop + 1][below])), 3) if below.any() else None,
            "max_vol_ratio_below_support": round(float(np.nanmax(vr[b:stop + 1][below])), 3) if below.any() else None,
        }
        weak = details["mean_vol_ratio_below_support"] is not None and details["mean_vol_ratio_below_support"] < rc.weak_break_vol_ratio
        details["breakdown"] = "yếu" if weak else "mạnh"
        pending = StatusChange(EventStatus.CANDIDATE, x, dates[x], "thoát xuống, chờ demand quay lại")
        if found is None:
            hist = [pending] + ([StatusChange(EventStatus.INVALIDATED, ended_at, dates[ended_at], end_reason)] if ended_at is not None else [])
            candidates.append(_candidate(df, EventType.SPRING, b, h.range_id, details, hist))
            continue
        details.update({"recovery_date": f"{dates[found]:%Y-%m-%d}", "recovery_close": float(c[found]),
                        "recovery_vol_ratio": float(vr[found]), "recovery_close_pos": float(cp[found])})
        e = _make_event(df, EventType.SPRING, b, found, h.range_id, details)
        hist = [pending, StatusChange(EventStatus.CONFIRMED, found, dates[found], "close quay lại trên support với demand")]
        k = cfg.phase.spring_invalid_atr
        spring_low = details["lowest_low"]
        t = _first_close_below(c, found, cfg.lifecycle.watch_bars, lambda j: spring_low - k * atr_ref[j])
        # SC tạo trước phiên hồi nhưng xác nhận sau đó cũng làm mất Spring
        late_sc = next((s for s in later_scs if s.idx <= found and s.confirmed_idx > found), None)
        if late_sc is not None and (t is None or late_sc.confirmed_idx < t):
            hist.append(StatusChange(EventStatus.INVALIDATED, late_sc.confirmed_idx, dates[late_sc.confirmed_idx],
                                     f"SC mới {vn_ts(late_sc.date)} đã xác nhận: cấu trúc mới, không phải Spring của range cũ"))
        elif t is not None:
            hist.append(StatusChange(EventStatus.INVALIDATED, t, dates[t], f"close {vn_num(c[t])} < đáy Spring {vn_num(spring_low)} - {vn_g(k)} ATR"))
        events.append(replace(e, history=tuple(hist)))
    return events, candidates


def _quick_springs(
    df: pd.DataFrame, ranges: list[TradingRange], hyps: list[TrendHypothesis], scs: list[Event], cfg: Config
) -> list[Event]:
    """Spring hồi phục nhanh: giá đã thoát xuống rồi quay lại range (Markdown đang bị bác bỏ), low lại thủng support,
    và trong `spring_quick_bars` phiên, tính cả phiên thủng, có close trên support với demand. Bộ nhận diện của nhật ký không xét
    trường hợp này vì range đã kết thúc. Không có demand thì không phải Spring. Chỉ dùng dữ liệu đến phiên đang xét."""
    rc = cfg.revision
    r_ = _rounded(df, cfg.indicators.ratio_decimals)
    vr, cp = r_["vol_ratio"].to_numpy(dtype=float), r_["close_pos"].to_numpy(dtype=float)
    o, c, low = (df[k].to_numpy(dtype=float) for k in ("open", "close", "low"))
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    last = len(df) - 1
    dates = df.index
    range_conf = [r.confirmed_idx for r in ranges]
    rng_by_id = {r.range_id: r for r in ranges}
    events: list[Event] = []
    for h in hyps:
        if h.stage != MARKDOWN or h.source != "range_exit":
            continue
        first_rej = next((v.idx for v in h.history if v.status == REJECTED), None)
        if first_rej is None:
            continue
        rng = rng_by_id[h.range_id]
        sup, res = rng.support, rng.resistance
        tick = tick_size(sup, cfg.data.exchange)
        conf_md = next((v.idx for v in h.history if v.status == CONFIRMED), None)
        next_range = min((q for q in range_conf if q > h.start_idx), default=last + 1)
        limit = _watch_stop(c, h.start_idx, sup, res, rc.spring_window, min(last, next_range - 1, h.end_idx))

        def pen(j: int) -> float:
            return max(cfg.spring.min_penetration_atr * atr_ref[j], cfg.spring.min_penetration_ticks * tick)

        b = first_rej + 1
        while b <= limit:
            if not (low[b] < sup - pen(b) - _EPS and low[b - 1] >= sup - pen(b - 1) - _EPS and h.status_at(b - 1) == REJECTED):
                b += 1
                continue
            later_scs = [s for s in scs if s.idx >= b]
            found = None
            for k in range(b, min(b + rc.spring_quick_bars, limit + 1)):
                if (conf_md is not None and k >= conf_md) or any(s.confirmed_idx <= k and (s.invalidated is None or s.invalidated.idx > k) for s in later_scs):
                    break
                if c[k] >= sup + cfg.spring.recovery_min_ticks * tick - _EPS and _is_demand(k, vr, cp, o, c, cfg):
                    found = k
                    break
            if found is None:
                b += 1
                continue
            below = c[b:found + 1] < sup
            spring_low = float(low[b:found + 1].min())
            details: dict[str, Any] = {
                "spring_type": "quick", "support": round(sup, 4), "exit_date": f"{dates[h.start_idx]:%Y-%m-%d}",
                "lowest_low": spring_low,
                "penetration_atr": round(float((sup - spring_low) / atr_ref[b]), 3),
                "bars_below_support": int(below.sum()),
                "max_vol_ratio_below_support": round(float(np.nanmax(vr[b:found + 1][below])), 3) if below.any() else None,
                "recovery_date": f"{dates[found]:%Y-%m-%d}", "recovery_bars": found - b + 1, "recovery_close": float(c[found]),
                "recovery_vol_ratio": float(vr[found]), "recovery_close_pos": float(cp[found]),
            }
            e = _make_event(df, EventType.SPRING, b, found, h.range_id, details)
            hist = [StatusChange(EventStatus.CANDIDATE, b, dates[b], "low lại thủng support, chờ hồi với demand"),
                    StatusChange(EventStatus.CONFIRMED, found, dates[found], "close quay lại trên support với demand")]
            atr_k = cfg.phase.spring_invalid_atr
            t = _first_close_below(c, found, cfg.lifecycle.watch_bars, lambda j: spring_low - atr_k * atr_ref[j])
            late_sc = next((s for s in later_scs if s.idx <= found and s.confirmed_idx > found), None)
            if late_sc is not None and (t is None or late_sc.confirmed_idx < t):
                hist.append(StatusChange(EventStatus.INVALIDATED, late_sc.confirmed_idx, dates[late_sc.confirmed_idx],
                                         f"SC mới {vn_ts(late_sc.date)} đã xác nhận: cấu trúc mới, không phải Spring của range cũ"))
            elif t is not None:
                hist.append(StatusChange(EventStatus.INVALIDATED, t, dates[t], f"close {vn_num(c[t])} < đáy Spring {vn_num(spring_low)} - {vn_g(atr_k)} ATR"))
            events.append(replace(e, history=tuple(hist)))
            b = found + 1
    return events


def _lps_strengths(
    df: pd.DataFrame, ranges: list[TradingRange], events: list[Event], swings: list[Swing], cfg: Config
) -> list[dict[str, Any]]:
    """Sức mạnh cầu làm nền cho LPS: SOS, và SOS nội bộ: trong range, nến có tiêu chí SOS đóng cửa vượt đỉnh swing gần nhất
    nhưng chưa tới resistance. Mức hỗ trợ là resistance đã vượt, hoặc đỉnh swing đã vượt."""
    res_by = {r.range_id: r.resistance for r in ranges}
    out = [{"idx": e.idx, "conf": e.confirmed_idx, "support": res_by[e.range_id], "range_id": e.range_id, "kind": "SOS",
            "details": {"sos_date": f"{e.date:%Y-%m-%d}"}, "date": e.date}
           for e in events if e.kind == EventType.SOS and e.range_id in res_by]
    if not cfg.revision.lps_internal_strength:
        return sorted(out, key=lambda s: s["conf"])
    r_ = _rounded(df, cfg.indicators.ratio_decimals)
    vr, cp, sa = (r_[k].to_numpy(dtype=float) for k in ("vol_ratio", "close_pos", "spread_atr"))
    o, c = df["open"].to_numpy(dtype=float), df["close"].to_numpy(dtype=float)
    dates = df.index
    last = len(df) - 1
    highs = sorted((s for s in swings if s.kind == "high"), key=lambda s: s.idx)
    conf_idx = [s.confirmed_idx for s in highs]
    sos_idx = {s["idx"] for s in out}
    sc = cfg.sos
    for rng in ranges:
        end = rng.end_confirmed_idx if rng.end_confirmed_idx is not None else last
        prev = -10**9
        for i in range(rng.confirmed_idx + 1, end + 1):
            if not (c[i] > o[i] and sa[i] > sc.min_spread_atr and vr[i] > sc.min_vol_ratio and cp[i] >= sc.min_close_pos):
                continue
            known = highs[:bisect_right(conf_idx, i)]
            if not known or i in sos_idx or i - prev < cfg.revision.lps_window:
                continue
            level = known[-1].price
            if level + _EPS < c[i] <= rng.resistance + _EPS:
                out.append({"idx": i, "conf": i, "support": float(level), "range_id": rng.range_id, "kind": "SOS nội bộ",
                            "details": {"strength_date": f"{dates[i]:%Y-%m-%d}"}, "date": dates[i]})
                prev = i
    return sorted(out, key=lambda s: s["conf"])


def _lps_events(
    df: pd.DataFrame, ranges: list[TradingRange], events: list[Event], swings: list[Swing], cfg: Config
) -> tuple[list[Event], list[Event]]:
    """LPS theo định nghĩa 05/11/2026 (docs/event-definitions.md): (đã từng xác nhận, ứng viên chưa / không xác nhận).
    Mỗi nền sức mạnh tối đa một LPS. Mọi điều kiện tại t chỉ dùng dữ liệu <= t."""
    rc = cfg.revision
    r_ = _rounded(df, cfg.indicators.ratio_decimals)
    vr, cp, sa = (r_[k].to_numpy(dtype=float) for k in ("vol_ratio", "close_pos", "spread_atr"))
    o, h, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "close"))
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    floor_locked = df["floor_locked"].to_numpy(dtype=bool)
    ceiling_locked = df["ceiling_locked"].to_numpy(dtype=bool)
    value_bn = (df["vol_ma"] * df["close"] * 1000 / 1e9).to_numpy(dtype=float)    # giá trị giao dịch TB20, tỷ đồng
    dates = df.index
    last = len(df) - 1
    out: list[Event] = []
    cands: list[Event] = []
    seen: set[tuple[int, int]] = set()
    for st in _lps_strengths(df, ranges, events, swings, cfg):
        sup = float(st["support"])
        if sup <= 0:
            continue
        peak = st["idx"]
        pull: int | None = None
        cand: int | None = None
        first: int | None = None
        run = 0
        conf: int | None = None
        fail: tuple[int, str] | None = None
        for t in range(st["conf"] + 1, last + 1):
            if cand is not None:
                if c[t] > h[cand] + _EPS and c[t] > o[t] and cp[t] >= rc.demand_min_close_pos and (ceiling_locked[t] or vr[t] > vr[cand] + _EPS):
                    conf = t
                    break
                if t - cand > rc.lps_confirm_bars:
                    fail = t, f"không có phản ứng tăng từ cầu trong {rc.lps_confirm_bars} phiên"
                    break
            if c[t] >= c[peak] - _EPS:
                if cand is not None:
                    fail = t, "vượt đỉnh nhưng chưa thấy cầu quay lại"
                    break
                peak, pull = t, None
                if t > st["idx"] + rc.lps_window:
                    break
                continue
            if pull is None:
                if t > st["idx"] + rc.lps_window:
                    break
                pull = t
            run = run + 1 if c[t] < sup - _EPS else 0
            if (sup - c[t]) / sup > rc.lps_max_depth + _EPS:
                fail = t, f"close {vn_num(c[t])} sâu hơn {vn_g(rc.lps_max_depth * 100)}% dưới hỗ trợ {vn_num(sup)}"
                break
            if run > rc.lps_max_bars:
                fail = t, f"quá {rc.lps_max_bars} close liên tiếp dưới hỗ trợ {vn_num(sup)}"
                break
            if floor_locked[t]:
                fail = t, "phiên khóa sàn: volume thấp không phản ánh cung yếu"
                break
            if c[t] < o[t] and vr[t] >= rc.lps_supply_vol_ratio and sa[t] >= rc.lps_supply_spread_atr:
                fail = t, f"phiên giảm volume {vn_num(vr[t])}x, biên độ {vn_num(sa[t])} ATR: cung còn mạnh"
                break
            if t == pull or np.isnan(atr_ref[t]) or value_bn[t] < rc.lps_min_value_bn:
                continue
            near = c[t] <= sup + rc.lps_near_atr * atr_ref[t] + _EPS and c[peak] - c[t] >= cfg.lps.min_pullback_atr * atr_ref[t] - _EPS
            weaker = vr[t] < np.nanmean(vr[pull:t]) - _EPS and sa[t] < np.nanmean(sa[pull:t]) - _EPS
            below_rally = np.nanmean(vr[pull:t + 1]) < np.nanmean(vr[st["idx"]:peak + 1]) - _EPS
            # Đáy phiên đủ điều kiện được dời xuống phiên thấp hơn: LPS là điểm cung yếu nhất ở vùng hỗ trợ
            if near and weaker and below_rally and (cand is None or c[t] < c[cand] - _EPS):
                first = t if first is None else first
                cand = t
        if cand is None or (st["range_id"], cand) in seen:
            continue
        seen.add((st["range_id"], cand))
        details = {
            "lps_definition": "candidate_confirmed", "strength": st["kind"], **st["details"], "support_level": round(sup, 4),
            "resistance": round(sup, 4), "pullback_mean_vol_ratio": round(float(np.nanmean(vr[pull:cand + 1])), 3),
            "depth_close_pct": round(max(float((sup - c[pull:cand + 1].min()) / sup * 100), 0.0), 2),
        }
        pending = StatusChange(EventStatus.CANDIDATE, first, dates[first], f"điều chỉnh về hỗ trợ {vn_num(sup)}, volume và biên độ giảm, chờ cầu quay lại")
        if conf is None:
            hist = [pending] + ([StatusChange(EventStatus.INVALIDATED, fail[0], dates[fail[0]], fail[1])] if fail else [])
            cands.append(_candidate(df, EventType.LPS, cand, st["range_id"], details, hist))
            continue
        details.update({"demand_date": f"{dates[conf]:%Y-%m-%d}", "demand_vol_ratio": float(vr[conf]), "demand_close_pos": float(cp[conf]),
                        "demand_ceiling_locked": bool(ceiling_locked[conf])})
        hist = [pending, StatusChange(EventStatus.CONFIRMED, conf, dates[conf], f"close {vn_num(c[conf])} đảo chiều tăng, volume cao hơn phiên LPS")]
        broke = _lps_break(c, sup, conf, cfg.lifecycle.watch_bars, cfg)
        if broke is not None:
            hist.append(StatusChange(EventStatus.INVALIDATED, broke[0], dates[broke[0]], broke[1]))
        out.append(replace(_make_event(df, EventType.LPS, cand, conf, st["range_id"], details), history=tuple(hist)))
    return out, cands


def _log_lps_assessments(
    df: pd.DataFrame, events: list[Event], lps: list[Event], lps_others: list[Event], assessments: dict[str, tuple[Verdict, ...]]
) -> dict[str, tuple[Verdict, ...]]:
    """LPS của nhật ký đánh giá lại theo định nghĩa mới: cùng phiên -> lấy trạng thái LPS mới; không đạt -> bác bỏ."""
    out = dict(assessments)
    by_idx = {(e.range_id, e.idx): e for e in lps_others + lps}
    dates = df.index
    for e in events:
        if e.kind != EventType.LPS:
            continue
        match = by_idx.get((e.range_id, e.idx))
        out[e.event_id] = _from_history(match) if match is not None else (
            Verdict(CONFIRMED, e.confirmed_idx, dates[e.confirmed_idx], "theo quy tắc nhật ký"),
            Verdict(REJECTED, e.confirmed_idx, dates[e.confirmed_idx], "không đạt định nghĩa LPS: thiếu vị trí, volume, biên độ hoặc phản ứng của cầu"))
    return out


def _selling_climaxes(df: pd.DataFrame, stages: StageResult, cfg: Config) -> tuple[list[Event], list[Event]]:
    """SC theo định nghĩa 05/11/2026: (đã từng xác nhận, ứng viên chưa / không xác nhận). Mọi điều kiện tại t chỉ dùng dữ liệu <= t."""
    rc, sc = cfg.revision, cfg.sc
    dec = cfg.indicators.ratio_decimals
    r = _rounded(df, dec)
    width = ((df["tr"] / df["atr_ref"]).round(dec) if sc.spread_measure == "true_range" else r["spread_atr"]).to_numpy(dtype=float)
    o, h, lo, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    vr, cp = r["vol_ratio"].to_numpy(dtype=float), r["close_pos"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    sma = df["sma"].to_numpy(dtype=float)
    dates = df.index
    last = len(df) - 1
    max_close = df["close"].rolling(sc.trend_lookback, min_periods=sc.trend_lookback).max().to_numpy(dtype=float)
    lowest = df["low"].rolling(sc.lowest_low_lookback, min_periods=sc.lowest_low_lookback).min().to_numpy(dtype=float)
    floors = floor_days(df, cfg.data.price_limit, cfg.data.limit_tolerance).astype(int)
    floor_count = floors.shift(1).rolling(sc.floor_chain_window, min_periods=1).sum().to_numpy(dtype=float)
    stage = stages.series["stage"].to_numpy(dtype=object)
    slope = cfg.stage.slope_bars

    stubs: list[Event] = []
    for i in range(1, len(df)):
        if np.isnan(max_close[i]) or np.isnan(lowest[i]) or np.isnan(sma[i]) or np.isnan(atr_ref[i]):
            continue
        decline = 1 - c[i] / max_close[i]
        falling = i >= slope and sma[i] < sma[i - slope]
        prior = decline >= sc.min_decline and lo[i] <= lowest[i] and (not sc.require_below_sma or c[i] < sma[i]) \
            and (stage[i] == MARKDOWN or falling)
        wide = width[i] > sc.min_spread_atr and c[i] < c[i - 1]
        chain = floor_count[i] >= sc.floor_chain_min_days and cp[i] >= sc.min_close_pos
        if not prior or vr[i] <= sc.min_vol_ratio or not (wide or chain):
            continue
        span = h[i] - lo[i]
        wick = (min(o[i], c[i]) - lo[i]) / span if span > 0 else 0.0
        absorbed = bool(cp[i] >= sc.min_close_pos or wick >= 1 / 3)
        stubs.append(_make_event(df, EventType.SC, i, i, None, {
            "sc_definition": "candidate_confirmed", "form": "wide_spread" if wide else "floor_chain",
            "decline_from_high": round(float(decline), 4), "width_atr": float(width[i]), "lower_wick": round(float(wick), 3),
            "absorption": "cùng phiên" if absorbed else "chờ phản ứng", "floor_days_before": int(floor_count[i]),
        }))
    ar_conf = {f"{dates[r['parent'].idx]:%Y-%m-%d}": r["conf"] for r in _ar_reactions(df, stubs, "up", cfg) if r["conf"] is not None}

    confirmed: list[Event] = []
    others: list[Event] = []
    prev: tuple[int, float, int | None, int | None] | None = None   # phiên, đáy, phiên xác nhận, phiên bác bỏ của ứng viên trước
    for stub in stubs:
        i = stub.idx
        day = f"{dates[i]:%Y-%m-%d}"
        pending = StatusChange(EventStatus.CANDIDATE, i, dates[i], "giảm mạnh, volume đột biến, chờ phản ứng các phiên sau")
        # Vẫn trong vùng climax của ứng viên trước và chưa thủng ngưỡng: gộp, không tính là SC mới
        if prev is not None and i - prev[0] < sc.cooldown_bars and (prev[3] is None or prev[3] > i) and lo[i] >= prev[1] - rc.sc_max_undercut_atr * atr_ref[prev[0]]:
            others.append(replace(_candidate(df, EventType.SC, i, None, dict(stub.details), [
                pending, StatusChange(EventStatus.REVISED, i, dates[i], f"gộp vào ứng viên SC {vn_ts(dates[prev[0]])}")])))
            continue
        floor = lo[i] - rc.sc_max_undercut_atr * atr_ref[i]
        zone = lo[i]
        how: str | None = None
        conf: int | None = None
        rej: tuple[int, str] | None = None
        horizon = max(rc.sc_confirm_window, cfg.ar.window)
        for t in range(i + 1, min(i + horizon, last) + 1):
            if c[t] < floor - _EPS:
                rej = t, f"close {vn_num(c[t])} thủng đáy ứng viên {vn_num(lo[i])} quá {vn_g(rc.sc_max_undercut_atr)} ATR"
                break
            zone = min(zone, lo[t])
            if ar_conf.get(day) == t:
                how = "có Automatic Rally"
            elif t - i <= rc.sc_confirm_window:
                if c[t] >= zone + rc.sc_reaction_atr * atr_ref[t] - _EPS:
                    how = f"phản ứng tăng mạnh: close {vn_num(c[t])} cách đáy vùng tối thiểu {vn_g(rc.sc_reaction_atr)} ATR"
                elif stub.details["absorption"] == "cùng phiên" and t - i >= rc.sc_stabilize_bars \
                        and c[i + 1:t + 1].min() >= lo[i] - _EPS and np.nanmean(vr[i + 1:t + 1]) <= rc.sc_stabilize_vol_factor * vr[i]:
                    how = "giá ổn định, volume giảm"
            if how:
                conf = t
                break
        if conf is None and rej is None and i + horizon <= last:
            rej = i + horizon, f"không có phản ứng tăng hoặc AR trong {horizon} phiên"
        details = {**stub.details, "lowest_low": float(zone)}
        if conf is None:
            hist = [pending] + ([StatusChange(EventStatus.INVALIDATED, rej[0], dates[rej[0]], rej[1])] if rej else [])
            others.append(_candidate(df, EventType.SC, i, None, details, hist))
            prev = (i, float(lo[i]), None, rej[0] if rej else None)
            continue
        # Đã xác nhận: chỉ bác bỏ khi thủng ngưỡng trước khi giá kịp hồi thành AR; sau đó là việc của range (ST, Spring)
        level = zone + sc.ar_min_atr * atr_ref[i]
        after = None
        peak = c[conf]
        for t in range(conf + 1, min(conf + sc.fail_window, last) + 1):
            if peak >= level:
                break
            if c[t] < floor - _EPS:
                after = t
                break
            peak = max(peak, c[t])
        details["confirmation"] = how
        hist = [pending, StatusChange(EventStatus.CONFIRMED, conf, dates[conf], how)]
        if after is not None:
            hist.append(StatusChange(EventStatus.INVALIDATED, after, dates[after], f"close {vn_num(c[after])} thủng đáy SC {vn_num(lo[i])} trước khi có AR"))
        e = replace(_make_event(df, EventType.SC, i, conf, None, details), low=float(zone), history=tuple(hist))
        confirmed.append(e)
        prev = (i, float(lo[i]), conf, after)
    return confirmed, others


def _ar_reactions(df: pd.DataFrame, parents: list[Event], side: str, cfg: Config) -> list[dict[str, Any]]:
    """Phản ứng ngược chiều sau SC (side "up") hoặc BC (side "down"), chỉ dùng dữ liệu đến phiên đang xét. Phía BC tính trên giá đổi dấu.
    Phiên phản ứng: giá đi đúng chiều, biên độ từ `ar_min_spread_atr` ATR, đóng cửa ở nửa thuận chiều của phiên.
    Ứng viên: đã có phiên phản ứng kể từ đáy vùng, và close rời đáy vùng tối thiểu `ar_min_displacement_atr` ATR. Không phụ thuộc volume hay phiên kế tiếp.
    Xác nhận: pivot `k` phiên mỗi bên, từ phiên ứng viên trở đi. Không đạt ứng viên thì không có sự kiện nào."""
    rc = cfg.revision
    sign = 1.0 if side == "up" else -1.0
    window, k = (cfg.ar.window, cfg.ar.pivot_bars) if side == "up" else (cfg.distribution.ar_window, cfg.distribution.ar_pivot_bars)
    undercut = rc.sc_max_undercut_atr if side == "up" else cfg.distribution.bc_fail_atr
    r_ = _rounded(df, cfg.indicators.ratio_decimals)
    cp_raw = r_["close_pos"].to_numpy(dtype=float)
    cp = cp_raw if side == "up" else 1.0 - cp_raw
    c = sign * df["close"].to_numpy(dtype=float)
    top = (df["high"] if side == "up" else -df["low"]).to_numpy(dtype=float)
    bottom = (df["low"] if side == "up" else -df["high"]).to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    width = (df["tr"] / df["atr_ref"]).round(cfg.indicators.ratio_decimals).to_numpy(dtype=float)
    last = len(c) - 1
    out: list[dict[str, Any]] = []
    for par in parents:
        i = par.idx
        floor = bottom[i] - undercut * atr_ref[i]
        zone = float(bottom[i])
        wide: int | None = None
        t0: int | None = None
        conf: int | None = None
        rej: tuple[int, str] | None = None
        for t in range(i + 1, min(i + window + k, last) + 1):
            if c[t] < floor - _EPS:
                rej = t, "lost"
                break
            if t0 is None:
                if t > i + window:
                    break
                if bottom[t] < zone - _EPS:
                    zone, wide = float(bottom[t]), None
                if c[t] > c[t - 1] + _EPS and width[t] >= rc.ar_min_spread_atr - _EPS and cp[t] >= rc.ar_min_close_pos - _EPS:
                    wide = t
                if wide is not None and c[t] >= zone + rc.ar_min_displacement_atr * atr_ref[t] - _EPS:
                    t0 = t
            p = t - k
            if t0 is not None and p >= t0 and top[p] > top[max(p - k, 0):p].max() + _EPS and top[p] >= top[p + 1:t + 1].max() - _EPS:
                conf = t
                break
        if t0 is None:
            continue
        if conf is None and rej is None and i + window + k <= last:
            rej = i + window + k, "no_swing"
        out.append({"parent": par, "wide": wide, "t0": t0, "conf": conf, "peak": None if conf is None else conf - k, "zone": sign * zone, "rej": rej})
    return out


def _ar_events(df: pd.DataFrame, scs: list[Event], distribution: list[Event], cfg: Config) -> tuple[list[Event], list[Event]]:
    """AR theo định nghĩa 06/11/2026 (docs/event-definitions.md): (đã từng xác nhận, ứng viên chưa / không xác nhận).
    `ar_high` / `ar_low` cùng đáy SC / đỉnh BC là biên Trading Range ban đầu. SC, BC bị bác bỏ thì AR bị bác bỏ theo."""
    dates = df.index
    bcs, bc_failed = _bcs(distribution)
    confirmed: list[Event] = []
    others: list[Event] = []
    r_ = _rounded(df, cfg.indicators.ratio_decimals)
    vr = r_["vol_ratio"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    groups = (("up", EventType.AR, "sc", _ar_reactions(df, scs, "up", cfg)), ("down", EventType.AR_D, "bc", _ar_reactions(df, bcs, "down", cfg)))
    for side, kind, tag, reactions in groups:
        for r in reactions:
            par, t0, peak, conf = r["parent"], r["t0"], r["peak"], r["conf"]
            day = f"{par.date:%Y-%m-%d}"
            name = "SC" if side == "up" else "BC"
            at = peak if peak is not None else t0
            end = float(df["high"].iloc[at] if side == "up" else df["low"].iloc[at])
            details: dict[str, Any] = {
                "ar_definition": "candidate_confirmed", "side": "accumulation" if side == "up" else "distribution", f"{tag}_date": day,
                ("sc_low" if side == "up" else "bc_high"): round(r["zone"], 4),
                ("rally_atr" if side == "up" else "reaction_atr"): round(abs(end - r["zone"]) / float(atr_ref[par.idx]), 3),
                "reaction_date": f"{dates[r['wide']]:%Y-%m-%d}", "reaction_vol_ratio": float(vr[r["wide"]]),
            }
            pending = StatusChange(EventStatus.CANDIDATE, t0, dates[t0], f"phản ứng mạnh sau {name}, chờ hoàn tất nhịp")
            lost = (r["rej"] is not None and r["rej"][1] == "lost")
            why = None if r["rej"] is None else (f"close mất vùng {name} trước khi tạo swing" if lost else "hết thời gian, chưa tạo swing")
            if conf is None:
                hist = [pending] + ([StatusChange(EventStatus.INVALIDATED, r["rej"][0], dates[r["rej"][0]], why)] if r["rej"] else [])
                others.append(_candidate(df, kind, t0, None, details, hist))
                continue
            details["ar_high" if side == "up" else "ar_low"] = end
            parent_conf = max(par.confirmed_idx, 0)
            known = max(conf, parent_conf)
            hist = [pending, StatusChange(EventStatus.CONFIRMED, known, dates[known], "hoàn tất nhịp phản ứng, " + ("tạo swing high" if side == "up" else "tạo swing low"))]
            gone = bc_failed.get(day) if side == "down" else None
            if par.invalidated is not None:
                gone = par.invalidated.idx if gone is None else min(gone, par.invalidated.idx)
            if gone is not None:
                gone = max(int(gone), known)
                hist.append(StatusChange(EventStatus.INVALIDATED, gone, dates[gone], f"{name} {vn_ts(par.date)} bị bác bỏ"))
            confirmed.append(replace(_make_event(df, kind, peak, known, None, details), history=tuple(hist)))
    return confirmed, others


def _st_tests(df: pd.DataFrame, par: Event, ar: Event, side: str, fail: float, cfg: Config) -> list[dict[str, Any]]:
    """Các lần kiểm tra vùng cao trào sau SC + AR (side "up") hoặc BC + AR (side "down"), chỉ dùng dữ liệu đến phiên đang xét. Phía BC tính trên giá đổi dấu.
    Áp lực "tương đương cao trào": phiên đi về phía vùng mà cả volume lẫn biên độ đều không yếu hơn, hoặc phiên khóa sàn (khóa trần với BC)."""
    rc = cfg.revision
    if side == "up":
        sign, window, below, above, max_vol, max_spread, gap = 1.0, cfg.st.window, cfg.st.band_below_atr, cfg.st.band_above_atr, cfg.st.max_vol_vs_sc, cfg.st.max_spread_vs_sc, cfg.st.min_gap_bars
        bottom, base, lock = df["low"].to_numpy(dtype=float), float(par.low), "floor_locked"
    else:
        d = cfg.distribution
        sign, window, below, above, max_vol, max_spread, gap = -1.0, d.st_window, d.st_band_above_atr, d.st_band_below_atr, d.st_max_vol_vs_bc, d.st_max_spread_vs_bc, d.st_min_gap_bars
        bottom, base, lock = -df["high"].to_numpy(dtype=float), -float(par.high), "ceiling_locked"
    c = sign * df["close"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    spread = (df["high"] - df["low"]).to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    vr = np.nan_to_num(_rounded(df, cfg.indicators.ratio_decimals)["vol_ratio"].to_numpy(dtype=float))
    locked = df[lock].to_numpy(dtype=bool) if lock in df.columns else np.zeros(len(c), dtype=bool)
    last = len(c) - 1
    par_vol, par_spread = float(volume[par.idx]), float(spread[par.idx])

    def weak_volume(t: int) -> bool:
        # So với cả cao trào và TB20: volume thấp hơn SC nhưng vẫn đột biến so với TB20 thì chưa phải suy yếu
        return bool(volume[t] < max_vol * par_vol and vr[t] < cfg.sc.min_vol_ratio)

    def weak_spread(t: int) -> bool:
        return bool(spread[t] < max_spread * par_spread)

    def toward(t: int) -> bool:
        return bool(c[t] < c[t - 1] - _EPS)

    out: list[dict[str, Any]] = []
    k = max(ar.idx, ar.confirmed_idx) + 1
    end = min(ar.idx + window, last)
    while k <= end and k < fail:
        a = atr_ref[k]
        in_zone = base - below * a - _EPS <= bottom[k] <= base + above * a + _EPS
        if not (in_zone and toward(k) and not locked[k] and (weak_volume(k) or weak_spread(k))):
            k += 1
            continue
        lowest, conf, rej = float(bottom[k]), None, None
        for t in range(k, min(k + rc.st_confirm_bars, last) + 1):
            lowest = min(lowest, float(bottom[t]))
            if bottom[t] < base - below * atr_ref[t] - _EPS:
                rej = t, "deep"
                break
            if toward(t) and (locked[t] or not (weak_volume(t) or weak_spread(t))):
                rej = t, "pressure"
                break
            if t > k and c[t] >= lowest + rc.st_reaction_atr * atr_ref[t] - _EPS:
                conf = t
                break
        if conf is None and rej is None and k + rc.st_confirm_bars <= last:
            rej = k + rc.st_confirm_bars, "no_reaction"
        stop = conf if conf is not None else rej[0] if rej is not None else last
        at = k + int(np.argmin(bottom[k:stop + 1]))
        out.append({"k": k, "idx": at, "conf": conf, "rej": rej, "stop": stop, "low": sign * lowest,
                    "volume_vs": round(float(volume[k:stop + 1].max() / par_vol), 3) if par_vol > 0 else None,
                    "spread_vs": round(float(spread[k:stop + 1].max() / par_spread), 3) if par_spread > 0 else None,
                    "vol_ratio": float(vr[k:stop + 1].max()), "zone_atr": round(float((bottom[at] - base) / atr_ref[at]), 3)})
        if conf is None and rej is None:
            break
        k = max(stop + 1, k + gap)
    return out


def _st_events(
    df: pd.DataFrame, ranges: list[TradingRange], scs: list[Event], distribution: list[Event], ars: list[Event], cfg: Config
) -> tuple[list[Event], list[Event]]:
    """ST theo định nghĩa 06/11/2026 (docs/event-definitions.md): (đã từng xác nhận, ứng viên chưa / không xác nhận). Có thể có nhiều ST cho một cao trào.
    ST thất bại chỉ bác bỏ lần ST đó; SC, BC bị bác bỏ thì ST bị bác bỏ theo."""
    dates = df.index
    last = len(df) - 1
    bcs, bc_failed = _bcs(distribution)
    sc_by, bc_by = {f"{s.date:%Y-%m-%d}": s for s in scs}, {f"{b.date:%Y-%m-%d}": b for b in bcs}
    why = {"deep": "xuyên sâu khỏi vùng kiểm tra", "no_reaction": "không có phản ứng giá", "pressure": "có áp lực tương đương cao trào"}

    def range_at(i: int, known_at: int) -> int | None:
        """Range chứa phiên i và đã được xác nhận tại phiên biết sự kiện: range xác nhận muộn hơn thì sự kiện chưa thuộc range đó."""
        return next((r.range_id for r in reversed(ranges) if r.start_idx <= i and r.confirmed_idx <= known_at and (r.end_confirmed_idx is None or i <= r.end_confirmed_idx)), None)

    confirmed: list[Event] = []
    others: list[Event] = []
    for ar in ars:
        up = ar.kind == EventType.AR
        day = ar.details["sc_date" if up else "bc_date"]
        par = (sc_by if up else bc_by).get(day)
        if par is None:
            continue
        name = "SC" if up else "BC"
        gone: int | None = None if up else bc_failed.get(day)
        if par.invalidated is not None:
            gone = par.invalidated.idx if gone is None else min(gone, par.invalidated.idx)
        for r in _st_tests(df, par, ar, "up" if up else "down", np.inf if gone is None else gone, cfg):
            details: dict[str, Any] = {
                "st_definition": "candidate_confirmed", "side": "accumulation" if up else "distribution", f"{name.lower()}_date": day,
                f"volume_vs_{name.lower()}": r["volume_vs"], f"spread_vs_{name.lower()}": r["spread_vs"], "max_vol_ratio": r["vol_ratio"],
                "test_price": round(r["low"], 4), f"{'low_vs_sc' if up else 'high_vs_bc'}_atr": r["zone_atr"], "test_bars": r["stop"] - r["k"] + 1,
            }
            kind = EventType.ST if up else EventType.ST_D
            pending = StatusChange(EventStatus.CANDIDATE, r["k"], dates[r["k"]], f"quay lại vùng {name}, áp lực yếu hơn cao trào, chờ phản ứng")
            if r["conf"] is None:
                hist = [pending] + ([StatusChange(EventStatus.INVALIDATED, r["rej"][0], dates[r["rej"][0]], why[r["rej"][1]])] if r["rej"] else [])
                others.append(_candidate(df, kind, r["idx"], range_at(r["idx"], r["k"]), details, hist))
                continue
            known = min(max(r["conf"], par.confirmed_idx, ar.confirmed_idx), last)
            hist = [pending, StatusChange(EventStatus.CONFIRMED, known, dates[known], f"vùng {name} được bảo vệ, giá phản ứng, không có áp lực tương đương cao trào")]
            if gone is not None:
                at = max(int(gone), known)
                hist.append(StatusChange(EventStatus.INVALIDATED, at, dates[at], f"{name} {vn_ts(par.date)} bị bác bỏ"))
            confirmed.append(replace(_make_event(df, kind, r["idx"], known, range_at(r["idx"], known), details), history=tuple(hist)))
    return confirmed, others


def _log_redefined_assessments(
    df: pd.DataFrame, log_events: list[Event], kinds: tuple[EventType, ...], new: list[Event], reason: str, assessments: dict[str, tuple[Verdict, ...]]
) -> dict[str, tuple[Verdict, ...]]:
    """Sự kiện của nhật ký đánh giá lại theo định nghĩa mới: cùng phiên -> lấy trạng thái mới; không đạt -> bác bỏ. Nhật ký và điểm tin cậy không đổi."""
    out = dict(assessments)
    by_key = {(e.kind, e.idx): e for e in new}
    dates = df.index
    for e in log_events:
        if e.kind not in kinds:
            continue
        match = by_key.get((e.kind, e.idx))
        at = e.confirmed_idx
        out[e.event_id] = _from_history(match) if match is not None else (
            Verdict(CONFIRMED, at, dates[at], "theo quy tắc nhật ký"), Verdict(REJECTED, at, dates[at], reason))
    return out


def _sc_children(df: pd.DataFrame, scs: list[Event], cfg: Config) -> list[Event]:
    """PS của các SC đã xác nhận. Biết tại phiên xác nhận của chính nó, nhưng không sớm hơn SC; SC bị bác bỏ thì bác bỏ theo."""
    items = detect_ps(df, scs, cfg.ps, decimals=cfg.indicators.ratio_decimals)
    by_date = {f"{s.date:%Y-%m-%d}": s for s in scs}
    out = []
    for e in items:
        parent = by_date[e.details["sc_date"]]
        conf = max(e.confirmed_idx, parent.confirmed_idx)
        hist = [StatusChange(EventStatus.CONFIRMED, conf, df.index[conf])]
        if parent.invalidated is not None:
            at = max(parent.invalidated.idx, conf)
            hist.append(StatusChange(EventStatus.INVALIDATED, at, df.index[at], f"SC {vn_ts(parent.date)} bị bác bỏ"))
        out.append(replace(e, confirmed_idx=conf, confirmed_date=df.index[conf], history=tuple(hist)))
    return out


def _log_sc_assessments(
    df: pd.DataFrame, events: list[Event], scs: list[Event], sc_others: list[Event], assessments: dict[str, tuple[Verdict, ...]]
) -> dict[str, tuple[Verdict, ...]]:
    """SC, PS, AR, ST của nhật ký đánh giá lại theo định nghĩa SC mới: cùng phiên -> lấy trạng thái SC mới;
    không còn là SC -> bác bỏ từ phiên nhật ký xác nhận. Nhật ký và điểm tin cậy không đổi."""
    out = dict(assessments)
    by_idx = {e.idx: e for e in scs + sc_others}
    dates = df.index
    log_sc = {f"{e.date:%Y-%m-%d}": e for e in events if e.kind == EventType.SC}
    verdict: dict[str, tuple[Verdict, ...]] = {}
    for day, e in log_sc.items():
        match = by_idx.get(e.idx)
        if match is not None:
            verdict[day] = _from_history(match)
        else:
            verdict[day] = (Verdict(CONFIRMED, e.confirmed_idx, dates[e.confirmed_idx], "theo quy tắc nhật ký"),
                            Verdict(REJECTED, e.confirmed_idx, dates[e.confirmed_idx], "không đạt định nghĩa SC: thiếu bối cảnh giảm, biên độ giảm hoặc volume"))
        out[e.event_id] = verdict[day]
    for e in events:
        if e.kind not in (EventType.PS, EventType.AR, EventType.ST) or e.details.get("sc_date") not in verdict:
            continue
        rej = next((v for v in verdict[e.details["sc_date"]] if v.status == REJECTED), None)
        if rej is None:
            continue
        at = max(rej.idx, e.confirmed_idx)
        base = out.get(e.event_id, ())
        kept = tuple(v for v in base if v.status != REJECTED and v.idx <= at)
        out[e.event_id] = kept + (Verdict(REJECTED, at, dates[at], f"SC {vn_ts(pd.Timestamp(e.details['sc_date']))} bị bác bỏ"),)
    return out


def _with_ids(items: list[Event], ranges: dict[int, TradingRange], suffix: str) -> list[Event]:
    seen: dict[str, int] = {}
    out = []
    for e in sorted(items, key=lambda x: (x.idx, x.history[0].idx if x.history else 0)):
        base = f"{base_event_id(e, ranges)}-{suffix}"
        seen[base] = seen.get(base, 0) + 1
        out.append(replace(e, event_id=base if seen[base] == 1 else f"{base}-{seen[base]}"))
    return out


# ---------------------------------------------------- Đánh giá sự kiện đã có

def _from_history(e: Event) -> tuple[Verdict, ...]:
    return tuple(Verdict(_FROM_EVENT_STATUS[h.status], h.idx, h.date, h.reason) for h in e.history)


def _assess_sos(df: pd.DataFrame, e: Event, cfg: Config) -> tuple[Verdict, ...]:
    """SOS xác nhận cùng phiên: tiềm năng cho đến khi có follow-through. Không theo tiếp được vẫn là tiềm năng, chưa phải bác bỏ."""
    base = _from_history(e)
    rejected = next((v for v in base if v.status == REJECTED), None)
    dates = df.index
    out = [Verdict(POTENTIAL, e.idx, dates[e.idx], "breakout, chờ follow-through")]
    conf, _, how = _follow_through(df, e.idx, float(e.details["resistance"]), cfg.sos)
    if conf is not None and (rejected is None or conf < rejected.idx):
        out.append(Verdict(CONFIRMED, conf, dates[conf], how))
    if rejected is not None:
        out.append(rejected)
    return tuple(out)


def _assess_upthrust(df: pd.DataFrame, e: Event, rng: TradingRange, cfg: Config) -> tuple[Verdict, ...]:
    """UTAD mode v2 (xác nhận ngay khi quay lại): dùng cùng phép thử yếu kém của mode ut_utad."""
    dates = df.index
    close = df["close"].to_numpy(dtype=float)
    ret = int(df.index.get_loc(pd.Timestamp(e.details["return_date"])))
    highest = float(e.details["highest_high"])
    mid = (rng.support + rng.resistance) / 2
    out = [Verdict(POTENTIAL, e.idx, dates[e.idx], "vượt resistance rồi quay lại, chờ yếu kém")]
    conf, _ = _weakness(df, ret, mid, highest, cfg.utad.weakness_window)
    if conf is not None:
        out.append(Verdict(CONFIRMED, conf, dates[conf], f"close {vn_num(close[conf])} dưới giữa range {vn_num(mid)}"))
    start = conf if conf is not None else ret
    t = next((j for j in range(start + 1, min(ret + cfg.revision.utad_watch_bars, len(close) - 1) + 1) if close[j] > highest + _EPS), None)
    if t is not None:
        out.append(Verdict(REJECTED, t, dates[t], f"close {vn_num(close[t])} vượt đỉnh upthrust {vn_num(highest)}"))
    return tuple(out)


def _assess_all(df: pd.DataFrame, items: list[Event], ranges: dict[int, TradingRange], cfg: Config) -> dict[str, tuple[Verdict, ...]]:
    out: dict[str, tuple[Verdict, ...]] = {}
    for e in items:
        confirmed = e.confirmed_idx >= 0
        if confirmed and e.kind == EventType.SOS and "follow_through" not in e.details and "resistance" in e.details:
            out[e.event_id] = _assess_sos(df, e, cfg)
        elif confirmed and e.kind in (EventType.UTAD, EventType.UT) and "weakness_date" not in e.details and e.range_id in ranges:
            out[e.event_id] = _assess_upthrust(df, e, ranges[e.range_id], cfg)
        elif e.history:
            out[e.event_id] = _from_history(e)
    return out


# ------------------------------------------------------------- Range là Accumulation

def _prior_markup(
    rng: TradingRange, close: np.ndarray, hyps: list[TrendHypothesis], stage_before: str | None, cfg: Config,
) -> tuple[bool, str]:
    """Điều kiện "Markup trước đó", dùng chung cho Re-accumulation và Distribution để việc phân xử dựa vào cung cầu:
    ngay từ đầu range, Markup đã đạt từ Developing trở lên (đã có HH-HL; xét tại đầu range để đỉnh, đáy trong range không được tính);
    hoặc xu hướng tăng kéo dài: close đầu range cao hơn đáy `context_lookback` phiên trước từ `prior_up_min_rise`, và trước range không phải Markdown."""
    start = rng.start_idx
    h = next((x for x in reversed(hyps) if x.stage == MARKUP and x.start_idx < start and x.end_idx >= start
              and x.status_at(start) in (DEVELOPING, CONFIRMED)), None)
    if h is not None:
        return True, f"Markup từ {vn_ts(h.start_date)}"
    low = close[max(0, start - cfg.ranges.context_lookback):start + 1].min()
    rise = close[start] / low - 1 if low > 0 else 0.0
    if stage_before != MARKDOWN and rise >= cfg.revision.prior_up_min_rise:
        return True, f"tăng {vn_g(round(rise * 100, 1))}% trước range"
    return False, ""


def _range_verdicts(
    df: pd.DataFrame, ranges: list[TradingRange], stages: StageResult, hyps: list[TrendHypothesis], events: list[Event],
    swings: list[Swing], scs: list[Event], assessments: dict[str, tuple[Verdict, ...]], cfg: Config,
) -> dict[int, RangeVerdict]:
    """Accumulation là quá trình hấp thụ cung, không phải chuỗi sự kiện (docs/stage-definitions.md). Mỗi range đi qua:
    Candidate (có Markdown trước đó, cung yếu đi) -> Developing (TR duy trì, hấp thụ cung, cầu tăng) ->
    Confirmed (breakout, cầu chiếm ưu thế, giữ hỗ trợ hoặc có LPS, HH-HL). Không bắt buộc qua Developing.
    SC, ST, Spring, SOS, LPS chỉ là bằng chứng, không sự kiện nào bắt buộc."""
    rc, sc = cfg.revision, cfg.sc
    r_ = _rounded(df, cfg.indicators.ratio_decimals)
    vr = np.nan_to_num(r_["vol_ratio"].to_numpy(dtype=float))
    sa = np.nan_to_num(r_["spread_atr"].to_numpy(dtype=float))
    cp = np.nan_to_num(r_["close_pos"].to_numpy(dtype=float))
    o, c = df["open"].to_numpy(dtype=float), df["close"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    sma = df["sma"].to_numpy(dtype=float)
    dates = df.index
    last = len(df) - 1
    prior = {r.range_id: r.prior_stage for r in stages.ranges}
    hyp_by_range = {h.range_id: h for h in hyps if h.source == "range_exit"}
    range_conf = sorted(r.confirmed_idx for r in ranges)

    mean = _SideStats(df, cfg).mean

    def status_time(e: Event, status: str) -> int | None:
        return next((v.idx for v in assessments.get(e.event_id, ()) if v.status == status), None)

    by_range: dict[int, list[Event]] = {}
    for e in events:
        if e.range_id is not None:
            by_range.setdefault(e.range_id, []).append(e)
    highs = sorted((s for s in swings if s.kind == "high"), key=lambda s: s.idx)
    lows = sorted((s for s in swings if s.kind == "low"), key=lambda s: s.idx)

    out: dict[int, RangeVerdict] = {}
    for rng in ranges:
        rid, start, sup, res = rng.range_id, rng.start_idx, rng.support, rng.resistance
        hyp = hyp_by_range.get(rid)
        # --- Bối cảnh: có Markdown trước đó
        look = max(0, start - cfg.ranges.context_lookback)
        decline = 1 - c[start] / c[look:start + 1].max() if c[look:start + 1].max() > 0 else 0.0
        falling = start >= cfg.stage.slope_bars and sma[start] < sma[start - cfg.stage.slope_bars]
        near_sc = [s for s in scs if start - cfg.ar.window <= s.idx <= rng.confirmed_idx and s.confirmed_idx <= rng.confirmed_idx
                   and (s.invalidated is None or s.invalidated.idx > rng.confirmed_idx)]
        stage_before = prior.get(rid)
        # Có Markup trước đó: xét Re-accumulation (song song với Distribution). Không có thì xét Accumulation.
        reacc, prior_up_text = _prior_markup(rng, c, hyps, stage_before, cfg)
        prior_ok = decline >= sc.min_decline and (stage_before == MARKDOWN or bool(falling) or bool(near_sc))
        if not reacc and not prior_ok:
            continue
        if reacc:
            near_sc = []
            prior_text = prior_up_text
        else:
            prior_text = f"giảm {vn_g(round(decline * 100, 1))}% trước range" + (f", SC {vn_ts(near_sc[-1].date)}" if near_sc else "")
        # Cấu trúc tăng: đáy swing gần nhất trước range, là HL cuối cùng của xu hướng
        last_hl = next((s.price for s in reversed(lows) if s.idx < start and s.confirmed_idx <= rng.confirmed_idx), sup)

        x = rng.end_confirmed_idx
        next_range = next((q for q in range_conf if q > rng.confirmed_idx), last + 1)
        if x is None:
            stop = min(last, next_range - 1)
        elif rng.exit_direction == "up":
            stop = min(x + rc.trend_watch_bars, last, next_range - 1)
        else:
            stop = _watch_stop(c, x, sup, res, rc.spring_window, min(last, next_range - 1))
        mid = (sup + res) / 2
        changes = np.abs(np.r_[0.0, np.diff(c)])
        absorb = (vr >= rc.acc_absorb_vol_ratio) & (c <= mid) & ((cp >= sc.min_close_pos) | (changes < 0.5 * np.nan_to_num(atr_ref)))
        absorb_cum = np.cumsum(np.where(np.arange(len(c)) >= start, absorb, False))

        own = by_range.get(rid, [])
        evidence = [e for e in own + near_sc if e.kind in (EventType.SC, EventType.ST, EventType.SPRING, EventType.TEST)]
        sos_list = [e for e in own if e.kind == EventType.SOS]
        lps_list = [e for e in own if e.kind == EventType.LPS]

        def evaluate(t: int) -> tuple[Condition, ...]:
            a = max(start, t - rc.acc_window + 1)
            # Cung yếu đi: phiên giảm gần đây volume hoặc biên độ thấp hơn đoạn giảm trước range, không có đáy mới
            before = (max(0, start - rc.acc_window), start - 1)
            v_now, s_now = mean("down", "vr", a, t), mean("down", "sa", a, t)
            v_old, s_old = mean("down", "vr", *before), mean("down", "sa", *before)
            floor = sup - cfg.ranges.exit_atr * atr[t]
            holds = c[max(a, t - 9):t + 1].min() >= floor - _EPS
            if reacc:
                # Đoạn trước range là xu hướng tăng, ít phiên giảm: so phiên giảm với phiên tăng ngay trong range
                v_up, s_up = mean("up", "vr", a, t), mean("up", "sa", a, t)
                calmer = v_now is None or (v_up is not None and (v_now <= v_up + _EPS or s_now <= s_up + _EPS))
                selling_text = "rất ít phiên giảm" if v_now is None else f"phiên giảm volume {vn_num(v_now)}x, biên độ {vn_num(s_now)} ATR; " + ("không có đáy mới" if holds else "vừa có đáy mới")
            else:
                calmer = v_now is not None and v_old is not None and s_now is not None and s_old is not None and (v_now <= v_old + _EPS or s_now <= s_old + _EPS)
                selling_text = "chưa đủ phiên giảm để so sánh" if v_now is None or v_old is None else \
                    f"phiên giảm volume {vn_num(v_now)}x, trước range {vn_num(v_old)}x; " + ("không có đáy mới" if holds else "vừa có đáy mới")
            selling = Condition("weak_selling", "Áp lực bán suy yếu", bool(holds and calmer), selling_text)
            # TR được duy trì: còn trong range, hoặc đã thoát lên, hoặc thoát xuống nhưng Markdown bị bác bỏ
            back_in = hyp is not None and hyp.stage == MARKDOWN and hyp.status_at(t) == REJECTED
            kept = rng.known_active_at(t, last) or back_in or (rng.exit_direction == "up" and x is not None and t >= x)
            maintained = Condition("range_kept", "Trading Range được duy trì", bool(kept), f"support {vn_num(sup)}, resistance {vn_num(res)}")
            # Hấp thụ cung: phiên bán lớn nhưng giá không giảm tương ứng; sự kiện chỉ là bằng chứng bổ sung
            n_abs = int(absorb_cum[t] - (absorb_cum[start - 1] if start > 0 else 0))
            known_ev = [e for e in evidence if status_time(e, CONFIRMED) is not None and status_time(e, CONFIRMED) <= t]
            absorption = Condition("absorption", "Hấp thụ cung", n_abs > 0 or bool(known_ev), f"{n_abs} phiên volume lớn giá không giảm tương ứng"
                                   + (", " + ", ".join(sorted({e.kind.value for e in known_ev})) if known_ev else ""))
            # Cầu gia tăng / chiếm ưu thế: phiên tăng so với phiên giảm gần đây
            vu, vd = mean("up", "vr", a, t), mean("down", "vr", a, t)
            su, sd = mean("up", "sa", a, t), mean("down", "sa", a, t)
            enough = None not in (vu, vd, su, sd)
            rising = Condition("demand", "Cầu gia tăng", bool(enough and vu >= vd - _EPS and su >= sd - _EPS),
                               "chưa đủ phiên để so sánh" if not enough else f"phiên tăng: volume {vn_num(vu)}x, biên độ {vn_num(su)} ATR; phiên giảm: {vn_num(vd)}x, {vn_num(sd)} ATR")
            # Gần như không có phiên giảm trong khi có phiên tăng cũng là cầu chiếm ưu thế
            dominant = Condition("dominance", "Cầu chiếm ưu thế", bool(vu is not None and (vd is None or vu > vd + _EPS)),
                                 "chưa đủ phiên tăng để so sánh" if vu is None else
                                 (f"volume phiên tăng {vn_num(vu)}x, rất ít phiên giảm" if vd is None else f"volume phiên tăng {vn_num(vu)}x, phiên giảm {vn_num(vd)}x"))
            # Breakout: SOS đã xác nhận, hoặc range thoát lên
            live_sos = [e for e in sos_list if (status_time(e, CONFIRMED) or last + 1) <= t and (status_time(e, REJECTED) or last + 1) > t]
            exited_up = rng.exit_direction == "up" and x is not None and x <= t
            b = min([e.idx for e in live_sos] + ([x] if exited_up else []), default=None)
            breakout = Condition("breakout", "SOS hoặc breakout đáng tin cậy", b is not None,
                                 "chưa có" if b is None else f"từ {vn_ts(dates[b])}" + (" (SOS)" if live_sos else " (thoát lên)"))
            lps_now = [e for e in lps_list if (status_time(e, CONFIRMED) or last + 1) <= t and (status_time(e, REJECTED) or last + 1) > t]
            if b is None:
                hold = Condition("hold", "Giữ hỗ trợ sau breakout hoặc có LPS", False, "chưa có breakout")
                turn = Condition("hh_hl", "Cấu trúc HH–HL", False, "chưa có breakout")
            else:
                after = c[b:t + 1]
                floor_b = res * (1 - rc.lps_max_depth)
                held = t - b >= rc.acc_hold_bars and after.min() >= floor_b - _EPS
                hold = Condition("hold", "Giữ hỗ trợ sau breakout hoặc có LPS", bool(lps_now or held),
                                 f"LPS {vn_ts(lps_now[0].date)}" if lps_now else f"{t - b} phiên sau breakout, close thấp nhất {vn_num(after.min())}")
                prev_low = next((s.price for s in reversed(lows) if s.idx < b and s.confirmed_idx <= t), sup)
                new_lows = [s for s in lows if s.idx > b and s.confirmed_idx <= t]
                # Có đáy swing sau breakout thì dùng đáy đó; chưa có thì LPS, hoặc đã giữ trên hỗ trợ đủ lâu mà chưa quay xuống
                hl = new_lows[-1].price > prev_low + _EPS if new_lows else bool(lps_now and lps_now[0].close > prev_low + _EPS) or bool(held)
                hh = after.max() > res + _EPS
                turn = Condition("hh_hl", "Cấu trúc HH–HL", bool(hl and hh), f"đỉnh sau breakout {vn_num(after.max())}, đáy trước {vn_num(prev_low)}" + ("" if hl else ", chưa có đáy cao hơn"))
            base = (selling, maintained, absorption, rising, dominant, breakout, hold, turn)
            if reacc:
                floor_hl = last_hl - cfg.ranges.exit_atr * atr[t]
                return base + (Condition("structure", "Cấu trúc tăng chưa bị phá", bool(c[t] >= floor_hl - _EPS), f"HL trước range {vn_num(last_hl)}, close {vn_num(c[t])}"),)
            return base

        hist: list[Verdict] = []
        level = None
        conds: tuple[Condition, ...] = ()
        conf_at: int | None = None
        demand_idx: int | None = None
        demand_run = 0
        for t in range(rng.confirmed_idx, stop + 1):
            if np.isnan(atr[t]):
                continue
            if hyp is not None and hyp.stage == MARKDOWN and hyp.status_at(t) == CONFIRMED and hyp.status_at(t - 1) != CONFIRMED:
                if hist:
                    hist.append(Verdict(REJECTED, t, dates[t], "Markdown đã xác nhận"))
                level = REJECTED
                break
            conds = evaluate(t)
            met = {k.key: k.met for k in conds}
            if reacc and not met["structure"]:
                if hist:
                    hist.append(Verdict(REJECTED, t, dates[t], f"close {vn_num(c[t])} phá cấu trúc tăng, HL trước range {vn_num(last_hl)}"))
                level = REJECTED
                break
            # Cầu bắt đầu kiểm soát: duy trì đủ số phiên cầu chiếm ưu thế ở nửa trên range, với đáy swing gần nhất cao hơn đáy trước.
            # Close thủng support nghĩa là cầu chưa kiểm soát được: bỏ mốc, xét lại từ đầu.
            known = [s.price for s in lows if s.idx >= start and s.confirmed_idx <= t]
            higher_low = len(known) >= 2 and known[-1] > known[-2] + _EPS
            demand_run = demand_run + 1 if met["dominance"] and c[t] > mid + _EPS and higher_low else 0
            if c[t] < sup - _EPS:
                demand_idx, demand_run = None, 0
            elif demand_idx is None and demand_run >= rc.acc_demand_bars:
                demand_idx = t - rc.acc_demand_bars + 1
            if met["breakout"] and met["dominance"] and met["hold"] and met["hh_hl"]:
                hist.append(Verdict(CONFIRMED, t, dates[t], "breakout, cầu chiếm ưu thế, giữ hỗ trợ hoặc có LPS, cấu trúc HH–HL"))
                level, conf_at = CONFIRMED, t
                break
            if level != DEVELOPING and met["weak_selling"] and met["range_kept"] and met["absorption"] and met["demand"]:
                hist.append(Verdict(DEVELOPING, t, dates[t], "TR duy trì, có hấp thụ cung, cung yếu đi, cầu tăng"))
                level = DEVELOPING
            elif level is None and reacc:
                hist.append(Verdict(POTENTIAL, t, dates[t], f"sau {prior_text}, hình thành range, cấu trúc tăng chưa bị phá"))
                level = POTENTIAL
            elif level is None and met["weak_selling"]:
                hist.append(Verdict(POTENTIAL, t, dates[t], f"sau Markdown ({prior_text}), áp lực bán yếu đi"))
                level = POTENTIAL
        if not hist:
            continue
        if level in (POTENTIAL, DEVELOPING):
            if rng.exit_direction == "down" and stop < next_range - 1 and stop < last and c[stop] < sup - _EPS:
                hist.append(Verdict(REJECTED, stop, dates[stop], f"thoát xuống, {rc.spring_window} phiên không close trong range"))
            elif next_range <= last:
                hist.append(Verdict(REJECTED, next_range, dates[next_range], "range mới đã xác nhận, chưa đủ bằng chứng cầu"))
        if conf_at is not None:
            # Sau xác nhận: chỉ gỡ khi SOS đang làm căn cứ bị bác bỏ, hoặc close thủng đáy Spring / support. LPS thất bại không gỡ nhãn.
            springs = [e for e in own if e.kind == EventType.SPRING]
            broke: tuple[int, str] | None = None
            for t in range(conf_at + 1, min(conf_at + rc.trend_watch_bars, last) + 1):
                live = [float(e.details["lowest_low"]) for e in springs if _at(assessments.get(e.event_id, ()), t) == CONFIRMED]
                lvl, name = (min(live), "đáy Spring") if live else (sup, "support")
                if c[t] < lvl - _EPS:
                    broke = t, f"close {vn_num(c[t])} thủng {name} {vn_num(lvl)}"
                    break
            s_rej = min((r for r in (status_time(e, REJECTED) for e in sos_list if (status_time(e, CONFIRMED) or last + 1) <= conf_at) if r is not None and r > conf_at), default=None)
            if s_rej is not None and (broke is None or s_rej < broke[0]):
                broke = s_rej, "SOS bị bác bỏ"
            if broke is not None:
                hist.append(Verdict(REJECTED, broke[0], dates[broke[0]], broke[1]))
        # Đoạn vẽ hồi cứu: đến trước Markup nếu Markup bắt đầu trong thời gian đang xét, không thì đến hết range / phiên xác nhận
        up_start = next((h.start_idx for h in hyps if h.stage == MARKUP and rng.confirmed_idx < h.start_idx <= stop + 1 and h.status != REJECTED), None)
        ref = conf_at if conf_at is not None else rng.end_idx
        end = up_start - 1 if up_start is not None and (conf_at is None or up_start <= conf_at) else ref
        supporting = tuple(sorted({f"{e.kind.value} {vn_ts(e.date)}" for e in evidence + sos_list + lps_list if _final(assessments.get(e.event_id, (Verdict(REJECTED, 0, e.date),))) == CONFIRMED}))
        typ = "Re-accumulation" if reacc else "Initial Accumulation" if stage_before == MARKDOWN else "Accumulation"
        leaning = None
        if reacc:
            # Markup -> range -> phân tích cung cầu -> Re-accumulation hoặc Distribution, không mặc định là Re-accumulation
            t_end = conf_at if conf_at is not None else stop
            a_end = max(start, t_end - rc.acc_window + 1)
            vu_l, vd_l, su_l, sd_l = mean("up", "vr", a_end, t_end), mean("down", "vr", a_end, t_end), mean("up", "sa", a_end, t_end), mean("down", "sa", a_end, t_end)
            new_lows = [s.price for s in lows if s.idx >= start and s.confirmed_idx <= t_end]
            new_highs = [s.price for s in highs if s.idx >= start and s.confirmed_idx <= t_end]
            lower_low = len(new_lows) >= 2 and new_lows[-1] < new_lows[-2] - _EPS
            lower_high = len(new_highs) >= 2 and new_highs[-1] < new_highs[-2] - _EPS
            sides = None not in (vu_l, vd_l, su_l, sd_l)
            if conf_at is not None or (sides and vu_l > vd_l + _EPS and not lower_low):
                leaning = "Re-accumulation"
            elif sides and vd_l > vu_l + _EPS and sd_l > su_l + _EPS and (lower_high or lower_low):
                leaning = "Distribution"
            else:
                leaning = "chưa rõ"
        watch_end = dates[min(conf_at + rc.trend_watch_bars, last) if conf_at is not None else stop]
        out[rid] = RangeVerdict(rid, typ, start, max(end, start), tuple(hist), conds, supporting, demand_idx, leaning, watch_end)
    return out


def _primary_verdict(main: RangeVerdict | None, dist: RangeVerdict | None) -> tuple[RangeVerdict | None, bool]:
    """Cấu trúc đại diện của range và cờ đã phân định. Markup -> range -> phân tích cung cầu -> Re-accumulation hoặc Distribution:
    mức cao hơn thắng; cùng mức thì theo hướng nghiêng; cùng mức mà chưa rõ thì chưa phân định."""
    rank = {POTENTIAL: 1, DEVELOPING: 2, CONFIRMED: 3}
    a = main if main is not None and main.status != REJECTED else None
    b = dist if dist is not None and dist.status != REJECTED else None
    if a is not None and b is None and a.is_reaccumulation and a.status == POTENTIAL and a.leaning != "Re-accumulation":
        return a, False     # Candidate mới dựa vào xu hướng trước, chưa có bằng chứng cung cầu: chưa phân định
    if a is None or b is None:
        return a or b, True
    if rank[a.status] != rank[b.status]:
        return (a if rank[a.status] > rank[b.status] else b), True
    if b.leaning == "Distribution":
        return b, True
    if a.leaning == "Re-accumulation":
        return a, True
    return a, False


def _distribution_verdicts(
    df: pd.DataFrame, ranges: list[TradingRange], stages: StageResult, hyps: list[TrendHypothesis], events: list[Event],
    dist_events: list[Event], swings: list[Swing], assessments: dict[str, tuple[Verdict, ...]], verdicts: dict[int, RangeVerdict], cfg: Config,
) -> dict[int, RangeVerdict]:
    """Distribution là quá trình chuyển giao cung cầu, không phải vùng đi ngang ở đỉnh (docs/stage-definitions.md). Range sau xu hướng tăng đi qua:
    Candidate (đà tăng yếu đi, cung xuất hiện) -> Developing (TR duy trì, nhịp tăng yếu, cung áp đảo, thất bại ở kháng cự) ->
    Confirmed (phá hỗ trợ có volume và spread xác nhận, LH-LL). Không sự kiện nào bắt buộc; UT, UTAD, SOW, BC chỉ là bằng chứng.
    Confirmed không đồng nghĩa Markdown đã xác nhận. Có sửa `verdicts`: Re-accumulation bị bác bỏ khi Distribution xác nhận trước."""
    rc, dc = cfg.revision, cfg.distribution
    r_ = _rounded(df, cfg.indicators.ratio_decimals)
    vr = np.nan_to_num(r_["vol_ratio"].to_numpy(dtype=float))
    sa = np.nan_to_num(r_["spread_atr"].to_numpy(dtype=float))
    o, c = df["open"].to_numpy(dtype=float), df["close"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    dates = df.index
    last = len(df) - 1
    mean = _SideStats(df, cfg).mean
    prior = {r.range_id: r.prior_stage for r in stages.ranges}
    hyp_by_range = {h.range_id: h for h in hyps if h.source == "range_exit"}
    range_conf = sorted(r.confirmed_idx for r in ranges)
    heavy = (c < o) & (vr >= dc.sow_min_vol_ratio) & (sa >= dc.sow_min_spread_atr)    # phiên giảm spread rộng, volume tăng
    heavy_cum = np.r_[0, np.cumsum(heavy)]
    highs = sorted((s for s in swings if s.kind == "high"), key=lambda s: s.idx)
    lows = sorted((s for s in swings if s.kind == "low"), key=lambda s: s.idx)
    by_range: dict[int, list[Event]] = {}
    for e in list(events) + list(dist_events):
        if e.range_id is not None:
            by_range.setdefault(e.range_id, []).append(e)

    out: dict[int, RangeVerdict] = {}
    for rng in ranges:
        rid, start, sup, res = rng.range_id, rng.start_idx, rng.support, rng.resistance
        existing = verdicts.get(rid)
        if existing is not None and not existing.is_reaccumulation:
            continue                    # đã xét là Accumulation: range sau Markdown
        if not _prior_markup(rng, c, hyps, prior.get(rid), cfg)[0]:
            continue                    # cùng điều kiện với Re-accumulation
        own = by_range.get(rid, [])
        up_thrusts = [e for e in own if e.kind in (EventType.UT, EventType.UTAD)]
        sows = [e for e in own if e.kind == EventType.SOW]
        x = rng.end_confirmed_idx
        next_range = next((q for q in range_conf if q > rng.confirmed_idx), last + 1)
        hyp = hyp_by_range.get(rid)
        if x is None:
            stop = min(last, next_range - 1)
        elif rng.exit_direction == "up":
            stop = min(x + rc.acc_hold_bars, last, next_range - 1)
        else:
            stop = _watch_stop(c, x, sup, res, rc.spring_window, min(last, next_range - 1))
        below = next((j for j in range(rng.confirmed_idx, stop + 1) if c[j] < sup - _EPS), None)

        def evaluate(t: int) -> tuple[Condition, ...]:
            nonlocal below
            a = max(start, t - rc.acc_window + 1)
            vu, vd = mean("up", "vr", a, t), mean("down", "vr", a, t)
            su, sd = mean("up", "sa", a, t), mean("down", "sa", a, t)
            before = (max(0, start - rc.acc_window), start - 1)
            vu_old, su_old = mean("up", "vr", *before), mean("up", "sa", *before)
            quiet_top = c[max(a, t - 9):t + 1].max() <= res + cfg.ranges.exit_atr * atr[t] + _EPS
            lost_pace = vu is None or vu_old is None or vu <= vu_old + _EPS or su <= su_old + _EPS
            fading = Condition("fading", "Đà tăng suy yếu", bool(quiet_top and lost_pace),
                               "chưa đủ phiên để so sánh" if vu is None or vu_old is None else f"phiên tăng volume {vn_num(vu)}x, trước range {vn_num(vu_old)}x")
            n_heavy = int(heavy_cum[t + 1] - heavy_cum[start])
            emerging = Condition("supply_emerging", "Cung xuất hiện", n_heavy > 0, f"{n_heavy} phiên giảm spread rộng, volume tăng")
            kept = Condition("range_kept", "Trading Range được duy trì", rng.known_active_at(t, last), f"support {vn_num(sup)}, resistance {vn_num(res)}")
            weak = Condition("weak_rally", "Nhịp tăng yếu dần", bool(vd is not None and (vu is None or vu < vd - _EPS or su < sd - _EPS)),
                             "rất ít phiên giảm" if vd is None else "rất ít phiên tăng" if vu is None else f"phiên tăng volume {vn_num(vu)}x, biên độ {vn_num(su)} ATR")
            dom = bool(vd is not None and vu is not None and vd > vu + _EPS and sd >= su - _EPS)
            dominance = Condition("supply_dominance", "Cung chiếm ưu thế", dom,
                                  "chưa đủ phiên để so sánh" if vd is None or vu is None else f"phiên giảm volume {vn_num(vd)}x, biên độ {vn_num(sd)} ATR; phiên tăng {vn_num(vu)}x, {vn_num(su)} ATR")
            known_up = [e for e in up_thrusts if 0 <= e.confirmed_idx <= t]
            new_highs = [s.price for s in highs if s.idx >= start and s.confirmed_idx <= t]
            lower_high = len(new_highs) >= 2 and new_highs[-1] < new_highs[-2] - _EPS
            fail = Condition("resistance_fail", "Thất bại ở kháng cự", bool(known_up or lower_high),
                             ", ".join(sorted({e.kind.value for e in known_up})) or ("đỉnh thấp hơn đỉnh trước" if lower_high else "chưa thấy"))
            known_x = rng.exit_direction == "down" and x is not None and x <= t
            broke = Condition("breakdown", "Phá hỗ trợ", bool(known_x), f"close {vn_num(c[t])} so với support {vn_num(sup)}")
            first = below if below is not None and below <= t else None
            backed = first is not None and heavy_cum[t + 1] - heavy_cum[first] > 0
            live_sow = [e for e in sows if 0 <= e.confirmed_idx <= t and first is not None and e.idx >= first]
            confirm = Condition("breakdown_backed", "Breakdown có volume và spread", bool(backed or live_sow),
                                ", ".join(sorted({e.kind.value for e in live_sow})) or ("có phiên giảm spread rộng, volume tăng" if backed else "chưa có"))
            lows_now = [s.price for s in lows if s.idx >= start and s.confirmed_idx <= t]
            lower_low = c[t] < sup - _EPS or (len(lows_now) >= 2 and lows_now[-1] < lows_now[-2] - _EPS)
            lh_ll = Condition("lh_ll", "Cấu trúc LH–LL", bool(lower_high and lower_low), ("có đỉnh thấp hơn" if lower_high else "chưa có đỉnh thấp hơn") + ("; có đáy thấp hơn" if lower_low else "; chưa có đáy thấp hơn"))
            return fading, emerging, kept, weak, dominance, fail, broke, confirm, lh_ll

        reacc_conf = next((v.idx for v in existing.history if v.status == CONFIRMED), None) if existing is not None else None
        hist: list[Verdict] = []
        level = None
        conds: tuple[Condition, ...] = ()
        conf_at: int | None = None
        for t in range(rng.confirmed_idx, stop + 1):
            if np.isnan(atr[t]):
                continue
            if reacc_conf is not None and t >= reacc_conf:
                if hist:
                    hist.append(Verdict(REJECTED, t, dates[t], "Re-accumulation đã xác nhận"))
                level = REJECTED
                break
            conds = evaluate(t)
            met = {k.key: k.met for k in conds}
            if met["breakdown"] and met["breakdown_backed"] and met["lh_ll"]:
                hist.append(Verdict(CONFIRMED, t, dates[t], "phá hỗ trợ có volume và spread xác nhận, cấu trúc LH–LL"))
                level, conf_at = CONFIRMED, t
                break
            if level != DEVELOPING and met["range_kept"] and met["weak_rally"] and met["supply_dominance"] and met["resistance_fail"]:
                hist.append(Verdict(DEVELOPING, t, dates[t], "TR duy trì, nhịp tăng yếu, cung áp đảo, thất bại ở kháng cự"))
                level = DEVELOPING
            elif level is None and met["fading"] and met["supply_emerging"]:
                hist.append(Verdict(POTENTIAL, t, dates[t], "sau xu hướng tăng, đà tăng yếu đi, cung xuất hiện"))
                level = POTENTIAL
        if not hist:
            continue
        if level in (POTENTIAL, DEVELOPING):
            if rng.exit_direction == "up" and x is not None and stop == x + rc.acc_hold_bars and stop <= last and c[x:stop + 1].min() >= res * (1 - rc.lps_max_depth) - _EPS:
                hist.append(Verdict(REJECTED, stop, dates[stop], "breakout giữ được, không phải đỉnh giả"))
            elif rng.exit_direction == "down" and stop < next_range - 1 and stop < last and not (hyp is not None and hyp.status_at(stop) == REJECTED):
                pass                    # đã thoát xuống nhưng thiếu xác nhận của volume hoặc cấu trúc: giữ mức hiện tại
            elif next_range <= last:
                hist.append(Verdict(REJECTED, next_range, dates[next_range], "range mới đã xác nhận, chưa đủ bằng chứng cung"))
        if conf_at is not None:
            t = next((j for j in range(conf_at + 1, min(conf_at + rc.trend_watch_bars, last) + 1) if c[j] > res + _EPS), None)
            if t is not None:
                hist.append(Verdict(REJECTED, t, dates[t], f"close {vn_num(c[t])} vượt lại resistance {vn_num(res)}"))
            # Distribution xác nhận trước: Re-accumulation của range không còn
            if existing is not None:
                kept_hist = tuple(v for v in existing.history if v.idx < conf_at)
                verdicts[rid] = replace(existing, history=kept_hist + (Verdict(REJECTED, conf_at, dates[conf_at], "Distribution đã xác nhận"),)) if kept_hist else existing
        # Hướng nghiêng theo cùng tiêu chí với Re-accumulation
        t_end = conf_at if conf_at is not None else stop
        a_end = max(start, t_end - rc.acc_window + 1)
        vu_l, vd_l, su_l, sd_l = mean("up", "vr", a_end, t_end), mean("down", "vr", a_end, t_end), mean("up", "sa", a_end, t_end), mean("down", "sa", a_end, t_end)
        h_now = [s.price for s in highs if s.idx >= start and s.confirmed_idx <= t_end]
        l_now = [s.price for s in lows if s.idx >= start and s.confirmed_idx <= t_end]
        down_shape = (len(h_now) >= 2 and h_now[-1] < h_now[-2] - _EPS) or (len(l_now) >= 2 and l_now[-1] < l_now[-2] - _EPS)
        sides = None not in (vu_l, vd_l, su_l, sd_l)
        if conf_at is not None or (sides and vd_l > vu_l + _EPS and sd_l > su_l + _EPS and down_shape):
            leaning = "Distribution"
        elif sides and vu_l > vd_l + _EPS and not (len(l_now) >= 2 and l_now[-1] < l_now[-2] - _EPS):
            leaning = "Re-accumulation"
        else:
            leaning = "chưa rõ"
        supporting = tuple(sorted({f"{e.kind.value} {vn_ts(e.date)}" for e in own if e.kind in (EventType.BC, EventType.AR_D, EventType.ST_D, EventType.UT, EventType.UTAD, EventType.SOW, EventType.LPSY)
                                   and e.confirmed_idx >= 0 and _final(assessments.get(e.event_id, (Verdict(CONFIRMED, 0, e.date),))) != REJECTED}))
        # Mốc pha D: phiên đầu tiên cung chiếm ưu thế sau khi TR xác nhận, không cần SOW
        d_mark = next((Verdict(DEVELOPING, v.idx, v.date).idx for v in hist if v.status == DEVELOPING), None)
        watch_end = dates[min(conf_at + rc.trend_watch_bars, last) if conf_at is not None else stop]
        out[rid] = RangeVerdict(rid, "Distribution", start, max(rng.end_idx, start), tuple(hist), conds, supporting, d_mark, leaning, watch_end)
    return out


def _distribution_phases(
    df: pd.DataFrame, series: pd.DataFrame, ranges: list[TradingRange], primary: dict[int, RangeVerdict], events: list[Event], dist_events: list[Event],
    assessments: dict[str, tuple[Verdict, ...]], cfg: Config,
) -> pd.DataFrame:
    """Vẽ pha A đến E cho range có cấu trúc đại diện là Distribution. A: BC nếu có, không thì đầu range; B: TR xác nhận;
    C: UT / UTAD; D: SOW hoặc khi cung bắt đầu chiếm ưu thế; E: breakdown đã xác nhận. Không sự kiện nào bắt buộc."""
    out = series.copy()
    phase = out["phase"].to_numpy(dtype=object)
    reason = out["reason"].to_numpy(dtype=object)
    range_col = out["range_id"].to_numpy(dtype=float)
    struct = out["structure_id"].to_numpy(dtype=float)
    dates = df.index
    last = len(df) - 1
    range_conf = sorted(r.confirmed_idx for r in ranges)

    def alive(e: Event) -> bool:
        return e.confirmed_idx >= 0 and _final(assessments.get(e.event_id, (Verdict(CONFIRMED, 0, e.date),))) != REJECTED

    for rng in ranges:
        v = primary.get(rng.range_id)
        if v is None or not v.is_distribution:
            continue
        rid = rng.range_id
        own = [e for e in list(events) + list(dist_events) if e.range_id == rid and alive(e)]
        bcs = [e for e in dist_events if e.kind == EventType.BC and alive(e) and rng.start_idx - cfg.ar.window <= e.idx <= rng.confirmed_idx]
        a0 = bcs[-1].idx if bcs else rng.start_idx
        b0 = rng.confirmed_idx
        sow = [e.idx for e in own if e.kind == EventType.SOW]
        d_list = sow + ([v.demand_idx] if v.demand_idx is not None else [])
        d0 = min(d_list, default=None)
        tests = [e.idx for e in own if e.kind in (EventType.UT, EventType.UTAD) and (d0 is None or e.idx < d0)]
        c0 = min(tests, default=None)
        conf = next((h.idx for h in v.history if h.status == CONFIRMED), None)
        next_range = next((q for q in range_conf if q > rng.confirmed_idx), last + 1)
        x = rng.end_confirmed_idx
        e0 = x if conf is not None and rng.exit_direction == "down" else None
        end = e0 - 1 if e0 is not None else (rng.end_idx if x is not None else min(next_range - 1, last))
        marks = [("A", a0, "Stopping Action: " + (f"BC {vn_ts(bcs[-1].date)}" if bcs else "dừng xu hướng tăng, hình thành TR")),
                 ("B", b0, "Building Cause: phân phối trong Trading Range")]
        if c0 is not None:
            marks.append(("C", c0, f"Testing Demand: kiểm tra cầu {vn_ts(dates[c0])}"))
        if d0 is not None:
            marks.append(("D", d0, "Supply Dominance: " + (f"SOW {vn_ts(dates[d0])}" if d0 in sow else f"cung bắt đầu chiếm ưu thế {vn_ts(dates[d0])}")))
        marks = sorted(marks, key=lambda m: m[1])
        for i, (name, begin, why) in enumerate(marks):
            stop = (marks[i + 1][1] - 1) if i + 1 < len(marks) else end
            for t in range(begin, min(stop, end) + 1):
                phase[t], reason[t] = name, why
                if np.isnan(struct[t]):
                    struct[t] = -1
                range_col[t] = rid
        if e0 is not None:
            why = f"Markdown: giá thoát khỏi TR#{rid} {vn_ts(dates[e0])}"
            t = e0
            while t <= last and t < next_range and (pd.isna(phase[t]) or phase[t] in (PHASE_POTENTIAL, "invalid")):
                phase[t], reason[t] = "E", why
                if np.isnan(struct[t]):
                    struct[t] = -1
                range_col[t] = rid
                t += 1
    out["phase"], out["reason"], out["range_id"], out["structure_id"] = phase, reason, range_col, struct
    return out


def _accumulation_phases(
    df: pd.DataFrame, series: pd.DataFrame, ranges: list[TradingRange], verdicts: dict[int, RangeVerdict], hyps: list[TrendHypothesis],
    events: list[Event], scs: list[Event], assessments: dict[str, tuple[Verdict, ...]], cfg: Config,
) -> pd.DataFrame:
    """Pha A đến E là pha của Accumulation và Re-accumulation (docs/stage-definitions.md): chỉ các range này mới có pha.
    Không sự kiện nào bắt buộc: A dừng xu hướng giảm (SC nếu có, không thì đầu range); B từ khi TR xác nhận hoặc có ST;
    C từ Spring / Test nếu có; D từ SOS hoặc khi cầu bắt đầu kiểm soát; E khi giá thoát khỏi TR.
    Range không phải Accumulation hoặc đã bị bác bỏ: bỏ các pha A đến E của nhật ký, giữ 'invalid' và 'potential'."""
    out = series.copy()
    phase = out["phase"].to_numpy(dtype=object)
    reason = out["reason"].to_numpy(dtype=object)
    range_col = out["range_id"].to_numpy(dtype=float)
    struct = out["structure_id"].to_numpy(dtype=float)
    log_phase = series["phase"].to_numpy(dtype=object)
    log_reason = series["reason"].to_numpy(dtype=object)
    dates = df.index
    last = len(df) - 1
    hyp_by_range = {h.range_id: h for h in hyps if h.source == "range_exit"}
    range_conf = sorted(r.confirmed_idx for r in ranges)

    def confirmed_now(e: Event) -> bool:
        return _final(assessments.get(e.event_id, (Verdict(REJECTED, 0, e.date),))) == CONFIRMED

    for rng in ranges:
        rid = rng.range_id
        v = verdicts.get(rid)
        if v is None or v.status == REJECTED:
            drop = (range_col == rid) & np.isin(log_phase, ("A", "B", "C", "D", "E"))
            phase[drop], reason[drop] = None, ""
            continue
        own = [e for e in events if e.range_id == rid and confirmed_now(e)]
        near_sc = [] if v.is_reaccumulation else [s for s in scs if rng.start_idx - cfg.ar.window <= s.idx <= rng.confirmed_idx and s.invalidated is None]
        a0 = near_sc[-1].idx if near_sc else rng.start_idx
        st = [e.idx for e in events if e.kind == EventType.ST and e.details.get("sc_date") in {f"{s.date:%Y-%m-%d}" for s in near_sc} and confirmed_now(e)]
        b0 = min(st + [rng.confirmed_idx])
        sos = [e.idx for e in own if e.kind == EventType.SOS]
        d0 = min(sos + ([v.demand_idx] if v.demand_idx is not None else []), default=None)
        tests = [e.idx for e in own if e.kind in (EventType.SPRING, EventType.TEST) and (d0 is None or e.idx < d0)]
        c0 = min(tests, default=None)
        x = rng.end_confirmed_idx
        next_range = next((q for q in range_conf if q > rng.confirmed_idx), last + 1)
        e0 = x if rng.exit_direction == "up" else next((t for t in range(rng.confirmed_idx, last + 1) if log_phase[t] == "E" and range_col[t] == rid), None)
        if e0 is not None:
            end = e0 - 1
        elif rng.exit_direction == "down" and c0 is None and not (hyp_by_range.get(rid) is not None and hyp_by_range[rid].status == REJECTED):
            end = rng.end_idx          # thoát xuống chưa rõ kết quả: phần sau do 'potential' / 'invalid' mô tả
        else:
            end = min(next_range - 1, last)
        marks = [("A", a0, "Stopping Action: " + (f"SC {vn_ts(near_sc[-1].date)}" if near_sc else "tạm dừng Markup, hình thành TR" if v.is_reaccumulation else "dừng xu hướng giảm, hình thành TR")),
                 ("B", b0, "Building Cause: hấp thụ cung, xây dựng nền giá")]
        if c0 is not None:
            marks.append(("C", c0, f"Testing Supply: kiểm tra cung {vn_ts(dates[c0])}"))
        if d0 is not None:
            marks.append(("D", d0, ("Demand Dominance: SOS " if d0 in sos else "Demand Dominance: cầu bắt đầu kiểm soát ") + vn_ts(dates[d0])))
        marks = sorted(marks, key=lambda m: m[1])
        for i, (name, begin, why) in enumerate(marks):
            stop = (marks[i + 1][1] - 1) if i + 1 < len(marks) else end
            for t in range(begin, min(stop, end) + 1):
                phase[t], reason[t] = name, why
                if np.isnan(struct[t]):
                    struct[t] = -1
                range_col[t] = rid
        if e0 is not None:
            why = f"{'Markup Resumption' if v.is_reaccumulation else 'Markup'}: giá thoát khỏi TR#{rid} {vn_ts(dates[e0])}"
            t = e0
            while t <= last and (t == e0 or log_phase[t] == "E" or pd.isna(log_phase[t])) and t < next_range:
                phase[t], reason[t] = "E", why
                if np.isnan(struct[t]):
                    struct[t] = -1
                range_col[t] = rid
                t += 1
    out["phase"], out["reason"], out["range_id"], out["structure_id"] = phase, reason, range_col, struct
    return out


# ------------------------------------------------------------- Pha hồi cứu

def _revise_phases(
    phases: PhaseResult, hyps: list[TrendHypothesis], springs: list[Event], scs: list[Event],
    assessments: dict[str, tuple[Verdict, ...]],
) -> pd.DataFrame:
    """Đoạn pha 'invalid' do range thoát xuống: pha C từ phiên Spring khi Spring kéo dài đã xác nhận và chưa bị bác bỏ;
    còn lại là tiềm năng khi Markdown chưa xác nhận. Spring bị bác bỏ thì không tính, nhãn trở lại tiềm năng.
    Markdown đã xác nhận và chưa bị bác bỏ thì giữ 'invalid'. Các lý do vô hiệu khác (UTAD, thủng đáy Spring) không đổi.
    Pha A: đoạn A mở bởi SC của nhật ký không còn là SC xác nhận thì bỏ; SC xác nhận còn hiệu lực mở pha A từ phiên SC,
    đè lên đoạn trống hoặc vô hiệu, đến khi gặp pha khác."""
    series = phases.series.copy()
    phase = series["phase"].to_numpy(dtype=object)
    reason = series["reason"].to_numpy(dtype=object)
    range_ids = series["range_id"].to_numpy(dtype=float)
    structure_ids = series["structure_id"].to_numpy(dtype=float)
    for sid, s in phases.structures.items():
        if s.sc is not None and _final(assessments.get(s.sc.event_id, (Verdict(CONFIRMED, 0, s.sc.date),))) != CONFIRMED:
            drop = (structure_ids == sid) & (phase == "A")
            phase[drop] = None
            reason[drop] = ""
    spring_by = {e.range_id: e for e in springs if e.invalidated is None}
    n = len(series)
    for h in hyps:
        if h.stage != MARKDOWN or h.source != "range_exit" or h.status == CONFIRMED:
            continue
        marker = f"TR#{h.range_id} thoát xuống"
        sp = spring_by.get(h.range_id)
        spring_reason = "" if sp is None else f"Spring kéo dài {vn_ts(sp.date)}, xác nhận {vn_ts(sp.confirmed_date)}: quay lại range với demand"
        if sp is not None:
            for t in range(sp.idx, h.start_idx):   # các phiên đầu của cú thủng, trước phiên xác nhận thoát
                if range_ids[t] == h.range_id and phase[t] in ("A", "B", "C"):
                    phase[t], reason[t] = "C", spring_reason
        t = h.start_idx
        while t < n and phase[t] == "invalid" and str(reason[t]).startswith(marker):
            if sp is not None:
                phase[t], reason[t] = "C", spring_reason
            else:
                phase[t] = PHASE_POTENTIAL
                reason[t] = (f"TR#{h.range_id} thoát xuống: Markdown bị bác bỏ, {h.reason}" if h.status == REJECTED
                             else f"TR#{h.range_id} thoát xuống, chờ xác nhận Markdown")
            t += 1
    for sc in sorted(scs, key=lambda e: e.idx):
        if sc.invalidated is not None:
            continue
        why = f"SC {vn_ts(sc.date)}, xác nhận {vn_ts(sc.confirmed_date)}"
        t = sc.idx
        while t < n and (pd.isna(phase[t]) or phase[t] == "invalid"):
            phase[t], reason[t] = "A", why
            if np.isnan(structure_ids[t]):
                structure_ids[t] = -1      # SC chưa thuộc cấu trúc nào của nhật ký
            t += 1
    series["structure_id"] = structure_ids
    series["phase"] = phase
    series["reason"] = reason
    return series


def build_revision(
    df: pd.DataFrame, ranges: list[TradingRange], events: list[Event], candidates: list[Event],
    phases: PhaseResult, stages: StageResult, distribution: list[Event], swings: list[Swing], cfg: Config,
) -> RevisionResult:
    rng_by_id = {r.range_id: r for r in ranges}
    lps, lps_cands = _lps_events(df, ranges, events, swings, cfg)
    hyps = _trend_hypotheses(df, stages, ranges, events, swings, distribution, cfg, lps)
    scs_raw, sc_others = _selling_climaxes(df, stages, cfg)
    springs, spring_cands = _extended_springs(df, ranges, hyps, scs_raw, cfg)
    springs = _with_ids(springs, rng_by_id, "EXT")
    quick = _with_ids(_quick_springs(df, ranges, hyps, scs_raw, cfg), rng_by_id, "QUICK")
    lps = _with_ids(lps, rng_by_id, "V2")
    lps_cands = _with_ids(lps_cands, rng_by_id, "V2C")
    cands = _with_ids(spring_cands, rng_by_id, "EXT") + lps_cands
    # ID của ứng viên có thể trùng với sự kiện đã xác nhận khác phiên kết thúc: thêm hậu tố
    taken = {e.event_id for e in springs + lps}
    cands = [replace(c, event_id=f"{c.event_id}-C") if c.event_id in taken else c for c in cands]
    scs = _with_ids(scs_raw, rng_by_id, "V2")
    ars_raw, ar_others = _ar_events(df, scs_raw, distribution, cfg)
    ars = _with_ids(ars_raw, rng_by_id, "V2")
    ar_others = _with_ids(ar_others, rng_by_id, "V2C")
    sc_children = _with_ids(_sc_children(df, scs_raw, cfg), rng_by_id, "V2")
    sts_raw, st_others = _st_events(df, ranges, scs_raw, distribution, ars_raw, cfg)
    sts = _with_ids(sts_raw, rng_by_id, "V2")
    st_others = _with_ids(st_others, rng_by_id, "V2C")
    sc_others = _with_ids(sc_others, rng_by_id, "V2C")
    everything = events + candidates + springs + quick + lps + cands + distribution + scs + sc_children + sc_others + ars + ar_others + sts + st_others
    assessments = _log_sc_assessments(df, events, scs, sc_others, _assess_all(df, everything, rng_by_id, cfg))
    assessments = _log_lps_assessments(df, events, lps, [c for c in cands if c.kind == EventType.LPS], assessments)
    assessments = _log_redefined_assessments(df, events + distribution, (EventType.AR, EventType.AR_D), ar_others + ars,
                                             "không đạt định nghĩa AR: thiếu phản ứng biên độ lớn hoặc chưa rời vùng cao trào đủ xa", assessments)
    assessments = _log_redefined_assessments(df, events + distribution, (EventType.ST, EventType.ST_D), st_others + sts,
                                             "không đạt định nghĩa ST: không có phản ứng giá hoặc còn áp lực mạnh", assessments)
    new_view = [e for e in events if e.kind not in (EventType.LPS, EventType.ST)] + lps + springs + quick + [e for e in sts if e.kind == EventType.ST]
    verdicts = _range_verdicts(df, ranges, stages, hyps, new_view, swings, scs, assessments, cfg)
    dist_view = [e for e in distribution if e.kind != EventType.ST_D] + [e for e in sts if e.kind == EventType.ST_D]
    dist_verdicts = _distribution_verdicts(df, ranges, stages, hyps, new_view, dist_view, swings, assessments, verdicts, cfg)
    primary = {r.range_id: _primary_verdict(verdicts.get(r.range_id), dist_verdicts.get(r.range_id))[0] for r in ranges}
    series = _revise_phases(phases, hyps, springs, scs, assessments)
    # Range có đại diện là Distribution thì không vẽ pha Accumulation / Re-accumulation
    non_dist = {rid: v for rid, v in primary.items() if v is not None and not v.is_distribution}
    series = _accumulation_phases(df, series, ranges, non_dist, hyps, new_view + sc_children, scs, assessments, cfg)
    series = _distribution_phases(df, series, ranges, primary, new_view, distribution, assessments, cfg)
    return RevisionResult(hypotheses=hyps, events=springs + quick + lps + scs + sc_children + ars + sts, candidates=cands + sc_others + ar_others + st_others, assessments=assessments,
                          phase_series=series, phase_segments=_segments(series),
                          labels={e.event_id: f"{_event_name(e)} {vn_ts(e.date)}" for e in everything},
                          range_verdicts=verdicts, distribution_verdicts=dist_verdicts)
