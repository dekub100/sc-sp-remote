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
33. **SoundCloud state fields prefixed with `sc*`** — `scTrack`, `scArtist`, `scAlbum`, `scId`, `scCoverUrl`, `scIsPlaying`, `scProgressMs`, `scDurationMs`, `scVolume`, `scIsLiked`.
34. **`broadcast_spotify_state` and `broadcast_soundcloud_state` are separate** — not a single `broadcast_current_state` like main. Each source broadcasts its own shape.
35. **`handle_client_log`** — SC plugin logs via WebSocket `clientLog` messages (SC can't access DevTools).
36. **Extension reconnection** — uses `_connecting` flag to prevent re-entrant `connect()` calls. Max 10 reconnect attempts before giving up.
37. **CLI unified in `manage.py`** — `tools/` (dev.py, install.py, service.py) deleted; all entry points are subcommands (`run`/`dev`/`install`/`service`). Old `tools/dev.py` set env var `SC_REMOTE_CONFIG`, but the server reads `SC_SP_REMOTE_CONFIG` — dev port isolation was silently broken; manage.py uses the correct name.
38. **pywin32 service class must be module-level** — SCM's service host imports `manage.py` and resolves class string `manage.ScSpRemoteService`. A factory function returning the class breaks service start while install/restart still print success. Also: `HandleCommandLine()` parses `sys.argv`, so pass `argv=[sys.argv[0], action]` or the subcommand name confuses it.
