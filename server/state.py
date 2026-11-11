from __future__ import annotations

import asyncio
import copy
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from config import SC_STATE_FILE, STATE_FILE, STATE_SAVE_DEBOUNCE_SECONDS, config
from log import logger

_MAX_MS: int = 7 * 24 * 60 * 60 * 1000  # 7 days; rejects absurd clock values


def as_ms(value: Any, default: int = 0) -> int:
    """Coerce a state field to a sane non-negative millisecond value.

    State is fed by WebSocket clients; one bad payload must never turn every
    /api/state request into a 500. Handlers validate before writing, this is
    the last line of defence for restored/legacy state.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(max(0, min(value, _MAX_MS)))


def as_volume(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class SourceSpec:
    """Everything the server needs to know about one playback source.

    State stays flat (`state["volume"]`, `state["scVolume"]`, ...); this table
    names the fields so read/save/interpolate/broadcast/reset can be shared
    instead of duplicated per source.
    """

    key: str
    label: str
    client_type: str
    state_file: str
    persisted: tuple[str, ...]
    runtime: tuple[str, ...]
    playing_key: str
    progress_key: str
    duration_key: str
    anchor_key: str
    volume_key: str
    volume_msg_type: str
    playback_msg_type: str
    progress_msg_type: str
    progress_field: str
    duration_field: str
    cover_path: tuple[str, ...]
    update_fields: tuple[tuple[str, str, str], ...]
    track_fields: tuple[str, ...] = ()
    cover_field: Optional[str] = None
    defaults: dict[str, Any] = field(default_factory=dict)
    serializers: dict[str, Callable[[Any], Any]] = field(default_factory=dict)


_SPOTIFY_DEFAULTS: dict[str, Any] = {
    "volume": config["defaultVolume"],
    "isPlaying": False,
    "currentTrack": {
        "trackName": "No song playing",
        "artistName": "",
        "albumName": "",
        "trackUri": "",
        "albumUri": "",
        "artistUri": "",
        "albumArtUrl": "",
    },
    "trackProgress": 0,
    "trackDuration": 0,
    "trackProgressStartTimestamp": 0,
    "isShuffling": False,
    "repeatStatus": 0,
    "isLiked": False,
    "lyrics": {
        "trackUri": "",
        "synced": [],
        "plain": "",
        "available": False,
        "instrumental": False,
        "loading": False,
    },
}

_SOUNDCLOUD_DEFAULTS: dict[str, Any] = {
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
    "scIsShuffling": False,
    "scRepeatStatus": 0,
}

SOURCES: dict[str, SourceSpec] = {
    "spotify": SourceSpec(
        key="spotify",
        label="Spotify",
        client_type="spicetify",
        state_file=STATE_FILE,
        persisted=(
            "volume", "isPlaying", "currentTrack", "trackDuration",
            "isShuffling", "repeatStatus", "isLiked",
        ),
        runtime=("trackProgress", "trackProgressStartTimestamp", "lyrics"),
        playing_key="isPlaying",
        progress_key="trackProgress",
        duration_key="trackDuration",
        anchor_key="trackProgressStartTimestamp",
        volume_key="volume",
        volume_msg_type="volumeUpdate",
        playback_msg_type="playbackUpdate",
        progress_msg_type="progressUpdate",
        progress_field="progress",
        duration_field="duration",
        cover_path=("currentTrack", "albumArtUrl"),
        update_fields=(
            ("volume", "volume", "volume"),
            ("isPlaying", "isPlaying", "bool"),
            ("isShuffling", "isShuffling", "bool"),
            ("repeatStatus", "repeatStatus", "repeat"),
            ("isLiked", "isLiked", "bool"),
            ("duration", "trackDuration", "ms"),
            ("progress", "trackProgress", "ms"),
        ),
        track_fields=("trackName", "artistName", "albumName", "albumUri", "artistUri", "albumArtUrl"),
        defaults=_SPOTIFY_DEFAULTS,
        serializers={"volume": lambda value: round(as_volume(value, 0.0), 2)},
    ),
    "soundcloud": SourceSpec(
        key="soundcloud",
        label="SoundCloud",
        client_type="soundcloud",
        state_file=SC_STATE_FILE,
        persisted=("scTrack", "scArtist", "scVolume"),
        runtime=(
            "scAlbum", "scId", "scCoverUrl", "scIsPlaying", "scProgressMs",
            "scDurationMs", "scProgressStartTimestamp", "scIsLiked",
            "scIsShuffling", "scRepeatStatus",
        ),
        playing_key="scIsPlaying",
        progress_key="scProgressMs",
        duration_key="scDurationMs",
        anchor_key="scProgressStartTimestamp",
        volume_key="scVolume",
        volume_msg_type="scVolumeUpdate",
        playback_msg_type="scPlaybackUpdate",
        progress_msg_type="scProgressUpdate",
        progress_field="progressMs",
        duration_field="durationMs",
        cover_path=("scCoverUrl",),
        update_fields=(
            ("track", "scTrack", "text"),
            ("artist", "scArtist", "text"),
            ("album", "scAlbum", "text"),
            ("id", "scId", "text"),
            ("isPlaying", "scIsPlaying", "bool"),
            ("progressMs", "scProgressMs", "ms"),
            ("durationMs", "scDurationMs", "ms"),
            ("volume", "scVolume", "volume"),
            ("isLiked", "scIsLiked", "bool"),
            ("isShuffling", "scIsShuffling", "bool"),
            ("repeatStatus", "scRepeatStatus", "repeat"),
        ),
        cover_field="coverUrl",
        defaults=_SOUNDCLOUD_DEFAULTS,
        serializers={"scVolume": as_volume},
    ),
}

SOURCE_BY_CLIENT_TYPE: dict[str, SourceSpec] = {
    spec.client_type: spec for spec in SOURCES.values()
}


def _initial_state() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for spec in SOURCES.values():
        merged.update(copy.deepcopy(spec.defaults))
    return merged


state: dict[str, Any] = _initial_state()


@dataclass
class _SaveRuntime:
    timer: Optional[asyncio.Task[None]] = None
    callback: Optional[Callable[[dict[str, Any]], None]] = None


_save_runtime: dict[str, _SaveRuntime] = {key: _SaveRuntime() for key in SOURCES}


def set_write_callback(source: str, callback: Optional[Callable[[dict[str, Any]], None]]) -> None:
    _save_runtime[source].callback = callback


def set_spotify_write_callback(callback: Optional[Callable[[dict[str, Any]], None]]) -> None:
    set_write_callback("spotify", callback)


def set_sc_write_callback(callback: Optional[Callable[[dict[str, Any]], None]]) -> None:
    set_write_callback("soundcloud", callback)


def _write_json_file(path: str, data: dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_source_state_now(source: str) -> None:
    """Write one source's persisted state synchronously (startup/shutdown/tests)."""
    spec: SourceSpec = SOURCES[source]
    callback = _save_runtime[source].callback
    data: dict[str, Any] = get_source_save_data(source)
    if callback is None:
        _write_json_file(spec.state_file, data)
    else:
        callback(data)


