# Giả thuyết H6 – tách UT / UTAD, xác nhận bằng yếu kém tiếp theo (chốt trước khi chạy, 04/11/2026)

Nguồn: quy chuẩn Wyckoff 04/11/2026 mục 5.5 ("UT… Xác nhận khi không reclaim được vùng breakout và sau đó xuất hiện yếu/SOW"),
5.6 ("UTAD… Xác nhận khi giá quay lại TR và SOW/breakdown củng cố Supply. Phân biệt UT/UTAD bằng vị trí trong vòng đời TR").
Phân tích khoảng cách: Project `claude/gap-analysis-quy-chuan-2026-11-04.md`. Quy tắc phân loại và xác nhận do người dùng chọn
(04/11/2026). Chốt trước khi chạy backtest; chưa xem kết quả lợi suất nào của quy tắc mới. Thống kê đã xem trước khi chốt (chỉ cấu trúc,
không có lợi suất): trên 1/3 mẫu cache, 857 upthrust ở 463 range, 200 range có ≥ 2 upthrust, tuổi range trung vị 44 phiên.

## Quy tắc (`utad.mode: ut_utad`, `config/h6.yaml`)

Phát hiện upthrust giữ nguyên điều kiện hiện tại (range xác nhận ≥ 20 phiên; high > resistance + max(0,1 ATR, 1 tick); trong ≤ 3 phiên
close ≤ resistance − 1 tick và close_pos ≤ 0,5). Khác ở cách gọi tên và cách xác nhận:

- **Phân loại**: upthrust đầu tiên trong một range = **UT**; từ upthrust thứ hai trong cùng range = **UTAD** (đã có UT trước → giai đoạn
  muộn). Đếm mọi upthrust đã quay lại TR trước đó trong range, kể cả upthrust chưa được xác nhận.
- **Chờ yếu kém**: sau phiên quay lại r, trong `utad.weakness_window` = **15** phiên (= `spring.test_window`, đối xứng với shakeout chờ Test):
  - close < giữa range ((support + resistance) / 2, cùng mức vô hiệu pha D mặc định) → **CONFIRMED** tại phiên đó;
  - close > đỉnh cao nhất của nhịp upthrust → **INVALIDATED** (breakout thật, không phải upthrust);
  - hết 15 phiên → **INVALIDATED** (không có yếu kém); hết dữ liệu → còn CANDIDATE.
- Vòng đời: DETECTED tại phiên vượt resistance, CANDIDATE tại phiên quay lại, CONFIRMED tại phiên yếu kém.
- **Pha**: UT hoặc UTAD **đã xác nhận** trong range của cấu trúc đang ở pha A–D → pha `invalid` (như UTAD hiện tại, nhưng muộn hơn và
  có điều kiện). Upthrust không xác nhận không đổi pha.

`utad.mode: v2` (mặc định) giữ nguyên hành vi hiện tại: mọi upthrust là UTAD, xác nhận tại phiên quay lại, vô hiệu cấu trúc ngay.

## Cách đo

- Mẫu: mọi mã trong `cache/` có ≥ 300 phiên, trừ chỉ số; từ 01/01/2018; `study_symbol` point-in-time (`scripts/parallel_study.py`).
- Đối chứng: cấu hình mặc định hiện tại (v2 + GT2 + SOS reclaim + vòng đời event; `sos.confirm_mode: same_bar`).
- Thước đo: lợi suất vượt VNINDEX điều chỉnh beta (`bexcess`), vào lệnh open phiên sau phiên xác nhận, chi phí 0,3%.

## Tiêu chí chấp nhận

`evaluate_hypothesis` như GT1, GT2, H4, H5; cần **cả 5**:

1. Thang tin cậy tăng đều thấp < trung bình < cao (20 phiên).
2. Mức cao có CI 90% > 0.
3. Chênh lệch cao − thấp lớn hơn đối chứng.
4. Giai đoạn 2023–nay: TB 60 phiên của mức cao lớn hơn đối chứng.
5. Bootstrap theo mã ghép cặp: P(chênh lệch > đối chứng) ≥ 0,80.

Tham khảo (không dùng để chấm): `bexcess` 20/60 phiên của tín hiệu UT, UTAD (H6) so với UTAD (đối chứng), pha invalid, pha D;
số upthrust được xác nhận / bị vô hiệu. Chấp nhận thì đề xuất bật mặc định, **chỉ bật sau khi người dùng duyệt**; không chấp nhận thì
để tắt và ghi kết quả. Nhãn UT/UTAD chỉ có trong `ut_utad`, nên nếu không chấp nhận thì mặc định vẫn là nhãn UTAD như cũ.

## Hạn chế biết trước

Các mã đã được xem ở các lần kiểm tra trước nên không phải mẫu mới; danh sách hiện tại có thiên lệch sống sót; tín hiệu chồng lấn.
Chưa có detector SOW/Distribution (bước 7) nên "yếu kém" là proxy (close dưới giữa range), không phải SOW đầy đủ. Hệ thống vẫn chỉ có
sơ đồ tích lũy: UT/UTAD chỉ dùng để vô hiệu cấu trúc tích lũy, chưa mở cấu trúc phân phối.

## Kết quả (04/11/2026): KHÔNG CHẤP NHẬN (trượt tiêu chí 4), giữ `utad.mode: v2`

Mẫu 311 mã, point-in-time. Đối chứng dùng lại lần chạy mặc định của H5 (cùng code mặc định: sự kiện, pha trên 307 mã trùng 100%).
Bảng đầy đủ: `output/h6/report.md` (`scripts/parallel_study.py`, `scripts/h6_eval.py`). Không chỉnh tham số nào sau khi xem kết quả.

| 20 phiên, bexcess % | Đối chứng | H6 |
|---|---|---|
| Thấp | −0,26 | −0,24 |
| Trung bình | +0,48 | +0,45 |
| Cao [CI 90%] | +1,19 [+0,79; +1,63] | +1,32 [+0,94; +1,70] |
| Cao − thấp [CI 90%] | +1,46 [+1,02; +1,93] | +1,57 [+1,15; +1,99] |
| Cao, 60 phiên, 2023–nay | −1,51 | −1,57 |
| P(chênh lệch > đối chứng) | – | 0,82 |

- Đạt 1, 2, 3, 5; **trượt 4** (2023–nay −1,57 so với −1,51). Theo quy tắc chốt trước: không chấp nhận.
- Tham khảo (không dùng để chấm):
  - Upthrust kiểu v2 (2.338 tín hiệu) đi kèm lợi suất **dương**: 20 phiên +1,01, 60 phiên +3,28 – tức là nhiều "UTAD" v2 thực ra đứng
    trước nhịp tăng, và vô hiệu cấu trúc ngay tại đó là sai hướng.
  - H6 chỉ xác nhận 652 upthrust (UT 390, UTAD 262). UT đã xác nhận: 20 phiên −0,14, 60 phiên +1,06 (yếu hơn rõ so với upthrust v2).
  - Pha invalid tách tốt hơn: 20 phiên +0,01 → −0,21, 60 phiên +0,75 → +0,21; pha D −0,20 → −0,04.
- Đọc kết quả: chờ yếu kém làm nhãn UT/UTAD và trạng thái invalid **có ý nghĩa hơn ở cấp sự kiện và pha**, thang tin cậy tốt hơn trên
  toàn kỳ, nhưng không cải thiện giai đoạn 2023–nay (vấn đề mở từ trước, chưa giả thuyết nào sửa được).
- Xem thử: `python run.py HPG --config config/h6.yaml`.
