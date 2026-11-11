# Directory Structure

```
├── README.md
├── requirements.txt          # Python runtime (aiohttp, pywin32)
├── requirements-dev.txt     # Python dev (pytest, ruff, pytest-asyncio)
├── pyproject.toml            # ruff + pytest config
├── conftest.py               # pytest: adds server/ to sys.path, isolates runtime data
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions (lint + test + CD on tag)
├── test_server.py            # Server test suite
├── setup.bat                 # One-click Windows installer
├── AGENTS.md                 # Agent instructions (this index)
├── CONTRIBUTING.md           # Running things, release workflow
├── cliff.toml                 # git-cliff config for conventional-commit release notes
├── data/
│   ├── config.default.json   # Shipped defaults (tracked)
│   ├── config.json           # User config, created on first run (gitignored)
│   ├── dev/                  # dev-server config/state/logs/cache (gitignored)
│   ├── state_spotify.json    # Spotify state (runtime, gitignored)
│   ├── state_soundcloud.json # SoundCloud state (runtime, gitignored)
│   └── (logs/, lyrics_cache.db — runtime, gitignored)
├── server/
│   ├── server.py             # Entry point, routes, main()
│   ├── config.py             # Paths, defaults, layered config loading
│   ├── log.py                # Logger setup, rotation
│   ├── state.py              # SOURCES descriptor, flat state, JSON persistence, debounced saves
│   ├── broadcast.py          # CLIENTS dict, broadcast functions, progress interpolation
│   ├── lyrics.py             # Lyrics providers (Musixmatch + LRCLIB), token mgmt, SQLite cache
│   ├── protocol.py           # Wire v2: version, per-role allowlist, command vocabulary
│   ├── handlers.py           # Message handlers + dispatch table (10 types)
│   └── routes.py             # WS handler, HTTP endpoints, admin config
├── manage.py                 # CLI: run / dev / install / service subcommands
├── web/
│   ├── index.html / style.css / script.js / lib.js / filter.js
│   ├── admin/                 # Admin panel (config editor + log viewer)
│   └── obs-widget/           # OBS browser source widget
├── spicetify-extension/
│   └── remoteVolume.js       # Runs inside Spotify (port 8888)
├── soundcloud-plugin/
│   └── soundcloud-remote-bridge.js  # Runs inside SoundCloud (soundcloud-rpc)
├── streamdeck-plugin/        # TypeScript + Rollup + Elgato SDK; src/actions/ (12 actions) build to bin/, ui/ Property Inspectors share pi-common.js
└── streamerbot-commands/     # Streamer.bot !song/!np commands (import blob + templates)
```

**Ignored:** `data/config.json`, `data/dev/`, `logs/`, `state_spotify.json`, `state_soundcloud.json`, `lyrics_cache.db`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `streamdeck-plugin/node_modules/`
