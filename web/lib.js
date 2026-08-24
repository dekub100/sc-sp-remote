function formatTime(ms) {
    if (isNaN(ms) || ms < 0) return "0:00";
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function extractDominantColor(img) {
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        canvas.width = 50;
        canvas.height = 50;
        ctx.drawImage(img, 0, 0, 50, 50);

        const imageData = ctx.getImageData(0, 0, 50, 50).data;
        let r = 0, g = 0, b = 0, count = 0;

        for (let i = 0; i < imageData.length; i += 16) {
            r += imageData[i];
            g += imageData[i + 1];
            b += imageData[i + 2];
            count++;
        }

        return {
            r: Math.floor(r / count),
            g: Math.floor(g / count),
            b: Math.floor(b / count)
        };
    } catch (e) {
        console.error("Color extraction failed:", e);
        return null;
    }
}

function updateMarquee(element, text) {
    const wrapper = element.querySelector('.marquee-wrapper');
    if (!wrapper) return;
    if (wrapper.textContent === text) return;

    wrapper.textContent = text;
    wrapper.setAttribute('data-text', text);
    element.classList.remove('marquee-active');

    setTimeout(() => {
        const clipEl = element.querySelector('.marquee-clip') || element;
        if (wrapper.scrollWidth > clipEl.clientWidth) {
            const duration = Math.max(10, text.length / 2);
            element.style.setProperty('--duration', `${duration}s`);
            element.classList.add('marquee-active');
        }
    }, 100);
}

function interpolateProgress(lastState) {
    if (!lastState.isPlaying) return { currentProgress: lastState.progress, now: lastState.timestamp };
    const now = Date.now();
    const elapsed = now - (lastState.clientTimestamp || lastState.timestamp);
    const currentProgress = Math.min(lastState.progress + elapsed, lastState.duration);
    return { currentProgress, now };
}

function findLyricIndex(synced, progressMs) {
    if (!synced || !synced.length) return -1;
    for (let i = synced.length - 1; i >= 0; i--) {
        if (progressMs >= synced[i].time) return i;
    }
    return -1;
}
