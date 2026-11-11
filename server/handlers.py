from __future__ import annotations

import asyncio
import json
import math
import re
import time
from typing import Any, Optional

from aiohttp import web
from broadcast import (
    CLIENTS,
    broadcast,
    broadcast_lyrics_update,
    broadcast_playback_update,
    broadcast_progress_update,
    broadcast_soundcloud_state,
    broadcast_spotify_state,
    broadcast_volume_update,
    build_lyrics_message,
    build_sc_state_message,
    build_spotify_state_message,
)
from config import config
from log import logger
from lyrics import fetch_and_broadcast_lyrics
from state import (
    SOURCES,
    get_interpolated_sc_progress,
    get_interpolated_track_progress,
    save_sc_state_debounced,
    save_spotify_state_debounced,
    state,
)

_MAX_MS: int = 7 * 24 * 60 * 60 * 1000


def _finite(value: Any) -> Optional[float]:
    """Return value as float when it is a real, finite number (bool excluded)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _ms(value: Any) -> Optional[int]:
    number = _finite(value)
    if number is None:
        return None
    return int(max(0, min(number, _MAX_MS)))


def _volume(value: Any) -> Optional[float]:
    number = _finite(value)
    if number is None:
        return None
    return max(0.0, min(1.0, number))


def _bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _repeat(value: Any) -> Optional[int]:
    number = _finite(value)
    if number is None or number not in (0, 1, 2):
        return None
    return int(number)


_FIELD_COERCERS: dict[str, Any] = {
    "ms": _ms,
    "volume": _volume,
    "bool": _bool,
    "text": _text,
    "repeat": _repeat,
}


def _apply_fields(data: dict[str, Any], fields: tuple[tuple[str, str, str], ...]) -> None:
    """Copy the valid fields from a source's descriptor into flat state."""
    for wire_key, state_key, kind in fields:
        value = _FIELD_COERCERS[kind](data.get(wire_key))
        if value is not None:
            state[state_key] = value


def _next_volume(current: float, data: dict[str, Any]) -> float:
    step: Optional[float] = _volume(data.get("step"))
    volume_step: float = step if step is not None else 0.05
    if data.get("command") == "volumeUp":
        return min(1.0, current + volume_step)
    if data.get("command") == "volumeDown":
        return max(0.0, current - volume_step)
    volume: Optional[float] = _volume(data.get("volume"))
    return volume if volume is not None else current


