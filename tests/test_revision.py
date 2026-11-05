"""Lớp đánh giá lại: tiềm năng / xác nhận / bác bỏ, sự kiện mới, không nhìn trước, không đổi kết quả cũ."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from wyckoff.config import Config, RangeConfig, load_config
from wyckoff.detectors.models import EventStatus, EventType
from wyckoff.detectors.swings import find_swings
from wyckoff.pipeline import analyze
from wyckoff.revision import CONFIRMED, DEVELOPING, POTENTIAL, REJECTED
from wyckoff.synthetic import make_wyckoff_accumulation


def _frame(closes: list[float], volume: float = 1_000_000.0, overrides: dict[int, float] | None = None) -> pd.DataFrame:
    """Nến nhỏ quanh close; `overrides`: phiên -> bội số volume."""
    c = np.array(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    idx = pd.bdate_range("2024-01-01", periods=len(c))
    v = np.full(len(c), volume)
    for i, m in (overrides or {}).items():
        v[i] = volume * m
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.05, "low": np.minimum(o, c) - 0.05, "close": c, "volume": v}, index=idx)


def _range_closes(bars: int = 80, low: float = 20.0, high: float = 22.0, period: int = 16) -> list[float]:
    """Đi ngang dao động đều giữa low và high: đủ swing để xác nhận range."""
    return [low + (high - low) * (0.5 + 0.5 * np.sin(2 * np.pi * i / period)) for i in range(bars)]


def _cfg() -> Config:
    return replace(Config(), ranges=RangeConfig(pivot_source="close", context_lookback=20))


def _exit_range(res) -> object:
    return next(r for r in res.ranges if r.exit_direction == "down")


def test_find_swings_source_close_uses_close_series() -> None:
    df = make_wyckoff_accumulation()
    sw = find_swings(df, source="close")
    closes = set(df["close"].round(6))
    assert sw and all(round(s.price, 6) in closes for s in sw)


def test_default_config_stays_high_low_v3_uses_close() -> None:
    assert Config().ranges.pivot_source == "high_low"
    assert load_config("config/v3.yaml").ranges.pivot_source == "close"
    assert replace(load_config("config/v3.yaml"), ranges=Config().ranges) == Config()


def test_unknown_pivot_source_rejected() -> None:
    with pytest.raises(ValueError, match="pivot_source"):
        analyze(make_wyckoff_accumulation(), replace(Config(), ranges=RangeConfig(pivot_source="median")))


def test_revision_does_not_change_log_results() -> None:
    """Pha, giai đoạn, sự kiện của nhật ký không phụ thuộc lớp đánh giá lại."""
    res = analyze(make_wyckoff_accumulation(), Config())
    own = {e.event_id for e in res.revision.events + res.revision.candidates}
    assert not own & {e.event_id for e in res.events + res.candidates}
    assert not any(e.details.get("spring_type") == "extended" or e.details.get("lps_definition") for e in res.events)


def test_markdown_rejected_when_close_returns_to_support() -> None:
    closes = _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 20.5, 21.0, 21.2, 21.4, 21.0, 21.2, 21.0, 21.1]
    res = analyze(_frame(closes), _cfg())
    rng = _exit_range(res)
    h = res.revision.hypothesis_of_range(rng.range_id)
    assert h.stage == "Markdown" and h.history[0].status == POTENTIAL and h.status == REJECTED
    assert closes[h.history[-1].idx] >= rng.support
    assert not any(v.status == CONFIRMED for v in h.history)


def _downtrend(start: float = 19.6, legs: int = 5) -> tuple[list[float], list[float]]:
    """Giảm từng nhịp: phiên giảm volume cao, nhịp hồi ngắn volume thấp. Trả về (close, bội số volume)."""
    closes: list[float] = []
    mult: list[float] = []
    p = start
    for _ in range(legs):
        for _ in range(8):
            p -= 0.3
            closes.append(p)
            mult.append(1.6)
        for _ in range(7):
            p += 0.1
            closes.append(p)
            mult.append(0.6)
    return closes, mult


def _downtrend_frame(tail: list[float] | None = None, legs: int = 5) -> pd.DataFrame:
    base = _range_closes()
    drop, mult = _downtrend(legs=legs)
    closes = base + drop + (tail or [])
    return _frame(closes, overrides={len(base) + i: m for i, m in enumerate(mult)})


def _conditions(h) -> dict[str, bool]:
    return {c.key: c.met for c in h.conditions}


def test_markdown_confirmed_needs_all_five_conditions() -> None:
    res = analyze(_downtrend_frame(), _cfg())
    h = res.revision.hypothesis_of_range(_exit_range(res).range_id)
    conf = next(v for v in h.history if v.status == CONFIRMED)
    assert conf.idx > h.start_idx
    assert _conditions(h) == {"breakdown": True, "lh_ll": True, "weak_rally": True, "supply": True, "no_demand": True}
    assert res.phases.series["phase"].iloc[conf.idx] == res.revision.phase_series["phase"].iloc[conf.idx] == "invalid"


def test_sharp_fall_alone_is_not_markdown() -> None:
    """Giảm mạnh liền một mạch: thủng hỗ trợ nhưng không có LH–LL và nhịp hồi, vẫn chỉ là tiềm năng."""
    closes = _range_closes() + [19.0 - 0.25 * i for i in range(40)]
    res = analyze(_frame(closes), _cfg())
    h = res.revision.hypothesis_of_range(_exit_range(res).range_id)
    assert h.status == POTENTIAL
    met = _conditions(h)
    assert met["breakdown"] and not met["lh_ll"]


def test_markdown_not_confirmed_when_supply_does_not_dominate() -> None:
    base = _range_closes()
    drop, _ = _downtrend()     # cùng cấu trúc giá, volume đều
    res = analyze(_frame(base + drop), _cfg())
    h = res.revision.hypothesis_of_range(_exit_range(res).range_id)
    assert h.status == POTENTIAL and not _conditions(h)["supply"]


def test_utad_and_supporting_events_are_not_conditions() -> None:
    res = analyze(_downtrend_frame(), _cfg())
    h = res.revision.hypothesis_of_range(_exit_range(res).range_id)
    assert set(_conditions(h)) == {"breakdown", "lh_ll", "weak_rally", "supply", "no_demand"}
    assert all(s.split()[0] in ("SOW", "LPSY") for s in h.supporting)


def test_confirmed_markdown_only_rejected_by_resistance() -> None:
    drop, _ = _downtrend(legs=3)
    bounce = list(np.linspace(drop[-1], 23.0, 20))
    res = analyze(_downtrend_frame(bounce, legs=3), _cfg())
    rng = _exit_range(res)
    h = res.revision.hypothesis_of_range(rng.range_id)
    assert [v.status for v in h.history] == [POTENTIAL, CONFIRMED, REJECTED]
    assert res.df["close"].iloc[h.history[-1].idx] >= rng.resistance


def test_confirmed_markdown_keeps_status_after_watch_window() -> None:
    """Vượt resistance sau cửa sổ theo dõi 60 phiên kể từ xác nhận không bác bỏ Markdown đã xảy ra."""
    drop, _ = _downtrend(legs=5)
    bounce = list(np.linspace(drop[-1], 23.0, 20))
    res = analyze(_downtrend_frame(bounce, legs=5), _cfg())
    h = res.revision.hypothesis_of_range(_exit_range(res).range_id)
    assert h.status == CONFIRMED


def test_extended_spring_needs_demand_and_confirms_at_recovery() -> None:
    n = len(DECLINE) + len(_range_closes())
    closes = DECLINE + _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 19.3, 20.8, 21.0, 21.1, 21.0, 21.1, 21.0, 21.1]
    recovery = n + 8
    res = analyze(_frame(closes, overrides={recovery: 3.0}), _cfg())
    springs = [e for e in res.revision.events if e.details.get("spring_type") == "extended"]
    assert len(springs) == 1
    sp = springs[0]
    assert sp.kind == EventType.SPRING and sp.confirmed_idx == recovery and sp.idx < n + 3
    assert sp.details["breakdown"] in ("yếu", "mạnh")
    assert res.revision.status_of(sp) == CONFIRMED
    assert sp.event_id.endswith("-EXT")
    # Biểu đồ hồi cứu: không còn vô hiệu do thoát xuống, về pha C từ phiên hồi
    ph = res.revision.phase_series["phase"]
    assert ph.iloc[recovery] == "C" and ph.iloc[recovery - 1] == "C" and ph.iloc[sp.idx] == "C"
    assert not (ph == "potential").any()
    assert res.phases.series["phase"].iloc[recovery] == "invalid"   # nhật ký giữ nguyên


def test_no_extended_spring_without_demand() -> None:
    closes = _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 19.3, 20.8, 21.0, 21.1, 21.0, 21.1, 21.0, 21.1]
    res = analyze(_frame(closes), _cfg())   # volume đều: không có phiên demand
    assert not [e for e in res.revision.events if e.details.get("spring_type") == "extended"]
    assert [e for e in res.revision.candidates if e.details.get("spring_type") == "extended"]
    assert (res.revision.phase_series["phase"] == "potential").any()   # không có Spring: vùng vẫn là chờ


def _phases(res) -> list[str]:
    return [g.phase for g in res.revision.phase_segments]


def test_range_without_accumulation_has_no_phases() -> None:
    """Phase A đến E là của Accumulation: range không sau Markdown chỉ là TR chưa xác định."""
    df, _ = _sos_then_pullback()
    res = analyze(df, _cfg())
    assert not res.revision.range_verdicts
    assert not set(_phases(res)) & {"A", "B", "C", "D", "E"}
    assert set(res.phases.series["phase"].dropna()) & {"B", "D", "E"}       # nhật ký vẫn giữ pha cũ


def test_phases_follow_accumulation_order_without_spring() -> None:
    """Không có Spring thì không có pha C; pha vẫn đi theo thứ tự thời gian."""
    df, _ = _sos_then_pullback(prefix=DECLINE)
    res = analyze(df, _cfg())
    assert res.revision.range_verdicts
    assert not [e for e in res.revision.events if e.kind == EventType.SPRING]
    names = [p for p in _phases(res) if p in "ABCDE"]
    assert "C" not in names and names == sorted(names) and names[:2] == ["A", "B"] and names[-1] == "E"


def test_phase_d_does_not_need_sos() -> None:
    """Cầu chiếm ưu thế, giá ở nửa trên range, đáy cao hơn trong đủ số phiên: có pha D dù chưa có SOS."""
    base = DECLINE + _range_closes()
    n = len(base)
    wave = [20.3, 20.6, 20.9, 21.2, 21.5, 21.7, 21.8] + [21.6, 21.3, 21.0, 20.8, 20.6, 20.6] \
        + [20.9, 21.1, 21.3, 21.4, 21.5, 21.6, 21.65, 21.7, 21.75, 21.8, 21.85, 21.9]    # đáy 20,6 cao hơn đáy 20 của range, chưa tới resistance
    closes = base + wave
    overrides = {n + i: (1.6 if wave[i] > wave[i - 1] else 0.6) for i in range(1, len(wave))}
    res = analyze(_frame(closes, overrides=overrides), _cfg())
    assert not [e for e in res.events if e.kind == EventType.SOS]
    rid = res.ranges[-1].range_id
    v = res.revision.range_verdicts[rid]
    assert v.demand_idx is not None
    assert res.revision.phase_series["phase"].iloc[v.demand_idx] == "D"


def test_support_break_cancels_demand_mark() -> None:
    """Close thủng support sau khi có mốc cầu kiểm soát: mốc bị bỏ, Spring sau đó vẫn là pha C."""
    base = DECLINE + _range_closes()
    n = len(base)
    rise = [20.3, 20.8, 21.0, 20.6, 20.8, 21.1, 21.3, 21.0, 20.9, 21.2, 21.4, 21.5, 21.3, 21.2, 21.5, 21.6, 21.7, 21.5, 21.4, 21.7]
    closes = base + rise + [20.5, 19.6, 19.4, 19.3, 19.4, 19.5, 20.9, 21.2, 21.3, 21.2]
    recovery = n + len(rise) + 6
    overrides = {n + i: (2.0 if rise[i] > rise[i - 1] else 0.6) for i in range(1, len(rise))}
    overrides[recovery] = 3.0
    res = analyze(_frame(closes, overrides=overrides), _cfg())
    sp = [e for e in res.revision.events if e.details.get("spring_type") == "extended"]
    rid = res.ranges[0].range_id if len(res.ranges) == 1 else sp[0].range_id if sp else res.ranges[-1].range_id
    v = res.revision.range_verdicts[rid]
    assert v.demand_idx is None or v.demand_idx > n + len(rise)


def _uptrend(start: float = 22.6, legs: int = 5) -> tuple[list[float], list[float]]:
    """Tăng từng nhịp: phiên tăng volume cao, nhịp điều chỉnh ngắn volume thấp, đỉnh và đáy cao dần."""
    closes: list[float] = []
    mult: list[float] = []
    p = start
    for _ in range(legs):
        for _ in range(8):
            p += 0.35
            closes.append(p)
            mult.append(1.8)
        for _ in range(7):
            p -= 0.12
            closes.append(p)
            mult.append(0.6)
    return closes, mult


def _markup_frame(legs: int = 5, tail: list[float] | None = None) -> pd.DataFrame:
    base = DECLINE + _range_closes()
    up, mult = _uptrend(legs=legs)
    return _frame(base + up + (tail or []), overrides={len(base) + i: m for i, m in enumerate(mult)})


def _markup(res):
    return next(h for h in res.revision.hypotheses if h.stage == "Markup" and h.source == "range_exit")


def test_markup_confirmed_through_several_swings() -> None:
    res = analyze(_markup_frame(), _cfg())
    h = _markup(res)
    assert [v.status for v in h.history] == [POTENTIAL, DEVELOPING, CONFIRMED]
    met = {c.key: c.met for c in h.conditions}
    assert met["hh_hl_multi"] and met["support"] and met["dominance"] and met["maintained"]
    assert h.state in ("Established Markup", "Extended Markup")


def test_few_strong_sessions_are_not_markup() -> None:
    """Một vài phiên tăng mạnh, chưa có nhịp điều chỉnh: chỉ là tiềm năng."""
    up, mult = _uptrend(legs=1)
    base = DECLINE + _range_closes()
    res = analyze(_frame(base + up[:8], overrides={len(base) + i: m for i, m in enumerate(mult[:8])}), _cfg())
    assert _markup(res).status == POTENTIAL and _markup(res).state == "Early Markup"


def test_markup_without_base_stays_potential() -> None:
    """Tăng theo SMA50 mà không có nền giá trước đó thì không xác nhận được."""
    up, mult = _uptrend(start=10.0, legs=8)
    res = analyze(_frame(list(np.linspace(14.0, 10.0, 60)) + up, overrides={60 + i: m for i, m in enumerate(mult)}), _cfg())
    sma = [h for h in res.revision.hypotheses if h.stage == "Markup" and h.source == "sma"]
    assert sma and all(h.status != CONFIRMED for h in sma)
    assert all(not {c.key: c.met for c in h.conditions}.get("prior_structure", False) for h in sma if h.conditions)


def test_markup_weakening_on_lower_high() -> None:
    """Đã xác nhận rồi tạo đỉnh thấp hơn: suy yếu, chưa phải bác bỏ."""
    up, _ = _uptrend(legs=5)
    tail = [up[-1] - 0.2 * i for i in range(1, 8)] + [up[-1] - 1.4 + 0.15 * i for i in range(1, 7)] + [up[-1] - 0.5 - 0.2 * i for i in range(1, 8)]
    res = analyze(_markup_frame(tail=tail), _cfg())
    h = _markup(res)
    assert CONFIRMED in [v.status for v in h.history]
    assert h.status == CONFIRMED and h.state == "Markup Weakening"


def test_markup_rejected_below_support() -> None:
    drop = [24.0, 22.0, 20.0, 19.0, 18.0, 17.0, 16.0]
    res = analyze(_markup_frame(legs=2, tail=drop), _cfg())
    h = _markup(res)
    assert h.status == REJECTED and "thủng support" in h.reason


def _reacc_frame(legs: int = 5, after: list[float] | None = None, after_vol: float = 1.0) -> tuple[pd.DataFrame, float, float]:
    """Markup theo từng nhịp, rồi đi ngang ở vùng cao, rồi `after`. Trả về (frame, support, resistance) dự kiến."""
    base = DECLINE + _range_closes()
    up, mult = _uptrend(legs=legs)
    top = up[-1]
    low, high = top - 2.0, top
    side = _range_closes(low=low, high=high)
    overrides = {len(base) + i: m for i, m in enumerate(mult)}
    closes = base + up + side + (after or [])
    for i in range(len(after or [])):
        overrides[len(closes) - len(after) + i] = after_vol
    return _frame(closes, overrides=overrides), low, high


def _reacc_verdict(res):
    return next((v for v in res.revision.range_verdicts.values() if v.is_reaccumulation), None)


def test_range_after_clear_markup_is_reaccumulation_structure_not_trend() -> None:
    df, _, _ = _reacc_frame()
    res = analyze(df, _cfg())
    v = _reacc_verdict(res)
    assert v is not None and v.status in (POTENTIAL, DEVELOPING) and v.leaning is not None
    assert {c.key: c.met for c in v.conditions}["structure"]
    market = res.revision.market_view(res.current_stage().range_id, res.current_stage().range_id is not None, res.df.index[-1])
    assert market["state"] == "Markup" and "Re-accumulation" in market["structure"]    # trạng thái vẫn là Markup


def test_markup_then_range_is_not_automatically_reaccumulation() -> None:
    """Markup chưa rõ (chưa có HH-HL) thì range sau đó chưa phải Re-accumulation."""
    base = DECLINE + _range_closes()
    up, mult = _uptrend(legs=1)
    top = up[7]
    res = analyze(_frame(base + up[:8] + _range_closes(low=top - 2.0, high=top), overrides={len(base) + i: m for i, m in enumerate(mult[:8])}), _cfg())
    assert _reacc_verdict(res) is None


def test_reaccumulation_rejected_when_uptrend_structure_breaks() -> None:
    df, low, _ = _reacc_frame(after=[low_step for low_step in np.linspace(29.0, 22.0, 12)])
    res = analyze(df, _cfg())
    v = _reacc_verdict(res)
    assert v is not None and v.status == REJECTED


def test_reaccumulation_confirmed_after_breakout_held() -> None:
    _, _, high = _reacc_frame()
    tail = [high + 0.5, high + 1.2, high + 1.6, high + 1.8, high + 1.5, high + 1.3, high + 1.2, high + 1.3, high + 1.6, high + 2.0, high + 2.3, high + 2.5,
            high + 2.3, high + 2.1, high + 2.0, high + 2.2, high + 2.6, high + 3.0, high + 3.3, high + 3.5]
    df, _, _ = _reacc_frame(after=tail, after_vol=1.8)
    res = analyze(df, _cfg())
    v = _reacc_verdict(res)
    assert v is not None and CONFIRMED in [x.status for x in v.history] and v.leaning == "Re-accumulation"
    names = [g.phase for g in res.revision.phase_segments if g.range_id == v.range_id]
    assert names and names[-1] == "E"
    assert any(g.reason.startswith("Markup Resumption") for g in res.revision.phase_segments)


def test_view_marks_reaccumulation_segment_and_market() -> None:
    from wyckoff.agent.payload import build_payload
    from wyckoff.web.viewmodel import build_view

    df, _, _ = _reacc_frame()
    res = analyze(df, _cfg())
    view = build_view(res, build_payload(res, "X"), "X", "1D")
    assert view["stage"]["market"]["state"] == "Markup"
    assert view["stage"]["accumulation"]["structure_type"] == "Re-accumulation"
    assert any("Re-acc" in s["label"] for s in view["stage_segments"])


def test_rejected_extended_spring_falls_back_to_potential() -> None:
    n = len(_range_closes())
    closes = _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 19.3, 20.8, 21.0, 20.0, 18.0, 16.5, 16.0, 15.5]
    res = analyze(_frame(closes, overrides={n + 8: 3.0}), _cfg())
    sp = next(e for e in res.revision.events if e.details.get("spring_type") == "extended")
    assert sp.invalidated is not None and res.revision.status_of(sp) == REJECTED
    ph = res.revision.phase_series["phase"]
    assert ph.iloc[sp.confirmed_idx] != "C" and ph.iloc[sp.idx] != "C"


def _acc_conditions(v) -> dict[str, bool]:
    return {c.key: c.met for c in v.conditions}


def test_accumulation_confirmed_after_breakout_demand_and_structure() -> None:
    df, back = _sos_then_pullback(prefix=DECLINE)
    res = analyze(df, _cfg())
    rid = _lps_reclaim(res)[0].range_id
    v = res.revision.accumulation_of(rid)
    assert v is not None and v.structure_type in ("Initial Accumulation", "Accumulation")
    conf = next(x for x in v.history if x.status == CONFIRMED)
    assert conf.idx >= back
    met = _acc_conditions(v)
    assert met["breakout"] and met["dominance"] and met["hold"] and met["hh_hl"]
    assert any(c["subject"].endswith(v.structure_type) for c in res.revision.changes(20))


def test_range_without_prior_markdown_is_not_accumulation() -> None:
    """Có SOS và LPS nhưng trước đó không có Markdown: chỉ là Trading Range chưa xác định."""
    df, _ = _sos_then_pullback()
    res = analyze(df, _cfg())
    assert _lps_reclaim(res) and not res.revision.range_verdicts


def test_accumulation_does_not_need_lps_or_spring() -> None:
    """Không có LPS: breakout giữ được hỗ trợ đủ lâu và có đáy cao hơn vẫn xác nhận được."""
    base = DECLINE + _range_closes()
    n = len(base)
    closes = base + [22.6, 23.4, 23.8, 24.2, 24.4, 24.5, 24.3, 24.1, 23.9, 23.8, 23.7, 23.8, 24.0, 24.3, 24.6, 24.8, 25.0, 25.1, 25.2, 25.3]
    overrides = {n: 2.0, n + 1: 3.0, n + 2: 2.0, n + 3: 2.0}
    res = analyze(_frame(closes, overrides=overrides), _cfg())
    rng = next(r for r in res.ranges if r.exit_direction == "up")
    assert not [e for e in res.revision.events if e.details.get("lps_definition") and res.revision.status_of(e) == CONFIRMED and e.range_id == rng.range_id]
    assert res.revision.accumulation_of(rng.range_id) is not None


def test_accumulation_levels_candidate_then_developing_in_range() -> None:
    """Đang trong range sau Markdown, chưa breakout: chưa thể là Confirmed."""
    res = analyze(_frame(DECLINE + _range_closes()), _cfg())
    assert res.ranges
    v = res.revision.range_verdicts[res.ranges[-1].range_id]
    assert v.history[0].status in (POTENTIAL, DEVELOPING)
    assert v.status in (POTENTIAL, DEVELOPING)
    assert not _acc_conditions(v)["breakout"]


def test_accumulation_rejected_when_markdown_confirmed() -> None:
    base = DECLINE + _range_closes()
    drop, mult = _downtrend()
    res = analyze(_frame(base + drop, overrides={len(base) + i: m for i, m in enumerate(mult)}), _cfg())
    v = res.revision.range_verdicts[_exit_range(res).range_id]
    assert v.status == REJECTED and "Markdown" in v.history[-1].reason


def _append(df: pd.DataFrame, tail: list[float]) -> pd.DataFrame:
    extra = pd.bdate_range(df.index[-1] + pd.Timedelta(days=1), periods=len(tail))
    c = np.array(tail)
    o = np.r_[df["close"].iloc[-1], c[:-1]]
    more = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.05, "low": np.minimum(o, c) - 0.05, "close": c, "volume": 1_000_000.0}, index=extra)
    return pd.concat([df, more])


def test_lps_survives_shallow_short_dip_below_resistance() -> None:
    """Như MSN: sau khi xác nhận, close xuống dưới resistance không quá 3% và không quá 4 phiên: LPS vẫn còn."""
    df, _ = _sos_then_pullback(prefix=DECLINE)
    res = analyze(_append(df, [24.0, 23.0, 21.8, 21.6, 21.7, 23.0, 23.5, 23.8]), _cfg())
    lps = _lps_reclaim(res)[0]
    assert res.revision.status_of(lps) == CONFIRMED
    assert res.revision.accumulation_of(lps.range_id) is not None


@pytest.mark.parametrize("tail, why", [
    ([24.0, 23.0, 21.0, 22.5, 23.0], "sâu hơn"),
    ([24.0, 23.0, 21.8, 21.8, 21.8, 21.8, 21.8, 23.0, 23.5], "liên tiếp"),
])
def test_lps_rejected_but_accumulation_keeps_label(tail: list[float], why: str) -> None:
    """LPS thất bại không gỡ nhãn khi SOS còn hiệu lực và giá chưa thủng support."""
    df, _ = _sos_then_pullback(prefix=DECLINE)
    res = analyze(_append(df, tail), _cfg())
    lps = _lps_reclaim(res)[0]
    assert res.revision.status_of(lps) == REJECTED and why in lps.history[-1].reason
    assert res.revision.accumulation_of(lps.range_id) is not None


def test_new_sc_after_breakdown_cancels_extended_spring() -> None:
    """Như MSN: thoát xuống, tạo SC mới rồi mới hồi với demand: không còn là Spring của range cũ."""
    base = _range_closes()
    n = len(base)
    fall = [19.3, 18.9, 18.5, 18.0, 17.6, 17.2, 16.8, 16.4, 15.0]          # n + 8: phiên climax
    rally = [15.6, 16.4, 17.2, 17.9, 18.6, 19.2, 19.7, 21.0, 21.2, 21.3]    # n + 16: hồi lại trên support với demand
    frame = _frame(base + fall + rally, overrides={n + 8: 4.0, n + 16: 3.0})
    res = analyze(frame, replace(_cfg(), sc=replace(Config().sc, min_decline=0.1, lowest_low_lookback=20, trend_lookback=20)))
    new_sc = [e for e in res.revision.events if e.kind == EventType.SC and e.idx == n + 8]
    assert new_sc and new_sc[0].confirmed_idx <= n + 16
    assert not [e for e in res.revision.events if e.details.get("spring_type") == "extended"]
    cand = [e for e in res.revision.candidates if e.details.get("spring_type") == "extended"]
    assert cand and "SC mới" in cand[0].history[-1].reason


def test_view_events_include_sos_of_current_range() -> None:
    from wyckoff.agent.payload import build_payload
    from wyckoff.web.viewmodel import build_view

    df, _ = _sos_then_pullback()
    res = analyze(df, _cfg())
    view = build_view(res, build_payload(res, "X"), "X", "1D")
    kinds = [e["kind"] for e in view["events"]]
    assert "SOS" in kinds and "LPS" in kinds
    assert len({(e["kind"], e["date"]) for e in view["events"]}) == len(view["events"])


def test_accumulation_rejected_when_price_breaks_support() -> None:
    df, back = _sos_then_pullback(prefix=DECLINE)
    res = analyze(_append(df, [24.0, 22.0, 20.0, 18.0, 17.0, 16.0]), _cfg())
    rid = _lps_reclaim(res)[0].range_id
    v = res.revision.range_verdicts[rid]
    assert v.status == REJECTED and res.revision.accumulation_of(rid) is None
    assert any(x.status == CONFIRMED for x in v.history)


PULLBACK = [22.8, 22.3, 22.05, 21.9]      # thân nến hẹp dần, về sát resistance 22
PULL_VOLS = [1.0, 0.8, 0.6, 0.4]          # volume giảm dần


DECLINE = list(np.linspace(45.0, 21.0, 70))    # Markdown trước range: giảm đủ 15% trong context_lookback = 20 phiên của _cfg()


def _sos_then_pullback(
    pullback: list[float] | None = None, vols: list[float] | None = None, demand_vol: float | None = 3.0,
    after: list[float] | None = None, prefix: list[float] | None = None,
) -> tuple[pd.DataFrame, int]:
    pullback = PULLBACK if pullback is None else pullback
    vols = PULL_VOLS if vols is None else vols
    base = (prefix or []) + _range_closes()
    after = [23.8, 24.0, 24.1, 24.2] if after is None else after
    closes = base + [22.6, 23.4, 23.6] + pullback + after
    sos = len(base) + 1
    back = sos + 2 + len(pullback)
    overrides = {len(base): 2.0, sos: 3.0}
    start = sos + 2
    for i, v in enumerate(vols):
        overrides[start + i] = v
    if demand_vol:
        overrides[back] = demand_vol
    return _frame(closes, overrides=overrides), back


def _lps_reclaim(res) -> list:
    return [e for e in res.revision.events if e.details.get("lps_definition")]


def _lps_candidates(res) -> list:
    return [e for e in res.revision.candidates if e.details.get("lps_definition")]


def test_lps_candidate_then_confirmed_by_demand_response() -> None:
    df, back = _sos_then_pullback()
    res = analyze(df, _cfg())
    assert [e for e in res.events if e.kind == EventType.SOS], "cần có SOS để kiểm tra"
    lps = _lps_reclaim(res)
    assert len(lps) == 1 and lps[0].confirmed_idx == back and lps[0].idx < back
    assert [h.status for h in lps[0].history][:2] == [EventStatus.CANDIDATE, EventStatus.CONFIRMED]
    assert lps[0].details["strength"] == "SOS" and lps[0].event_id.endswith("-V2")


def test_lps_candidate_stays_open_without_reaction_yet() -> None:
    df, _ = _sos_then_pullback(demand_vol=None, after=[])
    res = analyze(df, _cfg())
    assert not _lps_reclaim(res)
    cand = _lps_candidates(res)
    assert cand and res.revision.status_of(cand[0]) == POTENTIAL


def test_lps_needs_declining_volume_and_narrowing_spread() -> None:
    """Điều chỉnh với volume tăng dần thì chỉ là nhịp điều chỉnh thông thường."""
    df, _ = _sos_then_pullback(vols=[0.4, 0.6, 0.8, 1.2])
    res = analyze(df, _cfg())
    assert not _lps_reclaim(res) and not _lps_candidates(res)


def test_lps_rejected_by_heavy_supply_bar() -> None:
    """Phiên giảm volume lớn, biên độ rộng: cung còn mạnh, ứng viên bị bác bỏ."""
    df, _ = _sos_then_pullback(pullback=[22.8, 22.3, 22.05, 21.9, 21.5], vols=[1.0, 0.8, 0.6, 0.4, 3.0], after=[21.6, 21.7])
    i = len(_range_closes()) + 7
    df.loc[df.index[i], "high"] = 22.6
    df.loc[df.index[i], "low"] = 21.3
    res = analyze(df, _cfg())
    assert not _lps_reclaim(res)
    cand = _lps_candidates(res)
    assert cand and "cung còn mạnh" in cand[0].history[-1].reason


@pytest.mark.parametrize("pullback, why", [
    (PULLBACK + [21.85, 21.85, 21.85, 21.85, 21.85], "liên tiếp"),   # quá 4 phiên dưới hỗ trợ
    (PULLBACK + [20.8], "sâu hơn"),                                  # sâu quá 3%
])
def test_lps_candidate_rejected_when_support_breaks(pullback: list[float], why: str) -> None:
    vols = PULL_VOLS + [0.4] * (len(pullback) - len(PULL_VOLS))
    df, _ = _sos_then_pullback(pullback=pullback, vols=vols, demand_vol=None, after=[21.8, 21.8])
    res = analyze(df, _cfg())
    assert not _lps_reclaim(res)
    cand = _lps_candidates(res)
    assert cand and why in cand[0].history[-1].reason


def test_lps_not_confirmed_without_reaction() -> None:
    df, _ = _sos_then_pullback(demand_vol=None, after=[21.95, 21.9, 21.95, 22.0, 21.95, 22.0, 21.95, 22.0])
    res = analyze(df, _cfg())
    assert not _lps_reclaim(res)
    cand = _lps_candidates(res)
    assert cand and "không có phản ứng" in cand[0].history[-1].reason


def test_lps_floor_locked_bar_is_not_weak_selling() -> None:
    """Phiên khóa sàn volume thấp không phải cung yếu, kể cả khi vẫn trong giới hạn hỗ trợ."""
    cfg = _cfg()
    cfg = replace(cfg, revision=replace(cfg.revision, lps_max_depth=0.10))
    df, _ = _sos_then_pullback(demand_vol=None, after=[20.42, 20.5, 20.6])
    i = len(_range_closes()) + 7
    df.loc[df.index[i], "low"] = 20.40
    res = analyze(df, cfg)
    assert res.df["floor_locked"].iloc[i]
    cand = _lps_candidates(res)
    assert not _lps_reclaim(res) and cand and "khóa sàn" in cand[0].history[-1].reason


def test_lps_ceiling_locked_response_counts_without_volume() -> None:
    """Phiên khóa trần volume thấp: không có người bán, vẫn tính là cầu quay lại."""
    close = PULLBACK[-1] * 1.07
    df, back = _sos_then_pullback(demand_vol=None, after=[close, close + 0.2, close + 0.3])
    df.loc[df.index[back], "high"] = close
    df.loc[df.index[back], "volume"] = 200_000.0
    res = analyze(df, _cfg())
    assert res.df["ceiling_locked"].iloc[back]
    lps = _lps_reclaim(res)
    assert lps and lps[0].confirmed_idx == back and lps[0].details["demand_ceiling_locked"]


def test_lps_low_liquidity_is_skipped() -> None:
    df, _ = _sos_then_pullback()
    res = analyze(df.assign(volume=df["volume"] / 1000), _cfg())
    assert not _lps_reclaim(res) and not _lps_candidates(res)


def test_lps_after_internal_sos_inside_range() -> None:
    """SOS nội bộ: nến mạnh vượt đỉnh swing gần nhất nhưng chưa tới resistance."""
    base = _range_closes() + [20.4] * 6 + [20.6, 20.8, 21.0, 20.9, 20.7, 20.6, 20.5, 20.45, 20.4, 20.4]
    strong = len(base)
    closes = base + [21.6, 21.4, 21.25, 21.15, 21.1, 21.7, 21.8, 21.8]
    vols = {strong: 3.0, strong + 1: 1.0, strong + 2: 0.8, strong + 3: 0.6, strong + 4: 0.4, strong + 5: 3.0}
    res = analyze(_frame(closes, overrides=vols), _cfg())
    assert not [e for e in res.events if e.kind == EventType.SOS]    # chưa có SOS của range
    lps = _lps_reclaim(res)
    assert len(lps) == 1 and lps[0].details["strength"] == "SOS nội bộ" and lps[0].confirmed_idx == strong + 5
    assert lps[0].details["support_level"] == pytest.approx(21.0)
    # Accumulation vẫn cần SOS của range
    assert res.revision.accumulation_of(lps[0].range_id) is None


def test_log_lps_without_match_is_rejected_for_chart_only() -> None:
    res = analyze(make_wyckoff_accumulation(), Config())
    own = {(e.range_id, e.idx) for e in res.revision.events + res.revision.candidates if e.details.get("lps_definition")}
    for e in res.events:
        if e.kind == EventType.LPS and (e.range_id, e.idx) not in own:
            assert res.revision.status_of(e) == REJECTED
            assert e.is_confirmed       # nhật ký không đổi


def test_view_shows_only_new_definition_lps() -> None:
    from wyckoff.agent.payload import build_payload
    from wyckoff.web.viewmodel import build_view

    df, back = _sos_then_pullback()
    res = analyze(df, _cfg())
    view = build_view(res, build_payload(res, "X"), "X", "1D")
    new = {e.idx for e in _lps_reclaim(res) + _lps_candidates(res)}
    assert new and {e["i"] for e in view["chart_events"] if e["kind"] == "LPS"} <= new
    assert all(e["status"] != "rejected" for e in view["events"] if e["kind"] == "LPS")


def test_new_events_have_no_confidence_points() -> None:
    df, _ = _sos_then_pullback()
    res = analyze(df, _cfg())
    assert _lps_reclaim(res)
    for s in res.phases.structures.values():
        assert not any(e.details.get("lps_definition") for e in s.events)


def test_sos_potential_until_follow_through() -> None:
    res = analyze(make_wyckoff_accumulation(), Config())
    sos = next(e for e in res.events if e.kind == EventType.SOS)
    hist = res.revision.assessments[sos.event_id]
    assert hist[0].status == POTENTIAL and hist[0].idx == sos.idx


CUTS = [60, 80, 95, 100, 110, 120, 140, 150, 155, 160, 165, 170, 180, 190, 200, 210, 220, 230, 250, 270, 290, 310]


def _scenarios() -> dict[str, tuple[pd.DataFrame, Config]]:
    closes = _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 19.3, 20.8, 21.0, 21.1, 21.0, 21.1, 21.0, 21.1] \
        + [21.0 + 0.1 * (i % 5) for i in range(30)]
    df_sos, _ = _sos_then_pullback()
    df_acc, _ = _sos_then_pullback(prefix=DECLINE)
    return {
        "reacc": (_reacc_frame(after=list(np.linspace(29.0, 22.0, 12)))[0], _cfg()),
        "markup": (_markup_frame(), _cfg()),
        "accumulation": (_append(df_acc, [24.0, 22.0, 20.0, 18.0, 17.0, 16.0]), _cfg()),
        "climax": (_climax_frame([12.0, 11.95, 12.2, 12.8, 13.2, 13.6, 14.0, 14.2, 14.3] + [14.2] * 30 + [11.0, 10.5] * 4)[0], _cfg()),
        "downtrend": (_downtrend_frame(), _cfg()),
        "demo": (make_wyckoff_accumulation(), Config()),
        "demo_close": (make_wyckoff_accumulation(), _cfg()),
        "return": (_frame(closes, overrides={len(_range_closes()) + 8: 3.0}), _cfg()),
        "sos": (df_sos, _cfg()),
    }


@pytest.mark.parametrize("name", ["demo", "demo_close", "return", "sos", "downtrend", "climax", "accumulation", "markup", "reacc"])
def test_no_lookahead(name: str) -> None:
    """Trạng thái tại phiên t trên dữ liệu đầy đủ = trạng thái cuối khi chạy trên dữ liệu cắt tại t."""
    df, cfg = _scenarios()[name]
    full = analyze(df, cfg).revision
    for t in [c for c in CUTS if c < len(df)]:
        cut = analyze(df.iloc[:t + 1], cfg).revision
        for h in cut.hypotheses:
            other = next(x for x in full.hypotheses if x.start_idx == h.start_idx and x.stage == h.stage)
            assert other.status_at(t) == h.status, (name, t, h.start_date)
        cut_ids = {eid: hist for eid, hist in cut.assessments.items()}
        for eid, hist in cut_ids.items():
            if eid in full.assessments:
                full_hist = full.assessments[eid]
                now = next((v.status for v in reversed(full_hist) if v.idx <= t), None)
                assert now == hist[-1].status, (name, t, eid)
        # Sự kiện mới đã xác nhận tại t trong lần chạy cắt phải trùng với lần chạy đầy đủ
        full_new = {e.event_id for e in full.events if e.confirmed_idx <= t}
        assert {e.event_id for e in cut.events} == full_new, (name, t)
        # Nhãn Accumulation tại t trùng với lần chạy cắt
        for rid, v in full.range_verdicts.items():
            got = cut.range_verdicts.get(rid)
            assert v.status_at(t) == (got.status if got is not None else None), (name, t, rid)


def test_view_carries_status_and_revised_segments() -> None:
    from wyckoff.agent.payload import build_payload
    from wyckoff.web.viewmodel import build_view, stage_view

    n = len(DECLINE) + len(_range_closes())
    closes = DECLINE + _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 19.3, 20.8, 21.0, 21.1, 21.0, 21.1, 21.0, 21.1]
    res = analyze(_frame(closes, overrides={n + 8: 3.0}), _cfg())
    payload = build_payload(res, "X")
    view = build_view(res, payload, "X", "1D")
    assert payload["payload_version"] == "9"
    assert {e["status"] for e in view["chart_events"]} <= {POTENTIAL, CONFIRMED, REJECTED}
    assert not any(g["phase"] == "potential" for g in view["phase_segments"])   # đã có Spring: không còn vùng chờ
    assert any(g["phase"] == "C" for g in view["phase_segments"])
    assert any(e["kind"] == "Spring" and e["status"] == CONFIRMED for e in view["chart_events"])
    assert not any(g["kind"] == "down" for g in view["stage_segments"])   # Markdown bị bác bỏ không còn tô
    # Xu hướng bị bác bỏ hiển thị như chưa có xu hướng, tiềm năng thì ghi rõ
    cur = {"range_id": None, "stage": "Markdown", "candidates": [], "structure_type": "Trending Down", "reason": "x", "strength": {"a": 1}}
    gone = stage_view(cur, [], {"status": REJECTED, "reason": "close quay lại"})
    assert gone["view"] == "transition" and gone["strength"] is None and gone["reason"] == "close quay lại"
    maybe = stage_view(cur, [], {"status": POTENTIAL, "reason": "chờ"})
    assert maybe["view"] == "trend" and maybe["title"] == "Markdown tiềm năng"


def test_view_overlays_accumulation_segment() -> None:
    from wyckoff.web.viewmodel import _overlay_segment

    segs = [{"kind": "down", "label": "Markdown", "i0": 0, "i1": 50}, {"kind": "none", "label": "", "i0": 51, "i1": 60},
            {"kind": "up_potential", "label": "Markup?", "i0": 61, "i1": 70}]
    out = _overlay_segment(segs, {"kind": "accumulation", "label": "Initial Accumulation", "i0": 30, "i1": 60})
    assert [(s["kind"], s["i0"], s["i1"]) for s in out] == [("down", 0, 29), ("accumulation", 30, 60), ("up_potential", 61, 70)]


def _climax_frame(after: list[float], volume_mult: float = 4.0, sc_close: float = 12.1) -> tuple[pd.DataFrame, int]:
    """Giảm đều 70 phiên từ 20 xuống khoảng 13, rồi một phiên giảm mạnh volume đột biến, đóng cửa sát đáy."""
    closes = list(np.linspace(20.0, 13.0, 70))
    i = len(closes)
    closes += [sc_close] + after
    df = _frame(closes, overrides={i: volume_mult})
    df.loc[df.index[i], "low"] = sc_close - 0.05
    return df, i


def _new_sc(res, i: int):
    return next((e for e in res.revision.events + res.revision.candidates if e.kind == EventType.SC and e.idx == i), None)


def test_sc_close_near_low_waits_for_reaction_then_confirms() -> None:
    """Đóng cửa gần Low vẫn là ứng viên; giảm thêm một ít rồi hồi mạnh thì xác nhận."""
    df, i = _climax_frame([12.0, 11.95, 12.2, 12.8, 13.2, 13.6, 14.0, 14.2, 14.3, 14.2, 14.1, 14.0, 14.0])
    res = analyze(df, _cfg())
    sc = _new_sc(res, i)
    assert sc is not None and sc.details["absorption"] == "chờ phản ứng"
    assert [h.status for h in sc.history][:2] == [EventStatus.CANDIDATE, EventStatus.CONFIRMED]
    assert sc.confirmed_idx > i and res.revision.status_of(sc) == CONFIRMED
    assert sc.low <= df["low"].iloc[i]
    assert res.revision.phase_series["phase"].iloc[i] == "A"


def test_sc_keeps_falling_is_rejected() -> None:
    df, i = _climax_frame([11.5, 11.0, 10.5, 10.0, 9.5, 9.0, 8.5, 8.0])
    res = analyze(df, _cfg())
    sc = _new_sc(res, i)
    assert sc is not None and res.revision.status_of(sc) == REJECTED and "thủng đáy" in sc.history[-1].reason
    assert sc.confirmed_idx == -1


def test_sc_needs_climactic_volume() -> None:
    df, i = _climax_frame([12.0, 12.5, 13.5, 14.5, 15.0, 15.0], volume_mult=1.0)
    assert _new_sc(analyze(df, _cfg()), i) is None


def test_sc_needs_prior_decline() -> None:
    """Một phiên giảm mạnh, volume lớn nhưng không có xu hướng giảm trước đó thì không phải SC."""
    base = [20.0 + 0.01 * (k % 3) for k in range(70)]
    df = _frame(base + [19.0, 19.5, 20.0, 20.5, 21.0, 21.0], overrides={70: 4.0})
    assert _new_sc(analyze(df, _cfg()), 70) is None


def test_sc_candidate_stays_open_without_enough_bars() -> None:
    df, i = _climax_frame([12.1])
    sc = _new_sc(analyze(df, _cfg()), i)
    assert sc is not None and sc.status == EventStatus.CANDIDATE


def test_rejected_sc_propagates_to_ar_and_st_status_only() -> None:
    res = analyze(make_wyckoff_accumulation(), Config())
    ids = {e.event_id for e in res.events}
    assert len(ids) == len(res.events)
    for e in res.events:
        if e.kind in (EventType.AR, EventType.ST) and e.invalidated is not None:
            assert "SC" in e.invalidated.reason


def test_since_keeps_revision() -> None:
    res = analyze(make_wyckoff_accumulation(), _cfg())
    start = res.df.index[100]
    trimmed = res.since(start)
    assert trimmed.revision.phase_series.index[0] == start
    assert all(h.end_date >= start for h in trimmed.revision.hypotheses)
