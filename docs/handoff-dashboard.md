# Handoff Spec: Wyckoff Agent – Dashboard phân tích một mã

Thiết kế gốc: canvas "Wyckoff Agent Dashboard" (artboard 1440px + 390px).
Mã nguồn: API `wyckoff/web/` (FastAPI, `python serve.py`); giao diện `web/` (Next.js App Router + Tailwind, `npm run dev`).

### Cấu trúc giao diện Next.js

| Thành phần | File | Loại |
|---|---|---|
| Layout gốc: font, Sidebar, Header, Footer, StatusProvider | `app/layout.tsx` | Server |
| Sidebar (skip link, logo, menu Thị trường / Cổ phiếu) | `components/layout/Sidebar.tsx` | Client: đọc đường dẫn |
| Header (ô mã và khung thời gian ở trang cổ phiếu, pill trạng thái) | `components/layout/Header.tsx` | Client: đọc mã / khung từ URL |
| Footer (dòng miễn trừ) | `components/layout/Footer.tsx` | Server |
| Card, CardHeader, Eyebrow / Button / Skeleton | `components/ui/*` | Dùng chung |
| Dashboard (lưới 2/3 – 1/3, hàng dưới) | `components/dashboard/Dashboard.tsx` | Server |
| PriceChart (Lightweight Charts: zoom, kéo, nút khoảng thời gian, bàn phím); chartPrimitives (vùng giao dịch, nhãn sự kiện) | `components/dashboard/PriceChart.tsx` | Client |
| StagePhaseCard, EventsCard, Banner | `components/dashboard/*` | Server |
| ScenarioCard, AskAgent (dùng chung diễn giải qua ExplanationContext) | `components/dashboard/*` | Client |
| Trang mã: kiểm tra mã, URL chuẩn, gọi API | `app/co-phieu/[symbol]/page.tsx` | Server, động |
| Đang tải / lỗi / 404 | `loading.tsx`, `error.tsx`, `app/not-found.tsx` | – |

Token màu, font và breakpoint `wide` (> 1080px) khai báo trong `app/globals.css` (`@theme`); tên lớp Tailwind theo token:
`bg-surface`, `text-muted`, `border-line`...

## Overview

Nhà đầu tư cá nhân nhập một mã, xem trên một màn hình: biểu đồ nến kèm vùng giao dịch và sự kiện Wyckoff, pha hiện tại,
bằng chứng từng sự kiện, kịch bản xác nhận / vô hiệu / mục tiêu, và hỏi agent bằng ngôn ngữ tự nhiên.
Nguyên tắc của engine giữ nguyên: **code tính mọi con số, LLM chỉ diễn giải**. Giao diện không tự tính chỉ báo;
mọi số hiển thị lấy từ API.

### Khác với bản thiết kế (có chủ đích)

| Thiết kế | Bản chạy thật | Lý do |
|---|---|---|
| Độ tin cậy `[xx]%` | Chip mức (`thấp` / `trung bình` / `cao`) + "điểm N · thang quy tắc", mở rộng xem từng yếu tố | Engine tính điểm theo quy tắc, không phải xác suất. Hiển thị % sẽ gây hiểu nhầm |
| Nút 15 phút / Giờ hoạt động | Hiện nhưng `disabled`, viền đứt nét, tooltip "Chưa hỗ trợ" | Chưa có dữ liệu trong ngày và ngưỡng hiệu chỉnh cho khung nhỏ |
| Khung Tuần | Gộp từ nến ngày + banner "chỉ để tham khảo" | Ngưỡng detector hiệu chỉnh cho khung ngày |
| Một nút "Phân tích lại" | Thêm nút "Gửi" để hỏi; "Phân tích lại" tải lại dữ liệu và diễn giải | Tách hai hành động khác nhau: hỏi và chạy lại |
| Nhãn kháng cự / hỗ trợ trên đường đứt nét | Thẻ giá ở cột trục phải, tên trong `<title>` và chú giải | Nhãn trong vùng vẽ đè lên nhãn sự kiện ở dữ liệu thật |
| Mục tiêu P&F một con số | Khoảng "thận trọng – tích cực", thẻ "tạm tính" khi chưa có SOS | Đếm ngang chuẩn Wyckoff: chiếu từ đáy cấu trúc và từ đường đếm |

