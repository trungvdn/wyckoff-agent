"""Báo cáo: diễn giải theo mẫu (không LLM, dùng làm dự phòng) và trang HTML hoàn chỉnh."""
from __future__ import annotations

import html
from datetime import date
from typing import Any

from wyckoff.agent.payload import stage_conclusion

DISCLAIMER = "Công cụ hỗ trợ phân tích, không phải lời khuyên đầu tư."

PHASE_TEXT = {
    "A": "giai đoạn dừng xu hướng giảm (SC đã xuất hiện, chờ ST)",
    "B": "giai đoạn xây dựng nguyên nhân trong range",
    "C": "giai đoạn kiểm tra cung (Spring đã xác nhận)",
    "D": "giai đoạn cầu chiếm ưu thế",
    "E": "giai đoạn giá rời range đi lên",
    "invalid": "cấu trúc tích lũy đã bị vô hiệu",
    "potential": "range đã thoát xuống, chờ xác nhận",
}
DIST_PHASE_TEXT = {
    "A": "giai đoạn dừng xu hướng tăng",
    "B": "giai đoạn xây dựng nguyên nhân trong range",
    "C": "giai đoạn kiểm tra cầu",
    "D": "giai đoạn cung chiếm ưu thế",
    "E": "giai đoạn giá rời range đi xuống",
}


def vn(x: float | None, d: int = 2) -> str:
    if x is None:
        return "n/a"
    s = f"{x:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def vn_date(s: str | None) -> str:
    if not s:
        return "n/a"
    y, m, d = s.split("-")
    return f"{d}/{m}/{y}"


def vn_dates_in(text: str) -> str:
    """Đổi mọi ngày ISO trong chuỗi do code sinh sang dd/mm/yyyy."""
    import re

    return re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: f"{m[3]}/{m[2]}/{m[1]}", text)


TREND_VN = {"uptrend": "tăng", "downtrend": "giảm", "sideways": "đi ngang", None: "chưa xác định"}


def template_market(m: dict[str, Any] | None) -> str:
    if not m:
        return "Không có dữ liệu thị trường."
    b = m["benchmark"]
    parts = [f"{b} xu hướng {TREND_VN.get(m['trend'], m['trend'])}: close {vn(m['index_close'])}, "
             f"SMA50 {vn(m['sma_fast'])}, SMA200 {vn(m['sma_slow'])}."]
    rets = [(k.split("_")[1].rstrip("d"), v) for k, v in m.items() if k.startswith("return_") and v is not None]
    if rets:
        parts.append("Chỉ số thay đổi " + ", ".join(f"{w} phiên {vn(v, 1)}%" for w, v in rets)
                     + f"; cách đỉnh {m['params']['drawdown_lookback']} phiên {vn(m['drawdown_from_high_pct'], 1)}%.")
    rs = m["rs"]
    rs_bits = [f"RS {k.split('_')[2].rstrip('d')} phiên {vn(v, 1)}%" for k, v in rs.items()
               if k.startswith("rs_change_") and v is not None]
    if rs_bits:
        above = rs.get("rs_above_sma")
        tail = "" if above is None else (", RS trên SMA50" if above else ", RS dưới SMA50")
        parts.append("Sức mạnh tương đối: " + ", ".join(rs_bits) + tail + ".")
    d = m["divergence"]
    if d.get("bullish_divergence"):
        parts.append(f"Có phân kỳ đáy: {b} tạo đáy {vn(d['index_recent_low'])} thấp hơn {vn(d['index_prior_low'])}, "
                     f"cổ phiếu giữ đáy {vn(d['stock_recent_low'])} so với {vn(d['stock_prior_low'])}.")
    al = [a for a in m["event_alignment"] if a["index_change_pct"] is not None]
    if al:
        parts.append("Trong phiên sự kiện: " + "; ".join(
            f"{a['event']} {vn_date(a['date'])} {b} {vn(a['index_change_pct'])}%" for a in al) + ".")
    ref = m.get("index_phase_reference")
    if ref and ref.get("phase"):
        parts.append(f"Pha Wyckoff của {b} (tham khảo): pha {ref['phase']}.")
    return " ".join(parts)


TREND_LEVEL = {"potential": "tiềm năng", "developing": "đang hình thành", "confirmed": "đã xác nhận", "rejected": "đã bị bác bỏ"}


