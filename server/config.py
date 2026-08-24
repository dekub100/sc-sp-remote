from __future__ import annotations

import json
import os
from typing import Any

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.path.join(PROJECT_ROOT, "data")
CONFIG_PATH: str = os.environ.get("SC_SP_REMOTE_CONFIG", os.path.join(DATA_DIR, "config.json"))
STATE_FILE: str = os.path.join(DATA_DIR, "state_spotify.json")
SC_STATE_FILE: str = os.path.join(DATA_DIR, "state_soundcloud.json")
LOG_DIR: str = os.path.join(DATA_DIR, "logs")
LYRICS_CACHE_DB: str = os.path.join(DATA_DIR, "lyrics_cache.db")

config: dict[str, Any] = {
    "port": 8888,
    "host": "127.0.0.1",
    "allowedOrigins": ["http://localhost:8888", "http://127.0.0.1:8888"],
    "defaultVolume": 0.5,
    "enableOBS": True,
    "enableWebsite": True,
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
    "obsUpNextThresholdMs": 15000,
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Failed to read config.json, using defaults: {e}")

# Derived from user config so admin docs stay truthful (applied at startup).
STATE_SAVE_DEBOUNCE_SECONDS: float = float(config["stateSaveDebounceSeconds"])
PROGRESS_BROADCAST_INTERVAL: float = float(config["progressBroadcastInterval"])


CONFIG_FIELD_TYPES: dict[str, type] = {
    "port": int,
    "host": str,
    "allowedOrigins": list,
    "defaultVolume": float,
    "enableOBS": bool,
    "enableWebsite": bool,
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
    "obsUpNextThresholdMs": int,
}
