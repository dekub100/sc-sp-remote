import asyncio
import json
import time

from broadcast import (
    CLIENTS,
    broadcast,
    broadcast_current_state,
    broadcast_lyrics_update,
    broadcast_playback_update,
    broadcast_progress_update,
    broadcast_volume_update,
)
from config import config
from log import logger
from lyrics import fetch_and_broadcast_lyrics
from state import save_state_to_file_debounced, state


async def handle_register(ws, data):
    client_type = data.get("client", "unknown")
    CLIENTS[ws]["type"] = client_type
    if client_type == "spicetify":
        state["spicetifyClient"] = ws
    logger.info(f"Client registered as: {client_type}")


async def handle_get_initial_state(ws, data):
    initial_state = {
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
        "backgroundPalette": state["backgroundPalette"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"],
        "timestamp": time.time() * 1000
    }
    await ws.send_str(json.dumps(initial_state))
    lyrics = state["lyrics"]
    lyrics_msg = json.dumps({
        "type": "lyricsUpdate",
        "available": lyrics["available"],
        "instrumental": lyrics["instrumental"],
        "synced": lyrics["synced"],
        "plain": lyrics["plain"]
    })
    await ws.send_str(lyrics_msg)


async def handle_volume_update(ws, data):
    volume_step = config.get("volumeStep", 0.05)
    if data.get("command") == "volumeUp":
        state["volume"] = min(1.0, state["volume"] + volume_step)
    elif data.get("command") == "volumeDown":
        state["volume"] = max(0.0, state["volume"] - volume_step)
    elif "volume" in data:
        state["volume"] = max(0.0, min(1.0, data["volume"]))
    await save_state_to_file_debounced()
    await broadcast_volume_update()


async def handle_playback_update(ws, data):
    if "isPlaying" in data:
        state["isPlaying"] = data["isPlaying"]
    state["trackProgress"] = data.get("progress", state["trackProgress"])
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await save_state_to_file_debounced()
    await broadcast_playback_update(exclude_ws=ws)


async def handle_shuffle_update(ws, data):
    state["isShuffling"] = data.get("isShuffling", False)
    await save_state_to_file_debounced()
    await broadcast({"type": "shuffleUpdate", "isShuffling": state["isShuffling"]}, exclude_ws=ws)


async def handle_repeat_update(ws, data):
    state["repeatStatus"] = data.get("repeatStatus", 0)
    await save_state_to_file_debounced()
    await broadcast({"type": "repeatUpdate", "repeatStatus": state["repeatStatus"]}, exclude_ws=ws)


async def handle_like_update(ws, data):
    state["isLiked"] = data.get("isLiked", False)
    await save_state_to_file_debounced()
    await broadcast({"type": "likeUpdate", "isLiked": state["isLiked"]}, exclude_ws=ws)


async def handle_track_update(ws, data):
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

    prev_uri = state["currentTrack"]["trackUri"]
    new_uri = data.get("trackUri", prev_uri)

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
        state["lyrics"] = {"trackUri": new_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "loading": True}
        await broadcast_lyrics_update()
        task = asyncio.create_task(fetch_and_broadcast_lyrics(
            new_uri,
            state["currentTrack"]["trackName"],
            state["currentTrack"]["artistName"],
            state["currentTrack"]["albumName"],
            state["trackDuration"]
        ))
        task.add_done_callback(lambda t: logger.error(f"Lyrics background task failed: {t.exception()}") if t.exception() else None)

    await save_state_to_file_debounced()
    await broadcast_current_state(exclude_ws=ws)


async def handle_progress_update(ws, data):
    state["trackProgress"] = data.get("progress", 0)
    state["trackDuration"] = data.get("duration", 0)
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await broadcast_progress_update(exclude_ws=ws)


async def handle_playback_control(ws, data):
    await broadcast(data, target_type="spicetify", exclude_ws=ws)


async def handle_like_command(ws, data):
    await broadcast({"type": "playbackControl", "command": "like"}, target_type="spicetify", exclude_ws=ws)


MESSAGE_HANDLERS = {
    "register": handle_register,
    "getInitialState": handle_get_initial_state,
    "stateUpdate": handle_track_update,
    "volumeUpdate": handle_volume_update,
    "playbackUpdate": handle_playback_update,
    "shuffleUpdate": handle_shuffle_update,
    "repeatUpdate": handle_repeat_update,
    "likeUpdate": handle_like_update,
    "trackUpdate": handle_track_update,
    "progressUpdate": handle_progress_update,
    "playbackControl": handle_playback_control,
    "like": handle_like_command
}


async def handle_message(ws, message):
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        logger.warning("Server: Received invalid JSON")
        return

    if not isinstance(data, dict):
        logger.warning("Server: Received non-object JSON message")
        return

    msg_type = data.get("type")
    if not isinstance(msg_type, str):
        logger.warning(f"Server: Received message with invalid type field: {type(msg_type)}")
        return

    handler = MESSAGE_HANDLERS.get(msg_type)
    if handler:
        await handler(ws, data)
    else:
        logger.warning(f"Server: Received unknown message type: {msg_type}")
