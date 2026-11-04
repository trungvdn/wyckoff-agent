# Wyckoff Agent – dữ liệu, bộ phát hiện sự kiện, pha (GĐ1) + LLM diễn giải (GĐ2)

Công cụ hỗ trợ phân tích, **không phải lời khuyên đầu tư**. Có event study (backtest đo lường), chưa mô phỏng chiến lược.

## Cài đặt & chạy

```bash
pip install -r requirements.txt
python run.py --demo                     # dữ liệu tổng hợp, không cần mạng
python run.py HPG --start 2020-01-01     # dữ liệu thật qua vnstock (cache ở cache/HPG_1D.csv)
python run.py HPG --refresh --swings     # tải lại toàn bộ, vẽ thêm swing
python run.py HPG --config config/default.yaml
pytest -q
python scripts/check_vnstock.py HPG --start 2020-01-01   # chẩn đoán vnstock khi thiếu lịch sử
python run.py HPG --start 2020-01-01 --explain           # GĐ2: Claude diễn giải -> output/HPG_report.html
python run.py HPG --start 2020-01-01 --explain --no-llm  # báo cáo theo mẫu, không gọi API
python run.py HPG --start 2020-01-01 --explain --no-market  # không dùng bối cảnh VN-Index
python backtest.py                       # event study trên VN30 hiện tại, từ 2018 -> output/backtest/
python backtest.py --symbols HPG,FPT,VNM --no-pit   # danh sách tự chọn, bỏ tính lại tin cậy theo ngày
python serve.py                          # API cho web dashboard (xem mục "Web dashboard")
```

Đầu ra trong `output/`: `HPG_wyckoff.html` (biểu đồ, nền tô theo pha), `HPG_events.csv`, `HPG_ranges.csv`,
`HPG_phases.csv` (các đoạn pha), `HPG_current_phase.json` (pha hiện tại + bằng chứng + mức xác nhận/vô hiệu — đầu vào cho LLM ở giai đoạn 2).

## Cấu trúc

```
config/default.yaml        mọi ngưỡng (chỉ cần ghi khóa muốn đổi)
wyckoff/config.py          dataclass cấu hình + load YAML (báo lỗi khóa sai)
wyckoff/data/              fetcher.py (vnstock, chuẩn hóa, kiểm tra), cache.py, loader.py (get_ohlcv)
wyckoff/indicators/core.py ATR Wilder, TB volume, spread, close_pos, SMA
wyckoff/detectors/         swings.py, trading_range.py, events.py (SC/Spring/SOS), structure.py (PS/AR/ST/LPS/UTAD), distribution.py (BC/AR(d)/ST(d)/SOW/LPSY, chỉ ghi nhận), lifecycle.py (vòng đời event), models.py
wyckoff/phases.py          state machine pha A–E, current_phase()
wyckoff/phases_distribution.py  pha A–E theo sơ đồ phân phối, chạy song song, chỉ ghi nhận
wyckoff/stages.py          giai đoạn và loại cấu trúc (chỉ ghi nhận), current_stage()
wyckoff/market.py          bối cảnh thị trường: xu hướng chỉ số, RS, phân kỳ đáy, đối chiếu sự kiện
wyckoff/charts/plot.py     plotly: nến + volume + range + sự kiện
wyckoff/agent/             GĐ2: payload.py, prompts.py, llm.py, validate.py, explain.py, report.py
wyckoff/backtest/          event study: metrics.py, study.py, summary.py, report.py, universe.py
wyckoff/pipeline.py        analyze(): chỉ báo -> swing -> range -> sự kiện -> pha; .current(), .since()
wyckoff/service.py         dùng chung CLI/web: tải theo khung (1D, 1W gộp từ ngày), phân tích, bối cảnh thị trường
wyckoff/pnf.py             mục tiêu Nhân–Quả: đếm ngang Point & Figure
wyckoff/web/               API FastAPI (app.py) + view model cho dashboard
web/                       giao diện Next.js (App Router) + Tailwind CSS, gọi API của wyckoff/web
wyckoff/synthetic.py       chuỗi giá có cài sẵn SC/Range/Spring/SOS
tests/                     pytest (gồm test chống look-ahead)
```

## Định nghĩa định lượng (mặc định)

Ký hiệu: `vol_ratio = volume_t / TB20(volume_{t-20..t-1})`, `spread_atr = (H-L)_t / ATR14_{t-1}`,
`close_pos = (C-L)/(H-L)`. Tham chiếu dùng dữ liệu đến t-1 để nến t không tự làm loãng ngưỡng.

**Swing**: pivot với 5 phiên mỗi bên; chỉ được biết ở phiên `idx + 5` (`confirmed_idx`).

**Trading range** (xét online từng phiên t, chỉ dùng swing đã xác nhận):
≥ 2 swing high & ≥ 2 swing low từ điểm bắt đầu s; `resistance = max(swing high)`, `support = min(swing low)`;
`height ≤ 6 ATR`; `t - s ≥ 20`; mọi close trong `[support - 0.5 ATR, resistance + 0.5 ATR]`;
|độ dốc hồi quy close| ≤ 0.1 ATR/phiên. Biên cố định khi xác nhận. Kết thúc khi 3 close liên tiếp
ngoài biên > 0.5 ATR.

Các tỉ số được **làm tròn 2 chữ số** trước khi so ngưỡng (0,698 → 0,70). Tick HOSE: < 10k → 10đ, 10k–50k → 50đ, ≥ 50k → 100đ; HNX/UPCoM 100đ.

