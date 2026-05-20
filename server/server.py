from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from aiohttp import web
from broadcast import (  # noqa: F401
    CLIENTS,
    broadcast,
    broadcast_current_state,
    broadcast_lyrics_update,
    broadcast_playback_update,
    broadcast_progress_update,
    broadcast_queue_update,
    broadcast_volume_update,
    get_spicetify_client,
    set_spicetify_client,
    start_progress_broadcasting,
)
from config import (  # noqa: F401
    LYRICS_CACHE_DB,
    MAX_QUEUE_SIZE,
    PROJECT_ROOT,
    QUEUE_RATE_LIMIT_SECONDS,
    STATE_FILE,
    config,
)
from handlers import (  # noqa: F401
    MESSAGE_HANDLERS,
    handle_add_to_queue,
    handle_clear_queue,
    handle_error,
    handle_get_initial_state,
    handle_like_command,
    handle_like_update,
    handle_message,
    handle_playback_control,
    handle_playback_update,
    handle_progress_update,
    handle_queue_snapshot,
    handle_register,
    handle_remove_from_queue,
    handle_repeat_update,
    handle_shuffle_update,
    handle_track_update,
    handle_volume_update,
)
from log import logger
from lyrics import (  # noqa: F401
    _close_connection,
    fetch_and_broadcast_lyrics,
    get_cached_lyrics,
    init_lyrics_cache,
    parse_synced_lyrics,
    set_cached_lyrics,
)
from routes import (  # noqa: F401
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
    websocket_handler,
)
from state import (  # noqa: F401
    _rate_limit_store,
    _save_timer,
    cancel_pending_save,
    check_rate_limit,
    get_current_save_data,
    parse_track_input,
    pendingQueueMeta,
    read_state_from_file,
    reset_rate_limit,
    save_state_to_file_debounced,
    set_write_callback,
    state,
)


def _write_state_to_disk(data: dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def save_state_to_file() -> None:
    _write_state_to_disk(get_current_save_data())


init_lyrics_cache()
set_write_callback(_write_state_to_disk)
read_state_from_file()


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

    stop_event: asyncio.Event = asyncio.Event()

    try:
        main_site: web.TCPSite = web.TCPSite(main_runner, config.get('host', '0.0.0.0'), config['port'])

        await main_site.start()

        progress_task: asyncio.Task[None] = asyncio.create_task(start_progress_broadcasting())

        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Server: Stopping...")
    finally:
        logger.info("Server: Shutting down, performing final state save...")

        cancel_pending_save()

        save_state_to_file()
        logger.info("Server: State saved to disk.")

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
