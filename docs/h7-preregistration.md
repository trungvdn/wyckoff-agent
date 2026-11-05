# Giả thuyết H7 – giai đoạn và sức mạnh cung cầu trong thang tin cậy (chốt trước khi chạy, 04/11/2026)

Nguồn: kiến trúc phân loại 5 tầng do người dùng đưa ra (Market Stage, Structure Type, Phase, Events, Evidence), đã có ở dạng chỉ ghi nhận:
`wyckoff/stages.py`, `wyckoff/strength.py` (commit `c09e967`). Quy tắc của H7a, H7b do Claude đề xuất từ lý thuyết Wyckoff; người dùng yêu cầu chốt
(04/11/2026). Chốt trước khi chạy backtest; **chưa xem kết quả lợi suất nào của giai đoạn, loại cấu trúc hay sức mạnh cung cầu**.

Thống kê đã xem trước khi chốt (chỉ cấu trúc, không có lợi suất; 311 mã, từ 2018):

- Hướng thoát range gần như 50/50: thoát lên 50,6% sau nhịp giảm, 52,6% trung tính, 53,7% sau nhịp tăng; 51,5% khi range trước thoát xuống, 53,4% khi range trước thoát lên.
- Nhãn range đã chốt: Re-accumulation 1.878, Initial Distribution 1.624, Initial Accumulation 1.579, Re-distribution 1.506; không rõ xu hướng trước đó 56; đang mở 151.
- Tỷ lệ phiên: Transition / Uncertain 53,3%, Trending Up 24,9%, Trending Down 21,8%.
- Mức sức mạnh (lấy mẫu mỗi 20 phiên): Markup mạnh 33,6%, trung bình 52,2%, yếu đi 14,2%; Markdown mạnh 27,4%, trung bình 49,9%, yếu đi 22,6%.

Thứ tự: thống kê hướng thoát range được xem **trước** khi đặt quy tắc giai đoạn (và là lý do chỉ chốt nhãn khi range thoát). Tỷ lệ phiên và số nhãn range xem sau khi đặt quy tắc giai đoạn;
phân bố mức xem sau khi đặt ngưỡng sức mạnh. Không ngưỡng nào được chỉnh sau khi xem. Lần so hồi quy `study_symbol` trên 10 mã chỉ so hash, không in lợi suất.

## Quy tắc đã đóng băng (không đổi trong H7)

**Giai đoạn** (`StageConfig`): SMA50, độ dốc so với `slope_bars` = 20 phiên; có xu hướng khi `enter_bars` = 5 close liên tiếp đúng phía SMA đang dốc hoặc khi range thoát;
mất xu hướng khi `exit_bars` = 5 close liên tiếp sai phía SMA; tìm xu hướng trước range trong `prior_max_bars` = 60 phiên.

**Sức mạnh cung cầu** (`StrengthConfig`): ba tín hiệu, mỗi tín hiệu −1 / 0 / +1; tổng ≥ 2 mạnh, ≤ −1 yếu đi, còn lại trung bình.

| Tín hiệu | +1 | −1 |
|---|---|---|
| Khối lượng 20 phiên | Phiên cùng chiều xu hướng chiếm ≥ 55% | ≤ 45% |
| Đỉnh đáy (hai đỉnh, hai đáy đã xác nhận trong 60 phiên) | Cả đỉnh và đáy đi đúng chiều | Cả đỉnh và đáy đi ngược chiều |
| Nhịp điều chỉnh / nhịp hồi (cách cực trị ≥ 2 phiên và ≥ 0,5 ATR) | < 38,2% nhịp trước đó và volume < 1,0x TB20 | ≥ 61,8%, hoặc volume ≥ 1,3x TB20, hoặc close sai phía SMA50 |

## Giả thuyết

