"""Báo cáo HTML cho event study."""
from __future__ import annotations

import html
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import BacktestConfig
from wyckoff.fmt import vn_num

_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;color:#1f2328;line-height:1.5}
h1{margin:0 0 4px} .meta{color:#57606a;font-size:14px;margin-bottom:12px} h2{font-size:18px;border-bottom:1px solid #d0d7de;padding-bottom:4px;margin-top:26px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0} th,td{border:1px solid #d0d7de;padding:4px 7px;text-align:right}
th{background:#f6f8fa} td.l,th.l{text-align:left} .pos{color:#1a7f37;font-weight:600}.neg{color:#cf222e}
.note{color:#57606a;font-size:13px} .warn{background:#fff8c5;border-left:4px solid #d4a72c;padding:8px 12px;margin:10px 0;font-size:14px}
footer{margin-top:28px;color:#57606a;font-size:13px;border-top:1px solid #d0d7de;padding-top:8px}
"""

COLS = {
    "attribute": "Thuộc tính", "bucket": "Nhóm", "factor": "Yếu tố", "points": "Điểm", "period": "Giai đoạn",
    "mean_b20": "LS vượt β 20p %", "edge_b20": "Chênh β 20p %", "edge_b20_lo": "CI thấp", "edge_b20_hi": "CI cao",
    "mean_b60": "LS vượt β 60p %", "edge_b60": "Chênh β 60p %", "edge_b60_lo": "CI thấp ", "edge_b60_hi": "CI cao ",
    "win_20": "Thắng 20p %", "win_60": "Thắng 60p %",
    "kind": "Tín hiệu", "confidence_level": "Tin cậy", "confidence_score": "Điểm", "horizon": "Phiên", "n": "n",
    "mean_ret": "LS TB %", "mean_excess": "LS vượt TB %", "median_excess": "LS vượt trung vị %", "win_rate": "Tỉ lệ thắng %",
    "edge_vs_base": "Chênh so với nền %", "edge_ci_lo": "CI thấp", "edge_ci_hi": "CI cao", "mfe": "MFE TB %", "mae": "MAE TB %",
}


def _cell(col: str, v: Any) -> str:
    if isinstance(v, str):
        return f"<td class='l'>{html.escape(v)}</td>"
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "<td>—</td>"
    if col in ("n", "horizon", "confidence_score", "points") or (isinstance(v, (int, np.integer))):
        return f"<td>{int(v)}</td>"
    cls = ""
    if col in ("edge_vs_base", "mean_excess", "edge_b20", "edge_b60"):
        cls = " class='pos'" if v > 0 else " class='neg'" if v < 0 else ""
    return f"<td{cls}>{vn_num(float(v), 2)}</td>"


def table(df: pd.DataFrame, cols: list[str] | None = None) -> str:
    if df is None or df.empty:
        return "<p class='note'>Không có dữ liệu.</p>"
    cols = cols or list(df.columns)
    head = "".join(f"<th class='l'>{html.escape(COLS.get(c, c))}</th>" if df[c].dtype == object else
                   f"<th>{html.escape(COLS.get(c, c))}</th>" for c in cols)
    body = "".join("<tr>" + "".join(_cell(c, r[c]) for c in cols) + "</tr>" for _, r in df.iterrows())
    return f"<table><tr>{head}</tr>{body}</table>"


def render_backtest_html(summary: dict[str, pd.DataFrame], meta: dict[str, Any], cfg: BacktestConfig) -> str:
    H = max(cfg.horizons) if 20 not in cfg.horizons else 20
    bk = summary["by_kind"]
    kind_main = bk[bk["horizon"] == H] if not bk.empty else bk
    kind_cols = ["kind", "n", "mean_ret", "mean_excess", "median_excess", "win_rate", "edge_vs_base", "edge_ci_lo",
                 "edge_ci_hi", "mfe", "mae"]
    all_h = "".join(f"<h3>{h} phiên</h3>" + table(bk[bk["horizon"] == h], kind_cols) for h in cfg.horizons if h != H)
    conf = summary["by_confidence"]
    conf_cols = ["confidence_level", "horizon", "n", "mean_ret", "mean_excess", "win_rate", "edge_vs_base", "edge_ci_lo", "edge_ci_hi"]
    warns = "".join(f"<div class='warn'>{html.escape(w[:300])}</div>" for w in meta.get("warnings", []))
    syms = ", ".join(meta.get("symbols", []))
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>Backtest Wyckoff {html.escape(meta.get('universe', ''))}</title>
<style>{_CSS}</style></head><body>
<h1>Event study: detector Wyckoff</h1>
<div class="meta">Rổ {html.escape(meta.get('universe', ''))} ({len(meta.get('symbols', []))} mã) · từ {html.escape(meta.get('start', ''))} đến {html.escape(meta.get('end', ''))}
 · {meta.get('n_signals', 0)} tín hiệu · chi phí khứ hồi {vn_num(cfg.cost_pct, 1)}% · vào lệnh ở open phiên sau phiên xác nhận</div>
{warns}
<div class="warn">Thiên lệch sống sót: rổ là danh sách hiện tại, các mã từng bị loại khỏi rổ không có mặt nên kết quả có thể đẹp hơn thực tế.
Tín hiệu của nhiều mã thường xảy ra cùng lúc (tương quan), nên khoảng tin cậy bootstrap lạc quan hơn thực tế. Đây là đo lường, không phải chiến lược.</div>
<h2>Nền (mọi phiên)</h2><p class="note">Lợi suất nếu "vào lệnh" ở mọi phiên của cùng các mã, cùng giai đoạn — mốc để so sánh.</p>
{table(summary['baseline'], ['horizon', 'n', 'mean_ret', 'mean_excess', 'median_excess', 'win_rate'])}
<h2>Theo loại tín hiệu – {H} phiên</h2><p class="note">LS vượt = lợi suất (đã trừ chi phí) − lợi suất chỉ số cùng kỳ.
Chênh so với nền = LS vượt TB của tín hiệu − LS vượt TB của nền; CI {int(cfg.ci * 100)}% bootstrap. Chỉ có ý nghĩa khi cả CI nằm trên (hoặc dưới) 0.</p>
{table(kind_main, kind_cols)}
<h2>Theo mức tin cậy (point-in-time)</h2><p class="note">Pha C, pha D, Spring, SOS; mức tin cậy tính lại tại ngày xác nhận chỉ bằng dữ liệu đến ngày đó.
Nếu mức tin cậy có giá trị, "cao" phải tốt hơn "trung bình" và "thấp".</p>
{table(conf, conf_cols)}
<h3>Theo điểm tin cậy – 20 phiên</h3>{table(summary['by_score'], ['confidence_score', 'n', 'mean_excess', 'win_rate'])}
<h2>Kịch bản xác nhận / vô hiệu</h2><p class="note">Khi mở pha B/C/D: close vượt mức xác nhận gần nhất phía trên giá trước, hay thủng mức vô hiệu gần nhất
phía dưới giá trước (tối đa {cfg.scenario_max_bars} phiên). Chỉ xét mức giá, không xét điều kiện volume.</p>
{table(summary['scenarios'])}
{_diagnostics_html(summary)}
<h2>Các khung khác</h2>{all_h}
<p class="note">Mã: {html.escape(syms)}</p>
<footer>Công cụ hỗ trợ phân tích, không phải lời khuyên đầu tư. Tạo ngày {date.today():%d/%m/%Y}.</footer></body></html>"""


B_COLS = ["n", "mean_b20", "edge_b20", "edge_b20_lo", "edge_b20_hi", "win_20", "mean_b60", "edge_b60", "edge_b60_lo",
          "edge_b60_hi", "win_60"]


def _diagnostics_html(summary: dict[str, pd.DataFrame]) -> str:
    if "by_kind_beta" not in summary:
        return ""
    parts = ["<h2>Chẩn đoán 1 – Lợi suất điều chỉnh beta</h2><p class='note'>LS vượt β = lợi suất − beta × lợi suất chỉ số cùng kỳ; "
             "beta tính tại ngày tín hiệu từ 250 phiên trước (không nhìn trước). Nền tính cùng cách. Nếu lợi thế của SC/PS chỉ là beta, "
             "cột Chênh β sẽ co về 0.</p>", table(summary["by_kind_beta"], ["kind"] + B_COLS)]
    if "by_kind_period" in summary:
        parts += ["<h2>Chẩn đoán 2 – Độ ổn định theo giai đoạn</h2><p class='note'>Cùng phép đo, tách 2 giai đoạn; nền tính riêng từng giai đoạn. "
                  "Tín hiệu đáng tin phải cùng dấu ở cả hai giai đoạn.</p>",
                  table(summary["by_kind_period"], ["kind", "period"] + B_COLS)]
    if "by_factor" in summary:
        parts += ["<h2>Chẩn đoán 3 – Đóng góp từng yếu tố tin cậy</h2><p class='note'>Pha C, pha D, Spring, SOS; nhóm theo điểm của từng "
                  "yếu tố tại ngày tín hiệu. Yếu tố có ích: điểm cao hơn → Chênh β cao hơn.</p>",
                  table(summary["by_factor"], ["factor", "points"] + B_COLS)]
    for fam, title in (("spring", "Spring"), ("sos", "SOS"), ("sc", "SC")):
        key = f"breakdown_{fam}"
        if key in summary and not summary[key].empty:
            parts += [f"<h2>Chẩn đoán 4 – {title} theo thuộc tính</h2><p class='note'>Tìm nhóm {title} có / không có lợi thế. "
                      "Nhóm nhỏ (n &lt; 20) chỉ để gợi ý; mọi quy tắc mới phải kiểm tra ngoài mẫu.</p>",
                      table(summary[key], ["attribute", "bucket"] + B_COLS)]
    return "".join(parts)
