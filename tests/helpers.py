"""Small helpers shared by the server test suite (not fixtures)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import broadcast


def register_client(ws: AsyncMock, client_type: str) -> AsyncMock:
    """Make a mock socket look like a connected client to handlers/broadcast."""
    broadcast.CLIENTS[ws] = {"type": client_type, "remote_ip": "127.0.0.1", "protocolVersion": 2}
    return ws


class FakeMxmResponse:
    """Stands in for the aiohttp response object returned by lyrics._get_session()."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    async def json(self, content_type: Any = None) -> dict[str, Any]:
        return self._payload

    async def __aenter__(self) -> "FakeMxmResponse":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False


def mxm_header(status_code: int, hint: str = "") -> dict[str, Any]:
    """A Musixmatch response envelope with the given header status."""
    return {"message": {"header": {"status_code": status_code, "hint": hint}, "body": {}}}
