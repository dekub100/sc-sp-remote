// Spicetify extension to sync Spotify's volume, playback state, and current track with a remote server.
// It sends local changes and applies remote changes using a polling mechanism.

(function remoteVolume() {
  // User: Set your local server address here!
  const SERVER_HOST = "127.0.0.1";
  const SERVER_PORT = 8888; // Change this to match your config.json

  let SERVER_URL = null;
  const POLLING_INTERVAL = 500; // milliseconds
  let ws;

  let lastKnownLocalVolume = -1;
  let lastKnownLocalIsPlaying = false;
  let lastKnownLocalTrackUri = null;
  let lastKnownLocalProgress = -1;

  /**
   * The main function that runs once the Spicetify Player API and Platform API is ready.
   * This is where all the core logic is placed.
   */
  function main() {
    /**
     * Connects to the WebSocket server and sets up event listeners.
     */
    function connectWebSocket() {
      if (!SERVER_URL) {
        fetch("http://localhost:54321/api/config")
          .then((res) => res.json())
          .then((cfg) => {
            // Always use localhost and only the port from config
            SERVER_URL = `ws://localhost:${cfg.port}`;
            connectWebSocket();
          })
          .catch((err) => {
            console.error("Remote Volume: Failed to fetch server config:", err);
            setTimeout(connectWebSocket, 5000);
          });
        return;
      }

      try {
        ws = new WebSocket(SERVER_URL);

        ws.onopen = () => {
          console.log("Remote Volume: Connected to server.");
          sendLocalUpdates(true); // Force send on connect
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === "stateUpdate") {
              // Update volume and playback state if they are different.
              if (data.volume !== undefined) {
                // Use Spicetify.Player.getVolume() for the most accurate comparison
                const currentSpicetifyVolume =
                  Math.round(Spicetify.Player.getVolume() * 100) / 100;
                const serverVolume = Math.round(data.volume * 100) / 100;
                if (currentSpicetifyVolume !== serverVolume) {
                  Spicetify.Player.setVolume(data.volume);
                  console.log(
                    `Remote Volume: Volume set to ${data.volume} from server.`
                  );
                  // Update our local tracking variable to prevent sending this change back
                  lastKnownLocalVolume = data.volume;
                }
              }
              if (data.isPlaying !== undefined) {
                const currentIsPlaying =
                  !Spicetify.Player.origin._state.isPaused;
                if (currentIsPlaying !== data.isPlaying) {
                  // Spicetify.Player.togglePlay() doesn't always work reliably
                  // We directly call play or pause
                  if (data.isPlaying) {
                    Spicetify.Player.play();
                  } else {
                    Spicetify.Player.pause();
                  }
                  console.log(
                    `Remote Volume: Playback toggled to ${data.isPlaying} from server.`
                  );
                  lastKnownLocalIsPlaying = data.isPlaying;
                }
              }
            } else if (data.type === "playbackControl") {
              // Execute a playback command from the server.
              if (Spicetify.Player) {
                console.log(
                  `Remote Volume: Received command '${data.command}'.`
                );
                switch (data.command) {
                  case "togglePlay":
                    Spicetify.Player.togglePlay();
                    break;
                  case "stop":
                    Spicetify.Player.pause();
                    break;
                  case "play":
                    Spicetify.Player.play();
                    break;
                  case "previous":
                    Spicetify.Player.back();
                    break;
                  case "next":
                    Spicetify.Player.next();
                    break;
                  case "seek":
                    Spicetify.Player.seek(data.position);
                    break;
                  default:
                    console.warn(
                      `Remote Volume: Unknown playback command received: ${data.command}`
                    );
                    break;
                }
              }
            }
          } catch (error) {
            console.error(
              "Remote Volume: Failed to parse message from server:",
              error
            );
          }
        };

        ws.onclose = () => {
          console.log(
            "Remote Volume: Disconnected from server. Attempting to reconnect in 5 seconds..."
          );
          setTimeout(connectWebSocket, 5000);
        };

        ws.onerror = (error) => {
          console.error("Remote Volume: WebSocket error:", error);
          ws.close();
        };
      } catch (error) {
        console.error(
          "Remote Volume: Could not connect to WebSocket server:",
          error
        );
        setTimeout(connectWebSocket, 5000);
      }
    }

    /**
     * Extracts track information and ensures the album art URL is valid.
     * This function now correctly handles Spotify URIs.
     * @param {object} track - The track object from Spicetify.Player.data.item.
     * @returns {object} The cleaned track data.
     */
    function getTrackInfo(track) {
      let albumArtUrl = "";
      // Ensure track.images exists and is a non-empty array before trying to access its elements.
      if (
        track.images &&
        Array.isArray(track.images) &&
        track.images.length > 0
      ) {
        // Get the URL from the first image in the array.
        albumArtUrl = track.images[0].url || "";
      }
      // Check if the URL is a Spotify URI and convert it to a valid HTTPS URL.
      if (albumArtUrl.startsWith("spotify:image:")) {
        const imageHash = albumArtUrl.replace("spotify:image:", "");
        albumArtUrl = `https://i.scdn.co/image/${imageHash}`;
      }
      const finalAlbumArtUrl =
        albumArtUrl ||
        "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'><rect width='200' height='200' fill='%23535353'/><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' font-family='Arial, Helvetica, sans-serif' font-size='20' fill='%23FFFFFF'>No Art</text></svg>";
      const trackData = {
        trackName: track.name || "Unknown Track",
        artistName: track.artists[0]?.name || "Unknown Artist",
        albumArtUrl: finalAlbumArtUrl,
      };
      return trackData;
    }

    /**
     * Checks the current local state of the player and sends updates to the server if a change is detected.
     * @param {boolean} forceSend - If true, sends all state updates regardless of change detection.
     */
    function sendLocalUpdates(forceSend = false) {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.log("Remote Volume: WebSocket not connected. Skipping update.");
        return;
      }

      // Check for volume change
      const currentVolume = Spicetify.Player.getVolume();
      // Only send if the volume has changed significantly or we are forcing a send.
      if (
        forceSend ||
        (currentVolume !== null &&
          Math.abs(currentVolume - lastKnownLocalVolume) > 0.01)
      ) {
        console.log(
          `Remote Volume: Volume change detected! Current: ${currentVolume}, Last Known: ${lastKnownLocalVolume}`
        );
        ws.send(
          JSON.stringify({ type: "volumeUpdate", volume: currentVolume })
        );
        lastKnownLocalVolume = currentVolume;
      }

      // Check for playback state change
      const currentIsPlaying = !Spicetify.Player.origin._state.isPaused;
      if (forceSend || currentIsPlaying !== lastKnownLocalIsPlaying) {
        console.log(
          `Remote Volume: Playback change detected! Current: ${currentIsPlaying}, Last Known: ${lastKnownLocalIsPlaying}`
        );
        ws.send(
          JSON.stringify({
            type: "playbackUpdate",
            isPlaying: currentIsPlaying,
          })
        );
        lastKnownLocalIsPlaying = currentIsPlaying;
      }

      // Check for track progress change
      const currentProgress = Spicetify.Player.getProgress();
      const currentDuration = Spicetify.Player.getDuration();
      if (
        forceSend ||
        Math.abs(currentProgress - lastKnownLocalProgress) > 250 // Send update every second
      ) {
        if (currentProgress !== null && currentDuration !== null) {
          // console.log(
          //  `Remote Volume: Progress change detected! Current: ${currentProgress}, Last Known: ${lastKnownLocalProgress}`
          // );
          ws.send(
            JSON.stringify({
              type: "progressUpdate",
              progress: currentProgress,
              duration: currentDuration,
            })
          );
          lastKnownLocalProgress = currentProgress;
        }
      }

      // Check for track change
      const currentTrack = Spicetify.Player.data.item;
      const currentTrackUri = currentTrack?.uri;
      if (
        currentTrackUri &&
        (forceSend || currentTrackUri !== lastKnownLocalTrackUri)
      ) {
        console.log(
          `Remote Volume: Track change detected! Current: ${currentTrackUri}, Last Known: ${lastKnownLocalTrackUri}`
        );
        const trackData = getTrackInfo(currentTrack);
        ws.send(JSON.stringify({ type: "trackUpdate", ...trackData }));
        lastKnownLocalTrackUri = currentTrackUri;
      } else {
        // console.log("Remote Volume: No track change detected.");
      }
    }

    console.log(
      "Remote Volume: Extension is fully loaded and ready. Starting state polling."
    );
    setInterval(() => sendLocalUpdates(), POLLING_INTERVAL);

    connectWebSocket();
  }

  /**
   * Polls Spicetify.Player and Spicetify.Platform.PlaybackAPI until they are ready before
   * starting the main logic.
   */
  function waitForSpicetify() {
    if (
      Spicetify.Player &&
      Spicetify.Player.setVolume &&
      Spicetify.Platform &&
      Spicetify.Platform.PlaybackAPI
    ) {
      console.log(
        "Remote Volume: Spicetify Player and Platform APIs are ready. Starting extension..."
      );
      main();
    } else {
      // Re-check after a short delay
      setTimeout(waitForSpicetify, 300);
    }
  }

  waitForSpicetify();
})();
