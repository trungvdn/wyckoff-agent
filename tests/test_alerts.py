"""Cảnh báo sau phiên: chỉ báo khi có thay đổi, không báo lặp, chạy bù, ngày nghỉ, gửi lỗi. Không gọi mạng."""
from __future__ import annotations

import io
import json
import os
import urllib.error

import pytest

from wyckoff.alerts import (AlertSendError, TelegramSender, build_sections, current_summary, format_message, load_env_file, read_env_file,
                            row_state, run_alerts, split_message, telegram_from_env)
from wyckoff.portfolio import Holding, PortfolioStore, Rule, error_row, holding_row, portfolio_view, rule_catalog

CATALOG = rule_catalog((3, 5), (2, 3))


def _view_model(close, as_of, stage="Markup", phase="Pha E"):
    bars = [{"t": "2026-11-03", "c": 100.0, "ema_fast": None, "ema_slow": None}, {"t": as_of, "c": close, "ema_fast": None, "ema_slow": None}]
    return {"as_of": as_of, "bars": bars, "levels": [], "stage": {"title": stage}, "phase": {"title": phase, "support": None, "resistance": None},
            "stage_segments": [{"kind": "up", "i0": 0, "i1": 1}]}


def _row(close=100.0, as_of="2026-11-05", rules=(), symbol="AAA", **kw):
    h = Holding(symbol, 100, 100.0, "2026-11-01")
    return holding_row(h, _view_model(close, as_of, **kw), None, rules, CATALOG, (3, 5))


LOSS = Rule(1, "AAA", "loss_pct", 7, "loss")
PROFIT = Rule(2, "AAA", "profit_pct", 10, "profit")


class Outbox:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def __call__(self, text):
        if self.fail:
            raise AlertSendError("mạng lỗi")
        self.sent.append(text)


@pytest.fixture
def store(tmp_path):
    return PortfolioStore(tmp_path / "p.db")


def _run(store, rows, out=None, **kw):
    out = out if out is not None else Outbox()
    return run_alerts(portfolio_view(rows), store, out, **kw), out


# ------------------------------------------------------------------ chạy nhiều lượt

def test_first_run_sends_summary_even_when_nothing_is_ready(store):
    r, out = _run(store, [_row(100, rules=[LOSS])])
    assert r.status == "sent" and "Bắt đầu theo dõi 1 mã" in out.sent[0] and "chưa có mã nào" in out.sent[0]


def test_first_run_lists_current_state_without_stage_change(store):
    r, out = _run(store, [_row(90, rules=[LOSS])])
    assert "ĐỦ ĐIỀU KIỆN CHỐT LỖ" in out.sent[0] and "Lỗ quá 7%: -10,00% (ngưỡng 93,00)" in out.sent[0]
    assert "ĐỔI GIAI ĐOẠN" not in out.sent[0]


def test_no_repeat_while_state_is_unchanged(store):
    _run(store, [_row(90, rules=[LOSS])])
    r, out = _run(store, [_row(89, "2026-11-06", rules=[LOSS])])
    assert r.status == "quiet" and out.sent == []


def test_alerts_when_state_turns_ready(store):
    _run(store, [_row(100, rules=[LOSS])])
    r, out = _run(store, [_row(90, "2026-11-06", rules=[LOSS])])
    assert r.status == "sent" and "phiên 06/11/2026" in out.sent[0] and "AAA  Lỗ quá 7%" in out.sent[0]


def test_alerts_again_after_leaving_and_reentering(store):
    _run(store, [_row(90, rules=[LOSS])])
    _run(store, [_row(100, "2026-11-06", rules=[LOSS])])
    r, _ = _run(store, [_row(90, "2026-11-07", rules=[LOSS])])
    assert r.status == "sent"


def test_catches_up_after_days_off(store):
    # Máy tắt nhiều phiên: so với trạng thái đã lưu nên vẫn báo, dù quy tắc không còn "vừa đạt"
    _run(store, [_row(100, rules=[LOSS])])
    rule_row = _row(90, "2026-11-20", rules=[LOSS])
    rule_row["rules"][0]["fresh"] = False
    r, out = _run(store, [rule_row])
    assert r.status == "sent" and "Lỗ quá 7%" in out.sent[0]


