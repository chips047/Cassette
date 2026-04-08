import os
import re
import sys
import json
import time
import numpy
import random
import platform
import subprocess

from urllib.request import urlopen

from PyQt5.QtGui import (
    QFont,
    QPainterPath
)

from PyQt5.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QParallelAnimationGroup
)

from loguru import logger

def get_fox_image() -> str | None:
    url = "https://randomfox.ca/floof/"

    try:
        with urlopen(url, timeout = 2) as r:
            info = json.loads(r.read())
            return info.get("image")
    
    except:
        return None

def gaussian_filter1d_np(data: numpy.ndarray, sigma: float) -> numpy.ndarray:
    radius  = int(3 * sigma)
    x       = numpy.arange(-radius, radius + 1)
    kernel  = numpy.exp(-(x**2) / (2 * sigma**2))
    kernel /= kernel.sum()
    
    return numpy.convolve(data, kernel, mode='same')

def medfilt_np(data: numpy.ndarray, kernel_size: int) -> numpy.ndarray:
    if kernel_size % 2 == 0:
        raise ValueError("kernel_size must be odd")
    
    pad_width = kernel_size // 2

    padded  = numpy.pad(data, pad_width, mode = 'edge')
    shape   = (data.size, kernel_size)
    strides = (padded.strides[0], padded.strides[0])
    windows = numpy.lib.stride_tricks.as_strided(padded, shape=shape, strides=strides)
    
    return numpy.median(windows, axis = 1)

def get_time() -> str:
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

def NDot(size: int) -> QFont:
    Ndot = QFont("Ndot 57")
    
    px_size = round(size * 120 / 72)
    Ndot.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    Ndot.setPixelSize(px_size)
    
    return Ndot

def NType(size: int) -> QFont:
    Ntype = QFont("NType 82")
    
    px_size = round(size * 120 / 72)
    Ntype.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    Ntype.setPixelSize(px_size)
    
    return Ntype

def open_file(path: str) -> None:
    if platform.system() == "Windows":
        os.startfile(path)
    
    elif platform.system() == "Darwin":
        subprocess.run(["open", path])
    
    else:
        subprocess.run(["xdg-open", path])

def get_user_path(relative_path: str, folder: str) -> str:
    normalized_parts = os.path.normpath(relative_path).split(os.sep)
    full_path = os.path.join(os.path.expanduser("~"), folder, *normalized_parts)

    os.makedirs(os.path.dirname(full_path), exist_ok = True)

    return full_path

def run(*args, **kwargs) -> subprocess.CompletedProcess:
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    
    return subprocess.run(*args, **kwargs)

def auto_cast(value: str) -> str | bool | int | float | None:
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

def parse_svg_path_data(d_string: str) -> QPainterPath:
    path = QPainterPath()
    tokens = re.findall(r'([a-zA-Z]|-?[\d\.]+)', d_string)
    
    current_x = 0.0
    current_y = 0.0
    
    i = 0

    while i < len(tokens):
        cmd = tokens[i]
        
        if not cmd[0].isalpha():
            pass
        
        else:
            i += 1
        
        if cmd == 'M':
            x = float(tokens[i]); y = float(tokens[i+1])
            path.moveTo(x, y)
            current_x, current_y = x, y
            i += 2
        
        elif cmd == 'L':
            x = float(tokens[i]); y = float(tokens[i+1])
            path.lineTo(x, y)
            current_x, current_y = x, y
            i += 2
        
        elif cmd == 'H':
            x = float(tokens[i])
            path.lineTo(x, current_y)
            current_x = x
            i += 1
        
        elif cmd == 'V':
            y = float(tokens[i])
            path.lineTo(current_x, y)
            current_y = y
            i += 1
        
        elif cmd == 'C':
            c1x = float(tokens[i]);   c1y = float(tokens[i+1])
            c2x = float(tokens[i+2]); c2y = float(tokens[i+3])
            ex = float(tokens[i+4]);  ey = float(tokens[i+5])
            path.cubicTo(c1x, c1y, c2x, c2y, ex, ey)
            current_x, current_y = ex, ey
            i += 6
        
        elif cmd == 'Z' or cmd == 'z':
            path.closeSubpath()
        
        else:
            pass
    
    return path

def get_resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    
    else:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def get_ffmpeg_path(name: str = "ffmpeg") -> str:
    logger.debug(f"Searching for {name}...")

    plat = sys.platform
    arch = platform.machine().lower()
    is_arm = "arm" in arch

    logger.debug(f"Platform: {plat}")
    logger.debug(arch)
    logger.debug(f"Is ARM: {is_arm}")
    
    if plat == "win32":
        file_name = f"{name}-windows.exe"
    
    elif plat == "darwin":
        suffix = "silicon" if is_arm else "intel"
        file_name = f"{name}-macos-{suffix}"
    
    elif plat == "linux":
        file_name = f"{name}-linux"

    full_path = get_resource_path(f"System/FFmpeg/{file_name}")

    if os.path.exists(full_path):
        logger.success(f"Found {name}: {full_path}")
    
    else:
        logger.error(f"{name} not found at {full_path}")

    return full_path