## Layout

- Menu: cột trái rộng 220px, cố định khi cuộn, từ 1280px trở lên; hẹp hơn thì thành logo và hai tab ở đầu trang.
- Container nội dung: `max-width: 1384px`, căn giữa phần còn lại, padding `24px 28px 32px`, khoảng cách khối `--sp-5` (20px).
- Hàng chính: grid `minmax(0,2fr) minmax(0,1fr)`: biểu đồ (≈2/3) | cột phải (Pha hiện tại, Sự kiện).
- Hàng dưới: grid `minmax(0,1fr) minmax(0,1.6fr)`: Kịch bản | Hỏi Agent.
- Cột phải: flex dọc, thẻ Sự kiện `flex: 1` để đáy thẳng hàng với thẻ biểu đồ.
- Biểu đồ: cao 540px (480 ≤1080px, 400 ≤640px); vùng giá 78%, khối lượng 22% (kéo được đường phân cách); hàng nút khoảng thời gian cao 44px phía trên.

## Design Tokens Used

Khai báo trong `web/app/globals.css` (`@theme`, tên lớp Tailwind: bỏ tiền tố `--color-`, vd. `bg-surface`; `--surface-sunken` → `bg-sunken`, `--border` → `border-line`). Chỉ có giao diện tối, theo thiết kế.

| Token | Value | Usage |
|---|---|---|
| `--bg` | #0B1015 | Nền trang |
| `--surface` | #121A21 | Thẻ, ô mã, nút khung thời gian |
| `--surface-sunken` | #0F161C | Ô nhập câu hỏi, bong bóng agent |
| `--surface-raised` | #1A2730 | Bong bóng người dùng, tooltip, thẻ giá trên trục |
| `--border` / `--border-strong` | #22303A / #2A3741 | Viền thẻ, đường phân cách / viền control |
| `--text` / `--text-2` | #E6EDF3 / #C3CDD5 | Chữ chính / chữ mô tả |
| `--muted` / `--faint` | #9AA7B2 / #7F8D99 | Eyebrow, meta (≈7:1 trên surface) / nhãn trục, placeholder (≈5:1) |
| `--pos` | #2DD4BF | Nến tăng, nút chính, xác nhận, pha hiện tại, focus ring |
| `--pos-dim` | #1F6F67 | Pha đã qua |
| `--on-pos` | #062A26 | Chữ trên nền `--pos` |
| `--event` | #F5B841 | Nhãn sự kiện Wyckoff, đường TB20, mục tiêu |
| `--neg` | #F87171 | Nến giảm, vô hiệu, lỗi |
| `--vol` | #4A5866 | Cột khối lượng thường (SC đỏ, SOS xanh) |
| `--font-sans` | IBM Plex Sans 400–700 | Mọi chữ |
| `--font-mono` | IBM Plex Mono 400–600, `tabular-nums` | Giá, tỉ số, ngày, mã |
| `--fs-xs … --fs-2xl` | 12 / 13 / 14 / 18 / 24 / 26px | Meta / nhãn / thân / mục tiêu / – / tên pha |
| `--sp-1 … --sp-7` | 4 / 8 / 12 / 16 / 20 / 24 / 28px | Khoảng cách |
| `--r-sm` / `--r-md` / `--r-lg` | 8 / 10 / 12px | Control / bong bóng / thẻ |
| `--control-h` | 44px | Chiều cao tối thiểu mọi nút và ô nhập |
| `--dur` / `--ease` | 150ms / cubic-bezier(.2,0,0,1) | Chuyển trạng thái hover/focus |

## Components

