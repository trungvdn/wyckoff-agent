"""Giai đoạn 2: payload, tin cậy, kiểm soát đầu ra LLM, thử lại / dự phòng, cache, HTML. Không gọi mạng."""
from __future__ import annotations

import copy
import json
import sys
import types

import pandas as pd
import pytest

from wyckoff.agent.explain import explain
from wyckoff.agent.llm import AnthropicClient, FakeClient, LLMError
from wyckoff.agent.payload import build_payload, payload_json
from wyckoff.agent.prompts import OUTPUT_SCHEMA
from wyckoff.agent.report import render_html, template_explanation, vn, vn_date
from wyckoff.agent.validate import allowed_values, ungrounded, validate_explanation
from wyckoff.pipeline import analyze
from wyckoff.synthetic import SPRING_CONFIRM_IDX


@pytest.fixture
def payload_c(ohlcv: pd.DataFrame) -> dict:
    """Payload ở pha C (cắt dữ liệu sau Spring, trước SOS)."""
    return build_payload(analyze(ohlcv.iloc[:SPRING_CONFIRM_IDX + 5]), "DEMO")


def good_explanation(p: dict) -> dict:
    """Diễn giải mẫu 'kiểu LLM' chỉ dùng số trong payload (fixture viết tay cho test)."""
    ev = p["evidence_events"]
    spring = next(e for e in ev if e["kind"] == "Spring")
    return {
        "summary": f"{p['current_stage']['structure_type']}: DEMO đang ở pha C sau Spring ngày {vn_date(spring['date'])} "
                   f"với volume {vn(spring['vol_ratio'])}x TB20.",
        "phase_assessment": f"Spring thủng support {vn(p['current_phase']['support'])} rồi đóng cửa quay lại; "
                            f"close_pos phiên thủng {vn(spring['close_pos'])}.",
        "context_assessment": f"Range có SC mở đầu; giá cách resistance {vn(p['recent_bars']['distance_to_resistance_atr'])} ATR.",
        "market_assessment": "Không có dữ liệu thị trường.",
        "evidence_notes": [{"event_id": e["id"], "comment": f"{e['kind']} volume {vn(e['vol_ratio'])}x"} for e in ev],
        "confirmation_scenarios": [{"level_id": lv["id"], "narrative": "Nếu có SOS thì chuyển pha D."}
                                   for lv in p["levels"] if lv["type"] == "confirm"],
        "invalidation_scenarios": [{"level_id": lv["id"], "narrative": "Nếu thủng đáy Spring thì cấu trúc vô hiệu."}
                                   for lv in p["levels"] if lv["type"] == "invalidate"],
        "risks": ["Chưa có SOS xác nhận cầu."],
        "confidence_explanation": f"Mức tin cậy {p['confidence']['level']} do có SC, ST và Spring volume thấp.",
    }


# ------------------------------------------------------------------ payload

def test_payload_structure(payload_c: dict) -> None:
    cp = payload_c["current_phase"]
    assert cp["phase"] == "C" and cp["support"] == 64.0 and cp["resistance"] == 74.0
    assert [lv["id"] for lv in payload_c["levels"]] == ["confirm_0", "invalidate_0"]
    kinds = [e["kind"] for e in payload_c["evidence_events"]]
    assert kinds[:3] == ["SC", "AR", "ST"] and "Spring" in kinds
    json.dumps(payload_c)                                     # JSON-serializable


def test_payload_deterministic(ohlcv: pd.DataFrame) -> None:
    r = analyze(ohlcv.iloc[:SPRING_CONFIRM_IDX + 5])
    assert payload_json(build_payload(r, "DEMO")) == payload_json(build_payload(r, "DEMO"))


def test_confidence_rules(payload_c: dict) -> None:
    c = payload_c["confidence"]
    pts = {f["factor"]: f["points"] for f in c["factors"]}
    assert pts["Có SC mở cấu trúc (pha A xác định)"] == 1 and pts["Có ST xác nhận vùng đáy"] == 1
    assert c["score"] == sum(pts.values()) and c["level"] == "trung bình"
    keys = {f["key"]: f["points"] for f in c["factors"]}
    assert keys["spring"] == 0 and "hiệu chỉnh theo backtest" in next(f["factor"] for f in c["factors"] if f["key"] == "spring")


def test_confidence_v2_context_weights() -> None:
    from wyckoff.agent.payload import confidence
    from wyckoff.config import ConfidenceConfig
    from wyckoff.phases import CurrentPhase
    cur = CurrentPhase(pd.Timestamp("2024-01-02"), "B", None, "", 0, "sau nhịp giảm", 10.0, 12.0, 0.5, [], [], [], [])
    assert confidence(cur, [], "sau nhịp giảm")["score"] == -1
    assert confidence(cur, [], "sau nhịp tăng")["score"] == 0
    assert confidence(cur, [], "sau nhịp giảm", cfg=ConfidenceConfig(after_decline=1))["score"] == 1


