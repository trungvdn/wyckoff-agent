"""Danh mục nắm giữ: lưu cục bộ bằng SQLite, tính lãi/lỗ, mức giá gần nhất, thay đổi so với phiên trước.

Dữ liệu là thông tin riêng: file nằm trong thư mục đã đưa vào .gitignore, không gửi cho LLM.
Giá tính bằng nghìn đồng như phần còn lại của hệ thống; giá trị tiền tính bằng đồng.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from wyckoff.fmt import vn_g, vn_num

PRICE_UNIT_VND = 1000
NEAR_RULE_PCT = 2.0   # giá còn cách ngưỡng không quá chừng này (%) thì báo "gần đạt"


class DuplicateHolding(ValueError):
    """Mã đã có trong danh mục."""


class DuplicateRule(ValueError):
    """Mã đã có quy tắc giống hệt."""


@dataclass(frozen=True)
class Holding:
    symbol: str
    quantity: int
    cost: float        # giá vốn trung bình, nghìn đồng
    bought_on: str     # YYYY-MM-DD
    alerts_enabled: bool = True   # tắt thì job và nút gửi thông báo bỏ qua mã này


@dataclass(frozen=True)
class Rule:
    id: int
    symbol: str
    kind: str
    # % với quy tắc theo giá vốn; nghìn đồng với mức giá tự nhập; với đường trung bình là % so với đường, 0 hoặc âm
    value: float | None = None
    side: str = "loss"           # "profit": chốt lãi; "loss": chốt lỗ
    sufficient: bool = False     # "đạt là đủ": chỉ cần quy tắc này đạt là cả nhóm đủ điều kiện chốt


class PortfolioStore:
    """Mỗi mã một dòng. Mở kết nối theo từng thao tác nên dùng được từ nhiều luồng của web server."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("""CREATE TABLE IF NOT EXISTS holdings (
            symbol TEXT PRIMARY KEY,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            cost REAL NOT NULL CHECK (cost > 0),
            bought_on TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            kind TEXT NOT NULL,
            value REAL)""")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS rules_unique ON rules (symbol, kind, COALESCE(value, -1))")
        conn.execute("""CREATE TABLE IF NOT EXISTS alert_state (
            symbol TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            as_of TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY,
            sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            as_of TEXT,
            message TEXT NOT NULL)""")
        if "alerts_enabled" not in {c[1] for c in conn.execute("PRAGMA table_info(holdings)")}:   # dữ liệu cũ: mặc định bật
            conn.execute("ALTER TABLE holdings ADD COLUMN alerts_enabled INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        columns = {c[1] for c in conn.execute("PRAGMA table_info(rules)")}
        if "sufficient" not in columns:   # dữ liệu tạo trước khi có "đạt là đủ"
            conn.execute("ALTER TABLE rules ADD COLUMN sufficient INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if "side" not in columns:   # dữ liệu tạo trước khi có chốt lãi / chốt lỗ
            conn.execute("ALTER TABLE rules ADD COLUMN side TEXT NOT NULL DEFAULT 'loss'")
            conn.execute("UPDATE rules SET side = 'profit' WHERE kind = 'profit_pct'")
            conn.commit()
        return conn

    def list(self) -> list[Holding]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT symbol, quantity, cost, bought_on, alerts_enabled FROM holdings ORDER BY symbol").fetchall()
        return [Holding(*r[:4], bool(r[4])) for r in rows]

    def add(self, h: Holding) -> None:
        with closing(self._connect()) as conn, conn:
            try:
                conn.execute("INSERT INTO holdings (symbol, quantity, cost, bought_on, alerts_enabled) VALUES (?, ?, ?, ?, ?)",
                             (h.symbol, h.quantity, h.cost, h.bought_on, int(h.alerts_enabled)))
            except sqlite3.IntegrityError as exc:
                raise DuplicateHolding(h.symbol) from exc

    def update(self, h: Holding) -> bool:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("UPDATE holdings SET quantity = ?, cost = ?, bought_on = ? WHERE symbol = ?",
                               (h.quantity, h.cost, h.bought_on, h.symbol))
            return cur.rowcount > 0

    def set_alerts(self, symbol: str, enabled: bool) -> bool:
        with closing(self._connect()) as conn, conn:
            return conn.execute("UPDATE holdings SET alerts_enabled = ? WHERE symbol = ?", (int(enabled), symbol)).rowcount > 0

    def delete(self, symbol: str) -> bool:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM rules WHERE symbol = ?", (symbol,))
            return conn.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,)).rowcount > 0

    def rules(self) -> dict[str, list[Rule]]:
        """Mọi quy tắc, gom theo mã."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT id, symbol, kind, value, side, sufficient FROM rules ORDER BY id").fetchall()
        out: dict[str, list[Rule]] = {}
        for r in rows:
            out.setdefault(r[1], []).append(Rule(*r[:5], bool(r[5])))
        return out

    def rule(self, rule_id: int) -> Rule | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT id, symbol, kind, value, side, sufficient FROM rules WHERE id = ?", (rule_id,)).fetchone()
        return Rule(*row[:5], bool(row[5])) if row else None

    def add_rule(self, symbol: str, kind: str, value: float | None, side: str = "loss", sufficient: bool = False) -> Rule:
        with closing(self._connect()) as conn, conn:
            try:
                cur = conn.execute("INSERT INTO rules (symbol, kind, value, side, sufficient) VALUES (?, ?, ?, ?, ?)",
                                   (symbol, kind, value, side, int(sufficient)))
            except sqlite3.IntegrityError as exc:
                raise DuplicateRule(symbol) from exc
            return Rule(int(cur.lastrowid), symbol, kind, value, side, sufficient)

    def update_rule(self, rule_id: int, kind: str, value: float | None, side: str = "loss", sufficient: bool = False) -> bool:
        with closing(self._connect()) as conn, conn:
            try:
                return conn.execute("UPDATE rules SET kind = ?, value = ?, side = ?, sufficient = ? WHERE id = ?",
                                    (kind, value, side, int(sufficient), rule_id)).rowcount > 0
            except sqlite3.IntegrityError as exc:
                raise DuplicateRule(str(rule_id)) from exc

    def delete_rule(self, rule_id: int) -> bool:
        with closing(self._connect()) as conn, conn:
            return conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,)).rowcount > 0

    def alert_states(self) -> dict[str, tuple[dict[str, Any], str]]:
        """Trạng thái lần cảnh báo trước của từng mã: (trạng thái, phiên)."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT symbol, state, as_of FROM alert_state").fetchall()
        return {sym: (json.loads(state), as_of) for sym, state, as_of in rows}

    def save_alert_states(self, states: dict[str, tuple[dict[str, Any], str]]) -> None:
        """Thay toàn bộ trạng thái; mã đã bán không còn trong `states` thì bị xóa."""
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM alert_state")
            conn.executemany("INSERT INTO alert_state VALUES (?, ?, ?)",
                             [(sym, json.dumps(state, ensure_ascii=False), as_of) for sym, (state, as_of) in states.items()])

    def log_alert(self, as_of: str | None, message: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("INSERT INTO alert_log (as_of, message) VALUES (?, ?)", (as_of, message))

    def alert_log(self) -> list[tuple[str | None, str]]:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT as_of, message FROM alert_log ORDER BY id").fetchall()


def _level_ref(kind: str, price: float, close: float) -> dict[str, Any]:
    return {"kind": kind, "price": price, "pct": round((price / close - 1) * 100, 2),
            # Mọi mức vô hiệu của hệ thống đều có dạng "đóng cửa dưới X"
            "breached": kind == "invalidate" and close < price}


def _named_levels(view: dict[str, Any]) -> list[tuple[str, float]]:
    return [(lv["type"], lv["price"]) for lv in view["levels"]
            if lv.get("price") is not None and lv["type"] in ("confirm", "invalidate")
            # Thủng đáy SC chỉ làm vùng climax kéo dài, hệ thống không coi là vô hiệu
            and "không phải vô hiệu" not in (lv.get("label") or "")]


def _range_levels(view: dict[str, Any]) -> list[tuple[str, float]]:
    p = view["phase"]
    return [(k, p[k]) for k in ("support", "resistance") if p.get(k) is not None]


def nearest_levels(view: dict[str, Any], close: float) -> dict[str, dict[str, Any] | None]:
    """Mức gần nhất ở dưới và ở trên giá. Ưu tiên mức xác nhận / vô hiệu; không có thì dùng hỗ trợ / kháng cự."""
    out: dict[str, dict[str, Any] | None] = {}
    for side, is_side, pick in (("below", lambda p: p < close, max), ("above", lambda p: p > close, min)):
        chosen = None
        for group in (_named_levels(view), _range_levels(view)):
            matches = [lv for lv in group if is_side(lv[1])]
            if matches:
                chosen = pick(matches, key=lambda lv: lv[1])
                break
        out[side] = _level_ref(chosen[0], chosen[1], close) if chosen else None
    return out


def session_changes(now: dict[str, Any], prev: dict[str, Any], close: float, prev_close: float) -> list[dict[str, Any]]:
    """Những gì khác so với phiên trước: giai đoạn, pha, và các mức giá mà giá đóng cửa vừa cắt qua."""
    out: list[dict[str, Any]] = []
    if now["stage"]["title"] != prev["stage"]["title"]:
        out.append({"kind": "stage", "from": prev["stage"]["title"], "to": now["stage"]["title"]})
    if now["phase"]["title"] != prev["phase"]["title"]:
        out.append({"kind": "phase", "from": prev["phase"]["title"], "to": now["phase"]["title"]})
    seen: set[float] = set()
    for kind, price in _named_levels(now) + _range_levels(now):   # cùng một giá thì giữ tên cụ thể hơn
        if price in seen:
            continue
        seen.add(price)
        if prev_close >= price > close or prev_close <= price < close:
            out.append({"kind": "level", "level": kind, "price": price, "direction": "below" if close < price else "above",
                        "close": close, "prev_close": prev_close})
    return out


# ------------------------------------------------------------------ quy tắc bán
# Hệ thống chỉ báo đạt hay chưa kèm con số; quyết định bán thuộc về người dùng.

COST_KINDS = {"loss_pct", "profit_pct"}
VALUE_KINDS = COST_KINDS | {"close_below"}
MA_KINDS = {"below_sma_fast": "sma_fast", "below_sma_slow": "sma_slow", "below_ema_fast": "ema_fast", "below_ema_slow": "ema_slow"}
STAGE_KINDS = {"stage_distribution": ("Distribution", "distribution"), "stage_markdown": ("Markdown", "down")}
RULE_KINDS = VALUE_KINDS | set(MA_KINDS) | set(STAGE_KINDS) | {"below_invalidate"}
FIXED_SIDE = {"loss_pct": "loss", "profit_pct": "profit"}   # hai loại này tự nó đã là chốt lỗ, chốt lãi
RULE_SIDES = {"profit", "loss"}


def rule_catalog(sma_periods: tuple[int, int], ema_periods: tuple[int, int]) -> list[dict[str, Any]]:
    """Các loại quy tắc cho form: mỗi nhóm một danh sách, `value_label` khác None nghĩa là cần nhập số."""
    f, s = sma_periods
    ef, es = ema_periods
    offset = {"value_label": "Dưới đường bao nhiêu (%)", "default_value": 0, "value_hint": "0: chỉ cần đóng cửa dưới đường. -4: đóng cửa dưới đường 4%."}
    return [
        {"group": "Theo giá vốn", "kinds": [
            {"kind": "loss_pct", "label": "Lỗ quá (%)", "value_label": "Mức lỗ (%)", "fixed_side": "loss"},
            {"kind": "profit_pct", "label": "Lãi đạt (%)", "value_label": "Mức lãi (%)", "fixed_side": "profit"},
        ]},
        {"group": "Theo mức giá", "kinds": [
            {"kind": "close_below", "label": "Đóng cửa dưới mức giá tự nhập", "value_label": "Mức giá (nghìn đồng)"},
        ]},
        {"group": "Theo đường trung bình", "kinds": [
            {"kind": "below_sma_fast", "label": f"Đóng cửa dưới SMA{f}", "line": f"SMA{f}", **offset},
            {"kind": "below_sma_slow", "label": f"Đóng cửa dưới SMA{s}", "line": f"SMA{s}", **offset},
            {"kind": "below_ema_fast", "label": f"Đóng cửa dưới EMA{ef}", "line": f"EMA{ef}", **offset},
            {"kind": "below_ema_slow", "label": f"Đóng cửa dưới EMA{es}", "line": f"EMA{es}", **offset},
        ]},
        {"group": "Theo cấu trúc Wyckoff", "kinds": [
            {"kind": "below_invalidate", "label": "Đóng cửa dưới mức vô hiệu", "value_label": None},
            {"kind": "stage_distribution", "label": "Giai đoạn là Distribution", "value_label": None},
            {"kind": "stage_markdown", "label": "Giai đoạn là Markdown", "value_label": None},
        ]},
    ]


def validate_rule(kind: str, value: float | None) -> str | None:
    """Lỗi của cặp loại / giá trị, không có lỗi trả về None."""
    if kind not in RULE_KINDS:
        return f"Loại quy tắc không hợp lệ: {kind}."
    if kind in MA_KINDS:
        return None if value is None or -100 < value <= 0 else "Nhập 0 hoặc số âm, ví dụ -4 là đóng cửa dưới đường 4%."
    if kind in VALUE_KINDS and (value is None or value <= 0):
        return "Nhập một số lớn hơn 0."
    if kind not in VALUE_KINDS and value is not None:
        return "Loại quy tắc này không cần nhập số."
    if kind == "loss_pct" and value >= 100:
        return "Mức lỗ phải nhỏ hơn 100%."
    if kind == "profit_pct" and value > 10_000:
        return "Mức lãi quá lớn."
    if kind == "close_below" and value > 100_000:
        return "Mức giá quá lớn, tính bằng nghìn đồng."
    return None


def normalize_rule_value(kind: str, value: float | None) -> float | None:
    """Đường trung bình không nhập gì nghĩa là 0%, để hai cách gửi không thành hai quy tắc khác nhau."""
    return 0.0 if kind in MA_KINDS and value is None else value


def normalize_rule_side(kind: str, side: str | None) -> str:
    """Chốt lãi hay chốt lỗ. Loại theo lãi / lỗ so với giá vốn thì cố định; loại khác mặc định chốt lỗ."""
    return FIXED_SIDE.get(kind) or side or "loss"


def _rule_label(rule: Rule, catalog: list[dict[str, Any]]) -> str:
    if rule.kind == "loss_pct":
        return f"Lỗ quá {vn_g(rule.value)}%"
    if rule.kind == "profit_pct":
        return f"Lãi đạt {vn_g(rule.value)}%"
    if rule.kind == "close_below":
        return f"Đóng cửa dưới {vn_num(rule.value)}"
    label = next(k["label"] for g in catalog for k in g["kinds"] if k["kind"] == rule.kind)
    return f"{label} {vn_g(abs(rule.value))}%" if rule.kind in MA_KINDS and rule.value else label


def _streak(dates: list[str], flags: list[bool], bought_on: str) -> tuple[str, int] | None:
    """Phiên đầu của chuỗi đạt liên tục đến phiên cuối, chỉ tính từ ngày mua. Phiên cuối chưa đạt -> None."""
    if not flags[-1]:
        return None
    i = len(flags) - 1
    while i > 0 and flags[i - 1] and dates[i - 1] >= bought_on:
        i -= 1
    return dates[i], len(flags) - i


def _ma_series(view: dict[str, Any], name: str, sma_periods: tuple[int, int]) -> list[float | None]:
    bars = view["bars"]
    if name.startswith("ema"):
        return [b[name] for b in bars]
    n = sma_periods[0 if name == "sma_fast" else 1]
    sma = pd.Series([b["c"] for b in bars], dtype=float).rolling(n, min_periods=n).mean()
    return [None if pd.isna(x) else float(x) for x in sma]


def _stage_kind(view: dict[str, Any]) -> str | None:
    segments = view.get("stage_segments") or []
    return segments[-1]["kind"] if segments else None


def evaluate_rule(rule: Rule, h: Holding, view: dict[str, Any], prev_view: dict[str, Any] | None,
                  catalog: list[dict[str, Any]], sma_periods: tuple[int, int] = (50, 200)) -> dict[str, Any]:
    """Trạng thái của một quy tắc tại phiên cuối. Chỉ tính theo giá đóng cửa."""
    bars = view["bars"]
    dates = [b["t"] for b in bars]
    closes = [b["c"] for b in bars]
    close = closes[-1]
    out: dict[str, Any] = {**asdict(rule), "label": _rule_label(rule, catalog), "now": close, "now_type": "price",
                           "threshold": None, "threshold_text": None, "reference": None, "met": False, "fresh": False,
                           "near": False, "since": None, "sessions": None, "gap_pct": None, "note": None, "error": None}

    if rule.kind in STAGE_KINDS:
        name, seg_kind = STAGE_KINDS[rule.kind]
        out.update(now=view["stage"]["title"], now_type="text", threshold_text=name)
        if _stage_kind(view) == seg_kind:   # "tiềm năng" và "đang hình thành" chưa tính là đạt
            first = view["stage_segments"][-1]["i0"]
            since = max(dates[first], h.bought_on) if h.bought_on <= dates[-1] else dates[-1]
            out.update(met=True, since=since, sessions=sum(d >= since for d in dates),
                       fresh=prev_view is not None and _stage_kind(prev_view) != seg_kind)
        else:   # giai đoạn đang hình thành hoặc còn tiềm năng là bước ngay trước khi đạt
            out["near"] = _stage_kind(view) in (f"{seg_kind}_potential", f"{seg_kind}_developing")
        return out

    if rule.kind in COST_KINDS:
        factor = 1 - rule.value / 100 if rule.kind == "loss_pct" else 1 + rule.value / 100
        threshold = h.cost * factor
        flags = [c <= threshold if rule.kind == "loss_pct" else c >= threshold for c in closes]
        out.update(now=round((close / h.cost - 1) * 100, 2), now_type="pct")
    elif rule.kind == "close_below":
        threshold = rule.value
        flags = [c < threshold for c in closes]
    elif rule.kind == "below_invalidate":
        levels = [p for kind, p in _named_levels(view) if kind == "invalidate"]
        if not levels:
            out["note"] = "Cấu trúc hiện tại chưa có mức vô hiệu"
            return out
        # Mức của phiên cuối; "đạt từ" tính theo mức này vì không lưu lại mức của các phiên trước
        threshold = max(levels)
        flags = [c < threshold for c in closes]
    else:
        ma = _ma_series(view, MA_KINDS[rule.kind], sma_periods)
        if ma[-1] is None:
            out["note"] = "Chưa đủ dữ liệu để tính đường trung bình"
            return out
        factor = 1 + (rule.value or 0) / 100   # -4 -> đóng cửa dưới đường 4%
        threshold = ma[-1] * factor
        out["reference"] = round(ma[-1], 2)
        flags = [m is not None and c < m * factor for c, m in zip(closes, ma)]

    out["threshold"] = round(threshold, 2)
    streak = _streak(dates, flags, h.bought_on)
    if streak:
        out.update(met=True, since=streak[0], sessions=streak[1], fresh=streak[1] == 1)
    else:
        out["gap_pct"] = round((threshold / close - 1) * 100, 2)
        out["near"] = abs(out["gap_pct"]) <= NEAR_RULE_PCT   # so số đã làm tròn để khớp với con số hiển thị
    return out


def _rule_order(r: dict[str, Any]) -> tuple[int, float]:
    """Vừa đạt, đã đạt, gần đạt, rồi chưa đạt theo độ gần ngưỡng; không tính được khoảng cách thì xếp cuối."""
    if r["met"]:
        return (0 if r["fresh"] else 1, 0.0)
    gap = abs(r["gap_pct"]) if r["gap_pct"] is not None else 0.0
    if r["near"]:
        return (2, gap)
    return (3, gap) if r["gap_pct"] is not None else (4, 0.0)


def _exit_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Một nhóm quy tắc. `ready`: đạt toàn bộ, hoặc có một quy tắc "đạt là đủ" đã đạt.
    `near`: chưa đủ, nhưng mọi quy tắc còn lại đều gần đạt, hoặc có một quy tắc "đạt là đủ" gần đạt."""
    met = sum(x["met"] for x in items)
    sufficient_met = [x for x in items if x["sufficient"] and x["met"]]
    all_met = bool(items) and met == len(items)
    ready = all_met or bool(sufficient_met)
    # Đủ nhờ "đạt là đủ" thì chỉ tính vừa đủ khi chưa có quy tắc đó nào đạt từ trước
    fresh = all(x["fresh"] for x in sufficient_met) if sufficient_met else any(x["fresh"] for x in items)
    near = not ready and bool(items) and (all(x["met"] or x["near"] for x in items) or any(x["sufficient"] and x["near"] for x in items))
    return {"total": len(items), "met": met, "ready": ready, "fresh": ready and fresh, "near": near,
            "by_sufficient": bool(sufficient_met), "has_sufficient": any(x["sufficient"] for x in items)}


