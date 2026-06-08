# SC-Spotify-Remote — Project Knowledge

## What This Is

A dual-source remote control app for Spotify (via Spicetify) and SoundCloud (via soundcloud-rpc). Forked/adapted from [spicetify-remote](https://github.com/dekub100/spicetify-remote).

## Architecture

Hub-and-spoke WebSocket model. Python server is the single point of truth.

```
Spicetify Extension ──WS──► Python Server (port 8889) ◄──WS── SoundCloud Plugin
                                    │
                              Web UI (browser)
```

- **Single port** (8889) for HTTP + WebSocket
- **Client types** via query param: `?client=spicetify|soundcloud|website|obs`
- **Targeted broadcast**: commands go ONLY to the target client type
- **State is flat**: all keys in one `state` dict, SC keys prefixed with `sc*`

## Files

### Python Server (`server/`)
| File | Role |
|------|------|
| `server.py` | Entry point, route registration, main() |
| `config.py` | Paths, config loading, CONFIG_FIELD_TYPES |
| `state.py` | State dict, debounced saves, URI normalization, rate limiting |
| `broadcast.py` | CLIENTS dict, broadcast functions, progress interpolation |
| `handlers.py` | Message handlers + dispatch table (20+ message types) |
| `routes.py` | WebSocket upgrade, HTTP endpoints, CORS |
| `lyrics.py` | LRCLIB fetcher, SQLite cache, LRC parser |
| `log.py` | Session-based logging, rotation |

### JavaScript
| File | Role |
|------|------|
| `spicetify-extension/remoteVolume.js` | Runs inside Spotify via Spicetify. Polls Spicetify API 500ms. Sends delta-based state. |
| `soundcloud-plugin/soundcloud-remote-bridge.js` | soundcloud-rpc plugin. Injected into SC page. DOM manipulation + WebSocket to server. |
| `web/script.js` | Web UI. Dual-source tabs, interpolation, lyrics, queue. |

## Message Types

### Spotify (Spicetify → Server)
`stateUpdate`, `trackUpdate`, `volumeUpdate`, `playbackUpdate`, `shuffleUpdate`, `repeatUpdate`, `likeUpdate`, `progressUpdate`, `queueSnapshot`

### SoundCloud (Plugin → Server)
`scStateUpdate` — track, artist, coverUrl, isPlaying, progressMs, durationMs, volume

### Commands (Web UI → Server → Target)
- `playbackControl` → target: `spicetify`
- `scPlaybackControl` → target: `soundcloud`
- `scVolumeUpdate` → server updates state + broadcasts to SC plugin

### Cross-source
`setActiveSource` — switches which player is "active"
`activeSourceUpdate` — broadcast to all clients

## State Shape (state.py)

```python
state = {
    # Spotify
    "volume": 0.5, "isPlaying": False,
    "currentTrack": {"trackName", "artistName", "albumName", "trackUri", "albumUri", "albumArtUrl"},
    "trackProgress": 0, "trackDuration": 0, "trackProgressStartTimestamp": 0,
    "isShuffling": False, "repeatStatus": 0, "isLiked": False,
    "lyrics": {...}, "queue": {...},
    # SoundCloud
    "scTrack", "scArtist", "scAlbum", "scId", "scCoverUrl",
    "scIsPlaying": False, "scProgressMs": 0, "scDurationMs": 0,
    "scVolume": 0.5, "scIsLiked": False, "scQueue": [],
    # Cross-source
    "activeSource": "spotify",
}
```

## Known Bug (Fixed)

**Spotify progress jumps when SC is connected**: `handle_sc_state_update` was overwriting `state["trackProgressStartTimestamp"]` every 500ms. This timestamp is used by Spotify's progress interpolation. Fix: removed that line from the SC handler. SC should never touch `trackProgressStartTimestamp`.

## SoundCloud Plugin Selectors

From soundcloud-rpc's `audioMonitorService.ts`:

| Element | Selector |
|---------|----------|
| Play state | `.playControls__play` (check `.playing` class) |
| Click play | `.playControl` |
| Next | `.skipControl__next` |
| Previous | `.skipControl__previous` |
| Artist | `.playbackSoundBadge__lightLink` |
| Artwork | `.playbackSoundBadge__avatar .image__lightOutline span` (read `aria-label` + `style.backgroundImage`) |
| Like | `.playbackSoundBadge button.sc-button-like` |
| Elapsed | `.playbackTimeline__timePassed span:last-child` |
| Duration | `.playbackTimeline__duration span:last-child` |
| Track URL | `.playbackSoundBadge__titleLink` |
| Audio | `audio` |

**Title** comes from artwork element's `aria-label`, not a separate title element.

## SoundCloud Plugin Logging

The SC plugin can't access DevTools (Electron has it disabled). Logs are sent to the Python server via `clientLog` message type and appear in the terminal prefixed with `[soundcloud]`.

## Spotify Progress Interpolation

Uses `trackProgressStartTimestamp` as anchor. When playing, `interpolateProgress()` calculates:
```
currentProgress = progress + (Date.now() - timestamp)
```

The web UI uses `Date.now()` as anchor (not server timestamp) to avoid clock skew.

## Config (data/config.json)

Key fields:
- `port`: 8889
- `spicetifyPollingIntervalMs`: 500
- `soundcloudPollingIntervalMs`: 500
- `lyricsFetchTimeoutSeconds`: 15

## Conventions

- **No bare except** — always catch specific exceptions
- **Async handlers** — all message handlers are `async def`
- **Line length** — 120 chars (ruff)
- **No frameworks** — vanilla JS, no build step
- **Filter profanity** — base64-encoded word list in `web/filter.js`

## Dependencies

- Python: `aiohttp>=3.9.0,<4.0.0` only
- No SoundCloud API needed — plugin reads DOM directly
- Requires: Spotify + Spicetify, soundcloud-rpc

## To Run

```bash
pip install aiohttp
python server/server.py
# Open http://localhost:8889
```

## To Install Extensions

```bash
python tools/install.py spicetify    # Copies to %APPDATA%/spicetify/Extensions/
python tools/install.py soundcloud   # Copies to %APPDATA%/soundcloud-rpc/plugins/
```

Restart soundcloud-rpc after installing the plugin.
