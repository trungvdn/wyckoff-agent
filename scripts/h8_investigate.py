"""Điều tra sau H8: vì sao range có Spring hay thoát xuống, range có UTAD hay thoát lên. Khám phá, không phải kiểm định đã đăng ký.

    python scripts/h8_investigate.py --cache-dir output/h8/cache --out output/h8/investigate

Bốn phép đo:
    1. Placebo: xáo trộn ngày giao dịch (từng ngày, hoặc theo khối 20 phiên) rồi chạy lại toàn bộ pipeline.
    2. Vị trí: tỷ lệ thoát lên theo vị trí giá trong range, so sánh sự kiện với phiên không có sự kiện cùng vị trí và tuổi range.
    3. Thời gian: tỷ lệ thoát theo khoảng cách từ sự kiện đến phiên thoát.
    4. Bối cảnh: các nhóm đúng và không đúng bối cảnh lý thuyết.
Mọi đặc trưng tại phiên t chỉ dùng dữ liệu <= t; hướng thoát và số phiên đến thoát là kết quả cần đo.
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore", category=FutureWarning)

from wyckoff.backtest.metrics import baseline_returns, rolling_beta  # noqa: E402
from wyckoff.config import Config  # noqa: E402
from wyckoff.data.cache import load_cache  # noqa: E402
from wyckoff.detectors.models import EventStatus, EventType  # noqa: E402
from wyckoff.market import align_index  # noqa: E402
from wyckoff.pipeline import analyze  # noqa: E402

INDEX_SYMBOLS = {"VNINDEX", "VNSMALLCAP", "VNMIDCAP", "VN30", "HNXINDEX", "UPCOMINDEX", "VNSML", "VNMID"}
MIN_BARS = 300
START = pd.Timestamp("2018-01-01")
SAMPLE_EVERY = 5
BOOT_N, BOOT_SEED = 1000, 7
POS_BINS = [-np.inf, 0.0, 0.2, 0.4, 0.6, 0.8, 1.0, np.inf]
POS_LABELS = ["<0", "0-0,2", "0,2-0,4", "0,4-0,6", "0,6-0,8", "0,8-1", ">1"]
AGE_BINS = [-1, 20, 50, 100, np.inf]


def shuffle_days(df: pd.DataFrame, seed: int, block: int = 1) -> pd.DataFrame:
    """Hoán vị các ngày (hoặc khối `block` ngày): giữ phân phối lợi suất, hình dạng nến, volume từng ngày; phá thứ tự thời gian."""
    rng = np.random.default_rng(seed)
    df = df[df["close"] > 0]      # vài mã có phiên close = 0 trong cache; tỷ lệ giá không xác định ở các phiên đó
    n = len(df)
    c = df["close"].to_numpy(dtype=float)
    prev = np.r_[c[0], c[:-1]]
    ret = c / prev
    o, h, lo = df["open"].to_numpy(float) / c, df["high"].to_numpy(float) / c, df["low"].to_numpy(float) / c
    v = df["volume"].to_numpy(dtype=float)
    starts = np.arange(0, n, block)
    order = np.concatenate([np.arange(s, min(s + block, n)) for s in rng.permutation(starts)])
    new_c = c[0] * np.cumprod(ret[order])
    return pd.DataFrame({"open": o[order] * new_c, "high": h[order] * new_c, "low": lo[order] * new_c,
                         "close": new_c, "volume": v[order]}, index=df.index)


def _labels(res) -> tuple[dict, dict]:  # noqa: ANN001
    prior = {r.range_id: r.prior_stage for r in res.stages.ranges}
    sc = {s.rng.range_id for s in res.phases.structures.values() if s.rng is not None and s.sc is not None}
    return prior, {"sc": sc}


def range_rows(res, sym: str) -> list[dict]:  # noqa: ANN001
    prior, extra = _labels(res)
    close = res.df["close"].to_numpy(dtype=float)
    rows = []
    for r in res.ranges:
        if r.confirmed_date < START or r.end_confirmed_idx is None:
            continue
        evs = [e for e in res.events if e.range_id == r.range_id and e.confirmed_idx < r.end_confirmed_idx]
        n_spring = sum(e.kind == EventType.SPRING for e in evs)
        n_utad = sum(e.kind in (EventType.UT, EventType.UTAD) for e in evs)
        x = r.end_confirmed_idx
        after = close[x + 1:x + 31]
        back = bool(len(after) and ((after <= r.resistance) & (after >= r.support)).any())
        rows.append({"symbol": sym, "range_id": r.range_id, "exit": r.exit_direction, "n_spring": n_spring, "n_utad": n_utad,
                     "prior_stage": prior.get(r.range_id), "has_sc": r.range_id in extra["sc"], "bars": x - r.confirmed_idx,
                     "height_atr": r.height / r.atr_at_confirm, "back_in_30": back})
    return rows


def real_one(job: tuple[str, str]) -> dict | None:
    sym, cache_dir = job
    logging.disable(logging.WARNING)
    df = load_cache(Path(cache_dir) / f"{sym}_1D.csv")
    if df is None or len(df) < MIN_BARS:
        return None
    cfg = Config()
    bt = cfg.backtest
    res = analyze(df, cfg)
    d = res.df
    close = d["close"].to_numpy(dtype=float)
    atr = d["atr"].to_numpy(dtype=float)
    al = align_index(df, load_cache(Path(cache_dir) / "VNINDEX_1D.csv"))
    beta = rolling_beta(df, al, bt.beta_window, bt.beta_min_periods)
    base = baseline_returns(df, al, bt.horizons, bt.cost_pct, first_signal_idx=bt.min_history_bars, beta=beta)
    b20 = base["bexcess_20"].reindex(d.index).to_numpy(dtype=float)
    b60 = base["bexcess_60"].reindex(d.index).to_numpy(dtype=float)
    prior, extra = _labels(res)
    by_range: dict[int, list] = {}
    for e in res.events:
        if e.range_id is not None and e.kind in (EventType.SPRING, EventType.UTAD, EventType.UT):
            by_range.setdefault(e.range_id, []).append(e)

    events, panel = [], []
    for r in res.ranges:
        if r.confirmed_date < START:
            continue
        closed = r.end_confirmed_idx is not None
        evs = sorted(by_range.get(r.range_id, []), key=lambda e: e.confirmed_idx)
        stop = r.end_confirmed_idx if closed else len(d)
        h = r.height if r.height > 0 else np.nan

        def feats(t: int) -> dict:
            lag = close[t - 20] if t >= 20 else np.nan
            return {"pos": (close[t] - r.support) / h, "drift20": (close[t] - lag) / atr[t] if atr[t] > 0 else np.nan,
                    "age": t - r.confirmed_idx, "exit": r.exit_direction, "to_exit": (stop - t) if closed else np.nan,
                    "symbol": sym, "range_id": r.range_id, "prior_stage": prior.get(r.range_id), "has_sc": r.range_id in extra["sc"],
                    "bexcess_20": b20[t], "bexcess_60": b60[t], "period": "2018–2022" if d.index[t] < pd.Timestamp("2023-01-01") else "2023–nay"}

        seen = {"Spring": 0, "UTAD": 0}
        for e in evs:
            t = e.confirmed_idx
            if t >= stop or d.index[t] < START:
                continue
            k = "Spring" if e.kind == EventType.SPRING else "UTAD"
            seen[k] += 1
            events.append({**feats(t), "kind": k, "order": seen[k], "spring_type": e.details.get("spring_type"),
                           "pen_atr": e.details.get("penetration_atr"), "vol_ratio": e.vol_ratio,
                           "invalidated": e.status == EventStatus.INVALIDATED})
        for t in range(r.confirmed_idx, stop, SAMPLE_EVERY):
            if d.index[t] < START:
                continue
            panel.append({**feats(t), "spring_so_far": any(e.kind == EventType.SPRING and e.confirmed_idx <= t for e in evs),
                          "utad_so_far": any(e.kind != EventType.SPRING and e.confirmed_idx <= t for e in evs)})
    return {"events": events, "panel": panel, "ranges": range_rows(res, sym)}


def placebo_one(job: tuple[str, str, int, int]) -> list[dict]:
    sym, cache_dir, seed, block = job
    logging.disable(logging.WARNING)
    df = load_cache(Path(cache_dir) / f"{sym}_1D.csv")
    if df is None or len(df) < MIN_BARS:
        return []
    return range_rows(analyze(shuffle_days(df, seed + zlib.crc32(sym.encode()) % 100_000, block), Config()), sym)


def pct(x: pd.Series) -> float:
    return round(float((x == "up").mean() * 100), 1) if len(x) else np.nan


def group_rates(r: pd.DataFrame) -> dict[str, tuple[int, float]]:
    g = {
        "mọi range": r,
        "không có sự kiện": r[(r.n_spring == 0) & (r.n_utad == 0)],
        "chỉ có Spring": r[(r.n_spring > 0) & (r.n_utad == 0)],
        "chỉ có UTAD": r[(r.n_utad > 0) & (r.n_spring == 0)],
        "có cả hai": r[(r.n_spring > 0) & (r.n_utad > 0)],
    }
    return {k: (len(v), pct(v["exit"])) for k, v in g.items()}


def boot_lpm(p: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Hồi quy tuyến tính xác suất thoát lên; CI 90% bootstrap theo mã."""
    p = p.dropna(subset=cols + ["exit"])
    X = np.column_stack([np.ones(len(p))] + [p[c].to_numpy(dtype=float) for c in cols])
    y = (p["exit"] == "up").to_numpy(dtype=float)
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    syms = p["symbol"].to_numpy()
    uniq = np.unique(syms)
    idx = {s: np.flatnonzero(syms == s) for s in uniq}
    rng = np.random.default_rng(BOOT_SEED)
    out = np.empty((BOOT_N, X.shape[1]))
    for i in range(BOOT_N):
        take = np.concatenate([idx[s] for s in rng.choice(uniq, len(uniq))])
        out[i] = np.linalg.lstsq(X[take], y[take], rcond=None)[0]
    return pd.DataFrame({"hệ số (điểm %)": beta[1:] * 100, "CI thấp": np.quantile(out[:, 1:], 0.05, axis=0) * 100,
                         "CI cao": np.quantile(out[:, 1:], 0.95, axis=0) * 100}, index=cols).round(1)


