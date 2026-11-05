# Định nghĩa các giai đoạn (05/11/2026)

Tài liệu này ghi điều kiện để hệ thống gọi tên một giai đoạn. Ngưỡng nằm trong `RevisionConfig` và `StageConfig`, mã nguồn ở `wyckoff/revision.py` và `wyckoff/stages.py`.

| Giai đoạn | Tình trạng định nghĩa |
|---|---|
| Markdown | Định nghĩa lại 05/11/2026 |
| Accumulation | Định nghĩa lại 05/11/2026 |
| Markup | Tạm thời, theo khoảng cách giá |
| Distribution | Chưa định nghĩa lại, theo hướng thoát range |

## Nguyên tắc chung

Mỗi nhãn đi qua ba trạng thái: **tiềm năng → xác nhận → bác bỏ**. Dữ liệu mơ hồ thì chỉ dừng ở tiềm năng; chỉ xác nhận khi đã đủ điều kiện, và nhãn được sửa lại nếu dữ liệu về sau bác bỏ.

- **Biểu đồ hồi cứu** dùng trạng thái cuối để sửa nhãn các phiên đã qua.
- **Nhật ký tại từng thời điểm** chỉ dùng dữ liệu đến phiên đó. Backtest và điểm tin cậy dùng nhật ký này (`wyckoff/stages.py`, `wyckoff/phases.py`), nên vẫn gọi Markdown ngay khi range thoát xuống.

Quy tắc chi tiết của từng sự kiện: `docs/revision-rules.md`.

## Markdown

**Quy tắc quan trọng: không xác định Markdown chỉ vì giá giảm mạnh vài phiên.**

Markdown được xác nhận khi có phá vỡ hỗ trợ có ý nghĩa, cấu trúc giá chuyển sang LH–LL, và có bằng chứng cung áp đảo cầu cùng hồi phục yếu. Cả 5 điều kiện dưới đây phải đạt cùng lúc tại một phiên.

| # | Điều kiện | Ý nghĩa | Cách đo |
|---|---|---|---|
| 1 | Phá vỡ hỗ trợ | Giá đóng cửa dưới hỗ trợ của trading range hoặc cấu trúc trước đó | Close hiện tại dưới support của range. Với xu hướng theo SMA50: dưới đáy swing gần nhất đã biết khi vào xu hướng |
| 2 | Cấu trúc LH–LL | Giá liên tục tạo đỉnh thấp hơn và đáy thấp hơn | Sau phiên thủng đầu tiên: tối thiểu 1 đỉnh swing thấp hơn và 2 đáy swing thấp hơn, cả chuỗi giảm dần; close chưa vượt đỉnh gần nhất |
| 3 | Nhịp hồi yếu | Hồi biên độ nhỏ, khối lượng thấp, không vượt đỉnh trước | Nhịp hồi gần nhất đã hoàn tất: hồi không quá 61,8% nhịp giảm trước đó, volume trung bình không cao hơn nhịp giảm, đỉnh thấp hơn đỉnh trước |
| 4 | Cung áp đảo cầu | Phiên giảm spread rộng, khối lượng tăng; phiên tăng spread hẹp, khối lượng thấp | Từ phiên thủng: phiên giảm có volume trung bình và biên độ trung bình cùng cao hơn phiên tăng; tối thiểu 3 phiên mỗi loại |
| 5 | Không có cầu đủ mạnh | Các nỗ lực phục hồi thất bại, không có SOS đáng tin cậy | Từ phiên thủng: không có SOS, không có phiên demand (nến tăng, volume >= 1,5x TB20, close_pos >= 0,7) đóng cửa vượt đỉnh swing gần nhất |

Đỉnh và đáy swing dùng cùng nguồn pivot với biên range (`ranges.pivot_source`), với 5 phiên mỗi bên nên mỗi pivot được biết sau 5 phiên.

