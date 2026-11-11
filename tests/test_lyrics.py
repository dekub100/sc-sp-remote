"""Tests for server/lyrics.py: LRC parsing, SQLite cache, session
lifecycle, karaoke cache columns."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import lyrics
import pytest

import server


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


class TestLyricsCache:
    @pytest.fixture(autouse=True)
    def setup_db(self, lyrics_cache_db: str) -> None:
        self.db_path = lyrics_cache_db

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


class TestKaraokeCacheRoundtrip:
    @pytest.fixture(autouse=True)
    def setup_db(self, lyrics_cache_db: str) -> None:
        self.db_path = lyrics_cache_db

    def test_karaoke_roundtrip(self) -> None:
        params = {"artist_name": "A", "track_name": "S", "album_name": "Al", "duration": 100}
        karaoke = json.dumps([{"startTime": 500, "endTime": 900, "words": [{"text": "yo", "time": 500}]}])
        with patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            lyrics.set_cached_lyrics(params, "[00:00.50]yo", "", False, karaoke, "musixmatch")
            row = lyrics.get_cached_lyrics(params)
        assert json.loads(row[3])[0]["words"][0]["text"] == "yo"
        assert row[4] == "musixmatch"

    def test_row_without_karaoke(self) -> None:
        params = {"artist_name": "A", "track_name": "S", "album_name": "Al", "duration": 101}
        with patch("lyrics.LYRICS_CACHE_DB", self.db_path):
            lyrics.set_cached_lyrics(params, None, "plain", False)
            row = lyrics.get_cached_lyrics(params)
        assert row[3] is None or row[3] == ""