def test_confidence_not_applicable_without_structure(ohlcv: pd.DataFrame) -> None:
    p = build_payload(analyze(ohlcv.iloc[:90]), "DEMO")
    assert p["confidence"]["level"] == "không áp dụng" and p["levels"] == []


# ---------------------------------------------------------------- validator

def test_template_passes_validator(payload_c: dict, ohlcv: pd.DataFrame) -> None:
    assert validate_explanation(template_explanation(payload_c), payload_c) == []
    full = build_payload(analyze(ohlcv), "DEMO")                # pha E
    assert validate_explanation(template_explanation(full), full) == []


def test_good_explanation_passes(payload_c: dict) -> None:
    assert validate_explanation(good_explanation(payload_c), payload_c) == []


def test_invented_number_rejected(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["summary"] += " Mục tiêu giá 88,88."
    errs = validate_explanation(e, payload_c)
    assert any("88,88" in x for x in errs)


def test_invented_date_rejected(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["risks"].append("Có thể giảm trước 15/12/2030.")
    assert any("15/12/2030" in x for x in validate_explanation(e, payload_c))


@pytest.mark.parametrize("text", ["volume 600.000 cp", "volume 0,6 triệu cp", "close_pos 0,29", "2023-09-05", "05/09/2023",
                                  "TB20 ATR14 TR#0", "3 phiên"])
def test_grounded_formats(payload_c: dict, text: str) -> None:
    a, d = allowed_values(payload_c)
    assert ungrounded(text, a, d) == []


def test_unknown_or_wrong_level_rejected(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["confirmation_scenarios"][0]["level_id"] = "invalidate_0"
    errs = validate_explanation(e, payload_c)
    assert any("không phải 'confirm'" in x for x in errs) and any("confirm_0" in x for x in errs)
    e = good_explanation(payload_c)
    e["invalidation_scenarios"].append({"level_id": "invalidate_9", "narrative": "x"})
    assert any("invalidate_9" in x for x in validate_explanation(e, payload_c))


def test_missing_level_coverage_rejected(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["invalidation_scenarios"] = []
    assert any("invalidate_0" in x for x in validate_explanation(e, payload_c))


def test_unknown_event_rejected(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["evidence_notes"].append({"event_id": "ev_99", "comment": "x"})
    assert any("ev_99" in x for x in validate_explanation(e, payload_c))


def test_wrong_phase_and_confidence_rejected(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["summary"] = e["summary"].replace("pha C", "pha D")
    e["confidence_explanation"] = "Mức tin cậy thấp."
    errs = validate_explanation(e, payload_c)
    assert any("pha C" in x for x in errs) and any("mức tin cậy" in x for x in errs)


def test_schema_errors(payload_c: dict) -> None:
    assert validate_explanation([], payload_c) == ["Đầu ra không phải JSON object"]
    e = good_explanation(payload_c)
    del e["risks"]
    e["extra"] = 1
    errs = validate_explanation(e, payload_c)
    assert any("risks" in x for x in errs) and any("extra" in x for x in errs)


# ---------------------------------------------------------------- điều phối

def test_explain_llm_success(payload_c: dict, tmp_path) -> None:
    client = FakeClient([json.dumps(good_explanation(payload_c))])
    res = explain(payload_c, client, cache_dir=tmp_path)
    assert res.source == "llm" and res.attempts == 1 and res.errors == []
    call = client.calls[0]
    assert call["schema"] == OUTPUT_SCHEMA and "<payload>" in call["user"] and "Chỉ dùng con số" in call["system"]


def test_explain_retry_with_feedback(payload_c: dict) -> None:
    bad = good_explanation(payload_c)
    bad["summary"] += " Mục tiêu 88,88."
    client = FakeClient([json.dumps(bad), json.dumps(good_explanation(payload_c))])
    res = explain(payload_c, client)
    assert res.source == "llm" and res.attempts == 2
    assert "88,88" in client.calls[1]["user"] and "KHÔNG đạt kiểm tra" in client.calls[1]["user"]


def test_explain_falls_back_to_template(payload_c: dict) -> None:
    client = FakeClient(["không phải json", LLMError("timeout")])
    res = explain(payload_c, client)
    assert res.source == "template" and len(res.errors) == 2
    assert validate_explanation(res.explanation, payload_c) == []


def test_explain_without_client(payload_c: dict) -> None:
    res = explain(payload_c, None, no_llm_reason="thiếu key")
    assert res.source == "template" and res.errors == ["Không gọi LLM: thiếu key"]


def test_explain_cache(payload_c: dict, tmp_path) -> None:
    explain(payload_c, FakeClient([json.dumps(good_explanation(payload_c))]), cache_dir=tmp_path)
    client2 = FakeClient([])
    res = explain(payload_c, client2, cache_dir=tmp_path)
    assert res.source == "cache" and client2.calls == []
    changed = copy.deepcopy(payload_c)
    changed["as_of"] = "2099-01-01"                      # payload khác -> không dùng cache
    with pytest.raises(Exception):
        explain(changed, FakeClient([]), cache_dir=tmp_path, max_attempts=0).explanation["x"]


# ----------------------------------------------------------- Anthropic client

def test_anthropic_client_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class _Messages:
        def create(self, **kw):
            captured.update(kw)
            block = types.SimpleNamespace(type="text", text='{"ok": 1}')
            return types.SimpleNamespace(content=[block], stop_reason="end_turn")

    class _Anthropic:
        def __init__(self, api_key, timeout):
            captured["api_key"] = api_key
            self.messages = _Messages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_Anthropic))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    out = AnthropicClient().complete_json("sys", "user", OUTPUT_SCHEMA)
    assert out == '{"ok": 1}'
    assert captured["model"] == "claude-sonnet-5-5" and captured["system"] == "sys"
    assert captured["output_config"] == {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}}
    assert "tool_choice" not in captured


def test_anthropic_client_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=object))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        AnthropicClient()


def test_anthropic_client_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Anthropic:
        def __init__(self, **_):
            self.messages = types.SimpleNamespace(
                create=lambda **kw: types.SimpleNamespace(content=[], stop_reason="max_tokens"))

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_Anthropic))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    with pytest.raises(LLMError, match="max_tokens"):
        AnthropicClient().complete_json("s", "u", {})


