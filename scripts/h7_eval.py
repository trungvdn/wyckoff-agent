"""Chấm H7 theo tiêu chí chốt trước (docs/h7-preregistration.md).

    python scripts/parallel_study.py --cache-dir output/h7/cache --out output/h7/base
    python scripts/parallel_study.py --cache-dir output/h7/cache --config config/h7a.yaml --out output/h7/h7a
    python scripts/parallel_study.py --cache-dir output/h7/cache --config config/h7b.yaml --out output/h7/h7b
    python scripts/h7_reference.py --cache-dir output/h7/cache --out output/h7/reference.csv
    python scripts/h7_eval.py --base output/h7/base --h7a output/h7/h7a --h7b output/h7/h7b --reference output/h7/reference.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from wyckoff.backtest.oos import evaluate_hypothesis, render_hypothesis  # noqa: E402

LEVELS = ["thấp", "trung bình", "cao"]


def changed_levels(base: pd.DataFrame, h: pd.DataFrame) -> str:
    keys = ["symbol", "kind", "t"]
    m = base[keys + ["confidence_level"]].merge(h[keys + ["confidence_level"]], on=keys, suffixes=("_b", "_h"))
    m = m[m["confidence_level_b"].isin(LEVELS)]
    return f"{int((m['confidence_level_b'] != m['confidence_level_h']).sum())} / {len(m)} tín hiệu đổi mức so với đối chứng"


def main() -> None:
    p = argparse.ArgumentParser()
    for k in ("base", "h7a", "h7b"):
        p.add_argument(f"--{k}", required=True)
    p.add_argument("--reference", default=None)
    p.add_argument("--out", default="output/h7/report.md")
    a = p.parse_args()
    sig = {k: pd.read_csv(Path(getattr(a, k)) / "signals.csv", low_memory=False) for k in ("base", "h7a", "h7b")}

    out = ["# Kết quả H7 – giai đoạn và cung cầu trong thang tin cậy", "",
           f"Mẫu: {sig['base']['symbol'].nunique()} mã. Dữ liệu đến {pd.to_datetime(sig['base']['signal_date']).max():%d/%m/%Y}. "
           "Đơn vị: bexcess (%), CI 90%. Đăng ký trước: docs/h7-preregistration.md.", ""]
    for name in ("h7a", "h7b"):
        out.append(render_hypothesis(evaluate_hypothesis(sig[name], sig["base"], name.upper())))
        out.append(f"- {changed_levels(sig['base'], sig[name])}.")
        out.append("")
    for name, s in sig.items():
        c = s[s["confidence_level"].isin(LEVELS)]
        out.append(f"- {name}: tín hiệu {len(c)}, phân bố mức: {c['confidence_level'].value_counts().to_dict()}")
    if a.reference:
        ref = pd.read_csv(a.reference)
        out += ["", "## Tham khảo (không dùng để chấm)", "", "Chênh = bexcess trừ nền (mọi phiên) cùng giai đoạn.", ""]
        for group in ("loại cấu trúc", "phiên chốt nhãn", "mức sức mạnh", "tín hiệu"):
            g = ref[ref["nhóm"] == group].drop(columns="nhóm")
            out += [f"### {group}", "", "```", g.to_string(index=False), "```", ""]
        nen = ref[ref["nhóm"] == "nền"].drop(columns=["nhóm", "chênh_20", "chênh_60"])
        out += ["### nền", "", "```", nen.to_string(index=False), "```", ""]
    text = "\n".join(out)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
