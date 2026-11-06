# Định nghĩa các giai đoạn (05/11/2026)

Tài liệu này ghi điều kiện để hệ thống gọi tên một giai đoạn. Ngưỡng nằm trong `RevisionConfig` và `StageConfig`, mã nguồn ở `wyckoff/revision.py` và `wyckoff/stages.py`.

| Giai đoạn | Tình trạng định nghĩa |
|---|---|
| Markdown | Định nghĩa lại 05/11/2026 |
| Accumulation | Định nghĩa lại 05/11/2026 |
| Markup | Định nghĩa lại 05/11/2026 |
| Re-accumulation | Định nghĩa lại 05/11/2026; là cấu trúc trong Markup, không phải giai đoạn riêng |
| Distribution | Định nghĩa lại 05/11/2026 |
| Redistribution | Chưa định nghĩa; là cấu trúc trong Markdown, hiện vẫn theo hướng thoát range |

Phân tầng: **Market State** gồm Accumulation, Markup, Distribution, Markdown. **Market Structure** gồm Trading Range, Re-accumulation, Redistribution.

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
- **Mở lại:** Markdown từ range đã bị bác bỏ theo cách trên được mở lại về tiềm năng khi giá thủng lần nữa theo đúng tiêu chí thoát range (close dưới support hơn 0,5 ATR trong 3 phiên liên tiếp), và các điều kiện được đo lại từ cú thủng này. Mở lại và bác bỏ có thể lặp nhiều lần, cho đến khi xu hướng trong nhật ký kết thúc.
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
| TR được duy trì | Range còn hoạt động; hoặc đã thoát lên; hoặc thoát xuống nhưng Markdown đang bị bác bỏ. Markdown được mở lại thì điều kiện này không còn đạt |
| Hấp thụ cung | Có phiên volume >= 1,5 lần ở nửa dưới range, với close_pos >= 0,5 hoặc giá chỉ đổi dưới 0,5 ATR; hoặc có SC, ST, Spring, Test đã xác nhận làm bằng chứng |
| Cầu gia tăng | Phiên tăng gần đây có volume và biên độ không thấp hơn phiên giảm |
| Cầu chiếm ưu thế | Volume phiên tăng gần đây cao hơn phiên giảm; rất ít phiên giảm cũng được tính |
| SOS hoặc breakout | SOS đã xác nhận còn hiệu lực, hoặc range thoát lên |
| Giữ hỗ trợ hoặc có LPS | LPS đã xác nhận; hoặc tối thiểu 10 phiên sau breakout, close không sâu quá 3% dưới resistance |
| HH–HL | Close sau breakout vượt resistance (HH); đáy swing sau breakout cao hơn đáy trước đó (HL). Chưa có đáy swing thì dùng LPS, hoặc việc đã giữ trên hỗ trợ đủ lâu |

**Bác bỏ:**
- Trước khi Confirmed: Markdown của range được xác nhận; đã thoát xuống và 30 phiên không close trong range mà giá đang dưới support; hoặc range mới đã xác nhận.
- Sau khi Confirmed, trong 60 phiên: SOS làm căn cứ bị bác bỏ, hoặc close thủng đáy Spring còn hiệu lực (không có Spring thì thủng support). Một LPS thất bại không gỡ nhãn.

**Thời hạn đánh giá sau khi thoát xuống:** 30 phiên kể từ phiên thoát hoặc phiên cuối close còn trong range (giữa support và resistance), tùy phiên nào muộn hơn. Giá còn trong range thì range còn được đánh giá. Close trên resistance không kéo dài thời hạn. Quy tắc này dùng chung cho Accumulation, Re-accumulation và Distribution.

**Nhãn:** Initial Accumulation khi trước range là Markdown theo nhật ký, Accumulation khi bối cảnh giảm đến từ SMA50 hoặc SC. Range sau Markup đã rõ được xét là Re-accumulation (mục riêng bên dưới).

**Trên biểu đồ hồi cứu:** Confirmed và Developing phủ một đoạn liền từ đầu range đến trước Markup. Range không đạt hoặc bị bác bỏ hiện `TR ?`. Thẻ giai đoạn liệt kê từng bằng chứng "Đạt" hoặc "Chưa", kèm sự kiện làm bằng chứng.

**Spring trong Accumulation:** định nghĩa đầy đủ ở `docs/event-definitions.md`. Spring được xét cả khi range đã thoát xuống mà Markdown đang bị bác bỏ. Có SC mới thì giá đã sang cấu trúc mới. Biểu đồ hồi cứu vẽ từ phiên Spring sớm nhất liên quan đến cú thoát đến trước SOS là pha C.

**Khung range trên biểu đồ:** range đã thoát nhưng vẫn là cấu trúc hiện tại (không có xu hướng nào còn đứng, còn trong thời hạn đánh giá) thì khung kéo đến phiên cuối. Biên support và resistance giữ nguyên. Nhật ký vẫn ghi range đã kết thúc tại phiên thoát.

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

