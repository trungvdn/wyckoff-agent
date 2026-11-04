"""Kiểu dữ liệu kết quả của các detector."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal

import pandas as pd


class EventStatus(str, Enum):
    """Vòng đời event (quy chuẩn 04/11/2026 mục 1.2)."""
    DETECTED = "DETECTED"        # mới phát hiện dấu hiệu (vd. phiên thủng support)
    CANDIDATE = "CANDIDATE"      # đủ dấu hiệu ban đầu, chờ xác nhận (vd. Spring shakeout chờ Test)
    CONFIRMED = "CONFIRMED"      # đạt điều kiện xác nhận của detector
    INVALIDATED = "INVALIDATED"  # điều kiện cấu trúc bị phá vỡ / hết hạn chờ xác nhận
    REVISED = "REVISED"          # diễn giải thay đổi (vd. gộp vào event khác); giữ lịch sử, không xóa


TERMINAL_STATUSES = (EventStatus.INVALIDATED, EventStatus.REVISED)


@dataclass(frozen=True)
class StatusChange:
    status: EventStatus
    idx: int                      # phiên trạng thái bắt đầu có hiệu lực (đã biết tại phiên này)
    date: pd.Timestamp
    reason: str = ""


class EventType(str, Enum):
    SC = "SC"
    SPRING = "Spring"
    SOS = "SOS"
    TEST = "Test"
    SC_FAILED = "SC failed"
    PS = "PS"
    AR = "AR"
    ST = "ST"
    LPS = "LPS"
    UTAD = "UTAD"


SPRING_TYPE_LABEL = {"low_volume": "volume thấp", "shakeout": "shakeout"}

# Bối cảnh range = đà giá trước range (KHÔNG phải tích lũy / phân phối theo Wyckoff – backtest 03/11/2026)
CTX_AFTER_DECLINE = "sau nhịp giảm"
CTX_AFTER_RISE = "sau nhịp tăng"
CTX_NEUTRAL = "trung tính"
CTX_UNKNOWN = "chưa rõ"
CONTEXTS = (CTX_AFTER_DECLINE, CTX_NEUTRAL, CTX_AFTER_RISE, CTX_UNKNOWN)


@dataclass(frozen=True)
class Swing:
    idx: int                      # vị trí pivot
    date: pd.Timestamp
    price: float
    kind: Literal["high", "low"]
    confirmed_idx: int            # phiên đầu tiên biết chắc đây là pivot (idx + right)


@dataclass(frozen=True)
class TradingRange:
    range_id: int
    start_idx: int
    start_date: pd.Timestamp
    end_idx: int                  # phiên cuối còn nằm trong range
    end_date: pd.Timestamp
    confirmed_idx: int            # phiên range được xác nhận (đủ swing, đủ độ dài)
    confirmed_date: pd.Timestamp
    support: float
    resistance: float
    atr_at_confirm: float
    end_confirmed_idx: int | None = None   # phiên biết range đã kết thúc; None = đang hoạt động
    end_confirmed_date: pd.Timestamp | None = None
    exit_direction: Literal["up", "down"] | None = None
    context: str = "chưa rõ"              # một trong CONTEXTS
    prior_return: float | None = None      # lợi suất `context_lookback` phiên trước start_idx
    anchored: bool = False                 # biên lấy từ đáy SC và đỉnh AR, không phải từ swing

    @property
    def height(self) -> float:
        return self.resistance - self.support

    def known_active_at(self, i: int, last_idx: int) -> bool:
        """Range đã được xác nhận trước phiên i và chưa bị xác nhận kết thúc trước phiên i."""
        end = self.end_confirmed_idx if self.end_confirmed_idx is not None else last_idx
        return self.confirmed_idx < i <= end


@dataclass(frozen=True)
class Event:
    kind: EventType
    idx: int                      # phiên của sự kiện (với Spring: phiên thủng support)
    date: pd.Timestamp
    confirmed_idx: int            # phiên sự kiện được xác nhận (Spring: phiên đóng cửa quay lại)
    confirmed_date: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    vol_ratio: float              # volume / TB20 (20 phiên trước)
    spread_atr: float             # (high - low) / ATR phiên trước
    close_pos: float              # (close - low) / (high - low)
    range_id: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
    # --- vòng đời (gán bởi wyckoff.detectors.lifecycle.annotate) ---
    event_id: str = ""                          # ID ổn định: không đổi khi đổi ngày bắt đầu dữ liệu
    history: tuple[StatusChange, ...] = ()      # theo thứ tự thời gian; trạng thái cuối = status
    related_event_ids: tuple[str, ...] = ()
    test_of_event_id: str | None = None         # ST/Test: event đang được kiểm tra

    @property
    def status(self) -> EventStatus:
        return self.history[-1].status if self.history else EventStatus.CONFIRMED

    @property
    def is_confirmed(self) -> bool:
        """Đã từng đạt CONFIRMED (có thể sau đó bị INVALIDATED)."""
        return self.confirmed_idx >= 0 and (not self.history or any(h.status == EventStatus.CONFIRMED for h in self.history))

    @property
    def invalidated(self) -> StatusChange | None:
        return next((h for h in self.history if h.status == EventStatus.INVALIDATED), None)

    def known_at(self, i: int) -> bool:
        return self.status_at(i) is not None

    def status_at(self, i: int) -> EventStatus | None:
        """Trạng thái tại phiên i chỉ theo thông tin đã có đến i (None = chưa biết event này)."""
        if not self.history:
            return EventStatus.CONFIRMED if self.confirmed_idx <= i else None
        cur = None
        for h in self.history:
            if h.idx > i:
                break
            cur = h.status
        return cur

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d.update({f"detail_{k}": v for k, v in d.pop("details").items()})
        hist = d.pop("history")
        d["status"] = self.status.value
        d["history"] = "; ".join(f"{h['status'].value}@{h['date']:%Y-%m-%d}" + (f" ({h['reason']})" if h["reason"] else "")
                                 for h in hist)
        inv = self.invalidated
        d["invalidated_date"] = inv.date if inv is not None else None
        d["related_event_ids"] = ",".join(self.related_event_ids)
        return d

    def evidence(self) -> str:
        return (
            f"{self.kind.value} {self.date:%Y-%m-%d}: O={self.open:.2f} H={self.high:.2f} "
            f"L={self.low:.2f} C={self.close:.2f}, vol={self.volume:,.0f} ({self.vol_ratio:.2f}x TB20), "
            f"spread={self.spread_atr:.2f}xATR, close_pos={self.close_pos:.2f}"
        )
