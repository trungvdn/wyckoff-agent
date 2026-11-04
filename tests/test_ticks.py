import pytest

from wyckoff.indicators.ticks import tick_size


@pytest.mark.parametrize("price,exchange,tick", [
    (9.99, "HOSE", 0.01), (10, "HOSE", 0.05), (49.95, "HOSE", 0.05), (50, "HOSE", 0.1), (20, "HNX", 0.1),
])
def test_tick_size(price: float, exchange: str, tick: float) -> None:
    assert tick_size(price, exchange) == tick


def test_tick_size_unknown_exchange() -> None:
    with pytest.raises(ValueError):
        tick_size(10, "NYSE")
