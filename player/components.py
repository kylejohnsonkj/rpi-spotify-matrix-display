# Purpose: Defines visual UI components (album art, text scrolling, progress bar) for the display.
import math
import time
import threading
import requests
from io import BytesIO
import logging
from PIL import Image

logger = logging.getLogger(__name__)

from utils.color_utils import get_accent_color, SPOTIFY_BRAND_GREEN
PROGRESS_BG_COLOR = (100, 100, 100)

class ArtCache:
    """Manages fetching, resizing, and caching of album artwork and dominant colors."""
    def __init__(self):
        self._cache = {}
        self._fetching_url = None

    def get(self, url, size=None):
        data = self._cache.get(url)
        if not data or 'orig' not in data: return None
        if size is None: return data['orig']
        if size not in data:
            data[size] = data['orig'].resize((size, size), Image.LANCZOS)
        return data[size]

    def get_color(self, url):
        """Returns the dominant color of the cached artwork, or a fallback color."""
        data = self._cache.get(url)
        if not data or 'color' not in data: return SPOTIFY_BRAND_GREEN
        return data['color']

    def fetch(self, url, safe_urls):
        if not url or url in self._cache or self._fetching_url == url: return
        self._fetching_url = url
        def _fetch():
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                img = Image.open(BytesIO(r.content)).convert("RGB")
                width, height = img.size
                if width != height:
                    sz = min(width, height)
                    l, t = (width - sz) // 2, (height - sz) // 2
                    img = img.crop((l, t, l + sz, t + sz))
                
                # Pre-scale to max matrix size in the background thread!
                # This prevents the main thread from doing a heavy 640x640 resize.
                img.thumbnail((64, 64), getattr(Image, 'Resampling', Image).LANCZOS)
                
                # Pre-generate the 48x48 size used by the standard view so the main thread does ZERO resizing!
                img_48 = img.resize((48, 48), getattr(Image, 'Resampling', Image).LANCZOS)
                
                color = get_accent_color(img)
                self._cache[url] = {'orig': img, 'color': color, 48: img_48, 64: img}
                
                for k in list(self._cache.keys()):
                    if k not in safe_urls and k != url and len(self._cache) > 4:
                        del self._cache[k]
            except Exception as e:
                logger.error(f"Error fetching image {url}: {e}")
            finally:
                self._fetching_url = None
        threading.Thread(target=_fetch, daemon=True).start()

    @property
    def is_fetching(self):
        return self._fetching_url is not None


class AlbumArt:
    """Visual component for rendering album artwork at a specified position and size."""
    def __init__(self, x: int, y: int, width: int, height: int, cache):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.cache = cache

    def draw(self, img, url: str):
        if not url: return
        art = self.cache.get(url, self.width)
        if art:
            img.paste(art, (self.x, self.y))


class PlayIndicator:
    """Visual component for rendering animated play/pause icons based on playback state."""
    def __init__(self, x: int, y: int, width: int, height: int):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def draw(self, draw, state: str, color=SPOTIFY_BRAND_GREEN):
        draw.rectangle((self.x - 2, self.y - 2, 63, self.y + self.height + 2), fill=(0, 0, 0))
        if state == "Paused":
            draw.rectangle((self.x, self.y, self.x + 1, self.y + 6), fill=color)
            draw.rectangle((self.x + 3, self.y, self.x + 4, self.y + 6), fill=color)
        elif state == "Play":
            draw.polygon([(self.x, self.y), (self.x, self.y + 6), (self.x + 4, self.y + 3)], fill=color)
        elif state == "Active":
            t = time.time()
            for i in range(3):
                # Animate the bars to pulsate in a random but synced way
                h = 1.0 + 2.5 * (0.5 + 0.5 * math.sin(t * (10 + i * 2.5) + i * 2))
                t_y = max(self.y, int(self.y + 3 - h))
                b_y = min(self.y + 6, int(self.y + 3 + h))
                draw.rectangle((self.x + i * 2, t_y, self.x + i * 2, b_y), fill=color)

