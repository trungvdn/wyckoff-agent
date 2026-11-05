# Định nghĩa các sự kiện Wyckoff

Tài liệu sống, bổ sung dần từng sự kiện. Định nghĩa các giai đoạn nằm ở `docs/stage-definitions.md`; trạng thái tiềm năng, xác nhận, bác bỏ của các sự kiện chưa định nghĩa lại nằm ở `docs/revision-rules.md`.

| Sự kiện | Tình trạng |
|---|---|
| SC (Selling Climax) | Định nghĩa 05/11/2026 |
| LPS (Last Point of Support) | Định nghĩa 05/11/2026 |
| Các sự kiện khác | Chưa định nghĩa lại, sẽ bổ sung |

---

## LPS (Last Point of Support)

### Định nghĩa

LPS là sự kiện giá điều chỉnh trở lại sau khi xuất hiện sức mạnh tăng giá (SOS), nhưng áp lực bán suy yếu rõ rệt và lực cầu vẫn duy trì khả năng kiểm soát thị trường. Đây thường là vùng hỗ trợ quan trọng trước khi giá tiếp tục bước vào Markup.

### Điều kiện nhận diện

- **Bối cảnh:** đã xuất hiện SOS hoặc có bằng chứng rõ ràng về sức mạnh cầu.
- **Vị trí giá:** giá điều chỉnh về vùng hỗ trợ, thường là vùng kháng cự cũ đã breakout hoặc vùng cầu gần nhất.
- **Volume:** khối lượng giảm so với các nhịp tăng trước đó và giảm dần trong quá trình điều chỉnh.
- **Spread:** biên độ nến giảm hẹp dần, thể hiện áp lực bán suy yếu.
- **Price action:** giá không phá vỡ cấu trúc hỗ trợ quan trọng, lực bán không thể đẩy giá xuống sâu.
- **Demand response:** xuất hiện phản ứng tăng giá, cho thấy cầu quay trở lại và hấp thụ lượng cung còn lại.

### Quá trình hình thành

1. Giá hình thành vùng Accumulation.
2. Xuất hiện SOS: giá tăng mạnh, vượt kháng cự.
3. Giá điều chỉnh trở lại vùng hỗ trợ.
4. Volume giảm, spread thu hẹp, áp lực bán suy yếu.
5. Giá phản ứng tăng trở lại, xác nhận LPS.
6. Markup tiếp diễn.

### Quy tắc

```
LPS_CANDIDATE:
    Prior SOS or confirmed demand strength
    + Pullback toward support
    + Declining volume
    + Narrowing spread
    + Support holds or break slightly

LPS_CONFIRMED:
    LPS_CANDIDATE
    + Demand response
    + Price reversal upward
    + No meaningful support breakdown
```

### Phân biệt với nhịp điều chỉnh thông thường

| Tiêu chí | LPS | Điều chỉnh thông thường |
|---|---|---|
| Bối cảnh | Sau SOS hoặc sức mạnh cầu đã được xác nhận | Có thể xuất hiện ở bất kỳ giai đoạn nào |
| Volume giảm | Thường có | Không nhất thiết |
| Spread thu hẹp | Thường có | Không nhất thiết |
| Hỗ trợ | Giữ được vùng hỗ trợ quan trọng | Có thể phá cấu trúc |
| Phản ứng tăng | Có dấu hiệu cầu quay trở lại | Chưa chắc có |

### Không nên gán LPS

- Chưa có SOS hoặc bằng chứng sức mạnh cầu trước đó.
- Giá điều chỉnh với volume tăng mạnh và spread giảm rộng.
- Giá phá vỡ hỗ trợ với lực bán lớn.
- Giá hồi phục yếu, không có dấu hiệu cầu quay trở lại.
- Chỉ dựa vào việc giá chạm đường hỗ trợ để gán LPS.

### Lưu ý

Không bắt buộc LPS phải xuất hiện sau một cú breakout hoàn chỉnh. Trong một số cấu trúc Accumulation, LPS có thể hình thành sau SOS nội bộ hoặc một nhịp thể hiện sức mạnh cầu rõ ràng.

