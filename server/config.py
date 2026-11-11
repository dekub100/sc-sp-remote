from __future__ import annotations

import json
import os
from typing import Any

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR: str = os.path.dirname(os.path.abspath(__file__))
REPO_DATA_DIR: str = os.path.join(PROJECT_ROOT, "data")
# Runtime data (state, logs, lyrics cache). `SC_SP_REMOTE_DATA_DIR` lets the dev
# server and the test suite use a private directory instead of the live one.
DATA_DIR: str = os.environ.get("SC_SP_REMOTE_DATA_DIR", REPO_DATA_DIR)
DEFAULT_CONFIG_PATH: str = os.path.join(REPO_DATA_DIR, "config.default.json")
CONFIG_PATH: str = os.environ.get("SC_SP_REMOTE_CONFIG", os.path.join(DATA_DIR, "config.json"))
STATE_FILE: str = os.path.join(DATA_DIR, "state_spotify.json")
SC_STATE_FILE: str = os.path.join(DATA_DIR, "state_soundcloud.json")
LOG_DIR: str = os.path.join(DATA_DIR, "logs")
LYRICS_CACHE_DB: str = os.path.join(DATA_DIR, "lyrics_cache.db")

# Authoritative defaults. data/config.default.json must contain exactly this
# dict (enforced by test_server.py::TestConfigLayering).
CODE_DEFAULTS: dict[str, Any] = {
    "port": 8888,
    "host": "127.0.0.1",
    "allowedOrigins": ["http://localhost:8888", "http://127.0.0.1:8888"],
    # Extra Host header names accepted by the anti-rebinding gate. Needed when the
    # server is reached through a hostname (e.g. "myrig.local") instead of an IP.
    "allowedHosts": [],
    "defaultVolume": 0.5,
    "enableAlbumArt": True,
    "logLevel": "INFO",
    "backupCount": 3,
    "progressBroadcastInterval": 1.0,
    "stateSaveDebounceSeconds": 2.0,
    "enableLyrics": True,
    "lyricsFetchTimeoutSeconds": 30,
    "lyricsProviderOrder": ["musixmatch", "lrclib"],
    "musixmatchToken": "",
    "spicetifyPollingIntervalMs": 500,
    "spicetifyReconnectBaseDelayMs": 1000,
    "spicetifyReconnectMaxDelayMs": 10000,
    "spicetifyProgressDeltaThresholdMs": 2000,
    "spicetifyCommandFeedbackDelayMs": 150,
    "soundcloudPollingIntervalMs": 500,
}


def _read_json_object(path: str) -> dict[str, Any]:
    """Read a JSON object, returning {} for a missing or invalid file."""
    if not os.path.exists(path):
        return {}
    try:
        # utf-8-sig also accepts plain UTF-8; Windows editors often add a BOM.
        with open(path, "r", encoding="utf-8-sig") as f:
            data: Any = json.load(f)
        if isinstance(data, dict):
            return data
        print(f"Ignoring {path}: expected a JSON object")
    except Exception as e:
        print(f"Failed to read {path}, keeping current values: {e}")
    return {}


def write_json_atomic(path: str, data: dict[str, Any]) -> None:
    """Write a JSON file atomically (temp file + os.replace).

    A crash mid-write must never leave a truncated state/config file: the old
    file stays intact until the new one is fully flushed to disk.
    """
    tmp_path: str = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def load_config(
    default_path: str = DEFAULT_CONFIG_PATH,
    user_path: str = CONFIG_PATH,
) -> dict[str, Any]:
    """Merge code defaults <- shipped defaults <- user config (later wins)."""
    merged: dict[str, Any] = dict(CODE_DEFAULTS)
    merged.update(_read_json_object(default_path))
    merged.update(_read_json_object(user_path))
    return merged


def ensure_user_config(path: str | None = None) -> bool:
    """Create the user config on first run. Returns True when it was created."""
    target: str = path or CONFIG_PATH
    if os.path.exists(target):
        return False
    parent: str = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    write_json_atomic(target, config)
    return True


config: dict[str, Any] = load_config()


CONFIG_FIELD_TYPES: dict[str, type] = {
    "port": int,
    "host": str,
    "allowedOrigins": list,
    "allowedHosts": list,
    "defaultVolume": float,
    "enableAlbumArt": bool,
    "enableLyrics": bool,
    "logLevel": str,
    "backupCount": int,
    "progressBroadcastInterval": float,
    "stateSaveDebounceSeconds": float,
    "lyricsFetchTimeoutSeconds": float,
    "lyricsProviderOrder": list,
    "musixmatchToken": str,
    "spicetifyPollingIntervalMs": int,
    "spicetifyReconnectBaseDelayMs": int,
    "spicetifyReconnectMaxDelayMs": int,
    "spicetifyProgressDeltaThresholdMs": int,
    "spicetifyCommandFeedbackDelayMs": int,
    "soundcloudPollingIntervalMs": int,
}
