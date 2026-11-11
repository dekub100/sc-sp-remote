"""Fan-out in server/broadcast.py: broadcast(), state messages,
backpressure and the progress tick."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import broadcast
import pytest
import state as st


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
        assert msg["type"] == "nowPlaying"
        assert msg["source"] == "spotify"
        assert msg["state"]["volume"] == 0.42

    async def test_broadcast_playback_update_shape(self) -> None:
        st.state["isPlaying"] = True
        st.state["trackProgress"] = 30000
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast.broadcast_playback_update()
        assert mock_broadcast.call_count == 2
        msg = mock_broadcast.call_args_list[0][0][0]
        assert msg["type"] == "nowPlaying"
        assert msg["source"] == "spotify"
        assert msg["state"]["isPlaying"] is True

    async def test_broadcast_progress_update_shape(self) -> None:
        st.state["trackProgress"] = 45000
        st.state["trackDuration"] = 200000
        st.state["isPlaying"] = True
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast.broadcast_progress_update()
        assert mock_broadcast.call_count == 2
        msg = mock_broadcast.call_args_list[0][0][0]
        assert msg["type"] == "progress"
        assert msg["source"] == "spotify"
        assert msg["state"]["progress"] == 45000

    async def test_progress_tick_skips_paused_spotify(self) -> None:
        st.state["isPlaying"] = False
        st.state["scIsPlaying"] = True
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast._compute_and_broadcast_progress()
        assert mock_broadcast.call_count == 1
        assert mock_broadcast.call_args[0][0]["source"] == "soundcloud"

    async def test_progress_tick_skips_paused_soundcloud(self) -> None:
        st.state["isPlaying"] = True
        st.state["scIsPlaying"] = False
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast._compute_and_broadcast_progress()
        assert mock_broadcast.call_count == 1
        assert mock_broadcast.call_args[0][0]["source"] == "spotify"

    async def test_progress_tick_sends_both_when_playing(self) -> None:
        st.state["isPlaying"] = True
        st.state["scIsPlaying"] = True
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast._compute_and_broadcast_progress()
        assert mock_broadcast.call_count == 2

    async def test_broadcast_lyrics_update_shape(self) -> None:
        st.state["lyrics"] = {
            "available": True,
            "instrumental": False,
            "synced": [{"time": 1000, "text": "hello"}],
            "plain": "hello",
            "loading": False,
            "karaoke": [],
            "provider": "",
            "trackUri": "spotify:track:test"
        }
        with patch("broadcast.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await broadcast.broadcast_lyrics_update()
        mock_broadcast.assert_called_once_with({
            "v": 2,
            "type": "lyrics",
            "state": {
                "available": True,
                "instrumental": False,
                "synced": [{"time": 1000, "text": "hello"}],
                "plain": "hello",
                "karaoke": [],
                "provider": "",
                "loading": False,
            },
        })


class TestBuildStateMessages:
    def test_spotify_message_has_artist_uri(self) -> None:
        st.state["currentTrack"]["artistUri"] = "spotify:artist:abc"
        msg = broadcast.build_spotify_state_message(0)
        assert msg["state"]["artistUri"] == "spotify:artist:abc"
        for key in ("volume", "isPlaying", "trackName", "artistName", "albumName",
                    "trackUri", "albumUri", "isLiked", "isShuffling", "repeatStatus"):
            assert key in msg["state"]

    def test_spotify_message_missing_artist_uri_defaults_empty(self) -> None:
        st.state["currentTrack"].pop("artistUri", None)
        msg = broadcast.build_spotify_state_message(0)
        assert msg["state"]["artistUri"] == ""

    def test_sc_message_has_volume_and_isLiked(self) -> None:
        st.state["scVolume"] = 0.42
        st.state["scIsLiked"] = True
        msg = broadcast.build_sc_state_message(0)
        assert msg["state"]["volume"] == 0.42
        assert msg["state"]["isLiked"] is True
        for key in ("track", "artist", "coverUrl", "isPlaying", "isShuffling", "repeatStatus"):
            assert key in msg["state"]


class TestBroadcastBackpressure:
    async def test_stalled_client_is_dropped_not_awaited(self) -> None:
        class _Stalled:
            async def send_str(self, msg: str) -> None:
                await asyncio.sleep(30)

        class _Fast:
            def __init__(self) -> None:
                self.messages: list[str] = []

            async def send_str(self, msg: str) -> None:
                self.messages.append(msg)

        stalled, fast = _Stalled(), _Fast()
        broadcast.CLIENTS[stalled] = {"type": "obs"}  # type: ignore[index]
        broadcast.CLIENTS[fast] = {"type": "website"}  # type: ignore[index]
        with patch.object(broadcast, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.05):
            await asyncio.wait_for(broadcast.broadcast({"type": "progress"}), timeout=1.0)
        assert stalled not in broadcast.CLIENTS
        assert fast in broadcast.CLIENTS
        assert len(fast.messages) == 1

    async def test_progress_loop_keeps_ticking_past_a_stalled_client(self) -> None:
        class _Stalled:
            async def send_str(self, msg: str) -> None:
                await asyncio.sleep(30)

        class _Fast:
            def __init__(self) -> None:
                self.count = 0

            async def send_str(self, msg: str) -> None:
                self.count += 1

        stalled, fast = _Stalled(), _Fast()
        broadcast.CLIENTS[stalled] = {"type": "obs"}  # type: ignore[index]
        broadcast.CLIENTS[fast] = {"type": "website"}  # type: ignore[index]
        st.state["isPlaying"] = True
        st.state["trackDuration"] = 200000
        with patch.object(broadcast, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.05), \
             patch.dict(broadcast.config, {"progressBroadcastInterval": 0.02}):
            task = asyncio.create_task(broadcast.start_progress_broadcasting())
            await asyncio.sleep(0.4)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert fast.count >= 3
        assert stalled not in broadcast.CLIENTS
