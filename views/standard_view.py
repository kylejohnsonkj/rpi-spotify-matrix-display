# Purpose: Generates the standard player view showing album art, title, and progress.
from PIL import Image, ImageDraw
from utils.lyric_utils import get_active_lines, wrap_text
from utils.color_utils import SPOTIFY_BRAND_GREEN

W, H = 64, 64
ART_X, ART_Y, ART_W, ART_H = 8, 14, 48, 48
LYRICS_WIDTH = 60
LYRICS_FADE_MS = 300
LYRICS_V_PADDING = 2
DIMMED_BG_ALPHA = 200

def generate_standard_view(response, progress_ms, duration_ms, show_play, components, show_lyrics=False, time_paused=0.0, time_playing=0.0, time_since_lyrics_fetched=None):
    """ Generates the standard player view showing album art, title, and progress. """
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    components.title.x, components.title.y, components.title.width = 1, 1, 52
    components.artist.x, components.artist.y, components.artist.width = 1, 7, 52
    components.progress_bar.x, components.progress_bar.y, components.progress_bar.width, components.progress_bar.height = 0, 62, 64, 2

    components.album_art.x, components.album_art.y, components.album_art.width, components.album_art.height = ART_X, ART_Y, ART_W, ART_H
    
    components.play_indicator.x, components.play_indicator.y = 56, 3
    components.play_indicator.width, components.play_indicator.height = 4, 6

    color = components.album_art.cache.get_color(response.art_url) if getattr(response, 'art_url', None) else SPOTIFY_BRAND_GREEN

    components.title.draw(draw)
    components.artist.draw(draw)
    components.progress_bar.draw(draw, progress_ms, duration_ms, fill_color=color)
    
    draw.rectangle((53, 0, 63, 12), fill=(0, 0, 0))
    draw.rectangle((W - 1, 0, W - 1, 16), fill=(0, 0, 0))

    components.album_art.draw(img, response.art_url)

    if show_lyrics:
        _draw_inline_lyrics(img, response.lyrics, progress_ms, components.title.font, time_paused, time_playing, time_since_lyrics_fetched)

    draw.rectangle((55, 0, 63, 12), fill=(0, 0, 0))
    
    lyrics_data = getattr(response, 'lyrics', None)
    lyrics_fetch_complete = lyrics_data is not None
    
    has_lyrics = False
    is_currently_showing_lyrics = False
    if lyrics_fetch_complete:
        active_lines = get_active_lines(lyrics_data)
        has_lyrics = len(active_lines) > 0
        for line in active_lines:
            if line['start_ms'] <= progress_ms:
                is_currently_showing_lyrics = True
                break
        
    if not response.is_playing:
        state = "Paused"
    elif time_playing > 0 and time_playing <= components.title.text_scroll_delay:
        state = "Play"
    else:
        state = "Active"
        
    components.play_indicator.draw(draw, state, color=color)

    return img

def _calculate_inline_lyrics_state(valid_lines, progress_ms):
    """ Calculates the opacity and text to draw for inline lyrics. """
    text_alpha = 0.0
    text_to_draw = None

    for i, line in enumerate(valid_lines):
        s = line['start_ms']
        e = line['end_ms']
        if i + 1 < len(valid_lines):
            next_s = valid_lines[i+1]['start_ms']
            if e <= s or e > next_s or (next_s - e) < LYRICS_FADE_MS:
                e = next_s
        else:
            if e <= s:
                e = s + 5000

        if progress_ms >= s and progress_ms <= e:
            tf_in = min(1.0, (progress_ms - s) / float(LYRICS_FADE_MS))
            tf_out = min(1.0, (e - progress_ms) / float(LYRICS_FADE_MS))
            if i + 1 < len(valid_lines):
                next_s = valid_lines[i+1]['start_ms']
                if progress_ms >= next_s:
                    tf_out = 0.0
                elif next_s - progress_ms < LYRICS_FADE_MS:
                    tf_out = min(tf_out, (next_s - progress_ms) / float(LYRICS_FADE_MS))
            t_alpha = max(0.0, min(tf_in, tf_out))
            if t_alpha > text_alpha:
                text_alpha = t_alpha
                text_to_draw = line['text']

    return text_alpha, text_to_draw

def _draw_inline_lyrics(img, lyrics_data, progress_ms, font, time_paused=0.0, time_playing=0.0, time_since_lyrics_fetched=None):
    """ Renders the inline lyrics on top of the standard view. """
    active_lines = get_active_lines(lyrics_data)
    text_alpha, text_to_draw = _calculate_inline_lyrics_state(active_lines, progress_ms)
    
    fade_multiplier = 1.0
    if time_paused > 0:
        fade_multiplier = max(0.0, 1.0 - time_paused / (LYRICS_FADE_MS / 1000.0))
    elif time_playing > 0:
        fade_multiplier = min(1.0, time_playing / (LYRICS_FADE_MS / 1000.0))
        
    if time_since_lyrics_fetched is not None:
        fade_multiplier = min(fade_multiplier, max(0.0, time_since_lyrics_fetched) / (LYRICS_FADE_MS / 1000.0))
        
    text_alpha *= fade_multiplier

    if text_to_draw and text_alpha > 0.01:
        out = wrap_text(text_to_draw, font, LYRICS_WIDTH)
        if len(out) > 7: out = out[:7]
        
        total_height = max(0, len(out) * 6 - 1)
        dimmer_height = min(total_height + (LYRICS_V_PADDING * 2), 48)
        dimmer_y = 62 - dimmer_height
        
        dimmer = Image.new("RGBA", (48, dimmer_height), (0, 0, 0, int(DIMMED_BG_ALPHA * text_alpha)))
        img.paste(dimmer, (8, dimmer_y), dimmer)
        
        y_start = dimmer_y + LYRICS_V_PADDING
        
        text_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_img)
        c_alpha = int(255 * text_alpha)
        
        for i_line, text_line in enumerate(out):
            w = font.getlength(text_line)
            x = 2 + (LYRICS_WIDTH - w) // 2
            text_draw.text((x, y_start + i_line * 6), text_line, fill=(255, 255, 255, c_alpha), font=font)
            
        img.paste(text_img, (0, 0), text_img)
