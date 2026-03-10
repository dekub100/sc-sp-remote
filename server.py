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

def save_state_to_file():
    rounded_volume = round(state["volume"], 2)
    current_state_to_save = {
        "volume": rounded_volume,
        "isPlaying": state["isPlaying"],
        "currentTrack": state["currentTrack"],
        "isShuffling": state["isShuffling"],
        "repeatStatus": state["repeatStatus"],
        "isLiked": state["isLiked"]
    }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(current_state_to_save, f, indent=2)
        print("Server: Saved state to state.json")
    except Exception as e:
        print(f"Server: Error writing state file: {e}")

read_state_from_file()

# --- Broadcasting ---
CLIENTS = set()

async def broadcast(message, exclude_ws=None):
    if not CLIENTS: return
    msg = json.dumps(message)
    # Use a copy of the set to avoid "Set size changed during iteration" errors
    for ws in list(CLIENTS):
        if ws == exclude_ws:
            continue
        try:
            await ws.send_str(msg)
        except Exception:
            CLIENTS.discard(ws)

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
        "timestamp": time.time() * 1000  # Sync timestamp
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
            # Increment progress from the anchor
            state["trackProgress"] = min(state["trackProgress"] + elapsed_time, state["trackDuration"])
            state["trackProgressStartTimestamp"] = now
            await broadcast_progress_update()
        await asyncio.sleep(0.5) # Reduced frequency since clients will interpolate

# --- Message Handlers ---
async def handle_message(ws, message):
    try:
        data = json.loads(message)
        print(f"Received message: {data}")
        msg_type = data.get("type")
        
        if msg_type == "volumeUpdate":
            volume_step = config.get("volumeStep", 0.05)
            if data.get("command") == "volumeUp":
                state["volume"] = min(1.0, state["volume"] + volume_step)
            elif data.get("command") == "volumeDown":
                state["volume"] = max(0.0, state["volume"] - volume_step)
            elif "volume" in data:
                state["volume"] = data["volume"]
            save_state_to_file()
            await broadcast_volume_update(exclude_ws=ws)
                
        elif msg_type == "playbackUpdate":
            state["isPlaying"] = data.get("isPlaying", False)
            state["trackProgress"] = data.get("progress", state["trackProgress"])
            state["trackProgressStartTimestamp"] = time.time() * 1000
            save_state_to_file()
            await broadcast_playback_update(exclude_ws=ws)
            
        elif msg_type == "shuffleUpdate":
            state["isShuffling"] = data.get("isShuffling", False)
            save_state_to_file()
            await broadcast({"type": "shuffleUpdate", "isShuffling": state["isShuffling"]}, exclude_ws=ws)
            
        elif msg_type == "repeatUpdate":
            state["repeatStatus"] = data.get("repeatStatus", 0)
            save_state_to_file()
            await broadcast({"type": "repeatUpdate", "repeatStatus": state["repeatStatus"]}, exclude_ws=ws)
            
        elif msg_type == "likeUpdate":
            state["isLiked"] = data.get("isLiked", False)
            save_state_to_file()
            await broadcast({"type": "likeUpdate", "isLiked": state["isLiked"]}, exclude_ws=ws)
            
        elif msg_type == "trackUpdate":
            state["currentTrack"] = {
                "trackName": data.get("trackName", "Unknown Track"),
                "artistName": data.get("artistName", "Unknown Artist"),
                "albumName": data.get("albumName", "Unknown Album"),
                "trackUri": data.get("trackUri", ""),
                "albumUri": data.get("albumUri", ""),
                "albumArtUrl": data.get("albumArtUrl", "")
            }
            state["trackDuration"] = data.get("duration", 0)
            state["trackProgress"] = data.get("progress", 0)
            state["trackProgressStartTimestamp"] = time.time() * 1000
            save_state_to_file()
            await broadcast_current_state(exclude_ws=ws)
            
        elif msg_type == "progressUpdate":
            state["trackProgress"] = data.get("progress", 0)
            state["trackDuration"] = data.get("duration", 0)
            state["trackProgressStartTimestamp"] = time.time() * 1000
            await broadcast_progress_update(exclude_ws=ws)
            
        elif msg_type == "like":
            await broadcast({"type": "playbackControl", "command": "like"}, exclude_ws=ws)
            
        elif msg_type == "playbackControl":
            cmd = data.get("command")
            if cmd not in ["volumeUp", "volumeDown"]:
                await broadcast({
                    "type": "playbackControl",
                    "command": cmd,
                    "position": data.get("position")
                }, exclude_ws=ws)
        else:
            print(f"Unknown message type: {msg_type}")
            
    except Exception as e:
        print(f"Failed to parse message: {e}")

# --- Unified WebSocket Handler ---
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    CLIENTS.add(ws)
    print("Client connected via WebSocket.")
    
    if state["spicetifyClient"] is None:
        state["spicetifyClient"] = ws
        print("Spicetify client identified.")
        
    # Send initial state sync
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
        "isLiked": state["isLiked"]
    }
    await ws.send_str(json.dumps(initial_state))
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await handle_message(ws, msg.data)
            elif msg.type == web.WSMsgType.ERROR:
                print(f'WebSocket connection closed with exception {ws.exception()}')
    finally:
        CLIENTS.discard(ws)
        if ws == state["spicetifyClient"]:
            state["spicetifyClient"] = None
            print("Spicetify client disconnected.")
    
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
    
    await asyncio.gather(
        web.TCPSite(main_runner, '0.0.0.0', config['port']).start(),
        web.TCPSite(config_runner, '0.0.0.0', DISCOVERY_PORT).start(),
        start_progress_broadcasting()
    )
    
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
