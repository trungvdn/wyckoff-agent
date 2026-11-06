"""Chế độ server: chỉ đọc CSV đã đồng bộ, không gọi nguồn dữ liệu; script đồng bộ đóng gói đúng file."""
from __future__ import annotations

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wyckoff.config import Config, DataConfig
from wyckoff.data.cache import cache_path, save_cache
from wyckoff.data.loader import get_ohlcv
from wyckoff.service import DataUnavailable, load_ohlcv
from wyckoff.web.app import Settings, create_app


def _no_fetch(*a, **k):
    raise AssertionError("chế độ offline không được gọi nguồn dữ liệu")


def _load_sync():
    path = Path(__file__).resolve().parents[1] / "scripts" / "sync_cache.py"
    spec = importlib.util.spec_from_file_location("sync_cache", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_offline_reads_stale_cache_without_fetch_or_write(tmp_path, ohlcv):
    path = cache_path(tmp_path, "HPG")
    save_cache(ohlcv, path)
    before = path.read_bytes()
    out = get_ohlcv("hpg", f"{ohlcv.index[0]:%Y-%m-%d}", cache_dir=tmp_path, source_fn=_no_fetch,
                    cfg=DataConfig(offline=True))
    assert len(out) == len(ohlcv)
    assert path.read_bytes() == before


def test_offline_missing_symbol_is_404_with_clear_message(tmp_path):
    cfg = Config(data=DataConfig(offline=True))
    with pytest.raises(DataUnavailable) as e:
        load_ohlcv("ZZZ", "1D", cfg, cache_dir=str(tmp_path))
    assert e.value.status == 404 and "đồng bộ" in str(e.value)


def test_api_offline_shows_data_date(tmp_path, ohlcv):
    save_cache(ohlcv, cache_path(tmp_path, "HPG"))
    app = create_app(Settings(no_llm=True, no_market=True, offline=True, cache_dir=str(tmp_path), out_dir=str(tmp_path)))
    client = TestClient(app)
    view = client.get("/api/analysis/HPG").json()
    assert f"{ohlcv.index[-1]:%d/%m/%Y}" in " ".join(view["notices"])
    assert client.get("/api/analysis/ZZZ").status_code == 404


def test_sync_archive_is_flat_and_only_selected_files(tmp_path, ohlcv):
    sync = _load_sync()
    wanted = cache_path(tmp_path, "HPG")
    save_cache(ohlcv, wanted)
    (tmp_path / "secret.env").write_text("KEY=1")
    buf = io.BytesIO()
    sync.write_archive(buf, [wanted])
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        assert [(m.name, m.mode, m.uid) for m in tar.getmembers()] == [("HPG_1D.csv", 0o644, 0)]


def test_sync_update_continues_after_failure(tmp_path, monkeypatch, capsys):
    sync = _load_sync()

    def fake(symbol, start, **kw):
        if symbol == "BAD":
            raise RuntimeError("nguồn lỗi")
        return None

    monkeypatch.setattr(sync, "get_ohlcv", fake)
    assert sync.update(["BAD", "HPG"], tmp_path, Config()) == ["BAD"]
    assert "HPG: xong" in capsys.readouterr().out
