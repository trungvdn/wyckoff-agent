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
```

Đầu ra trong `output/`: `HPG_wyckoff.html` (biểu đồ, nền tô theo pha), `HPG_events.csv`, `HPG_ranges.csv`,
`HPG_phases.csv` (các đoạn pha), `HPG_current_phase.json` (pha hiện tại + bằng chứng + mức xác nhận/vô hiệu — đầu vào cho LLM ở giai đoạn 2).

## Cấu trúc

```
config/default.yaml        mọi ngưỡng (chỉ cần ghi khóa muốn đổi)
wyckoff/config.py          dataclass cấu hình + load YAML (báo lỗi khóa sai)
wyckoff/data/              fetcher.py (vnstock, chuẩn hóa, kiểm tra), cache.py, loader.py (get_ohlcv)
wyckoff/indicators/core.py ATR Wilder, TB volume, spread, close_pos, SMA
wyckoff/detectors/         swings.py, trading_range.py, events.py (SC/Spring/SOS), structure.py (PS/AR/ST/LPS/UTAD), models.py
wyckoff/phases.py          state machine pha A–E, current_phase()
wyckoff/market.py          bối cảnh thị trường: xu hướng chỉ số, RS, phân kỳ đáy, đối chiếu sự kiện
wyckoff/charts/plot.py     plotly: nến + volume + range + sự kiện
wyckoff/agent/             GĐ2: payload.py, prompts.py, llm.py, validate.py, explain.py, report.py
wyckoff/backtest/          event study: metrics.py, study.py, summary.py, report.py, universe.py
wyckoff/pipeline.py        analyze(): chỉ báo -> swing -> range -> sự kiện -> pha; .current(), .since()
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
| **SC failed** | Sau khi SC xác nhận, trong 30 phiên và trước khi có AR (close cao nhất ≥ đáy SC + 3 ATR): close < đáy SC − 0.5 ATR |
| **Bối cảnh range** | Lợi suất 120 phiên trước phiên bắt đầu range: ≤ −15% accumulation, ≥ +30% distribution, còn lại neutral; thiếu lịch sử → unknown |
| **Spring** | Trong range có bối cảnh thuộc `spring.allowed_contexts` (mặc định: tất cả). Range đã xác nhận ≥ 5 phiên trước. Phiên thủng đầu tiên: low < support − max(0.1 ATR, 1 tick). Phiên hồi trong ≤ 3 phiên (tính cả phiên thủng): close ≥ support + 1 tick **và** close_pos ≥ 0.5. Mọi phiên có low < support có vol_ratio < 1.0 → **Spring volume thấp**, xác nhận tại phiên hồi |
| **Spring (shakeout) + Test** | Như trên nhưng có phiên thủng vol_ratio ≥ 1.0 → chỉ xác nhận khi có **Test** trong 15 phiên sau phiên hồi: low ≥ đáy shakeout, low ≤ support + 0.1 ATR, volume < 0.6 × volume phiên thủng lớn nhất, support ≤ close ≤ resistance |
| **Gộp Spring** | Spring mới có phiên thủng cách Spring trước < 10 phiên chỉ được giữ nếu đáy thấp hơn (xét theo thứ tự xác nhận, không nhìn trước) |
| **SOS** | trong range (hoặc các phiên đang phá range trước khi xác nhận thoát); close > open; close > resistance + 0.2 ATR; spread_atr > 1.2; vol_ratio > 1.5; close_pos ≥ 0.7 |
| **PS** | Trong 40 phiên trước SC (lấy phiên gần nhất), close < SMA50: vol_ratio ≥ 1.5, close_pos ≥ 0.5, spread_atr ≥ 1.0, low > đáy SC. Xác nhận tại phiên xác nhận SC |
| **AR** | Đỉnh pivot (3 phiên mỗi bên) đầu tiên trong 30 phiên sau SC với high ≥ đáy SC + 3 ATR. Xác nhận ở pivot + 3. SC đã failed thì không có AR |
| **ST** | Sau AR, trong 60 phiên: low ∈ [đáy SC − 0.5 ATR, đáy SC + 1 ATR], volume < 0.7 × volume SC, biên độ < biên độ SC, close ≥ đáy SC; các ST cách nhau ≥ 10 phiên |
| **LPS** | Sau SOS, trong 20 phiên: low ≥ resistance − 1 ATR, low ≤ close cao nhất từ SOS − 0.5 ATR, vol_ratio < 1.0, spread_atr < 1.0; xác nhận khi trong 3 phiên sau có close > high phiên LPS. Mỗi SOS tối đa một LPS |
| **UTAD** | Range xác nhận ≥ 20 phiên; phiên đầu tiên high > resistance + max(0.1 ATR, 1 tick); trong ≤ 3 phiên close ≤ resistance − 1 tick với close_pos ≤ 0.5. Là sự kiện cảnh báo: vô hiệu cấu trúc tích lũy |

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
| invalid | SC failed; UTAD; range thoát xuống; pha C có close < đáy Spring − 0.5 ATR | cấu trúc mới khi có SC hoặc range mới |

