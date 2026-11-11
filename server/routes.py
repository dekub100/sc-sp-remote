from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import time
from typing import Any, Optional
from urllib.parse import urlparse

from aiohttp import web
from broadcast import (
    CLIENTS,
    broadcast_now_playing,
    broadcast_source_status,
)
from config import CONFIG_FIELD_TYPES, CONFIG_PATH, LOG_DIR, PROJECT_ROOT, config, write_json_atomic
from handlers import handle_get_initial_state, handle_message
from log import logger, set_log_level
from protocol import PROTOCOL_VERSION, error_message
from state import (
    SOURCE_BY_CLIENT_TYPE,
    as_ms,
    as_volume,
    get_album_art_url,
    get_interpolated_sc_progress,
    get_interpolated_track_progress,
    get_sc_cover_url,
    save_source_state_debounced,
    state,
)


def _write_config_to_disk() -> None:
    write_json_atomic(CONFIG_PATH, config)


def _build_client_config(client_type: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "v": PROTOCOL_VERSION,
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

_ALWAYS_ALLOWED_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})
_WILDCARD_BINDS: frozenset[str] = frozenset({"", "0.0.0.0", "::", "*"})
_UNSAFE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _host_only(value: str) -> str:
    """'[::1]:8888' -> '::1', 'localhost:8888' -> 'localhost'."""
    value = (value or "").strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end != -1 else value
    if value.count(":") == 1:
        return value.split(":", 1)[0]
    return value


