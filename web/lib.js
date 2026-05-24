// Shared utilities for the website and OBS widget.
// Loaded via <script src="lib.js"></script> in both index.html and obs-widget.html.

/**
 * Formats milliseconds into a human-readable time string (e.g. "3:45").
 */
function formatTime(ms) {
    if (isNaN(ms) || ms < 0) return "0:00";
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
}

/**
 * Extracts the dominant average color from an image using a 50x50 canvas sample.
 * Returns { r, g, b } or null on failure.
 */
function extractDominantColor(img) {
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        canvas.width = 50;
        canvas.height = 50;
        ctx.drawImage(img, 0, 0, 50, 50);

        const imageData = ctx.getImageData(0, 0, 50, 50).data;
        let r = 0, g = 0, b = 0, count = 0;

        // Sample every 4th pixel for performance
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

/**
 * Activates a CSS marquee on the given element if the text overflows.
 * Expects a child with class "marquee-wrapper" and a data-text attribute.
 */
function updateMarquee(element, text) {
    const wrapper = element.querySelector('.marquee-wrapper');
    if (!wrapper) return;
    if (wrapper.textContent === text) return;

    wrapper.textContent = text;
    wrapper.setAttribute('data-text', text);
    element.classList.remove('marquee-active');

    // Delay allows DOM to calculate widths after text update
    setTimeout(() => {
        const clipEl = element.querySelector('.marquee-clip') || element;
        if (wrapper.scrollWidth > clipEl.clientWidth) {
            const duration = Math.max(10, text.length / 2);
            element.style.setProperty('--duration', `${duration}s`);
            element.classList.add('marquee-active');
        }
    }, 100);
}

/**
 * Interpolates the current progress from stored state.
 * Returns { currentProgress, now } so callers can update their timestamp.
 */
function interpolateProgress(lastState) {
    if (!lastState.isPlaying) return { currentProgress: lastState.progress, now: lastState.timestamp };
    const now = Date.now();
    const elapsed = now - lastState.timestamp;
    const currentProgress = Math.min(lastState.progress + elapsed, lastState.duration);
    return { currentProgress, now };
}

/**
 * Finds the index of the active synced lyric line at a given time.
 * Returns -1 if no synced lyrics or no line matches.
 */
function findLyricIndex(synced, progressMs) {
    if (!synced || !synced.length) return -1;
    for (let i = synced.length - 1; i >= 0; i--) {
        if (progressMs >= synced[i].time) return i;
    }
    return -1;
}
