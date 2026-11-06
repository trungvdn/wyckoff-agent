# Định nghĩa các sự kiện Wyckoff

Tài liệu sống, bổ sung dần từng sự kiện. Định nghĩa các giai đoạn nằm ở `docs/stage-definitions.md`; trạng thái tiềm năng, xác nhận, bác bỏ của các sự kiện chưa định nghĩa lại nằm ở `docs/revision-rules.md`.

| Sự kiện | Tình trạng |
|---|---|
| SC (Selling Climax) | Định nghĩa 05/11/2026 |
| LPS (Last Point of Support) | Định nghĩa 05/11/2026 |
| AR (Automatic Rally / Automatic Reaction) | Định nghĩa 06/11/2026 |
| ST (Secondary Test) | Định nghĩa 06/11/2026 |
| Spring | Định nghĩa 06/11/2026 |
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

## Spring

### Định nghĩa

Spring là sự kiện giá xuyên thủng xuống dưới vùng hỗ trợ của Trading Range, thường xuất hiện trong Accumulation hoặc Re-accumulation, sau đó nhanh chóng quay trở lại bên trong TR. Bản chất của Spring là một false breakdown:

- Giá xuyên thủng vùng hỗ trợ, kích hoạt lệnh stop-loss và lệnh bán theo xu hướng.
- Lượng cung được hấp thụ bởi lực cầu.
- Giá không thể duy trì dưới vùng hỗ trợ và nhanh chóng quay trở lại TR.
- Nếu được xác nhận, Spring cho thấy nguồn cung tại vùng giá thấp có thể đã suy yếu đáng kể.

Spring có thể là dấu hiệu quá trình tích lũy đang tiến triển, nhưng không tự động xác nhận cổ phiếu đã sẵn sàng bước vào Markup.

**Kết luận:** bằng chứng quan trọng nhất không phải là việc giá xuyên thủng đáy, mà là khả năng lấy lại hỗ trợ và phản ứng của cung cầu sau đó.

### Điều kiện nhận diện

**A. Bối cảnh**

| Điều kiện | Mô tả |
|---|---|
| Có Trading Range | Giá đã hình thành vùng hỗ trợ và kháng cự tương đối rõ |
| Có hỗ trợ trước đó | Có một vùng đáy được kiểm tra hoặc có ý nghĩa cấu trúc |
| Bối cảnh phù hợp | Thường nằm trong Accumulation hoặc Re-accumulation |
| Có thể có ST trước đó | Thường sau một hoặc nhiều lần kiểm tra hỗ trợ, không bắt buộc |

Không phát hiện Spring chỉ dựa trên việc giá tạo đáy thấp hơn đáy trước đó. Phải xác định được Trading Range và vùng hỗ trợ tham chiếu.

**B. Hành động giá**

1. Giá xuyên thủng vùng hỗ trợ TR.
2. Mức thấp nhất của phiên hoặc một số phiên nằm dưới vùng hỗ trợ.
3. Giá nhanh chóng quay trở lại bên trong TR.
4. Giá đóng cửa có thể nằm trên vùng hỗ trợ, thể hiện sự từ chối mức giá thấp.

Không bắt buộc phải có bóng nến dưới dài. Spring vẫn có thể có thân nến tương đối lớn nếu giá giảm mạnh rồi được hấp thụ và hồi phục.

**C. Volume và biên độ**

| Yếu tố | Dấu hiệu tích cực |
|---|---|
| Volume | Thường thấp hơn các phiên bán tháo trước đó, hoặc không tăng tương xứng với mức phá đáy |
| Biên độ | Có thể rộng trong phiên xuyên thủng, nhưng cần quan sát phản ứng hồi phục |
| Giá đóng cửa | Gần vùng cao của nến, hoặc quay lại trên hỗ trợ |
| Volume tương đối | So sánh với TB20 và các phiên kiểm tra hỗ trợ trước đó |

Không đặt điều kiện volume bắt buộc phải thấp. Spring có volume cao vẫn có thể hợp lệ nếu lực cầu hấp thụ mạnh và giá nhanh chóng lấy lại vùng hỗ trợ.

**D. Xác nhận**

- Giá không tiếp tục giảm và đóng cửa dưới vùng hỗ trợ.
- Xuất hiện phản ứng tăng giá.
- Khi giá kiểm tra lại vùng đáy Spring, volume thường thấp hơn và biên độ thu hẹp.
- Giá giữ được vùng hỗ trợ và xuất hiện dấu hiệu cầu quay trở lại.

Spring có thể được xác nhận bằng phản ứng hồi phục mạnh, hoặc thông qua một lần kiểm tra thành công (Spring Test).

### Ba trạng thái

