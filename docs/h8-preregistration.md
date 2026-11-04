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

## Kết quả (04/11/2026): KHÔNG CHẤP NHẬN cả H8a và H8b, không hiện nhãn nghiêng trên dashboard

Mẫu 311 mã, 6.794 range từ 2018 (6.643 đã kết thúc), trên bản chép cache đóng băng (`output/h8/cache`). Bảng đầy đủ: `output/h8/report.md` (`scripts/h8_eval.py`, `wyckoff/evidence.py`).
Không chỉnh tham số nào sau khi xem kết quả. Nền: thoát lên 52,5%, thoát xuống 47,5%.

| Tiêu chí | H8a | H8b |
|---|---|---|
| 1. ≥ 300 range mỗi chiều | Đạt (533; 503) | Đạt (2.285; 1.178) |
| 2. Nghiêng tích lũy thoát lên ≥ 57,5% | **Trượt: 34,3%** | Đạt: 88,1% |
| 3. Nghiêng phân phối thoát xuống ≥ 52,5% | **Trượt: 24,1%** | Đạt: 87,3% |
| 4. Trung vị sớm ≥ 10 phiên | Đạt: 21 phiên | **Trượt: 2 phiên** |
| 5. Chênh bexcess 20 phiên > 0, CI > 0 | **Trượt: −1,54 [−2,57; −0,57]** | **Trượt: −1,02 [−1,57; −0,45]** |
| 6. Dương ở cả hai giai đoạn | **Trượt: −0,95; −2,22** | **Trượt: −0,89; −1,15** |

Đọc kết quả:

- **H8a ngược chiều lý thuyết, không chỉ là không có tín hiệu**: nghiêng tích lũy lại hay thoát xuống, nghiêng phân phối lại hay thoát lên; chênh lợi suất âm với CI không chứa 0, ở cả hai giai đoạn. Đã kiểm tra độc lập, không phải lỗi dấu (tham khảo: range chỉ có Spring thoát lên 18,0%, n = 1.322; chỉ có UTAD thoát lên 84,2%, n = 787; không có sự kiện nào thoát lên 57,1%, n = 3.895; đối chiếu trực tiếp từ detector trên 20 mã cho cùng chiều).
- **H8b đúng như dự báo trong phần hạn chế**: tỷ lệ thoát cao vì SOS / SOW gần như trùng lúc thoát (trung vị 2 phiên), không phải tín hiệu sớm. Lợi suất sau tín hiệu cũng không cùng chiều nhãn.
- **Giải thích khả dĩ, chưa kiểm định**: Spring đòi hỏi giá đã chạm biên dưới, upthrust đòi hỏi giá đã chạm biên trên, nên các sự kiện này có thể chỉ phản ánh giá đang trôi về biên nào và biên đó bị thử nhiều lần. Khi đó đây là đặc điểm của cách định nghĩa range và sự kiện, không nhất thiết là "Wyckoff sai".
- **Không đảo dấu để dùng**: quy tắc đảo được gợi ý từ chính dữ liệu này, nên chỉ có thể là giả thuyết mới, đăng ký trước và cần mẫu chưa dùng. Nhãn Spring, UTAD và pha C ở cả hai sơ đồ nên được đọc là mô tả sự kiện, không phải bằng chứng về hướng thoát.
