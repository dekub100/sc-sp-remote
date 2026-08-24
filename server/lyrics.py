from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import uuid
from typing import Any, Optional

import aiohttp
from broadcast import broadcast_lyrics_update
from config import CONFIG_PATH, LYRICS_CACHE_DB, config
from log import logger
from state import state

_connection: sqlite3.Connection | None = None
_connection_path: str | None = None
_session: aiohttp.ClientSession | None = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None:
        _session = aiohttp.ClientSession(headers={"User-Agent": "ScSpRemote/1.0"})
    return _session


def _get_conn() -> sqlite3.Connection:
    global _connection, _connection_path
    if _connection is None or _connection_path != LYRICS_CACHE_DB:
        if _connection is not None:
            _connection.close()
        _connection = sqlite3.connect(LYRICS_CACHE_DB, check_same_thread=False)
        _connection_path = LYRICS_CACHE_DB
    return _connection


def _close_connection() -> None:
    global _connection, _connection_path
    if _connection is not None:
        _connection.close()
        _connection = None
        _connection_path = None


async def _close_session() -> None:
    global _session
    if _session is not None:
        await _session.close()
        _session = None


# --- Musixmatch provider ---

MXM_BASE_URL: str = "https://apic-appmobile.musixmatch.com/ws/1.1"
MXM_APP_ID: str = "mac-ios-v2.0"
_MXM_HEADERS: dict[str, str] = {
    "Host": "apic-appmobile.musixmatch.com",
    "x-mxm-app-version": "10.1.1",
    "X-User-Agent": "Musixmatch/2025120901 CFNetwork/3860.300.31 Darwin/25.2.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json",
}
_mxm_guid: str | None = None


def _write_config_to_disk() -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def _get_mxm_timeout() -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(total=config.get("lyricsFetchTimeoutSeconds", 15))


async def _mxm_fetch_token() -> str:
    global _mxm_guid
    if _mxm_guid is None:
        _mxm_guid = str(uuid.uuid4()).upper()
    async with _get_session().get(
        f"{MXM_BASE_URL}/token.get",
        params={"app_id": MXM_APP_ID, "guid": _mxm_guid, "format": "json"},
        headers=_MXM_HEADERS,
        timeout=_get_mxm_timeout(),
    ) as resp:
        data: dict[str, Any] = await resp.json(content_type=None)
    header: dict[str, Any] = _as_dict(data.get("message", {})).get("header", {})
    body: dict[str, Any] = _as_dict(_as_dict(data.get("message", {})).get("body"))
    token: str = body.get("user_token", "") or ""
    if header.get("status_code") != 200 or not token:
        raise RuntimeError(f"token.get failed ({header.get('status_code')}: {header.get('hint', 'no hint')})")
    config["musixmatchToken"] = token
    try:
        _write_config_to_disk()
    except OSError as e:
        logger.warning(f"Lyrics: Could not persist Musixmatch token: {e}")
    return token


async def refresh_musixmatch_token() -> str:
    """Force-fetch a fresh usertoken (manual refresh entry point)."""
    logger.info("Lyrics: Refreshing Musixmatch token")
    return await _mxm_fetch_token()


async def _get_mxm_token(force: bool = False) -> str:
    token: str = config.get("musixmatchToken", "") or ""
    if token and not force:
        return token
    return await _mxm_fetch_token()


async def _mxm_get(path: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
    """GET a Musixmatch endpoint; auto-refreshes the token once on auth failure."""
    # ponytail: reactive-only token refresh — add a proactive expiry check if
    # tokens start expiring mid-session instead of at first 401.
    for attempt in range(2):
        try:
            params["usertoken"] = await _get_mxm_token(force=attempt > 0)
        except Exception as e:
            logger.warning(f"Lyrics: Musixmatch token fetch failed: {type(e).__name__}: {e}")
            return None
        try:
            async with _get_session().get(
                f"{MXM_BASE_URL}/{path}",
                params=params,
                headers=_MXM_HEADERS,
                timeout=_get_mxm_timeout(),
            ) as resp:
                data: dict[str, Any] = await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"Lyrics: Musixmatch request failed ({path}): {type(e).__name__}: {e}")
            return None
        header: dict[str, Any] = data.get("message", {}).get("header", {})
        if header.get("status_code") == 401 or "auth" in str(header.get("hint", "")).lower():
            logger.info("Lyrics: Musixmatch token rejected, refreshing and retrying once")
            continue
        return data
    return None