Cả hai chỉ đổi điểm tin cậy; sự kiện, pha, ngưỡng mức (≤ 0 thấp, 1–2 trung bình, ≥ 3 cao) giữ nguyên. Pha `invalid` vẫn "không áp dụng". Tính point-in-time tại phiên tín hiệu.

**H7a – thêm yếu tố sức mạnh cung cầu** (`config/h7a.yaml`, mã yếu tố `stagestrength`). Cầu mạnh cộng điểm cho cấu trúc tích lũy đang chấm; cung mạnh hoặc cầu yếu đi trừ điểm:

| Giai đoạn tại phiên t | Mức | Điểm |
|---|---|---|
| Markup | mạnh | +1 |
| Markup | trung bình | 0 |
| Markup | yếu đi | −1 |
| Markdown | mạnh | −1 |
| Markdown | trung bình | 0 |
| Markdown | yếu đi | 0 (cung yếu đi chưa phải cầu đã quay lại) |
| Trong range, hoặc chưa có xu hướng | – | 0 |

**H7b – thay nhãn đà giá bằng xu hướng trước range** (`config/h7b.yaml`, mã yếu tố `priorstage`). Bỏ điểm của `rangectx` (nhãn đà giá 120 phiên: sau nhịp giảm −1), dòng yếu tố vẫn ghi với 0 điểm.
Lấy `prior_stage` của range thuộc cấu trúc đang chấm, kể cả khi range đã kết thúc: Markdown −1, Markup 0, không rõ hoặc cấu trúc không có range 0.
Số điểm cố ý giống `rangectx` (`after_decline` −1, `after_rise` 0) để chỉ kiểm tra cách xác định xu hướng, không đổi trọng số.

Mặc định tắt cả hai. Cấu hình và mã yếu tố được thêm khi chạy, không làm đổi kết quả đối chứng.

## Cách đo

- Mẫu: mọi mã trong `cache/` có ≥ 300 phiên, trừ chỉ số; từ 01/01/2018; `study_symbol` point-in-time (`scripts/parallel_study.py`).
- **Đóng băng dữ liệu**: chép `cache/` sang một thư mục riêng và chạy mọi cấu hình trên bản chép (`--cache-dir`), vì API tự cập nhật cache khi có người mở mã. Ghi lại ngày dữ liệu cuối.
- Đối chứng: cấu hình mặc định tại commit `c09e967` (v2 + GT2 + SOS reclaim + vòng đời event; `sos.confirm_mode: same_bar`; `utad.mode: v2`), **chạy lại** trên bản cache đó, không dùng lại kết quả H5 / H6.
- Thước đo: lợi suất vượt VNINDEX điều chỉnh beta (`bexcess`), vào lệnh open phiên sau phiên xác nhận, chi phí 0,3%.

## Tiêu chí chấp nhận

`evaluate_hypothesis` như GT1, GT2, H4, H5, H6; chấm riêng từng giả thuyết, mỗi giả thuyết cần **cả 5**:

1. Thang tin cậy tăng đều thấp < trung bình < cao (20 phiên).
2. Mức cao có CI 90% > 0.
3. Chênh lệch cao − thấp lớn hơn đối chứng.
4. Giai đoạn 2023–nay: TB 60 phiên của mức cao lớn hơn đối chứng.
5. Bootstrap theo mã ghép cặp: P(chênh lệch > đối chứng) ≥ 0,80.

Chấp nhận thì đề xuất bật mặc định, **chỉ bật sau khi người dùng duyệt**; không chấp nhận thì để tắt và ghi kết quả. Không chỉnh tham số nào sau khi xem kết quả;
muốn thử ngưỡng khác phải đăng ký giả thuyết mới. Nếu cả hai cùng đạt thì không tự gộp: gộp là một giả thuyết mới.

## Tham khảo (không dùng để chấm)

`bexcess` 20 / 60 phiên, toàn kỳ và tách 2018–2022 / 2023–nay, so với nền cùng giai đoạn:

- Mọi phiên theo loại cấu trúc như biết tại phiên đó: Trending Up, Trending Down, Transition / Uncertain trong range, Transition / Uncertain ngoài range.
- Tại phiên chốt nhãn (`resolved_idx`), theo 4 loại: Re-accumulation, Initial Distribution, Initial Accumulation, Re-distribution. Đo từ phiên chốt nên không nhìn trước.
- Trong Markup / Markdown, theo mức sức mạnh và theo từng tín hiệu.
- Số tín hiệu đổi mức tin cậy so với đối chứng, phân bố mức.

Kết quả tham khảo chỉ dùng để đề xuất giả thuyết sau, không dùng để đổi nhãn trên dashboard trong H7.

## Hạn chế biết trước

- **Không phải mẫu mới**: 311 mã đã xem ở các lần kiểm tra trước; danh sách hiện tại có thiên lệch sống sót; tín hiệu chồng lấn.
- **H7b không hoàn toàn mù**: hướng −1 lấy từ kết quả backtest trước đó (range sau nhịp giảm kém nhất, `after_decline`), và `prior_stage` tương quan với nhãn đà giá. H7a không có kết quả lợi suất nào đi trước về chính yếu tố này, nhưng dùng các đại lượng (khối lượng, swing) đã có trong các lần đo.
- **Kiểm định nhiều lần**: H7a, H7b là hai giả thuyết nữa trên dữ liệu đã dùng cho H4a, H4b, H5a, H5b, H6 (GT1, GT2 dùng VNSmallCap, cũng nằm trong cache), không hiệu chỉnh cho số lần thử; đạt tiêu chí có thể do ngẫu nhiên.
- **Lệch sơ đồ**: thang tin cậy chấm cấu trúc tích lũy; chưa có detector BC / SOW / LPSY và sơ đồ pha phân phối (Bước 2, 3), nên H7 không kiểm tra được phía phân phối, chỉ kiểm tra giai đoạn có giúp chấm cấu trúc tích lũy hay không.
- **Yếu tố chồng lấn**: H7a có thể trùng một phần với `mkttrend`, `relstrength`, `lps`, `sos`; không gộp nhóm để giữ quy tắc đơn giản, có thể làm mức "cao" nhiều hơn.
- **Phạm vi tín hiệu**: tín hiệu là các sự kiện và lần mở pha nên phần lớn các phiên Markup / Markdown không có tín hiệu; H7a chủ yếu tác động lên pha A và E. Mô tả cung cầu trên dashboard không được H7 kiểm định ở mọi phiên, trừ phần tham khảo.

## Kết quả (04/11/2026): KHÔNG CHẤP NHẬN cả H7a và H7b, giữ `stage_strength: false`, `prior_stage: false`

Mẫu 311 mã, point-in-time, trên bản chép cache đóng băng (`output/h7/cache`, đa số mã có dữ liệu đến 03/11 hoặc 04/11/2026). Cấu hình mặc định trùng commit `53c93b5` trên bản cache này
(sự kiện, range, pha, payload trên 311 mã; `study_symbol` trên 10 mã). Đối chứng chạy lại cho đúng các số của H6. Bảng đầy đủ: `output/h7/report.md`
(`scripts/parallel_study.py`, `scripts/h7_reference.py`, `scripts/h7_eval.py`). Không chỉnh tham số nào sau khi xem kết quả.

| 20 phiên, bexcess % | Đối chứng | H7a | H7b |
|---|---|---|---|
| Thấp | −0,26 | −0,28 | −0,26 |
| Trung bình | +0,48 | +0,53 | +0,59 |
| Cao [CI 90%] | +1,19 [+0,79; +1,63] | +1,02 [+0,63; +1,39] | +1,19 [+0,76; +1,67] |
| Cao − thấp [CI 90%] | +1,46 [+1,04; +1,91] | +1,30 [+0,88; +1,70] | +1,45 [+0,98; +1,94] |
| Cao, 60 phiên, 2023–nay | −1,51 | −1,35 | −1,42 |
| P(chênh lệch > đối chứng) | – | 0,07 | 0,53 |
| Tín hiệu đổi mức | – | 1.128 / 29.454 | 1.924 / 29.454 |

