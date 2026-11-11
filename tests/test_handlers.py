"""Message dispatch and per-type handlers in server/handlers.py."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import handlers
import pytest
import state as st
from helpers import register_client


class TestMessageHandlers:
    async def test_handle_volume_absolute(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        st.state["volume"] = 0.3
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_volume(
                mock_ws, {"type": "volume", "source": "spotify", "state": {"volume": 0.8}}
            )
        assert st.state["volume"] == 0.8

    async def test_handle_volume_clamps(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_volume(
                mock_ws, {"type": "volume", "state": {"volume": 5.0}}
            )
            assert st.state["volume"] == 1.0
            await handlers.handle_volume(
                mock_ws, {"type": "volume", "state": {"volume": -10.0}}
            )
            assert st.state["volume"] == 0.0

    async def test_volume_rejects_mismatched_source(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        st.state["volume"] = 0.3
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_volume(
                mock_ws, {"type": "volume", "source": "soundcloud", "state": {"volume": 0.9}}
            )
        assert st.state["volume"] == 0.3
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "forbidden"

    async def test_handle_playback(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_playback(
                mock_ws,
                {"type": "playback", "state": {"isPlaying": True, "progress": 5000}},
            )
        assert st.state["isPlaying"] is True
        assert st.state["trackProgress"] == 5000
        assert st.state["trackProgressStartTimestamp"] > 0

    async def test_handle_shuffle(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_shuffle(
                mock_ws, {"type": "shuffle", "state": {"isShuffling": True}}
            )
        assert st.state["isShuffling"] is True

    async def test_handle_repeat(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_repeat(
                mock_ws, {"type": "repeat", "state": {"repeatStatus": 2}}
            )
        assert st.state["repeatStatus"] == 2

    async def test_handle_like(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_like(
                mock_ws, {"type": "like", "state": {"isLiked": True}}
            )
        assert st.state["isLiked"] is True

    async def test_handle_now_playing_new_track(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_spotify_state", new_callable=AsyncMock), \
             patch.object(handlers, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch.object(handlers, "fetch_and_broadcast_lyrics", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "source": "spotify",
                "state": {
                    "trackName": "New Song",
                    "artistName": "New Artist",
                    "trackUri": "spotify:track:new",
                    "duration": 200000,
                    "progress": 0,
                },
            })
            await asyncio.sleep(0)
        assert st.state["currentTrack"]["trackName"] == "New Song"
        assert st.state["currentTrack"]["artistName"] == "New Artist"
        assert st.state["currentTrack"]["trackUri"] == "spotify:track:new"
        assert st.state["trackDuration"] == 200000
        assert st.state["lyrics"]["loading"] is True

    async def test_handle_now_playing_same_track_no_lyrics_fetch(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        st.state["currentTrack"]["trackUri"] = "spotify:track:existing"
        st.state["lyrics"]["loading"] = False
        with patch.object(handlers, "broadcast_spotify_state", new_callable=AsyncMock), \
             patch.object(handlers, "broadcast_lyrics_update", new_callable=AsyncMock) as mock_lyrics, \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "source": "spotify",
                "state": {
                    "trackName": "Updated",
                    "artistName": "Artist",
                    "trackUri": "spotify:track:existing",
                    "duration": 180000,
                    "progress": 10000,
                },
            })
        mock_lyrics.assert_not_called()
        assert st.state["lyrics"]["loading"] is False

    async def test_handle_now_playing_batched_fields(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast_spotify_state", new_callable=AsyncMock), \
             patch.object(handlers, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "source": "spotify",
                "state": {
                    "trackUri": "spotify:track:batch",
                    "trackName": "Batch",
                    "volume": 0.9,
                    "isShuffling": True,
                    "repeatStatus": 1,
                    "isLiked": True,
                    "duration": 150000,
                },
            })
        assert st.state["volume"] == 0.9
        assert st.state["isShuffling"] is True
        assert st.state["repeatStatus"] == 1
        assert st.state["isLiked"] is True

    async def test_soundcloud_now_playing_shuffle_repeat(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "soundcloud")
        with patch.object(handlers, "broadcast_soundcloud_state", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "source": "soundcloud",
                "state": {"isShuffling": True, "repeatStatus": 2},
            })
        assert st.state["scIsShuffling"] is True
        assert st.state["scRepeatStatus"] == 2

    async def test_soundcloud_now_playing_suppresses_duplicate_broadcast(
        self, mock_ws: AsyncMock
    ) -> None:
        register_client(mock_ws, "soundcloud")
        with patch.object(handlers, "broadcast_soundcloud_state", new_callable=AsyncMock) as mock_broadcast, \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock) as mock_save:
            first: dict[str, Any] = {
                "type": "nowPlaying",
                "source": "soundcloud",
                "state": {"track": "Song", "isPlaying": True},
            }
            await handlers.handle_now_playing(mock_ws, dict(first, state={"track": "Song", "isPlaying": True, "progress": 1000}))
            await handlers.handle_now_playing(mock_ws, dict(first, state={"track": "Song", "isPlaying": True, "progress": 2500}))
        mock_broadcast.assert_called_once()
        mock_save.assert_called_once()
        # Progress still mutates server state — only the save/broadcast is gated.
        assert st.state["scProgressMs"] == 2500

    async def test_soundcloud_now_playing_broadcasts_on_field_change(
        self, mock_ws: AsyncMock
    ) -> None:
        register_client(mock_ws, "soundcloud")
        with patch.object(handlers, "broadcast_soundcloud_state", new_callable=AsyncMock) as mock_broadcast, \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock) as mock_save:
            first: dict[str, Any] = {
                "type": "nowPlaying",
                "source": "soundcloud",
                "state": {"track": "Song A", "isPlaying": True},
            }
            await handlers.handle_now_playing(mock_ws, first)
            await handlers.handle_now_playing(mock_ws, first)
            await handlers.handle_now_playing(mock_ws, {
                "type": "nowPlaying",
                "source": "soundcloud",
                "state": {"track": "Song B", "isPlaying": True},
            })
        assert mock_broadcast.call_count == 2
        assert mock_save.call_count == 2

    async def test_handle_progress(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast", new_callable=AsyncMock) as mock_broadcast:
            await handlers.handle_progress(
                mock_ws, {"type": "progress", "state": {"progress": 30000, "duration": 240000}}
            )
        assert st.state["trackProgress"] == 30000
        assert st.state["trackDuration"] == 240000
        sent = mock_broadcast.call_args[0][0]
        assert sent["type"] == "progress"
        assert sent["state"]["progress"] == 30000

    async def test_command_targets_spicetify(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        spicetify_ws: AsyncMock = AsyncMock()
        register_client(spicetify_ws, "spicetify")
        await handlers.handle_command(
            mock_ws, {"type": "command", "source": "spotify", "command": "next"}
        )
        spicetify_ws.send_str.assert_called_once()
        sent: dict[str, Any] = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["type"] == "command"
        assert sent["source"] == "spotify"
        assert sent["command"] == "next"
        assert sent["v"] == 2

    async def test_command_defaults_to_spotify(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        spicetify_ws = AsyncMock()
        register_client(spicetify_ws, "spicetify")
        await handlers.handle_command(mock_ws, {"type": "command", "command": "like"})
        sent = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["source"] == "spotify"
        assert sent["command"] == "like"

    async def test_command_targets_soundcloud(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "streamdeck")
        sc_ws = AsyncMock()
        register_client(sc_ws, "soundcloud")
        await handlers.handle_command(
            mock_ws, {"type": "command", "source": "soundcloud", "command": "like"}
        )
        sent = json.loads(sc_ws.send_str.call_args[0][0])
        assert sent["source"] == "soundcloud"
        assert sent["command"] == "like"

    async def test_command_drops_smuggled_fields(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        spicetify_ws = AsyncMock()
        register_client(spicetify_ws, "spicetify")
        await handlers.handle_command(
            mock_ws, {"type": "command", "command": "next", "volume": 0.1, "evil": True}
        )
        sent = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert "evil" not in sent
        assert "volume" not in sent

    async def test_command_rejects_unknown_command(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        await handlers.handle_command(mock_ws, {"type": "command", "command": "formatDisk"})
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "invalid_command"

    async def test_command_rejects_missing_volume(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        await handlers.handle_command(
            mock_ws, {"type": "command", "command": "setVolume"}
        )
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "invalid_command"

    async def test_command_set_volume_clamped(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        spicetify_ws = AsyncMock()
        register_client(spicetify_ws, "spicetify")
        await handlers.handle_command(
            mock_ws, {"type": "command", "command": "setVolume", "volume": 5.0}
        )
        sent = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["volume"] == 1.0

    async def test_command_volume_step_default(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        spicetify_ws = AsyncMock()
        register_client(spicetify_ws, "spicetify")
        await handlers.handle_command(
            mock_ws, {"type": "command", "command": "volumeUp"}
        )
        sent = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["step"] == 0.05

    async def test_handle_error_broadcasts_message(self, mock_ws: AsyncMock) -> None:
        with patch("handlers.broadcast", new_callable=AsyncMock) as mock_broadcast:
            with patch.object(handlers.logger, "warning"):
                await handlers.handle_error(mock_ws, {"type": "error", "message": "Something broke"})
        mock_broadcast.assert_called_once_with({
            "v": 2,
            "type": "error",
            "code": "client_error",
            "message": "Something broke",
        })

    async def test_handle_error_defaults_message(self, mock_ws: AsyncMock) -> None:
        with patch("handlers.broadcast", new_callable=AsyncMock) as mock_broadcast:
            with patch.object(handlers.logger, "warning"):
                await handlers.handle_error(mock_ws, {"type": "error"})
        assert mock_broadcast.call_args[0][0]["message"] == "Unknown error"

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
        register_client(mock_ws, "website")
        with patch.object(handlers.logger, "warning") as mock_warn:
            await handlers.handle_message(mock_ws, json.dumps({"type": "fooBar"}))
        assert "fooBar" in mock_warn.call_args[0][0]
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "unknown_type"

    async def test_wrong_protocol_version(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        with patch.object(handlers.logger, "warning"):
            await handlers.handle_message(
                mock_ws, json.dumps({"v": 1, "type": "command", "command": "next"})
            )
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "protocol_version"

    async def test_valid_message_dispatches_handler(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        mock_handler: AsyncMock = AsyncMock()
        original: Any = handlers.MESSAGE_HANDLERS["command"]
        handlers.MESSAGE_HANDLERS["command"] = mock_handler
        try:
            await handlers.handle_message(
                mock_ws, json.dumps({"type": "command", "command": "next"})
            )
            mock_handler.assert_called_once()
        finally:
            handlers.MESSAGE_HANDLERS["command"] = original

    async def test_source_cannot_send_command(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "spicetify")
        with patch.object(handlers, "broadcast", new_callable=AsyncMock) as mock_broadcast, \
             patch.object(handlers.logger, "warning"):
            await handlers.handle_message(
                mock_ws, json.dumps({"type": "command", "command": "next"})
            )
        mock_broadcast.assert_not_called()
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "forbidden"

    async def test_controller_cannot_send_source_state(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "website")
        with patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock) as mock_save, \
             patch.object(handlers.logger, "warning"):
            await handlers.handle_message(
                mock_ws, json.dumps({"type": "volume", "state": {"volume": 0.9}})
            )
        mock_save.assert_not_called()
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "forbidden"

    async def test_unknown_client_type_is_log_only(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "random-site")
        with patch.object(handlers.logger, "warning"):
            await handlers.handle_message(
                mock_ws, json.dumps({"type": "command", "command": "next"})
            )
        sent = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent["code"] == "forbidden"


class TestSoundCloudState:
    async def test_sc_volume_update_absolute(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "soundcloud")
        st.state["scVolume"] = 0.3
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_volume(
                mock_ws, {"type": "volume", "source": "soundcloud", "state": {"volume": 0.8}}
            )
        assert st.state["scVolume"] == 0.8

    async def test_sc_volume_is_clamped(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "soundcloud")
        with patch.object(handlers, "broadcast_now_playing", new_callable=AsyncMock), \
             patch.object(handlers, "save_source_state_debounced", new_callable=AsyncMock):
            await handlers.handle_volume(
                mock_ws, {"type": "volume", "state": {"volume": 5.0}}
            )
            assert st.state["scVolume"] == 1.0
            await handlers.handle_volume(
                mock_ws, {"type": "volume", "state": {"volume": -10.0}}
            )
            assert st.state["scVolume"] == 0.0

    async def test_volume_command_routes_to_soundcloud_as_absolute(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "streamdeck")
        sc_ws: AsyncMock = AsyncMock()
        register_client(sc_ws, "soundcloud")
        st.state["scVolume"] = 0.4
        await handlers.handle_command(
            mock_ws,
            {"type": "command", "source": "soundcloud", "command": "volumeUp", "step": 0.1},
        )
        sent = json.loads(sc_ws.send_str.call_args[0][0])
        # The SC bridge only implements setVolume, so the server converts.
        assert sent["command"] == "setVolume"
        assert sent["volume"] == pytest.approx(0.5)

    async def test_relative_volume_for_spotify_is_forwarded(self, mock_ws: AsyncMock) -> None:
        register_client(mock_ws, "streamdeck")
        spicetify_ws: AsyncMock = AsyncMock()
        register_client(spicetify_ws, "spicetify")
        await handlers.handle_command(
            mock_ws,
            {"type": "command", "source": "spotify", "command": "volumeUp", "step": 0.1},
        )
        sent = json.loads(spicetify_ws.send_str.call_args[0][0])
        assert sent["command"] == "volumeUp"
        assert sent["step"] == 0.1


class TestGetInitialState:
    async def test_sends_state_lyrics_and_status_snapshot(self, mock_ws: AsyncMock) -> None:
        st.state["currentTrack"]["artistUri"] = "spotify:artist:xyz"
        st.state["lyrics"]["provider"] = "lrclib"
        st.state["lyrics"]["karaoke"] = [{"startTime": 1000}]
        await handlers.handle_get_initial_state(mock_ws, {})
        payloads = [json.loads(call[0][0]) for call in mock_ws.send_str.call_args_list]
        assert [p["type"] for p in payloads] == [
            "nowPlaying", "nowPlaying", "lyrics", "sourceStatus", "sourceStatus",
        ]
        assert [p["source"] for p in payloads[:2]] == ["spotify", "soundcloud"]
        assert all(p["v"] == 2 for p in payloads)
        assert payloads[0]["state"]["artistUri"] == "spotify:artist:xyz"
        assert payloads[2]["state"]["provider"] == "lrclib"
        assert payloads[2]["state"]["karaoke"] == [{"startTime": 1000}]

    async def test_status_reflects_attached_sources(self, mock_ws: AsyncMock) -> None:
        source_ws: AsyncMock = AsyncMock()
        register_client(source_ws, "soundcloud")
        await handlers.handle_get_initial_state(mock_ws, {})
        payloads = [json.loads(call[0][0]) for call in mock_ws.send_str.call_args_list]
        status = {p["source"]: p["state"]["connected"] for p in payloads if p["type"] == "sourceStatus"}
        assert status == {"spotify": False, "soundcloud": True}


class TestHandleClientLog:
    async def test_error_routes_to_error(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "error") as mock_log:
            await handlers.handle_client_log(mock_ws, {"level": "error", "message": "boom"})
        assert "boom" in mock_log.call_args[0][0]

    async def test_warning_routes_to_warning(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "warning") as mock_log:
            await handlers.handle_client_log(mock_ws, {"level": "warning", "message": "careful"})
        assert "careful" in mock_log.call_args[0][0]

    async def test_debug_routes_to_debug(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "debug") as mock_log:
            await handlers.handle_client_log(mock_ws, {"level": "debug", "message": "tracing"})
        assert "tracing" in mock_log.call_args[0][0]

    async def test_unknown_level_routes_to_info(self, mock_ws: AsyncMock) -> None:
        with patch.object(handlers.logger, "info") as mock_log:
            await handlers.handle_client_log(mock_ws, {"level": "weird", "message": "note"})
        assert "note" in mock_log.call_args[0][0]

    async def test_client_type_prefix(self, mock_ws: AsyncMock) -> None:
        handlers.CLIENTS[mock_ws] = {"type": "spicetify", "remote_ip": "127.0.0.1"}
        with patch.object(handlers.logger, "info") as mock_log:
            await handlers.handle_client_log(mock_ws, {"message": "hello"})
        assert "[spicetify] hello" == mock_log.call_args[0][0]
        del handlers.CLIENTS[mock_ws]


class TestClientLogLimits:
    async def test_message_is_truncated(self, mock_ws: AsyncMock) -> None:
        handlers.CLIENTS[mock_ws] = {"type": "spicetify"}
        with patch.object(handlers.logger, "info") as mock_log:
            await handlers.handle_client_log(mock_ws, {"message": "a" * 1000})
        logged = mock_log.call_args[0][0]
        assert "[truncated]" in logged
        assert len(logged) < 600

    async def test_flood_is_rate_limited(self, mock_ws: AsyncMock) -> None:
        handlers.CLIENTS[mock_ws] = {"type": "spicetify"}
        with patch.object(handlers.logger, "info") as mock_log:
            for _ in range(handlers._CLIENT_LOG_MAX_PER_WINDOW + 5):
                await handlers.handle_client_log(mock_ws, {"message": "spam"})
        assert mock_log.call_count == handlers._CLIENT_LOG_MAX_PER_WINDOW

    async def test_non_string_message_is_coerced(self, mock_ws: AsyncMock) -> None:
        handlers.CLIENTS[mock_ws] = {"type": "spicetify"}
        with patch.object(handlers.logger, "info") as mock_log:
            await handlers.handle_client_log(mock_ws, {"message": {"a": 1}})
        assert "a" in mock_log.call_args[0][0]