| Trạng thái | Điều kiện |
|---|---|
| `SPRING_CANDIDATE` | Giá xuyên thủng vùng hỗ trợ TR và có dấu hiệu từ chối giá thấp |
| `SPRING_CONFIRMED` | Giá quay lại TR, không duy trì được breakdown và có phản ứng cầu đủ thuyết phục |
| `SPRING_FAILED` | Giá tiếp tục giao dịch dưới hỗ trợ, không thể lấy lại TR, hoặc xuất hiện áp lực bán tiếp diễn |

Spring Confirmed không đồng nghĩa với Accumulation Confirmed hay Markup Confirmed. Không gán Spring ngay tại phiên đầu tiên xuyên thủng.

### Phân biệt Spring, ST và Breakdown

| Tiêu chí | ST | Spring | Breakdown |
|---|---|---|---|
| Xuyên hỗ trợ | Không bắt buộc | Có | Có |
| Quay lại TR | Thường vẫn ở trong TR | Có | Không hoặc thất bại |
| Mục đích | Kiểm tra cung | Kiểm tra cung và hấp thụ | Phá vỡ cấu trúc |
| Ý nghĩa | Thành công nếu cung suy yếu | Có khả năng rũ bỏ nguồn cung | Có thể bắt đầu Markdown |

### Không nên gán Spring

- Giá phá hỗ trợ với volume lớn, biên độ rộng và đóng cửa gần đáy.
- Giá tiếp tục tạo LL trong các phiên sau.
- Giá hồi phục nhưng không thể lấy lại vùng hỗ trợ.
- Giá chỉ xuyên hỗ trợ một khoảng rất nhỏ do nhiễu, không có bằng chứng hấp thụ.
- Không có Trading Range đủ rõ để xác định vùng hỗ trợ tham chiếu.

Không gán Spring cho mọi phiên có low thấp hơn đáy TR nhưng close vẫn trên hỗ trợ. Cần đánh giá cả hành vi sau sự kiện.

### Nguyên tắc

- Hỗ trợ phải được xác định từ cấu trúc TR, không chỉ từ một mức low đơn lẻ.
- Dùng vùng giá hỗ trợ thay vì một mức giá chính xác, đặc biệt với cổ phiếu Việt Nam.
- Cho phép Spring xuyên thủng hơn một phiên, nhưng phải đánh giá tốc độ lấy lại vùng hỗ trợ.
- Tách thời điểm phát hiện Candidate và thời điểm Confirmed.
- Không bắt buộc phải có Spring trong mọi Accumulation.

**Spring và Shakeout:** Spring mô tả hành động xuyên thủng hỗ trợ TR rồi quay trở lại. Shakeout là hành động rũ bỏ mạnh hơn, đôi khi trong một cấu trúc tăng hoặc tái tích lũy, không nhất thiết có hình thái Spring cổ điển. Hệ thống lưu Spring như một sự kiện cụ thể; Shakeout có thể là nhãn hành vi rộng hơn nếu sau này cần mở rộng.

### Cách đo trong hệ thống

Ngưỡng trong `SpringConfig` và `RevisionConfig`. Mã nguồn: `_springs` trong `wyckoff/revision.py`. Thay cho Spring kéo dài và Spring hồi phục nhanh là hai quy tắc riêng trước đây.

| Yếu tố | Cách đo |
|---|---|
| Bối cảnh | Range đã xác nhận tối thiểu 5 phiên và còn hoạt động; hoặc đã thoát xuống mà Markdown đang bị bác bỏ, còn trong thời hạn đánh giá |
| Xuyên hỗ trợ | Low dưới support hơn max(0,1 ATR, 1 tick), phiên trước chưa xuyên. Mức này loại nhiễu |
| Candidate | Trong cú xuyên, có phiên close_pos >= 0,5 hoặc close từ support trở lên. Chưa có dấu hiệu này thì là breakdown thông thường, không ghi sự kiện |
| Lấy lại hỗ trợ | Close từ support + 1 tick, trong 15 phiên tính cả phiên xuyên |
| Phiên đặt Spring | Xuyên nhiều phiên: phiên xa range nhất, tức phiên có high thấp nhất trong các phiên xuyên, đến phiên lấy lại hỗ trợ. Phiên xuyên đầu tiên lưu ở `penetration_date`, đáy thấp nhất của cú xuyên lưu ở `lowest_low` |
| Confirmed, một trong ba | Sau khi lấy lại: phiên demand (nến tăng, volume >= 1,5 lần TB20, close_pos >= 0,7); hoặc close cách đáy tối thiểu 2 ATR (ATR tại phiên xuyên); hoặc Test: low về sát support (trong 0,1 ATR), giữ đáy, close trong range, volume dưới 0,6 lần và biên độ hẹp hơn phiên xuyên lớn nhất |
| Failed | Không lấy lại hỗ trợ trong 15 phiên; đáy mới sau khi đã quay lại; 15 phiên sau khi quay lại không có phản ứng; hết thời hạn của range; Markdown xác nhận; có SC mới; có range mới |
| Bác bỏ sau xác nhận | Trong 60 phiên, close dưới đáy − 0,5 ATR; hoặc có SC xác nhận tạo sau cú xuyên |
| Gộp | Cú xuyên mới cách cú trước dưới 10 phiên: đáy không thấp hơn thì gộp vào cú trước; đáy thấp hơn thì thay cú trước |
| Spring Test | Lần kiểm tra đầu tiên theo tiêu chí trên, trong 15 phiên sau khi lấy lại. Spring bị bác bỏ thì Test bị bác bỏ theo |

