# Troubleshooting

## Server won't start

Check that the port in `data/config.json` isn't already in use. Change the port if needed:

```json
{ "port": 8889 }
```

If the server binds to `127.0.0.1`, only localhost can reach it. Change to `"0.0.0.0"` for LAN access.

## Extension not connecting

1. Verify the server is running: `http://localhost:8888/` should load the web UI.
2. Ensure the port in `data/config.json` matches what the extension uses. Re-run `python tools/install.py` to patch the extension with the current port.
3. Check Spicetify is installed and the extension is applied: `spicetify config extensions remoteVolume.js` then `spicetify apply`.

## OBS widget not displaying

- Make sure `enableOBS` is `true` in `config.json`.
- Add a Browser Source in OBS pointing to `http://localhost:8888/obs/`.
- Enable "Use custom frame rate" and set to 60 FPS for smoother marquee animations.

## Lyrics not loading

- The server fetches lyrics from [LRCLIB](https://lrclib.net). If the track isn't in their database, lyrics will show as unavailable.
- Clear the local cache: delete `data/lyrics_cache.db` and restart the server.

## Port conflicts

If port 8888 is in use, change it in `data/config.json` and:
- Re-run `python tools/install.py` to patch the extension.
- Update your OBS Browser Source URL and Stream Deck Property Inspector port.
