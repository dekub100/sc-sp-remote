# AGENTS.md — Index

## sc-sp-remote — Overview

A dual-source remote control for Spotify (via Spicetify) and SoundCloud (via soundcloud-rpc). Port 8888. Dual-file state (`state_spotify.json` + `state_soundcloud.json`).

**Version:** 2.2.0
**GitHub:** https://github.com/dekub100/sc-sp-remote
**Server:** Python/aiohttp, single port for HTTP + WebSocket
**Clients:** Spicetify extension + SoundCloud plugin (DOM injection) + web UI + OBS widget

## Knowledge split into topic files under `docs/agents/`. Read only what you need.

| File | When to read |
|---|---|
| `docs/agents/structure.md` | Need file locations |
| `docs/agents/architecture.md` | Need state shape, message types, queue system |
| `docs/agents/conventions.md` | Need Python/JS code style rules |
| `docs/agents/gotchas.md` | Need numbered gotchas/war stories |
| `docs/agents/work.md` | Need dev workflow, adding features, testing, security |

**Always do before commit/PR:** read [CONTRIBUTING.md](CONTRIBUTING.md)

**Always do after changes:** `ruff check` + `pytest`