**Nhãn:** hồi phục nhanh khi lấy lại hỗ trợ trong 4 phiên, kéo dài khi lâu hơn. `volume_profile` ghi thấp hoặc cao theo mức 1 lần TB20. Hai nhãn này chỉ để mô tả, không quyết định trạng thái.

### Số đo khám phá

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định. Đã bỏ các ca gộp. Các cột cuối đo trong 60 phiên sau xác nhận. "Về sau bị bác bỏ" là tỷ lệ cuối cùng bị bác bỏ trong số đã xác nhận.

| Nhóm, thật / placebo | n | Về sau bị bác bỏ (%) | Close trên resistance (%) | Mất đáy Spring (%) | Lợi suất (%) |
|---|---|---|---|---|---|
| Mọi Spring xác nhận | 5.200 / 5.641 | 57,7 / 59,5 | 41,5 / 53,9 | 60,9 / 62,7 | +1,6 / +2,7 |
| Xác nhận bằng phản ứng tăng | 2.298 / 2.757 | 50,5 / 53,7 | 44,1 / 57,8 | 53,7 / 57,5 | +1,5 / +2,9 |
| Xác nhận bằng phiên demand | 1.747 / 2.062 | 57,6 / 60,3 | 44,2 / 53,6 | 60,7 / 63,3 | +1,8 / +2,2 |
| Xác nhận bằng Test | 1.155 / 822 | 72,2 / 77,0 | 31,9 / 42,1 | 75,8 / 78,3 | +1,5 / +3,0 |
| Hồi phục nhanh | 4.251 / 4.318 | 59,5 / 62,7 | 41,5 / 54,6 | 62,8 / 65,4 | +1,6 / +2,5 |
| Kéo dài | 949 / 1.323 | 49,7 / 49,1 | 41,2 / 51,7 | 52,5 / 53,7 | +1,6 / +3,3 |
| Volume cao | 3.475 / 3.628 | 57,5 / 58,9 | 41,6 / 53,1 | 60,3 / 62,0 | +1,7 / +3,0 |
| Volume thấp | 1.725 / 2.013 | 58,1 / 60,6 | 41,2 / 55,5 | 62,3 / 63,7 | +1,5 / +2,2 |

- **Spring xác nhận chưa cho thấy lợi thế:** lợi suất thấp hơn placebo, giá thật vượt resistance ít hơn placebo, và khoảng 60% ca mất đáy Spring trong 60 phiên.
- Spring khá phổ biến: 9.590 ứng viên trên 7.765 range (placebo 10.233 trên 8.413), 54,2% được xác nhận (placebo 55,1%). Hơn một nửa số đã xác nhận về sau bị bác bỏ.
- Volume thấp không tốt hơn volume cao, đúng với việc không đặt volume thấp làm điều kiện.
- Lý do Failed phổ biến nhất khi chưa xác nhận: đáy mới sau khi quay lại (2.480 / 2.500), không lấy lại hỗ trợ trong 15 phiên (1.310 / 1.485).
- So mức thời hạn lấy lại hỗ trợ: 5, 10, 15, 30 phiên xác nhận 47,1%, 51,6%, 54,2%, 57,5% (placebo 45,9%, 51,9%, 55,1%, 58,7%), lợi suất khoảng +1,6%. Không khác biệt, nên 15 phiên được chọn theo mô tả "nhanh chóng", không phải vì kết quả tốt hơn.
- 74,1% Spring của nhật ký trùng phiên với Spring mới (placebo 77,6%). Con số này giảm vì Spring mới đặt tại phiên có high thấp nhất, nên không đo được độ khớp của hai định nghĩa.

### Phạm vi