| Sự kiện | Điều kiện |
|---|---|
| **SC** | Điều kiện nền: vol_ratio > 2.0; giảm ≥ 15% từ close cao nhất 60 phiên; close < SMA50; low thấp nhất 60 phiên. **Dạng climax**: True Range (tính cả gap) > 1.5 ATR; xác nhận khi close_pos ≥ 0.5 (ngay phiên đó) **hoặc** trong 2 phiên sau có close > điểm giữa nến climax mà không thủng đáy climax. **Dạng chuỗi sàn (VN)**: ≥ 3 phiên giảm sàn (Δclose ≤ −6.5%) trong 10 phiên trước, phiên hiện tại close_pos ≥ 0.5, không xét biên độ. SC mới trong 10 phiên chỉ giữ nếu đáy thấp hơn |
| **SC failed** | Sau khi SC xác nhận, trong 30 phiên và trước khi có AR (close cao nhất ≥ đáy SC + 3 ATR): close < đáy SC − 0.5 ATR. **v2: không vô hiệu cấu trúc** – coi là vùng climax kéo dài, giữ pha A chờ SC mới (`phase.sc_failed_invalidates: true` để quay về v1) |
| **Bối cảnh range** | Lợi suất 120 phiên trước phiên bắt đầu range: ≤ −15% **sau nhịp giảm**, ≥ +30% **sau nhịp tăng**, còn lại **trung tính**; thiếu lịch sử → **chưa rõ**. Chỉ là đà giá trước range, không phải nhận định accumulation / distribution |
| **Spring** | Trong range có bối cảnh thuộc `spring.allowed_contexts` (mặc định: tất cả). Range đã xác nhận ≥ 5 phiên trước. Phiên thủng đầu tiên: low < support − max(0.1 ATR, 1 tick). Phiên hồi trong ≤ 3 phiên (tính cả phiên thủng): close ≥ support + 1 tick **và** close_pos ≥ 0.5. Mọi phiên có low < support có vol_ratio < 1.0 → **Spring volume thấp**, xác nhận tại phiên hồi |
| **Spring (shakeout) + Test** | Như trên nhưng có phiên thủng vol_ratio ≥ 1.0 → chỉ xác nhận khi có **Test** trong 15 phiên sau phiên hồi: low ≥ đáy shakeout, low ≤ support + 0.1 ATR, volume < 0.6 × volume phiên thủng lớn nhất, support ≤ close ≤ resistance |
| **Gộp Spring** | Spring mới có phiên thủng cách Spring trước < 10 phiên chỉ được giữ nếu đáy thấp hơn (xét theo thứ tự xác nhận, không nhìn trước) |
| **SOS** | trong range (hoặc các phiên đang phá range trước khi xác nhận thoát); close > open; close > resistance + 0.2 ATR; spread_atr > 1.2; vol_ratio > 1.5; close_pos ≥ 0.7. Xác nhận theo `sos.confirm_mode`: `same_bar` (mặc định, xác nhận ngay); `follow_through` (H5a): trong 3 phiên sau close < resistance → thất bại (candidate INVALIDATED), close > high phiên breakout → xác nhận, giữ ≥ resistance đủ 3 phiên → xác nhận; `locked_follow_through` (H5b): chỉ phiên khóa trần cần follow-through. LPS không xác nhận trước SOS của nó |
| **SOS reclaim** | Range đã thoát xuống; trong 30 phiên sau (`phase.reclaim_window`, chưa có range mới xác nhận) phiên đầu tiên thỏa đúng quy tắc SOS so với resistance cũ. Đưa cấu trúc từ invalid về D; sau đó 3 close > resistance + 0.5 ATR → E, 3 close < support − 0.5 ATR → invalid. Tin cậy 0 điểm: trên 308 mã, bexcess 20 phiên +1,62% (CI 90% −0,50 đến +3,78; nền +0,34%), 60 phiên +3,90% (nền +1,72%), giai đoạn 2023–nay −1,06% |
| **PS** | Trong 40 phiên trước SC (lấy phiên gần nhất), close < SMA50: vol_ratio ≥ 1.5, close_pos ≥ 0.5, spread_atr ≥ 1.0, low > đáy SC. Xác nhận tại phiên xác nhận SC |
| **AR** | Đỉnh pivot (3 phiên mỗi bên) đầu tiên trong 30 phiên sau SC với high ≥ đáy SC + 3 ATR. Xác nhận ở pivot + 3. SC đã failed thì không có AR |
| **ST** | Sau AR, trong 60 phiên: low ∈ [đáy SC − 0.5 ATR, đáy SC + 1 ATR], volume < 0.7 × volume SC, biên độ < biên độ SC, close ≥ đáy SC; các ST cách nhau ≥ 10 phiên |
| **LPS** | Sau SOS, trong 20 phiên: low ≥ resistance − 1 ATR, low ≤ close cao nhất từ SOS − 0.5 ATR, vol_ratio < 1.0, spread_atr < 1.0; xác nhận khi trong 3 phiên sau có close > high phiên LPS. Mỗi SOS tối đa một LPS |
| **UTAD** | Range xác nhận ≥ 20 phiên; phiên đầu tiên high > resistance + max(0.1 ATR, 1 tick); trong ≤ 3 phiên close ≤ resistance − 1 tick với close_pos ≤ 0.5. Là sự kiện cảnh báo: vô hiệu cấu trúc tích lũy (`utad.mode: v2`, mặc định). `utad.mode: ut_utad` (H6): upthrust đầu tiên trong range = **UT**, từ lần thứ hai = **UTAD**; chỉ xác nhận khi trong 15 phiên sau phiên quay lại có close < giữa range (close > đỉnh upthrust hoặc hết 15 phiên → candidate INVALIDATED) |

