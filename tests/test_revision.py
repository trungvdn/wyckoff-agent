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


def _rebreak_closes(bars_below: int) -> list[float]:
    """Thoát xuống, quay lại range, rồi thủng lần nữa `bars_below` phiên."""
    return _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 20.5, 20.6, 20.7, 20.6, 20.5, 20.6] + [18.8 - 0.1 * i for i in range(bars_below)]


def test_markdown_reopens_when_support_breaks_again() -> None:
    res = analyze(_frame(_rebreak_closes(4)), _cfg())
    h = res.revision.hypothesis_of_range(_exit_range(res).range_id)
    assert [v.status for v in h.history] == [POTENTIAL, REJECTED, POTENTIAL]
    assert h.status_at(h.history[1].idx) == REJECTED and h.status == POTENTIAL
    assert "thủng lại" in h.reason
    assert any(c["status"] == POTENTIAL and "thủng lại" in c["reason"] for c in res.revision.changes())


def test_markdown_stays_rejected_when_second_break_is_short() -> None:
    res = analyze(_frame(_rebreak_closes(2) + [20.5, 20.6, 20.5, 18.8, 18.7] + [20.5]), _cfg())
    h = res.revision.hypothesis_of_range(_exit_range(res).range_id)
    assert [v.status for v in h.history] == [POTENTIAL, REJECTED]


def test_reopened_markdown_is_rejected_again_on_return() -> None:
    res = analyze(_frame(_rebreak_closes(4) + [20.5, 20.6]), _cfg())
    h = res.revision.hypothesis_of_range(_exit_range(res).range_id)
    assert [v.status for v in h.history] == [POTENTIAL, REJECTED, POTENTIAL, REJECTED]


def _reaction_setup(after_climax: list[float], flip: bool = False):
    """Đi ngang rồi cao trào ở phiên 40, sau đó `after_climax`. `flip`: lật giá thành phía BC."""
    from wyckoff.detectors.events import _make_event
    from wyckoff.indicators.core import add_indicators

    closes = [20.0] * 40 + [20.0] + after_climax
    if flip:
        closes = [40.0 - x for x in closes]
    cfg = _cfg()
    df = add_indicators(_frame(closes), cfg.indicators)
    return df, _make_event(df, EventType.BC if flip else EventType.SC, 40, 40, None, {}), cfg


def test_ar_confirmed_on_completed_swing_after_strong_reaction() -> None:
    from wyckoff.revision import _ar_reactions

    df, sc, cfg = _reaction_setup([20.0, 20.1, 21.5, 22.0, 22.4, 22.2, 22.1, 22.0, 21.9, 21.8])
    r = _ar_reactions(df, [sc], "up", cfg)[0]
    assert r["t0"] == 43 and r["peak"] == 45 and r["conf"] == 48     # không nằm ngay phiên sau cao trào; pivot 3 phiên
    assert r["rej"] is None


def test_ar_stays_candidate_until_swing_completes() -> None:
    from wyckoff.revision import _ar_reactions

    df, sc, cfg = _reaction_setup([20.0, 20.1, 21.5, 22.0, 22.4])
    r = _ar_reactions(df, [sc], "up", cfg)[0]
    assert r["t0"] == 43 and r["conf"] is None and r["rej"] is None


def test_mild_recovery_is_not_ar() -> None:
    from wyckoff.revision import _ar_reactions

    df, sc, cfg = _reaction_setup([20.02 + 0.01 * i for i in range(15)] + [20.1] * 30)
    assert _ar_reactions(df, [sc], "up", cfg) == []


def test_ar_rejected_when_climax_zone_is_lost_before_swing() -> None:
    from wyckoff.revision import _ar_reactions

    df, sc, cfg = _reaction_setup([20.0, 20.1, 21.5, 22.0, 22.4, 17.0, 16.5, 16.0, 15.5])
    r = _ar_reactions(df, [sc], "up", cfg)[0]
    assert r["conf"] is None and r["rej"][1] == "lost"


def test_distribution_ar_mirrors_accumulation_ar() -> None:
    from wyckoff.revision import _ar_reactions

    after = [20.0, 20.1, 21.5, 22.0, 22.4, 22.2, 22.1, 22.0, 21.9, 21.8]
    up, down = _reaction_setup(after), _reaction_setup(after, flip=True)
    a, b = _ar_reactions(up[0], [up[1]], "up", up[2])[0], _ar_reactions(down[0], [down[1]], "down", down[2])[0]
    assert (a["t0"], a["peak"], a["conf"]) == (b["t0"], b["peak"], b["conf"])


