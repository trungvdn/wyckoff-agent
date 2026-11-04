"""SOS reclaim: range thoát xuống rồi lấy lại resistance với volume cao -> cấu trúc về pha D, không còn vô hiệu."""
from __future__ import annotations

import pandas as pd
import pytest

from wyckoff.agent.payload import confidence
from wyckoff.config import PhaseConfig, RangeConfig
from wyckoff.detectors.events import detect_sos_reclaim
from wyckoff.detectors.models import EventType, TradingRange
from wyckoff.indicators.core import add_indicators
from wyckoff.phases import classify_phases, current_phase
from wyckoff.pipeline import analyze

CONFIRM, EXIT_START, EXIT_CONFIRM, RECLAIM = 25, 40, 42, 50


def _frame(after: list[float], reclaim_bar: int = RECLAIM) -> pd.DataFrame:
    """Đi ngang quanh 100 (S=98, R=102), 3 phiên đóng cửa dưới biên, rồi nến tăng volume lớn tại `reclaim_bar`;
    `after`: các close sau nến đó."""
    rows = []
    n = reclaim_bar + 1 + len(after)
    for i in range(n):
        c, vol = 100.0 + (0.5 if i % 2 else -0.5), 1_000.0
        if EXIT_START <= i <= EXIT_CONFIRM or EXIT_CONFIRM < i < reclaim_bar:
            c = 96.0
        if i == reclaim_bar:
            rows.append((100.0, 104.0, 100.0, 103.8, 3_000.0))
            continue
        if i > reclaim_bar:
            c = after[i - reclaim_bar - 1]
        rows.append((c - 0.2, c + 1.0, c - 1.0, c, vol))
    idx = pd.bdate_range("2024-01-01", periods=n)
    return add_indicators(pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx))


def _range(df: pd.DataFrame) -> TradingRange:
    d = df.index
    return TradingRange(
        range_id=7, start_idx=5, start_date=d[5], end_idx=EXIT_START - 1, end_date=d[EXIT_START - 1],
        confirmed_idx=CONFIRM, confirmed_date=d[CONFIRM], support=98.0, resistance=102.0, atr_at_confirm=2.0,
        end_confirmed_idx=EXIT_CONFIRM, end_confirmed_date=d[EXIT_CONFIRM], exit_direction="down", context="trung tính",
    )


def test_detects_first_bar_meeting_sos_rule_after_down_exit():
    df = _frame([104.0] * 5)
    events = detect_sos_reclaim(df, [_range(df)])
    assert [e.idx for e in events] == [RECLAIM]
    e = events[0]
    assert e.kind == EventType.SOS and e.details["reclaim"] is True and e.details["bars_after_exit"] == RECLAIM - EXIT_CONFIRM


def test_causal_event_absent_before_its_bar():
    df = _frame([104.0] * 5)
    rng = _range(df)
    assert detect_sos_reclaim(df.iloc[:RECLAIM], [rng]) == []
    assert [e.idx for e in detect_sos_reclaim(df.iloc[:RECLAIM + 1], [rng])] == [RECLAIM]


def test_window_expired_or_disabled_or_new_range_blocks_reclaim():
    df = _frame([104.0] * 3)
    rng = _range(df)
    assert detect_sos_reclaim(df, [rng], window=RECLAIM - EXIT_CONFIRM - 1) == []
    assert detect_sos_reclaim(df, [rng], window=0) == []
    newer = TradingRange(
        range_id=8, start_idx=43, start_date=df.index[43], end_idx=len(df) - 1, end_date=df.index[-1], confirmed_idx=RECLAIM - 1,
        confirmed_date=df.index[RECLAIM - 1], support=95.0, resistance=97.0, atr_at_confirm=2.0,
    )
    assert detect_sos_reclaim(df, [rng, newer]) == []


def test_up_exit_is_not_reclaim():
    df = _frame([104.0] * 3)
    from dataclasses import replace

    assert detect_sos_reclaim(df, [replace(_range(df), exit_direction="up")]) == []


def _phases(df: pd.DataFrame):
    rng = _range(df)
    return classify_phases(df, [rng], detect_sos_reclaim(df, [rng]), PhaseConfig(), RangeConfig())


def test_phase_goes_invalid_then_d_then_e():
    df = _frame([104.0] * 5)
    ph = _phases(df).series["phase"]
    assert ph.iloc[EXIT_CONFIRM - 1] == "B" and ph.iloc[EXIT_CONFIRM] == "invalid" and ph.iloc[RECLAIM - 1] == "invalid"
    assert ph.iloc[RECLAIM] == "D" and ph.iloc[RECLAIM + 2] == "D" and ph.iloc[RECLAIM + 3] == "E"


def test_reclaim_can_fail_back_to_invalid():
    df = _frame([100.0, 96.0, 96.0, 96.0])
    ph = _phases(df).series["phase"]
    assert ph.iloc[RECLAIM + 1] == "D" and ph.iloc[RECLAIM + 3] == "D" and ph.iloc[RECLAIM + 4] == "invalid"


def test_current_phase_offers_levels_and_confidence_gives_no_bonus():
    df = _frame([101.0])
    res = _phases(df)
    cur = current_phase(df, res)
    assert cur.phase == "D" and "SOS reclaim" in cur.reason
    assert cur.confirm and cur.invalidate and cur.invalidate[0].price == pytest.approx(100.0)
    events = res.structures[int(res.series["structure_id"].iloc[-1])].events
    conf = confidence(cur, events, "trung tính")
    assert {f["key"]: f["points"] for f in conf["factors"]}["sos_reclaim"] == 0
    assert "sos" not in {f["key"] for f in conf["factors"]}


def test_pipeline_reclaim_window_zero_matches_no_reclaim(ohlcv: pd.DataFrame):
    from dataclasses import replace

    from wyckoff.config import Config

    cfg = Config()
    off = analyze(ohlcv, replace(cfg, phase=replace(cfg.phase, reclaim_window=0)))
    assert not any(e.details.get("reclaim") for e in off.events)
