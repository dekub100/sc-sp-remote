# AGENTS.md — Spicetify Remote

## Project Overview

A Spicetify extension for remote control/viewing of Spotify using WebSockets, without Spotify Premium. Provides a web UI, OBS widget, and Stream Deck plugin — all communicating through a central Python server.

**Version:** 1.5.0
**GitHub:** https://github.com/dekub100/spicetify-remote

---

## Directory Structure

```
├── README.md
├── requirements.txt          # Python runtime deps (aiohttp, pywin32)
├── requirements-dev.txt     # Python dev deps (pytest, ruff, pytest-asyncio)
├── pyproject.toml            # ruff + pytest config
├── conftest.py               # pytest: adds server/ to sys.path
├── test_server.py            # 76 tests for server logic
├── setup.bat                 # One-click Windows installer
├── AGENTS.md                 # This file
├── CONTRIBUTING.md           # Running things, release workflow
├── data/
│   ├── config.json           # Default server configuration
│   └── (state.json, logs/, lyrics_cache.db — runtime only, gitignored)
├── server/
│   ├── server.py             # Entry point, imports all modules, routes + main()
│   ├── config.py             # Paths, constants, config.json loading
│   ├── log.py                # Logger setup, log rotation cleanup
│   ├── state.py              # State dict, JSON persistence, debounced saves
│   ├── broadcast.py          # CLIENTS dict, WebSocket broadcast functions
│   ├── lyrics.py             # LRC parser, LRCLIB fetcher, SQLite cache
│   ├── handlers.py           # Message handlers + dispatch table
│   └── routes.py             # WS handler, HTTP endpoints, static files
├── tools/
│   ├── service.py            # Windows service wrapper (pywin32)
│   └── install.py            # Spicetify extension installer
├── web/
│   ├── index.html            # Main web UI
│   ├── style.css
│   ├── script.js             # Web UI logic + WebSocket client
│   ├── filter.js             # Shared profanity filter (base64-encoded slur list)
│   └── obs-widget/
│       ├── obs-widget.html   # OBS browser source widget
│       ├── obs-style.css
│       └── obs-script.js     # OBS widget logic + WebSocket client
├── spicetify-extension/
│   └── remoteVolume.js       # Spicetify extension (runs inside Spotify)
├── streamdeck-plugin/        # Full TypeScript + Rollup + Elgato SDK source
│   ├── src/
│   │   ├── plugin.ts
│   │   ├── websocket-manager.ts
│   │   └── actions/
│   ├── rollup.config.mjs
│   ├── tsconfig.json
│   ├── package.json
│   └── com.dekub.spicetify-remote.sdPlugin/  # Built plugin output
├── streamerbot-commands/     # Streamer.bot integration setup
└── com.dekub.spicetify-remote.streamDeckPlugin  # Pre-built plugin package
```

**Ignored:** `logs/`, `state.json`, `lyrics_cache.db`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `streamdeck-plugin/node_modules/`

---

## Architecture

### Communication Flow

```
Spotify → Spicetify (remoteVolume.js) ──┐
                                         │ WebSocket (localhost:8888)
Website (script.js) ─────────────────────┤
                                         │
OBS Widget (obs-script.js) ──────────────┤
                                         │
Stream Deck Plugin ──────────────────────┘
                                         │
                              ┌────────────┴────────────┐
                              │    server/server.py     │
                              │  (aiohttp, single port) │
                              ├─────────────────────────┤
                              │  HTTP GET /api/state    │
                              │  (full JSON, mm:ss)     │
                              │  HTTP GET /api/queue    │
                              │  (queue + revision)     │
                              │  POST /api/queue/add    │
                              │  DELETE /api/queue/remove│
                              │  POST /api/queue/clear  │
                              └─────────────────────────┘
                                          │
                             ┌────────────┴────────────┐
                             │  Discovery: port 54321  │
                             │  /api/config → port #   │
                             └─────────────────────────┘
                                          │
                             ┌────────────┴────────────┐
                             │    LRCLIB API (HTTPS)   │
                             │    SQLite cache (local) │
                             └─────────────────────────┘
```

### Key Design Decisions

