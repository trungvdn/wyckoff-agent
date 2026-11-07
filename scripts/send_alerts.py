"""Cảnh báo sau phiên qua Telegram: cập nhật giá, kiểm tra quy tắc bán, nhắn khi có thay đổi (docs/alerts.md).

Chạy trên máy có nguồn dữ liệu và file danh mục, sau 15:00.

    python scripts/send_alerts.py                       # chạy một lượt
    python scripts/send_alerts.py --dry-run             # in tin nhắn, không gửi, không lưu trạng thái
    python scripts/send_alerts.py --dry-run --no-update # như trên, không tải giá
    python scripts/send_alerts.py --test                # gửi một tin thử
    python scripts/send_alerts.py --chat-id             # xem chat ID sau khi đã nhắn cho bot
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wyckoff.alerts import AlertSendError, TelegramSender, load_env_file, run_alerts  # noqa: E402
from wyckoff.portfolio import PortfolioStore  # noqa: E402

logger = logging.getLogger("send_alerts")


def _sender() -> TelegramSender | None:
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    return TelegramSender(token, chat_id) if token and chat_id else None


def _near_enabled() -> bool:
    return os.environ.get("WYCKOFF_ALERT_NEAR", "1").strip().lower() not in {"0", "false", "no"}


def run_once(*, dry_run: bool, no_update: bool) -> int:
    # Nhập muộn: các lệnh --test, --chat-id không cần tới phần phân tích
    from sync_cache import index_symbols, update

    from wyckoff.web.store import AnalysisStore, Settings, load_app_config

    send = _sender()
    if send is None and not dry_run:
        print("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong .env (docs/alerts.md).", file=sys.stderr)
        return 2

    settings = Settings(no_llm=True)
    cfg = load_app_config(settings)
    holdings = PortfolioStore(settings.portfolio_db)
    symbols = [h.symbol for h in holdings.list() if h.alerts_enabled]
    problems: list[str] = []
    if symbols and not no_update:
        failed = update(sorted(set(symbols) | index_symbols(cfg)), Path(settings.cache_dir), cfg)
        problems = [f"{s}: không cập nhật được giá" for s in failed]

    # Giá vừa được cập nhật ở trên: phần phân tích chỉ đọc cache, tránh gọi nguồn thêm lần nữa
    cfg = replace(cfg, data=replace(cfg.data, offline=True))
    store = AnalysisStore(settings, cfg, lambda: (None, "job cảnh báo không dùng LLM"))
    result = run_alerts(store.portfolio(holdings), holdings, send.send if send else None, dry_run=dry_run,
                        include_near=_near_enabled(), extra_problems=problems)
    logger.info("Kết quả: %s", result.status)
    if result.text:
        print(result.text)
    else:
        print({"quiet": "Không có gì mới.", "no_holdings": "Danh mục trống.", "dry_run": "Không có gì mới."}.get(result.status, result.status))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Cảnh báo sau phiên qua Telegram")
    p.add_argument("--dry-run", action="store_true", help="in tin nhắn, không gửi, không lưu trạng thái")
    p.add_argument("--no-update", action="store_true", help="không tải giá, dùng dữ liệu đang có")
    p.add_argument("--test", action="store_true", help="gửi một tin thử")
    p.add_argument("--chat-id", action="store_true", help="in chat ID của các cuộc trò chuyện vừa nhắn cho bot")
    args = p.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    os.chdir(ROOT)   # Task Scheduler chạy từ thư mục khác; đường dẫn dữ liệu tính từ gốc dự án
    Path("output").mkdir(exist_ok=True)
    logging.basicConfig(filename="output/alerts.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env_file(".env")

    try:
        if args.chat_id:
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            if not token:
                print("Thiếu TELEGRAM_BOT_TOKEN trong .env.", file=sys.stderr)
                return 2
            chats = TelegramSender(token, "").recent_chats()
            print("\n".join(f"{cid}  {name}" for cid, name in chats) or "Chưa thấy tin nhắn nào. Hãy nhắn một tin cho bot rồi chạy lại.")
            return 0
        if args.test:
            send = _sender()
            if send is None:
                print("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong .env.", file=sys.stderr)
                return 2
            send.send("Wyckoff Agent: tin thử, cảnh báo đã kết nối.")
            print("Đã gửi tin thử.")
            return 0
        return run_once(dry_run=args.dry_run, no_update=args.no_update)
    except AlertSendError as exc:
        logger.error("%s", exc)
        print(f"Không gửi được: {exc}", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("Job cảnh báo lỗi")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
