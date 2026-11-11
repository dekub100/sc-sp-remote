const DISABLE_LYRICS = new URLSearchParams(window.location.search).get("disableLyrics") === "true";

let ws;
let currentSource = null;

const spotifyState = {
  trackName: '',
  artistName: '',
  albumName: '',
  albumArtUrl: '',
  albumUri: '',
  trackUri: '',
  progress: 0,
  duration: 0,
  isPlaying: false,
  volume: 0.5,
  isLiked: false,
  timestamp: Date.now(),
  clientTimestamp: Date.now(),
};

const soundcloudState = {
  track: '',
  artist: '',
  album: '',
  coverUrl: '',
  id: '',
  isPlaying: false,
  progressMs: 0,
  durationMs: 0,
  volume: 0.5,
  isLiked: false,
  timestamp: Date.now(),
  clientTimestamp: Date.now(),
};

let lastActiveSource = 'spotify';

function getDisplaySource() {
  if (spotifyState.isPlaying && soundcloudState.isPlaying) return lastActiveSource;
  if (soundcloudState.isPlaying) return 'soundcloud';
  if (spotifyState.isPlaying) return 'spotify';
  return lastActiveSource;
}

const elements = {
  albumArt: document.getElementById('albumArt'),
  songTitle: document.getElementById('songTitle'),
  artistName: document.getElementById('artistName'),
  albumName: document.getElementById('albumName'),
  progressBarFill: document.getElementById('progressBarFill'),
  currentTime: document.getElementById('currentTime'),
  totalTime: document.getElementById('totalTime'),
  container: document.querySelector('.widget-container'),
  lyricLine: document.getElementById('lyricLine'),
  textInfo: document.querySelector('.text-info'),
  progressSection: document.querySelector('.progress-section'),
  sourceBadge: document.getElementById('sourceBadge'),
};

const lyricsState = {
  synced: [],
  plain: '',
  available: false,
  instrumental: false,
  loading: false,
  karaoke: [],
  currentIndex: -1,
};

let isVisible = true;
let hideTimeout = null;

function setWidgetVisibility(visible) {
  if (visible) {
    if (hideTimeout) {
      clearTimeout(hideTimeout);
      hideTimeout = null;
    }
    if (!isVisible) {
      isVisible = true;
      elements.container.classList.remove('idle');
    }
  } else {
    if (hideTimeout || !isVisible) return;
    hideTimeout = setTimeout(() => {
      hideTimeout = null;
      if (!isVisible) return;
      isVisible = false;
      elements.container.classList.add('idle');
    }, 1000);
  }
}

function updateDynamicColors(img) {
  const color = extractDominantColor(img);
  if (!color) return;
  let { r, g, b } = color;
  // Dark album colors are unreadable on the dark background — brighten them.
  const brightness = (r * 299 + g * 587 + b * 114) / 1000;
  if (brightness < 60) {
    const scale = 60 / Math.max(brightness, 1);
    r = Math.min(255, Math.round(r * scale));
    g = Math.min(255, Math.round(g * scale));
    b = Math.min(255, Math.round(b * scale));
  }
  elements.container.style.background = `rgba(${Math.floor(r * 0.4)}, ${Math.floor(g * 0.4)}, ${Math.floor(b * 0.4)}, 0.65)`;
}

let lyricSwapTimer = null;

function setLyricLineContent(content, visible, isHtml) {
  const el = elements.lyricLine;
  // Cancel any pending swap so rapid line changes can't stack up.
  if (lyricSwapTimer) clearTimeout(lyricSwapTimer);
  el.classList.add('fade');
  lyricSwapTimer = setTimeout(() => {
    lyricSwapTimer = null;
    if (isHtml) el.innerHTML = content;
    else el.textContent = content;
    el.classList.remove('fade');
    el.classList.toggle('hidden', !visible);
  }, 120);
}

function setLyricLineText(text) {
  text = filterText(text);
  const el = elements.lyricLine;
  if (el.textContent === text && !lyricSwapTimer) return;
  setLyricLineContent(text, text.length > 0);
}

function updateCurrentKaraokeLine(progressMs) {
  const lines = lyricsState.karaoke;
  let lineIndex = -1;
  for (let i = lines.length - 1; i >= 0; i--) {
    if (progressMs >= lines[i].startTime) {
      lineIndex = i;
      break;
    }
  }

  if (lineIndex !== lyricsState.currentIndex) {
    lyricsState.currentIndex = lineIndex;
    if (lineIndex < 0) {
      setLyricLineText('');
    } else {
      const words = lines[lineIndex].words || [];
      setLyricLineHtml(words.map(w => {
        const dur = w.duration || 300;
        return `<span class="lyric-word" style="--word-duration:${dur}ms">${escapeHtml(filterText(w.text))}</span>`;
      }).join(''));
    }
  }

  if (lineIndex < 0) return;
  const spans = elements.lyricLine.querySelectorAll('.lyric-word');
  const words = lines[lineIndex].words || [];
  spans.forEach((el, j) => {
    if (words[j] !== undefined) el.classList.toggle('active', progressMs >= words[j].time);
  });
}

