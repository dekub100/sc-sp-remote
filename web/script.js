// Main website script for sc-sp-remote (dual-source)
let ws;
let isSeeking = false;
let activeSource = "spotify";

// Spotify interpolation state
let spotifyState = {
    progress: 0,
    duration: 0,
    isPlaying: false,
    timestamp: Date.now()
};

// SoundCloud state
let scState = {
    progressMs: 0,
    durationMs: 0,
    isPlaying: false,
    timestamp: Date.now(),
    clientTimestamp: Date.now()
};

// --- UI refs ---
const ui = {
    container: document.getElementById('mainContainer'),
    error: document.getElementById('connectionError'),
    // Tabs
    sourceTabs: document.querySelectorAll('.source-tab'),
    spotifyPanel: document.getElementById('spotifyPanel'),
    soundcloudPanel: document.getElementById('soundcloudPanel'),
    // Spotify
    albumArt: document.getElementById('albumArt'),
    songTitle: document.getElementById('songTitle'),
    artistName: document.getElementById('artistName'),
    albumName: document.getElementById('albumName'),
    songLink: document.getElementById('songLink'),
    albumLink: document.getElementById('albumLink'),
    progressBar: document.getElementById('progressBar'),
    currentTime: document.getElementById('currentTime'),
    durationTime: document.getElementById('durationTime'),
    volumeSlider: document.getElementById('volumeSlider'),
    volumeValue: document.getElementById('volumeValue'),
    playPauseBtn: document.getElementById('playPauseBtn'),
    shuffleBtn: document.getElementById('shuffleBtn'),
    repeatBtn: document.getElementById('repeatBtn'),
    likeBtn: document.getElementById('likeBtn'),
    lyricsBtn: document.getElementById('lyricsBtn'),
    lyricsPanel: document.getElementById('lyricsPanel'),
    lyricsContent: document.getElementById('lyricsContent'),
    // SoundCloud
    scAlbumArt: document.getElementById('scAlbumArt'),
    scSongTitle: document.getElementById('scSongTitle'),
    scArtistName: document.getElementById('scArtistName'),
    scProgressBar: document.getElementById('scProgressBar'),
    scCurrentTime: document.getElementById('scCurrentTime'),
    scDurationTime: document.getElementById('scDurationTime'),
    scVolumeSlider: document.getElementById('scVolumeSlider'),
    scVolumeValue: document.getElementById('scVolumeValue'),
    scPlayPauseBtn: document.getElementById('scPlayPauseBtn'),
    scLikeBtn: document.getElementById('scLikeBtn'),
};

// Lyrics state
const lyricsState = {
    synced: [],
    plain: "",
    available: false,
    instrumental: false,
    loading: false,
    currentIndex: -1,
    isVisible: false
};

function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
}

function spotifyUriToUrl(uri) {
    if (!uri) return '#';
    const parts = uri.split(':');
    if (parts.length < 3) return '#';
    return `https://open.spotify.com/${parts[1]}/${parts[2]}`;
}

function updateDynamicColors(img) {
    const color = extractDominantColor(img);
    if (!color) return;

    const { r, g, b } = color;
    const bgR = Math.floor(r * 0.2);
    const bgG = Math.floor(g * 0.2);
    const bgB = Math.floor(b * 0.2);

    ui.container.style.background = `rgba(${bgR}, ${bgG}, ${bgB}, 0.95)`;

    const accent = `rgb(${r}, ${g}, ${b})`;
    document.documentElement.style.setProperty('--accent-color', accent);

    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
    if (brightness < 60) {
        const scale = 60 / Math.max(brightness, 1);
        const brightAccent = `rgb(${Math.min(255, Math.round(r * scale))}, ${Math.min(255, Math.round(g * scale))}, ${Math.min(255, Math.round(b * scale))})`;
        document.documentElement.style.setProperty('--accent-color', brightAccent);
    }
}

// --- Source Tabs ---
function setActiveSource(source) {
    activeSource = source;
    ui.sourceTabs.forEach(tab => {
        tab.classList.toggle('active', tab.dataset.source === source);
    });
    ui.spotifyPanel.classList.toggle('active', source === 'spotify');
    ui.soundcloudPanel.classList.toggle('active', source === 'soundcloud');

    // Update dynamic colors based on active album art
    if (source === 'spotify' && ui.albumArt.src) {
        updateDynamicColors(ui.albumArt);
    } else if (source === 'soundcloud' && ui.scAlbumArt.src) {
        updateDynamicColors(ui.scAlbumArt);
    }
}

ui.sourceTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        setActiveSource(tab.dataset.source);
    });
});

