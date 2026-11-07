"""Quy tắc bán: đánh giá đạt / chưa kèm con số, "đạt từ", thứ tự, API. Không gọi mạng."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wyckoff.portfolio import (Holding, PortfolioStore, Rule, evaluate_rule, holding_row, portfolio_view, rule_catalog,
                               validate_rule)
from wyckoff.web.app import Settings, create_app

CATALOG = rule_catalog((3, 5), (2, 3))
DATES = [f"2026-10-{d:02d}" for d in range(1, 12)]


def _view(closes, levels=(), segments=None, stage="Markup", ema=None):
    bars = [{"t": DATES[i], "c": c, "ema_fast": None if ema is None else ema[i], "ema_slow": None} for i, c in enumerate(closes)]
    return {"as_of": bars[-1]["t"], "bars": bars, "levels": list(levels), "stage": {"title": stage},
            "phase": {"title": "Pha C", "support": None, "resistance": None},
            "stage_segments": segments if segments is not None else [{"kind": "up", "i0": 0, "i1": len(bars) - 1}]}


def _eval(kind, value, view, cost=100.0, bought="2026-10-01", prev=None):
    h = Holding("AAA", 100, cost, bought)
    return evaluate_rule(Rule(1, "AAA", kind, value), h, view, prev, CATALOG, (3, 5))


# ------------------------------------------------------------------ theo giá vốn

def test_loss_rule_not_met_shows_distance():
    r = _eval("loss_pct", 8, _view([100, 95, 93]))
    assert not r["met"] and r["threshold"] == 92 and r["now"] == -7 and r["now_type"] == "pct"
    assert r["gap_pct"] == round((92 / 93 - 1) * 100, 2) and r["label"] == "Lỗ quá 8%"


def test_loss_rule_counts_threshold_as_met_and_streak():
    r = _eval("loss_pct", 8, _view([100, 90, 95, 92, 91]))
    assert r["met"] and r["since"] == DATES[3] and r["sessions"] == 2 and not r["fresh"] and r["gap_pct"] is None


def test_profit_rule_fresh():
    r = _eval("profit_pct", 20, _view([100, 110, 121]))
    assert r["met"] and r["fresh"] and r["since"] == DATES[2] and r["threshold"] == 120 and r["label"] == "Lãi đạt 20%"


def test_streak_starts_no_earlier_than_purchase():
    r = _eval("close_below", 50, _view([40, 40, 40, 40]), bought=DATES[2])
    assert r["since"] == DATES[2] and r["sessions"] == 2


# ------------------------------------------------------------------ mức giá, đường trung bình, vô hiệu

def test_close_below_is_strict():
    assert not _eval("close_below", 50, _view([60, 50]))["met"]
    assert _eval("close_below", 50, _view([60, 49.9]))["met"]


def test_sma_rule_from_closes():
    r = _eval("below_sma_fast", None, _view([10, 10, 10, 10, 7]))
    assert r["met"] and r["threshold"] == 9 and r["label"] == "Đóng cửa dưới SMA3" and r["fresh"]


def test_ma_rule_with_offset_below_line():
    closes = [10, 10, 10, 9.65]
    sma = sum(closes[-3:]) / 3
    r = _eval("below_sma_fast", -4, _view(closes))
    assert r["threshold"] == round(sma * 0.96, 2) and r["reference"] == round(sma, 2) and r["label"] == "Đóng cửa dưới SMA3 4%"
    assert not r["met"] and r["gap_pct"] == round((sma * 0.96 / 9.65 - 1) * 100, 2)   # dưới đường nhưng chưa đủ 4%
    assert _eval("below_sma_fast", 0, _view(closes))["met"]                            # 0%: chỉ cần dưới đường
    assert _eval("below_sma_fast", -4, _view([10, 10, 10, 9]))["met"]


def test_ma_rule_zero_and_missing_offset_read_the_same():
    a, b = _eval("below_sma_fast", 0, _view([10, 10, 10, 9])), _eval("below_sma_fast", None, _view([10, 10, 10, 9]))
    assert a["label"] == b["label"] == "Đóng cửa dưới SMA3" and a["threshold"] == b["threshold"]


def test_ma_rule_offset_label_keeps_decimal():
    assert _eval("below_ema_fast", -2.5, _view([10, 9], ema=[None, 11]))["label"] == "Đóng cửa dưới EMA2 2,5%"


def test_ma_without_enough_history_is_explained():
    r = _eval("below_sma_slow", None, _view([10, 10]))
    assert not r["met"] and r["threshold"] is None and r["gap_pct"] is None and "đường trung bình" in r["note"]


def test_ema_rule_uses_engine_series():
    r = _eval("below_ema_fast", None, _view([10, 10, 9], ema=[None, 11, 12]))
    assert r["met"] and r["threshold"] == 12 and r["since"] == DATES[1] and r["label"] == "Đóng cửa dưới EMA2"


def test_invalidate_rule_uses_highest_level_and_skips_sc_extension():
    levels = [{"type": "invalidate", "price": 70.0, "label": "x"}, {"type": "invalidate", "price": 74.9, "label": "y"},
              {"type": "invalidate", "price": 90.0, "label": "Thủng đáy SC: vùng climax kéo dài (không phải vô hiệu)"}]
    r = _eval("below_invalidate", None, _view([75, 73.7], levels))
    assert r["met"] and r["fresh"] and r["threshold"] == 74.9


def test_invalidate_rule_without_level():
    r = _eval("below_invalidate", None, _view([75, 73.7]))
    assert not r["met"] and "chưa có mức vô hiệu" in r["note"]


# ------------------------------------------------------------------ gần đạt, chốt lãi / chốt lỗ

def test_near_when_gap_within_limit():
    assert _eval("close_below", 98, _view([100]))["near"] and _eval("close_below", 98, _view([100]))["gap_pct"] == -2
    assert not _eval("close_below", 97.9, _view([100]))["near"]
    assert _eval("profit_pct", 20, _view([118]))["near"]
    met = _eval("close_below", 110, _view([100]))
    assert met["met"] and not met["near"]


@pytest.mark.parametrize("seg, near", [("down_potential", True), ("distribution_developing", False), ("up", False)])
def test_stage_near_for_potential(seg, near):
    v = _view([10, 9], segments=[{"kind": seg, "i0": 0, "i1": 1}])
    assert _eval("stage_markdown", None, v)["near"] is near


def test_row_order_near_before_other_and_summary_by_side():
    v = _view([100, 100])
    rules = [Rule(1, "AAA", "close_below", 50, "loss"), Rule(2, "AAA", "close_below", 99, "loss"),
             Rule(3, "AAA", "close_below", 120, "profit"), Rule(4, "AAA", "close_below", 110, "loss")]
    row = holding_row(Holding("AAA", 100, 100.0, DATES[0]), v, None, rules, CATALOG, (3, 5))
    assert [r["id"] for r in row["rules"]] == [3, 4, 2, 1]
    s = portfolio_view([row])["summary"]
    # Chốt lãi đạt 1/1 là đủ; chốt lỗ mới đạt 1/3 và còn quy tắc xa ngưỡng nên chưa đủ, cũng chưa gần đủ
    assert (s["symbols_profit"], s["symbols_loss"], s["symbols_near"], s["symbols_with_rules"]) == (1, 0, 0, 1)
    assert row["attention"] == "profit" and row["exit"]["loss"]["met"] == 1 and not row["exit"]["loss"]["near"]


def test_rows_with_near_rule_come_before_larger_positions():
    v = _view([100, 100])
    big = holding_row(Holding("BIG", 1000, 100.0, DATES[0]), v, None, [Rule(1, "BIG", "close_below", 50)], CATALOG, (3, 5))
    near = holding_row(Holding("NER", 10, 100.0, DATES[0]), v, None, [Rule(2, "NER", "close_below", 99)], CATALOG, (3, 5))
    assert [r["symbol"] for r in portfolio_view([big, near])["rows"]] == ["NER", "BIG"]


def _group_row(symbol, rules, closes=(100, 100), qty=100):
    return holding_row(Holding(symbol, qty, 100.0, DATES[0]), _view(list(closes)), None, rules, CATALOG, (3, 5))


def test_partial_group_is_not_ready():
    # Như MSN: đạt 1/3 quy tắc chốt lỗ, các quy tắc còn lại xa ngưỡng
    r = _group_row("MSN", [Rule(1, "MSN", "close_below", 110), Rule(2, "MSN", "close_below", 50), Rule(3, "MSN", "close_below", 60)])
    assert r["attention"] is None and not r["exit"]["loss"]["ready"] and not r["exit"]["loss"]["near"]
    assert r["exit"]["loss"]["met"] == 1 and r["exit"]["loss"]["total"] == 3


def test_group_ready_only_when_all_rules_met():
    r = _group_row("VCB", [Rule(1, "VCB", "close_below", 110), Rule(2, "VCB", "close_below", 120)])
    assert r["exit"]["loss"]["ready"] and r["attention"] == "loss" and not r["exit"]["loss"]["near"]
    assert not r["exit"]["profit"]["ready"] and r["exit"]["profit"]["total"] == 0   # nhóm rỗng không bao giờ đủ


def test_group_near_only_when_every_remaining_rule_is_near():
    near = _group_row("AAA", [Rule(1, "AAA", "close_below", 110), Rule(2, "AAA", "close_below", 99)])
    assert near["exit"]["loss"]["near"] and near["attention"] == "near"
    far = _group_row("AAA", [Rule(1, "AAA", "close_below", 99), Rule(2, "AAA", "close_below", 50)])
    assert not far["exit"]["loss"]["near"] and far["attention"] is None and far["rules"][0]["near"]   # từng quy tắc vẫn báo gần đạt


def test_attention_prefers_loss_and_order_follows_it():
    both = _group_row("BOTH", [Rule(1, "BOTH", "close_below", 110, "profit"), Rule(2, "BOTH", "close_below", 110, "loss")])
    assert both["attention"] == "loss" and both["exit"]["profit"]["ready"]
    # Đủ điều kiện từ lâu xếp sau mã vừa đủ, trước mã gần đạt; mã không có gì xếp cuối dù giá trị lớn
    old = _group_row("OLD", [Rule(3, "OLD", "close_below", 110)], qty=1)
    fresh = _group_row("NEW", [Rule(4, "NEW", "close_below", 100.5)], closes=(101, 100), qty=1)
    near = _group_row("NER", [Rule(5, "NER", "close_below", 99)], qty=1)
    plain = _group_row("BIG", [], qty=9999)
    assert fresh["exit"]["loss"]["fresh"]
    assert [r["symbol"] for r in portfolio_view([plain, near, old, fresh])["rows"]] == ["NEW", "OLD", "NER", "BIG"]


def test_sufficient_rule_makes_group_ready_alone():
    # Như MSN: "Lỗ quá 7%" đã đạt, quy tắc EMA còn xa
    r = _group_row("MSN", [Rule(1, "MSN", "close_below", 110, "loss", True), Rule(2, "MSN", "close_below", 50, "loss")])
    g = r["exit"]["loss"]
    assert g["ready"] and g["by_sufficient"] and g["met"] == 1 and g["total"] == 2 and r["attention"] == "loss"


def test_sufficient_rule_only_affects_its_own_group():
    r = _group_row("AAA", [Rule(1, "AAA", "close_below", 110, "loss", True), Rule(2, "AAA", "close_below", 50, "profit")])
    assert r["exit"]["loss"]["ready"] and not r["exit"]["profit"]["ready"]


def test_sufficient_rule_not_met_changes_nothing():
    r = _group_row("AAA", [Rule(1, "AAA", "close_below", 50, "loss", True), Rule(2, "AAA", "close_below", 110, "loss")])
    assert not r["exit"]["loss"]["ready"] and r["exit"]["loss"]["has_sufficient"] and r["attention"] is None
    # Cách cũ vẫn đúng: đạt toàn bộ thì đủ, không cần quy tắc "đạt là đủ" nào
    r = _group_row("AAA", [Rule(1, "AAA", "close_below", 110), Rule(2, "AAA", "close_below", 120)])
    assert r["exit"]["loss"]["ready"] and not r["exit"]["loss"]["by_sufficient"]


def test_sufficient_rule_near_warns_even_if_others_are_far():
    r = _group_row("AAA", [Rule(1, "AAA", "close_below", 99, "loss", True), Rule(2, "AAA", "close_below", 50, "loss")])
    assert r["exit"]["loss"]["near"] and r["attention"] == "near"


def test_fresh_with_sufficient_counts_when_group_became_ready():
    closes = (101, 100)
    new = _group_row("NEW", [Rule(1, "NEW", "close_below", 100.5, "loss", True), Rule(2, "NEW", "close_below", 50)], closes=closes)
    assert new["exit"]["loss"]["fresh"]
    # Quy tắc đạt là đủ đã đạt từ trước; quy tắc thường vừa đạt không làm nhóm "vừa đủ"
    old = _group_row("OLD", [Rule(1, "OLD", "close_below", 110, "loss", True), Rule(2, "OLD", "close_below", 100.5)], closes=closes)
    assert old["exit"]["loss"]["ready"] and not old["exit"]["loss"]["fresh"]


def test_store_keeps_sufficient_as_bool(tmp_path):
    s = PortfolioStore(tmp_path / "p.db")
    a = s.add_rule("AAA", "loss_pct", 7, "loss", True)
    assert s.rule(a.id).sufficient is True and s.rules()["AAA"][0].sufficient is True
    s.update_rule(a.id, "loss_pct", 7, "loss", False)
    assert s.rule(a.id).sufficient is False


def test_old_database_gets_sufficient_column(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE rules (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, kind TEXT NOT NULL, value REAL, side TEXT NOT NULL DEFAULT 'loss')")
    conn.execute("INSERT INTO rules (symbol, kind, value, side) VALUES ('AAA', 'loss_pct', 8, 'loss')")
    conn.commit()
    conn.close()
    assert PortfolioStore(path).rules()["AAA"][0].sufficient is False


def test_old_database_gets_side_column(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE rules (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, kind TEXT NOT NULL, value REAL)")
    conn.executemany("INSERT INTO rules (symbol, kind, value) VALUES (?, ?, ?)",
                     [("AAA", "profit_pct", 20), ("AAA", "below_ema_slow", -4), ("AAA", "loss_pct", 8)])
    conn.commit()
    conn.close()
    assert [r.side for r in PortfolioStore(path).rules()["AAA"]] == ["profit", "loss", "loss"]
    assert [r.side for r in PortfolioStore(path).rules()["AAA"]] == ["profit", "loss", "loss"]   # mở lại không đổi


# ------------------------------------------------------------------ giai đoạn

@pytest.mark.parametrize("seg", ["down_potential", "distribution_potential", "distribution_developing", "up"])
def test_stage_rule_not_met_unless_confirmed(seg):
    v = _view([10, 9], segments=[{"kind": seg, "i0": 0, "i1": 1}], stage="Markdown tiềm năng")
    for kind in ("stage_markdown", "stage_distribution"):
        r = _eval(kind, None, v)
        assert not r["met"] and r["now"] == "Markdown tiềm năng" and r["now_type"] == "text"


def test_stage_rule_met_and_fresh_compared_to_previous_session():
    now = _view([10, 9, 8], segments=[{"kind": "range", "i0": 0, "i1": 0}, {"kind": "down", "i0": 1, "i1": 2}], stage="Markdown")
    prev = _view([10, 9], segments=[{"kind": "down_potential", "i0": 0, "i1": 1}])
    r = _eval("stage_markdown", None, now, prev=prev)
    assert r["met"] and r["fresh"] and r["since"] == DATES[1] and r["sessions"] == 2 and r["threshold_text"] == "Markdown"
    assert not _eval("stage_markdown", None, now, prev=now)["fresh"]
    assert _eval("stage_distribution", None, now, prev=prev)["met"] is False


# ------------------------------------------------------------------ kiểm tra đầu vào, thứ tự

@pytest.mark.parametrize("kind, value, ok", [
    ("loss_pct", 8, True), ("loss_pct", None, False), ("loss_pct", 0, False), ("loss_pct", 100, False),
    ("profit_pct", 20, True), ("close_below", 52, True), ("close_below", -1, False),
    ("below_sma_fast", None, True), ("below_sma_fast", 0, True), ("below_sma_fast", -4, True), ("below_sma_fast", 5, False), ("below_sma_fast", -100, False), ("stage_markdown", None, True), ("xyz", None, False),
])
def test_validate_rule(kind, value, ok):
    assert (validate_rule(kind, value) is None) == ok


def test_row_orders_rules_and_view_counts_them():
    v = _view([100, 95, 93, 80])
    rules = [Rule(1, "AAA", "profit_pct", 50), Rule(2, "AAA", "close_below", 79), Rule(3, "AAA", "loss_pct", 10),
             Rule(4, "AAA", "below_invalidate")]
    row = holding_row(Holding("AAA", 100, 100.0, DATES[0]), v, None, rules, CATALOG, (3, 5))
    assert [r["id"] for r in row["rules"]] == [3, 2, 1, 4]   # vừa đạt, chưa đạt gần trước, không có khoảng cách cuối
    other = holding_row(Holding("BBB", 1000, 100.0, DATES[0]), v, None, [], CATALOG, (3, 5))
    p = portfolio_view([other, row], catalog=CATALOG)
    assert p["summary"]["rules_total"] == 4 and p["summary"]["rules_met"] == 1 and p["summary"]["rules_fresh"] == 1
    assert [r["symbol"] for r in p["rows"]] == ["BBB", "AAA"]   # mới đạt 1/4 quy tắc chốt lỗ: chưa được ưu tiên, xếp theo giá trị
    assert p["rule_catalog"] == CATALOG


# ------------------------------------------------------------------ lưu trữ, API

def test_store_rules_and_cascade(tmp_path):
    s = PortfolioStore(tmp_path / "p.db")
    s.add(Holding("AAA", 1, 1.0, "2026-01-01"))
    a = s.add_rule("AAA", "loss_pct", 8)
    b = s.add_rule("AAA", "below_invalidate", None)
    with pytest.raises(ValueError):
        s.add_rule("AAA", "below_invalidate", None)   # NULL cũng không được trùng
    with pytest.raises(ValueError):
        s.update_rule(a.id, "below_invalidate", None)
    assert s.update_rule(a.id, "loss_pct", 10) and s.rule(a.id).value == 10
    assert [r.id for r in s.rules()["AAA"]] == [a.id, b.id]
    s.delete("AAA")
    assert s.rules() == {} and s.rule(a.id) is None


@pytest.fixture
def client(tmp_path) -> TestClient:
    c = TestClient(create_app(Settings(no_llm=True, no_market=True, out_dir=str(tmp_path), portfolio_db=str(tmp_path / "p.db"))))
    assert c.post("/api/portfolio", json={"symbol": "DEMO", "quantity": 100, "cost": 70.0, "bought_on": "2023-01-02"}).status_code == 201
    return c


def test_rules_api_flow(client: TestClient):
    r = client.post("/api/rules", json={"symbol": "demo", "kind": "loss_pct", "value": 5})
    assert r.status_code == 201
    rule_id = r.json()["id"]
    assert client.post("/api/rules", json={"symbol": "DEMO", "kind": "loss_pct", "value": 5}).status_code == 409

    p = client.get("/api/portfolio").json()
    item = p["rows"][0]["rules"][0]
    assert item["label"] == "Lỗ quá 5%" and item["threshold"] == 66.5 and p["summary"]["rules_total"] == 1 and p["rule_catalog"]

    assert client.put(f"/api/rules/{rule_id}", json={"kind": "below_sma_fast"}).json()["value"] == 0   # không gửi: 0%
    assert client.post("/api/rules", json={"symbol": "DEMO", "kind": "below_sma_fast", "value": 0}).status_code == 409
    created = client.post("/api/rules", json={"symbol": "DEMO", "kind": "below_sma_fast", "value": -4})
    assert created.status_code == 201
    assert client.get("/api/rules/preview", params={"symbol": "DEMO", "kind": "below_sma_fast", "value": -4}).json()["label"] == "Đóng cửa dưới SMA50 4%"
    assert client.delete(f"/api/rules/{created.json()['id']}").status_code == 204
    assert client.get("/api/portfolio").json()["rows"][0]["rules"][0]["kind"] == "below_sma_fast"
    assert client.delete(f"/api/rules/{rule_id}").status_code == 204
    assert client.delete(f"/api/rules/{rule_id}").status_code == 404
    assert client.put(f"/api/rules/{rule_id}", json={"kind": "below_sma_fast"}).status_code == 404


def test_rules_api_rejects_bad_input(client: TestClient):
    for body in ({"symbol": "DEMO", "kind": "xyz"}, {"symbol": "DEMO", "kind": "loss_pct"}, {"symbol": "DEMO", "kind": "loss_pct", "value": 150},
                 {"symbol": "DEMO", "kind": "stage_markdown", "value": 1}, {"symbol": "x!", "kind": "stage_markdown"}):
        assert client.post("/api/rules", json=body).status_code == 422, body
    assert client.post("/api/rules", json={"symbol": "HPG", "kind": "stage_markdown"}).status_code == 404   # mã chưa có trong danh mục
    assert client.get("/api/portfolio").json()["summary"]["rules_total"] == 0


def test_rules_api_side(client: TestClient):
    a = client.post("/api/rules", json={"symbol": "DEMO", "kind": "below_ema_slow", "side": "profit"}).json()
    assert a["side"] == "profit"
    assert client.post("/api/rules", json={"symbol": "DEMO", "kind": "below_sma_fast"}).json()["side"] == "loss"   # mặc định
    # Loại theo lãi / lỗ so với giá vốn không đổi được nhóm
    assert client.post("/api/rules", json={"symbol": "DEMO", "kind": "profit_pct", "value": 10, "side": "loss"}).json()["side"] == "profit"
    assert client.post("/api/rules", json={"symbol": "DEMO", "kind": "loss_pct", "value": 10, "side": "profit"}).json()["side"] == "loss"
    assert client.post("/api/rules", json={"symbol": "DEMO", "kind": "close_below", "value": 1, "side": "x"}).status_code == 422
    assert client.put(f"/api/rules/{a['id']}", json={"kind": "below_ema_slow", "side": "loss"}).json()["side"] == "loss"
    assert client.get("/api/portfolio").json()["near_pct"] == 2


def test_rules_api_sufficient(client: TestClient):
    a = client.post("/api/rules", json={"symbol": "DEMO", "kind": "loss_pct", "value": 99, "sufficient": True}).json()
    assert a["sufficient"] is True
    assert client.get("/api/portfolio").json()["rows"][0]["rules"][0]["sufficient"] is True
    assert client.put(f"/api/rules/{a['id']}", json={"kind": "loss_pct", "value": 99}).json()["sufficient"] is False
    assert client.post("/api/rules", json={"symbol": "DEMO", "kind": "profit_pct", "value": 1}).json()["sufficient"] is False


def test_rule_preview_does_not_save(client: TestClient):
    r = client.get("/api/rules/preview", params={"symbol": "DEMO", "kind": "profit_pct", "value": 10})
    assert r.status_code == 200 and r.json()["threshold"] == 77 and r.json()["label"] == "Lãi đạt 10%"
    assert client.get("/api/portfolio").json()["summary"]["rules_total"] == 0
    assert client.get("/api/rules/preview", params={"symbol": "HPG", "kind": "stage_markdown"}).status_code == 404
    assert client.get("/api/rules/preview", params={"symbol": "DEMO", "kind": "loss_pct"}).status_code == 422


def test_deleting_holding_removes_rules(client: TestClient):
    client.post("/api/rules", json={"symbol": "DEMO", "kind": "stage_markdown"})
    client.delete("/api/portfolio/DEMO")
    client.post("/api/portfolio", json={"symbol": "DEMO", "quantity": 100, "cost": 70.0, "bought_on": "2023-01-02"})
    assert client.get("/api/portfolio").json()["rows"][0]["rules"] == []
