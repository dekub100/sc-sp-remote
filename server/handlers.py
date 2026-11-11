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
    broadcast_now_playing,
    broadcast_soundcloud_state,
    broadcast_spotify_state,
    build_lyrics_message,
    build_now_playing_message,
    build_progress_message,
    build_source_status_message,
)
from config import config
from log import logger
from lyrics import fetch_and_broadcast_lyrics
from protocol import (
    COMMAND_ARGS,
    COMMANDS,
    PROTOCOL_VERSION,
    error_message,
    message_allowed,
)
from state import (
    SOURCE_BY_CLIENT_TYPE,
    SOURCES,
    as_volume,
    save_source_state_debounced,
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


def _now_ms() -> float:
    return time.time() * 1000


def _state_payload(data: dict[str, Any]) -> dict[str, Any]:
    """v2 nests per-source state; reject anything that is not an object."""
    payload = data.get("state")
    return payload if isinstance(payload, dict) else {}


def _source_of(ws: web.WebSocketResponse) -> Optional[str]:
    client_type = CLIENTS.get(ws, {}).get("type")
    if not isinstance(client_type, str):
        return None
    spec = SOURCE_BY_CLIENT_TYPE.get(client_type)
    return spec.key if spec else None


async def _send_error(ws: web.WebSocketResponse, code: str, message: str) -> None:
    logger.warning(f"Server: {code}: {message}")
    try:
        await ws.send_str(json.dumps(error_message(code, message)))
    except Exception:
        # The socket may already be gone; the log line is the useful part.
        pass


async def _require_source(ws: web.WebSocketResponse, data: dict[str, Any]) -> Optional[str]:
    """A source controller may only push state for the source it owns."""
    source = _source_of(ws)
    declared = data.get("source")
    if source is None or (declared is not None and declared != source):
        await _send_error(ws, "forbidden", "source state must come from that source's controller")
        return None
    return source


def _source_connected(source: str) -> bool:
    client_type = SOURCES[source].client_type
    return any(info.get("type") == client_type for info in CLIENTS.values())


def _state_key_for(source: str, wire_key: str) -> Optional[str]:
    for wire, state_key, _kind in SOURCES[source].update_fields:
        if wire == wire_key:
            return state_key
    return None


async def handle_get_initial_state(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    for spec in SOURCES.values():
        await ws.send_str(json.dumps(build_now_playing_message(spec.key)))
    await ws.send_str(json.dumps(build_lyrics_message()))
    for spec in SOURCES.values():
        await ws.send_str(json.dumps(build_source_status_message(spec.key, _source_connected(spec.key))))


# --- Source state (Spotify) ---

async def _apply_spotify_now_playing(ws: web.WebSocketResponse, payload: dict[str, Any]) -> None:
    spotify = SOURCES["spotify"]
    _apply_fields(payload, spotify.update_fields)

    track: dict[str, Any] = state["currentTrack"]
    prev_uri: str = track["trackUri"]
    new_uri: str = _text(payload.get("trackUri")) or prev_uri

    for key in spotify.track_fields:
        value: Optional[str] = _text(payload.get(key))
        if value is not None:
            track[key] = value
    track["trackUri"] = new_uri
    state["trackProgressStartTimestamp"] = _now_ms()

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

    await save_source_state_debounced("spotify")
    await broadcast_spotify_state(exclude_ws=ws)


def _lyrics_task_done(task: asyncio.Task[None]) -> None:
    try:
        exc: Optional[BaseException] = task.exception()
        if exc:
            logger.error(f"Lyrics background task failed: {exc}")
    except asyncio.CancelledError:
        pass


# --- Source state (SoundCloud) ---

_COVER_SIZE_RE = re.compile(r"-t\d+x\d+")

# Fields that are actually persisted and broadcast to clients. Compared against
# the previous fingerprint so the 500ms SC heartbeat only saves/broadcasts on
# real changes. progress / scProgressStartTimestamp are deliberately excluded:
# server state keeps updating every heartbeat (interpolation stays fresh) and
# clients re-anchor via the 1 Hz progress message.
_SC_FP_KEYS = (
    "scTrack", "scArtist", "scAlbum", "scId", "scCoverUrl", "scIsPlaying",
    "scDurationMs", "scIsLiked", "scIsShuffling", "scRepeatStatus",
)
_last_sc_fingerprint: Optional[tuple] = None


def _sc_fingerprint() -> tuple:
    # round(volume, 3) absorbs sub-pixel getBoundingClientRect() jitter from
    # _getVolume() so it cannot defeat the gate.
    return (*[state[key] for key in _SC_FP_KEYS], round(state["scVolume"], 3))


async def _apply_soundcloud_now_playing(ws: web.WebSocketResponse, payload: dict[str, Any]) -> None:
    global _last_sc_fingerprint

    soundcloud = SOURCES["soundcloud"]
    _apply_fields(payload, soundcloud.update_fields)

    cover_url: Optional[str] = _text(payload.get(soundcloud.cover_field or "coverUrl"))
    if cover_url is not None:
        state["scCoverUrl"] = _COVER_SIZE_RE.sub("-t500x500", cover_url)
    if "progress" in payload or "isPlaying" in payload:
        state["scProgressStartTimestamp"] = _now_ms()

    fingerprint: tuple = _sc_fingerprint()
    if fingerprint != _last_sc_fingerprint:
        _last_sc_fingerprint = fingerprint
        await save_source_state_debounced("soundcloud")
        await broadcast_soundcloud_state(exclude_ws=ws)


# --- Source state dispatch ---

async def handle_now_playing(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    source = await _require_source(ws, data)
    if source is None:
        return
    payload = _state_payload(data)
    if source == "spotify":
        await _apply_spotify_now_playing(ws, payload)
    else:
        await _apply_soundcloud_now_playing(ws, payload)


async def handle_volume(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    source = await _require_source(ws, data)
    if source is None:
        return
    state_key = _state_key_for(source, "volume")
    if state_key is None:
        return
    _apply_fields(_state_payload(data), (("volume", state_key, "volume"),))
    await save_source_state_debounced(source)
    await broadcast_now_playing(source, exclude_ws=ws)


async def handle_playback(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    source = await _require_source(ws, data)
    if source is None:
        return
    spec = SOURCES[source]
    _apply_fields(_state_payload(data), (
        ("isPlaying", spec.playing_key, "bool"),
        ("progress", spec.progress_key, "ms"),
    ))
    state[spec.anchor_key] = _now_ms()
    await save_source_state_debounced(source)
    await broadcast_now_playing(source, exclude_ws=ws)


async def handle_progress(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    source = await _require_source(ws, data)
    if source is None:
        return
    spec = SOURCES[source]
    _apply_fields(_state_payload(data), (
        ("progress", spec.progress_key, "ms"),
        ("duration", spec.duration_key, "ms"),
    ))
    state[spec.anchor_key] = _now_ms()
    await broadcast(build_progress_message(source), exclude_ws=ws)


async def _handle_single_field(
    ws: web.WebSocketResponse,
    data: dict[str, Any],
    wire_key: str,
    kind: str,
) -> None:
    source = await _require_source(ws, data)
    if source is None:
        return
    state_key = _state_key_for(source, wire_key)
    if state_key is None:
        return
    _apply_fields(_state_payload(data), ((wire_key, state_key, kind),))
    await save_source_state_debounced(source)
    await broadcast_now_playing(source, exclude_ws=ws)


async def handle_shuffle(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    await _handle_single_field(ws, data, "isShuffling", "bool")


async def handle_repeat(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    await _handle_single_field(ws, data, "repeatStatus", "repeat")


async def handle_like(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    await _handle_single_field(ws, data, "isLiked", "bool")


# --- Controller commands ---

def _command_args(command: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Validate and whitelist a command's arguments; None means reject it."""
    args: dict[str, Any] = {}
    for key in COMMAND_ARGS.get(command, ()):
        raw = data.get(key)
        if key == "volume":
            volume = _volume(raw)
            if volume is None:
                return None
            args["volume"] = volume
        elif key == "position":
            position = _ms(raw)
            if position is None:
                return None
            args["position"] = position
        elif key == "offset":
            offset = _ms(raw)
            if not offset:
                return None
            args["offset"] = offset
        elif key == "step":
            if raw is None:
                args["step"] = 0.05
            else:
                step = _volume(raw)
                if not step:
                    return None
                args["step"] = step
    return args


async def handle_command(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    command = data.get("command")
    if not isinstance(command, str) or command not in COMMANDS:
        await _send_error(ws, "invalid_command", f"unknown command: {command!r}")
        return
    source = data.get("source", "spotify")
    if not isinstance(source, str) or source not in SOURCES:
        await _send_error(ws, "invalid_source", f"unknown source: {source!r}")
        return
    args = _command_args(command, data)
    if args is None:
        await _send_error(ws, "invalid_command", f"missing or invalid arguments for '{command}'")
        return
    if source == "soundcloud" and command in ("volumeUp", "volumeDown"):
        # The SC bridge has no native step API, so translate the relative
        # command into an absolute setVolume using the volume it last reported.
        step = float(args.get("step", 0.05))
        current = as_volume(state[SOURCES["soundcloud"].volume_key])
        volume = min(1.0, current + step) if command == "volumeUp" else max(0.0, current - step)
        command = "setVolume"
        args = {"volume": volume}
    await broadcast(
        {
            "v": PROTOCOL_VERSION,
            "type": "command",
            "source": source,
            "command": command,
            **args,
        },
        target_type=SOURCES[source].client_type,
        exclude_ws=ws,
    )


# --- Error and logging ---

async def handle_error(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    message = data.get("message", "Unknown error")
    logger.warning(f"Extension error: {message}")
    await broadcast(error_message("client_error", str(message)))


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
    # Source -> server state
    "nowPlaying": handle_now_playing,
    "volume": handle_volume,
    "playback": handle_playback,
    "progress": handle_progress,
    "shuffle": handle_shuffle,
    "repeat": handle_repeat,
    "like": handle_like,
    # Controller -> server -> source
    "command": handle_command,
    # Diagnostics
    "error": handle_error,
    "clientLog": handle_client_log,
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

    version: Any = data.get("v")
    if version is not None and version != PROTOCOL_VERSION:
        await _send_error(ws, "protocol_version", f"protocol v{PROTOCOL_VERSION} required")
        return

    handler: Any = MESSAGE_HANDLERS.get(msg_type)
    if handler is None:
        await _send_error(ws, "unknown_type", f"unknown message type: '{msg_type}'")
        return

    client_type: str = str(CLIENTS.get(ws, {}).get("type", "unknown"))
    if not message_allowed(client_type, msg_type):
        await _send_error(
            ws,
            "forbidden",
            f"'{msg_type}' is not allowed for client type '{client_type}'",
        )
        return

    try:
        await handler(ws, data)
    except Exception:
        logger.exception(f"Server: Handler for '{msg_type}' crashed")