Mặc định **không lọc Spring theo bối cảnh** (nhãn bối cảnh vẫn ghi để LLM đánh giá); bỏ một nhãn khỏi `spring.allowed_contexts` để lọc.

## Pha (sơ đồ tích lũy, state machine causal)

SC/AR/ST gắn vào range khi |SC − phiên bắt đầu range| ≤ 10 phiên và |đáy SC − support| ≤ 1 ATR.

| Pha | Mở khi | Chuyển tiếp |
|---|---|---|
| A | SC xác nhận | → B khi có ST |
| B | ST, hoặc range xác nhận không có SC | → C khi Spring; → D khi SOS; → E nếu range thoát lên (không SOS) |
| C | Spring (volume thấp, hoặc shakeout + Test) | → D khi SOS |
| D | SOS (LPS được ghi nhận) | → E khi range thoát lên |
| E | Range thoát lên (3 close > resistance + 0.5 ATR) | — |
| invalid | UTAD (hoặc UT/UTAD đã xác nhận yếu kém khi `ut_utad`); range thoát xuống; pha C có close < đáy Spring − 0.5 ATR | cấu trúc mới khi có SC hoặc range mới; → D khi có **SOS reclaim** |

`current_phase()` trả về pha, ngày bắt đầu, support/resistance, ATR, bằng chứng (các sự kiện của cấu trúc) và
**mức xác nhận / vô hiệu tính sẵn**: A → ST / thủng đáy SC (vùng climax kéo dài, không vô hiệu); B → Spring, SOS / range thoát xuống; C → SOS / đáy Spring − 0.5 ATR;
D → thoát range / mức theo `phase.d_invalid_mode` (mặc định `range_mid`: giữa range; `lps_or_res_atr` (v1): đáy LPS hoặc
resistance − 1 ATR; `support`: support – chọn theo backtest: sau khi thủng mức v1 hoặc support, giá vẫn tăng hơn chỉ số); E → quay lại dưới resistance. Cảnh báo khi phiên cuối đóng cửa sát đáy (close_pos ≤ 0.2) với volume ≥ 1.2× TB20,
và ở pha C khi Spring xuyên ≥ 1 ATR dưới support (`phase.deep_spring_atr`).

## Giai đoạn và loại cấu trúc (`wyckoff/stages.py`, chỉ ghi nhận)

Tầng 1 (Accumulation, Markup, Distribution, Markdown) suy ra từ tầng 2 (loại cấu trúc). State machine causal, chỉ dùng close, SMA50 và
range đã xác nhận / đã kết thúc tại phiên đó. **Không đổi** sự kiện, pha, điểm tin cậy, backtest (khóa `stage` trong YAML).

| Trạng thái | Khi nào |
|---|---|
| **Trending Up** (Markup) | 5 close liên tiếp trên SMA50 đang tăng (so với 20 phiên trước), hoặc range thoát lên |
| **Trending Down** (Markdown) | 5 close liên tiếp dưới SMA50 đang giảm, hoặc range thoát xuống |
| **Transition / Uncertain** | Chưa có xu hướng; 5 close liên tiếp sai phía SMA50; hoặc đang trong range đã xác nhận |

Trong range chỉ có hai giả thuyết theo xu hướng trước range (tìm trong 60 phiên; không có thì dùng nhãn đà giá 120 phiên). Nhãn chốt khi range thoát:

| Trước range | Thoát lên | Thoát xuống |
|---|---|---|
| Markup | Re-accumulation | Initial Distribution |
| Markdown | Initial Accumulation | Re-distribution |
| Không rõ | Accumulation (chưa rõ loại) | Distribution (chưa rõ loại) |

- Nhãn đã chốt **mô tả điều đã xảy ra, không phải dự báo**: hướng thoát range gần như 50/50 ở mọi bối cảnh (311 mã).
- `result.stages.series` là nhãn như biết tại từng phiên, không ghi đè về sau; `result.stages.ranges` là nhãn từng range (`resolved_idx` = phiên chốt).
- Pha A–E và điểm tin cậy vẫn theo sơ đồ tích lũy, nên pha và giai đoạn có thể khác nhau (ví dụ SOS reclaim đưa về pha D trong khi giai đoạn còn Markdown).
- Đầu ra: `<MÃ>_stages.csv`; payload v7 thêm `current_stage` (kèm `strength`), `stage_history`; prompt v6; `summary` của LLM phải nêu đúng loại cấu trúc.

**Sức mạnh cung cầu** (`wyckoff/strength.py`, khóa `strength` trong YAML): chỉ có ở Markup (cầu) và Markdown (cung). Chỉ mô tả hiện trạng, **chưa kiểm định bằng backtest**.
Ba tín hiệu, mỗi tín hiệu −1 / 0 / +1; tổng ≥ 2 mạnh, ≤ −1 yếu đi, còn lại trung bình:

| Tín hiệu | +1 | −1 |
|---|---|---|
| Khối lượng 20 phiên | Phiên cùng chiều xu hướng chiếm ≥ 55% | ≤ 45% |
| Đỉnh đáy (hai đỉnh, hai đáy đã xác nhận trong 60 phiên) | Cả đỉnh và đáy đi đúng chiều | Cả đỉnh và đáy đi ngược chiều |
| Nhịp điều chỉnh / nhịp hồi (cách cực trị ≥ 2 phiên và ≥ 0,5 ATR) | < 38,2% nhịp trước đó và volume < 1,0x TB20 | ≥ 61,8%, hoặc volume ≥ 1,3x TB20, hoặc close sai phía SMA50 |

