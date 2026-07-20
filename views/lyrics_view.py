# Purpose: Generates the dedicated lyrics display view with synced lyrics.
from PIL import Image, ImageDraw
from player.transitions import SlideTransition, ScaleTransition
from utils.lyric_utils import get_active_lines, get_active_lyric, wrap_text
from utils.color_utils import SPOTIFY_BRAND_GREEN

W, H = 64, 64
ART_X, ART_Y, ART_W, ART_H = 8, 14, 48, 48
LYRICS_FADE_MS = 300

def generate_lyrics_view(response, progress_ms, duration_ms, show_play, components, transition_elapsed_sec, transition_duration_sec, has_lyrics_now, time_paused=0.0, time_playing=0.0):
    """ Generates the dedicated lyrics view with a scrolling text and synced lyric lines. """
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    t_total = min(1.0, transition_elapsed_sec / transition_duration_sec) if transition_duration_sec > 0 else 1.0
    art_t = min(1.0, t_total / (16 / 28))

    _transition_scrolling_text(components, art_t)
    ScaleTransition.apply(components.album_art, ART_X, ART_Y, ART_W, ART_H, 1, 1, 15, 15, art_t)
    _transition_play_indicator(components, t_total)
    color = components.album_art.cache.get_color(response.art_url) if getattr(response, 'art_url', None) else SPOTIFY_BRAND_GREEN

    components.title.draw(draw)
    components.artist.draw(draw)
    
    _draw_progress_bar(draw, components, progress_ms, duration_ms, art_t, t_total, color)
    _draw_backgrounds(draw, components, art_t, t_total)
    
    components.album_art.draw(img, response.art_url)

    if transition_elapsed_sec > 0:
        _draw_lyrics_text(img, response.lyrics, progress_ms, 18, components.title.font, transition_elapsed_sec, transition_duration_sec, time_paused, time_playing)

    if not response.is_playing:
        state = "Paused"
    elif time_playing > 0 and time_playing <= components.title.text_scroll_delay:
        state = "Play"
    else:
        state = "Active"
        
    components.play_indicator.draw(draw, state, color=color)

    return img

def _transition_scrolling_text(components, art_t):
    """ Animates the title and artist text moving to the top edge. """
    SlideTransition.apply(components.title, 1, 1, 17, 1, art_t)
    SlideTransition.apply(components.artist, 1, 7, 17, 7, art_t)
    current_right = int(53 + (63 - 53) * art_t)
    components.title.width = current_right - components.title.x
    components.artist.width = current_right - components.artist.x

def _transition_play_indicator(components, t_total):
    """ Animates the play/pause indicator sliding out and back in. """
    if t_total < 0.5:
        SlideTransition.apply(components.play_indicator, 56, 3, W, 3, t_total * 2)
    else:
        SlideTransition.apply(components.play_indicator, W, 54, 56, 54, (t_total - 0.5) * 2)
    components.play_indicator.width, components.play_indicator.height = 4, 6

def _draw_backgrounds(draw, components, art_t, t_total):
    """ Draws the solid background rectangles to cover up moving components. """
    text_x = components.title.x
    btn_x = components.play_indicator.x
    btn_y = components.play_indicator.y
    if btn_x < W: draw.rectangle((btn_x - 3, btn_y - 3, W - 1, btn_y + 9), fill=(0, 0, 0))
    if art_t > 0.5: draw.rectangle((0, 0, text_x - 1, 16), fill=(0, 0, 0))
    draw.rectangle((W - 1, 0, W - 1, 16), fill=(0, 0, 0))

