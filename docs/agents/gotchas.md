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
12. **Stream Deck plugin source** in `streamdeck-plugin/` — `.streamDeckPlugin` in root is the pre-built package.
13. **Server symbols re-exported** through `server.py` — tests use `import server; server.state` etc.
14. **Lazy import for LYRICS_CACHE_DB** — `lyrics.py` uses a `_get_db_path()` helper to avoid circular imports.
15. **`_write_state_to_disk` lives in `server.py`** — tests patch `server.STATE_FILE`.
16. **Callback pattern for state saves** — `state.py` exposes `set_write_callback()` to break circular deps.
17. **Discovery fetch uses fixed 1s retry** — `fetchServerConfig()` in `remoteVolume.js` retries every 1s (not exponential backoff). Prevents long waits when server starts shortly after extension.
18. **`Spicetify.Queue.nextTracks[i]` wraps ContextTrack**: use `item.contextTrack.uri`, not flat `uri`.
19. **`queueRevision` is BigInt** — `String()` it before JSON serialization.
20. **`nextTracks` includes all upcoming**: full context + requested + autoplay. Use `pendingQueueMeta.length` for full check.
21. **Filter `spotify:delimiter`** items from queue.
22. **Convert `metadata.image_url`** from `spotify:image:xxx` to `https://i.scdn.co/image/` + id.
23. **URI normalization**: `parse_track_input()` handles URLs, URIs, intl-xx/ variants.
24. **Startup timing**: Spicetify getters throw TypeError before webpack loads — wrap in try/catch (`_safeGet`).
25. **Metadata fallback**: `meta.title || t.name || ""`.
26. **Artist fallback**: `meta.artist_name || t.artists?.[0]?.name || ""`.
27. **Image fallback**: `meta.image_url || meta.image_small_url || meta.image_large_url || (t.album?.images?.[0]?.url) || ""`.
28. **CORS non-match** should omit header entirely, not fall back to `origins[0]`.
29. **SQLite connection reuse**: module-level persistent connection via `_get_conn()`, auto-reconnects if path changes.
30. **Admin config PUT validates types** — returns specific error messages, not silently storing garbage.
31. **`host` config field**: server bind address configurable via `config.json` (`"host": "127.0.0.1"` default). Previously hardcoded to `0.0.0.0`.
32. **`tools/install.py` auto-patches port** — reads `config.json` and regex-replaces `DEFAULT_PORT`.
33. **Stream Deck PI registration** uses `uuid: inUUID` (not `context: uuid`).
34. **Stream Deck global port** via `setGlobalSettings` — shared across action instances.
35. **`SPICETIFY_CONFIG` env var** overrides config path. Used by `tools/dev.py`.
