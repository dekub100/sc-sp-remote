## Task: Add song request queue to Spicetify Remote

### Architecture
Native Spotify queue approach: viewers request songs -> server forwards to extension -> extension calls `Spicetify.addToQueue()` -> extension polls `Spicetify.Queue.nextTracks` and mirrors to server -> server broadcasts to clients.

### Implementation Order (one layer at a time, test each before next)

#### Layer 1: Server state + handlers
**Files:** `server/config.py`, `server/config.json`, `server/state.py`, `server/broadcast.py`, `server/handlers.py`

1. `config.py` -- add constants:
   - `MAX_QUEUE_SIZE = 50`
   - `QUEUE_RATE_LIMIT_SECONDS = 30.0`
   - `QUEUE_SNAPSHOT_INTERVAL = 2.0`

2. `config.json` -- add `maxQueueSize: 50`, `queueRateLimitSeconds: 30`

3. `state.py` -- add queue state:
   - `state["queue"] = {"nextTracks": [], "queueRevision": ""}`
   - `pendingQueueMeta: list[dict[str, str]] = []` (FIFO for `{uri, requestedBy}`)
   - `_rate_limit_store: dict[str, float]` with `check_rate_limit(requester)` function
   - `parse_track_input(text)` -- regex to convert Spotify URLs (`https://open.spotify.com/track/xxx` including `intl-xx/` variant) to `spotify:track:xxx` format. Must handle both URL and bare URI.

4. `broadcast.py` -- add `broadcast_queue_update()`:
   ```python
   async def broadcast_queue_update():
       await broadcast({"type": "queueUpdate", "queue": state["queue"]["nextTracks"], "queueRevision": state["queue"]["queueRevision"]})
   ```

5. `handlers.py` -- add handlers:
   - `handle_queue_snapshot(ws, data)` -- stores `nextTracks` + `queueRevision`, then **matches URIs against `pendingQueueMeta`**: for each track in nextTracks, if `track["uri"]` matches a pending meta's `uri`, copy `requestedBy` into the track and pop the pending entry. Then broadcast.
   - `handle_add_to_queue(ws, data)` -- **critical: run `parse_track_input()` on the input** before storing in `pendingQueueMeta` and before broadcasting to extension. Queue-full check should use `len(pendingQueueMeta)` NOT `len(state["queue"]["nextTracks"])` (latter includes playlist context tracks). Check rate limit. Append `{"uri": normalized_uri, "requestedBy": ...}` to `pendingQueueMeta`, then broadcast `addToQueue` to spicetify only.
   - `handle_remove_from_queue` -- broadcast `removeFromQueue` to spicetify only.
   - `handle_clear_queue` -- broadcast `clearQueue` to spicetify only.
   - `handle_search_and_add` -- relay search query to spicetify via `send_str`.
   - Register all in `MESSAGE_HANDLERS` dict.
   - Extend `handle_get_initial_state` to also send `queueUpdate` to new clients.

**Tests:** verify snapshot stores/broadcasts, pending metadata merges, add forwards to spicetify, rate limiting works, remove/clear forward.

#### Layer 2: HTTP endpoints (for Streamer.bot)
**File:** `server/routes.py`

Five endpoints, all CORS-enabled:
- `GET /api/queue` -- returns `state["queue"]["nextTracks"]` + queueRevision
- `POST /api/queue/add` -- body: `{trackUri, requestedBy?}`. Use `parse_track_input()` to normalize. Check rate limit. Check `len(pendingQueueMeta)` against MAX_QUEUE_SIZE. Append to pendingQueueMeta, send to spicetify WS.
- `POST /api/queue/search-add` -- body: `{query, requestedBy?}`. Check rate limit. Forward to spicetify WS via `send_str`.
- `DELETE /api/queue/remove` -- body: `{trackUri, uid?}`. Forward to spicetify WS.
- `POST /api/queue/clear` -- Forward to spicetify WS.

Register all routes in `server.py`.

**Tests:** verify HTTP endpoints return correct status codes and error responses.

