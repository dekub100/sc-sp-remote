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


async def handle_get_initial_state(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    await ws.send_str(json.dumps(build_spotify_state_message(get_interpolated_track_progress())))
    await ws.send_str(json.dumps(build_sc_state_message(get_interpolated_sc_progress())))
    await ws.send_str(json.dumps(build_lyrics_message()))


# --- Spotify handlers ---

async def handle_spotify_state_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    volume: Optional[float] = _volume(data.get("volume"))
    if volume is not None:
        state["volume"] = volume
    is_playing: Optional[bool] = _bool(data.get("isPlaying"))
    if is_playing is not None:
        state["isPlaying"] = is_playing
    is_shuffling: Optional[bool] = _bool(data.get("isShuffling"))
    if is_shuffling is not None:
        state["isShuffling"] = is_shuffling
    repeat_status: Optional[int] = _repeat(data.get("repeatStatus"))
    if repeat_status is not None:
        state["repeatStatus"] = repeat_status
    is_liked: Optional[bool] = _bool(data.get("isLiked"))
    if is_liked is not None:
        state["isLiked"] = is_liked

    track: dict[str, Any] = state["currentTrack"]
    prev_uri: str = track["trackUri"]
    new_uri: str = _text(data.get("trackUri")) or prev_uri

    for key in ("trackName", "artistName", "albumName", "albumUri", "artistUri", "albumArtUrl"):
        value: Optional[str] = _text(data.get(key))
        if value is not None:
            track[key] = value
    track["trackUri"] = new_uri

    duration: Optional[int] = _ms(data.get("duration"))
    if duration is not None:
        state["trackDuration"] = duration
    progress: Optional[int] = _ms(data.get("progress"))
    if progress is not None:
        state["trackProgress"] = progress
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
    step: Optional[float] = _volume(data.get("step"))
    volume_step: float = step if step is not None else 0.05
    if data.get("command") == "volumeUp":
        state["volume"] = min(1.0, state["volume"] + volume_step)
    elif data.get("command") == "volumeDown":
        state["volume"] = max(0.0, state["volume"] - volume_step)
    else:
        volume: Optional[float] = _volume(data.get("volume"))
        if volume is not None:
            state["volume"] = volume
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

    for key, state_key in (("track", "scTrack"), ("artist", "scArtist"), ("album", "scAlbum"), ("id", "scId")):
        text_value: Optional[str] = _text(data.get(key))
        if text_value is not None:
            state[state_key] = text_value
    cover_url: Optional[str] = _text(data.get("coverUrl"))
    if cover_url is not None:
        state["scCoverUrl"] = _COVER_SIZE_RE.sub("-t500x500", cover_url)
    is_playing: Optional[bool] = _bool(data.get("isPlaying"))
    if is_playing is not None:
        state["scIsPlaying"] = is_playing
    progress_ms: Optional[int] = _ms(data.get("progressMs"))
    if progress_ms is not None:
        state["scProgressMs"] = progress_ms
    duration_ms: Optional[int] = _ms(data.get("durationMs"))
    if duration_ms is not None:
        state["scDurationMs"] = duration_ms
    volume: Optional[float] = _volume(data.get("volume"))
    if volume is not None:
        state["scVolume"] = volume
    is_liked: Optional[bool] = _bool(data.get("isLiked"))
    if is_liked is not None:
        state["scIsLiked"] = is_liked
    is_shuffling: Optional[bool] = _bool(data.get("isShuffling"))
    if is_shuffling is not None:
        state["scIsShuffling"] = is_shuffling
    repeat_status: Optional[int] = _repeat(data.get("repeatStatus"))
    if repeat_status is not None:
        state["scRepeatStatus"] = repeat_status
    if progress_ms is not None or is_playing is not None:
        state["scProgressStartTimestamp"] = time.time() * 1000

    fingerprint: tuple = _sc_fingerprint()
    if fingerprint != _last_sc_fingerprint:
        _last_sc_fingerprint = fingerprint
        await save_sc_state_debounced()
        await broadcast_soundcloud_state(exclude_ws=ws)


async def handle_sc_volume_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    step: Optional[float] = _volume(data.get("step"))
    volume_step: float = step if step is not None else 0.05
    if data.get("command") == "volumeUp":
        state["scVolume"] = min(1.0, state["scVolume"] + volume_step)
    elif data.get("command") == "volumeDown":
        state["scVolume"] = max(0.0, state["scVolume"] - volume_step)
    else:
        volume: Optional[float] = _volume(data.get("volume"))
        if volume is not None:
            state["scVolume"] = volume
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