def test_ar_events_store_range_bound_and_follow_parent() -> None:
    from dataclasses import replace as dc_replace

    from wyckoff.detectors.models import StatusChange
    from wyckoff.revision import _ar_events

    df, sc, cfg = _reaction_setup([20.0, 20.1, 21.5, 22.0, 22.4, 22.2, 22.1, 22.0, 21.9, 21.8])
    (ar,), others = _ar_events(df, [sc], [], cfg)
    assert not others and ar.kind == EventType.AR and ar.details["ar_high"] == df["high"].iloc[45]
    assert ar.details["sc_low"] == df["low"].iloc[40] and ar.history[0].status == EventStatus.CANDIDATE
    gone = dc_replace(sc, history=sc.history + (StatusChange(EventStatus.INVALIDATED, 47, df.index[47], "x"),))
    (ar2,), _ = _ar_events(df, [gone], [], cfg)
    assert ar2.history[-1].status == EventStatus.INVALIDATED and ar2.history[-1].idx == 48


def _st_setup(tail: list[float], overrides: dict[int, float] | None = None, flip: bool = False, floor_at: int | None = None):
    """Cao trào phiên 40 (volume x4), AR đỉnh phiên 47, rồi `tail` từ phiên 51. `flip`: lật giá thành phía BC."""
    from wyckoff.detectors.events import _make_event
    from wyckoff.indicators.core import add_indicators

    closes = [20.0] * 40 + [19.0, 19.2, 19.3, 21.0, 21.6, 22.0, 22.3, 22.5, 22.3, 22.2, 22.1] + tail
    if flip:
        closes = [40.0 - x for x in closes]
    cfg = _cfg()
    df = add_indicators(_frame(closes, overrides={40: 4.0, **(overrides or {})}), cfg.indicators)
    kind, ar_kind = (EventType.BC, EventType.AR_D) if flip else (EventType.SC, EventType.AR)
    par = _make_event(df, kind, 40, 40, None, {})
    ar = _make_event(df, ar_kind, 47, 50, None, {("bc_date" if flip else "sc_date"): f"{df.index[40]:%Y-%m-%d}"})
    if floor_at is not None:
        df["floor_locked"] = False
        df.iloc[floor_at, df.columns.get_loc("floor_locked")] = True
    return df, par, ar, cfg


_ST_TAIL = [21.5, 20.8, 20.2, 19.6, 19.3, 19.2, 19.4, 19.9, 20.6, 21.0, 21.2]


def test_st_confirmed_when_zone_holds_and_price_reacts() -> None:
    from wyckoff.revision import _st_tests

    df, par, ar, cfg = _st_setup(_ST_TAIL)
    r = _st_tests(df, par, ar, "up", np.inf, cfg)[0]
    assert r["conf"] is not None and r["rej"] is None and r["idx"] <= r["conf"]
    assert r["volume_vs"] < 0.7 and r["stop"] - r["k"] >= 1      # kiểm tra có thể kéo dài nhiều phiên


def test_st_is_optional_and_needs_return_to_zone() -> None:
    from wyckoff.revision import _st_tests

    df, par, ar, cfg = _st_setup([21.9, 22.0, 21.8, 22.1] * 5)    # không quay lại vùng SC
    assert _st_tests(df, par, ar, "up", np.inf, cfg) == []


def test_st_rejected_on_climax_like_pressure_or_floor_lock() -> None:
    from wyckoff.revision import _st_tests

    i = 51 + 5
    df, par, ar, cfg = _st_setup(_ST_TAIL, overrides={i: 4.0})
    df.iloc[i, df.columns.get_loc("high")] = df["high"].iloc[i] + 3.0      # biên độ rộng hơn cao trào, volume như cao trào
    assert _st_tests(df, par, ar, "up", np.inf, cfg)[0]["rej"][1] == "pressure"
    df2, par2, ar2, cfg2 = _st_setup(_ST_TAIL, floor_at=i)
    assert _st_tests(df2, par2, ar2, "up", np.inf, cfg2)[0]["rej"][1] == "pressure"


def test_st_rejected_when_zone_is_pierced_deep_or_no_reaction() -> None:
    from wyckoff.revision import _st_tests

    df, par, ar, cfg = _st_setup([21.5, 20.8, 20.2, 19.6, 19.3, 16.0, 15.8])
    assert _st_tests(df, par, ar, "up", np.inf, cfg)[0]["rej"][1] == "deep"
    df, par, ar, cfg = _st_setup([21.5, 20.8, 20.2, 19.6, 19.3] + [19.3] * 14)
    assert _st_tests(df, par, ar, "up", np.inf, cfg)[0]["rej"][1] == "no_reaction"


def test_failed_st_does_not_invalidate_parent_and_later_st_possible() -> None:
    from wyckoff.revision import _st_tests

    tail = [21.5, 20.8, 20.2, 19.6, 19.3] + [19.3] * 14 + [21.0, 21.5, 21.8, 21.2, 20.5, 19.9, 19.4, 19.3, 19.9, 20.6, 21.0]
    df, par, ar, cfg = _st_setup(tail)
    res = _st_tests(df, par, ar, "up", np.inf, cfg)
    assert res[0]["rej"][1] == "no_reaction" and any(r["conf"] is not None for r in res[1:])


