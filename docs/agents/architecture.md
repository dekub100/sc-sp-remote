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
- **Full-snapshot state** — every `nowPlaying` carries the whole source snapshot (the SoundCloud 500 ms heartbeat is change-gated by a fingerprint, so unchanged heartbeats are not rebroadcast); the 1 Hz `progress` message carries only position/duration/playing/timestamp
- **Client types** via query param (`?client=spicetify|soundcloud|website|obs|streamdeck`) + required `protocolVersion=2`
- **Protocol v2** — every message is `{"v":2,"type":...,"source":...,"state":{...}}`; source clients push `nowPlaying`/`volume`/`playback`/`progress`/`shuffle`/`repeat`/`like`, controllers send one `command`, and `protocol.py` enforces the per-role allowlist before a handler runs
- **Targeted broadcast** — commands go ONLY to the target source client type (`target_type` in `broadcast()`); the sender is always excluded
- **Dual-file state** — `state_spotify.json` + `state_soundcloud.json` (separate save flows driven by the `SOURCES` descriptor; flat `state` keys stay unchanged)
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

## Wire Protocol (v2)

Every frame is a JSON object with `v: 2`, `type`, and (for per-source messages) `source`.
State lives under `state`; a source's `nowPlaying` is a full snapshot, the partial
updates from a source contain only the fields that changed. A connection whose
`protocolVersion` query param is below 2 is sent an `error` (`code: "protocol_version"`)
and closed with 1002.

| Type | Direction | Allowed sender | Purpose |
|---|---|---|---|
| `config` | Server→Client | — | Per-client intervals, sent once on connect |
| `nowPlaying` | Source→Server | `spicetify`, `soundcloud` | Partial/full source snapshot (`track*`, `isPlaying`, `progress`, `duration`, `volume`, `isLiked`, `isShuffling`, `repeatStatus`) |
| `volume` | Source→Server | `spicetify`, `soundcloud` | `state:{volume}` |
| `playback` | Source→Server | `spicetify`, `soundcloud` | `state:{isPlaying, progress}` |
| `progress` | Source→Server | `spicetify`, `soundcloud` | `state:{progress, duration}` |
| `shuffle` / `repeat` / `like` | Source→Server | `spicetify`, `soundcloud` | `state:{isShuffling}` / `{repeatStatus}` / `{isLiked}` |
| `command` | Controller→Server→Source | `website`, `obs`, `streamdeck` | `command` + `source`; server whitelists args and forwards to that source only |
| `getInitialState` | Controller→Server | `website`, `obs`, `streamdeck` | Ask for the full snapshot (also sent automatically on connect) |
| `nowPlaying` | Server→Controllers | — | Full snapshot for one source |
| `progress` | Server→All | — | `state:{progress, duration, isPlaying, timestamp}` (1 Hz while playing) |
| `lyrics` | Server→All | — | `state:{synced, plain, karaoke, provider, loading, ...}` |
| `sourceStatus` | Server→All | — | `state:{connected}` — a source controller attached/detached (never means "paused") |
| `clientLog` | Any→Server | all | Client-side log line (useful for SC, which has no DevTools) |
| `error` | Both | — | `{code, message}`; violations never mutate state |

Commands: `play`, `pause`, `togglePlay`, `next`, `previous`, `seek` (`position`),
`seekForward`/`seekBack` (`offset`), `toggleShuffle`, `toggleRepeat`, `like`,
`volumeUp`/`volumeDown` (`step`), `setVolume` (`volume`). The vocabulary and the
per-role allowlist live in `server/protocol.py`.

`/api/state` is unchanged: it still returns the flat `spotify`/`soundcloud` blocks
(Streamer.bot templates depend on those key names).