- **H7a**: đạt tiêu chí 1, 2, 4; **trượt 3 và 5**. Yếu tố này làm thang tách kém đi: mức cao đông hơn nhưng lợi suất thấp hơn. P = 0,07 nghĩa là gần như chắc chắn không tốt hơn đối chứng.
- **H7b**: đạt tiêu chí 1, 2, 4; **trượt 3 và 5** (+1,45 so với +1,46, P = 0,53). Trung tính: đổi từ nhãn đà giá sang xu hướng trước range gần như không thay đổi gì, nên hai cách xác định thay thế được cho nhau về điểm tin cậy.
- Tiêu chí 4 (2023–nay) lần đầu được cả hai giả thuyết cải thiện, nhưng mức cao vẫn âm, và theo quy tắc chốt trước thì một tiêu chí không đủ.

Tham khảo (không dùng để chấm; TB chênh so với nền cùng giai đoạn, không có CI, các phiên chồng lấn mạnh nên không phải ước lượng độc lập):

| Chênh so với nền, % | 20 phiên | 60 phiên | 20 phiên 2018–2022 / 2023–nay | 60 phiên 2018–2022 / 2023–nay |
|---|---|---|---|---|
| Trending Up (mọi phiên) | +0,65 | +1,58 | +0,72 / +0,45 | +1,84 / +0,99 |
| Trending Down (mọi phiên) | −0,54 | −1,12 | −0,53 / −0,65 | −0,94 / −1,78 |
| Transition, trong range | −0,08 | −0,12 | −0,14 / +0,09 | −0,20 / +0,32 |
| Transition, ngoài range | −0,08 | −1,19 | −0,11 / −0,20 | −1,93 / −0,54 |
| Re-accumulation (phiên chốt, n = 1.875) | +1,24 | +3,20 | +1,40 / +0,86 | +4,53 / +0,76 |
| Initial Accumulation (n = 1.561) | +0,32 | −0,02 | −0,08 / +0,85 | +0,32 / +0,20 |
| Initial Distribution (n = 1.607) | −0,30 | −1,33 | −0,75 / +0,24 | −2,00 / −0,45 |
| Re-distribution (n = 1.487) | −0,93 | −2,11 | −1,01 / −0,80 | −1,57 / −2,76 |
| Markup · mạnh / trung bình / yếu đi | +0,65 / +0,74 / +0,30 | +2,08 / +1,58 / +0,28 | | |
| Markdown · mạnh / trung bình / yếu đi | −0,36 / −0,63 / −0,59 | −0,97 / −1,25 / −1,03 | | |

Đọc kết quả:

- **Loại cấu trúc có chênh cùng chiều ở cả hai giai đoạn**: Trending Up dương, Trending Down âm; Re-accumulation dương, Re-distribution âm ở cả 20 và 60 phiên. Nhưng đây có thể chỉ là hiệu ứng quán tính giá đã biết, mẫu có thiên lệch sống sót, và số liệu chưa có CI. Muốn dùng phải đăng ký giả thuyết mới.
- **Mức sức mạnh cung cầu chỉ tách được một phần**: trong Markup, "yếu đi" kém rõ ở 60 phiên. Trong Markdown, "cung mạnh" **không** kém hơn "cung yếu đi", trái với kỳ vọng. Một số tín hiệu đơn lẻ cũng trái lý thuyết (Markup: đỉnh đáy −1 cao hơn +1 ở 20 phiên), nên chỉ nên xem mức này là mô tả.
- Nhãn đã chốt và mức cung cầu trên dashboard giữ nguyên, ghi rõ là mô tả, không phải dự báo.