function setLyricLineHtml(html) {
  setLyricLineContent(html, html.length > 0, true);
}

function handleLyricsUpdate(data) {
  if (DISABLE_LYRICS) return;
  lyricsState.available = data.available;
  lyricsState.instrumental = data.instrumental;
  lyricsState.synced = data.synced || [];
  lyricsState.plain = data.plain || '';
  // Precompute per-word durations for the CSS background-position sweep.
  lyricsState.karaoke = (data.karaoke || []).map(l => {
    const words = (l.words || []).map(w => ({ text: w.text, time: w.time }));
    words.forEach((w, i) => {
      w.duration = Math.max(0, (i + 1 < words.length ? words[i + 1].time : l.endTime) - w.time);
    });
    return { startTime: l.startTime, endTime: l.endTime, words };
  });
  lyricsState.currentIndex = -1;
  lyricsState.loading = data.loading || false;

  if (data.instrumental) {
    setLyricLineText('\u266A');
  } else if (lyricsState.loading) {
    setLyricLineText('...');
  } else if (!data.available) {
    setLyricLineText('');
  } else if (!lyricsState.synced.length && lyricsState.plain) {
    setLyricLineText('');
  }
}

function updateCurrentLyricLine(progressMs) {
  if (DISABLE_LYRICS) return;
  if (!lyricsState.available) return;
  if (lyricsState.karaoke.length) return updateCurrentKaraokeLine(progressMs);
  if (!lyricsState.synced.length) return;
  const newIndex = findLyricIndex(lyricsState.synced, progressMs);
  if (newIndex === lyricsState.currentIndex) return;
  lyricsState.currentIndex = newIndex;
  const text = newIndex >= 0 ? (lyricsState.synced[newIndex].text || '\u266A') : '';
  setLyricLineText(text);
}

function updateProgressDisplay() {
  const state = getDisplaySource() === 'spotify' ? spotifyState : soundcloudState;
  const progress = getDisplaySource() === 'spotify' ? state.progress : state.progressMs;
  const duration = getDisplaySource() === 'spotify' ? state.duration : state.durationMs;

  if (duration > 0) {
    const pct = (progress / duration) * 100;
    elements.progressBarFill.style.width = `${pct}%`;
    setText(elements.currentTime, formatTime(progress));
    setText(elements.totalTime, formatTime(duration));
  }
}

function updateDisplay() {
  const source = getDisplaySource();
  const state = source === 'spotify' ? spotifyState : soundcloudState;
  const progressBarFill = elements.progressBarFill;

  if (source !== currentSource) {
    currentSource = source;
    elements.sourceBadge.innerHTML = source === 'spotify' ? '<i class="fa-brands fa-spotify"></i>' : '<i class="fa-brands fa-soundcloud"></i>';
    elements.sourceBadge.className = 'source-badge ' + source;
    progressBarFill.classList.toggle('soundcloud', source === 'soundcloud');
  }

  const title = source === 'spotify' ? state.trackName : state.track;
  const artist = source === 'spotify' ? state.artistName : state.artist;
  const album = source === 'spotify' ? state.albumName : state.album;
  const imgUrl = source === 'spotify' ? state.albumArtUrl : state.coverUrl;

  updateMarquee(elements.songTitle, title || 'No song playing');
  updateMarquee(elements.artistName, artist || '');
  updateMarquee(elements.albumName, album || '');

  if (imgUrl && elements.albumArt.src !== imgUrl) {
    elements.albumArt.crossOrigin = 'Anonymous';
    elements.albumArt.onload = () => updateDynamicColors(elements.albumArt);
    elements.albumArt.src = imgUrl;
    elements.albumArt.style.display = '';
  } else if (!imgUrl) {
    // display:none collapses the 275px art box so text uses the full width.
    elements.albumArt.style.display = 'none';
  }

  if (source !== 'spotify') {
    setLyricLineText('');
  }
}

function animate() {
  const state = getDisplaySource() === 'spotify' ? spotifyState : soundcloudState;

  if (state.isPlaying) {
    const progress = getDisplaySource() === 'spotify' ? state.progress : state.progressMs;
    const duration = getDisplaySource() === 'spotify' ? state.duration : state.durationMs;

    const elapsed = Date.now() - state.clientTimestamp;
    const currentProgress = Math.min(progress + elapsed, duration);

    if (duration > 0) {
      const pct = (currentProgress / duration) * 100;
      elements.progressBarFill.style.width = `${pct}%`;
      setText(elements.currentTime, formatTime(currentProgress));
      setText(elements.totalTime, formatTime(duration));
    }

    if (getDisplaySource() === 'spotify') {
      updateCurrentLyricLine(currentProgress);
    }
  }

  requestAnimationFrame(animate);
}

