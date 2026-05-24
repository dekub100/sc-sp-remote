# Development Workflow

## Commit Workflow

When asked to commit, push, create a PR, or update release artifacts, first read [CONTRIBUTING.md](../../CONTRIBUTING.md) for the project's conventions.

## Dev Server

```
python tools/dev.py                        # Port 8889 with auto-reload
python tools/dev.py --port 7777            # Custom port
python tools/dev.py --no-reload            # No file watcher
```

Dev tool auto-patches extension, auto-restores on exit, writes isolated `config.dev.json`.

## Adding Features

1. **New message type** → add to `MESSAGE_HANDLERS` in `handlers.py`, add handler, update client(s)
2. **New state field** → add to `state` in `state.py`, update `broadcast_current_state`, `get_current_save_data`, `handle_state_update`
3. **New web UI element** → HTML + `ui` object in `script.js` + event listener
4. **New OBS widget feature** → same pattern in `obs-widget/` files
5. **Always** → add tests in `test_server.py`, run `ruff check`, run `pytest`

## Testing Strategy

- Don't test frontend (browser/Spotify, painful to mock)
- Don't test full server lifecycle
- DO test: message handlers, input validation, broadcasting, config, lyrics cache, queue handlers, rate limiting, HTTP endpoints, pure functions
- `reset_state` fixture runs before every test
- Mock `broadcast_*` functions to avoid real WebSocket connections

## Security Model

- **No authentication** — by design, localhost-only. No user accounts, no PII, no cloud secrets.
- **Threat model** — LAN attacker sees now-playing and can skip/pause. Annoying but not sensitive. Admin API (`/api/admin/config`) is localhost-only by default.
- **Input validation** — JSON parse errors, type checks, unknown message types all handled gracefully.
- **CORS** — configurable via `allowedOrigins`, default `*`.
- **Auth not worth implementing** for localhost use case. Would require changes to 4+ client types with reconnect handling — ~80 lines for marginal security gain on a tool that already binds to localhost by default. Queue-adding from chat is handled via Streamer.bot → localhost HTTP API.
- Do not expose to internet without a reverse proxy with auth.
