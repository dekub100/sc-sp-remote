"""Input hardening in server/handlers.py: junk client state, handler
crashes, SoundCloud cover normalisation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import handlers
import state as st
from helpers import register_client


class TestInboundValidation:
    """State is fed by WebSocket clients; bad types must be ignored, not stored."""

    async def test_wrong_types_are_ignored(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        st.state["currentTrack"]["trackUri"] = "spotify:track:keep"
        st.state["currentTrack"]["trackName"] = "Keep"
        with patch.object(handlers, "broadcast_spotify_state", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "state": {
                    "isPlaying": "yes",
                    "isShuffling": 1,
                    "isLiked": "true",
                    "repeatStatus": 99,
                    "progress": "lol",
                    "duration": None,
                    "volume": [1],
                    "trackName": 5,
                    "trackUri": 7,
                    "artistName": "Artist",
                },
            })
        assert st.state["isPlaying"] is False
        assert st.state["isShuffling"] is False
        assert st.state["isLiked"] is False
        assert st.state["repeatStatus"] == 0
        assert st.state["trackProgress"] == 0
        assert st.state["trackDuration"] == 0
        assert st.state["volume"] == 0.5
        assert st.state["currentTrack"]["trackUri"] == "spotify:track:keep"
        assert st.state["currentTrack"]["trackName"] == "Keep"
        assert st.state["currentTrack"]["artistName"] == "Artist"

    async def test_nan_and_infinity_are_ignored(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_spotify_state", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "state": {
                    "progress": float("nan"),
                    "duration": float("inf"),
                    "volume": float("nan"),
                },
            })
        assert st.state["trackProgress"] == 0
        assert st.state["trackDuration"] == 0
        assert st.state["volume"] == 0.5

    async def test_values_are_clamped(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_spotify_state", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "state": {"volume": 5, "progress": -100, "duration": 10 ** 12},
            })
        assert st.state["volume"] == 1.0
        assert st.state["trackProgress"] == 0
        assert st.state["trackDuration"] == handlers._MAX_MS

    async def test_sc_wrong_types_are_ignored(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "soundcloud")
        with patch.object(handlers, "broadcast_soundcloud_state", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "state": {
                    "track": 1,
                    "progress": "x",
                    "duration": None,
                    "volume": "loud",
                    "isPlaying": "yes",
                    "repeatStatus": 7,
                    "coverUrl": {"a": 1},
                },
            })
        assert st.state["scTrack"] == "No song playing"
        assert st.state["scProgressMs"] == 0
        assert st.state["scDurationMs"] == 0
        assert st.state["scVolume"] == 0.5
        assert st.state["scIsPlaying"] is False
        assert st.state["scRepeatStatus"] == 0
        assert st.state["scCoverUrl"] == ""

    async def test_command_rejects_non_numeric_step(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "streamdeck")
        spicetify_ws: AsyncMock = AsyncMock()
        register_client(spicetify_ws, "spicetify")
        await handlers.handle_command(
            mock_ws, {"type": "command", "command": "volumeUp", "step": "huge"}
        )
        spicetify_ws.send_str.assert_not_called()
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "invalid_command"


class TestHandleMessageCrash:
    async def test_handler_exception_is_caught(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")

        async def boom(ws, data):
            raise RuntimeError("crash")

        original = handlers.MESSAGE_HANDLERS["volume"]
        handlers.MESSAGE_HANDLERS["volume"] = boom
        try:
            with patch.object(handlers.logger, "exception") as mock_exc:
                await handlers.handle_message(
                    mock_ws, json.dumps({"type": "volume", "state": {"volume": 0.5}})
                )
            mock_exc.assert_called_once()
        finally:
            handlers.MESSAGE_HANDLERS["volume"] = original


class TestCoverSizeNormalization:
    def test_thumbnail_size_replaced(self) -> None:
        result = handlers._COVER_SIZE_RE.sub("-t500x500", "https://i1.sndcdn.com/artworks-abc-t100x100.jpg")
        assert "-t500x500" in result
        assert "-t100x100" not in result

    def test_no_size_passthrough(self) -> None:
        url = "https://i1.sndcdn.com/artworks-abc-large.jpg"
        assert handlers._COVER_SIZE_RE.sub("-t500x500", url) == url

    async def test_sc_now_playing_normalizes_cover(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "soundcloud")
        with patch.object(handlers, "broadcast_soundcloud_state", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "source": "soundcloud",
                "state": {"coverUrl": "https://i1.sndcdn.com/artworks-x-t100x100.jpg"},
            })
        assert "-t500x500" in st.state["scCoverUrl"]
