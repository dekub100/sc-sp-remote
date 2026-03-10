// Simplified OBS Widget Script with Client-Side Color Extraction
let ws;
let serverUrl = null;

// Interpolation state
let lastState = {
  progress: 0,
  duration: 0,
  isPlaying: false,
  timestamp: Date.now(),
};

const elements = {
  albumArt: document.getElementById("albumArt"),
  songTitle: document.getElementById("songTitle"),
  artistName: document.getElementById("artistName"),
  albumName: document.getElementById("albumName"),
  progressBarFill: document.getElementById("progressBarFill"),
  currentTime: document.getElementById("currentTime"),
  totalTime: document.getElementById("totalTime"),
  container: document.querySelector(".widget-container"),
};

// Canvas for color extraction (hidden)
const canvas = document.createElement("canvas");
const ctx = canvas.getContext("2d", { willReadFrequently: true });

function formatTime(ms) {
  if (isNaN(ms) || ms < 0) return "0:00";
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
}

function updateMarquee(element, text) {
  const wrapper = element.querySelector(".marquee-wrapper");
  if (!wrapper) return;
  if (wrapper.textContent === text) return;

  wrapper.textContent = text;
  wrapper.setAttribute("data-text", text);
  element.classList.remove("marquee-active");
  setTimeout(() => {
    if (wrapper.scrollWidth > element.clientWidth) {
      const duration = Math.max(10, text.length / 2);
      element.style.setProperty("--duration", `${duration}s`);
      element.classList.add("marquee-active");
    }
  }, 100);
}

/**
 * Extracts dominant colors from the image using Canvas API
 */
function updateDynamicColors(img) {
  try {
    canvas.width = 50;
    canvas.height = 50;
    ctx.drawImage(img, 0, 0, 50, 50);

    const imageData = ctx.getImageData(0, 0, 50, 50).data;
    let r = 0,
      g = 0,
      b = 0,
      count = 0;

    for (let i = 0; i < imageData.length; i += 16) {
      r += imageData[i];
      g += imageData[i + 1];
      b += imageData[i + 2];
      count++;
    }

    r = Math.floor(r / count);
    g = Math.floor(g / count);
    b = Math.floor(b / count);

    const bgR = Math.floor(r * 0.4);
    const bgG = Math.floor(g * 0.4);
    const bgB = Math.floor(b * 0.4);

    elements.container.style.background = `rgba(${bgR}, ${bgG}, ${bgB}, 0.65)`;
    elements.progressBarFill.style.background = `rgb(${r}, ${g}, ${b}, 1)`;
  } catch (e) {
    console.error("Color extraction failed:", e);
  }
}

// Smooth interpolation loop
function animate() {
  if (lastState.isPlaying) {
    const now = Date.now();
    const elapsed = now - lastState.timestamp;
    const currentProgress = Math.min(
      lastState.progress + elapsed,
      lastState.duration
    );

    if (lastState.duration > 0) {
      const pct = (currentProgress / lastState.duration) * 100;
      elements.progressBarFill.style.width = `${pct}%`;
      elements.currentTime.textContent = formatTime(currentProgress);
    }
  }
  requestAnimationFrame(animate);
}

function connect() {
  if (!serverUrl) {
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg) => {
        serverUrl = `ws://${window.location.hostname}:${cfg.port}`;
        connect();
      })
      .catch(() => setTimeout(connect, 2000));
    return;
  }

  ws = new WebSocket(serverUrl);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    // Handle Track Info
    if (data.type === "stateUpdate" || data.type === "trackUpdate") {
      if (data.trackName) updateMarquee(elements.songTitle, data.trackName);
      if (data.artistName) updateMarquee(elements.artistName, data.artistName);
      if (data.albumName) updateMarquee(elements.albumName, data.albumName);

      if (data.albumArtUrl && elements.albumArt.src !== data.albumArtUrl) {
        elements.albumArt.crossOrigin = "Anonymous";
        elements.albumArt.src = data.albumArtUrl;
        elements.albumArt.onload = () => updateDynamicColors(elements.albumArt);
      }
    }

    // Handle Playback State
    if (data.isPlaying !== undefined) {
      lastState.isPlaying = data.isPlaying;
    }

    // Handle Progress
    if (data.progress !== undefined) {
      lastState.progress = data.progress;
      lastState.duration = data.duration ?? lastState.duration;
      lastState.timestamp = data.timestamp ?? Date.now();

      if (lastState.duration > 0) {
        const pct = (lastState.progress / lastState.duration) * 100;
        elements.progressBarFill.style.width = `${pct}%`;
        elements.currentTime.textContent = formatTime(lastState.progress);
        elements.totalTime.textContent = formatTime(lastState.duration);
      }
    }
  };

  ws.onclose = () => setTimeout(connect, 2000);
}

document.addEventListener("DOMContentLoaded", () => {
  connect();
  requestAnimationFrame(animate);
});
