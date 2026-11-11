"""Flat state in server/state.py: save data, debounced saves, progress
interpolation, source descriptor, restart anchors."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from unittest.mock import patch

import config as cfg
import pytest
import state as st


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


def test_write_state_to_disk(tmp_path: Any) -> None:
    state_file = tmp_path / "state_spotify.json"
    data: dict[str, Any] = {"volume": 0.5, "isPlaying": False}
    st._write_json_file(str(state_file), data)
    assert state_file.exists()
    assert json.loads(state_file.read_text()) == data


class TestInterpolatedProgress:
    def test_paused_returns_raw_progress(self) -> None:
        st.state["isPlaying"] = False
        st.state["trackProgress"] = 5000
        assert st.get_interpolated_track_progress() == 5000

    def test_playing_interpolates_from_anchor(self) -> None:
        import time as _time
        st.state["isPlaying"] = True
        st.state["trackProgress"] = 10000
        st.state["trackDuration"] = 200000
        st.state["trackProgressStartTimestamp"] = _time.time() * 1000 - 1500
        value: int = st.get_interpolated_track_progress()
        assert 11400 <= value <= 11600

    def test_clamps_to_duration(self) -> None:
        import time as _time
        st.state["isPlaying"] = True
        st.state["trackProgress"] = 199000
        st.state["trackDuration"] = 200000
        st.state["trackProgressStartTimestamp"] = _time.time() * 1000 - 60000
        assert st.get_interpolated_track_progress() == 200000


class TestAlbumArtToggle:
    @pytest.fixture(autouse=True)
    def restore_config(self):
        old = cfg.config.get("enableAlbumArt")
        yield
        if old is not None:
            cfg.config["enableAlbumArt"] = old

    def test_album_art_visible_by_default(self) -> None:
        cfg.config["enableAlbumArt"] = True
        st.state["currentTrack"]["albumArtUrl"] = "http://example.com/art.jpg"
        st.state["scCoverUrl"] = "http://example.com/cover.jpg"
        assert st.get_album_art_url() == "http://example.com/art.jpg"
        assert st.get_sc_cover_url() == "http://example.com/cover.jpg"

    def test_album_art_hidden_when_disabled(self) -> None:
        cfg.config["enableAlbumArt"] = False
        st.state["currentTrack"]["albumArtUrl"] = "http://example.com/art.jpg"
        st.state["scCoverUrl"] = "http://example.com/cover.jpg"
        assert st.get_album_art_url() == ""
        assert st.get_sc_cover_url() == ""


class TestDebouncedSave:
    @pytest.fixture(autouse=True)
    def setup(self):
        st.set_spotify_write_callback(lambda d: None)
        st.set_sc_write_callback(lambda d: None)
        yield
        st.cancel_pending_save()
        st.set_write_callback("spotify", None)
        st.set_write_callback("soundcloud", None)

    async def test_spotify_debounce_collapses_rapid_calls(self) -> None:
        calls: list[dict[str, Any]] = []
        st.set_spotify_write_callback(calls.append)
        with patch.dict(st.config, {"stateSaveDebounceSeconds": 0.01}):
            for _ in range(3):
                await st.save_spotify_state_debounced()
            await asyncio.sleep(0.05)
        assert len(calls) == 1
        assert calls[0]["volume"] == st.state["volume"]

    async def test_spotify_save_fires_after_delay(self) -> None:
        calls: list[dict[str, Any]] = []
        st.set_spotify_write_callback(calls.append)
        with patch.dict(st.config, {"stateSaveDebounceSeconds": 0.01}):
            await st.save_spotify_state_debounced()
            await asyncio.sleep(0.05)
        assert len(calls) == 1

    async def test_cancel_prevents_save(self) -> None:
        calls: list[dict[str, Any]] = []
        st.set_spotify_write_callback(calls.append)
        with patch.dict(st.config, {"stateSaveDebounceSeconds": 0.01}):
            await st.save_spotify_state_debounced()
            st.cancel_pending_save()
            await asyncio.sleep(0.05)
        assert len(calls) == 0

    async def test_sc_debounce_collapses_rapid_calls(self) -> None:
        calls: list[dict[str, Any]] = []
        st.set_sc_write_callback(calls.append)
        with patch.dict(st.config, {"stateSaveDebounceSeconds": 0.01}):
            for _ in range(3):
                await st.save_sc_state_debounced()
            await asyncio.sleep(0.05)
        assert len(calls) == 1
        assert calls[0]["scVolume"] == st.state["scVolume"]


class TestInterpolatedScProgress:
    def test_paused_returns_raw(self) -> None:
        st.state["scIsPlaying"] = False
        st.state["scProgressMs"] = 5000
        assert st.get_interpolated_sc_progress() == 5000

    def test_playing_interpolates(self) -> None:
        import time as _time
        st.state["scIsPlaying"] = True
        st.state["scProgressMs"] = 10000
        st.state["scDurationMs"] = 60000
        st.state["scProgressStartTimestamp"] = _time.time() * 1000
        result = st.get_interpolated_sc_progress()
        assert result >= 10000
        assert result < 12000

    def test_playing_clamped_to_duration(self) -> None:
        import time as _time
        st.state["scIsPlaying"] = True
        st.state["scProgressMs"] = 59000
        st.state["scDurationMs"] = 60000
        st.state["scProgressStartTimestamp"] = _time.time() * 1000 - 5000
        assert st.get_interpolated_sc_progress() == 60000


class TestSourceDescriptor:
    def test_persisted_and_runtime_partition_state(self) -> None:
        for spec in st.SOURCES.values():
            assert set(spec.persisted).isdisjoint(spec.runtime)
            assert set(spec.persisted) | set(spec.runtime) == set(spec.defaults)
            for key in spec.persisted + spec.runtime:
                assert key in st.state

    def test_client_type_mapping(self) -> None:
        assert st.SOURCE_BY_CLIENT_TYPE["spicetify"].key == "spotify"
        assert st.SOURCE_BY_CLIENT_TYPE["soundcloud"].key == "soundcloud"

    def test_reset_source_state(self) -> None:
        st.state["volume"] = 0.9
        st.state["trackProgress"] = 123
        st.reset_source_state("spotify")
        assert st.state["volume"] == st.SOURCES["spotify"].defaults["volume"]
        assert st.state["trackProgress"] == 0
        st.state["scTrack"] = "Other"
        st.reset_source_state("soundcloud")
        assert st.state["scTrack"] == "No song playing"

    def test_save_data_uses_serializers(self) -> None:
        st.state["volume"] = 0.777
        assert st.get_spotify_save_data()["volume"] == 0.78
        st.state["scVolume"] = 1.7
        assert st.get_sc_save_data()["scVolume"] == 1.0

    def test_interpolation_accepts_now(self) -> None:
        st.state.update({
            "isPlaying": True, "trackProgress": 1000, "trackDuration": 200000,
            "trackProgressStartTimestamp": 5000,
        })
        assert st.get_interpolated_progress("spotify", 6000) == 2000

    def test_write_source_state_now_uses_callback(self) -> None:
        calls: list[dict[str, Any]] = []
        st.set_write_callback("spotify", calls.append)
        try:
            st.write_source_state_now("spotify")
        finally:
            st.set_write_callback("spotify", None)
        assert len(calls) == 1
        assert calls[0] == st.get_spotify_save_data()


class TestProgressAnchor:
    """isPlaying is persisted but its anchor is not; never report end-of-track."""

    def test_restart_without_anchor_reports_stored_progress(self) -> None:
        st.state.update({
            "isPlaying": True, "trackProgress": 0, "trackDuration": 200000,
            "trackProgressStartTimestamp": 0,
        })
        assert st.get_interpolated_track_progress() == 0

    def test_sc_restart_without_anchor_reports_stored_progress(self) -> None:
        st.state.update({
            "scIsPlaying": True, "scProgressMs": 0, "scDurationMs": 200000,
            "scProgressStartTimestamp": 0,
        })
        assert st.get_interpolated_sc_progress() == 0

    def test_anchor_still_interpolates(self) -> None:
        import time as _time
        st.state.update({
            "isPlaying": True, "trackProgress": 1000, "trackDuration": 200000,
            "trackProgressStartTimestamp": _time.time() * 1000 - 1000,
        })
        assert st.get_interpolated_track_progress() == pytest.approx(2000, abs=200)

    def test_restore_marks_playing_source_paused_without_anchor(self) -> None:
        path = st.SOURCES["spotify"].state_file
        original = None
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"isPlaying": True, "volume": 0.7, "trackDuration": 200000}, f)
            st.state["isPlaying"] = False
            st.state["trackProgressStartTimestamp"] = 0
            st.read_spotify_state_from_file()
            assert st.state["isPlaying"] is False
            assert st.state["volume"] == 0.7
        finally:
            if original is None:
                os.remove(path)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(original)
