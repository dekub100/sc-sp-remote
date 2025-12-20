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

This script will check for dependencies, install Node.js packages, and set up the Spicetify extension. It will also ask you if you want to install the server as a service to run on startup.

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
npm run service-install
```

### Remove Service

To remove the service, run:

```bash
npm run service-uninstall
```

## Elgato Stream Deck Integration

This project now includes a dedicated Elgato Stream Deck Plugin (`com.dekub.spicetify-remote.sdPlugin`) for direct control of Spotify via your local `spicetify-remote` server. This offers a more seamless experience compared to generic web request plugins, providing custom actions that reflect the current state and allow for direct input.

### Plugin Installation

1. Just open the file i think it will install

### Available Actions

#### 1. Set Volume

This action allows you to set Spotify's volume to a specific, customizable level.

- **Customizable**: When you drag the "Set Volume" action onto a key, a Property Inspector will appear, allowing you to type in the exact volume percentage (0-100) you want to set.

- **Dynamic Display**: The button on your Stream Deck will dynamically display the configured volume percentage (e.g., "75%") instead of a static icon, updating in real-time as you adjust it in the Property Inspector.

- **Instance-Specific**: You can configure multiple "Set Volume" buttons, each with a different volume percentage, and they will all function independently.

#### Other Actions (Playback Control, Toggle Shuffle, etc.)

The plugin also includes native actions for:

- Play/Pause

- Next Track

- Previous Track

- Volume Up

- Volume Down

- Toggle Shuffle

- Toggle Repeat

- Toggle Like

- Volume Display (shows current Spotify volume dynamically)

These actions are available directly within the Stream Deck software once the plugin is installed.

### Server Communication

The Stream Deck plugin communicates with the `spicetify-remote` server via WebSockets. Ensure your `spicetify-remote` server is running (`npm start` or as a service) for the Stream Deck actions to function.

## Notes

- The server is localhost-only due to the Spicetify extension requiring https to workout outside of localhost.
- All configuration is handled via `config.json`.
- CORS is configurable via `allowedOrigins` in `config.json`.
- The Spicetify extension and widgets fetch server config from the dedicated config server.