Định nghĩa này áp dụng cho dashboard qua lớp đánh giá lại. Nhật ký, điểm tin cậy, backtest và cảnh báo Spring xuyên sâu vẫn dùng `detect_spring`. Mốc pha C trên biểu đồ hồi cứu bắt đầu từ phiên đặt Spring.

### Giới hạn

- Các ngưỡng từ chối giá thấp, 15 phiên, 2 ATR là diễn giải định lượng do Claude đề xuất; cần được rà soát cùng người dùng.
- Bối cảnh "thường trong Accumulation hoặc Re-accumulation" chưa dùng để lọc, vì mức Accumulation dùng chính Spring làm bằng chứng. Spring trong range nghiêng về Distribution vẫn được ghi.
- Hỗ trợ là một mức theo range với dung sai xuyên thủng và tick, chưa phải một vùng giá đầy đủ.
- Chưa có nhãn Shakeout riêng.

---

## ST (Secondary Test)

### Định nghĩa

ST là sự kiện giá quay trở lại kiểm tra vùng giá đã xuất hiện cao trào trước đó (SC hoặc BC), nhằm đánh giá lượng cung hoặc cầu còn tồn tại trên thị trường. Trong Accumulation, ST kiểm tra lại vùng đáy SC để đánh giá nguồn cung còn lại. Trong Distribution, ST kiểm tra lại vùng đỉnh BC để đánh giá lực cầu còn lại.

**Nguyên tắc cốt lõi:** ST không đơn giản là giá quay lại vùng SC hoặc BC. ST phải thể hiện một lần kiểm tra cung cầu, trong đó áp lực giao dịch theo hướng trước đó suy yếu tương đối so với sự kiện cao trào.

### Điều kiện nhận diện

| Tiêu chí | Accumulation | Distribution |
|---|---|---|
| Bối cảnh | Đã có SC và AR | Đã có BC và AR |
| Vị trí giá | Quay lại vùng đáy SC hoặc hỗ trợ gần SC | Quay lại vùng đỉnh BC hoặc kháng cự gần BC |
| Volume | Thường thấp hơn đáng kể so với SC | Thường thấp hơn đáng kể so với BC |
| Biên độ | Biên độ giảm thường hẹp hơn SC | Biên độ tăng thường hẹp hơn BC |
| Áp lực | Không tạo được áp lực bán mạnh như SC | Không tạo được lực cầu mạnh như BC |
| Phản ứng giá | Giữ hỗ trợ, hoặc chỉ xuyên nhẹ rồi phục hồi | Không duy trì trên kháng cự, bắt đầu suy yếu |
| Ý nghĩa | Nguồn cung suy yếu, cổ phiếu bán ra có thể đã được hấp thụ đáng kể | Lực cầu mua đuổi suy yếu, nguồn cung có thể đang kiểm soát vùng giá cao |

### Phân biệt với các sự kiện khác

| Sự kiện | Đặc điểm |
|---|---|
| SC | Cao trào bán, tạo vùng đáy quan trọng |
| AR | Phản ứng tăng mạnh sau SC |
| ST | Kiểm tra lại vùng SC với áp lực bán thường suy yếu |
| Spring | Giá xuyên thủng hỗ trợ TR rồi nhanh chóng quay trở lại |
| UTAD | Giá vượt kháng cự TR rồi nhanh chóng quay trở lại |

ST không nhất thiết phải xuyên thủng vùng SC. Spring là một dạng kiểm tra hỗ trợ đặc biệt có hành vi phá vỡ giả.

### ST có bắt buộc không

Không bắt buộc. Có thể có một hoặc nhiều ST, hoặc không có ST rõ ràng. ST có thể kiểm tra vùng SC, BC trong nhiều phiên. Một ST không thành công không đồng nghĩa cấu trúc Accumulation hoặc Distribution bị vô hiệu ngay.

### Hai trạng thái

- **ST Candidate:** đã có SC + AR hoặc BC + AR; giá quay lại vùng cực trị trước đó; có dấu hiệu suy yếu tương đối của volume hoặc biên độ.
- **ST Confirmed:** giá hoàn thành quá trình kiểm tra vùng SC, BC; không xuất hiện áp lực mạnh tương đương cao trào; có phản ứng giá cho thấy vùng hỗ trợ, kháng cự đang được bảo vệ.

```
ACCUMULATION_ST:
    Prior SC + AR
    + Retest SC support zone
    + Lower relative selling volume
    + Narrower downward spread
    + Support holds or quickly recovers

DISTRIBUTION_ST:
    Prior BC + AR
    + Retest BC resistance zone
    + Lower relative buying volume
    + Narrower upward spread
    + Resistance holds or price weakens
```

### Lưu ý cho chứng khoán Việt Nam

