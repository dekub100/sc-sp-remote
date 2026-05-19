from __future__ import annotations

import json
import os
from typing import Any

from aiohttp import web
from broadcast import CLIENTS, broadcast, set_spicetify_client
from config import DISCOVERY_PORT, MAX_QUEUE_SIZE, PROJECT_ROOT, config
from handlers import handle_get_initial_state, handle_message
from log import logger
from state import check_rate_limit, parse_track_input, pendingQueueMeta, state


def _cors_headers(request: web.Request) -> dict[str, str]:
    origins: list[str] = config["allowedOrigins"]
    if "*" in origins:
        return {"Access-Control-Allow-Origin": "*"}
    req_origin: str = request.headers.get("Origin", "")
    if req_origin and req_origin in origins:
        return {"Access-Control-Allow-Origin": req_origin}
    return {"Access-Control-Allow-Origin": origins[0]} if origins else {}


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


async def handle_queue_get(request: web.Request) -> web.Response:
    return web.json_response({
        "nextTracks": state["queue"]["nextTracks"],
        "queueRevision": state["queue"]["queueRevision"]
    }, headers=_cors_headers(request))


async def handle_queue_add(request: web.Request) -> web.Response:
    try:
        body: dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=_cors_headers(request))

    raw_input = body.get("trackUri", "")
    normalized_uri = parse_track_input(raw_input)
    requester = body.get("requestedBy", "http")

    allowed, msg = check_rate_limit(requester)
    if not allowed:
        return web.json_response({"error": msg}, status=429, headers=_cors_headers(request))

    if len(pendingQueueMeta) >= MAX_QUEUE_SIZE:
        return web.json_response({"error": "Queue is full"}, status=400, headers=_cors_headers(request))

    pendingQueueMeta.append({"uri": normalized_uri, "requestedBy": requester})
    await broadcast({
        "type": "addToQueue",
        "uri": normalized_uri,
        "requestedBy": requester
    }, target_type="spicetify")

    logger.info(f"Queue (HTTP): Added {normalized_uri} (requested by {requester})")
    return web.json_response({"status": "ok", "uri": normalized_uri}, headers=_cors_headers(request))


async def handle_queue_search_add(request: web.Request) -> web.Response:
    try:
        body: dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=_cors_headers(request))

    query = body.get("query", "")
    requester = body.get("requestedBy", "http")

    allowed, msg = check_rate_limit(requester)
    if not allowed:
        return web.json_response({"error": msg}, status=429, headers=_cors_headers(request))

    await broadcast({
        "type": "searchAndAdd",
        "query": query,
        "requestedBy": requester
    }, target_type="spicetify")

    logger.info(f"Queue (HTTP): Search '{query}' forwarded (requested by {requester})")
    return web.json_response({"status": "ok", "query": query}, headers=_cors_headers(request))


async def handle_queue_remove(request: web.Request) -> web.Response:
    try:
        body: dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=_cors_headers(request))

    uri = body.get("uri", "")
    uid = body.get("uid", "")
    await broadcast({
        "type": "removeFromQueue",
        "uri": uri,
        "uid": uid
    }, target_type="spicetify")

    logger.info(f"Queue (HTTP): Removed {uri}")
    return web.json_response({"status": "ok"}, headers=_cors_headers(request))


async def handle_queue_clear(request: web.Request) -> web.Response:
    pendingQueueMeta.clear()
    await broadcast({"type": "clearQueue"}, target_type="spicetify")
    logger.info("Queue (HTTP): Cleared")
    return web.json_response({"status": "ok"}, headers=_cors_headers(request))
