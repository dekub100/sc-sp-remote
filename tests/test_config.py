"""Layered config and atomic JSON writes in server/config.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import config as cfg
import pytest

import server


class TestConfigLayering:
    def test_default_file_matches_code_defaults(self) -> None:
        with open(cfg.DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
            shipped = json.load(f)
        assert shipped == cfg.CODE_DEFAULTS

    def test_user_config_overlays_defaults(self, tmp_path: Any) -> None:
        default = tmp_path / "config.default.json"
        user = tmp_path / "config.json"
        default.write_text(json.dumps({"port": 1111, "logLevel": "WARNING"}), encoding="utf-8")
        user.write_text(json.dumps({"port": 2222}), encoding="utf-8")
        merged = cfg.load_config(str(default), str(user))
        assert merged["port"] == 2222
        assert merged["logLevel"] == "WARNING"
        assert merged["defaultVolume"] == cfg.CODE_DEFAULTS["defaultVolume"]

    def test_invalid_user_config_falls_back_to_defaults(self, tmp_path: Any) -> None:
        user = tmp_path / "config.json"
        user.write_text("{ not json", encoding="utf-8")
        merged = cfg.load_config(str(tmp_path / "missing.default.json"), str(user))
        assert merged == cfg.CODE_DEFAULTS

    def test_user_config_with_utf8_bom_is_read(self, tmp_path: Any) -> None:
        # Notepad and PowerShell 5.1 write a BOM; ignore it instead of dropping the config.
        user = tmp_path / "config.json"
        user.write_bytes("\ufeff{\"port\": 3333}".encode("utf-8"))
        merged = cfg.load_config(str(tmp_path / "missing.default.json"), str(user))
        assert merged["port"] == 3333

    def test_missing_user_config_is_created(self, tmp_path: Any) -> None:
        target = tmp_path / "nested" / "config.json"
        assert cfg.ensure_user_config(str(target)) is True
        with open(target, encoding="utf-8") as f:
            created = json.load(f)
        assert set(created) == set(cfg.config)
        assert created["port"] == cfg.config["port"]
        assert cfg.ensure_user_config(str(target)) is False


class TestAtomicWrites:
    def test_write_replaces_file(self, tmp_path: Any) -> None:
        path = tmp_path / "state.json"
        cfg.write_json_atomic(str(path), {"a": 1})
        assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
        assert not (tmp_path / "state.json.tmp").exists()

    def test_failed_write_keeps_old_file(self, tmp_path: Any) -> None:
        path = tmp_path / "state.json"
        path.write_text('{"old": true}', encoding="utf-8")
        with patch.object(cfg.json, "dump", side_effect=RuntimeError("disk full")):
            with pytest.raises(RuntimeError):
                cfg.write_json_atomic(str(path), {"new": True})
        assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}


class TestUserConfigGuard:
    def test_read_only_config_creation_is_non_fatal(self) -> None:
        with patch.object(server, "ensure_user_config", side_effect=PermissionError("read-only")), \
             patch.object(server.logger, "warning") as mock_warning:
            server._ensure_user_config_or_default()
        assert mock_warning.called
