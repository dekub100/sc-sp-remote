# sc-sp-remote

![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)

A dual-source remote control for Spotify (via Spicetify) and SoundCloud (via soundcloud-rpc) using WebSockets.

## 🤖 AI-Generated

This project was written entirely by AI (OpenCode). I describe what I want, review the output, and run the tests — the AI does the coding. Full transparency.

## Requirements

- Python 3.9+
- [spicetify-cli](https://spicetify.app/docs/getting-started)
- [soundcloud-rpc](https://github.com/richardhbtz/soundcloud-rpc) (for SoundCloud support)

## Quick Start

1. **Install the extensions** — `python tools/install.py`
2. **Start the server** — `python server/server.py`
3. Open the **web UI** at `http://localhost:8888/`

Or run `setup.bat` for a one-click install on Windows.

## Usage

| Page        | URL                           |
| ----------- | ----------------------------- |
| Web UI      | `http://localhost:8888/`      |
| Admin panel | `http://localhost:8888/admin` |
| OBS widget  | `http://localhost:8888/obs`   |

Configure the Spotify extension from the profile menu → **Remote Config** (set host/port at runtime, no file editing needed).

## Configuration

Edit `data/config.json`. Key settings: `port`, `host`, `enableOBS`, `enableWebsite`.

Full reference: [`docs/troubleshooting.md`](docs/troubleshooting.md)

## Lyrics

Synced and plain lyrics are fetched from [LRCLIB](https://lrclib.net) and cached in a local SQLite database. The admin panel has a "Lyrics Fetch Timeout" setting and an "Enable Lyrics Fetching" toggle. Delete `data/lyrics_cache.db` to clear the cache.

## Service Management

Run the server as a background service (Windows or Linux): [`docs/service.md`](docs/service.md)

## Stream Deck & Streamer.bot

- **Stream Deck** — [`docs/stream-deck.md`](docs/stream-deck.md)
- **Streamer.bot** — [`streamerbot-commands/README.md`](streamerbot-commands/README.md)

## Security

No authentication. Designed for localhost-only use. Do not expose to the internet without a reverse proxy or firewall.

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, tests, linting, and release workflow.
