"""Kiểm soát đầu ra LLM: đúng schema, đúng ID, không có con số / ngày ngoài payload."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable

from wyckoff.agent.prompts import OUTPUT_SCHEMA, TEXT_FIELDS

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_VN_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")
_NUMBER = re.compile(r"(?<![A-Za-z_#\d])[-−]?\d+(?:[.,]\d+)*")
_SCALE = re.compile(r"\s*(triệu|tỷ|nghìn)\b", re.IGNORECASE)
_SCALES = {"triệu": 1e6, "tỷ": 1e9, "nghìn": 1e3}
_ABS_TOL = 0.011          # giá, tỉ số: phải khớp tới 2 chữ số thập phân
_REL_TOL = 0.006          # chỉ cho số lớn (volume viết tắt "27,85 triệu")
_REL_MIN = 1000.0
_FREE_INTS = set(range(0, 11))     # số đếm nhỏ (3 phiên, 2 lần...) luôn được phép
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_ALLOWED_SNAKE = {"close_pos"}
_PHASE_EN = re.compile(r"\bphase\b", re.IGNORECASE)
MAX_SCENARIO_CHARS = 400


# ---------------------------------------------------------------- tập giá trị hợp lệ

def _walk(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


def _parse_number(tok: str) -> list[float]:
    """Một cách đọc duy nhất cho mỗi token:
    - nhiều dấu '.'                -> phân cách nghìn kiểu VN (25.465.100)
    - nhiều dấu ','                -> phân cách nghìn kiểu EN (27,847,568 – chép từ chuỗi do code sinh)
    - có cả '.' và ','             -> dấu xuất hiện sau cùng là dấu thập phân
    - một '.' theo sau đúng 3 số   -> nghìn kiểu VN (1.500 = 1500); còn lại là thập phân (2.12)
    - một ','                      -> thập phân kiểu VN (22,74)
    """
    t = tok.replace("−", "-")
    dots, commas = t.count("."), t.count(",")
    if dots and commas:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif dots > 1:
        t = t.replace(".", "")
    elif commas > 1:
        t = t.replace(",", "")
    elif dots == 1:
        if re.fullmatch(r"-?\d{1,3}\.\d{3}", t):
            t = t.replace(".", "")
    elif commas == 1:
        t = t.replace(",", ".")
    try:
        return [float(t)]
    except ValueError:
        return []


def allowed_values(payload: dict[str, Any]) -> tuple[list[float], set[date]]:
    nums: list[float] = []
    dates: set[date] = set()
    for v in _walk(payload):
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            nums.append(float(v))
        elif isinstance(v, str):
            for m in _ISO_DATE.finditer(v):
                dates.add(date(int(m[1]), int(m[2]), int(m[3])))
            stripped = _ISO_DATE.sub(" ", v)
            for m in _NUMBER.finditer(stripped):
                nums.extend(_parse_number(m.group()))
    extra = [x * 100 for x in nums if abs(x) <= 1.5] + [abs(x) for x in nums]
    return sorted(set(nums + extra)), dates


def _matches(x: float, allowed: list[float]) -> bool:
    if x.is_integer() and int(x) in _FREE_INTS:
        return True
    return any(abs(x - a) <= _ABS_TOL or (abs(a) >= _REL_MIN and abs(x - a) / abs(a) <= _REL_TOL) for a in allowed)


def ungrounded(text: str, allowed: list[float], dates: set[date]) -> list[str]:
    """Các con số / ngày trong `text` không tìm thấy trong payload."""
    bad: list[str] = []
    for m in _ISO_DATE.finditer(text):
        if date(int(m[1]), int(m[2]), int(m[3])) not in dates:
            bad.append(m.group())
    text = _ISO_DATE.sub(" ", text)

    def _vn_date(m: re.Match[str]) -> str:
        d, mo, y = int(m[1]), int(m[2]), m[3]
        ok = any(dt.day == d and dt.month == mo and (y is None or dt.year == int(y)) for dt in dates)
        if not ok and 1 <= d <= 31 and 1 <= mo <= 12:
            bad.append(m.group())
        return " " if (1 <= d <= 31 and 1 <= mo <= 12) else m.group()

    text = _VN_DATE.sub(_vn_date, text)
    for m in _NUMBER.finditer(text):
        tok = m.group()
        scale = 1.0
        sm = _SCALE.match(text, m.end())
        if sm:
            scale = _SCALES[sm.group(1).lower()]
        cands = [v * scale for v in _parse_number(tok)]
        if not any(_matches(c, allowed) for c in cands):
            bad.append(tok + (sm.group(0) if sm else ""))
    return bad


# ------------------------------------------------------------------- kiểm tra

def style_issues(text: str) -> list[str]:
    """Lỗi trình bày: tên trường kỹ thuật, ngày ISO, 'phase' thay cho 'pha'."""
    out: list[str] = []
    snakes = sorted({m.group() for m in _SNAKE.finditer(text)} - _ALLOWED_SNAKE)
    if snakes:
        out.append(f"dùng tên trường kỹ thuật ({', '.join(snakes[:5])}); viết bằng từ đọc được")
    isos = [m.group() for m in _ISO_DATE.finditer(text)]
    if isos:
        out.append(f"ngày dạng ISO ({', '.join(isos[:3])}); dùng dd/mm/yyyy")
    if _PHASE_EN.search(text):
        out.append("dùng 'phase'; viết 'pha'")
    return out


def _schema_errors(expl: Any) -> list[str]:
    if not isinstance(expl, dict):
        return ["Đầu ra không phải JSON object"]
    errs = []
    req = OUTPUT_SCHEMA["required"]
    for k in req:
        if k not in expl:
            errs.append(f"Thiếu trường '{k}'")
    for k in expl:
        if k not in OUTPUT_SCHEMA["properties"]:
            errs.append(f"Trường không có trong schema: '{k}'")
    for k in TEXT_FIELDS:
        if k in expl and (not isinstance(expl[k], str) or not expl[k].strip()):
            errs.append(f"Trường '{k}' phải là chuỗi khác rỗng")
    for k, sub in (("evidence_notes", ("event_id", "comment")), ("confirmation_scenarios", ("level_id", "narrative")),
                   ("invalidation_scenarios", ("level_id", "narrative"))):
        items = expl.get(k, [])
        if not isinstance(items, list) or not all(isinstance(i, dict) and all(isinstance(i.get(s), str) for s in sub) for i in items):
            errs.append(f"Trường '{k}' sai cấu trúc (cần danh sách object có {sub})")
    if not isinstance(expl.get("risks", []), list) or not all(isinstance(r, str) for r in expl.get("risks", [])):
        errs.append("Trường 'risks' phải là danh sách chuỗi")
    return errs


def validate_explanation(expl: Any, payload: dict[str, Any]) -> list[str]:
    errs = _schema_errors(expl)
    if errs:
        return errs

    levels = {lv["id"]: lv["type"] for lv in payload.get("levels", [])}
    for section, typ in (("confirmation_scenarios", "confirm"), ("invalidation_scenarios", "invalidate")):
        used = [s["level_id"] for s in expl[section]]
        for lid in used:
            if lid not in levels:
                errs.append(f"{section}: level_id '{lid}' không có trong payload.levels")
            elif levels[lid] != typ:
                errs.append(f"{section}: level_id '{lid}' là loại '{levels[lid]}', không phải '{typ}'")
        expected = [i for i, t in levels.items() if t == typ]
        for lid in expected:
            if used.count(lid) != 1:
                errs.append(f"{section}: level '{lid}' phải xuất hiện đúng 1 lần (đang {used.count(lid)})")
        for s in expl[section]:
            if not s["narrative"].strip():
                errs.append(f"{section}: narrative của '{s['level_id']}' rỗng")

    event_ids = {e["id"] for e in payload.get("evidence_events", [])}
    for n in expl["evidence_notes"]:
        if n["event_id"] not in event_ids:
            errs.append(f"evidence_notes: event_id '{n['event_id']}' không có trong payload.evidence_events")

    phase = payload.get("current_phase", {}).get("phase")
    if phase and phase != "invalid" and not re.search(rf"\bpha\s+{re.escape(phase)}\b", expl["summary"], re.I):
        errs.append(f"summary phải nêu đúng pha hiện tại 'pha {phase}'")
    level = payload.get("confidence", {}).get("level")
    if level and level not in expl["confidence_explanation"]:
        errs.append(f"confidence_explanation phải nêu đúng mức tin cậy do code tính: '{level}'")

    for s in expl["confirmation_scenarios"] + expl["invalidation_scenarios"]:
        if len(s["narrative"]) > MAX_SCENARIO_CHARS:
            errs.append(f"scenario[{s['level_id']}]: diễn giải dài {len(s['narrative'])} ký tự (tối đa {MAX_SCENARIO_CHARS}, "
                        "tối đa 2 câu, không lặp điều kiện)")

    allowed, dates = allowed_values(payload)
    texts: list[tuple[str, str]] = [(k, expl[k]) for k in TEXT_FIELDS]
    texts += [(f"evidence_notes[{n['event_id']}]", n["comment"]) for n in expl["evidence_notes"]]
    texts += [(f"scenario[{s['level_id']}]", s["narrative"]) for s in expl["confirmation_scenarios"] + expl["invalidation_scenarios"]]
    texts += [(f"risks[{i}]", r) for i, r in enumerate(expl["risks"])]
    for where, t in texts:
        style = style_issues(t)
        if style:
            errs.append(f"{where}: {'; '.join(style)}")
        bad = ungrounded(t, allowed, dates)
        if bad:
            errs.append(f"{where}: số/ngày không có trong payload: {', '.join(bad[:6])}")
    return errs