**Dashboard** (`StagePhaseCard`, một thẻ): trong range hiện giả thuyết giai đoạn, pha, tiến trình A–E, điểm tin cậy; Markup / Markdown hiện sức mạnh cung cầu và nhịp điều chỉnh, không hiện pha; ngoài range và chưa có xu hướng chỉ nêu trạng thái.

## Sự kiện phía phân phối (`wyckoff/detectors/distribution.py`, chỉ ghi nhận)

Nằm trong `result.distribution`, xuất ra `<MÃ>_distribution.csv`. **Không** vào `result.events`, pha tích lũy, tin cậy hay backtest (khóa `distribution` trong YAML).

| Sự kiện | Điều kiện (đối xứng phía tích lũy, trừ chỗ ghi riêng) |
|---|---|
| **BC** | vol_ratio > 2; **tăng ≥ 30%** từ close thấp nhất 60 phiên; close > SMA50; high cao nhất 60 phiên. Dạng climax: True Range > 1,5 ATR, **không khóa trần**; xác nhận khi close_pos ≤ 0,5 hoặc trong 2 phiên sau có close < điểm giữa nến mà không vượt đỉnh. Dạng chuỗi trần: ≥ 3 phiên tăng trần trong 10 phiên trước, phiên hiện tại close_pos ≤ 0,5. BC mới trong 10 phiên chỉ giữ nếu đỉnh cao hơn |
| **BC failed** | Trong 30 phiên, trước AR(d): close > đỉnh BC + 0,5 ATR |
| **AR(d)** | Đáy pivot (3 phiên mỗi bên) đầu tiên trong 30 phiên sau BC, low ≤ đỉnh BC − 3 ATR |
| **ST(d)** | Sau AR(d), trong 60 phiên: high ∈ [đỉnh BC − 1 ATR, đỉnh BC + 0,5 ATR], volume < 0,7× BC, biên độ < BC, close ≤ đỉnh BC; cách nhau ≥ 10 phiên |
| **SOW** | Trong range: nến giảm; close < support − 0,2 ATR; spread_atr > 1,2; vol_ratio > 1,5; close_pos ≤ 0,3. **Dạng chuỗi khóa sàn**: phiên khóa sàn đầu tiên đạt ≥ 2 phiên khóa sàn trong 3 phiên, close < support − 0,2 ATR, không xét volume và biên độ; một phiên khóa sàn đơn lẻ không tự động là SOW |
| **LPSY** | Sau SOW, trong 20 phiên: high ≤ support + 1 ATR, high ≥ close thấp nhất từ SOW + 0,5 ATR, vol_ratio < 1, spread_atr < 1; xác nhận khi trong 3 phiên sau có close < low phiên đó |

Vô hiệu sau xác nhận (trong 60 phiên): BC ← BC failed; SOW ← close > giữa range; LPSY ← close > đỉnh LPSY + 0,5 ATR.
`tests/test_distribution.py` kiểm tra đối xứng bằng cách lật giá. Khác biệt riêng của BC chọn theo số đếm, không theo lợi suất.

**Khảo sát cấu trúc (311 mã, từ 2018)**: BC 1.656 (SC 1.410), BC failed 42% (SC failed 39%), AR(d) 1.012, ST(d) 1.052, SOW 1.711 gồm 1.351 biên độ rộng và 360 chuỗi khóa sàn (SOS 3.996). Vẫn lệch: 39% range thoát xuống có SOW (31% trước khi thêm dạng chuỗi khóa sàn), trong khi 71% range thoát lên có SOS.

**Pha theo sơ đồ phân phối** (`wyckoff/phases_distribution.py`, `result.distribution_phases`, `<MÃ>_distribution_phases.csv`): state machine causal chạy **song song** với pha tích lũy, vì trong range chưa biết giả thuyết nào đúng. Chỉ ghi nhận, không có điểm tin cậy và mức giá.

| Pha | Mở khi | Chuyển tiếp |
|---|---|---|
| A | BC xác nhận | → B khi có ST(d) |
| B | ST(d), hoặc range xác nhận không có BC | → C khi UT / UTAD; → D khi SOW |
| C | UT / UTAD | → D khi SOW |
| D | SOW (LPSY được ghi nhận) | → E khi range thoát xuống |
| E | Range thoát xuống | — |
| invalid | Range thoát lên; pha C có close > đỉnh upthrust + 0,5 ATR | cấu trúc mới khi có BC hoặc range mới |

Khác phía tích lũy: Spring không vô hiệu cấu trúc phân phối, không có "SOS reclaim" đối xứng. Payload v8 thêm `current_stage.distribution_phase` khi đang trong range; prompt v7. Dashboard hiện cả hai sơ đồ trong thẻ `StagePhaseCard` khi đang trong range.

## Chống look-ahead
- Chỉ báo causal; swing có độ trễ xác nhận; range xử lý online; Spring xác nhận ở phiên quay lại.
- Nến hôm nay bị bỏ nếu chạy trước 15:00 giờ VN (nến chưa hoàn tất).
- `tests/test_detectors.py::test_no_lookahead` chạy pipeline trên dữ liệu cắt tại nhiều thời điểm
  và đòi hỏi kết quả (sự kiện, range, chuỗi pha) trùng với dữ liệu đầy đủ (lọc theo `confirmed_idx`).

## Vòng đời event (quy chuẩn 04/11/2026, bước 1)

