# Purpose: Provides visual transition effects (scaling, sliding) for UI elements.
import time
from PIL import Image

W, H = 64, 64
BASELINE_FPS = 60
SLIDE_FRAMES = 80
SLIDE_DURATION_SEC = SLIDE_FRAMES / BASELINE_FPS

class ScaleTransition:
    @staticmethod
    def apply(element, start_x: int, start_y: int, start_w: int, start_h: int, end_x: int, end_y: int, end_w: int, end_h: int, progress: float):
        element.x = int(start_x + (end_x - start_x) * progress)
        element.y = int(start_y + (end_y - start_y) * progress)
        element.width = int(start_w + (end_w - start_w) * progress)
        element.height = int(start_h + (end_h - start_h) * progress)

class SlideTransition:
    @staticmethod
    def apply(element, start_x: int, start_y: int, end_x: int, end_y: int, progress: float):
        element.x = int(start_x + (end_x - start_x) * progress)
        element.y = int(start_y + (end_y - start_y) * progress)

class PlayerTransition:
    def __init__(self):
        self.active = False
        self.elapsed_sec = 0.0
        self.direction = 1
        self.snapshot = None
        self.history = []

    def start(self, new_track_id, current_track_id, snapshot, slide_progress_bar=False):
        self.active = True
        self.elapsed_sec = 0.0
        self.direction = 1
        self.snapshot = snapshot.copy() if snapshot else None
        self.slide_progress_bar = slide_progress_bar or (current_track_id is None)
        
        if new_track_id in self.history and current_track_id in self.history:
            if self.history.index(new_track_id) < self.history.index(current_track_id):
                self.direction = -1

    def update_history(self, track_id):
        if track_id not in self.history:
            self.history.append(track_id)
            if len(self.history) > 5:
                self.history.pop(0)

    def generate_frame(self, target_frame, dt: float):
        self.elapsed_sec += dt
        progress = min(1.0, self.elapsed_sec / SLIDE_DURATION_SEC)
        eased_progress = 1 - (1 - progress) ** 2
        o_l = round(W * eased_progress)
        
        d, t_base = (-1, W) if self.direction == 1 else (1, -W)
        comp = Image.new("RGB", (W, H), 0)
        
        if self.snapshot:
            comp.paste(self.snapshot, (d * o_l, 0))
        
        comp.paste(target_frame, (t_base + d * o_l, 0))

        if not getattr(self, 'slide_progress_bar', False):
            pb_new = target_frame.crop((0, 62, W, H))
            comp.paste(pb_new, (0, 62))

        if self.elapsed_sec >= SLIDE_DURATION_SEC:
            self.active = False
            
        return comp
