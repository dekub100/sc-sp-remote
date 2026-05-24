# Architecture

## Communication Flow

```
Spotify → Spicetify (remoteVolume.js) ──┐
                                         │ WebSocket (localhost:8888)
Website (script.js) ─────────────────────┤
                                         │
OBS Widget (obs-script.js) ──────────────┤
                                         │
Stream Deck Plugin ──────────────────────┘
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

- **Single port** for HTTP + WebSocket
- **Server split into modules** — `server.py` is a thin coordinator
- **No discovery** — clients connect directly to main port
- **Delta-based sync** — only changed fields sent
- **Client types** via query param (`?client=spicetify|website|obs`)
- **Targeted broadcast** — commands from web/deck go ONLY to spicetify
- **Debounced state saves** (2s inactivity)
- **Client-side color extraction** from album art via Canvas API
- **Profanity filter** — base64-encoded word list (GitHub moderation safety)
- **OBS Up Next transition** — shows next queued track when ≤15s remaining
- **`/api/state` HTTP endpoint** — returns full state JSON with pre-formatted `progressFmt`/`durationFmt` (mm:ss). Used by Streamer.bot; no WebSocket needed.
- **Queue URI normalization** — `parse_track_input()` converts URLs (incl. `intl-xx/` variant) and bare URIs to `spotify:track:xxx`
- **Queue rate limiting** — per-requester 30s cooldown, configurable via `queueRateLimitSeconds`
- **Queue polling** — extension polls `Spicetify.Queue` every 2s, sends `queueSnapshot`, server matches URIs against `pendingQueueMeta` to inject `requestedBy`

## State Shape (state.py)

```python
state = {
    "volume": 0.0-1.0,
    "isPlaying": bool,
    "currentTrack": {"trackName", "artistName", "albumName", "trackUri", "albumUri", "albumArtUrl"},
    "trackProgress": int (ms),
    "trackDuration": int (ms),
    "trackProgressStartTimestamp": float (ms),
    "isShuffling": bool,
    "repeatStatus": 0|1|2,
    "isLiked": bool,
    "spicetifyClient": WebSocket|None,
    "lyrics": {"trackUri", "synced": [], "plain": "", "available": bool, "instrumental": bool, "loading": bool},
    "queue": {"nextTracks": [], "queueRevision": ""}
}
```

## Message Types

| Type | Direction | Purpose |
|---|---|---|
| `register` | Client→Server | Register client type |
| `getInitialState` | Client→Server | Request full state dump |
| `stateUpdate` | Spicetify→Server | Full snapshot on connect |
| `volumeUpdate` | Any→Server | Volume change |
| `playbackUpdate` | Spicetify→Server | Play/pause/progress |
| `shuffleUpdate` | Spicetify→Server | Shuffle toggle |
| `repeatUpdate` | Spicetify→Server | Repeat mode (0/1/2) |
| `likeUpdate` | Spicetify→Server | Heart/like status |
| `trackUpdate` | Spicetify→Server | New track (triggers lyrics fetch) |
| `progressUpdate` | Spicetify→Server | Progress sync |
| `playbackControl` | Any→Server | Command → spicetify only |
| `like` | Any→Server | Like shortcut |
| `lyricsUpdate` | Server→Clients | Lyrics data |
| `queueSnapshot` | Spicetify→Server | Queue state from polling |
| `addToQueue` | Any→Server | Add track → spicetify |
| `removeFromQueue` | Any→Server | Remove track → spicetify |
| `clearQueue` | Any→Server | Clear queue → spicetify |
| `queueUpdate` | Server→Clients | Queue state broadcast |
| `error` | Any→Server/Client | Error relay |

## Queue System

Viewers request songs → server forwards to extension → extension calls `Spicetify.addToQueue()` → extension polls `Spicetify.Queue.nextTracks` and mirrors to server → server broadcasts to clients. Queue-full check uses `pendingQueueMeta.length` (not `nextTracks.length`). `requestedBy` is matched via URI against pending metadata in FIFO order.
