import json
import os
import sqlite3
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import broadcast
import config as cfg
import handlers
import lyrics
import pytest
import routes
import state as st

import server


@pytest.fixture(autouse=True)
def reset_state():
    st.state.update({
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
        "isShuffling": False,
        "repeatStatus": 0,
        "isLiked": False,
        "scTrack": "No song playing",
        "scArtist": "",
        "scAlbum": "",
        "scId": "",
        "scCoverUrl": "",
        "scIsPlaying": False,
        "scProgressMs": 0,
        "scDurationMs": 0,
        "scProgressStartTimestamp": 0,
        "scVolume": 0.5,
        "scIsLiked": False,
        "lyrics": {
            "trackUri": "",
            "synced": [],
            "plain": "",
            "available": False,
            "instrumental": False,
            "loading": False
        },
    })
    broadcast.CLIENTS.clear()
    broadcast.set_spicetify_client(None)
    broadcast.set_soundcloud_client(None)
    st._spotify_save_timer = None
    st._sc_save_timer = None
    yield


@pytest.fixture
def mock_ws():
    ws: AsyncMock = AsyncMock()
    ws.send_str = AsyncMock()
    return ws


@pytest.fixture
def temp_db():
    fd: int
    path: str
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    server._close_connection()
    os.unlink(path)


class TestParseSyncedLyrics:
    def test_basic(self) -> None:
        lrc: str = "[00:12.34]Hello world\n[00:15.00]Second line"
        result: list[dict[str, Any]] = lyrics.parse_synced_lyrics(lrc)
        assert len(result) == 2
        assert result[0]["time"] == 12340
        assert result[0]["text"] == "Hello world"
        assert result[1]["time"] == 15000

    def test_empty(self) -> None:
        assert lyrics.parse_synced_lyrics("") == []
        assert lyrics.parse_synced_lyrics("no tags here") == []

    def test_comma_separator(self) -> None:
        result: list[dict[str, Any]] = lyrics.parse_synced_lyrics("[00:01,500]Comma separated")
        assert result[0]["time"] == 1500

    def test_sorts_output(self) -> None:
        result: list[dict[str, Any]] = lyrics.parse_synced_lyrics("[00:10.00]Later\n[00:05.00]Earlier")
        assert result[0]["time"] == 5000
        assert result[1]["time"] == 10000

    def test_strips_text(self) -> None:
        result: list[dict[str, Any]] = lyrics.parse_synced_lyrics("[00:01.00]  padded text  ")
        assert result[0]["text"] == "padded text"

    def test_hundredths(self) -> None:
        result: list[dict[str, Any]] = lyrics.parse_synced_lyrics("[01:30.50]Two digit")
        assert result[0]["time"] == 90500

    def test_thousandths(self) -> None:
        result: list[dict[str, Any]] = lyrics.parse_synced_lyrics("[01:30.500]Three digit")
        assert result[0]["time"] == 90500


def test_get_spotify_save_data_shape() -> None:
    st.state["volume"] = 0.75
    st.state["isPlaying"] = True
    st.state["currentTrack"]["trackName"] = "Test"
    data: dict[str, Any] = st.get_spotify_save_data()
    assert data == {
        "volume": 0.75,
        "isPlaying": True,
        "currentTrack": st.state["currentTrack"],
        "trackDuration": 0,
        "isShuffling": False,
        "repeatStatus": 0,
        "isLiked": False
    }


def test_write_spotify_state_to_disk(tmp_path: Any) -> None:
    state_file = tmp_path / "state_spotify.json"
    data: dict[str, Any] = {"volume": 0.5, "isPlaying": False}
    with patch.object(server, "STATE_FILE", str(state_file)):
        server._write_spotify_state_to_disk(data)
    assert state_file.exists()
    assert json.loads(state_file.read_text()) == data


