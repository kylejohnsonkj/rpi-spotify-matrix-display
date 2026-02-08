# Purpose: Lyrics fetching module integrating with LibreLyrics.
import time
import threading
import logging
from typing import Optional

from librelyrics import LibreLyrics
from librelyrics.exceptions import RateLimitError, LyricsNotFound

logger = logging.getLogger(__name__)

class LyricsFetcher:
    def __init__(self, config):
        self.config = config
        self.ll: Optional[LibreLyrics] = None
        self.last_track_id: Optional[str] = None
        self.last_lyrics: Optional[dict] = None
        self.rate_limit_until = 0.0
        self._fetching_lyrics_id: Optional[str] = None
        
        self._setup_librelyrics()

    def _setup_librelyrics(self):
        sp_dc = self.config.get('Spotify', 'sp_dc', fallback=None)
                
        if sp_dc and len(sp_dc) > 100:
            try:
                self.ll = LibreLyrics(config={'plugins': {'spotify': {'sp_dc': sp_dc}}})
                logger.info("LibreLyrics initialized successfully")
            except Exception as e:
                logger.error(f"LibreLyrics failed to initialize: {e}", exc_info=True)
                self.ll = None
        else:
            logger.info("Lyrics fetching disabled. Please provide your sp_dc cookie in config.ini.")
            logger.info("- See https://github.com/akashrchandran/syrics/wiki/Finding-sp_dc")
            self.ll = None

    def get_lyrics(self, track_id: str, track_name: str = "", allow_fetch: bool = True) -> Optional[dict]:
        if not self.ll or not track_id:
            return {}
            
        if track_id != self.last_track_id:
            if not allow_fetch or self._fetching_lyrics_id == track_id or time.time() < self.rate_limit_until:
                return None
            
            self._fetching_lyrics_id = track_id
            
            def fetch_thread():
                try:
                    res = self.ll.fetch(f"https://open.spotify.com/track/{track_id}")
                    lines = []
                    for line in res.lyrics:
                        lines.append({
                            'startTimeMs': line.start_ms if line.start_ms is not None else 0,
                            'words': line.text
                        })
                    is_synced = any(line.start_ms is not None for line in res.lyrics)
                    self.last_lyrics = {
                        'lyrics': {
                            'lines': lines,
                            'syncType': 'LINE_SYNCED' if is_synced else 'UNSYNCED'
                        }
                    }
                    self.last_track_id = track_id
                    logger.info("Lyrics fetched ✅")
                except RateLimitError as e:
                    retry = getattr(e, 'retry_after', 30) or 30
                    self.rate_limit_until = time.time() + retry
                    logger.warning(f"Lyrics rate limited ❌ (retry in {retry}s): {e}")
                    self.last_lyrics = {}
                    self.last_track_id = track_id
                except LyricsNotFound:
                    logger.info("Lyrics not found ❌")
                    self.last_lyrics = {}
                    self.last_track_id = track_id
                except Exception as e:
                    logger.error(f"Lyrics exception ❌: {e}")
                    self.last_lyrics = {}
                    self.last_track_id = track_id
                finally:
                    self._fetching_lyrics_id = None
            
            threading.Thread(target=fetch_thread, daemon=True).start()
            return None
            
        return self.last_lyrics