**Số đo khám phá (cache H8, 311 mã, từ 2018):** 42,8% số phiên không có pha nào (placebo 43,1%). Trong 1.763 range còn là Accumulation hoặc Re-accumulation đến cuối (placebo 1.888), 16,4% có pha C (20,1%), 77,5% có pha D (62,7%), 83,5% có pha E (90,5%). Trong các range có pha D, 70% có mốc D không đến từ SOS (950 so với 417). Các tỷ lệ này được tính sau khi đã biết nhãn cuối, nên chỉ mô tả cơ cấu, không đo khả năng dự báo.

### Hiển thị cấu trúc và mức bằng chứng

Thẻ giai đoạn gọi tên theo cấu trúc đại diện của range khi cấu trúc đó đã phân định và ở mức Developing hoặc Confirmed: `Accumulation đang hình thành`, `Re-accumulation đang hình thành`, `Distribution đang hình thành`, hoặc tên đầy đủ khi Confirmed. Candidate vẫn hiện các giả thuyết như cũ.

Quy tắc áp dụng cả khi giá đã rời range mà không còn xu hướng nào đứng, ví dụ thoát xuống rồi quay lại và Markdown bị bác bỏ. Khi đó Market State là trạng thái của cấu trúc, và đoạn trên dải giai đoạn kéo đến phiên cuối. Xu hướng còn đứng thì giai đoạn là xu hướng đó. Hết thời gian đánh giá (30 phiên không close trong range sau khi thoát xuống, 60 phiên sau khi thoát lên hoặc sau Confirmed) thì bằng chứng ngừng cập nhật, thẻ không còn gọi là cấu trúc hiện tại.

**Mức bằng chứng** là tỷ lệ điều kiện đang đạt: thấp dưới 50%, trung bình từ 50%, cao từ 70%. Đây là độ đầy đủ của bằng chứng, không phải xác suất. Thẻ không hiện phần trăm xác suất, vì số đo dưới đây không phân biệt được với dữ liệu xáo trộn.

Đo tại thời điểm trên cache H8, 311 mã, từ 2018. Mỗi range tính một lần cho mỗi số bằng chứng khi đang Developing; bỏ các trường hợp chưa có kết cục. Đây là khám phá trên mẫu cũ, không phải kiểm định.

| Accumulation, mức bằng chứng | Số trường hợp, thật / placebo | Sau đó Confirmed, thật / placebo | Lợi suất 60 phiên, thật / placebo |
|---|---|---|---|
| Thấp | 2.956 / 3.791 | 21,5% / 21,5% | +1,5% / +3,1% |
| Trung bình | 3.321 / 4.383 | 41,1% / 38,5% | +1,6% / +3,0% |
| Cao | 947 / 1.602 | 74,2% / 66,4% | +3,9% / +2,7% |

Tỷ lệ Confirmed tăng theo mức ở cả hai bên, nên phần lớn là cơ học: Confirmed dùng chính các điều kiện này. Lợi suất không tăng đều theo mức. Riêng range đã thoát xuống rồi quay lại, Confirmed vẫn hiếm ở mức trung bình: 7,7% (n = 260), placebo 8,4%. Trước khi đổi cách tính thời hạn, hai số này là 6,1% (n = 197) và 3,1%: thời hạn dài hơn cho thêm cơ hội xác nhận ở cả hai bên, nhưng không tạo được khác biệt với placebo.

### Số đo khám phá của Accumulation

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định.

| Chỉ số | Thật (7.765 range) | Placebo (8.413 range) |
|---|---|---|
| Từng là Candidate | 36,9% | 38,7% |
| Từng là Developing | 25,7% | 31,2% |
| Từng là Confirmed | 16,2% | 16,2% |
| Giữ Confirmed đến cuối (trong số Confirmed) | 65,7% | 72,0% |
| Close thủng support trong 60 phiên sau Confirmed | 24,9% | 22,9% |
| Lợi suất 60 phiên sau Confirmed | +3,3% | +3,3% |
| Range từng Developing thoát lên | 50,5% | 55,9% |
| Mọi range thoát lên | 52,8% | 53,5% |

Các tỷ lệ gần như bằng placebo, nên định nghĩa này mô tả hành vi của quy tắc, chưa phân biệt được thị trường thật với dữ liệu xáo trộn, và Developing chưa cho thông tin về hướng thoát. Nhóm Confirmed có LPS cho lợi suất +11,7% (n = 89), nhưng placebo cũng +12,1% (n = 56), nên đó chủ yếu là hiệu ứng cơ học.

## Markup