| Component | Variant | Props / dữ liệu (API) | Notes |
|---|---|---|---|
| Ô mã | – | `symbol` | Tự viết hoa; kiểm tra `^[A-Z0-9]{3,10}$` ở cả client và server; Enter hoặc nút kính lúp để phân tích |
| Nút khung | selected / default / disabled | `data-tf` | `aria-pressed`; 15m, 1H luôn disabled |
| Pill trạng thái | loading / ok / error | – | `role=status`; chấm hổ phách nhấp nháy khi tải |
| Banner | notice / warning | `notices[]`, `warnings[]` | Ẩn khi rỗng; cảnh báo màu `--event` |
| Biểu đồ nến | – | `bars[]`, `view_from`, `ranges[]`, `chart_events[]` | TradingView Lightweight Charts (canvas, Apache 2.0, giữ logo ghi công); màu đọc từ biến CSS |
| Dải pha | A, B, C, D, E, vô hiệu | `phase_segments[]` | Nền màu phủ hết chiều cao vùng giá, tên pha ở đỉnh dải (ẩn nếu dải hẹp hơn chữ; dòng OHLC vẫn ghi pha của nến dưới con trỏ). Dải mở từ phiên xác nhận nên có thể bắt đầu sau ngày sự kiện. Màu: token `--color-phase-*`, độ đậm 13% |
| Vùng giao dịch | hiện tại / cũ | `ranges[]` | Nền `--color-pos` 24% / 16%, viền 90% / 45% để nổi trên mọi dải pha |
| Nút khoảng thời gian | Mặc định, 3T, 6T, 1N, 3N, Tất cả; + / − | `aria-pressed` | "Mặc định" = khung nhìn quanh cấu trúc hiện tại; zoom hoặc kéo tay thì bỏ chọn |
| Readout OHLC | – | nến dưới con trỏ, mặc định nến cuối | % thay đổi xanh/đỏ |
| Thẻ pha | A–E / invalid / none | `phase`, `confidence` | 5 đoạn: done / current / pending; `<details>` liệt kê yếu tố tin cậy ±điểm |
| Dòng sự kiện | – | `events[]` | Tên (hổ phách, mono) · mô tả · ngày · KL ×TB20 · biên độ ×ATR · vị trí đóng cửa · ngày xác nhận nếu khác |
| Kịch bản | confirm / invalidate / target | `levels[]`, `target`, diễn giải LLM theo `level_id` | Diễn giải chèn vào sau khi `/api/explanation` trả về |
| Chat | agent / user / pending / error | `/api/explanation`, `/api/ask` | Tối đa 500 ký tự; khung chat cao tối đa 360px, tự cuộn |

## States and Interactions

| Element | State | Behavior |
|---|---|---|
| Toàn trang | Loading lần đầu | Skeleton shimmer ở biểu đồ, thẻ pha, sự kiện, kịch bản; pill "Đang phân tích HPG…" |
| Toàn trang | Đổi mã / khung | Điều hướng tới `/co-phieu/<MÃ>[?tf=1W]`; skeleton (`loading.tsx`) hiện ngay; Back / Forward hoạt động |
| Biểu đồ | Hover / chạm | Crosshair + nhãn trên hai trục; dòng OHLC đầu thẻ đổi theo nến dưới con trỏ (gồm KL, ×TB20) |
| Biểu đồ | Zoom / kéo | Con lăn hoặc pinch để zoom, kéo ngang để xem ngày cũ, kéo trục giá để co giãn (nhấp đúp trục để về tự động). Điện thoại: vuốt dọc vẫn cuộn trang |
| Biểu đồ | Bàn phím (focus) | ←/→ từng nến, PageUp/PageDown 20 nến, Home/End, +/− zoom, Esc bỏ con trỏ; khung nhìn tự cuộn theo con trỏ |
| Biểu đồ | Lỗi | Thông báo `role=alert` + nút "Thử lại"; các thẻ khác hiện "—" |
| Nút chính | Hover | `--pos` → `--pos-hover` |
| "Phân tích lại" | Loading | Disabled, nhãn "Đang phân tích…"; bỏ cache 5 phút ở server, cập nhật dữ liệu tăng dần, diễn giải lại |
| "Gửi" | Pending | Disabled; bong bóng agent "Agent đang trả lời…" (`aria-busy`) |
| Agent | Không có LLM / LLM sai số liệu | Trả lời theo mẫu + ghi chú phụ; nguồn hiển thị ở góc thẻ ("Diễn giải bởi <model>" / "theo mẫu") |
| Ô nhập | Focus | Viền `--pos`; mọi control có `:focus-visible` 2px `--pos` |

## Responsive Behavior