Chỉ **ghi nhận**, không đổi pha / tin cậy / backtest: `result.events` vẫn đúng tập event đã xác nhận như trước
(đã so trên 307 mã trong cache: sự kiện, chuỗi pha, pha hiện tại trùng khớp 100%).

- **Trạng thái** (`Event.history`, `Event.status`, `Event.status_at(t)`): DETECTED → CANDIDATE → CONFIRMED → INVALIDATED / REVISED.
  `idx` = ngày event, `confirmed_idx` = ngày xác nhận (giữ nguyên quy tắc detector hiện tại).
- **Candidate** (`result.candidates`, `confirmed_idx = -1`): SC dạng vùng không xác nhận, phiên thủng support không hồi trong 3 phiên,
  shakeout không có Test trong 15 phiên / thủng đáy shakeout / range kết thúc → INVALIDATED; SC trong cooldown và Spring bị gộp → REVISED.
  Chỉ SC và Spring ghi mốc DETECTED/CANDIDATE trước xác nhận (vì chỉ hai loại này ghi cả candidate thất bại; loại khác biết từ phiên xác nhận).
- **Vô hiệu hóa sau xác nhận** (trong `lifecycle.watch_bars` = 60 phiên): SC ← có SC failed (PS của SC đó theo);
  Spring ← close < đáy Spring − `phase.spring_invalid_atr` ATR (Test theo); SOS ← close dưới mức vô hiệu pha D (`phase.d_invalid_mode`, mặc định giữa range);
  LPS ← close < đáy LPS − `lifecycle.lps_invalid_atr` (0,5) ATR. AR, ST, UTAD chưa có quy tắc vô hiệu.
- **ID ổn định** `event_id`: `<LOẠI>-<yyyymmdd>[-TR<ngày bắt đầu range>][-SC|-SPRING|-SOS<ngày event gốc>][-RECLAIM]` – chỉ dựa vào ngày,
  không đổi khi đổi `--start` (range_id thì có thể đổi).
- **Quan hệ**: `related_event_ids` (PS/AR/ST/SC failed ↔ SC, Test ↔ Spring, LPS ↔ SOS), `test_of_event_id` (ST → SC, Test → Spring);
  `result.structure_of()` = event_id → structure_id.
- `result.snapshot(t)`: mọi event + candidate đã biết tại phiên t với trạng thái lúc đó.
  `tests/test_lifecycle.py::test_lifecycle_no_lookahead`: trạng thái tại t trên dữ liệu đầy đủ == trạng thái cuối khi chỉ có dữ liệu đến t.
- Đầu ra: `<MÃ>_events.csv` thêm cột `event_id, status, history, invalidated_date, related_event_ids, test_of_event_id, structure_id`
  và gồm cả candidate; payload v5 thêm `uid, status, status_reason, related` cho từng sự kiện bằng chứng (prompt chưa đổi).

## Dữ liệu
- `vnstock` 5.x (tương thích 3.x). Nguồn chính VCI, dự phòng KBS (giá nghìn đồng, đã điều chỉnh).
- Chuỗi dự phòng, dừng ở cách đầu tiên phủ đủ từ `start` (dung sai 15 ngày):
  `Quote.history(start, end)` → `Market().equity().ohlcv(start, end, limit=N)` → `Quote.history` chia đoạn 365 ngày, lặp lại với nguồn dự phòng.
  Không cách nào phủ đủ → dùng kết quả phủ xa nhất và cảnh báo **THIẾU LỊCH SỬ**.
- Chẩn đoán: `python scripts/check_vnstock.py HPG` in cấp tài khoản và độ phủ của từng cách gọi.
- **Khởi động**: `run.py` tải thêm ~120 phiên trước `--start`, phân tích trên toàn bộ rồi chỉ báo cáo/vẽ từ `--start` (`AnalysisResult.since`).
- **Cờ trần / sàn** (`wyckoff/indicators/limits.py`, cột của `result.df`, `details["limit"]` của event): `limit_up` / `limit_down` khi
  |ΔClose| ≥ `price_limit` − `limit_tolerance` (HOSE 6,5%); `ceiling_locked` = `limit_up` và high − close ≤ 1 tick; `floor_locked` = `limit_down`
  và close − low ≤ 1 tick. Giá đã điều chỉnh, một `price_limit` cho mọi mã; không phân biệt khóa lúc ATC.
- **Kiểm tra điều chỉnh giá**: trên HOSE |ΔClose| ≤ 7%. Phiên vượt 7.5% bị cảnh báo là có thể chưa điều chỉnh
  (ngày GDKHQ). HNX: đặt `data.price_limit: 0.10`.
- Cache cập nhật tăng dần với 10 ngày chồng lấn; nếu close vùng chồng lấn lệch > 0.1% (có sự kiện quyền mới) thì tải lại toàn bộ.

## Giai đoạn 2: LLM diễn giải

Nguyên tắc: **code tính mọi con số, LLM chỉ diễn giải và đánh giá bối cảnh.**

1. `payload.py` – gói JSON tất định (~5 KB): pha hiện tại, mức giá có ID (`confirm_0`, `invalidate_0`...),
   sự kiện bằng chứng (`ev_0`...), 20 phiên gần nhất, lịch sử pha/range, cảnh báo, ngưỡng quy tắc,
   **mức tin cậy do code tính** – thang v2 hiệu chỉnh theo backtest (`confidence` trong YAML): SC +1, ST +1, SOS +1, LPS +1,
   Spring 0 và Test 0 (vẫn ghi để minh bạch, là mốc pha C), range sau nhịp giảm ≥ 15% −1, sau nhịp tăng 0,
   mỗi cảnh báo −1 (SOS/LPS thất bại, quay lại range −2); ≤ 0 thấp, 1–2 trung bình, ≥ 3 cao.
