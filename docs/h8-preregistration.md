# Giả thuyết H8 – bằng chứng trong range có nghiêng được giả thuyết sớm không (chốt trước khi chạy, 04/11/2026)

Nguồn: Bước 4 của lộ trình áp dụng kiến trúc 5 tầng. Hiện nhãn giai đoạn chỉ chốt khi range thoát, nên 53,3% số phiên là Transition / Uncertain. H8 kiểm tra xem
sự kiện đã xác nhận trong range có cho biết sớm hướng thoát hay không. Quy tắc do Claude đề xuất từ lý thuyết Wyckoff; người dùng duyệt 04/11/2026. **Chưa viết mã, chưa chạy số liệu nào của quy tắc này.**

Kết quả đã biết trước khi đề xuất (nên không hoàn toàn mù):

- Hướng thoát range gần như 50/50 theo xu hướng trước đó; nền thoát lên 52,5%, thoát xuống 47,5%.
- Ngay trước khi thoát: pha D phân phối chiếm 35% khi thoát xuống, 3% khi thoát lên; pha D tích lũy chiếm 49% khi thoát lên, 4% khi thoát xuống. SOS / SOW đòi hỏi close đã ngoài biên nên gần như trùng lúc thoát: đây là lý do tách H8a khỏi H8b.
- Backtest trước: Spring và Test không có lợi thế; upthrust kiểu v2 đi kèm lợi suất dương (H6). Hai kết quả này gợi ý H8a có thể không đạt; quy tắc không được chỉnh theo chúng.

## Quy tắc

Tại mỗi phiên t khi range đang hoạt động, cộng điểm các sự kiện của range đó có `confirmed_idx` ≤ t và trạng thái tại t chưa INVALIDATED (`status_at(t)`):

| Sự kiện | H8a: chỉ sự kiện trong range | H8b: thêm sự kiện phá biên |
|---|---|---|
| SC, ST, Spring, Test (của cấu trúc tích lũy gắn với range) | +1 mỗi loại mỗi lần | +1 |
| BC, ST(d), UT, UTAD (của cấu trúc phân phối gắn với range) | −1 mỗi loại mỗi lần | −1 |
| SOS / SOW | không tính | +2 / −2 |
| LPS / LPSY | không tính | +1 / −1 |

- Tổng ≥ +2: **nghiêng tích lũy**. Tổng ≤ −2: **nghiêng phân phối**. Còn lại: chưa nghiêng.
- Tín hiệu là phiên đầu tiên range đổi sang một trạng thái nghiêng; một range có thể đổi chiều nhiều lần.
- Dùng `utad.mode: v2` (mặc định) và các ngưỡng phát hiện hiện tại. Không đổi sự kiện, pha, điểm tin cậy.

## Cách đo

- Mẫu: mọi mã trong cache có ≥ 300 phiên, trừ chỉ số; từ 01/01/2018. Chép cache thành bản đóng băng riêng trước khi chạy, ghi lại ngày dữ liệu cuối.
- Hướng thoát: chỉ tính range đã kết thúc; lấy trạng thái nghiêng cuối cùng trước phiên thoát.
- Sớm: số phiên từ tín hiệu nghiêng đầu tiên cùng chiều với trạng thái cuối đến phiên range thoát.
- Lợi suất: `bexcess` 20 phiên, vào lệnh open phiên sau tín hiệu, chi phí 0,3%. Bootstrap theo mã, CI 90%.

## Tiêu chí chấp nhận

Chấm riêng H8a và H8b, mỗi giả thuyết cần **cả 6**:

1. Đủ mẫu: mỗi chiều nghiêng có ≥ 300 range đã kết thúc.
2. Nghiêng tích lũy: tỷ lệ thoát lên ≥ nền + 5 điểm %.
3. Nghiêng phân phối: tỷ lệ thoát xuống ≥ nền + 5 điểm %.
4. Sớm: trung vị ≥ 10 phiên trước khi range thoát.
5. `bexcess` 20 phiên của nghiêng tích lũy trừ nghiêng phân phối > 0, cận dưới CI 90% > 0.
6. Chênh lệch ở tiêu chí 5 dương ở cả 2018–2022 và 2023–nay.

Chấp nhận thì đề xuất hiện nhãn nghiêng trên dashboard, **chỉ bật sau khi người dùng duyệt**, và vẫn ghi là chưa chốt. Không chấp nhận thì giữ thẻ hiện tại và ghi kết quả.
Dù kết quả thế nào cũng không đổi điểm tin cậy trong H8: H7 vừa cho thấy thêm yếu tố giai đoạn không cải thiện thang này. Không chỉnh tham số sau khi xem kết quả.

## Tham khảo (không dùng để chấm)

Tỷ lệ thoát và `bexcess` 20 / 60 phiên theo từng mức tổng điểm và từng loại sự kiện; so với nền cùng giai đoạn; tỷ lệ range không bao giờ nghiêng; số lần đổi chiều trong một range.

## Hạn chế biết trước

- **Không phải mẫu mới**: 311 mã đã dùng cho H4–H7; danh sách hiện tại có thiên lệch sống sót; tín hiệu chồng lấn; không hiệu chỉnh cho số lần thử.
- **H8b gần như tất yếu đạt tiêu chí 2, 3**: SOS / SOW xảy ra sát lúc thoát. Tiêu chí 4 là chốt chặn chính; H8a mới là phép thử đúng nghĩa "sớm".
- **Trọng số đều và ngưỡng ±2 là lựa chọn đơn giản**, không tối ưu. Trượt không có nghĩa mọi cách dùng bằng chứng đều vô ích, nhưng không được thử lại với ngưỡng khác nếu không đăng ký mới.
- **Ít cấu trúc có climax**: chỉ 2,6% range gắn với SC, nên SC, ST, BC, ST(d) ít tác động; điểm chủ yếu đến từ Spring, Test và upthrust.
