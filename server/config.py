from __future__ import annotations

import json
import os
from typing import Any

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.path.join(PROJECT_ROOT, "data")
CONFIG_PATH: str = os.environ.get("SC_REMOTE_CONFIG", os.path.join(DATA_DIR, "config.json"))
STATE_FILE: str = os.path.join(DATA_DIR, "state_spotify.json")
SC_STATE_FILE: str = os.path.join(DATA_DIR, "state_soundcloud.json")
LOG_DIR: str = os.path.join(DATA_DIR, "logs")
LYRICS_CACHE_DB: str = os.path.join(DATA_DIR, "lyrics_cache.db")

STATE_SAVE_DEBOUNCE_SECONDS: float = 2.0
PROGRESS_BROADCAST_INTERVAL: float = 1.0

config: dict[str, Any] = {
    "port": 8889,
    "host": "127.0.0.1",
    "allowedOrigins": ["*"],
    "defaultVolume": 0.5,
    "enableWebsite": True,
    "volumeStep": 0.05,
    "logLevel": "INFO",
    "backupCount": 3,
    "progressBroadcastInterval": 1.0,
    "stateSaveDebounceSeconds": 2.0,
    "lyricsFetchTimeoutSeconds": 15,
    "spicetifyPollingIntervalMs": 500,
    "spicetifyQueuePollingIntervalMs": 2000,
    "spicetifyReconnectBaseDelayMs": 1000,
    "spicetifyReconnectMaxDelayMs": 10000,
    "spicetifyProgressDeltaThresholdMs": 2000,
    "spicetifyCommandFeedbackDelayMs": 150,
    "soundcloudPollingIntervalMs": 500,
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Failed to read config.json, using defaults: {e}")

CONFIG_FIELD_TYPES: dict[str, type] = {
    "port": int,
    "host": str,
    "allowedOrigins": list,
    "defaultVolume": float,
    "enableWebsite": bool,
    "volumeStep": float,
    "logLevel": str,
    "backupCount": int,
    "progressBroadcastInterval": float,
    "stateSaveDebounceSeconds": float,
    "lyricsFetchTimeoutSeconds": float,
    "spicetifyPollingIntervalMs": int,
    "spicetifyQueuePollingIntervalMs": int,
    "spicetifyReconnectBaseDelayMs": int,
    "spicetifyReconnectMaxDelayMs": int,
    "spicetifyProgressDeltaThresholdMs": int,
    "spicetifyCommandFeedbackDelayMs": int,
    "soundcloudPollingIntervalMs": int,
}