- So sánh volume với SC, BC và trung bình 20 phiên, không chỉ dùng volume tuyệt đối.
- Điều chỉnh đánh giá với phiên giảm sàn hoặc tăng trần.
- Không yêu cầu ST nằm chính xác tại low của SC hoặc high của BC.
- Dùng vùng giá thay vì một mức giá cố định.
- Phân biệt ST với Spring, UTAD bằng hành vi giá sau khi xuyên thủng vùng hỗ trợ, kháng cự.

### Cách đo trong hệ thống

Ngưỡng vùng, volume, biên độ trong `STConfig` và `DistributionConfig`; ngưỡng phản ứng trong `RevisionConfig`. Mã nguồn: `_st_tests`, `_st_events` trong `wyckoff/revision.py`. Phía BC dùng cùng thuật toán trên giá đổi dấu. Dưới đây mô tả phía SC.

| Yếu tố | Cách đo |
|---|---|
| Bối cảnh | Sau khi AR đã xác nhận, trong 60 phiên kể từ đỉnh AR |
| Vùng kiểm tra | Low trong khoảng đáy SC − 0,5 ATR đến đáy SC + 1 ATR (phía BC: đỉnh BC − 1 ATR đến đỉnh BC + 0,5 ATR) |
| Volume yếu hơn | Volume dưới 0,7 lần volume SC, và dưới 2 lần TB20 |
| Biên độ yếu hơn | Biên độ phiên hẹp hơn phiên SC |
| Ứng viên | Close giảm so với phiên trước, trong vùng, volume hoặc biên độ yếu hơn, không khóa sàn |
| Áp lực tương đương cao trào | Phiên giảm mà cả volume lẫn biên độ đều không yếu hơn, hoặc phiên khóa sàn (khóa trần với BC) |
| Xác nhận | Trong 10 phiên, close phản ứng tối thiểu 1 ATR khỏi điểm thấp nhất của lần kiểm tra, không có áp lực tương đương cao trào |
| Bác bỏ lần ST | Low xuyên sâu hơn đáy vùng; có áp lực tương đương cao trào; hoặc hết 10 phiên không phản ứng |
| Cao trào bị bác bỏ | ST đã xác nhận bị bác bỏ theo |
| Nhiều ST | Các lần kiểm tra bắt đầu cách nhau tối thiểu 10 phiên |

Sự kiện đặt tại phiên có điểm kiểm tra sâu nhất. Xuyên sâu hơn vùng thì không phải ST; hành vi đó được xét theo Spring, UTAD. ST gắn với range đã xác nhận tại lúc biết sự kiện. ST thất bại không làm đổi nhãn Accumulation, Distribution.

### Số đo khám phá

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định. Lợi suất và "mất đáy, đỉnh" đo trong 60 phiên sau xác nhận.

| Loại | n ứng viên, thật / placebo | Từng xác nhận, thật / placebo (%) | Mất đáy SC / đỉnh BC, thật / placebo (%) | Lợi suất, thật / placebo (%) |
|---|---|---|---|---|
| ST | 855 / 1.441 | 55,8 / 55,3 | 60,0 / 64,2 | +1,5 / +4,5 |
| ST(d) | 897 / 848 | 52,7 / 48,7 | 67,8 / 69,0 | +6,6 / +2,5 |

Ở cả hai bên, volume lớn nhất của lần kiểm tra có trung vị khoảng 0,5 đến 0,6 lần cao trào, biên độ khoảng 0,75 đến 0,85 lần, kéo dài trung vị 3 phiên. Lý do bác bỏ phổ biến nhất là xuyên sâu (322 trong 376 ca ST bị bác bỏ, chưa từng xác nhận; placebo 604 trong 644).

So sánh các SC có AR, đo sau 60 phiên kể từ AR xác nhận:

| | n, thật / placebo | Mất đáy SC trong 60 phiên tiếp, thật / placebo (%) | Lợi suất 60 phiên tiếp, thật / placebo (%) |
|---|---|---|---|
| Đã có ST xác nhận | 291 / 531 | 57,0 / 59,5 | +0,9 / +4,7 |
| Chưa có ST | 591 / 651 | 30,1 / 46,2 | +6,2 / +2,2 |

- ST đã xác nhận **không cho thấy giá mạnh hơn**: sau ST, giá thật có lợi suất thấp hơn placebo, và tỷ lệ mất đáy gần bằng placebo.
- Nhóm chưa có ST tốt hơn rõ, nhưng một phần là cơ học: giá chưa quay lại vùng SC thì còn cách đáy SC xa hơn. Đây không phải bằng chứng rằng ST có hại.
- Sau ST(d), lợi suất dương và cao hơn placebo, nên ST(d) không cho thấy giá giảm tiếp.
- Chỉ 6,4% ST của nhật ký trùng phiên với ST mới (ST(d) 11,0%), vì sự kiện mới đặt ở điểm kiểm tra sâu nhất nên con số này không đo được độ khớp của hai định nghĩa.