def _parse_richsync(richsync_body: str) -> list[dict[str, Any]]:
    """Parse MXM richsync JSON into absolute-time karaoke lines.

    Shape: [{startTime, endTime, words: [{text, time}]}] where word times are
    absolute ms offsets into the track.
    """
    karaoke: list[dict[str, Any]] = []
    for line in json.loads(richsync_body):
        start_ms: int = round(line["ts"] * 1000)
        end_ms: int = round(line["te"] * 1000)
        raw_words: list[dict[str, Any]] = line.get("l", [])
        words: list[dict[str, Any]] = []
        for i, w in enumerate(raw_words):
            word_start: int = start_ms + round(w.get("o", 0) * 1000)
            next_start: int = start_ms + round(raw_words[i + 1]["o"] * 1000) if i + 1 < len(raw_words) else end_ms
            words.append({"text": w.get("c", ""), "time": min(word_start, next_start)})
        karaoke.append({"startTime": start_ms, "endTime": end_ms, "words": words})
    return karaoke


def _subtitle_to_lrc(subtitle_body: str) -> str:
    """Convert MXM subtitle JSON ([{text, time:{total}}]) to LRC text so it fits the existing cache/parser."""
    lrc_lines: list[str] = []
    for line in json.loads(subtitle_body):
        total: float = float(line["time"]["total"])
        minutes: int = int(total // 60)
        seconds: float = total - minutes * 60
        text: str = str(line.get("text", ""))
        lrc_lines.append(f"[{minutes:02d}:{seconds:05.2f}]{text}")
    return "\n".join(lrc_lines)


def _as_dict(value: Any) -> dict[str, Any]:
    """Musixmatch returns [] instead of {} for empty bodies — coerce so .get() chains are safe."""
    return value if isinstance(value, dict) else {}


async def _fetch_musixmatch(params: dict[str, Any], duration_ms: int) -> Optional[dict[str, Any]]:
    """Fetch lyrics from Musixmatch. Returns normalized result dict or None to fall through."""
    durr: float = duration_ms / 1000
    macro_data: Optional[dict[str, Any]] = await _mxm_get("macro.subtitles.get", {
        "app_id": MXM_APP_ID,
        "format": "json",
        "namespace": "lyrics_richsynched",
        "subtitle_format": "mxm",
        "q_album": params["album_name"],
        "q_artist": params["artist_name"],
        "q_artists": params["artist_name"],
        "q_track": params["track_name"],
        "q_duration": durr,
        "f_subtitle_length": max(1, round(durr)),
        "part": "track_lyrics_translation_status,track_structure",
    })
    if macro_data is None:
        return None
    try:
        macro_calls: dict[str, Any] = _as_dict(_as_dict(_as_dict(macro_data["message"])["body"])["macro_calls"])
        matcher_header: dict[str, Any] = _as_dict(_as_dict(macro_calls["matcher.track.get"])["message"])["header"]
        if matcher_header.get("status_code") != 200:
            logger.info(f"Lyrics: Musixmatch matcher failed ({matcher_header.get('mode')})")
            return None
        meta: dict[str, Any] = _as_dict(_as_dict(macro_calls["matcher.track.get"])["message"])["body"]
    except (KeyError, TypeError):
        return None

    track: dict[str, Any] = meta.get("track", {})
    instrumental: bool = bool(track.get("instrumental", False))
    lyrics_section: dict[str, Any] = _as_dict(
        _as_dict(_as_dict(_as_dict(macro_calls.get("track.lyrics.get"))["message"])["body"]).get("lyrics", {})
    )
    if lyrics_section.get("restricted"):
        logger.info("Lyrics: Musixmatch lyrics restricted, falling through")
        return None

    synced_raw: str = ""
    subtitle_list: list[Any] = (
        _as_dict(_as_dict(_as_dict(macro_calls.get("track.subtitles.get"))["message"])["body"]).get("subtitle_list", []) or []
    )
    subtitle: dict[str, Any] = subtitle_list[0].get("subtitle", {}) if subtitle_list else {}
    if track.get("has_subtitles") and subtitle.get("subtitle_body"):
        try:
            synced_raw = _subtitle_to_lrc(subtitle["subtitle_body"])
        except (KeyError, TypeError, ValueError):
            synced_raw = ""

    plain: str = ""
    if not synced_raw and (track.get("has_lyrics") or track.get("has_lyrics_crowd")) and lyrics_section.get("lyrics_body"):
        plain = lyrics_section["lyrics_body"]

    if instrumental:
        synced_raw = ""
        plain = ""
    elif not synced_raw and not plain:
        return None

    karaoke: list[dict[str, Any]] = []
    if track.get("has_richsync") and not instrumental:
        richsync_data = await _mxm_get("track.richsync.get", {
            "app_id": MXM_APP_ID,
            "format": "json",
            "subtitle_format": "mxm",
            "commontrack_id": track.get("commontrack_id"),
            "f_subtitle_length": track.get("track_length", max(1, round(durr))),
            "q_duration": track.get("track_length", max(1, round(durr))),
        })
        richsync_body: str = (
            _as_dict(_as_dict(_as_dict(richsync_data.get("message"))["body"])["richsync"]).get("richsync_body", "")
            if richsync_data else ""
        )
        if richsync_body:
            try:
                karaoke = _parse_richsync(richsync_body)
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Lyrics: Failed to parse richsync: {e}")

    return {"synced_raw": synced_raw, "plain": plain, "instrumental": instrumental, "karaoke": karaoke, "provider": "musixmatch"}


async def _fetch_lrclib(params: dict[str, Any], duration_ms: int) -> Optional[dict[str, Any]]:
    session = _get_session()
    async with session.get(
        "https://lrclib.net/api/get",
        params=params,
        timeout=_get_mxm_timeout(),
    ) as resp:
        if resp.status != 200:
            if resp.status != 404:
                logger.warning(f"Lyrics: LRCLIB returned status {resp.status}")
            return None
        data: dict[str, Any] = await resp.json()
    synced_raw = data.get("syncedLyrics") or ""
    plain = data.get("plainLyrics") or ""
    if not synced_raw and not plain:
        return None
    return {"synced_raw": synced_raw, "plain": plain, "instrumental": bool(data.get("instrumental", False)), "karaoke": [], "provider": "lrclib"}


def parse_synced_lyrics(lrc_text: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    pattern: re.Pattern[str] = re.compile(r'\[(\d+):(\d+)[.,](\d+)\](.*)')
    for line in lrc_text.split('\n'):
        m: Optional[re.Match[str]] = pattern.match(line.strip())
        if m:
            minutes: int = int(m.group(1))
            seconds: int = int(m.group(2))
            frac: str = m.group(3)
            text: str = m.group(4).strip()
            if len(frac) == 2:
                frac_ms: int = int(frac) * 10
            elif len(frac) == 3:
                frac_ms = int(frac)
            else:
                frac_ms = int(frac[:2]) * 10
            time_ms: int = (minutes * 60 + seconds) * 1000 + frac_ms
            lines.append({"time": time_ms, "text": text})
    return sorted(lines, key=lambda x: x["time"])


def init_lyrics_cache() -> None:
    conn: sqlite3.Connection = _get_conn()
    conn.execute("""
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
    """)
    # Migrations for pre-existing DBs.
    for column in ("karaoke TEXT", "provider TEXT"):
        try:
            conn.execute(f"ALTER TABLE lyrics_cache ADD COLUMN {column}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    logger.info(f"Lyrics cache: Initialized at {LYRICS_CACHE_DB}")


def get_cached_lyrics(params: dict[str, Any]) -> Optional[tuple[Any, ...]]:
    conn: sqlite3.Connection = _get_conn()
    row: Optional[tuple[Any, ...]] = conn.execute(
        "SELECT synced_lyrics, plain_lyrics, instrumental, karaoke, provider FROM lyrics_cache WHERE artist_name=? AND track_name=? AND album_name=? AND duration=?",
        (params["artist_name"], params["track_name"], params["album_name"], params["duration"])
    ).fetchone()
    return row


def set_cached_lyrics(params: dict[str, Any], synced_lyrics: Optional[str], plain_lyrics: Optional[str], instrumental: bool, karaoke_json: str = "", provider: str = "") -> None:
    conn: sqlite3.Connection = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO lyrics_cache (artist_name, track_name, album_name, duration, synced_lyrics, plain_lyrics, instrumental, karaoke, provider) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (params["artist_name"], params["track_name"], params["album_name"], params["duration"], synced_lyrics, plain_lyrics, 1 if instrumental else 0, karaoke_json, provider)
    )
    conn.commit()


def _track_still_current(track_uri: str) -> bool:
    return state["currentTrack"]["trackUri"] == track_uri


async def fetch_and_broadcast_lyrics(track_uri: str, track_name: str, artist_name: str, album_name: str, duration_ms: int) -> None:
    duration_s: int = max(1, round(duration_ms / 1000))
    params: dict[str, Any] = {
        "artist_name": artist_name,
        "track_name": track_name,
        "album_name": album_name,
        "duration": duration_s
    }
    logger.info(f"Lyrics: Fetching for '{track_name}' by '{artist_name}'")

    cached = get_cached_lyrics(params)
    if cached:
        synced_raw, plain, instrumental, karaoke_json, provider = cached
        synced: list[dict[str, Any]] = parse_synced_lyrics(synced_raw) if synced_raw else []
        karaoke: list[dict[str, Any]] = []
        if karaoke_json:
            try:
                karaoke = json.loads(karaoke_json)
            except (TypeError, ValueError):
                karaoke = []
        if not _track_still_current(track_uri):
            return
        state["lyrics"] = {
            "trackUri": track_uri,
            "synced": synced,
            "plain": plain or "",
            "available": True,
            "instrumental": bool(instrumental),
            "karaoke": karaoke,
            "provider": provider or "",
            "loading": False
        }
        karaoke_note = " (karaoke)" if karaoke else ""
        logger.info(f"Lyrics: Cache hit for '{track_name}' ({len(synced)} synced lines, provider: {provider or 'unknown'}{karaoke_note})")
        await broadcast_lyrics_update()
        return

    result: Optional[dict[str, Any]] = None
    try:
        provider_order: list[str] = config.get("lyricsProviderOrder") or ["lrclib"]
        for provider in provider_order:
            try:
                if provider == "musixmatch":
                    result = await _fetch_musixmatch(params, duration_ms)
                elif provider == "lrclib":
                    result = await _fetch_lrclib(params, duration_ms)
                else:
                    logger.warning(f"Lyrics: Unknown provider in lyricsProviderOrder: {provider}")
            except asyncio.TimeoutError:
                logger.error(f"Lyrics: {provider} timed out for '{track_name}' by '{artist_name}'")
            except Exception as e:
                logger.error(f"Lyrics: {provider} failed for '{track_name}': {type(e).__name__}: {e}")
            if result:
                break
            logger.info(f"Lyrics: {provider} returned no results")

        if result:
            if not _track_still_current(track_uri):
                logger.info("Lyrics: Track changed during fetch, discarding.")
                return
            synced_raw = result["synced_raw"]
            plain = result["plain"]
            instrumental = result["instrumental"]
            karaoke = result["karaoke"]
            synced = parse_synced_lyrics(synced_raw) if synced_raw else []
            state["lyrics"] = {
                "trackUri": track_uri,
                "synced": synced,
                "plain": plain,
                "available": True,
                "instrumental": instrumental,
                "karaoke": karaoke,
                "provider": result["provider"],
                "loading": False
            }
            karaoke_note = " (karaoke)" if result["karaoke"] else ""
            logger.info(f"Lyrics: Found {len(synced)} synced lines for '{track_name}' (provider: {result['provider']}{karaoke_note})")
            set_cached_lyrics(
                params,
                synced_raw,
                "" if synced_raw else plain,
                instrumental,
                json.dumps(karaoke) if karaoke else "",
                result["provider"]
            )
            await broadcast_lyrics_update()
        else:
            logger.info(f"Lyrics: Not found for '{track_name}'")
            if _track_still_current(track_uri):
                state["lyrics"] = {"trackUri": track_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "karaoke": [], "provider": "", "loading": False}
                await broadcast_lyrics_update()
    except Exception as e:
        logger.error(f"Lyrics: Fetch failed for '{track_name}': {type(e).__name__}: {e}")
        if _track_still_current(track_uri):
            state["lyrics"]["loading"] = False
            await broadcast_lyrics_update()
