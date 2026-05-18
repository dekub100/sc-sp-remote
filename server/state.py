from __future__ import annotations

import asyncio
import json
import os
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
    "spicetifyClient": None,
    "lyrics": {
        "trackUri": "",
        "synced": [],
        "plain": "",
        "available": False,
        "instrumental": False,
        "loading": False
    }
}

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
            await asyncio.to_thread(_write_callback, get_current_save_data())
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


read_state_from_file()