### Phạm vi

Định nghĩa này áp dụng cho dashboard qua lớp đánh giá lại. Nhật ký, điểm tin cậy và backtest vẫn dùng ST, ST(d) theo quy tắc cũ. Mốc pha B trên biểu đồ hồi cứu dùng ST mới.

### Giới hạn

- Các ngưỡng phản ứng 1 ATR và 10 phiên, cùng mức 2 lần TB20, là diễn giải định lượng do Claude đề xuất; ngưỡng vùng, volume, biên độ giữ từ quy tắc cũ. Cần được rà soát cùng người dùng.
- Chỉ xét sau khi AR đã xác nhận, đúng theo định nghĩa, nên SC, BC không có AR thì không có ST.
- ST xảy ra sau khi range đã thoát chưa được tính vào điều kiện "Hấp thụ cung" của range đó, vì chưa gắn với range; vẫn hiện trên biểu đồ và danh sách sự kiện.
- BC vẫn theo định nghĩa cũ.

---

## AR (Automatic Rally / Automatic Reaction)

### Định nghĩa

AR là sự kiện giá phục hồi mạnh sau Selling Climax (SC) trong Accumulation, hoặc giảm mạnh sau Buying Climax (BC) trong Distribution. Đây là phản ứng tự nhiên của thị trường khi áp lực mua, bán mất cân bằng sau một sự kiện cao trào.

- **Accumulation AR:** giá tăng mạnh sau SC do lực cầu hấp thụ lượng cung bán tháo và áp lực bán suy giảm.
- **Distribution AR:** giá giảm mạnh sau BC do nguồn cung gia tăng và lực cầu mua đuổi suy yếu.

**Nguyên tắc:** SC, BC thể hiện điểm cao trào của áp lực giao dịch; AR thể hiện phản ứng ngược chiều sau cao trào. Hai sự kiện kết hợp giúp xác định biên độ Trading Range ban đầu, nhưng chưa đủ để kết luận thị trường đã hoàn tất Accumulation hoặc Distribution.

### Điều kiện nhận diện

| Tiêu chí | Accumulation AR | Distribution AR |
|---|---|---|
| Bối cảnh | Sau SC hoặc vùng bán tháo cực độ | Sau BC hoặc vùng mua cao trào |
| Biến động giá | Tăng mạnh, biên độ tăng lớn | Giảm mạnh, biên độ rộng |
| Volume | Thường cao hoặc cải thiện, không bắt buộc đột biến | Thường cao hoặc cải thiện do nguồn cung xuất hiện |
| Cung cầu | Lực cầu đủ mạnh để đẩy giá rời vùng đáy SC | Áp lực bán đủ lớn để đẩy giá rời vùng đỉnh BC |
| Tác động cấu trúc | Đỉnh hồi phục đầu tiên, xác định kháng cự ban đầu | Đáy phản ứng đầu tiên, xác định hỗ trợ ban đầu |

### Vai trò trong Trading Range

| | Accumulation | Distribution |
|---|---|---|
| Sự kiện cao trào | SC xác định hỗ trợ ban đầu | BC xác định kháng cự ban đầu |
| AR | Xác định kháng cự ban đầu | Xác định hỗ trợ ban đầu |
| ST | Kiểm tra lại hỗ trợ SC | Kiểm tra lại kháng cự BC |

### Hai trạng thái

- **AR Candidate:** xuất hiện sau SC, BC; giá phản ứng mạnh theo hướng ngược lại; biên độ lớn hơn bình thường.
- **AR Confirmed:** giá hoàn thành một nhịp phản ứng rõ ràng; tạo được swing high (Accumulation) hoặc swing low (Distribution); xác định được kháng cự, hỗ trợ ban đầu.

Không cần chờ ST mới xác nhận AR. ST là sự kiện kiểm tra tiếp theo, không phải điều kiện của AR.

### Không nên gán AR

- Giá chỉ hồi phục nhẹ sau SC, không có thay đổi đáng kể về biên độ.
- Giá tăng nhưng không có bối cảnh bán tháo hoặc SC trước đó.
- Giá giảm thông thường trong Markup nhưng không có BC trước đó.
- Nhầm một nhịp hồi kỹ thuật với Automatic Rally.

### Quy tắc

