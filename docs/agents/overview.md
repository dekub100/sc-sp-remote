# SC-Spotify-Remote — Overview

A dual-source remote control for Spotify (via Spicetify) and SoundCloud (via soundcloud-rpc). Forked from [spicetify-remote](https://github.com/dekub100/spicetify-remote), diverged at v1.5.4. Port 8889 (avoids conflict with main branch's 8888). Dual-file state (`state_spotify.json` + `state_soundcloud.json`).

**Version:** 1.5.5
**GitHub:** https://github.com/dekub100/spicetify-remote
**Server:** Python/aiohttp, single port for HTTP + WebSocket
**Clients:** Spicetify extension + SoundCloud plugin (DOM injection) + web UI + OBS widget
