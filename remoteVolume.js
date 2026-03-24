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
          this.config.SERVER_URL = `ws://localhost:${cfg.port}/?client=spicetify`;
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
        this.connectionTimestamp = Date.now();
      } catch (error) {
        console.error("[RemoteVolume] Connection error:", error);
        this.scheduleReconnect(this.connect.bind(this));
      }
    },

    onOpen() {
      console.log("[RemoteVolume] Connected.");
      this.reconnectAttempts = 0;
      // No need for manual register, handled by query params
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
      });
      Spicetify.Player.addEventListener("onplaypause", () =>
        this.checkPlaybackStatus(true)
      );
    },

    /**
     * Checks state that requires polling (Volume, Shuffle, Repeat, Heart)
     */
    checkPolledState() {
      this.checkVolume();
      this.checkShuffle();
      this.checkRepeat();
      this.checkLikeStatus();
      this.checkProgressChange(); 
    },

    syncFullState() {
      // This is the "Snapshot" - sent only on connection
      const data = Spicetify.Player.data || {};
      const track = data.item;
      if (!track) return;

      const meta = track.metadata || {};
      let artUrl = "";
      if (track.images && track.images.length > 0) {
          artUrl = track.images[0].url;
      } else if (meta.image_url) {
          artUrl = meta.image_url;
      }
      if (artUrl && artUrl.startsWith("spotify:image:")) {
          artUrl = "https://i.scdn.co/image/" + artUrl.substring(14);
      }

      const snapshot = {
        type: "stateUpdate", 
        volume: Spicetify.Player.getVolume(),
        isPlaying: Spicetify.Player.isPlaying(),
        isShuffling: Spicetify.Player.getShuffle(),
        repeatStatus: Spicetify.Player.getRepeat(),
        isLiked: Spicetify.Player.getHeart(),
        trackName: track.name || meta.title || "Unknown Track",
        artistName: (track.artists && track.artists[0] && track.artists[0].name) || meta.artist_name || "Unknown Artist",
        albumName: (track.album && track.album.name) || meta.album_title || "Unknown Album",
        trackUri: track.uri || meta.uri || "",
        albumUri: (track.album && track.album.uri) || meta.album_uri || "",
        albumArtUrl: artUrl,
        duration: Spicetify.Player.getDuration(),
        progress: Spicetify.Player.getProgress()
      };

      this.state = { ...snapshot };
      this.send(snapshot);
    },

    // --- Individual Checkers (The Deltas) ---

    checkVolume(force = false) {
      const vol = Spicetify.Player.getVolume();
      if (force || Math.abs(vol - this.state.volume) > 0.001) {
        this.state.volume = vol;
        this.send({ type: "volumeUpdate", volume: vol });
      }
    },

    checkPlaybackStatus(force = false) {
      const isPlaying = Spicetify.Player.isPlaying();
      if (force || isPlaying !== this.state.isPlaying) {
        this.state.isPlaying = isPlaying;
        this.send({ type: "playbackUpdate", isPlaying: isPlaying, progress: Spicetify.Player.getProgress() });
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
        
        let artUrl = "";
        if (track.images && track.images.length > 0) {
            artUrl = track.images[0].url;
        } else if (meta.image_url) {
            artUrl = meta.image_url;
        }
        if (artUrl && artUrl.startsWith("spotify:image:")) {
            artUrl = "https://i.scdn.co/image/" + artUrl.substring(14);
        }

        const metadata = {
          type: "trackUpdate",
          trackName: track.name || meta.title || "Unknown Track",
          artistName: (track.artists && track.artists[0] && track.artists[0].name) || meta.artist_name || "Unknown Artist",
          albumName: (track.album && track.album.name) || meta.album_title || "Unknown Album",
          trackUri: track.uri || meta.uri || "",
          albumUri: (track.album && track.album.uri) || meta.album_uri || "",
          albumArtUrl: artUrl,
          duration: Spicetify.Player.getDuration(),
          progress: 0 // New tracks always start at 0
        };

        this.send(metadata);
      }
    },

    checkProgressChange(force = false) {
      let progress = Spicetify.Player.getProgress();
      // Only send update if progress has drifted significantly (> 2 sec)
      if (force || Math.abs(progress - this.state.progress) > 2000) {
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
      if (serverState.volume !== undefined) {
        if (Math.abs(Spicetify.Player.getVolume() - serverState.volume) > 0.01) {
          Spicetify.Player.setVolume(serverState.volume);
          this.state.volume = serverState.volume;
        }
      }

      if (serverState.isPlaying !== undefined) {
        const isStaleWindow = (Date.now() - this.connectionTimestamp) < 2000;
        if (!isStaleWindow && Spicetify.Player.isPlaying() !== serverState.isPlaying) {
          if (serverState.isPlaying) Spicetify.Player.play();
          else Spicetify.Player.pause();
          this.state.isPlaying = serverState.isPlaying;
        }
      }

      if (serverState.isShuffling !== undefined) {
        if (Spicetify.Player.getShuffle() !== serverState.isShuffling) {
          Spicetify.Player.toggleShuffle();
          this.state.isShuffling = serverState.isShuffling;
        }
      }

      if (serverState.repeatStatus !== undefined) {
        if (Spicetify.Player.getRepeat() !== serverState.repeatStatus) {
          Spicetify.Player.setRepeat(serverState.repeatStatus);
          this.state.repeatStatus = serverState.repeatStatus;
        }
      }

      if (serverState.isLiked !== undefined) {
        if (Spicetify.Player.getHeart() !== serverState.isLiked) {
          Spicetify.Player.toggleHeart();
          this.state.isLiked = serverState.isLiked;
        }
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
          if (data.position !== undefined) Spicetify.Player.seek(data.position);
          break;
        case "toggleShuffle":
          Spicetify.Player.toggleShuffle();
          break;
        case "toggleRepeat":
          Spicetify.Player.setRepeat((Spicetify.Player.getRepeat() + 1) % 3);
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
      
      // OPTIMIZED SYNC: Only check the specific thing likely to have changed.
      // 150ms delay gives Spotify enough time to update its internal state.
      setTimeout(() => {
        if (["next", "previous"].includes(data.command)) this.checkTrackChange();
        else if (["play", "pause", "togglePlay"].includes(data.command)) this.checkPlaybackStatus();
        else if (data.command === "toggleShuffle") this.checkShuffle();
        else if (data.command === "toggleRepeat") this.checkRepeat();
        else if (data.command === "like") this.checkLikeStatus();
        else if (["volumeUp", "volumeDown"].includes(data.command)) this.checkVolume();
      }, 150);
    },

    exposeGlobals() {
      // Expose for other extensions or debugging
      window.SpotifyRemote = this;
    }
  };

  SpotifyRemote.init();
})();
