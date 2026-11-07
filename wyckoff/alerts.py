"""Cảnh báo sau phiên: so trạng thái danh mục với lần báo trước, chỉ báo khi có thay đổi.

Nội dung chỉ mô tả theo quy tắc người dùng đặt, không khuyến nghị. Tin nhắn không chứa số lượng, giá vốn hay
số tiền vì danh mục là thông tin riêng; ngưỡng giá vẫn có vì đó là phần người dùng cần đối chiếu.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from wyckoff.fmt import vn_num
from wyckoff.portfolio import PortfolioStore

TELEGRAM_LIMIT = 4000   # Telegram giới hạn 4096 ký tự mỗi tin
DISCLAIMER = "ℹ️ Chỉ mô tả theo quy tắc bạn đặt, không phải khuyến nghị."
NOTHING_NOW = "Hiện chưa có mã nào đủ điều kiện chốt hoặc gần đạt."
SIDE_NAME = {"profit": "chốt lãi", "loss": "chốt lỗ"}
SIDE_ICON = {"profit": "🟢", "loss": "🔴"}


class AlertSendError(RuntimeError):
    """Không gửi được tin nhắn. Nội dung lỗi không chứa token."""


# ------------------------------------------------------------------ so sánh trạng thái

def row_state(row: dict[str, Any]) -> dict[str, Any]:
    """Những gì cần nhớ của một mã để lần sau biết có đổi hay không."""
    return {"profit_ready": row["exit"]["profit"]["ready"], "loss_ready": row["exit"]["loss"]["ready"],
            "profit_near": row["exit"]["profit"]["near"], "loss_near": row["exit"]["loss"]["near"],
            "stage": row["stage"], "phase": row["phase"]}


def _pct(x: float) -> str:
    return f"{'+' if x > 0 else ''}{vn_num(x)}%"


def _rule_detail(r: dict[str, Any]) -> str:
    if r["now_type"] == "text":
        return r["label"]
    if r["now_type"] == "pct":
        return f"{r['label']}: {_pct(r['now'])} (ngưỡng {vn_num(r['threshold'])})"
    return f"{r['label']}: {vn_num(r['now'])} (ngưỡng {vn_num(r['threshold'])})"


def _near_detail(r: dict[str, Any]) -> str:
    if r["now_type"] == "text":
        return f"{r['label']}, đang {r['now']}"
    return f"{r['label']}, giá còn cách {_pct(r['gap_pct'])}"


def _ready_rules(row: dict[str, Any], side: str) -> list[dict[str, Any]]:
    """Các quy tắc làm nhóm đủ điều kiện: quy tắc "đạt là đủ" đã đạt, hoặc toàn bộ quy tắc của nhóm."""
    items = [r for r in row["rules"] if r["side"] == side and r["met"]]
    return [r for r in items if r["sufficient"]] if row["exit"][side]["by_sufficient"] else items


@dataclass
class Sections:
    """Nội dung tin nhắn, theo thứ tự cần chú ý."""
    ready_loss: list[str]
    ready_profit: list[str]
    near: list[str]
    changes: list[str]

    def any(self) -> bool:
        return bool(self.ready_loss or self.ready_profit or self.near or self.changes)


def build_sections(rows: list[dict[str, Any]], previous: dict[str, dict[str, Any]], include_near: bool = True) -> Sections:
    """Chỉ lấy những gì mới so với lần trước. Mã chưa từng theo dõi: báo trạng thái hiện tại, không báo đổi giai đoạn."""
    out = Sections([], [], [], [])
    for row in rows:
        sym = row["symbol"]
        now, prev = row_state(row), previous.get(sym, {})
        for side, bucket in (("loss", out.ready_loss), ("profit", out.ready_profit)):
            if now[f"{side}_ready"] and not prev.get(f"{side}_ready"):
                bucket.extend(f"{sym}  {_rule_detail(r)}" for r in _ready_rules(row, side))
            if include_near and now[f"{side}_near"] and not prev.get(f"{side}_near"):
                out.near.extend(f"{SIDE_ICON[side]} {sym}  Gần {SIDE_NAME[side]}: {_near_detail(r)}"
                                for r in row["rules"] if r["side"] == side and r["near"])
        for key in ("stage", "phase"):
            if prev.get(key) and prev[key] != now[key]:
                out.changes.append(f"{sym}  {prev[key]} → {now[key]}")
    return out


def _session(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "chưa có dữ liệu"


def format_message(as_of: str | None, sections: Sections, problems: list[str], intro: str | None = None) -> str:
    parts = [f"🤖 Wyckoff Agent · phiên {_session(as_of)}"]
    if intro:
        parts.append(intro)
    for title, lines in (("🔴 ĐỦ ĐIỀU KIỆN CHỐT LỖ", sections.ready_loss), ("🟢 ĐỦ ĐIỀU KIỆN CHỐT LÃI", sections.ready_profit),
                         ("⚠️ GẦN ĐẠT", sections.near), ("🔄 ĐỔI GIAI ĐOẠN, PHA", sections.changes),
                         ("❗ CẦN KIỂM TRA", problems)):
        if lines:
            parts.append("\n".join([title, *lines]))
    parts.append(DISCLAIMER)
    return "\n\n".join(parts)


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Chia theo dòng để không cắt giữa một quy tắc."""
    chunks, current = [], ""
    for line in text.split("\n"):
        line = line[:limit]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    return [*chunks, current] if current else chunks


