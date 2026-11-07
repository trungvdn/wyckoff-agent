"""Lọc cổ phiếu: dòng quét từ view model, lưu kết quả và bộ lọc, chạy quét nền, API. Không gọi mạng."""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from wyckoff.scanner import (DuplicateFilter, ScanJob, ScanProgress, ScanStore, classify_stage, run_scan, scan_row)
from wyckoff.web.app import Settings, create_app
from wyckoff.web.store import load_app_config, scan_runner


# ------------------------------------------------------------------ phân loại giai đoạn

@pytest.mark.parametrize("title, expected", [
    ("Accumulation", ("Accumulation", "confirmed")),
    ("Initial Accumulation", ("Accumulation", "confirmed")),
    ("Accumulation đang hình thành", ("Accumulation", "developing")),
    ("Re-accumulation đang hình thành", ("Re-accumulation", "developing")),
    ("Markup", ("Markup", "confirmed")),
    ("Markup tiềm năng", ("Markup", "potential")),
    ("Markdown đang hình thành", ("Markdown", "developing")),
    ("Re-distribution", ("Re-distribution", "confirmed")),
    ("Re-accumulation hoặc Initial Distribution", ("unclear", None)),
    ("Chưa có xu hướng rõ", ("unclear", None)),
])
def test_classify_stage(title, expected):
    assert classify_stage(title) == expected


# ------------------------------------------------------------------ dòng quét

def _view(closes: list[float], **over) -> dict:
    n = len(closes)
    dates = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    bars = [{"t": d, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1_000_000, "vr": 1.5,
             "ema_fast": c, "ema_slow": c * 0.98} for d, c in zip(dates, closes)]
    view = {
        "symbol": "AAA", "as_of": dates[-1], "bars": bars,
        "stage": {"title": "Accumulation đang hình thành"},
        "stage_segments": [{"kind": "range", "i0": n - 10, "i1": n - 1}],
        "phase": {"phase": "C", "title": "Pha C", "since": dates[-4], "support": 9.0, "resistance": 11.0},
        "confidence": {"level": "thấp"},
        "levels": [{"type": "confirm", "price": 11.0, "label": "SOS"}, {"type": "invalidate", "price": 9.0, "label": "Spring"},
                   {"type": "invalidate", "price": 8.0, "label": "SC"}],
        "events": [{"kind": "Spring", "date": dates[-4], "status": "confirmed"},
                   {"kind": "SOS", "date": dates[-2], "status": "rejected"},
                   {"kind": "SC", "date": dates[0], "status": "confirmed"}],
        "target": {"conservative": 15.0, "reached": False},
    }
    view.update(over)
    return view


def test_scan_row_fields():
    closes = [10.0] * 260 + [10.0, 10.5]
    row = scan_row(_view(closes), {"rs": {"rs_change_20d_pct": 3.2, "rs_change_60d_pct": -1.5}}, (50, 200))
    assert row["symbol"] == "AAA" and row["close"] == 10.5 and row["day_pct"] == 5.0
    assert row["value20"] == pytest.approx((10.0 * 18 + 10 + 10.5) / 20 * 1_000_000 * 1000 / 1e9, abs=0.01)
    assert (row["stage_group"], row["stage_status"], row["stage_age"]) == ("Accumulation", "developing", 9)
    assert (row["phase"], row["phase_age"]) == ("C", 3)
    assert row["confidence_rank"] == 1
    # Mức xác nhận gần nhất ở trên; mức vô hiệu là mức cao nhất (giống quy tắc bán)
    assert row["confirm_pct"] == pytest.approx(4.76, abs=0.01)
    assert row["invalidate_pct"] == pytest.approx(-14.29, abs=0.01) and not row["invalidate_breached"]
    assert row["range_pos"] == 75.0 and row["target_pct"] == pytest.approx(42.86, abs=0.01)
    # Sự kiện bị bác bỏ và sự kiện quá xa đều bị bỏ; mới nhất đứng đầu
    assert [(e["kind"], e["ago"]) for e in row["events"]] == [("Spring", 3)]
    assert row["sma_fast_pct"] == pytest.approx((10.5 / ((49 * 10 + 10.5) / 50) - 1) * 100, abs=0.01) and row["ema_up"] is True
    assert (row["rs20"], row["rs60"]) == (3.2, -1.5)
    assert row["high52_pct"] == pytest.approx(-0.99, abs=0.01)


