import asyncio
import json
import os
import sqlite3
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module-under-test. It has module-level side effects (logging, config load, etc.)
# but that's fine — we just need to isolate state between tests.
import server

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test so tests don't interfere."""
    server.state.update({
        "volume": 0.5,
        "isPlaying": False,
        "currentTrack": {
            "trackName": "No song playing",
            "artistName": "",
            "albumName": "",
            "trackUri": "",
            "albumUri": "",
            "albumArtUrl": ""
        },
        "trackProgress": 0,
        "trackDuration": 0,
        "trackProgressStartTimestamp": 0,
        "backgroundPalette": None,
        "isShuffling": False,
        "repeatStatus": 0,
        "isLiked": False,
        "spicetifyClient": None,
        "lyrics": {
            "trackUri": "",
            "synced": [],
            "plain": "",
            "available": False,
            "instrumental": False,
            "loading": False
        }
    })
    server.CLIENTS.clear()
    server._save_timer = None
    yield

@pytest.fixture
def mock_ws():
    """A mock WebSocket object."""
    ws = AsyncMock()
    ws.send_str = AsyncMock()
    return ws

@pytest.fixture
def temp_db():
    """Create a temporary SQLite DB for lyrics cache tests."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------

class TestParseSyncedLyrics:
    def test_basic(self):
        lrc = "[00:12.34]Hello world\n[00:15.00]Second line"
        result = server.parse_synced_lyrics(lrc)
        assert len(result) == 2
        assert result[0]["time"] == 12340
        assert result[0]["text"] == "Hello world"
        assert result[1]["time"] == 15000

    def test_empty(self):
        assert server.parse_synced_lyrics("") == []
        assert server.parse_synced_lyrics("no tags here") == []

    def test_comma_separator(self):
        result = server.parse_synced_lyrics("[00:01,500]Comma separated")
        assert result[0]["time"] == 1500

    def test_sorts_output(self):
        result = server.parse_synced_lyrics("[00:10.00]Later\n[00:05.00]Earlier")
        assert result[0]["time"] == 5000
        assert result[1]["time"] == 10000

    def test_strips_text(self):
        result = server.parse_synced_lyrics("[00:01.00]  padded text  ")
        assert result[0]["text"] == "padded text"

    def test_hundredths(self):
        result = server.parse_synced_lyrics("[01:30.50]Two digit")
        assert result[0]["time"] == 90500

    def test_thousandths(self):
        result = server.parse_synced_lyrics("[01:30.500]Three digit")
        assert result[0]["time"] == 90500


def test_get_current_save_data_shape():
    server.state["volume"] = 0.75
    server.state["isPlaying"] = True
    server.state["currentTrack"]["trackName"] = "Test"
    data = server.get_current_save_data()
    assert data == {
        "volume": 0.75,
        "isPlaying": True,
        "currentTrack": server.state["currentTrack"],
        "isShuffling": False,
        "repeatStatus": 0,
        "isLiked": False
    }


def test_write_state_to_disk(tmp_path):
    state_file = tmp_path / "state.json"
    data = {"volume": 0.5, "isPlaying": False}
    with patch.object(server, "STATE_FILE", str(state_file)):
        server._write_state_to_disk(data)
    assert state_file.exists()
    assert json.loads(state_file.read_text()) == data


# ---------------------------------------------------------------------------
# Lyrics cache tests
# ---------------------------------------------------------------------------

class TestLyricsCache:
    @pytest.fixture(autouse=True)
    def setup_db(self, temp_db):
        """Create the lyrics_cache table in the temp DB."""
        self.db_path = temp_db
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lyrics_cache (
                artist_name TEXT NOT NULL,
                track_name TEXT NOT NULL,
                album_name TEXT NOT NULL,
                duration INTEGER NOT NULL,
                synced_lyrics TEXT,
                plain_lyrics TEXT,
                instrumental INTEGER NOT NULL DEFAULT 0,
                fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (artist_name, track_name, album_name, duration)
            )
        """)
        conn.commit()
        conn.close()

    def _cache_params(self):
        return {
            "artist_name": "Artist",
            "track_name": "Song",
            "album_name": "Album",
            "duration": 200
        }

    def test_cache_miss(self):
        with patch.object(server, "LYRICS_CACHE_DB", self.db_path):
            result = server.get_cached_lyrics(self._cache_params())
        assert result is None

    def test_cache_roundtrip(self):
        params = self._cache_params()
        synced = "[00:01.00]Line one"
        plain = "Plain text"
        with patch.object(server, "LYRICS_CACHE_DB", self.db_path):
            server.set_cached_lyrics(params, synced, plain, False)
            result = server.get_cached_lyrics(params)
        assert result is not None
        assert result[0] == synced
        assert result[1] == plain
        assert result[2] == 0

    def test_cache_instrumental_flag(self):
        params = self._cache_params()
        with patch.object(server, "LYRICS_CACHE_DB", self.db_path):
            server.set_cached_lyrics(params, None, None, True)
            result = server.get_cached_lyrics(params)
        assert result[2] == 1

    def test_cache_overwrite(self):
        """INSERT OR REPLACE should update existing rows."""
        params = self._cache_params()
        with patch.object(server, "LYRICS_CACHE_DB", self.db_path):
            server.set_cached_lyrics(params, "old", "old_plain", False)
            server.set_cached_lyrics(params, "new", "new_plain", True)
            result = server.get_cached_lyrics(params)
        assert result[0] == "new"
        assert result[1] == "new_plain"
        assert result[2] == 1


