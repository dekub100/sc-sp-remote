from __future__ import annotations

import os
from typing import Any

from aiohttp import web
from broadcast import CLIENTS, set_spicetify_client
from config import DISCOVERY_PORT, PROJECT_ROOT, config
from handlers import handle_get_initial_state, handle_message
from log import logger
from state import state


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws: web.WebSocketResponse = web.WebSocketResponse()
    await ws.prepare(request)

    client_type: str = request.query.get("client", "unknown")
    CLIENTS[ws] = {"type": client_type, "remote_ip": request.remote}

    logger.info(f"New connection: {client_type} ({request.remote})")

    if client_type == "spicetify":
        set_spicetify_client(ws)
    else:
        await handle_get_initial_state(ws, {})

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await handle_message(ws, msg.data)
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f'WebSocket connection closed with exception {ws.exception()}')
    finally:
        info: dict[str, Any] | None = CLIENTS.pop(ws, None)
        if info and info.get("type") == "spicetify":
            set_spicetify_client(None)
        logger.info(f"Disconnected: {info.get('type') if info else 'unknown'}")

    return ws


async def handle_config(request: web.Request) -> web.Response:
    origins: list[str] = config["allowedOrigins"]
    if "*" in origins:
        cors_origin: str = "*"
    else:
        req_origin: str = request.headers.get("Origin", "")
        cors_origin = req_origin if req_origin in origins else origins[0] if origins else ""

    headers: dict[str, str] = {"Access-Control-Allow-Origin": cors_origin} if cors_origin else {}
    return web.json_response({
        "port": config["port"],
        "discoveryPort": DISCOVERY_PORT,
        "allowedOrigins": origins,
        "defaultVolume": config["defaultVolume"],
        "enableOBS": config.get("enableOBS", True),
        "enableWebsite": config.get("enableWebsite", True)
    }, headers=headers)


def format_ms(ms: int) -> str:
    total_sec: int = max(0, int(ms / 1000))
    return f"{total_sec // 60}:{total_sec % 60:02d}"


async def handle_state(request: web.Request) -> web.Response:
    return web.json_response({
        "trackName": state["currentTrack"]["trackName"],
        "artistName": state["currentTrack"]["artistName"],
        "albumName": state["currentTrack"]["albumName"],
        "trackUri": state["currentTrack"]["trackUri"],
        "albumArtUrl": state["currentTrack"]["albumArtUrl"],
        "volume": state["volume"],
        "isPlaying": state["isPlaying"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"],
        "progress": state["trackProgress"],
        "duration": state["trackDuration"],
        "progressFmt": format_ms(state["trackProgress"]),
        "durationFmt": format_ms(state["trackDuration"])
    })


async def index_handler(request: web.Request) -> web.StreamResponse:
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await websocket_handler(request)
    return web.FileResponse(os.path.join(PROJECT_ROOT, 'web', 'index.html'))


async def obs_handler(request: web.Request) -> web.StreamResponse:
    if not request.path.endswith('/'):
        return web.HTTPFound(request.path + '/')
    return web.FileResponse(os.path.join(PROJECT_ROOT, 'web', 'obs-widget', 'obs-widget.html'))
