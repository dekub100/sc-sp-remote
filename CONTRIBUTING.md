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
python manage.py run
```

#### Windows Service
```powershell
python manage.py service install
python manage.py service start
python manage.py service stop
python manage.py service remove
```

#### Spicetify Extension Install
```bash
python manage.py install
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

Pushing to `main` triggers lint + tests on Python 3.9, 3.11, and 3.13. Pushing a tag matching `v*` (e.g., `v2.0.0`) also builds the release zip and creates a GitHub release automatically.

The workflow is at `.github/workflows/ci.yml`.

## Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) spec:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

| Type        | Usage                          |
|-------------|--------------------------------|
| `feat`      | A new feature                  |
| `fix`       | A bug fix                      |
| `build`     | Build system / dependencies    |
| `chore`     | Routine tasks, maintenance     |
| `ci`        | CI configuration               |
| `docs`      | Documentation only             |
| `perf`      | Performance improvement        |
| `refactor`  | Code change with no behaviour change |
| `style`     | Formatting, missing semicolons, etc. |
| `test`      | Adding or fixing tests         |

Use `!` after the type/scope or a `BREAKING CHANGE` footer for breaking changes. Append body and footers after a blank line.

```powershell
git commit -m "feat: add lyrics panel

implement synced lyrics display with real-time highlighting

Closes #42"
```

## Release Workflow

Releases are automated via CI/CD — just push a tag:

```bash
git tag v2.0.0
git push origin v2.0.0
```

GitHub Actions will:
1. Run lint + tests
2. Build `sc-sp-remote-core-v2.0.0.zip` and the `.streamDeckPlugin`
3. Generate release notes from conventional commits via [git-cliff](https://git-cliff.org)
4. Create a GitHub release with both assets and the notes attached

### Manual fallback (if CI fails)

#### 1. Bump Version

Update version in these files:
- `README.md` — badge URL (`version-X.X.X-blue`)
- `AGENTS.md` — `**Version:** X.X.X`
- `pyproject.toml` — `version = "X.X.X"`

Do NOT bump the StreamDeck plugin manifest version unless the plugin source actually changed.

#### 2. Commit & Push

Use the conventional-commit format described above.

```powershell
git add -A
git commit -m "Bump version to X.X.X"
git push
```

#### 3. Create GitHub Release

The CI workflow builds both assets and generates release notes automatically — assets are not committed. If CI failed, push a tag and let CI retry.

For a manual release (CI unavailable), push the tag first so it resolves, generate notes with git-cliff, then create:

```powershell
git-cliff --current --tag vX.X.X -o RELEASE_NOTES.md
gh release create vX.X.X -F RELEASE_NOTES.md
```

Pitfalls:
- Re-upload: `gh release delete-asset vX.X.X <filename> --yes && gh release upload vX.X.X <filename> --clobber`
- git-cliff config lives in `cliff.toml` at the project root