Đối với cổ phiếu Việt Nam, nên đánh giá volume tương đối so với trung bình 20 phiên, đồng thời xét đến thanh khoản và các phiên tăng trần, giảm sàn để tránh nhận diện sai LPS.

### Cách đo trong hệ thống

Ngưỡng trong `RevisionConfig`, mã nguồn `wyckoff/revision.py`.

| Yếu tố | Cách đo |
|---|---|
| Sức mạnh cầu trước đó | SOS của range (hỗ trợ là resistance), hoặc SOS nội bộ: trong range, nến đạt tiêu chí SOS đóng cửa vượt đỉnh swing gần nhất nhưng chưa tới resistance (hỗ trợ là đỉnh swing đó) |
| Điều chỉnh về hỗ trợ | Điều chỉnh bắt đầu trong 20 phiên sau nền sức mạnh; close <= hỗ trợ + 1 ATR; đã giảm >= 0,5 ATR từ đỉnh |
| Volume giảm | Volume phiên ứng viên thấp hơn trung bình các phiên điều chỉnh trước đó; trung bình nhịp điều chỉnh thấp hơn trung bình nhịp tăng từ nền sức mạnh. Volume tính theo tỷ lệ TB20 |
| Spread thu hẹp | Biên độ phiên ứng viên nhỏ hơn trung bình các phiên điều chỉnh trước đó |
| Hỗ trợ giữ hoặc thủng nhẹ | Close không sâu quá 3% dưới hỗ trợ, không quá 4 close liên tiếp dưới hỗ trợ |
| Phản ứng của cầu | Trong 5 phiên: nến tăng, close vượt đỉnh phiên ứng viên, close_pos >= 0,7, volume cao hơn phiên ứng viên |

Phiên ứng viên được dời xuống phiên đủ điều kiện có close thấp hơn, nên LPS là điểm cung yếu nhất ở vùng hỗ trợ.

**Bác bỏ ứng viên:** phá giới hạn hỗ trợ; có phiên giảm volume >= 2 lần TB20 và biên độ >= 1,5 ATR; có phiên khóa sàn; hết 5 phiên không có phản ứng; vượt đỉnh mà không có dấu hiệu cầu.

**Bác bỏ sau xác nhận:** trong 60 phiên, phá giới hạn hỗ trợ như trên.

**Đặc thù Việt Nam:**
- Phiên khóa sàn volume thấp không được xem là cung yếu, nên ứng viên bị bác bỏ.
- Phiên khóa trần volume thấp vẫn tính là cầu quay lại, vì không có người bán.
- Thanh khoản: giá trị giao dịch TB20 dưới 1 tỷ đồng thì không nhận diện ứng viên.

### Số đo khám phá

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định. "Thủng hỗ trợ" là close sâu quá 3% dưới hỗ trợ trong 60 phiên sau xác nhận.

| Nhóm | n, thật / placebo | Bị bác bỏ, thật / placebo (%) | Thủng hỗ trợ, thật / placebo (%) | Lợi suất 60 phiên, thật / placebo (%) |
|---|---|---|---|---|
| LPS theo quy tắc cũ | 2.914 / 2.167 | Không so sánh được | 48,4 / 52,6 | +4,8 / +3,3 |
| LPS mới sau SOS | 509 / 290 | 61,3 / 66,6 | 57,3 / 64,1 | +2,8 / +0,2 |
| LPS mới sau SOS nội bộ | 308 / 196 | 67,9 / 63,8 | 65,6 / 62,2 | −0,3 / +1,4 |

Định nghĩa này chọn lọc mạnh hơn nhiều: số LPS sau SOS chỉ còn khoảng 1/6, và tỷ lệ thật so với placebo tăng từ 1,34 lên 1,76 lần. Lợi suất và tỷ lệ thủng hỗ trợ không tốt hơn quy tắc cũ, một phần vì LPS mới luôn nằm sát hỗ trợ. LPS sau SOS nội bộ không vượt placebo.

