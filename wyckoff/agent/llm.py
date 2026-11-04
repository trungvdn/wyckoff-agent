"""Lớp gọi LLM. Mặc định Claude qua Anthropic API, đầu ra JSON theo schema (structured outputs).

Lưu ý: Claude Sonnet 5.5 / Opus 5.5 không hỗ trợ ép tool bằng `tool_choice` (trả lỗi 400),
nên dùng `output_config.format = json_schema` và đọc JSON từ khối text.
API key lấy từ biến môi trường ANTHROPIC_API_KEY, không ghi trong code/config.
"""
from __future__ import annotations

import os
from typing import Any, Protocol

DEFAULT_MODEL = "claude-sonnet-5-5"


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        """Trả về chuỗi JSON (chưa parse)."""
        ...


class AnthropicClient:
    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 4000, api_key: str | None = None,
                 timeout: float = 120.0) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise LLMError("Chưa cài thư viện anthropic: pip install anthropic") from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("Thiếu biến môi trường ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=key, timeout=timeout)
        self.model = model
        self.max_tokens = max_tokens

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except Exception as exc:  # noqa: BLE001 - gói mọi lỗi API thành LLMError
            raise LLMError(f"Lỗi gọi API: {type(exc).__name__}: {exc}") from exc
        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise LLMError("Câu trả lời bị cắt (max_tokens)")
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        if not text:
            raise LLMError("Câu trả lời không có khối text")
        return text


class FakeClient:
    """Client giả cho test: trả lần lượt các chuỗi trong `responses` (Exception thì raise)."""

    def __init__(self, responses: list[str | Exception], model: str = "fake-model") -> None:
        self.responses = list(responses)
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        self.calls.append({"system": system, "user": user, "schema": schema})
        if not self.responses:
            raise LLMError("FakeClient hết câu trả lời")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
