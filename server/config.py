import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SERVER_DIR, "config.json")
STATE_FILE = os.path.join(PROJECT_ROOT, "state.json")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LYRICS_CACHE_DB = os.path.join(PROJECT_ROOT, "lyrics_cache.db")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

DISCOVERY_PORT = 54321

STATE_SAVE_DEBOUNCE_SECONDS = 2.0
PROGRESS_BROADCAST_INTERVAL = 1.0

config = {
    "port": 8888,
    "allowedOrigins": ["*"],
    "defaultVolume": 0.5,
    "enableOBS": True,
    "enableWebsite": True,
    "volumeStep": 0.05,
    "logLevel": "INFO",
    "backupCount": 3
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Failed to read config.json, using defaults: {e}")
