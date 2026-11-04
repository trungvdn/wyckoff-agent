"""Web dashboard: mục tiêu P&F, hỏi–đáp có kiểm tra số liệu, API trên dữ liệu DEMO. Không gọi mạng."""
from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from wyckoff.agent.ask import answer_question, validate_answer
from wyckoff.agent.llm import FakeClient
from wyckoff.agent.payload import build_payload
from wyckoff.config import PnfConfig
from wyckoff.pipeline import analyze
from wyckoff.pnf import box_size, cause_effect_target, pnf_columns
from wyckoff.service import resample_weekly
from wyckoff.web.app import Settings, create_app
from wyckoff.web.viewmodel import current_structure


# ------------------------------------------------------------------ P&F

def test_pnf_columns_reversal():
    # lên 3 ô, giảm 3 ô (đảo chiều), lên lại 3 ô
    cols = pnf_columns([10, 11, 12, 13, 12, 11, 10, 11, 12, 13], box=1, reversal=3)
    assert [c.direction for c in cols] == [1, -1, 1]
    assert (cols[0].low_box, cols[0].high_box) == (10, 13)


def test_pnf_small_pullback_does_not_reverse():
    cols = pnf_columns([10, 12, 14, 13, 12, 15], box=1, reversal=3)
    assert len(cols) == 1 and cols[0].high_box == 15


def test_pnf_rejects_bad_box():
    with pytest.raises(ValueError):
        pnf_columns([1, 2], box=0)


def test_box_size_rounds_up_to_tick():
    assert box_size(atr=2.1, ref_price=64, cfg=PnfConfig(box_atr=0.5)) == pytest.approx(1.1)   # tick 0,1 ở giá >= 50
    assert box_size(atr=0.001, ref_price=20, cfg=PnfConfig()) == pytest.approx(0.05)          # tối thiểu 1 tick


def test_cause_effect_target_on_demo(ohlcv: pd.DataFrame):
    res = analyze(ohlcv)
    s = current_structure(res)
    t = cause_effect_target(res.df, s)
    assert t is not None and t["columns"] > 0
    assert t["count_to_event"] == "SOS" and not t["provisional"]
    assert t["conservative"] == pytest.approx(t["base_low"] + t["columns"] * t["box"] * t["reversal"], abs=0.01)
    assert t["aggressive"] >= t["conservative"]


def test_resample_weekly(ohlcv: pd.DataFrame):
    w = resample_weekly(ohlcv)
    assert w["volume"].sum() == ohlcv["volume"].sum()
    first = ohlcv.loc[: w.index[0]]
    assert w["high"].iloc[0] == first["high"].max() and w["close"].iloc[0] == first["close"].iloc[-1]


# ------------------------------------------------------------------ hỏi–đáp

@pytest.fixture
def payload(ohlcv: pd.DataFrame) -> dict:
    return build_payload(analyze(ohlcv), "DEMO")


def test_ask_accepts_grounded_answer(payload: dict):
    sos = next(e for e in payload["evidence_events"] if e["kind"] == "SOS")
    good = json.dumps({"answer": "SOS có volume 2,05x TB20 và biên độ 2,05 ATR.", "event_ids": [sos["id"]]})
    client = FakeClient([good])
    res = answer_question(payload, "SOS có mạnh không?", client)
    assert res.source == "llm" and res.attempts == 1 and res.event_ids == [sos["id"]]
    assert "<question>" in client.calls[0]["user"]


def test_ask_retries_then_falls_back_on_invented_numbers(payload: dict):
    bad = json.dumps({"answer": "Giá sẽ lên 123,45 trong 7 phiên.", "event_ids": []})
    client = FakeClient([bad, bad])
    res = answer_question(payload, "Mục tiêu?", client)
    assert res.source == "template" and res.attempts == 2
    assert any("123,45" in e for e in res.errors)
    assert "Lần trả lời trước KHÔNG đạt" in client.calls[1]["user"]


def test_ask_allows_numbers_from_question(payload: dict):
    ans = {"answer": "Hệ thống không có dữ liệu về mức 99,9 bạn hỏi.", "event_ids": []}
    assert validate_answer(ans, payload, "Giá 99,9 thì sao?") == []
    assert validate_answer(ans, payload, "Giá thì sao?")


def test_ask_rejects_unknown_event_and_field_names(payload: dict):
    errs = validate_answer({"answer": "vol_ratio cao", "event_ids": ["ev_99"]}, payload, "?")
    assert any("event_id" in e for e in errs) and any("tên trường" in e for e in errs)


# ------------------------------------------------------------------ API

@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(no_llm=True, no_market=True, cache_dir="cache", out_dir="output")))


def test_api_only_with_strict_csp(client: TestClient):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/api/docs"
    r = client.get("/api/health")
    assert r.status_code == 200 and r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert client.get("/static/app.js").status_code == 404


