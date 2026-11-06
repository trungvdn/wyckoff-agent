# Định nghĩa các sự kiện Wyckoff

Tài liệu sống, bổ sung dần từng sự kiện. Định nghĩa các giai đoạn nằm ở `docs/stage-definitions.md`; trạng thái tiềm năng, xác nhận, bác bỏ của các sự kiện chưa định nghĩa lại nằm ở `docs/revision-rules.md`.

| Sự kiện | Tình trạng |
|---|---|
| SC (Selling Climax) | Định nghĩa 05/11/2026 |
| LPS (Last Point of Support) | Định nghĩa 05/11/2026 |
| AR (Automatic Rally / Automatic Reaction) | Định nghĩa 06/11/2026 |
| ST (Secondary Test) | Định nghĩa 06/11/2026 |
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