def test_distribution_st_mirrors_accumulation_st() -> None:
    from wyckoff.revision import _st_tests

    up = _st_setup(_ST_TAIL)
    down = _st_setup(_ST_TAIL, flip=True)
    a = _st_tests(*up[:3], "up", np.inf, up[3])[0]
    b = _st_tests(*down[:3], "down", np.inf, down[3])[0]
    assert (a["k"], a["conf"], a["rej"]) == (b["k"], b["conf"], b["rej"])


def test_st_events_follow_parent_rejection() -> None:
    from dataclasses import replace as dc_replace

    from wyckoff.detectors.models import StatusChange
    from wyckoff.revision import _st_events

    df, par, ar, cfg = _st_setup(_ST_TAIL)
    (st, *_), _ = _st_events(df, [], [par], [], [ar], cfg)
    assert st.kind == EventType.ST and st.details["st_definition"] and st.history[0].status == EventStatus.CANDIDATE
    known = st.confirmed_idx
    gone = dc_replace(par, history=par.history + (StatusChange(EventStatus.INVALIDATED, known + 1, df.index[known + 1], "x"),))
    (st2, *_), _ = _st_events(df, [], [gone], [], [ar], cfg)
    assert st2.history[-1].status == EventStatus.INVALIDATED


def test_multi_bar_spring_marked_at_session_with_lowest_high() -> None:
    res, found = _dip([19.8, 19.6, 19.3, 19.7, 20.4, 20.5], overrides={4: 3.0})
    e = found[0]
    assert e.details["recovery_bars"] == 5 and e.idx == len(_DIP_HEAD) + 2     # high thấp nhất, không phải phiên xuyên đầu tiên
    assert e.details["penetration_date"] == f"{res.df.index[len(_DIP_HEAD)]:%Y-%m-%d}"
    assert e.details["lowest_low"] == res.df["low"].iloc[len(_DIP_HEAD):len(_DIP_HEAD) + 5].min()


def test_spring_test_follows_spring_rejection() -> None:
    res, found = _dip([19.7, 19.7, 19.7, 20.1, 20.0, 20.0, 20.1, 18.0, 17.5, 17.0], overrides={0: 3.0})
    assert res.revision.status_of(found[0]) == REJECTED
    t = next(x for x in res.revision.events if x.kind == EventType.TEST and x.details.get("spring_date") == f"{found[0].date:%Y-%m-%d}")
    assert res.revision.status_of(t) == REJECTED


def _second_dip(recover_at: int, volume_mult: float = 3.0) -> pd.DataFrame:
    """Thoát xuống, quay lại range, low lại thủng support 20 và hồi ở phiên thứ `recover_at`, tính cả phiên thủng."""
    head = _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 20.5, 20.6, 20.7, 20.6, 20.5, 20.6]
    dip = [19.7] * (recover_at - 1) + [20.8]
    closes = head + dip + [20.8, 20.7]
    return _frame(closes, overrides={len(head) + recover_at - 1: volume_mult})


def _quick(res) -> list:
    return [e for e in res.revision.events if e.details.get("spring_type") == "quick"]


def test_quick_spring_confirmed_on_recovery_with_demand() -> None:
    res = analyze(_second_dip(4), _cfg())
    found = _quick(res)
    assert len(found) == 1
    e = found[0]
    assert e.kind == EventType.SPRING and e.details["recovery_bars"] == 4 and e.details["bars_below_support"] == 3
    assert res.revision.status_of(e) == CONFIRMED
    assert res.revision.assessments[e.event_id][0].status == POTENTIAL


def test_spring_speed_label_follows_bars_to_reclaim() -> None:
    assert not _quick(analyze(_second_dip(5), _cfg()))              # quá 4 phiên: nhãn kéo dài
    late = [e for e in analyze(_second_dip(5), _cfg()).revision.events if e.kind == EventType.SPRING and e.details["spring_type"] == "extended"]
    assert late and late[-1].details["recovery_bars"] == 5


_DIP_HEAD = _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 20.5, 20.6, 20.7, 20.6, 20.5, 20.6]


def _dip(after: list[float], overrides: dict[int, float] | None = None):
    """Cú xuyên support 20 sau khi range đã thoát rồi quay lại; `overrides`: vị trí trong `after` -> bội số volume."""
    frame = _frame(_DIP_HEAD + after, overrides={len(_DIP_HEAD) + i: m for i, m in (overrides or {}).items()})
    res = analyze(frame, _cfg())
    b = len(_DIP_HEAD)
    return res, [e for e in res.revision.events + res.revision.candidates if e.kind == EventType.SPRING and e.idx >= b]


