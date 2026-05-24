# Directory Structure

```
├── README.md
├── requirements.txt          # Python runtime (aiohttp, pywin32)
├── requirements-dev.txt     # Python dev (pytest, ruff, pytest-asyncio)
├── pyproject.toml            # ruff + pytest config
├── conftest.py               # pytest: adds server/ to sys.path
├── test_server.py            # 76+ tests for server logic
├── setup.bat                 # One-click Windows installer
├── AGENTS.md                 # Agent instructions (this index)
├── CONTRIBUTING.md           # Running things, release workflow
├── data/
│   ├── config.json           # Default server config
│   └── (state.json, logs/, lyrics_cache.db — runtime, gitignored)
├── server/
│   ├── server.py             # Entry point, routes, main()
│   ├── config.py             # Paths, constants, config loading
│   ├── log.py                # Logger setup, rotation
│   ├── state.py              # State dict, JSON persistence, debounced saves
│   ├── broadcast.py          # CLIENTS dict, broadcast functions
│   ├── lyrics.py             # LRC parser, LRCLIB fetcher, SQLite cache
│   ├── handlers.py           # Message handlers + dispatch table
│   └── routes.py             # WS handler, HTTP endpoints
├── tools/
│   ├── dev.py                # Dev server (auto-reload, port isolation)
│   ├── service.py            # Windows service wrapper
│   └── install.py            # Extension installer
├── web/
│   ├── index.html / style.css / script.js / lib.js / filter.js
│   └── obs-widget/           # OBS browser source widget
├── spicetify-extension/
│   └── remoteVolume.js       # Runs inside Spotify
├── streamdeck-plugin/        # TypeScript + Rollup + Elgato SDK
├── streamerbot-commands/     # Streamer.bot integration
└── com.dekub.spicetify-remote.streamDeckPlugin  # Pre-built plugin
```

**Ignored:** `logs/`, `state.json`, `lyrics_cache.db`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `streamdeck-plugin/node_modules/`
