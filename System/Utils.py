import os
import sys
import shutil
import platform
import subprocess

import numpy as np

def gaussian_filter1d_np(data, sigma):
    # Размер ядра: 6 * sigma (как в scipy) или минимум 3
    radius = int(3 * sigma)
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-(x**2) / (2 * sigma**2))
    kernel /= kernel.sum()
    return np.convolve(data, kernel, mode='same')

def medfilt_np(data, kernel_size):
    if kernel_size % 2 == 0:
        raise ValueError("kernel_size must be odd")
    pad_width = kernel_size // 2
    padded = np.pad(data, pad_width, mode='edge')
    shape = (data.size, kernel_size)
    strides = (padded.strides[0], padded.strides[0])
    windows = np.lib.stride_tricks.as_strided(padded, shape=shape, strides=strides)
    return np.median(windows, axis=1)

def system_global_error_message(title, message):
    system = platform.system()

    if system == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,
                message,
                title, 0x40 | 0x1)
        
        except:
            pass

    elif system == "Darwin":
        subprocess.run([
            "osascript", "-e",
            f'display dialog "{message}" '
            f'with title "{title}" buttons ["OK"]'
        ])

    elif system == "Linux":
        if shutil.which("zenity"):
            subprocess.run([
                "zenity", "--info",
                "--title", title,
                "--text", message
            ])
    
    sys.exit(1)

try:
    import time
    import pygame

    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *

except ModuleNotFoundError as e:
    system_global_error_message(
        "Oops!",
        f"Missing module: {e.name}\nTry to install it with the \"pip install {e.name}\" command."
    )

def get_time():
    t = time.localtime()
    hours = t.tm_hour
    
    if 19 <= hours <= 21:
        return "Good evening."
    
    elif hours >= 22 or hours <= 5:
        return "Nighty night."
    
    elif 7 <= hours <= 11:
        return "Good morning."
    
    elif 12 <= hours <= 18:
        return "Hello."
    
    else:
        return "what the fuck"

def NDot(size):
    Ndot = QFont("Ndot 57")
    px_size = round(size * 120 / 72)
    Ndot.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    Ndot.setPixelSize(px_size)
    
    return Ndot

def NType(size):
    Ntype = QFont("NType 82")
    px_size = round(size * 120 / 72)
    Ntype.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    Ntype.setPixelSize(px_size)
    
    return Ntype

class Icons:
    WindowIcon = QIcon("System/Icons/Icon256.ico")
    Duration = QIcon("System/Icons/Duration.png")
    Brightness = QIcon("System/Icons/Brightness.png")
    Speed = QIcon("System/Icons/Speed.png")
    Play = QIcon("System/Icons/Play.png")
    Pause = QIcon("System/Icons/Pause.png")

def get_songs_path(relative_path: str) -> str:
    base_path = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
    cassette_root = os.path.abspath(os.path.join(base_path, ".."))
    normalized_parts = os.path.normpath(relative_path).split(os.sep)
    full_path = os.path.join(cassette_root, "Songs", *normalized_parts)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    return full_path

def get_cache_path(relative_path: str) -> str:
    base_path = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
    cassette_root = os.path.abspath(os.path.join(base_path, ".."))
    normalized_parts = os.path.normpath(relative_path).split(os.sep)
    full_path = os.path.join(cassette_root, "Cache", *normalized_parts)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    return full_path

def run(*args, **kwargs):
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    
    return subprocess.run(*args, **kwargs)

def ui_sound(name):
    try:
        sound = pygame.mixer.Sound(f"System/UI/{name}.wav")

        array = pygame.sndarray.array(sound)
        rate = np.random.uniform(0.97, 1.03)
        new_length = int(len(array) / rate)
        resampled = np.interp(np.linspace(0, len(array), new_length), np.arange(len(array)), array[:, 0]).astype(np.int16)
        
        new_sound = pygame.sndarray.make_sound(np.column_stack((resampled, resampled)))
        new_sound.play()

    except Exception as e: print(str(e))