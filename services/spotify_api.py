# Purpose: Manages Spotify API integration and current playback state polling.
import os
import time
import logging
from dataclasses import dataclass

import threading
import configparser
from typing import Optional, Dict, Any

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from services.lyrics_api import LyricsFetcher
from utils.lyric_utils import clean_text


LYRIC_FETCH_DELAY_SEC = 1.5
logger = logging.getLogger(__name__)

@dataclass
class PlaybackInfo:
    artist: Optional[str]
    title: Optional[str]
    art_url: Optional[str]
    is_playing: bool
    progress_ms: int
    duration_ms: int
    lyrics: Optional[dict] = None
    track_id: Optional[str] = None


class SpotifyModule:
    """
    Manages Spotify API interactions, authentication, and state polling.
    Exposes methods to manually fetch the current playback state or start a background polling thread.
    """

    def __init__(self, config: configparser.ConfigParser, is_emulated: bool = False):
        self.config = config
        self.is_emulated = is_emulated
        self.spotify: Optional[spotipy.Spotify] = None
        self.lyrics_fetcher = LyricsFetcher(config)
        self.device_whitelist = self._parse_whitelist(config)
        self.rate_limit_until = 0.0
        self.last_track_id = None
        self.track_start_time = 0.0
        
        self._setup_spotify()

    def _setup_spotify(self):
        try:
            cfg = self.config['Spotify']
            os.environ["SPOTIPY_CLIENT_ID"] = cfg['client_id']
            os.environ["SPOTIPY_CLIENT_SECRET"] = cfg['client_secret']
            os.environ["SPOTIPY_REDIRECT_URI"] = "http://127.0.0.1:8080/callback"
            
            cache_path = ".cache"
            if os.path.exists(cache_path) and not os.access(cache_path, os.W_OK):
                print(f"\n❌ Error: Cannot write to {cache_path} (likely owned by root).")
                print(f"To fix this, please run the following command:\n    \033[1;36msudo chown {os.environ.get('USER', 'pi')} {cache_path}\033[0m\n")
                sys.exit(1)
            
            auth_manager = SpotifyOAuth(
                scope="user-read-currently-playing, user-read-playback-state",
                open_browser=False
            )
            
            needs_auth = not auth_manager.cache_handler.get_cached_token()
            
            self.spotify = spotipy.Spotify(
                auth_manager=auth_manager,
                requests_timeout=10
            )
            
            if needs_auth:
                # Force authentication immediately so we can show the instructions
                auth_manager.get_access_token(as_dict=False)
                print("\n" + "="*70)
                print("🎉 Spotify authentication successful!")
                
                try:
                    from rgbmatrix import RGBMatrix
                    is_rpi = True
                except ImportError:
                    is_rpi = False
                    
                if is_rpi:
                    print("If you want the display to start automatically on boot, run:")
                    print("    \033[1;36msudo systemctl enable --now matrix\033[0m")
                    print("\nYou can now use \033[1;36mmatrix start\033[0m, \033[1;36mmatrix stop\033[0m, and \033[1;36mmatrix restart\033[0m to control the display in the background. No more need to execute \033[1;36mmake run\033[0m each time!")
                
                print("="*70 + "\n")
        except Exception as e:
            logger.error(f"Spotify setup failed: {e}")

    def get_current_playback(self) -> Optional[PlaybackInfo]:
        """
        Polls the Spotify API for the current playback state.
        Returns a PlaybackInfo object if music is playing on a whitelisted device, otherwise None.
        Handles rate limits and token refreshes automatically.
        """
        if not self.spotify or time.time() < self.rate_limit_until:
            return None

        try:
            track = self.spotify.current_playback()
            if not track or not track.get('item'):
                return PlaybackInfo(artist=None, title=None, art_url=None, is_playing=False, progress_ms=0, duration_ms=0, track_id=None)

            if self.device_whitelist:
                device = track.get('device')
                if not device or device.get('name') not in self.device_whitelist:
                    return PlaybackInfo(artist=None, title=None, art_url=None, is_playing=False, progress_ms=0, duration_ms=0, track_id=None)

            info = self._process_track(track)
            return info

        except SpotifyException as e:
            if getattr(e, 'http_status', 0) == 401 and self.spotify:
                try:
                    token_info = self.spotify.auth_manager.cache_handler.get_cached_token()
                    if token_info and 'refresh_token' in token_info:
                        logger.info("Spotify 401 - Forcing token refresh")
                        self.spotify.auth_manager.refresh_access_token(token_info['refresh_token'])
                except Exception as refresh_err:
                    logger.error(f"Failed to force token refresh: {refresh_err}")
            self._handle_rate_limit(e)
            return None
        except Exception as e:
            logger.error(f"Spotify polling error: {e}")
            return None

    def _process_track(self, track: Dict[str, Any]) -> PlaybackInfo:
        """Parses the raw Spotify API track response into a PlaybackInfo data class."""
        item = track.get('item')
        if not item:
             return PlaybackInfo(None, None, None, track.get('is_playing', False), track.get('progress_ms', 0), 0)

        artists = item['artists']
        artist_text = ", ".join(a['name'] for a in artists if 'name' in a) if artists else None
        artist_text = clean_text(artist_text)
            
        images = item['album']['images']
        art_url = images[0]['url'] if images else None
        
        track_id = item['id']
        if track_id != self.last_track_id:
            self.last_track_id = track_id
            self.track_start_time = time.time()
            self.lyrics_fetcher.last_track_id = None
            
        allow_fetch = track.get('is_playing', False) and (time.time() - self.track_start_time) >= LYRIC_FETCH_DELAY_SEC
        
        return PlaybackInfo(
            artist=artist_text,
            title=clean_text(item['name']) if item['name'] else None,
            art_url=art_url,
            is_playing=track['is_playing'],
            progress_ms=track.get('progress_ms', 0),
            duration_ms=item.get('duration_ms', 0),
            lyrics=self.lyrics_fetcher.get_lyrics(track_id, track_name=item['name'], allow_fetch=allow_fetch) if track_id else None,
            track_id=track_id
        )



    def _parse_whitelist(self, config):
        wl_str = config.get('Spotify', 'device_whitelist', fallback='')
        if not wl_str: return []
        return [x.strip().strip("'\"") for x in wl_str.strip("[]").split(',') if x.strip()]

    def _handle_rate_limit(self, e: SpotifyException):
        if e.http_status == 429:
            retry = int(e.headers.get("Retry-After", 30))
            self.rate_limit_until = time.time() + retry
            logger.warning(f"Rate limited. Pausing for {retry}s")

    def start_polling(self, callback, fetch_interval: float):
        """
        Starts a background daemon thread that continually fetches the current 
        playback state and passes the result to the provided callback function.
        """
        def _fetch_loop():
            while True:
                start_time = time.time()
                try:
                    info = self.get_current_playback()
                    if info is not None:
                        callback(info)
                except Exception as e:
                    logger.error(f"Error fetching Spotify data: {e}")
                finally:
                    elapsed = time.time() - start_time
                    time.sleep(max(0.0, fetch_interval - elapsed))
        
        threading.Thread(target=_fetch_loop, daemon=True).start()