def stage_text(cs: dict[str, Any], rv: dict[str, Any] | None = None) -> str:
    """Một câu mô tả giai đoạn hiện tại: cấu trúc còn hiệu lực nếu có, không thì payload.current_stage kèm mức của xu hướng."""
    rv = rv or {}
    trend = rv.get("trend") or {}
    st = rv.get("structure")
    if st:
        ev = st["evidence"]
        rejected = f" {trend['stage']} đã bị bác bỏ: {vn_dates_in(trend['reason'])}." if trend.get("status") == "rejected" else ""
        return f"Giai đoạn: {st['title']}, bằng chứng {ev['level']}: đạt {ev['met']} trên {ev['total']} điều kiện.{rejected}"
    level = f" {TREND_LEVEL[trend['status']]}" if trend.get("status") in TREND_LEVEL and cs["stage"] else ""
    stage = f" ({cs['stage']}{level})" if cs["stage"] else ""
    cand = f", giả thuyết {' hoặc '.join(cs['candidates'])}" if cs["candidates"] else ""
    strength = f" {cs['strength']['headline']}." if cs.get("strength") and trend.get("status") != "rejected" else ""
    dist = cs.get("distribution_phase") or {}
    dist_txt = f" Theo sơ đồ phân phối: pha {dist['phase']}." if dist.get("phase") and dist["phase"] != "invalid" else ""
    return f"Giai đoạn: {cs['structure_type']}{stage}{cand}.{strength}{dist_txt}"