class TestLyricsCache:
    @pytest.fixture(autouse=True)
    def setup_db(self, temp_db: Any) -> None:
        self.db_path = temp_db
        conn: sqlite3.Connection = sqlite3.connect(self.db_path)
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

    def _cache_params(self) -> dict[str, Any]:
        return {
            "artist_name": "Artist",
            "track_name": "Song",
            "album_name": "Album",
            "duration": 200
        }

    def test_cache_miss(self) -> None:
        with patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            result: Any = lyrics.get_cached_lyrics(self._cache_params())
        assert result is None

    def test_cache_roundtrip(self) -> None:
        params: dict[str, Any] = self._cache_params()
        synced: str = "[00:01.00]Line one"
        plain: str = "Plain text"
        with patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            lyrics.set_cached_lyrics(params, synced, plain, False)
            result: Any = lyrics.get_cached_lyrics(params)
        assert result is not None
        assert result[0] == synced
        assert result[1] == plain
        assert result[2] == 0

    def test_cache_instrumental_flag(self) -> None:
        params = self._cache_params()
        with patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            lyrics.set_cached_lyrics(params, None, None, True)
            result = lyrics.get_cached_lyrics(params)
        assert result[2] == 1

    def test_cache_overwrite(self) -> None:
        params = self._cache_params()
        with patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            lyrics.set_cached_lyrics(params, "old", "old_plain", False)
            lyrics.set_cached_lyrics(params, "new", "new_plain", True)
            result = lyrics.get_cached_lyrics(params)
        assert result[0] == "new"
        assert result[1] == "new_plain"
        assert result[2] == 1


class TestLyricsSession:
    async def test_close_session_closes_and_clears(self) -> None:
        mock_session = AsyncMock()
        with patch("lyrics._session", mock_session):
            await server._close_session()
        mock_session.close.assert_awaited_once()

    async def test_close_session_noop_when_none(self) -> None:
        with patch("lyrics._session", None):
            await server._close_session()