def test_spring_fails_without_demand_reaction_after_reclaim() -> None:
    _, found = _dip([19.7, 19.7, 19.7] + [20.1] * 18)
    assert len(found) == 1 and "không có phản ứng cầu" in found[0].history[-1].reason


def test_spring_candidate_stays_open_until_reaction() -> None:
    res, found = _dip([19.7, 19.7, 19.7, 20.1])
    assert len(found) == 1 and res.revision.status_of(found[0]) == POTENTIAL


def test_spring_fails_when_support_not_reclaimed_or_new_low() -> None:
    _, found = _dip([19.7] * 16)
    assert found and found[0].history[-1].status == EventStatus.INVALIDATED
    _, found = _dip([19.7, 19.7, 19.7, 20.1, 19.0, 19.0])
    assert found and "đáy mới" in found[0].history[-1].reason


def test_plain_breakdown_is_not_spring() -> None:
    _, found = _dip([19.6, 19.2, 18.8, 18.4, 18.0, 17.6, 17.2])    # đóng cửa gần đáy liên tục, không từ chối giá thấp
    assert not found


def test_high_volume_spring_is_valid_and_confirmed_by_test() -> None:
    res, found = _dip([19.7, 19.7, 19.7, 20.1, 20.0, 20.0], overrides={0: 3.0})
    e = found[0]
    assert res.revision.status_of(e) == CONFIRMED and e.details["volume_profile"] == "cao" and e.details["confirmation"].startswith("Test")
    assert [t for t in res.revision.events if t.kind == EventType.TEST and t.details.get("spring_date") == f"{e.date:%Y-%m-%d}"]


def test_quick_spring_rejected_when_close_breaks_low() -> None:
    df = _second_dip(4)
    tail = df.iloc[[-1]].copy()
    tail.index = pd.bdate_range(df.index[-1] + pd.offsets.BDay(1), periods=1)
    tail[["open", "high", "low", "close"]] = [20.7, 20.7, 17.5, 17.6]
    res = analyze(pd.concat([df, tail]), _cfg())
    e = _quick(res)[0] if _quick(res) else None
    assert e is not None and res.revision.status_of(e) == REJECTED


def test_range_box_extends_to_last_bar_while_structure_is_current() -> None:
    from wyckoff.agent.payload import build_payload
    from wyckoff.web.viewmodel import build_view

    res = analyze(_second_dip(4), _cfg())
    rid = res.reopened_range_id()
    assert rid == _exit_range(res).range_id
    view = build_view(res, build_payload(res, "X"), "X", "1D")
    box = next(r for r in view["ranges"] if r["id"] == rid)
    assert box["i1"] == len(res.df) - 1 and box["active"] is False
    assert any(c["kind"] == "Spring" and c["status"] == CONFIRMED and c["i"] == _quick(res)[0].idx for c in view["chart_events"])
    assert any("hồi phục nhanh" in x["text"] for x in view["events"])


def test_view_has_ema_cross_data() -> None:
    from wyckoff.agent.payload import build_payload
    from wyckoff.web.viewmodel import build_view

    res = analyze(_second_dip(4), _cfg())
    v = build_view(res, build_payload(res, "X"), "X", "1D")
    assert v["ema_periods"] == [9, 21]
    assert v["bars"][0]["ema_fast"] is None and v["bars"][-1]["ema_fast"] is not None and v["bars"][19]["ema_slow"] is None
    close = res.df["close"]
    assert v["bars"][-1]["ema_slow"] == pytest.approx(close.ewm(span=21, adjust=False).mean().iloc[-1], abs=1e-3)
    for x in v["ema_crosses"]:
        now, before = v["bars"][x["i"]], v["bars"][x["i"] - 1]
        assert (now["ema_fast"] > now["ema_slow"]) == x["up"] and (before["ema_fast"] > before["ema_slow"]) != x["up"]


def test_stage_strip_follows_range_box() -> None:
    from wyckoff.web.viewmodel import stage_segments

    res = analyze(_second_dip(4), _cfg())
    segs = stage_segments(res)
    r = _exit_range(res)
    at = lambda i: next(s for s in segs if s["i0"] <= i <= s["i1"])    # noqa: E731
    assert at(r.start_idx)["kind"] == "range"                          # từ đầu range, không phải từ phiên xác nhận range
    assert at(len(res.df) - 1) == at(r.start_idx + 1) or at(len(res.df) - 1)["kind"] == "range"   # còn là cấu trúc hiện tại: kéo đến phiên cuối
    assert sorted((s["i0"], s["i1"]) for s in segs) == [(s["i0"], s["i1"]) for s in segs]
    assert all(a["i1"] < b["i0"] for a, b in zip(segs, segs[1:]))      # không chồng lấn
    assert not any(a["kind"] == b["kind"] and a["label"] == b["label"] for a, b in zip(segs, segs[1:]))   # cùng nhãn thì gộp