# ---------------------------------------------------------------------------
# Message handler tests
# ---------------------------------------------------------------------------

class TestMessageHandlers:
    async def test_handle_volume_update_absolute(self, mock_ws):
        server.state["volume"] = 0.3
        with patch.object(server, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_volume_update(mock_ws, {"type": "volumeUpdate", "volume": 0.8})
        assert server.state["volume"] == 0.8

    async def test_handle_volume_update_up(self, mock_ws):
        server.state["volume"] = 0.5
        with patch.object(server, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_volume_update(mock_ws, {"type": "volumeUpdate", "command": "volumeUp"})
        assert server.state["volume"] == pytest.approx(0.55)

    async def test_handle_volume_update_down(self, mock_ws):
        server.state["volume"] = 0.5
        with patch.object(server, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_volume_update(mock_ws, {"type": "volumeUpdate", "command": "volumeDown"})
        assert server.state["volume"] == pytest.approx(0.45)

    async def test_handle_volume_update_clamp_max(self, mock_ws):
        server.state["volume"] = 0.98
        with patch.object(server, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_volume_update(mock_ws, {"type": "volumeUpdate", "command": "volumeUp"})
        assert server.state["volume"] == 1.0

    async def test_handle_volume_update_clamp_min(self, mock_ws):
        server.state["volume"] = 0.02
        with patch.object(server, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_volume_update(mock_ws, {"type": "volumeUpdate", "command": "volumeDown"})
        assert server.state["volume"] == 0.0

    async def test_handle_volume_update_absolute_clamp_max(self, mock_ws):
        with patch.object(server, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_volume_update(mock_ws, {"type": "volumeUpdate", "volume": 5.0})
        assert server.state["volume"] == 1.0

    async def test_handle_volume_update_absolute_clamp_min(self, mock_ws):
        with patch.object(server, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_volume_update(mock_ws, {"type": "volumeUpdate", "volume": -10.0})
        assert server.state["volume"] == 0.0

    async def test_handle_playback_update(self, mock_ws):
        with patch.object(server, "broadcast_playback_update", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_playback_update(mock_ws, {"type": "playbackUpdate", "isPlaying": True, "progress": 5000})
        assert server.state["isPlaying"] is True
        assert server.state["trackProgress"] == 5000

    async def test_handle_shuffle_update(self, mock_ws):
        with patch.object(server, "broadcast", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_shuffle_update(mock_ws, {"type": "shuffleUpdate", "isShuffling": True})
        assert server.state["isShuffling"] is True

    async def test_handle_repeat_update(self, mock_ws):
        with patch.object(server, "broadcast", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_repeat_update(mock_ws, {"type": "repeatUpdate", "repeatStatus": 2})
        assert server.state["repeatStatus"] == 2

    async def test_handle_like_update(self, mock_ws):
        with patch.object(server, "broadcast", new_callable=AsyncMock):
            with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                await server.handle_like_update(mock_ws, {"type": "likeUpdate", "isLiked": True})
        assert server.state["isLiked"] is True

    async def test_handle_track_update_new_track(self, mock_ws):
        with patch.object(server, "broadcast_current_state", new_callable=AsyncMock):
            with patch.object(server, "broadcast_lyrics_update", new_callable=AsyncMock):
                with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                    await server.handle_track_update(mock_ws, {
                        "type": "trackUpdate",
                        "trackName": "New Song",
                        "artistName": "New Artist",
                        "trackUri": "spotify:track:new",
                        "duration": 200000,
                        "progress": 0
                    })
        assert server.state["currentTrack"]["trackName"] == "New Song"
        assert server.state["currentTrack"]["artistName"] == "New Artist"
        assert server.state["currentTrack"]["trackUri"] == "spotify:track:new"
        assert server.state["trackDuration"] == 200000
        assert server.state["lyrics"]["loading"] is True

    async def test_handle_track_update_same_track_no_lyrics_fetch(self, mock_ws):
        """Same URI should NOT trigger a lyrics fetch."""
        server.state["currentTrack"]["trackUri"] = "spotify:track:existing"
        server.state["lyrics"]["loading"] = False
        with patch.object(server, "broadcast_current_state", new_callable=AsyncMock):
            with patch.object(server, "broadcast_lyrics_update", new_callable=AsyncMock) as mock_lyrics:
                with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                    await server.handle_track_update(mock_ws, {
                        "type": "trackUpdate",
                        "trackName": "Updated",
                        "artistName": "Artist",
                        "trackUri": "spotify:track:existing",
                        "duration": 180000,
                        "progress": 10000
                    })
        mock_lyrics.assert_not_called()
        assert server.state["lyrics"]["loading"] is False

    async def test_handle_track_update_batched_fields(self, mock_ws):
        """StateUpdate can include volume, shuffle, repeat, like alongside track info."""
        with patch.object(server, "broadcast_current_state", new_callable=AsyncMock):
            with patch.object(server, "broadcast_lyrics_update", new_callable=AsyncMock):
                with patch.object(server, "save_state_to_file_debounced", new_callable=AsyncMock):
                    await server.handle_track_update(mock_ws, {
                        "type": "stateUpdate",
                        "trackUri": "spotify:track:batch",
                        "trackName": "Batch",
                        "volume": 0.9,
                        "isShuffling": True,
                        "repeatStatus": 1,
                        "isLiked": True,
                        "duration": 150000
                    })
        assert server.state["volume"] == 0.9
        assert server.state["isShuffling"] is True
        assert server.state["repeatStatus"] == 1
        assert server.state["isLiked"] is True

    async def test_handle_progress_update(self, mock_ws):
        with patch.object(server, "broadcast_progress_update", new_callable=AsyncMock):
            await server.handle_progress_update(mock_ws, {"type": "progressUpdate", "progress": 30000, "duration": 240000})
        assert server.state["trackProgress"] == 30000
        assert server.state["trackDuration"] == 240000

    async def test_handle_register_spicetify(self, mock_ws):
        server.CLIENTS[mock_ws] = {"type": "unknown", "remote_ip": "127.0.0.1"}
        await server.handle_register(mock_ws, {"type": "register", "client": "spicetify"})
        assert server.CLIENTS[mock_ws]["type"] == "spicetify"
        assert server.state["spicetifyClient"] is mock_ws

    async def test_handle_register_website(self, mock_ws):
        server.CLIENTS[mock_ws] = {"type": "unknown", "remote_ip": "127.0.0.1"}
        await server.handle_register(mock_ws, {"type": "register", "client": "website"})
        assert server.CLIENTS[mock_ws]["type"] == "website"
        assert server.state["spicetifyClient"] is None

    async def test_handle_playback_control_targets_spicetify(self, mock_ws):
        server.CLIENTS[mock_ws] = {"type": "website", "remote_ip": "127.0.0.1"}
        spicetify_ws = AsyncMock()
        server.CLIENTS[spicetify_ws] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        await server.handle_playback_control(mock_ws, {"type": "playbackControl", "command": "next"})
        spicetify_ws.send_str.assert_called_once()
        sent = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["command"] == "next"

    async def test_handle_like_command_targets_spicetify(self, mock_ws):
        spicetify_ws = AsyncMock()
        server.CLIENTS[spicetify_ws] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        await server.handle_like_command(mock_ws, {"type": "like"})
        spicetify_ws.send_str.assert_called_once()
        sent = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["command"] == "like"


# ---------------------------------------------------------------------------
# handle_message input validation tests
# ---------------------------------------------------------------------------

class TestHandleMessage:
    async def test_invalid_json(self, mock_ws):
        with patch.object(server.logger, "warning") as mock_warn:
            await server.handle_message(mock_ws, "not json {{{")
        mock_warn.assert_called_once()
        assert "invalid JSON" in mock_warn.call_args[0][0]

    async def test_non_dict_json(self, mock_ws):
        with patch.object(server.logger, "warning") as mock_warn:
            await server.handle_message(mock_ws, json.dumps([1, 2, 3]))
        mock_warn.assert_called_once()
        assert "non-object" in mock_warn.call_args[0][0]

    async def test_missing_type_field(self, mock_ws):
        with patch.object(server.logger, "warning") as mock_warn:
            await server.handle_message(mock_ws, json.dumps({"volume": 0.5}))
        mock_warn.assert_called_once()
        assert "invalid type field" in mock_warn.call_args[0][0]

    async def test_non_string_type_field(self, mock_ws):
        with patch.object(server.logger, "warning") as mock_warn:
            await server.handle_message(mock_ws, json.dumps({"type": 123}))
        mock_warn.assert_called_once()
        assert "invalid type field" in mock_warn.call_args[0][0]

    async def test_unknown_type(self, mock_ws):
        with patch.object(server.logger, "warning") as mock_warn:
            await server.handle_message(mock_ws, json.dumps({"type": "fooBar"}))
        mock_warn.assert_called_once()
        assert "fooBar" in mock_warn.call_args[0][0]

    async def test_valid_message_dispatches_handler(self, mock_ws):
        """A valid message should call the correct handler via MESSAGE_HANDLERS."""
        mock_handler = AsyncMock()
        original = server.MESSAGE_HANDLERS["volumeUpdate"]
        server.MESSAGE_HANDLERS["volumeUpdate"] = mock_handler
        try:
            await server.handle_message(mock_ws, json.dumps({"type": "volumeUpdate", "volume": 0.7}))
            mock_handler.assert_called_once()
        finally:
            server.MESSAGE_HANDLERS["volumeUpdate"] = original


# ---------------------------------------------------------------------------
# Broadcasting tests
# ---------------------------------------------------------------------------

class TestBroadcast:
    async def test_no_clients_noop(self):
        server.CLIENTS.clear()
        # Should not raise
        await server.broadcast({"type": "test"})

    async def test_broadcast_to_all(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        server.CLIENTS[ws1] = {"type": "website", "remote_ip": "127.0.0.1"}
        server.CLIENTS[ws2] = {"type": "obs", "remote_ip": "127.0.0.1"}
        await server.broadcast({"type": "test"})
        ws1.send_str.assert_called_once()
        ws2.send_str.assert_called_once()

    async def test_broadcast_exclude_ws(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        server.CLIENTS[ws1] = {"type": "website", "remote_ip": "127.0.0.1"}
        server.CLIENTS[ws2] = {"type": "obs", "remote_ip": "127.0.0.1"}
        await server.broadcast({"type": "test"}, exclude_ws=ws1)
        ws1.send_str.assert_not_called()
        ws2.send_str.assert_called_once()

    async def test_broadcast_target_type(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()
        server.CLIENTS[ws1] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        server.CLIENTS[ws2] = {"type": "website", "remote_ip": "127.0.0.1"}
        server.CLIENTS[ws3] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        await server.broadcast({"type": "test"}, target_type="spicetify")
        assert ws1.send_str.called
        ws2.send_str.assert_not_called()
        assert ws3.send_str.called

    async def test_broadcast_removes_dead_clients(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.send_str = AsyncMock(side_effect=ConnectionError("dead"))
        server.CLIENTS[ws1] = {"type": "website", "remote_ip": "127.0.0.1"}
        server.CLIENTS[ws2] = {"type": "obs", "remote_ip": "127.0.0.1"}
        await server.broadcast({"type": "test"})
        assert ws1 not in server.CLIENTS
        assert ws2 in server.CLIENTS


# ---------------------------------------------------------------------------
# Config endpoint tests (aiohttp test client)
# ---------------------------------------------------------------------------

class TestConfigEndpoint:
    async def test_cors_with_wildcard_origin(self):
        """When '*' is in allowedOrigins, response header should be '*'."""
        req = MagicMock()
        req.headers = {}
        orig = server.config["allowedOrigins"].copy()
        server.config["allowedOrigins"] = ["*"]
        try:
            resp = await server.handle_config(req)
        finally:
            server.config["allowedOrigins"] = orig
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    async def test_cors_matching_origin(self):
        """When a specific origin matches, return that origin."""
        req = MagicMock()
        req.headers = {"Origin": "http://localhost:3000"}
        orig = server.config["allowedOrigins"].copy()
        server.config["allowedOrigins"] = ["http://localhost:3000"]
        try:
            resp = await server.handle_config(req)
        finally:
            server.config["allowedOrigins"] = orig
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"

    async def test_cors_non_matching_origin(self):
        """When origin doesn't match, return first in allowlist."""
        req = MagicMock()
        req.headers = {"Origin": "http://evil.com"}
        orig = server.config["allowedOrigins"].copy()
        server.config["allowedOrigins"] = ["http://localhost:3000"]
        try:
            resp = await server.handle_config(req)
        finally:
            server.config["allowedOrigins"] = orig
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"

    async def test_config_response_body(self):
        req = MagicMock()
        req.headers = {}
        orig_port = server.config["port"]
        orig_vol = server.config["defaultVolume"]
        orig_obs = server.config["enableOBS"]
        server.config["port"] = 9999
        server.config["defaultVolume"] = 0.7
        server.config["enableOBS"] = False
        try:
            resp = await server.handle_config(req)
        finally:
            server.config["port"] = orig_port
            server.config["defaultVolume"] = orig_vol
            server.config["enableOBS"] = orig_obs
        body = resp.body
        data = json.loads(body)
        assert data["port"] == 9999
        assert data["discoveryPort"] == 54321
        assert data["defaultVolume"] == 0.7
        assert data["enableOBS"] is False
        assert data["enableWebsite"] is True
