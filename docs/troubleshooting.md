# Troubleshooting

## Server won't start

Check that the port in `data/config.json` isn't already in use. Change the port if needed:

```json
{ "port": 8888 }
```

By default the server binds to `127.0.0.1` (localhost only). Set `"host": "0.0.0.0"` in `data/config.json` for LAN access.

## Extension not connecting

1. Verify the server is running: `http://localhost:8888/` should load the web UI.
2. Open Spotify, click your profile → **Remote Config**, and verify the host/port match your server.
3. Check Spicetify is installed and the extension is applied: `spicetify config extensions remoteVolume.js` then `spicetify apply`.

## Web UI not loading

The website at `http://localhost:8888/` shows a dual-source remote with Spotify and SoundCloud panels.

- Both panels show album art, track info, progress bar (draggable), and volume slider.
- Spotify panel also has shuffle, repeat, and lyrics toggle.
- Ensure `enableWebsite` is `true` in `data/config.json`.
- Switch sources via the **Spotify / SoundCloud** tabs at the top.

## Admin panel

Open `http://localhost:8888/admin` for a web-based config editor and log viewer.

- **Server Config** tab — edit all settings live (changes apply immediately, reconnect clients after saving).
- **Log Viewer** tab — browse and view server log files.

## SoundCloud integration is fragile

SoundCloud support works by **scraping the SoundCloud website's DOM** via the [soundcloud-rpc](https://github.com/richardhbtz/soundcloud-rpc) Electron app. This is inherently fragile:

- SoundCloud UI changes can break track/state detection at any time.
- Metadata (album art, progress, like status) is read from DOM elements — delays and missed updates are expected.
- `soundcloud-rpc` must be running for any SoundCloud actions to work.
- There is no shuffle or repeat for SoundCloud (these are Spotify API features only).
- Track progress polling relies on the DOM — seek commands may feel slower than Spotify.

If SoundCloud actions stop working:
1. Check that `soundcloud-rpc` is running.
2. Restart the `soundcloud-rpc` app.
3. Check the server log for polling or WebSocket errors (`Log Viewer` in the admin panel).

## OBS widget not displaying

- Make sure `enableOBS` is `true` in `data/config.json`.
- Add a Browser Source in OBS pointing to `http://localhost:8888/obs/`.
- Enable "Use custom frame rate" and set to 60 FPS for smoother marquee animations.
- The widget shows album art, track info, a progress bar, and a synced lyrics line.
- A **source badge** (Spotify/SoundCloud) appears in the top-left corner.
- When a track is nearing the end, "Up Next" is shown ahead of time (threshold configurable via `obsUpNextThresholdMs` in the admin panel).

## Lyrics not loading

- Lyrics come from [Musixmatch](https://musixmatch.com) first (with word-level karaoke when available), falling back to [LRCLIB](https://lrclib.net). If a track isn't in either database, lyrics will show as unavailable.
- Ensure `enableLyrics` is `true` in `data/config.json` (or toggled on in the admin panel).
- Clear the local cache: delete `data/lyrics_cache.db` and restart the server.
- Adjust `lyricsFetchTimeoutSeconds` in the admin panel if requests time out.
- Check `lyricsProviderOrder` in the admin panel — remove `"musixmatch"` if Musixmatch is having issues; the server will use LRCLIB only.
- If Musixmatch lyrics suddenly stop but LRCLIB still works, force a token refresh: **Refresh Token** button in the admin panel, or `python manage.py musixmatch-token`.

## Port conflicts

If port 8888 is in use, change it in `data/config.json`. Then open Spotify, click your profile → **Remote Config** and update the port there too. Update your OBS Browser Source URL and Stream Deck Property Inspector port as needed.

## Config reference

All settings live in `data/config.json` or can be edited live via the admin panel at `http://localhost:8888/admin`.

| Field | Type | Default | Description |
|---|---|---|---|
| `port` | int | `8888` | HTTP/WebSocket server port |
| `host` | string | `"127.0.0.1"` | Bind address (`"0.0.0.0"` for LAN) |
| `allowedOrigins` | list | `["*"]` | CORS allowed origins |
| `defaultVolume` | float | `0.5` | Initial volume (0.0–1.0) |
| `enableOBS` | bool | `true` | Enable OBS widget at `/obs/` |
| `enableWebsite` | bool | `true` | Enable web UI at `/` |
| `enableLyrics` | bool | `true` | Enable lyrics fetching |
| `logLevel` | string | `"INFO"` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `backupCount` | int | `3` | Number of old log files to keep |
| `progressBroadcastInterval` | float | `1.0` | Seconds between progress broadcasts to clients |
| `stateSaveDebounceSeconds` | float | `2.0` | Seconds of inactivity before saving state to disk |
| `lyricsFetchTimeoutSeconds` | int | `30` | Lyrics request timeout (per provider) |
| `lyricsProviderOrder` | list | `["musixmatch", "lrclib"]` | Provider priority order (`musixmatch`, `lrclib`) |
| `musixmatchToken` | string | `""` | Musixmatch usertoken — auto-fetched, don't edit manually (use admin panel / `manage.py musixmatch-token`) |
| `spicetifyPollingIntervalMs` | int | `500` | Spotify polling interval (ms) |
| `spicetifyReconnectBaseDelayMs` | int | `1000` | Initial reconnect backoff (ms) |
| `spicetifyReconnectMaxDelayMs` | int | `10000` | Max reconnect backoff (ms) |
| `spicetifyProgressDeltaThresholdMs` | int | `2000` | Progress drift before re-broadcasting (ms) |
| `spicetifyCommandFeedbackDelayMs` | int | `150` | Wait after command before checking state (ms) |
| `soundcloudPollingIntervalMs` | int | `500` | SoundCloud DOM polling interval (ms) |
| `obsUpNextThresholdMs` | int | `15000` | How early to show "Up Next" before track ends (ms) |
