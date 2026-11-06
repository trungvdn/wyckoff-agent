# Đánh giá lại nhãn: tiềm năng, xác nhận, bác bỏ (05/11/2026)

Mã nguồn: `wyckoff/revision.py`, ngưỡng trong `RevisionConfig`. Test: `tests/test_revision.py`.

## Hai góc nhìn

| | Biểu đồ hồi cứu | Nhật ký tại từng thời điểm |
|---|---|---|
| Câu hỏi | Với dữ liệu đến hôm nay, đoạn này là gì? | Tại phiên đó, hệ thống biết gì? |
| Nguồn | `result.revision`, trạng thái cuối | `result.events`, `result.phases`, `result.stages`, `status_at(t)` |
| Dùng cho | Dashboard | Backtest, điểm tin cậy, H1–H8 |

Lớp này chỉ ghi nhận. Sự kiện mới không có điểm tin cậy và không vào backtest. Dashboard vẫn hiện điểm tin cậy của nhật ký.

## Quy tắc

| Loại | Tiềm năng khi | Xác nhận khi | Bác bỏ khi |
|---|---|---|---|
| Markdown, từ range | Range thoát xuống; hoặc đã bị bác bỏ rồi thủng lại đủ tiêu chí thoát range | Đủ 5 điều kiện trong `docs/stage-definitions.md` | Trước xác nhận: close >= support. Sau xác nhận, trong 60 phiên: close >= resistance hoặc SOS reclaim |
| Markdown, từ SMA | 5 close liên tiếp dưới SMA50 đang giảm | Đủ 5 điều kiện, hỗ trợ là đáy swing gần nhất khi vào xu hướng | Close trên SMA50 lúc vào xu hướng |
| Markup, từ range | Range thoát lên | Xem `docs/stage-definitions.md` (Candidate, Developing, Confirmed) | Close < support (trong 60 phiên nếu đã xác nhận) |
| Markup, từ SMA | 5 close liên tiếp trên SMA50 đang tăng | Như trên, cần có nền giá | Close dưới SMA50 lúc vào xu hướng |
| Spring hồi phục nhanh | Low lại thủng support khi Markdown đang bị bác bỏ, còn trong thời hạn đánh giá | Trong 4 phiên tính cả phiên thủng: close >= support + 1 tick, nến tăng, volume >= 1,5x TB20, close_pos >= 0,7 | Có SC xác nhận tạo sau cú thủng; sau xác nhận: close < đáy − 0,5 ATR |
| Spring kéo dài | Range thoát xuống | Trong 30 phiên: close >= support + 1 tick, nến tăng, volume >= 1,5x TB20, close_pos >= 0,7, Markdown chưa xác nhận, chưa có SC xác nhận tạo sau cú thủng | Hết hạn; có SC xác nhận tạo sau cú thủng (cấu trúc mới); sau xác nhận: close < đáy − 0,5 ATR |
| LPS | Xem `docs/event-definitions.md` | Xem `docs/event-definitions.md` | Xem `docs/event-definitions.md` |
| Range là Accumulation | Xem `docs/stage-definitions.md` (Candidate, Developing) | Xem `docs/stage-definitions.md` | Xem `docs/stage-definitions.md` |
| SOS | Phiên breakout | Follow-through 3 phiên | Theo `phase.d_invalid_mode` (mặc định dưới giữa range) |
| UT/UTAD | Vượt rồi quay lại | Close dưới giữa range trong 15 phiên | Close vượt đỉnh upthrust trong 60 phiên |
| Sự kiện khác | Theo `lifecycle` | Theo `lifecycle` | Theo `lifecycle`; AR, ST theo SC; AR(d), ST(d) theo BC |

