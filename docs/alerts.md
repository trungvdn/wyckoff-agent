# Cảnh báo sau phiên qua Telegram

Mỗi ngày giao dịch, job cập nhật giá, kiểm tra quy tắc bán trong danh mục và nhắn cho bạn **khi có thay đổi**. Tin nhắn chỉ mô tả theo quy tắc bạn đặt, không phải khuyến nghị.

Job chạy trên máy có nguồn dữ liệu và file danh mục. Máy tắt thì cảnh báo đến muộn, gửi khi máy bật lại.

## Thiết lập

1. Trong Telegram, nhắn cho `@BotFather` lệnh `/newbot` và làm theo hướng dẫn để nhận token.
2. Mở bot vừa tạo và gửi cho nó một tin bất kỳ.
3. Tạo file `.env` ở thư mục gốc dự án nếu chưa có, điền token:

   ```
   TELEGRAM_BOT_TOKEN=token-của-bạn
   ```

4. Lấy chat ID rồi thêm vào `.env` dòng `TELEGRAM_CHAT_ID=...`:

   ```bash
   python scripts/send_alerts.py --chat-id
   ```

   Đừng dùng phần số đầu của token: đó là ID của bot, Telegram sẽ báo lỗi 403 "the bot can't send messages to the bot".

5. Gửi thử:

   ```bash
   python scripts/send_alerts.py --test
   ```

`.env` đã có trong `.gitignore`. Không chia sẻ token: ai có token đều gửi được tin qua bot của bạn.

## Xem trước

In tin nhắn, không gửi và không lưu trạng thái:

```bash
python scripts/send_alerts.py --dry-run --no-update
```

Bỏ `--no-update` để tải giá mới trước khi xem.

## Chạy tự động trên Windows

Tạo tác vụ chạy 15:30 từ thứ Hai đến thứ Sáu (sửa đường dẫn `python.exe` nếu cần):

```bash
schtasks /Create /TN "Wyckoff Alerts" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:30 /TR "python \"C:\Backend Engineer\wyckoff_agent\scripts\send_alerts.py\""
```

Sau đó mở Task Scheduler, vào tab Settings của tác vụ và bật **Run task as soon as possible after a scheduled start is missed** để chạy bù khi máy bật lại. Nhật ký nằm ở `output/alerts.log`.

## Khi nào có tin nhắn

| Sự kiện | Báo khi |
|---|---|
| Đủ điều kiện chốt lãi, chốt lỗ | Mã chuyển sang đủ điều kiện |
| Gần đạt | Mã chuyển sang "Gần chốt lãi", "Gần chốt lỗ" |
| Đổi giai đoạn, pha | Khác với lần báo trước |
| Cần kiểm tra | Không cập nhật được giá, mã lỗi, hoặc dữ liệu của mã chậm hơn các mã khác |

- **Không báo lặp:** mã đang đủ điều kiện chỉ báo một lần. Thoát rồi quay lại thì báo lại.
- **Chạy bù:** so với trạng thái đã lưu, nên máy tắt vài ngày không bỏ sót.
- **Không có phiên mới:** cuối tuần, ngày nghỉ, chạy lại trong ngày đều không xét thay đổi. Lỗi dữ liệu vẫn được báo.
- **Không có gì mới:** không gửi gì. Lần chạy đầu luôn có một tin tóm tắt để biết job đã hoạt động.
- **Gửi lỗi:** không lưu trạng thái, lần chạy sau báo lại. Xem lỗi trong `output/alerts.log` vì lúc đó không nhắn được cho bạn.

Không muốn báo gần đạt: thêm `WYCKOFF_ALERT_NEAR=0` vào `.env`.

## Trên trang Danh mục

- **Nút chuông ở từng mã:** tắt thì lịch tự động và nút gửi đều bỏ qua mã đó, kể cả lỗi dữ liệu của mã. Mã mới mặc định bật. Bật lại thì từ phiên tiếp theo được coi như mã mới: báo trạng thái lúc đó nếu đang đủ điều kiện hoặc gần đạt, không báo những gì đã đổi trong lúc tắt.
- **Nút Gửi thông báo:** xem trước rồi mới gửi tình trạng hiện tại của các mã đang bật, ngay cả khi đã báo rồi. Gửi tay không đổi trạng thái đã lưu nên không ảnh hưởng lịch tự động. Dùng dữ liệu đang có, không tải giá mới.

## Dữ liệu gửi đi

Tin nhắn có mã, tên quy tắc, % và ngưỡng giá. **Không có** số lượng, giá vốn hay số tiền. Tin nhắn với bot Telegram không mã hóa đầu cuối; ngưỡng của quy tắc theo giá vốn (ví dụ "Lỗ quá 7%") vẫn cho phép suy ra giá vốn.

Trạng thái và lịch sử tin đã gửi nằm trong `data/portfolio.db`, chỉ ở trên máy này.