**Tiềm năng:** bắt đầu từ phiên range thoát xuống (close ngoài support hơn 0,5 ATR trong 3 phiên liên tiếp), hoặc khi có 5 close liên tiếp dưới SMA50 đang giảm. Xu hướng kết thúc mà chưa đủ điều kiện thì giữ nguyên tiềm năng.

**Bác bỏ:**
- Trước xác nhận: close quay lại trên support của range (hoặc qua lại SMA50 lúc vào xu hướng).
- Sau xác nhận, trong 60 phiên: close vượt resistance của range hoặc có SOS reclaim. Quay lại support chỉ là cảnh báo, vì hồi lên kiểm tra support cũ là bình thường (LPSY).

**Sự kiện:**

| Sự kiện | Vai trò | Ý nghĩa |
|---|---|---|
| SOW (Sign of Weakness) | Hỗ trợ, không bắt buộc | Dấu hiệu suy yếu, thường xuất hiện khi giá phá hỗ trợ với lực bán mạnh |
| LPSY (Last Point of Supply) | Hỗ trợ, không bắt buộc | Điểm cung cuối cùng, nhịp hồi yếu trước khi giá tiếp tục giảm |
| UT / UTAD | Thuộc Distribution, **không phải** điều kiện của Markdown | Có thể xuất hiện trong giai đoạn phân phối trước khi Markdown bắt đầu |

## Accumulation

Accumulation là giai đoạn thị trường hình thành vùng giao dịch đi ngang (Trading Range, TR) sau một xu hướng giảm (Markdown), trong đó nguồn cung dần được hấp thụ bởi lực cầu. Khi quá trình hấp thụ cung hoàn tất, giá có khả năng thoát khỏi TR và bắt đầu Markup.

**Nguyên tắc cốt lõi: Accumulation là một quá trình hấp thụ cung, không phải một tập hợp các sự kiện SC, AR, ST, Spring.** Accumulation không đơn thuần là giá đi ngang; nó phải thể hiện cán cân cung cầu chuyển từ bên bán sang bên mua. Các sự kiện chỉ là bằng chứng giúp nhận diện quá trình đó. Không dùng chuỗi `SC → AR → ST → Spring → SOS → LPS` làm điều kiện bắt buộc. Thay vào đó đánh giá:

- **Market Context:** xu hướng trước đó.
- **Trading Range:** cấu trúc vùng giá.
- **Supply Analysis:** quá trình hấp thụ cung.
- **Demand Analysis:** sự xuất hiện của lực cầu.
- **Structural Transition:** chuyển đổi từ TR sang Markup.

### Điều kiện nhận diện

| Yếu tố | Nội dung |
|---|---|
| Prior Trend | Trước đó có xu hướng giảm (Markdown) đủ rõ ràng |
| Trading Range | Giá bắt đầu hình thành vùng hỗ trợ và kháng cự tương đối ổn định |
| Selling Pressure | Áp lực bán dần suy yếu, các nhịp giảm khó tạo đáy thấp mới |
| Volume Behavior | Xuất hiện những phiên bán mạnh nhưng giá không giảm tương ứng, cho thấy khả năng hấp thụ cung |
| Demand Emergence | Các nhịp tăng ngày càng mạnh, spread mở rộng và volume cải thiện |
| Structural Change | Giá bắt đầu hình thành Higher Low (HL), vượt các vùng kháng cự quan trọng |

### Các pha

| Pha | Đặc điểm | Sự kiện thường gặp |
|---|---|---|
| A, Stopping Action | Dừng xu hướng giảm trước đó | PS, SC, AR, ST |
| B, Building Cause | Hấp thụ cung, xây dựng nền giá | Secondary Tests, các nhịp kiểm tra cung |
| C, Testing Supply | Kiểm tra lượng cung còn lại | Spring hoặc Test (không bắt buộc Spring) |
| D, Demand Dominance | Cầu bắt đầu kiểm soát thị trường | SOS, LPS |
| E, Markup | Giá thoát khỏi TR và hình thành xu hướng tăng | Breakout, HH, HL |

### Sự kiện không bắt buộc