def test_analysis_demo(client: TestClient):
    v = client.get("/api/analysis/demo").json()
    assert v["symbol"] == "DEMO" and v["phase"]["title"] == "Pha E"
    assert v["stage"]["view"] == "trend" and v["stage"]["title"] == "Markup" and v["stage"]["structure_type"] == "Trending Up"
    assert v["stage"]["candidates"] == [] and v["stage"]["strength"]["side"] == "demand"
    assert v["stage"]["last_resolved"]["label"] == "Initial Accumulation"
    assert v["target"]["direction"] == "up" and v["target_down"] is None and v["stage"]["note"] is None
    segs = v["stage_segments"]
    assert segs[0]["i0"] == 0 and segs[-1]["i1"] == len(v["bars"]) - 1 and all(a["i1"] + 1 == b["i0"] for a, b in zip(segs, segs[1:]))
    assert [s["kind"] for s in segs][-3:] == ["none", "range", "up"] and segs[-2]["label"] == "Acc" and segs[-1]["label"] == "Markup"
    assert [s["status"] for s in v["phase"]["steps"]] == ["done"] * 4 + ["current"]
    assert {"SC", "AR", "ST", "Spring", "SOS"} <= {e["kind"] for e in v["events"]}
    assert v["bars"] and all(0 <= e["i"] < len(v["bars"]) for e in v["chart_events"])
    assert all(v["bars"][e["i"]]["t"] == e["t"] for e in v["chart_events"])
    assert any(r["current"] for r in v["ranges"]) and v["target"] is not None
    assert v["confidence"]["level"] in {"thấp", "trung bình", "cao"}


def test_analysis_returns_full_history_with_default_view(client: TestClient, ohlcv: pd.DataFrame):
    v = client.get("/api/analysis/DEMO").json()
    assert len(v["bars"]) == len(ohlcv)
    sc = next(e for e in v["chart_events"] if e["kind"] == "SC")
    assert 0 <= v["view_from"] <= sc["i"]          # khung nhìn mặc định thấy trọn cấu trúc hiện tại
    assert len(v["bars"]) - v["view_from"] <= 400


def test_phase_segments_match_engine(client: TestClient, ohlcv: pd.DataFrame):
    v = client.get("/api/analysis/DEMO").json()
    series = analyze(ohlcv).phases.series["phase"]
    segs = v["phase_segments"]
    assert segs and segs[-1]["phase"] == v["phase"]["phase"] and segs[-1]["i1"] == len(v["bars"]) - 1
    for g in segs:
        assert 0 <= g["i0"] <= g["i1"] < len(v["bars"])
        assert (series.iloc[g["i0"]: g["i1"] + 1] == g["phase"]).all()
    assert all(a["i1"] < b["i0"] for a, b in zip(segs, segs[1:]))   # không chồng lấn, theo thứ tự thời gian


def test_analysis_rejects_bad_input(client: TestClient):
    assert client.get("/api/analysis/x!").status_code == 422
    r = client.get("/api/analysis/DEMO?tf=15m")
    assert r.status_code == 422 and "chưa được hỗ trợ" in r.json()["detail"]
    r = client.get("/api/analysis/DEMO?tf=1W")       # DEMO chỉ có 43 nến tuần
    assert r.status_code == 422 and "nến" in r.json()["detail"]


def test_explanation_and_ask_without_llm(client: TestClient):
    ex = client.get("/api/explanation/DEMO").json()
    assert ex["source"] == "template" and "pha E" in ex["summary"]
    r = client.post("/api/ask", json={"symbol": "DEMO", "question": "Spring có đáng tin không?"}).json()
    assert r["source"] == "template" and r["answer"]
    assert client.post("/api/ask", json={"symbol": "DEMO", "question": ""}).status_code == 422
    assert client.post("/api/ask", json={"symbol": "DEMO", "question": "x" * 501}).status_code == 422


def test_ask_uses_llm_client(ohlcv: pd.DataFrame):
    answer = json.dumps({"answer": "DEMO đang ở pha E.", "event_ids": []})
    fake = FakeClient([answer], model="fake-model")
    app = create_app(Settings(no_market=True), client_factory=lambda: (fake, ""))
    r = TestClient(app).post("/api/ask", json={"symbol": "DEMO", "question": "Pha nào?"}).json()
    assert r == {"answer": "DEMO đang ở pha E.", "event_ids": [], "source": "llm", "model": "fake-model", "errors": []}


def test_data_error_message_is_short(monkeypatch):
    import wyckoff.service as service
    from wyckoff.config import Config

    def boom(*a, **k):
        raise RuntimeError("Quote.history[VCI]: InputError: Nguồn 'vci' không có mã 'ZZZZ'. | Market.ohlcv[KBS]: ...")

    monkeypatch.setattr(service, "get_ohlcv", boom)
    with pytest.raises(service.DataUnavailable) as e:
        service.load_ohlcv("ZZZZ", "1D", Config())
    assert e.value.status == 404 and "Quote.history" not in str(e.value)
