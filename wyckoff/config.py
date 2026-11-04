"""Cấu hình tập trung. Mọi ngưỡng định lượng đều nằm ở đây (override bằng YAML)."""
from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml

T = TypeVar("T")


@dataclass(frozen=True)
class DataConfig:
    source: str = "VCI"                 # nguồn vnstock
    fallback_sources: tuple[str, ...] = ("KBS",)  # thử thêm khi nguồn chính thiếu lịch sử
    exchange: str = "HOSE"              # quyết định bước giá (tick)
    coverage_tolerance_days: int = 15   # dữ liệu bắt đầu muộn hơn start quá 15 ngày => coi là thiếu
    chunk_days: int = 365               # cỡ mỗi đoạn khi tải chia nhỏ theo năm
    warmup_bars: int = 120              # tải thêm ~120 phiên trước start để khởi động chỉ báo
    price_limit: float = 0.07           # biên độ sàn: HOSE 7%, HNX 10%, UPCoM 15%
    limit_tolerance: float = 0.005      # dung sai làm tròn bước giá
    overlap_days: int = 10              # số ngày chồng lấn khi cập nhật cache
    adjust_check_tolerance: float = 0.001  # lệch close > 0.1% ở vùng chồng lấn => giá đã bị điều chỉnh lại
    market_close_hour: int = 15         # trước 15:00 bỏ nến hôm nay (chưa hoàn tất)
    timezone: str = "Asia/Ho_Chi_Minh"


@dataclass(frozen=True)
class IndicatorConfig:
    atr_period: int = 14
    vol_ma_period: int = 20
    sma_period: int = 50
    ratio_decimals: int = 2           # so ngưỡng trên vol_ratio/spread_atr/close_pos đã làm tròn 2 chữ số


@dataclass(frozen=True)
class SwingConfig:
    left: int = 5
    right: int = 5          # pivot chỉ được xác nhận sau `right` phiên


@dataclass(frozen=True)
class RangeConfig:
    max_height_atr: float = 6.0       # (resistance - support) <= k * ATR
    min_bars: int = 20
    min_swing_highs: int = 2
    min_swing_lows: int = 2
    max_slope_atr: float = 0.1        # |độ dốc hồi quy close| / ATR mỗi phiên
    close_tolerance_atr: float = 0.5  # close trong range được phép lệch khỏi biên tối đa 0.5 ATR
    exit_atr: float = 0.5             # thoát range: close ngoài biên > 0.5 ATR ...
    exit_bars: int = 3                # ... trong 3 phiên liên tiếp
    max_lookback: int = 250
    # Bối cảnh range: lợi suất `context_lookback` phiên trước phiên bắt đầu range
    context_lookback: int = 120
    after_decline_max_return: float = -0.15  # <= -15% -> "sau nhịp giảm"
    after_rise_min_return: float = 0.30      # >= +30% -> "sau nhịp tăng"; còn lại "trung tính"
    anchor_sc_ar: bool = False               # H4b: AR xác nhận -> mở range support = đáy SC, resistance = đỉnh AR


@dataclass(frozen=True)
class SellingClimaxConfig:
    min_vol_ratio: float = 2.0        # volume > 2 x TB20
    min_spread_atr: float = 1.5       # biên độ > 1.5 x ATR
    min_close_pos: float = 0.5        # đóng cửa ở nửa trên nến (xa đáy)
    trend_lookback: int = 60
    min_decline: float = 0.15         # giảm >= 15% từ close cao nhất 60 phiên
    require_below_sma: bool = True    # close < SMA50
    lowest_low_lookback: int = 60     # low là thấp nhất 60 phiên
    cooldown_bars: int = 10           # bỏ SC trùng trong 10 phiên trừ khi tạo đáy thấp hơn
    zone_bars: int = 2                # nến climax đóng cửa thấp vẫn là SC nếu trong 2 phiên sau
                                      # có phiên đóng cửa > điểm giữa nến climax
    zone_undercut_atr: float = 0.0    # H4a: trong các phiên đó được thủng đáy climax tối đa k ATR (climax hai phiên)
    spread_measure: str = "true_range"  # "true_range" (tính cả gap) hoặc "range" (high - low)
    # Dạng Việt Nam: chuỗi giảm sàn rồi phiên rút chân
    floor_chain_min_days: int = 3     # >= 3 phiên giảm sàn ...
    floor_chain_window: int = 10      # ... trong 10 phiên trước phiên rút chân
    # SC thất bại
    fail_atr: float = 0.5             # close < đáy SC - 0.5 ATR ...
    fail_window: int = 30             # ... trong 30 phiên sau xác nhận ...
    ar_min_atr: float = 3.0           # ... và trước khi có AR (close cao nhất >= đáy SC + 3 ATR)


