"""Quét thị trường cho trang lọc cổ phiếu: mỗi mã một dòng số liệu mô tả trạng thái tại phiên cuối.

Kết quả lưu trong SQLite cục bộ (data/scanner.db) theo từng phiên để giữ lịch sử; việc lọc làm ở giao diện.
Đây là mô tả trạng thái theo engine, không xếp hạng và không phải khuyến nghị (bộ phát hiện range chưa
vượt được kiểm định placebo, điều tra H8).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from wyckoff.portfolio import PRICE_UNIT_VND, _named_levels

logger = logging.getLogger(__name__)

STAGE_GROUPS = ("Accumulation", "Re-accumulation", "Markup", "Distribution", "Re-distribution", "Markdown")
STAGE_STATUSES = ("confirmed", "developing", "potential")
CONFIDENCE_RANK = {"thấp": 1, "trung bình": 2, "cao": 3}
EVENT_LOOKBACK = 60          # chỉ giữ sự kiện trong chừng này phiên gần nhất
VALUE_WINDOW = 20            # GTGD và KL trung bình 20 phiên
HIGH_WINDOW = 250            # đỉnh 52 tuần ≈ 250 phiên
RETURN_WINDOWS = (20, 60)
MAX_FILTERS = 50


def classify_stage(title: str) -> tuple[str, str | None]:
    """(nhóm giai đoạn, trạng thái) từ tên giai đoạn trên dashboard. Nhiều khả năng hoặc chưa rõ -> ("unclear", None)."""
    if " hoặc " in title:
        return "unclear", None
    base = title.replace("Initial ", "")
    # Thử tên dài trước để "Re-accumulation" không bị đọc thành "Accumulation"
    for group in sorted(STAGE_GROUPS, key=len, reverse=True):
        if base.startswith(group):
            rest = base[len(group):]
            status = "developing" if "đang hình thành" in rest else "potential" if "tiềm năng" in rest else "confirmed"
            return group, status
    return "unclear", None


def _pct(a: float | None, b: float | None, d: int = 2) -> float | None:
    if a is None or b is None or b == 0 or pd.isna(a) or pd.isna(b):
        return None
    return round(float(a / b - 1) * 100, d)


def _sessions_since(dates: list[str], day: str | None) -> int | None:
    """Số phiên từ `day` đến phiên cuối (0 = phiên cuối)."""
    if not day:
        return None
    pos = pd.Index(dates).searchsorted(day)
    return None if pos >= len(dates) else len(dates) - 1 - int(pos)


def scan_row(view: dict[str, Any], market: dict[str, Any] | None = None, sma_periods: tuple[int, int] = (50, 200)) -> dict[str, Any]:
    """Một dòng của bảng lọc từ view model phân tích (khung ngày). `market`: payload["market"] khi có."""
    bars = view["bars"]
    dates = [b["t"] for b in bars]
    closes = pd.Series([b["c"] for b in bars], dtype=float)
    vols = pd.Series([b["v"] for b in bars], dtype=float)
    close = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) > 1 else close
    recent = slice(-VALUE_WINDOW, None)
    value20 = float((closes.iloc[recent] * vols.iloc[recent]).mean()) * PRICE_UNIT_VND / 1e9

    stage = view["stage"]
    group, status = classify_stage(stage["title"])
    segments = view.get("stage_segments") or []
    phase = view["phase"]
    conf = (view.get("confidence") or {}).get("level")

    levels = _named_levels(view)
    confirm_above = [p for k, p in levels if k == "confirm" and p > close]
    invalidate = [p for k, p in levels if k == "invalidate"]
    inv = max(invalidate) if invalidate else None
    support, resistance = phase.get("support"), phase.get("resistance")
    range_pos = (round((close - support) / (resistance - support) * 100, 1)
                 if support is not None and resistance is not None and resistance > support else None)
    target = view.get("target")

    events = []
    for e in view.get("events") or []:
        ago = _sessions_since(dates, e["date"])
        if ago is not None and ago <= EVENT_LOOKBACK and e["status"] != "rejected":
            events.append({"kind": e["kind"], "date": e["date"], "status": e["status"], "ago": ago})
    events.sort(key=lambda e: e["ago"])

    sma = {n: closes.rolling(n, min_periods=n).mean().iloc[-1] for n in sma_periods}
    last = bars[-1]
    rs = (market or {}).get("rs") or {}
    return {
        "symbol": view["symbol"],
        "as_of": view["as_of"],
        "close": round(close, 2),
        "day_pct": _pct(close, prev),
        "value20": round(value20, 2),                       # tỷ đồng
        "vol20": int(vols.iloc[recent].mean()),
        "vol_ratio": last.get("vr"),
        "stage": stage["title"],
        "stage_group": group,
        "stage_status": status,
        "stage_age": len(bars) - 1 - segments[-1]["i0"] if segments else None,
        "phase": phase.get("phase"),
        "phase_title": phase["title"],
        "phase_since": phase.get("since"),
        "phase_age": _sessions_since(dates, phase.get("since")),
        "confidence": conf,
        "confidence_rank": CONFIDENCE_RANK.get(conf or "", 0),
        "events": events,
        "confirm_pct": _pct(min(confirm_above), close) if confirm_above else None,
        "invalidate_pct": _pct(inv, close),
        "invalidate_breached": inv is not None and close < inv,
        "range_pos": range_pos,
        "target_pct": _pct(target["conservative"], close) if target and not target.get("reached") else None,
        "sma_fast_pct": _pct(close, sma[sma_periods[0]]),
        "sma_slow_pct": _pct(close, sma[sma_periods[1]]),
        "ema_up": None if last.get("ema_fast") is None or last.get("ema_slow") is None else last["ema_fast"] > last["ema_slow"],
        **{f"ret{w}": _pct(close, float(closes.iloc[-1 - w])) if len(closes) > w else None for w in RETURN_WINDOWS},
        **{f"rs{w}": rs.get(f"rs_change_{w}d_pct") for w in RETURN_WINDOWS},
        "high52_pct": _pct(close, max(b["h"] for b in bars[-HIGH_WINDOW:])),
    }


# ------------------------------------------------------------------ lưu trữ

class DuplicateFilter(ValueError):
    """Đã có bộ lọc trùng tên."""


@dataclass(frozen=True)
class SavedFilter:
    id: int
    name: str
    filters: dict[str, Any]
    updated: str


class ScanStore:
    """Kết quả quét theo phiên và các bộ lọc người dùng lưu."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scans (
                as_of TEXT PRIMARY KEY, started TEXT NOT NULL, finished TEXT NOT NULL,
                universe INTEGER NOT NULL, failed TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_rows (
                as_of TEXT NOT NULL REFERENCES scans(as_of) ON DELETE CASCADE,
                symbol TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (as_of, symbol));
            CREATE TABLE IF NOT EXISTS filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, filters TEXT NOT NULL, updated TEXT NOT NULL);
        """)
        return conn

    def save_scan(self, rows: list[dict[str, Any]], failed: list[dict[str, str]], *, started: str, finished: str,
                  universe: int) -> str | None:
        """Lưu một lượt quét dưới phiên mới nhất trong các dòng. Quét lại cùng phiên thì thay lượt cũ. Không có dòng -> None."""
        if not rows:
            return None
        as_of = max(r["as_of"] for r in rows)
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM scans WHERE as_of = ?", (as_of,))
            conn.execute("INSERT INTO scans VALUES (?, ?, ?, ?, ?)",
                         (as_of, started, finished, universe, json.dumps(failed, ensure_ascii=False)))
            conn.executemany("INSERT INTO scan_rows VALUES (?, ?, ?)",
                             [(as_of, r["symbol"], json.dumps(r, ensure_ascii=False)) for r in rows])
        return as_of

    def sessions(self) -> list[str]:
        with closing(self._connect()) as conn:
            return [r[0] for r in conn.execute("SELECT as_of FROM scans ORDER BY as_of DESC")]

    def scan(self, as_of: str | None = None) -> dict[str, Any] | None:
        """Một lượt quét (mặc định lượt của phiên mới nhất)."""
        with closing(self._connect()) as conn:
            q = "SELECT as_of, started, finished, universe, failed FROM scans "
            meta = conn.execute(q + ("WHERE as_of = ?" if as_of else "ORDER BY as_of DESC LIMIT 1"),
                                (as_of,) if as_of else ()).fetchone()
            if meta is None:
                return None
            rows = [json.loads(d) for (d,) in conn.execute("SELECT data FROM scan_rows WHERE as_of = ? ORDER BY symbol", (meta[0],))]
        return {"as_of": meta[0], "started": meta[1], "finished": meta[2], "universe": meta[3],
                "failed": json.loads(meta[4]), "rows": rows}

    def filters(self) -> list[SavedFilter]:
        with closing(self._connect()) as conn:
            return [SavedFilter(i, n, json.loads(f), u) for i, n, f, u in
                    conn.execute("SELECT id, name, filters, updated FROM filters ORDER BY name COLLATE NOCASE")]

    def add_filter(self, name: str, filters: dict[str, Any]) -> SavedFilter:
        now = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn, conn:
            if conn.execute("SELECT COUNT(*) FROM filters").fetchone()[0] >= MAX_FILTERS:
                raise ValueError(f"Chỉ lưu được tối đa {MAX_FILTERS} bộ lọc")
            try:
                cur = conn.execute("INSERT INTO filters (name, filters, updated) VALUES (?, ?, ?)",
                                   (name, json.dumps(filters, ensure_ascii=False), now))
            except sqlite3.IntegrityError as exc:
                raise DuplicateFilter(f"Đã có bộ lọc tên “{name}”") from exc
        return SavedFilter(int(cur.lastrowid), name, filters, now)

    def update_filter(self, filter_id: int, name: str, filters: dict[str, Any]) -> SavedFilter | None:
        now = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn, conn:
            try:
                cur = conn.execute("UPDATE filters SET name = ?, filters = ?, updated = ? WHERE id = ?",
                                   (name, json.dumps(filters, ensure_ascii=False), now, filter_id))
            except sqlite3.IntegrityError as exc:
                raise DuplicateFilter(f"Đã có bộ lọc tên “{name}”") from exc
        return SavedFilter(filter_id, name, filters, now) if cur.rowcount else None

    def delete_filter(self, filter_id: int) -> bool:
        with closing(self._connect()) as conn, conn:
            return conn.execute("DELETE FROM filters WHERE id = ?", (filter_id,)).rowcount > 0


# ------------------------------------------------------------------ chạy quét

@dataclass
class ScanProgress:
    running: bool = False
    total: int = 0
    done: int = 0
    current: str | None = None
    waiting: str | None = None           # đang chờ hạn mức nguồn dữ liệu
    failed: list[dict[str, str]] = field(default_factory=list)
    started: str | None = None
    finished: str | None = None
    elapsed_s: float = 0.0
    stopped: bool = False
    as_of: str | None = None             # phiên vừa lưu
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        eta = (self.elapsed_s / self.done * (self.total - self.done)) if self.running and self.done else None
        return {**self.__dict__, "failed": list(self.failed), "eta_s": None if eta is None else round(eta)}


def run_scan(symbols: Iterable[str], analyze: Callable[[str], dict[str, Any]], *,
             update: Callable[[str], None] | None = None, progress: ScanProgress | None = None,
             stop: threading.Event | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Quét lần lượt từng mã; lỗi một mã không dừng cả lượt. `update`: cập nhật giá trước khi phân tích
    (lỗi thì vẫn phân tích trên dữ liệu đang có và ghi chú lại)."""
    symbols = list(symbols)
    p = progress or ScanProgress()
    p.total, p.done = len(symbols), 0
    t0 = time.monotonic()
    rows: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for symbol in symbols:
        if stop is not None and stop.is_set():
            p.stopped = True
            break
        p.current = symbol
        if update is not None:
            try:
                update(symbol)
            except Exception as exc:  # noqa: BLE001 - lỗi nguồn dữ liệu của một mã
                logger.warning("Không cập nhật được giá %s: %s", symbol, exc)
                failed.append({"symbol": symbol, "reason": "không cập nhật được giá, dùng dữ liệu đang có"})
        try:
            rows.append(analyze(symbol))
        except Exception as exc:  # noqa: BLE001 - mã thiếu dữ liệu hoặc lỗi phân tích
            logger.warning("Không quét được %s: %s", symbol, exc)
            failed.append({"symbol": symbol, "reason": str(exc) or type(exc).__name__})
        p.done += 1
        p.waiting = None
        p.elapsed_s = time.monotonic() - t0
        p.failed = failed
    p.current = None
    return rows, failed


