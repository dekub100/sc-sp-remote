"""Provider fetch path for server/lyrics.py: Musixmatch, LRCLIB,
fallback order, negative cache, cache hits."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import broadcast
import lyrics
import pytest
import state as st
from helpers import FakeMxmResponse, mxm_header


class TestMusixmatchParsing:
    def test_subtitle_to_lrc(self) -> None:
        subtitle = json.dumps([
            {"text": "Hello", "time": {"total": 61.25}},
            {"text": "World", "time": {"total": 4.0}},
        ])
        result: str = lyrics._subtitle_to_lrc(subtitle)
        assert result == "[01:01.25]Hello\n[00:04.00]World"
        parsed = lyrics.parse_synced_lyrics(result)
        assert {"time": 61250, "text": "Hello"} in parsed
        assert {"time": 4000, "text": "World"} in parsed

    def test_parse_richsync_absolute_word_times(self) -> None:
        richsync = json.dumps([
            {
                "ts": 10.0,
                "te": 14.0,
                "l": [
                    {"c": "La ", "o": 0.0},
                    {"c": "la", "o": 1.5},
                ],
            }
        ])
        result: list[dict[str, Any]] = lyrics._parse_richsync(richsync)
        line = result[0]
        assert line["startTime"] == 10000
        assert line["endTime"] == 14000
        assert line["words"][0] == {"text": "La ", "time": 10000}
        # Last word runs to the line end.
        assert line["words"][1] == {"text": "la", "time": 11500}


class TestMusixmatchToken:
    async def test_get_token_uses_cached(self, mxm_config: dict[str, Any]) -> None:
        mxm_config["musixmatchToken"] = "cached-token"
        with patch.object(lyrics, "_mxm_fetch_token", new_callable=AsyncMock) as mock_fetch:
            token = await lyrics._get_mxm_token()
        assert token == "cached-token"
        mock_fetch.assert_not_awaited()

    async def test_mxm_get_retries_once_on_auth_failure(self, mxm_config: dict[str, Any]) -> None:
        import aiohttp
        responses = [FakeMxmResponse(mxm_header(401)), FakeMxmResponse(mxm_header(200))]
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=responses)
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=aiohttp.ClientTimeout(total=1)), \
             patch.object(lyrics, "_mxm_fetch_token", new_callable=AsyncMock, return_value="fresh"):
            data = await lyrics._mxm_get("token.get", {})
        assert data == mxm_header(200)
        assert mock_session.get.call_count == 2

    async def test_mxm_get_returns_none_after_second_auth_failure(self, mxm_config: dict[str, Any]) -> None:
        import aiohttp
        responses = [FakeMxmResponse(mxm_header(401)), FakeMxmResponse(mxm_header(401))]
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=responses)
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=aiohttp.ClientTimeout(total=1)), \
             patch.object(lyrics, "_mxm_fetch_token", new_callable=AsyncMock, return_value="fresh"):
            data = await lyrics._mxm_get("macro.subtitles.get", {})
        assert data is None

    async def test_refresh_persists_token_to_config(self, mxm_config: dict[str, Any], tmp_path: Any) -> None:

        import aiohttp
        payload = {"message": {"header": {"status_code": 200}, "body": {"user_token": "brand-new-token"}}}
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=FakeMxmResponse(payload))
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=aiohttp.ClientTimeout(total=1)):
            token = await lyrics.refresh_musixmatch_token()
        assert token == "brand-new-token"
        assert mxm_config["musixmatchToken"] == "brand-new-token"
        saved = json.loads(open(os.path.join(str(tmp_path), "config.json")).read())
        assert saved["musixmatchToken"] == "brand-new-token"


class TestProviderFallback:
    @pytest.fixture(autouse=True)
    def setup_db(self, lyrics_cache_db: str) -> None:
        self.db_path = lyrics_cache_db

    def _current_track(self, uri: str) -> None:
        st.state["currentTrack"]["trackUri"] = uri

    async def test_musixmatch_result_used_lrclib_not_called(self, mxm_config: dict[str, Any]) -> None:
        self._current_track("spotify:track:abc")
        mxm_result = {"synced_raw": "[00:01.00]Hi", "plain": "", "instrumental": False,
                      "karaoke": [{"startTime": 1000}],
                      "provider": "musixmatch"}
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock, return_value=mxm_result), \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock) as mock_lrc, \
             patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:abc", "Song", "Artist", "Album", 200000)
        mock_lrc.assert_not_called()
        assert st.state["lyrics"]["karaoke"] == [{"startTime": 1000}]
        assert st.state["lyrics"]["available"] is True

    async def test_falls_through_to_lrclib_on_musixmatch_miss(self, mxm_config: dict[str, Any]) -> None:
        self._current_track("spotify:track:def")
        lrc_result = {"synced_raw": "", "plain": "Plain words", "instrumental": False, "karaoke": [], "provider": "lrclib"}
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock, return_value=None), \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock, return_value=lrc_result) as mock_lrc, \
             patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:def", "Song", "Artist", "Album", 200000)
        mock_lrc.assert_awaited_once()
        assert st.state["lyrics"]["plain"] == "Plain words"

    async def test_all_providers_missing_marks_unavailable(self, mxm_config: dict[str, Any]) -> None:
        self._current_track("spotify:track:xyz")
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock, return_value=None), \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock, return_value=None), \
             patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:xyz", "Song", "Artist", "Album", 200000)
        assert st.state["lyrics"]["available"] is False
        assert st.state["lyrics"]["loading"] is False

    async def test_missing_lyrics_negative_cache_skips_providers(self, mxm_config: dict[str, Any]) -> None:
        self._current_track("spotify:track:nolrc")
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock, return_value=None) as mock_mxm, \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock, return_value=None) as mock_lrc, \
             patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:nolrc", "Song", "Artist", "Album", 200000)
            assert st.state["lyrics"]["available"] is False
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:nolrc", "Song", "Artist", "Album", 200000)
        assert mock_mxm.await_count == 1
        assert mock_lrc.await_count == 1
        assert st.state["lyrics"]["available"] is False

    async def test_expired_negative_cache_retries_providers(self, mxm_config: dict[str, Any]) -> None:
        self._current_track("spotify:track:nolrc")
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock, return_value=None), \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock, return_value=None), \
             patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:nolrc", "Song", "Artist", "Album", 200000)
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE lyrics_cache SET fetched_at=datetime('now', '-7 hours')")
        conn.commit()
        conn.close()
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock, return_value=None) as mock_mxm, \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock, return_value=None), \
             patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:nolrc", "Song", "Artist", "Album", 200000)
        assert mock_mxm.await_count == 1

    async def test_provider_exception_falls_through(self, mxm_config: dict[str, Any]) -> None:
        self._current_track("spotify:track:err")
        lrc_result = {"synced_raw": "[00:02.00]Ok", "plain": "", "instrumental": False, "karaoke": [], "provider": "lrclib"}
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock, side_effect=RuntimeError("boom")), \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock, return_value=lrc_result), \
             patch.object(broadcast, "broadcast_lyrics_update", new_callable=AsyncMock), \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:err", "Song", "Artist", "Album", 200000)
        assert st.state["lyrics"]["synced"][0]["text"] == "Ok"


class TestMusixmatchEmptyBody:
    async def test_empty_list_body_returns_none_not_crash(self, mxm_config: dict[str, Any]) -> None:
        """MXM returns "body": [] when there's no data; must not raise AttributeError."""
        payload = {"message": {"header": {"status_code": 200}, "body": {"macro_calls": {
            "matcher.track.get": {"message": {"header": {"status_code": 200},
                                              "body": {"track": {"has_lyrics": True}}}},
            "track.lyrics.get": {"message": {"header": {"status_code": 200}, "body": []}},
            "track.subtitles.get": {"message": {"header": {"status_code": 200}, "body": []}},
        }}}}
        with patch.object(lyrics, "_mxm_get", new_callable=AsyncMock, return_value=payload):
            result = await lyrics._fetch_musixmatch(
                {"artist_name": "A", "track_name": "S", "album_name": "Al", "duration": 100}, 100000)
        assert result is None