| Breakpoint | Changes |
|---|---|
| > 1080px | Layout như thiết kế 1440 |
| ≤ 1080px | Hai hàng grid thành một cột: biểu đồ → pha → sự kiện → kịch bản → hỏi agent; biểu đồ cao 480px |
| ≤ 640px | Thanh trên xếp dọc; ô mã full width; 4 nút khung thành grid 4 cột; padding 16px; biểu đồ 400px, 4 nhãn ngày và 4 mức giá; nhãn trục kháng cự/hỗ trợ chỉ hiện giá; nút Gửi / Phân tích lại chia đôi hàng dưới ô nhập |

Không cuộn ngang ở 375px (đã kiểm tra).

## Edge Cases

- **Chưa có cấu trúc**: tiêu đề "Chưa có cấu trúc", không có bước pha hiện tại, danh sách sự kiện "Chưa có sự kiện nào thuộc cấu trúc hiện tại", mục tiêu "Chưa đủ điều kiện".
- **Cấu trúc vô hiệu** (UTAD, thoát xuống, thủng Spring): tiêu đề "Cấu trúc vô hiệu", tin cậy "không áp dụng".
- **Mã sai / không có dữ liệu**: 422 (sai định dạng, thiếu nến), 404 (không có dữ liệu), 502 (nguồn vnstock lỗi). Thông báo tiếng Việt từ server hiện trong vùng biểu đồ.
- **Thiếu dữ liệu chỉ số**: banner "bỏ qua bối cảnh thị trường"; phân tích vẫn chạy.
- **Chữ dài**: điều kiện kịch bản (mono) `overflow-wrap: anywhere`; câu trả lời agent ≤ 1.200 ký tự (server kiểm tra); câu hỏi ≤ 500 ký tự.
- **Nhiều sự kiện gần nhau**: chữ nhãn đè nhau được đẩy xuống / lên tầng tiếp theo (14px/tầng), chữ sát mép được kéo vào trong vùng vẽ. Nhìn rộng hơn 250 nến: sự kiện của cấu trúc cũ chỉ còn tam giác mờ.
- **Lịch sử biểu đồ**: API trả toàn bộ dữ liệu đã phân tích (khung ngày từ giữa 2019, khoảng 1.800 nến, khoảng 180 KB JSON với HPG). Khung nhìn mặc định `view_from`: 160 nến ngày / 156 nến tuần, mở rộng để thấy trọn cấu trúc hiện tại (tối đa 400 nến). "Phân tích lại" giữ nguyên khung nhìn đang xem.
- **Mạng chậm**: phân tích (nhanh, có cache) và diễn giải LLM (chậm) là hai request riêng; dashboard hiện ngay, agent điền sau.
- **Trước 15:00**: engine bỏ nến hôm nay (chưa hoàn tất); pill trạng thái ghi "dữ liệu đến <ngày>".

## Animation / Motion

| Element | Trigger | Animation | Duration | Easing |
|---|---|---|---|---|
| Control (nút, ô nhập) | Hover / focus | Đổi nền, viền | 150ms | `--ease` |
| Skeleton | Đang tải | Shimmer ngang | 1.4s lặp | linear |
| Chấm trạng thái, "…" của agent | Đang tải / đang trả lời | Nhấp nháy opacity | 1s lặp | ease-in-out |

`prefers-reduced-motion: reduce` tắt toàn bộ animation và transition.

## Accessibility Notes

- Thứ tự focus: link "Bỏ qua tới ô hỏi agent" → ô mã → nút tìm → khung thời gian → biểu đồ (`tabindex=0`) → chi tiết tin cậy → ô câu hỏi → Gửi → Phân tích lại.
- Biểu đồ: `role=img` với `aria-label` tóm tắt (mã, số nến, pha, hỗ trợ / kháng cự, hướng dẫn phím). Danh sách sự kiện và thẻ kịch bản là bản văn bản tương đương.
- Tiến trình pha: `<ol>` với `aria-current="step"` và chữ ẩn "(đã qua)" / "(chưa tới)".
- Khung chat `aria-live="polite"`: câu trả lời mới được đọc; pill trạng thái `role=status`; lỗi biểu đồ `role=alert`.
- Ô nhập có `<label>` (ẩn trực quan cho ô câu hỏi); nút icon có `aria-label`.
- Tương phản (ước tính theo WCAG): chữ chính ≈14:1, `--muted` ≈7:1, `--faint` ≈5:1 trên `--surface`; chữ trên nút chính ≈8:1.
- Màu không phải kênh duy nhất: nến tăng/giảm khác vị trí thân (open/close), xác nhận / vô hiệu có tiêu đề chữ, mức tin cậy ghi bằng chữ.