def test_candidate_structure_overlays_strip() -> None:
    from wyckoff.web.viewmodel import stage_segments

    closes = DECLINE + _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 20.5, 20.6, 20.7, 20.6, 20.5, 20.6]
    res = analyze(_frame(closes), _cfg())
    rid = _exit_range(res).range_id
    v = res.revision.primary_of(rid)[0]
    assert v is not None
    seg = next(s for s in stage_segments(res) if s["i0"] <= v.start_idx <= s["i1"])
    if v.status == POTENTIAL:
        assert seg["kind"] == "accumulation_potential" and seg["label"] == "Accumulation?"
    assert seg["kind"] != "none"


def test_explanation_follows_stage_card_when_structure_is_live() -> None:
    from wyckoff.agent.payload import build_payload, stage_conclusion
    from wyckoff.agent.report import template_explanation
    from wyckoff.agent.validate import validate_explanation
    from wyckoff.web.viewmodel import build_view

    n = len(DECLINE) + len(_range_closes())
    closes = DECLINE + _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 19.3, 20.8, 21.0]
    res = analyze(_frame(closes, overrides={n + 8: 3.0}), _cfg())
    payload = build_payload(res, "X")
    assert payload["current_stage"]["stage"] == "Markdown" and payload["current_phase"]["phase"] != payload["revision"]["phase"]["phase"]
    c = stage_conclusion(payload)
    assert c is not None and payload["revision"]["trend"]["status"] == REJECTED
    view = build_view(res, payload, "X", "1D")
    t = template_explanation(payload)
    assert c["title"] == view["stage"]["title"] and t["summary"].startswith(f"Giai đoạn: {c['title']}")
    assert "Trending Down" not in t["summary"] and "vô hiệu" not in t["summary"] and "đã bị bác bỏ" in t["summary"]
    assert validate_explanation(t, payload) == []
    # Nêu nhãn của nhật ký thay vì kết luận của thẻ thì không qua kiểm tra
    bad = {**t, "summary": t["summary"].replace(c["title"], "Trending Down")}
    assert any("loại cấu trúc" in e for e in validate_explanation(bad, payload))
    assert view["target_down"] is None                                  # mục tiêu theo cấu trúc còn hiệu lực, không theo xu hướng đã bác bỏ
    assert c["phase"] != "C" or view["target"] is not None


def test_explanation_keeps_log_view_without_live_structure() -> None:
    from wyckoff.agent.payload import build_payload, stage_conclusion
    from wyckoff.agent.report import template_explanation
    from wyckoff.agent.validate import validate_explanation

    res = analyze(_frame(_rebreak_closes(4)), _cfg())   # Markdown được mở lại, còn đứng
    payload = build_payload(res, "X")
    assert stage_conclusion(payload) is None
    t = template_explanation(payload)
    assert "Trending Down (Markdown tiềm năng)" in t["summary"] and validate_explanation(t, payload) == []


def test_range_box_stops_when_markdown_stands() -> None:
    res = analyze(_frame(_rebreak_closes(4)), _cfg())    # Markdown được mở lại, còn đứng
    assert res.reopened_range_id() is None


def test_watch_window_counts_from_last_close_in_range() -> None:
    from wyckoff.revision import _watch_stop

    c = np.array([19.0] * 5 + [20.5] * 3 + [19.0] * 20)      # support 20, resistance 22; trong range ở phiên 5, 6, 7
    assert _watch_stop(c, 2, 20.0, 22.0, 4, len(c) - 1) == 11      # 7 + 4
    assert _watch_stop(c[:5], 2, 20.0, 22.0, 2, 4) == 4            # không quay lại: x + 2
    assert _watch_stop(np.array([19.0] * 40), 2, 20.0, 22.0, 30, 39) == 32
    assert _watch_stop(c, 2, 20.0, 22.0, 4, 9) == 9                # không vượt giới hạn
    above = np.array([19.0, 20.5] + [23.0] * 20)                   # trên resistance không được tính là trong range
    assert _watch_stop(above, 0, 20.0, 22.0, 4, 21) == 5


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
    assert sp.kind == EventType.SPRING and sp.confirmed_idx == recovery and sp.idx == n + 3    # phiên có high thấp nhất
    assert res.revision.status_of(sp) == CONFIRMED
    assert sp.event_id.endswith("-V2")
    # Biểu đồ hồi cứu: không còn vô hiệu do thoát xuống, về pha C từ phiên hồi
    ph = res.revision.phase_series["phase"]
    assert ph.iloc[recovery] == "C" and ph.iloc[recovery - 1] == "C" and ph.iloc[sp.idx] == "C"
    assert not (ph == "potential").any()
    assert res.phases.series["phase"].iloc[recovery] == "invalid"   # nhật ký giữ nguyên