def test_no_new_session_sends_nothing(store):
    _run(store, [_row(100, rules=[LOSS])])
    r, out = _run(store, [_row(90, rules=[LOSS])])   # cùng phiên, ngày nghỉ hoặc chạy lại trong ngày
    assert r.status == "quiet" and out.sent == []
    assert store.alert_states()["AAA"][0]["loss_ready"] is False   # phiên mới vẫn báo được


def test_failed_send_keeps_state_so_next_run_retries(store):
    _run(store, [_row(100, rules=[LOSS])])
    with pytest.raises(AlertSendError):
        _run(store, [_row(90, "2026-11-06", rules=[LOSS])], Outbox(fail=True))
    assert store.alert_states()["AAA"][1] == "2026-11-05"
    r, out = _run(store, [_row(90, "2026-11-06", rules=[LOSS])])
    assert r.status == "sent" and out.sent


def test_dry_run_changes_nothing(store):
    out = Outbox()
    r = run_alerts(portfolio_view([_row(90, rules=[LOSS])]), store, out, dry_run=True)
    assert r.status == "dry_run" and "Lỗ quá 7%" in r.text and out.sent == [] and store.alert_states() == {} and store.alert_log() == []


def test_empty_portfolio_sends_nothing(store):
    r, out = _run(store, [])
    assert r.status == "no_holdings" and out.sent == []


def test_sold_symbol_state_is_removed_and_rebuy_counts_as_new(store):
    _run(store, [_row(90, rules=[LOSS]), _row(100, symbol="BBB")])
    _run(store, [_row(100, "2026-11-06", symbol="BBB")])
    assert set(store.alert_states()) == {"BBB"}


def test_log_keeps_sent_messages(store):
    _run(store, [_row(90, rules=[LOSS])])
    assert store.alert_log()[0][0] == "2026-11-05" and "Lỗ quá 7%" in store.alert_log()[0][1]


# ------------------------------------------------------------------ bật / tắt theo mã

def _muted(**kw):
    return {**_row(**kw), "alerts_enabled": False}


def test_muted_symbol_is_not_alerted(store):
    r, out = _run(store, [_muted(close=90, rules=[LOSS], symbol="AAA"), _row(100, symbol="BBB")])
    assert "AAA" not in out.sent[0] and "Bắt đầu theo dõi 1 mã" in out.sent[0]
    assert set(store.alert_states()) == {"BBB"}


def test_muted_symbol_error_is_not_reported(store):
    bad = {**error_row(Holding("AAA", 1, 1.0, "2026-11-01"), "lỗi"), "alerts_enabled": False}
    r, out = _run(store, [bad, _row(100, symbol="BBB")])
    assert "CẦN KIỂM TRA" not in out.sent[0]


def test_all_muted_sends_nothing(store):
    r, out = _run(store, [_muted(close=90, rules=[LOSS])])
    assert r.status == "quiet" and out.sent == []


def test_reenabling_reports_current_state_on_next_session(store):
    _run(store, [_row(90, rules=[LOSS]), _row(100, symbol="BBB")])            # AAA đã báo
    _run(store, [_muted(close=90, as_of="2026-11-06", rules=[LOSS]), _row(100, "2026-11-06", symbol="BBB")])   # tắt
    assert "AAA" not in store.alert_states()
    r, out = _run(store, [_row(90, "2026-11-07", rules=[LOSS]), _row(100, "2026-11-07", symbol="BBB")])         # bật lại
    assert r.status == "sent" and "AAA  Lỗ quá 7%" in out.sent[0] and "Bắt đầu" not in out.sent[0]


def test_muting_on_same_session_drops_state(store):
    _run(store, [_row(90, rules=[LOSS]), _row(100, symbol="BBB")])
    _run(store, [_muted(close=90, rules=[LOSS]), _row(100, symbol="BBB")])
    assert set(store.alert_states()) == {"BBB"}


def test_store_alerts_flag(store):
    store.add(Holding("AAA", 1, 1.0, "2026-01-01"))
    assert store.list()[0].alerts_enabled is True
    assert store.set_alerts("AAA", False) and store.list()[0].alerts_enabled is False
    store.update(Holding("AAA", 2, 1.0, "2026-01-01"))                 # sửa mã không đổi cờ
    assert store.list()[0].alerts_enabled is False
    assert not store.set_alerts("ZZZ", True)


