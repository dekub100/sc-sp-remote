from __future__ import annotations

import asyncio
import json
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
    broadcast_queue_update,
    broadcast_soundcloud_state,
    broadcast_spotify_state,
    broadcast_volume_update,
    set_soundcloud_client,
    set_spicetify_client,
)
from config import config
from log import logger
from lyrics import fetch_and_broadcast_lyrics
from state import (
    check_rate_limit,
    is_queue_full,
    parse_track_input,
    pendingQueueMeta,
    save_sc_state_debounced,
    save_spotify_state_debounced,
    state,
)

KNOWN_CLIENT_TYPES: frozenset[str] = frozenset({"spicetify", "soundcloud", "website", "obs"})
PROTOCOL_VERSION: int = 1


async def handle_register(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    client_type: str = data.get("client", "unknown")
    client_version: int = data.get("protocolVersion", 0)
    if client_type not in KNOWN_CLIENT_TYPES:
        logger.warning(f"Unknown client type registration: {client_type}")
        client_type = "unknown"
    CLIENTS[ws]["type"] = client_type
    CLIENTS[ws]["protocolVersion"] = client_version
    if client_type == "spicetify":
        set_spicetify_client(ws)
    elif client_type == "soundcloud":
        set_soundcloud_client(ws)
    logger.info(f"Client registered as: {client_type} (protocol v{client_version})")
    await ws.send_str(json.dumps({"type": "registered", "protocolVersion": PROTOCOL_VERSION}))


async def handle_get_initial_state(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    initial_state: dict[str, Any] = {
        "type": "stateUpdate",
        "source": "spotify",
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
    await ws.send_str(json.dumps(initial_state))

    sc_state: dict[str, Any] = {
        "type": "scStateUpdate",
        "source": "soundcloud",
        "track": state["scTrack"],
        "artist": state["scArtist"],
        "album": state["scAlbum"],
        "id": state["scId"],
        "coverUrl": state["scCoverUrl"],
        "isPlaying": state["scIsPlaying"],
        "progressMs": state["scProgressMs"],
        "durationMs": state["scDurationMs"],
        "volume": state["scVolume"],
        "isLiked": state["scIsLiked"],
        "timestamp": time.time() * 1000
    }
    await ws.send_str(json.dumps(sc_state))

    lyrics: dict[str, Any] = state["lyrics"]
    lyrics_msg: str = json.dumps({
        "type": "lyricsUpdate",
        "available": lyrics["available"],
        "instrumental": lyrics["instrumental"],
        "synced": lyrics["synced"],
        "plain": lyrics["plain"]
    })
    await ws.send_str(lyrics_msg)
    queue_msg: str = json.dumps({
        "type": "queueUpdate",
        "queue": state["queue"]["nextTracks"],
        "queueRevision": state["queue"]["queueRevision"]
    })
    await ws.send_str(queue_msg)


# --- Spotify handlers ---

async def handle_spotify_state_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    if "volume" in data:
        state["volume"] = data["volume"]
    if "isPlaying" in data:
        state["isPlaying"] = data["isPlaying"]
    if "isShuffling" in data:
        state["isShuffling"] = data["isShuffling"]
    if "repeatStatus" in data:
        state["repeatStatus"] = data["repeatStatus"]
    if "isLiked" in data:
        state["isLiked"] = data["isLiked"]

    prev_uri: str = state["currentTrack"]["trackUri"]
    new_uri: str = data.get("trackUri", prev_uri)

    state["currentTrack"].update({
        "trackName": data.get("trackName", state["currentTrack"]["trackName"]),
        "artistName": data.get("artistName", state["currentTrack"]["artistName"]),
        "albumName": data.get("albumName", state["currentTrack"]["albumName"]),
        "trackUri": new_uri,
        "albumUri": data.get("albumUri", state["currentTrack"]["albumUri"]),
        "albumArtUrl": data.get("albumArtUrl", state["currentTrack"]["albumArtUrl"])
    })
    state["trackDuration"] = data.get("duration", state["trackDuration"])
    state["trackProgress"] = data.get("progress", state["trackProgress"])
    state["trackProgressStartTimestamp"] = time.time() * 1000

    if new_uri and new_uri != prev_uri and new_uri != state["lyrics"]["trackUri"]:
        if config["enableLyrics"]:
            state["lyrics"] = {"trackUri": new_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "loading": True}
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
            state["lyrics"] = {"trackUri": new_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "loading": False}
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
    volume_step: float = data.get("step", 0.05)
    if data.get("command") == "volumeUp":
        state["volume"] = min(1.0, state["volume"] + volume_step)
    elif data.get("command") == "volumeDown":
        state["volume"] = max(0.0, state["volume"] - volume_step)
    elif isinstance(data.get("volume"), (int, float)):
        state["volume"] = max(0.0, min(1.0, data["volume"]))
    await save_spotify_state_debounced()
    await broadcast_volume_update()


async def handle_spotify_playback_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    if "isPlaying" in data:
        state["isPlaying"] = data["isPlaying"]
    state["trackProgress"] = data.get("progress", state["trackProgress"])
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await save_spotify_state_debounced()
    await broadcast_playback_update(exclude_ws=ws)


async def handle_spotify_shuffle_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["isShuffling"] = data.get("isShuffling", False)
    await save_spotify_state_debounced()
    await broadcast({"type": "shuffleUpdate", "source": "spotify", "isShuffling": state["isShuffling"]}, exclude_ws=ws)


async def handle_spotify_repeat_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["repeatStatus"] = data.get("repeatStatus", 0)
    await save_spotify_state_debounced()
    await broadcast({"type": "repeatUpdate", "source": "spotify", "repeatStatus": state["repeatStatus"]}, exclude_ws=ws)


async def handle_spotify_like_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["isLiked"] = data.get("isLiked", False)
    await save_spotify_state_debounced()
    await broadcast({"type": "likeUpdate", "source": "spotify", "isLiked": state["isLiked"]}, exclude_ws=ws)


async def handle_spotify_progress_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    state["trackProgress"] = data.get("progress", 0)
    state["trackDuration"] = data.get("duration", 0)
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await broadcast_progress_update(exclude_ws=ws)


# --- SoundCloud handlers ---

async def handle_sc_state_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    if "track" in data:
        state["scTrack"] = data["track"]
    if "artist" in data:
        state["scArtist"] = data["artist"]
    if "album" in data:
        state["scAlbum"] = data["album"]
    if "id" in data:
        state["scId"] = data["id"]
    if "coverUrl" in data:
        state["scCoverUrl"] = re.sub(r'-t\d+x\d+', '-t500x500', data["coverUrl"])
    if "isPlaying" in data:
        state["scIsPlaying"] = data["isPlaying"]
    if "progressMs" in data:
        state["scProgressMs"] = data["progressMs"]
    if "durationMs" in data:
        state["scDurationMs"] = data["durationMs"]
    if "volume" in data:
        state["scVolume"] = max(0.0, min(1.0, data["volume"]))
    if "isLiked" in data:
        state["scIsLiked"] = data["isLiked"]
    if "progressMs" in data or "isPlaying" in data:
        state["scProgressStartTimestamp"] = time.time() * 1000

    await save_sc_state_debounced()
    await broadcast_soundcloud_state(exclude_ws=ws)


async def handle_sc_volume_update(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    volume_step: float = data.get("step", 0.05)
    if data.get("command") == "volumeUp":
        state["scVolume"] = min(1.0, state["scVolume"] + volume_step)
    elif data.get("command") == "volumeDown":
        state["scVolume"] = max(0.0, state["scVolume"] - volume_step)
    elif isinstance(data.get("volume"), (int, float)):
        state["scVolume"] = max(0.0, min(1.0, data["volume"]))
    await save_sc_state_debounced()
    await broadcast({
        "type": "scVolumeUpdate",
        "source": "soundcloud",
        "volume": state["scVolume"]
    }, exclude_ws=ws)
    logger.info(f"SC volume updated to {state['scVolume']:.3f}")


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


# --- Queue handlers ---

async def handle_queue_snapshot(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    next_tracks = data.get("nextTracks", [])
    queue_revision = str(data.get("queueRevision", ""))
    state["queue"]["nextTracks"] = next_tracks
    state["queue"]["queueRevision"] = queue_revision

    if next_tracks and pendingQueueMeta:
        uri_to_meta: dict[str, dict[str, str]] = {}
        for meta in pendingQueueMeta:
            uri_to_meta[meta["uri"]] = meta

        matched_uris: list[str] = []
        for track in next_tracks:
            track_uri = track.get("uri", "")
            if track_uri in uri_to_meta:
                track["requestedBy"] = uri_to_meta[track_uri]["requestedBy"]
                matched_uris.append(track_uri)

        for uri in matched_uris:
            pendingQueueMeta[:] = [m for m in pendingQueueMeta if m["uri"] != uri]

    await broadcast_queue_update()


async def handle_add_to_queue(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    raw_input = data.get("input", data.get("trackUri", ""))
    normalized_uri = parse_track_input(raw_input)
    requester = data.get("requestedBy", "anonymous")

    allowed, msg = check_rate_limit(requester)
    if not allowed:
        await ws.send_str(json.dumps({"type": "error", "message": msg}))
        return

    if is_queue_full():
        await ws.send_str(json.dumps({"type": "error", "message": "Queue is full"}))
        return

    if any(m["uri"] == normalized_uri for m in pendingQueueMeta):
        await ws.send_str(json.dumps({"type": "error", "message": "Track already in queue"}))
        return

    meta_entry = {"uri": normalized_uri, "requestedBy": requester}
    pendingQueueMeta.append(meta_entry)

    await broadcast({
        "type": "addToQueue",
        "uri": normalized_uri,
        "requestedBy": requester
    }, target_type="spicetify")

    logger.info(f"Queue: Added {normalized_uri} (requested by {requester})")


async def handle_remove_from_queue(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    uri = data.get("uri", "")
    uid = data.get("uid", "")
    pendingQueueMeta[:] = [m for m in pendingQueueMeta if m["uri"] != uri]
    await broadcast({
        "type": "removeFromQueue",
        "uri": uri,
        "uid": uid
    }, target_type="spicetify")
    logger.info(f"Queue: Removed {uri}")


async def handle_clear_queue(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    pendingQueueMeta.clear()
    state["queue"]["nextTracks"] = []
    state["queue"]["queueRevision"] = ""
    await broadcast({"type": "clearQueue"}, target_type="spicetify")
    await broadcast_queue_update()
    logger.info("Queue: Cleared")


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
    "register": handle_register,
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
    "queueSnapshot": handle_queue_snapshot,
    "addToQueue": handle_add_to_queue,
    "removeFromQueue": handle_remove_from_queue,
    "clearQueue": handle_clear_queue,
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
