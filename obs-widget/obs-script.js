// Simplified OBS Widget Script
let ws;
let serverUrl = null;

const elements = {
    albumArt: document.getElementById('albumArt'),
    songTitle: document.getElementById('songTitle'),
    artistName: document.getElementById('artistName'),
    progressBarFill: document.getElementById('progressBarFill'),
    currentTime: document.getElementById('currentTime'),
    totalTime: document.getElementById('totalTime')
};

function formatTime(ms) {
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
}

function updateMarquee(element, text) {
    const wrapper = element.querySelector('.marquee-wrapper');
    if (!wrapper) return;

    wrapper.textContent = text;
    // Set attribute for CSS ::after content
    wrapper.setAttribute('data-text', text);
    
    // Reset state
    element.classList.remove('marquee-active');
    
    // Small delay to let browser calculate width
    setTimeout(() => {
        if (wrapper.scrollWidth > element.clientWidth) {
            const duration = Math.max(10, text.length / 2); // Dynamic speed
            element.style.setProperty('--duration', `${duration}s`);
            element.classList.add('marquee-active');
        }
    }, 50);
}

function connect() {
    if (!serverUrl) {
        fetch('/api/config')
            .then(r => r.json())
            .then(cfg => {
                serverUrl = `ws://${window.location.hostname}:${cfg.port}`;
                connect();
            })
            .catch(() => setTimeout(connect, 2000));
        return;
    }

    ws = new WebSocket(serverUrl);
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'stateUpdate' || data.type === 'trackUpdate') {
            if (data.trackName) updateMarquee(elements.songTitle, data.trackName);
            if (data.artistName) updateMarquee(elements.artistName, data.artistName);
            if (data.albumArtUrl) elements.albumArt.src = data.albumArtUrl;
        }

        if (data.progress !== undefined && data.duration !== undefined) {
            const pct = (data.progress / data.duration) * 100;
            elements.progressBarFill.style.width = `${pct}%`;
            elements.currentTime.textContent = formatTime(data.progress);
            elements.totalTime.textContent = formatTime(data.duration);
        }
    };

    ws.onclose = () => setTimeout(connect, 2000);
}

document.addEventListener('DOMContentLoaded', connect);
