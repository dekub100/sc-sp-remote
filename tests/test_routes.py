"""HTTP + WebSocket endpoints in server/routes.py: config API, admin
API, log endpoints, client lifecycle."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import config as cfg
import pytest
import routes
import state as st


class TestConfigEndpoint:
    async def test_cors_with_wildcard_origin(self) -> None:
        req: MagicMock = MagicMock()
        req.headers = {}
        orig: list[str] = cfg.config["allowedOrigins"].copy()
        cfg.config["allowedOrigins"] = ["*"]
        try:
            resp: Any = await routes.handle_config(req)
        finally:
            cfg.config["allowedOrigins"] = orig
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    async def test_cors_matching_origin(self) -> None:
        req = MagicMock()
        req.headers = {"Origin": "http://localhost:3000"}
        orig = cfg.config["allowedOrigins"].copy()
        cfg.config["allowedOrigins"] = ["http://localhost:3000"]
        try:
            resp = await routes.handle_config(req)
        finally:
            cfg.config["allowedOrigins"] = orig
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"

    async def test_cors_non_matching_origin(self) -> None:
        req = MagicMock()
        req.headers = {"Origin": "http://evil.com"}
        orig = cfg.config["allowedOrigins"].copy()
        cfg.config["allowedOrigins"] = ["http://localhost:3000"]
        try:
            resp = await routes.handle_config(req)
        finally:
            cfg.config["allowedOrigins"] = orig
        assert resp.headers.get("Access-Control-Allow-Origin") is None

    async def test_config_response_body(self) -> None:
        req = MagicMock()
        req.headers = {}
        orig_port: int = cfg.config["port"]
        orig_vol: float = cfg.config["defaultVolume"]
        cfg.config["port"] = 9999
        cfg.config["defaultVolume"] = 0.7
        try:
            resp = await routes.handle_config(req)
        finally:
            cfg.config["port"] = orig_port
            cfg.config["defaultVolume"] = orig_vol
        body: bytes = resp.body
        data: dict[str, Any] = json.loads(body)
        assert data["port"] == 9999
        assert data["defaultVolume"] == 0.7
        assert set(data) == {"port", "allowedOrigins", "defaultVolume"}


class TestAdminConfigPut:
    @pytest.fixture
    async def client(self, tmp_path: Any):
        from copy import deepcopy

        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        saved_config = deepcopy(cfg.config)
        app = web.Application()
        app.router.add_put('/api/admin/config', routes.handle_admin_config_put)
        app.router.add_get('/api/admin/config', routes.handle_admin_config_get)
        # The handler persists to routes.CONFIG_PATH; point it at tmp_path so a
        # test run never rewrites the real user config.
        with patch.object(routes, "CONFIG_PATH", str(tmp_path / "config.json")):
            async with TestClient(TestServer(app)) as tc:
                yield tc
        cfg.config.clear()
        cfg.config.update(saved_config)

    async def test_valid_port_update(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"port": 9090})
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert cfg.config["port"] == 9090

    async def test_port_out_of_range(self, client) -> None:
        orig = cfg.config["port"]
        resp = await client.put('/api/admin/config', json={"port": 99999})
        assert resp.status == 400
        data = await resp.json()
        assert "port" in data["error"].lower() or "validation" in data["error"].lower()
        assert cfg.config["port"] == orig

    async def test_port_zero_rejected(self, client) -> None:
        orig = cfg.config["port"]
        resp = await client.put('/api/admin/config', json={"port": 0})
        assert resp.status == 400
        assert cfg.config["port"] == orig

    async def test_default_volume_clamped(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"defaultVolume": 0.75})
        assert resp.status == 200
        assert cfg.config["defaultVolume"] == 0.75

    async def test_default_volume_out_of_range(self, client) -> None:
        orig = cfg.config["defaultVolume"]
        resp = await client.put('/api/admin/config', json={"defaultVolume": 5.0})
        assert resp.status == 400
        assert cfg.config["defaultVolume"] == orig

    async def test_log_level_valid(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"logLevel": "DEBUG"})
        assert resp.status == 200
        assert cfg.config["logLevel"] == "DEBUG"

    async def test_log_level_applies_live(self, client) -> None:
        from log import logger
        orig = logger.level
        try:
            resp = await client.put('/api/admin/config', json={"logLevel": "DEBUG"})
            assert resp.status == 200
            assert logger.level == logging.DEBUG
        finally:
            logger.setLevel(orig)

    async def test_restart_required_for_process_keys(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"port": 9091})
        assert resp.status == 200
        data = await resp.json()
        assert data["restartRequired"] == ["port"]

    async def test_live_key_needs_no_restart(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"progressBroadcastInterval": 2.0})
        assert resp.status == 200
        data = await resp.json()
        assert data["restartRequired"] == []

    async def test_interval_below_admin_minimum_rejected(self, client) -> None:
        orig = cfg.config["progressBroadcastInterval"]
        resp = await client.put('/api/admin/config', json={"progressBroadcastInterval": 0.0001})
        assert resp.status == 400
        assert cfg.config["progressBroadcastInterval"] == orig

    async def test_debounce_below_admin_minimum_rejected(self, client) -> None:
        orig = cfg.config["stateSaveDebounceSeconds"]
        resp = await client.put('/api/admin/config', json={"stateSaveDebounceSeconds": 0.1})
        assert resp.status == 400
        assert cfg.config["stateSaveDebounceSeconds"] == orig

    async def test_log_level_invalid(self, client) -> None:
        orig = cfg.config.get("logLevel")
        resp = await client.put('/api/admin/config', json={"logLevel": "VERBOSE"})
        assert resp.status == 400
        assert cfg.config.get("logLevel") == orig

    async def test_allowed_origins_valid(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"allowedOrigins": ["http://localhost:3000"]})
        assert resp.status == 200
        assert cfg.config["allowedOrigins"] == ["http://localhost:3000"]

    async def test_config_get_redacts_token(self, client) -> None:
        cfg.config["musixmatchToken"] = "secret-token-123"
        resp = await client.get('/api/admin/config')
        assert resp.status == 200
        data = await resp.json()
        assert "musixmatchToken" not in data
        assert "port" in data  # other fields still present

    async def test_allowed_origins_not_list(self, client) -> None:
        orig = cfg.config["allowedOrigins"].copy()
        resp = await client.put('/api/admin/config', json={"allowedOrigins": "not-a-list"})
        assert resp.status == 400
        assert cfg.config["allowedOrigins"] == orig

    async def test_allowed_origins_non_string_items(self, client) -> None:
        orig = cfg.config["allowedOrigins"].copy()
        resp = await client.put('/api/admin/config', json={"allowedOrigins": [123, 456]})
        assert resp.status == 400
        assert cfg.config["allowedOrigins"] == orig

    async def test_unknown_field_ignored(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"unknownField": "value"})
        assert resp.status == 200
        data = await resp.json()
        assert data["updated"] == []

    async def test_multiple_fields_partial_fail(self, client) -> None:
        orig_port = cfg.config["port"]
        resp = await client.put('/api/admin/config', json={"port": 7777, "defaultVolume": 5.0})
        assert resp.status == 400
        data = await resp.json()
        details = data.get("details", [])
        assert any("defaultVolume" in d for d in details)
        assert cfg.config["port"] == orig_port

    async def test_invalid_json(self, client) -> None:
        resp = await client.put('/api/admin/config', data="not json", headers={"Content-Type": "application/json"})
        assert resp.status == 400
        data = await resp.json()
        assert "Invalid JSON" in data["error"]

    async def test_type_coercion_port_string_to_int(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"port": "9090"})
        assert resp.status == 200
        assert cfg.config["port"] == 9090

    async def test_type_coercion_volume_string_to_float(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"defaultVolume": "0.8"})
        assert resp.status == 200


class TestAdminLogEndpoints:
    @pytest.fixture
    async def client(self, tmp_path):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        app = web.Application()
        app.router.add_get('/api/admin/logs', routes.handle_admin_logs_list)
        app.router.add_get('/api/admin/logs/{filename}', routes.handle_admin_log_file)
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        async with TestClient(TestServer(app)) as tc:
            with patch("routes.LOG_DIR", str(log_dir)):
                yield tc, log_dir

    async def test_logs_list_empty(self, client) -> None:
        tc, _ = client
        resp = await tc.get('/api/admin/logs')
        assert resp.status == 200
        data = await resp.json()
        assert data["logs"] == []

    async def test_logs_list_returns_entries(self, client) -> None:
        tc, log_dir = client
        (log_dir / "server.log").write_text("hello")
        (log_dir / "error.log").write_text("oops")
        resp = await tc.get('/api/admin/logs')
        assert resp.status == 200
        data = await resp.json()
        names = [f["name"] for f in data["logs"]]
        assert "server.log" in names
        assert "error.log" in names
        assert all(f["size"] >= 0 for f in data["logs"])

    async def test_logs_list_ignores_non_log_files(self, client) -> None:
        tc, log_dir = client
        (log_dir / "secret.txt").write_text("hidden")
        (log_dir / "server.log").write_text("real")
        resp = await tc.get('/api/admin/logs')
        data = await resp.json()
        assert all(f["name"].endswith(".log") for f in data["logs"])

    async def test_log_file_success(self, client) -> None:
        tc, log_dir = client
        (log_dir / "server.log").write_text("line1\nline2")
        resp = await tc.get('/api/admin/logs/server.log')
        assert resp.status == 200
        text = await resp.text()
        assert text == "line1\nline2"

    async def test_log_file_not_found(self, client) -> None:
        tc, _ = client
        resp = await tc.get('/api/admin/logs/nonexistent.log')
        assert resp.status == 404
        data = await resp.json()
        assert "not found" in data["error"].lower()

    async def test_log_file_non_log_extension(self, client) -> None:
        tc, log_dir = client
        (log_dir / "evil.txt").write_text("hack")
        resp = await tc.get('/api/admin/logs/evil.txt')
        assert resp.status == 404

    async def test_log_file_path_traversal_dotdot(self, client) -> None:
        tc, _ = client
        resp = await tc.get('/api/admin/logs/..%2F..%2Fetc%2Fpasswd')
        assert resp.status == 400
        data = await resp.json()
        assert "invalid" in data["error"].lower()

    async def test_log_file_path_traversal_forward_slash_urlencoded(self, client) -> None:
        tc, _ = client
        resp = await tc.get('/api/admin/logs/..%2Fetc%2Fpasswd')
        assert resp.status == 400
        data = await resp.json()
        assert "invalid" in data["error"].lower()


class TestFormatMs:
    def test_zero(self) -> None:
        assert routes.format_ms(0) == "0:00"

    def test_seconds(self) -> None:
        assert routes.format_ms(59999) == "0:59"

    def test_minutes(self) -> None:
        assert routes.format_ms(60000) == "1:00"

    def test_negative_clamped(self) -> None:
        assert routes.format_ms(-5000) == "0:00"

    def test_exact_minute(self) -> None:
        assert routes.format_ms(120000) == "2:00"

    def test_hour_rollover(self) -> None:
        assert routes.format_ms(3_600_000) == "1:00:00"

    def test_hours_minutes_seconds(self) -> None:
        assert routes.format_ms(3_723_000) == "1:02:03"


class TestBuildClientConfig:
    def test_spicetify_keys(self) -> None:
        result = routes._build_client_config("spicetify")
        for key in ("pollingIntervalMs", "reconnectBaseDelayMs", "reconnectMaxDelayMs",
                    "progressDeltaThresholdMs", "commandFeedbackDelayMs"):
            assert key in result
        assert result["type"] == "config"

    def test_soundcloud_keys(self) -> None:
        result = routes._build_client_config("soundcloud")
        assert "pollingIntervalMs" in result
        assert "reconnectBaseDelayMs" not in result
        assert result["type"] == "config"

    def test_unknown_only_type(self) -> None:
        result = routes._build_client_config("website")
        assert result == {"v": 2, "type": "config"}


class TestWebSocketLifecycle:
    V2 = "&protocolVersion=2"

    @pytest.fixture
    async def tc(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        app = web.Application()
        app.router.add_get('/', routes.websocket_handler)
        app.router.add_get('/api/state', routes.handle_state)
        async with TestClient(TestServer(app)) as client:
            yield client

    async def _is_playing(self, tc) -> bool:
        async with tc.get('/api/state') as resp:
            return (await resp.json())["spotify"]["isPlaying"]

    async def test_reconnect_does_not_pause_while_another_controller_is_attached(self, tc) -> None:
        with patch.object(routes, "DISCONNECT_PAUSE_GRACE_SECONDS", 0.05), \
             patch.object(routes, "save_source_state_debounced", new_callable=AsyncMock):
            old = await tc.ws_connect('/?client=spicetify' + self.V2)
            new = await tc.ws_connect('/?client=spicetify' + self.V2)
            await old.send_json({"type": "nowPlaying", "state": {
                "isPlaying": True, "trackName": "Song", "progress": 1000, "duration": 200000,
            }})
            await asyncio.sleep(0.05)
            await old.close()
            await asyncio.sleep(0.2)
            assert await self._is_playing(tc) is True
            await new.close()

    async def test_last_controller_disconnect_pauses(self, tc) -> None:
        with patch.object(routes, "DISCONNECT_PAUSE_GRACE_SECONDS", 0.05), \
             patch.object(routes, "save_source_state_debounced", new_callable=AsyncMock):
            ws = await tc.ws_connect('/?client=spicetify' + self.V2)
            await ws.send_json({"type": "nowPlaying", "state": {
                "isPlaying": True, "trackName": "Song", "progress": 1000, "duration": 200000,
            }})
            await asyncio.sleep(0.05)
            await ws.close()
            await asyncio.sleep(0.2)
            assert await self._is_playing(tc) is False

    async def test_source_status_is_broadcast(self, tc) -> None:
        with patch.object(routes, "DISCONNECT_PAUSE_GRACE_SECONDS", 0.05), \
             patch.object(routes, "save_source_state_debounced", new_callable=AsyncMock):
            observer = await tc.ws_connect('/?client=obs' + self.V2)
            source = await tc.ws_connect('/?client=spicetify' + self.V2)
            messages = []
            for _ in range(10):
                try:
                    messages.append(await asyncio.wait_for(observer.receive_json(), timeout=1.0))
                except asyncio.TimeoutError:
                    break
            connected = [
                m for m in messages
                if m["type"] == "sourceStatus" and m["state"]["connected"]
            ]
            assert connected and connected[0]["source"] == "spotify"
            await source.close()
            await observer.close()

    async def test_v1_client_is_rejected(self, tc) -> None:
        ws = await tc.ws_connect('/?client=website&protocolVersion=1')
        message = await asyncio.wait_for(ws.receive_json(), timeout=1.0)
        assert message["type"] == "error"
        assert message["code"] == "protocol_version"
        await ws.close()


class TestStreamDeckClient:
    """The Stream Deck plugin is the primary client: no Origin header, commands
    must reach only the source client, and the sender must not get an echo."""

    V2 = "&protocolVersion=2"

    @pytest.fixture
    async def tc(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        app = web.Application(middlewares=[routes.security_middleware])
        app.router.add_get('/', routes.websocket_handler)
        app.router.add_get('/api/state', routes.handle_state)
        async with TestClient(TestServer(app)) as client:
            yield client

    @staticmethod
    async def _next_type(ws, wanted: str, timeout: float = 1.0) -> dict[str, Any]:
        while True:
            message: dict[str, Any] = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
            if message.get("type") == wanted:
                return message

    @staticmethod
    async def _drain(ws) -> None:
        while True:
            try:
                await asyncio.wait_for(ws.receive_json(), timeout=0.05)
            except asyncio.TimeoutError:
                return

    async def test_connect_without_origin_gets_config_and_state(self, tc) -> None:
        deck = await tc.ws_connect('/?client=streamdeck' + self.V2)
        config_msg = await self._next_type(deck, "config")
        assert config_msg["v"] == 2
        state = await self._next_type(deck, "nowPlaying")
        assert state["source"] == "spotify" and "state" in state
        sc_state = await self._next_type(deck, "nowPlaying")
        assert sc_state["source"] == "soundcloud"
        await self._next_type(deck, "lyrics")
        await self._next_type(deck, "sourceStatus")
        await deck.close()

    async def test_command_reaches_source_and_not_sender(self, tc) -> None:
        deck = await tc.ws_connect('/?client=streamdeck' + self.V2)
        ext = await tc.ws_connect('/?client=spicetify' + self.V2)
        # Drain the sourceStatus(connected) broadcast and the initial snapshots
        # before asserting on new traffic.
        await self._drain(ext)
        await self._drain(deck)
        await deck.send_json({"type": "command", "source": "spotify", "command": "togglePlay"})
        command = await self._next_type(ext, "command")
        assert command["command"] == "togglePlay"
        assert command["source"] == "spotify"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(deck.receive_json(), timeout=0.3)
        await deck.close()
        await ext.close()

    async def test_soundcloud_command_routes_to_soundcloud_only(self, tc) -> None:
        deck = await tc.ws_connect('/?client=streamdeck' + self.V2)
        sc = await tc.ws_connect('/?client=soundcloud' + self.V2)
        await self._next_type(sc, "sourceStatus")
        await deck.send_json({"type": "command", "source": "soundcloud", "command": "next"})
        command = await self._next_type(sc, "command")
        assert command["command"] == "next"
        assert command["source"] == "soundcloud"
        await deck.close()
        await sc.close()

async def test_state_endpoint_survives_poisoned_state() -> None:
    # Defensive path: even if something writes junk, /api/state must answer.
    st.state["isPlaying"] = True
    st.state["trackProgress"] = "lol"
    st.state["trackDuration"] = "nope"
    resp = await routes.handle_state(MagicMock())
    body: dict[str, Any] = json.loads(resp.body)
    assert resp.status == 200
    assert body["spotify"]["progress"] == 0
    assert body["spotify"]["duration"] == 0
