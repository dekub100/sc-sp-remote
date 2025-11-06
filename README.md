# spicetify-remote

A spicetify extension for remote control/viewing info using websockets. Without the use of Spotify Premium.

_Code was made with the help of AI, but its honestly so simple i think it just works_

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Service Management](#service-management)
- [Elgato Stream Deck Integration](#elgato-stream-deck-integration)
- [Notes](#notes)

## Features

- Remote control from a website or using websockets
- Remote viewing from a website
- Built in OBS Widget for streamers
- Dynamic configuration for host, ports, CORS, and more

## Requirements

- npm
- git
- spicetify-cli

## Installation

1. Clone the Repo and navigate to the directory:

```bash
git clone https://github.com/dekub100/spicetify-remote
cd spicetify-remote
```

2. Run the setup script:

```bash
npm run setup
```

This script will check for dependencies, install Node.js packages, and set up the Spicetify extension.

**Note:** The current setup script (`npm run setup`) is largely untested and may not work as expected on all systems (especially on macOS since i dont have a mac device). Manual installation steps are provided below.

### Manual Installation

If the `npm run setup` script fails, you can follow these steps for a manual installation:

1.  **Install Node.js Dependencies:**
    Navigate to the project directory and run:

    ```bash
    npm install
    ```

2.  **Locate Spicetify Extensions Folder:**
    The Spicetify extensions folder is usually located at:

    - **Windows:** `%APPDATA%\spicetify\Extensions` (e.g., `C:\Users\YOUR_USERNAME\AppData\Roaming\spicetify\Extensions`)
    - **Linux/macOS:** `~/.config/spicetify/Extensions` (e.g., `/home/YOUR_USERNAME/.config/spicetify/Extensions`)

3.  **Copy Extension File:**
    Copy the `remoteVolume.js` file from the cloned repository to the Spicetify extensions folder.

4.  **Configure Spicetify:**
    Run the following commands in your terminal:
    ```bash
    spicetify config extensions remoteVolume.js
    spicetify apply
    ```

## Configuration

The server uses a `config.json` file for all major settings.  
You can edit this file to change the ports, allowed origins, default volume, and OBS widget support.

**Example `config.json`:**

```json
{
  "port": 8080,
  "configPort": 54321,
  "allowedOrigins": ["*"],
  "defaultVolume": 0.5,
  "enableOBS": true,
  "volumeStep": 0.05
}
```

- `port`: Main server port (for website and websocket)
- `configPort`: Dedicated port for config server (used by extensions/widgets to fetch config)
- `allowedOrigins`: List of allowed origins for CORS (default: `["*"]`)
- `defaultVolume`: Initial volume value when the server starts
- `enableOBS`: Enable or disable the OBS widget routes

**Notes:**

- If you change the `configPort` , update your Spicetify extension to fetch config from the correct `configPort`.
- If you change the `port` , be sure to restart your server and do

```bash
spicetify apply
```

## Service Management

You can also use the setup script to install or remove the server as a system service.

### Install Service

To install the server as a service, run:

```bash
node setup.js --install-service
```

### Remove Service

To remove the service, run:

```bash
node setup.js --remove-service
```

## Elgato Stream Deck Integration

You can control your Spotify player directly from an Elgato Stream Deck using the ["Web Requests" plugin by Adrian Mullings on the Elgato Marketplace](https://marketplace.elgato.com/product/web-requests-d7d46868-f9c8-4fa5-b775-ab3b9a7c8add). This allows full control (e.g., play/pause, next/previous, like, shuffle, repeat, volume) without needing Spotify Premium.

To send commands, you will need to send a POST request to `http://localhost:8080` with a JSON body. Here are some examples:

- **Playback Control (e.g., Play/Pause, Next, Previous, Like, Shuffle, Repeat):**

  ```json
  { "type": "playbackControl", "command": "togglePlay" }
  ```

  Replace `togglePlay` with `next`, `previous`, `like`, `toggleShuffle`, or `toggleRepeat`.

- **Set Specific Volume Level:**

  ```json
  { "type": "volumeUpdate", "volume": 0.5 }
  ```

  Replace `0.5` with your desired volume level (a float between 0.0 and 1.0).

- **Adjust Volume Up/Down:**
  ```json
  { "type": "volumeUpdate", "command": "volumeUp" }
  ```
  Replace `volumeUp` with `volumeDown` to decrease the volume.

## Notes

- The server is localhost-only due to the Spicetify extension requiring https to workout outside of localhost.
- All configuration is handled via `config.json`.
- CORS is configurable via `allowedOrigins` in `config.json`.
- The Spicetify extension and widgets fetch server config from the dedicated config server.
