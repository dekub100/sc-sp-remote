import asyncio
import json
import time

from config import PROGRESS_BROADCAST_INTERVAL
from state import state

CLIENTS = {}


async def broadcast(message, exclude_ws=None, target_type=None):
    if not CLIENTS:
        return
    msg = json.dumps(message)
    for ws, info in list(CLIENTS.items()):
        if ws == exclude_ws:
            continue
        if target_type and info.get("type") != target_type:
            continue
        try:
            await ws.send_str(msg)
        except Exception:
            if ws in CLIENTS:
                del CLIENTS[ws]


async def broadcast_current_state(exclude_ws=None):
    full_state_message = {
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
    await broadcast(full_state_message, exclude_ws)


async def broadcast_volume_update(exclude_ws=None):
    await broadcast({
        "type": "volumeUpdate",
        "volume": state["volume"]
    }, exclude_ws)


async def broadcast_playback_update(exclude_ws=None):
    await broadcast({
        "type": "playbackUpdate",
        "isPlaying": state["isPlaying"],
        "progress": state["trackProgress"],
        "timestamp": time.time() * 1000
    }, exclude_ws)


async def broadcast_progress_update(exclude_ws=None):
    progress_message = {
        "type": "progressUpdate",
        "progress": state["trackProgress"],
        "duration": state["trackDuration"],
        "isPlaying": state["isPlaying"],
        "timestamp": time.time() * 1000
    }
    await broadcast(progress_message, exclude_ws)


async def broadcast_lyrics_update():
    lyrics = state["lyrics"]
    await broadcast({
        "type": "lyricsUpdate",
        "available": lyrics["available"],
        "instrumental": lyrics["instrumental"],
        "synced": lyrics["synced"],
        "plain": lyrics["plain"],
        "loading": lyrics["loading"]
    })


async def start_progress_broadcasting():
    while True:
        if state["isPlaying"]:
            now = time.time() * 1000
            elapsed_time = now - state["trackProgressStartTimestamp"]
            state["trackProgress"] = min(state["trackProgress"] + elapsed_time, state["trackDuration"])
            state["trackProgressStartTimestamp"] = now
            await broadcast_progress_update()
        await asyncio.sleep(PROGRESS_BROADCAST_INTERVAL)
