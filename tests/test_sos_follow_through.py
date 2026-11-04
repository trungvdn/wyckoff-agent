"""H5: cờ trần/sàn và SOS follow-through (docs/h5-preregistration.md)."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from wyckoff.config import Config, SOSConfig
from wyckoff.detectors.models import EventStatus, EventType
from wyckoff.indicators.limits import add_limit_flags
from wyckoff.pipeline import analyze
from wyckoff.synthetic import SOS_IDX, make_wyckoff_accumulation

BASE = Config()
FT = replace(BASE, sos=replace(BASE.sos, confirm_mode="follow_through"))
LOCKED = replace(BASE, sos=replace(BASE.sos, confirm_mode="locked_follow_through"))


def _sos(res, candidates: bool = False):
    return [e for e in (res.candidates if candidates else res.events) if e.kind == EventType.SOS]


def _set(df: pd.DataFrame, i: int, o: float, h: float, lo: float, c: float) -> None:
    df.iloc[i, df.columns.get_indexer(["open", "high", "low", "close"])] = [o, h, lo, c]


def _locked_sos_df() -> pd.DataFrame:
    """Phiên SOS tăng trần và khóa trần: close = high = 78,4 (+7,0% so với 73,3)."""
    df = make_wyckoff_accumulation()
    _set(df, SOS_IDX, 73.3, 78.4, 72.8, 78.4)
    return df


# ------------------------------------------------------------------ cờ trần / sàn

def test_limit_flags() -> None:
    idx = pd.bdate_range("2024-01-01", periods=5)
    df = pd.DataFrame({"open": [10, 10, 10.6, 10.0, 9.4], "high": [10, 10.7, 11.3, 10.0, 9.5],
                       "low": [10, 10, 10.6, 9.30, 9.0], "close": [10, 10.7, 11.2, 9.30, 9.0],
                       "volume": [1.0] * 5}, index=idx, dtype=float)
    f = add_limit_flags(df)
    assert f["limit_up"].tolist() == [False, True, False, False, False]
    assert f["ceiling_locked"].tolist() == [False, True, False, False, False]
    assert f["limit_down"].tolist() == [False, False, False, True, False]   # 11,2 -> 9,3 = -17%
    assert f["floor_locked"].tolist() == [False, False, False, True, False]
    # 10,7 -> 11,2 = +4,7%: không phải trần
    assert not f["limit_up"].iloc[2]


def test_limit_flag_in_event_details() -> None:
    res = analyze(_locked_sos_df())
    assert _sos(res)[0].details["limit"] == "ceiling_locked"
    assert res.df["ceiling_locked"].iloc[SOS_IDX]


# ------------------------------------------------------------------ follow-through

def test_same_bar_is_default() -> None:
    assert SOSConfig().confirm_mode == "same_bar"
    sos = _sos(analyze(make_wyckoff_accumulation()))[0]
    assert sos.idx == sos.confirmed_idx == SOS_IDX and "follow_through" not in sos.details


def test_follow_through_confirms_on_close_above_breakout_high() -> None:
    res = analyze(make_wyckoff_accumulation(), FT)
    sos = _sos(res)[0]
    assert sos.idx == SOS_IDX and sos.confirmed_idx == SOS_IDX + 1          # 77,6 > high 77,5
    assert sos.details["follow_through"] == "close vượt high phiên breakout"
    assert [h.status for h in sos.history][:2] == [EventStatus.DETECTED, EventStatus.CONFIRMED]
    seg = res.phases.series["phase"]
    assert seg.iloc[SOS_IDX] != "D" and seg.iloc[SOS_IDX + 1] == "D"


def test_follow_through_confirms_by_holding() -> None:
    df = make_wyckoff_accumulation()
    for k in range(1, 4):   # giữ trên resistance 74 nhưng không vượt high 77,5
        _set(df, SOS_IDX + k, 76.0, 77.0, 75.0, 76.0)
    sos = _sos(analyze(df, FT))[0]
    assert sos.confirmed_idx == SOS_IDX + 3 and sos.details["follow_through"] == "giữ trên resistance 3 phiên"


def test_follow_through_fails_back_inside_range() -> None:
    df = make_wyckoff_accumulation()
    _set(df, SOS_IDX + 1, 77.0, 77.2, 73.0, 73.5)   # close 73,5 < resistance 74
    res = analyze(df, FT)
    assert not [e for e in _sos(res) if e.idx == SOS_IDX]
    c = next(e for e in _sos(res, candidates=True) if e.idx == SOS_IDX)
    assert [h.status for h in c.history] == [EventStatus.DETECTED, EventStatus.INVALIDATED]
    assert c.history[-1].idx == SOS_IDX + 1 and "quay lại dưới resistance" in c.history[-1].reason
    # mặc định: vẫn là SOS như v2
    assert any(e.idx == SOS_IDX for e in _sos(analyze(df)))


def test_open_candidate_when_data_ends() -> None:
    res = analyze(make_wyckoff_accumulation().iloc[:SOS_IDX + 1], FT)
    assert not _sos(res)
    c = _sos(res, candidates=True)[0]
    assert c.status == EventStatus.DETECTED and c.confirmed_idx == -1


def test_locked_mode_only_delays_ceiling_locked_bar() -> None:
    plain = _sos(analyze(make_wyckoff_accumulation(), LOCKED))[0]
    assert plain.confirmed_idx == SOS_IDX                       # không khóa trần -> như v2
    locked = _sos(analyze(_locked_sos_df(), LOCKED))[0]
    assert locked.idx == SOS_IDX and locked.confirmed_idx > SOS_IDX


def test_lps_not_confirmed_before_its_sos() -> None:
    for cfg in (BASE, FT):
        res = analyze(make_wyckoff_accumulation(), cfg)
        sos = {e.date.strftime("%Y-%m-%d"): e for e in _sos(res)}
        for lps in (e for e in res.events if e.kind == EventType.LPS):
            assert lps.confirmed_idx >= sos[lps.details["sos_date"]].confirmed_idx


def test_sos_after_range_exit_kept_as_evidence_in_phase_e() -> None:
    """Range thoát lên trước khi SOS hoàn tất follow-through: SOS vẫn vào cấu trúc, pha giữ E."""
    df = make_wyckoff_accumulation()
    base = analyze(df)
    exit_t = base.ranges[0].end_confirmed_idx
    for k in range(1, 4):   # close > resistance + 0,5 ATR nhưng không vượt high phiên SOS -> xác nhận ở i+3
        _set(df, SOS_IDX + k, 76.0, 77.0, 75.0, 76.0)
    res = analyze(df, FT)
    sos = _sos(res)[0]
    rng = res.ranges[0]
    assert rng.end_confirmed_idx is not None and rng.end_confirmed_idx <= sos.confirmed_idx
    sid = int(res.phases.series["structure_id"].iloc[-1])
    assert sos in res.phases.structures[sid].events
    assert res.phases.series["phase"].iloc[sos.confirmed_idx] == "E"
    assert exit_t is not None


@pytest.mark.parametrize("cfg", [FT, LOCKED])
@pytest.mark.parametrize("cutoff", [SOS_IDX + 1, SOS_IDX + 2, SOS_IDX + 3, SOS_IDX + 5])
def test_follow_through_no_lookahead(cfg: Config, cutoff: int) -> None:
    for df in (make_wyckoff_accumulation(), _locked_sos_df()):
        full, part = analyze(df, cfg), analyze(df.iloc[:cutoff], cfg)
        t = cutoff - 1
        key = lambda evts: [(e.kind, e.idx, e.confirmed_idx) for e in evts]  # noqa: E731
        assert key(part.events) == key([e for e in full.events if e.confirmed_idx <= t])
        want = {e.event_id: e.status_at(t) for e in full.events + full.candidates if e.status_at(t) is not None}
        assert {e.event_id: e.status for e in part.events + part.candidates} == want
        pd.testing.assert_series_equal(part.phases.series["phase"], full.phases.series["phase"].iloc[:cutoff])


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError):
        analyze(make_wyckoff_accumulation(), replace(BASE, sos=replace(BASE.sos, confirm_mode="xyz")))
