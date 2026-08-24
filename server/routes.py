from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any
from urllib.parse import urlparse

from aiohttp import web
from broadcast import (
    CLIENTS,
    broadcast_playback_update,
)
from config import CONFIG_FIELD_TYPES, CONFIG_PATH, LOG_DIR, PROJECT_ROOT, config
from handlers import handle_get_initial_state, handle_message
from log import logger
from state import (
    get_album_art_url,
    get_interpolated_track_progress,
    get_sc_cover_url,
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


_ALLOWED_WS_ORIGIN_HOSTS = {"localhost", "127.0.0.1", "::1", "xpui.app.spotify.com", "soundcloud.com"}


def _is_foreign_web_origin(request: web.Request) -> bool:
    # WebSockets ignore CORS — any website you visit could open ws://localhost and send commands.
    # Allowlist known client origins (web UI, Spicetify/CEF, SoundCloud tab); everything else is blocked.
    # Native clients (streamdeck plugin etc.) send no Origin header at all.
    origin = request.headers.get("Origin", "")
    if not origin.startswith(("http://", "https://")):
        return False
    hostname = urlparse(origin).hostname or ""
    return hostname not in _ALLOWED_WS_ORIGIN_HOSTS and hostname != request.host


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    if _is_foreign_web_origin(request):
        logger.warning(f"Rejected WebSocket connection from foreign origin: {request.headers.get('Origin')}")
        raise web.HTTPForbidden(text="foreign origin rejected")
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

    if client_type not in ("spicetify", "soundcloud"):
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
                state["isPlaying"] = False
                state["trackProgressStartTimestamp"] = time.time() * 1000
                await save_spotify_state_debounced()
            elif info.get("type") == "soundcloud":
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
            "albumArtUrl": get_album_art_url(),
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
            "coverUrl": get_sc_cover_url(),
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
    # Don't leak the musixmatch token to anyone who can read this endpoint.
    return web.json_response({k: v for k, v in config.items() if k != "musixmatchToken"}, headers=_cors_headers(request))


# key -> (min, max) inclusive; None = unbounded on that side
_CONFIG_LIMITS: dict[str, tuple[Any, Any]] = {
    "port": (1, 65535),
    "defaultVolume": (0.0, 1.0),
    "backupCount": (0, None),
}
_CONFIG_POSITIVE_KEYS: frozenset[str] = frozenset({
    "progressBroadcastInterval", "stateSaveDebounceSeconds", "lyricsFetchTimeoutSeconds",
    "spicetifyPollingIntervalMs", "spicetifyReconnectBaseDelayMs", "spicetifyReconnectMaxDelayMs",
    "spicetifyProgressDeltaThresholdMs", "spicetifyCommandFeedbackDelayMs",
    "soundcloudPollingIntervalMs", "obsUpNextThresholdMs",
})
_LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")


async def handle_admin_config_put(request: web.Request) -> web.Response:
    try:
        body: dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=_cors_headers(request))

    errors: list[str] = []
    updates: dict[str, Any] = {}
    for key, value in body.items():
        expected_type = CONFIG_FIELD_TYPES.get(key)
        if expected_type is None:
            continue
        try:
            # list must be an actual list (list("abc") would "coerce" a string)
            coerced = value if expected_type is list else expected_type(value)
            assert isinstance(coerced, expected_type)
            lo, hi = _CONFIG_LIMITS.get(key, (None, None))
            assert lo is None or coerced >= lo
            assert hi is None or coerced <= hi
            assert key not in _CONFIG_POSITIVE_KEYS or coerced > 0
            assert key != "logLevel" or coerced in _LOG_LEVELS
            assert key != "allowedOrigins" or all(isinstance(o, str) for o in coerced)
        except (ValueError, TypeError, AssertionError):
            errors.append(f"{key}: invalid value")
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