Markup là giai đoạn thị trường chuyển sang xu hướng tăng sau khi quá trình Accumulation hoặc Re-accumulation hoàn tất. Trong giai đoạn này, lực cầu chiếm ưu thế so với nguồn cung, khiến giá liên tục hình thành các đỉnh cao hơn (Higher High, HH) và đáy cao hơn (Higher Low, HL).

**Điểm cốt lõi: Markup không chỉ là giá tăng, mà là một xu hướng tăng được duy trì bởi sự mất cân bằng cung cầu theo hướng có lợi cho bên mua.** Markup là một Market State, không phải một sự kiện đơn lẻ. Một vài phiên tăng mạnh không đủ để kết luận cổ phiếu đã bước vào Markup.

Không yêu cầu chuỗi `SOS → LPS → HH → HL → SOS → LPS`. Thay vào đó đánh giá liên tục:

- **Trend Structure:** HH–HL.
- **Demand/Supply:** tương quan cung cầu.
- **Momentum:** sức mạnh và độ bền của các nhịp tăng.
- **Support Integrity:** khả năng giữ các vùng hỗ trợ.
- **Range Expansion:** khả năng mở rộng biên độ tăng.

### Điều kiện nhận diện

| Yếu tố | Nội dung |
|---|---|
| Prior Structure | Trước đó có Accumulation hoặc Re-accumulation, hoặc một nền giá đủ rõ ràng |
| Breakout | Giá phá vỡ vùng kháng cự hoặc Trading Range với lực cầu đáng tin cậy |
| Price Structure | Hình thành cấu trúc HH–HL liên tiếp |
| Demand | Các nhịp tăng có spread mở rộng, volume cải thiện |
| Supply Weakness | Các nhịp điều chỉnh thường có spread thu hẹp, volume suy giảm |
| Trend Persistence | Giá duy trì trên các vùng hỗ trợ quan trọng và tiếp tục tạo đỉnh mới |

### Sự kiện thường gặp

| Sự kiện | Ý nghĩa | Bắt buộc? |
|---|---|---|
| SOS | Dấu hiệu sức mạnh của cầu | Không bắt buộc lặp lại |
| LPS | Điểm hỗ trợ cuối cùng sau nhịp điều chỉnh | Không |
| HH | Đỉnh cao hơn đỉnh trước | Đặc trưng của xu hướng tăng |
| HL | Đáy cao hơn đáy trước | Đặc trưng của xu hướng tăng |
| BU / BUEC | Back-up sau khi vượt kháng cự | Không |
| Re-accumulation | Tích lũy lại trong xu hướng tăng | Không |

### Trạng thái vận động

Đây là cách phân loại để phân tích, không phải bốn pha A–D chính thức của Wyckoff.

| Trạng thái | Nội dung | Cách đo |
|---|---|---|
| Early Markup | Giá breakout khỏi vùng tích lũy, xác lập xu hướng tăng mới | Đã breakout, chưa Confirmed |
| Established Markup | Giá duy trì HH–HL, cầu chiếm ưu thế | Đã Confirmed |
| Extended Markup | Xu hướng tăng kéo dài, biên độ có thể mở rộng, biến động mạnh hơn | Đã Confirmed, từ 60 phiên sau breakout, hoặc ATR gấp 1,5 lần lúc breakout |
| Markup Weakening | Đà tăng suy yếu, cung gia tăng, cấu trúc có nguy cơ bị phá vỡ | Từ Developing trở lên, và có đỉnh thấp hơn đỉnh trước, hoặc close dưới đáy swing gần nhất, hoặc phiên giảm có volume và biên độ cao hơn phiên tăng |

### Phân biệt với nhịp hồi trong Markdown

| Markup | Nhịp hồi phục trong Markdown |
|---|---|
| Phá vỡ cấu trúc kháng cự quan trọng | Chưa vượt được đỉnh cấu trúc |
| Hình thành HH–HL | Có thể vẫn hình thành LH |
| Cầu duy trì ưu thế | Cầu chỉ xuất hiện tạm thời |
| Điều chỉnh thường giữ được HL | Giá có thể tiếp tục tạo LL |
| Xu hướng tăng được duy trì | Giá có nguy cơ tiếp tục giảm |

### Ba mức

| Mức | Điều kiện | Trên biểu đồ |
|---|---|---|
| **Candidate** | Giá breakout khỏi Trading Range; có dấu hiệu Demand Expansion; giá bắt đầu phá cấu trúc Lower High trước đó | `Markup?`, nhạt |
| **Developing** | Breakout được duy trì; hình thành HH–HL; các nhịp điều chỉnh có dấu hiệu suy yếu về cung | `Markup?`, nhạt |
| **Confirmed** | Xu hướng HH–HL được xác lập qua nhiều nhịp vận động; các vùng hỗ trợ cấu trúc được giữ; lực cầu tiếp tục chiếm ưu thế | `Markup`, đậm |

### Cách đo trong hệ thống

