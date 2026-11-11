# Architecture (SC Dual-Source)

## Communication Flow

```
Spotify → Spicetify Extension (remoteVolume.js) ──┐
                                                    │
SoundCloud → SC Plugin (soundcloud-remote-bridge.js) ─┤
                                                    │ WS (localhost:8888)
Website (script.js) ──────────────────────────────────┤
                                                    │
OBS Widget (obs-script.js) ──────────────────────────┘
                                                    │
                                         ┌──────────┴──────────┐
                                         │   server/server.py  │
                                         │  (aiohttp, single)  │
                                         ├─────────────────────┤
                                         │  GET  /api/state    │

                                         └─────────────────────┘
                                                    │
                                         ┌──────────┴──────────┐
                                         │ Musixmatch + LRCLIB │
                                         │  APIs (HTTPS)       │
                                         │  SQLite cache (local)│
                                         └─────────────────────┘
```

## Key Design Decisions

- **Single port** (8888) for HTTP + WebSocket
- **Server split into modules** — `server.py` is a thin coordinator
- **No discovery** — clients connect directly to main port
- **Full-snapshot broadcasts** — state/progress messages carry the whole source snapshot (the SoundCloud 500 ms heartbeat is change-gated by a fingerprint, so unchanged heartbeats are not rebroadcast)
- **Client types** via query param (`?client=spicetify|soundcloud|website|obs|streamdeck`)
- **Targeted broadcast** — playback commands go ONLY to the target client type (`target_type` in `broadcast()`); the sender is always excluded
- **Dual-file state** — `state_spotify.json` + `state_soundcloud.json` (separate save flows)
- **Layered config** — code defaults ← tracked `data/config.default.json` ← gitignored user `data/config.json` (created on first run). `SC_SP_REMOTE_CONFIG` overrides the user-config path; `SC_SP_REMOTE_DATA_DIR` redirects all runtime data (state, logs, cache) for dev/tests.
- **Debounced state saves** (2s inactivity)
- **Disconnect is not "paused"** — a source controller disconnect broadcasts `sourceStatus{connected:false}` and only pauses playback after a 1.5 s grace, re-checked against the client list, so reconnects don't pause the music
- **Bounded broadcast** — every WebSocket send has a 1 s timeout; an unresponsive client is dropped instead of stalling the 1 Hz progress loop
- **Client-side color extraction** from album art via Canvas API
- **Profanity filter** — base64-encoded word list (GitHub moderation safety)
- **`/api/state` HTTP endpoint** — returns dual-source state (`spotify` + `soundcloud` blocks) with pre-formatted `progressFmt`/`durationFmt`
- **Security gates** — `security_middleware` (Host allowlist against DNS rebinding, same-origin check for state-changing requests, `/api/admin` loopback-only), CORS allowlist (explicit localhost default), WebSocket origin allowlist (`_is_foreign_web_origin`), `musixmatchToken` redacted from admin config GET, lyric text HTML-escaped before innerHTML


## State Shape (state.py)

```python
state = {
    # Spotify
    "volume": 0.0-1.0,
    "isPlaying": bool,
    "currentTrack": {trackName, artistName, albumName, trackUri, albumUri, artistUri, albumArtUrl},
    "trackProgress": int (ms), "trackDuration": int (ms), "trackProgressStartTimestamp": float,
    "isShuffling": bool, "repeatStatus": 0|1|2, "isLiked": bool,
    "lyrics": {trackUri, synced, plain, available, instrumental, loading},  # karaoke/provider added at runtime
    # SoundCloud (sc* prefix)
    "scTrack", "scArtist", "scAlbum", "scId", "scCoverUrl",
    "scIsPlaying": bool, "scProgressMs": 0, "scDurationMs": 0,
    "scProgressStartTimestamp": float,
    "scVolume": 0.5, "scIsLiked": bool,
    "scIsShuffling": bool, "scRepeatStatus": 0|1|2,
}

```

## Message Types

| Type | Direction | Purpose |
|---|---|---|
| `getInitialState` | Client→Server | Request full state dump |
| `stateUpdate`/`trackUpdate` | Spicetify→Server | Spotify snapshot |
| `volumeUpdate` | Spicetify→Server | Spotify volume |
| `playbackUpdate` | Spicetify→Server | Spotify play/pause/progress |
| `shuffleUpdate`/`repeatUpdate`/`likeUpdate` | Spicetify→Server | Spotify state |
| `progressUpdate` | Spicetify→Server | Spotify progress sync |
| `clientLog` | Any→Server | Client-side log messages (useful for SC which can't access DevTools) |
| **SoundCloud** | | |
| `scStateUpdate` | SC Plugin→Server | SC track/artist/progress + shuffle/repeat (normalized to Spotify's 0=off, 1=all, 2=one scale) |
| `scVolumeUpdate` | SC Plugin→Server | SC volume |
| `scPlaybackControl` | Web/StreamDeck→Server→SC Plugin | Play/pause/next/prev/toggleShuffle/toggleRepeat/like (server routes by source) |
| **Commands** | | |
| `playbackControl` | Web→Server→Spicetify | Play/pause/next/prev/seek |
| `like` | Web→Server | Like current track (source-aware) |
| **Server→All** | | |
| `lyricsUpdate` | Server→All | Lyrics data (`synced`/`plain`/`karaoke`, `provider` attribution, `loading`) |
| `sourceStatus` | Server→All | `{source, connected}` — a playback source's controller attached/detached (never means "paused") |
| `error` | Any | Error relay |