def test_old_database_gets_alerts_column(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE holdings (symbol TEXT PRIMARY KEY, quantity INTEGER NOT NULL, cost REAL NOT NULL, bought_on TEXT NOT NULL)")
    conn.execute("INSERT INTO holdings VALUES ('AAA', 1, 1.0, '2026-01-01')")
    conn.commit()
    conn.close()
    assert PortfolioStore(path).list()[0].alerts_enabled is True


def test_current_summary_lists_all_and_keeps_state(store):
    _run(store, [_row(90, rules=[LOSS])])   # đã báo rồi, gửi tay vẫn liệt kê
    s = current_summary(portfolio_view([_row(90, rules=[LOSS]), _muted(close=90, rules=[LOSS], symbol="MUT")]))
    assert "AAA  Lỗ quá 7%" in s["text"] and "MUT" not in s["text"]
    assert s["enabled_count"] == 1 and s["muted"] == ["MUT"] and "Tình trạng hiện tại của 1 mã" in s["text"]


def test_current_summary_when_nothing_to_report():
    s = current_summary(portfolio_view([_row(100)]))
    assert "chưa có mã nào đủ điều kiện" in s["text"]


def test_telegram_from_env_reads_file_each_time(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    f = tmp_path / ".env"
    assert telegram_from_env(f) is None
    f.write_text("TELEGRAM_BOT_TOKEN=a\nTELEGRAM_CHAT_ID=1\n", encoding="utf-8")
    assert telegram_from_env(f).chat_id == "1"
    f.write_text("TELEGRAM_BOT_TOKEN=a\nTELEGRAM_CHAT_ID=2\n", encoding="utf-8")
    assert telegram_from_env(f).chat_id == "2"   # sửa file không cần khởi động lại
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "9")
    assert telegram_from_env(f).chat_id == "9"
    assert read_env_file(tmp_path / "khong-co") == {}


# ------------------------------------------------------------------ API

@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import wyckoff.web.app as web

    sent = []

    class Fake:
        fail = False

        def send(self, text):
            if Fake.fail:
                raise AlertSendError("Telegram báo lỗi 403: Forbidden")
            sent.append(text)

    box = {"sender": Fake()}
    monkeypatch.setattr(web, "telegram_from_env", lambda: box["sender"])
    client = TestClient(web.create_app(web.Settings(no_llm=True, no_market=True, out_dir=str(tmp_path), portfolio_db=str(tmp_path / "p.db"))))
    assert client.post("/api/portfolio", json={"symbol": "DEMO", "quantity": 100, "cost": 70.0, "bought_on": "2023-01-02"}).status_code == 201
    return client, sent, box, Fake, tmp_path


def test_api_toggle(api):
    client, *_ = api
    assert client.get("/api/portfolio").json()["rows"][0]["alerts_enabled"] is True
    assert client.put("/api/portfolio/demo/alerts", json={"enabled": False}).json() == {"symbol": "DEMO", "alerts_enabled": False}
    assert client.get("/api/portfolio").json()["rows"][0]["alerts_enabled"] is False
    assert client.put("/api/portfolio/HPG/alerts", json={"enabled": False}).status_code == 404
    assert client.put("/api/portfolio/DEMO/alerts", json={"enabled": "x"}).status_code == 422


def test_api_preview_does_not_send(api):
    client, sent, *_ = api
    p = client.get("/api/alerts/preview").json()
    assert p["configured"] is True and p["enabled_count"] == 1 and "Wyckoff Agent" in p["text"] and sent == []


def test_api_send_and_log(api):
    client, sent, _, _, tmp_path = api
    r = client.post("/api/alerts/send", json={"confirm": True})
    assert r.status_code == 200 and len(sent) == 1 and "Tình trạng hiện tại" in sent[0]
    s = PortfolioStore(tmp_path / "p.db")
    assert len(s.alert_log()) == 1 and s.alert_states() == {}   # gửi tay không đổi trạng thái của lịch tự động


def test_api_send_requires_json_confirm(api):
    client, sent, *_ = api
    assert client.post("/api/alerts/send").status_code == 422
    assert client.post("/api/alerts/send", json={"confirm": False}).status_code == 422
    assert client.post("/api/alerts/send", content='{"confirm": true}', headers={"Content-Type": "text/plain"}).status_code == 422
    assert sent == []


def test_api_send_without_config(api):
    client, sent, box, *_ = api
    box["sender"] = None
    assert client.get("/api/alerts/preview").json()["configured"] is False
    r = client.post("/api/alerts/send", json={"confirm": True})
    assert r.status_code == 503 and "TELEGRAM_CHAT_ID" in r.json()["detail"]


def test_api_send_failure_is_reported_and_not_logged(api):
    client, _, _, Fake, tmp_path = api
    Fake.fail = True
    r = client.post("/api/alerts/send", json={"confirm": True})
    assert r.status_code == 502 and "403" in r.json()["detail"]
    assert PortfolioStore(tmp_path / "p.db").alert_log() == []


def test_api_send_when_all_muted(api):
    client, sent, *_ = api
    client.put("/api/portfolio/DEMO/alerts", json={"enabled": False})
    assert client.post("/api/alerts/send", json={"confirm": True}).status_code == 422 and sent == []


# ------------------------------------------------------------------ lỗi dữ liệu

def test_data_error_is_reported_and_keeps_old_state(store):
    _run(store, [_row(90, rules=[LOSS]), _row(100, symbol="BBB")])
    bad = error_row(Holding("AAA", 100, 100.0, "2026-11-01"), "Không tải được", [LOSS], CATALOG)
    r, out = _run(store, [bad, _row(100, "2026-11-06", symbol="BBB")])
    assert "CẦN KIỂM TRA" in out.sent[0] and "AAA: Không tải được" in out.sent[0]
    assert store.alert_states()["AAA"][1] == "2026-11-05"   # giữ để lần sau không báo lại như mã mới


def test_all_symbols_failing_still_alerts(store):
    bad = error_row(Holding("AAA", 100, 100.0, "2026-11-01"), "Không tải được")
    r, out = _run(store, [bad])
    assert r.status == "sent" and "CẦN KIỂM TRA" in out.sent[0] and "chưa có dữ liệu" in out.sent[0]


def test_update_failure_is_reported_even_without_new_session(store):
    _run(store, [_row(100)])
    r, out = _run(store, [_row(100)], extra_problems=["AAA: không cập nhật được giá"])
    assert r.status == "sent" and "không cập nhật được giá" in out.sent[0]


def test_lagging_symbol_is_flagged(store):
    r, out = _run(store, [_row(100), _row(100, "2026-11-06", symbol="BBB")])
    assert "AAA: dữ liệu chỉ đến 05/11/2026" in out.sent[0]


# ------------------------------------------------------------------ nội dung

def test_near_section_and_switch(store):
    near = [_row(94, rules=[LOSS])]   # ngưỡng 93, còn cách -1,06%
    s = build_sections(near, {})
    assert s.near == ["🔴 AAA  Gần chốt lỗ: Lỗ quá 7%, giá còn cách -1,06%"]
    assert build_sections(near, {}, include_near=False).near == []
    assert build_sections(near, {"AAA": row_state(near[0])}).near == []   # đã báo rồi


def test_stage_and_phase_changes():
    prev = {"AAA": row_state(_row(100, stage="Markup", phase="Pha D"))}
    s = build_sections([_row(100, stage="Markdown", phase="Pha E")], prev)
    assert s.changes == ["AAA  Markup → Markdown", "AAA  Pha D → Pha E"]


def test_ready_lists_only_sufficient_rule():
    r = _row(90, rules=[Rule(1, "AAA", "loss_pct", 7, "loss", True), Rule(2, "AAA", "close_below", 50, "loss")])
    s = build_sections([r], {})
    assert len(s.ready_loss) == 1 and "Lỗ quá 7%" in s.ready_loss[0]


def test_profit_goes_to_its_own_section():
    s = build_sections([_row(120, rules=[PROFIT])], {})
    assert s.ready_profit == ["AAA  Lãi đạt 10%: +20,00% (ngưỡng 110,00)"] and not s.ready_loss


def test_stage_rule_text():
    v = _view_model(100, "2026-11-05", stage="Markdown")
    v["stage_segments"] = [{"kind": "down", "i0": 0, "i1": 1}]
    r = holding_row(Holding("AAA", 1, 100.0, "2026-11-01"), v, None, [Rule(1, "AAA", "stage_markdown", None, "loss")], CATALOG, (3, 5))
    assert build_sections([r], {}).ready_loss == ["AAA  Giai đoạn là Markdown"]


def test_message_keeps_portfolio_private():
    # Số lượng và giá trị tiền không được xuất hiện, chỉ có ngưỡng và %
    h = Holding("AAA", 1234, 100.0, "2026-11-01")
    r = holding_row(h, _view_model(90, "2026-11-05"), None, [LOSS], CATALOG, (3, 5))
    text = format_message("2026-11-05", build_sections([r], {}), [])
    assert "1.234" not in text and "1234" not in text and " tr" not in text and "không phải khuyến nghị" in text


def test_message_icons_match_sections():
    loss, profit, near = _row(90, rules=[LOSS]), _row(120, rules=[PROFIT]), _row(94, rules=[LOSS], symbol="NER")
    text = format_message("2026-11-05", build_sections([loss, profit, near], {}), ["AAA: lỗi"])
    assert text.startswith("🤖 Wyckoff Agent · phiên 05/11/2026")
    for line in ("🔴 ĐỦ ĐIỀU KIỆN CHỐT LỖ", "🟢 ĐỦ ĐIỀU KIỆN CHỐT LÃI", "⚠️ GẦN ĐẠT", "🔴 NER  Gần chốt lỗ", "❗ CẦN KIỂM TRA"):
        assert line in text
    # Chốt lỗ đứng trước chốt lãi, chốt lãi trước gần đạt
    assert text.index("CHỐT LỖ") < text.index("CHỐT LÃI") < text.index("GẦN ĐẠT")


def test_split_message_on_lines():
    text = "\n".join(f"dòng {i}" for i in range(100))
    chunks = split_message(text, limit=50)
    assert all(len(c) <= 50 for c in chunks) and "\n".join(chunks) == text
    assert split_message("x" * 60, limit=50) == ["x" * 50]


# ------------------------------------------------------------------ Telegram, .env

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_telegram_send_payload(monkeypatch):
    calls = []

    def fake(req, timeout):
        calls.append((req.full_url, json.loads(req.data)))
        return _Resp(b'{"ok": true}')

    monkeypatch.setattr("urllib.request.urlopen", fake)
    TelegramSender("TOKEN", "42").send("xin chào")
    assert calls == [("https://api.telegram.org/botTOKEN/sendMessage", {"chat_id": "42", "text": "xin chào", "disable_web_page_preview": True})]


def test_telegram_error_never_contains_token(monkeypatch):
    def fake(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"description": "Unauthorized"}'))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(AlertSendError) as e:
        TelegramSender("SECRET-TOKEN", "42").send("x")
    assert "SECRET-TOKEN" not in str(e.value) and "401" in str(e.value) and e.value.__cause__ is None


def test_telegram_network_error_is_wrapped_and_retried(monkeypatch):
    n = []

    def fake(req, timeout):
        n.append(1)
        raise urllib.error.URLError(f"cannot reach {req.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(AlertSendError) as e:
        TelegramSender("SECRET-TOKEN", "42").send("x")
    assert len(n) == 2 and "SECRET-TOKEN" not in str(e.value)


def test_recent_chats(monkeypatch):
    body = {"result": [{"message": {"chat": {"id": 7, "first_name": "An"}}}, {"message": {"chat": {"id": 7, "first_name": "An"}}}, {"other": 1}]}
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: _Resp(json.dumps(body).encode()))
    assert TelegramSender("T", "").recent_chats() == [(7, "An")]


def test_load_env_file(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# ghi chú\nTELEGRAM_BOT_TOKEN='abc'\nTELEGRAM_CHAT_ID=42\nWYCKOFF_KEEP=moi\nBAD\n", encoding="utf-8")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("WYCKOFF_KEEP", "cu")
    load_env_file(f)
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "abc" and os.environ["TELEGRAM_CHAT_ID"] == "42" and os.environ["WYCKOFF_KEEP"] == "cu"
    load_env_file(tmp_path / "khong-co")   # không có file: bỏ qua
