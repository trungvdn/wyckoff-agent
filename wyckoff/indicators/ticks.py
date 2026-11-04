"""Bước giá (tick) theo sàn. Giá tính bằng nghìn đồng (như vnstock)."""
from __future__ import annotations


def tick_size(price: float, exchange: str = "HOSE") -> float:
    """HOSE: < 10.000đ -> 10đ; 10.000-49.950đ -> 50đ; >= 50.000đ -> 100đ.
    HNX / UPCoM: 100đ."""
    ex = exchange.upper()
    if ex == "HOSE":
        if price < 10:
            return 0.01
        if price < 50:
            return 0.05
        return 0.1
    if ex in {"HNX", "UPCOM"}:
        return 0.1
    raise ValueError(f"Sàn không hỗ trợ: {exchange}")
