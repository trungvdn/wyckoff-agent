"""Danh mục: lưu trữ SQLite, mức giá gần nhất, thay đổi so với phiên trước, API trên dữ liệu DEMO. Không gọi mạng."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from wyckoff.portfolio import (DuplicateHolding, Holding, PortfolioStore, error_row, holding_row, nearest_levels,
                               portfolio_view, session_changes)
from wyckoff.web.app import Settings, create_app


def _view(levels=(), support=None, resistance=None, stage="Markup", phase="Pha E", closes=(20.0, 21.0)):
    return {
        "as_of": "2026-11-06", "bars": [{"c": c} for c in closes], "levels": list(levels),
        "stage": {"title": stage}, "phase": {"title": phase, "support": support, "resistance": resistance},
    }


def _lv(kind, price, label="x"):
    return {"type": kind, "price": price, "label": label}


# ------------------------------------------------------------------ lưu trữ

def test_store_roundtrip(tmp_path):
    s = PortfolioStore(tmp_path / "sub" / "p.db")   # tự tạo thư mục
    assert s.list() == []
    s.add(Holding("HPG", 2000, 22.4, "2026-08-12"))
    s.add(Holding("FPT", 300, 78.0, "2026-02-10"))
    assert [h.symbol for h in s.list()] == ["FPT", "HPG"]
    with pytest.raises(DuplicateHolding):
        s.add(Holding("HPG", 1, 1.0, "2026-01-01"))
    assert s.update(Holding("HPG", 100, 20.0, "2026-01-02")) and not s.update(Holding("ZZZ", 1, 1.0, "2026-01-01"))
    assert PortfolioStore(tmp_path / "sub" / "p.db").list()[1] == Holding("HPG", 100, 20.0, "2026-01-02")   # còn sau khi mở lại
    assert s.delete("FPT") and not s.delete("FPT")


# ------------------------------------------------------------------ mức giá

def test_nearest_levels_prefers_named_levels():
    # VCB 06/11: hỗ trợ 54 và kháng cự 60,8 đều gần hơn, nhưng mức vô hiệu và xác nhận được ưu tiên
    v = _view([_lv("confirm", 61.02), _lv("invalidate", 52.55)], support=54.0, resistance=60.8)
    n = nearest_levels(v, 53.6)
    assert (n["below"]["kind"], n["below"]["price"], n["below"]["pct"], n["below"]["breached"]) == ("invalidate", 52.55, -1.96, False)
    assert (n["above"]["kind"], n["above"]["price"], n["above"]["pct"]) == ("confirm", 61.02, 13.84)


def test_nearest_levels_marks_breached_invalidation():
    n = nearest_levels(_view([_lv("invalidate", 74.9)], support=68.88, resistance=74.9), 73.7)
    assert n["above"]["kind"] == "invalidate" and n["above"]["breached"] and n["above"]["pct"] == 1.63
    assert n["below"]["kind"] == "support"


def test_nearest_levels_price_outside_range():
    n = nearest_levels(_view(support=62.77, resistance=69.68), 50.8)
    assert n["below"] is None and (n["above"]["kind"], n["above"]["price"]) == ("support", 62.77)
    assert nearest_levels(_view(), 50.0) == {"below": None, "above": None}


def test_sc_extension_is_not_an_invalidation():
    v = _view([_lv("invalidate", 10.0, "Thủng đáy SC: vùng climax kéo dài (không phải vô hiệu)")], support=11.0)
    assert nearest_levels(v, 12.0)["below"]["kind"] == "support"


# ------------------------------------------------------------------ thay đổi so với phiên trước

def test_changes_level_crossing_keeps_most_specific_name():
    v = _view([_lv("invalidate", 74.9)], support=68.88, resistance=74.9)
    c = session_changes(v, v, 73.7, 75.0)
    assert c == [{"kind": "level", "level": "invalidate", "price": 74.9, "direction": "below", "close": 73.7, "prev_close": 75.0}]


def test_changes_upward_crossing_and_no_crossing():
    v = _view([_lv("confirm", 61.0)], support=54.0)
    assert session_changes(v, v, 62.0, 60.0)[0]["direction"] == "above"
    assert session_changes(v, v, 58.0, 57.0) == []


def test_changes_stage_and_phase():
    c = session_changes(_view(stage="B", phase="Pha D"), _view(stage="A", phase="Pha C"), 21, 20)
    assert [(x["kind"], x["from"], x["to"]) for x in c] == [("stage", "A", "B"), ("phase", "Pha C", "Pha D")]


# ------------------------------------------------------------------ tính tiền

def test_holding_row_money():
    r = holding_row(Holding("HPG", 2000, 22.4, "2026-08-12"), _view(closes=(21.5, 21.2)), None)
    assert r["value"] == 42_400_000 and r["cost_value"] == 44_800_000 and r["pl"] == -2_400_000
    assert r["pl_pct"] == -5.36 and r["day_value"] == -600_000 and r["day_pct"] == -1.4
    assert r["changes"] is None   # không có phiên trước để so


def test_portfolio_view_totals_order_and_errors():
    v = _view([_lv("invalidate", 74.9)], closes=(75.0, 73.7))
    rows = [
        holding_row(Holding("HPG", 2000, 22.4, "2026-08-12"), _view(closes=(21.5, 21.2)), _view()),
        holding_row(Holding("MWG", 600, 62.5, "2026-03-20"), v, v),
        error_row(Holding("ZZZ", 100, 10.0, "2026-01-01"), "Không có dữ liệu"),
    ]
    p = portfolio_view(rows)
    # Mã lỗi không tính vào tổng; mức trong cùng danh mục minh họa
    s = p["summary"]
    assert s["count"] == 3 and s["value"] == 42_400_000 + 44_220_000 and s["cost"] == 44_800_000 + 37_500_000
    assert s["pl"] == 4_320_000 and s["pl_pct"] == 5.25 and s["day"] == -600_000 - 780_000
    assert [r["symbol"] for r in p["rows"]] == ["MWG", "HPG", "ZZZ"]   # có thay đổi trước, rồi theo giá trị, mã lỗi cuối
    assert p["warnings"] == ["ZZZ: Không có dữ liệu"]


def test_portfolio_view_empty():
    p = portfolio_view([])
    assert p["rows"] == [] and p["summary"]["pl_pct"] is None and p["as_of"] is None


# ------------------------------------------------------------------ API

@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(no_llm=True, no_market=True, out_dir=str(tmp_path), portfolio_db=str(tmp_path / "p.db"))))


BODY = {"symbol": "demo", "quantity": 1000, "cost": 70.5, "bought_on": "2023-05-02"}


def test_portfolio_api_flow(client: TestClient):
    assert client.get("/api/portfolio").json()["rows"] == []
    r = client.post("/api/portfolio", json=BODY)
    assert r.status_code == 201 and r.json()["symbol"] == "DEMO"
    assert client.post("/api/portfolio", json=BODY).status_code == 409

    p = client.get("/api/portfolio").json()
    row = p["rows"][0]
    assert row["symbol"] == "DEMO" and row["error"] is None and row["stage"] and row["phase"]
    assert row["value"] == round(1000 * row["price"] * 1000) and p["summary"]["value"] == row["value"]
    assert isinstance(row["changes"], list)

    r = client.put("/api/portfolio/DEMO", json={"quantity": 500, "cost": 70.5, "bought_on": "2023-05-02"})
    assert r.status_code == 200 and client.get("/api/portfolio").json()["rows"][0]["quantity"] == 500
    assert client.delete("/api/portfolio/DEMO").status_code == 204
    assert client.delete("/api/portfolio/DEMO").status_code == 404
    assert client.put("/api/portfolio/DEMO", json={"quantity": 1, "cost": 1, "bought_on": "2023-05-02"}).status_code == 404


@pytest.mark.parametrize("patch", [{"quantity": 0}, {"quantity": 1.5}, {"cost": 0}, {"cost": -1}, {"bought_on": "x"}, {"symbol": "x!"}])
def test_portfolio_api_rejects_bad_input(client: TestClient, patch):
    assert client.post("/api/portfolio", json={**BODY, **patch}).status_code == 422
    assert client.get("/api/portfolio").json()["rows"] == []


def test_portfolio_api_rejects_future_date(client: TestClient):
    future = (date.today() + timedelta(days=2)).isoformat()
    r = client.post("/api/portfolio", json={**BODY, "bought_on": future})
    assert r.status_code == 422 and "sau hôm nay" in r.json()["detail"]


def test_portfolio_api_does_not_save_symbol_without_data(client: TestClient, monkeypatch):
    import wyckoff.service as service

    def boom(*a, **k):
        raise RuntimeError("không có mã ZZZZ")

    monkeypatch.setattr(service, "get_ohlcv", boom)
    r = client.post("/api/portfolio", json={**BODY, "symbol": "ZZZZ"})
    assert r.status_code == 404 and client.get("/api/portfolio").json()["rows"] == []


def test_portfolio_api_keeps_row_when_data_fails_later(client: TestClient, tmp_path, monkeypatch):
    import wyckoff.service as service

    PortfolioStore(tmp_path / "p.db").add(Holding("ZZZZ", 100, 10.0, "2026-01-01"))

    def boom(*a, **k):
        raise RuntimeError("mạng lỗi")

    monkeypatch.setattr(service, "get_ohlcv", boom)
    p = client.get("/api/portfolio").json()
    assert p["rows"][0]["error"] and p["warnings"] and p["summary"]["value"] == 0


def test_quote(client: TestClient):
    q = client.get("/api/quote/demo").json()
    assert q["symbol"] == "DEMO" and q["close"] > 0
    assert client.get("/api/quote/x!").status_code == 422
