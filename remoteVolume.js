// Spicetify extension to sync Spotify's state with a remote server.
// Refactored for performance, reliability, and modern Spicetify API usage.

(function remoteVolume() {
  const SpotifyRemote = {
    // --- Configuration ---
    config: {
      CONFIG_URL: "http://localhost:54321/api/config",
      SERVER_URL: null,
      POLLING_INTERVAL_MS: 500, // Reduced frequency since we use events
      RECONNECT_DELAY_BASE: 1000,
      MAX_RECONNECT_DELAY: 30000,
    },

    // --- State Management ---
    // We keep a local copy to avoid sending redundant updates to the server.
    state: {
      volume: -1,
      isPlaying: false,
      isShuffling: false,
      repeatStatus: -1,
      isLiked: false,
      trackUri: null,
      progress: -1,
      timestamp: 0,
    },

    ws: null,
    reconnectAttempts: 0,
    pollInterval: null,

    // --- Initialization ---
    init() {
      if (!Spicetify.Player || !Spicetify.Platform) {
        setTimeout(this.init.bind(this), 300);
        return;
      }
      console.log("[RemoteVolume] Spicetify ready. Initializing...");
      this.fetchServerConfig();
    },

    fetchServerConfig() {
      fetch(this.config.CONFIG_URL)
        .then((res) => res.json())
        .then((cfg) => {
          this.config.SERVER_URL = `ws://localhost:${cfg.port}`;
          this.reconnectAttempts = 0;
          this.connect();
        })
        .catch((err) => {
          console.error("[RemoteVolume] Config fetch failed:", err);
          this.scheduleReconnect(this.fetchServerConfig.bind(this));
        });
    },

    // --- WebSocket Logic ---
    connect() {
      if (this.ws) {
        this.ws.close();
      }

      console.log(`[RemoteVolume] Connecting to ${this.config.SERVER_URL}...`);
      try {
        this.ws = new WebSocket(this.config.SERVER_URL);
        this.ws.onopen = this.onOpen.bind(this);
        this.ws.onmessage = this.onMessage.bind(this);
        this.ws.onclose = this.onClose.bind(this);
        this.ws.onerror = this.onError.bind(this);
      } catch (error) {
        console.error("[RemoteVolume] Connection error:", error);
        this.scheduleReconnect(this.connect.bind(this));
      }
    },

    onOpen() {
      console.log("[RemoteVolume] Connected.");
      this.reconnectAttempts = 0;
      this.syncFullState(true); // Force push all state on connect
      this.startServices();
    },

    onMessage(event) {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "stateUpdate":
          case "volumeUpdate":
          case "playbackUpdate":
          case "shuffleUpdate":
          case "repeatUpdate":
          case "likeUpdate":
            this.applyServerState(data);
            break;
          case "playbackControl":
            this.handleCommand(data);
            break;
        }
      } catch (err) {
        console.error("[RemoteVolume] Message parse error:", err);
      }
    },

    onClose() {
      console.warn("[RemoteVolume] Socket closed.");
      this.stopServices();
      this.scheduleReconnect(this.connect.bind(this));
    },

    onError(err) {
      console.error("[RemoteVolume] Socket error:", err);
      // specific error handling if needed, usually 'onclose' follows
    },

    scheduleReconnect(callback) {
      const delay = Math.min(
        this.config.RECONNECT_DELAY_BASE * Math.pow(2, this.reconnectAttempts),
        this.config.MAX_RECONNECT_DELAY
      );
      this.reconnectAttempts++;
      console.log(`[RemoteVolume] Reconnecting in ${delay}ms...`);
      setTimeout(callback, delay);
    },

    send(data) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(data));
      }
    },

    // --- Core Logic ---

    startServices() {
      this.setupEventListeners();
      if (!this.pollInterval) {
        this.pollInterval = setInterval(
          this.checkPolledState.bind(this),
          this.config.POLLING_INTERVAL_MS
        );
      }
    },

    stopServices() {
      if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
      }
      // Note: We don't remove event listeners because Spicetify doesn't provide an easy way 
      // to remove specific anonymous functions without storing references, and they are harmless 
      // if the socket is closed (send() just drops data).
    },

    setupEventListeners() {
      // Spicetify events are the most reliable source for these changes
      Spicetify.Player.addEventListener("songchange", () => {
        this.checkTrackChange(true);
        this.checkProgressChange(true);
      });
      Spicetify.Player.addEventListener("onplaypause", () =>
        this.checkPlaybackStatus(true)
      );
      
      // We can use the 'onprogress' event, but it fires very rapidly. 
      // We'll trust the poller/songchange for progress to save bandwidth, 
      // or throttle this if needed.
    },

    /**
     * Checks state that requires polling (Volume, Shuffle, Repeat, Heart)
     * as they don't always have consistent events across Spicetify versions.
     */
    checkPolledState() {
      this.checkVolume();
      this.checkShuffle();
      this.checkRepeat();
      this.checkLikeStatus();
      this.checkProgressChange(); // Periodic sync for progress
    },

    syncFullState(force = false) {
      this.checkVolume(force);
      this.checkPlaybackStatus(force);
      this.checkShuffle(force);
      this.checkRepeat(force);
      this.checkLikeStatus(force);
      this.checkTrackChange(force);
      this.checkProgressChange(force);
    },

    // --- Individual Checkers ---

    checkVolume(force = false) {
      const vol = Spicetify.Player.getVolume();
      if (force || Math.abs(vol - this.state.volume) > 0.001) {
        this.state.volume = vol;
        this.send({ type: "volumeUpdate", volume: vol });
      }
    },

    checkPlaybackStatus(force = false) {
      // Use public API for playback state
      const isPlaying = Spicetify.Player.isPlaying();
      if (force || isPlaying !== this.state.isPlaying) {
        this.state.isPlaying = isPlaying;
        this.send({ type: "playbackUpdate", isPlaying: isPlaying });
      }
    },

    checkShuffle(force = false) {
      const isShuffling = Spicetify.Player.getShuffle();
      if (force || isShuffling !== this.state.isShuffling) {
        this.state.isShuffling = isShuffling;
        this.send({ type: "shuffleUpdate", isShuffling: isShuffling });
      }
    },

    checkRepeat(force = false) {
      const repeat = Spicetify.Player.getRepeat();
      if (force || repeat !== this.state.repeatStatus) {
        this.state.repeatStatus = repeat;
        this.send({ type: "repeatUpdate", repeatStatus: repeat });
      }
    },

    checkLikeStatus(force = false) {
      const isLiked = Spicetify.Player.getHeart();
      if (force || isLiked !== this.state.isLiked) {
        this.state.isLiked = isLiked;
        this.send({ type: "likeUpdate", isLiked: isLiked });
      }
    },

    checkTrackChange(force = false) {
      const data = Spicetify.Player.data || {};
      const track = data.item;
      if (!track) return;

      if (force || track.uri !== this.state.trackUri) {
        this.state.trackUri = track.uri;
        const meta = track.metadata || {};
        
        // Extract artwork safely
        let artUrl = "";
        if (track.images && track.images.length > 0) {
            artUrl = track.images[0].url;
        } else if (meta.image_url) {
            artUrl = meta.image_url;
        }
        
        // Normalize Spotify image URIs to HTTPS URLs if needed
        if (artUrl && artUrl.startsWith("spotify:image:")) {
            artUrl = "https://i.scdn.co/image/" + artUrl.substring(14);
        }

        const trackData = {
          trackName: track.name || meta.title || "Unknown Track",
          artistName: (track.artists && track.artists[0] && track.artists[0].name) || meta.artist_name || "Unknown Artist",
          albumArtUrl: artUrl,
          duration: Spicetify.Player.getDuration(),
        };

        this.send({ type: "trackUpdate", ...trackData });
      }
    },

    checkProgressChange(force = false) {
      const progress = Spicetify.Player.getProgress();
      // Only send update if progress has drifted significantly (> 1 sec) or forced
      // This prevents spamming the server every 250ms with micro-updates
      if (force || Math.abs(progress - this.state.progress) > 1000) {
        this.state.progress = progress;
        this.send({
          type: "progressUpdate",
          progress: progress,
          duration: Spicetify.Player.getDuration(),
        });
      }
    },

    // --- Server -> Client Command Handling ---

    applyServerState(serverState) {
      // Volume
      if (serverState.volume !== undefined) {
        const current = Spicetify.Player.getVolume();
        if (Math.abs(current - serverState.volume) > 0.01) {
          Spicetify.Player.setVolume(serverState.volume);
          this.state.volume = serverState.volume;
        }
      }

      // Playback
      if (serverState.isPlaying !== undefined) {
        const current = Spicetify.Player.isPlaying();
        
        // ISOLATION LOGIC:
        // We only honor playback changes if they come from a dedicated playbackUpdate 
        // OR a full stateUpdate that actually intends to sync state.
        // If it's a volumeUpdate, we ignore the isPlaying field to avoid stale pauses.
        const isReliableSource = serverState.type === "playbackUpdate" || 
                                 (serverState.type === "stateUpdate" && serverState.trackName !== undefined);

        if (isReliableSource && current !== serverState.isPlaying) {
          if (serverState.isPlaying) Spicetify.Player.play();
          else Spicetify.Player.pause();
          this.state.isPlaying = serverState.isPlaying;
        }
      }

      // Shuffle
      if (
        serverState.isShuffling !== undefined &&
        Spicetify.Player.getShuffle() !== serverState.isShuffling
      ) {
        Spicetify.Player.toggleShuffle();
        this.state.isShuffling = serverState.isShuffling;
      }

      // Repeat
      if (
        serverState.repeatStatus !== undefined &&
        Spicetify.Player.getRepeat() !== serverState.repeatStatus
      ) {
        Spicetify.Player.setRepeat(serverState.repeatStatus);
        this.state.repeatStatus = serverState.repeatStatus;
      }
    },

    handleCommand(data) {
      console.log(`[RemoteVolume] Command: ${data.command}`);
      switch (data.command) {
        case "play":
        case "pause":
        case "togglePlay":
          Spicetify.Player.togglePlay();
          break;
        case "next":
          Spicetify.Player.next();
          break;
        case "previous":
          Spicetify.Player.back();
          break;
        case "seek":
          if (data.position !== undefined) {
            Spicetify.Player.seek(data.position);
          }
          break;
        case "toggleShuffle":
          Spicetify.Player.toggleShuffle();
          break;
        case "toggleRepeat":
          // Cycle: 0 (off) -> 1 (track) -> 2 (context) -> 0
          const nextRepeat = (Spicetify.Player.getRepeat() + 1) % 3;
          Spicetify.Player.setRepeat(nextRepeat);
          break;
        case "like":
          Spicetify.Player.toggleHeart();
          break;
        case "volumeUp":
          Spicetify.Player.increaseVolume();
          break;
        case "volumeDown":
          Spicetify.Player.decreaseVolume();
          break;
      }
      
      // FORCE SYNC: Immediately check state after a command.
      // This "wakes up" the UI even if Spotify is in the background.
      setTimeout(() => this.syncFullState(true), 100);
    },

    exposeGlobals() {
      // Expose for other extensions or debugging
      window.SpotifyRemote = this;
    }
  };

  SpotifyRemote.init();
})();
