# Code Conventions

## Python
- **No bare `except:`** — always catch specific exceptions
- **Async handlers** — all message handlers are `async def`
- **Global state** — `state` dict is module-level (fine for single-threaded asyncio)
- **Import order** — stdlib, third-party, local (enforced by ruff `I` rule)
- **Line length** — 120 chars
- **No f-string without placeholders** — ruff catches this

## JavaScript
- **No framework** — vanilla JS, no build step for web files
- **WebSocket reconnect** — exponential backoff (1s → 10s max), max 10 attempts, guarded by `_connecting` flag
- **Event listener cleanup** — store references, remove on disconnect
- **onload before src** — always set `img.onload` before `img.src` to catch cached images
- **Marquee** — CSS `::after` pseudo-element with `data-text` attribute, not JS animation
- **Shared code** in `web/lib.js` (loaded before main script in both website and OBS widget)
- **Messages carry `source`** — all extension messages have `source: "spotify"` for dual-source routing

## Shared
- **`filter.js`** in `web/` — loaded via `src="/static/filter.js"` in both website and OBS widget
- **Art URL conversion** — `spotify:image:` → `https://i.scdn.co/image/` (in `remoteVolume.js`)
