from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from aiohttp import web
from config import PROGRESS_BROADCAST_INTERVAL
from log import logger
from state import get_album_art_url, get_sc_cover_url, state

CLIENTS: dict[web.WebSocketResponse, dict[str, Any]] = {}

spicetify_client: Optional[web.WebSocketResponse] = None
soundcloud_client: Optional[web.WebSocketResponse] = None


def set_spicetify_client(ws: Optional[web.WebSocketResponse]) -> None:
    global spicetify_client
    spicetify_client = ws


def get_spicetify_client() -> Optional[web.WebSocketResponse]:
    return spicetify_client


def set_soundcloud_client(ws: Optional[web.WebSocketResponse]) -> None:
    global soundcloud_client
    soundcloud_client = ws


def get_soundcloud_client() -> Optional[web.WebSocketResponse]:
    return soundcloud_client


async def broadcast(
    message: dict[str, Any],
    exclude_ws: Optional[web.WebSocketResponse] = None,
    target_type: Optional[str] = None
) -> None:
    if not CLIENTS:
        return
    msg: str = json.dumps(message)
    dead: list[web.WebSocketResponse] = []
    for ws, info in list(CLIENTS.items()):
        if ws == exclude_ws:
            continue
        if target_type and info.get("type") != target_type:
            continue
        try:
            await ws.send_str(msg)
        except ConnectionResetError:
            logger.debug(f"Broadcast: Client disconnected ({info.get('type', 'unknown')})")
            dead.append(ws)
        except ConnectionAbortedError:
            logger.debug(f"Broadcast: Connection aborted ({info.get('type', 'unknown')})")
            dead.append(ws)
        except Exception:
            logger.warning(f"Broadcast: Removing dead client ({info.get('type', 'unknown')})")
            dead.append(ws)
    for ws in dead:
        CLIENTS.pop(ws, None)


async def broadcast_spotify_state(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    full_state_message: dict[str, Any] = {
        "type": "stateUpdate",
        "source": "spotify",
        "volume": state["volume"],
        "isPlaying": state["isPlaying"],
        "trackName": state["currentTrack"]["trackName"],
        "artistName": state["currentTrack"]["artistName"],
        "albumName": state["currentTrack"]["albumName"],
        "trackUri": state["currentTrack"]["trackUri"],
        "albumUri": state["currentTrack"]["albumUri"],
        "albumArtUrl": get_album_art_url(),
        "progress": state["trackProgress"],
        "duration": state["trackDuration"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"],
        "timestamp": time.time() * 1000
    }
    await broadcast(full_state_message, exclude_ws)


async def broadcast_soundcloud_state(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    sc_state_message: dict[str, Any] = {
        "type": "scStateUpdate",
        "source": "soundcloud",
        "track": state["scTrack"],
        "artist": state["scArtist"],
        "album": state["scAlbum"],
        "id": state["scId"],
        "coverUrl": get_sc_cover_url(),
        "isPlaying": state["scIsPlaying"],
        "progressMs": state["scProgressMs"],
        "durationMs": state["scDurationMs"],
        "volume": state["scVolume"],
        "isLiked": state["scIsLiked"],
        "timestamp": time.time() * 1000
    }
    await broadcast(sc_state_message, exclude_ws)


async def broadcast_volume_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    await broadcast({
        "type": "volumeUpdate",
        "source": "spotify",
        "volume": state["volume"]
    }, exclude_ws)
    await broadcast({
        "type": "scVolumeUpdate",
        "source": "soundcloud",
        "volume": state["scVolume"]
    }, exclude_ws)


async def broadcast_playback_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    now = time.time() * 1000
    await broadcast({
        "type": "playbackUpdate",
        "source": "spotify",
        "isPlaying": state["isPlaying"],
        "progress": state["trackProgress"],
        "timestamp": now
    }, exclude_ws)
    await broadcast({
        "type": "scPlaybackUpdate",
        "source": "soundcloud",
        "isPlaying": state["scIsPlaying"],
        "progressMs": state["scProgressMs"],
        "timestamp": now
    }, exclude_ws)


async def broadcast_progress_update(exclude_ws: Optional[web.WebSocketResponse] = None) -> None:
    now = time.time() * 1000
    await broadcast({
        "type": "progressUpdate",
        "source": "spotify",
        "progress": state["trackProgress"],
        "duration": state["trackDuration"],
        "isPlaying": state["isPlaying"],
        "timestamp": now
    }, exclude_ws)
    await broadcast({
        "type": "scProgressUpdate",
        "source": "soundcloud",
        "progressMs": state["scProgressMs"],
        "durationMs": state["scDurationMs"],
        "isPlaying": state["scIsPlaying"],
        "timestamp": now
    }, exclude_ws)


async def broadcast_lyrics_update() -> None:
    lyrics: dict[str, Any] = state["lyrics"]
    await broadcast({
        "type": "lyricsUpdate",
        "available": lyrics["available"],
        "instrumental": lyrics["instrumental"],
        "synced": lyrics["synced"],
        "plain": lyrics["plain"],
        "karaoke": lyrics.get("karaoke", []),
        "provider": lyrics.get("provider", ""),
        "loading": lyrics["loading"]
    })


async def _compute_and_broadcast_progress() -> None:
    now: float = time.time() * 1000
    spotify_elapsed: float = now - state["trackProgressStartTimestamp"]
    spotify_interpolated: float = min(state["trackProgress"] + spotify_elapsed, state["trackDuration"])
    await broadcast({
        "type": "progressUpdate",
        "source": "spotify",
        "progress": int(spotify_interpolated),
        "duration": state["trackDuration"],
        "isPlaying": state["isPlaying"],
        "timestamp": now
    })
    sc_elapsed: float = now - state["scProgressStartTimestamp"]
    sc_interpolated: float = min(state["scProgressMs"] + sc_elapsed, state["scDurationMs"])
    await broadcast({
        "type": "scProgressUpdate",
        "source": "soundcloud",
        "progressMs": int(sc_interpolated),
        "durationMs": state["scDurationMs"],
        "isPlaying": state["scIsPlaying"],
        "timestamp": now
    })


async def start_progress_broadcasting() -> None:
    while True:
        if state["isPlaying"] or state["scIsPlaying"]:
            await _compute_and_broadcast_progress()
        await asyncio.sleep(PROGRESS_BROADCAST_INTERVAL)