#### Layer 3: Extension polling + handlers
**File:** `spicetify-extension/remoteVolume.js`

1. Add `queueInterval` to state, start in `startServices()` (2s interval), stop in `stopServices()`.

2. **CRITICAL: Wrap all `Spicetify.Player.get*()` calls in try/catch.** Use a helper:
   ```javascript
   _safeGet(fn, fallback) {
       try { return fn(); } catch { return fallback; }
   }
   ```
   This prevents startup errors when internal webpack modules (`_volume`, `_state`) aren't loaded yet. Apply to ALL checkers: `checkVolume`, `checkShuffle`, `checkRepeat`, `checkLikeStatus`, `checkProgressChange`, `checkTrackChange`. Also wrap `syncFullState` and `applyServerState`.

3. Add BigInt-safe JSON replacer to `send()`:
   ```javascript
   this.ws.send(JSON.stringify(data, (_key, value) =>
       typeof value === 'bigint' ? value.toString() : value
   ));
   ```

4. `checkQueue()` -- poll `Spicetify.Queue`:
   ```javascript
   checkQueue() {
       const q = Spicetify.Queue;
       if (!q) return;
       const rev = String(q.queueRevision);  // BigInt -> String!
       if (rev === this.state.queueRevision) return;
       this.state.queueRevision = rev;
       const rawItems = q.nextTracks || [];
       const tracks = rawItems
           .filter(item => {
               const ct = item.contextTrack || item;
               return ct.uri && ct.uri !== "spotify:delimiter";
           })
           .map(item => {
               const ct = item.contextTrack || item;  // CRITICAL: real structure is {contextTrack: {uri, uid, metadata}, ...}
               const meta = ct.metadata || {};
               const rawImg = meta.image_url || meta.image_small_url || meta.image_large_url || "";
               return {
                   uri: ct.uri || "",
                   uid: String(ct.uid ?? ""),
                   metadata: {
                       title: meta.title || ct.name || "",  // try metadata first, then top-level name
                       artist_name: meta.artist_name || (ct.artists?.[0]?.name) || "",
                       image_url: rawImg.startsWith("spotify:image:")
                           ? "https://i.scdn.co/image/" + rawImg.substring(14)
                           : rawImg,
                       duration: meta.duration || ""
                   }
               };
           });
       this.send({ type: "queueSnapshot", nextTracks: tracks, queueRevision: rev });
   }
   ```

5. Add handlers in `onMessage` dispatch:
   - `addToQueue` -> `handleAddToQueue(data)` -- use `Spicetify.URI.from(uri)` to validate, then `Spicetify.addToQueue([{uri: parsed.toURI()}])`
   - `removeFromQueue` -> `handleRemoveFromQueue(data)` -- `Spicetify.removeFromQueue([{uri, uid}])`
   - `clearQueue` -> `handleClearQueue()` -- iterate `Spicetify.Queue.nextTracks`, remove each
   - `searchAndAdd` -> `handleSearchAndAdd(data)` -- `Spicetify.CosmosAsync.get("https://api.spotify.com/v1/search", {q, type:"track", limit:1})`, then `addToQueue` the first result

6. Call `checkQueue()` in `syncFullState()` after sending the initial snapshot, and in `setupEventListeners()` songchange callback.

#### Layer 4: Web UI panel
**Files:** `web/index.html`, `web/script.js`, `web/style.css`

1. Queue panel HTML section with: input field + add button, queue list container, count badge
2. `handleQueueUpdate(data)` -- assign `queueState.items = data.queue`, call `renderQueue()`
3. `renderQueue()` -- render each item showing thumbnail, title, artist, `requestedBy` label, remove button
   - **Count badge shows only `requestedBy` items** (not total nextTracks):
     ```javascript
     const requestedCount = queueState.items.filter(i => i.requestedBy).length;
     ui.queueCount.textContent = requestedCount;
     ```
   - Add `loading="lazy"` to thumbnail images
   - Handle empty state