```
ACCUMULATION_AR_CANDIDATE:
    Prior SC or Selling Climax context
    + Strong upward price reaction
    + Wide upward spread
    + Meaningful displacement from SC low

ACCUMULATION_AR_CONFIRMED:
    AR_CANDIDATE
    + Completed upward swing
    + Identifiable reaction high

DISTRIBUTION_AR_CANDIDATE:
    Prior BC or Buying Climax context
    + Strong downward price reaction
    + Wide downward spread
    + Meaningful displacement from BC high

DISTRIBUTION_AR_CONFIRMED:
    AR_CANDIDATE
    + Completed downward swing
    + Identifiable reaction low
```

### Lưu ý

1. AR không bắt buộc phải có volume đột biến.
2. AR phải được đánh giá trong bối cảnh SC hoặc BC; không phải mọi nhịp tăng, giảm mạnh đều là AR.
3. AR không đồng nghĩa với xác nhận Accumulation hoặc Distribution.
4. Không cố định AR phải xuất hiện ngay phiên sau SC, BC.
5. Lưu `ar_high`, `ar_low` để làm biên Trading Range ban đầu.

### Cách đo trong hệ thống

Ngưỡng trong `RevisionConfig`, `ARConfig` và `DistributionConfig`. Mã nguồn: `_ar_reactions`, `_ar_events` trong `wyckoff/revision.py`. Phía BC dùng cùng thuật toán trên giá đổi dấu.

| Yếu tố | Cách đo |
|---|---|
| Bối cảnh | Trong 30 phiên sau SC đã xác nhận (định nghĩa mới) hoặc BC của nhật ký |
| Phiên phản ứng | Close đi đúng chiều so với phiên trước, True Range từ 1 ATR, đóng cửa ở nửa thuận chiều của phiên. Volume không tham gia, chỉ ghi lại |
| Rời vùng cao trào | Close cách đáy vùng (đỉnh vùng với BC) tối thiểu 2 ATR, tính từ đáy thấp nhất kể từ SC. Có đáy mới thì phiên phản ứng phải có lại từ đáy đó |
| Ứng viên | Đã có phiên phản ứng và đã rời vùng đủ xa, có thể ở bất kỳ phiên nào trong 30 phiên |
| Xác nhận | Đỉnh pivot (đáy pivot với BC) 3 phiên mỗi bên, từ phiên ứng viên trở đi; biết sau 3 phiên, không sớm hơn SC xác nhận |
| Bác bỏ ứng viên | Close thủng đáy SC quá 1 ATR (vượt đỉnh BC quá 0,5 ATR), hoặc hết 33 phiên chưa tạo swing |
| Bác bỏ sau xác nhận | SC hoặc BC bị bác bỏ |
| Biên ban đầu | `ar_high` và `sc_low`; `ar_low` và `bc_high` trong `details` |

Không đạt ứng viên thì không có sự kiện nào, nên hồi nhẹ không được ghi là AR. SC xác nhận bằng đường "có AR" cũng dùng định nghĩa này. ST được tìm sau AR theo định nghĩa này.

### Số đo khám phá

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định. Các cột cuối đo trong 60 phiên sau xác nhận.

| Loại | n ứng viên, thật / placebo | Từng xác nhận, thật / placebo (%) | Chiều cao trung vị (ATR) | Vượt `ar_high` / `ar_low`, thật / placebo (%) | Mất đáy SC / đỉnh BC, thật / placebo (%) | Lợi suất, thật / placebo (%) |
|---|---|---|---|---|---|---|
| AR | 1.030 / 1.309 | 92,1 / 94,3 | 3,9 / 4,0 | 72,4 / 72,5 | 39,0 / 53,2 | +5,6 / +2,8 |
| AR(d) | 1.135 / 840 | 89,6 / 89,8 | 4,1 / 4,2 | 66,1 / 70,3 | 51,7 / 58,6 | +6,1 / +3,4 |

- Sau xác nhận, close nằm trong vùng ban đầu khoảng một nửa số phiên (AR 49,7%, placebo 44,6%). Khoảng 70% ca vượt biên AR trong 60 phiên, trên cả dữ liệu thật và placebo, nên biên ban đầu chỉ là mốc tạm, không phải vùng giữ giá.
- Tỷ lệ xác nhận khoảng 90% ở cả hai bên: gần như mọi ứng viên đều tạo swing, nên phần sàng lọc nằm ở bước ứng viên.
- AR thật "mất đáy" ít hơn placebo, nhưng phần lớn thừa hưởng từ việc chọn SC (SC xác nhận: 46,0% / 57,2%). Chưa tách được đóng góp riêng của AR.
- Sau AR(d), lợi suất vẫn dương và cao hơn placebo, nên AR(d) không cho thấy giá giảm tiếp.
- Mức rời vùng 3 ATR cho 798 AR xác nhận, chiều cao 4,6 ATR, trễ 11 phiên, vượt biên 71,6% / 71,9%, lợi suất +5,7% / +3,4%. Kết quả tương tự, nên chọn 2 ATR để không bỏ qua phản ứng sớm.
- So với quy tắc cũ, 55,3% AR của nhật ký đạt định nghĩa này (placebo 40,6%), và 83,3% với AR(d) (placebo 72,4%).

