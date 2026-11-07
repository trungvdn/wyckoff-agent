"""Cập nhật giá trên máy này rồi đẩy CSV lên server (xem docs/deploy.md).

Server không cài vnstock nên chỉ đọc dữ liệu do script này gửi lên. Chạy sau 15:00, khi đã có nến ngày.

    python scripts/sync_cache.py --host user@server                  # mọi mã đang có trong cache/
    python scripts/sync_cache.py --host user@server --symbols HPG,FPT
    python scripts/sync_cache.py --no-upload                         # chỉ cập nhật cache trên máy này
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.config import Config, load_config  # noqa: E402
from wyckoff.data.cache import cache_path  # noqa: E402
from wyckoff.service import cached_symbols, index_symbols, is_index, update_symbol  # noqa: E402,F401

CONFIG = Path(__file__).resolve().parents[1] / "config" / "v3.yaml"


def update(symbols: list[str], cache_dir: Path, cfg: Config) -> list[str]:
    """Cập nhật tăng dần từng mã; lỗi một mã không dừng cả lượt. Trả về các mã lỗi."""
    failed = []
    for i, symbol in enumerate(symbols, 1):
        try:
            update_symbol(symbol, cfg, cache_dir=cache_dir)
            print(f"[{i}/{len(symbols)}] {symbol}: xong")
        except Exception as exc:  # noqa: BLE001 - ghi nhận rồi sang mã tiếp theo
            failed.append(symbol)
            print(f"[{i}/{len(symbols)}] {symbol}: LỖI {exc}", file=sys.stderr)
    return failed


def write_archive(fileobj, files: list[Path]) -> None:
    """Đóng gói phẳng, chỉ gồm các CSV đã chọn; quyền đọc cho mọi user để container đọc được."""
    def clean(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.mode, info.uid, info.gid, info.uname, info.gname = 0o644, 0, 0, "", ""
        return info

    with tarfile.open(fileobj=fileobj, mode="w|gz") as tar:
        for path in files:
            tar.add(path, arcname=path.name, filter=clean)


def upload(files: list[Path], host: str, remote_dir: str) -> None:
    target = shlex.quote(remote_dir)
    proc = subprocess.Popen(["ssh", host, f"mkdir -p {target} && tar xzf - -C {target}"], stdin=subprocess.PIPE)
    try:
        write_archive(proc.stdin, files)
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"Đẩy dữ liệu lên {host} thất bại (ssh trả về {proc.returncode})")


def main() -> int:
    p = argparse.ArgumentParser(description="Cập nhật giá và đẩy CSV lên server")
    p.add_argument("--host", help="user@server để đẩy dữ liệu qua ssh")
    p.add_argument("--remote-dir", default="/opt/wyckoff-agent/data/cache")
    p.add_argument("--symbols", help="danh sách mã, cách nhau dấu phẩy; mặc định mọi mã trong cache")
    p.add_argument("--cache-dir", default="cache")
    p.add_argument("--no-update", action="store_true", help="không tải giá, chỉ đẩy cache hiện có")
    p.add_argument("--no-upload", action="store_true", help="không đẩy lên server")
    args = p.parse_args()
    if not args.no_upload and not args.host:
        p.error("cần --host, hoặc dùng --no-upload")

    cfg, cache_dir = load_config(CONFIG), Path(args.cache_dir)
    # Luôn kèm chỉ số so sánh: thiếu thì dashboard mất bối cảnh thị trường
    symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols
               else cached_symbols(cache_dir))
    symbols = sorted(set(symbols) | index_symbols(cfg)) if args.symbols else symbols
    failed = [] if args.no_update else update(symbols, cache_dir, cfg)

    files = [path for s in symbols if (path := cache_path(cache_dir, s)).exists()]
    if not args.no_upload:
        upload(files, args.host, args.remote_dir)
        print(f"Đã đẩy {len(files)} file lên {args.host}:{args.remote_dir}")
    if failed:
        print(f"{len(failed)} mã không cập nhật được: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