class TestMessageHandlers:
    async def test_handle_spotify_volume_update_absolute(self, mock_ws: AsyncMock) -> None:
        st.state["volume"] = 0.3
        with patch.object(broadcast, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_volume_update(mock_ws, {"type": "volumeUpdate", "volume": 0.8})
        assert st.state["volume"] == 0.8

    async def test_handle_spotify_volume_update_up(self, mock_ws: AsyncMock) -> None:
        st.state["volume"] = 0.5
        with patch.object(broadcast, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_volume_update(mock_ws, {"type": "volumeUpdate", "command": "volumeUp"})
        assert st.state["volume"] == pytest.approx(0.55)

    async def test_handle_spotify_volume_update_down(self, mock_ws: AsyncMock) -> None:
        st.state["volume"] = 0.5
        with patch.object(broadcast, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_volume_update(mock_ws, {"type": "volumeUpdate", "command": "volumeDown"})
        assert st.state["volume"] == pytest.approx(0.45)

    async def test_handle_spotify_volume_update_clamp_max(self, mock_ws: AsyncMock) -> None:
        st.state["volume"] = 0.98
        with patch.object(broadcast, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_volume_update(mock_ws, {"type": "volumeUpdate", "command": "volumeUp"})
        assert st.state["volume"] == 1.0

    async def test_handle_spotify_volume_update_clamp_min(self, mock_ws: AsyncMock) -> None:
        st.state["volume"] = 0.02
        with patch.object(broadcast, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_volume_update(mock_ws, {"type": "volumeUpdate", "command": "volumeDown"})
        assert st.state["volume"] == 0.0

    async def test_handle_spotify_volume_update_absolute_clamp_max(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_volume_update(mock_ws, {"type": "volumeUpdate", "volume": 5.0})
        assert st.state["volume"] == 1.0

    async def test_handle_spotify_volume_update_absolute_clamp_min(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast_volume_update", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_volume_update(mock_ws, {"type": "volumeUpdate", "volume": -10.0})
        assert st.state["volume"] == 0.0

    async def test_handle_spotify_playback_update(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast_playback_update", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_playback_update(mock_ws, {"type": "playbackUpdate", "isPlaying": True, "progress": 5000})
        assert st.state["isPlaying"] is True
        assert st.state["trackProgress"] == 5000

    async def test_handle_spotify_shuffle_update(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_shuffle_update(mock_ws, {"type": "shuffleUpdate", "isShuffling": True})
        assert st.state["isShuffling"] is True

    async def test_handle_spotify_repeat_update(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_repeat_update(mock_ws, {"type": "repeatUpdate", "repeatStatus": 2})
        assert st.state["repeatStatus"] == 2

    async def test_handle_spotify_like_update(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast", new_callable=AsyncMock):
            with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                await handlers.handle_spotify_like_update(mock_ws, {"type": "likeUpdate", "isLiked": True})
        assert st.state["isLiked"] is True

    async def test_handle_spotify_state_update_new_track(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast_spotify_state", new_callable=AsyncMock):
            with patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock):
                with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                    await handlers.handle_spotify_state_update(mock_ws, {
                        "type": "trackUpdate",
                        "trackName": "New Song",
                        "artistName": "New Artist",
                        "trackUri": "spotify:track:new",
                        "duration": 200000,
                        "progress": 0
                    })
        assert st.state["currentTrack"]["trackName"] == "New Song"
        assert st.state["currentTrack"]["artistName"] == "New Artist"
        assert st.state["currentTrack"]["trackUri"] == "spotify:track:new"
        assert st.state["trackDuration"] == 200000
        assert st.state["lyrics"]["loading"] is True

    async def test_handle_spotify_state_update_same_track_no_lyrics_fetch(self, mock_ws: AsyncMock) -> None:
        st.state["currentTrack"]["trackUri"] = "spotify:track:existing"
        st.state["lyrics"]["loading"] = False
        with patch.object(broadcast, "broadcast_spotify_state", new_callable=AsyncMock):
            with patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock) as mock_lyrics:
                with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                    await handlers.handle_spotify_state_update(mock_ws, {
                        "type": "trackUpdate",
                        "trackName": "Updated",
                        "artistName": "Artist",
                        "trackUri": "spotify:track:existing",
                        "duration": 180000,
                        "progress": 10000
                    })
        mock_lyrics.assert_not_called()
        assert st.state["lyrics"]["loading"] is False

    async def test_handle_spotify_state_update_batched_fields(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast_spotify_state", new_callable=AsyncMock):
            with patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock):
                with patch.object(st, "save_spotify_state_debounced", new_callable=AsyncMock):
                    await handlers.handle_spotify_state_update(mock_ws, {
                        "type": "stateUpdate",
                        "trackUri": "spotify:track:batch",
                        "trackName": "Batch",
                        "volume": 0.9,
                        "isShuffling": True,
                        "repeatStatus": 1,
                        "isLiked": True,
                        "duration": 150000
                    })
        assert st.state["volume"] == 0.9
        assert st.state["isShuffling"] is True
        assert st.state["repeatStatus"] == 1
        assert st.state["isLiked"] is True

    async def test_handle_spotify_progress_update(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast_progress_update", new_callable=AsyncMock):
            await handlers.handle_spotify_progress_update(mock_ws, {"type": "progressUpdate", "progress": 30000, "duration": 240000})
        assert st.state["trackProgress"] == 30000
        assert st.state["trackDuration"] == 240000

    async def test_handle_register_spicetify(self, mock_ws: AsyncMock) -> None:
        broadcast.CLIENTS[mock_ws] = {"type": "unknown", "remote_ip": "127.0.0.1"}
        await handlers.handle_register(mock_ws, {"type": "register", "client": "spicetify"})
        assert broadcast.CLIENTS[mock_ws]["type"] == "spicetify"
        assert broadcast.get_spicetify_client() is mock_ws

    async def test_handle_register_website(self, mock_ws: AsyncMock) -> None:
        broadcast.CLIENTS[mock_ws] = {"type": "unknown", "remote_ip": "127.0.0.1"}
        await handlers.handle_register(mock_ws, {"type": "register", "client": "website"})
        assert broadcast.CLIENTS[mock_ws]["type"] == "website"
        assert broadcast.get_spicetify_client() is None

    async def test_handle_register_unknown(self, mock_ws: AsyncMock) -> None:
        broadcast.CLIENTS[mock_ws] = {"type": "unknown", "remote_ip": "127.0.0.1"}
        with patch.object(handlers.logger, "warning") as mock_warn:
            await handlers.handle_register(mock_ws, {"type": "register", "client": "foobar"})
        assert broadcast.CLIENTS[mock_ws]["type"] == "unknown"
        mock_warn.assert_called_once()
        assert "foobar" in mock_warn.call_args[0][0]

    async def test_handle_playback_control_targets_spicetify(self, mock_ws: AsyncMock) -> None:
        broadcast.CLIENTS[mock_ws] = {"type": "website", "remote_ip": "127.0.0.1"}
        spicetify_ws: AsyncMock = AsyncMock()
        broadcast.CLIENTS[spicetify_ws] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        await handlers.handle_playback_control(mock_ws, {"type": "playbackControl", "command": "next"})
        spicetify_ws.send_str.assert_called_once()
        sent: dict[str, Any] = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["command"] == "next"

    async def test_handle_like_command_targets_spotify_by_default(self, mock_ws: AsyncMock) -> None:
        spicetify_ws = AsyncMock()
        broadcast.CLIENTS[spicetify_ws] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        await handlers.handle_like_command(mock_ws, {"type": "like"})
        spicetify_ws.send_str.assert_called_once()
        sent = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["command"] == "like"

    async def test_handle_like_command_targets_soundcloud(self, mock_ws: AsyncMock) -> None:
        sc_ws = AsyncMock()
        broadcast.CLIENTS[sc_ws] = {"type": "soundcloud", "remote_ip": "127.0.0.1"}
        await handlers.handle_like_command(mock_ws, {"type": "like", "source": "soundcloud"})
        sc_ws.send_str.assert_called_once()
        sent = json.loads(sc_ws.send_str.call_args[0][0])
        assert sent["command"] == "like"

    async def test_handle_error_broadcasts_message(self, mock_ws: AsyncMock) -> None:
        with patch("handlers.broadcast", new_callable=AsyncMock) as mock_broadcast:
            with patch.object(handlers.logger, "warning"):
                await handlers.handle_error(mock_ws, {"type": "error", "message": "Something broke"})
        mock_broadcast.assert_called_once_with({"type": "error", "message": "Something broke"})

    async def test_handle_error_defaults_message(self, mock_ws: AsyncMock) -> None:
        with patch("handlers.broadcast", new_callable=AsyncMock) as mock_broadcast:
            with patch.object(handlers.logger, "warning"):
                await handlers.handle_error(mock_ws, {"type": "error"})
        mock_broadcast.assert_called_once_with({"type": "error", "message": "Unknown error"})

    async def test_handle_error_logs_warning(self, mock_ws: AsyncMock) -> None:
        with patch("handlers.broadcast", new_callable=AsyncMock):
            with patch.object(handlers.logger, "warning") as mock_warn:
                await handlers.handle_error(mock_ws, {"type": "error", "message": "fail"})
        mock_warn.assert_called_once_with("Extension error: fail")


class TestHandleMessage:
    async def test_invalid_json(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "warning") as mock_warn:
            await handlers.handle_message(mock_ws, "not json {{{")
        mock_warn.assert_called_once()
        assert "invalid JSON" in mock_warn.call_args[0][0]

    async def test_non_dict_json(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "warning") as mock_warn:
            await handlers.handle_message(mock_ws, json.dumps([1, 2, 3]))
        mock_warn.assert_called_once()
        assert "non-object" in mock_warn.call_args[0][0]

    async def test_missing_type_field(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "warning") as mock_warn:
            await handlers.handle_message(mock_ws, json.dumps({"volume": 0.5}))
        mock_warn.assert_called_once()
        assert "invalid type field" in mock_warn.call_args[0][0]

    async def test_non_string_type_field(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "warning") as mock_warn:
            await handlers.handle_message(mock_ws, json.dumps({"type": 123}))
        mock_warn.assert_called_once()
        assert "invalid type field" in mock_warn.call_args[0][0]

    async def test_unknown_type(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "warning") as mock_warn:
            await handlers.handle_message(mock_ws, json.dumps({"type": "fooBar"}))
        mock_warn.assert_called_once()
        assert "fooBar" in mock_warn.call_args[0][0]

    async def test_valid_message_dispatches_handler(self, mock_ws: AsyncMock) -> None:
        mock_handler: AsyncMock = AsyncMock()
        original: Any = handlers.MESSAGE_HANDLERS["volumeUpdate"]
        handlers.MESSAGE_HANDLERS["volumeUpdate"] = mock_handler
        try:
            await handlers.handle_message(mock_ws, json.dumps({"type": "volumeUpdate", "volume": 0.7}))
            mock_handler.assert_called_once()
        finally:
            handlers.MESSAGE_HANDLERS["volumeUpdate"] = original


class TestBroadcast:
    async def test_no_clients_noop(self) -> None:
        broadcast.CLIENTS.clear()
        await broadcast.broadcast({"type": "test"})

    async def test_broadcast_to_all(self) -> None:
        ws1: AsyncMock = AsyncMock()
        ws2: AsyncMock = AsyncMock()
        broadcast.CLIENTS[ws1] = {"type": "website", "remote_ip": "127.0.0.1"}
        broadcast.CLIENTS[ws2] = {"type": "obs", "remote_ip": "127.0.0.1"}
        await broadcast.broadcast({"type": "test"})
        ws1.send_str.assert_called_once()
        ws2.send_str.assert_called_once()

    async def test_broadcast_exclude_ws(self) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        broadcast.CLIENTS[ws1] = {"type": "website", "remote_ip": "127.0.0.1"}
        broadcast.CLIENTS[ws2] = {"type": "obs", "remote_ip": "127.0.0.1"}
        await broadcast.broadcast({"type": "test"}, exclude_ws=ws1)
        ws1.send_str.assert_not_called()
        ws2.send_str.assert_called_once()

    async def test_broadcast_target_type(self) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()
        broadcast.CLIENTS[ws1] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        broadcast.CLIENTS[ws2] = {"type": "website", "remote_ip": "127.0.0.1"}
        broadcast.CLIENTS[ws3] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        await broadcast.broadcast({"type": "test"}, target_type="spicetify")
        assert ws1.send_str.called
        ws2.send_str.assert_not_called()
        assert ws3.send_str.called

    async def test_broadcast_removes_dead_clients(self) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.send_str = AsyncMock(side_effect=ConnectionError("dead"))
        broadcast.CLIENTS[ws1] = {"type": "website", "remote_ip": "127.0.0.1"}
        broadcast.CLIENTS[ws2] = {"type": "obs", "remote_ip": "127.0.0.1"}
        await broadcast.broadcast({"type": "test"})
        assert ws1 not in broadcast.CLIENTS
        assert ws2 in broadcast.CLIENTS

    async def test_broadcast_volume_update_shape(self) -> None:
        st.state["volume"] = 0.42
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast.broadcast_volume_update()
        assert mock_broadcast.call_count == 2
        msg = mock_broadcast.call_args_list[0][0][0]
        assert msg["type"] == "volumeUpdate"
        assert msg["source"] == "spotify"

    async def test_broadcast_playback_update_shape(self) -> None:
        st.state["isPlaying"] = True
        st.state["trackProgress"] = 30000
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast.broadcast_playback_update()
        assert mock_broadcast.call_count == 2
        msg = mock_broadcast.call_args_list[0][0][0]
        assert msg["type"] == "playbackUpdate"
        assert msg["source"] == "spotify"

    async def test_broadcast_progress_update_shape(self) -> None:
        st.state["trackProgress"] = 45000
        st.state["trackDuration"] = 200000
        st.state["isPlaying"] = True
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast.broadcast_progress_update()
        assert mock_broadcast.call_count == 2
        msg = mock_broadcast.call_args_list[0][0][0]
        assert msg["type"] == "progressUpdate"
        assert msg["source"] == "spotify"

    async def test_broadcast_lyrics_update_shape(self) -> None:
        st.state["lyrics"] = {
            "available": True,
            "instrumental": False,
            "synced": [{"time": 1000, "text": "hello"}],
            "plain": "hello",
            "loading": False,
            "trackUri": "spotify:track:test"
        }
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast.broadcast_lyrics_update()
        mock_broadcast.assert_called_once_with({
            "type": "lyricsUpdate",
            "available": True,
            "instrumental": False,
            "synced": [{"time": 1000, "text": "hello"}],
            "plain": "hello",
            "loading": False
        })

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
        orig_obs: bool = cfg.config["enableOBS"]
        cfg.config["port"] = 9999
        cfg.config["defaultVolume"] = 0.7
        cfg.config["enableOBS"] = False
        try:
            resp = await routes.handle_config(req)
        finally:
            cfg.config["port"] = orig_port
            cfg.config["defaultVolume"] = orig_vol
            cfg.config["enableOBS"] = orig_obs
        body: bytes = resp.body
        data: dict[str, Any] = json.loads(body)
        assert data["port"] == 9999
        assert data["defaultVolume"] == 0.7
        assert data["enableOBS"] is False
        assert data["enableWebsite"] is True


class TestAdminConfigPut:
    @pytest.fixture
    async def client(self):
        from copy import deepcopy

        import routes
        from config import CONFIG_PATH
        saved_config = deepcopy(cfg.config)
        saved_file = None
        try:
            with open(CONFIG_PATH, "r") as f:
                saved_file = f.read()
        except FileNotFoundError:
            pass
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        app = web.Application()
        app.router.add_put('/api/admin/config', routes.handle_admin_config_put)
        app.router.add_get('/api/admin/config', routes.handle_admin_config_get)
        async with TestClient(TestServer(app)) as tc:
            yield tc
        cfg.config.clear()
        cfg.config.update(saved_config)
        if saved_file is not None:
            with open(CONFIG_PATH, "w") as f:
                f.write(saved_file)

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

    async def test_log_level_invalid(self, client) -> None:
        orig = cfg.config.get("logLevel")
        resp = await client.put('/api/admin/config', json={"logLevel": "VERBOSE"})
        assert resp.status == 400
        assert cfg.config.get("logLevel") == orig

    async def test_allowed_origins_valid(self, client) -> None:
        resp = await client.put('/api/admin/config', json={"allowedOrigins": ["http://localhost:3000"]})
        assert resp.status == 200
        assert cfg.config["allowedOrigins"] == ["http://localhost:3000"]

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