### Phạm vi

Áp dụng cho dashboard và nhãn Accumulation qua lớp đánh giá lại; với Accumulation, LPS chỉ là một bằng chứng, không bắt buộc. Nhật ký, điểm tin cậy và backtest vẫn dùng quy tắc LPS cũ (`detect_lps`); dashboard chỉ hiện LPS theo định nghĩa mới.

### Giới hạn

- Các ngưỡng trên là diễn giải định lượng do Claude đề xuất, trừ 3% và 4 phiên do người dùng đặt; cần được rà soát cùng người dùng.
- Mức "volume cao hơn phiên ứng viên" nhẹ hơn nhiều so với ngưỡng 1,5 lần TB20 trước đây, vì sau một nhịp volume cạn, nhịp đảo chiều thường có volume dưới trung bình.

---

## SC (Selling Climax)

### Định nghĩa

SC là sự kiện xuất hiện ở cuối một xu hướng giảm (Markdown), khi áp lực bán đạt mức cực đoan, khiến giá giảm mạnh nhưng gặp lực cầu hấp thụ lớn, tạo tiền đề cho quá trình hình thành vùng tích lũy (Accumulation).

### Yếu tố nhận diện

SC được đánh giá đồng thời 5 yếu tố:

1. Xuất hiện sau một giai đoạn Markdown hoặc xu hướng giảm kéo dài.
2. Biên độ giảm lớn bất thường so với các phiên trước (Wide Spread Down).
3. Khối lượng giao dịch tăng đột biến, thể hiện hoạt động bán tháo mạnh.
4. Giá có thể tạo bóng nến dưới dài, đóng cửa cách xa mức thấp nhất phiên, cho thấy lực cầu hấp thụ cung.
5. Sau SC, giá không tiếp tục giảm dễ dàng; áp lực bán bắt đầu suy yếu.

### Hai thời điểm

```
SC Candidate:
    Prior Markdown
    + Abnormally Wide Spread Down
    + Climactic Volume
    + Evidence of Absorption

SC Confirmed:
    SC Candidate
    + Subsequent Selling Pressure Weakens
    + Price Stabilization or Automatic Rally
```

- **SC Candidate:** phiên giảm mạnh, volume đột biến, xuất hiện dấu hiệu hấp thụ cung. Đây mới là ứng viên SC.
- **SC Confirmed:** các phiên tiếp theo cho thấy giá không thể tiếp tục giảm đáng kể. Giá có thể giảm thêm một ít trong vài phiên, nhưng sau đó hồi lại, xuất hiện phản ứng tăng mạnh hoặc hình thành Automatic Rally (AR).

**Lưu ý:** SC không bắt buộc phải có bóng nến dưới dài hoặc đóng cửa ở nửa trên cây nến. SC có thể đóng cửa gần Low nếu lực bán vẫn mạnh, nhưng khi đó cần chờ phản ứng của các phiên tiếp theo để xác nhận.

### Không nên gán SC

- Giá giảm mạnh nhưng volume thấp hoặc bình thường.
- Giá giảm mạnh, volume cao nhưng đóng cửa gần Low và tiếp tục giảm mạnh ở các phiên sau.
- Chỉ có một phiên giảm mạnh nhưng không có bối cảnh Markdown trước đó.
- Giá giảm mạnh do tin tức hoặc sự kiện bất thường nhưng chưa có bằng chứng hấp thụ cung.

### Nguyên tắc

Không dùng điều kiện cứng để tự động kết luận SC. Một phiên đạt các ngưỡng mới chỉ là ứng viên; kết luận phụ thuộc vào phản ứng của giá ở các phiên sau.

### Cách đo trong hệ thống

Ngưỡng ứng viên dùng `SellingClimaxConfig`, ngưỡng xác nhận dùng `RevisionConfig`. Mã nguồn: `wyckoff/revision.py`.

