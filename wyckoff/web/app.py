"""API JSON cho dashboard (giao diện Next.js ở web/ gọi qua /api/*).

    python serve.py                      # http://127.0.0.1:8000/api/docs
    uvicorn wyckoff.web.app:app          # dùng biến môi trường WYCKOFF_* (xem Settings)
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from wyckoff.agent.ask import MAX_QUESTION_CHARS, answer_question
from wyckoff.agent.explain import explain
from wyckoff.agent.llm import DEFAULT_MODEL, AnthropicClient, LLMClient, LLMError
from wyckoff.agent.payload import build_payload
from wyckoff.config import Config, load_config
from wyckoff.service import (DEFAULT_START, DEMO_SYMBOL, TIMEFRAMES, DataUnavailable, load_market, load_market_overview,
                             run_analysis)
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
