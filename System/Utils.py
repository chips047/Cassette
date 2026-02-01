import os
import sys
import time
import pygame
import random
import shutil
import requests
import platform
import subprocess

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

import numpy as np

from System.Constants import *

def get_fox_image(url="https://randomfox.ca/floof/"):
    try:
        resp = requests.get(url, timeout = 2)
        resp.raise_for_status()
        data = resp.json()
        return data.get("image")
    
    except requests.Timeout:
        return

def gaussian_filter1d_np(data, sigma):
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

def get_time():
    t = time.localtime()
    hours = t.tm_hour
    
    if 19 <= hours <= 21:
        return random.choice(
            [
                "Good evening.",
                "Evening vibes.",
                "Time to unwind."
            ]
        )
    
    elif hours >= 22 or hours <= 5:
        return random.choice(
            [
                "Sleep tight.",
                "Sweet dreams.",
                "Nighty night."
            ]
        )
    
    elif 6 <= hours <= 11:
        return random.choice(
            [
                "Good morning.",
                "Rise and shine.",
                "You should get a coffee."
            ]
        )
    
    elif 12 <= hours <= 18:
        return random.choice(
            [
                "Good afternoon.",
                "A great day.",
                "Music time."
            ]
        )
    
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

def open_file(path):
    if platform.system() == "Windows":
        os.startfile(path)
    
    elif platform.system() == "Darwin":
        subprocess.run(["open", path])
    
    else:
        subprocess.run(["xdg-open", path])

def get_songs_path(relative_path: str) -> str:
    normalized_parts = os.path.normpath(relative_path).split(os.sep)
    full_path = os.path.join(os.path.expanduser("~"), "Songs", *normalized_parts)
    
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    return full_path

def run(*args, **kwargs):
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    
    return subprocess.run(*args, **kwargs)

def ui_sound(name, tone=None):
    try:
        if CurrentSettings["disable_sounds"]:
            return

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        sound = pygame.mixer.Sound(f"System/Sounds/{name}.wav")
        array = pygame.sndarray.array(sound)

        rate = np.random.uniform(0.97, 1.03)
        
        if tone:
            rate = tone

        if tone == 1 or not CurrentSettings["sound_tone_effects"]:
            sound.play()
            return

        if array.ndim == 1:
            array_resample = array
        
        else:
            array_resample = array.mean(axis=1)

        new_length = int(len(array_resample) / rate)
        
        resampled = np.interp(
            np.linspace(0, len(array_resample), new_length),
            np.arange(len(array_resample)),
            array_resample
        ).astype(np.int16)

        mixer_channels = pygame.mixer.get_init()[2]
        resampled_multi = np.repeat(resampled[:, None], mixer_channels, axis=1)

        new_sound = pygame.sndarray.make_sound(np.ascontiguousarray(resampled_multi))
        new_sound.play()

    except Exception as e:
        print(str(e))

def auto_cast(value: str):
    if value is None:
        return None

    v = str(value).strip()

    if v.lower() in {"true", "yes", "1"}:
        return True
    if v.lower() in {"false", "no", "0"}:
        return False

    try:
        return int(v)
    except ValueError:
        pass

    try:
        return float(v)
    except ValueError:
        pass

    return value

class Animations:
    def make_animation(object, keyframes: list, property: bytes, duration: int, curve: QEasingCurve = QEasingCurve.OutCubic, loop = False, finished = None):
        anim = QPropertyAnimation(object, property)
        anim.setDuration(duration)
        anim.setKeyValues(keyframes)
        anim.setEasingCurve(curve)
        
        if loop:
            anim.setLoopCount(-1)
        
        if finished:
            anim.finished.connect(finished)

        return anim
    
    def group_animate(animations, finished = None, valueChanged = None, multiplier = 1.0):
        anim_group = QParallelAnimationGroup()

        if multiplier == 1.0:
            multiplier = float(CurrentSettings["animation_multiplier"])

        if multiplier != 1.0:
            for animation in animations:
                animation.setDuration(int(animation.duration() * multiplier))

        for animation in animations:
            if valueChanged:
                animation.valueChanged.connect(valueChanged)
            
            anim_group.addAnimation(animation)
        
        if finished:
            anim_group.finished.connect(finished)

        return anim_group