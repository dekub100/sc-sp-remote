// This script connects to the Node.js server to sync volume and playback.
// This version ensures all DOM elements are loaded before attempting to connect
// or add event listeners, which fixes issues with button functionality.

const SERVER_URL = "ws://localhost:8888";
// Use a Data URI for the fallback image. This embeds the image data directly in the code,
// making it impossible for ad blockers to block.
const FALLBACK_ALBUM_ART =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'><rect width='200' height='200' fill='%23535353'/><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' font-family='Arial, Helvetica, sans-serif' font-size='20' fill='%23FFFFFF'>No Art</text></svg>";

// Get DOM elements. This must be done inside the DOMContentLoaded listener to guarantee they exist.
let volumeSlider;
let volumeValueSpan;
let previousBtn;
let playPauseBtn;
let nextBtn;
let albumArtImg;
let songTitleElem;
let artistNameElem;

// New elements for the progress bar
let progressBar;
let currentTimeElem;
let durationTimeElem;

let ws;
let isPlaying = false;
let isSeeking = false; // Prevents the progress bar from updating while the user is dragging it.

/**
 * Connects to the WebSocket server and sets up event listeners.
 */
function connectWebSocket() {
  try {
    ws = new WebSocket(SERVER_URL);

    ws.onopen = () => {
      console.log("Website: Connected to server.");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "stateUpdate") {
          // Update volume and playback state if they are different.
          if (data.volume !== undefined) {
            const volume = parseFloat(data.volume);
            volumeSlider.value = volume;
            volumeValueSpan.textContent = `${Math.round(volume * 100)}%`;
          }
          if (data.isPlaying !== undefined) {
            isPlaying = data.isPlaying;
            updatePlayPauseButton(isPlaying);
          }
          // Update track information if available.
          if (data.trackName !== undefined) {
            songTitleElem.textContent = data.trackName;
            artistNameElem.textContent = data.artistName;
            // Use a dedicated function to handle image loading
            setAlbumArt(data.albumArtUrl);
          }
          // Update track progress if available.
          if (
            data.progress !== undefined &&
            data.duration !== undefined &&
            !isSeeking
          ) {
            progressBar.max = data.duration;
            progressBar.value = data.progress;
            currentTimeElem.textContent = formatTime(data.progress);
            durationTimeElem.textContent = formatTime(data.duration);
          }
        }
      } catch (error) {
        console.error("Website: Failed to parse message from server:", error);
      }
    };

    ws.onclose = () => {
      console.log(
        "Website: Disconnected from server. Attempting to reconnect in 5 seconds..."
      );
      // Attempt to reconnect after a delay.
      setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (error) => {
      console.error("Website: WebSocket error:", error);
      // Close the connection explicitly if an error occurs.
      ws.close();
    };
  } catch (error) {
    console.error("Website: Could not connect to WebSocket server:", error);
    // Attempt to reconnect after a delay.
    setTimeout(connectWebSocket, 5000);
  }
}

/**
 * Handles the loading of the album art image to prevent broken image flashes.
 * @param {string} url - The URL of the album art.
 */
function setAlbumArt(url) {
  if (!url) {
    albumArtImg.src = FALLBACK_ALBUM_ART;
    return;
  }
  // Create a new image object to handle loading
  const tempImage = new Image();
  tempImage.onload = () => {
    // If it loads successfully, update the main image
    albumArtImg.src = url;
  };
  tempImage.onerror = () => {
    // If it fails, use the placeholder
    albumArtImg.src = FALLBACK_ALBUM_ART;
    console.error(
      "Website: Failed to load album art from URL, using placeholder."
    );
  };
  // Set the source to start loading the image
  tempImage.src = url;
}

/**
 * Toggles the icon and color of the play/pause button.
 * @param {boolean} isPlayingState - The current playback state.
 */
function updatePlayPauseButton(isPlayingState) {
  const playIcon = playPauseBtn.querySelector(".fa-play");
  const pauseIcon = playPauseBtn.querySelector(".fa-pause");
  if (isPlayingState) {
    playIcon.style.display = "none";
    pauseIcon.style.display = "inline-block";
    playPauseBtn.classList.add("playing");
  } else {
    playIcon.style.display = "inline-block";
    pauseIcon.style.display = "none";
    playPauseBtn.classList.remove("playing");
  }
}

/**
 * Formats a time in milliseconds into a readable minute:second string.
 * @param {number} ms - Time in milliseconds.
 * @returns {string} The formatted time string.
 */
function formatTime(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

// Ensure the DOM is fully loaded before running the script.
document.addEventListener("DOMContentLoaded", () => {
  // Get DOM elements.
  volumeSlider = document.getElementById("volumeSlider");
  volumeValueSpan = document.getElementById("volumeValue");
  previousBtn = document.getElementById("previousBtn");
  playPauseBtn = document.getElementById("playPauseBtn");
  nextBtn = document.getElementById("nextBtn");
  albumArtImg = document.getElementById("albumArt");
  songTitleElem = document.getElementById("songTitle");
  artistNameElem = document.getElementById("artistName");

  // New elements for the progress bar
  progressBar = document.getElementById("progressBar");
  currentTimeElem = document.getElementById("currentTime");
  durationTimeElem = document.getElementById("durationTime");

  // Event listener for the volume slider.
  volumeSlider.addEventListener("input", (event) => {
    const newVolume = parseFloat(event.target.value);
    volumeValueSpan.textContent = `${Math.round(newVolume * 100)}%`;

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "volumeUpdate", volume: newVolume }));
    }
  });

  // Event listeners for playback control buttons.
  previousBtn.addEventListener("click", () => {
    console.log("Website: Sending 'previous' command to server.");
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "playbackControl", command: "previous" }));
    }
  });

  playPauseBtn.addEventListener("click", () => {
    console.log("Website: Sending 'togglePlay' command to server.");
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({ type: "playbackControl", command: "togglePlay" })
      );
    }
  });

  nextBtn.addEventListener("click", () => {
    console.log("Website: Sending 'next' command to server.");
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "playbackControl", command: "next" }));
    }
  });

  // Event listeners for the progress bar.
  progressBar.addEventListener("mousedown", () => {
    isSeeking = true;
  });

  progressBar.addEventListener("mouseup", (event) => {
    isSeeking = false;
    const newProgress = parseInt(event.target.value);
    console.log(
      "Website: Sending 'seek' command to server with new position:",
      newProgress
    );
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "playbackControl",
          command: "seek",
          position: newProgress,
        })
      );
    }
  });

  progressBar.addEventListener("input", (event) => {
    currentTimeElem.textContent = formatTime(event.target.value);
  });

  connectWebSocket();
});
