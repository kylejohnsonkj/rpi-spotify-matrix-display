# Purpose: Manages playback state, synchronization, and progress calculations.
from services.spotify_api import SpotifyModule
from player.components import ArtCache

import threading

class PlaybackController:
    def __init__(self, spotify_module: SpotifyModule, art_cache: ArtCache):
        self.spotify_module = spotify_module
        self.art_cache = art_cache
        self.response = None
        self.response_timestamp = 0.0
        self.pending_response = None
        self.last_prog_ms = 0
        self.last_track_prog = None
        self.latest_data = None
        self.data_lock = threading.Lock()

    def set_current_playback(self, info):
        with self.data_lock:
            self.latest_data = info

    def _sync_queue(self, now):
        with self.data_lock:
            new_data = self.latest_data
            self.latest_data = None
            
            if new_data:
                if new_data.track_id is None:
                    if self.response is not None:
                        self.response.is_playing = False
                    return

                if self.response is None or (self.response.track_id and new_data.track_id != self.response.track_id):
                    self.pending_response = new_data
                    self._request_art(new_data.art_url)
                else:
                    self.response = new_data
                    self.response_timestamp = now
                    self.pending_response = None

    def _apply_pending_response(self, now):
        if self.pending_response and not self.art_cache.is_fetching:
            self.response = self.pending_response
            self.response_timestamp = now
            self.pending_response = None

    def _calculate_progress(self, now, dt):
        progress_ms = self.response.progress_ms
        if self.response_timestamp > 0 and self.response.is_playing:
            progress_ms += int((now - self.response_timestamp) * 1000)

        duration_ms = self.response.duration_ms
        if duration_ms > 0: progress_ms = min(progress_ms, duration_ms)

        if self.last_track_prog == self.response.track_id:
            diff = self.last_prog_ms - progress_ms
            if 0 < diff < 3000:
                progress_ms = self.last_prog_ms + int(dt * 1000)
            
        self.last_prog_ms = progress_ms
        self.last_track_prog = self.response.track_id
        return progress_ms

    def update(self, now, dt):
        self._sync_queue(now)
        self._apply_pending_response(now)

        if not self.response:
            return None, 0, 0

        progress_ms = self._calculate_progress(now, dt)
        self._request_art(self.response.art_url)
        return self.response, progress_ms, self.response.duration_ms

    def _request_art(self, art_url):
        if not art_url: return
        safe = [art_url]
        if self.response and self.response.art_url: safe.append(self.response.art_url)
        if self.pending_response and self.pending_response.art_url: safe.append(self.pending_response.art_url)
        self.art_cache.fetch(art_url, safe)