## API

| Method | Path | Trả về |
|---|---|---|
| GET | `/api/health` | Trạng thái, LLM có sẵn không, mã mặc định |
| GET | `/api/analysis/{symbol}?tf=1D\|1W&refresh=` | View model: `bars`, `view_from`, `ranges`, `chart_events`, `phase`, `confidence`, `events`, `levels`, `target`, `market`, `notices`, `warnings` |
| GET | `/api/market?refresh=` | Trang thị trường: `close`, `change_pct`, `trend`, `conditions`, `returns`, `drawdown`, `bars`, `trend_segments`, `notices` |
| GET | `/api/explanation/{symbol}?tf=` | Diễn giải (LLM / cache / theo mẫu) theo schema prompt v4 |
| POST | `/api/ask` | `{symbol, timeframe, question}` → `{answer, event_ids, source, model, errors}` |

OpenAPI: `/api/docs`. Cấu hình qua biến môi trường `WYCKOFF_CONFIG`, `WYCKOFF_CACHE_DIR`, `WYCKOFF_OUT_DIR`,
`WYCKOFF_MODEL`, `WYCKOFF_NO_LLM`, `WYCKOFF_NO_MARKET`, `WYCKOFF_TTL_S`, `WYCKOFF_DEFAULT_SYMBOL`; LLM cần `ANTHROPIC_API_KEY`.

## Trang thị trường

Đường dẫn `/thi-truong`, mã nguồn `app/thi-truong/` và `components/market/`, số liệu từ `market_overview` (`wyckoff/market.py`). Trang không có ô nhập mã; muốn phân tích một mã thì vào menu Cổ phiếu.

| Khối | Nội dung | Ghi chú |
|---|---|---|
| Tóm tắt | Điểm chỉ số, thay đổi phiên, nhãn xu hướng, ngày bắt đầu và số phiên | Thiếu lịch sử: "Chưa đủ dữ liệu", ẩn hai thẻ điều kiện |
| Bốn ô số | Lợi suất 20/60/120 phiên; giảm so với đỉnh 250 phiên | Đỉnh tính theo `high`, cùng định nghĩa với bối cảnh thị trường ở trang cổ phiếu |
| Biểu đồ | Nến, SMA20 (chỉ để vẽ, không thuộc quy tắc xu hướng), SMA50, SMA200, dấu đỉnh, khối lượng (xanh/đỏ theo nến) kèm TB20, dải xu hướng dưới cùng | Mặc định 1N, 6T khi vùng vẽ hẹp hơn 560px; không có logo nổi vì che dải xu hướng, ghi công TradingView bằng dòng chữ có link |
| Thẻ điều kiện | Giảm: "Vì sao là xu hướng giảm" và "Điều kiện đảo chiều tăng" kèm khoảng cách và mốc gần nhất. Tăng: đối xứng. Đi ngang: điều kiện của cả hai chiều | Đây là quy tắc đặt nhãn của `market_regime`, trang ghi rõ chưa phải tín hiệu đã kiểm định |

Chưa đưa pha Wyckoff của chỉ số vào trang vì ngưỡng detector chưa hiệu chỉnh cho chỉ số. `WYCKOFF_NO_MARKET` hoặc `market.enabled: false`: API trả 404, trang hiện thông báo lỗi.

## Chưa làm (cần quyết định trước khi mở ra Internet)

- Xác thực người dùng và giới hạn tần suất cho `/api/ask` (mỗi câu hỏi là một lần gọi LLM có phí).
- Khung 15 phút / giờ: cần nguồn dữ liệu trong ngày và hiệu chỉnh lại ngưỡng.
- Content-Security-Policy cho giao diện Next.js (cần nonce cho script nội tuyến của Next); hiện chỉ đặt `X-Frame-Options`, `nosniff`, `Referrer-Policy`.
