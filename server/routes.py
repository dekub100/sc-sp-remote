from __future__ import annotations

import json
import os
from typing import Any

from aiohttp import web
from broadcast import CLIENTS, broadcast, broadcast_queue_update, set_spicetify_client
from config import CONFIG_PATH, LOG_DIR, PROJECT_ROOT, config
from handlers import handle_get_initial_state, handle_message
from log import logger
from state import check_rate_limit, is_queue_full, parse_track_input, pendingQueueMeta, state


def _build_client_config(client_type: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": "config",
        "volumeStep": config.get("volumeStep", 0.05),
    }
    if client_type == "spicetify":
        base.update({
            "pollingIntervalMs": config.get("spicetifyPollingIntervalMs", 500),
            "queuePollingIntervalMs": config.get("spicetifyQueuePollingIntervalMs", 2000),
            "reconnectBaseDelayMs": config.get("spicetifyReconnectBaseDelayMs", 1000),
            "reconnectMaxDelayMs": config.get("spicetifyReconnectMaxDelayMs", 10000),
            "progressDeltaThresholdMs": config.get("spicetifyProgressDeltaThresholdMs", 2000),
            "commandFeedbackDelayMs": config.get("spicetifyCommandFeedbackDelayMs", 150),
        })
    elif client_type == "obs":
        base["upNextThresholdMs"] = config.get("obsUpNextThresholdMs", 15000)
    return base


