# Purpose: Generates the fullscreen album art view when paused.
from PIL import Image

W, H = 64, 64
ART_X, ART_Y, ART_W, ART_H = 8, 14, 48, 48

def generate_fullscreen_view(response, components, fullscreen_t: float = 1.0, standard_frame: Image.Image = None):
    """ Animates the transition between the standard view and the fullscreen album art view. """
    t = fullscreen_t * fullscreen_t * (3.0 - 2.0 * fullscreen_t)  # smoothstep

    x = int(ART_X * (1 - t))
    y = int(ART_Y * (1 - t))
    w = int(ART_W + (W - ART_W) * t)
    h = int(ART_H + (H - ART_H) * t)

    img = standard_frame.copy() if standard_frame is not None else Image.new("RGB", (W, H), 0)

    if getattr(response, 'art_url', None) and w > 0 and h > 0:
        art = components.album_art.cache.get(response.art_url, W)
        if art:
            if w == art.width and h == art.height:
                img.paste(art, (x, y))
            else:
                img.paste(art.resize((w, h), getattr(Image, 'Resampling', Image).BILINEAR), (x, y))

    return img
