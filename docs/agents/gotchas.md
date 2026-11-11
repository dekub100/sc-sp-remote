# Important Gotchas

1. **`websockets` in requirements.txt was dead** — removed. aiohttp handles all WebSocket traffic.
2. **`exposeGlobals()` in remoteVolume.js was dead code** — removed.
3. **CORS `Access-Control-Allow-Origin`** only accepts ONE origin or `*`. Match request Origin against allowlist; don't join.
4. **Event listener accumulation** in Spicetify extension — store references, remove on disconnect.
5. **`socket.setdefaulttimeout(60)` in service.py** — set a global timeout affecting the child server. Removed.
6. **`input()` hang** in elevated service.py — replaced with 10s auto-close timeout.
7. **`albumArt.onload` race** — set handler BEFORE `src` (cached images fire synchronously).
8. **Volume validation** — clamp to `max(0.0, min(1.0, value))`.
9. **Profanity filter base64** — two reasons: (a) protects streamers from accidentally displaying slurs in lyrics on stream/OBS, (b) avoids GitHub's automated content moderation flagging the repo for having a slur list in plaintext. NOT security through obscurity — trivially decoded in the browser.
10. **`conftest.py`** adds `server/` to `sys.path` for `import server`.
11. **`pyproject.toml`** has `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed.
12. **Stream Deck plugin source** in `streamdeck-plugin/` — build with `npm run build` then pack with `@elgato/cli`.
13. **Tests import submodules directly** — server.py no longer re-exports submodule symbols. Tests that need broadcast, handlers, etc. import from the owning module (`from broadcast import ...`), not via `server.*`.
14. **Spotify state writes** via `_write_spotify_state_to_disk` and `_write_sc_state_to_disk` in `server.py` — tested directly.
15. **Callback pattern for state saves** — `state.py` exposes `set_spotify_write_callback()` / `set_sc_write_callback()` to break circular deps.
16. **Convert `metadata.image_url`** from `spotify:image:xxx` to `https://i.scdn.co/image/` + id.
17. **Startup timing**: Spicetify getters throw TypeError before webpack loads — wrap in try/catch (`_safeGet`).
18. **Metadata fallback**: `meta.title || t.name || ""`.
19. **Artist fallback**: `meta.artist_name || t.artists?.[0]?.name || ""`.
20. **Image fallback**: `meta.image_url || meta.image_small_url || meta.image_large_url || (t.album?.images?.[0]?.url) || ""`.
21. **CORS non-match** should omit header entirely, not fall back to `origins[0]`.
22. **SQLite connection reuse**: module-level persistent connection via `_get_conn()`, auto-reconnects if path changes.
23. **Admin config PUT validates types** — returns specific error messages, not silently storing garbage.
24. **`host` config field**: server bind address configurable via `config.json` (`"host": "127.0.0.1"` default). Previously hardcoded to `0.0.0.0`.
25. **Extension reads host/port from localStorage** — users configure via Spotify's profile menu (Remote Config). Key: `sc-sp-remote:config`.
26. **Stream Deck PI registration** uses `uuid: inUUID` (not `context: uuid`).
27. **Stream Deck global port** via `setGlobalSettings` — shared across action instances.
28. **`SC_SP_REMOTE_CONFIG` env var** overrides config path.
29. **Dual-file state** — SC uses `state_spotify.json` + `state_soundcloud.json` instead of main's single `state.json`. Each has its own save callback and debounced timer.
30. **Port 8888** — single port for HTTP + WebSocket.
31. **`source: "spotify"`** in extension messages — allows server to route dual-source traffic. Added to all Spotify-origin messages.
32. **`handle_message` crash handler does NOT close WS** — avoids infinite reconnect loop. Extension has `_connecting` guard + `MAX_RECONNECT_ATTEMPTS` (10) + 1011 close-code special case.
33. **SoundCloud state fields prefixed with `sc*`** — `scTrack`, `scArtist`, `scAlbum`, `scId`, `scCoverUrl`, `scIsPlaying`, `scProgressMs`, `scDurationMs`, `scProgressStartTimestamp`, `scVolume`, `scIsLiked`, `scIsShuffling`, `scRepeatStatus`. Wire messages use canonical `progress`/`duration` for both sources.
34. **`broadcast_spotify_state` and `broadcast_soundcloud_state` are separate** — not a single `broadcast_current_state` like main. Each source broadcasts its own shape.
35. **`handle_client_log`** — SC plugin logs via WebSocket `clientLog` messages (SC can't access DevTools).
36. **Extension reconnection** — uses `_connecting` flag to prevent re-entrant `connect()` calls. Max 10 reconnect attempts before giving up.
37. **CLI unified in `manage.py`** — `tools/` (dev.py, install.py, service.py) deleted; all entry points are subcommands (`run`/`dev`/`install`/`service`). Old `tools/dev.py` set env var `SC_REMOTE_CONFIG`, but the server reads `SC_SP_REMOTE_CONFIG` — dev port isolation was silently broken; manage.py uses the correct name.
38. **pywin32 service class must be module-level** — SCM's service host imports `manage.py` and resolves class string `manage.ScSpRemoteService`. A factory function returning the class breaks service start while install/restart still print success. Also: `HandleCommandLine()` parses `sys.argv`, so pass `argv=[sys.argv[0], action]` or the subcommand name confuses it.
39. **Runtime config is untracked** — `data/config.default.json` holds the shipped defaults; `data/config.json` is created on first run and gitignored. The auto-fetched Musixmatch token and admin-panel edits land there, never in git. Change shipped defaults in both `server/config.py` (`CODE_DEFAULTS`) and `data/config.default.json` (test-enforced).
40. **Musixmatch token is reactive-only refresh** — no proactive expiry check; `_mxm_get` retries once on 401/auth-failure with a fresh token, then falls through to the next provider in `lyricsProviderOrder`. Manual override: admin endpoint or `python manage.py musixmatch-token`.
41. **Browser clients DO send http(s) Origin headers** — Spicetify's CEF shell sends `https://xpui.app.spotify.com`, the SoundCloud tab sends `https://soundcloud.com`. Don't assume extension/embedded = no Origin. The WS gate (`_is_foreign_web_origin` in routes.py) accepts same-origin netloc matches (so the web UI works on a LAN bind), then the fixed allowlist (`_ALLOWED_WS_ORIGIN_HOSTS`); anything else gets 403, and `allowedOrigins: ["*"]` does not open it.
42. **Admin UI never displays musixmatchToken** — its Refresh button hits `/api/admin/lyrics/musixmatch-token` (preview only). `GET /api/admin/config` deliberately redacts the token; don't "fix" it back to returning full config.
43. **Host fallback is `127.0.0.1`, not `0.0.0.0`** — server.py's fallback when config can't be read must stay localhost-only.
44. **Third-party lyric text → always `escapeHtml()` before innerHTML** — lyrics come from Musixmatch/LRCLIB over the network; a malicious API response is an XSS vector. `filterText()` is the profanity filter, NOT a sanitizer.
45. **`await` in the WebSocket handler's `finally` is cancelled** — aiohttp tears down the handler when the client disconnects, so the sleep/broadcast never completes. Disconnect bookkeeping runs in a detached task (`_spawn_source_disconnect`), kept alive by `routes._disconnect_tasks`.
46. **A slow WS client must not block a broadcast** — `broadcast.py` wraps every `send_str` in `asyncio.wait_for(BROADCAST_SEND_TIMEOUT_SECONDS)` and drops the client; without it one paused OBS source stalls the 1 Hz progress loop.
47. **Disconnect ≠ paused** — reconnects close the old socket after the new one registers. Pausing immediately stomps the fresh `syncFullState` and pauses the music, so the pause is delayed by `DISCONNECT_PAUSE_GRACE_SECONDS` and re-checked against `CLIENTS`.
48. **`Host` and `Origin` are checked in one middleware** (`security_middleware`), not per-route — the WS upgrade is a plain GET, so route-level checks would miss it. `/api/admin/*` additionally requires a loopback peer.
49. **`"*"` in `allowedOrigins` opens CORS only, never the WebSocket gate** — otherwise any website could drive playback.
50. **Every state key must be declared in `SOURCES`** (`server/state.py`) as either `persisted` or `runtime`. The old per-source read/save/broadcast/interpolate helpers now derive from that table; `TestSourceDescriptor` fails if a key is unclassified. Flat `state["sc*"]` keys are unchanged on purpose.
51. **Wire v2 is a hard break** — clients must connect with `protocolVersion=2` (lower versions get an `error` + close 1002). Source clients push `nowPlaying`/`volume`/`playback`/`progress`/`shuffle`/`repeat`/`like`; controllers send one `command`. The allowlist in `server/protocol.py` is checked before handlers run, so a controller can never push source state and a source can never send commands. `/api/state` is deliberately *not* versioned.
52. **`volumeUp`/`volumeDown` are commands, not source state** — the server never changes volume itself; it forwards the command (with `step`) to the owning source. Source clients only report absolute volume via `volume`/`nowPlaying`.
53. **A reconnecting source must not be marked disconnected** — `_pause_source_if_alone()` returns the paused source key or `None`, and `_handle_source_disconnect()` broadcasts nothing when a controller reconnected inside the grace window.
54. **State/config writes are atomic** — `config.write_json_atomic()` writes a `.tmp` file, fsyncs and `os.replace()`s it. A crash mid-write leaves the previous file intact; don't replace it with a bare `open(..., "w")`. Interactive `manage.py run`/`dev` children stay in the console process group so Ctrl+C reaches them and `server.py`'s stop handler runs the final save; only the Windows service uses a private group + CTRL_BREAK.
55. **Admin config validation mirrors the HTML form minimums** — `_CONFIG_MINIMUMS` in routes.py enforces `>= 0.1` / `>= 0.5` etc.; `port`/`host`/`backupCount` return `restartRequired` and everything else applies live.
56. **A restored "playing" source is reported paused** — `isPlaying` is persisted but the progress anchor is runtime-only. `read_source_state_from_file()` clears `isPlaying` when the anchor is missing; the source client's reconnect re-syncs the truth. Don't re-add an epoch-based anchor to "fix" the pause.
57. **Inbound WS frames are capped at 256 KB** (`MAX_WS_MESSAGE_BYTES` in routes.py) — snapshots are a few KB, so aiohttp's 4 MB default was unnecessary surface. Oversized frames close the socket with code 1009.
