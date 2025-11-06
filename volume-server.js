// This server uses the Express framework to serve the website files and
// a WebSocket server to communicate with the Spicetify extension.
const express = require("express");
const path = require("path");
const WebSocket = require("ws");
const http = require("http");
const fs = require("fs");

// Load config
const configPath = path.join(__dirname, "config.json");
let config = {
  port: 8888,
  configPort: 54321,
  allowedOrigins: ["*"],
  defaultVolume: 0.5,
  enableOBS: true,
};
try {
  if (fs.existsSync(configPath)) {
    config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  }
} catch (err) {
  console.error("Failed to read config.json, using defaults.", err);
}

const port = config.port;
const configPort = config.configPort;
const allowedOrigins = config.allowedOrigins;
const enableOBS = config.enableOBS;
const volumeStep = config.volumeStep || 0.05;

// Use defaultVolume from config
let volume = config.defaultVolume;

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Path to the state file
const stateFilePath = path.join(__dirname, "state.json");

let spicetifyClient = null;

// Store the current state of the player on the server
let isPlaying = false;
let currentTrack = {
  trackName: "No song playing",
  artistName: "",
  albumArtUrl: "",
};
let trackProgress = 0;
let trackDuration = 0;
let progressUpdateInterval; // Holds the setInterval for progress updates
let trackProgressStartTimestamp = 0; // Timestamp when the current track started
let backgroundPalette = null; // New variable to store the color palette

let isShuffling = false; // NEW: Track server-side shuffle state
let repeatStatus = 0; // NEW: Track server-side repeat state
let isLiked = false; // NEW: Track server-side liked state

/**
 * Reads the state from the state.json file on server startup.
 */
function readStateFromFile() {
  try {
    if (fs.existsSync(stateFilePath)) {
      const rawData = fs.readFileSync(stateFilePath);
      const savedState = JSON.parse(rawData);
      // Load saved state, using defaults if a key is missing
      volume = savedState.volume || volume;
      isPlaying = savedState.isPlaying || isPlaying;
      currentTrack = savedState.currentTrack || currentTrack;
      isShuffling = savedState.isShuffling || isShuffling; // NEW: Load shuffle state
      repeatStatus = savedState.repeatStatus || repeatStatus; // NEW: Load repeat state
      isLiked = savedState.isLiked || isLiked; // NEW: Load liked state
      // Do not load trackProgress or trackDuration from the file to avoid stale data
      console.log("Server: Loaded state from state.json");
    } else {
      console.log("Server: No state.json file found. Using default state.");
    }
  } catch (error) {
    console.error("Server: Error reading state file:", error);
  }
}

/**
 * Saves the current state to the state.json file.
 * This version only saves the stable, non-realtime state.
 */
function saveStateToFile() {
  // Round the volume to 2 decimal places before saving
  const roundedVolume = Math.round(volume * 100) / 100;
  const currentStateToSave = {
    volume: roundedVolume,
    isPlaying,
    currentTrack,
    isShuffling, // NEW: Save shuffle state
    repeatStatus, // NEW: Save repeat state
    isLiked, // NEW: Save liked state
  };
  try {
    fs.writeFileSync(
      stateFilePath,
      JSON.stringify(currentStateToSave, null, 2)
    );
    console.log("Server: Saved state to state.json");
  } catch (error) {
    console.error("Server: Error writing state file:", error);
  }
}

/**
 * Starts a progress broadcasting interval if one is not already running.
 */
function startProgressBroadcasting() {
  if (progressUpdateInterval) {
    clearInterval(progressUpdateInterval);
  }

  progressUpdateInterval = setInterval(() => {
    if (isPlaying) {
      const elapsedTime = Date.now() - trackProgressStartTimestamp;
      const newProgress = Math.min(trackProgress + elapsedTime, trackDuration);
      if (newProgress !== trackProgress) {
        trackProgress = newProgress;
        wss.clients.forEach((c) => {
          if (c.readyState === WebSocket.OPEN) {
            c.send(
              JSON.stringify({
                type: "stateUpdate",
                progress: trackProgress,
                duration: trackDuration,
              })
            );
          }
        });
      }
      // Reset start timestamp for the next interval
      trackProgressStartTimestamp = Date.now();
    }
  }, 250); // Broadcast every 250ms for smooth updates
}

/**
 * Gets a color palette from the provided image URL.
 * @param {string} url - The URL of the image to analyze.
 */
