const { state, saveStateToFile } = require("./state");
const { broadcast, broadcastCurrentState, getPaletteFromUrl } = require("./utils"); // Import broadcastCurrentState
const config = require("./config");

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
  const volumeStep = config.volumeStep || 0.05;
  if (data.command === "volumeUp") {
    state.volume = Math.min(1.0, state.volume + volumeStep);
    saveStateToFile();
    console.log(`Server: Volume increased to ${state.volume}`);
    broadcastCurrentState(); // Use broadcastCurrentState
  } else if (data.command === "volumeDown") {
    state.volume = Math.max(0.0, state.volume - volumeStep);
    saveStateToFile();
    console.log(`Server: Volume decreased to ${state.volume}`);
    broadcastCurrentState(); // Use broadcastCurrentState
  } else if (data.volume !== undefined) {
    state.volume = data.volume;
    saveStateToFile();
    broadcastCurrentState(); // Use broadcastCurrentState
  }
}

function handlePlaybackUpdate(ws, data) {
  state.isPlaying = data.isPlaying;
  saveStateToFile();
  if (state.isPlaying) {
    state.trackProgressStartTimestamp = Date.now();
  } else {
    state.trackProgress = data.progress;
  }
  broadcastCurrentState(); // Use broadcastCurrentState
}

function handleShuffleUpdate(ws, data) {
  state.isShuffling = data.isShuffling;
  saveStateToFile();
  broadcastCurrentState(); // Use broadcastCurrentState
}

function handleRepeatUpdate(ws, data) {
  state.repeatStatus = data.repeatStatus;
  saveStateToFile();
  broadcastCurrentState(); // Use broadcastCurrentState
}

function handleLikeUpdate(ws, data) {
  state.isLiked = data.isLiked;
  saveStateToFile();
  broadcastCurrentState(); // Use broadcastCurrentState
}

async function handleTrackUpdate(ws, data) {
  state.currentTrack = {
    trackName: data.trackName,
    artistName: data.artistName,
    albumArtUrl: data.albumArtUrl,
  };
  state.trackDuration = data.duration;
  state.trackProgress = data.progress;
  state.trackProgressStartTimestamp = Date.now();

  await getPaletteFromUrl(state.currentTrack.albumArtUrl);
  saveStateToFile();

  broadcastCurrentState(); // Use broadcastCurrentState
}

function handleProgressUpdate(ws, data) {
  state.trackProgress = data.progress;
  state.trackDuration = data.duration;
  state.trackProgressStartTimestamp = Date.now();
  broadcastCurrentState(); // Use broadcastCurrentState
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

module.exports = { handleMessage };