def test_spring_confirmed_by_strong_reaction_without_demand_bar() -> None:
    closes = _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 19.3, 20.8, 21.0, 21.1, 21.0, 21.1, 21.0, 21.1]
    res = analyze(_frame(closes), _cfg())   # volume đều: không có phiên demand, nhưng giá phản ứng mạnh
    sp = [e for e in res.revision.events if e.details.get("spring_type") == "extended"]
    assert sp and "phản ứng tăng" in sp[0].details["confirmation"]


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


def _staircase_frame() -> pd.DataFrame:
    """Như MSB: tăng theo bậc thang, mỗi nhịp điều chỉnh chỉ 3 phiên."""
    base = DECLINE + _range_closes()
    closes: list[float] = []
    mult: list[float] = []
    p = 22.6
    for _ in range(8):
        for _ in range(5):
            p += 0.3
            closes.append(p)
            mult.append(1.8)
        for _ in range(3):
            p -= 0.12
            closes.append(p)
            mult.append(0.6)
    return _frame(base + closes, overrides={len(base) + i: m for i, m in enumerate(mult)})


def test_staircase_markup_confirmed_with_short_pivots() -> None:
    """Nhịp điều chỉnh ngắn: pivot 3 phiên thấy được HH-HL, pivot 5 phiên thì bỏ sót."""
    df = _staircase_frame()
    cfg = _cfg()
    assert CONFIRMED in [v.status for v in _markup(analyze(df, cfg)).history]
    long_pivot = replace(cfg, revision=replace(cfg.revision, mk_pivot_bars=5))
    assert CONFIRMED not in [v.status for v in _markup(analyze(df, long_pivot)).history]


def test_markup_pivot_setting_does_not_change_ranges() -> None:
    """Pivot của Markup không ảnh hưởng biên range và nhật ký."""
    df = _staircase_frame()
    cfg = _cfg()
    a = analyze(df, cfg)
    b = analyze(df, replace(cfg, revision=replace(cfg.revision, mk_pivot_bars=5)))
    assert [(r.start_idx, r.support, r.resistance) for r in a.ranges] == [(r.start_idx, r.support, r.resistance) for r in b.ranges]
    pd.testing.assert_series_equal(a.phases.series["phase"], b.phases.series["phase"])


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
    if v.status == DEVELOPING or v.leaning == "Re-accumulation":
        assert market["state"] == "Markup" and "Re-accumulation" in market["structure"]    # trạng thái vẫn là Markup
    else:
        assert market["state"] is None and "chưa phân định" in market["structure"]         # chưa có bằng chứng cung cầu


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
    assert view["stage"]["market"]["state"] in (None, "Markup")
    assert view["stage"]["accumulation"]["structure_type"] == "Re-accumulation"
    assert any("Re-acc" in s["label"] for s in view["stage_segments"])


def _dist_frame(after: list[float] | None = None, after_vols: dict[int, float] | None = None) -> tuple[pd.DataFrame, float, float]:
    """Markup, rồi range ở đỉnh với nhịp tăng yếu, nhịp giảm mạnh và đỉnh thấp dần, rồi `after`."""
    base = DECLINE + _range_closes()
    up, mult = _uptrend(legs=5)
    top = up[-1]
    side: list[float] = []
    vols: list[float] = []
    # Ba sóng trong range, đỉnh thấp dần: phiên giảm volume cao, phiên tăng volume thấp
    for peak in (top, top - 0.1, top - 0.2, top - 0.3):
        for k in range(8):
            side.append(peak - 0.15 * (k + 1))
            vols.append(2.2)
        for k in range(8):
            side.append(peak - 1.2 + (1.1 * (k + 1) / 8))
            vols.append(0.6)
    low = top - 1.5
    overrides = {len(base) + i: m for i, m in enumerate(mult)}
    overrides.update({len(base) + len(up) + i: m for i, m in enumerate(vols)})
    closes = base + up + side + (after or [])
    start_side = len(base) + len(up)
    start_after = start_side + len(side)
    for i, m in (after_vols or {}).items():
        overrides[start_after + i] = m
    df = _frame(closes, overrides=overrides)
    # Phiên giảm trong range có biên độ rộng hơn phiên tăng
    pos_high, pos_low = df.columns.get_loc("high"), df.columns.get_loc("low")
    for i in range(start_side, start_after):
        if closes[i] < closes[i - 1]:
            df.iloc[i, pos_high] += 0.12
            df.iloc[i, pos_low] -= 0.12
    return df, low, top


def _dist_verdict(res):
    return next((v for v in res.revision.distribution_verdicts.values()), None)