2. `llm.py` – Claude qua Anthropic API (mặc định `claude-sonnet-5-5`), **structured outputs** (`output_config` +
   `json_schema`; Sonnet/Opus 5.5 không hỗ trợ ép `tool_choice`). Key lấy từ biến môi trường `ANTHROPIC_API_KEY`.
3. `validate.py` – kiểm soát đầu ra (prompt v2): đúng schema; không có tên trường kỹ thuật (`vol_ratio`... – trừ `close_pos`),
   không có ngày ISO (dùng dd/mm/yyyy), viết "pha" không viết "phase", diễn giải mỗi kịch bản ≤ 400 ký tự; mọi `level_id` tồn tại, đúng loại, mỗi level dùng đúng 1 lần;
   `event_id` tồn tại; summary nêu đúng pha; nêu đúng mức tin cậy; **mọi con số và ngày trong văn bản phải có trong payload**
   (giá/tỉ số khớp ±0,011; số ≥ 1.000 sai lệch ≤ 0,6%, hỗ trợ "27,85 triệu", "25.465.100", "02/10/2026").
4. `explain.py` – gọi LLM → kiểm tra → sai thì gửi lỗi lại cho LLM thử thêm 1 lần → vẫn sai thì dùng
   **báo cáo theo mẫu** (`report.template_explanation`) và ghi lý do. Cache theo hash(prompt version, model, payload)
   ở `output/llm_cache/`.
5. `report.py` – HTML: tóm tắt, đánh giá pha, bối cảnh, bảng kịch bản (mức giá + điều kiện do code, diễn giải do LLM),
   bằng chứng, rủi ro, bảng tin cậy, biểu đồ.

Đầu ra thêm: `HPG_payload.json`, `HPG_explanation.json` (nguồn, model, số lần gọi, lỗi), `HPG_report.html`.

Cài đặt (PowerShell): `pip install anthropic` rồi `$env:ANTHROPIC_API_KEY="..."` (hoặc đặt biến môi trường trong Windows).

## Bối cảnh thị trường (GĐ2a)

Chỉ số so sánh tự chọn theo sàn (`market.benchmarks`: HOSE → VNINDEX, HNX → HNXINDEX, UPCoM → UPCOMINDEX), tải bằng
`Market().index(symbol).ohlcv()` (KBS), dự phòng `Quote(symbol, VCI).history()`; cache `cache/VNINDEX_1D.csv`, khởi động
≥ 200 phiên cho SMA200, không kiểm tra biên độ ±7%. Mọi đại lượng tại t chỉ dùng dữ liệu ≤ t; chỉ số căn theo ngày cổ phiếu (ffill ≤ 3 phiên).

| Đại lượng | Định nghĩa |
|---|---|
| Xu hướng | uptrend: close > SMA50 > SMA200 và SMA50 tăng so với 20 phiên trước; downtrend: ngược lại; còn lại sideways |
| Lợi suất / drawdown | thay đổi chỉ số 20/60/120 phiên; cách đỉnh 250 phiên |
| RS | giá cổ phiếu / chỉ số; thay đổi RS 20 và 60 phiên (%); RS so với SMA50 của RS |
| Phân kỳ đáy | đáy chỉ số 20 phiên gần nhất < đáy 20 phiên trước đó, trong khi đáy cổ phiếu cùng kỳ ≥ đáy kỳ trước |
| Đối chiếu sự kiện | % thay đổi chỉ số trong phiên mỗi sự kiện của cổ phiếu, xu hướng và pha (tham khảo) của chỉ số ngày đó |
| Pha Wyckoff của chỉ số | cùng bộ detector, **chỉ tham khảo** (ngưỡng chưa hiệu chỉnh cho chỉ số), không tính vào tin cậy |

Điểm tin cậy thêm (2 yếu tố, mỗi yếu tố trong [−1, +1]): (1) chỉ số uptrend +1 **chỉ khi RS 60 phiên > +3%** (GT2, mặc định từ 03/11/2026; ngược lại 0) / downtrend −1; (2) nhóm **sức mạnh tương đối**
= clamp(RS + phân kỳ, −1, +1), trong đó RS 60 phiên > +3% → +1, < −3% → −1, trong ±3% → 0 (đi ngang); phân kỳ đáy +1.
Gộp nhóm để không chấm hai lần (cổ phiếu giữ đáy khi chỉ số tạo đáy mới cũng làm RS tăng; với HPG đáy "giữ được" chính là cặp Spring/Test).
Mọi chuỗi do code sinh (điều kiện, lý do pha, bằng chứng) dùng định dạng VN: 27.360.105; 22,75; 1.699,62; 03/11/2026.
Prompt v3 thêm trường `market_assessment`. Lớp kiểm tra đọc số theo **một cách duy nhất** (1.500 = 1500; 22,74 = 22.74;
27,847,568 = 27847568) để tránh lọt số bịa.

## Backtest (event study)

Đo, không tối ưu: mọi ngưỡng giữ nguyên. Tín hiệu = mọi sự kiện (tại phiên xác nhận) + mọi lần mở pha (B, C, D, E, invalid).

- **Vào lệnh**: open phiên t+1 (t = phiên xác nhận); đo đến close phiên t+H, H ∈ {5, 20, 60}; trừ 0,3% chi phí khứ hồi.
  Phiên t+1 mở cửa giá trần → đánh dấu "không khớp được" và loại khỏi thống kê.