async def handle_get_initial_state(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    await ws.send_str(json.dumps(build_spotify_state_message(get_interpolated_track_progress())))
    await ws.send_str(json.dumps(build_sc_state_message(get_interpolated_sc_progress())))
    await ws.send_str(json.dumps(build_lyrics_message()))


# --- Spotify handlers ---

async def handle_spotify_state_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    spotify = SOURCES["spotify"]
    _apply_fields(data, spotify.update_fields)

    track: dict[str, Any] = state["currentTrack"]
    prev_uri: str = track["trackUri"]
    new_uri: str = _text(data.get("trackUri")) or prev_uri

    for key in spotify.track_fields:
        value: Optional[str] = _text(data.get(key))
        if value is not None:
            track[key] = value
    track["trackUri"] = new_uri
    state["trackProgressStartTimestamp"] = time.time() * 1000

    if new_uri and new_uri != prev_uri and new_uri != state["lyrics"]["trackUri"]:
        if config["enableLyrics"]:
            state["lyrics"] = {"trackUri": new_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "karaoke": [], "provider": "", "loading": True}
            await broadcast_lyrics_update()
            task: asyncio.Task[None] = asyncio.create_task(fetch_and_broadcast_lyrics(
                new_uri,
                state["currentTrack"]["trackName"],
                state["currentTrack"]["artistName"],
                state["currentTrack"]["albumName"],
                state["trackDuration"]
            ))
            task.add_done_callback(_lyrics_task_done)
        else:
            state["lyrics"] = {"trackUri": new_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "karaoke": [], "provider": "", "loading": False}
            await broadcast_lyrics_update()

    await save_spotify_state_debounced()
    await broadcast_spotify_state(exclude_ws=ws)


def _lyrics_task_done(task: asyncio.Task[None]) -> None:
    try:
        exc: Optional[BaseException] = task.exception()
        if exc:
            logger.error(f"Lyrics background task failed: {exc}")
    except asyncio.CancelledError:
        pass


async def handle_spotify_volume_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["volume"] = _next_volume(state["volume"], data)
    await save_spotify_state_debounced()
    await broadcast_volume_update()


async def handle_spotify_playback_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    is_playing: Optional[bool] = _bool(data.get("isPlaying"))
    if is_playing is not None:
        state["isPlaying"] = is_playing
    progress: Optional[int] = _ms(data.get("progress"))
    if progress is not None:
        state["trackProgress"] = progress
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await save_spotify_state_debounced()
    await broadcast_playback_update(exclude_ws=ws)


async def handle_spotify_shuffle_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["isShuffling"] = _bool(data.get("isShuffling")) or False
    await save_spotify_state_debounced()
    await broadcast({"type": "shuffleUpdate", "source": "spotify", "isShuffling": state["isShuffling"]}, exclude_ws=ws)


async def handle_spotify_repeat_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    repeat_status: Optional[int] = _repeat(data.get("repeatStatus"))
    state["repeatStatus"] = repeat_status if repeat_status is not None else 0
    await save_spotify_state_debounced()
    await broadcast({"type": "repeatUpdate", "source": "spotify", "repeatStatus": state["repeatStatus"]}, exclude_ws=ws)


async def handle_spotify_like_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["isLiked"] = _bool(data.get("isLiked")) or False
    await save_spotify_state_debounced()
    await broadcast({"type": "likeUpdate", "source": "spotify", "isLiked": state["isLiked"]}, exclude_ws=ws)


async def handle_spotify_progress_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["trackProgress"] = _ms(data.get("progress")) or 0
    state["trackDuration"] = _ms(data.get("duration")) or 0
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await broadcast_progress_update(exclude_ws=ws)


# --- SoundCloud handlers ---

_COVER_SIZE_RE = re.compile(r"-t\d+x\d+")

# Fields that are actually persisted and broadcast to clients. Compared against
# the previous fingerprint so the 500ms SC heartbeat only saves/broadcasts on
# real changes. progressMs / scProgressStartTimestamp are deliberately excluded:
# server state keeps updating every heartbeat (interpolation stays fresh) and
# clients re-anchor via the 1 Hz scProgressUpdate.
_SC_FP_KEYS = (
    "scTrack", "scArtist", "scAlbum", "scId", "scCoverUrl", "scIsPlaying",
    "scDurationMs", "scIsLiked", "scIsShuffling", "scRepeatStatus",
)
_last_sc_fingerprint: Optional[tuple] = None


def _sc_fingerprint() -> tuple:
    # round(volume, 3) absorbs sub-pixel getBoundingClientRect() jitter from
    # _getVolume() so it cannot defeat the gate.
    return (*[state[key] for key in _SC_FP_KEYS], round(state["scVolume"], 3))


async def handle_sc_state_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    global _last_sc_fingerprint

    soundcloud = SOURCES["soundcloud"]
    progress_ms: Optional[int] = _ms(data.get("progressMs"))
    is_playing: Optional[bool] = _bool(data.get("isPlaying"))
    _apply_fields(data, soundcloud.update_fields)

    cover_url: Optional[str] = _text(data.get(soundcloud.cover_field or "coverUrl"))
    if cover_url is not None:
        state["scCoverUrl"] = _COVER_SIZE_RE.sub("-t500x500", cover_url)
    if progress_ms is not None or is_playing is not None:
        state["scProgressStartTimestamp"] = time.time() * 1000

    fingerprint: tuple = _sc_fingerprint()
    if fingerprint != _last_sc_fingerprint:
        _last_sc_fingerprint = fingerprint
        await save_sc_state_debounced()
        await broadcast_soundcloud_state(exclude_ws=ws)


async def handle_sc_volume_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["scVolume"] = _next_volume(state["scVolume"], data)
    await save_sc_state_debounced()
    await broadcast({
        "type": "scVolumeUpdate",
        "source": "soundcloud",
        "volume": state["scVolume"]
    }, exclude_ws=ws)
    logger.debug(f"SC volume updated to {state['scVolume']:.3f}")


# --- Cross-source control ---

async def handle_playback_control(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    await broadcast(data, target_type="spicetify", exclude_ws=ws)


async def handle_sc_playback_control(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    await broadcast(data, target_type="soundcloud", exclude_ws=ws)


async def handle_like_command(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    source = data.get("source", "spotify")
    if source == "soundcloud":
        await broadcast({"type": "scPlaybackControl", "command": "like"}, target_type="soundcloud", exclude_ws=ws)
    else:
        await broadcast({"type": "playbackControl", "command": "like"}, target_type="spicetify", exclude_ws=ws)


async def handle_error(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    message = data.get("message", "Unknown error")
    logger.warning(f"Extension error: {message}")
    await broadcast({"type": "error", "message": message})


async def handle_client_log(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    level = data.get("level", "info")
    message = data.get("message", "")
    client_type = CLIENTS.get(ws, {}).get("type", "unknown")
    log_msg = f"[{client_type}] {message}"
    if level == "error":
        logger.error(log_msg)
    elif level == "warning":
        logger.warning(log_msg)
    elif level == "debug":
        logger.debug(log_msg)
    else:
        logger.info(log_msg)


MESSAGE_HANDLERS: dict[str, Any] = {
    "getInitialState": handle_get_initial_state,
    # Spotify messages
    "stateUpdate": handle_spotify_state_update,
    "trackUpdate": handle_spotify_state_update,
    "volumeUpdate": handle_spotify_volume_update,
    "playbackUpdate": handle_spotify_playback_update,
    "shuffleUpdate": handle_spotify_shuffle_update,
    "repeatUpdate": handle_spotify_repeat_update,
    "likeUpdate": handle_spotify_like_update,
    "progressUpdate": handle_spotify_progress_update,
    "playbackControl": handle_playback_control,
    "like": handle_like_command,
    # SoundCloud messages
    "scStateUpdate": handle_sc_state_update,
    "scVolumeUpdate": handle_sc_volume_update,
    "scPlaybackControl": handle_sc_playback_control,
    # Error
    "error": handle_error,
    # Logging
    "clientLog": handle_client_log
}


async def handle_message(ws: web.WebSocketResponse, message: str) -> None:
    try:
        data: Any = json.loads(message)
    except json.JSONDecodeError:
        logger.warning("Server: Received invalid JSON")
        return

    if not isinstance(data, dict):
        logger.warning("Server: Received non-object JSON message")
        return

    msg_type: Any = data.get("type")
    if not isinstance(msg_type, str):
        logger.warning(f"Server: Received message with invalid type field: {type(msg_type)}")
        return

    handler: Any = MESSAGE_HANDLERS.get(msg_type)
    if handler:
        try:
            await handler(ws, data)
        except Exception:
            logger.exception(f"Server: Handler for '{msg_type}' crashed")
    else:
        logger.warning(f"Server: Received unknown message type: {msg_type}")