def template_explanation(payload: dict[str, Any]) -> dict[str, Any]:
    """Diễn giải tất định từ payload; chỉ dùng số có trong payload nên luôn qua được validator."""
    cp = payload["current_phase"]
    cs = payload["current_stage"]
    rv = payload.get("revision") or {}
    # Có cấu trúc còn hiệu lực: pha và lý do theo lớp đánh giá lại, như trên thẻ giai đoạn
    conclusion = stage_conclusion(payload)
    ph = conclusion["phase"] if conclusion else cp["phase"]
    phase_reason = (conclusion["phase_reason"] or conclusion["reason"]) if conclusion else cp["reason"]
    phase_since = conclusion["phase_since"] if conclusion else cp["since"]
    is_dist = bool(conclusion) and conclusion["structure_type"] == "Distribution"
    waiting = not conclusion and ph == "invalid" and (rv.get("phase") or {}).get("phase") == "potential"
    conf = payload["confidence"]
    rb = payload["recent_bars"]
    # Sự kiện của nhật ký đã bị bác bỏ theo định nghĩa mới thì không dùng làm căn cứ
    evs = [e for e in payload["evidence_events"] if e.get("assessment") != "rejected"] if conclusion else payload["evidence_events"]
    sym = payload["symbol"]
    if conclusion and ph is None:
        summary = f"{sym}: Trading Range chưa có pha xác định, vùng {vn(cp['support'])} – {vn(cp['resistance'])}."
    elif waiting:
        # Range đã thoát xuống, Markdown còn tiềm năng: chưa thể nói cấu trúc đã vô hiệu
        summary = f"{sym}: TR#{cp['range_id']} (vùng {vn(cp['support'])} – {vn(cp['resistance'])}) đã thoát xuống từ {vn_date(cp['since'])}, chờ xác nhận."
    elif ph is None:
        summary = f"{sym}: chưa có cấu trúc Wyckoff nào được nhận diện tại {vn_date(payload['as_of'])}."
    else:
        rng = f" trong TR#{cp['range_id']} (vùng {vn(cp['support'])} – {vn(cp['resistance'])})" if cp["range_id"] is not None else ""
        tail = "Mức bằng chứng là độ đầy đủ của các điều kiện, không phải xác suất." if conclusion else f"Mức tin cậy theo quy tắc: {conf['level']}."
        texts = DIST_PHASE_TEXT if is_dist else PHASE_TEXT
        summary = (f"{sym} đang ở pha {ph} – {texts.get(ph, '')}{rng}, từ {vn_date(phase_since)}. "
                   f"Lý do: {vn_dates_in(phase_reason)}. {tail}")
    summary = f"{stage_text(cs, rv)} {summary}"
    ev_line = "; ".join(f"{e['kind']} {vn_date(e['date'])} (volume {vn(e['vol_ratio'])}x TB20, biên độ "
                        f"{vn(e['spread_atr'])} ATR, close_pos {vn(e['close_pos'])})" for e in evs)
    if conclusion:
        phase_assessment = f"Pha {ph}: {vn_dates_in(phase_reason)}." if ph else f"Chưa có pha: {vn_dates_in(conclusion['reason'])}."
        if ev_line:
            phase_assessment += f" Sự kiện của cấu trúc: {ev_line}."
    elif waiting:
        phase_assessment = f"Range đã thoát xuống, chờ xác nhận: {vn_dates_in(cp['reason'])}."
    else:
        phase_assessment = (f"Pha {ph} được xác định bởi chuỗi sự kiện của cấu trúc: {ev_line}." if evs
                            else f"Pha {ph}: {vn_dates_in(cp['reason'])}.")
    ctx = [f"Căn cứ giai đoạn: {vn_dates_in(conclusion['reason'] if conclusion else cs['reason'])}."]
    if cs.get("strength") and not conclusion:      # sức mạnh của xu hướng, không dùng khi xu hướng đó đã bị bác bỏ
        ctx += [sig["text"] for sig in cs["strength"]["signals"]]
    if cp["range_context"]:
        pr = f" (lợi suất {vn(cp['range_prior_return_pct'], 1)}% trước range)" if cp["range_prior_return_pct"] is not None else ""
        ctx.append(f"Bối cảnh range: {cp['range_context']}{pr}.")
    if not is_dist and not any(e["kind"] == "SC" for e in evs + (rv.get("events") or [])):
        ctx.append("Không có SC mở cấu trúc nên pha A không xác định; cấu trúc dựa trên range dựng từ swing.")
    ctx.append(f"Phiên gần nhất {vn_date(rb['last_date'])}: close {vn(rb['last_close'])}, volume {vn(rb['last_vol_ratio'])}x TB20, "
               f"close_pos {vn(rb['last_close_pos'])}, biên độ {vn(rb['last_spread_atr'])} ATR.")
    ds, dr = rb.get("distance_to_support_atr"), rb.get("distance_to_resistance_atr")
    if ds is not None:
        sup_txt = f"cách support {vn(ds)} ATR" if ds >= 0 else f"dưới support {vn(abs(ds))} ATR"
        res_txt = "" if dr is None else (f", cách resistance {vn(dr)} ATR" if dr >= 0 else f", đã vượt resistance {vn(abs(dr))} ATR")
        ctx.append(f"Giá {sup_txt}{res_txt}.")
    notes = [{"event_id": e["id"], "comment": f"{e['kind']} {vn_date(e['date'])}: volume {vn(e['vol_ratio'])}x TB20, "
                                              f"biên độ {vn(e['spread_atr'])} ATR, close_pos {vn(e['close_pos'])}."} for e in evs]
    conf_sc = [{"level_id": lv["id"], "narrative": f"{lv['label']}: nếu điều kiện trong bảng được thỏa, cấu trúc tiến sang bước tiếp theo."}
               for lv in payload["levels"] if lv["type"] == "confirm"]
    inv_sc = [{"level_id": lv["id"], "narrative": f"{lv['label']}: nếu xảy ra, kịch bản tích lũy hiện tại không còn hiệu lực."}
              for lv in payload["levels"] if lv["type"] == "invalidate"]
    risks = [vn_dates_in(w) for w in payload["warnings"]] or ["Không có cảnh báo tự động."]
    factors = "; ".join(f"{vn_dates_in(f['factor'])} ({'+' if f['points'] > 0 else ''}{f['points']})" for f in conf["factors"])
    return {
        "summary": summary,
        "phase_assessment": phase_assessment,
        "context_assessment": " ".join(ctx),
        "market_assessment": template_market(payload.get("market")),
        "evidence_notes": notes,
        "confirmation_scenarios": conf_sc,
        "invalidation_scenarios": inv_sc,
        "risks": risks,
        "confidence_explanation": f"Mức tin cậy {conf['level']}: {factors}." if conf["factors"] else f"Mức tin cậy: {conf['level']}.",
    }


# ------------------------------------------------------------------------ HTML