@dataclass(frozen=True)
class SpringConfig:
    min_penetration_atr: float = 0.1  # low < support - max(0.1 ATR, min_penetration_ticks tick)
    min_penetration_ticks: int = 1
    max_recovery_bars: int = 3        # phiên hồi trong tối đa 3 phiên (tính cả phiên thủng)
    recovery_min_ticks: int = 1       # phiên hồi: close >= support + 1 tick ...
    recovery_min_close_pos: float = 0.5  # ... và close_pos >= 0.5
    min_bars_after_confirm: int = 5   # phiên thủng cách phiên xác nhận range >= 5 phiên
    merge_bars: int = 10              # Spring mới cách Spring trước < 10 phiên: chỉ giữ nếu đáy thấp hơn
    max_vol_ratio: float = 1.0        # mọi phiên thủng có volume < 1.0 x TB20 => Spring volume thấp
    # Volume >= max_vol_ratio => Shakeout, chỉ xác nhận khi có Test:
    test_window: int = 15             # Test trong 15 phiên sau phiên hồi
    test_vol_factor: float = 0.6      # volume Test < 0.6 x volume phiên shakeout
    test_proximity_atr: float = 0.1   # low Test <= support + 0.1 ATR (quay về vùng support)
    # Mặc định không lọc theo bối cảnh (nhãn vẫn được ghi; LLM đánh giá bối cảnh ở giai đoạn 2)
    allowed_contexts: tuple[str, ...] = ("sau nhịp giảm", "trung tính", "sau nhịp tăng", "chưa rõ")


@dataclass(frozen=True)
class SOSConfig:
    min_breakout_atr: float = 0.2     # close > resistance + 0.2 ATR
    min_spread_atr: float = 1.2
    min_vol_ratio: float = 1.5
    min_close_pos: float = 0.7
    # H5 (quy chuẩn 04/11/2026 mục 4.7): same_bar = xác nhận ngay phiên breakout (v2);
    # follow_through = chờ <= follow_through_bars phiên: close < resistance -> thất bại, close > high phiên breakout -> xác nhận,
    # giữ >= resistance đủ số phiên -> xác nhận; locked_follow_through = chỉ phiên khóa trần cần follow-through.
    confirm_mode: str = "same_bar"
    follow_through_bars: int = 3


SOS_CONFIRM_MODES = ("same_bar", "follow_through", "locked_follow_through")


@dataclass(frozen=True)
class PSConfig:
    lookback: int = 40                # tìm trong 40 phiên trước SC (lấy phiên gần SC nhất)
    min_vol_ratio: float = 1.5
    min_close_pos: float = 0.5
    min_spread_atr: float = 1.0
    require_below_sma: bool = True


@dataclass(frozen=True)
class ARConfig:
    pivot_bars: int = 3               # đỉnh pivot 3 phiên mỗi bên -> xác nhận sau 3 phiên
    min_rally_atr: float = 3.0        # đỉnh AR >= đáy SC + 3 ATR
    window: int = 30                  # trong 30 phiên sau SC


@dataclass(frozen=True)
class STConfig:
    window: int = 60                  # trong 60 phiên sau AR
    band_below_atr: float = 0.5       # low trong [đáy SC - 0.5 ATR,
    band_above_atr: float = 1.0       #             đáy SC + 1.0 ATR]
    max_vol_vs_sc: float = 0.7        # volume < 0.7 x volume SC
    max_spread_vs_sc: float = 1.0     # biên độ < 1.0 x biên độ SC
    min_gap_bars: int = 10            # các ST cách nhau >= 10 phiên


@dataclass(frozen=True)
class LPSConfig:
    window: int = 20                  # trong 20 phiên sau SOS
    hold_above_res_atr: float = 1.0   # low >= resistance - 1.0 ATR
    min_pullback_atr: float = 0.5     # low <= close cao nhất từ SOS - 0.5 ATR
    max_vol_ratio: float = 1.0
    max_spread_atr: float = 1.0
    confirm_bars: int = 3             # xác nhận: trong 3 phiên sau có close > high phiên LPS


