from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from aiohttp import web
from broadcast import (
    CLIENTS,
    broadcast_playback_update,
    set_soundcloud_client,
    set_spicetify_client,
)
from config import CONFIG_FIELD_TYPES, CONFIG_PATH, LOG_DIR, PROJECT_ROOT, config
from handlers import handle_get_initial_state, handle_message
from log import logger
from state import (
    get_interpolated_track_progress,
    save_sc_state_debounced,
    save_spotify_state_debounced,
    state,
)


def _write_config_to_disk() -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def _build_client_config(client_type: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": "config",
    }
    if client_type == "spicetify":
        base.update({
            "pollingIntervalMs": config.get("spicetifyPollingIntervalMs", 500),
            "reconnectBaseDelayMs": config.get("spicetifyReconnectBaseDelayMs", 1000),
            "reconnectMaxDelayMs": config.get("spicetifyReconnectMaxDelayMs", 10000),
            "progressDeltaThresholdMs": config.get("spicetifyProgressDeltaThresholdMs", 2000),
            "commandFeedbackDelayMs": config.get("spicetifyCommandFeedbackDelayMs", 150),
        })
    elif client_type == "soundcloud":
        base.update({
            "pollingIntervalMs": config.get("soundcloudPollingIntervalMs", 500),
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
    try:
        client_version: int = int(request.query.get("protocolVersion", 0))
    except ValueError:
        client_version = 0
    CLIENTS[ws] = {"type": client_type, "remote_ip": request.remote, "protocolVersion": client_version}

    logger.info(f"New connection: {client_type} (protocol v{client_version}, {request.remote})")

    client_config = _build_client_config(client_type)
    await ws.send_json(client_config)

    if client_type == "spicetify":
        set_spicetify_client(ws)
    elif client_type == "soundcloud":
        set_soundcloud_client(ws)
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
        if info:
            # Source controller gone: pause it so clients (web/OBS/streamdeck)
            # stop showing phantom playback and auto-routing gets unstuck.
            if info.get("type") == "spicetify":
                set_spicetify_client(None)
                state["isPlaying"] = False
                state["trackProgressStartTimestamp"] = time.time() * 1000
                await save_spotify_state_debounced()
            elif info.get("type") == "soundcloud":
                set_soundcloud_client(None)
                state["scIsPlaying"] = False
                state["scProgressStartTimestamp"] = time.time() * 1000
                await save_sc_state_debounced()
            if info.get("type") in ("spicetify", "soundcloud"):
                await broadcast_playback_update()
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
        "spotify": {
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
            "progress": get_interpolated_track_progress(),
            "duration": state["trackDuration"],
            "progressFmt": format_ms(state["trackProgress"]),
            "durationFmt": format_ms(state["trackDuration"])
        },
        "soundcloud": {
            "track": state["scTrack"],
            "artist": state["scArtist"],
            "album": state["scAlbum"],
            "coverUrl": state["scCoverUrl"],
            "isPlaying": state["scIsPlaying"],
            "progressMs": state["scProgressMs"],
            "durationMs": state["scDurationMs"],
            "volume": state["scVolume"],
            "isLiked": state["scIsLiked"],
            "progressFmt": format_ms(state["scProgressMs"]),
            "durationFmt": format_ms(state["scDurationMs"])
        }
    })


async def index_handler(request: web.Request) -> web.StreamResponse:
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await websocket_handler(request)
    return web.FileResponse(os.path.join(PROJECT_ROOT, 'web', 'index.html'))


async def obs_handler(request: web.Request) -> web.StreamResponse:
    if not request.path.endswith('/'):
        return web.HTTPFound(request.rel_url.with_path(request.path + '/'))
    return web.FileResponse(os.path.join(PROJECT_ROOT, 'web', 'obs-widget', 'obs-widget.html'))


async def handle_admin_config_get(request: web.Request) -> web.Response:
    return web.json_response(config, headers=_cors_headers(request))


_CONFIG_ERRORS: dict[str, str] = {
    "port": "must be an integer between 1 and 65535",
    "host": "must be a valid IP address or hostname",
    "defaultVolume": "must be a number between 0.0 and 1.0",
    "backupCount": "must be a non-negative integer",
    "progressBroadcastInterval": "must be a positive number",
    "stateSaveDebounceSeconds": "must be a positive number",
    "lyricsFetchTimeoutSeconds": "must be a positive number",
    "spicetifyPollingIntervalMs": "must be a positive integer",
    "spicetifyReconnectBaseDelayMs": "must be a positive integer",
    "spicetifyReconnectMaxDelayMs": "must be a positive integer",
    "spicetifyProgressDeltaThresholdMs": "must be a positive integer",
    "spicetifyCommandFeedbackDelayMs": "must be a positive integer",
    "soundcloudPollingIntervalMs": "must be a positive integer",
    "obsUpNextThresholdMs": "must be a positive integer",
    "enableOBS": "must be a boolean",
    "enableWebsite": "must be a boolean",
    "enableLyrics": "must be a boolean",
    "logLevel": "must be a string",
    "allowedOrigins": "must be a list of strings",
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
        if key not in CONFIG_FIELD_TYPES:
            continue
        expected_type = CONFIG_FIELD_TYPES[key]
        error_msg = _CONFIG_ERRORS.get(key, "invalid value")
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
        if key in ("backupCount",) and coerced < 0:
            errors.append(f"{key}: {error_msg}")
            continue
        if key in ("progressBroadcastInterval", "stateSaveDebounceSeconds",
                     "lyricsFetchTimeoutSeconds",
                     "spicetifyPollingIntervalMs",
                     "spicetifyReconnectBaseDelayMs", "spicetifyReconnectMaxDelayMs",
                     "spicetifyProgressDeltaThresholdMs", "spicetifyCommandFeedbackDelayMs",
                     "soundcloudPollingIntervalMs",
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
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _write_config_to_disk)
    except Exception as e:
        return web.json_response({"error": f"Failed to save config: {str(e)}"}, status=500, headers=_cors_headers(request))

    logger.info(f"Admin: Config updated ({', '.join(updates.keys())})")
    return web.json_response({"status": "ok", "updated": list(updates.keys())}, headers=_cors_headers(request))


async def handle_admin_mxm_token_refresh(request: web.Request) -> web.Response:
    from lyrics import refresh_musixmatch_token
    try:
        token = await refresh_musixmatch_token()
        logger.info("Admin: Musixmatch token refreshed")
        return web.json_response({"status": "ok", "tokenPreview": token[:6] + "..."}, headers=_cors_headers(request))
    except Exception as e:
        logger.error(f"Admin: Musixmatch token refresh failed: {type(e).__name__}: {e}")
        return web.json_response({"error": f"Token refresh failed: {e}"}, status=502, headers=_cors_headers(request))


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
