# Architecture (SC Dual-Source)

## Communication Flow

```
Spotify → Spicetify Extension (remoteVolume.js) ──┐
                                                    │
SoundCloud → SC Plugin (soundcloud-remote-bridge.js) ─┤
                                                    │ WS (localhost:8889)
Website (script.js) ──────────────────────────────────┤
                                                    │
OBS Widget (obs-script.js) ──────────────────────────┘
                                                    │
                                         ┌──────────┴──────────┐
                                         │   server/server.py  │
                                         │  (aiohttp, single)  │
                                         ├─────────────────────┤
                                         │  GET  /api/state    │
                                         │  GET  /api/queue    │
                                         │  POST /api/queue/add│
                                         │  DEL  /api/queue/remove│
                                         │  POST /api/queue/clear│
                                         └─────────────────────┘
                                                    │
                                         ┌──────────┴──────────┐
                                         │  LRCLIB API (HTTPS) │
                                         │  SQLite cache (local)│
                                         └─────────────────────┘
```

## Key Design Decisions

- **Single port** (8889) for HTTP + WebSocket — avoids collision with main branch (8888)
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
- **OBS Up Next transition** — shows next queued track when ≤15s remaining
- **`/api/state` HTTP endpoint** — returns dual-source state (`spotify` + `soundcloud` blocks) with pre-formatted `progressFmt`/`durationFmt`
- **Queue URI normalization** — `parse_track_input()` converts URLs to `spotify:track:xxx`
- **Queue rate limiting** — per-requester 30s cooldown, configurable via `queueRateLimitSeconds`
- **Queue polling** — extension polls `Spicetify.Queue` every 2s, sends `queueSnapshot`

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
    "queue": {nextTracks: [], queueRevision: ""},
    # SoundCloud (sc* prefix)
    "scTrack", "scArtist", "scAlbum", "scId", "scCoverUrl",
    "scIsPlaying": bool, "scProgressMs": 0, "scDurationMs": 0,
    "scProgressStartTimestamp": float,
    "scVolume": 0.5, "scIsLiked": bool, "scQueue": [],
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
| `queueSnapshot` | Spicetify→Server | Queue state polling |
| **SoundCloud** | | |
| `scStateUpdate` | SC Plugin→Server | SC track/artist/progress |
| `scVolumeUpdate` | SC Plugin→Server | SC volume |
| `scPlaybackControl` | Server→SC Plugin | Play/pause/next/prev |
| **Cross-source** | | |
| `activeSourceUpdate` | Server→All | Active player changed |
| **Commands** | | |
| `playbackControl` | Web→Server→Spicetify | Play/pause/next/prev/seek |
| `like` | Web→Server | Like current track (source-aware) |
| `addToQueue`/`removeFromQueue`/`clearQueue` | Web→Server→Spicetify | Queue management |
| **Server→All** | | |
| `lyricsUpdate` | Server→All | Lyrics data |
| `queueUpdate` | Server→All | Queue state broadcast |
| `error` | Any | Error relay |

## Queue System

Viewers request songs via web UI → server checks rate limit + queue-full + dedup → forwards to extension → extension calls `Spicetify.addToQueue()` → extension polls `Spicetify.Queue.nextTracks` → mirrors to server → server broadcasts to clients. Queue-full check uses `pendingQueueMeta.length`. `requestedBy` is matched via URI against `pendingQueueMeta` FIFO.