def enabled_rows(view: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in view["rows"] if r.get("alerts_enabled", True)]


def current_summary(view: dict[str, Any], include_near: bool = True) -> dict[str, Any]:
    """Tình trạng hiện tại để gửi tay: liệt kê mọi mã đang đủ điều kiện hoặc gần đạt, không so với lần trước
    và không đổi trạng thái đã lưu, nên lịch tự động vẫn báo thay đổi như bình thường."""
    rows = enabled_rows(view)
    ok = [r for r in rows if r["error"] is None]
    sections = build_sections(ok, {}, include_near)
    problems = [f"{r['symbol']}: {r['error']}" for r in rows if r["error"]]
    as_of = max((r["as_of"] for r in ok), default=None)
    intro = f"Tình trạng hiện tại của {len(rows)} mã đang bật thông báo." + ("" if sections.any() else f" {NOTHING_NOW}")
    return {"text": format_message(as_of, sections, problems, intro), "as_of": as_of, "enabled_count": len(rows),
            "muted_count": len(view["rows"]) - len(rows), "muted": [r["symbol"] for r in view["rows"] if not r.get("alerts_enabled", True)]}


# ------------------------------------------------------------------ chạy một lượt

@dataclass
class AlertResult:
    status: str          # sent, quiet, no_holdings, dry_run
    text: str | None = None