def test_distribution_candidate_and_developing_inside_range() -> None:
    df, _, _ = _dist_frame()
    res = analyze(df, _cfg())
    v = _dist_verdict(res)
    assert v is not None and v.status in (POTENTIAL, DEVELOPING) and v.is_distribution
    met = {c.key: c.met for c in v.conditions}
    assert met["supply_emerging"] and not met["breakdown"]


def test_distribution_confirmed_on_backed_breakdown_without_utad() -> None:
    """Không cần UTAD, BC: phá hỗ trợ có volume và spread xác nhận, cấu trúc LH-LL."""
    _, low0, _ = _dist_frame()
    drop = [low0 - 0.3, low0 - 0.8, low0 - 1.3, low0 - 1.8, low0 - 2.2, low0 - 2.5, low0 - 2.8]
    df, _, _ = _dist_frame(after=drop, after_vols={0: 2.5, 1: 2.5, 2: 2.5})
    res = analyze(df, _cfg())
    v = _dist_verdict(res)
    assert v is not None and CONFIRMED in [x.status for x in v.history] and v.leaning == "Distribution"
    assert not [s for s in v.supporting if s.startswith("UTAD")]
    reacc = _reacc_verdict(res)
    assert reacc is None or reacc.status == REJECTED
    assert any(s["kind"] in ("distribution", "distribution_developing") for s in _view_segments(res))


def _view_segments(res) -> list[dict]:
    from wyckoff.web.viewmodel import stage_segments

    return stage_segments(res)


def test_distribution_rejected_when_breakout_holds() -> None:
    """Thoát lên và giữ được: không phải đỉnh giả, Distribution bị bác bỏ."""
    _, _, top = _dist_frame()
    tail = [top + 0.5 + 0.2 * i for i in range(20)]
    df, _, _ = _dist_frame(after=tail, after_vols={i: 1.8 for i in range(20)})
    res = analyze(df, _cfg())
    v = _dist_verdict(res)
    assert v is not None and v.status == REJECTED


def test_reaccumulation_and_distribution_share_prior_markup_condition() -> None:
    """Cùng một range: hoặc được xét cả hai giả thuyết, hoặc không giả thuyết nào, tùy một điều kiện chung."""
    from wyckoff.revision import _prior_markup

    df, _, _ = _reacc_frame()
    res = analyze(df, _cfg())
    close = res.df["close"].to_numpy(dtype=float)
    prior = {x.range_id: x.prior_stage for x in res.stages.ranges}
    for g in res.ranges:
        ok = _prior_markup(g, close, res.revision.hypotheses, prior.get(g.range_id), res.cfg)[0]
        main = res.revision.range_verdicts.get(g.range_id)
        assert not (main is not None and main.is_reaccumulation) or ok
        assert g.range_id not in res.revision.distribution_verdicts or ok


def test_prior_rise_counts_but_not_after_markdown() -> None:
    from wyckoff.revision import _prior_markup

    df, _, _ = _reacc_frame()
    cfg = _cfg()
    res = analyze(df, replace(cfg, ranges=replace(cfg.ranges, context_lookback=120)))
    close = res.df["close"].to_numpy(dtype=float)
    rng = res.ranges[-1]
    no_hyps: list = []
    assert _prior_markup(rng, close, no_hyps, None, res.cfg)[0] is True           # tăng kéo dài từ đáy
    assert _prior_markup(rng, close, no_hyps, "Markdown", res.cfg)[0] is False    # trước range là Markdown thì không tính


def test_candidate_without_supply_demand_evidence_is_undecided() -> None:
    from wyckoff.revision import RangeVerdict, Verdict, _primary_verdict

    ts = pd.Timestamp("2024-01-01")
    only = RangeVerdict(1, "Re-accumulation", 0, 1, (Verdict(POTENTIAL, 0, ts),), leaning="chưa rõ")
    assert _primary_verdict(only, None)[1] is False
    assert _primary_verdict(replace(only, leaning="Re-accumulation"), None)[1] is True


def test_primary_verdict_resolves_reaccumulation_vs_distribution() -> None:
    from wyckoff.revision import RangeVerdict, Verdict, _primary_verdict

    ts = pd.Timestamp("2024-01-01")
    def mk(typ: str, status: str, lean: str) -> RangeVerdict:
        return RangeVerdict(1, typ, 0, 1, (Verdict(status, 0, ts),), leaning=lean)

    # Mức cao hơn thắng
    assert _primary_verdict(mk("Re-accumulation", DEVELOPING, "chưa rõ"), mk("Distribution", POTENTIAL, "chưa rõ"))[0].is_reaccumulation
    # Cùng mức: theo hướng nghiêng
    assert _primary_verdict(mk("Re-accumulation", POTENTIAL, "chưa rõ"), mk("Distribution", POTENTIAL, "Distribution"))[0].is_distribution
    # Cùng mức, chưa rõ: chưa phân định
    assert _primary_verdict(mk("Re-accumulation", POTENTIAL, "chưa rõ"), mk("Distribution", POTENTIAL, "chưa rõ"))[1] is False
    # Một bên bị bác bỏ thì bên còn lại là đại diện
    assert _primary_verdict(mk("Re-accumulation", REJECTED, "chưa rõ"), mk("Distribution", POTENTIAL, "chưa rõ"))[0].is_distribution


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
        "dist": (_dist_frame(after=[28.0, 27.0, 26.0, 25.0, 24.5, 24.0, 23.5], after_vols={0: 2.5, 1: 2.5, 2: 2.5})[0], _cfg()),
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