async function getPaletteFromUrl(url) {
  if (!url) {
    backgroundPalette = null;
    return;
  }
  try {
    // This is the fix. We use a dynamic import of the named export from the `node` subpath.
    const { Vibrant } = await import("node-vibrant/node");
    const palette = await Vibrant.from(url).getPalette();
    backgroundPalette = {
      // Corrected: use the .hex property directly instead of calling a non-existent method.
      vibrant: palette.Vibrant?.hex,
      darkVibrant: palette.DarkVibrant?.hex,
      lightVibrant: palette.LightVibrant?.hex,
      muted: palette.Muted?.hex,
      darkMuted: palette.DarkMuted?.hex,
      lightMuted: palette.LightMuted?.hex,
    };
    console.log("Server: Generated new color palette.");
  } catch (error) {
    console.error("Server: Failed to get color palette:", error);
    backgroundPalette = null;
    broadcast({ type: "error", message: "Failed to get color palette" });
  }
}

// Call this function once on server startup
readStateFromFile();
startProgressBroadcasting(); // Start the progress broadcaster on server startup

/**
 * Configure Express to serve static files from the 'website' directory.
 * This is crucial for serving index.html, style.css, and script.js.
 */
// Serve normal website files
app.use(express.static(path.join(__dirname, "website")));

// Serve OBS widget files only if enabled
if (enableOBS) {
  app.use("/obs", express.static(path.join(__dirname, "obs-widget")));
  app.get("/obs", (req, res) => {
    res.sendFile(path.join(__dirname, "obs-widget", "obs-widget.html"));
  });
}

// Route for the main website
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "website", "index.html"));
});

// Endpoint to get server config (port)
app.get("/api/config", (req, res) => {
  res.json({ port });
});

/**
 * Broadcasts a message to all connected WebSocket clients.
 * @param {object} message - The message to broadcast.
 */
function broadcast(message) {
  wss.clients.forEach((c) => {
    if (c.readyState === WebSocket.OPEN) {
      c.send(JSON.stringify(message));
    }
  });
}

/**
 * Broadcasts a message to all connected WebSocket clients except the sender.
 * @param {object} ws - The WebSocket connection of the sender.
 * @param {object} message - The message to broadcast.
 */
function broadcastToOthers(ws, message) {
  wss.clients.forEach((c) => {
    if (c !== ws && c.readyState === WebSocket.OPEN) {
      c.send(JSON.stringify(message));
    }
  });
}

async function handleMessage(ws, message) {
  try {
    const data = JSON.parse(message);
    console.log("Received message:", data);

    switch (data.type) {
      case "volumeUpdate":
        handleVolumeUpdate(ws, data);
        break;
      case "playbackUpdate":
        handlePlaybackUpdate(ws, data);
        break;
      case "shuffleUpdate":
        handleShuffleUpdate(ws, data);
        break;
      case "repeatUpdate":
        handleRepeatUpdate(ws, data);
        break;
      case "likeUpdate":
        handleLikeUpdate(ws, data);
        break;
      case "trackUpdate":
        await handleTrackUpdate(ws, data);
        break;
      case "progressUpdate":
        handleProgressUpdate(ws, data);
        break;
      case "like":
        handleLike(ws, data);
        break;
      case "playbackControl":
        handlePlaybackControl(ws, data);
        break;
      default:
        console.warn(`Unknown message type: ${data.type}`);
        ws.send(
          JSON.stringify({
            type: "error",
            message: `Unknown message type: ${data.type}`,
          })
        );
    }
  } catch (error) {
    console.error("Failed to parse message:", error);
    ws.send(JSON.stringify({ type: "error", message: "Invalid JSON format" }));
  }
}

function handleVolumeUpdate(ws, data) {
  if (data.command === "volumeUp") {
    volume = Math.min(1.0, volume + volumeStep);
    saveStateToFile();
    console.log(`Server: Volume increased to ${volume}`);
    broadcast({ type: "stateUpdate", volume: volume });
  } else if (data.command === "volumeDown") {
    volume = Math.max(0.0, volume - volumeStep);
    saveStateToFile();
    console.log(`Server: Volume decreased to ${volume}`);
    broadcast({ type: "stateUpdate", volume: volume });
  } else if (data.volume !== undefined) {
    volume = data.volume;
    saveStateToFile();
    broadcastToOthers(ws, { type: "stateUpdate", volume: volume });
  }
}

