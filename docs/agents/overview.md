# Spicetify Remote — Overview

A Spicetify extension for remote control/viewing of Spotify using WebSockets, without Spotify Premium. Provides a web UI, OBS widget, and Stream Deck plugin — all communicating through a central Python server.

**Version:** 1.5.3
**GitHub:** https://github.com/dekub100/spicetify-remote
**Server:** Python/aiohttp, single port for HTTP + WebSocket
**Clients:** vanilla JS, no build step (except Stream Deck — TypeScript + Rollup)
