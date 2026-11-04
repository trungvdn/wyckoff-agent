# Giả thuyết H5 – SOS cần follow-through, cờ khóa trần/sàn (chốt trước khi chạy, 04/11/2026)

Nguồn: quy chuẩn Wyckoff 04/11/2026 mục 4.7 ("Close vượt vùng kháng cự có ý nghĩa, không chỉ wick; có follow-through hoặc
giữ được vùng breakout. Nếu nhanh chóng quay lại TR, hạ cấp SOS"; "Một phiên tăng trần không tự động là SOS"), mục 8 (cờ
`limit_up`, `limit_down`, `ceiling_locked`, `floor_locked`). Phân tích khoảng cách: Project `claude/gap-analysis-quy-chuan-2026-11-04.md`.
Chốt trước khi chạy backtest; chưa xem kết quả nào của quy tắc mới.

## Cờ trần / sàn (không đổi quy tắc, chỉ ghi nhận)

Trên giá đã điều chỉnh, so với close phiên trước, ngưỡng như `floor_days` hiện có (`data.price_limit` − `data.limit_tolerance`, HOSE 6,5%):

- `limit_up`: Δclose ≥ +6,5%; `limit_down`: Δclose ≤ −6,5%.
- `ceiling_locked`: `limit_up` và high − close ≤ 1 tick (đóng cửa tại giá cao nhất = giá trần).
- `floor_locked`: `limit_down` và close − low ≤ 1 tick.

Cờ được ghi vào cột chỉ báo và `details` của event (`limit`), không tham gia điều kiện nào trừ H5b.

## Quy tắc SOS follow-through (`sos.confirm_mode`)

Phiên breakout i giữ nguyên điều kiện SOS hiện tại. Thay vì xác nhận ngay tại i, chờ tối đa `sos.follow_through_bars` = **3** phiên
(cùng số phiên với `ranges.exit_bars` và `lps.confirm_bars`):

- **Thất bại** (INVALIDATED, không thành SOS): có close < resistance trong (i, i+3] – giá quay lại range.
- **Xác nhận sớm** tại phiên j đầu tiên có close > high phiên i (mọi close từ i+1 đến j ≥ resistance) – follow-through.
- **Xác nhận** tại i+3 nếu cả 3 phiên đều đóng cửa ≥ resistance – giữ được breakout.
- Hết dữ liệu khi chưa đủ 3 phiên: còn là CANDIDATE.

Áp dụng cho cả SOS reclaim (mỗi range vẫn tối đa một SOS reclaim: candidate đầu tiên được xác nhận).
LPS xác nhận không sớm hơn SOS của nó. Phiên range thoát lên có thể đến trước phiên SOS xác nhận (pha E mở trước): khi đó SOS vẫn
được ghi vào cấu trúc làm bằng chứng, pha giữ E.

- **H5a** (`config/h5a.yaml`): `sos.confirm_mode: follow_through` – mọi SOS cần follow-through.
- **H5b** (`config/h5b.yaml`): `sos.confirm_mode: locked_follow_through` – chỉ phiên breakout có cờ `ceiling_locked` cần
  follow-through; phiên khác xác nhận ngay như hiện tại.

## Cách đo

- Mẫu: mọi mã trong `cache/` có ≥ 300 phiên, trừ chỉ số; từ 01/01/2018; `study_symbol` point-in-time (`scripts/parallel_study.py`).
- Đối chứng: cấu hình mặc định hiện tại (v2 + GT2 + SOS reclaim + vòng đời event).
- Thước đo: lợi suất vượt VNINDEX điều chỉnh beta (`bexcess`), vào lệnh open phiên sau phiên xác nhận, chi phí 0,3%.

## Tiêu chí chấp nhận

`evaluate_hypothesis` như GT1, GT2, H4; cần **cả 5**:

1. Thang tin cậy tăng đều thấp < trung bình < cao (20 phiên).
2. Mức cao có CI 90% > 0.
3. Chênh lệch cao − thấp lớn hơn đối chứng.
4. Giai đoạn 2023–nay: TB 60 phiên của mức cao lớn hơn đối chứng.
5. Bootstrap theo mã ghép cặp: P(chênh lệch > đối chứng) ≥ 0,80.

Tham khảo (không dùng để chấm): `bexcess` 20/60 phiên của tín hiệu SOS và pha D; số SOS bị loại; tỉ lệ SOS bị vô hiệu sau xác nhận.
Chấm H5a trước (thay đổi chính của quy chuẩn), H5b riêng. Chấp nhận thì đề xuất bật mặc định, **chỉ bật sau khi người dùng duyệt**;
không chấp nhận thì để tắt và ghi kết quả. Nếu cả hai được chấp nhận, chọn theo tiêu chí 3 không phải là quy tắc chốt trước –
sẽ báo cả hai để người dùng quyết định.

## Hạn chế biết trước

Các mã đã được xem ở các lần kiểm tra trước (VN30, VNMidCap, VNSmallCap, H4) nên không phải mẫu mới; danh sách hiện tại có thiên
lệch sống sót; tín hiệu chồng lấn; giá đã điều chỉnh nên cờ trần/sàn ở ngày GDKHQ có thể sai; `price_limit` một giá trị cho mọi mã
(HOSE 7%), mã HNX/UPCoM trong cache bị đánh giá theo biên độ HOSE. Theo dữ liệu ngày, không phân biệt được khóa trần lúc ATC.

## Kết quả (04/11/2026): cả hai KHÔNG CHẤP NHẬN, giữ `sos.confirm_mode: same_bar`

Mẫu 311 mã (`cache/`, ≥ 300 phiên, trừ chỉ số), point-in-time. Bảng đầy đủ: `output/h5/report.md`
(`scripts/parallel_study.py`, `scripts/h5_eval.py`). Không chỉnh tham số nào sau khi xem kết quả.

| 20 phiên, bexcess % | Đối chứng | H5a | H5b |
|---|---|---|---|
| Thấp | −0,26 | −0,17 | −0,21 |
| Trung bình | +0,48 | +0,64 | +0,56 |
| Cao [CI 90%] | +1,19 [+0,79; +1,63] | +1,36 [+0,93; +1,80] | +1,18 [+0,77; +1,59] |
| Cao − thấp [CI 90%] | +1,46 [+1,02; +1,93] | +1,53 [+1,07; +1,98] | +1,38 [+0,93; +1,82] |
| Cao, 60 phiên, 2023–nay | −1,51 | −2,03 | −2,13 |
| P(chênh lệch > đối chứng) | – | 0,61 | 0,27 |

- H5a đạt tiêu chí 1–3, trượt 4 (2023–nay tệ hơn) và 5 (P = 0,61). H5b trượt 3, 4, 5.
- Tham khảo (không dùng để chấm): H5a loại 19% SOS (3.838 → 3.095); tín hiệu SOS còn lại tốt hơn rõ (20 phiên +0,17 → +0,59;
  60 phiên +1,58 → +2,22), tín hiệu mở pha D −0,20 → +0,06. Phiên SOS khóa trần ít (~120 tín hiệu), nên H5b gần như không đổi gì.
- Đọc kết quả: follow-through **lọc SOS tốt hơn ở cấp sự kiện**, nhưng **không cải thiện thang tin cậy** đủ để vượt tiêu chí, và làm
  điểm yếu 2023–nay nặng hơn. Không có bằng chứng để đổi mặc định.
- Vẫn dùng được để xem: `python run.py HPG --config config/h5a.yaml` (SOS thất bại hiện ở danh sách candidate, trạng thái INVALIDATED).
- Nếu muốn khai thác kết quả cấp sự kiện (ví dụ dùng follow-through riêng cho điểm SOS trong thang tin cậy), đó là giả thuyết mới, cần
  đăng ký trước riêng.