- **Single port** for HTTP + WebSocket (aiohttp handles both)
- **Server split into modules** — `server.py` is a thin coordinator; `config.py`, `log.py`, `state.py`, `broadcast.py`, `lyrics.py`, `handlers.py`, `routes.py` each own one concern
- **Discovery server** on port 54321 lets clients auto-find the main port
- **Delta-based sync** — clients send only changed fields, not full state
- **Client types** via query param: `?client=spicetify`, `?client=website`, `?client=obs`
- **`/api/state` HTTP endpoint** — returns full Spotify state as JSON with pre-formatted `progressFmt`/`durationFmt` (mm:ss). Used by Streamer.bot display commands; no WebSocket needed.
- **Commands from web/deck go ONLY to spicetify client** (targeted broadcast)
- **Debounced state saves** (2s inactivity) to avoid disk thrashing
- **Client-side color extraction** from album art via Canvas API (no server-side processing)
- **Profanity filter** uses base64-encoded word list to avoid GitHub content moderation flags
- **Queue URI normalization** — `parse_track_input()` in `state.py` converts Spotify URLs (including `intl-xx/` variant) and bare URIs to `spotify:track:xxx` format
- **Queue rate limiting** — per-requester 30s cooldown, configurable via `queueRateLimitSeconds`
- **Queue polling** — extension polls `Spicetify.Queue` every 2s, sends `queueSnapshot` to server, server matches URIs against `pendingQueueMeta` to inject `requestedBy`
- **OBS Up Next transition** — when current track has ≤15s remaining, OBS widget fades out current info and shows next queued track's details

### State Shape (state.py)

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

### Message Types

| Type | Direction | Purpose |
|---|---|---|
| `register` | Client→Server | Register client type |
| `getInitialState` | Client→Server | Request full state dump |
| `stateUpdate` | Spicetify→Server | Full snapshot on connect |
| `volumeUpdate` | Any→Server | Volume change (absolute or command) |
| `playbackUpdate` | Spicetify→Server | Play/pause/progress change |
| `shuffleUpdate` | Spicetify→Server | Shuffle toggle |
| `repeatUpdate` | Spicetify→Server | Repeat mode change (0/1/2) |
| `likeUpdate` | Spicetify→Server | Heart/like status |
| `trackUpdate` | Spicetify→Server | New track info (triggers lyrics fetch) |
| `progressUpdate` | Spicetify→Server | Progress sync |
| `playbackControl` | Any→Server | Command routed to spicetify only |
| `like` | Any→Server | Like command shortcut |
| `lyricsUpdate` | Server→Clients | Lyrics data push |
| `queueSnapshot` | Spicetify→Server | Queue state from extension polling |
| `addToQueue` | Any→Server | Add track (routed to spicetify) |
| `removeFromQueue` | Any→Server | Remove track (routed to spicetify) |
| `clearQueue` | Any→Server | Clear queue (routed to spicetify) |
| `queueUpdate` | Server→Clients | Queue state broadcast |
| `error` | Any→Server/Client | Error relay |

---

## Conventions

### Python
- **No bare `except:`** — always catch specific exceptions
- **Async handlers** — all message handlers are `async def`
- **Global state** — `state` dict is module-level (fine for single-threaded asyncio)
- **Import order** — stdlib, third-party, local (enforced by ruff `I` rule)
- **Line length** — 120 chars (ruff config)
- **No f-string without placeholders** — ruff catches this

### JavaScript
- **No framework** — vanilla JS, no build step for web files
- **WebSocket reconnect** — exponential backoff (1s → 10s max)
- **Event listener cleanup** — store references, remove on disconnect (fixed in remoteVolume.js)
- **onload before src** — always set `img.onload` before `img.src` to catch cached images
- **Marquee** — CSS `::after` pseudo-element with `data-text` attribute, not JS animation

### Shared
- **`filter.js`** lives in `web/` — both website and OBS widget reference it (website: relative `filter.js`, OBS: absolute `/filter.js`)
- **Art URL conversion** — `spotify:image:` → `https://i.scdn.co/image/` (handled in remoteVolume.js `getAlbumArtUrl()`)

---

> **Running the server, tests, linting, Stream Deck build, and release workflow → see [CONTRIBUTING.md](CONTRIBUTING.md)**

---

## Important Gotchas

1. **`websockets` in requirements.txt was a dead dependency** — removed. aiohttp handles all WebSocket traffic.
2. **`exposeGlobals()` in remoteVolume.js was dead code** — removed.
3. **CORS `Access-Control-Allow-Origin`** only accepts ONE origin or `*`. The old code joined multiple origins with commas which is invalid. Fixed to match request Origin against allowlist.
4. **Event listener accumulation** — Spicetify extension used to add duplicate listeners on every reconnect. Fixed by storing references and removing on disconnect.
5. **`socket.setdefaulttimeout(60)`** in service.py set a global timeout affecting the child server process. Removed.
6. **`input()` hang** in elevated service.py — replaced with 10s auto-close timeout.
7. **`albumArt.onload` race** — handler was set AFTER `src`, so cached images would miss the event. Fixed by setting handler first.
8. **Volume validation** — absolute volume values were not clamped. Fixed to `max(0.0, min(1.0, value))`.
9. **Profanity filter base64** — NOT security through obscurity. It's to avoid GitHub's automated content moderation flagging repos with slur lists in plaintext.
10. **`conftest.py`** adds `server/` to `sys.path` so `import server` works in tests.
11. **`pyproject.toml`** has `asyncio_mode = "auto"` so async tests don't need `@pytest.mark.asyncio`.
12. **Stream Deck plugin source** is in `streamdeck-plugin/` — the `.streamDeckPlugin` file in root is the pre-built package.