@dataclass(frozen=True)
class UTADConfig:
    min_bars_after_confirm: int = 20
    min_penetration_atr: float = 0.1  # high > resistance + max(0.1 ATR, 1 tick)
    min_penetration_ticks: int = 1
    max_return_bars: int = 3          # trong 3 phiên đóng cửa <= resistance - 1 tick ...
    return_ticks: int = 1
    max_close_pos: float = 0.5        # ... với close_pos <= 0.5
    # H6 (quy chuẩn 04/11/2026 mục 5.5–5.6): v2 = mọi upthrust là UTAD, xác nhận tại phiên quay lại;
    # ut_utad = upthrust đầu tiên trong range là UT, từ lần thứ hai là UTAD; xác nhận khi trong weakness_window phiên
    # sau phiên quay lại có close < giữa range, vô hiệu khi close > đỉnh upthrust hoặc hết thời hạn.
    mode: str = "v2"
    weakness_window: int = 15


UTAD_MODES = ("v2", "ut_utad")


@dataclass(frozen=True)
class ConfidenceConfig:
    """Điểm từng yếu tố tin cậy (v2, hiệu chỉnh theo backtest VN30 03/11/2026 – xem Project
    claude/backtest-diagnostics-2026-11-03.md). Điểm 0 = vẫn ghi nhận nhưng không cộng."""
    sc: int = 1
    st: int = 1
    spring: int = 0              # v1: +1 – backtest: Spring không có lợi thế
    test: int = 0                # v1: +1 – backtest: Test âm ở cả 2 giai đoạn
    sos: int = 1
    sos_reclaim: int = 0         # SOS reclaim: nghiên cứu 04/11/2026 không thấy lợi thế vững so với nền -> không cộng
    lps: int = 1
    after_decline: int = -1      # v1: "accumulation" +1 – backtest: range sau nhịp giảm kém nhất
    after_rise: int = 0          # v1: "distribution" -1 – backtest: không kém range trung tính
    test_max_vol_vs_shakeout: float = 0.5


@dataclass(frozen=True)
class PhaseConfig:
    attach_max_bars: int = 10         # SC gắn vào range: |SC - phiên bắt đầu range| <= 10 phiên
    attach_max_atr: float = 1.0       # và |đáy SC - support| <= 1 ATR
    spring_invalid_atr: float = 0.5   # pha C vô hiệu: close < đáy Spring - 0.5 ATR
    d_invalid_atr: float = 1.0        # pha D, mode lps_or_res_atr: close < resistance - 1 ATR (khi chưa có LPS)
    d_invalid_mode: str = "range_mid"        # lps_or_res_atr (v1) | range_mid | support – range_mid chọn theo backtest v2
    sc_failed_invalidates: bool = False      # v2: SC failed = vùng climax kéo dài, giữ pha A chờ SC mới
    deep_spring_atr: float = 1.0             # cảnh báo khi Spring xuyên >= 1 ATR dưới support
    reclaim_window: int = 30                 # range thoát xuống: 30 phiên chờ SOS lấy lại resistance (0 = tắt, như trước 04/11/2026)


D_INVALID_MODES = ("lps_or_res_atr", "range_mid", "support")


@dataclass(frozen=True)
class MarketConfig:
    enabled: bool = True
    benchmarks: dict[str, str] = field(
        default_factory=lambda: {"HOSE": "VNINDEX", "HNX": "HNXINDEX", "UPCOM": "UPCOMINDEX"}
    )
    index_source: str = "KBS"          # Market().index(...).ohlcv; dự phòng Quote(...) nguồn VCI
    sma_fast: int = 50
    sma_slow: int = 200
    slope_bars: int = 20               # SMA50 tăng/giảm so với 20 phiên trước
    return_windows: tuple[int, ...] = (20, 60, 120)
    drawdown_lookback: int = 250
    rs_windows: tuple[int, ...] = (20, 60)
    rs_sma: int = 50
    divergence_window: int = 20        # phân kỳ đáy: so 20 phiên gần nhất với 20 phiên trước đó
    confidence_rs_window: int = 60     # RS dùng cho điểm tin cậy
    rs_neutral_band_pct: float = 3.0   # |RS 60 phiên| < 3% -> đi ngang so với thị trường (0 điểm)
    # --- giả thuyết kiểm tra ngoài mẫu (mặc định tắt = v2) ---
    trend_up_requires_rs: bool = True          # GT2 (mặc định từ 03/11/2026): uptrend chỉ +1 khi RS 60 phiên > +band, ngược lại 0
    context_benchmark: str | None = None       # GT1: chỉ số dùng cho bối cảnh thị trường (vd. VNSML); None = theo sàn


