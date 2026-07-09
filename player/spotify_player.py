# Purpose: Orchestrates the matrix display, transitions, and different playback views.
import threading
import time
import configparser
import logging
from pathlib import Path
from PIL import Image, ImageFont, ImageDraw

logger = logging.getLogger(__name__)

from services.spotify_api import SpotifyModule
from player.components import ArtCache
from player.transitions import PlayerTransition
from utils.color_utils import SPOTIFY_BRAND_GREEN
from views.standard_view import generate_standard_view
from views.lyrics_view import generate_lyrics_view
from views.fullscreen_view import generate_fullscreen_view
from views.crt_view import generate_crt_view
from utils.lyric_utils import has_current_lyrics, get_active_lines, get_active_lyric
from views.player_view import PlayerView
from player.playback_controller import PlaybackController

W, H = 64, 64

class SpotifyPlayer:
    """
    Orchestrates the matrix display, manages state transitions, and renders 
    the active view (Standard, Fullscreen, CRT, or Lyrics).
    """
    def __init__(self, config: configparser.ConfigParser, spotify_module: SpotifyModule):
        self.spotify_module = spotify_module
        self.config = config
        
        self.target_fps = config.getint('Player', 'target_fps', fallback=60)
        self.fetch_interval = config.getint('Spotify', 'fetch_interval', fallback=1)
        self.fullscreen_delay = config.getfloat('Player', 'fullscreen_delay', fallback=10.0)
        self.shutdown_delay = config.getfloat('Player', 'shutdown_delay', fallback=30.0)

        for p in [Path("font.otf"), Path(__file__).parent / "font.otf"]:
            if p.exists():
                self.font = ImageFont.truetype(str(p), 5)
                break
        else:
            self.font = ImageFont.load_default()

        self.black_screen = Image.new("RGB", (W, H), (0, 0, 0))
        self.art_cache = ArtCache()
        self.player_transition = PlayerTransition(self.target_fps)
        self.playback = PlaybackController(spotify_module, self.art_cache)
        
        self.view = PlayerView(
            self.art_cache, self.font,
            config.getfloat('Player', 'text_scroll_speed', fallback=15.0),
            config.getfloat('Player', 'text_scroll_delay', fallback=4.0)
        )
        
        self.last_generated_frame = self.black_screen
        self.pre_crt_frame = self.black_screen
        self.last_playing_time = time.time()
        self.lyrics_t = 0.0
        self.fullscreen_start_time = 0.0
        self.crt_start_time = 0.0
        self.is_crt = False
        self.last_paused_time = time.time()
        self.transition_end_time = 0.0
        
        self.last_track_id = None
        self.last_response = None
        self.lyrics_arrived_time = 0.0
        self.had_lyrics = False
        self.last_playing_state = None
        self.current_view_name = None
        self.current_power_state = None

        self.spotify_module.start_polling(self.playback.set_current_playback, self.fetch_interval)

    def _handle_track_change(self, current_track_id: str, now: float):
        """Detects if the track has changed and triggers transition animations."""
        if current_track_id and current_track_id != self.last_track_id:
            always_fullscreen = self.config.getboolean('Player', 'always_fullscreen', fallback=False)
            if self.last_response and self.last_track_id:
                draw = ImageDraw.Draw(self.last_generated_frame)
                color = self.art_cache.get_color(self.last_response.art_url) if getattr(self.last_response, 'art_url', None) else SPOTIFY_BRAND_GREEN
                if self.lyrics_t < 0.5 and not always_fullscreen:
                    self.view.play_indicator.draw(draw, "Paused", color=color)
            
            self.player_transition.start(current_track_id, self.last_track_id, self.last_generated_frame, slide_progress_bar=always_fullscreen)
            self.player_transition.update_history(current_track_id)
            self.view.title.end_scroll(now)
            self.view.artist.end_scroll(now)
            self.lyrics_t = 0.0
            self.last_track_id = current_track_id
            self.last_paused_time = now

    def _update_lyric_state(self, response, progress_ms: int, dt: float, dedicated_lyrics: bool, now: float, time_playing: float) -> bool:
        """Updates the timing state for the dedicated lyrics transition. Returns true if dedicated lyrics are active."""
        is_dedicated_lyrics = (
            response.is_playing 
            and dedicated_lyrics 
            and has_current_lyrics(response, progress_ms, lookahead_ms=1000)
            and time_playing > self.view.title.text_scroll_delay
        )
        
        if is_dedicated_lyrics:
            self.lyrics_t = min(1.0, self.lyrics_t + dt)
        else:
            self.lyrics_t = max(0.0, self.lyrics_t - dt)
            
        return is_dedicated_lyrics

    def _render_active_view(self, response, progress_ms: int, duration_ms: int, time_paused: float, time_playing: float, time_since_lyrics_fetched: float, now: float, dt: float):
        """Determines and renders the appropriate view based on playback state and timeouts."""
        dedicated_lyrics = self.config.getboolean('Player', 'dedicated_lyrics', fallback=False)
        always_fullscreen = self.config.getboolean('Player', 'always_fullscreen', fallback=False)
        show_lyrics = not dedicated_lyrics
        
        if always_fullscreen or time_paused > self.fullscreen_delay:
            view_name = "fullscreen"
            if self.fullscreen_start_time == 0: self.fullscreen_start_time = now
            self.lyrics_t = 0.0
            
            if always_fullscreen:
                t = 1.0
            else:
                t = min(1.0, (now - self.fullscreen_start_time) / 0.5)
                
            std = generate_standard_view(response, progress_ms, duration_ms, True, self.view, show_lyrics, time_paused, time_playing, time_since_lyrics_fetched)
            frame = generate_fullscreen_view(response, self.view, t, std)
        else:
            self.fullscreen_start_time = 0
            is_dedicated_lyrics = self._update_lyric_state(response, progress_ms, dt, dedicated_lyrics, now, time_playing)
            view_name = "lyrics" if is_dedicated_lyrics else "standard"
                
            if self.lyrics_t > 0.0:
                frames = self.lyrics_t * 60
                frame = generate_lyrics_view(response, progress_ms, duration_ms, True, self.view, frames, 60, is_dedicated_lyrics, self.lyrics_t, time_paused, time_playing)
            else:
                frame = generate_standard_view(response, progress_ms, duration_ms, True, self.view, show_lyrics, time_paused, time_playing, time_since_lyrics_fetched)
                
        if time_paused > self.shutdown_delay:
            view_name = "crt"

        if view_name != self.current_view_name:
            if view_name == "lyrics":
                logger.info("Entering dedicated lyrics view 🎙️")
            elif view_name == "standard":
                logger.info("Entering standard view 🖼️")
            elif view_name == "fullscreen":
                logger.info("Entering fullscreen view 🔳")
            self.current_view_name = view_name
            
        new_power_state = "active"
        if time_paused > self.shutdown_delay:
            new_power_state = "inactive"
        elif time_paused > self.fullscreen_delay:
            new_power_state = "idle"
            
        if self.current_power_state != new_power_state:
            if new_power_state == "inactive":
                logger.info("Entering inactive state 🔴")
            elif new_power_state == "active" and self.current_power_state == "inactive":
                if response:
                    logger.info(f"Now playing: {response.title} by {response.artist}")
            self.current_power_state = new_power_state
            
        if self.player_transition.active:
            frame = self.player_transition.generate_frame(frame, dt)
            
        if time_paused > self.shutdown_delay:
            if not self.is_crt:
                self.crt_start_time = now
                self.is_crt = True
                self.pre_crt_frame = frame.copy()
            t = min(1.0, (now - self.crt_start_time) / 0.6)
            frame = generate_crt_view(self.pre_crt_frame, t)
            
        return frame

    def generate(self, dt: float):
        """Core rendering loop that orchestrates state updates and view generation."""
        now = time.time()
        response, progress_ms, duration_ms = self.playback.update(now, dt)
        
        current_track_id = response.track_id if response else None
        
        if response and response.track_id != self.last_track_id:
            if self.last_response and self.last_response.track_id:
                if self.playback.last_prog_ms < self.last_response.duration_ms - 10000:
                    logger.info("Song skipped ⏭️")
            logger.info(f"Now playing: {response.title} by {response.artist}")
            
        self._handle_track_change(current_track_id, now)

        if response:
            if self.last_playing_state is not None and self.last_playing_state != response.is_playing:
                if response.is_playing:
                    logger.info("Playback started ▶️")
                else:
                    logger.info("Playback paused ⏸️")
            self.last_playing_state = response.is_playing

        if response and response.is_playing:
            self.last_playing_time = now
        elif response:
            self.last_paused_time = now
            
        time_paused = now - self.last_playing_time
        
        if response and self.is_crt and time_paused <= self.shutdown_delay:
            self.player_transition.start(response.track_id, None, self.black_screen)
            self.is_crt = False
            self.crt_start_time = 0.0
        
        if response:
            self.last_response = response
            lyrics_data = getattr(response, 'lyrics', None)
            
            if lyrics_data:
                active_lines = get_active_lines(lyrics_data)
                if active_lines:
                    get_active_lyric(active_lines, progress_ms)
                    
            if lyrics_data and not self.had_lyrics:
                self.lyrics_arrived_time = now
                self.had_lyrics = True
            elif not lyrics_data:
                self.had_lyrics = False
        else:
            response = self.last_response

        if not response:
            return self.black_screen

        if self.player_transition.active:
            self.transition_end_time = now
            self.view.title.end_scroll(now)
            self.view.artist.end_scroll(now)

        self.view.update(response, now)
        
        time_playing = now - self.last_paused_time if response.is_playing else 0.0
        time_since_lyrics_fetched = now - self.lyrics_arrived_time if self.had_lyrics else None
        frame = self._render_active_view(response, progress_ms, duration_ms, time_paused, time_playing, time_since_lyrics_fetched, now, dt)
        
        self.last_generated_frame = frame
        return frame
