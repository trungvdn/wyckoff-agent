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
    pivot_source: str = "high_low"           # biên range lấy từ pivot của: high_low | close (config/v3.yaml, dashboard)


PIVOT_SOURCES = ("close", "high_low")


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
    # Giả thuyết H7 (docs/h7-preregistration.md), mặc định tắt
    stage_strength: bool = False  # H7a: thêm yếu tố sức mạnh cung cầu trong Markup / Markdown
    prior_stage: bool = False     # H7b: thay điểm nhãn đà giá bằng xu hướng trước range


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
class RevisionConfig:
    """Lớp đánh giá lại (wyckoff/revision.py): tiềm năng -> xác nhận -> bác bỏ, dùng dữ liệu về sau để sửa nhãn trên biểu đồ.
    Chỉ ghi nhận, không đổi pha / tin cậy / backtest. Ngưỡng là khám phá trên mẫu H8, chưa phải kiểm định."""
    # Markup (docs/stage-definitions.md)
    mk_min_swings: int = 2            # HH-HL qua nhiều nhịp: tối thiểu 2 đỉnh và 2 đáy cao dần
    mk_base_lookback: int = 60        # xu hướng theo SMA: nền giá là range kết thúc trong 60 phiên trước
    mk_extended_bars: int = 60        # Extended Markup: từ 60 phiên sau breakout ...
    mk_extended_atr: float = 1.5      # ... hoặc ATR gấp 1,5 lần lúc breakout
    trend_watch_bars: int = 60        # Markdown / Markup: theo dõi bác bỏ tối đa 60 phiên sau xác nhận
    # Markdown: xác nhận khi đủ 5 điều kiện (docs/stage-definitions.md)
    md_min_lower_highs: int = 1       # số đỉnh thấp dần tạo sau khi thủng hỗ trợ
    md_min_lower_lows: int = 2        # số đáy thấp dần tạo sau khi thủng hỗ trợ (đáy đầu tiên luôn thấp hơn hỗ trợ)
    md_max_retrace: float = 0.618     # nhịp hồi gần nhất hồi không quá 61,8% nhịp giảm trước đó
    md_min_side_bars: int = 3         # cần ít nhất 3 phiên tăng và 3 phiên giảm để so cung cầu
    # Phiên có demand (Spring kéo dài, LPS reclaim)
    demand_min_vol_ratio: float = 1.5
    demand_min_close_pos: float = 0.7
    # Spring kéo dài: thoát xuống rồi quay lại với demand
    spring_window: int = 30           # tối đa 30 phiên sau phiên xác nhận thoát
    weak_break_vol_ratio: float = 1.0 # chỉ để mô tả: volume TB dưới support < 1.0 x TB20 là "thoát yếu"
    # LPS (docs/event-definitions.md)
    lps_window: int = 20              # điều chỉnh bắt đầu trong 20 phiên sau SOS hoặc SOS nội bộ
    lps_max_bars: int = 4             # thủng nhẹ: tối đa 4 close liên tiếp dưới hỗ trợ
    lps_max_depth: float = 0.03       # thủng nhẹ: close không sâu quá 3% dưới hỗ trợ
    lps_near_atr: float = 1.0         # về vùng hỗ trợ: close <= hỗ trợ + 1 ATR
    lps_confirm_bars: int = 5         # phản ứng của cầu trong 5 phiên sau ứng viên
    lps_supply_vol_ratio: float = 2.0     # phiên giảm volume >= 2x TB20 ...
    lps_supply_spread_atr: float = 1.5    # ... và biên độ >= 1,5 ATR: cung còn mạnh, không phải LPS
    lps_min_value_bn: float = 1.0     # thanh khoản: giá trị giao dịch TB20 >= 1 tỷ đồng
    lps_internal_strength: bool = True    # tính cả SOS nội bộ trong range làm nền cho LPS dưới resistance
    # Markup trước đó, dùng chung cho Re-accumulation và Distribution
    prior_up_min_rise: float = 0.30   # hoặc đã có HH-HL, hoặc tăng từ 30% so với đáy `context_lookback` phiên trước range
    # Accumulation (docs/stage-definitions.md)
    acc_window: int = 20              # so sánh cung cầu trên 20 phiên gần nhất
    acc_absorb_vol_ratio: float = 1.5 # hấp thụ cung: phiên volume >= 1,5x TB20 ở nửa dưới range, giá không giảm tương ứng
    acc_hold_bars: int = 10           # giữ hỗ trợ: tối thiểu 10 phiên sau breakout không sâu quá lps_max_depth dưới resistance
    acc_demand_bars: int = 5          # pha D không cần SOS: 5 phiên liên tiếp cầu chiếm ưu thế, ở nửa trên range, có đáy cao hơn
    # SC (docs/event-definitions.md): ngưỡng nhận diện ứng viên dùng chung với `sc`
    sc_max_undercut_atr: float = 1.0  # sau ứng viên, close không được thấp hơn đáy ứng viên quá 1 ATR
    sc_confirm_window: int = 10       # phản ứng tăng mạnh hoặc ổn định trong 10 phiên
    sc_reaction_atr: float = 2.0      # phản ứng tăng mạnh: close >= đáy vùng + 2 ATR
    sc_stabilize_bars: int = 5        # ổn định: tối thiểu 5 phiên không có close dưới đáy ứng viên ...
    sc_stabilize_vol_factor: float = 0.5  # ... và volume TB <= 0,5 x volume ứng viên
    # Xác nhận theo dõi cho SOS và UT/UTAD đã có
    utad_watch_bars: int = 60         # theo dõi close vượt đỉnh upthrust tối đa 60 phiên


