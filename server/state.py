from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Callable, Optional

from config import STATE_FILE, STATE_SAVE_DEBOUNCE_SECONDS, config
from log import logger

state: dict[str, Any] = {
    "volume": config["defaultVolume"],
    "isPlaying": False,
    "currentTrack": {
        "trackName": "No song playing",
        "artistName": "",
        "albumName": "",
        "trackUri": "",
        "albumUri": "",
        "albumArtUrl": ""
    },
    "trackProgress": 0,
    "trackDuration": 0,
    "trackProgressStartTimestamp": 0,
    "isShuffling": False,
    "repeatStatus": 0,
    "isLiked": False,
    "lyrics": {
        "trackUri": "",
        "synced": [],
        "plain": "",
        "available": False,
        "instrumental": False,
        "loading": False
    },
    "queue": {
        "nextTracks": [],
        "queueRevision": ""
    }
}

pendingQueueMeta: list[dict[str, str]] = []

_rate_limit_store: dict[str, float] = {}

_save_timer: Optional[asyncio.Task[None]] = None
_write_callback: Optional[Callable[[dict[str, Any]], None]] = None


def set_write_callback(callback: Callable[[dict[str, Any]], None]) -> None:
    global _write_callback
    _write_callback = callback


def read_state_from_file() -> None:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved_state: dict[str, Any] = json.load(f)
                state["volume"] = saved_state.get("volume", state["volume"])
                state["isPlaying"] = saved_state.get("isPlaying", state["isPlaying"])
                state["currentTrack"].update(saved_state.get("currentTrack", {}))
                state["isShuffling"] = saved_state.get("isShuffling", state["isShuffling"])
                state["repeatStatus"] = saved_state.get("repeatStatus", state["repeatStatus"])
                state["isLiked"] = saved_state.get("isLiked", state["isLiked"])
                logger.info("Server: Loaded state from state.json")
        except Exception as e:
            logger.error(f"Server: Error reading state file: {e}")


async def save_state_to_file_debounced() -> None:
    global _save_timer
    if _save_timer:
        _save_timer.cancel()

    _save_timer = asyncio.create_task(_actually_save_after_delay(STATE_SAVE_DEBOUNCE_SECONDS))


def get_current_save_data() -> dict[str, Any]:
    return {
        "volume": round(state["volume"], 2),
        "isPlaying": state["isPlaying"],
        "currentTrack": state["currentTrack"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"]
    }


async def _actually_save_after_delay(delay: float) -> None:
    try:
        await asyncio.sleep(delay)
        if _write_callback:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _write_callback, get_current_save_data())
        logger.info("Server: Saved state to state.json (debounced)")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Server: Error in debounced save: {e}")


def cancel_pending_save() -> None:
    global _save_timer
    if _save_timer:
        _save_timer.cancel()
        _save_timer = None
        logger.debug("Server: Pending save timer cancelled.")


def parse_track_input(text: str) -> str:
    text = text.strip()
    match = re.search(r'open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]+)', text)
    if match:
        return f"spotify:track:{match.group(1)}"
    match = re.search(r'spotify:track:([a-zA-Z0-9]+)', text)
    if match:
        return f"spotify:track:{match.group(1)}"
    return text


def check_rate_limit(requester: str) -> tuple[bool, str]:
    now = time.time()
    last_request = _rate_limit_store.get(requester, 0)
    elapsed = now - last_request
    limit = float(config.get("queueRateLimitSeconds", 30))
    if elapsed < limit:
        remaining = int(limit - elapsed)
        return False, f"Rate limited. Try again in {remaining}s"
    _rate_limit_store[requester] = now
    return True, ""


def reset_rate_limit(requester: str) -> None:
    _rate_limit_store.pop(requester, None)


def is_queue_full() -> bool:
    from config import MAX_QUEUE_SIZE
    return len(pendingQueueMeta) >= MAX_QUEUE_SIZE


