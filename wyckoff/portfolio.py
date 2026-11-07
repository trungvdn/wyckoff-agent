"""Danh mục nắm giữ: lưu cục bộ bằng SQLite, tính lãi/lỗ, mức giá gần nhất, thay đổi so với phiên trước.

Dữ liệu là thông tin riêng: file nằm trong thư mục đã đưa vào .gitignore, không gửi cho LLM.
Giá tính bằng nghìn đồng như phần còn lại của hệ thống; giá trị tiền tính bằng đồng.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

PRICE_UNIT_VND = 1000


class DuplicateHolding(ValueError):
    """Mã đã có trong danh mục."""


@dataclass(frozen=True)
class Holding:
    symbol: str
    quantity: int
    cost: float        # giá vốn trung bình, nghìn đồng
    bought_on: str     # YYYY-MM-DD


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
        return conn

    def list(self) -> list[Holding]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT symbol, quantity, cost, bought_on FROM holdings ORDER BY symbol").fetchall()
        return [Holding(*r) for r in rows]

    def add(self, h: Holding) -> None:
        with closing(self._connect()) as conn, conn:
            try:
                conn.execute("INSERT INTO holdings VALUES (?, ?, ?, ?)", (h.symbol, h.quantity, h.cost, h.bought_on))
            except sqlite3.IntegrityError as exc:
                raise DuplicateHolding(h.symbol) from exc

    def update(self, h: Holding) -> bool:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("UPDATE holdings SET quantity = ?, cost = ?, bought_on = ? WHERE symbol = ?",
                               (h.quantity, h.cost, h.bought_on, h.symbol))
            return cur.rowcount > 0

    def delete(self, symbol: str) -> bool:
        with closing(self._connect()) as conn, conn:
            return conn.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,)).rowcount > 0


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


def holding_row(h: Holding, view: dict[str, Any], prev_view: dict[str, Any] | None) -> dict[str, Any]:
    """Một dòng của bảng danh mục từ view model phân tích của mã đó."""
    bars = view["bars"]
    price = bars[-1]["c"]
    prev_close = bars[-2]["c"] if len(bars) > 1 else price
    cost_value = h.quantity * h.cost * PRICE_UNIT_VND
    value = h.quantity * price * PRICE_UNIT_VND
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
        "error": None,
    }


def error_row(h: Holding, message: str) -> dict[str, Any]:
    """Mã không tải được dữ liệu: vẫn hiện để sửa hoặc xóa, không tính vào tổng."""
    return {**asdict(h), "cost_value": round(h.quantity * h.cost * PRICE_UNIT_VND), "changes": None, "error": message}


def portfolio_view(rows: list[dict[str, Any]], notices: list[str] | None = None) -> dict[str, Any]:
    """Tổng hợp danh mục. Mã có thay đổi xếp trước, sau đó theo giá trị giảm dần."""
    ok = [r for r in rows if r["error"] is None]
    value = sum(r["value"] for r in ok)
    cost = sum(r["cost_value"] for r in ok)
    day = sum(r["day_value"] for r in ok)
    prev_value = value - day
    latest = max((r["as_of"] for r in ok), default=None)
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
        },
        "rows": sorted(rows, key=lambda r: (r["error"] is None, bool(r["changes"]), r.get("value", 0)), reverse=True),
        "notices": list(notices or []),
        "warnings": warnings,
    }
