# Lọc cổ phiếu

Trang `/loc-co-phieu` cho lọc mọi cổ phiếu trong `cache/` theo trạng thái Wyckoff, xu hướng và thanh khoản. Bản mẫu đã duyệt: canvas "Lọc cổ phiếu".

Kết quả chỉ mô tả trạng thái theo điều kiện bạn đặt. Trang không xếp hạng và không khuyến nghị: bộ phát hiện range chưa vượt được kiểm định placebo ([H8](h8-investigation.md)).

## Chạy quét

Trang đọc kết quả quét đã lưu, không phân tích lại khi mở trang. Có hai cách tạo kết quả:

```bash
python scripts/scan_market.py                    # cập nhật giá rồi quét mọi cổ phiếu trong cache/
python scripts/scan_market.py --no-update        # quét trên dữ liệu đang có
python scripts/scan_market.py --symbols HPG,FPT  # chỉ vài mã
```

Hoặc bấm **Quét lại** trên trang. Server chạy lượt quét nền và hiện tiến độ, có nút Dừng. Trong lúc quét, bảng cũ vẫn hiện. Dừng giữa chừng thì không lưu gì.

- Danh sách mã: mọi file `*_1D.csv` trong `cache/`, trừ các chỉ số (VNINDEX, HNXINDEX, UPCOMINDEX, VNSMALLCAP).
- Cập nhật giá: tăng dần từng mã, giống `sync_cache.py`. Hết hạn mức theo phút thì chờ rồi thử lại. Mã không cập nhật được vẫn được phân tích trên dữ liệu cũ và được ghi chú. Server chạy `WYCKOFF_OFFLINE` thì không tải giá.
- VN-Index được cập nhật và phân tích một lần cho cả lượt. Đo ngày 07/11/2026: 316 mã mất 99 giây khi không tải giá, khoảng 2 phút khi có tải giá.
- Mỗi phiên lưu một lượt; quét lại cùng phiên thì thay lượt cũ. Lịch sử giữ trong `data/scanner.db` (`WYCKOFF_SCANNER_DB`, đã có trong `.gitignore`). Chưa đặt lịch chạy tự động.

## Điều kiện lọc

Mọi điều kiện kết hợp bằng "và". Nhóm chọn nhiều giá trị (giai đoạn, trạng thái, pha) để trống nghĩa là không lọc.

| Nhóm | Điều kiện | Cách tính |
|---|---|---|
| Cấu trúc Wyckoff | Giai đoạn | Đọc từ tên giai đoạn trên trang cổ phiếu. "Initial Accumulation" tính là Accumulation. Tên có "hoặc" (nhiều khả năng) và "Chưa có xu hướng rõ" xếp vào Chưa rõ |
| | Trạng thái | Đã xác nhận, đang hình thành, tiềm năng, theo đuôi tên giai đoạn |
| | Pha | Pha A–E hoặc Vô hiệu của lớp đánh giá lại |
| | Tin cậy tối thiểu | Mức của điểm tin cậy. "Không áp dụng" chỉ khớp khi chọn Bất kỳ |
| Sự kiện, thay đổi | Có sự kiện trong N phiên | Sự kiện trong danh sách sự kiện của mã (bỏ sự kiện đã bị bác bỏ), tính theo ngày xảy ra |
| | Vừa đổi pha trong N phiên | Số phiên từ ngày bắt đầu pha hiện tại |
| Mức giá, xu hướng | Tới mức xác nhận | % từ giá tới mức xác nhận gần nhất ở trên giá |
| | Cách mức vô hiệu | % mức vô hiệu cao nhất nằm dưới giá. Âm khi giá đã thủng mức đó |
| | So với SMA50 | % giá so với SMA50 |
| | RS 60 phiên | Thay đổi của tỷ số giá cổ phiếu / VN-Index trong 60 phiên, cùng định nghĩa với trang cổ phiếu |
| Thanh khoản | GTGD TB20 | Trung bình 20 phiên của giá đóng cửa × khối lượng, tỷ đồng |
| | Giá | Giá đóng cửa, nghìn đồng |
| | KL phiên so TB20 | Khối lượng phiên cuối so với trung bình |
| Danh mục | Bỏ mã đang giữ | Theo `data/portfolio.db` lúc mở trang |

Mỗi dòng còn có lợi suất 20/60 phiên, RS 20 phiên, so SMA200, EMA ngắn trên EMA dài, vị trí trong range, mục tiêu P&F và khoảng cách tới đỉnh 52 tuần. Các số này có trong API nhưng chưa có điều kiện lọc riêng.

## Giao diện

| Thành phần | Hành vi |
|---|---|
| Bộ lọc đã lưu | Chọn để nạp điều kiện. Mở trang thì tự chọn bộ lọc đầu tiên theo tên. Nút thùng rác xóa bộ lọc, có bước xác nhận. Không có bộ lọc mẫu |
| Lưu bộ lọc | Đặt tên (tối đa 60 ký tự, không trùng). Khi đang chọn một bộ lọc thì có tùy chọn ghi đè |
| Kết quả | Mặc định xếp theo GTGD giảm dần; bấm tiêu đề cột để đổi. Điện thoại: thẻ, chọn cách xếp bằng ô chọn |
| Dữ liệu cũ | Mã có phiên cuối cũ hơn phiên quét ghi "dữ liệu đến dd/mm/yyyy" màu hổ phách, cuối bảng ghi tổng số mã như vậy |
| Màn hình hẹp hơn 1081px | Bảng điều kiện mở dạng hộp thoại (toàn màn hình trên điện thoại), nút "Xem N mã" ở đáy |

## API

| Method | Path | Trả về |
|---|---|---|
| GET | `/api/scan?as_of=` | Lượt quét (mặc định mới nhất): `rows` có cờ `held`, `failed`, `sessions`, `held`, `job`, `notices` |
| POST | `/api/scan` | `{confirm: true}`: bắt đầu quét nền; 409 nếu đang có lượt chạy |
| GET | `/api/scan/status` | Tiến độ: `running`, `done`, `total`, `current`, `waiting`, `eta_s`, `failed`, `stopped`, `error` |
| POST | `/api/scan/stop` | Dừng lượt đang chạy; 409 nếu không có |
| GET, POST | `/api/filters` | Danh sách bộ lọc; thêm `{name, filters}` (409 nếu trùng tên) |
| PUT, DELETE | `/api/filters/{id}` | Sửa hoặc xóa |

Mã nguồn: `wyckoff/scanner.py` (dòng quét, lưu trữ, job), `scan_runner` trong `wyckoff/web/store.py`, `web/lib/screener.ts` (điều kiện, lọc, sắp xếp), `web/components/screener/`.

## Chưa làm

- Kiểm thử bộ lọc: kết quả lịch sử của mỗi bộ lọc so với nền (#15).
- Lọc theo lịch sử nhiều phiên (ví dụ "mới khớp bộ lọc hôm nay"), dùng cho trang "Hôm nay" (#17).
- Đặt lịch quét tự động.