def exit_status(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Trạng thái chốt của một mã. `attention`: mức cần chú ý nhất, đủ điều kiện chốt lỗ trước chốt lãi, rồi gần đạt."""
    groups = {side: _exit_group([x for x in items if x["side"] == side]) for side in ("profit", "loss")}
    attention = ("loss" if groups["loss"]["ready"] else "profit" if groups["profit"]["ready"]
                 else "near" if groups["loss"]["near"] or groups["profit"]["near"] else None)
    return {"exit": groups, "attention": attention}


def _attention_rank(row: dict[str, Any]) -> int:
    """Vừa đủ điều kiện chốt, đã đủ, gần đạt, còn lại."""
    groups = row["exit"].values()
    if any(g["fresh"] for g in groups):
        return 3
    return {"loss": 2, "profit": 2, "near": 1}.get(row["attention"], 0)


def holding_row(h: Holding, view: dict[str, Any], prev_view: dict[str, Any] | None, rules: Iterable[Rule] = (),
                catalog: list[dict[str, Any]] | None = None, sma_periods: tuple[int, int] = (50, 200)) -> dict[str, Any]:
    """Một dòng của bảng danh mục từ view model phân tích của mã đó."""
    bars = view["bars"]
    price = bars[-1]["c"]
    prev_close = bars[-2]["c"] if len(bars) > 1 else price
    cost_value = h.quantity * h.cost * PRICE_UNIT_VND
    value = h.quantity * price * PRICE_UNIT_VND
    items = sorted((evaluate_rule(r, h, view, prev_view, catalog or [], sma_periods) for r in rules), key=_rule_order)
    return {
        **asdict(h),
        "as_of": view["as_of"],
        "price": price,
        "prev_close": prev_close,
        "day_pct": round((price / prev_close - 1) * 100, 2),
        "day_value": round(h.quantity * (price - prev_close) * PRICE_UNIT_VND),
        "value": round(value),
        "cost_value": round(cost_value),
        "pl": round(value - cost_value),
        "pl_pct": round((price / h.cost - 1) * 100, 2),
        "stage": view["stage"]["title"],
        "phase": view["phase"]["title"],
        **nearest_levels(view, price),
        "changes": session_changes(view, prev_view, price, prev_close) if prev_view is not None else None,
        "rules": items,
        **exit_status(items),
        "error": None,
    }


def error_row(h: Holding, message: str, rules: Iterable[Rule] = (), catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Mã không tải được dữ liệu: vẫn hiện để sửa hoặc xóa, không tính vào tổng."""
    items = [{**asdict(r), "label": _rule_label(r, catalog or []), "now": None, "now_type": "price", "threshold": None,
              "threshold_text": None, "reference": None, "met": False, "fresh": False, "near": False, "since": None, "sessions": None, "gap_pct": None,
              "note": "Không tải được dữ liệu của mã", "error": message} for r in rules]
    return {**asdict(h), "cost_value": round(h.quantity * h.cost * PRICE_UNIT_VND), "changes": None, "rules": items, **exit_status(items), "error": message}


def portfolio_view(rows: list[dict[str, Any]], notices: list[str] | None = None,
                   catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Tổng hợp danh mục. Mã vừa đủ điều kiện chốt, đã đủ, gần đạt xếp trước, sau đó theo giá trị giảm dần; mã lỗi cuối cùng."""
    ok = [r for r in rows if r["error"] is None]
    value = sum(r["value"] for r in ok)
    cost = sum(r["cost_value"] for r in ok)
    day = sum(r["day_value"] for r in ok)
    prev_value = value - day
    latest = max((r["as_of"] for r in ok), default=None)
    all_rules = [x for r in rows for x in r["rules"]]
    warnings = [f"{r['symbol']}: {r['error']}" for r in rows if r["error"]]
    warnings += [f"{r['symbol']}: dữ liệu chỉ đến {date.fromisoformat(r['as_of']):%d/%m/%Y}" for r in ok if r["as_of"] != latest]
    return {
        "as_of": latest,
        "summary": {
            "count": len(rows),
            "value": value,
            "cost": cost,
            "pl": value - cost,
            "pl_pct": round((value / cost - 1) * 100, 2) if cost else None,
            "day": day,
            "day_pct": round((value / prev_value - 1) * 100, 2) if prev_value else None,
            "rules_total": len(all_rules),
            "rules_met": sum(x["met"] for x in all_rules),
            "rules_fresh": sum(x["fresh"] for x in all_rules),
            "symbols_with_rules": sum(bool(r["rules"]) for r in rows),
            "symbols_profit": sum(r["exit"]["profit"]["ready"] for r in rows),
            "symbols_loss": sum(r["exit"]["loss"]["ready"] for r in rows),
            "symbols_near": sum(r["attention"] == "near" for r in rows),
        },
        "near_pct": NEAR_RULE_PCT,
        "rows": sorted(rows, key=lambda r: (r["error"] is None, _attention_rank(r), r.get("value", 0)), reverse=True),
        "rule_catalog": catalog or [],
        "notices": list(notices or []),
        "warnings": warnings,
    }