Trên biểu đồ hồi cứu: Spring kéo dài đã xác nhận làm cả vùng từ phiên Spring đến phiên trước SOS thành pha C; Spring bị bác bỏ thì vùng đó trở lại chờ xác nhận. Range là Accumulation được vẽ một đoạn liền từ đầu range đến trước Markup, thay cho nhãn theo hướng thoát (Initial Accumulation sau Markdown, Re-accumulation sau Markup).

Xu hướng kết thúc mà chưa đủ điều kiện thì giữ nguyên tiềm năng. Volume và độ sâu khi thoát xuống chỉ ghi vào `details` (`breakdown`), không dùng để quyết định nhãn.

## Biên range theo close

`ranges.pivot_source: close` trong `config/v3.yaml`, dùng cho dashboard và `run.py`. `Config()` và `config/default.yaml` giữ `high_low`, nên `backtest.py`, `config/h*.yaml` và test tái lập như cũ. Muốn dashboard dùng cấu hình mặc định: đặt `WYCKOFF_CONFIG` rỗng.

## Số đo khám phá

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Số đếm gồm cả ứng viên chưa từng xác nhận. "Từng xác nhận" là tỷ lệ từng đạt xác nhận, kể cả sau đó bị bác bỏ.

| Loại | n thật | Từng xác nhận, thật / placebo (%) | Cuối cùng bác bỏ, thật / placebo (%) | Còn tiềm năng, thật / placebo (%) |
|---|---|---|---|---|
| Markdown từ range | 3.692 | 9,1 / 9,6 | 42,4 / 48,6 | 49,2 / 43,1 |
| Markdown từ SMA | 1.283 | 3,2 / 3,6 | 29,9 / 32,6 | 67,3 / 64,4 |
| Markup từ range | 4.131 | 27,7 / 26,3 | 8,0 / 7,5 | 28,5 / 34,6 |
| Markup từ SMA | 1.331 | 10,6 / 10,2 | 29,2 / 30,7 | 52,1 / 50,0 |
| Spring kéo dài | 3.690 | 31,4 / 37,2 | 77,2 / 74,6 | 1,4 / 0,5 |
| SOS | 4.520 | 81,3 / 81,1 | 45,5 / 47,4 | 6,0 / 5,8 |
| UTAD | 2.274 | 35,8 / 39,4 | 70,9 / 77,6 | 8,4 / 3,3 |

**Spring hồi phục nhanh** (231 ca thật, 333 placebo; mọi ca đều từng xác nhận vì không có ứng viên chờ): bị bác bỏ về sau 49,4% / 52,9%; lợi suất 60 phiên +4,4% / +3,1%, trung vị 0,0% / +1,4%; close dưới support trong 60 phiên 72,5% / 70,7%; close trên resistance trong 60 phiên 55,9% / 55,2%. So mốc hồi phục: 3 phiên có 190 ca, +5,2% / +3,7%; 5 phiên có 271 ca, +4,3% / +2,8%. Các tỷ lệ gần với placebo ở cả ba mốc, nên 4 phiên được chọn theo mô tả hành vi giá, không phải vì kết quả tốt hơn.

Số đo của LPS, SC, AR và ST: `docs/event-definitions.md`. Số đo của Markdown và Accumulation: `docs/stage-definitions.md`.

Các tỷ lệ này gần với placebo, nên chúng mô tả hành vi của quy tắc, chưa phải bằng chứng về lợi thế. Trạng thái "xác nhận" không phải tín hiệu. Chưa kiểm định; muốn dùng để ra quyết định cần đăng ký giả thuyết riêng, gồm placebo và đối chứng vị trí giá như `docs/h8-investigation.md`.

## Giới hạn

- Khám phá trên cùng mẫu với H8, ngưỡng gợi ra một phần từ ca SZC, placebo một seed, chưa tính phí.
- Điểm tin cậy và mức giá trên dashboard vẫn lấy từ nhật ký, chưa theo trạng thái đánh giá lại.
- Backtest chưa chạy với `pivot_source: close`, nên các số liệu backtest đã công bố thuộc cấu hình high_low.