// --- Lyrics ---
function renderLyrics() {
    if (lyricsState.instrumental) {
        ui.lyricsContent.innerHTML = '<p class="lyrics-unavailable">Instrumental track</p>';
        return;
    }
    if (lyricsState.loading) {
        ui.lyricsContent.innerHTML = '<p class="lyrics-unavailable">Downloading lyrics...</p>';
        return;
    }
    if (!lyricsState.available) {
        ui.lyricsContent.innerHTML = '<p class="lyrics-unavailable">No lyrics available</p>';
        return;
    }
    if (lyricsState.synced.length > 0) {
        ui.lyricsContent.innerHTML = lyricsState.synced
            .map((line, i) => `<div class="lyric-line" data-index="${i}" data-time="${line.time}">${line.text || ''}</div>`)
            .join('');
        lyricsState.currentIndex = -1;
    } else if (lyricsState.plain) {
        ui.lyricsContent.innerHTML = `<div class="lyric-plain">${lyricsState.plain.replace(/\n/g, '<br>')}</div>`;
        lyricsState.currentIndex = -1;
    } else {
        ui.lyricsContent.innerHTML = '<p class="lyrics-unavailable">No lyrics available</p>';
    }
}

function updateLyricsHighlight(progressMs) {
    if (!lyricsState.available || !lyricsState.synced.length) return;

    const newIndex = findLyricIndex(lyricsState.synced, progressMs);
    if (newIndex === lyricsState.currentIndex) return;
    lyricsState.currentIndex = newIndex;

    const lines = ui.lyricsContent.querySelectorAll('.lyric-line');
    lines.forEach((el, i) => {
        el.classList.remove('active', 'near-active');
        const dist = i - newIndex;
        if (dist === 0) el.classList.add('active');
        else if (dist > 0 && dist <= 2) el.classList.add('near-active');
    });

    if (newIndex >= 0 && lyricsState.isVisible) {
        const activeLine = lines[newIndex];
        if (activeLine) activeLine.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function handleLyricsUpdate(data) {
    lyricsState.available = data.available;
    lyricsState.instrumental = data.instrumental;
    lyricsState.synced = (data.synced || []).map(l => ({ ...l, text: filterText(l.text) }));
    lyricsState.plain = filterText(data.plain || "");
    lyricsState.loading = data.loading || false;
    lyricsState.currentIndex = -1;
    renderLyrics();
}

function toggleLyrics() {
    lyricsState.isVisible = !lyricsState.isVisible;
    ui.lyricsPanel.classList.toggle('hidden', !lyricsState.isVisible);
    ui.lyricsBtn.classList.toggle('active', lyricsState.isVisible);
    if (lyricsState.isVisible && lyricsState.currentIndex >= 0) {
        const lines = ui.lyricsContent.querySelectorAll('.lyric-line');
        const activeLine = lines[lyricsState.currentIndex];
        if (activeLine) setTimeout(() => activeLine.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
    }
}

function debounce(fn, delay) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

// Smooth interpolation loop
function animate() {
    // Spotify interpolation
    if (activeSource === 'spotify' && !isSeeking) {
        if (spotifyState.isPlaying) {
            const { currentProgress } = interpolateProgress(spotifyState);
            ui.progressBar.value = currentProgress;
            ui.currentTime.textContent = formatTime(currentProgress);
            updateLyricsHighlight(currentProgress);
        } else {
            ui.progressBar.value = spotifyState.progress;
            ui.currentTime.textContent = formatTime(spotifyState.progress);
            updateLyricsHighlight(spotifyState.progress);
        }
    }
    // SoundCloud interpolation
    if (activeSource === 'soundcloud' && !isSeeking) {
        if (scState.isPlaying) {
            const now = Date.now();
            const elapsed = now - scState.clientTimestamp;
            const currentProgress = Math.min(scState.progressMs + elapsed, scState.durationMs);
            ui.scProgressBar.value = currentProgress;
            ui.scCurrentTime.textContent = formatTime(currentProgress);
        } else {
            ui.scProgressBar.value = scState.progressMs;
            ui.scCurrentTime.textContent = formatTime(scState.progressMs);
        }
    }
    requestAnimationFrame(animate);
}

// --- WebSocket ---
function connect() {
    ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/?client=website&protocolVersion=1`);

    ws.onopen = () => {
        ui.container.classList.remove('hidden');
        ui.error.classList.add('hidden');
    };

    ws.onmessage = (event) => {
        let data;
        try { data = JSON.parse(event.data); } catch (e) { return; }

        // --- Spotify messages ---
        if ((data.type === 'stateUpdate' || data.type === 'trackUpdate') && data.source === 'spotify') {
            if (data.trackName) updateMarquee(ui.songTitle, data.trackName);
            if (data.artistName) updateMarquee(ui.artistName, data.artistName);
            if (data.albumName) updateMarquee(ui.albumName, data.albumName);

            if (data.trackUri) ui.songLink.href = spotifyUriToUrl(data.trackUri);
            if (data.albumUri) ui.albumLink.href = spotifyUriToUrl(data.albumUri);

            if (data.albumArtUrl && ui.albumArt.src !== data.albumArtUrl) {
                ui.albumArt.crossOrigin = "Anonymous";
                ui.albumArt.onload = () => updateDynamicColors(ui.albumArt);
                ui.albumArt.src = data.albumArtUrl;
            }

        }

        if (data.type === 'volumeUpdate' && data.source === 'spotify') {
            ui.volumeSlider.value = data.volume;
            ui.volumeValue.textContent = `${Math.round(data.volume * 100)}%`;
        }

        if (data.type === 'playbackUpdate' && data.source === 'spotify') {
            spotifyState.isPlaying = data.isPlaying;
            ui.playPauseBtn.querySelector('.fa-play').style.display = data.isPlaying ? 'none' : 'inline-block';
            ui.playPauseBtn.querySelector('.fa-pause').style.display = data.isPlaying ? 'inline-block' : 'none';
        }

        if (data.type === 'shuffleUpdate' && data.source === 'spotify') {
            ui.shuffleBtn.classList.toggle('active', data.isShuffling);
        }

        if (data.type === 'repeatUpdate' && data.source === 'spotify') {
            const repeatIcon = ui.repeatBtn.querySelector('i');
            ui.repeatBtn.classList.toggle('active', data.repeatStatus > 0);
            if (data.repeatStatus === 2) {
                repeatIcon.className = 'fas fa-redo-alt';
                ui.repeatBtn.setAttribute('data-mode', 'track');
            } else {
                repeatIcon.className = 'fas fa-repeat';
                ui.repeatBtn.removeAttribute('data-mode');
            }
        }

        if (data.type === 'likeUpdate' && data.source === 'spotify') {
            ui.likeBtn.classList.toggle('liked', data.isLiked);
        }

        if ((data.type === 'progressUpdate' || data.type === 'playbackUpdate') && data.source === 'spotify') {
            if (data.progress !== undefined) {
                const prevProgress = spotifyState.progress;
                spotifyState.progress = data.progress;
                spotifyState.duration = data.duration ?? spotifyState.duration;
                spotifyState.timestamp = Date.now();

                // Log progress jumps for debugging
                const jump = Math.abs(data.progress - prevProgress);
                if (jump > 5000 && prevProgress > 0) {
                    console.warn(`[SP-DEBUG] Large progress jump: ${formatTime(prevProgress)} -> ${formatTime(data.progress)} (delta: ${jump}ms)`);
                }

                if (!isSeeking) {
                    ui.progressBar.max = spotifyState.duration;
                    ui.durationTime.textContent = formatTime(spotifyState.duration);
                }
            }
        }

        // --- SoundCloud messages ---
        if (data.type === 'scStateUpdate') {
            if (data.track) updateMarquee(ui.scSongTitle, data.track);
            if (data.artist) updateMarquee(ui.scArtistName, data.artist);

            if (data.coverUrl && ui.scAlbumArt.src !== data.coverUrl) {
                ui.scAlbumArt.crossOrigin = "Anonymous";
                ui.scAlbumArt.onload = () => updateDynamicColors(ui.scAlbumArt);
                ui.scAlbumArt.src = data.coverUrl;
            }

            scState.isPlaying = data.isPlaying;
            scState.progressMs = data.progressMs || 0;
            scState.durationMs = data.durationMs || 0;
            scState.timestamp = data.timestamp || Date.now();
            scState.clientTimestamp = Date.now();

            ui.scPlayPauseBtn.querySelector('.fa-play').style.display = data.isPlaying ? 'none' : 'inline-block';
            ui.scPlayPauseBtn.querySelector('.fa-pause').style.display = data.isPlaying ? 'inline-block' : 'none';

            ui.scProgressBar.max = scState.durationMs;
            ui.scProgressBar.value = scState.progressMs;
            ui.scCurrentTime.textContent = formatTime(scState.progressMs);
            ui.scDurationTime.textContent = formatTime(scState.durationMs);

            if (data.isLiked !== undefined) {
                ui.scLikeBtn.classList.toggle('liked', data.isLiked);
            }
        }

        if (data.type === 'scVolumeUpdate') {
            ui.scVolumeSlider.value = data.volume;
            ui.scVolumeValue.textContent = `${Math.round(data.volume * 100)}%`;
        }

        if (data.type === 'scPlaybackUpdate') {
            scState.isPlaying = data.isPlaying;
            scState.progressMs = data.progressMs || 0;
            scState.timestamp = Date.now();
            scState.clientTimestamp = Date.now();

            ui.scPlayPauseBtn.querySelector('.fa-play').style.display = data.isPlaying ? 'none' : 'inline-block';
            ui.scPlayPauseBtn.querySelector('.fa-pause').style.display = data.isPlaying ? 'inline-block' : 'none';
        }

        if (data.type === 'scProgressUpdate') {
            scState.progressMs = data.progressMs || 0;
            scState.durationMs = data.durationMs || 0;
            scState.timestamp = Date.now();
            scState.clientTimestamp = Date.now();

            if (!isSeeking) {
                ui.scProgressBar.max = scState.durationMs;
                ui.scDurationTime.textContent = formatTime(scState.durationMs);
            }
        }

        // --- Shared messages ---

        if (data.type === 'lyricsUpdate') {
            handleLyricsUpdate(data);
        }

        if (data.type === 'error') {
            console.error('Server error:', data.message);
        }
    };

    ws.onclose = () => {
        ui.container.classList.add('hidden');
        ui.error.classList.remove('hidden');
        setTimeout(connect, 5000);
    };
}

// Click-to-seek on lyric lines
ui.lyricsContent.addEventListener('click', (e) => {
    const line = e.target.closest('.lyric-line');
    if (line) {
        const time = parseInt(line.dataset.time);
        if (!isNaN(time)) {
            send({type: 'playbackControl', command: 'seek', position: time});
        }
    }
});

// --- Spotify Event Listeners ---
ui.playPauseBtn.onclick = () => send({type: 'playbackControl', command: 'togglePlay'});
document.getElementById('previousBtn').onclick = () => send({type: 'playbackControl', command: 'previous'});
document.getElementById('nextBtn').onclick = () => send({type: 'playbackControl', command: 'next'});
ui.shuffleBtn.onclick = () => send({type: 'playbackControl', command: 'toggleShuffle'});
ui.repeatBtn.onclick = () => send({type: 'playbackControl', command: 'toggleRepeat'});
ui.likeBtn.onclick = () => send({type: 'like', source: 'spotify'});
ui.lyricsBtn.onclick = () => toggleLyrics();

const sendSpotifyVolume = debounce((val) => send({type: 'volumeUpdate', volume: val}), 150);
ui.volumeSlider.oninput = (e) => {
    const val = parseFloat(e.target.value);
    ui.volumeValue.textContent = `${Math.round(val * 100)}%`;
    sendSpotifyVolume(val);
};

ui.progressBar.onmousedown = () => isSeeking = true;
ui.progressBar.onmouseup = (e) => {
    isSeeking = false;
    const newPos = parseInt(e.target.value);
    spotifyState.progress = newPos;
    spotifyState.timestamp = Date.now();
    send({type: 'playbackControl', command: 'seek', position: newPos});
};
ui.progressBar.oninput = (e) => ui.currentTime.textContent = formatTime(e.target.value);

// --- SoundCloud Event Listeners ---
ui.scPlayPauseBtn.onclick = () => send({type: 'scPlaybackControl', command: 'togglePlay'});
document.getElementById('scPreviousBtn').onclick = () => send({type: 'scPlaybackControl', command: 'previous'});
document.getElementById('scNextBtn').onclick = () => send({type: 'scPlaybackControl', command: 'next'});
ui.scLikeBtn.onclick = () => send({type: 'scPlaybackControl', command: 'like'});

const sendScVolume = debounce((val) => send({type: 'scVolumeUpdate', volume: val}), 150);
ui.scVolumeSlider.oninput = (e) => {
    const val = parseFloat(e.target.value);
    ui.scVolumeValue.textContent = `${Math.round(val * 100)}%`;
    sendScVolume(val);
};

ui.scProgressBar.onmousedown = () => isSeeking = true;
ui.scProgressBar.onmouseup = (e) => {
    isSeeking = false;
    const newPos = parseInt(e.target.value);
    scState.progressMs = newPos;
    scState.timestamp = Date.now();
    send({type: 'scPlaybackControl', command: 'seek', position_ms: newPos});
};
ui.scProgressBar.oninput = (e) => ui.scCurrentTime.textContent = formatTime(e.target.value);

document.addEventListener('DOMContentLoaded', () => {
    connect();
    requestAnimationFrame(animate);
});
