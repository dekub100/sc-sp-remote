"""Wire protocol v2: version, permissions and command validation.

The WebSocket message shape is deliberately boring: every message is a JSON
object with a `type`, an optional `source`, and (for state) a nested `state`
object. Keeping the version, the per-client-type permission table and the
command vocabulary in one module means the server and the tests cannot drift.

v2 split:

* source clients (`spicetify`, `soundcloud`) push state:
  `nowPlaying`, `volume`, `playback`, `progress`, `shuffle`, `repeat`, `like`.
* controller clients (`website`, `obs`, `streamdeck`) send `command`.
* every client may send `clientLog`; a source controller may report `error`.

Controllers can never push source state, and source clients can never send
commands. That is enforced before a handler runs (see `handlers.handle_message`).
"""

from __future__ import annotations

from typing import Any

PROTOCOL_VERSION: int = 2

SOURCE_MESSAGE_TYPES: frozenset[str] = frozenset({
    "nowPlaying",
    "volume",
    "playback",
    "progress",
    "shuffle",
    "repeat",
    "like",
    "error",
    "clientLog",
})

CONTROLLER_MESSAGE_TYPES: frozenset[str] = frozenset({
    "command",
    "getInitialState",
    "clientLog",
})

# Identity is advisory (a query parameter) but authority is not: a client can
# only send the message types its role needs.
PERMISSIONS: dict[str, frozenset[str]] = {
    "spicetify": SOURCE_MESSAGE_TYPES,
    "soundcloud": SOURCE_MESSAGE_TYPES,
    "website": CONTROLLER_MESSAGE_TYPES,
    "obs": CONTROLLER_MESSAGE_TYPES,
    "streamdeck": CONTROLLER_MESSAGE_TYPES,
}

# Unknown client types get logging only: no state, no commands.
DEFAULT_PERMISSIONS: frozenset[str] = frozenset({"clientLog"})

COMMANDS: frozenset[str] = frozenset({
    "play",
    "pause",
    "togglePlay",
    "next",
    "previous",
    "seek",
    "seekForward",
    "seekBack",
    "toggleShuffle",
    "toggleRepeat",
    "like",
    "volumeUp",
    "volumeDown",
    "setVolume",
})

# Which extra fields a command may carry. Anything else is dropped before the
# command reaches the source client, so a controller cannot smuggle state.
COMMAND_ARGS: dict[str, tuple[str, ...]] = {
    "seek": ("position",),
    "seekForward": ("offset",),
    "seekBack": ("offset",),
    "volumeUp": ("step",),
    "volumeDown": ("step",),
    "setVolume": ("volume",),
}


def permissions_for(client_type: str) -> frozenset[str]:
    return PERMISSIONS.get(client_type, DEFAULT_PERMISSIONS)


def message_allowed(client_type: str, msg_type: str) -> bool:
    return msg_type in permissions_for(client_type)


def error_message(code: str, message: str) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "type": "error",
        "code": code,
        "message": message,
    }