class _FakeLrcResponse:
    def __init__(self, status: int, payload: dict[str, Any] | None = None):
        self.status = status
        self._payload = payload or {}

    async def json(self, content_type: Any = None) -> dict[str, Any]:
        return self._payload

    async def __aenter__(self) -> "_FakeLrcResponse":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False


class TestFetchLrclib:
    async def test_404_returns_none_silent(self) -> None:
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=_FakeLrcResponse(404))
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=None), \
             patch.object(lyrics.logger, "warning") as mock_warn:
            result = await lyrics._fetch_lrclib({"artist_name": "A", "track_name": "S"}, 180000)
        assert result is None
        mock_warn.assert_not_called()

    async def test_500_returns_none_warns(self) -> None:
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=_FakeLrcResponse(500))
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=None), \
             patch.object(lyrics.logger, "warning") as mock_warn:
            result = await lyrics._fetch_lrclib({"artist_name": "A", "track_name": "S"}, 180000)
        assert result is None
        mock_warn.assert_called_once()

    async def test_empty_lyrics_returns_none(self) -> None:
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=_FakeLrcResponse(200, {"syncedLyrics": "", "plainLyrics": ""}))
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=None):
            result = await lyrics._fetch_lrclib({"artist_name": "A", "track_name": "S"}, 180000)
        assert result is None

    async def test_success_synced(self) -> None:
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=_FakeLrcResponse(200, {
            "syncedLyrics": "[00:01.00]Hello\n[00:05.00]World",
            "plainLyrics": "Hello\nWorld",
            "instrumental": False,
        }))
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=None):
            result = await lyrics._fetch_lrclib({"artist_name": "A", "track_name": "S"}, 180000)
        assert result["provider"] == "lrclib"
        assert result["instrumental"] is False
        assert "Hello" in result["synced_raw"]
        assert result["karaoke"] == []

    async def test_instrumental_flag(self) -> None:
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=_FakeLrcResponse(200, {
            "syncedLyrics": "", "plainLyrics": "", "instrumental": True,
        }))
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=None):
            result = await lyrics._fetch_lrclib({"artist_name": "A", "track_name": "S"}, 180000)
        assert result is None

    async def test_instrumental_with_plain(self) -> None:
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=_FakeLrcResponse(200, {
            "syncedLyrics": "", "plainLyrics": "instrumental text", "instrumental": True,
        }))
        with patch.object(lyrics, "_get_session", return_value=mock_session), \
             patch.object(lyrics, "_get_mxm_timeout", return_value=None):
            result = await lyrics._fetch_lrclib({"artist_name": "A", "track_name": "S"}, 180000)
        assert result["instrumental"] is True
        assert result["plain"] == "instrumental text"


