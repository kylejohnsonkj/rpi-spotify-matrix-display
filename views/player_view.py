# Purpose: Aggregates UI components into a cohesive player view state.
from player.components import ProgressBar, ScrollingText, AlbumArt, PlayIndicator

class PlayerView:
    def __init__(self, art_cache, font, scroll_speed, scroll_delay):
        """ Initializes the UI components required for the player view. """
        self.progress_bar = ProgressBar(0, 62, 64, 2)
        self.title = ScrollingText(1, 1, 52, 6, scroll_speed, scroll_delay, font)
        self.artist = ScrollingText(1, 7, 52, 6, scroll_speed, scroll_delay, font)
        self.title.add_sync(self.artist)
        self.album_art = AlbumArt(8, 14, 48, 48, art_cache)
        self.play_indicator = PlayIndicator(56, 3, 5, 7)
        self.font = font

    def update(self, response, now):
        """ Updates the state of UI components, like scrolling text and art. """
        self.title.update_text(response.title if response else "")
        self.artist.update_text(response.artist if response else "")
        self.title.update(now)
        self.artist.update(now)