def test_scan_row_breached_and_missing_levels():
    row = scan_row(_view([10.0] * 30 + [8.5]), None)
    assert row["invalidate_breached"] and row["invalidate_pct"] > 0
    assert row["rs60"] is None and row["sma_slow_pct"] is None
    bare = scan_row(_view([10.0] * 30, levels=[], target=None, confidence={"level": "không áp dụng"}), None)
    assert bare["confirm_pct"] is None and bare["invalidate_pct"] is None and bare["target_pct"] is None
    assert bare["confidence_rank"] == 0


def test_scan_runner_on_demo(tmp_path):
    settings = Settings(no_llm=True, no_market=True, cache_dir=str(tmp_path))
    symbols, analyze, update = scan_runner(settings, load_app_config(settings), update_prices=False, symbols=["DEMO"])(ScanProgress())
    assert symbols == ["DEMO"] and update is None
    row = analyze("DEMO")
    assert row["symbol"] == "DEMO" and row["value20"] > 0 and row["stage_group"] in (
        "Accumulation", "Re-accumulation", "Markup", "Distribution", "Re-distribution", "Markdown", "unclear")


def test_scan_runner_universe_skips_indices(tmp_path):
    for name in ("HPG", "VNINDEX", "VNSMALLCAP", "FPT"):
        (tmp_path / f"{name}_1D.csv").write_text("")
    settings = Settings(no_llm=True, no_market=True, cache_dir=str(tmp_path), offline=True)
    symbols, _, update = scan_runner(settings, load_app_config(settings))(ScanProgress())
    assert symbols == ["FPT", "HPG"] and update is None   # offline: không tải giá


# ------------------------------------------------------------------ lưu trữ

def _row(symbol: str, as_of: str = "2026-11-06") -> dict:
    return {"symbol": symbol, "as_of": as_of, "close": 10.0}


def test_scan_store_keeps_history_and_replaces_same_session(tmp_path):
    s = ScanStore(tmp_path / "s.db")
    assert s.scan() is None and s.sessions() == []
    assert s.save_scan([], [], started="a", finished="b", universe=0) is None
    s.save_scan([_row("AAA", "2026-11-05")], [], started="a", finished="b", universe=1)
    # Phiên của lượt quét là phiên mới nhất trong các dòng; mã dữ liệu cũ vẫn được giữ
    s.save_scan([_row("AAA"), _row("BBB", "2026-11-04")], [{"symbol": "CCC", "reason": "x"}], started="c", finished="d", universe=3)
    s.save_scan([_row("AAA"), _row("DDD")], [], started="e", finished="f", universe=2)
    assert s.sessions() == ["2026-11-06", "2026-11-05"]
    latest = s.scan()
    assert latest["as_of"] == "2026-11-06" and [r["symbol"] for r in latest["rows"]] == ["AAA", "DDD"]
    assert latest["failed"] == [] and latest["universe"] == 2
    assert [r["symbol"] for r in s.scan("2026-11-05")["rows"]] == ["AAA"]


def test_scan_store_filters(tmp_path):
    s = ScanStore(tmp_path / "s.db")
    a = s.add_filter("Tích lũy", {"stages": ["Accumulation"]})
    s.add_filter("Markup", {"stages": ["Markup"]})
    assert [f.name for f in s.filters()] == ["Markup", "Tích lũy"]
    with pytest.raises(DuplicateFilter):
        s.add_filter("Markup", {})
    with pytest.raises(DuplicateFilter):
        s.update_filter(a.id, "Markup", {})
    assert s.update_filter(a.id, "Tích lũy C", {"phases": ["C"]}).filters == {"phases": ["C"]}
    assert s.update_filter(999, "x", {}) is None
    assert s.delete_filter(a.id) and not s.delete_filter(a.id)


# ------------------------------------------------------------------ chạy quét

def test_run_scan_continues_after_errors():
    def analyze(symbol: str) -> dict:
        if symbol == "BAD":
            raise RuntimeError("thiếu dữ liệu")
        return _row(symbol)

    def update(symbol: str) -> None:
        if symbol == "OLD":
            raise RuntimeError("mạng")

    p = ScanProgress()
    rows, failed = run_scan(["AAA", "BAD", "OLD"], analyze, update=update, progress=p)
    assert [r["symbol"] for r in rows] == ["AAA", "OLD"]   # lỗi cập nhật giá: vẫn phân tích trên dữ liệu cũ
    assert [f["symbol"] for f in failed] == ["BAD", "OLD"] and "thiếu dữ liệu" in failed[0]["reason"]
    assert (p.done, p.total, p.current) == (3, 3, None)