- **Đo**: lợi suất, lợi suất vượt chỉ số (cùng kỳ, chỉ số từ open t+1), MFE/MAE, tỉ lệ thắng.
- **Nền**: cùng phép đo cho mọi phiên của cùng các mã (từ khi đủ 250 phiên lịch sử). "Chênh so với nền" = LS vượt TB tín hiệu − LS vượt TB nền,
  kèm CI 90% bootstrap (lạc quan vì tín hiệu giữa các mã tương quan).
- **Point-in-time**: tại mỗi phiên tín hiệu chạy lại toàn bộ phân tích trên dữ liệu đến phiên đó → pha, mức tin cậy, bối cảnh thị trường,
  mức xác nhận/vô hiệu đúng như lúc đó (test: phá dữ liệu sau phiên đó không làm đổi kết quả).
- **Kịch bản**: khi mở pha B/C/D, close vượt mức xác nhận gần nhất phía trên giá trước, hay thủng mức vô hiệu gần nhất phía dưới giá trước
  (≤ 120 phiên; chỉ xét giá, không xét điều kiện volume).
- **Hạn chế**: rổ VN30 hiện tại → thiên lệch sống sót; số mẫu mỗi loại sự kiện nhỏ; chưa mô phỏng chiến lược.
- **Chẩn đoán (bước 1, không đổi quy tắc)**:
  1. Lợi suất vượt điều chỉnh beta (`bexcess`): lợi suất − β × lợi suất chỉ số; β point-in-time từ lợi suất ngày 250 phiên trước tín hiệu.
  2. Độ ổn định: tách 2018–2022 / 2023–nay (`backtest.split_date`), nền tính riêng từng giai đoạn.
  3. Đóng góp từng yếu tố tin cậy (mỗi yếu tố có mã ổn định: sc, st, spring, test, sos, lps, rangectx, warning, mkttrend, relstrength).
  4. Spring / SOS / SC theo thuộc tính (độ sâu thủng, volume phiên thủng, phiên hồi, độ dài và chiều cao range, bối cảnh, xu hướng chỉ số, beta...).
  Đầu ra thêm: by_kind_beta.csv, by_kind_period.csv, by_factor.csv, breakdown_spring.csv, breakdown_sos.csv, breakdown_sc.csv.
- Kết quả mốc (trước chẩn đoán): Project `claude/backtest-baseline-2026-11-03.md`.
- **Bước 2 (v2, 03/11/2026)**: thang tin cậy v2, SC failed không vô hiệu, đổi nhãn bối cảnh, cảnh báo Spring xuyên sâu,
  mức vô hiệu pha D `range_mid`; payload v4, prompt v4 (nhãn bối cảnh chỉ là đà giá; yếu tố 0 điểm không cộng tin cậy).
  Cột `h_<mã>` trong signals.csv ghi yếu tố có mặt (kể cả 0 điểm). Kết quả: Project `claude/backtest-v2-2026-11-03.md`.
- **Kiểm tra ngoài mẫu** (`wyckoff/backtest/oos.py`): `config/v1.yaml` tái hiện quy tắc v1 để so trên cùng dữ liệu;
  `scripts/oos_eval.py` chấm theo tiêu chí chốt trước. VNMidCap: ĐẠT (Project `claude/oos-results-2026-11-03.md`).
- **Giả thuyết** (kiểm tra trên VNSmallCap, Project `claude/oos-hypotheses-results-2026-11-03.md`):
  GT1 `market.context_benchmark` (`config/h1.yaml`, bối cảnh theo VNSMALLCAP) – **không chấp nhận**, mặc định tắt;
  GT2 `market.trend_up_requires_rs` (`config/h2.yaml`) – **chấp nhận, mặc định bật từ 03/11/2026**.
  Tái lập v2 trước GT2: `config/v2_pre_gt2.yaml`; v1: `config/v1.yaml`. Chấm bằng `scripts/hypothesis_eval.py` (bootstrap theo mã ghép cặp).

## Web dashboard

```bash
pip install -r requirements.txt
python serve.py                    # API: http://127.0.0.1:8000/api/docs ; mã DEMO dùng dữ liệu tổng hợp
python serve.py --no-llm           # agent trả lời theo mẫu, không gọi API

cd web && npm install && npm run dev   # giao diện Next.js: http://localhost:3000 (cần serve.py đang chạy)
npm run build && npm start             # bản production (Node >= 20.9)
```

**Giao diện Next.js** (`web/`, Next 16 App Router, React 19, Tailwind CSS 4, TypeScript):

| Đường dẫn | Nội dung |
|---|---|
| `/` , `/co-phieu` | Chuyển tới mã mặc định (`NEXT_PUBLIC_DEFAULT_SYMBOL`, mặc định HPG) |
| `/co-phieu/[symbol]` | Dashboard khung ngày; `?tf=1W` khung tuần. Mã viết thường hoặc `?tf=1D` / tf sai được chuyển về URL chuẩn |
| mã sai định dạng | Trang 404 (`app/not-found.tsx`); mã không có dữ liệu / API lỗi: thông báo tại chỗ + Thử lại |

