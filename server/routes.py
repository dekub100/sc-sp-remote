import os

from aiohttp import web
from broadcast import CLIENTS
from config import DISCOVERY_PORT, PROJECT_ROOT, config
from handlers import handle_get_initial_state, handle_message
from log import logger
from state import state


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    client_type = request.query.get("client", "unknown")
    CLIENTS[ws] = {"type": client_type, "remote_ip": request.remote}

    logger.info(f"New connection: {client_type} ({request.remote})")

    if client_type == "spicetify":
        state["spicetifyClient"] = ws
    else:
        await handle_get_initial_state(ws, {})

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await handle_message(ws, msg.data)
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f'WebSocket connection closed with exception {ws.exception()}')
    finally:
        info = CLIENTS.pop(ws, None)
        if info and info.get("type") == "spicetify":
            state["spicetifyClient"] = None
        logger.info(f"Disconnected: {info.get('type') if info else 'unknown'}")

    return ws


async def handle_config(request):
    origins = config["allowedOrigins"]
    if "*" in origins:
        cors_origin = "*"
    else:
        req_origin = request.headers.get("Origin", "")
        cors_origin = req_origin if req_origin in origins else origins[0] if origins else ""

    headers = {"Access-Control-Allow-Origin": cors_origin} if cors_origin else {}
    return web.json_response({
        "port": config["port"],
        "discoveryPort": DISCOVERY_PORT,
        "allowedOrigins": origins,
        "defaultVolume": config["defaultVolume"],
        "enableOBS": config.get("enableOBS", True),
        "enableWebsite": config.get("enableWebsite", True)
    }, headers=headers)


async def index_handler(request):
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await websocket_handler(request)
    return web.FileResponse(os.path.join(PROJECT_ROOT, 'web', 'index.html'))


async def obs_handler(request):
    if not request.path.endswith('/'):
        return web.HTTPFound(request.path + '/')
    return web.FileResponse(os.path.join(PROJECT_ROOT, 'web', 'obs-widget', 'obs-widget.html'))
