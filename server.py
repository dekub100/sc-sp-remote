import asyncio
import json
import os
import time
from aiohttp import web

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_FILE = os.path.join(BASE_DIR, "state.json")

# Hard-coded Discovery Port (Standardized for all clients)
DISCOVERY_PORT = 54321

config = {
    "port": 8888,
    "allowedOrigins": ["*"],
    "defaultVolume": 0.5,
    "enableOBS": True,
    "enableWebsite": True,
    "volumeStep": 0.05
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Failed to read config.json, using defaults: {e}")

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
    "spicetifyClient": None
}

_save_timer = None

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
                print("Server: Loaded state from state.json")
        except Exception as e:
            print(f"Server: Error reading state file: {e}")

async def save_state_to_file_debounced():
    """Wait for a period of inactivity before saving to disk."""
    global _save_timer
    if _save_timer:
        _save_timer.cancel()
    
    _save_timer = asyncio.create_task(_actually_save_after_delay(2.0))

async def _actually_save_after_delay(delay):
    try:
        await asyncio.sleep(delay)
        rounded_volume = round(state["volume"], 2)
        current_state_to_save = {
            "volume": rounded_volume,
            "isPlaying": state["isPlaying"],
            "currentTrack": state["currentTrack"],
            "isShuffling": state["isShuffling"],
            "repeatStatus": state["repeatStatus"],
            "isLiked": state["isLiked"]
        }
        # Run synchronous file writing in a thread to avoid blocking the event loop
        await asyncio.to_thread(_write_state_to_disk, current_state_to_save)
        print("Server: Saved state to state.json (debounced)")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Server: Error in debounced save: {e}")

def _write_state_to_disk(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_state_to_file():
    # Deprecated for async handlers, but kept for sync initialization if needed
    rounded_volume = round(state["volume"], 2)
    current_state_to_save = {
        "volume": rounded_volume,
        "isPlaying": state["isPlaying"],
        "currentTrack": state["currentTrack"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"]
    }
    _write_state_to_disk(current_state_to_save)

read_state_from_file()

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
    print(f"Client registered as: {client_type}")

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

async def handle_volume_update(ws, data):
    volume_step = config.get("volumeStep", 0.05)
    if data.get("command") == "volumeUp":
        state["volume"] = min(1.0, state["volume"] + volume_step)
    elif data.get("command") == "volumeDown":
        state["volume"] = max(0.0, state["volume"] - volume_step)
    elif "volume" in data:
        state["volume"] = data["volume"]
    await save_state_to_file_debounced()
    await broadcast_volume_update()

async def handle_playback_update(ws, data):
    if "isPlaying" in data:
        state["isPlaying"] = data["isPlaying"]
    state["trackProgress"] = data.get("progress", state["trackProgress"])
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await save_state_to_file_debounced()
    await broadcast_playback_update()

async def handle_shuffle_update(ws, data):
    state["isShuffling"] = data.get("isShuffling", False)
    await save_state_to_file_debounced()
    await broadcast({"type": "shuffleUpdate", "isShuffling": state["isShuffling"]})

async def handle_repeat_update(ws, data):
    state["repeatStatus"] = data.get("repeatStatus", 0)
    await save_state_to_file_debounced()
    await broadcast({"type": "repeatUpdate", "repeatStatus": state["repeatStatus"]})

async def handle_like_update(ws, data):
    state["isLiked"] = data.get("isLiked", False)
    await save_state_to_file_debounced()
    await broadcast({"type": "likeUpdate", "isLiked": state["isLiked"]})

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
        
    state["currentTrack"].update({
        "trackName": data.get("trackName", state["currentTrack"]["trackName"]),
        "artistName": data.get("artistName", state["currentTrack"]["artistName"]),
        "albumName": data.get("albumName", state["currentTrack"]["albumName"]),
        "trackUri": data.get("trackUri", state["currentTrack"]["trackUri"]),
        "albumUri": data.get("albumUri", state["currentTrack"]["albumUri"]),
        "albumArtUrl": data.get("albumArtUrl", state["currentTrack"]["albumArtUrl"])
    })
    state["trackDuration"] = data.get("duration", state["trackDuration"])
    state["trackProgress"] = data.get("progress", state["trackProgress"])
    state["trackProgressStartTimestamp"] = time.time() * 1000
    
    await save_state_to_file_debounced()
    await broadcast_current_state()

async def handle_progress_update(ws, data):
    state["trackProgress"] = data.get("progress", 0)
    state["trackDuration"] = data.get("duration", 0)
    state["trackProgressStartTimestamp"] = time.time() * 1000
    await broadcast_progress_update()

async def handle_playback_control(ws, data):
    # Commands from clients go ONLY to Spicetify
    await broadcast(data, target_type="spicetify")

async def handle_like_command(ws, data):
    await broadcast({"type": "playbackControl", "command": "like"}, target_type="spicetify")

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
            print(f"Server: Received unknown message type: {msg_type}")
    except Exception as e:
        print(f"Server: Failed to handle message: {e}")

# --- Unified WebSocket Handler ---
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    # Identify client type from query params
    client_type = request.query.get("client", "unknown")
    CLIENTS[ws] = {"type": client_type, "remote_ip": request.remote}
    
    print(f"New connection: {client_type} ({request.remote})")
    
    if client_type == "spicetify":
        state["spicetifyClient"] = ws
        
    # Send initial state sync immediately
    await handle_get_initial_state(ws, {})
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await handle_message(ws, msg.data)
            elif msg.type == web.WSMsgType.ERROR:
                print(f'WebSocket connection closed with exception {ws.exception()}')
    finally:
        info = CLIENTS.pop(ws, None)
        if info and info.get("type") == "spicetify":
            state["spicetifyClient"] = None
        print(f"Disconnected: {info.get('type') if info else 'unknown'}")
    
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

    print(f"Main Server: http://localhost:{config['port']}")
    print(f"Discovery Server: http://localhost:{DISCOVERY_PORT}")
    
    try:
        await asyncio.gather(
            web.TCPSite(main_runner, '0.0.0.0', config['port']).start(),
            web.TCPSite(config_runner, '0.0.0.0', DISCOVERY_PORT).start(),
            start_progress_broadcasting()
        )
        await asyncio.Future()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        print("Server: Shutting down, performing final state save...")
        save_state_to_file()
        await main_runner.cleanup()
        await config_runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