`current_phase()` trả về pha, ngày bắt đầu, support/resistance, ATR, bằng chứng (các sự kiện của cấu trúc) và
**mức xác nhận / vô hiệu tính sẵn**: A → ST / SC failed; B → Spring, SOS / range thoát xuống; C → SOS / đáy Spring − 0.5 ATR;
D → thoát range / đáy LPS (hoặc resistance − 1 ATR); E → quay lại dưới resistance. Kèm cảnh báo khi phiên cuối đóng cửa sát đáy
(close_pos ≤ 0.2) với volume ≥ 1.2× TB20.

## Chống look-ahead
- Chỉ báo causal; swing có độ trễ xác nhận; range xử lý online; Spring xác nhận ở phiên quay lại.
- Nến hôm nay bị bỏ nếu chạy trước 15:00 giờ VN (nến chưa hoàn tất).
- `tests/test_detectors.py::test_no_lookahead` chạy pipeline trên dữ liệu cắt tại nhiều thời điểm
  và đòi hỏi kết quả (sự kiện, range, chuỗi pha) trùng với dữ liệu đầy đủ (lọc theo `confirmed_idx`).

## Dữ liệu
- `vnstock` 5.x (tương thích 3.x). Nguồn chính VCI, dự phòng KBS (giá nghìn đồng, đã điều chỉnh).
- Chuỗi dự phòng, dừng ở cách đầu tiên phủ đủ từ `start` (dung sai 15 ngày):
  `Quote.history(start, end)` → `Market().equity().ohlcv(start, end, limit=N)` → `Quote.history` chia đoạn 365 ngày, lặp lại với nguồn dự phòng.
  Không cách nào phủ đủ → dùng kết quả phủ xa nhất và cảnh báo **THIẾU LỊCH SỬ**.
- Chẩn đoán: `python scripts/check_vnstock.py HPG` in cấp tài khoản và độ phủ của từng cách gọi.
- **Khởi động**: `run.py` tải thêm ~120 phiên trước `--start`, phân tích trên toàn bộ rồi chỉ báo cáo/vẽ từ `--start` (`AnalysisResult.since`).
- **Kiểm tra điều chỉnh giá**: trên HOSE |ΔClose| ≤ 7%. Phiên vượt 7.5% bị cảnh báo là có thể chưa điều chỉnh
  (ngày GDKHQ). HNX: đặt `data.price_limit: 0.10`.
- Cache cập nhật tăng dần với 10 ngày chồng lấn; nếu close vùng chồng lấn lệch > 0.1% (có sự kiện quyền mới) thì tải lại toàn bộ.

## Giai đoạn 2: LLM diễn giải

Nguyên tắc: **code tính mọi con số, LLM chỉ diễn giải và đánh giá bối cảnh.**

1. `payload.py` – gói JSON tất định (~5 KB): pha hiện tại, mức giá có ID (`confirm_0`, `invalidate_0`...),
   sự kiện bằng chứng (`ev_0`...), 20 phiên gần nhất, lịch sử pha/range, cảnh báo, ngưỡng quy tắc,
   **mức tin cậy do code tính** (SC +1, ST +1, Spring +1, Test < 0,5× shakeout +1, SOS +1, LPS +1,
   bối cảnh accumulation +1 / distribution −1, mỗi cảnh báo −1 (SOS/LPS thất bại −2); ≤ 0 thấp, 1–2 trung bình, ≥ 3 cao).
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

Điểm tin cậy thêm (2 yếu tố, mỗi yếu tố trong [−1, +1]): (1) chỉ số uptrend +1 / downtrend −1; (2) nhóm **sức mạnh tương đối**
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
