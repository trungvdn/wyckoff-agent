"""API JSON cho dashboard (giao diện Next.js ở web/ gọi qua /api/*).

    python serve.py                      # http://127.0.0.1:8000/api/docs
    uvicorn wyckoff.web.app:app          # dùng biến môi trường WYCKOFF_* (xem Settings)
"""
from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from wyckoff.agent.ask import MAX_QUESTION_CHARS, answer_question
from wyckoff.agent.explain import explain
from wyckoff.agent.llm import DEFAULT_MODEL, AnthropicClient, LLMClient, LLMError
from wyckoff.agent.payload import build_payload
from wyckoff.config import Config, load_config
from wyckoff.pipeline import analyze
from wyckoff.portfolio import (DuplicateHolding, DuplicateRule, Holding, PortfolioStore, Rule, error_row, evaluate_rule,
                               holding_row, normalize_rule_side, normalize_rule_value, portfolio_view, rule_catalog, validate_rule)
from wyckoff.service import (DEFAULT_START, DEMO_SYMBOL, TIMEFRAMES, DataUnavailable, load_market, load_market_overview,
                             load_ohlcv, run_analysis)
from wyckoff.web.viewmodel import build_view

logger = logging.getLogger(__name__)
SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,10}$")
TF_LABEL = {"1D": "Ngày", "1W": "Tuần"}
UNSUPPORTED_TF = {"15m": "15 phút", "1H": "Giờ"}


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
    ttl_s: float = field(default_factory=lambda: float(os.environ.get("WYCKOFF_TTL_S", "300")))
    default_symbol: str = field(default_factory=lambda: os.environ.get("WYCKOFF_DEFAULT_SYMBOL", "HPG"))


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

    def explanation(self, symbol: str, tf: str) -> dict[str, Any]:
        e = self.get(symbol, tf)
        if e.explanation is None:
            client, reason = self.client()
            res = explain(e.payload, client, cache_dir=Path(self.settings.out_dir) / "llm_cache", no_llm_reason=reason)
            e.explanation = {"source": res.source, "model": res.model, "attempts": res.attempts,
                             "errors": res.errors if res.source == "template" else [], **res.explanation}
        return e.explanation


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


class AskBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    timeframe: str = "1D"
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class HoldingFields(BaseModel):
    quantity: int = Field(gt=0, le=1_000_000_000)
    cost: float = Field(gt=0, le=100_000)      # nghìn đồng
    bought_on: date


class NewHolding(HoldingFields):
    symbol: str = Field(min_length=1, max_length=10)


class RuleFields(BaseModel):
    kind: str = Field(max_length=32)
    value: float | None = None
    side: Literal["profit", "loss"] | None = None   # None: theo loại quy tắc
    sufficient: bool = False                        # "đạt là đủ"


class NewRule(RuleFields):
    symbol: str = Field(min_length=1, max_length=10)


def _symbol(raw: str) -> str:
    s = raw.strip().upper()
    if not SYMBOL_RE.match(s):
        raise HTTPException(422, "Mã cổ phiếu gồm 3–10 ký tự chữ hoặc số, ví dụ HPG.")
    return s


def _tf(raw: str) -> str:
    if raw in UNSUPPORTED_TF:
        raise HTTPException(422, f"Khung {UNSUPPORTED_TF[raw]} chưa được hỗ trợ: chưa có dữ liệu trong ngày và ngưỡng hiệu chỉnh.")
    if raw not in TIMEFRAMES:
        raise HTTPException(422, f"Khung thời gian không hợp lệ: {raw}. Chọn {', '.join(TIMEFRAMES)}.")
    return raw


