// Simplified Main Website Script with Client-Side Color Extraction
let ws;
let isSeeking = false;

// Interpolation state
let lastState = {
    progress: 0,
    duration: 0,
    isPlaying: false,
    timestamp: Date.now()
};

const ui = {
    container: document.getElementById('mainContainer'),
    error: document.getElementById('connectionError'),
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
    queueBtn: document.getElementById('queueBtn'),
    queuePanel: document.getElementById('queuePanel'),
    queueList: document.getElementById('queueList'),
    queueCount: document.getElementById('queueCount'),
    queueInput: document.getElementById('queueInput'),
    queueAddBtn: document.getElementById('queueAddBtn')
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

// Queue state
const queueState = {
    items: [],
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
    if (brightness < 40) {
        const brightAccent = `rgb(${Math.min(255, r+100)}, ${Math.min(255, g+100)}, ${Math.min(255, b+100)})`;
        document.documentElement.style.setProperty('--accent-color', brightAccent);
    }
}

// --- Lyrics ---

function renderLyrics() {
    if (lyricsState.instrumental) {
        ui.lyricsContent.innerHTML = '<p class="lyrics-unavailable">🎵 Instrumental track</p>';
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

    let newIndex = -1;
    for (let i = lyricsState.synced.length - 1; i >= 0; i--) {
        if (progressMs >= lyricsState.synced[i].time) {
            newIndex = i;
            break;
        }
    }

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

// --- Lyrics ---

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
    ui.queuePanel.classList.add('hidden');
    ui.queueBtn.classList.remove('active');
    queueState.isVisible = false;
    ui.lyricsPanel.classList.toggle('hidden', !lyricsState.isVisible);
    ui.lyricsBtn.classList.toggle('active', lyricsState.isVisible);
    if (lyricsState.isVisible && lyricsState.currentIndex >= 0) {
        const lines = ui.lyricsContent.querySelectorAll('.lyric-line');
        const activeLine = lines[lyricsState.currentIndex];
        if (activeLine) setTimeout(() => activeLine.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
    }
}

function handleQueueUpdate(data) {
    queueState.items = data.queue || [];
    renderQueue();
}

function renderQueue() {
    const requestedItems = queueState.items.filter(i => i.requestedBy);
    ui.queueCount.textContent = requestedItems.length;

    if (queueState.items.length === 0) {
        ui.queueList.innerHTML = '<p class="queue-empty">Queue is empty</p>';
        return;
    }

    ui.queueList.innerHTML = queueState.items.map((item, index) => {
        const meta = item.metadata || {};
        const title = meta.title || '';
        const artist = meta.artist_name || '';
        const imgUrl = meta.image_url || '';
        const requestedBy = item.requestedBy ? `<span class="queue-requested">by ${filterText(item.requestedBy)}</span>` : '';
        const uid = item.uid || '';
        const uri = item.uri || '';

        return `<div class="queue-item" data-index="${index}">
            ${imgUrl ? `<img class="queue-thumb" src="${imgUrl}" alt="" loading="lazy">` : '<div class="queue-thumb-placeholder"><i class="fas fa-music"></i></div>'}
            <div class="queue-item-info">
                <div class="queue-item-title">${filterText(title)}</div>
                <div class="queue-item-artist">${filterText(artist)}</div>
                ${requestedBy}
            </div>
            <button class="queue-remove-btn" data-uri="${uri}" data-uid="${uid}" title="Remove">
                <i class="fas fa-times"></i>
            </button>
        </div>`;
    }).join('');
}

function toggleQueue() {
    queueState.isVisible = !queueState.isVisible;
    ui.lyricsPanel.classList.add('hidden');
    ui.lyricsBtn.classList.remove('active');
    lyricsState.isVisible = false;
    ui.queuePanel.classList.toggle('hidden', !queueState.isVisible);
    ui.queueBtn.classList.toggle('active', queueState.isVisible);
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
    if (lastState.isPlaying && !isSeeking) {
        const now = Date.now();
        const elapsed = now - lastState.timestamp;
        const currentProgress = Math.min(lastState.progress + elapsed, lastState.duration);
        
        ui.progressBar.value = currentProgress;
        ui.currentTime.textContent = formatTime(currentProgress);
        updateLyricsHighlight(currentProgress);
    }
    requestAnimationFrame(animate);
}

function connect() {
    ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/?client=website&protocolVersion=1`);
    
    ws.onopen = () => {
        ui.container.classList.remove('hidden');
        ui.error.classList.add('hidden');
        // Register handled by query param
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        // Handle Track Info
        if (data.type === 'stateUpdate' || data.type === 'trackUpdate') {
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

        // Handle Volume
        if (data.volume !== undefined) {
            ui.volumeSlider.value = data.volume;
            ui.volumeValue.textContent = `${Math.round(data.volume * 100)}%`;
        }

        // Handle Playback State
        if (data.isPlaying !== undefined) {
            lastState.isPlaying = data.isPlaying;
            ui.playPauseBtn.querySelector('.fa-play').style.display = data.isPlaying ? 'none' : 'inline-block';
            ui.playPauseBtn.querySelector('.fa-pause').style.display = data.isPlaying ? 'inline-block' : 'none';
        }

        // Handle Shuffle
        if (data.isShuffling !== undefined) {
            ui.shuffleBtn.classList.toggle('active', data.isShuffling);
        }

        // Handle Repeat
        if (data.repeatStatus !== undefined) {
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

        // Handle Liked Status
        if (data.isLiked !== undefined) {
            ui.likeBtn.classList.toggle('liked', data.isLiked);
        }

        // Handle Progress
        if (data.progress !== undefined) {
            lastState.progress = data.progress;
            lastState.duration = data.duration ?? lastState.duration;
            lastState.timestamp = data.timestamp ?? Date.now();
            
            if (!isSeeking) {
                ui.progressBar.max = lastState.duration;
                ui.progressBar.value = lastState.progress;
                ui.currentTime.textContent = formatTime(lastState.progress);
                ui.durationTime.textContent = formatTime(lastState.duration);
            }
        }

        // Handle Lyrics
        if (data.type === 'lyricsUpdate') {
            handleLyricsUpdate(data);
        }

        // Handle Queue
        if (data.type === 'queueUpdate') {
            handleQueueUpdate(data);
        }

        // Handle Errors
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

// Event Listeners
ui.playPauseBtn.onclick = () => send({type: 'playbackControl', command: 'togglePlay'});
document.getElementById('previousBtn').onclick = () => send({type: 'playbackControl', command: 'previous'});
document.getElementById('nextBtn').onclick = () => send({type: 'playbackControl', command: 'next'});
ui.shuffleBtn.onclick = () => send({type: 'playbackControl', command: 'toggleShuffle'});
ui.repeatBtn.onclick = () => send({type: 'playbackControl', command: 'toggleRepeat'});
ui.likeBtn.onclick = () => send({type: 'like'});
ui.lyricsBtn.onclick = () => toggleLyrics();
ui.queueBtn.onclick = () => toggleQueue();

ui.queueAddBtn.onclick = () => {
    const input = ui.queueInput.value.trim();
    if (!input) return;
    const isUri = input.startsWith('spotify:') || input.includes('open.spotify.com');
    if (isUri) {
        send({type: 'addToQueue', input, requestedBy: 'web'});
        ui.queueInput.value = '';
    } else {
        alert('Please enter a valid Spotify track URL or URI (e.g., spotify:track:... or https://open.spotify.com/track/...)');
    }
};

ui.queueInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        const input = ui.queueInput.value.trim();
        if (!input) return;
        const isUri = input.startsWith('spotify:') || input.includes('open.spotify.com');
        if (isUri) {
            send({type: 'addToQueue', input, requestedBy: 'web'});
            ui.queueInput.value = '';
        } else {
            alert('Please enter a valid Spotify track URL or URI (e.g., spotify:track:... or https://open.spotify.com/track/...)');
        }
    }
});

ui.queueList.addEventListener('click', (e) => {
    const btn = e.target.closest('.queue-remove-btn');
    if (btn) {
        const uri = btn.dataset.uri;
        const uid = btn.dataset.uid;
        send({type: 'removeFromQueue', uri, uid});
    }
});

const sendVolume = debounce((val) => send({type: 'volumeUpdate', volume: val}), 150);
ui.volumeSlider.oninput = (e) => {
    const val = parseFloat(e.target.value);
    ui.volumeValue.textContent = `${Math.round(val * 100)}%`;
    sendVolume(val);
};

ui.progressBar.onmousedown = () => isSeeking = true;
ui.progressBar.onmouseup = (e) => {
    isSeeking = false;
    const newPos = parseInt(e.target.value);
    lastState.progress = newPos;
    lastState.timestamp = Date.now();
    send({type: 'playbackControl', command: 'seek', position: newPos});
};
ui.progressBar.oninput = (e) => ui.currentTime.textContent = formatTime(e.target.value);

document.addEventListener('DOMContentLoaded', () => {
    connect();
    requestAnimationFrame(animate);
});
