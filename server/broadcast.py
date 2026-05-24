from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from aiohttp import web
from config import PROGRESS_BROADCAST_INTERVAL
from log import logger
from state import state

CLIENTS: dict[web.WebSocketResponse, dict[str, Any]] = {}

spicetify_client: Optional[web.WebSocketResponse] = None


def set_spicetify_client(ws: Optional[web.WebSocketResponse]) -> None:
    global spicetify_client
    spicetify_client = ws


def get_spicetify_client() -> Optional[web.WebSocketResponse]:
    return spicetify_client


async def broadcast(
    message: dict[str, Any],
    exclude_ws: Optional[web.WebSocketResponse] = None,
    target_type: Optional[str] = None
) -> None:
    if not CLIENTS:
        return
    msg: str = json.dumps(message)
    for ws, info in list(CLIENTS.items()):
        if ws == exclude_ws:
            continue
        if target_type and info.get("type") != target_type:
            continue
        try:
            await ws.send_str(msg)
        except ConnectionResetError:
            logger.debug(f"Broadcast: Client disconnected ({info.get('type', 'unknown')})")
            CLIENTS.pop(ws, None)
        except ConnectionAbortedError:
            logger.debug(f"Broadcast: Connection aborted ({info.get('type', 'unknown')})")
            CLIENTS.pop(ws, None)
        except Exception:
            logger.warning(f"Broadcast: Removing dead client ({info.get('type', 'unknown')})")
            CLIENTS.pop(ws, None)


async def broadcast_current_state(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    full_state_message: dict[str, Any] = {
        "type": "stateUpdate",
        "volume": state["volume"],
        "isPlaying": state["isPlaying"],
        "trackName": state["currentTrack"]["trackName"],
        "artistName": state["currentTrack"]["artistName"],
        "albumName": state["currentTrack"]["albumName"],
        "trackUri": state["currentTrack"]["trackUri"],
        "albumUri": state["currentTrack"]["albumUri"],
        "albumArtUrl": state["currentTrack"]["albumArtUrl"],
        "progress": state["trackProgress"],
        "duration": state["trackDuration"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"],
        "timestamp": time.time() * 1000
    }
    await broadcast(full_state_message, exclude_ws)


async def broadcast_volume_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    await broadcast({
        "type": "volumeUpdate",
        "volume": state["volume"]
    }, exclude_ws)


async def broadcast_playback_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    await broadcast({
        "type": "playbackUpdate",
        "isPlaying": state["isPlaying"],
        "progress": state["trackProgress"],
        "timestamp": time.time() * 1000
    }, exclude_ws)


async def broadcast_progress_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    progress_message: dict[str, Any] = {
        "type": "progressUpdate",
        "progress": state["trackProgress"],
        "duration": state["trackDuration"],
        "isPlaying": state["isPlaying"],
        "timestamp": time.time() * 1000
    }
    await broadcast(progress_message, exclude_ws)


async def broadcast_lyrics_update() -> None:
    lyrics: dict[str, Any] = state["lyrics"]
    await broadcast({
        "type": "lyricsUpdate",
        "available": lyrics["available"],
        "instrumental": lyrics["instrumental"],
        "synced": lyrics["synced"],
        "plain": lyrics["plain"],
        "loading": lyrics["loading"]
    })


async def _compute_and_broadcast_progress() -> None:
    now: float = time.time() * 1000
    elapsed: float = now - state["trackProgressStartTimestamp"]
    interpolated: float = min(state["trackProgress"] + elapsed, state["trackDuration"])
    await broadcast({
        "type": "progressUpdate",
        "progress": int(interpolated),
        "duration": state["trackDuration"],
        "isPlaying": True,
        "timestamp": now
    })


async def start_progress_broadcasting() -> None:
    while True:
        if state["isPlaying"]:
            await _compute_and_broadcast_progress()
        await asyncio.sleep(PROGRESS_BROADCAST_INTERVAL)


async def broadcast_queue_update() -> None:
    await broadcast({
        "type": "queueUpdate",
        "queue": state["queue"]["nextTracks"],
        "queueRevision": state["queue"]["queueRevision"]
    })