Ngưỡng trong `RevisionConfig`, mã nguồn `_MarkupTest` trong `wyckoff/revision.py`. Volume tính theo tỷ lệ TB20, biên độ theo ATR. "Gần đây" là tối đa 20 phiên, không tính trước breakout.

| Điều kiện | Cách đo |
|---|---|
| Có nền giá | Range vừa thoát lên; với xu hướng theo SMA50 là range đã xác nhận, kết thúc trong 60 phiên trước. Không có thì không xác nhận được |
| Phá vỡ kháng cự | Có close trên resistance của nền kể từ khi range kết thúc, và hiện không sâu quá 3% dưới resistance |
| Cầu mở rộng | Phiên tăng gần đây có volume và biên độ không thấp hơn phiên giảm; rất ít phiên giảm cũng được tính |
| Phá đỉnh cấu trúc | Close vượt đỉnh swing gần nhất trước breakout |
| Breakout được duy trì | Từ breakout đến nay, close không sâu quá 3% dưới resistance |
| HH–HL | Pivot theo close, 3 phiên mỗi bên (`mk_pivot_bars`), ngắn hơn pivot của biên range để không bỏ sót nhịp điều chỉnh ngắn khi giá tăng theo bậc thang. Tính từ pivot mới nhất ngược lại: tối thiểu 1 đỉnh và 1 đáy cao dần liên tiếp sau breakout |
| Điều chỉnh yếu về cung | Phiên giảm gần đây có volume và biên độ không cao hơn phiên tăng |
| HH–HL qua nhiều nhịp | Tối thiểu 2 đỉnh và 2 đáy cao dần liên tiếp |
| Giữ hỗ trợ cấu trúc | Close không dưới đáy swing gần nhất sau breakout, và không sâu quá 3% dưới resistance |
| Cầu chiếm ưu thế | Volume phiên tăng gần đây cao hơn phiên giảm |

Xu hướng bắt đầu ở mức tiềm năng khi range thoát lên, hoặc khi có 5 close liên tiếp trên SMA50 đang tăng. Thẻ giai đoạn liệt kê từng điều kiện và trạng thái vận động; SOS và LPS chỉ hiện như sự kiện hỗ trợ.

**Bác bỏ:** close dưới support của range, hoặc dưới mốc SMA50 lúc vào xu hướng; sau khi Confirmed thì xét trong 60 phiên. Close quay lại dưới resistance chưa phải bác bỏ, vì pullback sau breakout là bình thường. Tạo đỉnh thấp hơn chỉ chuyển sang Markup Weakening, chưa phải bác bỏ.

**Chưa đo:** Momentum và Range Expansion chỉ phản ánh gián tiếp qua volume, biên độ và trạng thái Extended. BU / BUEC chưa có bộ phát hiện.

### Số đo khám phá của Markup

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định.

| Chỉ số, Markup từ range | Thật (4.131) | Placebo (4.572) |
|---|---|---|
| Từng Developing | 65,8% | 58,5% |
| Từng Confirmed | 27,7% | 26,3% |
| Độ trễ xác nhận trung vị | 22 phiên | 22 phiên |
| Lợi suất 60 phiên sau Confirmed | +7,1% | +3,8% |
| Close dưới resistance trong 60 phiên sau Confirmed | 29,9% | 34,1% |

Quy tắc trước đó (10 phiên + 3 ATR) xác nhận 55,1% với lợi suất 60 phiên +7,1% (placebo 57,9%, +3,7%). Định nghĩa này chọn lọc hơn nhiều nhưng lợi suất gần như không đổi, và tỷ lệ xác nhận gần bằng placebo.

Đã so ba mức pivot: 5 phiên xác nhận 13,3%, trễ 37 phiên, 19,3% close quay lại dưới resistance; 3 phiên như bảng trên; 2 phiên xác nhận 33,5%, trễ 15 phiên, 34,6%. Lợi suất 60 phiên đều khoảng +7%. Chọn 3 phiên vì pivot 5 phiên bỏ sót nhịp điều chỉnh ngắn của xu hướng tăng theo bậc thang (ca MSB tháng 10/2026), còn 2 phiên coi cả dao động nhỏ là một nhịp. Đánh đổi là xác nhận sớm hơn nên giá dễ quay lại dưới resistance hơn.

Xu hướng tăng thẳng, không có nhịp điều chỉnh nào đủ 3 phiên, vẫn không tạo được đỉnh và đáy swing nên chỉ dừng ở tiềm năng.

## Re-accumulation

Re-accumulation là quá trình thị trường tạm dừng xu hướng Markup để hình thành một Trading Range mới, trong đó nguồn cung được hấp thụ và lực cầu tiếp tục duy trì ưu thế. Sau khi quá trình này hoàn tất, giá có khả năng tiếp tục xu hướng tăng (Markup).