def test_run_scan_stops():
    stop = threading.Event()

    def analyze(symbol: str) -> dict:
        stop.set()
        return _row(symbol)

    p = ScanProgress()
    rows, _ = run_scan(["AAA", "BBB"], analyze, progress=p, stop=stop)
    assert len(rows) == 1 and p.stopped


def test_scan_job_saves_and_refuses_second_run(tmp_path):
    gate = threading.Event()

    def make(progress):
        def analyze(symbol):
            gate.wait(5)
            return _row(symbol)
        return ["AAA", "BBB"], analyze, None

    job = ScanJob(ScanStore(tmp_path / "s.db"), make)
    assert job.start() and not job.start()
    gate.set()
    job.wait(5)
    assert not job.progress.running and job.progress.as_of == "2026-11-06" and job.progress.error is None
    assert len(job.store.scan()["rows"]) == 2


def test_scan_job_stopped_keeps_previous_scan(tmp_path):
    store = ScanStore(tmp_path / "s.db")
    store.save_scan([_row("OLD")], [], started="a", finished="b", universe=1)
    gate = threading.Event()

    def make(progress):
        def analyze(symbol):
            gate.wait(5)
            return _row(symbol)
        return ["AAA", "BBB", "CCC"], analyze, None

    job = ScanJob(store, make)
    job.start()
    assert job.stop()
    gate.set()
    job.wait(5)
    assert job.progress.stopped and job.progress.as_of is None
    assert [r["symbol"] for r in store.scan()["rows"]] == ["OLD"]
    assert not job.stop()


def test_scan_job_reports_runner_error(tmp_path):
    def make(progress):
        raise RuntimeError("không đọc được cache")

    job = ScanJob(ScanStore(tmp_path / "s.db"), make)
    job.start()
    job.wait(5)
    assert job.progress.error == "không đọc được cache" and not job.progress.running


# ------------------------------------------------------------------ API

@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(no_llm=True, no_market=True, out_dir=str(tmp_path), portfolio_db=str(tmp_path / "p.db"),
                        scanner_db=str(tmp_path / "s.db"), cache_dir=str(tmp_path))
    app = create_app(settings)
    app.state.scan_job._make_runner = lambda progress: (["DEMO"], lambda s: {**_row(s), "close": 1.0}, None)
    return TestClient(app)


def test_scan_api_flow(client: TestClient):
    empty = client.get("/api/scan").json()
    assert empty["as_of"] is None and empty["rows"] == [] and not empty["job"]["running"]
    assert client.post("/api/scan", json={}).status_code == 422          # cần {"confirm": true}
    assert client.post("/api/scan", json={"confirm": True}).status_code == 202
    client.app.state.scan_job.wait(5)
    assert client.get("/api/scan/status").json()["as_of"] == "2026-11-06"
    client.post("/api/portfolio", json={"symbol": "DEMO", "quantity": 100, "cost": 10, "bought_on": "2023-05-02"})
    data = client.get("/api/scan").json()
    assert data["sessions"] == ["2026-11-06"] and data["held"] == ["DEMO"]
    assert data["rows"][0]["symbol"] == "DEMO" and data["rows"][0]["held"] is True
    assert client.get("/api/scan", params={"as_of": "2026-11-05"}).status_code == 404
    assert client.post("/api/scan/stop").status_code == 409


def test_filters_api_flow(client: TestClient):
    assert client.get("/api/filters").json() == []
    r = client.post("/api/filters", json={"name": "  Tích lũy   C ", "filters": {"phases": ["C"]}})
    assert r.status_code == 201 and r.json()["name"] == "Tích lũy C"
    fid = r.json()["id"]
    assert client.post("/api/filters", json={"name": "Tích lũy C", "filters": {}}).status_code == 409
    assert client.post("/api/filters", json={"name": "   ", "filters": {}}).status_code == 422
    assert client.post("/api/filters", json={"name": "Lớn", "filters": {"x": "a" * 5000}}).status_code == 422
    assert client.put(f"/api/filters/{fid}", json={"name": "Pha D", "filters": {"phases": ["D"]}}).json()["filters"] == {"phases": ["D"]}
    assert client.put("/api/filters/999", json={"name": "x", "filters": {}}).status_code == 404
    assert client.delete(f"/api/filters/{fid}").status_code == 204
    assert client.delete(f"/api/filters/{fid}").status_code == 404
