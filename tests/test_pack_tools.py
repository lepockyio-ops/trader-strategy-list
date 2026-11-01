"""Packaging and installation must not overwrite user state or bypass framework pinning."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pack_tools", ROOT / "tools/packs.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


def fixture(tmp_path, monkeypatch):
    source = tmp_path / "source"
    framework = tmp_path / "framework"
    base = source / "packs/example"
    names = ["docs/STRATEGY.md", "docs/TESTING.md", "docs/VALIDATION.md", "docs/RESEARCH.md",
             "user_data/strategies/Example.py", "tests/test_example.py"]
    for name in names:
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test " + name, encoding="utf-8")
    risk = framework / "user_data/strategies/framework_base.py"
    risk.parent.mkdir(parents=True)
    risk.write_text("reviewed base\n", encoding="utf-8")
    config = framework / "user_data/config.json"
    config.write_text('{"dry_run":true,"strategy":"MyStrategy"}', encoding="utf-8")
    item = {"slug": "example", "strategy_file": names[4], "test_file": names[5]}
    (source / "manifest.json").write_text(json.dumps({"packs": [item], "framework": {
        "base_sha256": tools.framework_digest(risk)}}), encoding="utf-8")
    monkeypatch.setattr(tools, "ROOT", source)
    return source, framework, config


def test_install_is_idempotent_and_preserves_config(tmp_path, monkeypatch):
    _, framework, config = fixture(tmp_path, monkeypatch)
    before = config.read_bytes()
    assert len(tools.install("example", framework)) == 6
    assert len(tools.install("example", framework)) == 6
    assert config.read_bytes() == before
    assert not (framework / "research/ideas.jsonl").exists()


def test_conflict_preflight_does_not_partially_install(tmp_path, monkeypatch):
    _, framework, _ = fixture(tmp_path, monkeypatch)
    existing = framework / "tests/test_example.py"
    existing.parent.mkdir()
    existing.write_text("user's existing test", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        tools.install("example", framework)
    assert not (framework / "user_data/strategies/Example.py").exists()


def test_changed_framework_is_rejected(tmp_path, monkeypatch):
    _, framework, _ = fixture(tmp_path, monkeypatch)
    (framework / "user_data/strategies/framework_base.py").write_text("different", encoding="utf-8")
    with pytest.raises(ValueError, match="review compatibility"):
        tools.install("example", framework)


def test_windows_line_endings_do_not_reject_same_framework(tmp_path, monkeypatch):
    _, framework, _ = fixture(tmp_path, monkeypatch)
    (framework / "user_data/strategies/framework_base.py").write_bytes(b"reviewed base\r\n")
    assert len(tools.install("example", framework)) == 6


def test_archive_is_reproducible_and_complete(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    first = tools.build("example", tmp_path / "dist")
    second = tools.build("example", tmp_path / "dist")
    assert first == second
    with zipfile.ZipFile(tmp_path / "dist/example-v1.zip") as archive:
        assert len(archive.namelist()) == 8
        assert archive.testzip() is None


def test_path_traversal_is_refused(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        tools.contained(tmp_path, "../outside")
