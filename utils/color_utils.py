import colorsys
import math
from PIL import Image

SPOTIFY_BRAND_GREEN = (102, 240, 110)

def get_accent_color(img: Image.Image) -> tuple[int, int, int]:
    """
    Extracts a standout accent color from the album artwork.
    Uses continuous mathematical scoring (smarts) rather than discrete conditional boundaries.
    Prioritizes vibrant/warm colors, smartly avoids background, and aggressively penalizes muddy skin tones.
    """
    img = img.convert("RGB")
    # Downscale for performance and to smooth out noisy pixels
    img.thumbnail((192, 192), Image.Resampling.LANCZOS)
    
    colors_info = img.getcolors(img.width * img.height)
    if not colors_info:
        return SPOTIFY_BRAND_GREEN
        
    total_pixels = img.width * img.height
    
    # 1. Smart Grouping
    # Group similar pixels. Instead of averaging (which creates muddy colors),
    # we keep the single most vibrant pixel from each group as its representative.
    groups = {}
    for count, (r, g, b) in colors_info:
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        
        # Group by 64s in RGB space (~64 possible buckets)
        bucket_key = (r // 64, g // 64, b // 64)
        
        # Base vibrancy metric (heavily favors saturated & bright)
        # We multiply s by v so pitch-black pixels don't get artificially high saturation scores
        vibrancy = (s * v * 2.0) + v
        
        if bucket_key not in groups:
            groups[bucket_key] = {
                'count': count,
                'color': (r, g, b),
                'hsv': (h, s, v),
                'vibrancy': vibrancy
            }
        else:
            groups[bucket_key]['count'] += count
            if vibrancy > groups[bucket_key]['vibrancy']:
                groups[bucket_key]['color'] = (r, g, b)
                groups[bucket_key]['hsv'] = (h, s, v)
                groups[bucket_key]['vibrancy'] = vibrancy

    # 2. Identify the background
    # The background is usually the largest group
    dominant_group = max(groups.values(), key=lambda g: g['count'])
    bg_h, bg_s, bg_v = dominant_group['hsv']
    bg_vibrancy = dominant_group['vibrancy']
    bg_percentage = dominant_group['count'] / total_pixels
    
    scored_colors = []
    
    for data in groups.values():
        r, g, b = data['color']
        h, s, v = data['hsv']
        percentage = data['count'] / total_pixels
        
        # --- BASE SCORE ---
        vibrancy = (s * v * 2.0) + v
        score = vibrancy ** 3.0
        score *= math.log1p(percentage * 100)
        
        # --- PENALTIES & BONUSES ---
        
        # 1. Low Luma Penalty
        luma = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        if luma < 0.25:
            score *= 0.01

        # 2. Too Dark Penalty
        if v < 0.55:
            score *= 0.1
        elif v < 0.72:
            score *= 0.6
            
        # 3. Muddy/Brown Penalty
        is_muddy = False
        if 0.04 <= h <= 0.20:
            if s < 0.7 or v < 0.8:
                score *= 0.05
                is_muddy = True
                
        # 4. Warm Color Bonus
        if (h <= 0.18 or h >= 0.80) and not is_muddy:
            score *= 2.5
            
        # 5. Cold Color Penalty
        if 0.55 <= h <= 0.75:
            score *= 0.7
            
        # 6. Washout Penalty
        if s < 0.6:
            score *= (s / 0.6) ** 2.0
            
        # 7. Background Separation
        if bg_percentage > 0.15:
            hue_diff = min(abs(h - bg_h), 1.0 - abs(h - bg_h))
            if hue_diff < 0.15:
                if vibrancy <= bg_vibrancy + 1.0:
                    score *= 0.1
            elif hue_diff > 0.3:
                score *= 1.5
                
        scored_colors.append({
            'color': (r, g, b),
            'hsv': (h, s, v),
            'score': score,
            'percentage': percentage
        })

    # Sort to find the best
    scored_colors.sort(key=lambda x: x['score'], reverse=True)
    
    import logging
    log = logging.getLogger(__name__)
    
    color_strings = []
    for c in scored_colors[:5]:
        color_block = f"\033[38;2;{c['color'][0]};{c['color'][1]};{c['color'][2]}m██\033[0m"
        hex_str = f"\033[38;2;{c['color'][0]};{c['color'][1]};{c['color'][2]}m#{c['color'][0]:02X}{c['color'][1]:02X}{c['color'][2]:02X}\033[0m"
        color_strings.append(f"{color_block} {hex_str}")
        
    log.info(f"Accents: {'  '.join(color_strings)}")

    # 4. Final safety net
    # If an accent color is gray, fallback to the next color. 
    # Only use the fallback green if all are grayscale.
    for c in scored_colors:
        h, s, v = c['hsv']

        # Smart colorfulness check: S + V ensures that dark colors must be highly saturated,
        # and less saturated colors must be very bright.
        # We also enforce a hard floor of v >= 0.55 so it never picks a color that is just too dark to see.
        if s >= 0.20 and v >= 0.55 and (s + v) >= 0.83:
            if c != scored_colors[0]:
                log.debug(f"Higher ranked colors were gray. Falling back to #{c['color'][0]:02X}{c['color'][1]:02X}{c['color'][2]:02X}")
            return c['color']
            
    log.debug("No vibrant accents found (all were gray, too dark, or muddy brown). Using fallback green.")
    return SPOTIFY_BRAND_GREEN
