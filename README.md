# sc-sp-remote

![Version](https://img.shields.io/badge/version-2.2.0-blue.svg)

A dual-source remote control for Spotify (via Spicetify) and SoundCloud (via soundcloud-rpc) using WebSockets.

## 🤖 AI-Generated

This project was written entirely by AI ([OpenCode](https://github.com/anomalyco/opencode) & [PI Coding Agent](https://github.com/earendil-works/pi) [actual good projects unlike this one]). I do the tests to see if it works etc. Issues and PR's are very welcome to fix my (bad) approach.

## Requirements

- Python 3.9+
- [spicetify-cli](https://spicetify.app/docs/getting-started)
- [soundcloud-rpc](https://github.com/richardhbtz/soundcloud-rpc) (for SoundCloud support)

## Quick Start

1. **Install the extensions** — `python manage.py install`
2. **Start the server** — `python manage.py run`
3. Open the **web UI** at `http://localhost:8888/`

Or run `setup.bat` for a one-click install on Windows.

## Usage

| Page        | URL                           |
| ----------- | ----------------------------- |
| Web UI      | `http://localhost:8888/`      |
| Admin panel | `http://localhost:8888/admin` |
| OBS widget  | `http://localhost:8888/obs`   |

Configure the Spotify extension from the profile menu → **Remote Config** (set host/port at runtime, no file editing needed).

> **Disclaimer:** Album covers and other artwork are shown exactly as provided by Spotify/SoundCloud. You are responsible for what you display on stream — the author is not liable for any strikes, bans, or other consequences caused by showing inappropriate artwork. If in doubt, toggle **Show Album Art** off in the admin panel.

## Configuration

Edit `data/config.json` or use the admin panel at `http://localhost:8888/admin`.

Full reference: [`docs/troubleshooting.md`](docs/troubleshooting.md#config-reference)

## SoundCloud

SoundCloud support works by scraping the SoundCloud DOM via [soundcloud-rpc](https://github.com/richardhbtz/soundcloud-rpc). This is inherently fragile — SoundCloud UI changes can break detection at any time. See [`docs/troubleshooting.md`](docs/troubleshooting.md#soundcloud-integration-is-fragile).

## Lyrics

Lyrics are fetched server-side and cached in a local SQLite database (`data/lyrics_cache.db` — delete it to clear the cache).

- **Providers:** [Musixmatch](https://musixmatch.com) (primary, synced + plain + word-level karaoke) with [LRCLIB](https://lrclib.net) as fallback. Order is configurable via `lyricsProviderOrder` in `data/config.json` or the admin panel.
- **Token:** Musixmatch needs an anonymous usertoken. It's fetched automatically on first use and refreshed when it expires — no interaction needed. If auto-refresh ever breaks: click **Refresh Token** in the admin panel, or run `python manage.py musixmatch-token`.
- **Karaoke:** When Musixmatch has a richsync for a track, both the web UI and OBS widget sweep word-by-word in a fixed highlight color.
- **Covers:** Album artwork on all clients can be hidden with the **Show Album Art** toggle (see disclaimer above).
- The admin panel also has "Lyrics Fetch Timeout" and "Enable Lyrics Fetching" settings.

> The lyrics UI (especially the word-by-word karaoke styling and sync feel) is heavily inspired by Spicetify's [lyrics-plus](https://github.com/spicetify/cli/tree/main/CustomApps/lyrics-plus) — go star it.

## Service Management

Run the server as a background service (Windows or Linux): [`docs/service.md`](docs/service.md)

## Stream Deck & Streamer.bot

- **Stream Deck** — [`docs/stream-deck.md`](docs/stream-deck.md)
- **Streamer.bot** — [`streamerbot-commands/README.md`](streamerbot-commands/README.md)

## Security

No authentication. Designed for localhost-only use. Do not expose to the internet without a reverse proxy or firewall.

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, tests, linting, and release workflow.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