function handlePlaybackUpdate(ws, data) {
  isPlaying = data.isPlaying;
  saveStateToFile();
  if (isPlaying) {
    trackProgressStartTimestamp = Date.now();
  } else {
    trackProgress = data.progress;
  }
  broadcastToOthers(ws, { type: "stateUpdate", isPlaying: isPlaying });
}

function handleShuffleUpdate(ws, data) {
  isShuffling = data.isShuffling;
  saveStateToFile();
  broadcastToOthers(ws, { type: "stateUpdate", isShuffling: isShuffling });
}

function handleRepeatUpdate(ws, data) {
  repeatStatus = data.repeatStatus;
  saveStateToFile();
  broadcastToOthers(ws, { type: "stateUpdate", repeatStatus: repeatStatus });
}

function handleLikeUpdate(ws, data) {
  isLiked = data.isLiked;
  saveStateToFile();
  broadcastToOthers(ws, { type: "stateUpdate", isLiked: isLiked });
}

async function handleTrackUpdate(ws, data) {
  currentTrack = {
    trackName: data.trackName,
    artistName: data.artistName,
    albumArtUrl: data.albumArtUrl,
  };
  trackDuration = data.duration;
  trackProgress = data.progress;
  trackProgressStartTimestamp = Date.now();

  await getPaletteFromUrl(currentTrack.albumArtUrl);
  saveStateToFile();

  broadcast({
    type: "stateUpdate",
    trackName: currentTrack.trackName,
    artistName: currentTrack.artistName,
    albumArtUrl: currentTrack.albumArtUrl,
    duration: trackDuration,
    backgroundPalette: backgroundPalette,
  });
}

function handleProgressUpdate(ws, data) {
  trackProgress = data.progress;
  trackDuration = data.duration;
  trackProgressStartTimestamp = Date.now();
  broadcastToOthers(ws, {
    type: "stateUpdate",
    progress: trackProgress,
    duration: trackDuration,
  });
}

function handleLike(ws, data) {
  broadcast({ type: "playbackControl", command: "like" });
}

function handlePlaybackControl(ws, data) {
  console.log(`Server: Broadcasting playback control command: ${data.command}`);
  if (data.command !== "volumeUp" && data.command !== "volumeDown") {
    broadcast({
      type: "playbackControl",
      command: data.command,
      position: data.position,
    });
  }
}

// WebSocket server setup
wss.on("connection", (ws) => {
  console.log("Client connected.");

  // Identify the client type. For simplicity, we assume the first connection from Spicetify is the control client.
  // In a real-world scenario, you would use a more robust identification method.
  if (!spicetifyClient) {
    spicetifyClient = ws;
    console.log("Spicetify client identified.");
  }

  // Send the current state to the newly connected client.
  ws.send(
    JSON.stringify({
      type: "stateUpdate",
      volume: volume,
      isPlaying: isPlaying,
      trackName: currentTrack.trackName,
      artistName: currentTrack.artistName,
      albumArtUrl: currentTrack.albumArtUrl,
      progress: trackProgress,
      duration: trackDuration,
      backgroundPalette: backgroundPalette, // Send the current color palette
      isShuffling: isShuffling, // NEW: Send shuffle state
      repeatStatus: repeatStatus, // NEW: Send repeat state
      isLiked: isLiked, // NEW: Send liked state
    })
  );

  // The message listener is now 'async' so we can use 'await' inside.
  ws.on("message", (message) => handleMessage(ws, message));

  ws.on("close", () => {
    console.log("Client disconnected.");
    if (ws === spicetifyClient) {
      spicetifyClient = null;
      console.log("Spicetify client disconnected.");
    }
  });

  ws.on("error", (error) => {
    console.error("WebSocket error:", error);
  });
});

// Dedicated config server for Spicetify extension
const configServer = http.createServer((req, res) => {
  if (req.url === "/api/config") {
    res.writeHead(200, {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": allowedOrigins.join(","),
    });
    res.end(
      JSON.stringify({
        port,
        configPort,
        allowedOrigins,
        defaultVolume: config.defaultVolume,
        enableOBS,
      })
    );
  } else {
    res.writeHead(404, {
      "Access-Control-Allow-Origin": allowedOrigins.join(","),
    });
    res.end();
  }
});
configServer.listen(configPort, "127.0.0.1", () => {
  console.log(
    `Config server running at http://127.0.0.1:${configPort}/api/config`
  );
});

// Start the server
server.listen(port, "127.0.0.1", () => {
  console.log(`Server is running at http://127.0.0.1:${port}`);
  console.log(`WebSocket server is listening on 127.0.0.1:${port}`);
});
