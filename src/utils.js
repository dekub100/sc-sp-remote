const WebSocket = require("ws");
const { state } = require("./state");

let wss;

function setWss(webSocketServer) {
  wss = webSocketServer;
}

function broadcast(message) {
  if (!wss) return;
  wss.clients.forEach((c) => {
    if (c.readyState === WebSocket.OPEN) {
      c.send(JSON.stringify(message));
    }
  });
}

function broadcastToOthers(ws, message) {
  if (!wss) return;
  wss.clients.forEach((c) => {
    if (c !== ws && c.readyState === WebSocket.OPEN) {
      c.send(JSON.stringify(message));
    }
  });
}

async function getPaletteFromUrl(url) {
  if (!url) {
    state.backgroundPalette = null;
    return;
  }
  try {
    const { Vibrant } = await import("node-vibrant/node");
    const palette = await Vibrant.from(url).getPalette();
    state.backgroundPalette = {
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
    state.backgroundPalette = null;
    broadcast({ type: "error", message: "Failed to get color palette" });
  }
}

function startProgressBroadcasting() {
  if (state.progressUpdateInterval) {
    clearInterval(state.progressUpdateInterval);
  }

  state.progressUpdateInterval = setInterval(() => {
    if (state.isPlaying) {
      const elapsedTime = Date.now() - state.trackProgressStartTimestamp;
      const newProgress = Math.min(
        state.trackProgress + elapsedTime,
        state.trackDuration
      );
      if (newProgress !== state.trackProgress) {
        state.trackProgress = newProgress;
        broadcast({
          type: "stateUpdate",
          progress: state.trackProgress,
          duration: state.trackDuration,
        });
      }
      state.trackProgressStartTimestamp = Date.now();
    }
  }, 250);
}

module.exports = {
  setWss,
  broadcast,
  broadcastToOthers,
  getPaletteFromUrl,
  startProgressBroadcasting,
};
