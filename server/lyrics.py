import asyncio
import re
import sqlite3

import aiohttp
from broadcast import broadcast_lyrics_update
from log import logger
from state import state


def _get_db_path():
    from server import LYRICS_CACHE_DB
    return LYRICS_CACHE_DB


def parse_synced_lyrics(lrc_text):
    lines = []
    pattern = re.compile(r'\[(\d+):(\d+)[.,](\d+)\](.*)')
    for line in lrc_text.split('\n'):
        m = pattern.match(line.strip())
        if m:
            minutes = int(m.group(1))
            seconds = int(m.group(2))
            frac = m.group(3)
            text = m.group(4).strip()
            if len(frac) == 2:
                frac_ms = int(frac) * 10
            elif len(frac) == 3:
                frac_ms = int(frac)
            else:
                frac_ms = int(frac[:2]) * 10
            time_ms = (minutes * 60 + seconds) * 1000 + frac_ms
            lines.append({"time": time_ms, "text": text})
    return sorted(lines, key=lambda x: x["time"])


def init_lyrics_cache():
    conn = sqlite3.connect(_get_db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lyrics_cache (
            artist_name TEXT NOT NULL,
            track_name TEXT NOT NULL,
            album_name TEXT NOT NULL,
            duration INTEGER NOT NULL,
            synced_lyrics TEXT,
            plain_lyrics TEXT,
            instrumental INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (artist_name, track_name, album_name, duration)
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"Lyrics cache: Initialized at {_get_db_path()}")


def get_cached_lyrics(params):
    conn = sqlite3.connect(_get_db_path())
    try:
        row = conn.execute(
            "SELECT synced_lyrics, plain_lyrics, instrumental FROM lyrics_cache WHERE artist_name=? AND track_name=? AND album_name=? AND duration=?",
            (params["artist_name"], params["track_name"], params["album_name"], params["duration"])
        ).fetchone()
        return row
    finally:
        conn.close()


def set_cached_lyrics(params, synced_lyrics, plain_lyrics, instrumental):
    conn = sqlite3.connect(_get_db_path())
    try:
        conn.execute(
            "INSERT OR REPLACE INTO lyrics_cache (artist_name, track_name, album_name, duration, synced_lyrics, plain_lyrics, instrumental) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (params["artist_name"], params["track_name"], params["album_name"], params["duration"], synced_lyrics, plain_lyrics, 1 if instrumental else 0)
        )
        conn.commit()
    finally:
        conn.close()


async def fetch_and_broadcast_lyrics(track_uri, track_name, artist_name, album_name, duration_ms):
    duration_s = max(1, round(duration_ms / 1000))
    params = {
        "artist_name": artist_name,
        "track_name": track_name,
        "album_name": album_name,
        "duration": duration_s
    }
    logger.info(f"Lyrics: Fetching for '{track_name}' by '{artist_name}'")

    cached = get_cached_lyrics(params)
    if cached:
        synced_raw, plain, instrumental = cached
        synced = parse_synced_lyrics(synced_raw) if synced_raw else []
        if state["currentTrack"]["trackUri"] != track_uri:
            return
        state["lyrics"] = {
            "trackUri": track_uri,
            "synced": synced,
            "plain": plain or "",
            "available": True,
            "instrumental": bool(instrumental),
            "loading": False
        }
        logger.info(f"Lyrics: Cache hit for '{track_name}' ({len(synced)} synced lines)")
        await broadcast_lyrics_update()
        return

    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "SpicetifyRemote/1.0 (https://github.com/dekub/spicetify-remote)"}) as session:
            async with session.get(
                "https://lrclib.net/api/get",
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if state["currentTrack"]["trackUri"] != track_uri:
                        logger.info("Lyrics: Track changed during fetch, discarding.")
                        return
                    synced_raw = data.get("syncedLyrics") or ""
                    plain = data.get("plainLyrics") or ""
                    instrumental = data.get("instrumental", False)
                    synced = parse_synced_lyrics(synced_raw) if synced_raw else []
                    state["lyrics"] = {
                        "trackUri": track_uri,
                        "synced": synced,
                        "plain": plain,
                        "available": True,
                        "instrumental": instrumental,
                        "loading": False
                    }
                    logger.info(f"Lyrics: Found {len(synced)} synced lines for '{track_name}'")
                    set_cached_lyrics(params, synced_raw, "" if synced_raw else plain, instrumental)
                    await broadcast_lyrics_update()
                elif resp.status == 404:
                    logger.info(f"Lyrics: Not found for '{track_name}'")
                    if state["currentTrack"]["trackUri"] == track_uri:
                        state["lyrics"] = {"trackUri": track_uri, "synced": [], "plain": "", "available": False, "instrumental": False, "loading": False}
                        await broadcast_lyrics_update()
                else:
                    logger.warning(f"Lyrics: LRCLIB returned status {resp.status}")
    except asyncio.TimeoutError:
        logger.error(f"Lyrics: Timed out after 30s for '{track_name}' by '{artist_name}'")
    except Exception as e:
        logger.error(f"Lyrics: Fetch failed for '{track_name}': {type(e).__name__}: {e}")