### Phạm vi

Định nghĩa này áp dụng cho dashboard qua lớp đánh giá lại. Nhật ký, điểm tin cậy, backtest và cách dựng range (`detect_ar`, `sc_ar_anchors`) vẫn theo quy tắc cũ. Vì vậy `ar_high`, `ar_low` được lưu và đưa vào payload, nhưng khung range trên biểu đồ chưa dùng các giá trị này, và có thể khác biên ban đầu (ví dụ SSI: SC 17,34, AR 20,38; khung range 19,40 – 21,65).

### Giới hạn

- Các ngưỡng 1 ATR, 2 ATR, close_pos 0,5 và thời gian chờ là diễn giải định lượng do Claude đề xuất cho các cụm "biên độ lớn", "rời khỏi vùng đáy đáng kể"; cần được rà soát cùng người dùng.
- BC vẫn theo định nghĩa cũ, vì BC chưa được định nghĩa lại.
- Bối cảnh chỉ tính SC, BC đã nhận diện. Trường hợp "vùng bán tháo cực độ" mà không có SC chưa được xét.

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
| Xác nhận, một trong ba | Close >= đáy vùng + 2 ATR trong 10 phiên; hoặc có AR đã xác nhận; hoặc giá ổn định: tối thiểu 5 phiên trong 10 phiên đầu, không close dưới đáy ứng viên, volume trung bình <= 0,5 lần volume ứng viên. Riêng ổn định chỉ áp dụng khi có hấp thụ ngay trong phiên |
| Được phép giảm thêm | Close không thấp hơn đáy ứng viên quá 1 ATR |
| Bác bỏ | Trước xác nhận: close thủng ngưỡng trên, hoặc hết 30 phiên không có phản ứng. Sau xác nhận: close thủng ngưỡng trên trước khi giá hồi được đáy vùng + 3 ATR, trong 30 phiên |

Ứng viên xuất hiện trong 10 phiên sau một ứng viên khác mà chưa thủng ngưỡng thì được gộp vào ứng viên trước.

PS, AR, ST của một SC bị bác bỏ cũng bị bác bỏ theo. Trên biểu đồ hồi cứu, pha A bắt đầu từ phiên SC đã xác nhận còn hiệu lực; đoạn A mở bởi SC không còn hiệu lực thì được bỏ.

### Số đo khám phá

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định. "Mất đáy" là close dưới đáy SC trong 60 phiên sau xác nhận.

| Nhóm | n, thật / placebo | Mất đáy, thật / placebo (%) | Lợi suất 60 phiên, thật / placebo (%) |
|---|---|---|---|
| SC theo quy tắc cũ | 1.410 / 1.532 | 59,6 / 67,7 | +6,8 / +2,9 |
| SC xác nhận theo định nghĩa này | 1.104 / 1.377 | 46,0 / 57,2 | +6,0 / +2,9 |
| Xác nhận bằng phản ứng tăng mạnh | 874 / 1.054 | 41,8 / 54,7 | +7,0 / +3,2 |
| Xác nhận bằng AR | 81 / 154 | 46,8 / 57,3 | +2,4 / −0,4 |
| Xác nhận bằng giá ổn định | 149 / 169 | 70,9 / 72,7 | +2,0 / +4,4 |

Khoảng 55% ứng viên được xác nhận, trên cả dữ liệu thật và placebo. 60,5% SC xác nhận trùng phiên với SC cũ; 39,5% còn lại là SC cũ không nhận ra. Đường xác nhận bằng giá ổn định yếu nhất và không vượt placebo về lợi suất.

### Phạm vi

Định nghĩa này áp dụng cho dashboard qua lớp đánh giá lại. Nhật ký tại từng thời điểm, điểm tin cậy và backtest vẫn dùng quy tắc SC cũ (`detect_selling_climax`), nên điểm tin cậy "Có SC" có thể khác với nhãn trên biểu đồ.

### Giới hạn

- Hệ thống không có dữ liệu tin tức, nên chỉ nhận ra trường hợp tin tức gián tiếp qua việc thiếu phản ứng của giá.
- Các ngưỡng xác nhận (1 ATR, 2 ATR, 10 phiên, 0,5 lần volume) là diễn giải định lượng do Claude đề xuất cho các cụm "giảm thêm một ít", "phản ứng tăng mạnh", "ổn định"; cần được rà soát cùng người dùng.