| Yếu tố | Cách đo |
|---|---|
| Bối cảnh giảm | Close thấp hơn close cao nhất 60 phiên từ 15%, low là thấp nhất 60 phiên, close dưới SMA50, và đang ở Markdown theo nhật ký hoặc SMA50 giảm so với 20 phiên trước |
| Biên độ giảm lớn | True Range > 1,5 ATR và close thấp hơn phiên trước. Dạng riêng cho Việt Nam: từ 3 phiên giảm sàn trong 10 phiên trước, rồi phiên rút chân có close_pos >= 0,5, vì biên độ bị sàn chặn |
| Volume đột biến | Volume > 2 lần TB20 |
| Hấp thụ cung | close_pos >= 0,5 hoặc bóng dưới >= 1/3 biên độ phiên. **Không bắt buộc**: không có thì ghi "chờ phản ứng" |
| Xác nhận, một trong ba | Close >= đáy vùng + 2 ATR trong 10 phiên; hoặc có AR (đỉnh pivot >= đáy SC + 3 ATR trong 30 phiên); hoặc giá ổn định: tối thiểu 5 phiên trong 10 phiên đầu, không close dưới đáy ứng viên, volume trung bình <= 0,5 lần volume ứng viên. Riêng ổn định chỉ áp dụng khi có hấp thụ ngay trong phiên |
| Được phép giảm thêm | Close không thấp hơn đáy ứng viên quá 1 ATR |
| Bác bỏ | Trước xác nhận: close thủng ngưỡng trên, hoặc hết 30 phiên không có phản ứng. Sau xác nhận: close thủng ngưỡng trên trước khi giá hồi được đáy vùng + 3 ATR, trong 30 phiên |

Ứng viên xuất hiện trong 10 phiên sau một ứng viên khác mà chưa thủng ngưỡng thì được gộp vào ứng viên trước.

PS, AR, ST của một SC bị bác bỏ cũng bị bác bỏ theo. Trên biểu đồ hồi cứu, pha A bắt đầu từ phiên SC đã xác nhận còn hiệu lực; đoạn A mở bởi SC không còn hiệu lực thì được bỏ.

### Số đo khám phá

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định. "Mất đáy" là close dưới đáy SC trong 60 phiên sau xác nhận.

| Nhóm | n, thật / placebo | Mất đáy, thật / placebo (%) | Lợi suất 60 phiên, thật / placebo (%) |
|---|---|---|---|
| SC theo quy tắc cũ | 1.410 / 1.532 | 59,6 / 67,7 | +6,8 / +2,9 |
| SC xác nhận theo định nghĩa này | 1.069 / 1.309 | 45,8 / 56,7 | +6,2 / +3,0 |
| Xác nhận bằng phản ứng tăng mạnh | 872 / 1.053 | 42,3 / 54,3 | +7,0 / +3,2 |
| Xác nhận bằng AR | 48 / 92 | 35,4 / 52,2 | +4,8 / −1,3 |
| Xác nhận bằng giá ổn định | 149 / 164 | 69,8 / 74,4 | +2,0 / +4,0 |

Khoảng 55% ứng viên được xác nhận, trên cả dữ liệu thật và placebo. 60,5% SC xác nhận trùng phiên với SC cũ; 39,5% còn lại là SC cũ không nhận ra. Đường xác nhận bằng giá ổn định yếu nhất và không vượt placebo về lợi suất.

### Phạm vi

Định nghĩa này áp dụng cho dashboard qua lớp đánh giá lại. Nhật ký tại từng thời điểm, điểm tin cậy và backtest vẫn dùng quy tắc SC cũ (`detect_selling_climax`), nên điểm tin cậy "Có SC" có thể khác với nhãn trên biểu đồ.

### Giới hạn

- Hệ thống không có dữ liệu tin tức, nên chỉ nhận ra trường hợp tin tức gián tiếp qua việc thiếu phản ứng của giá.
- Các ngưỡng xác nhận (1 ATR, 2 ATR, 10 phiên, 0,5 lần volume) là diễn giải định lượng do Claude đề xuất cho các cụm "giảm thêm một ít", "phản ứng tăng mạnh", "ổn định"; cần được rà soát cùng người dùng.