def _is_private_literal(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def _is_allowed_host(host_header: str) -> bool:
    """Reject Host headers that no local browser could have produced.

    This is the anti-DNS-rebinding gate: a rebound attacker domain arrives with
    its own name in Host, which is neither loopback, the configured bind
    address, an entry in `allowedHosts`, nor a private IP literal.
    """
    host: str = _host_only(host_header)
    if not host:
        return False
    if host in _ALWAYS_ALLOWED_HOSTS:
        return True
    configured: str = str(config.get("host", "")).strip().lower()
    if configured and configured not in _WILDCARD_BINDS and host == configured:
        return True
    extra_hosts: list[Any] = config.get("allowedHosts") or []
    if any(isinstance(extra, str) and host == extra.strip().lower() for extra in extra_hosts):
        return True
    return _is_private_literal(host)


def _is_loopback_peer(remote: str | None) -> bool:
    if not remote:
        return False
    try:
        return ipaddress.ip_address(remote).is_loopback
    except ValueError:
        return remote == "localhost"


def _origin_is_self(origin: str, request: web.Request, allow_wildcard: bool = True) -> bool:
    parsed = urlparse(origin)
    if not parsed.netloc:
        return False
    if parsed.netloc.lower() == (request.headers.get("Host", "") or "").lower():
        return True
    origins: list[Any] = config["allowedOrigins"]
    if origin in origins:
        return True
    return allow_wildcard and "*" in origins


def _forbidden(message: str) -> web.Response:
    return web.json_response({"error": message}, status=403)


@web.middleware
async def security_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    """Localhost threat-model gate for every HTTP and WebSocket request.

    - Host must be a local name, a private IP literal, or explicitly allowed.
    - Cross-site state-changing requests are refused (CSRF).
    - /api/admin is loopback-only; LAN users keep playback, not config editing.
    """
    host_header: str = request.headers.get("Host", "") or ""
    if not _is_allowed_host(host_header):
        logger.warning(f"Rejected request with unexpected Host header: {host_header!r} ({request.path})")
        return _forbidden("unexpected host")

    if request.method in _UNSAFE_METHODS:
        if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            logger.warning(f"Rejected cross-site {request.method} {request.path}")
            return _forbidden("cross-site request rejected")
        origin: str = request.headers.get("Origin", "") or ""
        if origin and not _origin_is_self(origin, request):
            logger.warning(f"Rejected {request.method} {request.path} from origin {origin}")
            return _forbidden("origin rejected")

    if request.path.startswith("/api/admin") and not _is_loopback_peer(request.remote):
        logger.warning(f"Rejected remote admin access from {request.remote} ({request.path})")
        return _forbidden("admin is loopback-only")

    return await handler(request)


# A reconnect is "new socket registers, old socket closes". Pausing immediately
# on the old close would stomp the fresh syncFullState and pause the music, so
# wait briefly and re-check whether a controller of that type is still attached.
DISCONNECT_PAUSE_GRACE_SECONDS: float = 1.5

_SOURCE_CLIENT_TYPES: tuple[str, ...] = ("spicetify", "soundcloud")


async def _pause_source_if_alone(client_type: str) -> Optional[str]:
    """Mark a source paused once its last controller is really gone.

    Returns the paused source key, or None when a controller reconnected
    inside the grace window (nothing should be broadcast in that case).
    """
    await asyncio.sleep(DISCONNECT_PAUSE_GRACE_SECONDS)
    if any(info.get("type") == client_type for info in CLIENTS.values()):
        logger.info(f"Source {client_type}: controller reconnected within grace, not pausing")
        return None
    logger.info(f"Source {client_type}: controller gone, marking paused")
    spec = SOURCE_BY_CLIENT_TYPE[client_type]
    state[spec.playing_key] = False
    state[spec.anchor_key] = time.time() * 1000
    await save_source_state_debounced(spec.key)
    return spec.key


# Awaiting inside the websocket handler's `finally` is unsafe: aiohttp cancels the
# handler once the client is gone, which aborts the sleep/broadcast mid-flight.
# Disconnect bookkeeping therefore runs in a detached, strongly-referenced task.
_disconnect_tasks: set[asyncio.Task[None]] = set()


async def _handle_source_disconnect(client_type: str) -> None:
    paused_source = await _pause_source_if_alone(client_type)
    if paused_source is None:
        return
    await broadcast_now_playing(paused_source)
    await broadcast_source_status(paused_source, False)


def _spawn_source_disconnect(client_type: str) -> None:
    task: asyncio.Task[None] = asyncio.create_task(_handle_source_disconnect(client_type))
    _disconnect_tasks.add(task)
    task.add_done_callback(_disconnect_tasks.discard)


def _is_foreign_web_origin(request: web.Request) -> bool:
    # WebSockets ignore CORS — any website you visit could open ws://localhost and send commands.
    # Allowlist known client origins (web UI, Spicetify/CEF, SoundCloud tab); everything else is blocked.
    # Native clients (streamdeck plugin etc.) send no Origin header at all.
    # `security_middleware` has already rejected non-local Host headers, so comparing
    # netloc against Host here is safe and keeps the UI working on a LAN bind.
    origin = request.headers.get("Origin", "")
    if not origin.startswith(("http://", "https://")):
        return False
    hostname = urlparse(origin).hostname or ""
    if hostname in _ALLOWED_WS_ORIGIN_HOSTS:
        return False
    # Wildcard CORS must not open the WebSocket gate: any site could then drive playback.
    return not _origin_is_self(origin, request, allow_wildcard=False)


# Inbound snapshots are a few KB; this bounds a malicious/broken client without
# getting anywhere near legitimate traffic. aiohttp's default is 4 MB.
MAX_WS_MESSAGE_BYTES: int = 256 * 1024


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    if _is_foreign_web_origin(request):
        logger.warning(f"Rejected WebSocket connection from foreign origin: {request.headers.get('Origin')}")
        raise web.HTTPForbidden(text="foreign origin rejected")
    ws: web.WebSocketResponse = web.WebSocketResponse(max_msg_size=MAX_WS_MESSAGE_BYTES)
    await ws.prepare(request)

    client_type: str = request.query.get("client", "unknown")
    try:
        client_version: int = int(request.query.get("protocolVersion", 0))
    except ValueError:
        client_version = 0
    if client_version < PROTOCOL_VERSION:
        logger.warning(
            f"Rejected {client_type or 'unknown'} client: protocol v{client_version} "
            f"(v{PROTOCOL_VERSION} required)"
        )
        await ws.send_json(error_message(
            "protocol_version",
            f"protocol v{PROTOCOL_VERSION} required (client sent v{client_version})",
        ))
        await ws.close(code=1002, message=b"protocol v2 required")
        return ws
    CLIENTS[ws] = {"type": client_type, "remote_ip": request.remote, "protocolVersion": client_version}

    logger.info(f"New connection: {client_type} (protocol v{client_version}, {request.remote})")

    if client_type in _SOURCE_CLIENT_TYPES:
        await broadcast_source_status(SOURCE_BY_CLIENT_TYPE[client_type].key, True)

    client_config = _build_client_config(client_type)
    await ws.send_json(client_config)

    if client_type not in _SOURCE_CLIENT_TYPES:
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
            client_type = info.get("type", "")
            if client_type in _SOURCE_CLIENT_TYPES:
                # Source controller gone: pause it only if no other controller of
                # that type is attached, so reconnects don't pause playback.
                _spawn_source_disconnect(client_type)
        logger.info(f"Disconnected: {info.get('type') if info else 'unknown'}")

    return ws


async def handle_config(request: web.Request) -> web.Response:
    headers: dict[str, str] = _cors_headers(request)
    return web.json_response({
        "port": config["port"],
        "allowedOrigins": config["allowedOrigins"],
        "defaultVolume": config["defaultVolume"],
    }, headers=headers)


def format_ms(ms: int) -> str:
    try:
        total_sec: int = max(0, int(float(ms) / 1000))
    except (TypeError, ValueError):
        total_sec = 0
    hours, rem = divmod(total_sec, 3600)
    if hours:
        return f"{hours}:{rem // 60:02d}:{rem % 60:02d}"
    return f"{rem // 60}:{rem % 60:02d}"


async def handle_state(request: web.Request) -> web.Response:
    spotify_progress: int = get_interpolated_track_progress()
    sc_progress: int = get_interpolated_sc_progress()
    spotify_duration: int = as_ms(state["trackDuration"])
    sc_duration: int = as_ms(state["scDurationMs"])
    return web.json_response({
        "spotify": {
            "trackName": state["currentTrack"]["trackName"],
            "artistName": state["currentTrack"]["artistName"],
            "albumName": state["currentTrack"]["albumName"],
            "trackUri": state["currentTrack"]["trackUri"],
            "albumArtUrl": get_album_art_url(),
            "volume": as_volume(state["volume"]),
            "isPlaying": state["isPlaying"],
            "isShuffling": state["isShuffling"],
            "repeatStatus": state["repeatStatus"],
            "isLiked": state["isLiked"],
            "progress": spotify_progress,
            "duration": spotify_duration,
            "progressFmt": format_ms(spotify_progress),
            "durationFmt": format_ms(spotify_duration)
        },
        "soundcloud": {
            "track": state["scTrack"],
            "artist": state["scArtist"],
            "album": state["scAlbum"],
            "coverUrl": get_sc_cover_url(),
            "isPlaying": state["scIsPlaying"],
            "progressMs": sc_progress,
            "durationMs": sc_duration,
            "volume": as_volume(state["scVolume"]),
            "isLiked": state["scIsLiked"],
            "progressFmt": format_ms(sc_progress),
            "durationFmt": format_ms(sc_duration)
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
# Lower bounds matching the `min` attributes in web/admin/admin.html. Without
# them a value like 0.0001 is accepted and the loops hammer.
_CONFIG_MINIMUMS: dict[str, float] = {
    "progressBroadcastInterval": 0.1,
    "stateSaveDebounceSeconds": 0.5,
    "lyricsFetchTimeoutSeconds": 5,
    "spicetifyPollingIntervalMs": 100,
    "spicetifyReconnectBaseDelayMs": 200,
    "spicetifyReconnectMaxDelayMs": 1000,
    "spicetifyProgressDeltaThresholdMs": 500,
    "spicetifyCommandFeedbackDelayMs": 50,
    "soundcloudPollingIntervalMs": 100,
}
_LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")
# Changing these needs a new process (bind address, listen port, log retention
# sweep at startup). Everything else applies live.
_RESTART_REQUIRED_KEYS: frozenset[str] = frozenset({"port", "host", "backupCount"})


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
            minimum = _CONFIG_MINIMUMS.get(key)
            assert minimum is None or coerced >= minimum
            assert key != "logLevel" or coerced in _LOG_LEVELS
            assert key not in ("allowedOrigins", "allowedHosts") or all(isinstance(o, str) for o in coerced)
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

    if "logLevel" in updates:
        set_log_level(updates["logLevel"])
    logger.info(f"Admin: Config updated ({', '.join(updates.keys())})")
    restart_required: list[str] = [key for key in updates if key in _RESTART_REQUIRED_KEYS]
    return web.json_response({
        "status": "ok",
        "updated": list(updates.keys()),
        "restartRequired": restart_required,
    }, headers=_cors_headers(request))


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


LOG_TAIL_BYTES: int = 256 * 1024


def _read_log_tail(path: str) -> tuple[str, bool]:
    """Read the last LOG_TAIL_BYTES of a log file (blocking; run in executor).

    Log files are per-session and can grow to many MB; reading them whole in
    the event loop stalls every connected client. Returns (text, truncated).
    """
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        truncated = size > LOG_TAIL_BYTES
        f.seek(max(0, size - LOG_TAIL_BYTES))
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    # Match text-mode reads (and the Windows file handler's CRLF output) so a
    # log tail never shows doubled line breaks.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if truncated:
        text = f"[showing last {LOG_TAIL_BYTES // 1024} KB of {size} bytes]\n" + text
    return text, truncated


async def handle_admin_log_file(request: web.Request) -> web.Response:
    filename = request.match_info["filename"]
    if ".." in filename or "/" in filename or "\\" in filename:
        return web.json_response({"error": "Invalid filename"}, status=400, headers=_cors_headers(request))

    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path) or not filename.endswith(".log"):
        return web.json_response({"error": "Log file not found"}, status=404, headers=_cors_headers(request))

    try:
        loop = asyncio.get_running_loop()
        content, _truncated = await loop.run_in_executor(None, _read_log_tail, path)
        return web.Response(text=content, content_type="text/plain", headers=_cors_headers(request))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500, headers=_cors_headers(request))
