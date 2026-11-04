"""Điều phối: payload -> LLM -> kiểm tra -> (thử lại) -> dự phòng theo mẫu; có cache."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wyckoff.agent.llm import LLMClient, LLMError
from wyckoff.agent.payload import payload_json
from wyckoff.agent.prompts import OUTPUT_SCHEMA, PROMPT_VERSION, SYSTEM_PROMPT, user_prompt
from wyckoff.agent.report import template_explanation
from wyckoff.agent.validate import validate_explanation

logger = logging.getLogger(__name__)


@dataclass
class ExplainResult:
    payload: dict[str, Any]
    explanation: dict[str, Any]
    source: str                         # "llm" | "cache" | "template"
    model: str | None
    attempts: int
    errors: list[str] = field(default_factory=list)


def cache_key(payload: dict[str, Any], model: str) -> str:
    raw = f"{PROMPT_VERSION}|{model}|{payload_json(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def explain(
    payload: dict[str, Any],
    client: LLMClient | None,
    *,
    cache_dir: str | Path | None = None,
    max_attempts: int = 2,
    no_llm_reason: str = "không có LLM client",
) -> ExplainResult:
    if client is None:
        return ExplainResult(payload, template_explanation(payload), "template", None, 0, [f"Không gọi LLM: {no_llm_reason}"])

    pj = payload_json(payload)
    cache_path = Path(cache_dir) / f"{cache_key(payload, client.model)}.json" if cache_dir else None
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if not validate_explanation(cached, payload):
            logger.info("Dùng diễn giải trong cache %s", cache_path.name)
            return ExplainResult(payload, cached, "cache", client.model, 0)

    errors: list[str] = []
    feedback: list[str] | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            raw = client.complete_json(SYSTEM_PROMPT, user_prompt(pj, feedback), OUTPUT_SCHEMA)
        except LLMError as exc:
            errors.append(f"Lần {attempt}: {exc}")
            feedback = None
            continue
        try:
            expl = json.loads(raw)
        except json.JSONDecodeError as exc:
            errs = [f"JSON không hợp lệ: {exc}"]
        else:
            errs = validate_explanation(expl, payload)
        if not errs:
            if cache_path:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(expl, ensure_ascii=False, indent=1), encoding="utf-8")
            return ExplainResult(payload, expl, "llm", client.model, attempt, errors)
        errors += [f"Lần {attempt}: {e}" for e in errs]
        feedback = errs[:12]
        logger.warning("Diễn giải lần %d không đạt kiểm tra (%d lỗi)", attempt, len(errs))

    logger.warning("Dùng báo cáo theo mẫu sau %d lần thử", max_attempts)
    return ExplainResult(payload, template_explanation(payload), "template", client.model, max_attempts, errors)
