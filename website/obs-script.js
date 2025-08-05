// This script connects to the Node.js server to sync volume and playback.
// This version ensures all DOM elements are loaded before attempting to connect
// or add event listeners, which fixes issues with button functionality.

const SERVER_URL = "ws://localhost:8888";
// Use a Data URI for the fallback image. This embeds the image data directly in the code,
// making it impossible for ad blockers to block.
const FALLBACK_ALBUM_ART =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'><rect width='200' height='200' fill='%23535353'/><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' font-family='Arial, Helvetica, sans-serif' font-size='20' fill='%23FFFFFF'>No Art</text></svg>";

// Get DOM elements. This must be done inside the DOMContentLoaded listener to guarantee they exist.
let albumArtImg;
let songTitleElem;
let artistNameElem;
let progressBarFill;
let currentTimeElem;
let totalTimeElem;
let widgetContainer;
let timeContainer;

let ws;
let isDomReady = false; // New flag to track if the DOM is ready

/**
 * Helper function to format milliseconds to a mm:ss string.
 * @param {number} ms - The time in milliseconds.
 * @returns {string} - The formatted time string.
 */
function formatTime(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Checks if a given hex color is "light" for contrast purposes.
 * @param {string} hex - The hex color code (e.g., "#FFFFFF").
 * @returns {boolean} - True if the color is light, false otherwise.
 */
function isLightColor(hex) {
  if (!hex) return false;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  // Formula for perceived brightness (Luminance)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.5;
}

/**
 * Converts a hex color to an RGBA color with a given opacity.
 * @param {string} hex - The hex color code (e.g., "#FFFFFF").
 * @param {number} opacity - The opacity value (0 to 1).
 * @returns {string} - The RGBA formatted color string.
 */
function hexToRgba(hex, opacity) {
  if (!hex) return `rgba(0, 0, 0, ${opacity})`;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

/**
 * Updates the background of the widget with a gradient based on the color palette
 * and sets the text color for readability.
 * @param {object} palette - The color palette object from the server.
 */
function updateBackground(palette) {
  const opacity = 0.7; // Set your desired opacity here (0.0 to 1.0)
  const defaultColor = `rgba(0, 0, 0, ${opacity / 2})`; // A slightly more transparent default
  let startColor = defaultColor;
  let endColor = defaultColor;

  if (palette && palette.vibrant && palette.darkMuted) {
    startColor = hexToRgba(palette.vibrant, opacity);
    endColor = hexToRgba(palette.darkMuted, opacity);
  }

  // Apply the background gradient
  if (widgetContainer) {
    widgetContainer.style.background = `linear-gradient(90deg, ${startColor} 0%, ${endColor} 100%)`;

    // Check if the background is light and adjust text color
    if (isLightColor(startColor) || isLightColor(endColor)) {
      widgetContainer.classList.add("dark-text");
      if (timeContainer) {
        timeContainer.classList.add("dark-text");
      }
    } else {
      widgetContainer.classList.remove("dark-text");
      if (timeContainer) {
        timeContainer.classList.remove("dark-text");
      }
    }
  }
}

/**
 * Handles the marquee effect logic for a given text element.
 * This version is more robust in resetting the animation state by using a CSS class.
 * @param {HTMLElement} element - The main element (e.g., songTitleElem).
 * @param {string} textContent - The text to be displayed.
 */
function handleMarquee(element, textContent) {
  if (!element) {
    console.warn("handleMarquee was called with a null element.");
    return;
  }

  // Get the wrapper and all content elements
  const wrapper = element.querySelector(".marquee-wrapper");
  const contentElements = element.querySelectorAll(".marquee-content");

  if (!wrapper || contentElements.length === 0) {
    console.error("Marquee elements not found for:", element.id);
    return;
  }

  // Set the text for both content elements
  contentElements.forEach((content) => {
    content.textContent = textContent;
  });

  // Use a small delay to ensure the DOM has rendered the new content before measuring.
  setTimeout(() => {
    // Check if the text overflows its container
    // We check the first content element's scrollWidth against the parent's clientWidth
    const firstContent = contentElements[0];
    if (firstContent.scrollWidth > element.clientWidth) {
      // Duplicate the content to create a seamless loop
      if (contentElements.length < 2) {
        const secondContent = firstContent.cloneNode(true);
        wrapper.appendChild(secondContent);
      }

      // Calculate the animation duration based on the content width
      const animationDuration = firstContent.scrollWidth / 175; // change this to make it go faster or slower
      wrapper.style.animationDuration = `${animationDuration}s`;

      // Add the class to start the animation
      element.classList.add("marquee-active");
    } else {
      // If it doesn't overflow, remove the marquee effect
      element.classList.remove("marquee-active");
      wrapper.style.width = "100%";
      wrapper.style.animationDuration = "0s";
      // Remove the duplicate content if it exists
      if (contentElements.length > 1) {
        contentElements[1].remove();
      }
    }
  }, 50); // Increased delay slightly for better reliability
}

/**
 * Connects to the WebSocket server and sets up event listeners.
 */
function connectWebSocket() {
  try {
    ws = new WebSocket(SERVER_URL);

    ws.onopen = () => {
      console.log(
        "OBS Widget: Connected to server. Requesting initial state..."
      );
      // Wait a moment before requesting state to ensure the server is fully ready.
      setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "requestState" }));
        }
      }, 200); // 200ms delay
    };

    ws.onmessage = (event) => {
      // Only process messages if the DOM is ready
      if (!isDomReady) {
        return;
      }
      try {
        const data = JSON.parse(event.data);
        if (data.type === "stateUpdate") {
          // Update the track information and album art.
          if (data.trackName !== undefined) {
            handleMarquee(songTitleElem, data.trackName);
            if (artistNameElem) {
              handleMarquee(artistNameElem, data.artistName);
            }
            if (albumArtImg) {
              albumArtImg.src = data.albumArtUrl || FALLBACK_ALBUM_ART;
            }
          }

          // Update progress bar
          if (data.progress !== undefined && data.duration !== undefined) {
            updateProgressBar(data.progress, data.duration);
            if (currentTimeElem) {
              currentTimeElem.textContent = formatTime(data.progress);
            }
            if (totalTimeElem) {
              totalTimeElem.textContent = formatTime(data.duration);
            }
          }

          // Update the background with the new palette
          if (data.backgroundPalette !== undefined) {
            updateBackground(data.backgroundPalette);
          }
        }
      } catch (error) {
        console.error("OBS Widget: Failed to parse message:", error);
      }
    };

    ws.onclose = () => {
      console.log(
        "OBS Widget: Disconnected from server. Attempting to reconnect..."
      );
      // Reconnect after a delay
      setTimeout(connectWebSocket, 1000);
    };

    ws.onerror = (error) => {
      console.error("OBS Widget: WebSocket error:", error);
    };
  } catch (error) {
    console.error("OBS Widget: Error creating WebSocket:", error);
    setTimeout(connectWebSocket, 1000); // Reconnect on initial connection failure
  }
}

/**
 * Updates the progress bar and time display.
 * @param {number} progress - The current playback position in milliseconds.
 * @param {number} duration - The total duration of the track in milliseconds.
 */
function updateProgressBar(progress, duration) {
  if (progressBarFill && duration > 0) {
    const progressPercent = (progress / duration) * 100;
    progressBarFill.style.width = `${progressPercent}%`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Get DOM elements.
  albumArtImg = document.getElementById("albumArt");
  songTitleElem = document.getElementById("songTitle");
  artistNameElem = document.getElementById("artistName");
  progressBarFill = document.getElementById("progressBarFill");
  currentTimeElem = document.getElementById("currentTime");
  totalTimeElem = document.getElementById("totalTime");
  widgetContainer = document.querySelector(".widget-container");
  timeContainer = document.querySelector(".time-container");

  // Set the DOM as ready
  isDomReady = true;

  // Set a subtle default background color immediately on load.
  updateBackground();

  // Initial call to connect to the WebSocket server.
  connectWebSocket();
});
