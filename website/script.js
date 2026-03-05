// Simplified Main Website Script with Client-Side Color Extraction
let ws;
let serverUrl = null;
let isSeeking = false;

const ui = {
    container: document.getElementById('mainContainer'),
    error: document.getElementById('connectionError'),
    albumArt: document.getElementById('albumArt'),
    songTitle: document.getElementById('songTitle'),
    artistName: document.getElementById('artistName'),
    progressBar: document.getElementById('progressBar'),
    currentTime: document.getElementById('currentTime'),
    durationTime: document.getElementById('durationTime'),
    volumeSlider: document.getElementById('volumeSlider'),
    volumeValue: document.getElementById('volumeValue'),
    playPauseBtn: document.getElementById('playPauseBtn'),
    shuffleBtn: document.getElementById('shuffleBtn'),
    repeatBtn: document.getElementById('repeatBtn'),
    likeBtn: document.getElementById('likeBtn')
};

// Canvas for color extraction (hidden)
const canvas = document.createElement('canvas');
const ctx = canvas.getContext('2d', { willReadFrequently: true });

function formatTime(ms) {
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
}

function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
}

function updateMarquee(element, text) {
    const wrapper = element.querySelector('.marquee-wrapper');
    if (!wrapper) return;
    wrapper.textContent = text;
    wrapper.setAttribute('data-text', text);
    element.classList.remove('marquee-active');
    setTimeout(() => {
        if (wrapper.scrollWidth > element.clientWidth) {
            const duration = Math.max(10, text.length / 2);
            element.style.setProperty('--duration', `${duration}s`);
            element.classList.add('marquee-active');
        }
    }, 50);
}

function updateDynamicColors(img) {
    try {
        canvas.width = 50;
        canvas.height = 50;
        ctx.drawImage(img, 0, 0, 50, 50);
        
        const imageData = ctx.getImageData(0, 0, 50, 50).data;
        let r = 0, g = 0, b = 0, count = 0;
        
        for (let i = 0; i < imageData.length; i += 16) {
            r += imageData[i];
            g += imageData[i+1];
            b += imageData[i+2];
            count++;
        }
        
        r = Math.floor(r / count);
        g = Math.floor(g / count);
        b = Math.floor(b / count);
        
        // Darken for container background
        const bgR = Math.floor(r * 0.2);
        const bgG = Math.floor(g * 0.2);
        const bgB = Math.floor(b * 0.2);
        
        ui.container.style.background = `rgba(${bgR}, ${bgG}, ${bgB}, 0.95)`;
        
        // Update green accent elements to match song
        const accent = `rgb(${r}, ${g}, ${b})`;
        document.documentElement.style.setProperty('--accent-color', accent);
        
        // Use a brightness check for text contrast if needed
        const brightness = (r * 299 + g * 587 + b * 114) / 1000;
        if (brightness < 40) {
            // If color is too dark, use a brighter version for the accent
            const brightAccent = `rgb(${Math.min(255, r+100)}, ${Math.min(255, g+100)}, ${Math.min(255, b+100)})`;
            document.documentElement.style.setProperty('--accent-color', brightAccent);
        }
    } catch (e) {
        console.error("Color extraction failed:", e);
    }
}

function connect() {
    if (!serverUrl) {
        fetch('/api/config').then(r => r.json()).then(cfg => {
            serverUrl = `ws://${window.location.hostname}:${cfg.port}`;
            connect();
        }).catch(() => setTimeout(connect, 5000));
        return;
    }

    ws = new WebSocket(serverUrl);
    
    ws.onopen = () => {
        ui.container.classList.remove('hidden');
        ui.error.classList.add('hidden');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'stateUpdate') {
            if (data.trackName) updateMarquee(ui.songTitle, data.trackName);
            if (data.artistName) updateMarquee(ui.artistName, data.artistName);
            
            if (data.albumArtUrl && ui.albumArt.src !== data.albumArtUrl) {
                ui.albumArt.crossOrigin = "Anonymous";
                ui.albumArt.src = data.albumArtUrl;
                ui.albumArt.onload = () => updateDynamicColors(ui.albumArt);
            }
            
            if (data.volume !== undefined) {
                ui.volumeSlider.value = data.volume;
                ui.volumeValue.textContent = `${Math.round(data.volume * 100)}%`;
            }

            ui.playPauseBtn.querySelector('.fa-play').style.display = data.isPlaying ? 'none' : 'inline-block';
            ui.playPauseBtn.querySelector('.fa-pause').style.display = data.isPlaying ? 'inline-block' : 'none';
            ui.shuffleBtn.classList.toggle('active', data.isShuffling);
            
            const repeatIcon = ui.repeatBtn.querySelector('i');
            ui.repeatBtn.classList.toggle('active', data.repeatStatus > 0);
            if (data.repeatStatus === 2) {
                repeatIcon.className = 'fas fa-redo-alt';
                ui.repeatBtn.setAttribute('data-mode', 'track');
            } else {
                repeatIcon.className = 'fas fa-repeat';
                ui.repeatBtn.removeAttribute('data-mode');
            }
            
            ui.likeBtn.classList.toggle('liked', data.isLiked);
        }

        if ((data.progress !== undefined || data.type === 'progressUpdate') && !isSeeking) {
            const progress = data.progress;
            const duration = data.duration ?? ui.progressBar.max;
            ui.progressBar.max = duration;
            ui.progressBar.value = progress;
            ui.currentTime.textContent = formatTime(progress);
            ui.durationTime.textContent = formatTime(duration);
        }
    };

    ws.onclose = () => {
        ui.container.classList.add('hidden');
        ui.error.classList.remove('hidden');
        setTimeout(connect, 5000);
    };
}

// Event Listeners
ui.playPauseBtn.onclick = () => send({type: 'playbackControl', command: 'togglePlay'});
document.getElementById('previousBtn').onclick = () => send({type: 'playbackControl', command: 'previous'});
document.getElementById('nextBtn').onclick = () => send({type: 'playbackControl', command: 'next'});
ui.shuffleBtn.onclick = () => send({type: 'playbackControl', command: 'toggleShuffle'});
ui.repeatBtn.onclick = () => send({type: 'playbackControl', command: 'toggleRepeat'});
ui.likeBtn.onclick = () => send({type: 'like'});

ui.volumeSlider.oninput = (e) => {
    const val = parseFloat(e.target.value);
    ui.volumeValue.textContent = `${Math.round(val * 100)}%`;
    send({type: 'volumeUpdate', volume: val});
};

ui.progressBar.onmousedown = () => isSeeking = true;
ui.progressBar.onmouseup = (e) => {
    isSeeking = false;
    send({type: 'playbackControl', command: 'seek', position: parseInt(e.target.value)});
};
ui.progressBar.oninput = (e) => ui.currentTime.textContent = formatTime(e.target.value);

document.addEventListener('DOMContentLoaded', connect);
