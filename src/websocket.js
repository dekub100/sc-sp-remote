const WebSocket = require("ws");
const { state } = require("./state");
const { handleMessage } = require("./message-handlers");
const { setWss } = require("./utils");

function setupWebSocket(server) {
  const wss = new WebSocket.Server({ server });
  setWss(wss);

  wss.on("connection", (ws) => {
    console.log("Client connected.");

    if (!state.spicetifyClient) {
      state.spicetifyClient = ws;
      console.log("Spicetify client identified.");
    }

    ws.send(
      JSON.stringify({
        type: "stateUpdate",
        volume: state.volume,
        isPlaying: state.isPlaying,
        trackName: state.currentTrack.trackName,
        artistName: state.currentTrack.artistName,
        albumArtUrl: state.currentTrack.albumArtUrl,
        progress: state.trackProgress,
        duration: state.trackDuration,
        backgroundPalette: state.backgroundPalette,
        isShuffling: state.isShuffling,
        repeatStatus: state.repeatStatus,
        isLiked: state.isLiked,
      })
    );

    ws.on("message", (message) => handleMessage(ws, message));

    ws.on("close", () => {
      console.log("Client disconnected.");
      if (ws === state.spicetifyClient) {
        state.spicetifyClient = null;
        console.log("Spicetify client disconnected.");
      }
    });

    ws.on("error", (error) => {
      console.error("WebSocket error:", error);
    });
  });

  return wss;
}

module.exports = { setupWebSocket };
