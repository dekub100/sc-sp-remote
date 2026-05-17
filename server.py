import asyncio
import json
import os
import re
import time
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
from aiohttp import web
import aiohttp

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_FILE = os.path.join(BASE_DIR, "state.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LYRICS_CACHE_DB = os.path.join(BASE_DIR, "lyrics_cache.db")

# Ensure logs directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Hard-coded Discovery Port (Standardized for all clients)
DISCOVERY_PORT = 54321

config = {
    "port": 8888,
    "allowedOrigins": ["*"],
    "defaultVolume": 0.5,
    "enableOBS": True,
    "enableWebsite": True,
    "volumeStep": 0.05,
    "logLevel": "INFO",
    "backupCount": 3
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        # We can't use the logger yet, so print is fine here
        print(f"Failed to read config.json, using defaults: {e}")

# --- Logging Setup ---
# Create a unique log file for this session
session_timestamp = time.strftime("%Y%m%d-%H%M%S")
log_file = os.path.join(LOG_DIR, f"server_{session_timestamp}.log")

log_level = getattr(logging, config["logLevel"].upper(), logging.INFO)
logger = logging.getLogger("SpicetifyRemote")
logger.setLevel(log_level)

# Formatter
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

# File Handler (New file per session)
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def cleanup_old_logs():
    """Keep only the most recent log files based on backupCount."""
    try:
        files = [os.path.join(LOG_DIR, f) for f in os.listdir(LOG_DIR) if f.startswith("server_") and f.endswith(".log")]
        files.sort(key=os.path.getmtime, reverse=True)
        
        if len(files) > config["backupCount"]:
            for old_file in files[config["backupCount"]:]:
                os.remove(old_file)
                # Use print because logger might not be fully ready or we don't want to log the deletion in the new log
                print(f"LogCleanup: Removed old log file: {os.path.basename(old_file)}")
    except Exception as e:
        print(f"LogCleanup: Error cleaning up logs: {e}")

cleanup_old_logs()
logger.info(f"Logging initialized. Session log: {os.path.basename(log_file)}")

# --- State Management ---
state = {
    "volume": config["defaultVolume"],
    "isPlaying": False,
    "currentTrack": {
        "trackName": "No song playing",
        "artistName": "",
        "albumName": "",
        "trackUri": "",
        "albumUri": "",
        "albumArtUrl": ""
    },
    "trackProgress": 0,
    "trackDuration": 0,
    "trackProgressStartTimestamp": 0,
    "backgroundPalette": None,
    "isShuffling": False,
    "repeatStatus": 0,
    "isLiked": False,
    "spicetifyClient": None,
    "lyrics": {
        "trackUri": "",
        "synced": [],
        "plain": "",
        "available": False,
        "instrumental": False,
        "loading": False
    }
}

_save_timer = None

# --- Lyrics (LRCLIB) ---

def parse_synced_lyrics(lrc_text):
    """Parse LRC format into [{time, text}] list (time in milliseconds)."""
    lines = []
    pattern = re.compile(r'\[(\d+):(\d+)[.,](\d+)\](.*)')
    for line in lrc_text.split('\n'):
        m = pattern.match(line.strip())
        if m:
            minutes = int(m.group(1))
            seconds = int(m.group(2))
            frac = m.group(3)
            text = m.group(4).strip()
            if len(frac) == 2:
                frac_ms = int(frac) * 10
            elif len(frac) == 3:
                frac_ms = int(frac)
            else:
                frac_ms = int(frac[:2]) * 10
            time_ms = (minutes * 60 + seconds) * 1000 + frac_ms
            lines.append({"time": time_ms, "text": text})
    return sorted(lines, key=lambda x: x["time"])

# --- Lyrics SQLite cache ---

def init_lyrics_cache():
    conn = sqlite3.connect(LYRICS_CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lyrics_cache (
            artist_name TEXT NOT NULL,
            track_name TEXT NOT NULL,
            album_name TEXT NOT NULL,
            duration INTEGER NOT NULL,
            synced_lyrics TEXT,
            plain_lyrics TEXT,
            instrumental INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (artist_name, track_name, album_name, duration)
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"Lyrics cache: Initialized at {LYRICS_CACHE_DB}")

def get_cached_lyrics(params):
    conn = sqlite3.connect(LYRICS_CACHE_DB)
    try:
        row = conn.execute(
            "SELECT synced_lyrics, plain_lyrics, instrumental FROM lyrics_cache WHERE artist_name=? AND track_name=? AND album_name=? AND duration=?",
            (params["artist_name"], params["track_name"], params["album_name"], params["duration"])
        ).fetchone()
        return row
    finally:
        conn.close()

def set_cached_lyrics(params, synced_lyrics, plain_lyrics, instrumental):
    conn = sqlite3.connect(LYRICS_CACHE_DB)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO lyrics_cache (artist_name, track_name, album_name, duration, synced_lyrics, plain_lyrics, instrumental) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (params["artist_name"], params["track_name"], params["album_name"], params["duration"], synced_lyrics, plain_lyrics, 1 if instrumental else 0)
        )
        conn.commit()
    finally:
        conn.close()

async def fetch_and_broadcast_lyrics(track_uri, track_name, artist_name, album_name, duration_ms):
    """Fetch lyrics from LRCLIB and broadcast to all clients. Skips if track changed."""
    duration_s = max(1, round(duration_ms / 1000))
    params = {
        "artist_name": artist_name,
        "track_name": track_name,
        "album_name": album_name,
        "duration": duration_s
    }
    logger.info(f"Lyrics: Fetching for '{track_name}' by '{artist_name}'")

    # Check local cache first
    cached = get_cached_lyrics(params)
    if cached:
        synced_raw, plain, instrumental = cached
        synced = parse_synced_lyrics(synced_raw) if synced_raw else []
        if state["currentTrack"]["trackUri"] != track_uri:
            return
        state["lyrics"] = {
            "trackUri": track_uri,
            "synced": synced,
            "plain": plain or "",
            "available": True,
            "instrumental": bool(instrumental),
            "loading": False
        }
        logger.info(f"Lyrics: Cache hit for '{track_name}' ({len(synced)} synced lines)")
        await broadcast_lyrics_update()
        return

    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "SpicetifyRemote/1.0 (https://github.com/dekub/spicetify-remote)"}) as session:
            async with session.get(
                "https://lrclib.net/api/get",
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if state["currentTrack"]["trackUri"] != track_uri:
                        logger.info("Lyrics: Track changed during fetch, discarding.")
                        return
                    synced_raw = data.get("syncedLyrics") or ""
                    plain = data.get("plainLyrics") or ""
                    instrumental = data.get("instrumental", False)
                    synced = parse_synced_lyrics(synced_raw) if synced_raw else []
                    state["lyrics"] = {
                        "trackUri": track_uri,
                        "synced": synced,
                        "plain": plain,
                        "available": True,
                        "instrumental": instrumental,
                        "loading": False
                    }
                    logger.info(f"Lyrics: Found {len(synced)} synced lines for '{track_name}'")
                    set_cached_lyrics(params, synced_raw, "" if synced_raw else plain, instrumental)
                    await broadcast_lyrics_update()
                elif resp.status == 404:
                    logger.info(f"Lyrics: Not found for '{track_name}'")
                    if state["currentTrack"]["trackUri"] == track_uri:
                        state["lyrics"] = {"trackUri": track_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "loading": False}
                        await broadcast_lyrics_update()
                else:
                    logger.warning(f"Lyrics: LRCLIB returned status {resp.status}")
    except asyncio.TimeoutError:
        logger.error(f"Lyrics: Timed out after 30s for '{track_name}' by '{artist_name}'")
    except Exception as e:
        logger.error(f"Lyrics: Fetch failed for '{track_name}': {type(e).__name__}: {e}")

def read_state_from_file():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved_state = json.load(f)
                state["volume"] = saved_state.get("volume", state["volume"])
                state["isPlaying"] = saved_state.get("isPlaying", state["isPlaying"])
                state["currentTrack"].update(saved_state.get("currentTrack", {}))
                state["isShuffling"] = saved_state.get("isShuffling", state["isShuffling"])
                state["repeatStatus"] = saved_state.get("repeatStatus", state["repeatStatus"])
                state["isLiked"] = saved_state.get("isLiked", state["isLiked"])
                logger.info("Server: Loaded state from state.json")
        except Exception as e:
            logger.error(f"Server: Error reading state file: {e}")

async def save_state_to_file_debounced():
    """Wait for a period of inactivity before saving to disk."""
    global _save_timer
    if _save_timer:
        _save_timer.cancel()
    
    _save_timer = asyncio.create_task(_actually_save_after_delay(2.0))

def get_current_save_data():
    return {
        "volume": round(state["volume"], 2),
        "isPlaying": state["isPlaying"],
        "currentTrack": state["currentTrack"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"]
    }

async def _actually_save_after_delay(delay):
    try:
        await asyncio.sleep(delay)
        # Run synchronous file writing in a thread to avoid blocking the event loop
        await asyncio.to_thread(_write_state_to_disk, get_current_save_data())
        logger.info("Server: Saved state to state.json (debounced)")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Server: Error in debounced save: {e}")

def _write_state_to_disk(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_state_to_file():
    _write_state_to_disk(get_current_save_data())

read_state_from_file()
init_lyrics_cache()

# --- Broadcasting ---
CLIENTS = {} # {ws: {"type": "unknown", "remote_ip": ""}}

async def broadcast(message, exclude_ws=None, target_type=None):
    if not CLIENTS: return
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
            # Progress update is mostly for controllers and widgets
            await broadcast_progress_update()
        await asyncio.sleep(1.0) # Increased interval, clients interpolate

# --- Message Handlers ---

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
    # Also push current lyrics so late-joining clients stay in sync
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
        state["volume"] = data["volume"]
    await save_state_to_file_debounced()
    await broadcast_volume_update() # Don't exclude sender - deck needs echo to update its display

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
    # Support for batched updates
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

    # Fetch lyrics when track changes
    if new_uri and new_uri != prev_uri and new_uri != state["lyrics"]["trackUri"]:
        state["lyrics"] = {"trackUri": new_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "loading": True}
        await broadcast_lyrics_update()
        asyncio.create_task(fetch_and_broadcast_lyrics(
            new_uri,
            state["currentTrack"]["trackName"],
            state["currentTrack"]["artistName"],
            state["currentTrack"]["albumName"],
            state["trackDuration"]
        ))

    await save_state_to_file_debounced()
    await broadcast_current_state(exclude_ws=ws)

async def handle_progress_update(ws, data):
    state["trackProgress"] = data.get("progress", 0)
    state["trackDuration"] = data.get("duration", 0)
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await broadcast_progress_update(exclude_ws=ws)

async def handle_playback_control(ws, data):
    # Commands from clients go ONLY to Spicetify
    await broadcast(data, target_type="spicetify", exclude_ws=ws)

async def handle_like_command(ws, data):
    await broadcast({"type": "playbackControl", "command": "like"}, target_type="spicetify", exclude_ws=ws)

MESSAGE_HANDLERS = {
    "register": handle_register,
    "getInitialState": handle_get_initial_state,
    "stateUpdate": handle_track_update, # Snapshot from client
    "volumeUpdate": handle_volume_update,
    "playbackUpdate": handle_playback_update,
    "shuffleUpdate": handle_shuffle_update,
    "repeatUpdate": handle_repeat_update,
    "likeUpdate": handle_like_update,
    "trackUpdate": handle_track_update, # Delta from client
    "progressUpdate": handle_progress_update,
    "playbackControl": handle_playback_control,
    "like": handle_like_command
}

async def handle_message(ws, message):
    try:
        data = json.loads(message)
        msg_type = data.get("type")
        handler = MESSAGE_HANDLERS.get(msg_type)
        if handler:
            await handler(ws, data)
        else:
            logger.warning(f"Server: Received unknown message type: {msg_type}")
    except Exception as e:
        logger.error(f"Server: Failed to handle message: {e}")

# --- Unified WebSocket Handler ---
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    # Identify client type from query params
    client_type = request.query.get("client", "unknown")
    CLIENTS[ws] = {"type": client_type, "remote_ip": request.remote}
    
    logger.info(f"New connection: {client_type} ({request.remote})")
    
    if client_type == "spicetify":
        state["spicetifyClient"] = ws
    else:
        # Send initial state sync immediately to non-spicetify clients
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


# --- API & Static Hosting ---
async def handle_config(request):
    headers = {"Access-Control-Allow-Origin": ",".join(config["allowedOrigins"])}
    return web.json_response({
        "port": config["port"],
        "discoveryPort": DISCOVERY_PORT,
        "allowedOrigins": config["allowedOrigins"],
        "defaultVolume": config["defaultVolume"],
        "enableOBS": config.get("enableOBS", True),
        "enableWebsite": config.get("enableWebsite", True)
    }, headers=headers)

async def index_handler(request):
    # Differentiate between WebSocket and browser request
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await websocket_handler(request)
    return web.FileResponse(os.path.join(BASE_DIR, 'website', 'index.html'))

async def obs_handler(request):
    # Ensure there's a trailing slash so relative assets load correctly
    if not request.path.endswith('/'):
        return web.HTTPFound(request.path + '/')
    return web.FileResponse(os.path.join(BASE_DIR, 'obs-widget', 'obs-widget.html'))

async def main():
    # Main Server (Static Files + WebSocket on SAME port)
    main_app = web.Application()
    
    # Specific Routes (Matches Node.js logic)
    main_app.router.add_get('/', index_handler)
    main_app.router.add_get('/obs', obs_handler)
    main_app.router.add_get('/obs/', obs_handler)
    main_app.router.add_get('/api/config', handle_config)
    
    # Static Files for assets (CSS, JS, Images)
    main_app.router.add_static('/obs/', os.path.join(BASE_DIR, 'obs-widget'))
    main_app.router.add_static('/', os.path.join(BASE_DIR, 'website'))

    main_runner = web.AppRunner(main_app)
    await main_runner.setup()
    
    # Config Server (Secondary port for Spicetify discovery)
    config_app = web.Application()
    config_app.router.add_get('/api/config', handle_config)
    config_runner = web.AppRunner(config_app)
    await config_runner.setup()

    logger.info(f"Main Server: http://localhost:{config['port']}")
    logger.info(f"Discovery Server: http://localhost:{DISCOVERY_PORT}")
    
    stop_event = asyncio.Event()

    try:
        # Create background tasks for servers and broadcasting
        main_site = web.TCPSite(main_runner, '0.0.0.0', config['port'])
        config_site = web.TCPSite(config_runner, '0.0.0.0', DISCOVERY_PORT)
        
        await main_site.start()
        await config_site.start()
        
        progress_task = asyncio.create_task(start_progress_broadcasting())
        
        # Wait until the event is set or interrupted
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Server: Stopping...")
    finally:
        logger.info("Server: Shutting down, performing final state save...")
        
        # Cancel any pending debounced save
        global _save_timer
        if _save_timer:
            _save_timer.cancel()
            logger.debug("Server: Pending save timer cancelled.")

        # Final save
        save_state_to_file()
        logger.info("Server: State saved to disk.")

        # Force close all active websockets to prevent cleanup hang
        if CLIENTS:
            logger.debug(f"Server: Closing {len(CLIENTS)} active connections...")
            for ws in list(CLIENTS.keys()):
                try:
                    asyncio.create_task(ws.close(code=1001, message='Server shutting down'))
                except Exception:
                    pass
        
        # Clean up tasks
        if 'progress_task' in locals():
            logger.debug("Server: Cancelling progress broadcasting task...")
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
            logger.debug("Server: Progress broadcasting task stopped.")
            
        logger.debug("Server: Cleaning up main runner...")
        await main_runner.cleanup()
        logger.debug("Server: Main runner cleaned up.")

        logger.debug("Server: Cleaning up config runner...")
        await config_runner.cleanup()
        logger.debug("Server: Config runner cleaned up.")
        
        logger.info("Server: Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())
