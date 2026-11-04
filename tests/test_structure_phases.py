"""PS, AR, ST, LPS, UTAD và state machine pha."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from wyckoff.config import ARConfig, Config, PhaseConfig, STConfig
from wyckoff.detectors.models import EventType
from wyckoff.indicators.core import add_indicators
from wyckoff.pipeline import analyze
from wyckoff.synthetic import RESISTANCE, SC_IDX, SOS_IDX, SPRING_CONFIRM_IDX, SPRING_IDX


def _set_bar(df: pd.DataFrame, i: int, **vals: float) -> None:
    for k, v in vals.items():
        df.iloc[i, df.columns.get_loc(k)] = v


def _kinds(res, kind: EventType):
    return [e for e in res.events if e.kind == kind]


def _segments(res):
    return [(g.phase, g.start_idx) for g in res.phases.segments]


# -------------------------------------------------------------- sự kiện

def test_ar_and_st_on_synthetic(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv)
    (ar,) = _kinds(res, EventType.AR)
    assert ar.idx == SC_IDX + 6 and ar.confirmed_idx == ar.idx + 3 and ar.details["rally_atr"] >= 3
    sts = _kinds(res, EventType.ST)
    assert [s.idx for s in sts] == [113, 133, 153]
    assert all(s.details["volume_vs_sc"] < 0.7 for s in sts)
    assert all(b.idx - a.idx >= 10 for a, b in zip(sts, sts[1:]))


def test_ar_needs_enough_rally(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv, replace(Config(), ar=ARConfig(min_rally_atr=8.0)))
    assert _kinds(res, EventType.AR) == [] and _kinds(res, EventType.ST) == []


def test_st_rejected_on_high_volume(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv, replace(Config(), st=STConfig(max_vol_vs_sc=0.3)))
    assert _kinds(res, EventType.ST) == []


def test_ps_found_before_sc(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    i = SC_IDX - 8
    c = df["close"].iloc[i]
    _set_bar(df, i, open=c - 1.0, low=c - 1.6, high=c + 0.6, close=c + 0.4, volume=1_800_000)
    (ps,) = _kinds(analyze(df), EventType.PS)
    assert ps.idx == i and ps.confirmed_idx == SC_IDX and ps.details["bars_before_sc"] == 8


def _with_lps(ohlcv: pd.DataFrame, vol: float = 600_000) -> pd.DataFrame:
    df = ohlcv.copy()
    k = SOS_IDX + 2                                     # điều chỉnh về sát resistance cũ, volume thấp
    _set_bar(df, k, open=77.8, high=77.9, low=76.0, close=77.1, volume=vol)
    _set_bar(df, k + 1, open=77.2, high=78.6, low=77.1, close=78.5)
    return df


def test_lps_after_sos(ohlcv: pd.DataFrame) -> None:
    (lps,) = _kinds(analyze(_with_lps(ohlcv)), EventType.LPS)
    assert lps.idx == SOS_IDX + 2 and lps.confirmed_idx == SOS_IDX + 3
    assert lps.details["low_vs_resistance_atr"] > -1.0 and lps.details["pullback_atr"] >= 0.5


def test_lps_rejected_on_high_volume(ohlcv: pd.DataFrame) -> None:
    assert _kinds(analyze(_with_lps(ohlcv, vol=1_500_000)), EventType.LPS) == []


def _with_utad(ohlcv: pd.DataFrame) -> pd.DataFrame:
    df = ohlcv.copy()
    i = 166                                             # đỉnh sóng trong range, sau xác nhận 131 + 20
    _set_bar(df, i, high=RESISTANCE + 1.2, close=72.4, open=73.4)
    return df


def test_utad_detected(ohlcv: pd.DataFrame) -> None:
    (ut,) = _kinds(analyze(_with_utad(ohlcv)), EventType.UTAD)
    assert ut.idx == 166 and ut.confirmed_idx == 166 and ut.details["penetration_atr"] > 0.1


def test_no_utad_on_clean_synthetic(ohlcv: pd.DataFrame) -> None:
    assert _kinds(analyze(ohlcv), EventType.UTAD) == []


# ---------------------------------------------------------------- pha

def test_phase_sequence_synthetic(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv)
    assert _segments(res) == [("A", SC_IDX), ("B", 113), ("C", SPRING_CONFIRM_IDX), ("D", SOS_IDX), ("E", SOS_IDX + 2)]
    # pha A kết thúc trước khi range xác nhận (131); pha B được gắn TR#0 khi range xác nhận
    assert res.phases.segments[0].range_id is None and res.phases.segments[1].range_id == 0


def test_phase_without_sc_starts_in_b(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SC_IDX, volume=1_000_000)                  # không còn SC
    res = analyze(df)
    assert res.phases.segments[0].phase == "B" and "không có SC" in res.phases.segments[0].reason


def test_utad_invalidates(ohlcv: pd.DataFrame) -> None:
    res = analyze(_with_utad(ohlcv))
    assert ("invalid", 166) in _segments(res)


def test_phase_c_invalidated_below_spring_low(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SPRING_CONFIRM_IDX + 2, low=60.0, close=60.5, open=65.0, high=65.2)   # dưới 62.5 - 0.5 ATR
    assert ("invalid", SPRING_CONFIRM_IDX + 2) in _segments(analyze(df))


def test_sc_not_attached_when_far_from_range(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv, replace(Config(), phase=PhaseConfig(attach_max_atr=0.0, attach_max_bars=-1)))
    segs = _segments(res)
    assert segs[0] == ("A", SC_IDX) and ("B", 131) in segs   # range xác nhận ở 131 mở cấu trúc mới


# --------------------------------------------------------- current_phase

def test_current_phase_c_levels(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv.iloc[:SPRING_CONFIRM_IDX + 5])
    cur = res.current()
    assert cur.phase == "C" and cur.range_id == 0 and cur.support == 64.0 and cur.resistance == RESISTANCE
    assert [lv.label for lv in cur.confirm] == ["SOS -> pha D"]
    assert cur.confirm[0].price == pytest.approx(RESISTANCE + 0.2 * cur.atr)
    (inv,) = cur.invalidate
    assert inv.price == pytest.approx(62.5 - 0.5 * cur.atr)
    assert any("Spring" in ev for ev in cur.evidence)


def test_current_phase_b_levels(ohlcv: pd.DataFrame) -> None:
    cur = analyze(ohlcv.iloc[:150]).current()
    assert cur.phase == "B"
    assert [lv.label for lv in cur.confirm] == ["Spring -> pha C", "SOS -> pha D"]
    assert cur.invalidate[0].price == pytest.approx(64.0 - 0.5 * cur.atr)


def test_current_phase_a_levels(ohlcv: pd.DataFrame) -> None:
    cur = analyze(ohlcv.iloc[:SC_IDX + 5]).current()
    assert cur.phase == "A" and cur.invalidate[0].label.startswith("Thủng đáy SC")
    assert "không phải vô hiệu" in cur.invalidate[0].label


def _sc_failed_df(ohlcv: pd.DataFrame) -> pd.DataFrame:
    df = ohlcv.copy()
    i = df.index[SC_IDX + 2]
    df.loc[i, ["open", "high", "low", "close"]] = [70.0, 70.2, 62.0, 62.6]
    return df


def test_sc_failed_keeps_phase_a_by_default(ohlcv: pd.DataFrame) -> None:
    res = analyze(_sc_failed_df(ohlcv).iloc[:SC_IDX + 6])
    cur = res.current()
    assert cur.phase == "A" and "vùng climax kéo dài" in cur.reason
    assert any(e.kind == EventType.SC_FAILED for e in res.phases.structures[0].events)


def test_sc_failed_invalidates_when_configured(ohlcv: pd.DataFrame) -> None:
    from dataclasses import replace
    from wyckoff.config import Config
    cfg = Config()
    cfg = replace(cfg, phase=replace(cfg.phase, sc_failed_invalidates=True))
    cur = analyze(_sc_failed_df(ohlcv).iloc[:SC_IDX + 6], cfg).current()
    assert cur.phase == "invalid" and cur.reason.startswith("SC failed")


@pytest.mark.parametrize("mode,label", [("lps_or_res_atr", "Quay sâu vào range"), ("range_mid", "Quay về giữa range"),
                                        ("support", "Quay về support")])
def test_d_invalid_modes(ohlcv: pd.DataFrame, mode: str, label: str) -> None:
    from dataclasses import replace
    from wyckoff.config import Config
    cfg = Config()
    cfg = replace(cfg, phase=replace(cfg.phase, d_invalid_mode=mode))
    cur = analyze(ohlcv.iloc[:SOS_IDX + 2], cfg).current()
    assert cur.phase == "D"
    lv = cur.invalidate[0]
    assert lv.label.startswith(label)
    expected = {"range_mid": (cur.support + cur.resistance) / 2, "support": cur.support}.get(mode, cur.resistance - cur.atr)
    assert lv.price == pytest.approx(expected)


def test_d_invalid_mode_rejects_unknown(ohlcv: pd.DataFrame) -> None:
    from dataclasses import replace
    from wyckoff.config import Config
    cfg = Config()
    cfg = replace(cfg, phase=replace(cfg.phase, d_invalid_mode="xyz"))
    with pytest.raises(ValueError):
        analyze(ohlcv.iloc[:SOS_IDX + 2], cfg).current()


def test_deep_spring_warning(ohlcv: pd.DataFrame) -> None:
    from dataclasses import replace
    from wyckoff.config import Config
    cut = ohlcv.iloc[:SPRING_CONFIRM_IDX + 1]
    cur = analyze(cut).current()
    assert cur.phase == "C"
    pen = analyze(cut).phases.structures[cur_sid(cut)].spring.details["penetration_atr"]
    cfg = Config()
    shallow = replace(cfg, phase=replace(cfg.phase, deep_spring_atr=pen + 0.01))
    deep = replace(cfg, phase=replace(cfg.phase, deep_spring_atr=pen))
    assert not any("xuyên sâu" in w for w in analyze(cut, shallow).current().warnings)
    w = [w for w in analyze(cut, deep).current().warnings if "xuyên sâu" in w]
    assert len(w) == 1 and "thất bại" not in w[0] and "quay lại" not in w[0]


def cur_sid(df: pd.DataFrame) -> int:
    r = analyze(df)
    return int(r.phases.series["structure_id"].iloc[-1])


def test_current_phase_none_before_structure(ohlcv: pd.DataFrame) -> None:
    assert analyze(ohlcv.iloc[:90]).current().phase is None


def test_current_phase_to_dict(ohlcv: pd.DataFrame) -> None:
    d = analyze(ohlcv).current().to_dict()
    assert d["phase"] == "E" and isinstance(d["invalidate"][0], dict)
