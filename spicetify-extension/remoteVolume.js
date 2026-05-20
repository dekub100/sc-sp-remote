// Spicetify extension to sync Spotify's state with a remote server.
// Refactored for performance, reliability, and modern Spicetify API usage.

(function remoteVolume() {
  const SpotifyRemote = {
    // --- Configuration ---
    config: {
      DEFAULT_PORT: 8888,
      SERVER_URL: null,
      POLLING_INTERVAL_MS: 500,
      QUEUE_POLLING_INTERVAL_MS: 2000,
      RECONNECT_DELAY_BASE: 1000,
      MAX_RECONNECT_DELAY: 10000,
      PROGRESS_DELTA_THRESHOLD_MS: 2000,
      COMMAND_FEEDBACK_DELAY_MS: 150,
      PROTOCOL_VERSION: 1,
      STALE_CONNECTION_WINDOW_MS: 2000,
      VOLUME_STEP: 0.05,
    },

    // --- State Management ---
    state: {
      volume: -1,
      isPlaying: false,
      isShuffling: false,
      repeatStatus: -1,
      isLiked: false,
      trackUri: null,
      progress: -1,
      timestamp: 0,
      queueRevision: "",
    },

    ws: null,
    reconnectAttempts: 0,
    pollInterval: null,
    queueInterval: null,

    // --- Initialization ---
    init() {
      if (!Spicetify.Player || !Spicetify.Platform) {
        setTimeout(this.init.bind(this), 300);
        return;
      }
      console.log("[RemoteVolume] Spicetify ready. Initializing...");
      this.config.SERVER_URL = `ws://localhost:${this.config.DEFAULT_PORT}/?client=spicetify&protocolVersion=${this.config.PROTOCOL_VERSION}`;
      this.connect();
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
      this.syncFullState();
      this.startServices();
    },

    applyClientConfig(data) {
      if (data.pollingIntervalMs !== undefined) {
        this.config.POLLING_INTERVAL_MS = data.pollingIntervalMs;
        console.log(`[RemoteVolume] Config: pollingInterval = ${data.pollingIntervalMs}ms`);
      }
      if (data.queuePollingIntervalMs !== undefined) {
        this.config.QUEUE_POLLING_INTERVAL_MS = data.queuePollingIntervalMs;
        console.log(`[RemoteVolume] Config: queuePollingInterval = ${data.queuePollingIntervalMs}ms`);
      }
      if (data.reconnectBaseDelayMs !== undefined) {
        this.config.RECONNECT_DELAY_BASE = data.reconnectBaseDelayMs;
      }
      if (data.reconnectMaxDelayMs !== undefined) {
        this.config.MAX_RECONNECT_DELAY = data.reconnectMaxDelayMs;
      }
      if (data.progressDeltaThresholdMs !== undefined) {
        this.config.PROGRESS_DELTA_THRESHOLD_MS = data.progressDeltaThresholdMs;
      }
      if (data.commandFeedbackDelayMs !== undefined) {
        this.config.COMMAND_FEEDBACK_DELAY_MS = data.commandFeedbackDelayMs;
      }
      if (data.volumeStep !== undefined) {
        this.config.VOLUME_STEP = data.volumeStep;
      }
      this.stopServices();
      this.startServices();
    },

    onMessage(event) {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "config":
            this.applyClientConfig(data);
            break;
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
          case "addToQueue":
            this.handleAddToQueue(data);
            break;
          case "removeFromQueue":
            this.handleRemoveFromQueue(data);
            break;
          case "clearQueue":
            this.handleClearQueue();
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
        this.ws.send(JSON.stringify(data, (_key, value) =>
          typeof value === 'bigint' ? value.toString() : value
        ));
      }
    },

    _safeGet(fn, fallback) {
      try { return fn(); } catch { return fallback; }
    },

    // --- Helpers ---

    /**
     * Converts a Spotify internal image URI to a public URL.
     */
    getAlbumArtUrl(track) {
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
      return artUrl;
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
      if (!this.queueInterval) {
        this.queueInterval = setInterval(
          this.checkQueue.bind(this),
          this.config.QUEUE_POLLING_INTERVAL_MS
        );
      }
    },

    stopServices() {
      if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
      }
      if (this.queueInterval) {
        clearInterval(this.queueInterval);
        this.queueInterval = null;
      }
      if (this._onSongChange) {
        Spicetify.Player.removeEventListener("songchange", this._onSongChange);
        this._onSongChange = null;
      }
      if (this._onPlayPause) {
        Spicetify.Player.removeEventListener("onplaypause", this._onPlayPause);
        this._onPlayPause = null;
      }
    },

    setupEventListeners() {
      this._onSongChange = () => this.checkTrackChange(true);
      this._onPlayPause = () => this.checkPlaybackStatus(true);
      Spicetify.Player.addEventListener("songchange", this._onSongChange);
      Spicetify.Player.addEventListener("onplaypause", this._onPlayPause);
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
      const data = Spicetify.Player.data || {};
      const track = data.item;
      if (!track) return;

      const meta = track.metadata || {};
      const artUrl = this.getAlbumArtUrl(track);

      const snapshot = {
        type: "stateUpdate",
        volume: this._safeGet(() => Spicetify.Player.getVolume(), 0.5),
        isPlaying: this._safeGet(() => Spicetify.Player.isPlaying(), false),
        isShuffling: this._safeGet(() => Spicetify.Player.getShuffle(), false),
        repeatStatus: this._safeGet(() => Spicetify.Player.getRepeat(), 0),
        isLiked: this._safeGet(() => Spicetify.Player.getHeart(), false),
        trackName: track.name || meta.title || "Unknown Track",
        artistName: (track.artists && track.artists[0] && track.artists[0].name) || meta.artist_name || "Unknown Artist",
        albumName: (track.album && track.album.name) || meta.album_title || "Unknown Album",
        trackUri: track.uri || meta.uri || "",
        albumUri: (track.album && track.album.uri) || meta.album_uri || "",
        albumArtUrl: artUrl,
        duration: this._safeGet(() => Spicetify.Player.getDuration(), 0),
        progress: this._safeGet(() => Spicetify.Player.getProgress(), 0)
      };

      this.state = { ...snapshot };
      this.send(snapshot);
      this.checkQueue();
    },

    // --- Individual Checkers (The Deltas) ---

    checkVolume(force = false) {
      const vol = this._safeGet(() => Spicetify.Player.getVolume(), this.state.volume);
      if (force || Math.abs(vol - this.state.volume) > 0.001) {
        this.state.volume = vol;
        this.send({ type: "volumeUpdate", volume: vol });
      }
    },

    checkPlaybackStatus(force = false) {
      const isPlaying = this._safeGet(() => Spicetify.Player.isPlaying(), this.state.isPlaying);
      if (force || isPlaying !== this.state.isPlaying) {
        this.state.isPlaying = isPlaying;
        this.send({ type: "playbackUpdate", isPlaying: isPlaying, progress: this._safeGet(() => Spicetify.Player.getProgress(), 0) });
      }
    },

    checkShuffle(force = false) {
      const isShuffling = this._safeGet(() => Spicetify.Player.getShuffle(), this.state.isShuffling);
      if (force || isShuffling !== this.state.isShuffling) {
        this.state.isShuffling = isShuffling;
        this.send({ type: "shuffleUpdate", isShuffling: isShuffling });
      }
    },

    checkRepeat(force = false) {
      const repeat = this._safeGet(() => Spicetify.Player.getRepeat(), this.state.repeatStatus);
      if (force || repeat !== this.state.repeatStatus) {
        this.state.repeatStatus = repeat;
        this.send({ type: "repeatUpdate", repeatStatus: repeat });
      }
    },

    checkLikeStatus(force = false) {
      const isLiked = this._safeGet(() => Spicetify.Player.getHeart(), this.state.isLiked);
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
        const artUrl = this.getAlbumArtUrl(track);

        const metadata = {
          type: "trackUpdate",
          trackName: track.name || meta.title || "Unknown Track",
          artistName: (track.artists && track.artists[0] && track.artists[0].name) || meta.artist_name || "Unknown Artist",
          albumName: (track.album && track.album.name) || meta.album_title || "Unknown Album",
          trackUri: track.uri || meta.uri || "",
          albumUri: (track.album && track.album.uri) || meta.album_uri || "",
          albumArtUrl: artUrl,
          duration: this._safeGet(() => Spicetify.Player.getDuration(), 0),
          progress: 0
        };

        this.send(metadata);
        this.checkQueue();
      }
    },

    checkProgressChange(force = false) {
      let progress = this._safeGet(() => Spicetify.Player.getProgress(), this.state.progress);
      if (force || Math.abs(progress - this.state.progress) > this.config.PROGRESS_DELTA_THRESHOLD_MS) {
        this.state.progress = progress;
        this.send({
          type: "progressUpdate",
          progress: progress,
          duration: this._safeGet(() => Spicetify.Player.getDuration(), 0),
        });
      }
    },

    // --- Server -> Client Command Handling ---

    applyServerState(serverState) {
      const isStaleWindow = (Date.now() - this.connectionTimestamp) < this.config.STALE_CONNECTION_WINDOW_MS;

      if (serverState.volume !== undefined) {
        const currentVol = this._safeGet(() => Spicetify.Player.getVolume(), this.state.volume);
        if (Math.abs(currentVol - serverState.volume) > 0.01) {
          Spicetify.Player.setVolume(serverState.volume);
          this.state.volume = serverState.volume;
        }
      }

      if (serverState.isPlaying !== undefined) {
        if (!isStaleWindow) {
          const currentlyPlaying = this._safeGet(() => Spicetify.Player.isPlaying(), this.state.isPlaying);
          if (currentlyPlaying !== serverState.isPlaying) {
            if (serverState.isPlaying) Spicetify.Player.play();
            else Spicetify.Player.pause();
            this.state.isPlaying = serverState.isPlaying;
          }
        }
      }

      if (serverState.isShuffling !== undefined) {
        if (!isStaleWindow) {
          const currentShuffle = this._safeGet(() => Spicetify.Player.getShuffle(), this.state.isShuffling);
          if (currentShuffle !== serverState.isShuffling) {
            Spicetify.Player.toggleShuffle();
            this.state.isShuffling = serverState.isShuffling;
          }
        }
      }

      if (serverState.repeatStatus !== undefined) {
        if (!isStaleWindow) {
          const currentRepeat = this._safeGet(() => Spicetify.Player.getRepeat(), this.state.repeatStatus);
          if (currentRepeat !== serverState.repeatStatus) {
            Spicetify.Player.setRepeat(serverState.repeatStatus);
            this.state.repeatStatus = serverState.repeatStatus;
          }
        }
      }

      if (serverState.isLiked !== undefined) {
        if (!isStaleWindow) {
          const currentLiked = this._safeGet(() => Spicetify.Player.getHeart(), this.state.isLiked);
          if (currentLiked !== serverState.isLiked) {
            Spicetify.Player.toggleHeart();
            this.state.isLiked = serverState.isLiked;
          }
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
          Spicetify.Player.setRepeat((this._safeGet(() => Spicetify.Player.getRepeat(), 0) + 1) % 3);
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

      setTimeout(() => {
        if (["next", "previous"].includes(data.command)) this.checkTrackChange();
        else if (["play", "pause", "togglePlay"].includes(data.command)) this.checkPlaybackStatus();
        else if (data.command === "toggleShuffle") this.checkShuffle();
        else if (data.command === "toggleRepeat") this.checkRepeat();
        else if (data.command === "like") this.checkLikeStatus();
        else if (["volumeUp", "volumeDown"].includes(data.command)) this.checkVolume();
      }, this.config.COMMAND_FEEDBACK_DELAY_MS);
    },

    checkQueue() {
      const q = Spicetify.Queue;
      if (!q) return;
      const rev = String(q.queueRevision);
      if (rev === this.state.queueRevision) return;
      this.state.queueRevision = rev;
      const rawItems = q.nextTracks || [];
      const tracks = rawItems
        .filter(item => {
          const ct = item.contextTrack || item;
          return ct.uri && ct.uri !== "spotify:delimiter";
        })
        .map(item => {
          const ct = item.contextTrack || item;
          const meta = ct.metadata || {};
          const rawImg = meta.image_url || meta.image_small_url || meta.image_large_url || "";
          return {
            uri: ct.uri || "",
            uid: String(ct.uid ?? ""),
            metadata: {
              title: meta.title || ct.name || "",
              artist_name: meta.artist_name || (ct.artists?.[0]?.name) || "",
              album_name: meta.album_title || meta.album_name || (ct.album?.name) || "",
              image_url: rawImg.startsWith("spotify:image:")
                ? "https://i.scdn.co/image/" + rawImg.substring(14)
                : rawImg,
              duration: meta.duration || ""
            }
          };
        });
      this.send({ type: "queueSnapshot", nextTracks: tracks, queueRevision: rev });
    },

    async handleAddToQueue(data) {
      try {
        const uri = data.uri;
        if (!uri) return;
        await Spicetify.addToQueue([{ uri }]);
        console.log(`[RemoteVolume] Added to queue: ${uri}`);
      } catch (err) {
        console.error("[RemoteVolume] addToQueue failed:", err);
        this.send({ type: "error", message: `Failed to add track: ${err.message}` });
      }
    },

    async handleRemoveFromQueue(data) {
      try {
        const uri = data.uri;
        const uid = data.uid;
        if (!uri) return;
        if (!uid) {
          console.warn("[RemoteVolume] removeFromQueue: no uid provided, may remove duplicates");
        }
        const track = { uri };
        if (uid) track.uid = uid;
        await Spicetify.removeFromQueue([track]);
        console.log(`[RemoteVolume] Removed from queue: ${uri}`);
      } catch (err) {
        console.error("[RemoteVolume] removeFromQueue failed:", err);
        this.send({ type: "error", message: `Failed to remove track: ${err.message}` });
      }
    },

    async handleClearQueue() {
      try {
        const q = Spicetify.Queue;
        if (!q || !q.nextTracks || q.nextTracks.length === 0) return;
        const items = q.nextTracks
          .filter(item => {
            const ct = item.contextTrack || item;
            return ct.uri && ct.uri !== "spotify:delimiter";
          })
          .map(item => {
            const ct = item.contextTrack || item;
            const track = { uri: ct.uri };
            if (ct.uid) track.uid = ct.uid;
            return track;
          });
        await Spicetify.removeFromQueue(items);
        console.log(`[RemoteVolume] Cleared ${items.length} tracks from queue`);
      } catch (err) {
        console.error("[RemoteVolume] clearQueue failed:", err);
        this.send({ type: "error", message: `Failed to clear queue: ${err.message}` });
      }
    }
  };

  SpotifyRemote.init();
})();
