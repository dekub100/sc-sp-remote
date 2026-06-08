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
cd ..
npx --package=@elgato/cli --yes streamdeck pack streamdeck-plugin/com.dekub.sc-sp-remote.sdPlugin --output . --force
```
The `.streamDeckPlugin` file is output to the project root. It is not committed to the repo — only included in GitHub releases.

---

## CI / CD

Pushing to `main` triggers lint + tests on Python 3.9, 3.11, and 3.13. Pushing a tag matching `v*` (e.g., `v1.5.5`) also builds the release zip and creates a GitHub release automatically.

The workflow is at `.github/workflows/ci.yml`.

## Release Workflow

Releases are automated via CI/CD — just push a tag:

```bash
git tag v1.5.5
git push origin v1.5.5
```

GitHub Actions will:
1. Run lint + tests
2. Build `sc-sp-remote-core-v1.5.5.zip`
3. Create a GitHub release with the zip attached

### Manual fallback (if CI fails)

#### 1. Bump Version

Update version in these files:
- `README.md` — badge URL (`version-X.X.X-blue`)
- `AGENTS.md` — `**Version:** X.X.X`
- `pyproject.toml` — `version = "X.X.X"`

Do NOT bump the StreamDeck plugin manifest version unless the plugin source actually changed.

#### 2. Create the Release Zip

Only runtime files — no dev artifacts. `Compress-Archive` flattens paths — use `7z`:

```powershell
Remove-Item sc-sp-remote-core-vX.X.X.zip -Force -ErrorAction SilentlyContinue
7z a -xr'!__pycache__' sc-sp-remote-core-vX.X.X.zip `
  README.md requirements.txt setup.bat `
  server\ data\config.json tools\install.py tools\service.py `
  spicetify-extension\ web\
```

Pitfalls:
- `Compress-Archive` flattens paths — never use it for release zips
- `__pycache__` gets picked up unless explicitly excluded
- **Do not `git add` the zip**

#### 3. Commit & Push

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

#### 4. Create GitHub Release

```powershell
gh release create vX.X.X `
  sc-sp-remote-core-vX.X.X.zip `
  com.dekub.sc-sp-remote.streamDeckPlugin `
  --title "vX.X.X - Short Title" `
  --notes "..."
```

Pitfalls:
- Pass filenames as positional args (not `--files`)
- Re-upload: `gh release delete-asset vX.X.X <filename> --yes && gh release upload vX.X.X <filename> --clobber`
