# Elgato Stream Deck Plugin

## Available Actions

- **Play/Pause** — Toggle play/pause (configurable source: Spotify or SoundCloud).
- **Next Track** — Skip to next track (configurable source).
- **Previous Track** — Go to previous track (configurable source).
- **Seek Forward** — Seek forward by a configurable number of seconds (configurable source).
- **Seek Back** — Seek backward by a configurable number of seconds (configurable source).
- **Volume Up/Down** — Adjust volume (configurable source).
- **Set Volume** — Set exact percentage (configurable source).
- **Volume Display** — Shows current volume dynamically on the button (configurable source).
- **Toggle Shuffle** — Toggle shuffle mode (Spotify only).
- **Toggle Repeat** — Cycle repeat: off → context → track (Spotify only).
- **Toggle Like** — Like/unlike current track (configurable source).

## Source Configuration

Each action (except Shuffle and Repeat) has a **Source** setting in its Property Inspector. Choose `Spotify` or `SoundCloud` to control which source the button operates on. Default is `Spotify`.

The Source setting is stored per action instance, so you can have separate buttons for each source on your Stream Deck.

## Installing

Download `com.dekub.sc-sp-remote.streamDeckPlugin` from the [releases page](https://github.com/dekub100/sc-sp-remote/releases) and double-click to install.

## Building from Source

```bash
cd streamdeck-plugin
npm install
npm run build
cd ..
npx --package=@elgato/cli --yes streamdeck pack streamdeck-plugin/com.dekub.sc-sp-remote.sdPlugin --output . --force
```

The `.streamDeckPlugin` file is output to the project root. It is not committed to the repo — CI auto-builds it and includes it in GitHub releases. Double-click the downloaded `.streamDeckPlugin` to install, or use `npx @elgato/cli install com.dekub.sc-sp-remote`.

## Server Communication

The plugin communicates with the server via WebSocket. Ensure your server is running (`python server/server.py` or as a service) for the actions to function.

## Global Port Configuration

The plugin uses Elgato's Global Settings to share the server port across all buttons. Change the port in any action's Property Inspector and all buttons will use the new port. The port persists across restarts.
