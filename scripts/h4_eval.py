"""Chấm H4 theo tiêu chí chốt trước (docs/h4-preregistration.md).

    python scripts/h4_eval.py --base output/h4/base --h4a output/h4/h4a --h4b output/h4/h4b --out output/h4/report.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from wyckoff.backtest.oos import evaluate_hypothesis, render_hypothesis  # noqa: E402

EXCLUDE = {"SZC"}   # mã sinh ra giả thuyết


def _kinds(sig: pd.DataFrame, kinds: list[str]) -> pd.DataFrame:
    s = sig[(sig["untradable"] == False) & (~sig["symbol"].isin(EXCLUDE))]  # noqa: E712
    rows = []
    for k in kinds:
        g = s[s["kind"] == k]
        rows.append({"kind": k, "n": len(g), "mã": g["symbol"].nunique(),
                     **{f"bexcess_{h}": round(g[f"bexcess_{h}"].mean(), 2) for h in (20, 60)}})
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    for k in ("base", "h4a", "h4b"):
        p.add_argument(f"--{k}", required=True)
    p.add_argument("--out", default="output/h4/report.md")
    a = p.parse_args()
    sig = {k: pd.read_csv(Path(getattr(a, k)) / "signals.csv") for k in ("base", "h4a", "h4b")}

    out = ["# Kết quả H4", "", f"Mẫu: {sig['base'].loc[~sig['base']['symbol'].isin(EXCLUDE), 'symbol'].nunique()} mã, loại SZC. "
           "Đơn vị: bexcess (%), CI 90%.", ""]
    for name in ("h4b", "h4a"):
        v = evaluate_hypothesis(sig[name], sig["base"], name.upper(), exclude=EXCLUDE)
        out.append(render_hypothesis(v))
    kinds = ["SC", "AR", "ST", "SOS", "SOS (reclaim)", "LPS", "UTAD", "Spring (volume thấp)", "Spring (shakeout)",
             "pha B", "pha C", "pha D", "pha E", "pha invalid"]
    out += ["## Tham khảo theo loại tín hiệu", ""]
    t = _kinds(sig["base"], kinds).merge(_kinds(sig["h4b"], kinds), on="kind", suffixes=("_base", "_h4b"))
    out += ["```", t.to_string(index=False), "```", ""]
    for name, s in sig.items():
        c = s[s["confidence_level"].notna() & (~s["symbol"].isin(EXCLUDE))]
        out.append(f"{name}: tín hiệu {len(c)}, phân bố mức: {c['confidence_level'].value_counts().to_dict()}")
    text = "\n".join(out)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