13. **Server split into modules** — `server/server.py` was split into `config.py`, `log.py`, `state.py`, `broadcast.py`, `lyrics.py`, `handlers.py`, `routes.py`. All symbols are re-exported through `server.py` so `import server` and `server.state`, `server.broadcast`, etc. still work in tests.

14. **Lazy import for LYRICS_CACHE_DB** — `lyrics.py` uses a `_get_db_path()` helper that does `from server import LYRICS_CACHE_DB` at call time (not module level). This avoids circular imports and allows tests to `patch.object(server, "LYRICS_CACHE_DB", ...)`.

15. **`_write_state_to_disk` lives in server.py** because tests patch `server.STATE_FILE`. Kept in the entry-point module so the patched value is read by the write function.

16. **Callback pattern for state saves** — `state.py` exposes `set_write_callback()` so `server.py` can register `_write_state_to_disk`. This breaks the circular dependency between `state.py` and `server.py`.

17. **Discovery fetch uses fixed 1s retry** — `fetchServerConfig()` in `remoteVolume.js` retries every 1s instead of using the exponential WebSocket backoff. This prevents long waits when the server starts shortly after the extension.

18. **`Spicetify.Queue.nextTracks[i]` wraps ContextTrack**: real structure is `{contextTrack: {uri, uid, metadata}, removed, blocked, provider}`, NOT a flat `{uri, uid, metadata}`. Always use `item.contextTrack.uri`.

19. **`queueRevision` is BigInt**: must `String()` it before JSON serialization and before comparison with stored state.

20. **`nextTracks` includes ALL upcoming tracks**: playlist context + user-requested + pre-fetched autoplay recommendations. Queue-full check must use `pendingQueueMeta.length`, not `nextTracks.length`.

21. **`spotify:delimiter` items**: filter out items with `uri === "spotify:delimiter"`.

22. **`metadata.image_url` is `spotify:image:xxx`**: convert to `https://i.scdn.co/image/` + id before sending to clients.

23. **URI normalization**: users may input `https://open.spotify.com/track/xxx` but snapshot URIs are `spotify:track:xxx`. Normalize both pending metadata and stored URIs with `parse_track_input()`.

24. **Startup timing**: `Spicetify.Player.getVolume/getShuffle/getRepeat/getHeart/getProgress/getDuration` all throw TypeError when internal webpack modules haven't loaded yet. Wrap ALL getters in try/catch (`_safeGet` helper).

25. **Metadata fallback chain**: queue items may have track info in `metadata.title` or `track.name` (top-level). Try `meta.title || t.name || ""`.

26. **Artist fallback chain**: `meta.artist_name` or `t.artists?.[0]?.name || ""`.

27. **Image fallback chain**: `meta.image_url || meta.image_small_url || meta.image_large_url || (t.album?.images?.[0]?.url) || ""`.

---

## Testing Strategy

- **Don't test frontend** — runs in browser/Spotify, painful to mock
- **Don't test full server lifecycle** — requires integration tests, overkill
- **DO test** — message handlers, input validation, broadcasting, config endpoint, lyrics cache, queue handlers, rate limiting, HTTP endpoints, pure functions
- **State isolation** — `reset_state` fixture runs before every test
- **Mock broadcasts** — patch `broadcast_*` functions to avoid needing real WebSocket connections

---

## Security Model

- **No authentication** — by design, localhost-only
- **CORS** — configurable via `allowedOrigins` in config.json
- **Input validation** — JSON parse errors, type checks, unknown message types all handled gracefully
- **Do not expose to internet** without reverse proxy + auth layer

---

## What to Do When Adding Features

1. **New message type** → add to `MESSAGE_HANDLERS` dict in `handlers.py`, add handler function, update client(s)
2. **New state field** → add to `state` dict in `state.py`, update `broadcast_current_state` in `broadcast.py`, update `get_current_save_data` in `state.py`, update `handle_track_update` in `handlers.py` if it should persist
3. **New web UI element** → add to HTML, add to `ui` object in script.js, wire up event listener
4. **New OBS widget feature** → same pattern but in obs-widget/ files
5. **Always** → add tests for new handlers in `test_server.py`, run `ruff check`, run `pytest`

---

## Queue System Architecture

Native Spotify approach: viewers request songs → server forwards to extension → extension calls `Spicetify.addToQueue()` → extension polls `Spicetify.Queue.nextTracks` and mirrors to server → server broadcasts to clients. Queue-full check uses `pendingQueueMeta.length` (not `nextTracks.length`). `requestedBy` is matched via URI against pending metadata in FIFO order.
