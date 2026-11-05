"""Chấm H6 theo tiêu chí chốt trước (docs/h6-preregistration.md).

    python scripts/parallel_study.py --out output/h6/base
    python scripts/parallel_study.py --config config/h6.yaml --out output/h6/h6
    python scripts/h6_eval.py --base output/h6/base --h6 output/h6/h6 --out output/h6/report.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from wyckoff.backtest.oos import evaluate_hypothesis, render_hypothesis  # noqa: E402

KINDS = ["UTAD", "UT", "pha invalid", "pha D", "pha E", "pha C", "pha B", "SOS", "LPS"]


def _kinds(sig: pd.DataFrame) -> pd.DataFrame:
    s = sig[sig["untradable"] == False]  # noqa: E712
    rows = []
    for k in KINDS:
        g = s[s["kind"] == k]
        rows.append({"kind": k, "n": len(g), "mã": g["symbol"].nunique(),
                     **{f"bexcess_{h}": round(g[f"bexcess_{h}"].mean(), 2) for h in (20, 60)}})
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    for k in ("base", "h6"):
        p.add_argument(f"--{k}", required=True)
    p.add_argument("--out", default="output/h6/report.md")
    a = p.parse_args()
    sig = {k: pd.read_csv(Path(getattr(a, k)) / "signals.csv") for k in ("base", "h6")}

    out = ["# Kết quả H6 – tách UT / UTAD, chờ yếu kém", "",
           f"Mẫu: {sig['base']['symbol'].nunique()} mã. Đơn vị: bexcess (%), CI 90%. Đăng ký trước: docs/h6-preregistration.md.", ""]
    for name in ("h6",):
        out.append(render_hypothesis(evaluate_hypothesis(sig[name], sig["base"], name.upper())))
    out += ["## Tham khảo theo loại tín hiệu (không dùng để chấm)", ""]
    t = _kinds(sig["base"])
    for name in ("h6",):
        t = t.merge(_kinds(sig[name]), on="kind", suffixes=("", f"_{name}"))
    out += ["```", t.to_string(index=False), "```", ""]
    for name, s in sig.items():
        c = s[s["confidence_level"].notna()]
        out.append(f"- {name}: tín hiệu {len(c)}, phân bố mức: {c['confidence_level'].value_counts().to_dict()}")
    text = "\n".join(out)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
