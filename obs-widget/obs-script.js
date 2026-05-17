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
  lyricLine: document.getElementById("lyricLine"),
};

// Lyrics state
const lyricsState = {
  synced: [],
  plain: "",
  available: false,
  instrumental: false,
  loading: false,
  currentIndex: -1,
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

// --- Profanity Filter ---

// Base64-encoded list of slurs/offensive words to filter out of lyrics.
// Decode and split to get the plaintext array.
const slurList = atob("YmVhbmVyLGJlYW5lcnMsY2hpbmssY2hpbmtzLGNoaW5reSxjb29uLGNvb25zLGNvb255LGNyYWNrZXIsY3JhY2tlcnMsY3VudCxjdW50cyxkYWdvLGRhZ29zLGR5a2UsZHlrZXMsZHlrZXksZXNraW1vLGZhZyxmYWdnb3QsZmFnZ290cyxmYWdzLGdpcHN5LGdvb2ssZ3lwc3ksaGFqamksaHVuLGppZ2Fib28samlnZyxraWtlLGtpa2VzLGtyYXV0LGt5a2UsbmlnLG5pZ2csbmlnZ2EsbmlnZ2FzLG5pZ2dheixuaWdnZXIsbmlnZ2VycyxuaXAscGlrZXkscG9yY2htb25rZXkscG9yY2gtbW9ua2V5LHJhZ2hlYWQscmVkc2tpbixyZXRhcmQscmV0YXJkZWQscmV0YXJkcyxzYW5kbmlnZ2VyLHNhbmQtbmlnZ2VyLHNoZW1hbGUsc2hlLW1hbGUsc2xhbnRleWUsc2xhbnQtZXllLHNwZWFyY2h1Y2tlcixzcGljLHNwaWNrLHNwaWNzLHNwaWssdG93ZWxoZWFkLHRyYW5uaWVzLHRyYW5ueSx0d2F0LHdldGJhY2ssd2V0YmFja3Msd29wLHdvcHMsemlwcGVyaGVhZA==").split(",");

function filterText(text) {
  if (!text) return text;
  let result = text;
  for (const slur of slurList) {
    const regex = new RegExp(`\\b${slur.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "gi");
    result = result.replace(regex, (m) => "*".repeat(m.length));
  }
  return result;
}

// --- Lyrics ---

function setLyricLineText(text) {
  text = filterText(text);
  const el = elements.lyricLine;
  if (el.textContent === text) return;
  const visible = text.length > 0;
  el.classList.add("fade");
  setTimeout(() => {
    el.textContent = text;
    el.classList.remove("fade");
    el.classList.toggle("hidden", !visible);
  }, 350);
}

function handleLyricsUpdate(data) {
  lyricsState.available = data.available;
  lyricsState.instrumental = data.instrumental;
  lyricsState.synced = data.synced || [];
  lyricsState.plain = data.plain || "";
  lyricsState.currentIndex = -1;

  lyricsState.loading = data.loading || false;

  if (data.instrumental) {
    setLyricLineText("🎵");
  } else if (lyricsState.loading) {
    setLyricLineText("...");
  } else if (!data.available) {
    setLyricLineText("");
  } else if (!lyricsState.synced.length && lyricsState.plain) {
    setLyricLineText("");
  }
}

function updateCurrentLyricLine(progressMs) {
  if (!lyricsState.available || !lyricsState.synced.length) return;

  let newIndex = -1;
  for (let i = lyricsState.synced.length - 1; i >= 0; i--) {
    if (progressMs >= lyricsState.synced[i].time) {
      newIndex = i;
      break;
    }
  }

  if (newIndex === lyricsState.currentIndex) return;
  lyricsState.currentIndex = newIndex;
  const text = newIndex >= 0 ? (lyricsState.synced[newIndex].text || "♪") : "";
  setLyricLineText(text);
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
    updateCurrentLyricLine(currentProgress);
  }
  requestAnimationFrame(animate);
}

function connect() {
  if (!serverUrl) {
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg) => {
        serverUrl = `ws://${window.location.hostname}:${cfg.port}/?client=obs`;
        connect();
      })
      .catch(() => setTimeout(connect, 2000));
    return;
  }

  ws = new WebSocket(serverUrl);

  ws.onopen = () => {
    // Register handled by query param
  };

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

    // Handle Lyrics
    if (data.type === "lyricsUpdate") {
      handleLyricsUpdate(data);
    }
  };

  ws.onclose = () => setTimeout(connect, 2000);
}

document.addEventListener("DOMContentLoaded", () => {
  connect();
  requestAnimationFrame(animate);
});
