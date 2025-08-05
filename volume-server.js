// This server uses the Express framework to serve the website files and
// a WebSocket server to communicate with the Spicetify extension.
const express = require("express");
const path = require("path");
const WebSocket = require("ws");
const http = require("http");
const fs = require("fs");

// Define the port for the web server and WebSocket server
const port = 8888;
const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Path to the state file
const stateFilePath = path.join(__dirname, "state.json");

let spicetifyClient = null;

// Store the current state of the player on the server
let isPlaying = false;
let volume = 0.5;
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
  }
}

// Call this function once on server startup
readStateFromFile();
startProgressBroadcasting(); // Start the progress broadcaster on server startup

/**
 * Configure Express to serve static files from the 'website' directory.
 * This is crucial for serving index.html, style.css, and script.js.
 */
app.use(express.static(path.join(__dirname, "website")));

// New route for the OBS widget
app.get("/obs", (req, res) => {
  res.sendFile(path.join(__dirname, "website", "obs-widget.html"));
});

app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "website", "index.html"));
});

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
    })
  );

  // The message listener is now 'async' so we can use 'await' inside.
  ws.on("message", async (message) => {
    try {
      const data = JSON.parse(message);
      console.log("Received message:", data);

      if (data.type === "volumeUpdate") {
        volume = data.volume;
        saveStateToFile(); // Save state on change
        // Broadcast to all other clients, but not the sender.
        wss.clients.forEach((c) => {
          if (c !== ws && c.readyState === WebSocket.OPEN) {
            c.send(
              JSON.stringify({
                type: "stateUpdate",
                volume: volume,
              })
            );
          }
        });
      } else if (data.type === "playbackUpdate") {
        isPlaying = data.isPlaying;
        saveStateToFile(); // Save state on change
        // Update the timestamp if the playback state changes.
        if (isPlaying) {
          trackProgressStartTimestamp = Date.now();
        } else {
          // Store the last known progress when paused
          trackProgress = data.progress;
        }

        wss.clients.forEach((c) => {
          if (c !== ws && c.readyState === WebSocket.OPEN) {
            c.send(
              JSON.stringify({
                type: "stateUpdate",
                isPlaying: isPlaying,
              })
            );
          }
        });
      } else if (data.type === "trackUpdate") {
        currentTrack = {
          trackName: data.trackName,
          artistName: data.artistName,
          albumArtUrl: data.albumArtUrl,
        };
        trackDuration = data.duration;
        trackProgress = data.progress; // Initial progress from Spicetify
        trackProgressStartTimestamp = Date.now(); // Reset timestamp for new track

        // Asynchronously get the new color palette from the album art
        await getPaletteFromUrl(currentTrack.albumArtUrl);
        saveStateToFile(); // Save state after palette is generated
        wss.clients.forEach((c) => {
          if (c.readyState === WebSocket.OPEN) {
            c.send(
              JSON.stringify({
                type: "stateUpdate",
                trackName: currentTrack.trackName,
                artistName: currentTrack.artistName,
                albumArtUrl: currentTrack.albumArtUrl,
                duration: trackDuration,
                backgroundPalette: backgroundPalette, // Send the new color palette
              })
            );
          }
        });
      } else if (data.type === "progressUpdate") {
        // We no longer rely on the client for continuous progress updates.
        // This is only used for the initial state and seeking.
        trackProgress = data.progress;
        trackDuration = data.duration;
        trackProgressStartTimestamp = Date.now();
        wss.clients.forEach((c) => {
          if (c !== ws && c.readyState === WebSocket.OPEN) {
            c.send(
              JSON.stringify({
                type: "stateUpdate",
                progress: trackProgress,
                duration: trackDuration,
              })
            );
          }
        });
      } else if (data.type === "playbackControl") {
        // This is a playback control message from the website.
        // We now broadcast it to all clients, but specifically expect the Spicetify client to handle it.
        console.log(
          `Server: Broadcasting playback control command: ${data.command}`
        );
        wss.clients.forEach((c) => {
          if (c.readyState === WebSocket.OPEN) {
            c.send(
              JSON.stringify({
                type: "playbackControl",
                command: data.command,
                position: data.position, // Forward the new position for the 'seek' command
              })
            );
          }
        });
      }
    } catch (error) {
      console.error("Failed to parse message:", error);
    }
  });

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

// Start the server
server.listen(port, () => {
  console.log(`Server is running at http://localhost:${port}`);
  console.log(`WebSocket server is listening on port ${port}`);
});
