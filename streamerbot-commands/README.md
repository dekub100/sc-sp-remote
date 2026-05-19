# Streamer.bot Commands for Spicetify Remote

## Server Setup

The `/api/state` endpoint is added in `server/routes.py` and registered in `server/server.py`. Restart the server after updating.

## Control Commands (C# — WebSocket)

Each file is an **Execute C# Code** sub-action. No extra references needed. All use `CPH.WebsocketSend(json, 0)`.

| Trigger       | File             | Action                                     |
| ------------- | ---------------- | ------------------------------------------ |
| `!play`       | PlayPause.cs     | Toggle play/pause                          |
| `!pause`      | Pause.cs         | Pause                                      |
| `!next`       | Next.cs          | Next track                                 |
| `!prev`       | Previous.cs      | Previous track                             |
| `!volup`      | VolumeUp.cs      | Volume +5%                                 |
| `!voldown`    | VolumeDown.cs    | Volume -5%                                 |
| `!volume`     | SetVolume.cs     | Set volume `!volume 50`                    |
| `!shuffle`    | ToggleShuffle.cs | Toggle shuffle                             |
| `!repeat`     | ToggleRepeat.cs  | Cycle repeat                               |
| `!like`       | Like.cs          | Toggle heart                               |
| `!seek`       | Seek.cs          | Seek `!seek 45000`                         |
| `!addqueue`   | AddQueue.cs      | Search & add `!addqueue Bohemian Rhapsody` |
| `!clearqueue` | ClearQueue.cs    | Clear queue                                |

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

## Queue HTTP Endpoints

All endpoints are CORS-enabled and return JSON.

| Method   | Endpoint                | Body                       | Description                      |
| -------- | ----------------------- | -------------------------- | -------------------------------- |
| `GET`    | `/api/queue`            | —                          | Returns current queue + revision |
| `POST`   | `/api/queue/add`        | `{trackUri, requestedBy?}` | Add track by URI (normalized)    |
| `POST`   | `/api/queue/search-add` | `{query, requestedBy?}`    | Search Spotify & add top result  |
| `DELETE` | `/api/queue/remove`     | `{uri, uid?}`              | Remove track from queue          |
| `POST`   | `/api/queue/clear`      | —                          | Clear the entire queue           |

### Response Codes

| Code | Meaning                                   |
| ---- | ----------------------------------------- |
| 200  | Success                                   |
| 400  | Bad request (invalid JSON, queue full)    |
| 429  | Rate limited (30s cooldown per requester) |

### Queue Variables (GET /api/queue)

After Parse JSON on `/api/queue`, these are available:

| Variable                    | Type   | Example             |
| --------------------------- | ------ | ------------------- |
| `%queueJson.queueRevision%` | string | "12345"             |
| `%queueJson.nextTracks%`    | array  | (parsed JSON array) |

### Example: !queue / !queuecount

| #   | Sub-action       | Settings                                        |
| --- | ---------------- | ----------------------------------------------- |
| 1   | **HTTP Request** | `GET /api/queue` → Variable: `queueJson`        |
| 2   | **Send Message** | `Queue: %queueJson.nextTracks% tracks upcoming` |

### Example: !addqueue (via HTTP instead of WebSocket)

| #   | Sub-action       | Settings                                                                                                              |
| --- | ---------------- | --------------------------------------------------------------------------------------------------------------------- |
| 1   | **HTTP Request** | `POST /api/queue/search-add`, Body: `{"query":"%rawInput%","requestedBy":"%user%"}`, Content-Type: `application/json` |
| 2   | **Send Message** | `Added "%rawInput%" to the queue!`                                                                                    |

## Streamer.bot Import

The existing import code below contains only the Spotify playback commands. Queue commands (`!addqueue`, `!clearqueue`) are provided as separate C# files — import them individually via **Actions → Import** or paste the code directly into a new action's **Execute C# Code** sub-action.

```
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
```
