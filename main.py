# Purpose: Entry point for the Raspberry Pi Spotify Matrix Display application.

import argparse
import configparser
import sys
import time
import warnings
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from services.spotify_api import SpotifyModule
from player.spotify_player import SpotifyPlayer

logger = logging.getLogger(__name__)

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            RotatingFileHandler("matrix.log", maxBytes=5*1024*1024, backupCount=2),
            logging.StreamHandler(sys.stdout)
        ]
    )

def load_config(config_path: str) -> configparser.ConfigParser:
    config = configparser.ConfigParser()

    if not Path(config_path).exists():
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    
    config.read(config_path)
    return config


def setup_matrix(config: configparser.ConfigParser, is_emulated: bool):
    if is_emulated:
        from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
        import pygame
        
        # Clear RGBME's custom logger to prevent duplicate logs
        import logging
        logging.getLogger('RGBME').handlers.clear()
        
        # Workaround for Pygame built without PNG support (e.g., Python 3.14 alpha on macOS)
        # RGBMatrixEmulator attempts to load an icon.png which crashes Pygame if it only supports BMP
        original_load = pygame.image.load
        def safe_load(filepath, *args, **kwargs):
            try:
                return original_load(filepath, *args, **kwargs)
            except pygame.error as e:
                # Return a dummy 1x1 surface if load fails
                return pygame.Surface((1, 1))
        pygame.image.load = safe_load

    else:
        try:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
        except ImportError:
            logger.error("❌ Error: Could not import 'rgbmatrix' module.")
            logger.info("💡 This command is meant for running on a Raspberry Pi connected to an RGB matrix.")
            logger.info("   Use 'make emulate' to run the display within an emulator window.")
            sys.exit(1)
    
    options = RGBMatrixOptions()
    options.hardware_mapping = config.get('Matrix', 'hardware_mapping', fallback='regular')
    options.rows = 64
    options.cols = 64
    options.brightness = 100 if is_emulated else config.getint('Matrix', 'brightness', fallback=100)
    options.gpio_slowdown = config.getint('Matrix', 'gpio_slowdown', fallback=1)
    options.drop_privileges = False
    
    matrix = RGBMatrix(options=options)
    
    # Workaround for RGBMatrixEmulator bug where self.canvas is not initialized
    if is_emulated and not hasattr(matrix, 'canvas'):
        matrix.canvas = None
        
    return matrix


def main():
    parser = argparse.ArgumentParser(description='Raspberry Pi Spotify Matrix Display')
    parser.add_argument('-e', '--emulate', action='store_true', help='run within an emulator window')
    args = parser.parse_args()
    
    # Suppress Pillow 12 (2025-10-15) deprecation warning
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    
    try:
        setup_logging()
        config = load_config('config.ini')
        spotify_module = SpotifyModule(config, is_emulated=args.emulate)
        spotify_player = SpotifyPlayer(config, spotify_module)
        
        matrix = setup_matrix(config, args.emulate)
        
        target_fps = config.getint('Matrix', 'target_fps', fallback=60)
        target_frame_time = 1.0 / target_fps
        
        next_frame_time = time.perf_counter()
        last_time = next_frame_time
        
        while True:
            now = time.perf_counter()
            delta_time = now - last_time
            last_time = now
            
            frame = spotify_player.generate(delta_time)
            
            if frame:
                matrix.SetImage(frame)
            else:
                matrix.Clear()
            
            now = time.perf_counter()
            sleep_time = next_frame_time - now
            
            if sleep_time > 0:
                time.sleep(sleep_time)
                next_frame_time += target_frame_time
            else:
                next_frame_time = now + target_frame_time
            
    except KeyboardInterrupt:
        logger.info(' Interrupted with Ctrl-C')


if __name__ == '__main__':
    main()