"""Phần tính toán dùng chung cho API và job cảnh báo: cấu hình, cache phân tích, danh mục.
Tách khỏi app.py để dùng được mà không phải dựng ứng dụng web."""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from wyckoff.agent.explain import explain
from wyckoff.agent.llm import DEFAULT_MODEL, AnthropicClient, LLMClient, LLMError
from wyckoff.agent.payload import build_payload
from wyckoff.config import Config, load_config
from wyckoff.pipeline import analyze
from wyckoff.portfolio import Holding, PortfolioStore, Rule, error_row, holding_row, portfolio_view, rule_catalog
from wyckoff.scanner import ScanProgress, scan_row
from wyckoff.service import (DEFAULT_START, DEMO_SYMBOL, DataUnavailable, cached_symbols, is_index, load_market,
                             load_market_overview, load_ohlcv, prepare_index, run_analysis, update_symbol)
from wyckoff.web.viewmodel import build_view

logger = logging.getLogger(__name__)
TF_LABEL = {"1D": "Ngày", "1W": "Tuần"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


@dataclass
class Settings:
    # Mặc định config/v3.yaml; WYCKOFF_CONFIG rỗng: dùng Config() (như backtest)
    config_path: str | None = field(default_factory=lambda: os.environ.get(
        "WYCKOFF_CONFIG", str(Path(__file__).resolve().parents[2] / "config" / "v3.yaml")) or None)
    cache_dir: str = field(default_factory=lambda: os.environ.get("WYCKOFF_CACHE_DIR", "cache"))
    out_dir: str = field(default_factory=lambda: os.environ.get("WYCKOFF_OUT_DIR", "output"))
    model: str = field(default_factory=lambda: os.environ.get("WYCKOFF_MODEL", DEFAULT_MODEL))
    no_llm: bool = field(default_factory=lambda: _env_flag("WYCKOFF_NO_LLM"))
    no_market: bool = field(default_factory=lambda: _env_flag("WYCKOFF_NO_MARKET"))
    offline: bool = field(default_factory=lambda: _env_flag("WYCKOFF_OFFLINE"))
    portfolio_db: str = field(default_factory=lambda: os.environ.get("WYCKOFF_PORTFOLIO_DB", "data/portfolio.db"))
    scanner_db: str = field(default_factory=lambda: os.environ.get("WYCKOFF_SCANNER_DB", "data/scanner.db"))
    ttl_s: float = field(default_factory=lambda: float(os.environ.get("WYCKOFF_TTL_S", "300")))
    default_symbol: str = field(default_factory=lambda: os.environ.get("WYCKOFF_DEFAULT_SYMBOL", "HPG"))


def load_app_config(settings: Settings) -> Config:
    cfg = load_config(settings.config_path)
    return replace(cfg, data=replace(cfg.data, offline=True)) if settings.offline else cfg


@dataclass
class Entry:
    created: float
    view: dict[str, Any]
    payload: dict[str, Any]
    explanation: dict[str, Any] | None = None


class AnalysisStore:
    """Cache trong bộ nhớ theo (mã, khung), hết hạn sau `ttl_s`; khóa riêng từng khóa để không tải trùng."""

    def __init__(self, settings: Settings, cfg: Config, client_factory: Callable[[], tuple[LLMClient | None, str]]):
        self.settings, self.cfg = settings, cfg
        self._entries: dict[tuple[str, str], Entry] = {}
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._guard = threading.Lock()
        self._client_factory = client_factory
        self._client: tuple[LLMClient | None, str] | None = None

    def client(self) -> tuple[LLMClient | None, str]:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _lock(self, key: tuple[str, str]) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _cached(self, key: tuple[str, str], refresh: bool, build: Callable[[], Entry]) -> Entry:
        with self._lock(key):
            e = self._entries.get(key)
            if e is not None and not refresh and time.monotonic() - e.created < self.settings.ttl_s:
                return e
            e = build()
            self._entries[key] = e
            return e

    def get(self, symbol: str, tf: str, refresh: bool = False) -> Entry:
        return self._cached((symbol, tf), refresh, lambda: self._build(symbol, tf))

    def market(self, refresh: bool = False) -> dict[str, Any]:
        """Số liệu trang thị trường. Khóa cache không trùng mã nào vì mã không chứa dấu gạch dưới."""
        return self._cached(("_market", "1D"), refresh, lambda: self._build_market(refresh)).view

    def _build_market(self, refresh: bool) -> Entry:
        st = self.settings
        if st.no_market or not self.cfg.market.enabled:
            raise DataUnavailable("Dữ liệu chỉ số đang tắt trong cấu hình máy chủ.", status=404)
        view = load_market_overview(self.cfg, cache_dir=st.cache_dir, refresh=refresh)
        notices = []
        if self.cfg.data.offline:
            notices.append(f"Dữ liệu đồng bộ đến phiên {pd.Timestamp(view['as_of']):%d/%m/%Y}; máy chủ không tự cập nhật giá.")
        return Entry(time.monotonic(), {**view, "notices": notices}, {})

    def _build(self, symbol: str, tf: str) -> Entry:
        st = self.settings
        start = DEFAULT_START[tf]
        result = run_analysis(symbol, tf, self.cfg, start=start, cache_dir=st.cache_dir)
        notices: list[str] = []
        market = None
        if tf != "1D":
            notices.append(f"Khung {TF_LABEL[tf].lower()}: ngưỡng detector được hiệu chỉnh cho khung ngày, kết quả chỉ để tham khảo.")
        elif not st.no_market and self.cfg.market.enabled:
            market, _, _ = load_market(result, symbol, self.cfg, start=start, cache_dir=st.cache_dir,
                                       demo=symbol == DEMO_SYMBOL)
            if market is None:
                notices.append("Không tải được dữ liệu chỉ số: bỏ qua bối cảnh thị trường.")
        if symbol == DEMO_SYMBOL:
            notices.append("Dữ liệu tổng hợp (DEMO), không phải giá thật.")
        elif self.cfg.data.offline:
            notices.append(f"Dữ liệu đồng bộ đến phiên {result.df.index[-1]:%d/%m/%Y}; máy chủ không tự cập nhật giá.")
        payload = build_payload(result, symbol, market)
        return Entry(time.monotonic(), build_view(result, payload, symbol, tf, notices), payload)

    def previous_view(self, symbol: str) -> dict[str, Any] | None:
        """View model tính đến phiên liền trước, để so sánh. Lỗi hoặc thiếu nến -> None (không so được)."""
        def build() -> Entry:
            try:
                ohlcv = load_ohlcv(symbol, "1D", self.cfg, start=DEFAULT_START["1D"], cache_dir=self.settings.cache_dir)
                res = analyze(ohlcv.iloc[:-1], self.cfg)
                view = build_view(res, build_payload(res, symbol, None), symbol, "1D")
            except Exception as exc:  # noqa: BLE001 - thiếu phần so sánh không được làm hỏng cả danh mục
                logger.warning("Không so được %s với phiên trước: %s", symbol, exc)
                view = {}
            return Entry(time.monotonic(), view, {})
        return self._cached((symbol, "_previous"), False, build).view or None

    @property
    def sma_periods(self) -> tuple[int, int]:
        return self.cfg.market.sma_fast, self.cfg.market.sma_slow

    def rule_catalog(self) -> list[dict[str, Any]]:
        ind = self.cfg.indicators
        return rule_catalog(self.sma_periods, (ind.ema_fast, ind.ema_slow))

    def holding_row(self, h: Holding, rules: list[Rule]) -> dict[str, Any]:
        catalog = self.rule_catalog()
        try:
            return holding_row(h, self.get(h.symbol, "1D").view, self.previous_view(h.symbol), rules, catalog, self.sma_periods)
        except DataUnavailable as exc:
            return error_row(h, str(exc), rules, catalog)

    def portfolio(self, holdings: PortfolioStore) -> dict[str, Any]:
        """Toàn bộ danh mục, gồm trạng thái quy tắc bán. API và job cảnh báo cùng dùng hàm này."""
        notices = ["Dữ liệu đồng bộ theo lần gần nhất; máy chủ không tự cập nhật giá."] if self.cfg.data.offline else []
        rules = holdings.rules()
        return portfolio_view([self.holding_row(h, rules.get(h.symbol, [])) for h in holdings.list()], notices, self.rule_catalog())

    def explanation(self, symbol: str, tf: str) -> dict[str, Any]:
        e = self.get(symbol, tf)
        if e.explanation is None:
            client, reason = self.client()
            res = explain(e.payload, client, cache_dir=Path(self.settings.out_dir) / "llm_cache", no_llm_reason=reason)
            e.explanation = {"source": res.source, "model": res.model, "attempts": res.attempts,
                             "errors": res.errors if res.source == "template" else [], **res.explanation}
        return e.explanation


ScanRunner = tuple[list[str], Callable[[str], dict[str, Any]], Callable[[str], None] | None]


def scan_runner(settings: Settings, cfg: Config, *, update_prices: bool = True,
                symbols: list[str] | None = None) -> Callable[[ScanProgress], ScanRunner]:
    """Chuẩn bị một lượt quét: danh sách mã (mặc định mọi cổ phiếu trong cache), hàm cập nhật giá, hàm phân tích.
    Máy chủ chạy offline thì không tải giá. Chỉ số so sánh được cập nhật và phân tích một lần cho cả lượt."""
    def make(progress: ScanProgress) -> ScanRunner:
        online = update_prices and not cfg.data.offline

        def on_wait(attempt: int, wait_s: float, exc: Exception) -> None:
            progress.waiting = f"Nguồn dữ liệu báo hết hạn mức theo phút, chờ {wait_s:.0f} giây (lần {attempt})"

        universe = symbols or [s for s in cached_symbols(settings.cache_dir) if not is_index(s, cfg)]
        offline_cfg = replace(cfg, data=replace(cfg.data, offline=True))
        start = DEFAULT_START["1D"]
        index = None
        if not settings.no_market and cfg.market.enabled:
            from wyckoff.market import benchmark_for

            if online:
                try:
                    update_symbol(benchmark_for(cfg.data.exchange, cfg.market), cfg, cache_dir=settings.cache_dir, on_wait=on_wait)
                except Exception as exc:  # noqa: BLE001 - vẫn quét được với dữ liệu chỉ số đang có
                    logger.warning("Không cập nhật được chỉ số: %s", exc)
            try:
                index = prepare_index(offline_cfg, start=start, cache_dir=settings.cache_dir)
            except Exception as exc:  # noqa: BLE001 - thiếu chỉ số chỉ làm mất cột RS
                logger.warning("Không tải được chỉ số so sánh: %s", exc)
        sma_periods = (cfg.market.sma_fast, cfg.market.sma_slow)

        def analyze_one(symbol: str) -> dict[str, Any]:
            result = run_analysis(symbol, "1D", offline_cfg, start=start, cache_dir=settings.cache_dir)
            market = None
            if index is not None:
                market, _, _ = load_market(result, symbol, offline_cfg, start=start, index=index)
            payload = build_payload(result, symbol, market)
            return scan_row(build_view(result, payload, symbol, "1D"), market, sma_periods)

        def update(symbol: str) -> None:
            update_symbol(symbol, cfg, cache_dir=settings.cache_dir, on_wait=on_wait)

        return universe, analyze_one, update if online else None
    return make


def default_client_factory(settings: Settings) -> Callable[[], tuple[LLMClient | None, str]]:
    def make() -> tuple[LLMClient | None, str]:
        if settings.no_llm:
            return None, "tắt LLM (WYCKOFF_NO_LLM)"
        try:
            return AnthropicClient(model=settings.model), ""
        except LLMError as exc:
            logger.warning("Không dùng được LLM: %s", exc)
            return None, str(exc)
    return make