class TestLyricsCacheHit:
    @pytest.fixture(autouse=True)
    def setup_db(self, lyrics_cache_db: str) -> None:
        self.db_path = lyrics_cache_db
        with patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            lyrics.init_lyrics_cache()

    def _seed(self, uri: str) -> None:
        st.state["currentTrack"]["trackUri"] = uri
        params = {"artist_name": "Artist", "track_name": "Song", "album_name": "Album", "duration": 200}
        with patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            lyrics.set_cached_lyrics(params, "[00:01.00]Hi", "", False, "", "lrclib")

    async def test_cache_hit_skips_fetchers(self) -> None:
        self._seed("spotify:track:cached")
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock) as mock_mxm, \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock) as mock_lrc, \
             patch.object(lyrics, "broadcast_lyrics_update", new_callable=AsyncMock) as mock_bcast, \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:cached", "Song", "Artist", "Album", 200000)
        mock_mxm.assert_not_called()
        mock_lrc.assert_not_called()
        mock_bcast.assert_awaited_once()
        assert st.state["lyrics"]["available"] is True
        assert st.state["lyrics"]["synced"][0]["text"] == "Hi"
        assert st.state["lyrics"]["provider"] == "lrclib"

    async def test_cache_hit_discarded_if_track_changed(self) -> None:
        self._seed("spotify:track:cached")
        st.state["currentTrack"]["trackUri"] = "spotify:track:different"
        with patch.object(lyrics, "_fetch_musixmatch", new_callable=AsyncMock), \
             patch.object(lyrics, "_fetch_lrclib", new_callable=AsyncMock), \
             patch.object(lyrics, "broadcast_lyrics_update", new_callable=AsyncMock) as mock_bcast, \
             patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            await lyrics.fetch_and_broadcast_lyrics("spotify:track:cached", "Song", "Artist", "Album", 200000)
        mock_bcast.assert_not_awaited()
        assert st.state["lyrics"]["available"] is False