def read_source_state_from_file(source: str) -> None:
    spec: SourceSpec = SOURCES[source]
    if not os.path.exists(spec.state_file):
        return
    try:
        with open(spec.state_file, "r") as f:
            saved_state: dict[str, Any] = json.load(f)
            for key in spec.persisted:
                if key not in saved_state:
                    continue
                if key == "currentTrack":
                    state[key].update(saved_state[key] or {})
                else:
                    state[key] = saved_state[key]
            logger.info(f"Server: Loaded {spec.label} state from {os.path.basename(spec.state_file)}")
    except Exception as e:
        logger.error(f"Server: Error reading {spec.label} state file: {e}")


def read_spotify_state_from_file() -> None:
    read_source_state_from_file("spotify")


def read_sc_state_from_file() -> None:
    read_source_state_from_file("soundcloud")


def reset_source_state(source: str) -> None:
    """Restore one source to its initial values (used by the test fixture)."""
    state.update(copy.deepcopy(SOURCES[source].defaults))


async def save_source_state_debounced(source: str) -> None:
    runtime: _SaveRuntime = _save_runtime[source]
    if runtime.timer:
        runtime.timer.cancel()
    runtime.timer = asyncio.create_task(
        _actually_save_after_delay(SOURCES[source], float(STATE_SAVE_DEBOUNCE_SECONDS))
    )


async def save_spotify_state_debounced() -> None:
    await save_source_state_debounced("spotify")


async def save_sc_state_debounced() -> None:
    await save_source_state_debounced("soundcloud")


def get_source_save_data(source: str) -> dict[str, Any]:
    spec: SourceSpec = SOURCES[source]
    data: dict[str, Any] = {}
    for key in spec.persisted:
        value: Any = state[key]
        serializer = spec.serializers.get(key)
        data[key] = serializer(value) if serializer else value
    return data


def get_spotify_save_data() -> dict[str, Any]:
    return get_source_save_data("spotify")


def get_sc_save_data() -> dict[str, Any]:
    return get_source_save_data("soundcloud")


def get_interpolated_progress(source: str, now_ms: Optional[float] = None) -> int:
    """Current position in ms, interpolating from the last progress anchor."""
    spec: SourceSpec = SOURCES[source]
    progress: int = as_ms(state[spec.progress_key])
    if not state[spec.playing_key]:
        return progress
    anchor: Any = state[spec.anchor_key]
    # isPlaying is persisted but the anchor is not, so a fresh process can have
    # isPlaying=True with no anchor. Interpolating from 0 would report the end
    # of the track; the stored position is the only truthful value.
    if not isinstance(anchor, (int, float)) or isinstance(anchor, bool) or anchor <= 0:
        return progress
    now: float = now_ms if now_ms is not None else time.time() * 1000
    elapsed = now - anchor
    return int(min(progress + max(0, elapsed), as_ms(state[spec.duration_key])))


def get_interpolated_track_progress() -> int:
    return get_interpolated_progress("spotify")


def get_interpolated_sc_progress() -> int:
    return get_interpolated_progress("soundcloud")


def get_source_cover_url(source: str) -> str:
    """Album art URL for a source, or "" when the cover toggle is off (stream safety)."""
    if not config.get("enableAlbumArt", True):
        return ""
    value: Any = state
    for key in SOURCES[source].cover_path:
        value = value[key]
    return value


def get_album_art_url() -> str:
    return get_source_cover_url("spotify")


def get_sc_cover_url() -> str:
    return get_source_cover_url("soundcloud")


async def _actually_save_after_delay(spec: SourceSpec, delay: float) -> None:
    try:
        await asyncio.sleep(delay)
        callback = _save_runtime[spec.key].callback
        data: dict[str, Any] = get_source_save_data(spec.key)
        loop = asyncio.get_running_loop()
        if callback is None:
            await loop.run_in_executor(None, _write_json_file, spec.state_file, data)
        else:
            await loop.run_in_executor(None, callback, data)
        logger.info(f"Server: Saved {spec.label} state to {os.path.basename(spec.state_file)} (debounced)")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Server: Error in debounced {spec.label} save: {e}")


def cancel_pending_save() -> None:
    for runtime in _save_runtime.values():
        if runtime.timer:
            runtime.timer.cancel()
            runtime.timer = None
    logger.debug("Server: Pending save timers cancelled.")
