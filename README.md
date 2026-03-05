# spicetify-remote

A Spicetify extension for remote control/viewing info using WebSockets, without the use of Spotify Premium.

_Code was made with the help of AI, but its honestly so simple i think it just works._

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Service Management (Windows)](#service-management-windows)
- [Elgato Stream Deck Integration](#elgato-stream-deck-integration)
- [Notes](#notes)

## Features

- Remote control from a website or using WebSockets
- Remote viewing from a website
- Built-in OBS Widget for streamers
- Dynamic configuration for host, ports, CORS, and more
- Unified server (HTTP + WebSockets) on a single port

## Requirements

- Python 3.8+
- [spicetify-cli](https://spicetify.app/docs/getting-started)

## Installation

1. Clone the repo and navigate to the directory:

```bash
git clone https://github.com/dekub100/spicetify-remote
cd spicetify-remote
```

2. Install the required Python dependencies:

```bash
pip install aiohttp websockets pywin32
```

3. Run the setup script to install the Spicetify extension:

```bash
python setup.py
```

## Configuration

The server uses a `config.json` file for all major settings. You can edit this file to change the ports, allowed origins, default volume, and OBS widget support.

**Example `config.json`:**

```json
{
  "port": 8888,
  "configPort": 54321,
  "allowedOrigins": ["*"],
  "defaultVolume": 0.5,
  "enableOBS": true,
  "enableWebsite": true,
  "volumeStep": 0.05
}
```

- `port`: Main server port (for website, OBS widget, and WebSocket)
- `configPort`: Dedicated port for the config server (used by extensions/widgets to discover the main port)
- `allowedOrigins`: List of allowed origins for CORS (default: `["*"]`)
- `defaultVolume`: Initial volume value when the server starts
- `enableOBS`: Enable or disable the OBS widget routes
- `enableWebsite`: Enable or disable the web interface

## Running the Server

To start the server manually, run:

```bash
python server.py
```

- **Website**: `http://localhost:8888/`
- **OBS Widget**: `http://localhost:8888/obs`
- **Config API**: `http://localhost:54321/api/config`

## Service Management (Windows)

You can run the server as a background Windows Service. The script will automatically ask for Administrator privileges if needed.

### Install & Start
```powershell
python service.py install
python service.py start
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
ExecStart=/usr/bin/python3 /path/to/spicetify-remote/server.py
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

This project includes a dedicated Elgato Stream Deck Plugin (`com.dekub.spicetify-remote.sdPlugin`) for direct control of Spotify via your local `spicetify-remote` server.

### Available Actions
- **Set Volume**: Configurable to an exact percentage.
- **Playback Control**: Play/Pause, Next, Previous.
- **Toggles**: Shuffle, Repeat, Like.
- **Displays**: Shows current volume dynamically on the button.

### Server Communication
The Stream Deck plugin communicates with the server via WebSockets. Ensure your server is running (`python server.py` or as a service) for the actions to function.

## Notes

- All configuration is handled via `config.json`.
- The Spicetify extension and widgets fetch server config from the dedicated config server on `54321`.
- If you change the `port` in `config.json`, the extension will automatically find it via the discovery port.
