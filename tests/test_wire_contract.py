"""Pinned v2 wire payload shapes shared by clients (protocol.py,
broadcast.py, routes.py)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import broadcast
import handlers
import routes
import state as st


class TestWireContract:
    """Pin the exact v2 payload shapes; clients depend on these key names."""

    ENVELOPE_KEYS = {"v", "type", "source", "state"}
    SPOTIFY_STATE_KEYS = {
        "volume", "isPlaying", "trackName", "artistName", "albumName", "trackUri",
        "albumUri", "artistUri", "albumArtUrl", "progress", "duration",
        "isShuffling", "repeatStatus", "isLiked", "timestamp",
    }
    SC_STATE_KEYS = {
        "track", "artist", "album", "id", "coverUrl", "isPlaying", "progress",
        "duration", "volume", "isLiked", "isShuffling", "repeatStatus", "timestamp",
    }
    LYRICS_STATE_KEYS = {
        "available", "instrumental", "synced", "plain", "karaoke", "provider", "loading",
    }
    PROGRESS_STATE_KEYS = {"progress", "duration", "isPlaying", "timestamp"}

    def test_spotify_now_playing(self) -> None:
        msg = broadcast.build_spotify_state_message(1234)
        assert set(msg) == self.ENVELOPE_KEYS
        assert set(msg["state"]) == self.SPOTIFY_STATE_KEYS
        assert msg["v"] == 2
        assert msg["type"] == "nowPlaying" and msg["source"] == "spotify"
        assert msg["state"]["progress"] == 1234

    def test_sc_now_playing(self) -> None:
        msg = broadcast.build_sc_state_message(5678)
        assert set(msg) == self.ENVELOPE_KEYS
        assert set(msg["state"]) == self.SC_STATE_KEYS
        assert msg["v"] == 2
        assert msg["type"] == "nowPlaying" and msg["source"] == "soundcloud"
        assert msg["state"]["progress"] == 5678

    def test_lyrics_message(self) -> None:
        msg = broadcast.build_lyrics_message()
        assert set(msg) == {"v", "type", "state"}
        assert msg["type"] == "lyrics"
        assert set(msg["state"]) == self.LYRICS_STATE_KEYS

    def test_source_status_message(self) -> None:
        msg = broadcast.build_source_status_message("spotify", True)
        assert msg == {
            "v": 2, "type": "sourceStatus", "source": "spotify",
            "state": {"connected": True},
        }

    async def test_now_playing_broadcasts_for_both_sources(self) -> None:
        sent: list[dict[str, Any]] = []

        async def capture(message: dict[str, Any], exclude_ws: Any = None, target_type: Any = None) -> None:
            sent.append(message)

        with patch.object(broadcast, "broadcast", capture):
            await broadcast.broadcast_volume_update()
        assert [m["type"] for m in sent] == ["nowPlaying", "nowPlaying"]
        assert [m["source"] for m in sent] == ["spotify", "soundcloud"]
        assert all(set(m) == self.ENVELOPE_KEYS for m in sent)

    async def test_playback_broadcasts_full_snapshots(self) -> None:
        sent: list[dict[str, Any]] = []

        async def capture(message: dict[str, Any], exclude_ws: Any = None, target_type: Any = None) -> None:
            sent.append(message)

        with patch.object(broadcast, "broadcast", capture):
            await broadcast.broadcast_playback_update()
        assert [m["type"] for m in sent] == ["nowPlaying", "nowPlaying"]
        assert set(sent[0]["state"]) == self.SPOTIFY_STATE_KEYS
        assert set(sent[1]["state"]) == self.SC_STATE_KEYS

    async def test_progress_messages(self) -> None:
        sent: list[dict[str, Any]] = []

        async def capture(message: dict[str, Any], exclude_ws: Any = None, target_type: Any = None) -> None:
            sent.append(message)

        with patch.object(broadcast, "broadcast", capture):
            await broadcast.broadcast_progress_update()
        assert [m["type"] for m in sent] == ["progress", "progress"]
        assert [m["source"] for m in sent] == ["spotify", "soundcloud"]
        for message in sent:
            assert set(message["state"]) == self.PROGRESS_STATE_KEYS

    async def test_progress_loop_messages(self) -> None:
        st.state["isPlaying"] = True
        st.state["scIsPlaying"] = True
        st.state["trackProgressStartTimestamp"] = 1.0
        st.state["scProgressStartTimestamp"] = 1.0
        sent: list[dict[str, Any]] = []

        async def capture(message: dict[str, Any], exclude_ws: Any = None, target_type: Any = None) -> None:
            sent.append(message)

        with patch.object(broadcast, "broadcast", capture):
            await broadcast._compute_and_broadcast_progress()
        assert [m["type"] for m in sent] == ["progress", "progress"]
        assert all(set(m["state"]) == self.PROGRESS_STATE_KEYS for m in sent)

    async def test_api_state_shape_is_stable(self) -> None:
        st.state["isPlaying"] = False
        st.state["scIsPlaying"] = False
        req = MagicMock()
        body: bytes = (await routes.handle_state(req)).body
        assert body == (await routes.handle_state(req)).body
        data: dict[str, Any] = json.loads(body)
        assert list(data) == ["spotify", "soundcloud"]
        assert set(data["spotify"]) == {
            "trackName", "artistName", "albumName", "trackUri", "albumArtUrl",
            "volume", "isPlaying", "isShuffling", "repeatStatus", "isLiked",
            "progress", "duration", "progressFmt", "durationFmt",
        }
        assert set(data["soundcloud"]) == {
            "track", "artist", "album", "coverUrl", "isPlaying", "progressMs",
            "durationMs", "volume", "isLiked", "progressFmt", "durationFmt",
        }


class TestLyricsMessageShape:
    async def test_initial_state_includes_loading(self, mock_ws: AsyncMock) -> None:
        st.state["lyrics"] = {
            "trackUri": "spotify:track:x", "synced": [], "plain": "", "available": False,
            "instrumental": False, "loading": True, "karaoke": [], "provider": "",
        }
        await handlers.handle_get_initial_state(mock_ws, {})
        messages = [json.loads(call.args[0]) for call in mock_ws.send_str.await_args_list]
        lyrics = next(m for m in messages if m["type"] == "lyrics")
        assert lyrics["state"]["loading"] is True

    async def test_broadcast_and_initial_payloads_match(self, mock_ws: AsyncMock) -> None:
        with patch.object(broadcast, "broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast.broadcast_lyrics_update()
        await handlers.handle_get_initial_state(mock_ws, {})
        messages = [json.loads(call.args[0]) for call in mock_ws.send_str.await_args_list]
        initial = next(m for m in messages if m["type"] == "lyrics")
        assert mock_broadcast.await_args.args[0] == initial
