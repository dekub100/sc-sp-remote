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
                                         │  LRCLIB API (HTTPS) │
                                         │  SQLite cache (local)│
                                         └─────────────────────┘
```

## Key Design Decisions

- **Single port** (8888) for HTTP + WebSocket
- **Server split into modules** — `server.py` is a thin coordinator
- **No discovery** — clients connect directly to main port
- **Delta-based sync** — only changed fields sent
- **Client types** via query param (`?client=spicetify|soundcloud|website|obs`)
- **Targeted broadcast** — commands from web go ONLY to target client type
- **Dual-file state** — `state_spotify.json` + `state_soundcloud.json` (separate save flows)
- **SC_REMOTE_CONFIG env var** — overrides config path (instead of SPICETIFY_CONFIG)
- **Debounced state saves** (2s inactivity)
- **Client-side color extraction** from album art via Canvas API
- **Profanity filter** — base64-encoded word list (GitHub moderation safety)
- **`/api/state` HTTP endpoint** — returns dual-source state (`spotify` + `soundcloud` blocks) with pre-formatted `progressFmt`/`durationFmt`


## State Shape (state.py)

```python
state = {
    # Spotify
    "volume": 0.0-1.0,
    "isPlaying": bool,
    "currentTrack": {trackName, artistName, albumName, trackUri, albumUri, albumArtUrl},
    "trackProgress": int (ms), "trackDuration": int (ms), "trackProgressStartTimestamp": float,
    "isShuffling": bool, "repeatStatus": 0|1|2, "isLiked": bool,
    "lyrics": {trackUri, synced, plain, available, instrumental, loading},
    # SoundCloud (sc* prefix)
    "scTrack", "scArtist", "scAlbum", "scId", "scCoverUrl",
    "scIsPlaying": bool, "scProgressMs": 0, "scDurationMs": 0,
    "scProgressStartTimestamp": float,
    "scVolume": 0.5, "scIsLiked": bool,
}

```

## Message Types

| Type | Direction | Purpose |
|---|---|---|
| `register` | Client→Server | Register client type |
| `getInitialState` | Client→Server | Request full state dump |
| `stateUpdate`/`trackUpdate` | Spicetify→Server | Spotify snapshot |
| `volumeUpdate` | Spicetify→Server | Spotify volume |
| `playbackUpdate` | Spicetify→Server | Spotify play/pause/progress |
| `shuffleUpdate`/`repeatUpdate`/`likeUpdate` | Spicetify→Server | Spotify state |
| `progressUpdate` | Spicetify→Server | Spotify progress sync |
| `clientLog` | Any→Server | Client-side log messages (useful for SC which can't access DevTools) |
| **SoundCloud** | | |
| `scStateUpdate` | SC Plugin→Server | SC track/artist/progress |
| `scVolumeUpdate` | SC Plugin→Server | SC volume |
| `scPlaybackControl` | Server→SC Plugin | Play/pause/next/prev |
| **Commands** | | |
| `playbackControl` | Web→Server→Spicetify | Play/pause/next/prev/seek |
| `like` | Web→Server | Like current track (source-aware) |
| **Server→All** | | |
| `lyricsUpdate` | Server→All | Lyrics data |
| `error` | Any | Error relay |


