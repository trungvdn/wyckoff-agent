# Roadmap

Cập nhật: 07/11/2026.

Mỗi tính năng một dòng; thiết kế và kết quả để ở file riêng rồi dẫn link. PR hoàn thành tính năng nào thì chuyển dòng đó sang mục Đã xong, ghi ngày hoàn thành và link PR.

Roadmap bám theo bốn việc hằng ngày: xem danh mục, kiểm tra điều kiện bán, tìm mã tiềm năng, xem thị trường chung.

Công sức (S, M, L) là ước lượng sơ bộ, chưa thiết kế chi tiết. Số # là mã cố định của tính năng, không phải thứ tự làm.

## Đang làm

- [ ] Quyết định nguồn dữ liệu lâu dài: `vnstock` đang bị PyPI cách ly (`quarantined`), chưa rõ lý do.

## Tạm hoãn

- [ ] Triển khai riêng tư lên VPS ([hướng dẫn](deploy.md)): bộ deploy đã xong, tạm dừng theo quyết định ngày 07/11/2026.

## Đã xong

| # | Tính năng | Nội dung | Hoàn thành | PR |
|---|---|---|---|---|
| 16 | Trang thị trường | `/thi-truong`: xu hướng VN-Index, điều kiện của xu hướng và điều kiện đảo chiều, lợi suất 20/60/120 phiên, mức giảm so với đỉnh, biểu đồ có khối lượng; menu trái dùng chung ([spec](handoff-dashboard.md#trang-thị-trường)) | 07/11/2026 | [#7](https://github.com/trungvdn/wyckoff-agent/pull/7) |
| 12 | Danh mục nắm giữ | `/danh-muc`: thêm, sửa, xóa mã; lãi/lỗ, giai đoạn, pha, thay đổi so với hôm qua (gồm #2), khoảng cách tới các mức giá; lưu bằng SQLite cục bộ ([spec](handoff-dashboard.md#danh-mục-nắm-giữ)) | 07/11/2026 | [#8](https://github.com/trungvdn/wyckoff-agent/pull/8) |
| 13 | Quy tắc bán do người dùng đặt | Quy tắc theo giá vốn, mức giá, đường trung bình và cấu trúc Wyckoff; tách chốt lãi và chốt lỗ, ghi rõ đạt, gần đạt hay chưa kèm con số, có kiểu "Đạt là đủ" ([spec](handoff-dashboard.md#quy-tắc-bán)). Khối "Thay đổi so với hôm qua" đã bỏ khỏi trang, API vẫn trả `changes` cho #17 và #6 | 07/11/2026 | [#9](https://github.com/trungvdn/wyckoff-agent/pull/9) |
| 6 | Cảnh báo Telegram | Job sau phiên báo khi đủ điều kiện chốt lãi, chốt lỗ, gần đạt, đổi giai đoạn hoặc pha; không báo lặp, chạy bù; nút chuông bật/tắt theo mã và nút Gửi thông báo trên trang danh mục ([hướng dẫn](alerts.md)). Chưa làm email | 07/11/2026 | [#10](https://github.com/trungvdn/wyckoff-agent/pull/10) |

## Tiếp theo

Xếp theo thứ tự làm.

| # | Tính năng | Nội dung | Công sức | Phụ thuộc |
|---|---|---|---|---|
| 14 | Kiểm thử quy tắc bán | So sánh bán theo quy tắc với tiếp tục giữ trên dữ liệu lịch sử, dùng lại event study | M | #13 |
| 1 | Trình quét toàn thị trường | Job sau 15:00 lưu trạng thái mọi mã; trang bảng lọc theo giai đoạn, pha, mức tin cậy, RS, khoảng cách tới mức xác nhận/vô hiệu | M–L | Nơi lưu lịch sử trạng thái |
| 15 | Bộ lọc đã lưu và kiểm thử | Lưu tiêu chí, lọc thanh khoản, bỏ mã đang giữ; mỗi bộ lọc có kết quả lịch sử so với nền | M | #1, #12 |
| 17 | Trang "Hôm nay" | Trang chủ gom thị trường, quy tắc bán vừa đạt, thay đổi trong danh mục, mã mới khớp bộ lọc | S–M | #12, #13, #15, #16 |
| 7 | Độ rộng thị trường và ngành | Mở rộng #16: tỷ lệ mã ở từng giai đoạn, RS theo ngành | M | #1, #16 |
| 5 | Tua lại theo thời gian | Xem hệ thống nói gì tại một ngày bất kỳ, so với nhãn đã đánh giá lại | M | – |
| 8 | Agent hội thoại nhiều lượt | Nhớ ngữ cảnh, so sánh được nhiều mã | M | – |

## Chạy song song

Mọi tín hiệu ở trên đều dựa vào range, nên hai việc này không chờ các tính năng trên.

| # | Tính năng | Nội dung | Công sức | Phụ thuộc |
|---|---|---|---|---|
| 3 | Khung kiểm định chuẩn | Gom `scripts/h*_eval.py` thành một khung, mặc định có placebo và kiểm soát vị trí giá | M | – |
| 4 | H9: làm lại bộ phát hiện range | Đăng ký trước tiêu chí, thử định nghĩa mới so với placebo (lý do: [điều tra H8](h8-investigation.md)) | L | #3 |

## Để sau

| # | Tính năng | Nội dung | Công sức | Điều kiện |
|---|---|---|---|---|
| 9 | Mô phỏng chiến lược | Danh mục có T+2, giá trần/sàn, thanh khoản; rổ mã đúng theo từng thời điểm | L | Sau H9 |
| 10 | Xác thực và giới hạn tần suất | Đăng nhập, giới hạn `/api/ask`, CSP | M | Bắt buộc trước khi mở ra Internet, nhất là khi đã có dữ liệu danh mục |
| 11 | Dữ liệu dòng tiền | Giao dịch khối ngoại và tự doanh | M | Chưa kiểm tra vnstock có cung cấp không |

## Chưa nên làm

- **Khung 15 phút và giờ:** cần nguồn dữ liệu trong ngày và hiệu chỉnh lại ngưỡng, trong khi range ở khung ngày còn chưa vượt được placebo.

## Nguyên tắc

- **Quyết định bán thuộc về người dùng:** hệ thống chỉ báo quy tắc đã đạt hay chưa. Mức vô hiệu chưa phải tín hiệu bán đã kiểm chứng, vì sau khi thủng mức v1 hoặc support, giá vẫn tăng hơn chỉ số (README).
- **"Tiềm năng" do bộ lọc của người dùng định nghĩa:** lọc theo trạng thái, không xếp hạng kiểu "mã tốt nhất". Pha C, pha D và nhãn đã chốt chỉ nên đọc là mô tả.
- **Dữ liệu danh mục là thông tin riêng:** lưu cục bộ, đưa vào `.gitignore`.
- **Pha của VN-Index chỉ để tham khảo:** ngưỡng detector chưa hiệu chỉnh cho chỉ số, nên trang thị trường hiện xu hướng trước.
- **Giả thuyết mới phải vượt placebo và vị trí giá**, theo [điều tra H8](h8-investigation.md).
