# spicetify-remote

A spicetify extension for remote control/viewing info using websockets.

_Code was made with the help of AI, but its honestly so simple i think it just works_

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Adding the server as a service in Windows (optional)](#adding-the-server-as-a-service-in-windows-optional)
- [Adding Streamer.bot commands (optional)](#adding-streamerbot-commands-optional)

## Features

- Remote control from a website or using websockets
- Remote viewing from a website
- Built in OBS Widget for streamers
- Dynamic configuration for host, ports, CORS, and more

## Requirements

- git

## Installation

1. Clone the Repo and navigate to the directory:

```bash
git clone https://github.com/dekub100/spicetify-remote
cd spicetify-remote
```

2. Run the automated setup script for your operating system:

- **For Windows:** Run `setup.bat` as an **administrator**.
- **For Linux/macOS:** Run `setup.sh` as a regular user. (have not tried macOS)

These scripts will tell you if there's any dependencies missing and configure the extension automatically.

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
  "enableOBS": true
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

## Usage

1. Test if everything has installed correctly by running the server:

```bash
node volume-server.js
```

2. If there are no errors, open up [http://localhost:8080](http://localhost:8080) or [http://localhost:8080/obs](http://localhost:8080/obs) (if OBS widget is enabled).

3. The Spicetify extension and OBS widget will automatically fetch the correct host and port from the config server running at `http://127.0.0.1:54321/api/config`.

## Adding the server as a service in Windows (optional)

Instead of manually installing the service, you can now use the provided automated scripts.

1. **Install the service:**
   Run `install-service.bat`. This script will automatically download and set up the service for you.

2. **Remove the service:**
   Run `remove-service.bat`. This script will automatically remove the service for you. You will need to stop it beforehand.

## Adding Streamer.bot commands (optional)

1. Open up streamerbot/streamerbot.txt and copy the contents into the 'Import' feature in Streamer.bot

2. **Update file paths in 'Show Music - Chat Message' Action (Important):**
   - Newtonsoft.Json.dll: In the 'Execute Code' sub-action references, update the path for Newtonsoft.Json.dll. The current path is D:\Stream.bot\Newtonsoft.Json.dll. Change this to the location of the file in your Streamer.bot installation folder. (Image 1)
   - state.json: In the 'Read Lines (state.json)' Sub-Action, update the path for the state.json file. The current path is C:\spicetify-remote\state.json. Change this to the location of the file in your spicetify-remote folder. (Image 2)

<table>
  <tr>
    <td>
    <img src="streamerbot/references.jpg" alt="Image 1">
      </td>
       <td>
    <img src="streamerbot/file_location.jpg" alt="Image 2">
    </td>
  </tr>
</table>
   
<br>

3. Test out the commands in twitch chat:

- !music
- !sstop
- !splay
- !snext
- !sprev
- !vol 0-100 / !vol 0-1.0

## Notes

- The server is localhost-only due to the Spicetify extension requiring https to workout outside of localhost.
- All configuration is handled via `config.json`.
- CORS is configurable via `allowedOrigins` in `config.json`.
- The Spicetify extension and widgets fetch server config from the dedicated config server.
