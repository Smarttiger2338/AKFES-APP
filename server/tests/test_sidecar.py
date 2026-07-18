from __future__ import annotations

import json
from pathlib import Path

from sidecar import load_or_create_runtime_config, read_runtime_config


def test_load_or_create_runtime_config_creates_missing_file(tmp_path: Path) -> None:
    config = load_or_create_runtime_config(tmp_path)
    saved = json.loads((tmp_path / "server-runtime.json").read_text(encoding="utf-8"))

    assert len(config["license_secret"]) >= 32
    assert len(config["admin_token"]) >= 32
    assert config["created_at"].isdigit()
    assert saved["version"] == 2
    assert saved["protected"] is True
    assert saved["payload"]
    assert "admin_token" not in saved
    assert read_runtime_config(tmp_path / "server-runtime.json") == config


def test_load_or_create_runtime_config_migrates_plaintext_file(tmp_path: Path) -> None:
    config_path = tmp_path / "server-runtime.json"
    plaintext = {
        "license_secret": "l" * 48,
        "admin_token": "a" * 48,
        "created_at": "123",
    }
    config_path.write_text(json.dumps(plaintext), encoding="utf-8")

    config = load_or_create_runtime_config(tmp_path)
    saved = json.loads(config_path.read_text(encoding="utf-8"))

    assert config == plaintext
    assert saved["version"] == 2
    assert saved["protected"] is True
    assert "admin_token" not in saved


def test_load_or_create_runtime_config_replaces_invalid_file(tmp_path: Path) -> None:
    config_path = tmp_path / "server-runtime.json"
    config_path.write_text("{invalid", encoding="utf-8")

    config = load_or_create_runtime_config(tmp_path)
    backups = list(tmp_path.glob("server-runtime.invalid-*.json"))
    saved = json.loads(config_path.read_text(encoding="utf-8"))

    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{invalid"
    assert len(config["license_secret"]) >= 32
    assert len(config["admin_token"]) >= 32
    assert saved["version"] == 2
    assert saved["protected"] is True
    assert read_runtime_config(config_path) == config
