# Streamer.bot Commands for Spicetify Remote

## Server Setup

The `/api/state` endpoint is added in `server/routes.py` and registered in `server/server.py`. Restart the server after updating.

## Control Commands (C# — WebSocket)

Each file is an **Execute C# Code** sub-action. No extra references needed. All use `CPH.WebsocketSend(json, 0)`.

| Trigger    | File             | Action                  |
| ---------- | ---------------- | ----------------------- |
| `!play`    | PlayPause.cs     | Toggle play/pause       |
| `!pause`   | Pause.cs         | Pause                   |
| `!next`    | Next.cs          | Next track              |
| `!prev`    | Previous.cs      | Previous track          |
| `!volup`   | VolumeUp.cs      | Volume +5%              |
| `!voldown` | VolumeDown.cs    | Volume -5%              |
| `!volume`  | SetVolume.cs     | Set volume `!volume 50` |
| `!shuffle` | ToggleShuffle.cs | Toggle shuffle          |
| `!repeat`  | ToggleRepeat.cs  | Cycle repeat            |
| `!like`    | Like.cs          | Toggle heart            |
| `!seek`    | Seek.cs          | Seek `!seek 45000`      |

## Display Commands (Native Streamer.bot Sub-Actions)

No C# needed. Each action uses:

| #   | Sub-action          | Settings                                                                                                                  |
| --- | ------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 1   | **HTTP Request**    | Method: GET, URL: `http://localhost:8888/api/state`, Variable: `stateJson` _(auto-parses JSON into `%stateJson.X%` vars)_ |
| 2   | _(logic if needed)_ | Conditional branches                                                                                                      |
| 3   | **Send Message**    | Uses `%stateJson.X%` variables                                                                                            |

### Available Variables

After Parse JSON, these are available:

| Variable                   | Type   | Example               |
| -------------------------- | ------ | --------------------- |
| `%stateJson.trackName%`    | string | "Poker Face"          |
| `%stateJson.artistName%`   | string | "Lady Gaga"           |
| `%stateJson.albumName%`    | string | "The Fame"            |
| `%stateJson.trackUri%`     | string | spotify:track:...     |
| `%stateJson.albumArtUrl%`  | string | https://i.scdn.co/... |
| `%stateJson.isPlaying%`    | string | "True" / "False"      |
| `%stateJson.isShuffling%`  | string | "True" / "False"      |
| `%stateJson.repeatStatus%` | string | "0", "1", "2"         |
| `%stateJson.isLiked%`      | string | "True" / "False"      |
| `%stateJson.volume%`       | string | "0.5"                 |
| `%stateJson.progress%`     | string | "190817" (ms)         |
| `%stateJson.duration%`     | string | "237200" (ms)         |
| `%stateJson.progressFmt%`  | string | "3:10"                |
| `%stateJson.durationFmt%`  | string | "3:57"                |

### Example: !np / !song

| #   | Sub-action          | Settings                                                                                                               |
| --- | ------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1   | **HTTP Request**    | `GET /api/state` → Variable: `stateJson`                                                                               |
| 2   | **Logic — If/Else** | If `%stateJson.isPlaying%` equals `"True"` → branch A, else branch B                                                   |
|     | _Branch A_          | **Send Message:** `%stateJson.trackName% — %stateJson.artistName% [%stateJson.progressFmt% / %stateJson.durationFmt%]` |
|     | _Branch B_          | **Send Message:** `Nothing is playing at the moment.`                                                                  |

### Example: !volume

| #   | Sub-action       | Settings                                 |
| --- | ---------------- | ---------------------------------------- |
| 1   | **HTTP Request** | `GET /api/state` → Variable: `stateJson` |
| 2   | **Send Message** | `Volume: %stateJson.volume%`             |

_(Volume is 0.0–1.0 raw — see note below for percentage display.)_

### Example: !current / !track

| #   | Sub-action          | Settings                                                                                      |
| --- | ------------------- | --------------------------------------------------------------------------------------------- |
| 1   | **HTTP Request**    | `GET /api/state` → Variable: `stateJson`                                                      |
| 2   | **Logic — If/Else** | If `%stateJson.isPlaying%` equals `"True"` → branch A, else branch B                          |
|     | _Branch A_          | **Send Message:** `"%stateJson.trackName%" by %stateJson.artistName% — %stateJson.albumName%` |
|     | _Branch B_          | **Send Message:** `Nothing is playing.`                                                       |

### Volume as Percentage

The volume field comes as 0.0–1.0. To show as 0–100%, either:

- Accept the raw value: `Volume: %stateJson.volume%`
- Or use a **Set Global Variable** with a C# sub-action to multiply by 100 (if you need percentage display)

## Streamer.bot Import

Paste this into Streamer.bot's **Import** dialog to add all commands at once:

```
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
```
