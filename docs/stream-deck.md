# Elgato Stream Deck Plugin

## Available Actions

- **Set Volume** — Configurable to an exact percentage.
- **Playback Control** — Play/Pause, Next, Previous.
- **Toggles** — Shuffle, Repeat, Like.
- **Volume Display** — Shows current volume dynamically on the button.

## Installing

Download `com.dekub.spicetify-remote.streamDeckPlugin` from the [releases page](https://github.com/dekub100/spicetify-remote/releases) and double-click to install.

## Building from Source

```bash
cd streamdeck-plugin
npm install
npm run build
cd ..
npx --package=@elgato/cli --yes streamdeck pack streamdeck-plugin/com.dekub.spicetify-remote.sdPlugin --output . --force
```

The `.streamDeckPlugin` file is output to the project root. Double-click to install, or use `npx @elgato/cli install com.dekub.spicetify-remote`.

## Server Communication

The plugin communicates with the server via WebSocket. Ensure your server is running (`python server/server.py` or as a service) for the actions to function.

## Global Port Configuration

The plugin uses Elgato's Global Settings to share the server port across all buttons. Change the port in any action's Property Inspector and all buttons will use the new port. The port persists across restarts.
