# spicetify-remote

![Version](https://img.shields.io/badge/version-1.4.0-blue.svg)

A Spicetify extension for remote control/viewing info using WebSockets, without the use of Spotify Premium.

_Code was made with the help of AI, but its honestly so simple i think it just works._

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Service Management (Windows)](#service-management-windows)
- [Service Management (Linux)](#service-management-linux)
- [Elgato Stream Deck Integration](#elgato-stream-deck-integration)
- [Lyrics](#lyrics)
- [Updating](#updating)
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

## Requirements

- Python 3.8+
- [spicetify-cli](https://spicetify.app/docs/getting-started)

## Installation

1. Clone the repo and navigate to the directory:

```bash
git clone https://github.com/dekub100/spicetify-remote
cd spicetify-remote
```

2. Run the install script to set up the Spicetify extension and required Python dependencies:

```bash
python server/install.py
```

3. (Optional) If you'd like to install dependencies manually, you can use:

```bash
pip install -r requirements.txt
```

## Configuration

The server uses a `server/config.json` file for all major settings. You can edit this file to change the ports, allowed origins, default volume, log levels, and more.

**Example `config.json`:**

```json
{
  "port": 8888,
  "allowedOrigins": ["*"],
  "defaultVolume": 0.5,
  "enableOBS": true,
  "enableWebsite": true,
  "volumeStep": 0.05,
  "logLevel": "INFO",
  "backupCount": 3
}
```

- `port`: Main server port (for website, OBS widget, and WebSocket)
- `allowedOrigins`: List of allowed origins for CORS (default: `["*"]`)
- `defaultVolume`: Initial volume value when the server starts
- `enableOBS`: Enable or disable the OBS widget routes
- `enableWebsite`: Enable or disable the web interface
- `logLevel`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `backupCount`: Number of old session log files to keep in `logs/`

**Notes:**

- The Discovery Server is standardized on port `54321`. The Spicetify extension and widgets use this to automatically find your main `port`.
- If you change the `port`, be sure to restart your server and do

```bash
spicetify apply
```

## Running the Server

To start the server manually, run:

```bash
python server/server.py
```

- **Website**: `http://localhost:8888/`
- **OBS Widget**: `http://localhost:8888/obs`
- **Discovery API**: `http://localhost:54321/api/config`

## Service Management (Windows)

You can run the server as a background Windows Service. The script will automatically ask for Administrator privileges if needed.

### Install & Start

```powershell
python server/service.py install
python server/service.py start
```

## Service Management (Linux)

On Linux, you can use `systemd` to run the server in the background.

1. Create a service file:

```bash
sudo nano /etc/systemd/system/spicetify-remote.service
```

2. Paste the following (replace `YOUR_USER` and `YOUR_PATH`):

```ini
[Unit]
Description=Spicetify Remote Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/spicetify-remote/server/server.py
WorkingDirectory=/path/to/spicetify-remote
StandardOutput=inherit
StandardError=inherit
Restart=always
User=YOUR_USER

[Install]
WantedBy=multi-user.target
```

3. Start and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable spicetify-remote
sudo systemctl start spicetify-remote
```

## Elgato Stream Deck Integration

This project includes a dedicated Elgato Stream Deck Plugin for direct control of Spotify via your local `spicetify-remote` server. The source code is in `streamdeck-plugin/`.

### Available Actions

- **Set Volume**: Configurable to an exact percentage.
- **Playback Control**: Play/Pause, Next, Previous.
- **Toggles**: Shuffle, Repeat, Like.
- **Displays**: Shows current volume dynamically on the button.

### Building the Plugin

```bash
cd streamdeck-plugin
npm install
npm run build
```

The built plugin will be output to `com.dekub.spicetify-remote.sdPlugin/`. Double-click the `.streamDeckPlugin` package to install it, or use `npx @elgato/cli install` from the plugin directory.

### Server Communication

The Stream Deck plugin communicates with the server via WebSockets. Ensure your server is running (`python server/server.py` or as a service) for the actions to function.

## Lyrics

Lyrics are fetched from [LRCLIB](https://lrclib.net) and cached locally in `lyrics_cache.db` (SQLite). On the first play of a track the server fetches from LRCLIB's external sources which may take a few seconds; subsequent plays are instant from the local cache. Synced lyrics are highlighted in real-time on the website; plain lyrics are shown as static text when synced aren't available.

To clear the cache, delete `lyrics_cache.db` and restart the server.

### Updating

Download the latest `spicetify-remote-core-v*.zip` from the [releases page](https://github.com/dekub100/spicetify-remote/releases) and extract it over your existing installation — this replaces the server, web files, and extension. Restart the server afterwards.

## Notes

- All configuration is handled via `server/config.json`.
- The Spicetify extension and widgets fetch server config from the dedicated config server on `54321`.
- If you change the `port` in `config.json`, the extension will automatically find it via the discovery port.

## Security

This server has **no authentication** and is designed for **localhost-only** use. Anyone with network access to the server port can control playback, change volume, and skip tracks. Do not expose this server to the internet or untrusted networks without adding your own authentication layer (reverse proxy, firewall rules, etc.).

## Development

Install dev dependencies:

```bash
pip install -r requirements.txt
```

### Running Tests

```bash
python -m pytest test_server.py -v
```

### Linting

```bash
ruff check server/ test_server.py
```
