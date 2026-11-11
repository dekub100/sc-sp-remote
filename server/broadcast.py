from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from aiohttp import web
from config import PROGRESS_BROADCAST_INTERVAL
from log import logger
from state import (
    SOURCES,
    as_ms,
    as_volume,
    get_album_art_url,
    get_interpolated_progress,
    get_sc_cover_url,
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


def build_spotify_state_message(progress: int) -> dict[str, Any]:
    return {
        "type": "stateUpdate",
        "source": "spotify",
        "volume": as_volume(state["volume"]),
        "isPlaying": state["isPlaying"],
        "trackName": state["currentTrack"]["trackName"],
        "artistName": state["currentTrack"]["artistName"],
        "albumName": state["currentTrack"]["albumName"],
        "trackUri": state["currentTrack"]["trackUri"],
        "albumUri": state["currentTrack"]["albumUri"],
        "artistUri": state["currentTrack"].get("artistUri", ""),
        "albumArtUrl": get_album_art_url(),
        "progress": as_ms(progress),
        "duration": as_ms(state["trackDuration"]),
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"],
        "timestamp": time.time() * 1000
    }


def build_sc_state_message(progress_ms: int) -> dict[str, Any]:
    return {
        "type": "scStateUpdate",
        "source": "soundcloud",
        "track": state["scTrack"],
        "artist": state["scArtist"],
        "album": state["scAlbum"],
        "id": state["scId"],
        "coverUrl": get_sc_cover_url(),
        "isPlaying": state["scIsPlaying"],
        "progressMs": as_ms(progress_ms),
        "durationMs": as_ms(state["scDurationMs"]),
        "volume": as_volume(state["scVolume"]),
        "isLiked": state["scIsLiked"],
        "isShuffling": state["scIsShuffling"],
        "repeatStatus": state["scRepeatStatus"],
        "timestamp": time.time() * 1000
    }


async def broadcast_spotify_state(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    await broadcast(build_spotify_state_message(state["trackProgress"]), exclude_ws)


async def broadcast_soundcloud_state(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    await broadcast(build_sc_state_message(state["scProgressMs"]), exclude_ws)


async def broadcast_volume_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    for spec in SOURCES.values():
        await broadcast({
            "type": spec.volume_msg_type,
            "source": spec.key,
            "volume": state[spec.volume_key]
        }, exclude_ws)


async def broadcast_playback_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    now = time.time() * 1000
    for spec in SOURCES.values():
        await broadcast({
            "type": spec.playback_msg_type,
            "source": spec.key,
            "isPlaying": state[spec.playing_key],
            spec.progress_field: state[spec.progress_key],
            "timestamp": now
        }, exclude_ws)


async def broadcast_progress_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    now = time.time() * 1000
    for spec in SOURCES.values():
        await broadcast({
            "type": spec.progress_msg_type,
            "source": spec.key,
            spec.progress_field: state[spec.progress_key],
            spec.duration_field: state[spec.duration_key],
            "isPlaying": state[spec.playing_key],
            "timestamp": now
        }, exclude_ws)


def build_lyrics_message() -> dict[str, Any]:
    """Single source of truth for the lyricsUpdate payload (initial + broadcast).

    Clients rely on `loading` to show "downloading" instead of "no lyrics".
    """
    lyrics: dict[str, Any] = state["lyrics"]
    return {
        "type": "lyricsUpdate",
        "available": lyrics.get("available", False),
        "instrumental": lyrics.get("instrumental", False),
        "synced": lyrics.get("synced", []),
        "plain": lyrics.get("plain", ""),
        "karaoke": lyrics.get("karaoke", []),
        "provider": lyrics.get("provider", ""),
        "loading": lyrics.get("loading", False)
    }


async def broadcast_lyrics_update() -> None:
    await broadcast(build_lyrics_message())


async def broadcast_source_status(source: str, connected: bool) -> None:
    """Tell clients whether a playback source's controller is attached.

    Unlike the old "disconnect means paused" rule this carries no playback
    state, so a reconnect can't pause anything.
    """
    await broadcast({"type": "sourceStatus", "source": source, "connected": connected})


async def _compute_and_broadcast_progress() -> None:
    now: float = time.time() * 1000
    for spec in SOURCES.values():
        if not state[spec.playing_key]:
            continue
        await broadcast({
            "type": spec.progress_msg_type,
            "source": spec.key,
            spec.progress_field: get_interpolated_progress(spec.key, now),
            spec.duration_field: state[spec.duration_key],
            "isPlaying": state[spec.playing_key],
            "timestamp": now
        })


async def start_progress_broadcasting() -> None:
    while True:
        if state["isPlaying"] or state["scIsPlaying"]:
            await _compute_and_broadcast_progress()
        await asyncio.sleep(PROGRESS_BROADCAST_INTERVAL)