4. Remove button sends `removeFromQueue`
5. Add button sends `addToQueue` (raw input, server normalizes via `parse_track_input`)
6. CSS: queue panel, items, search bar, badge, remove button styling

#### Layer 5: OBS widget queue count
**Files:** `web/obs-widget/obs-widget.html`, `obs-script.js`, `obs-style.css`

1. Queue count badge element (hidden by default)
2. In `queueUpdate` handler: count only items with `requestedBy`, show/hide badge
3. CSS: positioned overlay badge

#### Layer 6: Streamer.bot documentation
**File:** `streamerbot-commands/README.md`

1. Add `!addqueue` and `!clearqueue` to control commands table
2. Create `AddQueue.cs` (reads `rawInput`, sends `searchAndAdd` via WebSocket)
3. Create `ClearQueue.cs` (sends `clearQueue` via WebSocket)
4. Document display via `GET /api/queue`
5. Document full HTTP endpoint reference table

### Known Gotchas (from debugging)

1. **`Spicetify.Queue.nextTracks[i]` wraps ContextTrack**: real structure is `{contextTrack: {uri, uid, metadata}, removed, blocked, provider}`, NOT a flat `{uri, uid, metadata, removed, blocked, provider}`. Always use `item.contextTrack.uri`.

2. **`queueRevision` is BigInt**: must `String()` it before JSON serialization and before comparison with stored state.

3. **`nextTracks` includes ALL upcoming tracks**: playlist context + user-requested + pre-fetched autoplay recommendations. Queue-full check must use `pendingQueueMeta.length`, not `nextTracks.length`.

4. **`spotify:delimiter` items**: filter out items with `uri === "spotify:delimiter"`.

5. **`metadata.image_url` is `spotify:image:xxx`**: convert to `https://i.scdn.co/image/` + id before sending to clients.

6. **URI normalization**: users may input `https://open.spotify.com/track/xxx` but snapshot URIs are `spotify:track:xxx`. Normalize both pending metadata and stored URIs with `parse_track_input()`.

7. **Startup timing**: `Spicetify.Player.getVolume/getShuffle/getRepeat/getHeart/getProgress/getDuration` all throw TypeError when internal webpack modules haven't loaded yet. `Spicetify.Player` exists but `_volume`/`_state` properties don't. Wrap ALL getters in try/catch (`_safeGet` helper). Also wrap `syncFullState`, `applyServerState`, and `handleCommand`.

8. **Metadata fallback chain**: queue items may have track info in `metadata.title` or `track.name` (top-level). Try `meta.title || t.name || ""`.

9. **Artist fallback chain**: `meta.artist_name` or `t.artists?.[0]?.name || ""`.

10. **Image fallback chain**: `meta.image_url || meta.image_small_url || meta.image_large_url || (t.album?.images?.[0]?.url) || ""`.

### Files to Modify

- `server/config.py` -- constants
- `server/config.json` -- runtime overrides
- `server/state.py` -- queue state, pendingMeta, rate limit, parse_track_input
- `server/broadcast.py` -- broadcast_queue_update
- `server/handlers.py` -- queue handlers + MESSAGE_HANDLERS reg
- `server/routes.py` -- HTTP endpoints + CORS
- `server/server.py` -- route registration, re-exports
- `spicetify-extension/remoteVolume.js` -- checkQueue, addToQueue, removeFromQueue, clearQueue, searchAndAdd, _safeGet, BigInt-safe send
- `web/index.html` -- queue panel HTML
- `web/script.js` -- queue rendering + WS handler
- `web/style.css` -- queue styles
- `web/obs-widget/obs-widget.html` -- queue count badge
- `web/obs-widget/obs-script.js` -- queue count handler
- `web/obs-widget/obs-style.css` -- queue count styles
- `streamerbot-commands/README.md` -- queue command docs
- `streamerbot-commands/AddQueue.cs` -- C# sub-action
- `streamerbot-commands/ClearQueue.cs` -- C# sub-action
- `test_server.py` -- queue tests + fixture update