@pytest.mark.parametrize("name", ["demo", "demo_close", "return", "sos", "downtrend", "climax", "accumulation", "markup", "reacc", "dist"])
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
        for rid, v in full.distribution_verdicts.items():
            got = cut.distribution_verdicts.get(rid)
            assert v.status_at(t) == (got.status if got is not None else None), (name, t, rid, "dist")


def test_view_carries_status_and_revised_segments() -> None:
    from wyckoff.agent.payload import build_payload
    from wyckoff.web.viewmodel import build_view, stage_view

    n = len(DECLINE) + len(_range_closes())
    closes = DECLINE + _range_closes() + [19.2, 19.0, 18.9, 18.9, 19.0, 19.1, 19.2, 19.3, 20.8, 21.0, 21.1, 21.0, 21.1, 21.0, 21.1]
    res = analyze(_frame(closes, overrides={n + 8: 3.0}), _cfg())
    payload = build_payload(res, "X")
    view = build_view(res, payload, "X", "1D")
    assert payload["payload_version"] == "10"
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


def test_view_shows_live_structure_with_evidence_level() -> None:
    from wyckoff.web.viewmodel import stage_view

    cur = {"range_id": None, "stage": "Markdown", "candidates": [], "structure_type": "Trending Down", "reason": "x", "strength": None}
    rejected = {"status": REJECTED, "reason": "close quay lại support"}
    live = {"range_id": 1, "level": DEVELOPING, "structure_type": "Initial Accumulation", "watch_end": "2026-11-19",
            "evidence": {"met": 4, "total": 8, "level": "trung bình"}}
    v = stage_view(cur, [], rejected, live)
    assert v["view"] == "range" and v["title"] == "Accumulation đang hình thành"
    assert v["evidence"]["level"] == "trung bình" and v["reason"] == "close quay lại support"
    assert stage_view(cur, [], rejected, {**live, "level": CONFIRMED})["title"] == "Initial Accumulation"
    candidate = stage_view(cur, [], rejected, {**live, "level": POTENTIAL})
    assert candidate["view"] == "range" and candidate["title"] == "Accumulation đang hình thành" and candidate["evidence"] is not None
    # Trong range: tên cấu trúc thay cho danh sách giả thuyết
    in_range = {**cur, "range_id": 1, "stage": None, "candidates": ["Accumulation", "Distribution"]}
    assert stage_view(in_range, [], None, live)["title"] == "Accumulation đang hình thành"
    assert stage_view(in_range, [], None, None)["title"] == "Accumulation hoặc Distribution"
    # Xu hướng còn đứng thì giai đoạn là xu hướng đó, không phải cấu trúc
    up = stage_view({**cur, "stage": "Markup"}, [], {"status": CONFIRMED, "reason": "y"}, live)
    assert up["view"] == "trend" and up["title"] == "Markup" and up["evidence"] is None


def test_evidence_level_is_share_of_conditions_met() -> None:
    from wyckoff.revision import Condition, RangeVerdict

    def level(met: int, total: int = 8) -> str:
        conds = tuple(Condition(str(i), "x", i < met, "") for i in range(total))
        return RangeVerdict(1, "Accumulation", 0, 1, (), conds).evidence(_cfg().revision)["level"]

    assert [level(n) for n in (3, 4, 5, 6)] == ["thấp", "trung bình", "trung bình", "cao"]


def test_live_structure_expires_after_watch_window() -> None:
    from wyckoff.revision import RangeVerdict, RevisionResult, Verdict

    day = pd.Timestamp("2026-10-01")
    end = pd.Timestamp("2026-11-19")
    v = RangeVerdict(1, "Accumulation", 0, 1, (Verdict(DEVELOPING, 0, day, "r"),), watch_end=end)
    rv = RevisionResult([], [], [], {}, pd.DataFrame(), [], range_verdicts={1: v})
    assert rv.live_structure(1, end) is v
    assert rv.live_structure(1, end + pd.Timedelta(days=1)) is None   # bằng chứng đã ngừng cập nhật: không còn là hiện tại
    assert rv.live_structure(None, end) is None


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
