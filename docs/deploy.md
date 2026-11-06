# Triển khai riêng tư trên VPS

Mục tiêu: xem dashboard từ mọi thiết bị khi máy cá nhân đang tắt, chỉ mình bạn đăng nhập được. Chưa dùng được để mở công khai (xem cuối file).

## Kiến trúc

```
Máy cá nhân (có vnstock)  --ssh, sau 15:00-->  VPS: data/cache/*.csv  (chỉ đọc)
                                                       |
Trình duyệt --> Cloudflare Access --> Tunnel --> web (Next.js) --> api (FastAPI) --> Anthropic
```

- **Server không cài vnstock.** PyPI đang để gói này ở trạng thái `quarantined`, không có file để cài, và chỉ mục của nhà cung cấp không có bản 5.2.1 cho Linux (kiểm tra ngày 06/11/2026).
- **Giá chỉ mới đến lần đồng bộ gần nhất.** Dashboard ghi rõ phiên cuối; nút "Phân tích lại" không tải giá mới. Mã chưa đồng bộ trả về 404.
- **Không có cổng nào mở ra Internet.** Chỉ `cloudflared` kết nối ra ngoài, và chỉ thấy service `web`.

## Cần chuẩn bị

- VPS Linux từ 1 GB RAM, có Docker và Docker Compose.
- Một tên miền đã đưa vào Cloudflare.
- SSH từ máy cá nhân tới VPS bằng khóa.

## 1. Đưa code lên VPS

Code phải được commit và push trước.

```bash
sudo mkdir -p /opt/wyckoff-agent && sudo chown "$USER" /opt/wyckoff-agent
git clone https://github.com/trungvdn/wyckoff-agent.git /opt/wyckoff-agent
cd /opt/wyckoff-agent
cp .env.example .env
chmod 600 .env
mkdir -p data/cache
```

Điền `ANTHROPIC_API_KEY` vào `.env`. Nên dùng một khóa riêng cho server và đặt hạn mức chi tiêu trong Anthropic Console.

## 2. Tạo Access trước, tunnel sau

Làm theo đúng thứ tự này để trang không bao giờ lộ ra khi chưa có đăng nhập.

1. Trong Cloudflare Zero Trust, vào **Access > Applications**, tạo **Self-hosted** cho tên miền con, ví dụ `wyckoff.ten-mien-cua-ban.com`.
2. Tạo policy **Allow** chỉ gồm đúng email của bạn.
3. Vào **Networks > Tunnels**, tạo tunnel loại Cloudflared, chép token vào `TUNNEL_TOKEN` trong `.env`.
4. Thêm **Public Hostname** cho tên miền con trên, trỏ tới `http://web:3000`.

## 3. Đồng bộ dữ liệu lần đầu

Chạy trên máy cá nhân, tại thư mục dự án:

```bash
python scripts/sync_cache.py --host user@server --no-update
```

Lệnh này đẩy toàn bộ `cache/` hiện có (khoảng 30 MB), không gọi vnstock.

## 4. Khởi động

```bash
docker compose --profile tunnel up -d --build
docker compose ps
```

## 5. Kiểm tra

1. Mở trang bằng cửa sổ ẩn danh: phải thấy màn hình đăng nhập của Cloudflare, **không** thấy dashboard. Nếu thấy dashboard, chạy `docker compose stop cloudflared` rồi sửa Access.
2. Đăng nhập, mở một mã, kiểm tra dòng "Dữ liệu đồng bộ đến phiên ...".
3. Thử một câu hỏi cho agent.

## Đồng bộ hằng ngày

```bash
python scripts/sync_cache.py --host user@server
```

Lệnh này chạy tuần tự mọi mã trong `cache/`; `--symbols HPG,FPT` chỉ chạy các mã bạn cần và luôn kèm chỉ số so sánh. Máy tắt vào ngày nào thì dữ liệu dừng ở lần đồng bộ trước.

Để tự chạy trên Windows, tạo tác vụ trong Task Scheduler vào khoảng 15:30 các ngày giao dịch. Bật "Run task as soon as possible after a scheduled start is missed" để chạy bù khi máy bật lại.

## Cập nhật phiên bản

```bash
cd /opt/wyckoff-agent
git pull
docker compose --profile tunnel up -d --build
```

Kết quả diễn giải LLM nằm trong volume `llm_output`, được giữ lại sau khi build lại. Đổi `NEXT_PUBLIC_DEFAULT_SYMBOL` thì cũng cần `--build`.

Đổi dependency của API: sửa `requirements-prod.in` rồi sinh lại file khóa.

```bash
docker run --rm -v "$PWD/requirements-prod.in:/tmp/r.in:ro" python:3.12-slim sh -c 'pip install -q -r /tmp/r.in >&2 && pip freeze' > requirements-prod.txt
```

## Chạy thử trên máy phát triển

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Mở `http://127.0.0.1:3000`. Bản này đọc `./cache`, tắt LLM và không dùng tunnel.

## Xử lý sự cố

| Hiện tượng | Kiểm tra |
|---|---|
| Lỗi 502 hoặc không vào được trang | `docker compose ps`, `docker compose logs web api cloudflared` |
| Mã báo chưa có dữ liệu | Đồng bộ lại mã đó |
| Mất bối cảnh thị trường | `data/cache/VNINDEX_1D.csv` có tồn tại không |
| Agent trả lời theo mẫu | `/api/health` có `llm: true` không, `ANTHROPIC_API_KEY` trong `.env` |
| Lỗi 524 khi gọi LLM | Cloudflare ngắt request quá khoảng 100 giây; bấm thử lại |

## Giới hạn

- **Chưa mở công khai được.** API không có xác thực và giới hạn tần suất, nên Cloudflare Access là lớp bảo vệ duy nhất (`docs/roadmap.md`, mục #10).
- **Giấy phép vnstock.** Bản cập nhật 11/2026 (dự kiến hiệu lực 30/11/2026) không cho phân phối lại dữ liệu của nguồn và giới hạn bản Cộng đồng ở mục đích cá nhân, học tập, nghiên cứu. Đây là một lý do nữa để giữ trang riêng tư.
- **Chỉ có một bản dữ liệu.** `data/cache` tạo lại được từ máy cá nhân, nên không cần sao lưu trên server.
