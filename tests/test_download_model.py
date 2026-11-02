import importlib.util
import json
import sys
import types
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "download_model", Path(__file__).parents[1] / "scripts" / "download_model.py"
)
download_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download_model)


def test_second_start_uses_cache_without_network(tmp_path, monkeypatch):
    target = tmp_path / "Qwen--Qwen2.5-1.5B-Instruct"
    target.mkdir()
    (target / download_model.MARKER).write_text(
        json.dumps({"model_id": "Qwen/Qwen2.5-1.5B-Instruct", "revision": "main"})
    )
    monkeypatch.setenv("MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    assert download_model.main() == 0


def test_first_start_downloads_and_writes_marker(tmp_path, monkeypatch):
    calls = []
    fake = types.ModuleType("huggingface_hub")
    fake.HfApi = lambda token=None: types.SimpleNamespace(
        model_info=lambda *a, **k: types.SimpleNamespace(sha="abc123")
    )
    fake.snapshot_download = lambda repo, **kwargs: calls.append((repo, kwargs))
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)
    monkeypatch.setenv("MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path))
    (tmp_path / "Qwen--Qwen2.5-1.5B-Instruct").mkdir()

    assert download_model.main() == 0
    assert calls[0][0] == "Qwen/Qwen2.5-1.5B-Instruct" and calls[0][1]["revision"] == "abc123"
    marker = json.loads((tmp_path / "Qwen--Qwen2.5-1.5B-Instruct" / download_model.MARKER).read_text())
    assert marker["commit"] == "abc123"


def test_other_model_in_cache_triggers_download(tmp_path):
    target = tmp_path / "m"
    target.mkdir()
    (target / download_model.MARKER).write_text(json.dumps({"model_id": "other/model", "revision": "main"}))
    assert not download_model.is_complete(target, "Qwen/Qwen2.5-1.5B-Instruct", "main")