**Khác biệt:** Accumulation xuất hiện sau Markdown, còn Re-accumulation xuất hiện trong một xu hướng tăng đã được hình thành.

**Đây là cấu trúc, không phải trạng thái.** Re-accumulation là Market Structure nằm bên trong Market State Markup, không phải một xu hướng độc lập tương đương Markup hay Markdown:

```
Market State:     Accumulation, Markup, Distribution, Markdown
Market Structure: Trading Range, Re-accumulation, Redistribution và các cấu trúc con

Accumulation → Markup → Re-accumulation → Markup → Re-accumulation → Markup → Distribution → Markdown
```

**Nguyên tắc:** không định nghĩa `Markup → Trading Range = Re-accumulation`, mà là `Markup → Trading Range → Supply/Demand Analysis → Re-accumulation hoặc Distribution`. Không kết luận Re-accumulation chỉ vì giá vẫn nằm trên đáy của xu hướng tăng trước đó. Cần đánh giá đồng thời: Prior Trend, Structure, Supply Absorption, Demand Strength, Structural Integrity, Breakout Confirmation.

### Điều kiện nhận diện

| Tiêu chí | Điều kiện |
|---|---|
| Prior Trend | Trước đó đã có Markup rõ ràng, với cấu trúc HH–HL |
| Trading Range | Giá tạm dừng tăng và hình thành vùng đi ngang hoặc điều chỉnh |
| Support Structure | Giá duy trì được các vùng hỗ trợ quan trọng của xu hướng tăng trước đó |
| Supply Absorption | Áp lực bán dần suy yếu, các nhịp giảm không tạo được LL đáng kể |
| Demand Behavior | Các nhịp tăng có lực cầu tốt, trong khi các nhịp giảm thường có volume và spread suy giảm |
| Structural Continuity | Cấu trúc tăng dài hạn chưa bị phá vỡ |

### Các pha

Đây là cấu trúc tham chiếu. Không phải Re-accumulation nào cũng có đủ 5 pha hoặc tất cả sự kiện.

| Pha | Đặc điểm | Sự kiện thường gặp |
|---|---|---|
| A, Stopping Action | Tạm dừng xu hướng Markup trước đó | PS, BC, AR, ST |
| B, Building Cause | Hấp thụ cung trong Trading Range | ST, các nhịp kiểm tra cung |
| C, Testing Supply | Kiểm tra nguồn cung còn lại | Spring hoặc Test |
| D, Demand Dominance | Cầu tiếp tục chiếm ưu thế | SOS, LPS |
| E, Markup Resumption | Thoát Trading Range, tiếp tục tăng | Breakout, HH, HL |

### Phân biệt với Distribution

| Tiêu chí | Re-accumulation | Distribution |
|---|---|---|
| Xu hướng trước đó | Markup | Markup |
| Cán cân cung cầu | Cầu vẫn có ưu thế | Cung dần chiếm ưu thế |
| Các nhịp giảm | Cung suy yếu dần | Cung gia tăng |
| Các nhịp tăng | Cầu mạnh, dễ mở rộng | Cầu yếu, khó vượt kháng cự |
| Volume khi giảm | Thường giảm | Có thể tăng |
| Volume khi tăng | Có thể cải thiện | Có thể suy yếu |
| Cấu trúc giá | Giữ được hỗ trợ, HL | Có nguy cơ hình thành LH–LL |
| Kết quả | Tiếp tục Markup | Chuyển sang Markdown |

### Sự kiện không bắt buộc

PS, BC, AR, ST, Spring, LPS đều không bắt buộc. Không nhất thiết có SOS cổ điển, nhưng phải có bằng chứng cầu chiếm ưu thế. Một Re-accumulation có thể không có Spring: giá có thể hấp thụ cung ngay trong Trading Range rồi breakout trực tiếp.

### Ba mức

| Mức | Điều kiện | Trên biểu đồ |
|---|---|---|
| **Candidate** | Xu hướng trước đó là Markup; giá bắt đầu hình thành Trading Range hoặc điều chỉnh kéo dài; cấu trúc tăng dài hạn chưa bị phá vỡ | `Re-acc?` trong đoạn range |
| **Developing** | Trading Range được duy trì; có bằng chứng hấp thụ cung; các nhịp giảm suy yếu; lực cầu có dấu hiệu quay trở lại | `Re-accumulation?`, nhạt |
| **Confirmed** | Có bằng chứng cầu chiếm ưu thế; giá breakout khỏi Trading Range; breakout được duy trì và không nhanh chóng thất bại; xu hướng HH–HL tiếp tục được thiết lập | `Re-accumulation`, đậm |

### Cách đo trong hệ thống

Dùng chung `_range_verdicts` với Accumulation. Khác biệt:

| Yếu tố | Cách đo |
|---|---|
| Markup trước đó | Dùng chung với Distribution (`_prior_markup`): ngay từ đầu range, Markup đã đạt từ Developing trở lên (đã có HH–HL trước range); hoặc xu hướng tăng kéo dài: close đầu range cao hơn đáy 120 phiên trước từ 30%, và trước range không phải Markdown |
| Cấu trúc tăng chưa bị phá | Close không thấp hơn đáy swing gần nhất trước range (HL cuối của xu hướng) quá 0,5 ATR. Phá mức này thì bị bác bỏ |
| Áp lực bán suy yếu | Phiên giảm gần đây có volume hoặc biên độ không cao hơn phiên tăng trong range; 10 phiên gần nhất không close dưới support − 0,5 ATR |
| Nghiêng về | **Re-accumulation** khi đã Confirmed, hoặc volume phiên tăng cao hơn phiên giảm và chưa có đáy thấp hơn. **Distribution** khi phiên giảm có volume và biên độ cùng cao hơn phiên tăng, kèm đỉnh hoặc đáy thấp hơn. Còn lại là **chưa rõ** |

Developing và Confirmed dùng cùng các điều kiện với Accumulation (hấp thụ cung, cầu gia tăng, cầu chiếm ưu thế, breakout, giữ hỗ trợ hoặc có LPS, HH–HL). Bác bỏ khác như ở trên; sau Confirmed giống Accumulation.

Trên thẻ giai đoạn, Market State và cấu trúc hiện tách riêng. Khi đang trong Re-accumulation, Market State vẫn là Markup.

**Số đo khám phá (cache H8, 311 mã, từ 2018):** 2.481 trên 7.765 range được xét Re-accumulation (32,0%; placebo 2.812 trên 8.413, 33,4%). Trong đó 1.104 từng Confirmed (44,5%; placebo 1.076, 38,3%). Lợi suất 60 phiên sau Confirmed +8,5% (placebo +3,8%). Chưa kiểm soát xu hướng chung của thị trường và các ca trùng thời điểm, nên chưa phải bằng chứng về lợi thế. "Nghiêng về" được tính đến cuối thời gian xét, có thể gồm cả phần sau breakout, nên chưa đo được khả năng dự báo hướng thoát.

**Chưa làm:** pha A chưa dùng BC làm mốc mà bắt đầu từ đầu range. Markup sau Re-accumulation vẫn tính là đoạn mới nên có thể hiện Early Markup, chưa nối với xu hướng trước. Phân xử với Distribution: xem mục Distribution.

## Distribution

Distribution là quá trình thị trường chuyển từ trạng thái cầu chiếm ưu thế sang cung chiếm ưu thế, thường xuất hiện sau một xu hướng Markup. Trong giai đoạn này, các nhà đầu tư lớn có thể phân phối lượng cổ phiếu đang nắm giữ cho lực cầu còn lại, khiến giá hình thành Trading Range trước khi có khả năng chuyển sang Markdown.

**Điểm cốt lõi:** Distribution không đơn thuần là giá đi ngang ở vùng đỉnh. Nó phải thể hiện sự suy yếu của lực cầu, sự gia tăng tương đối của nguồn cung và quá trình chuyển giao quyền kiểm soát từ bên mua sang bên bán. Điều quan trọng nhất là phát hiện thời điểm cán cân cung cầu bắt đầu thay đổi, thay vì chờ đủ UTAD, SOW và LPSY.

Không dùng chuỗi cứng `PSY → BC → AR → ST → UTAD → SOW → LPSY → Markdown`. Thay vào đó đánh giá độc lập: Prior Trend, Trading Range, Supply Analysis, Demand Analysis, Structural Weakness, Breakdown Confirmation.

### Điều kiện nhận diện

| Tiêu chí | Điều kiện |
|---|---|
| Prior Trend | Trước đó đã có Markup hoặc xu hướng tăng kéo dài |
| Trading Range | Giá bắt đầu mất đà tăng và hình thành vùng giao dịch đi ngang |
| Buying Exhaustion | Các nhịp tăng khó tạo đỉnh mới, hoặc breakout không duy trì được |
| Supply Emergence | Xuất hiện các phiên giảm spread rộng, volume tăng, thể hiện áp lực bán |
| Weak Demand | Các nhịp hồi có spread hẹp, volume thấp, lực cầu suy yếu |
| Structural Weakness | Giá bắt đầu hình thành Lower High (LH), không giữ được các vùng hỗ trợ quan trọng |

### Các pha

Không phải mọi cấu trúc Distribution đều có đầy đủ năm pha hoặc các sự kiện dưới đây.

| Pha | Đặc điểm | Sự kiện thường gặp |
|---|---|---|
| A, Stopping Action | Dừng xu hướng tăng trước đó | PSY, BC, AR, ST |
| B, Building Cause | Phân phối cổ phiếu trong Trading Range | ST, các nhịp kiểm tra cung cầu |
| C, Testing Demand | Kiểm tra lực cầu còn lại | UT hoặc UTAD |
| D, Supply Dominance | Cung bắt đầu chiếm ưu thế | SOW, LPSY |
| E, Markdown | Giá thoát khỏi Trading Range theo hướng giảm | Breakdown, LH, LL |

