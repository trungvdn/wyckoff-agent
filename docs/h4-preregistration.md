# Giả thuyết H4 – neo cấu trúc theo SC và AR (chốt trước khi chạy, 04/11/2026)

Nguồn ý tưởng: đối chiếu thủ công mã SZC. **SZC bị loại khỏi phần chấm điểm.** Các tham số dưới đây lấy từ quy tắc đã có
hoặc từ ca SZC; không dò thêm sau khi xem kết quả.

## Quy tắc

- **H4a – SC hai phiên** (`config/h4a.yaml`). Nến climax đóng cửa thấp vẫn xác nhận được dù phiên sau thủng nhẹ đáy:
  chờ 3 phiên thay vì 2 (`sc.zone_bars: 3`), cho thủng tối đa 0,5 ATR (`sc.zone_undercut_atr: 0.5`, cùng ngưỡng với SC failed).
  Đáy SC là đáy thấp nhất của cả vùng climax.
- **H4b – H4a + range neo theo SC–AR** (`config/h4b.yaml`). Khi AR xác nhận và đang không có range hoạt động: mở range với
  support = đáy SC, resistance = đỉnh AR, nếu chiều cao ≤ 6 ATR (`ranges.max_height_atr`, quy tắc có sẵn)
  (`ranges.anchor_sc_ar: true`). Các quy tắc thoát range, Spring, SOS, LPS, UTAD giữ nguyên trên biên mới.

## Cách đo

- Mẫu: mọi mã trong `cache/` có ≥ 300 phiên, trừ chỉ số và SZC; từ 01/01/2018; dùng `study_symbol` có point-in-time.
- Đối chứng: cấu hình mặc định hiện tại (đã có SOS reclaim).
- Thước đo: lợi suất vượt VNINDEX điều chỉnh beta (`bexcess`).

## Tiêu chí chấp nhận

Dùng nguyên `evaluate_hypothesis` đã dùng cho GT1, GT2; cần **cả 5**:

1. Thang tin cậy tăng đều thấp < trung bình < cao (20 phiên).
2. Mức cao có CI 90% > 0.
3. Chênh lệch cao − thấp lớn hơn đối chứng.
4. Giai đoạn 2023–nay: TB 60 phiên của mức cao lớn hơn đối chứng.
5. Bootstrap theo mã ghép cặp: P(chênh lệch > đối chứng) ≥ 0,80.

Chấp nhận thì bật mặc định; không chấp nhận thì để tắt và ghi kết quả. Chấm H4b trước vì đó là thay đổi cần cho SZC; H4a chấm riêng.

## Hạn chế biết trước

Các mã này đã được xem ở các lần kiểm tra trước (VN30, VNMidCap, VNSmallCap), nên đây không phải mẫu hoàn toàn mới; danh sách
hiện tại có thiên lệch sống sót; tín hiệu trong cùng cấu trúc chồng lấn.

## Kết quả (04/11/2026): cả hai KHÔNG CHẤP NHẬN, giữ tắt mặc định

Mẫu 308 mã, loại SZC. Bảng đầy đủ: `output/h4/report.md` (`scripts/parallel_study.py`, `scripts/h4_eval.py`).

| | Đối chứng | H4a | H4b |
|---|---|---|---|
| Thấp, 20 phiên | −0,29 | −0,26 | −0,34 |
| Trung bình | +0,46 | +0,46 | +0,50 |
| Cao | +1,26 | +1,27 | +1,22 |
| Cao − thấp [CI 90%] | +1,55 [+1,11; +1,99] | +1,52 [+1,08; +1,97] | +1,56 [+1,14; +2,02] |
| Cao, 60 phiên, 2023–nay | −1,61 | −1,55 | −1,53 |
| P(chênh lệch > đối chứng) | – | 0,27 | 0,53 |

- H4a trượt tiêu chí 3 và 5. H4b chỉ trượt tiêu chí 5, nhưng chênh lệch +0,01 là không đáng kể.
- Đọc kết quả: H4b **trung tính**, không làm thang tin cậy tốt lên hay xấu đi rõ rệt. Nó không có bằng chứng cải thiện khả năng
  phân loại; lợi ích duy nhất đã thấy là cấu trúc đúng hơn trên ca SZC, và đó là ca sinh ra quy tắc.
- Bật thử không đổi mặc định: `python serve.py --config config/h4b.yaml`.
