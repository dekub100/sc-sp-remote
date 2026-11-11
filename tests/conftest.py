"""Shared fixtures for the server test suite. Runtime data isolation and
sys.path wiring live in the repo-root conftest.py and must run first."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Any
from unittest.mock import AsyncMock, patch

import broadcast
import config as cfg
import handlers
import pytest
import state as st

import server


@pytest.fixture(autouse=True)
def reset_state():
    st.reset_source_state("spotify")
    st.reset_source_state("soundcloud")
    broadcast.CLIENTS.clear()
    st.cancel_pending_save()
    # The SC delta gate keeps a module-level fingerprint; clear it so test
    # order can never leak one test's broadcast decisions into the next.
    handlers._last_sc_fingerprint = None
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


# One copy of the lyrics_cache schema for every suite that needs it; keep this
# in sync with lyrics.init_lyrics_cache() instead of pasting it into fixtures.
_LYRICS_CACHE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS lyrics_cache (
        artist_name TEXT NOT NULL,
        track_name TEXT NOT NULL,
        album_name TEXT NOT NULL,
        duration INTEGER NOT NULL,
        synced_lyrics TEXT,
        plain_lyrics TEXT,
        instrumental INTEGER NOT NULL DEFAULT 0,
        karaoke TEXT,
        provider TEXT,
        fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (artist_name, track_name, album_name, duration)
    )
"""


@pytest.fixture
def lyrics_cache_db(temp_db: str) -> str:
    """An empty lyrics_cache DB on disk, ready for one test."""
    conn: sqlite3.Connection = sqlite3.connect(temp_db)
    conn.execute(_LYRICS_CACHE_SCHEMA)
    conn.commit()
    conn.close()
    return temp_db


@pytest.fixture
def mxm_config(tmp_path: Any):
    """Isolate Musixmatch config/token state per test."""
    old_token = cfg.config.get("musixmatchToken")
    old_order = cfg.config.get("lyricsProviderOrder")
    with patch("lyrics.CONFIG_PATH", str(tmp_path / "config.json")):
        yield cfg.config
    if old_token is not None:
        cfg.config["musixmatchToken"] = old_token
    if old_order is not None:
        cfg.config["lyricsProviderOrder"] = old_order
