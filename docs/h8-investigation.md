# Điều tra sau H8: vì sao Spring và UTAD đi ngược lý thuyết (05/11/2026)

Đây là phân tích khám phá sau khi xem kết quả H8, **không phải kiểm định đã đăng ký**. Không đổi quy tắc, sự kiện, pha hay điểm tin cậy nào.
Chạy trên bản cache đóng băng của H8 (`output/h8/cache`, 311 mã, từ 2018). Chạy lại: `scripts/h8_investigate.py`, `scripts/h8_placebo_extra.py`.

## Kết luận

**Hiện tượng chủ yếu là hệ quả cơ học của cách định nghĩa, không phải đặc điểm của thị trường, và cũng không phải bằng chứng chống lại Wyckoff.**
Spring chỉ xảy ra khi giá đang ở sát biên dưới, UTAD khi giá đang ở sát biên trên; giá ở gần biên nào thì range dễ thoát qua biên đó, kể cả trên dữ liệu không có cấu trúc.
Khi đã biết vị trí giá, hai sự kiện này gần như không cho thêm thông tin về hướng thoát.

## Bằng chứng

### 1. Placebo: hiện tượng vẫn còn trên dữ liệu vô nghĩa

Hoán vị ngẫu nhiên các ngày giao dịch của từng mã (giữ phân phối lợi suất, hình dạng nến, volume; phá thứ tự thời gian), rồi chạy lại toàn bộ pipeline.

| Thoát lên (%) | Dữ liệu thật | Xáo từng ngày, seed 1 | Xáo từng ngày, seed 2 | Xáo khối 20 phiên |
|---|---|---|---|---|
| Mọi range | 52,5 (n = 6.643) | 55,0 | 55,3 | 54,9 |
| Không có sự kiện | 57,3 (n = 4.126) | 59,2 | 59,3 | 58,2 |
| Chỉ có Spring | **18,0** (n = 1.322) | **22,3** | **22,8** | **23,0** |
| Chỉ có UTAD | **84,2** (n = 787) | **83,2** | **84,8** | **85,0** |

Chênh lệch lớn (khoảng 60 điểm %) xuất hiện cả khi không có gì để "tích lũy" hay "phân phối". Dữ liệu thật và placebo chỉ lệch 4 đến 5 điểm % với Spring, khoảng 1 điểm % với UTAD; một phần là do nền thoát lên của placebo cao hơn 2,5 điểm %.

### 2. Vị trí trong range giải thích gần hết

| Vị trí giá trong range (0 = support, 1 = resistance) | < 0 | 0–0,2 | 0,2–0,4 | 0,4–0,6 | 0,6–0,8 | 0,8–1 | > 1 |
|---|---|---|---|---|---|---|---|
| Thoát lên, dữ liệu thật (%) | 12,2 | 26,6 | 40,9 | 54,5 | 67,0 | 78,0 | 88,4 |
| Thoát lên, placebo (%) | 12,4 | 28,9 | 42,1 | 54,6 | 65,2 | 75,4 | 89,4 |

Hai đường gần như trùng nhau. Khi xác nhận, Spring có vị trí trung vị 0,10 và đà 20 phiên −1,27 ATR; UTAD là 0,89 và +1,52 ATR.

So sự kiện với các phiên chưa có sự kiện đó, cùng vị trí và tuổi range: Spring 27,2% so với 28,7%; UTAD 74,7% so với 77,4%. **Khác biệt gần như biến mất.**

Hồi quy xác suất thoát lên (điểm %, CI 90% bootstrap theo mã):

| Hệ số | Thật, chưa kiểm soát | Placebo, chưa kiểm soát | Thật, kiểm soát vị trí và đà | Placebo, kiểm soát vị trí và đà |
|---|---|---|---|---|
| Đã có Spring | −10,7 [−14,3; −7,1] | −9,7 [−12,1; −7,1] | +3,3 [−0,1; +6,7] | +0,9 [−1,2; +3,2] |
| Đã có UTAD | +7,0 [+3,0; +11,2] | +5,9 [+2,7; +9,5] | −5,5 [−9,5; −1,2] | −3,7 [−6,4; −0,5] |

Sau khi kiểm soát, hệ số đổi dấu sang chiều lý thuyết nhưng nhỏ, và **placebo cũng cho cùng dấu**, nên không thể coi đây là bằng chứng ủng hộ Wyckoff. Nếu có phần thật, nó chỉ khoảng 2 điểm % và nằm trong sai số.

### 3. Hiệu ứng tập trung sát lúc thoát