### Các sự kiện

| Sự kiện | Định nghĩa | Bắt buộc? |
|---|---|---|
| PSY | Preliminary Supply: dấu hiệu nguồn cung bắt đầu xuất hiện | Không |
| BC | Buying Climax: cao trào mua, lực cầu đạt mức cực đoan | Không |
| AR | Automatic Reaction: phản ứng giảm tự nhiên sau BC | Không |
| ST | Secondary Test: kiểm tra lại vùng đỉnh và lực cầu | Không |
| UT | Upthrust: giá vượt kháng cự nhưng không duy trì được | Không |
| UTAD | Upthrust After Distribution: cú vượt đỉnh giả ở cuối quá trình phân phối | Không |
| SOW | Sign of Weakness: dấu hiệu suy yếu của giá và lực cầu | Không bắt buộc về hình thái |
| LPSY | Last Point of Supply: nhịp hồi yếu trước khi Markdown tiếp diễn | Không |

UTAD thuộc pha C trong cấu trúc Distribution cổ điển, không phải điều kiện bắt buộc để xác nhận Distribution. Tuy nhiên, để xác nhận Distribution, phải có bằng chứng về sự suy yếu của cầu và sự gia tăng tương đối của cung.

### Phân biệt với Re-accumulation

Đây là bài toán quan trọng nhất khi cổ phiếu đã trải qua Markup và bắt đầu hình thành Trading Range. Không dùng riêng volume để phân biệt; cần kết hợp với spread, vị trí đóng cửa, kết quả vận động giá và phản ứng ở các vùng hỗ trợ, kháng cự.

| Tiêu chí | Distribution | Re-accumulation |
|---|---|---|
| Xu hướng trước đó | Markup | Markup |
| Cán cân cung cầu | Cung dần chiếm ưu thế | Cầu duy trì ưu thế |
| Nhịp tăng | Yếu dần, khó vượt đỉnh | Có lực cầu tốt |
| Nhịp giảm | Spread mở rộng, volume tăng | Thường thu hẹp, volume giảm |
| Kiểm tra kháng cự | Thất bại, có thể xuất hiện UTAD | Có thể breakout thành công |
| Kiểm tra hỗ trợ | Dễ bị phá vỡ | Thường được bảo vệ |
| Cấu trúc giá | LH, sau đó có thể LL | HL được duy trì |
| Kết quả | Markdown | Tiếp tục Markup |

### Ba mức

| Mức | Điều kiện | Trên biểu đồ |
|---|---|---|
| **Candidate** | Xu hướng trước đó là Markup; giá bắt đầu hình thành Trading Range; đà tăng suy yếu; xuất hiện dấu hiệu cung gia tăng | `Dist?` trong đoạn range |
| **Developing** | Trading Range được duy trì; các nhịp tăng ngày càng yếu; xuất hiện dấu hiệu Supply Dominance; giá bắt đầu thất bại khi kiểm tra vùng kháng cự; có thể xuất hiện UT, UTAD hoặc SOW | `Distribution?`, nhạt |
| **Confirmed** | Có bằng chứng rõ ràng cung chiếm ưu thế; giá phá vỡ vùng hỗ trợ quan trọng; breakdown có sự xác nhận của volume và price spread; giá hình thành LH–LL hoặc tiếp tục duy trì cấu trúc giảm | `Distribution`, đậm |

**Distribution Confirmed không đồng nghĩa Markdown đã được xác nhận hoàn toàn.** Cần tiếp tục quan sát hành vi giá sau breakdown; Markdown có 5 điều kiện riêng ở trên.

### Cách đo trong hệ thống

Ngưỡng dùng chung với `DistributionConfig` và `RevisionConfig`, mã nguồn `_distribution_verdicts` trong `wyckoff/revision.py`. "Gần đây" là tối đa 20 phiên, không tính trước đầu range.