def _draw_progress_bar(draw, components, progress_ms, duration_ms, art_t, t_total, color):
    """ Draws and animates the progress bar matching the layout. """
    text_x = components.title.x
    btn_x = int(56 + (W + 3 - 56) * (1.0 - t_total))
    text_width = btn_x - 3 - text_x - 1
    
    if art_t < 0.5:
        bar_y = 62 + int(art_t * 4)
        if bar_y < 64:
            SlideTransition.apply(components.progress_bar, 0, 62, 0, 66, art_t * 2)
            components.progress_bar.draw(draw, progress_ms, duration_ms, fill_color=color)

    bar_width = W - text_x - 1 if t_total > 0 else text_width
    bar_start_t = 16 / 28

    if t_total > bar_start_t:
        grow_t = min(1.0, (t_total - bar_start_t) / (1.0 - bar_start_t))
        current_bar_width = int(bar_width * grow_t)
        if current_bar_width > 0:
            draw.rectangle((text_x, 14, text_x + current_bar_width - 1, 15), fill=(100, 100, 100))
        green_w = max(1, round(current_bar_width * progress_ms / duration_ms)) if duration_ms > 0 else 0
        if green_w > 0:
            draw.rectangle((text_x, 14, text_x + green_w - 1, 15), fill=color)
    elif t_total == 1.0:
        components.progress_bar.x, components.progress_bar.y = text_x, 14
        components.progress_bar.width, components.progress_bar.height = bar_width, 2
        components.progress_bar.draw(draw, progress_ms, duration_ms, fill_color=color)

def _draw_lyrics_text(img, lyrics, progress_ms, y_offset, font, transition_elapsed_sec, transition_duration_sec, time_paused=0.0, time_playing=0.0):
    """ Draws the synchronized lyrics text lines. """
    active_lines = get_active_lines(lyrics)
    if not active_lines:
        return
    lyrics_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(lyrics_img)
    lyrics_text_start_sec = transition_duration_sec * 16 / 28

    ms_since_appear = max(0.0, (transition_elapsed_sec - lyrics_text_start_sec) * 1000.0)
    
    target_ms = progress_ms
    text, current_line_start_ms, current_line_end_ms, next_line_start_ms = get_active_lyric(active_lines, target_ms, keepalive=True)
    
    if not text: return
    
    out = wrap_text(text, font, W - 4)

    time_at_target_ms = target_ms - current_line_start_ms
    line_elapsed_ms = min(time_at_target_ms, ms_since_appear)
    line_fade_in_t = max(0.0, min(1.0, line_elapsed_ms / LYRICS_FADE_MS))
    
    line_fade_out_t = 1.0
    y_offset_anim = 0.0
    if line_fade_in_t < 1.0: y_offset_anim += ((1.0 - line_fade_in_t) ** 2) * 8.0
        
    time_until_next = float('inf')
    if next_line_start_ms:
        time_until_next = next_line_start_ms - target_ms
    if current_line_end_ms > 0:
        time_until_next = min(time_until_next, current_line_end_ms - target_ms)
        
    if time_until_next != float('inf'):
        out_elapsed = LYRICS_FADE_MS - time_until_next
        if out_elapsed > 0:
            out_progress = min(1.0, out_elapsed / LYRICS_FADE_MS)
            line_fade_out_t = 1.0 - out_progress
            y_offset_anim += -(out_progress * 8.0)

    line_alpha = line_fade_in_t * line_fade_out_t
    
    fade_multiplier = 1.0
    if time_paused > 0:
        fade_multiplier = max(0.0, 1.0 - time_paused / (LYRICS_FADE_MS / 1000.0))
    elif time_playing > 0:
        fade_multiplier = min(1.0, time_playing / (LYRICS_FADE_MS / 1000.0))
        
    line_alpha *= fade_multiplier
    fill_c = int(255 * line_alpha)
    fill = (fill_c, fill_c, fill_c)

    for i, line in enumerate(out):
        y = y_offset + i * 6 + y_offset_anim
        if y + 6 > H: break
        if y > -6 and fill_c > 0:
            draw.text((2, int(y)), line, fill=fill, font=font)

    clip_y = y_offset - 1
    img.paste(lyrics_img.crop((0, clip_y, W, H)), (0, clip_y), lyrics_img.crop((0, clip_y, W, H)))