| Sự kiện | Bắt buộc? |
|---|---|
| PS | Không |
| SC | Không bắt buộc về hình thái, nhưng cần bằng chứng dừng xu hướng giảm |
| AR | Không bắt buộc |
| ST | Không |
| Spring | Không |
| SOS | Không nhất thiết phải có đúng sự kiện SOS theo định nghĩa cổ điển, nhưng cần bằng chứng cầu chiếm ưu thế trước khi xác nhận chuyển sang Markup |
| LPS | Không |

### Phân biệt với Trading Range thông thường

| Accumulation | Trading Range chưa xác định |
|---|---|
| Xuất hiện sau Markdown | Có thể xuất hiện sau bất kỳ xu hướng nào |
| Có dấu hiệu hấp thụ cung | Chưa xác định được cán cân cung cầu |
| Selling Pressure suy yếu | Chưa rõ bên nào kiểm soát |
| Demand dần gia tăng | Chưa có bằng chứng cầu chiếm ưu thế |
| Có khả năng chuyển sang Markup | Chưa xác định hướng phá vỡ |

### Ba mức

| Mức | Điều kiện | Trên biểu đồ |
|---|---|---|
| **Candidate** | Có Markdown trước đó; giá bắt đầu hình thành TR; có dấu hiệu áp lực bán suy yếu | `Acc?` trong đoạn range |
| **Developing** | TR được duy trì; có bằng chứng hấp thụ cung; các nhịp giảm suy yếu; xuất hiện dấu hiệu cầu gia tăng | `Accumulation?`, nhạt |
| **Confirmed** | Có bằng chứng cầu chiếm ưu thế; có SOS hoặc breakout đáng tin cậy; giá giữ được hỗ trợ sau breakout, hoặc có LPS; cấu trúc bắt đầu chuyển sang HH–HL | `Initial Accumulation`, đậm |

Không bắt buộc phải đi qua Developing rồi mới Confirmed, vì các mức mô tả bằng chứng đã có, không phải chuỗi sự kiện.

### Cách đo trong hệ thống

Ngưỡng trong `RevisionConfig`, mã nguồn `_range_verdicts` trong `wyckoff/revision.py`. Volume tính theo tỷ lệ TB20, biên độ tính theo ATR. "Gần đây" là 20 phiên gần nhất, không vượt quá đầu range.

| Yếu tố | Cách đo |
|---|---|
| Có Markdown trước đó | Close đầu range thấp hơn close cao nhất 120 phiên trước từ 15%, và một trong: xu hướng trước range là Markdown, SMA50 đang giảm, có SC xác nhận gần đầu range |
| Áp lực bán suy yếu | Phiên giảm gần đây có volume hoặc biên độ không cao hơn đoạn 20 phiên trước range; 10 phiên gần nhất không close dưới support − 0,5 ATR |
| TR được duy trì | Range còn hoạt động; hoặc đã thoát lên; hoặc thoát xuống nhưng Markdown bị bác bỏ |
| Hấp thụ cung | Có phiên volume >= 1,5 lần ở nửa dưới range, với close_pos >= 0,5 hoặc giá chỉ đổi dưới 0,5 ATR; hoặc có SC, ST, Spring, Test đã xác nhận làm bằng chứng |
| Cầu gia tăng | Phiên tăng gần đây có volume và biên độ không thấp hơn phiên giảm |
| Cầu chiếm ưu thế | Volume phiên tăng gần đây cao hơn phiên giảm; rất ít phiên giảm cũng được tính |
| SOS hoặc breakout | SOS đã xác nhận còn hiệu lực, hoặc range thoát lên |
| Giữ hỗ trợ hoặc có LPS | LPS đã xác nhận; hoặc tối thiểu 10 phiên sau breakout, close không sâu quá 3% dưới resistance |
| HH–HL | Close sau breakout vượt resistance (HH); đáy swing sau breakout cao hơn đáy trước đó (HL). Chưa có đáy swing thì dùng LPS, hoặc việc đã giữ trên hỗ trợ đủ lâu |