| Số phiên từ sự kiện đến thoát | 1–5 | 6–10 | 11–20 | 21–40 | 41–80 | > 80 |
|---|---|---|---|---|---|---|
| Spring: thoát lên (%) | 2,5 | 8,3 | 18,3 | 38,2 | 40,9 | 50,1 |
| UTAD: thoát lên (%) | 96,9 | 95,8 | 82,3 | 67,0 | 57,6 | 45,9 |

Sự kiện càng xa lúc thoát, tỷ lệ càng về gần nền. Bảng này điều kiện theo kết quả nên chỉ mang tính mô tả, nhưng khớp với cơ chế "vị trí".

### 4. Bối cảnh lý thuyết không tạo khác biệt về hướng thoát

| Nhóm | n | Thoát lên (%) |
|---|---|---|
| Spring sau Markdown / sau Markup | 1.337 / 1.578 | 26,6 / 27,7 |
| Spring volume thấp / shakeout | 1.976 / 967 | 27,6 / 26,4 |
| Spring xuyên ≤ 0,25 ATR / > 1 ATR | 465 / 771 | 29,2 / 26,7 |
| Spring đúng lý thuyết (sau Markdown, volume thấp, xuyên < 1 ATR, lần đầu) | 422 | 28,9 |
| Như trên, thêm có SC | 19 | 31,6 (mẫu quá nhỏ) |
| UTAD sau Markup / sau Markdown | 1.164 / 1.085 | 75,9 / 73,4 |

## Phát hiện kèm theo: thoát range rất nhiễu

**55,4% range quay lại biên cũ trong 30 phiên sau khi thoát** (placebo 58,9%), và tỷ lệ này như nhau ở mọi nhóm sự kiện. Nghĩa là "thoát range" theo định nghĩa hiện tại chỉ tốt hơn ngẫu nhiên một chút.
Việc này ảnh hưởng trực tiếp đến nhãn giai đoạn đã chốt (Re-accumulation, Initial Distribution...) vì các nhãn đó dựa vào hướng thoát.

Range trên dữ liệu thật cũng không khác nhiều so với placebo: độ dài trung vị 25 so với 21 phiên, chiều cao trung vị 4,73 so với 5,0 ATR, số range đã kết thúc 6.643 so với khoảng 7.100 đến 7.450. Bộ phát hiện range tìm thấy "range" gần như nhiều bằng nhau trên dữ liệu không có cấu trúc.

## Hệ quả

1. **Không dùng được quy tắc đảo dấu của H8a**: nó chỉ đo lại vị trí giá, dùng trực tiếp vị trí sẽ đơn giản và trung thực hơn.
2. **Giả thuyết về sau cần vượt qua placebo và vị trí giá**, vì hai đối chứng này loại được các kết quả cơ học mà tiêu chí so với nền không loại được.
3. **Pha C, pha D và nhãn đã chốt chỉ nên đọc là mô tả.** Tỷ lệ "pha D trước khi thoát" đã nêu trong Bước 3 cũng thuộc loại này.
4. **Bộ phát hiện range là điểm yếu nền tảng hơn so với từng sự kiện**, vì range xuất hiện gần như nhiều bằng nhau trên dữ liệu xáo trộn.

## Giới hạn

- **Kết luận về hướng thoát, không phải về lợi suất.** Lợi suất sau sự kiện (20 phiên: Spring −0,61, UTAD +1,07, nền trong range +0,29; 60 phiên: +0,27, +3,28, nền +1,66; từ `output/h8/investigate/`) chưa được kiểm tra bằng placebo tương ứng, có thể phản ánh đà giá. Bảng tham khảo của H7 (Trending Up / Down, nhãn đã chốt) cũng chưa qua kiểm tra này.
- **Không bác bỏ phương pháp Wyckoff**: đây là kết luận về cách định nghĩa định lượng trong dự án. Người đọc biểu đồ có thể dùng nhiều yếu tố mà các quy tắc này không nắm được.
- **Placebo kiểu hoán vị** phá cả đà giá và cụm biến động (khối 20 phiên giữ một phần); kết quả ba cách xáo gần như giống nhau, nhưng chưa thử mô hình giả lập khác.
- **Phân tích này được thiết kế sau khi đã thấy kết quả H8**, trên cùng dữ liệu, không hiệu chỉnh cho số phép đo.
- **Chất lượng dữ liệu**: cache có phiên close bằng 0 ở NHT (2), NTC, PVP, SCS, VCA (mỗi mã 1). Placebo loại các phiên này; pipeline thật vẫn chạy trên chúng, chưa đánh giá tác động.
