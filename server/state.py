from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable, Optional

from config import SC_STATE_FILE, STATE_FILE, STATE_SAVE_DEBOUNCE_SECONDS, config
from log import logger

state: dict[str, Any] = {
    # Spotify state (from Spicetify extension)
    "volume": config["defaultVolume"],
    "isPlaying": False,
    "currentTrack": {
        "trackName": "No song playing",
        "artistName": "",
        "albumName": "",
        "trackUri": "",
        "albumUri": "",
        "artistUri": "",
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
    # SoundCloud state (from soundcloud-rpc plugin)
    "scTrack": "No song playing",
    "scArtist": "",
    "scAlbum": "",
    "scId": "",
    "scCoverUrl": "",
    "scIsPlaying": False,
    "scProgressMs": 0,
    "scDurationMs": 0,
    "scProgressStartTimestamp": 0,
    "scVolume": 0.5,
    "scIsLiked": False,
    "scIsShuffling": False,
    "scRepeatStatus": 0,
}

_spotify_save_timer: Optional[asyncio.Task[None]] = None
_sc_save_timer: Optional[asyncio.Task[None]] = None
_spotify_write_callback: Optional[Callable[[dict[str, Any]], None]] = None
_sc_write_callback: Optional[Callable[[dict[str, Any]], None]] = None


def set_spotify_write_callback(callback: Callable[[dict[str, Any]], None]) -> None:
    global _spotify_write_callback
    _spotify_write_callback = callback


def set_sc_write_callback(callback: Callable[[dict[str, Any]], None]) -> None:
    global _sc_write_callback
    _sc_write_callback = callback


def read_spotify_state_from_file() -> None:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved_state: dict[str, Any] = json.load(f)
                state["volume"] = saved_state.get("volume", state["volume"])
                state["isPlaying"] = saved_state.get("isPlaying", state["isPlaying"])
                state["currentTrack"].update(saved_state.get("currentTrack", {}))
                state["trackDuration"] = saved_state.get("trackDuration", state["trackDuration"])
                state["isShuffling"] = saved_state.get("isShuffling", state["isShuffling"])
                state["repeatStatus"] = saved_state.get("repeatStatus", state["repeatStatus"])
                state["isLiked"] = saved_state.get("isLiked", state["isLiked"])
                logger.info("Server: Loaded Spotify state from state_spotify.json")
        except Exception as e:
            logger.error(f"Server: Error reading Spotify state file: {e}")


def read_sc_state_from_file() -> None:
    if os.path.exists(SC_STATE_FILE):
        try:
            with open(SC_STATE_FILE, "r") as f:
                saved_state: dict[str, Any] = json.load(f)
                state["scTrack"] = saved_state.get("scTrack", state["scTrack"])
                state["scArtist"] = saved_state.get("scArtist", state["scArtist"])
                state["scVolume"] = saved_state.get("scVolume", state["scVolume"])
                logger.info("Server: Loaded SoundCloud state from state_soundcloud.json")
        except Exception as e:
            logger.error(f"Server: Error reading SoundCloud state file: {e}")


async def save_spotify_state_debounced() -> None:
    global _spotify_save_timer
    if _spotify_save_timer:
        _spotify_save_timer.cancel()
    _spotify_save_timer = asyncio.create_task(_actually_save_spotify_after_delay(STATE_SAVE_DEBOUNCE_SECONDS))


async def save_sc_state_debounced() -> None:
    global _sc_save_timer
    if _sc_save_timer:
        _sc_save_timer.cancel()
    _sc_save_timer = asyncio.create_task(_actually_save_sc_after_delay(STATE_SAVE_DEBOUNCE_SECONDS))


_MAX_MS: int = 7 * 24 * 60 * 60 * 1000  # 7 days; rejects absurd clock values


def as_ms(value: Any, default: int = 0) -> int:
    """Coerce a state field to a sane non-negative millisecond value.

    State is fed by WebSocket clients; one bad payload must never turn every
    /api/state request into a 500. Handlers validate before writing, this is
    the last line of defence for restored/legacy state.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(max(0, min(value, _MAX_MS)))


def as_volume(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(0.0, min(1.0, float(value)))


def get_interpolated_track_progress() -> int:
    """Current Spotify position in ms, interpolating from the last progress anchor.

    Raw state["trackProgress"] can be 0-2s stale (the extension only re-anchors
    past PROGRESS_DELTA_THRESHOLD_MS). Fresh clients must anchor on this, not the
    raw value, or they start offset until the next play/pause.
    """
    progress: int = as_ms(state["trackProgress"])
    if not state["isPlaying"]:
        return progress
    anchor: Any = state["trackProgressStartTimestamp"]
    # isPlaying is persisted but the anchor is not, so a fresh process can have
    # isPlaying=True with no anchor. Interpolating from 0 would report the end
    # of the track; the stored position is the only truthful value.
    if not isinstance(anchor, (int, float)) or isinstance(anchor, bool) or anchor <= 0:
        return progress
    elapsed = time.time() * 1000 - anchor
    return int(min(progress + max(0, elapsed), as_ms(state["trackDuration"])))


def get_interpolated_sc_progress() -> int:
    """Same as get_interpolated_track_progress but for SoundCloud."""
    progress: int = as_ms(state["scProgressMs"])
    if not state["scIsPlaying"]:
        return progress
    anchor: Any = state["scProgressStartTimestamp"]
    if not isinstance(anchor, (int, float)) or isinstance(anchor, bool) or anchor <= 0:
        return progress
    elapsed = time.time() * 1000 - anchor
    return int(min(progress + max(0, elapsed), as_ms(state["scDurationMs"])))


def get_album_art_url() -> str:
    """Spotify album art URL, or "" when the cover toggle is off (stream safety)."""
    if not config.get("enableAlbumArt", True):
        return ""
    return state["currentTrack"]["albumArtUrl"]


def get_sc_cover_url() -> str:
    """SoundCloud cover URL, gated by the same cover toggle."""
    if not config.get("enableAlbumArt", True):
        return ""
    return state["scCoverUrl"]


def get_spotify_save_data() -> dict[str, Any]:
    return {
        "volume": round(as_volume(state["volume"], 0.0), 2),
        "isPlaying": state["isPlaying"],
        "currentTrack": state["currentTrack"],
        "trackDuration": state["trackDuration"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"],
    }


def get_sc_save_data() -> dict[str, Any]:
    return {
        "scTrack": state["scTrack"],
        "scArtist": state["scArtist"],
        "scVolume": as_volume(state["scVolume"], 0.0),
    }


async def _actually_save_spotify_after_delay(delay: float) -> None:
    try:
        await asyncio.sleep(delay)
        if _spotify_write_callback:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _spotify_write_callback, get_spotify_save_data())
        logger.info("Server: Saved Spotify state to state_spotify.json (debounced)")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Server: Error in debounced Spotify save: {e}")


async def _actually_save_sc_after_delay(delay: float) -> None:
    try:
        await asyncio.sleep(delay)
        if _sc_write_callback:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _sc_write_callback, get_sc_save_data())
        logger.info("Server: Saved SoundCloud state to state_soundcloud.json (debounced)")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Server: Error in debounced SoundCloud save: {e}")


def cancel_pending_save() -> None:
    global _spotify_save_timer, _sc_save_timer
    if _spotify_save_timer:
        _spotify_save_timer.cancel()
        _spotify_save_timer = None
    if _sc_save_timer:
        _sc_save_timer.cancel()
        _sc_save_timer = None
    logger.debug("Server: Pending save timers cancelled.")



