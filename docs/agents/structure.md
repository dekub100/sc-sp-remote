# Directory Structure

```
├── README.md
├── requirements.txt          # Python runtime (aiohttp, pywin32)
├── requirements-dev.txt     # Python dev (pytest, ruff, pytest-asyncio)
├── pyproject.toml            # ruff + pytest config
├── conftest.py               # pytest: adds server/ to sys.path
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions (lint + test + CD on tag)
├── test_server.py            # 118 tests for server logic
├── setup.bat                 # One-click Windows installer
├── AGENTS.md                 # Agent instructions (this index)
├── CONTRIBUTING.md           # Running things, release workflow
├── cliff.toml                 # git-cliff config for conventional-commit release notes
├── data/
│   ├── config.json           # Default server config (port 8888)
│   ├── state_spotify.json    # Spotify state (runtime, gitignored)
│   ├── state_soundcloud.json # SoundCloud state (runtime, gitignored)
│   └── (logs/, lyrics_cache.db — runtime, gitignored)
├── server/
│   ├── server.py             # Entry point, routes, main()
│   ├── config.py             # Paths, constants, config loading
│   ├── log.py                # Logger setup, rotation
│   ├── state.py              # State dict, JSON persistence, debounced saves
│   ├── broadcast.py          # CLIENTS dict, broadcast functions, progress interpolation
│   ├── lyrics.py             # LRC parser, LRCLIB fetcher, SQLite cache
│   ├── handlers.py           # Message handlers + dispatch table (25+ types)
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
├── streamdeck-plugin/        # TypeScript + Rollup + Elgato SDK (future)
└── streamerbot-commands/     # Streamer.bot integration (future)
```

**Ignored:** `logs/`, `state_spotify.json`, `state_soundcloud.json`, `lyrics_cache.db`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `streamdeck-plugin/node_modules/`
