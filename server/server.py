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
    broadcast_volume_update,
    get_spicetify_client,
    set_spicetify_client,
    start_progress_broadcasting,
)
from config import (  # noqa: F401
    DISCOVERY_PORT,
    LYRICS_CACHE_DB,
    PROJECT_ROOT,
    STATE_FILE,
    config,
)
from handlers import (  # noqa: F401
    MESSAGE_HANDLERS,
    handle_get_initial_state,
    handle_like_command,
    handle_like_update,
    handle_message,
    handle_playback_control,
    handle_playback_update,
    handle_progress_update,
    handle_register,
    handle_repeat_update,
    handle_shuffle_update,
    handle_track_update,
    handle_volume_update,
)
from log import logger
from lyrics import (  # noqa: F401
    fetch_and_broadcast_lyrics,
    get_cached_lyrics,
    init_lyrics_cache,
    parse_synced_lyrics,
    set_cached_lyrics,
)
from routes import (  # noqa: F401
    handle_config,
    handle_state,
    index_handler,
    obs_handler,
    websocket_handler,
)
from state import (  # noqa: F401
    _save_timer,
    cancel_pending_save,
    get_current_save_data,
    read_state_from_file,
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

    main_app.router.add_static('/obs/', os.path.join(PROJECT_ROOT, 'web', 'obs-widget'))
    main_app.router.add_static('/', os.path.join(PROJECT_ROOT, 'web'))

    main_runner: web.AppRunner = web.AppRunner(main_app)
    await main_runner.setup()

    config_app: web.Application = web.Application()
    config_app.router.add_get('/api/config', handle_config)
    config_runner: web.AppRunner = web.AppRunner(config_app)
    await config_runner.setup()

    logger.info(f"Main Server: http://localhost:{config['port']}")
    logger.info(f"Discovery Server: http://localhost:{DISCOVERY_PORT}")

    stop_event: asyncio.Event = asyncio.Event()

    try:
        main_site: web.TCPSite = web.TCPSite(main_runner, '0.0.0.0', config['port'])
        config_site: web.TCPSite = web.TCPSite(config_runner, '0.0.0.0', DISCOVERY_PORT)

        await main_site.start()
        await config_site.start()

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

        logger.debug("Server: Cleaning up config runner...")
        await config_runner.cleanup()
        logger.debug("Server: Config runner cleaned up.")

        logger.info("Server: Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
