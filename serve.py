"""Chạy API cho web dashboard (giao diện: cd web && npm run dev).

    python serve.py                         # http://127.0.0.1:8000/api/docs
    python serve.py --port 8080 --no-llm    # diễn giải theo mẫu, không gọi API
    python serve.py --host 0.0.0.0          # mở cho máy khác trong mạng (cân nhắc bảo mật)
"""
from __future__ import annotations

import argparse
import logging
import os


def main() -> None:
    p = argparse.ArgumentParser(description="Wyckoff Agent – API cho web dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--config", default=None)
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--no-llm", action="store_true", help="dùng diễn giải theo mẫu, không gọi LLM")
    p.add_argument("--no-market", action="store_true", help="không dùng bối cảnh chỉ số thị trường")
    p.add_argument("--reload", action="store_true", help="tự nạp lại khi sửa code (phát triển)")
    args = p.parse_args()

    # Settings đọc biến môi trường khi tạo app (cả trong tiến trình con của --reload)
    for flag, env, value in ((args.config, "WYCKOFF_CONFIG", args.config), (args.cache_dir, "WYCKOFF_CACHE_DIR", args.cache_dir),
                             (args.no_llm, "WYCKOFF_NO_LLM", "1"), (args.no_market, "WYCKOFF_NO_MARKET", "1")):
        if flag:
            os.environ[env] = value
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    import uvicorn

    uvicorn.run("wyckoff.web.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
