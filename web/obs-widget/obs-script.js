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
  textInfo: document.querySelector(".text-info"),
  progressSection: document.querySelector(".progress-section"),
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

// Queue state
const queueState = {
  items: [],
};

// Up Next transition state
const upNextState = {
  isActive: false,
  lastTrackUri: "",
};

const UP_NEXT_THRESHOLD_MS = 15000;

/**
 * Applies extracted dominant color to the OBS widget background and progress bar.
 */
function updateDynamicColors(img) {
  const color = extractDominantColor(img);
  if (!color) return;

  const { r, g, b } = color;
  const bgR = Math.floor(r * 0.4);
  const bgG = Math.floor(g * 0.4);
  const bgB = Math.floor(b * 0.4);

  elements.container.style.background = `rgba(${bgR}, ${bgG}, ${bgB}, 0.65)`;
  elements.progressBarFill.style.background = `rgb(${r}, ${g}, ${b})`;
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

function handleQueueUpdate(data) {
  queueState.items = data.queue || [];
}

function showUpNext() {
  if (upNextState.isActive) return;
  const nextTrack = queueState.items[0];
  if (!nextTrack) return;

  const meta = nextTrack.metadata || {};
  const title = meta.title || "Unknown Track";
  const artist = meta.artist_name || "Unknown Artist";
  const album = meta.album_name || "";
  const imgUrl = meta.image_url || "";

  upNextState.isActive = true;

  elements.textInfo.classList.add("fade-out");

  setTimeout(() => {
    elements.songTitle.querySelector(".marquee-wrapper").textContent = `Up Next: ${title}`;
    elements.songTitle.classList.remove("marquee-active");
    updateMarquee(elements.artistName, artist);
    updateMarquee(elements.albumName, album);

    if (imgUrl && elements.albumArt.src !== imgUrl) {
      elements.albumArt.crossOrigin = "Anonymous";
      elements.albumArt.onload = () => updateDynamicColors(elements.albumArt);
      elements.albumArt.src = imgUrl;
    }

    elements.textInfo.classList.remove("fade-out");
    elements.textInfo.classList.add("fade-in");
  }, 400);
}

function resetUpNext() {
  if (!upNextState.isActive) return;
  upNextState.isActive = false;

  elements.textInfo.classList.remove("fade-out", "fade-in");
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

    const remaining = lastState.duration - currentProgress;
    if (remaining <= UP_NEXT_THRESHOLD_MS && remaining > 0) {
      showUpNext();
    } else if (upNextState.isActive) {
      resetUpNext();
    }
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
      resetUpNext();
      if (data.trackUri) upNextState.lastTrackUri = data.trackUri;
      if (data.trackName) updateMarquee(elements.songTitle, data.trackName);
      if (data.artistName) updateMarquee(elements.artistName, data.artistName);
      if (data.albumName) updateMarquee(elements.albumName, data.albumName);

      if (data.albumArtUrl && elements.albumArt.src !== data.albumArtUrl) {
        elements.albumArt.crossOrigin = "Anonymous";
        elements.albumArt.onload = () => updateDynamicColors(elements.albumArt);
        elements.albumArt.src = data.albumArtUrl;
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

    // Handle Queue
    if (data.type === "queueUpdate") {
      handleQueueUpdate(data);
    }
  };

  ws.onclose = () => setTimeout(connect, 2000);
}

document.addEventListener("DOMContentLoaded", () => {
  connect();
  requestAnimationFrame(animate);
});
