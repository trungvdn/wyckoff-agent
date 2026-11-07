"""API JSON cho dashboard (giao diện Next.js ở web/ gọi qua /api/*).

    python serve.py                      # http://127.0.0.1:8000/api/docs
    uvicorn wyckoff.web.app:app          # dùng biến môi trường WYCKOFF_* (xem Settings)
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from wyckoff.agent.ask import MAX_QUESTION_CHARS, answer_question
from wyckoff.agent.llm import LLMClient
from wyckoff.alerts import AlertSendError, current_summary, split_message, telegram_from_env
from wyckoff.portfolio import (DuplicateHolding, DuplicateRule, Holding, PortfolioStore, Rule, evaluate_rule,
                               normalize_rule_side, normalize_rule_value, validate_rule)
from wyckoff.service import TIMEFRAMES, DataUnavailable
from wyckoff.web.store import AnalysisStore, Settings, default_client_factory, load_app_config

SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,10}$")
UNSUPPORTED_TF = {"15m": "15 phút", "1H": "Giờ"}


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


class AlertToggle(BaseModel):
    enabled: bool


class SendAlert(BaseModel):
    # Bắt buộc có thân JSON: trang web khác không gửi được yêu cầu này nếu không qua kiểm tra CORS
    confirm: Literal[True]


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
    cfg = load_app_config(settings)
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
        return store.portfolio(holdings)

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

    @app.put("/api/portfolio/{symbol}/alerts")
    def set_holding_alerts(symbol: str, body: AlertToggle) -> dict[str, Any]:
        s = _symbol(symbol)
        if not holdings.set_alerts(s, body.enabled):
            raise HTTPException(404, f"{s} không có trong danh mục.")
        return {"symbol": s, "alerts_enabled": body.enabled}

    @app.get("/api/alerts/preview")
    def preview_alert() -> dict[str, Any]:
        return {**current_summary(store.portfolio(holdings)), "configured": telegram_from_env() is not None}

    @app.post("/api/alerts/send")
    def send_alert(body: SendAlert) -> dict[str, Any]:
        sender = telegram_from_env()
        if sender is None:
            raise HTTPException(503, "Chưa cấu hình Telegram: cần TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong file .env.")
        summary = current_summary(store.portfolio(holdings))
        if not summary["enabled_count"]:
            raise HTTPException(422, "Không có mã nào đang bật thông báo.")
        try:
            for chunk in split_message(summary["text"]):
                sender.send(chunk)
        except AlertSendError as exc:
            raise HTTPException(502, str(exc)) from None
        holdings.log_alert(summary["as_of"], summary["text"])
        return {"sent": True, "enabled_count": summary["enabled_count"]}

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