def _cors_headers(request: web.Request) -> dict[str, str]:
    origins: list[str] = config["allowedOrigins"]
    if "*" in origins:
        return {"Access-Control-Allow-Origin": "*"}
    req_origin: str = request.headers.get("Origin", "")
    if req_origin and req_origin in origins:
        return {"Access-Control-Allow-Origin": req_origin}
    return {}


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws: web.WebSocketResponse = web.WebSocketResponse()
    await ws.prepare(request)

    client_type: str = request.query.get("client", "unknown")
    client_version: int = int(request.query.get("protocolVersion", 0))
    CLIENTS[ws] = {"type": client_type, "remote_ip": request.remote, "protocolVersion": client_version}

    logger.info(f"New connection: {client_type} (protocol v{client_version}, {request.remote})")

    client_config = _build_client_config(client_type)
    await ws.send_json(client_config)

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
    headers: dict[str, str] = _cors_headers(request)
    return web.json_response({
        "port": config["port"],
        "allowedOrigins": config["allowedOrigins"],
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

    if is_queue_full():
        return web.json_response({"error": "Queue is full"}, status=400, headers=_cors_headers(request))

    if any(m["uri"] == normalized_uri for m in pendingQueueMeta):
        return web.json_response({"error": "Track already in queue"}, status=400, headers=_cors_headers(request))

    pendingQueueMeta.append({"uri": normalized_uri, "requestedBy": requester})
    await broadcast({
        "type": "addToQueue",
        "uri": normalized_uri,
        "requestedBy": requester
    }, target_type="spicetify")

    logger.info(f"Queue (HTTP): Added {normalized_uri} (requested by {requester})")
    return web.json_response({"status": "ok", "uri": normalized_uri}, headers=_cors_headers(request))


async def handle_queue_remove(request: web.Request) -> web.Response:
    try:
        body: dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=_cors_headers(request))

    uri = body.get("uri", "")
    uid = body.get("uid", "")
    pendingQueueMeta[:] = [m for m in pendingQueueMeta if m["uri"] != uri]
    await broadcast({
        "type": "removeFromQueue",
        "uri": uri,
        "uid": uid
    }, target_type="spicetify")

    logger.info(f"Queue (HTTP): Removed {uri}")
    return web.json_response({"status": "ok"}, headers=_cors_headers(request))


async def handle_queue_clear(request: web.Request) -> web.Response:
    pendingQueueMeta.clear()
    state["queue"]["nextTracks"] = []
    state["queue"]["queueRevision"] = ""
    await broadcast({"type": "clearQueue"}, target_type="spicetify")
    await broadcast_queue_update()
    logger.info("Queue (HTTP): Cleared")
    return web.json_response({"status": "ok"}, headers=_cors_headers(request))


async def handle_admin_config_get(request: web.Request) -> web.Response:
    return web.json_response(config, headers=_cors_headers(request))


_CONFIG_VALIDATORS: dict[str, tuple[type, str]] = {
    "port": (int, "must be an integer between 1 and 65535"),
    "host": (str, "must be a valid IP address or hostname"),
    "defaultVolume": (float, "must be a number between 0.0 and 1.0"),
    "volumeStep": (float, "must be a number between 0.001 and 1.0"),
    "maxQueueSize": (int, "must be a positive integer"),
    "queueRateLimitSeconds": (float, "must be a non-negative number"),
    "backupCount": (int, "must be a non-negative integer"),
    "progressBroadcastInterval": (float, "must be a positive number"),
    "stateSaveDebounceSeconds": (float, "must be a positive number"),
    "lyricsFetchTimeoutSeconds": (float, "must be a positive number"),
    "spicetifyPollingIntervalMs": (int, "must be a positive integer"),
    "spicetifyQueuePollingIntervalMs": (int, "must be a positive integer"),
    "spicetifyReconnectBaseDelayMs": (int, "must be a positive integer"),
    "spicetifyReconnectMaxDelayMs": (int, "must be a positive integer"),
    "spicetifyProgressDeltaThresholdMs": (int, "must be a positive integer"),
    "spicetifyCommandFeedbackDelayMs": (int, "must be a positive integer"),
    "obsUpNextThresholdMs": (int, "must be a positive integer"),
    "enableOBS": (bool, "must be a boolean"),
    "enableWebsite": (bool, "must be a boolean"),
    "logLevel": (str, "must be a string"),
    "allowedOrigins": (list, "must be a list of strings"),
}


def _coerce_type(value: Any, expected_type: type) -> Any:
    if expected_type is list:
        if not isinstance(value, list):
            raise TypeError(f"expected list, got {type(value).__name__}")
        return value
    return expected_type(value)


async def handle_admin_config_put(request: web.Request) -> web.Response:
    try:
        body: dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=_cors_headers(request))

    errors: list[str] = []
    updates: dict[str, Any] = {}
    for key, value in body.items():
        if key not in _CONFIG_VALIDATORS:
            continue
        expected_type, error_msg = _CONFIG_VALIDATORS[key]
        try:
            coerced = _coerce_type(value, expected_type)
        except (ValueError, TypeError):
            errors.append(f"{key}: {error_msg}")
            continue
        if not isinstance(coerced, expected_type):
            errors.append(f"{key}: {error_msg}")
            continue
        if key == "port" and (coerced < 1 or coerced > 65535):
            errors.append(f"{key}: {error_msg}")
            continue
        if key in ("defaultVolume",) and (coerced < 0.0 or coerced > 1.0):
            errors.append(f"{key}: {error_msg}")
            continue
        if key in ("volumeStep",) and (coerced < 0.001 or coerced > 1.0):
            errors.append(f"{key}: {error_msg}")
            continue
        if key in ("maxQueueSize", "backupCount") and coerced < 0:
            errors.append(f"{key}: {error_msg}")
            continue
        if key in ("queueRateLimitSeconds",) and coerced < 0:
            errors.append(f"{key}: {error_msg}")
            continue
        if key in ("progressBroadcastInterval", "stateSaveDebounceSeconds",
                     "lyricsFetchTimeoutSeconds",
                     "spicetifyPollingIntervalMs", "spicetifyQueuePollingIntervalMs",
                     "spicetifyReconnectBaseDelayMs", "spicetifyReconnectMaxDelayMs",
                     "spicetifyProgressDeltaThresholdMs", "spicetifyCommandFeedbackDelayMs",
                     "obsUpNextThresholdMs") and coerced <= 0:
            errors.append(f"{key}: {error_msg}")
            continue
        if key == "logLevel" and coerced not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            errors.append(f"{key}: must be one of DEBUG, INFO, WARNING, ERROR")
            continue
        if key == "allowedOrigins":
            if not all(isinstance(o, str) for o in coerced):
                errors.append(f"{key}: must be a list of strings")
                continue
        updates[key] = coerced

    if errors:
        return web.json_response({"error": "Validation failed", "details": errors}, status=400, headers=_cors_headers(request))

    config.update(updates)
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        return web.json_response({"error": f"Failed to save config: {str(e)}"}, status=500, headers=_cors_headers(request))

    logger.info(f"Admin: Config updated ({', '.join(updates.keys())})")
    return web.json_response({"status": "ok", "updated": list(updates.keys())}, headers=_cors_headers(request))


async def handle_admin_logs_list(request: web.Request) -> web.Response:
    try:
        files = []
        if os.path.exists(LOG_DIR):
            for f in os.listdir(LOG_DIR):
                if f.endswith(".log"):
                    path = os.path.join(LOG_DIR, f)
                    stat = os.stat(path)
                    files.append({
                        "name": f,
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })
        files.sort(key=lambda x: x["modified"], reverse=True)
        return web.json_response({"logs": files}, headers=_cors_headers(request))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500, headers=_cors_headers(request))


async def handle_admin_log_file(request: web.Request) -> web.Response:
    filename = request.match_info["filename"]
    if ".." in filename or "/" in filename or "\\" in filename:
        return web.json_response({"error": "Invalid filename"}, status=400, headers=_cors_headers(request))

    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path) or not filename.endswith(".log"):
        return web.json_response({"error": "Log file not found"}, status=404, headers=_cors_headers(request))

    try:
        with open(path, "r") as f:
            content = f.read()
        return web.Response(text=content, content_type="text/plain", headers=_cors_headers(request))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500, headers=_cors_headers(request))