**Bác bỏ:**
- Trước khi Confirmed: Markdown của range được xác nhận; thoát xuống và không quay lại trong 30 phiên; hoặc range mới đã xác nhận.
- Sau khi Confirmed, trong 60 phiên: SOS làm căn cứ bị bác bỏ, hoặc close thủng đáy Spring còn hiệu lực (không có Spring thì thủng support). Một LPS thất bại không gỡ nhãn.

**Nhãn:** Initial Accumulation khi trước range là Markdown theo nhật ký, Accumulation khi bối cảnh giảm đến từ SMA50 hoặc SC. Range sau Markup không được xem là Accumulation theo định nghĩa này; Re-accumulation chưa được định nghĩa lại.

**Trên biểu đồ hồi cứu:** Confirmed và Developing phủ một đoạn liền từ đầu range đến trước Markup. Range không đạt hoặc bị bác bỏ hiện `TR ?`. Thẻ giai đoạn liệt kê từng bằng chứng "Đạt" hoặc "Chưa", kèm sự kiện làm bằng chứng.

**Spring trong Accumulation:** range thoát xuống rồi quay lại trên support với demand trong 30 phiên, khi Markdown chưa xác nhận và chưa có SC xác nhận tạo sau cú thủng, được tính là Spring kéo dài. Có SC mới thì giá đã sang cấu trúc mới. Biểu đồ hồi cứu vẽ từ phiên Spring đến trước SOS là pha C.

### Dải pha trên biểu đồ

Pha A đến E là pha của Accumulation, nên chỉ range đang ở mức Candidate, Developing hoặc Confirmed mới có pha. Range không sau Markdown, hoặc đã bị bác bỏ, chỉ là Trading Range chưa xác định: không có pha. "Vô hiệu" và "Chờ" vẫn hiện như trước. Sự kiện chỉ định mốc khi có, không sự kiện nào bắt buộc.

| Pha | Bắt đầu từ |
|---|---|
| A | SC đã xác nhận gần đầu range; không có SC thì đầu range |
| B | Phiên xác nhận TR, hoặc ST nếu sớm hơn |
| C | Spring hoặc Test sớm nhất trước pha D. Không có thì không có pha C |
| D | SOS, hoặc khi cầu bắt đầu kiểm soát: 5 phiên liên tiếp cầu chiếm ưu thế, close ở nửa trên range, đáy swing gần nhất cao hơn đáy trước. Close thủng support thì bỏ mốc này và xét lại |
| E | Giá thoát khỏi TR: range thoát lên, hoặc 3 phiên close trên ngưỡng thoát sau SOS reclaim |

Nhật ký tại từng thời điểm (`result.phases`), điểm tin cậy và mức xác nhận, vô hiệu trên dashboard vẫn theo máy trạng thái cũ.

**Số đo khám phá (cache H8, 311 mã, từ 2018):** khoảng 60% số phiên không có pha nào (placebo cũng khoảng 60%). Trong 979 range còn là Accumulation đến cuối (placebo 1.040), 14,5% có pha C (17,0%), 73,9% có pha D (61,6%), 85,5% có pha E (93,8%). Trong các range có pha D, 73% có mốc D không đến từ SOS (528 so với 195). Các tỷ lệ này được tính sau khi đã biết nhãn cuối, nên chỉ mô tả cơ cấu, không đo khả năng dự báo.

### Số đo khám phá của Accumulation

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định.

| Chỉ số | Thật (7.765 range) | Placebo (8.413 range) |
|---|---|---|
| Từng là Candidate | 37,9% | 39,3% |
| Từng là Developing | 26,1% | 31,2% |
| Từng là Confirmed | 16,5% | 16,1% |
| Giữ Confirmed đến cuối (trong số Confirmed) | 65,9% | 72,4% |
| Close thủng support trong 60 phiên sau Confirmed | 24,4% | 21,9% |
| Lợi suất 60 phiên sau Confirmed | +3,7% | +3,4% |
| Range từng Developing thoát lên | 51,0% | 56,8% |
| Mọi range thoát lên | 52,8% | 53,5% |