def run_alerts(view: dict[str, Any], store: PortfolioStore, send: Callable[[str], None] | None, *, include_near: bool = True,
               dry_run: bool = False, extra_problems: list[str] | None = None) -> AlertResult:
    """So danh mục với trạng thái đã lưu, gửi nếu có gì mới, rồi mới lưu trạng thái.

    Gửi lỗi thì không lưu, để lần chạy sau báo lại. Không có phiên mới (ngày nghỉ, chạy lại trong ngày) thì
    không xét thay đổi, chỉ báo lỗi dữ liệu nếu có.
    """
    if not view["rows"]:
        return AlertResult("no_holdings")
    rows = enabled_rows(view)
    saved = store.alert_states()
    ok = [r for r in rows if r["error"] is None]
    latest = max((r["as_of"] for r in ok), default=None)
    last = max((as_of for _, as_of in saved.values()), default=None)
    new_session = latest is not None and (last is None or latest > last)
    first_run = not saved and new_session and bool(rows)

    previous = {s: state for s, (state, _) in saved.items()}
    sections = build_sections(ok, previous, include_near) if new_session else Sections([], [], [], [])
    problems = [*(extra_problems or []), *(f"{r['symbol']}: {r['error']}" for r in rows if r["error"])]
    if new_session:
        problems += [f"{r['symbol']}: dữ liệu chỉ đến {_session(r['as_of'])}" for r in ok if r["as_of"] != latest]

    text = None
    if sections.any() or problems or first_run:
        intro = f"Bắt đầu theo dõi {len(rows)} mã." + ("" if sections.any() else f" {NOTHING_NOW}") if first_run else None
        text = format_message(latest, sections, problems, intro)
    if dry_run:
        return AlertResult("dry_run", text)

    if text:
        if send is None:
            raise AlertSendError("Chưa cấu hình nơi gửi")
        for chunk in split_message(text):
            send(chunk)
        store.log_alert(latest, text)
    held = {r["symbol"] for r in rows}
    if new_session:
        # Mã lỗi giữ trạng thái cũ để lần sau vẫn so được; mã đã bán hoặc đã tắt thì bỏ,
        # nên bật lại sẽ được coi như mã mới và báo trạng thái lúc đó
        states = {s: v for s, v in saved.items() if s in held}
        states.update({r["symbol"]: (row_state(r), r["as_of"]) for r in ok})
        store.save_alert_states(states)
    elif set(saved) - held:
        store.save_alert_states({s: v for s, v in saved.items() if s in held})
    return AlertResult("sent" if text else "quiet", text)


# ------------------------------------------------------------------ Telegram

class TelegramSender:
    def __init__(self, token: str, chat_id: str, timeout: float = 20, retries: int = 2) -> None:
        self.token, self.chat_id, self.timeout, self.retries = token, chat_id, timeout, retries

    def _call(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/{method}",
                                     data=json.dumps(payload or {}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:   # chỉ lấy mô tả của Telegram; URL chứa token nên không đưa vào lỗi
            try:
                detail = json.loads(exc.read()).get("description", "")
            except ValueError:
                detail = ""
            raise AlertSendError(f"Telegram báo lỗi {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise AlertSendError(f"Không kết nối được Telegram: {type(exc).__name__}") from None

    def send(self, text: str) -> None:
        for attempt in range(self.retries):
            try:
                self._call("sendMessage", {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True})
                return
            except AlertSendError:
                if attempt == self.retries - 1:
                    raise
                time.sleep(3)

    def recent_chats(self) -> list[tuple[int, str]]:
        """Các cuộc trò chuyện vừa nhắn cho bot, để lấy chat ID lúc thiết lập."""
        updates = self._call("getUpdates").get("result", [])
        chats = {}
        for u in updates:
            chat = (u.get("message") or u.get("edited_message") or {}).get("chat")
            if chat:
                chats[chat["id"]] = chat.get("title") or chat.get("first_name") or chat.get("username") or ""
        return list(chats.items())


def read_env_file(path: str | Path) -> dict[str, str]:
    """Các cặp KEY=VALUE trong file .env. Không có file thì trả về rỗng."""
    p = Path(path)
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip("'\"")
    return out


def load_env_file(path: str | Path) -> None:
    """Nạp .env cho những biến chưa có sẵn."""
    for key, value in read_env_file(path).items():
        os.environ.setdefault(key, value)


def telegram_from_env(env_file: str | Path = Path(__file__).resolve().parents[1] / ".env") -> TelegramSender | None:
    """Đọc .env mỗi lần gọi để sửa file xong không phải khởi động lại API. Biến môi trường được ưu tiên."""
    values = {**read_env_file(env_file), **os.environ}
    token, chat_id = values.get("TELEGRAM_BOT_TOKEN", ""), values.get("TELEGRAM_CHAT_ID", "")
    return TelegramSender(token, chat_id) if token and chat_id else None
