const fs = require("fs");
const path = require("path");
const config = require("./config");

const stateFilePath = path.join(__dirname, "..", "state.json");

let state = {
  volume: config.defaultVolume,
  isPlaying: false,
  currentTrack: {
    trackName: "No song playing",
    artistName: "",
    albumArtUrl: "",
  },
  trackProgress: 0,
  trackDuration: 0,
  progressUpdateInterval: null,
  trackProgressStartTimestamp: 0,
  backgroundPalette: null,
  isShuffling: false,
  repeatStatus: 0,
  isLiked: false,
  spicetifyClient: null,
};

function readStateFromFile() {
  try {
    if (fs.existsSync(stateFilePath)) {
      const rawData = fs.readFileSync(stateFilePath);
      const savedState = JSON.parse(rawData);
      state.volume = savedState.volume || state.volume;
      state.isPlaying = savedState.isPlaying || state.isPlaying;
      state.currentTrack = savedState.currentTrack || state.currentTrack;
      state.isShuffling = savedState.isShuffling || state.isShuffling;
      state.repeatStatus = savedState.repeatStatus || state.repeatStatus;
      state.isLiked = savedState.isLiked || state.isLiked;
      console.log("Server: Loaded state from state.json");
    } else {
      console.log("Server: No state.json file found. Using default state.");
    }
  } catch (error) {
    console.error("Server: Error reading state file:", error);
  }
}

function saveStateToFile() {
  const roundedVolume = Math.round(state.volume * 100) / 100;
  const currentStateToSave = {
    volume: roundedVolume,
    isPlaying: state.isPlaying,
    currentTrack: state.currentTrack,
    isShuffling: state.isShuffling,
    repeatStatus: state.repeatStatus,
    isLiked: state.isLiked,
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

readStateFromFile();

module.exports = {
  state,
  readStateFromFile,
  saveStateToFile,
};