function applySpotifyNowPlaying(s) {
  if (s.trackUri) spotifyState.trackUri = s.trackUri;
  if (s.trackName !== undefined) spotifyState.trackName = s.trackName;
  if (s.artistName !== undefined) spotifyState.artistName = s.artistName;
  if (s.albumName !== undefined) spotifyState.albumName = s.albumName;
  if (s.albumArtUrl !== undefined) spotifyState.albumArtUrl = s.albumArtUrl;
  if (s.albumUri !== undefined) spotifyState.albumUri = s.albumUri;
  if (s.progress !== undefined) spotifyState.progress = s.progress;
  if (s.duration !== undefined) spotifyState.duration = s.duration;
  if (s.isPlaying !== undefined) spotifyState.isPlaying = s.isPlaying;
  if (s.volume !== undefined) spotifyState.volume = s.volume;
  if (s.isLiked !== undefined) spotifyState.isLiked = s.isLiked;
  spotifyState.timestamp = s.timestamp || Date.now();
  spotifyState.clientTimestamp = Date.now();
  if (s.isPlaying) lastActiveSource = 'spotify';
  updateDisplay();
  setWidgetVisibility(spotifyState.isPlaying || soundcloudState.isPlaying);
}

function applySoundCloudNowPlaying(s) {
  if (s.track !== undefined) soundcloudState.track = s.track;
  if (s.artist !== undefined) soundcloudState.artist = s.artist;
  if (s.album !== undefined) soundcloudState.album = s.album;
  if (s.coverUrl !== undefined) soundcloudState.coverUrl = s.coverUrl;
  if (s.id !== undefined) soundcloudState.id = s.id;
  if (s.isPlaying !== undefined) soundcloudState.isPlaying = s.isPlaying;
  if (s.progress !== undefined) soundcloudState.progressMs = s.progress;
  if (s.duration !== undefined) soundcloudState.durationMs = s.duration;
  if (s.volume !== undefined) soundcloudState.volume = s.volume;
  if (s.isLiked !== undefined) soundcloudState.isLiked = s.isLiked;
  soundcloudState.timestamp = s.timestamp || Date.now();
  soundcloudState.clientTimestamp = Date.now();
  if (s.isPlaying) lastActiveSource = 'soundcloud';
  updateDisplay();
  setWidgetVisibility(spotifyState.isPlaying || soundcloudState.isPlaying);
}

function applyProgress(source, s) {
  // Periodic corrected anchors from the server — keeps interpolation honest
  // after page refresh (initial snapshot can carry a stale raw progress).
  if (source === 'spotify') {
    if (s.progress !== undefined) spotifyState.progress = s.progress;
    if (s.duration !== undefined) spotifyState.duration = s.duration;
    if (s.isPlaying !== undefined) spotifyState.isPlaying = s.isPlaying;
    spotifyState.timestamp = s.timestamp || Date.now();
    spotifyState.clientTimestamp = Date.now();
  } else if (source === 'soundcloud') {
    if (s.progress !== undefined) soundcloudState.progressMs = s.progress;
    if (s.duration !== undefined) soundcloudState.durationMs = s.duration;
    if (s.isPlaying !== undefined) soundcloudState.isPlaying = s.isPlaying;
    soundcloudState.timestamp = s.timestamp || Date.now();
    soundcloudState.clientTimestamp = Date.now();
  }
}

function handleMessage(data) {
  const state = data.state || {};

  if (data.type === 'nowPlaying') {
    if (data.source === 'spotify') applySpotifyNowPlaying(state);
    else if (data.source === 'soundcloud') applySoundCloudNowPlaying(state);
    return;
  }

  if (data.type === 'progress') {
    applyProgress(data.source, state);
    return;
  }

  if (data.type === 'lyrics') {
    handleLyricsUpdate(state);
    return;
  }

  if (data.type === 'error') {
    console.error('Server error:', data.message);
  }
}

function connect() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${wsProtocol}://${window.location.host}/?client=obs&protocolVersion=2`);

  ws.onmessage = (event) => {
    let data;
    try { data = JSON.parse(event.data); } catch (e) { return; }
    handleMessage(data);
  };

  ws.onclose = () => setTimeout(connect, 2000);
}

document.addEventListener('DOMContentLoaded', () => {
  if (DISABLE_LYRICS) {
    document.getElementById('lyricLine')?.classList.add('hidden');
  }
  connect();
  requestAnimationFrame(animate);
});