Các tỷ lệ gần như bằng placebo, nên định nghĩa này mô tả hành vi của quy tắc, chưa phân biệt được thị trường thật với dữ liệu xáo trộn, và Developing chưa cho thông tin về hướng thoát. Nhóm Confirmed có LPS cho lợi suất +11,9% (n = 95), nhưng placebo cũng +12,0% (n = 55), nên đó chủ yếu là hiệu ứng cơ học.

## Markup (tạm thời)

**Tiềm năng:** range thoát lên, hoặc 5 close liên tiếp trên SMA50 đang tăng.

**Xác nhận:** tối thiểu 10 phiên và close cách mốc tham chiếu từ 3 ATR trở lên. Mốc là resistance của range, hoặc SMA50 lúc vào xu hướng.

**Bác bỏ:** close dưới support của range, hoặc dưới mốc SMA50. Từ range, close quay lại dưới resistance chưa phải bác bỏ, vì pullback sau breakout là bình thường (LPS).

Định nghĩa này chỉ dựa vào khoảng cách giá, chưa đối xứng với Markdown.

## Distribution (chưa định nghĩa lại)

**Hiện tại:** range thoát xuống được gán Initial Distribution (trước đó là Markup) hoặc Re-distribution (trước đó là Markdown). Trên biểu đồ, nhãn có "?" khi Markdown sau đó còn tiềm năng và trở về "TR ?" khi Markdown bị bác bỏ.

Sự kiện liên quan: BC, AR(d), ST(d), UT, UTAD, SOW, LPSY.

## Chưa có xu hướng

Trong range chưa phân định, hoặc sau 5 close liên tiếp nằm sai phía SMA50, hoặc xu hướng đã bị bác bỏ.

## Số đo khám phá của Markdown

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định. "Quay lại" tính trong 60 phiên sau xác nhận.

| Yêu cầu LH–LL, xu hướng từ range | Được xác nhận, thật / placebo (%) | Độ trễ trung vị từ phiên thoát, thật (phiên) | Quay lại support, thật / placebo (%) | Quay lại resistance, thật / placebo (%) |
|---|---|---|---|---|
| 1 đỉnh, 1 đáy | 17,8 / 15,8 | 16 | 43,5 / 46,6 | 13,1 / 18,1 |
| **1 đỉnh, 2 đáy (mặc định)** | **8,6 / 8,7** | **22** | **31,2 / 37,6** | **8,3 / 14,3** |
| 2 đỉnh, 1 đáy | 2,7 / 3,6 | 34 | 20,7 / 22,6 | 4,3 / 8,0 |
| 2 đỉnh, 2 đáy | 2,5 / 3,0 | 35 | 21,6 / 19,1 | 5,7 / 6,1 |

Mức mặc định được chọn vì đáy đầu tiên sau khi thủng luôn thấp hơn hỗ trợ, nên phải có 2 đáy mới tạo được chuỗi đáy, đỉnh thấp hơn, đáy thấp hơn; và mức này cách placebo xa nhất ở chỉ số quay lại resistance.

**Hệ quả cần biết:**
- Chỉ khoảng 1/12 lần thoát xuống được xác nhận Markdown; 36,5% còn tiềm năng và 55,6% bị bác bỏ. Điều kiện chặn nhiều nhất là cung áp đảo cầu, tiếp đến là LH–LL và nhịp hồi yếu.
- Khi được xác nhận, giá trung vị đã dưới hỗ trợ 13,4%, và lợi suất 20 phiên sau đó khoảng +0,5%. Vì vậy nhãn xác nhận mô tả điều đã xảy ra, không phải tín hiệu.
- Tỷ lệ xác nhận trên dữ liệu thật và placebo gần bằng nhau, nên 5 điều kiện chưa cho thấy phân biệt được thị trường thật với dữ liệu xáo trộn.
