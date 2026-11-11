# Development Workflow

## Commit Workflow

When asked to commit, push, create a PR, or update release artifacts, first read [CONTRIBUTING.md](../../CONTRIBUTING.md) for the project's conventions.

## Dev Server

```
python manage.py dev                        # Port 8888 with auto-reload
python manage.py dev --port 7777            # Custom port
python manage.py dev --no-reload            # No file watcher
```

Dev tool isolates both its config (`data/dev/config.dev.json`) and all runtime data (`data/dev/` state, logs, lyrics cache — via `SC_SP_REMOTE_DATA_DIR`), so it can run next to a production service. The extension reads host/port from localStorage via the in-app Remote Config menu — no file patching needed.

## Adding Features

1. **New message type** → add to `MESSAGE_HANDLERS` in `handlers.py`, add it to the right role in `protocol.py` (`SOURCE_MESSAGE_TYPES` / `CONTROLLER_MESSAGE_TYPES`), add the handler, bump `PROTOCOL_VERSION` if the frame shape changes, update all clients, and add a permission test
2. **New state field** → declare it in `SOURCES` in `state.py` (`defaults`, plus `persisted` or `runtime`, and an `update_fields` entry if clients may push it), then add it to the `nowPlaying` snapshot in `broadcast.py` and to clients. The descriptor test fails if a state key is unclassified.
3. **New web UI element** → HTML + `ui` object in `script.js` + event listener
4. **New OBS widget feature** → same pattern in `obs-widget/` files
5. **Always** → add tests in `test_server.py`, run `ruff check`, run `pytest`

## SoundCloud-Specific Notes

- State fields use `sc*` prefix — never overwrite non-SC fields in SC handlers (esp. `trackProgressStartTimestamp`)
- SoundCloud plugin is a DOM-injection script for soundcloud-rpc, has no DevTools access — logs via WebSocket `clientLog` messages
- Extension messages carry `source: "spotify"` for dual-source routing on the server
- Use `broadcast_spotify_state()` / `broadcast_soundcloud_state()` — NOT a unified `broadcast_current_state()`

## Testing Strategy

- Don't test DOM rendering (browser/Spotify, painful to mock) — DO test the DOM-free helpers: `web/tests/lib.test.js` runs `lib.js`/`filter.js` in a VM with `node --test` (CI job `web-tests`)
- DO test: message handlers, inbound validation, broadcasting/backpressure, config, lyrics cache, HTTP endpoints, the WS lifecycle (`TestWebSocketLifecycle`, `TestStreamDeckClient`)
- The autouse `reset_state` fixture calls `reset_source_state()` for both sources, restoring `SOURCES[...].defaults`
- Mock `broadcast_*` functions to avoid real WebSocket connections; use real `TestClient`/`TestServer` sockets for lifecycle tests
- Prefer real sockets over mocks for anything that depends on connect/disconnect ordering
- Beware: `await` inside the websocket handler's `finally` is cancelled when the client disconnects — use a detached task (see `_spawn_source_disconnect`)

## Security Model

- **No authentication** — by design, localhost-only. No user accounts, no PII.
- **Threat model** — LAN attacker sees now-playing and can skip/pause. Annoying but not sensitive. Everything is gated by `security_middleware` in `routes.py`:
  - **Host allowlist** — `Host` must be `localhost`, a loopback/private IP literal, the configured `host`, or an entry in `allowedHosts`. This blocks DNS rebinding (a rebound attacker domain arrives with its own name in `Host`).
  - **CSRF** — state-changing requests (`POST`/`PUT`/`PATCH`/`DELETE`) are refused when `Origin` is cross-origin or `Sec-Fetch-Site: cross-site`. Native clients send no `Origin` and are allowed.
  - **Admin is loopback-only** — `/api/admin/*` refuses peers whose `request.remote` is not a loopback address, even when the server is bound to a LAN address. LAN users get the web UI, OBS widget and WS commands; config editing stays on the machine.
  - `GET /api/admin/config` still redacts `musixmatchToken`.
- **CORS** — configurable via `allowedOrigins`, default explicit localhost origins (`http://localhost:8888`, `http://127.0.0.1:8888`). It only grants browser read access to `/api/config` and admin responses; `/api/state` sends no CORS header. `"*"` is still honored for CORS if explicitly set, but **never** for the WebSocket gate.
- **WebSocket origin gate** — WS handshakes ignore CORS entirely, so a malicious website could open `ws://localhost:8888` from the visitor's browser. `_is_foreign_web_origin()` allowlists browser origins (localhost, `xpui.app.spotify.com`, `soundcloud.com`) plus same-origin (netloc vs `Host`, so a LAN IP works); anything else gets 403. Native clients that send no Origin header pass.
- **XSS** — lyric text comes from third-party APIs (Musixmatch/LRCLIB) and MUST go through `escapeHtml` before any `innerHTML` interpolation. `lib.js` is the single implementation (quote-escaping included) and the OBS widget loads it too.
- **Input validation** — `handlers.py` coerces every inbound state field (`_ms`, `_volume`, `_bool`, `_repeat`, `_text`) and ignores invalid values. `get_interpolated_*` / `as_ms` / `as_volume` in `state.py` are the last line of defence so one bad payload can't 500 `/api/state`.
- **Bind fallback** — `server.py` falls back to `127.0.0.1` when `host` can't be read from config.
- **Auth not worth implementing** for the localhost use case. Chat-driven actions are handled via Streamer.bot → localhost HTTP API.
- Do not expose to internet without a reverse proxy with auth.
