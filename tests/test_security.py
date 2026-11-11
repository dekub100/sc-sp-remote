"""Host/origin gating and frame limits in server/routes.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import config as cfg
import pytest
import routes


class TestSecurityMiddleware:
    @pytest.fixture
    async def tc(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        app = web.Application(middlewares=[routes.security_middleware])
        app.router.add_get('/api/state', routes.handle_state)
        app.router.add_get('/api/admin/config', routes.handle_admin_config_get)
        app.router.add_post('/api/admin/lyrics/musixmatch-token', routes.handle_admin_mxm_token_refresh)
        app.router.add_get('/ws', routes.websocket_handler)
        async with TestClient(TestServer(app)) as client:
            yield client

    async def test_default_host_is_allowed(self, tc) -> None:
        resp = await tc.get('/api/state')
        assert resp.status == 200

    async def test_rebound_host_is_rejected(self, tc) -> None:
        for host in ("attacker.example", "attacker.example:8888", "evil.test:80"):
            resp = await tc.get('/api/state', headers={"Host": host})
            assert resp.status == 403, host
            resp = await tc.get('/api/admin/config', headers={"Host": host})
            assert resp.status == 403, host

    async def test_private_lan_host_is_allowed(self, tc) -> None:
        resp = await tc.get('/api/state', headers={"Host": "192.168.1.5:8888"})
        assert resp.status == 200

    async def test_configured_allowed_hosts_are_allowed(self, tc) -> None:
        original = list(cfg.config.get("allowedHosts") or [])
        cfg.config["allowedHosts"] = ["myrig.local"]
        try:
            resp = await tc.get('/api/state', headers={"Host": "myrig.local:8888"})
        finally:
            cfg.config["allowedHosts"] = original
        assert resp.status == 200

    async def test_cross_site_post_is_rejected_before_handler(self, tc) -> None:
        with patch("lyrics.refresh_musixmatch_token", new_callable=AsyncMock) as refresh:
            resp = await tc.post('/api/admin/lyrics/musixmatch-token',
                                 headers={"Origin": "https://evil.example"})
            refresh.assert_not_called()
        assert resp.status == 403

    async def test_cross_site_put_is_rejected(self, tc) -> None:
        resp = await tc.put('/api/admin/config', json={"port": 9999},
                            headers={"Origin": "https://evil.example"})
        assert resp.status == 403
        assert cfg.config["port"] != 9999

    async def test_sec_fetch_site_cross_site_is_rejected(self, tc) -> None:
        resp = await tc.post('/api/admin/lyrics/musixmatch-token',
                             headers={"Origin": f"http://127.0.0.1:{tc.server.port}",
                                      "Sec-Fetch-Site": "cross-site"})
        assert resp.status == 403

    async def test_same_origin_post_is_allowed(self, tc) -> None:
        origin = f"http://127.0.0.1:{tc.server.port}"
        with patch("lyrics.refresh_musixmatch_token", new_callable=AsyncMock, return_value="abcdef"):
            resp = await tc.post('/api/admin/lyrics/musixmatch-token', headers={"Origin": origin})
        assert resp.status == 200

    async def test_native_client_without_origin_is_allowed(self, tc) -> None:
        with patch("lyrics.refresh_musixmatch_token", new_callable=AsyncMock, return_value="abcdef"):
            resp = await tc.post('/api/admin/lyrics/musixmatch-token')
        assert resp.status == 200

    def test_admin_peer_must_be_loopback(self) -> None:
        assert routes._is_loopback_peer("127.0.0.1") is True
        assert routes._is_loopback_peer("::1") is True
        assert routes._is_loopback_peer("192.168.1.9") is False
        assert routes._is_loopback_peer("203.0.113.7") is False
        assert routes._is_loopback_peer(None) is False

    def test_wildcard_cors_does_not_open_the_ws_gate(self) -> None:
        original = list(cfg.config["allowedOrigins"])
        cfg.config["allowedOrigins"] = ["*"]
        try:
            request = MagicMock()
            request.headers = {"Origin": "https://evil.example", "Host": "localhost:8888"}
            assert routes._is_foreign_web_origin(request) is True
        finally:
            cfg.config["allowedOrigins"] = original

    def test_lan_origin_ws_is_accepted(self) -> None:
        request = MagicMock()
        request.headers = {"Origin": "http://192.168.1.5:8888", "Host": "192.168.1.5:8888"}
        assert routes._is_foreign_web_origin(request) is False

    def test_mismatched_port_is_foreign(self) -> None:
        # Loopback origins are always allowed (any port); a self-origin match
        # elsewhere must still include the port.
        request = MagicMock()
        request.headers = {"Origin": "http://192.168.1.5:7777", "Host": "192.168.1.5:8888"}
        assert routes._is_foreign_web_origin(request) is True

    async def test_ws_rejects_foreign_web_origin(self) -> None:
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        app = web.Application()
        app.router.add_get('/ws', routes.websocket_handler)
        async with TestClient(TestServer(app)) as tc:
            for origin in ("https://evil.example.com", "http://evil.example.com"):
                resp = await tc.get('/ws', headers={"Origin": origin})
                assert resp.status == 403, f"{origin} should be rejected"

    async def test_ws_allows_known_client_origins(self) -> None:
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        app = web.Application()
        async def ok_handler(request):
            return web.json_response({"foreign": routes._is_foreign_web_origin(request)})
        app.router.add_get('/probe', ok_handler)
        async with TestClient(TestServer(app)) as tc:
            origins = (
                "http://localhost:8888", "http://127.0.0.1:8888",
                "https://soundcloud.com", "https://xpui.app.spotify.com",
                "chrome-extension://abc", "",
            )
            for origin in origins:
                headers = {"Origin": origin} if origin else {}
                resp = await tc.get('/probe', headers=headers)
                data = await resp.json()
                assert data["foreign"] is False, f"{origin!r} wrongly flagged foreign"

        async with TestClient(TestServer(app)) as tc:
            for origin in ("http://localhost:8888", "http://127.0.0.1:8888"):
                resp = await tc.get('/probe', headers={"Origin": origin})
                data = await resp.json()
                assert data["foreign"] is False, f"{origin!r} wrongly flagged foreign"


class TestWebSocketMessageLimit:
    async def test_oversized_message_closes_with_1009(self) -> None:
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        app = web.Application()
        app.router.add_get('/', routes.websocket_handler)
        async with TestClient(TestServer(app)) as tc:
            ws = await tc.ws_connect('/?client=streamdeck&protocolVersion=2')
            await ws.send_str("x" * (routes.MAX_WS_MESSAGE_BYTES + 1))
            for _ in range(20):
                msg = await ws.receive(timeout=2)
                if msg.type == web.WSMsgType.CLOSE:
                    assert msg.data == 1009
                    break
                assert msg.type == web.WSMsgType.TEXT
            else:
                pytest.fail("server never closed the oversized connection")
            await ws.close()