def standardized(ev: pd.DataFrame, panel: pd.DataFrame, flag: str) -> dict:
    """So sự kiện với phiên chưa có sự kiện loại đó, cùng ô (vị trí, tuổi range); chuẩn hóa theo phân bố của sự kiện."""
    ctrl = panel[~panel[flag]]
    e = ev.assign(p=pd.cut(ev.pos, POS_BINS, labels=False), a=pd.cut(ev.age, AGE_BINS, labels=False))
    c = ctrl.assign(p=pd.cut(ctrl.pos, POS_BINS, labels=False), a=pd.cut(ctrl.age, AGE_BINS, labels=False))
    eg = e.groupby(["p", "a"], observed=True)["exit"].agg(n="count", up=lambda s: (s == "up").mean())
    cg = c.groupby(["p", "a"], observed=True)["exit"].agg(nc="count", upc=lambda s: (s == "up").mean())
    m = eg.join(cg, how="inner")
    m = m[m["nc"] >= 30]
    w = m["n"] / m["n"].sum()
    return {"sự kiện": round(float((w * m["up"]).sum() * 100), 1), "đối chứng cùng ô": round(float((w * m["upc"]).sum() * 100), 1),
            "phủ": f"{int(m['n'].sum())}/{len(ev)}"}


def rate_table(df: pd.DataFrame, by: str | list) -> pd.DataFrame:
    t = df.groupby(by, observed=True).agg(n=("exit", "size"), thoat_len=("exit", pct), b20=("bexcess_20", "mean"), b60=("bexcess_60", "mean"))
    return t.round(2)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out", default="output/h8/investigate")
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()
    syms = [f.stem.replace("_1D", "") for f in sorted(Path(a.cache_dir).glob("*_1D.csv"))]
    syms = [s for s in syms if s not in INDEX_SYMBOLS]
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    events, panel, ranges = [], [], []
    placebo: dict[str, list[dict]] = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for r in ex.map(real_one, [(s, a.cache_dir) for s in syms], chunksize=4):
            if r:
                events += r["events"]
                panel += r["panel"]
                ranges += r["ranges"]
        for name, block, seed in (("xáo trộn từng ngày, seed 1", 1, 1), ("xáo trộn từng ngày, seed 2", 1, 2), ("xáo trộn khối 20 phiên", 20, 3)):
            rows: list[dict] = []
            for x in ex.map(placebo_one, [(s, a.cache_dir, seed, block) for s in syms], chunksize=4):
                rows += x
            placebo[name] = rows

    ev, pn, rg = pd.DataFrame(events), pd.DataFrame(panel), pd.DataFrame(ranges)
    ev.to_csv(out_dir / "events.csv", index=False)
    pn.to_csv(out_dir / "panel.csv", index=False)
    rg.to_csv(out_dir / "ranges.csv", index=False)
    closed_ev = ev[ev["exit"].notna()]
    closed_pn = pn[pn["exit"].notna()]

    L: list[str] = ["# Điều tra sau H8 (khám phá, không phải kiểm định đã đăng ký)", ""]
    L += ["## 1. Placebo: tỷ lệ thoát lên (%) khi phá cấu trúc thời gian", "", "```"]
    tbl = {"dữ liệu thật": group_rates(rg)}
    tbl.update({k: group_rates(pd.DataFrame(v)) for k, v in placebo.items()})
    L.append(pd.DataFrame({k: {g: f"{p} (n={n})" for g, (n, p) in v.items()} for k, v in tbl.items()}).to_string())
    L += ["```", ""]

    L += ["## 2. Vị trí trong range", "", "Tỷ lệ thoát lên theo vị trí giá, mọi phiên lấy mẫu của range đã kết thúc:", "```"]
    L.append(closed_pn.assign(vi_tri=pd.cut(closed_pn.pos, POS_BINS, labels=POS_LABELS)).groupby("vi_tri", observed=True)["exit"]
             .agg(n="size", thoat_len=pct).to_string())
    L += ["```", "", "Sự kiện so với phiên chưa có sự kiện đó, cùng vị trí và tuổi range:", "```"]
    L.append(pd.DataFrame({
        "Spring": standardized(closed_ev[closed_ev.kind == "Spring"], closed_pn, "spring_so_far"),
        "UTAD": standardized(closed_ev[closed_ev.kind == "UTAD"], closed_pn, "utad_so_far")}).to_string())
    L += ["```", "", "Hồi quy xác suất thoát lên (điểm %, CI 90% theo mã). Đà 20 phiên tính theo ATR:", "```"]
    L.append(boot_lpm(closed_pn.assign(s=closed_pn.spring_so_far.astype(float), u=closed_pn.utad_so_far.astype(float)), ["s", "u"]).to_string())
    L.append("")
    L.append(boot_lpm(closed_pn.assign(s=closed_pn.spring_so_far.astype(float), u=closed_pn.utad_so_far.astype(float),
                                       pos_clip=closed_pn.pos.clip(-0.5, 1.5)), ["s", "u", "pos_clip", "drift20"]).to_string())
    L += ["```", ""]

    L += ["## 3. Khoảng cách từ sự kiện đến phiên thoát", "", "Vị trí khi sự kiện xác nhận và khoảng cách đến thoát:", "```"]
    L.append(closed_ev.groupby("kind")[["pos", "drift20", "age", "to_exit"]].median().round(2).to_string())
    bins = [0, 5, 10, 20, 40, 80, np.inf]
    labs = ["1-5", "6-10", "11-20", "21-40", "41-80", ">80"]
    L += ["```", "", "Tỷ lệ thoát lên theo khoảng cách đến thoát:", "```"]
    L.append(closed_ev.assign(cach=pd.cut(closed_ev.to_exit, bins, labels=labs)).groupby(["kind", "cach"], observed=True)["exit"]
             .agg(n="size", thoat_len=pct).unstack("kind").to_string())
    L += ["```", "", "Spring / UTAD đã bị vô hiệu sau đó so với chưa:", "```"]
    L.append(closed_ev.groupby(["kind", "invalidated"])["exit"].agg(n="size", thoat_len=pct).to_string())
    L += ["```", ""]

    L += ["## 4. Bối cảnh lý thuyết (n, % thoát lên, bexcess 20 / 60 phiên từ phiên sự kiện)", "", "```"]
    sp = closed_ev[closed_ev.kind == "Spring"].copy()
    ut = closed_ev[closed_ev.kind == "UTAD"].copy()
    L += ["Spring theo xu hướng trước range:", rate_table(sp.assign(p=sp.prior_stage.fillna("không rõ")), "p").to_string(), ""]
    L += ["Spring theo loại:", rate_table(sp, "spring_type").to_string(), ""]
    L += ["Spring theo độ sâu (ATR):", rate_table(sp.assign(d=pd.cut(sp.pen_atr, [0, 0.25, 0.5, 1, np.inf])), "d").to_string(), ""]
    L += ["Spring có SC gắn với range:", rate_table(sp, "has_sc").to_string(), ""]
    L += ["Spring lần thứ:", rate_table(sp.assign(o=sp.order.clip(upper=3)), "o").to_string(), ""]
    strict = sp[(sp.prior_stage == "Markdown") & (sp.spring_type == "low_volume") & (sp.pen_atr < 1) & (sp.order == 1)]
    strictest = strict[strict.has_sc]
    L += [f"Spring đúng lý thuyết (sau Markdown, volume thấp, xuyên < 1 ATR, lần đầu): n={len(strict)}, thoát lên {pct(strict['exit'])}%, "
          f"b20 {strict.bexcess_20.mean():.2f}, b60 {strict.bexcess_60.mean():.2f}",
          f"  thêm điều kiện có SC: n={len(strictest)}, thoát lên {pct(strictest['exit'])}%, b20 {strictest.bexcess_20.mean():.2f}, b60 {strictest.bexcess_60.mean():.2f}", ""]
    L += ["UTAD theo xu hướng trước range:", rate_table(ut.assign(p=ut.prior_stage.fillna("không rõ")), "p").to_string(), ""]
    L += ["UTAD lần thứ:", rate_table(ut.assign(o=ut.order.clip(upper=3)), "o").to_string(), ""]
    L += ["Theo giai đoạn thời gian:", rate_table(closed_ev, ["kind", "period"]).to_string(), ""]
    L += ["Nền bexcess mọi phiên trong range đã kết thúc:", closed_pn[["bexcess_20", "bexcess_60"]].mean().round(2).to_string(), "```", ""]

    L += ["## 5. Sau khi thoát: giá có quay lại range trong 30 phiên không (%)", "", "```"]
    rg2 = rg.assign(nhom=np.select([(rg.n_spring > 0) & (rg.n_utad == 0), (rg.n_utad > 0) & (rg.n_spring == 0), (rg.n_spring == 0) & (rg.n_utad == 0)],
                                   ["chỉ Spring", "chỉ UTAD", "không sự kiện"], "cả hai"))
    L.append(rg2.groupby(["nhom", "exit"])["back_in_30"].agg(n="size", quay_lai=lambda s: round(float(s.mean() * 100), 1)).to_string())
    L += ["```", ""]

    text = "\n".join(L)
    (out_dir / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
