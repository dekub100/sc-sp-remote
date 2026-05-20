# spicetify-remote

![Version](https://img.shields.io/badge/version-1.5.2-blue.svg)

A Spicetify extension for remote control/viewing info using WebSockets, without the use of Spotify Premium.

_Code was made with the help of AI, but its honestly so simple i think it just works._

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Service Management](#service-management)
- [Elgato Stream Deck Integration](#elgato-stream-deck-integration)
- [Streamer.bot Integration](#streamerbot-integration)
- [Lyrics](#lyrics)
- [Updating](#updating)
- [Detailed Documentation](#detailed-documentation)
- [Notes](#notes)
- [Security](#security)
- [Development](#development)

## Features

- Remote control from a website or using WebSockets
- Remote viewing from a website
- Built-in OBS Widget for streamers with synced lyrics display
- Dynamic configuration for host, ports, CORS, and more
- Unified server (HTTP + WebSockets) on a single port
- **Synced & plain lyrics** from LRCLIB with download progress indicator
- **Local SQLite cache** — instant repeat plays, no re-fetching from the network
- **Session-based Logging**: Individual log files for each session with configurable levels (DEBUG, INFO, etc.)
- **Robust Sync**: Specialized protection against state-toggling loops
- **Immediate Shutdown**: Improved task management for clean shutdown
- **Song Request Queue**: Viewers can add songs via web UI, Streamer.bot (`!addqueue`), or HTTP API. Queue panel with count badge, remove/clear buttons, and `requestedBy` labels.
- **OBS "Up Next" Transition**: When a song nears its end (~15s), the OBS widget transitions to show the next queued track's title, artist, album, and album art.
- **Queue HTTP Endpoints**: Full REST API for queue management (`GET /api/queue`, `POST /api/queue/add`, `DELETE /api/queue/remove`, `POST /api/queue/clear`).

## Requirements

- Python 3.9+
- [spicetify-cli](https://spicetify.app/docs/getting-started)

## Installation

1. Download the latest `spicetify-remote-core-v*.zip` from the [releases page](https://github.com/dekub100/spicetify-remote/releases).
2. Extract the zip anywhere — it contains `server/`, `web/`, `tools/`, and `spicetify-extension/` folders.
3. Install the Spicetify extension and Python dependencies:

```bash
cd path/to/extracted/folder
python tools/install.py
```

4. Start the server:

```bash
python server/server.py
```

> **Note:** Or just run `setup.bat` for a one-click install on Windows. The install script handles both the Spicetify extension installation and Python dependency setup. If you prefer to install dependencies manually, run `pip install -r requirements.txt` instead.

## Configuration

The server uses a `data/config.json` file for all major settings. You can edit this file to change the ports, allowed origins, default volume, log levels, and more.

**Example `config.json`:**

```json
{
  "port": 8888,
  "host": "127.0.0.1",
  "allowedOrigins": ["*"],
  "defaultVolume": 0.5,
  "enableOBS": true,
  "enableWebsite": true,
  "volumeStep": 0.05,
  "logLevel": "INFO",
  "backupCount": 3,
  "maxQueueSize": 50,
  "queueRateLimitSeconds": 30
}
```

- `port`: Main server port (for website, OBS widget, and WebSocket)
- `host`: Bind address (default: `"127.0.0.1"` for localhost-only; change to `"0.0.0.0"` for LAN access)
- `allowedOrigins`: List of allowed origins for CORS (default: `["*"]`)
- `defaultVolume`: Initial volume value when the server starts
- `enableOBS`: Enable or disable the OBS widget routes
- `enableWebsite`: Enable or disable the web interface
- `logLevel`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `backupCount`: Number of old session log files to keep in `logs/`
- `maxQueueSize`: Maximum number of tracks in the queue (default: 50)
- `queueRateLimitSeconds`: Cooldown between queue adds per requester (default: 30)

**Notes:**

- All clients (Spicetify extension, website, OBS widget) connect directly to the main server port.
- If you change the `port` in `config.json`, re-run `python tools/install.py` to patch the extension automatically.

## Running the Server

To start the server manually, run:

```bash
python server/server.py
```

- **Website**: `http://localhost:8888/`
- **OBS Widget**: `http://localhost:8888/obs`
- **Admin Panel**: `http://localhost:8888/admin`

## Service Management

Run the server as a background service (Windows or Linux). See [`docs/service.md`](docs/service.md) for Windows service and Linux systemd setup.

## Elgato Stream Deck Integration

Includes a dedicated Stream Deck plugin for direct Spotify control. See [`docs/stream-deck.md`](docs/stream-deck.md) for available actions, installation, building from source, and global port configuration.

## Streamer.bot Integration

Control Spotify and display now-playing info from [Streamer.bot](https://streamer.bot) using chat commands. All commands, C# sub-actions, and Streamer.bot import code are documented in:

[`streamerbot-commands/README.md`](streamerbot-commands/README.md)

Includes `!play`, `!pause`, `!next`, `!prev`, `!volume`, `!shuffle`, `!repeat`, `!like`, `!seek`, `!addqueue <url>`, `!clearqueue`, plus display-only commands (`!np`, `!song`, `!current`) via HTTP. Queue commands also available via HTTP endpoints for non-WebSocket integrations.

## Lyrics

Lyrics are fetched from [LRCLIB](https://lrclib.net) and cached locally in `lyrics_cache.db` (SQLite). On the first play of a track the server fetches from LRCLIB's external sources which may take a few seconds; subsequent plays are instant from the local cache. Synced lyrics are highlighted in real-time on the website; plain lyrics are shown as static text when synced aren't available.

To clear the cache, delete `data/lyrics_cache.db` and restart the server.

### Updating

Download the latest `spicetify-remote-core-v*.zip` from the [releases page](https://github.com/dekub100/spicetify-remote/releases) and extract it over your existing installation — this replaces the server, web files, and extension. Restart the server afterwards.

## Detailed Documentation

- [`docs/service.md`](docs/service.md) — Windows service and Linux systemd setup
- [`docs/stream-deck.md`](docs/stream-deck.md) — Stream Deck plugin details and build instructions
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — Common issues and fixes
- [`streamerbot-commands/README.md`](streamerbot-commands/README.md) — Streamer.bot integration and chat commands

## Notes

- All configuration is handled via `data/config.json`.
- The Spicetify extension connects directly to the main server port — no discovery step.
- Log files are stored in the `data/logs/` directory, one per session.

## Security

This server has **no authentication** and is designed for **localhost-only** use. Anyone with network access to the server port can control playback, change volume, and skip tracks. Do not expose this server to the internet or untrusted networks without adding your own authentication layer (reverse proxy, firewall rules, etc.).

---

## Development

For contributors working on the source code.

### Setup

Clone the repo and install dev dependencies:

```bash
git clone https://github.com/dekub100/spicetify-remote
cd spicetify-remote
pip install -r requirements-dev.txt
```

### Running the Server

```bash
python server/server.py
```

Opens on `http://localhost:8888`.

### Project Structure

```
data/                  # Runtime data (config, state, logs, cache)
  config.json          #   Default server configuration (shipped)
server/                # Python backend (split into modules)
  server.py            #   Entry point, routes, main()
  config.py            #   Paths, constants, config loading
  log.py               #   Logger setup, log rotation
  state.py             #   State dict, JSON persistence
  broadcast.py         #   WebSocket broadcast functions
  lyrics.py            #   LRC parser, LRCLIB fetcher, SQLite cache
  handlers.py          #   Message handlers + dispatch table
  routes.py            #   WS handler, HTTP endpoints
tools/                 # Deployment utilities
  install.py           #   Spicetify extension installer
  service.py           #   Windows service wrapper
web/                   # Frontend (no build step)
spicetify-extension/   # Spicetify extension (runs inside Spotify)
streamdeck-plugin/     # Elgato Stream Deck plugin source
```

### Running Tests

```bash
python -m pytest test_server.py -v
```

76 tests covering: lyrics parsing, state save, SQLite cache, message handlers, input validation, broadcasting, CORS config, client registration, queue handlers, rate limiting, URI normalization, and HTTP queue endpoints.

### Linting

```bash
ruff check server/ test_server.py
```

### Stream Deck Plugin

See [`docs/stream-deck.md`](docs/stream-deck.md) for build instructions.
