# Purpose: Utility functions for parsing, validating, and formatting lyrics data.

MAX_LYRIC_GAP_MS = 5000

def clean_text(text):
    """Replaces common typographic characters and homoglyphs with ASCII equivalents to fix font rendering issues."""
    if not text:
        return text
    replacements = {
        '’': "'", '‘': "'", '”': '"', '“': '"',
        '–': '-', '—': '-', '…': '...',
        '\u0399': 'I', '\u03b9': 'i',  # Greek Iota
        '\u0410': 'A', '\u0430': 'a',  # Cyrillic A
        '\u0412': 'B',                 # Cyrillic B
        '\u0421': 'C', '\u0441': 'c',  # Cyrillic C
        '\u0415': 'E', '\u0435': 'e',  # Cyrillic E
        '\u041d': 'H',                 # Cyrillic H
        '\u0406': 'I', '\u0456': 'i',  # Cyrillic I
        '\u041c': 'M',                 # Cyrillic M
        '\u041e': 'O', '\u043e': 'o',  # Cyrillic O
        '\u0420': 'P', '\u0440': 'p',  # Cyrillic P
        '\u0422': 'T',                 # Cyrillic T
        '\u0425': 'X', '\u0445': 'x',  # Cyrillic X
        '\u0443': 'y',                 # Cyrillic y
        '\xa0': ' ',                   # Non-breaking space
        '\u200b': '', '\u200c': '', '\u200d': '', '\u200e': '', '\u200f': '', '\ufeff': ''  # Zero-width / markers
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def get_active_lines(lyrics_data):
    """
    Extracts line-synced lyrics from Spotify data.
    Filters out empty lines and music notes, and extends lines to cover gaps < 5s.
    """
    if not lyrics_data or not lyrics_data.get('lyrics') or lyrics_data['lyrics'].get('syncType') != 'LINE_SYNCED':
        return []
        
    if '_cached_active_lines' in lyrics_data:
        return lyrics_data['_cached_active_lines']
        
    lines = lyrics_data['lyrics'].get('lines', [])
    active_lines = []
    
    for line in lines:
        words = line.get('words', '').strip()
        if "♪" in words:
            words = ""
            
        active_lines.append({
            'start_ms': int(line.get('startTimeMs', 0)),
            'end_ms': int(line.get('endTimeMs', 0)),
            'text': clean_text(words)
        })
            
    for i, line in enumerate(active_lines):
        next_start = active_lines[i+1]['start_ms'] if i + 1 < len(active_lines) else line['start_ms'] + MAX_LYRIC_GAP_MS
        
        if line['end_ms'] == 0:
            line['end_ms'] = next_start
            
    lyrics_data['_cached_active_lines'] = active_lines
    return active_lines

_last_printed_lyric = None

def get_active_lyric(active_lines, progress_ms, keepalive=False):
    """
    Finds the active lyric based on the current playback progress.
    Returns (text, start_ms, end_ms, next_start_ms).
    """
    for i, line in enumerate(active_lines):
        if progress_ms < line['start_ms']:
            return None, 0, 0, line['start_ms']
            
        next_start = active_lines[i+1]['start_ms'] if i + 1 < len(active_lines) else None
        
        effective_end = line['end_ms']
        if keepalive and line['text']:
            next_text_start = None
            for j in range(i + 1, len(active_lines)):
                if active_lines[j]['text']:
                    next_text_start = active_lines[j]['start_ms']
                    break
                    
            if next_text_start and next_text_start - line['end_ms'] <= MAX_LYRIC_GAP_MS:
                effective_end = next_text_start
                next_start = next_text_start
                
        if line['text'] and line['start_ms'] <= progress_ms < effective_end:
            global _last_printed_lyric
            if line['text'] != _last_printed_lyric:
                # print(f"- {line['text']}", flush=True)
                _last_printed_lyric = line['text']
                
            return line['text'], line['start_ms'], effective_end, next_start
            
    return None, 0, 0, None

def has_current_lyrics(response, progress_ms, lookahead_ms=0):
    """Checks if there are any active lyrics for the given playback progress."""
    if not response or not getattr(response, 'lyrics', None):
        return False
        
    active_lines = get_active_lines(response.lyrics)
    target_ms = progress_ms + lookahead_ms
    
    if any(line['text'] and line['start_ms'] <= target_ms and progress_ms < line['end_ms'] for line in active_lines):
        return True
        
    last_text_end = None
    next_text_start = None
    
    for line in active_lines:
        if line['text']:
            if line['end_ms'] <= progress_ms:
                last_text_end = line['end_ms']
            elif line['start_ms'] > progress_ms:
                next_text_start = line['start_ms']
                break
                
    if last_text_end is not None and next_text_start is not None:
        if next_text_start - last_text_end <= MAX_LYRIC_GAP_MS:
            return True
            
    if last_text_end is None and next_text_start is not None:
        if next_text_start <= MAX_LYRIC_GAP_MS:
            return True
            
    return False

def wrap_text(text, font, max_width):
    """
    Wraps text to fit within a given maximum width using the provided font.
    Splits long words and adds hyphens where necessary.
    """
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip()
        if font.getlength(test_line) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
                
            current_line = ""
            remaining_word = word
            
            while remaining_word:
                if font.getlength(remaining_word) <= max_width:
                    current_line = remaining_word
                    break
                    
                found_split = False
                
                # Try to split on existing hyphens
                for i in range(len(remaining_word) - 1, 0, -1):
                    if remaining_word[i] == '-':
                        test_part = remaining_word[:i+1]
                        if font.getlength(test_part) <= max_width:
                            lines.append(test_part)
                            remaining_word = remaining_word[i+1:]
                            found_split = True
                            break
                            
                if found_split:
                    continue
                    
                # Try to forcefully split with a new hyphen
                for i in range(len(remaining_word) - 1, 0, -1):
                    test_part = remaining_word[:i] + "-"
                    if font.getlength(test_part) <= max_width:
                        lines.append(test_part)
                        remaining_word = remaining_word[i:]
                        found_split = True
                        break
                        
                if not found_split:
                    # If we can't even fit one character with a hyphen, just take the first character
                    lines.append(remaining_word[0])
                    remaining_word = remaining_word[1:]
                    
    if current_line:
        lines.append(current_line)
        
    return lines