@dataclass(frozen=True)
class BacktestConfig:
    universe: str = "VN30"              # nhóm vnstock Listing().symbols_by_group
    start: str = "2018-01-01"
    horizons: tuple[int, ...] = (5, 20, 60)
    cost_pct: float = 0.3               # chi phí khứ hồi (phí + thuế bán), %
    min_history_bars: int = 250         # baseline chỉ tính từ khi có đủ lịch sử
    scenario_max_bars: int = 120        # theo dõi kịch bản xác nhận / vô hiệu tối đa 120 phiên
    bootstrap_n: int = 2000
    ci: float = 0.90
    seed: int = 7
    point_in_time: bool = True          # tính lại pha / tin cậy tại ngày xác nhận bằng dữ liệu đến ngày đó
    beta_window: int = 250              # beta point-in-time từ lợi suất ngày 250 phiên trước tín hiệu
    beta_min_periods: int = 120
    split_date: str = "2023-01-01"      # chẩn đoán độ ổn định: 2018–2022 vs 2023–nay
    rate_limit_wait_s: float = 65.0     # hết hạn mức lượt gọi theo phút -> chờ rồi thử lại
    rate_limit_retries: int = 3


@dataclass(frozen=True)
class LifecycleConfig:
    """Vòng đời event (quy chuẩn 04/11/2026): chỉ ghi nhận trạng thái, không đổi pha / tin cậy / backtest.
    Spring dùng phase.spring_invalid_atr, SOS dùng phase.d_invalid_mode để thống nhất với mức vô hiệu của pha."""
    watch_bars: int = 60              # theo dõi vô hiệu hóa Spring / SOS / LPS tối đa 60 phiên sau xác nhận
    lps_invalid_atr: float = 0.5      # LPS vô hiệu: close < đáy LPS - 0.5 ATR


@dataclass(frozen=True)
class PnfConfig:
    box_atr: float = 0.5                # ô P&F = 0.5 ATR lúc range xác nhận (làm tròn lên theo tick)
    reversal: int = 3                   # đảo chiều 3 ô
    phases: tuple[str, ...] = ("C", "D", "E")   # chỉ tính mục tiêu khi đã có Spring / SOS


@dataclass(frozen=True)
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    swings: SwingConfig = field(default_factory=SwingConfig)
    ranges: RangeConfig = field(default_factory=RangeConfig)
    sc: SellingClimaxConfig = field(default_factory=SellingClimaxConfig)
    spring: SpringConfig = field(default_factory=SpringConfig)
    sos: SOSConfig = field(default_factory=SOSConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    ps: PSConfig = field(default_factory=PSConfig)
    ar: ARConfig = field(default_factory=ARConfig)
    st: STConfig = field(default_factory=STConfig)
    lps: LPSConfig = field(default_factory=LPSConfig)
    utad: UTADConfig = field(default_factory=UTADConfig)
    phase: PhaseConfig = field(default_factory=PhaseConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    pnf: PnfConfig = field(default_factory=PnfConfig)
    lifecycle: LifecycleConfig = field(default_factory=LifecycleConfig)


def _build(cls: type[T], values: dict[str, Any] | None) -> T:
    values = values or {}
    known = {f.name: f for f in fields(cls)}  # type: ignore[arg-type]
    unknown = set(values) - set(known)
    if unknown:
        raise ValueError(f"Khóa cấu hình không hợp lệ cho {cls.__name__}: {sorted(unknown)}")
    kwargs: dict[str, Any] = {}
    for name, f in known.items():
        if name not in values:
            continue
        sub_cls = f.default_factory if f.default_factory is not MISSING else None
        if sub_cls is not None and is_dataclass(sub_cls):
            kwargs[name] = _build(sub_cls, values[name])  # type: ignore[arg-type]
        else:
            value = values[name]
            kwargs[name] = tuple(value) if isinstance(value, list) else value
    return cls(**kwargs)


def load_config(path: str | Path | None = None) -> Config:
    """Đọc YAML (nếu có) và ghi đè lên giá trị mặc định."""
    if path is None:
        return Config()
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return _build(Config, raw)
