from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from aiohttp import web
from broadcast import CLIENTS, start_progress_broadcasting
from config import PROJECT_ROOT, SC_STATE_FILE, STATE_FILE, config
from log import logger
from lyrics import _close_connection, _close_session, get_cached_lyrics, init_lyrics_cache, parse_synced_lyrics
from routes import (
    handle_admin_config_get,
    handle_admin_config_put,
    handle_admin_log_file,
    handle_admin_logs_list,
    handle_config,
    handle_queue_add,
    handle_queue_clear,
    handle_queue_get,
    handle_queue_remove,
    handle_state,
    index_handler,
    obs_handler,
)
from state import (
    cancel_pending_save,
    get_sc_save_data,
    get_spotify_save_data,
    read_sc_state_from_file,
    read_spotify_state_from_file,
    set_sc_write_callback,
    set_spotify_write_callback,
)


def _write_spotify_state_to_disk(data: dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _write_sc_state_to_disk(data: dict[str, Any]) -> None:
    with open(SC_STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


init_lyrics_cache()
set_spotify_write_callback(_write_spotify_state_to_disk)
set_sc_write_callback(_write_sc_state_to_disk)
read_spotify_state_from_file()
read_sc_state_from_file()

# Load cached lyrics for the current track
from state import state  # noqa: E402

track_uri = state["currentTrack"]["trackUri"]
track_duration = state["trackDuration"]
if track_uri and track_duration > 0:
    cached = get_cached_lyrics({
        "artist_name": state["currentTrack"]["artistName"],
        "track_name": state["currentTrack"]["trackName"],
        "album_name": state["currentTrack"]["albumName"],
        "duration": max(1, round(track_duration / 1000))
    })
    if cached:
        synced_raw, plain, instrumental = cached
        synced = parse_synced_lyrics(synced_raw) if synced_raw else []
        state["lyrics"] = {
            "trackUri": track_uri,
            "synced": synced,
            "plain": plain or "",
            "available": True,
            "instrumental": bool(instrumental),
            "loading": False
        }
        logger.info(f"Lyrics: Loaded from cache for '{state['currentTrack']['trackName']}' ({len(synced)} synced lines)")


async def main() -> None:
    main_app: web.Application = web.Application()

    main_app.router.add_get('/', index_handler)
    main_app.router.add_get('/obs', obs_handler)
    main_app.router.add_get('/obs/', obs_handler)
    main_app.router.add_get('/api/config', handle_config)
    main_app.router.add_get('/api/state', handle_state)

    main_app.router.add_get('/api/queue', handle_queue_get)
    main_app.router.add_post('/api/queue/add', handle_queue_add)
    main_app.router.add_delete('/api/queue/remove', handle_queue_remove)
    main_app.router.add_post('/api/queue/clear', handle_queue_clear)

    main_app.router.add_get('/api/admin/config', handle_admin_config_get)
    main_app.router.add_put('/api/admin/config', handle_admin_config_put)
    main_app.router.add_get('/api/admin/logs', handle_admin_logs_list)
    main_app.router.add_get('/api/admin/logs/{filename}', handle_admin_log_file)

    async def admin_redirect(request: web.Request) -> web.Response:
        return web.HTTPFound('/static/admin/admin.html')

    main_app.router.add_get('/admin', admin_redirect)
    main_app.router.add_get('/admin/', admin_redirect)

    main_app.router.add_static('/obs/', os.path.join(PROJECT_ROOT, 'web', 'obs-widget'))
    main_app.router.add_static('/static/', os.path.join(PROJECT_ROOT, 'web'))

    main_runner: web.AppRunner = web.AppRunner(main_app)
    await main_runner.setup()

    logger.info(f"Server: http://localhost:{config['port']}")

    try:
        main_site: web.TCPSite = web.TCPSite(main_runner, config.get('host', '0.0.0.0'), config['port'])

        await main_site.start()

        progress_task: asyncio.Task[None] = asyncio.create_task(start_progress_broadcasting())

        await asyncio.sleep(365 * 86400)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Server: Stopping...")
    finally:
        logger.info("Server: Shutting down, performing final state save...")

        cancel_pending_save()

        _write_spotify_state_to_disk(get_spotify_save_data())
        _write_sc_state_to_disk(get_sc_save_data())
        logger.info("Server: State saved to disk.")

        await _close_session()
        logger.debug("Server: HTTP session closed.")

        _close_connection()
        logger.debug("Server: SQLite connection closed.")

        if CLIENTS:
            logger.debug(f"Server: Closing {len(CLIENTS)} active connections...")
            for ws in list(CLIENTS.keys()):
                try:
                    asyncio.create_task(ws.close(code=1001, message='Server shutting down'))
                except Exception:
                    pass

        if 'progress_task' in locals():
            logger.debug("Server: Cancelling progress broadcasting task...")
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
            logger.debug("Server: Progress broadcasting task stopped.")

        logger.debug("Server: Cleaning up main runner...")
        await main_runner.cleanup()
        logger.debug("Server: Main runner cleaned up.")

        logger.info("Server: Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