class ProgressBar:
    """Visual component for rendering a playback progress bar."""
    def __init__(self, x: int, y: int, width: int, height: int):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def draw(self, draw, progress_ms: int, duration_ms: int, bg_color=PROGRESS_BG_COLOR, fill_color=SPOTIFY_BRAND_GREEN):
        draw.rectangle((self.x, self.y, self.x + self.width - 1, self.y + self.height - 1), fill=bg_color)
        if duration_ms > 0:
            w = max(1, round(self.width * progress_ms / duration_ms))
            draw.rectangle((self.x, self.y, self.x + min(w, self.width) - 1, self.y + self.height - 1), fill=fill_color)

class ScrollingText:
    """
    Visual component for scrolling long text horizontally.
    Supports syncing scroll state across multiple instances.
    """
    def __init__(self, x: int, y: int, width: int, height: int, text_scroll_speed: float, text_scroll_delay: float, font):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text_scroll_speed = text_scroll_speed
        self.text_scroll_delay = text_scroll_delay
        self.font = font
        self.text = ""
        self.base_text_width = 0
        self.full_text_width = 0
        self.pos = 0.0
        self.is_scrolling = False
        self.last_scroll_end = time.time()
        self.last_cycle_start = time.time()
        self.sync_group = []
        self.was_needs_scroll = False

        self._scroll_x = x
        self._scroll_text_width = 0

    def _needs_scroll_for_width(self, w):
        return self.base_text_width > w

    @property
    def text_width(self):
        return self.full_text_width if self.base_text_width > self.width else 0

    def update_text(self, text: str):
        if self.text != text:
            self.text = text
            if text:
                self.base_text_width = self.font.getlength(text)
                self.full_text_width = self.font.getlength(text + "     ")
            else:
                self.base_text_width = 0
                self.full_text_width = 0
            self.is_scrolling = False
            self.pos = 0.0
            self._scroll_text_width = 0
            self.last_scroll_end = time.time()

    def update(self, now: float):
        """Updates internal scroll positions based on elapsed time and sync states."""
        needs_scroll = self.text_width > 0
        if needs_scroll and not self.was_needs_scroll:
            self.last_scroll_end = now
        self.was_needs_scroll = needs_scroll

        if not self.is_scrolling:
            if needs_scroll and (now - self.last_scroll_end >= self.text_scroll_delay):
                can_start = True
                for other in self.sync_group:
                    if other.text_width > 0 and (other.is_scrolling or now - other.last_scroll_end < self.text_scroll_delay):
                        can_start = False
                if can_start:
                    self.start_scroll(now)
                    for other in self.sync_group:
                        other.start_scroll(now)
        
        if self.is_scrolling:
            elapsed = now - self.last_cycle_start
            self.pos = elapsed * self.text_scroll_speed
            display_offset = self.pos
            done = self._scroll_text_width == 0 or display_offset >= self._scroll_text_width
            if done:
                self.end_scroll(now)
        else:
            self.pos = 0.0

    def start_scroll(self, now):
        self.is_scrolling = True
        self.last_cycle_start = now
        self._scroll_x = self.x
        self._scroll_text_width = self.full_text_width if self._needs_scroll_for_width(self.width) else 0

    def end_scroll(self, now):
        self.is_scrolling = False
        self.pos = 0.0
        self._scroll_text_width = 0
        self.last_scroll_end = now

    def add_sync(self, other):
        if other not in self.sync_group:
            self.sync_group.append(other)
            other.sync_group.append(self)

    def draw(self, draw, color=(255, 255, 255)):
        if not self.text: return

        if self.is_scrolling and self._scroll_text_width > 0:
            display_offset = int(self.pos)
            draw.text((self.x - display_offset, self.y), self.text + "     " + self.text, fill=color, font=self.font)
        elif self.text_width > 0:
            draw.text((self.x, self.y), self.text + "     " + self.text, fill=color, font=self.font)
        else:
            draw.text((self.x, self.y), self.text, fill=color, font=self.font)
