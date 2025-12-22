// Spicetify extension to sync Spotify's state with a remote server.
// This version is refactored for better readability and organization.

(function remoteVolume() {
  /**
   * The main application object that encapsulates all state and functionality.
   */
  const SpotifyRemote = {
    /**
     * Configuration for the remote server and polling.
     */
    config: {
      SERVER_URL: null,
      CONFIG_URL: "http://localhost:54321/api/config",
      POLLING_INTERVAL_MS: 250,
      RECONNECT_INTERVAL_MS: 5000,
    },

    /**
     * Stores the last known state of the Spotify player to detect changes.
     */
    localState: {
      volume: -1,
      isPlaying: false,
      trackUri: null,
      progress: -1,
      isShuffling: false,
      repeatStatus: 0,
      isLiked: false,
    },

    /**
     * The WebSocket instance.
     */
    ws: null,

    /**
     * Initializes the extension by waiting for Spicetify to be ready,
     * then fetching the server config and starting the main logic.
     */
    init() {
      if (
        !Spicetify.Player ||
        !Spicetify.Platform ||
        !Spicetify.Platform.PlaybackAPI
      ) {
        setTimeout(this.init.bind(this), 300);
        return;
      }
      console.log("Remote Volume: Spicetify ready. Initializing...");
      this.fetchServerConfig();
    },

    /**
     * Fetches the server port from the config server.
     */
    fetchServerConfig() {
      fetch(this.config.CONFIG_URL)
        .then((res) => res.json())
        .then((cfg) => {
          this.config.SERVER_URL = `ws://localhost:${cfg.port}`;
          this.main();
        })
        .catch((err) => {
          console.error(
            "Remote Volume: Failed to fetch server config. Retrying...",
            err
          );
          setTimeout(() => this.fetchServerConfig(), this.config.RECONNECT_INTERVAL_MS);
        });
    },

    /**
     * The main logic of the extension. Connects to the WebSocket and
     * sets up polling and event listeners.
     */
    main() {
      this.websocket.connect();
      this.setupEventListeners();
      this.startPolling();
      this.exposeGlobalControls();
    },

    /**
     * Handles all interactions with the WebSocket server.
     */
    websocket: {
      connect() {
        console.log(`Remote Volume: Connecting to ${SpotifyRemote.config.SERVER_URL}...`);
        try {
          SpotifyRemote.ws = new WebSocket(SpotifyRemote.config.SERVER_URL);
          SpotifyRemote.ws.onopen = this.onOpen;
          SpotifyRemote.ws.onmessage = this.onMessage;
          SpotifyRemote.ws.onclose = this.onClose;
          SpotifyRemote.ws.onerror = this.onError;
        } catch (error) {
          console.error("Remote Volume: WebSocket connection error:", error);
          setTimeout(() => this.connect(), SpotifyRemote.config.RECONNECT_INTERVAL_MS);
        }
      },

      onOpen() {
        console.log("Remote Volume: Connected to server.");
        SpotifyRemote.sendAllLocalUpdates(true); // Force send on connect
      },

      onMessage(event) {
        try {
          const data = JSON.parse(event.data);
          switch (data.type) {
            case "stateUpdate":
              SpotifyRemote.handleStateUpdate(data);
              break;
            case "playbackControl":
              SpotifyRemote.handlePlaybackControl(data);
              break;
          }
        } catch (error) {
          console.error("Remote Volume: Failed to parse server message:", error);
        }
      },

      onClose() {
        console.log("Remote Volume: Disconnected. Reconnecting...");
        setTimeout(() => SpotifyRemote.websocket.connect(), SpotifyRemote.config.RECONNECT_INTERVAL_MS);
      },

      onError(error) {
        console.error("Remote Volume: WebSocket error:", error);
        SpotifyRemote.ws.close();
      },

      send(data) {
        if (SpotifyRemote.ws && SpotifyRemote.ws.readyState === WebSocket.OPEN) {
          SpotifyRemote.ws.send(JSON.stringify(data));
        }
      },
    },

    /**
     * Handles a `stateUpdate` message from the server, syncing the local
     * Spotify client to the server's state if necessary.
     * @param {object} serverState The state object from the server.
     */
    handleStateUpdate(serverState) {
        // Volume
        if (serverState.volume !== undefined) {
            const currentVolume = Math.round(Spicetify.Player.getVolume() * 100) / 100;
            const newVolume = Math.round(serverState.volume * 100) / 100;
            if (currentVolume !== newVolume) {
                Spicetify.Player.setVolume(newVolume);
                this.localState.volume = newVolume;
            }
        }
        // Playback
        if (serverState.isPlaying !== undefined) {
            const isCurrentlyPlaying = !Spicetify.Player.origin._state.isPaused;
            if (isCurrentlyPlaying !== serverState.isPlaying) {
                Spicetify.Player.togglePlay();
                this.localState.isPlaying = serverState.isPlaying;
            }
        }
        // Shuffle
        if (serverState.isShuffling !== undefined && Spicetify.Player.getShuffle() !== serverState.isShuffling) {
            Spicetify.Player.toggleShuffle();
            this.localState.isShuffling = serverState.isShuffling;
        }
        // Repeat
        if (serverState.repeatStatus !== undefined && Spicetify.Player.getRepeat() !== serverState.repeatStatus) {
            Spicetify.Player.setRepeat(serverState.repeatStatus);
            this.localState.repeatStatus = serverState.repeatStatus;
        }
    },

    /**
     * Handles a `playbackControl` message from the server, executing the command.
     * @param {object} commandData The command object from the server.
     */
    handlePlaybackControl(commandData) {
        console.log(`Remote Volume: Received command '${commandData.command}'.`);
        switch (commandData.command) {
            case "togglePlay": Spicetify.Player.togglePlay(); break;
            case "play": Spicetify.Player.play(); break;
            case "pause": Spicetify.Player.pause(); break;
            case "previous": Spicetify.Player.back(); break;
            case "next": Spicetify.Player.next(); break;
            case "seek": Spicetify.Player.seek(commandData.position); break;
            case "toggleShuffle": Spicetify.Player.toggleShuffle(); break;
            case "toggleRepeat":
                const nextRepeat = (Spicetify.Player.getRepeat() + 1) % 3;
                Spicetify.Player.setRepeat(nextRepeat);
                break;
            case "like": Spicetify.Player.toggleHeart(); break;
            default:
                console.warn(`Remote Volume: Unknown playback command: ${commandData.command}`);
        }
    },

    /**
     * Sets up listeners for Spicetify player events.
     */
    setupEventListeners() {
      Spicetify.Player.addEventListener("songchange", () => this.checkForTrackChange(true));
      Spicetify.Player.addEventListener("onplaypause", () => this.checkForPlaybackChange(true));
      Spicetify.Player.addEventListener("onprogress", () => this.checkForProgressChange());
      Spicetify.Player.addEventListener("toggleheart", () => this.checkForLikeChange(true));
    },

    /**
     * Starts the polling mechanism to periodically check for state changes.
     */
    startPolling() {
      setInterval(() => {
        this.checkForVolumeChange();
        this.checkForShuffleChange();
        this.checkForRepeatChange();
        this.checkForLikeChange();
      }, this.config.POLLING_INTERVAL_MS);
    },

    /**
     * A wrapper to send all local state updates to the server.
     * @param {boolean} force - If true, sends updates regardless of change.
     */
    sendAllLocalUpdates(force = false) {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      this.checkForVolumeChange(force);
      this.checkForPlaybackChange(force);
      this.checkForShuffleChange(force);
      this.checkForRepeatChange(force);
      this.checkForProgressChange(force);
      this.checkForTrackChange(force);
      this.checkForLikeChange(force);
    },

    // --- Individual State Checkers ---

    checkForVolumeChange(force = false) {
      const current = Spicetify.Player.getVolume();
      if (force || Math.abs(current - this.localState.volume) > 0.01) {
        this.localState.volume = current;
        this.websocket.send({ type: "volumeUpdate", volume: current });
      }
    },

    checkForPlaybackChange(force = false) {
      const current = !Spicetify.Player.origin._state.isPaused;
      if (force || current !== this.localState.isPlaying) {
        this.localState.isPlaying = current;
        this.websocket.send({ type: "playbackUpdate", isPlaying: current });
      }
    },

    checkForShuffleChange(force = false) {
      const current = Spicetify.Player.getShuffle();
      if (force || current !== this.localState.isShuffling) {
        this.localState.isShuffling = current;
        this.websocket.send({ type: "shuffleUpdate", isShuffling: current });
      }
    },

    checkForRepeatChange(force = false) {
      const current = Spicetify.Player.getRepeat();
      if (force || current !== this.localState.repeatStatus) {
        this.localState.repeatStatus = current;
        this.websocket.send({ type: "repeatUpdate", repeatStatus: current });
      }
    },

    checkForProgressChange(force = false) {
      const current = Spicetify.Player.getProgress();
      if (force || Math.abs(current - this.localState.progress) > this.config.POLLING_INTERVAL_MS) {
        this.localState.progress = current;
        this.websocket.send({
          type: "progressUpdate",
          progress: current,
          duration: Spicetify.Player.getDuration(),
        });
      }
    },

    checkForTrackChange(force = false) {
      const track = Spicetify.Player.data.item;
      if (!track) return;
      const current = track.uri;
      if (force || current !== this.localState.trackUri) {
        this.localState.trackUri = current;
        const trackData = this.getTrackInfo(track);
        this.websocket.send({ type: "trackUpdate", ...trackData });
      }
    },

    checkForLikeChange(force = false) {
      const current = Spicetify.Player.getHeart();
      if (force || current !== this.localState.isLiked) {
        this.localState.isLiked = current;
        this.websocket.send({ type: "likeUpdate", isLiked: current });
      }
    },

    /**
     * Extracts and formats track information.
     * @param {object} track - The track object from Spicetify.
     * @returns {object} Cleaned track data.
     */
    getTrackInfo(track) {
      let albumArtUrl = track.images?.[0]?.url || "";
      if (albumArtUrl.startsWith("spotify:image:")) {
        albumArtUrl = `https://i.scdn.co/image/${albumArtUrl.replace("spotify:image:", "")}`;
      }
      return {
        trackName: track.name || "Unknown Track",
        artistName: track.artists?.[0]?.name || "Unknown Artist",
        albumArtUrl: albumArtUrl || "",
      };
    },

    /**
     * Exposes global controls for hotkeys or other extensions.
     */
    exposeGlobalControls() {
        Spicetify.Player.volumeUp = () => this.websocket.send({ type: "volumeUpdate", command: "volumeUp" });
        Spicetify.Player.volumeDown = () => this.websocket.send({ type: "volumeUpdate", command: "volumeDown" });
    }
  };

  SpotifyRemote.init();
})();
