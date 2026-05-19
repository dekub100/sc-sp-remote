from __future__ import annotations

import json
import os
from typing import Any

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.path.join(PROJECT_ROOT, "data")
CONFIG_PATH: str = os.path.join(DATA_DIR, "config.json")
STATE_FILE: str = os.path.join(DATA_DIR, "state.json")
LOG_DIR: str = os.path.join(DATA_DIR, "logs")
LYRICS_CACHE_DB: str = os.path.join(DATA_DIR, "lyrics_cache.db")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

DISCOVERY_PORT: int = 54321

STATE_SAVE_DEBOUNCE_SECONDS: float = 2.0
PROGRESS_BROADCAST_INTERVAL: float = 1.0

QUEUE_RATE_LIMIT_SECONDS: float = 30.0
QUEUE_SNAPSHOT_INTERVAL: float = 2.0

config: dict[str, Any] = {
    "port": 8888,
    "allowedOrigins": ["*"],
    "defaultVolume": 0.5,
    "enableOBS": True,
    "enableWebsite": True,
    "volumeStep": 0.05,
    "logLevel": "INFO",
    "backupCount": 3,
    "maxQueueSize": 50,
    "queueRateLimitSeconds": 30
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Failed to read config.json, using defaults: {e}")

MAX_QUEUE_SIZE: int = int(config.get("maxQueueSize", 50))
QUEUE_RATE_LIMIT_SECONDS: float = float(config.get("queueRateLimitSeconds", 30))