# ------------------------------------------------------------------- HTML

def test_render_html_escapes_and_shows_levels(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["risks"].append("<script>alert(1)</script>")
    page = render_html(payload_c, e, source="llm", model="m")
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    price = vn(payload_c["levels"][0]["price"])
    assert price in page and "không phải lời khuyên đầu tư" in page and "Pha C" in page


def test_render_html_template_notes(payload_c: dict) -> None:
    page = render_html(payload_c, template_explanation(payload_c), source="template", errors=["Không gọi LLM: thiếu key"])
    assert "mẫu không dùng LLM" in page and "thiếu key" in page


# ------------------------------------------------- prompt v2: quy tắc trình bày

from wyckoff.agent.validate import MAX_SCENARIO_CHARS, style_issues  # noqa: E402


@pytest.mark.parametrize("text,needle", [
    ("Spring có vol_ratio 2,12", "vol_ratio"),
    ("avg_vol_ratio_5d là 1,45", "avg_vol_ratio_5d"),
    ("xem confirm_0", "confirm_0"),
    ("Test ngày 2026-10-09", "ISO"),
    ("đang ở phase C", "'pha'"),
])
def test_style_issues_detected(text: str, needle: str) -> None:
    assert any(needle in x for x in style_issues(text))


def test_style_allows_readable_text() -> None:
    assert style_issues("Spring 02/10/2026 volume 2,12x TB20, biên độ 1,45 ATR, close_pos 0,82; pha C, TB20, ATR14") == []


def test_style_errors_block_explanation(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["context_assessment"] += " spread_atr cao."
    assert any("spread_atr" in x for x in validate_explanation(e, payload_c))


def test_summary_must_say_pha_not_phase(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["summary"] = e["summary"].replace("pha C", "phase C")
    errs = validate_explanation(e, payload_c)
    assert any("'pha C'" in x for x in errs) and any("'phase'" in x for x in errs)


def test_long_scenario_rejected(payload_c: dict) -> None:
    e = good_explanation(payload_c)
    e["confirmation_scenarios"][0]["narrative"] = "Nếu có SOS thì chuyển pha D. " * 20
    assert any(f"tối đa {MAX_SCENARIO_CHARS}" in x for x in validate_explanation(e, payload_c))


def test_template_has_no_iso_dates_or_field_names(ohlcv: pd.DataFrame) -> None:
    for cut in (SPRING_CONFIRM_IDX + 5, len(ohlcv)):
        p = build_payload(analyze(ohlcv.iloc[:cut]), "DEMO")
        t = template_explanation(p)
        texts = [t["summary"], t["phase_assessment"], t["context_assessment"], t["market_assessment"],
                 t["confidence_explanation"], *t["risks"]]
        assert all(style_issues(x) == [] for x in texts)


def test_prompt_rules_present() -> None:
    from wyckoff.agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT

    assert PROMPT_VERSION == "7"
    assert "market_assessment" in SYSTEM_PROMPT and "CHỈ là tham khảo" in SYSTEM_PROMPT
    assert "dd/mm/yyyy" in SYSTEM_PROMPT and "vol_ratio 2,12 -> \"volume 2,12x TB20\"" in SYSTEM_PROMPT
    assert "tối đa 2 câu" in SYSTEM_PROMPT
