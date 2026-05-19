# Contributing

## Quick Setup

### Windows (one-click)
```powershell
.\setup.bat
```
Installs dependencies, creates `data/` with default config, copies the Spicetify extension, and optionally installs as a Windows service.

### Manual

#### Server
```bash
python server/server.py
```

#### Windows Service
```powershell
python tools/service.py install
python tools/service.py start
python tools/service.py stop
python tools/service.py remove
```

#### Spicetify Extension Install
```bash
python tools/install.py
```

### Tests
```bash
python -m pytest test_server.py -v
```

### Linting
```bash
ruff check server/ test_server.py
```

### Stream Deck Plugin
```bash
cd streamdeck-plugin
npm install
npm run build
```

---

## Release Workflow

### 1. Bump Version

Update version in these files:
- `README.md` — badge URL (`version-X.X.X-blue`)
- `AGENTS.md` — `**Version:** X.X.X`
- `pyproject.toml` — `version = "X.X.X"`

Do NOT bump the StreamDeck plugin manifest version (`streamdeck-plugin/com.dekub.spicetify-remote.sdPlugin/manifest.json`) unless the plugin source actually changed.

### 2. Create the Release Zip

Only runtime files — no dev artifacts:

**Include:**
```
README.md
requirements.txt
setup.bat
server/              # everything except __pycache__/
data/config.json     # default config only (no state.json, logs/, etc.)
tools/               # install.py, service.py
spicetify-extension/
web/                 # everything
```

**Exclude:**
```
test_server.py       # tests — not needed by users
conftest.py          # pytest config — not needed
pyproject.toml       # ruff/pytest config — not needed
.gitignore
__pycache__/
.pytest_cache/
.ruff_cache/
*.pyc
data/state.json      # runtime state
data/logs/           # runtime logs
data/lyrics_cache.db # runtime cache
*.streamDeckPlugin   # shipped separately, not in core zip
streamerbot-commands/ # setup guide only, link in release notes
```

**The `Compress-Archive` cmdlet strips folder structure** — files end up flat. Always use `7z` instead to preserve directories:
```powershell
# Delete any old zip first
Remove-Item spicetify-remote-core-vX.X.X.zip -Force -ErrorAction SilentlyContinue

# Create with proper folder structure
7z a -xr'!__pycache__' spicetify-remote-core-vX.X.X.zip README.md requirements.txt setup.bat server\ data\config.json tools\ spicetify-extension\ web\
```

Pitfalls to avoid:
- `Compress-Archive` flattens paths — never use it for release zips
- `__pycache__` gets picked up unless explicitly excluded with `-xr'!__pycache__'`
- If a previous upload locked the zip, rename it first (`Move-Item`) then delete
- **Do not `git add` the zip** — release zips are for GitHub releases only, not the repo itself

### 3. Commit

Stage everything, commit with a structured message:

```powershell
git add -A
git commit -m "vX.X.X - Short Title

### New Features
* ...

### Improvements
* ...

### Bug Fixes
* ...

### Documentation
* ..."
git push
```

### 4. Create GitHub Release

```powershell
gh release create vX.X.X `
  spicetify-remote-core-vX.X.X.zip `
  com.dekub.spicetify-remote.streamDeckPlugin `
  --title "vX.X.X - Short Title" `
  --notes "### New Features
* ...

### Improvements
* ...

### Bug Fixes
* ...

### How to Update
1. Download the latest spicetify-remote-core-vX.X.X.zip below.
2. Extract it over your existing installation.
3. Restart the server.

---

### Download Assets
* **Core Package:** spicetify-remote-core-vX.X.X.zip (Server + Web + Extension)
* **Stream Deck Plugin:** com.dekub.spicetify-remote.streamDeckPlugin (Optional)
* **Streamer.bot Commands:** See [setup guide](https://github.com/dekub100/spicetify-remote/blob/main/streamerbot-commands/README.md)"
```

Pitfalls:
- `--files` flag doesn't exist on `gh release create` — pass filenames as positional args after the tag
- If re-uploading a fixed asset, use `gh release delete-asset vX.X.X <filename> --yes` then `gh release upload vX.X.X <filename> --clobber`
