"""Biểu đồ nến + volume bằng plotly, chú thích range và sự kiện Wyckoff."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from wyckoff.detectors.models import Event, EventType
from wyckoff.pipeline import AnalysisResult

EVENT_STYLE: dict[EventType, dict[str, str]] = {
    EventType.SC: {"color": "#d62728", "symbol": "triangle-up", "anchor": "low"},
    EventType.SPRING: {"color": "#2ca02c", "symbol": "triangle-up", "anchor": "low"},
    EventType.SOS: {"color": "#1f77b4", "symbol": "triangle-down", "anchor": "high"},
    EventType.TEST: {"color": "#9467bd", "symbol": "circle", "anchor": "low"},
    EventType.SC_FAILED: {"color": "#7f7f7f", "symbol": "x", "anchor": "low"},
    EventType.PS: {"color": "#ff7f0e", "symbol": "triangle-up-open", "anchor": "low"},
    EventType.AR: {"color": "#17becf", "symbol": "triangle-down-open", "anchor": "high"},
    EventType.ST: {"color": "#8c564b", "symbol": "circle-open", "anchor": "low"},
    EventType.LPS: {"color": "#2ca02c", "symbol": "diamond", "anchor": "low"},
    EventType.UTAD: {"color": "#d62728", "symbol": "triangle-down-open", "anchor": "high"},
    EventType.UT: {"color": "#e377c2", "symbol": "triangle-down-open", "anchor": "high"},
}


PHASE_COLORS: dict[str, str] = {
    "A": "rgba(214,39,40,0.07)", "B": "rgba(127,127,127,0.06)", "C": "rgba(44,160,44,0.09)",
    "D": "rgba(31,119,180,0.09)", "E": "rgba(31,119,180,0.16)", "invalid": "rgba(0,0,0,0.05)",
}


def _missing_business_days(index: pd.DatetimeIndex) -> list[str]:
    """Ngày làm việc không có dữ liệu (nghỉ lễ) -> ẩn trên trục x."""
    full = pd.bdate_range(index.min(), index.max())
    return [d.strftime("%Y-%m-%d") for d in full.difference(index)]


def _label(e: Event) -> str:
    if e.kind == EventType.SPRING and e.details.get("spring_type") == "shakeout":
        return "Spring (shakeout)"
    return e.kind.value


def _hover(e: Event) -> str:
    lines = [
        f"<b>{e.kind.value}</b> {e.date:%Y-%m-%d}",
        f"O {e.open:.2f} H {e.high:.2f} L {e.low:.2f} C {e.close:.2f}",
        f"Vol {e.volume:,.0f} ({e.vol_ratio:.2f}x TB20)",
        f"Spread {e.spread_atr:.2f}x ATR, close_pos {e.close_pos:.2f}",
    ]
    if e.confirmed_idx != e.idx:
        lines.append(f"Xác nhận: {e.confirmed_date:%Y-%m-%d}")
    lines += [f"{k}: {v}" for k, v in e.details.items()]
    return "<br>".join(lines)


def build_figure(result: AnalysisResult, symbol: str, show_swings: bool = False):  # -> go.Figure
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = result.df
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name=symbol,
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        ),
        row=1, col=1,
    )
    vol_colors = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(df["open"], df["close"])]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], marker_color=vol_colors, name="Volume", opacity=0.6), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["vol_ma"], line=dict(color="#555", width=1), name="TB20 vol"), row=2, col=1)

    for rng in result.ranges:
        status = "đang hoạt động" if rng.end_confirmed_idx is None else f"thoát {rng.exit_direction}"
        x0 = max(rng.start_date, df.index[0])
        fig.add_shape(
            type="rect", x0=x0, x1=rng.end_date, y0=rng.support, y1=rng.resistance,
            fillcolor="rgba(255,165,0,0.12)", line=dict(color="orange", width=1, dash="dot"), row=1, col=1,
        )
        fig.add_annotation(
            x=x0, y=rng.resistance, text=f"TR#{rng.range_id} {rng.context} ({status})", showarrow=False,
            xanchor="left", yanchor="bottom", font=dict(size=10, color="darkorange"), row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=[rng.confirmed_date], y=[rng.resistance], mode="markers",
                marker=dict(symbol="diamond", size=7, color="orange"), name=f"TR#{rng.range_id} xác nhận",
                hovertext=f"TR#{rng.range_id} xác nhận {rng.confirmed_date:%Y-%m-%d}<br>"
                          f"support {rng.support:.2f} / resistance {rng.resistance:.2f}",
                hoverinfo="text", showlegend=False,
            ),
            row=1, col=1,
        )

    for kind, style in EVENT_STYLE.items():
        evs = [e for e in result.events if e.kind == kind]
        if not evs:
            continue
        atr = df["atr"].reindex([e.date for e in evs]).to_numpy()
        if style["anchor"] == "low":
            y = [e.low - 0.4 * a for e, a in zip(evs, atr)]
            pos = "bottom center"
        else:
            y = [e.high + 0.4 * a for e, a in zip(evs, atr)]
            pos = "top center"
        fig.add_trace(
            go.Scatter(
                x=[e.date for e in evs], y=y, mode="markers+text", text=[_label(e) for e in evs],
                textposition=pos, marker=dict(symbol=style["symbol"], size=12, color=style["color"]),
                textfont=dict(color=style["color"], size=11), name=kind.value,
                hovertext=[_hover(e) for e in evs], hoverinfo="text", cliponaxis=False,
            ),
            row=1, col=1,
        )

    for seg in result.phases.segments:
        x0 = max(seg.start_date, df.index[0])
        fig.add_vrect(
            x0=x0, x1=seg.end_date, fillcolor=PHASE_COLORS.get(seg.phase, "rgba(0,0,0,0)"), line_width=0,
            layer="below", row=1, col=1,
        )
        if (seg.end_idx - seg.start_idx) >= 5:
            fig.add_annotation(
                x=x0, y=1.0, yref="y domain", text=f"<b>{seg.phase}</b>", showarrow=False, xanchor="left",
                yanchor="top", font=dict(size=10, color="#555"), hovertext=seg.reason, row=1, col=1,
            )

    if show_swings:
        for kind, color in (("high", "#9467bd"), ("low", "#8c564b")):
            sw = [s for s in result.swings if s.kind == kind]
            fig.add_trace(
                go.Scatter(x=[s.date for s in sw], y=[s.price for s in sw], mode="markers",
                           marker=dict(size=4, color=color), name=f"swing {kind}"),
                row=1, col=1,
            )

    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(values=_missing_business_days(df.index))])
    fig.update_layout(
        title=f"{symbol} – Wyckoff: pha A–E và sự kiện", xaxis_rangeslider_visible=False,
        height=820, template="plotly_white", hovermode="closest", margin=dict(t=120),
        legend=dict(orientation="h", y=1.06, yanchor="bottom"),
    )
    fig.update_yaxes(title_text="Giá", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig


def save_html(fig, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(path, include_plotlyjs="cdn")
    return path


def build_rs_figure(stock: pd.DataFrame, index: pd.DataFrame, benchmark: str, symbol: str, sma: int = 50):
    """Đường RS = giá cổ phiếu / chỉ số và SMA của nó."""
    import plotly.graph_objects as go

    from wyckoff.market import relative_strength
    from wyckoff.config import MarketConfig

    rs = relative_strength(stock, index, MarketConfig(rs_sma=sma))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rs.index, y=rs["rs"], name=f"RS {symbol}/{benchmark}", line=dict(color="#0969da", width=1.5)))
    fig.add_trace(go.Scatter(x=rs.index, y=rs["rs_sma"], name=f"SMA{sma} của RS", line=dict(color="#8c959f", width=1, dash="dot")))
    fig.update_layout(height=280, template="plotly_white", margin=dict(t=20, b=30, l=50, r=20),
                      legend=dict(orientation="h", y=1.12), hovermode="x unified")
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(values=_missing_business_days(rs.index))])
    return fig
