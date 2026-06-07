# SC + Spotify Remote

![Version](https://img.shields.io/badge/version-1.5.5-blue.svg)
![Status](https://img.shields.io/badge/status-experimental-orange.svg)

**Experimental build** — extends spicetify-remote with SoundCloud support via soundcloud-rpc. Dual-source WebSocket server for controlling and viewing both Spotify (via Spicetify) and SoundCloud (via soundcloud-rpc).

## Requirements

- Python 3.9+
- [spicetify-cli](https://spicetify.app/docs/getting-started)
- [soundcloud-rpc](https://github.com/soundcloud-rpc/soundcloud-rpc) (for SoundCloud support)

## Quick Start

1. **Install the extensions** — `python tools/install.py`
2. **Start the server** — `python server/server.py`
3. Open the **web UI** at `http://localhost:8889/`

## Usage

| Page        | URL                           |
| ----------- | ----------------------------- |
| Web UI      | `http://localhost:8889/`      |
| Admin panel | `http://localhost:8889/admin` |
| OBS widget  | `http://localhost:8889/obs`   |

Configure the extension from Spotify's profile menu → **Remote Config** (set host/port at runtime).

## Configuration

Edit `data/config.json`. Key settings: `port` (default 8889), `host`, `enableOBS`, `enableWebsite`, `maxQueueSize`, `queueRateLimitSeconds`.

## Lyrics

Synced and plain lyrics are fetched from [LRCLIB](https://lrclib.net) and cached in a local SQLite database.

## Service Management

Run the server as a background service (Windows): [`docs/service.md`](docs/service.md)

## Security

No authentication. Designed for localhost-only use. Do not expose to the internet.

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, tests, linting, and release workflow.