| Điều kiện | Cách đo |
|---|---|
| Xu hướng tăng trước đó | Cùng điều kiện với Re-accumulation (`_prior_markup`): đã có HH–HL ngay từ đầu range, hoặc close đầu range cao hơn đáy 120 phiên trước từ 30% và trước range không phải Markdown. Mốc 30% đổi được bằng `prior_up_min_rise` |
| Đà tăng suy yếu | Phiên tăng gần đây có volume hoặc biên độ không cao hơn 20 phiên trước range; 10 phiên gần nhất không close trên resistance + 0,5 ATR |
| Cung xuất hiện | Có phiên giảm volume từ 1,5 lần và biên độ từ 1,2 ATR trong range |
| Trading Range được duy trì | Range còn hoạt động |
| Nhịp tăng yếu dần | Phiên tăng gần đây có volume hoặc biên độ thấp hơn phiên giảm |
| Cung chiếm ưu thế | Phiên giảm gần đây có volume cao hơn và biên độ không thấp hơn phiên tăng |
| Thất bại ở kháng cự | Có UT, UTAD, hoặc đỉnh swing trong range thấp hơn đỉnh trước |
| Phá hỗ trợ | Range thoát xuống |
| Breakdown có volume và spread | Từ close đầu tiên dưới support: có phiên giảm volume từ 1,5 lần và biên độ từ 1,2 ATR, hoặc có SOW |
| LH–LL | Đỉnh swing trong range thấp hơn đỉnh trước, và close dưới support hoặc đáy swing thấp hơn đáy trước |

**Bác bỏ:** Re-accumulation của range xác nhận trước; breakout giữ được 10 phiên (không phải đỉnh giả); range mới xác nhận khi chưa đủ bằng chứng; sau Confirmed, trong 60 phiên, close vượt lại resistance.

**Phân xử với Re-accumulation trên cùng range:** mỗi range sau xu hướng tăng được xét song song hai giả thuyết. Mức cao hơn là cấu trúc đại diện; cùng mức thì theo hướng nghiêng; cùng mức mà chưa rõ thì ghi "chưa phân định". Re-accumulation mới ở mức Candidate, chưa có bằng chứng cung cầu, cũng ghi "chưa phân định": Market State chưa được xem là Markup. Distribution xác nhận trước thì Re-accumulation bị bác bỏ, và ngược lại. Thẻ giai đoạn liệt kê bằng chứng của cả hai.

**Dải pha:** range có đại diện là Distribution vẽ A từ BC nếu có (không thì đầu range), B từ khi TR xác nhận, C từ UT/UTAD, D từ SOW hoặc từ khi đạt Developing, E khi breakdown đã xác nhận.

**Redistribution:** chưa được định nghĩa. Range sau Markdown thoát xuống vẫn hiện `Re-dist` theo hướng thoát.

### Số đo khám phá của Distribution

Cache H8, 311 mã, từ 2018, `config/v3.yaml`. Đây là phân tích trên mẫu cũ, không phải kiểm định.

| Chỉ số | Thật | Placebo |
|---|---|---|
| Range được xét Distribution | 2.222 trên 7.765 (28,6%) | 2.664 trên 8.413 (31,7%) |
| Từng Confirmed | 883 (39,7%) | 1.051 (39,5%) |
| Lợi suất 60 phiên sau Confirmed | +3,0% | +3,5% |
| Đại diện là Distribution | 782 | 808 |
| Đại diện là Re-accumulation | 798 | 842 |

Lợi suất sau Confirmed vẫn dương và không thấp hơn placebo một cách rõ ràng, nên nhãn này chưa cho thấy giá giảm tiếp. Sau khi dùng chung điều kiện "Markup trước đó", số range đại diện của hai bên đã cân bằng (trước đó là 1.172 so với 105). Cấu trúc đại diện khớp với hướng thoát khoảng 99% trên cả dữ liệu thật và placebo, vì mức Confirmed của hai bên dựa vào chính hướng thoát: đây là phân loại sau khi đã biết kết quả, không phải dự báo.

Đã so hai cách đặt điều kiện: chỉ cần HH–HL (10,7% số range được xét, placebo 10,2%) và HH–HL hoặc tăng từ 30% (33,5%, placebo 35,5%). Chọn cách sau vì khớp với "Markup hoặc xu hướng tăng kéo dài" và xét được nhiều range hơn. Với cách này, Re-accumulation không còn đòi hỏi HH–HL trong mọi trường hợp.

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
- Chỉ khoảng 1/11 lần thoát xuống được xác nhận Markdown (9,1%; placebo 9,6%); 49,2% còn tiềm năng và 42,4% bị bác bỏ. Trước quy tắc mở lại, hai số cuối là 36,5% và 55,6%. Quy tắc này mở lại 20,6% số giả thuyết (761 trên 3.692; placebo 23,7%), nhưng chỉ 19 trong đó được xác nhận (placebo 36), quá ít để kết luận về lợi suất. Điều kiện chặn nhiều nhất là cung áp đảo cầu, tiếp đến là LH–LL và nhịp hồi yếu.
- Khi được xác nhận (đo trước quy tắc mở lại), giá trung vị đã dưới hỗ trợ 13,4%, và lợi suất 20 phiên sau đó khoảng +0,5%. Vì vậy nhãn xác nhận mô tả điều đã xảy ra, không phải tín hiệu.
- Tỷ lệ xác nhận trên dữ liệu thật và placebo gần bằng nhau, nên 5 điều kiện chưa cho thấy phân biệt được thị trường thật với dữ liệu xáo trộn.
