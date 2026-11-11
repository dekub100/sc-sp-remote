from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from aiohttp import web
from config import config
from log import logger
from protocol import PROTOCOL_VERSION
from state import (
    SOURCES,
    as_ms,
    as_volume,
    get_interpolated_progress,
    get_source_cover_url,
    state,
)

CLIENTS: dict[web.WebSocketResponse, dict[str, Any]] = {}

# A client whose TCP buffer is full (paused OBS source, sleeping laptop, hung
# browser tab) must never block a broadcast: send_str awaits transport drain.
BROADCAST_SEND_TIMEOUT_SECONDS: float = 1.0


async def _send_to_client(
    ws: web.WebSocketResponse,
    info: dict[str, Any],
    msg: str
) -> Optional[web.WebSocketResponse]:
    try:
        await asyncio.wait_for(ws.send_str(msg), timeout=BROADCAST_SEND_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(f"Broadcast: Dropping unresponsive client ({info.get('type', 'unknown')})")
        return ws
    except ConnectionResetError:
        logger.debug(f"Broadcast: Client disconnected ({info.get('type', 'unknown')})")
        return ws
    except ConnectionAbortedError:
        logger.debug(f"Broadcast: Connection aborted ({info.get('type', 'unknown')})")
        return ws
    except Exception:
        logger.warning(f"Broadcast: Removing dead client ({info.get('type', 'unknown')})")
        return ws
    return None


async def broadcast(
    message: dict[str, Any],
    exclude_ws: Optional[web.WebSocketResponse] = None,
    target_type: Optional[str] = None
) -> None:
    if not CLIENTS:
        return
    msg: str = json.dumps(message)
    targets: list[tuple[web.WebSocketResponse, dict[str, Any]]] = [
        (ws, info) for ws, info in list(CLIENTS.items())
        if ws != exclude_ws and not (target_type and info.get("type") != target_type)
    ]
    if not targets:
        return
    # Parallel fan-out: one buffered client must not stall the rest.
    results = await asyncio.gather(*(_send_to_client(ws, info, msg) for ws, info in targets))
    for dead in results:
        if dead is not None:
            CLIENTS.pop(dead, None)


def _envelope(msg_type: str, **fields: Any) -> dict[str, Any]:
    return {"v": PROTOCOL_VERSION, "type": msg_type, **fields}


def build_spotify_state_message(progress: int) -> dict[str, Any]:
    return _envelope(
        "nowPlaying",
        source="spotify",
        state={
            "volume": as_volume(state["volume"]),
            "isPlaying": state["isPlaying"],
            "trackName": state["currentTrack"]["trackName"],
            "artistName": state["currentTrack"]["artistName"],
            "albumName": state["currentTrack"]["albumName"],
            "trackUri": state["currentTrack"]["trackUri"],
            "albumUri": state["currentTrack"]["albumUri"],
            "artistUri": state["currentTrack"].get("artistUri", ""),
            "albumArtUrl": get_source_cover_url("spotify"),
            "progress": as_ms(progress),
            "duration": as_ms(state["trackDuration"]),
            "isShuffling": state["isShuffling"],
            "repeatStatus": state["repeatStatus"],
            "isLiked": state["isLiked"],
            "timestamp": time.time() * 1000,
        },
    )


def build_sc_state_message(progress_ms: int) -> dict[str, Any]:
    return _envelope(
        "nowPlaying",
        source="soundcloud",
        state={
            "track": state["scTrack"],
            "artist": state["scArtist"],
            "album": state["scAlbum"],
            "id": state["scId"],
            "coverUrl": get_source_cover_url("soundcloud"),
            "isPlaying": state["scIsPlaying"],
            "progress": as_ms(progress_ms),
            "duration": as_ms(state["scDurationMs"]),
            "volume": as_volume(state["scVolume"]),
            "isLiked": state["scIsLiked"],
            "isShuffling": state["scIsShuffling"],
            "repeatStatus": state["scRepeatStatus"],
            "timestamp": time.time() * 1000,
        },
    )


def build_now_playing_message(source: str) -> dict[str, Any]:
    if source == "soundcloud":
        return build_sc_state_message(state["scProgressMs"])
    return build_spotify_state_message(state["trackProgress"])


def build_progress_message(source: str, now: Optional[float] = None) -> dict[str, Any]:
    spec = SOURCES[source]
    timestamp: float = now if now is not None else time.time() * 1000
    return _envelope(
        "progress",
        source=source,
        state={
            "progress": get_interpolated_progress(source, timestamp),
            "duration": as_ms(state[spec.duration_key]),
            "isPlaying": state[spec.playing_key],
            "timestamp": timestamp,
        },
    )


async def broadcast_now_playing(
    source: str,
    exclude_ws: Optional[web.WebSocketResponse] = None
) -> None:
    await broadcast(build_now_playing_message(source), exclude_ws)


async def broadcast_spotify_state(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    await broadcast_now_playing("spotify", exclude_ws)


async def broadcast_soundcloud_state(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    await broadcast_now_playing("soundcloud", exclude_ws)


# Kept as the internal "all sources changed" helpers. In v2 a state change is
# always a full `nowPlaying` snapshot, so volume/playback are not separate
# message types on the wire.
async def broadcast_volume_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    for spec in SOURCES.values():
        await broadcast_now_playing(spec.key, exclude_ws)


async def broadcast_playback_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    for spec in SOURCES.values():
        await broadcast_now_playing(spec.key, exclude_ws)


async def broadcast_progress_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    now: float = time.time() * 1000
    for spec in SOURCES.values():
        await broadcast(build_progress_message(spec.key, now), exclude_ws)


def build_lyrics_message() -> dict[str, Any]:
    """Single source of truth for the lyrics payload (initial + broadcast).

    Clients rely on `loading` to show "downloading" instead of "no lyrics".
    """
    lyrics: dict[str, Any] = state["lyrics"]
    return _envelope(
        "lyrics",
        state={
            "available": lyrics.get("available", False),
            "instrumental": lyrics.get("instrumental", False),
            "synced": lyrics.get("synced", []),
            "plain": lyrics.get("plain", ""),
            "karaoke": lyrics.get("karaoke", []),
            "provider": lyrics.get("provider", ""),
            "loading": lyrics.get("loading", False),
        },
    )


async def broadcast_lyrics_update() -> None:
    await broadcast(build_lyrics_message())


def build_source_status_message(source: str, connected: bool) -> dict[str, Any]:
    return _envelope("sourceStatus", source=source, state={"connected": connected})


async def broadcast_source_status(source: str, connected: bool) -> None:
    """Tell clients whether a playback source's controller is attached.

    Unlike the old "disconnect means paused" rule this carries no playback
    state, so a reconnect can't pause anything.
    """
    await broadcast(build_source_status_message(source, connected))


async def _compute_and_broadcast_progress() -> None:
    now: float = time.time() * 1000
    for spec in SOURCES.values():
        if not state[spec.playing_key]:
            continue
        await broadcast(build_progress_message(spec.key, now))


async def start_progress_broadcasting() -> None:
    while True:
        if any(state[spec.playing_key] for spec in SOURCES.values()):
            await _compute_and_broadcast_progress()
        # Read at use time so the admin edit applies without a restart. A
        # hand-edited bad value must not kill the progress loop.
        try:
            interval: float = float(config.get("progressBroadcastInterval", 1.0))
        except (TypeError, ValueError):
            interval = 1.0
        await asyncio.sleep(max(0.1, interval))
