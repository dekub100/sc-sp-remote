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
  currentIndex: -1,
};

const queueState = {
  items: [],
};

const upNextState = {
  isActive: false,
  lastTrackUri: '',
};

let UP_NEXT_THRESHOLD_MS = 15000;
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
  const { r, g, b } = color;
  elements.container.style.background = `rgba(${Math.floor(r * 0.4)}, ${Math.floor(g * 0.4)}, ${Math.floor(b * 0.4)}, 0.65)`;
}

function setLyricLineText(text) {
  text = filterText(text);
  const el = elements.lyricLine;
  if (el.textContent === text) return;
  const visible = text.length > 0;
  el.classList.add('fade');
  setTimeout(() => {
    el.textContent = text;
    el.classList.remove('fade');
    el.classList.toggle('hidden', !visible);
  }, 350);
}

function handleLyricsUpdate(data) {
  if (DISABLE_LYRICS) return;
  lyricsState.available = data.available;
  lyricsState.instrumental = data.instrumental;
  lyricsState.synced = data.synced || [];
  lyricsState.plain = data.plain || '';
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
  if (!lyricsState.available || !lyricsState.synced.length) return;
  const newIndex = findLyricIndex(lyricsState.synced, progressMs);
  if (newIndex === lyricsState.currentIndex) return;
  lyricsState.currentIndex = newIndex;
  const text = newIndex >= 0 ? (lyricsState.synced[newIndex].text || '\u266A') : '';
  setLyricLineText(text);
}

function handleQueueUpdate(data) {
  queueState.items = data.queue || [];
}

function showUpNext() {
  if (upNextState.isActive) return;
  const nextTrack = queueState.items.find(i => i.requestedBy) || queueState.items[0];
  if (!nextTrack) return;

  const meta = nextTrack.metadata || {};
  const title = meta.title || 'Unknown Track';
  const artist = meta.artist_name || 'Unknown Artist';
  const album = meta.album_name || '';
  const imgUrl = meta.image_url || '';

  upNextState.isActive = true;
  elements.textInfo.classList.add('fade-out');

  setTimeout(() => {
    let prefix = elements.songTitle.querySelector('.up-next-prefix');
    if (!prefix) {
      prefix = document.createElement('span');
      prefix.className = 'up-next-prefix';
      prefix.textContent = 'Up Next: ';
      elements.songTitle.insertBefore(prefix, elements.songTitle.querySelector('.marquee-clip'));
    }
    updateMarquee(elements.songTitle, title);
    updateMarquee(elements.artistName, artist);
    updateMarquee(elements.albumName, album);

    if (imgUrl && elements.albumArt.src !== imgUrl) {
      elements.albumArt.crossOrigin = 'Anonymous';
      elements.albumArt.onload = () => updateDynamicColors(elements.albumArt);
      elements.albumArt.src = imgUrl;
    }

    elements.textInfo.classList.remove('fade-out');
    elements.textInfo.classList.add('fade-in');
  }, 400);
}

function resetUpNext() {
  if (!upNextState.isActive) return;
  upNextState.isActive = false;
  const prefix = elements.songTitle.querySelector('.up-next-prefix');
  if (prefix) prefix.remove();
  elements.textInfo.classList.remove('fade-out', 'fade-in');
}

function updateProgressDisplay() {
  const state = getDisplaySource() === 'spotify' ? spotifyState : soundcloudState;
  const progress = getDisplaySource() === 'spotify' ? state.progress : state.progressMs;
  const duration = getDisplaySource() === 'spotify' ? state.duration : state.durationMs;

  if (duration > 0) {
    const pct = (progress / duration) * 100;
    elements.progressBarFill.style.width = `${pct}%`;
    elements.currentTime.textContent = formatTime(progress);
    elements.totalTime.textContent = formatTime(duration);
  }
}

function updateDisplay() {
  const source = getDisplaySource();
  const state = source === 'spotify' ? spotifyState : soundcloudState;
  const progressBarFill = elements.progressBarFill;

  if (source !== currentSource) {
    currentSource = source;
    elements.sourceBadge.textContent = source === 'spotify' ? '\u266B' : '\u2601';
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
      elements.currentTime.textContent = formatTime(currentProgress);
      elements.totalTime.textContent = formatTime(duration);
    }

    if (getDisplaySource() === 'spotify') {
      updateCurrentLyricLine(currentProgress);

      const remaining = duration - currentProgress;
      if (remaining <= UP_NEXT_THRESHOLD_MS && remaining > 0) {
        showUpNext();
      } else if (upNextState.isActive) {
        resetUpNext();
      }
    } else if (upNextState.isActive) {
      resetUpNext();
    }
  }

  requestAnimationFrame(animate);
}