def create_app(settings: Settings | None = None,
               client_factory: Callable[[], tuple[LLMClient | None, str]] | None = None) -> FastAPI:
    settings = settings or Settings()
    cfg = load_config(settings.config_path)
    if settings.offline:
        cfg = replace(cfg, data=replace(cfg.data, offline=True))
    store = AnalysisStore(settings, cfg, client_factory or default_client_factory(settings))
    app = FastAPI(title="Wyckoff Agent", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.store = store
    holdings = PortfolioStore(settings.portfolio_db)

    def holding(symbol: str, body: HoldingFields) -> Holding:
        if body.bought_on > datetime.now(ZoneInfo(cfg.data.timezone)).date():
            raise HTTPException(422, "Ngày mua không được sau hôm nay.")
        return Holding(symbol, body.quantity, body.cost, body.bought_on.isoformat())

    def checked_rule(kind: str, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise HTTPException(422, "Giá trị của quy tắc không hợp lệ.")
        error = validate_rule(kind, value)
        if error:
            raise HTTPException(422, error)
        return normalize_rule_value(kind, value)

    def held(symbol: str) -> Holding:
        h = next((x for x in holdings.list() if x.symbol == symbol), None)
        if h is None:
            raise HTTPException(404, f"{symbol} không có trong danh mục.")
        return h

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if not request.url.path.startswith("/api/docs"):
            resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return resp

    @app.exception_handler(DataUnavailable)
    async def data_unavailable(_: Request, exc: DataUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/api/docs")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        client, reason = store.client()
        return {"status": "ok", "llm": client is not None, "llm_reason": reason or None,
                "default_symbol": settings.default_symbol, "timeframes": list(TIMEFRAMES)}

    @app.get("/api/market")
    def market(refresh: bool = False) -> dict[str, Any]:
        return store.market(refresh=refresh)

    @app.get("/api/quote/{symbol}")
    def quote(symbol: str) -> dict[str, Any]:
        view = store.get(_symbol(symbol), "1D").view
        return {"symbol": view["symbol"], "close": view["bars"][-1]["c"], "as_of": view["as_of"]}

    @app.get("/api/portfolio")
    def portfolio() -> dict[str, Any]:
        notices = ["Dữ liệu đồng bộ theo lần gần nhất; máy chủ không tự cập nhật giá."] if cfg.data.offline else []
        rules = holdings.rules()
        return portfolio_view([store.holding_row(h, rules.get(h.symbol, [])) for h in holdings.list()], notices, store.rule_catalog())

    @app.post("/api/portfolio", status_code=201)
    def add_holding(body: NewHolding) -> dict[str, Any]:
        h = holding(_symbol(body.symbol), body)
        store.get(h.symbol, "1D")   # mã không có dữ liệu -> báo lỗi, không lưu
        try:
            holdings.add(h)
        except DuplicateHolding as exc:
            raise HTTPException(409, f"{h.symbol} đã có trong danh mục. Hãy sửa dòng hiện có.") from exc
        return asdict(h)

    @app.put("/api/portfolio/{symbol}")
    def update_holding(symbol: str, body: HoldingFields) -> dict[str, Any]:
        h = holding(_symbol(symbol), body)
        if not holdings.update(h):
            raise HTTPException(404, f"{h.symbol} không có trong danh mục.")
        return asdict(h)

    @app.delete("/api/portfolio/{symbol}", status_code=204)
    def delete_holding(symbol: str) -> None:
        s = _symbol(symbol)
        if not holdings.delete(s):
            raise HTTPException(404, f"{s} không có trong danh mục.")

    @app.get("/api/rules/preview")
    def preview_rule(symbol: str, kind: str, value: float | None = None, side: Literal["profit", "loss"] | None = None) -> dict[str, Any]:
        """Xem trước trạng thái của một quy tắc, không lưu."""
        s = _symbol(symbol)
        value = checked_rule(kind, value)
        h = held(s)
        view = store.get(s, "1D").view
        return evaluate_rule(Rule(0, s, kind, value, normalize_rule_side(kind, side)), h, view, store.previous_view(s), store.rule_catalog(), store.sma_periods)

    @app.post("/api/rules", status_code=201)
    def add_rule(body: NewRule) -> dict[str, Any]:
        s = _symbol(body.symbol)
        value = checked_rule(body.kind, body.value)
        held(s)
        try:
            return asdict(holdings.add_rule(s, body.kind, value, normalize_rule_side(body.kind, body.side), body.sufficient))
        except DuplicateRule as exc:
            raise HTTPException(409, f"{s} đã có quy tắc này.") from exc

    @app.put("/api/rules/{rule_id}")
    def update_rule(rule_id: int, body: RuleFields) -> dict[str, Any]:
        value = checked_rule(body.kind, body.value)
        current = holdings.rule(rule_id)
        if current is None:
            raise HTTPException(404, "Quy tắc không còn tồn tại.")
        try:
            side = normalize_rule_side(body.kind, body.side)
            holdings.update_rule(rule_id, body.kind, value, side, body.sufficient)
        except DuplicateRule as exc:
            raise HTTPException(409, f"{current.symbol} đã có quy tắc này.") from exc
        return asdict(Rule(rule_id, current.symbol, body.kind, value, side, body.sufficient))

    @app.delete("/api/rules/{rule_id}", status_code=204)
    def delete_rule(rule_id: int) -> None:
        if not holdings.delete_rule(rule_id):
            raise HTTPException(404, "Quy tắc không còn tồn tại.")

    @app.get("/api/analysis/{symbol}")
    def analysis(symbol: str, tf: str = Query("1D"), refresh: bool = False) -> dict[str, Any]:
        return store.get(_symbol(symbol), _tf(tf), refresh=refresh).view

    @app.get("/api/explanation/{symbol}")
    def explanation(symbol: str, tf: str = Query("1D")) -> dict[str, Any]:
        return store.explanation(_symbol(symbol), _tf(tf))

    @app.post("/api/ask")
    def ask(body: AskBody) -> dict[str, Any]:
        e = store.get(_symbol(body.symbol), _tf(body.timeframe))
        client, reason = store.client()
        res = answer_question(e.payload, body.question, client, no_llm_reason=reason)
        return {"answer": res.answer, "event_ids": res.event_ids, "source": res.source, "model": res.model,
                "errors": res.errors if res.source == "template" else []}

    return app


app = create_app()
