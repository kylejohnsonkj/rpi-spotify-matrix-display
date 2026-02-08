# Purpose: Generates the CRT screen off transition effect.
from PIL import Image, ImageDraw

W, H = 64, 64

def generate_crt_view(frame: Image.Image, progress: float) -> Image.Image:
    """ Generates the CRT screen-off effect, scaling down the frame based on progress. """
    img = Image.new("RGB", (W, H))
    if progress >= 1.0: return img
    draw = ImageDraw.Draw(img)
    
    if progress < 0.5:
        t = progress * 2
        h = max(2, int(H * (1 - t)))
        img.paste(frame.resize((W, h), getattr(Image, 'Resampling', Image).BILINEAR), (0, (H - h) // 2))
        draw.line([(0, H // 2), (W, H // 2)], fill=(int(255 * t),) * 3)
    else:
        w = max(1, int(W * (1 - (progress - 0.5) * 2)))
        draw.line([((W - w) // 2, H // 2), ((W + w) // 2, H // 2)], fill=(255, 255, 255))
    return img