function handleMessage(data) {
  if (data.type === 'config') {
    if (data.upNextThresholdMs !== undefined) {
      UP_NEXT_THRESHOLD_MS = data.upNextThresholdMs;
    }
    return;
  }

  if (data.type === 'stateUpdate' || (data.type === 'trackUpdate' && data.source === 'spotify')) {
    resetUpNext();
    if (data.trackUri) upNextState.lastTrackUri = data.trackUri;
    if (data.trackName !== undefined) spotifyState.trackName = data.trackName;
    if (data.artistName !== undefined) spotifyState.artistName = data.artistName;
    if (data.albumName !== undefined) spotifyState.albumName = data.albumName;
    if (data.albumArtUrl !== undefined) spotifyState.albumArtUrl = data.albumArtUrl;
    if (data.albumUri !== undefined) spotifyState.albumUri = data.albumUri;
    if (data.trackUri !== undefined) spotifyState.trackUri = data.trackUri;
    if (data.progress !== undefined) spotifyState.progress = data.progress;
    if (data.duration !== undefined) spotifyState.duration = data.duration;
    if (data.isPlaying !== undefined) spotifyState.isPlaying = data.isPlaying;
    if (data.volume !== undefined) spotifyState.volume = data.volume;
    if (data.isLiked !== undefined) spotifyState.isLiked = data.isLiked;
    spotifyState.timestamp = data.timestamp || Date.now();
    spotifyState.clientTimestamp = Date.now();
    if (data.isPlaying) lastActiveSource = 'spotify'
    updateDisplay();
    setWidgetVisibility(spotifyState.isPlaying || soundcloudState.isPlaying);
    return;
  }

  if (data.type === 'scStateUpdate') {
    resetUpNext();
    if (data.track !== undefined) soundcloudState.track = data.track;
    if (data.artist !== undefined) soundcloudState.artist = data.artist;
    if (data.album !== undefined) soundcloudState.album = data.album;
    if (data.coverUrl !== undefined) soundcloudState.coverUrl = data.coverUrl;
    if (data.id !== undefined) soundcloudState.id = data.id;
    if (data.isPlaying !== undefined) soundcloudState.isPlaying = data.isPlaying;
    if (data.progressMs !== undefined) soundcloudState.progressMs = data.progressMs;
    if (data.durationMs !== undefined) soundcloudState.durationMs = data.durationMs;
    if (data.volume !== undefined) soundcloudState.volume = data.volume;
    if (data.isLiked !== undefined) soundcloudState.isLiked = data.isLiked;
    soundcloudState.timestamp = data.timestamp || Date.now();
    soundcloudState.clientTimestamp = Date.now();
    if (data.isPlaying) lastActiveSource = 'soundcloud';
    updateDisplay();
    setWidgetVisibility(spotifyState.isPlaying || soundcloudState.isPlaying);
    return;
  }

  if (data.type === 'playbackUpdate' && data.source === 'spotify') {
    if (data.isPlaying !== undefined) spotifyState.isPlaying = data.isPlaying;
    if (data.progress !== undefined) spotifyState.progress = data.progress;
    spotifyState.timestamp = data.timestamp || Date.now();
    spotifyState.clientTimestamp = Date.now();
    if (data.isPlaying) lastActiveSource = 'spotify';
    updateDisplay();
    setWidgetVisibility(spotifyState.isPlaying || soundcloudState.isPlaying);
    return;
  }

  if (data.type === 'scPlaybackUpdate') {
    if (data.isPlaying !== undefined) soundcloudState.isPlaying = data.isPlaying;
    if (data.progressMs !== undefined) soundcloudState.progressMs = data.progressMs;
    soundcloudState.timestamp = data.timestamp || Date.now();
    soundcloudState.clientTimestamp = Date.now();
    if (data.isPlaying) lastActiveSource = 'soundcloud';
    updateDisplay();
    setWidgetVisibility(spotifyState.isPlaying || soundcloudState.isPlaying);
    return;
  }

  if (data.type === 'lyricsUpdate') {
    handleLyricsUpdate(data);
    return;
  }

  if (data.type === 'queueUpdate') {
    handleQueueUpdate(data);
    return;
  }

  if (data.type === 'volumeUpdate' && data.source === 'spotify') {
    if (data.volume !== undefined) spotifyState.volume = data.volume;
    return;
  }

  if (data.type === 'scVolumeUpdate') {
    if (data.volume !== undefined) soundcloudState.volume = data.volume;
    return;
  }

  if (data.type === 'error') {
    console.error('Server error:', data.message);
  }
}

function connect() {
  ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/?client=obs&protocolVersion=1`);

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