@dataclass(frozen=True)
class DistributionConfig:
    """Sự kiện phía phân phối (wyckoff/detectors/distribution.py): chỉ ghi nhận, không đổi pha / tin cậy / backtest.
    Đối xứng với SC, AR, ST, SOS, LPS; khác: `bc_min_rise`, `bc_exclude_ceiling_locked` (hiệu chỉnh theo số đếm, không theo lợi suất)."""
    # BC
    bc_min_vol_ratio: float = 2.0
    bc_min_spread_atr: float = 1.5
    bc_max_close_pos: float = 0.5     # đóng cửa ở nửa dưới nến
    bc_trend_lookback: int = 60
    bc_min_rise: float = 0.30         # tăng >= 30% từ close thấp nhất 60 phiên
    bc_highest_high_lookback: int = 60
    bc_cooldown_bars: int = 10        # bỏ BC trùng trong 10 phiên trừ khi tạo đỉnh cao hơn
    bc_zone_bars: int = 2             # nến đóng cửa cao vẫn là BC nếu trong 2 phiên sau có close < điểm giữa nến
    bc_exclude_ceiling_locked: bool = True  # phiên khóa trần không phải climax: chưa thấy cung hấp thụ cầu
    ceiling_chain_min_days: int = 3   # dạng VN: >= 3 phiên tăng trần ...
    ceiling_chain_window: int = 10    # ... trong 10 phiên trước phiên đảo chiều
    bc_fail_atr: float = 0.5          # BC failed: close > đỉnh BC + 0.5 ATR ...
    bc_fail_window: int = 30          # ... trong 30 phiên, trước khi có AR(d)
    # AR(d)
    ar_min_atr: float = 3.0           # đáy AR(d) <= đỉnh BC - 3 ATR
    ar_pivot_bars: int = 3
    ar_window: int = 30
    # ST(d)
    st_window: int = 60
    st_band_above_atr: float = 0.5    # high trong [đỉnh BC - 1 ATR, đỉnh BC + 0.5 ATR]
    st_band_below_atr: float = 1.0
    st_max_vol_vs_bc: float = 0.7
    st_max_spread_vs_bc: float = 1.0
    st_min_gap_bars: int = 10
    # SOW
    sow_min_breakdown_atr: float = 0.2  # close < support - 0.2 ATR
    sow_min_spread_atr: float = 1.2
    sow_min_vol_ratio: float = 1.5
    sow_max_close_pos: float = 0.3
    sow_floor_chain_min_days: int = 2  # dạng VN: >= 2 phiên khóa sàn ...
    sow_floor_chain_window: int = 3    # ... trong 3 phiên, close dưới support: không xét volume, biên độ (bị khóa sàn chặn)
    # LPSY
    lpsy_window: int = 20
    lpsy_hold_below_sup_atr: float = 1.0  # high <= support + 1 ATR
    lpsy_min_rally_atr: float = 0.5       # high >= close thấp nhất từ SOW + 0.5 ATR
    lpsy_max_vol_ratio: float = 1.0
    lpsy_max_spread_atr: float = 1.0
    lpsy_confirm_bars: int = 3            # xác nhận: trong 3 phiên sau có close < low phiên LPSY
    lpsy_invalid_atr: float = 0.5         # LPSY vô hiệu: close > đỉnh LPSY + 0.5 ATR


@dataclass(frozen=True)
class StageConfig:
    """Giai đoạn / loại cấu trúc (wyckoff/stages.py): chỉ ghi nhận, không đổi pha / tin cậy / backtest."""
    slope_bars: int = 20              # SMA tăng / giảm so với 20 phiên trước (như market.slope_bars)
    enter_bars: int = 5               # 5 close liên tiếp đúng phía SMA đang dốc -> có xu hướng
    exit_bars: int = 5                # 5 close liên tiếp sai phía SMA -> mất xu hướng
    prior_max_bars: int = 60          # tìm xu hướng trước range trong tối đa 60 phiên


@dataclass(frozen=True)
class StrengthConfig:
    """Sức mạnh cung cầu trong Markup / Markdown (wyckoff/strength.py): chỉ mô tả, chưa kiểm định bằng backtest."""
    window: int = 20                  # đo tỷ trọng khối lượng trong 20 phiên
    volume_strong_pct: float = 55.0   # phiên cùng chiều xu hướng chiếm >= 55% khối lượng -> +1
    volume_weak_pct: float = 45.0     # <= 45% -> -1
    swing_lookback: int = 60          # chỉ xét đỉnh đáy xác nhận trong 60 phiên
    min_correction_bars: int = 2      # có nhịp điều chỉnh khi cách cực trị >= 2 phiên ...
    min_correction_atr: float = 0.5   # ... và >= 0.5 ATR
    shallow_retrace_pct: float = 38.2 # nông: < 38,2% nhịp trước đó
    deep_retrace_pct: float = 61.8    # sâu: >= 61,8% nhịp trước đó
    low_vol_ratio: float = 1.0        # volume nhịp điều chỉnh < 1.0 x TB20 là thấp
    high_vol_ratio: float = 1.3       # >= 1.3 x TB20 là cao
    strong_score: int = 2             # tổng điểm >= 2: mạnh
    weak_score: int = -1              # tổng điểm <= -1: yếu đi


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
    stage: StageConfig = field(default_factory=StageConfig)
    strength: StrengthConfig = field(default_factory=StrengthConfig)
    distribution: DistributionConfig = field(default_factory=DistributionConfig)
    revision: RevisionConfig = field(default_factory=RevisionConfig)


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