class ScanJob:
    """Một lượt quét chạy nền cho API, có tiến độ và nút dừng. Mỗi lúc chỉ một lượt."""

    def __init__(self, store: ScanStore, make_runner: Callable[[ScanProgress], tuple[list[str], Callable[[str], dict[str, Any]], Callable[[str], None] | None]]):
        self.store = store
        self._make_runner = make_runner
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.progress = ScanProgress()

    def start(self) -> bool:
        with self._lock:
            if self.progress.running:
                return False
            self._stop.clear()
            self.progress = ScanProgress(running=True, started=datetime.now().isoformat(timespec="seconds"))
            self._thread = threading.Thread(target=self._run, name="scan-market", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> bool:
        if not self.progress.running:
            return False
        self._stop.set()
        return True

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        p = self.progress
        try:
            symbols, analyze, update = self._make_runner(p)
            rows, failed = run_scan(symbols, analyze, update=update, progress=p, stop=self._stop)
            if not p.stopped:
                p.as_of = self.store.save_scan(rows, failed, started=p.started or "", universe=len(symbols),
                                               finished=datetime.now().isoformat(timespec="seconds"))
                if p.as_of is None:
                    p.error = "Không quét được mã nào"
        except Exception as exc:  # noqa: BLE001 - báo lỗi cho giao diện thay vì làm chết luồng
            logger.exception("Lượt quét lỗi")
            p.error = str(exc) or type(exc).__name__
        finally:
            p.finished = datetime.now().isoformat(timespec="seconds")
            p.running = False