_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1180px;margin:24px auto;padding:0 16px;color:#1f2328;line-height:1.55}
h1{margin:0 0 4px} .meta{color:#57606a;font-size:14px;margin-bottom:16px}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-weight:600;font-size:14px;margin-right:6px}
.ph{background:#ddf4ff;color:#0969da}.cf{background:#fff8c5;color:#7d4e00}.src{background:#eaeef2;color:#424a53}
section{margin:20px 0} h3{font-size:15px;margin:14px 0 6px} h2{font-size:18px;border-bottom:1px solid #d0d7de;padding-bottom:4px}
table{border-collapse:collapse;width:100%;font-size:14px} th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f6f8fa} td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.confirm{color:#1a7f37;font-weight:600}.invalidate{color:#cf222e;font-weight:600}
.warn{background:#fff8c5;border-left:4px solid #d4a72c;padding:8px 12px;margin:8px 0}
.note{color:#57606a;font-size:13px} footer{margin-top:28px;color:#57606a;font-size:13px;border-top:1px solid #d0d7de;padding-top:8px}
"""


def _e(s: Any) -> str:
    return html.escape(str(s))


def _market_html(m: dict[str, Any] | None, text: str, rs_chart_html: str | None) -> str:
    if not m:
        return f"<section><h2>Bối cảnh thị trường</h2><p>{_e(text)}</p></section>"
    rs = m["rs"]
    d = m["divergence"]
    ref = m.get("index_phase_reference") or {}
    rows = [
        ("Chỉ số so sánh", f"{m['benchmark']} (đến {vn_date(m['index_last_date'])})"),
        ("Xu hướng", TREND_VN.get(m["trend"], m["trend"])),
        ("Close / SMA50 / SMA200", f"{vn(m['index_close'])} / {vn(m['sma_fast'])} / {vn(m['sma_slow'])}"),
        ("Độ dốc SMA50 (20 phiên)", f"{vn(m['sma_fast_slope_pct'])}%"),
    ] + [(f"Thay đổi {k.split('_')[1].rstrip('d')} phiên", f"{vn(v, 1)}%") for k, v in m.items()
         if k.startswith("return_") and v is not None] + [
        (f"Cách đỉnh {m['params']['drawdown_lookback']} phiên", f"{vn(m['drawdown_from_high_pct'], 1)}%"),
    ] + [(f"RS {k.split('_')[2].rstrip('d')} phiên", f"{vn(v, 1)}%") for k, v in rs.items()
         if k.startswith("rs_change_") and v is not None] + [
        ("RS so với SMA50", "—" if rs.get("rs_above_sma") is None else ("trên" if rs["rs_above_sma"] else "dưới")),
        ("Phân kỳ đáy", "có" if d.get("bullish_divergence") else "không"),
        ("Pha Wyckoff chỉ số (tham khảo)", f"{ref.get('phase') or '—'}" + (f" – {ref.get('reason')}" if ref.get("reason") else "")),
    ]
    tbl = "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in rows)
    al = "".join(
        f"<tr><td>{_e(a['event'])}</td><td>{_e(vn_date(a['date']))}</td><td class='num'>"
        f"{_e('—' if a['index_change_pct'] is None else vn(a['index_change_pct']) + '%')}</td>"
        f"<td>{_e(TREND_VN.get(a['index_trend'], a['index_trend']))}</td><td>{_e(a['index_phase'] or '—')}</td></tr>"
        for a in m["event_alignment"]
    )
    warn = "".join(f"<div class='warn'>{_e(w)}</div>" for w in m.get("warnings", []))
    al_tbl = ("<h3>Chỉ số trong phiên sự kiện</h3><table><tr><th>Sự kiện</th><th>Ngày</th><th>Chỉ số</th>"
              f"<th>Xu hướng chỉ số</th><th>Pha chỉ số (tham khảo)</th></tr>{al}</table>") if al else ""
    chart = f"<h3>Sức mạnh tương đối (RS)</h3>{rs_chart_html}" if rs_chart_html else ""
    return (f"<section><h2>Bối cảnh thị trường</h2>{warn}<p>{_e(text)}</p>"
            f"<table>{tbl}</table>{al_tbl}{chart}</section>")


def render_html(
    payload: dict[str, Any], explanation: dict[str, Any], *, source: str, model: str | None = None,
    errors: list[str] | None = None, chart_html: str | None = None, rs_chart_html: str | None = None,
) -> str:
    conclusion = stage_conclusion(payload)
    cp = payload["current_phase"]
    conf = payload["confidence"]
    narr = {s["level_id"]: s["narrative"] for s in explanation["confirmation_scenarios"] + explanation["invalidation_scenarios"]}
    notes = {n["event_id"]: n["comment"] for n in explanation["evidence_notes"]}
    src_label = {"llm": f"LLM ({model})", "cache": f"LLM ({model}, cache)", "template": "mẫu không dùng LLM"}.get(source, source)

    rows_lv = "".join(
        f"<tr><td class='{_e(lv['type'])}'>{'Xác nhận' if lv['type'] == 'confirm' else 'Vô hiệu'}</td>"
        f"<td>{_e(lv['label'])}</td><td class='num'>{_e(vn(lv['price']))}</td><td>{_e(lv['condition'])}</td>"
        f"<td>{_e(narr.get(lv['id'], ''))}</td></tr>"
        for lv in payload["levels"]
    ) or "<tr><td colspan='5'>Không có mức giá (cấu trúc đã vô hiệu hoặc chưa có cấu trúc).</td></tr>"
    rows_ev = "".join(
        f"<tr><td>{_e(ev['kind'])}</td><td>{_e(vn_date(ev['date']))}</td><td>{_e(vn_date(ev['confirmed_date']))}</td>"
        f"<td class='num'>{_e(vn(ev['close']))}</td><td class='num'>{_e(vn(ev['volume'], 0))}</td>"
        f"<td class='num'>{_e(vn(ev['vol_ratio']))}x</td><td class='num'>{_e(vn(ev['spread_atr']))}</td>"
        f"<td class='num'>{_e(vn(ev['close_pos']))}</td><td>{_e(notes.get(ev['id'], ''))}</td></tr>"
        for ev in payload["evidence_events"]
    ) or "<tr><td colspan='9'>Không có sự kiện.</td></tr>"
    rows_cf = "".join(
        f"<tr><td>{_e(f['factor'])}</td><td class='num'>{'+' if f['points'] > 0 else ''}{f['points']}</td><td>{_e(f['evidence'])}</td></tr>"
        for f in conf["factors"]
    )
    warns = "".join(f"<div class='warn'>{_e(w)}</div>" for w in payload["warnings"])
    risks = "".join(f"<li>{_e(r)}</li>" for r in explanation["risks"])
    err_html = ""
    if errors:
        err_html = ("<section><h2>Ghi chú kiểm soát</h2><p class='note'>Báo cáo dùng " + _e(src_label)
                    + " vì các lý do sau:</p><ul class='note'>"
                    + "".join(f"<li>{_e(x)}</li>" for x in errors[:20]) + "</ul></section>")
    rng = f"TR#{cp['range_id']} · {vn(cp['support'])} – {vn(cp['resistance'])} · bối cảnh {cp['range_context']}" \
        if cp["range_id"] is not None else "chưa gắn range"
    return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(payload['symbol'])} – Wyckoff {_e(payload['as_of'])}</title><style>{_CSS}</style></head><body>
<h1>{_e(payload['symbol'])} · phân tích Wyckoff</h1>
<div class="meta">Dữ liệu đến {_e(vn_date(payload['as_of']))} · {_e(payload['data']['bars'])} phiên · giá {_e(payload['price_unit'])} · {_e(rng)}</div>
<span class="badge ph">{_e(conclusion['title']) if conclusion else _e(payload['current_stage']['structure_type'])}{'' if conclusion else ' từ ' + _e(vn_date(payload['current_stage']['since'])) if payload['current_stage']['since'] else ''}</span>
<span class="badge ph">Pha {_e((conclusion['phase'] if conclusion else cp['phase']) or '—')}{(' từ ' + _e(vn_date(conclusion['phase_since'] if conclusion else cp['since']))) if (conclusion['phase_since'] if conclusion else cp['since']) else ''}</span>
<span class="badge cf">Tin cậy: {_e(conf['level'])}</span><span class="badge src">Diễn giải: {_e(src_label)}</span>
{warns}
<section><h2>Tóm tắt</h2><p>{_e(explanation['summary'])}</p></section>
<section><h2>Đánh giá pha</h2><p>{_e(explanation['phase_assessment'])}</p></section>
<section><h2>Bối cảnh và chất lượng bằng chứng</h2><p>{_e(explanation['context_assessment'])}</p></section>
{_market_html(payload.get("market"), explanation.get("market_assessment", ""), rs_chart_html)}
<section><h2>Kịch bản xác nhận / vô hiệu</h2><p class="note">Mức giá và điều kiện do code tính; cột cuối là diễn giải.</p>
<table><tr><th>Loại</th><th>Kịch bản</th><th>Mức giá</th><th>Điều kiện định lượng</th><th>Diễn giải</th></tr>{rows_lv}</table></section>
<section><h2>Bằng chứng</h2><table><tr><th>Sự kiện</th><th>Ngày</th><th>Xác nhận</th><th>Close</th><th>Volume</th>
<th>Vol/TB20</th><th>Biên độ/ATR</th><th>close_pos</th><th>Nhận xét</th></tr>{rows_ev}</table></section>
<section><h2>Rủi ro</h2><ul>{risks}</ul></section>
<section><h2>Mức tin cậy (quy tắc)</h2><p>{_e(explanation['confidence_explanation'])}</p>
<table><tr><th>Yếu tố</th><th>Điểm</th><th>Bằng chứng</th></tr>{rows_cf}</table></section>
{('<section><h2>Biểu đồ</h2>' + chart_html + '</section>') if chart_html else ''}
{err_html}
<footer>{_e(DISCLAIMER)} Tạo ngày {date.today():%d/%m/%Y}. Mọi con số do code tính từ dữ liệu; LLM chỉ diễn giải và đã qua kiểm tra tự động (không có số/ngày ngoài dữ liệu).</footer>
</body></html>"""