Trang phân tích chạy trên server (gọi `WYCKOFF_API_URL`); `loading.tsx` hiện skeleton khi đổi mã / khung. Diễn giải agent,
hỏi đáp và Phân tích lại chạy ở client qua `/api/*` (Next rewrite sang FastAPI, không cần CORS). Font IBM Plex tự host bằng
`next/font`. Thành phần: `components/layout` (Header, Footer, trạng thái), `components/ui` (Card, Button, Skeleton),
`components/dashboard` (PriceChart, StagePhaseCard, EventsCard, ScenarioCard, AskAgent...).
Biểu đồ dùng TradingView Lightweight Charts: con lăn / pinch để zoom, kéo để xem ngày cũ, nút 3T–Tất cả, phím mũi tên và +/−; API trả toàn bộ lịch sử đã phân tích (`bars`) kèm khung nhìn mặc định (`view_from`) và các đoạn pha (`phase_segments`), vẽ thành dải nền theo pha như báo cáo HTML. Kiểm tra: `npm run lint`, `npm run typecheck`, `npm run build`.

Một màn hình cho một mã: biểu đồ nến + vùng giao dịch + nhãn sự kiện, pha hiện tại và các yếu tố tin cậy, bằng chứng
từng sự kiện, kịch bản xác nhận / vô hiệu, mục tiêu Nhân–Quả, hỏi agent. Khung **Ngày** là khung gốc; **Tuần** gộp từ
nến ngày (chỉ tham khảo); 15 phút / Giờ chưa hỗ trợ.

- API (`/api/docs`): `GET /api/analysis/{mã}?tf=1D|1W`, `GET /api/explanation/{mã}`, `POST /api/ask`. Phân tích được cache
  5 phút trong bộ nhớ (`WYCKOFF_TTL_S`); "Phân tích lại" bỏ cache và cập nhật dữ liệu tăng dần.
- **Hỏi agent** (`wyckoff/agent/ask.py`): cùng nguyên tắc diễn giải – chỉ dùng số trong payload (số người dùng tự gõ trong
  câu hỏi được phép nhắc lại), không tên trường kỹ thuật, `event_ids` phải tồn tại; sai -> thử lại 1 lần -> trả lời theo mẫu.
- **Mục tiêu P&F** (`wyckoff/pnf.py`, khóa `pnf` trong YAML): P&F theo close, ô = 0,5 ATR lúc range xác nhận (làm tròn lên
  theo tick), đảo chiều 3 ô; đếm số cột từ đầu range đến LPS (chưa có LPS: đến trước SOS; chưa có SOS: đến phiên cuối, **tạm tính**).
  Thận trọng = đáy thấp nhất cấu trúc + cột × ô × 3; tích cực = đường đếm (đáy LPS, chưa có thì support) + cột × ô × 3. Chỉ tính ở pha C, D, E.
- Đặc tả giao diện cho dev: `docs/handoff-dashboard.md`. Biến môi trường: `WYCKOFF_CONFIG`, `WYCKOFF_CACHE_DIR`, `WYCKOFF_OUT_DIR`,
  `WYCKOFF_MODEL`, `WYCKOFF_NO_LLM`, `WYCKOFF_NO_MARKET`, `WYCKOFF_DEFAULT_SYMBOL`.
- Chưa có xác thực / giới hạn tần suất: mặc định chỉ nghe `127.0.0.1`; cần bổ sung trước khi mở ra Internet.
- **Giả thuyết H4** (`docs/h4-preregistration.md`, 308 mã): H4a SC hai phiên (`config/h4a.yaml`) và H4b range neo theo SC–AR (`config/h4b.yaml`) – **không chấp nhận**, mặc định tắt. H4b trung tính với thang tin cậy (chênh lệch cao − thấp +1,56 so với +1,55; P = 0,53). Chạy lại: `scripts/parallel_study.py`, `scripts/h4_eval.py`.
- **Giả thuyết H5** (`docs/h5-preregistration.md`, 311 mã): H5a SOS cần follow-through (`config/h5a.yaml`) và H5b chỉ phiên khóa trần cần follow-through (`config/h5b.yaml`) – **không chấp nhận**, mặc định `same_bar`. H5a: cao − thấp +1,53 so với +1,46 nhưng 2023–nay mức cao 60 phiên −2,03 so với −1,51, P = 0,61. Tham khảo: H5a loại 19% SOS, SOS còn lại 20 phiên +0,59 so với +0,17. Chạy lại: `scripts/parallel_study.py`, `scripts/h5_eval.py`.
- **Giả thuyết H6** (`docs/h6-preregistration.md`, 311 mã): tách UT / UTAD và chỉ xác nhận khi có yếu kém (`config/h6.yaml`, `utad.mode: ut_utad`) – **không chấp nhận** (trượt tiêu chí 2023–nay: −1,57 so với −1,51), mặc định `v2`. Đạt 4/5: cao − thấp +1,57 so với +1,46, P = 0,82. Tham khảo: upthrust kiểu v2 có lợi suất dương (20 phiên +1,01), UT đã xác nhận −0,14; pha invalid 20 phiên −0,21 so với +0,01. Chạy lại: `scripts/parallel_study.py`, `scripts/h6_eval.py`.
- **Giả thuyết H7** (`docs/h7-preregistration.md`, 311 mã): H7a thêm yếu tố sức mạnh cung cầu (`config/h7a.yaml`) và H7b thay nhãn đà giá bằng xu hướng trước range (`config/h7b.yaml`) – **không chấp nhận**, mặc định tắt. H7a: cao − thấp +1,30 so với +1,46, P = 0,07. H7b: +1,45 so với +1,46, P = 0,53. Tham khảo: Trending Up 60 phiên +1,58 so với nền, Trending Down −1,12; Re-accumulation +3,20, Re-distribution −2,11 (chưa có CI, có thể chỉ là quán tính giá). Chạy lại: `scripts/parallel_study.py`, `scripts/h7_reference.py`, `scripts/h7_eval.py`.
