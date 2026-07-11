from __future__ import annotations

import time
import math
import threading
import traceback

from enum import Enum
from itertools import count
from weakref import WeakKeyDictionary

from loguru import logger

from collections.abc import Callable

from System.Common import Constants

# Signals

class EventSignal:
    __slots__ = ("callbacks",)

    def __init__(self) -> None:
        self.callbacks: list[Callable[..., object]] = []

    def connect(self, callback: Callable[..., object]) -> None:
        if callback in self.callbacks:
            return

        self.callbacks.append(callback)

    def disconnect(self, callback: Callable[..., object] | None = None) -> None:
        if callback is None:
            self.callbacks.clear()
            return

        if callback not in self.callbacks:
            return

        self.callbacks.remove(callback)

    def emit(self, *arguments: object, **keywords: object) -> None:
        for callback in list(self.callbacks):
            try:
                callback(*arguments, **keywords)

            except Exception:
                logger.error(f"Signal callback failed: {traceback.format_exc()}")

# Geometry

class Point:
    __slots__ = ("x_value", "y_value")

    def __init__(
            self,
            x: float = 0.0,
            y: float = 0.0
        ) -> None:

        self.x_value = x
        self.y_value = y

    def x(self) -> float:
        return self.x_value

    def y(self) -> float:
        return self.y_value

class Size:
    __slots__ = ("width_value", "height_value")

    def __init__(
            self,
            width:  float = 0.0,
            height: float = 0.0
        ) -> None:

        self.width_value  = width
        self.height_value = height

    def width(self) -> float:
        return self.width_value

    def height(self) -> float:
        return self.height_value

class Rect:
    __slots__ = ("x_value", "y_value", "width_value", "height_value")

    def __init__(
            self,
            x:      float = 0.0,
            y:      float = 0.0,
            width:  float = 0.0,
            height: float = 0.0
        ) -> None:

        self.x_value      = x
        self.y_value      = y
        self.width_value  = width
        self.height_value = height

    def x(self) -> float:
        return self.x_value

    def y(self) -> float:
        return self.y_value

    def width(self) -> float:
        return self.width_value

    def height(self) -> float:
        return self.height_value

class Color:
    __slots__ = ("red_value", "green_value", "blue_value", "alpha_value")

    def __init__(
            self,
            red:   int = 0,
            green: int = 0,
            blue:  int = 0,
            alpha: int = 255
        ) -> None:

        self.red_value   = red
        self.green_value = green
        self.blue_value  = blue
        self.alpha_value = alpha

    def red(self) -> int:
        return self.red_value

    def green(self) -> int:
        return self.green_value

    def blue(self) -> int:
        return self.blue_value

    def alpha(self) -> int:
        return self.alpha_value

# Timekeeping

class Stopwatch:
    def __init__(self) -> None:
        self.started_at = time.perf_counter()

    def start(self) -> None:
        self.started_at = time.perf_counter()

    def elapsed(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

class QtTicker:
    def __init__(
            self,
            callback:    Callable[[], object],
            interval_ms: int,
            timer_type:  object
        ) -> None:

        self.timer = timer_type()
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(callback)

    def start(self) -> None:
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def set_interval_ms(self, interval_ms: int) -> None:
        self.timer.setInterval(interval_ms)

class ThreadTicker:
    def __init__(
            self,
            callback:    Callable[[], object],
            interval_ms: int
        ) -> None:

        self.callback                        = callback
        self.interval_ms                     = interval_ms
        self.running                         = False
        self.stop_event                      = threading.Event()
        self.thread: threading.Thread | None = None

    def run(self) -> None:
        next_tick = time.perf_counter()

        while not self.stop_event.is_set():
            next_tick += self.interval_ms / 1000.0

            try:
                self.callback()

            except Exception as exception:
                logger.error(f"Ticker callback failed: {exception}")

            remaining = next_tick - time.perf_counter()

            if remaining > 0:
                self.stop_event.wait(remaining)

        self.running = False

    def start(self) -> None:
        if self.running:
            return

        self.stop_event.clear()
        self.thread  = threading.Thread(target = self.run, daemon = True)
        self.running = True
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

        if self.thread is None:
            return

        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout = 1.0)

        self.running = False

    def set_interval_ms(self, interval_ms: int) -> None:
        self.interval_ms = interval_ms

class RuntimeBackend:
    def __init__(self, name: str | None) -> None:
        self.name    = (name or "pure").lower()
        self.is_pure = self.name in {"pure", "none"}
        self.is_qt   = self.name in {"pyqt5", "pyqt6", "pyside2", "pyside6"}

        self.qt_timer_type       = None
        self.qt_single_shot      = None
        self.qt_elapsed_timer    = None
        self.qt_application_type = None

        self.qt_point_type  = None
        self.qt_rect_type   = None
        self.qt_size_type   = None
        self.qt_color_type  = None
        self.qt_pointf_type = None
        self.qt_rectf_type  = None
        self.qt_sizef_type  = None

        if self.is_qt:
            self.initialize_qt_backend()

    def initialize_qt_backend(self) -> None:
        if self.name == "pyqt5":
            from PyQt5.QtCore import (
                QSize,
                QTimer,
                QPoint,
                QRect,
                QSizeF,
                QPointF,
                QRectF,
                QElapsedTimer,
                QCoreApplication
            )

            from PyQt5.QtGui import (
                QColor
            )

        elif self.name == "pyqt6":
            from PyQt6.QtCore import (
                QSize,
                QTimer,
                QPoint,
                QRect,
                QSizeF,
                QPointF,
                QRectF,
                QElapsedTimer,
                QCoreApplication
            )

            from PyQt6.QtGui import (
                QColor
            )

        elif self.name == "pyside2":
            from PySide2.QtCore import (
                QSize,
                QTimer,
                QPoint,
                QRect,
                QSizeF,
                QPointF,
                QRectF,
                QElapsedTimer,
                QCoreApplication
            )

            from PySide2.QtGui import (
                QColor
            )

        elif self.name == "pyside6":
            from PySide6.QtCore import (
                QSize,
                QTimer,
                QPoint,
                QRect,
                QSizeF,
                QPointF,
                QRectF,
                QElapsedTimer,
                QCoreApplication
            )

            from PySide6.QtGui import (
                QColor
            )

        else:
            raise ValueError(f"Unknown backend: {self.name}")

        self.qt_timer_type       = QTimer
        self.qt_single_shot      = QTimer.singleShot
        self.qt_elapsed_timer    = QElapsedTimer
        self.qt_application_type = QCoreApplication

        self.qt_point_type  = QPoint
        self.qt_rect_type   = QRect
        self.qt_size_type   = QSize
        self.qt_color_type  = QColor
        self.qt_pointf_type = QPointF
        self.qt_rectf_type  = QRectF
        self.qt_sizef_type  = QSizeF

    def qt_application_running(self) -> bool:
        if not self.is_qt:
            return False

        return self.qt_application_type.instance() is not None

    def create_stopwatch(self) -> object:
        if self.is_qt:
            timer = self.qt_elapsed_timer()
            timer.start()

            return timer

        return Stopwatch()

    def create_ticker(
            self,
            callback:    Callable[[], object],
            interval_ms: int
        ) -> object:

        if self.is_qt:
            if not self.qt_application_running():
                return None

            logger.debug(f"Creating Qt ticker with interval {interval_ms} ms")
            return QtTicker(
                callback              = callback,
                interval_ms           = interval_ms,
                timer_type            = self.qt_timer_type
            )

        return ThreadTicker(
            callback              = callback,
            interval_ms           = interval_ms
        )

    def defer(self, callback: Callable[[], object]) -> None:
        if self.is_qt and self.qt_application_running():
            self.qt_single_shot(0, callback)
            return

        callback()

# Easing

class Easing:
    @staticmethod
    def linear(t: float) -> float:
        return t

    @staticmethod
    def bouncy(t: float) -> float:
        if t == 0:
            return 0.0

        if t == 1:
            return 1.0

        amplitude = 1.7
        period    = 0.27
        shift     = period / (2 * math.pi) * math.asin(1.0 / amplitude)

        return amplitude * math.pow(2, -10 * t) * math.sin((t - shift) * (2 * math.pi) / period) + 1.0

    @staticmethod
    def very_bouncy(t: float) -> float:
        if t == 0:
            return 0.0

        if t == 1:
            return 1.0

        period = 0.35
        shift  = period / 4

        return math.pow(2, -7 * t) * math.sin((t - shift) * (2 * math.pi) / period) + 1

    @staticmethod
    def smooth(t: float) -> float:
        return t * t * (3 - 2 * t)

    @staticmethod
    def ease_in_sine(t: float) -> float:
        return 1 - math.cos((t * math.pi) / 2)

    @staticmethod
    def ease_out_sine(t: float) -> float:
        return math.sin((t * math.pi) / 2)

    @staticmethod
    def ease_in_out_sine(t: float) -> float:
        return -(math.cos(math.pi * t) - 1) / 2

    @staticmethod
    def ease_in_quad(t: float) -> float:
        return t * t

    @staticmethod
    def ease_out_quad(t: float) -> float:
        return 1 - (1 - t) * (1 - t)

    @staticmethod
    def ease_in_out_quad(t: float) -> float:
        return 2 * t * t if t < 0.5 else 1 - math.pow(-2 * t + 2, 2) / 2

    @staticmethod
    def ease_in_out_cubic(t: float) -> float:
        return 4 * t * t * t if t < 0.5 else 1 - math.pow(-2 * t + 2, 3) / 2

    @staticmethod
    def ease_in_out_quart(t: float) -> float:
        return 8 * t ** 4 if t < 0.5 else 1 - math.pow(-2 * t + 2, 4) / 2

    @staticmethod
    def ease_out_quint(t: float) -> float:
        return 1 - math.pow(1 - t, 5)

    @staticmethod
    def ease_out_circ(t: float) -> float:
        return math.sqrt(max(0.0, 1 - math.pow(t - 1, 2)))

    @staticmethod
    def ease_in_back(t: float) -> float:
        constant_one   = 1.70158
        constant_three = constant_one + 1

        return constant_three * t * t * t - constant_one * t * t

    @staticmethod
    def ease_out_back(t: float) -> float:
        constant_one   = 2.0
        constant_three = constant_one + 1

        return 1 + constant_three * math.pow(t - 1, 3) + constant_one * math.pow(t - 1, 2)

    @staticmethod
    def ease_in_out_back(t: float) -> float:
        constant_one = 1.70158
        constant_two = constant_one * 1.525

        if t < 0.5:
            return (math.pow(2 * t, 2) * ((constant_two + 1) * 2 * t - constant_two)) / 2

        return (math.pow(2 * t - 2, 2) * ((constant_two + 1) * (2 * t - 2) + constant_two) + 2) / 2

    @staticmethod
    def ease_out_elastic(t: float) -> float:
        if t == 0.0:
            return 0.0
    
        if t == 1.0:
            return 1.0
    
        constant_four = (2 * math.pi) / 3
    
        return math.pow(2, -10 * t) * math.sin((t * 10 - 0.75) * constant_four) + 1

    @staticmethod
    def ease_out_bounce(t: float) -> float:
        gradient = 7.5625
        divisor  = 2.75

        if t < 1 / divisor:
            return gradient * t * t

        if t < 2 / divisor:
            t -= 1.5 / divisor
            return gradient * t * t + 0.75

        if t < 2.5 / divisor:
            t -= 2.25 / divisor
            return gradient * t * t + 0.9375

        t -= 2.625 / divisor

        return gradient * t * t + 0.984375

    @staticmethod
    def ease_in_bounce(t: float) -> float:
        return 1 - Easing.ease_out_bounce(1 - t)

    @staticmethod
    def ease_in_out_bounce(t: float) -> float:
        if t < 0.5:
            return (1 - Easing.ease_out_bounce(1 - 2 * t)) / 2

        return (1 + Easing.ease_out_bounce(2 * t - 1)) / 2

    @staticmethod
    def ease_out_quart(t: float) -> float:
        t = max(0.0, min(1.0, t))

        return 1 - (1 - t) ** 4

    @staticmethod
    def ease_in_quart(t: float) -> float:
        t = max(0.0, min(1.0, t))

        return t ** 4

    @staticmethod
    def ease_out_cubic(t: float) -> float:
        t = max(0.0, min(1.0, t))

        return 1 - (1 - t) ** 3

    @staticmethod
    def ease_in_expo(t: float) -> float:
        if t == 0.0:
            return 0.0

        return math.pow(2, 10 * (t - 1))

    @staticmethod
    def ease_out_expo(t: float) -> float:
        if t == 1.0:
            return 1.0

        return 1 - math.pow(2, -10 * t)

    @staticmethod
    def ease_in_out_expo(t: float) -> float:
        if t == 0.0:
            return 0.0

        if t == 1.0:
            return 1.0

        if t < 0.5:
            return math.pow(2, 20 * t - 10) / 2

        return (2 - math.pow(2, -20 * t + 10)) / 2

# Mix Modes

class MixMode(Enum):
    ADD      = 0
    MULTIPLY = 1
    REPLACE  = 2

# Playback Modes

class PlaybackMode(Enum):
    CURVE    = 0
    TIMELINE = 1
    STEP     = 2

# Animation Math

class AnimationMath:
    _shape_cache:    dict[type, str]              = {}
    _accessor_cache: dict[tuple[type, str], bool] = {}

    @staticmethod
    def lerp_scalar(start, end, progress):
        return start + (end - start) * progress

    @staticmethod
    def is_number(value: object) -> bool:
        return isinstance(value, (int, float))

    @staticmethod
    def is_color_like(value: object) -> bool:
        return all(
            hasattr(value, attribute)
            for attribute in ("red", "green", "blue", "alpha")
        )

    @staticmethod
    def is_rect_like(value: object) -> bool:
        return all(
            hasattr(value, attribute)
            for attribute in ("x", "y", "width", "height")
        )

    @staticmethod
    def is_size_like(value: object) -> bool:
        return (
            all(hasattr(value, attribute) for attribute in ("width", "height"))
            and not AnimationMath.is_rect_like(value)
        )

    @staticmethod
    def is_point_like(value: object) -> bool:
        return (
            all(hasattr(value, attribute) for attribute in ("x", "y"))
            and not AnimationMath.is_rect_like(value)
        )

    @staticmethod
    def _classify(value: object) -> str:
        value_type = type(value)
        kind        = AnimationMath._shape_cache.get(value_type)

        if kind is not None:
            return kind

        if AnimationMath.is_number(value):
            kind = "number"

        elif AnimationMath.is_point_like(value):
            kind = "point"

        elif AnimationMath.is_size_like(value):
            kind = "size"

        elif AnimationMath.is_rect_like(value):
            kind = "rect"

        elif AnimationMath.is_color_like(value):
            kind = "color"

        else:
            kind = "other"

        AnimationMath._shape_cache[value_type] = kind

        return kind

    @staticmethod
    def component_value(value: object, name: str) -> float:
        key         = (type(value), name)
        is_callable = AnimationMath._accessor_cache.get(key)

        component = getattr(value, name)

        if is_callable is None:
            is_callable = callable(component)
            AnimationMath._accessor_cache[key] = is_callable

        if is_callable:
            return component()

        return component

    @staticmethod
    def construct_like(value: object, *arguments: object) -> object:
        try:
            return type(value)(*arguments)

        except (TypeError, ValueError):
            return type(value)(*[int(argument) for argument in arguments])

    @staticmethod
    def interpolate(
            start:    object,
            end:      object,
            progress: float
        ) -> object:
        
        if isinstance(start, tuple) and isinstance(end, tuple):
            return tuple(AnimationMath.interpolate(s, e, progress) for s, e in zip(start, end))
            
        if isinstance(start, list) and isinstance(end, list):
            return [AnimationMath.interpolate(s, e, progress) for s, e in zip(start, end)]

        kind = AnimationMath._classify(start)

        if kind == "number":
            return AnimationMath.lerp_scalar(start, end, progress)

        if kind == "point":
            x = AnimationMath.component_value(start, "x") + (AnimationMath.component_value(end, "x") - AnimationMath.component_value(start, "x")) * progress
            y = AnimationMath.component_value(start, "y") + (AnimationMath.component_value(end, "y") - AnimationMath.component_value(start, "y")) * progress

            return AnimationMath.construct_like(start, x, y)

        if kind == "size":
            width  = AnimationMath.component_value(start, "width")  + (AnimationMath.component_value(end, "width")  - AnimationMath.component_value(start, "width"))  * progress
            height = AnimationMath.component_value(start, "height") + (AnimationMath.component_value(end, "height") - AnimationMath.component_value(start, "height")) * progress

            return AnimationMath.construct_like(start, width, height)

        if kind == "rect":
            x      = AnimationMath.component_value(start, "x")      + (AnimationMath.component_value(end, "x")      - AnimationMath.component_value(start, "x"))      * progress
            y      = AnimationMath.component_value(start, "y")      + (AnimationMath.component_value(end, "y")      - AnimationMath.component_value(start, "y"))      * progress
            width  = AnimationMath.component_value(start, "width")  + (AnimationMath.component_value(end, "width")  - AnimationMath.component_value(start, "width"))  * progress
            height = AnimationMath.component_value(start, "height") + (AnimationMath.component_value(end, "height") - AnimationMath.component_value(start, "height")) * progress

            return AnimationMath.construct_like(start, x, y, width, height)

        if kind == "color":
            red   = int(AnimationMath.component_value(start, "red")   + (AnimationMath.component_value(end, "red")   - AnimationMath.component_value(start, "red"))   * progress)
            green = int(AnimationMath.component_value(start, "green") + (AnimationMath.component_value(end, "green") - AnimationMath.component_value(start, "green")) * progress)
            blue  = int(AnimationMath.component_value(start, "blue")  + (AnimationMath.component_value(end, "blue")  - AnimationMath.component_value(start, "blue"))  * progress)
            alpha = int(AnimationMath.component_value(start, "alpha") + (AnimationMath.component_value(end, "alpha") - AnimationMath.component_value(start, "alpha")) * progress)

            return AnimationMath.construct_like(start, red, green, blue, alpha)

        return start

    @staticmethod
    def add(
            first:  object,
            second: object
        ) -> object:
        
        if isinstance(first, tuple) and isinstance(second, tuple):
            return tuple(AnimationMath.add(f, s) for f, s in zip(first, second))
            
        if isinstance(first, list) and isinstance(second, list):
            return [AnimationMath.add(f, s) for f, s in zip(first, second)]

        kind = AnimationMath._classify(first)

        if kind == "number":
            return first + second

        if kind == "point":
            return AnimationMath.construct_like(
                first,
                AnimationMath.component_value(first, "x") + AnimationMath.component_value(second, "x"),
                AnimationMath.component_value(first, "y") + AnimationMath.component_value(second, "y")
            )

        if kind == "size":
            return AnimationMath.construct_like(
                first,
                AnimationMath.component_value(first, "width")  + AnimationMath.component_value(second, "width"),
                AnimationMath.component_value(first, "height") + AnimationMath.component_value(second, "height")
            )

        if kind == "rect":
            return AnimationMath.construct_like(
                first,
                AnimationMath.component_value(first, "x")      + AnimationMath.component_value(second, "x"),
                AnimationMath.component_value(first, "y")      + AnimationMath.component_value(second, "y"),
                AnimationMath.component_value(first, "width")  + AnimationMath.component_value(second, "width"),
                AnimationMath.component_value(first, "height") + AnimationMath.component_value(second, "height")
            )

        if kind == "color":
            return AnimationMath.construct_like(
                first,
                min(255, int(AnimationMath.component_value(first, "red")   + AnimationMath.component_value(second, "red"))),
                min(255, int(AnimationMath.component_value(first, "green") + AnimationMath.component_value(second, "green"))),
                min(255, int(AnimationMath.component_value(first, "blue")  + AnimationMath.component_value(second, "blue"))),
                min(255, int(AnimationMath.component_value(first, "alpha") + AnimationMath.component_value(second, "alpha")))
            )

        return second

    @staticmethod
    def multiply(
            first:  object,
            second: object
        ) -> object:
        
        if isinstance(first, tuple) and isinstance(second, tuple):
            return tuple(AnimationMath.multiply(f, s) for f, s in zip(first, second))
            
        if isinstance(first, list) and isinstance(second, list):
            return [AnimationMath.multiply(f, s) for f, s in zip(first, second)]

        kind = AnimationMath._classify(first)

        if kind == "number":
            return first * second

        if kind == "point":
            return AnimationMath.construct_like(
                first,
                AnimationMath.component_value(first, "x") * AnimationMath.component_value(second, "x"),
                AnimationMath.component_value(first, "y") * AnimationMath.component_value(second, "y")
            )

        if kind == "size":
            return AnimationMath.construct_like(
                first,
                AnimationMath.component_value(first, "width")  * AnimationMath.component_value(second, "width"),
                AnimationMath.component_value(first, "height") * AnimationMath.component_value(second, "height")
            )

        if kind == "rect":
            return AnimationMath.construct_like(
                first,
                AnimationMath.component_value(first, "x")      * AnimationMath.component_value(second, "x"),
                AnimationMath.component_value(first, "y")      * AnimationMath.component_value(second, "y"),
                AnimationMath.component_value(first, "width")  * AnimationMath.component_value(second, "width"),
                AnimationMath.component_value(first, "height") * AnimationMath.component_value(second, "height")
            )

        if kind == "color":
            return AnimationMath.construct_like(
                first,
                int(AnimationMath.component_value(first, "red")   * AnimationMath.component_value(second, "red")   / 255),
                int(AnimationMath.component_value(first, "green") * AnimationMath.component_value(second, "green") / 255),
                int(AnimationMath.component_value(first, "blue")  * AnimationMath.component_value(second, "blue")  / 255),
                int(AnimationMath.component_value(first, "alpha") * AnimationMath.component_value(second, "alpha") / 255)
            )

        return second

    @staticmethod
    def is_different(
            first:     object,
            second:    object,
            tolerance: float = 0.0001
        ) -> bool:

        if type(first) != type(second):
            return True
            
        if isinstance(first, tuple) and isinstance(second, tuple):
            return any(AnimationMath.is_different(f, s, tolerance) for f, s in zip(first, second))
            
        if isinstance(first, list) and isinstance(second, list):
            return any(AnimationMath.is_different(f, s, tolerance) for f, s in zip(first, second))

        kind = AnimationMath._classify(first)

        if kind == "number":
            return abs(first - second) > tolerance

        if kind == "point":
            return (
                abs(AnimationMath.component_value(first, "x") - AnimationMath.component_value(second, "x")) > tolerance or
                abs(AnimationMath.component_value(first, "y") - AnimationMath.component_value(second, "y")) > tolerance
            )

        if kind == "size":
            return (
                abs(AnimationMath.component_value(first, "width")  - AnimationMath.component_value(second, "width"))  > tolerance or
                abs(AnimationMath.component_value(first, "height") - AnimationMath.component_value(second, "height")) > tolerance
            )

        if kind == "rect":
            return (
                abs(AnimationMath.component_value(first, "x")      - AnimationMath.component_value(second, "x"))      > tolerance or
                abs(AnimationMath.component_value(first, "y")      - AnimationMath.component_value(second, "y"))      > tolerance or
                abs(AnimationMath.component_value(first, "width")  - AnimationMath.component_value(second, "width"))  > tolerance or
                abs(AnimationMath.component_value(first, "height") - AnimationMath.component_value(second, "height")) > tolerance
            )

        if kind == "color":
            return (
                abs(AnimationMath.component_value(first, "red")   - AnimationMath.component_value(second, "red"))   > tolerance or
                abs(AnimationMath.component_value(first, "green") - AnimationMath.component_value(second, "green")) > tolerance or
                abs(AnimationMath.component_value(first, "blue")  - AnimationMath.component_value(second, "blue"))  > tolerance or
                abs(AnimationMath.component_value(first, "alpha") - AnimationMath.component_value(second, "alpha")) > tolerance
            )

        return first != second
    
    @staticmethod
    def soft_limit_max(
            value:           object,
            max_val:         object,
            softness_factor: float = 0.8
        ) -> object:

        if max_val is None:
            return value

        if isinstance(value, tuple) and isinstance(max_val, tuple):
            return tuple(AnimationMath.soft_limit_max(v, m, softness_factor) for v, m in zip(value, max_val))
            
        if isinstance(value, list) and isinstance(max_val, list):
            return [AnimationMath.soft_limit_max(v, m, softness_factor) for v, m in zip(value, max_val)]

        kind = AnimationMath._classify(value)

        if kind == "number":
            threshold = max_val * softness_factor

            if value <= threshold:
                return value

            if max_val <= threshold:
                return max_val

            return max_val - (max_val - threshold) * math.exp(-(value - threshold) / (max_val - threshold))

        if kind == "point":
            return AnimationMath.construct_like(
                value,
                AnimationMath.soft_limit_max(AnimationMath.component_value(value, "x"), AnimationMath.component_value(max_val, "x"), softness_factor),
                AnimationMath.soft_limit_max(AnimationMath.component_value(value, "y"), AnimationMath.component_value(max_val, "y"), softness_factor)
            )

        if kind == "size":
            return AnimationMath.construct_like(
                value,
                AnimationMath.soft_limit_max(AnimationMath.component_value(value, "width"),  AnimationMath.component_value(max_val, "width"), softness_factor),
                AnimationMath.soft_limit_max(AnimationMath.component_value(value, "height"), AnimationMath.component_value(max_val, "height"), softness_factor)
            )

        if kind == "rect":
            return AnimationMath.construct_like(
                value,
                AnimationMath.soft_limit_max(AnimationMath.component_value(value, "x"),      AnimationMath.component_value(max_val, "x"), softness_factor),
                AnimationMath.soft_limit_max(AnimationMath.component_value(value, "y"),      AnimationMath.component_value(max_val, "y"), softness_factor),
                AnimationMath.soft_limit_max(AnimationMath.component_value(value, "width"),  AnimationMath.component_value(max_val, "width"), softness_factor),
                AnimationMath.soft_limit_max(AnimationMath.component_value(value, "height"), AnimationMath.component_value(max_val, "height"), softness_factor)
            )

        if kind == "color":
            return AnimationMath.construct_like(
                value,
                int(AnimationMath.soft_limit_max(AnimationMath.component_value(value, "red"),   AnimationMath.component_value(max_val, "red"), softness_factor)),
                int(AnimationMath.soft_limit_max(AnimationMath.component_value(value, "green"), AnimationMath.component_value(max_val, "green"), softness_factor)),
                int(AnimationMath.soft_limit_max(AnimationMath.component_value(value, "blue"),  AnimationMath.component_value(max_val, "blue"), softness_factor)),
                int(AnimationMath.soft_limit_max(AnimationMath.component_value(value, "alpha"), AnimationMath.component_value(max_val, "alpha"), softness_factor))
            )

        return value

# Animation Clip

class AnimationClip:
    __slots__ = (
        "scheduler", "mode", "moments", "delay_ms", "easing", "tag", "loop",
        "elapsed_ms", "is_finished", "finished_callback", "updated", "duration_ms"
    )

    def __init__(
            self,
            scheduler:              Callable[[Callable[[], object]], None],
            moments:                list[tuple[float, object]],
            mode:                   PlaybackMode,
            duration_ms:            int | None                  = None,
            delay_ms:               int                         = 0,
            easing_function:        Callable[[float], float]    = Easing.linear,
            finished_callback:      Callable[[], object] | None = None,
            loop:                   bool                        = False,
            tag:                    str | None                  = None
        ) -> None:

        self.scheduler             = scheduler
        self.mode                  = mode
        self.moments               = self.prepare_moments(moments, mode)
        self.delay_ms              = delay_ms
        self.easing                = easing_function
        self.tag                   = tag
        self.loop                  = loop
        self.elapsed_ms            = 0
        self.is_finished           = False
        self.finished_callback     = finished_callback
        self.updated               = EventSignal()

        self.duration_ms = duration_ms if duration_ms is not None else self.infer_duration_ms(mode)

    def prepare_moments(
            self,
            moments: list[tuple[float, object]],
            mode:    PlaybackMode
        ) -> list[tuple[float, object]]:

        if mode == PlaybackMode.STEP:
            return list(moments)

        return sorted(moments, key = lambda moment: moment[0])

    def infer_duration_ms(self, mode: PlaybackMode) -> int:
        if mode == PlaybackMode.TIMELINE and self.moments:
            return int(self.moments[-1][0])

        if mode == PlaybackMode.STEP:
            return int(sum(hold for hold, _ in self.moments))

        return 0

    def total_duration_ms(self) -> int:
        return self.delay_ms + self.duration_ms

    def update(self, delta_ms: int) -> None:
        self.elapsed_ms += delta_ms
        self.updated.emit()

        total = self.total_duration_ms()

        if self.elapsed_ms < total:
            return

        if self.loop:
            self.elapsed_ms %= total if total > 0 else 1
            return

        self.elapsed_ms = total
        self.is_finished          = True

        if self.finished_callback is None:
            return

        callback               = self.finished_callback
        self.finished_callback = None
        self.scheduler(callback)

    def value(self) -> object:
        if not self.moments:
            return 0

        if self.elapsed_ms < self.delay_ms:
            return self.first_value()

        if self.mode == PlaybackMode.STEP:
            return self.value_for_step()

        if self.mode == PlaybackMode.TIMELINE:
            return self.value_for_timeline()

        return self.value_for_curve()

    def first_value(self) -> object:
        if self.mode == PlaybackMode.STEP:
            return self.moments[0][1]

        return self.moments[0][1]

    def value_for_step(self) -> object:
        remaining = self.elapsed_ms - self.delay_ms

        for hold_ms, step_value in self.moments:
            if remaining < hold_ms:
                return step_value

            remaining -= hold_ms

        return self.moments[-1][1]

    def value_for_timeline(self) -> object:
        if len(self.moments) == 1:
            return self.moments[0][1]

        position = self.elapsed_ms - self.delay_ms

        if position <= self.moments[0][0]:
            return self.moments[0][1]

        if position >= self.moments[-1][0]:
            return self.moments[-1][1]

        for index in range(len(self.moments) - 1):
            left, right = self.moments[index], self.moments[index + 1]

            if not (left[0] <= position <= right[0]):
                continue

            segment_duration = right[0] - left[0]

            if segment_duration == 0:
                return right[1]

            local_progress = self.easing((position - left[0]) / segment_duration)

            return AnimationMath.interpolate(left[1], right[1], local_progress)

        return self.moments[-1][1]

    def value_for_curve(self) -> object:
        if len(self.moments) == 1:
            return self.moments[0][1]

        progress       = (self.elapsed_ms - self.delay_ms) / self.duration_ms if self.duration_ms > 0 else 1.0
        eased_progress = self.easing(progress)

        clamped_low  = self.moments[0]
        clamped_high = self.moments[-1]

        if eased_progress <= clamped_low[0]:
            return self.interpolate_between(self.moments[0], self.moments[1], eased_progress)

        if eased_progress >= clamped_high[0]:
            return self.interpolate_between(self.moments[-2], self.moments[-1], eased_progress)

        for index in range(len(self.moments) - 1):
            left, right = self.moments[index], self.moments[index + 1]

            if left[0] <= eased_progress <= right[0]:
                return self.interpolate_between(left, right, eased_progress)

        return self.moments[-1][1]

    def interpolate_between(
            self,
            left:            tuple[float, object],
            right:           tuple[float, object],
            eased_progress:  float
        ) -> object:

        segment_duration = right[0] - left[0]

        if segment_duration == 0:
            return right[1]

        local_progress = (eased_progress - left[0]) / segment_duration

        return AnimationMath.interpolate(left[1], right[1], local_progress)

# Property Track

class PropertyTrack:
    __slots__ = (
        "scheduler", "mix_mode", "backend", "clips", "smoothing_enabled",
        "smoothing_factor", "max_value", "soft_limit_factor", "base_value",
        "cached_value", "target_value", "is_targeting", "target_start_value",
        "target_end_value", "target_duration_ms", "target_elapsed_ms",
        "target_easing", "updated", "interpolator"
    )

    def __init__(
            self,
            scheduler:           Callable[[Callable[[], object]], None],
            base_value:          object,
            mix_mode:            MixMode,
            backend:             RuntimeBackend | None = None,
            smoothing_enabled:   bool                  = False,
            smoothing_factor:    float                 = 0.1,
            max_value:           object | None         = None,
            soft_limit_factor:   float                 = 0.8
        ) -> None:

        self.scheduler = scheduler
        self.mix_mode  = mix_mode
        self.backend   = backend

        self.clips = []

        self.smoothing_enabled = smoothing_enabled
        self.smoothing_factor  = smoothing_factor

        self.max_value         = max_value
        self.soft_limit_factor = soft_limit_factor

        self.base_value   = base_value
        self.cached_value = base_value
        self.target_value = base_value

        self.is_targeting = False

        self.target_start_value  = base_value
        self.target_end_value    = base_value

        self.target_duration_ms = 0
        self.target_elapsed_ms  = 0
        self.target_easing      = Easing.linear

        self.updated = EventSignal()

        logger.debug(f"Choosing interpolator for {scheduler}, {base_value}")
        self.interpolator = self.choose_interpolator(base_value)

    def choose_interpolator(self, value: object) -> Callable[[object, object, float], object]:
        qt     = self.backend if (self.backend and self.backend.is_qt) else None
        v_type = type(value)

        integer_points = (qt.qt_point_type,) if qt else ()
        float_points   = (Point, qt.qt_pointf_type) if qt else (Point,)

        integer_sizes = (qt.qt_size_type,) if qt else ()
        float_sizes   = (Size, qt.qt_sizef_type) if qt else (Size,)

        integer_rects = (qt.qt_rect_type,) if qt else ()
        float_rects   = (Rect, qt.qt_rectf_type) if qt else (Rect,)

        color_types = (Color, qt.qt_color_type) if qt else (Color,)

        is_integer_target = isinstance(value, (int, *integer_points, *integer_sizes, *integer_rects, *color_types))

        cast = (lambda number: int(round(number))) if is_integer_target else (lambda number: number)

        if isinstance(value, (int, float)):
            return lambda start, end, progress: cast(AnimationMath.lerp_scalar(start, end, progress))

        if isinstance(value, integer_points + float_points):
            return lambda start, end, progress: v_type(
                cast(AnimationMath.lerp_scalar(start.x(), end.x(), progress)),
                cast(AnimationMath.lerp_scalar(start.y(), end.y(), progress))
            )

        if isinstance(value, integer_sizes + float_sizes):
            return lambda start, end, progress: v_type(
                cast(AnimationMath.lerp_scalar(start.width(),  end.width(),  progress)),
                cast(AnimationMath.lerp_scalar(start.height(), end.height(), progress))
            )

        if isinstance(value, integer_rects + float_rects):
            return lambda start, end, progress: v_type(
                cast(AnimationMath.lerp_scalar(start.x(),      end.x(),      progress)),
                cast(AnimationMath.lerp_scalar(start.y(),      end.y(),      progress)),
                cast(AnimationMath.lerp_scalar(start.width(),  end.width(),  progress)),
                cast(AnimationMath.lerp_scalar(start.height(), end.height(), progress))
            )

        if isinstance(value, color_types):
            return lambda start, end, progress: v_type(
                int(AnimationMath.lerp_scalar(start.red(),   end.red(),   progress)),
                int(AnimationMath.lerp_scalar(start.green(), end.green(), progress)),
                int(AnimationMath.lerp_scalar(start.blue(),  end.blue(),  progress)),
                int(AnimationMath.lerp_scalar(start.alpha(), end.alpha(), progress))
            )

        if isinstance(value, tuple):
            interpolators = [self.choose_interpolator(item) for item in value]
            return lambda start, end, progress: tuple(
                interp(s, e, progress) for interp, s, e in zip(interpolators, start, end)
            )
            
        if isinstance(value, list):
            interpolators = [self.choose_interpolator(item) for item in value]
            return lambda start, end, progress: [
                interp(s, e, progress) for interp, s, e in zip(interpolators, start, end)
            ]
            
        if isinstance(value, (str, bool, type(None))):
            return lambda start, end, progress: start if progress < 0.5 else end

        logger.error(f"{v_type} is an unsupported type for animations.")

        return lambda start, end, progress: start

    def set_max_value(
            self,
            max_value:         object | None,
            soft_limit_factor: float | None = None
        ) -> None:

        self.max_value = max_value

        if soft_limit_factor is not None:
            self.soft_limit_factor = soft_limit_factor

        self.updated.emit(self.cached_value)

    def set_base_value(self, value: object) -> None:
        self.is_targeting = False

        self.base_value   = value
        self.cached_value = value
        self.interpolator = self.choose_interpolator(value)

        self.clips.clear()

        self.updated.emit(self.cached_value)

    def set_target(
            self,
            value:                  object,
            duration_ms:            int,
            easing_function:        Callable[[float], float]
        ) -> None:

        self.target_start_value = self.cached_value
        self.target_end_value   = value
        self.target_duration_ms = duration_ms
        self.target_elapsed_ms  = 0
        self.target_easing      = easing_function
        self.is_targeting       = True

        if self.mix_mode == MixMode.REPLACE:
            self.clips.clear()

    def add_clip(
            self,
            clip:          AnimationClip,
            snap_to_start: bool = True
        ) -> None:

        if self.mix_mode == MixMode.REPLACE:
            self.clips.clear()

        self.clips.append(clip)

        if not (snap_to_start and clip.moments) or clip.delay_ms > 0:
            return

        first_value = clip.first_value()

        if self.mix_mode == MixMode.MULTIPLY:
            self.cached_value = AnimationMath.multiply(self.base_value, first_value)

        elif self.mix_mode == MixMode.ADD:
            self.cached_value = AnimationMath.add(self.base_value, first_value)

        elif self.mix_mode == MixMode.REPLACE:
            self.cached_value = first_value

        self.updated.emit(self.cached_value)

    def clear_clips(self, tag: str | None = None) -> None:
        if tag is None:
            self.clips.clear()
            self.updated.emit(self.cached_value)

            return

        remaining_clips = []
        contribution    = None
        found           = False

        for clip in self.clips:
            if clip.tag != tag:
                remaining_clips.append(clip)
                continue

            found = True
            value = clip.value()

            if contribution is None:
                contribution = value

            elif self.mix_mode == MixMode.ADD:
                contribution = AnimationMath.add(contribution, value)

            elif self.mix_mode == MixMode.MULTIPLY:
                contribution = AnimationMath.multiply(contribution, value)

        if not found:
            return

        if self.mix_mode == MixMode.ADD:
            self.base_value = AnimationMath.add(self.base_value, contribution)

        elif self.mix_mode == MixMode.MULTIPLY:
            self.base_value = AnimationMath.multiply(self.base_value, contribution)

        elif self.mix_mode == MixMode.REPLACE:
            self.base_value = contribution

        self.clips = remaining_clips

        self.updated.emit(self.cached_value)
    
    def stop_target(self) -> None:
        self.is_targeting       = False

        self.target_elapsed_ms  = 0
        self.target_start_value = self.cached_value
        self.target_end_value   = self.cached_value
        self.target_value       = self.cached_value

    def update(self, delta_ms: int) -> None:
        running_clips        = []
        any_clip_finished    = False
        target_just_finished = False

        for clip in self.clips:
            clip.update(delta_ms)

            if not clip.is_finished:
                running_clips.append(clip)
                continue

            any_clip_finished = True
            final_value        = clip.value()

            if self.mix_mode == MixMode.MULTIPLY:
                self.base_value = AnimationMath.multiply(self.base_value, final_value)

            elif self.mix_mode == MixMode.ADD:
                self.base_value = AnimationMath.add(self.base_value, final_value)

            elif self.mix_mode == MixMode.REPLACE:
                self.base_value = final_value

        self.clips = running_clips

        target = self.base_value

        if self.is_targeting:
            self.target_elapsed_ms += delta_ms

            progress       = min(1.0, self.target_elapsed_ms / self.target_duration_ms) if self.target_duration_ms > 0 else 1.0
            eased_progress = self.target_easing(progress)
            target         = self.interpolator(self.target_start_value, self.target_end_value, eased_progress)

            if progress >= 1.0:
                self.base_value      = self.target_end_value
                self.is_targeting    = False
                target_just_finished = True

        if self.mix_mode == MixMode.REPLACE:
            if self.clips:
                target = self.clips[-1].value()

        else:
            for clip in self.clips:
                if clip.elapsed_ms < clip.delay_ms:
                    continue

                value = clip.value()

                if self.mix_mode == MixMode.MULTIPLY:
                    target = AnimationMath.multiply(target, value)

                elif self.mix_mode == MixMode.ADD:
                    target = AnimationMath.add(target, value)

        self.target_value = target

        if self.max_value is not None:
            target = AnimationMath.soft_limit_max(target, self.max_value, self.soft_limit_factor)

        self.target_value = target

        if self.smoothing_enabled:
            actual_factor     = min(1.0, self.smoothing_factor * (delta_ms / 16.0))
            self.cached_value = self.interpolator(self.cached_value, self.target_value, actual_factor)

        else:
            self.cached_value = self.target_value

        should_notify = (
            AnimationMath.is_different(self.cached_value, self.target_value) or
            bool(self.clips) or
            self.is_targeting or
            any_clip_finished or
            target_just_finished
        )

        if should_notify:
            self.updated.emit(self.cached_value)

# Property Namespacing

class PropertyNamespace:
    def __init__(self) -> None:
        self.identifiers_by_owner: WeakKeyDictionary = WeakKeyDictionary()
        self.identifier_source                        = count(1)

    def key_for(self, owner: object, name: str) -> str:
        if owner not in self.identifiers_by_owner:
            self.identifiers_by_owner[owner] = next(self.identifier_source)

        return f"{self.identifiers_by_owner[owner]}:{name}"

# Property Handle

class PropertyHandle:
    __slots__ = ("engine", "key")

    def __init__(
            self,
            engine: AnimationEngine,
            key:    str
        ) -> None:

        self.engine = engine
        self.key    = key

    @property
    def value(self) -> object:
        return self.engine.property_value(self.key)

    def set_base(self, value: object) -> None:
        self.engine.set_property_base_value(self.key, value)

    def set_max_value(
            self,
            max_value:         object | None,
            soft_limit_factor: float | None = None
        ) -> None:

        self.engine.set_property_max_value(self.key, max_value, soft_limit_factor)

    def set_target(
            self,
            value:                      object,
            duration_ms:                int                      = 500,
            easing_function:            Callable[[float], float] = Easing.smooth,
            multiply_duration_by_speed: bool                     = True
        ) -> None:

        self.engine.set_target_value(
            key                        = self.key,
            value                      = value,
            duration_ms                = duration_ms,
            easing_function            = easing_function,
            multiply_duration_by_speed = multiply_duration_by_speed
        )

    def play_curve(
            self,
            keyframes:                     list[tuple[float, object]],
            duration_ms:                   int,
            easing_function:               Callable[[float], float]    = Easing.linear,
            finished:                      Callable[[], object] | None = None,
            multiply_duration_by_speed:    bool                        = True,
            snap_to_start:                 bool                        = False,
            loop:                          bool                        = False,
            tag:                           str | None                  = None,
            delay_ms:                      int                         = 0
        ) -> None:

        self.engine.play(
            key                         = self.key,
            moments                     = keyframes,
            mode                        = PlaybackMode.CURVE,
            duration_ms                 = duration_ms,
            easing_function             = easing_function,
            finished                    = finished,
            multiply_duration_by_speed  = multiply_duration_by_speed,
            snap_to_start               = snap_to_start,
            loop                        = loop,
            tag                         = tag,
            delay_ms                    = delay_ms
        )

    def play_timeline(
            self,
            moments:                        list[tuple[int, object]],
            easing_function:                Callable[[float], float]    = Easing.linear,
            finished:                       Callable[[], object] | None = None,
            multiply_duration_by_speed:     bool                        = True,
            snap_to_start:                  bool                        = False,
            loop:                           bool                        = False,
            tag:                            str | None                  = None,
            delay_ms:                       int                         = 0
        ) -> None:

        self.engine.play(
            key                         = self.key,
            moments                     = moments,
            mode                        = PlaybackMode.TIMELINE,
            duration_ms                 = None,
            easing_function             = easing_function,
            finished                    = finished,
            multiply_duration_by_speed  = multiply_duration_by_speed,
            snap_to_start               = snap_to_start,
            loop                        = loop,
            tag                         = tag,
            delay_ms                    = delay_ms
        )

    def play_steps(
            self,
            steps:                          list[tuple[int, object]],
            finished:                       Callable[[], object] | None = None,
            multiply_duration_by_speed:     bool                        = False,
            loop:                           bool                        = False,
            tag:                            str | None                  = None,
            delay_ms:                       int                         = 0
        ) -> None:

        self.engine.play(
            key                         = self.key,
            moments                     = steps,
            mode                        = PlaybackMode.STEP,
            duration_ms                 = None,
            easing_function             = Easing.linear,
            finished                    = finished,
            multiply_duration_by_speed  = multiply_duration_by_speed,
            snap_to_start               = True,
            loop                        = loop,
            tag                         = tag,
            delay_ms                    = delay_ms
        )

    def stop(self, tag: str | None = None) -> None:
        self.engine.stop_property(self.key, tag)
    
    def stop_targeting(self) -> None:
        self.engine.stop_property_targeting(self.key)

    def release(self) -> None:
        self.engine.forget_property(self.key)

# Engine

class AnimationEngine:
    def __init__(
            self,
            backend_name:      str | None = None,
            frames_per_second: int        = 120
        ) -> None:

        self.backend     = RuntimeBackend(backend_name)
        self.namespace   = PropertyNamespace()

        self.tracks: dict[str, PropertyTrack] = {}

        self.stopwatch         = self.backend.create_stopwatch()
        self.last_tick_ms      = 0
        self.frames_per_second = frames_per_second
        self.interval_ms       = max(1, 1000 // max(1, frames_per_second))
        self.ticker            = None
        self.running           = False
        self.active_users      = 0
        self.updated           = EventSignal()

    def ensure_ticker(self) -> None:
        if self.ticker is not None:
            return

        self.ticker = self.backend.create_ticker(
            callback    = self.tick,
            interval_ms = self.interval_ms
        )

    def set_frames_per_second(self, frames_per_second: int) -> None:
        self.frames_per_second = frames_per_second
        self.interval_ms = max(1, 1000 // max(1, frames_per_second))

        if self.ticker is not None:
            self.ticker.set_interval_ms(self.interval_ms)

    def start(self) -> None:
        if self.running:
            return

        if self.backend.is_qt and not self.backend.qt_application_running():
            logger.debug("Qt application is not ready yet. Engine start is delayed.")
            return

        self.ensure_ticker()

        if self.ticker is None:
            logger.debug("Ticker was not created.")
            return

        self.stopwatch.start()
        self.last_tick_ms = 0
        self.ticker.start()
        self.running = True

    def pause(self) -> None:
        if not self.running:
            return

        logger.debug("Animation engine paused: no widgets are currently using it.")
        self.ticker.stop()
        self.running = False

    def resume(self) -> None:
        if self.running:
            return

        if self.backend.is_qt and not self.backend.qt_application_running():
            logger.warning("Qt application is not ready yet. Engine resume is delayed.")
            return

        self.ensure_ticker()

        if self.ticker is None:
            return

        self.last_tick_ms = self.stopwatch.elapsed()
        self.ticker.start()
        self.running = True

    def acquire(self) -> None:
        self.active_users += 1

        if self.active_users == 1:
            self.resume()

    def release(self) -> None:
        self.active_users = max(0, self.active_users - 1)

        if self.active_users == 0:
            self.pause()

    def unbind_owner(self, owner: object) -> None:
        owner_id = self.namespace.identifiers_by_owner.get(owner)
        
        if owner_id is None:
            return

        prefix = f"{owner_id}:"

        keys_to_delete = [key for key in self.tracks if key.startswith(prefix)]

        for key in keys_to_delete:
            logger.warning(f"Deleted {key} property")
            del self.tracks[key]

    def bind(
            self,
            owner:              object,
            name:               str,
            base_value:         object,
            mix_mode:           MixMode                           = MixMode.REPLACE,
            on_change:          Callable[[object], object] | None = None,
            smoothing_enabled:  bool                              = False,
            smoothing_factor:   float                             = 0.1,
            max_value:          object | None                     = None,
            soft_limit_factor:  float                             = 0.8
        ) -> PropertyHandle:

        key = self.namespace.key_for(owner, name)

        if key not in self.tracks:
            logger.debug(f"Binding {name} for {owner.__class__}")
            self.tracks[key] = PropertyTrack(
                scheduler         = self.backend.defer,
                base_value        = base_value,
                mix_mode          = mix_mode,
                backend           = self.backend,
                smoothing_enabled = smoothing_enabled,
                smoothing_factor  = smoothing_factor,
                max_value         = max_value,
                soft_limit_factor = soft_limit_factor
            )

        if on_change is not None:
            self.tracks[key].updated.connect(on_change)

        return PropertyHandle(self, key)

    def property_value(self, key: str) -> object:
        if key not in self.tracks:
            logger.error(f"Property {key} not found.")
            return None

        return self.tracks[key].cached_value

    def set_property_base_value(
            self,
            key:   str,
            value: object
        ) -> None:

        if key not in self.tracks:
            logger.error(f"Property {key} not found.")
            return

        self.tracks[key].set_base_value(value)

    def set_property_max_value(
            self,
            key:               str,
            max_value:         object | None,
            soft_limit_factor: float | None = None
        ) -> None:

        if key not in self.tracks:
            logger.error(f"Property {key} not found.")
            return

        self.tracks[key].set_max_value(max_value, soft_limit_factor)

    def set_target_value(
            self,
            key:                           str,
            value:                         object,
            duration_ms:                   int                      = 500,
            easing_function:               Callable[[float], float] = Easing.smooth,
            multiply_duration_by_speed:    bool                     = True
        ) -> None:

        if key not in self.tracks:
            logger.error(f"Property {key} not found.")
            return
        
        multiplier = Constants.current_settings.get("animation_multiplier", 1.0) if multiply_duration_by_speed else 1.0

        final_duration_ms = int(duration_ms * multiplier)
        self.tracks[key].set_target(value, final_duration_ms, easing_function)

    def play(
            self,
            key:                          str,
            moments:                      list[tuple[float, object]],
            mode:                         PlaybackMode,
            duration_ms:                  int | None,
            easing_function:              Callable[[float], float],
            finished:                     Callable[[], object] | None,
            multiply_duration_by_speed:   bool,
            snap_to_start:                bool,
            loop:                         bool,
            tag:                          str | None,
            delay_ms:                     int
        ) -> None:

        if key not in self.tracks:
            logger.error(f"Property {key} not found.")
            return

        should_multiply = multiply_duration_by_speed

        final_duration_ms = duration_ms
        final_delay_ms    = delay_ms

        if should_multiply:
            if final_duration_ms is not None:
                final_duration_ms = int(final_duration_ms * Constants.current_settings.get("animation_multiplier", 1.0))

            final_delay_ms = int(final_delay_ms * Constants.current_settings.get("animation_multiplier", 1.0))

        clip = AnimationClip(
            scheduler               = self.backend.defer,
            moments                 = moments,
            mode                    = mode,
            duration_ms             = final_duration_ms,
            delay_ms                = final_delay_ms,
            easing_function         = easing_function,
            finished_callback       = finished,
            loop                    = loop,
            tag                     = tag
        )

        self.tracks[key].add_clip(clip, snap_to_start)

    def stop_property(
            self,
            key: str,
            tag: str | None = None
        ) -> None:

        if key not in self.tracks:
            logger.error(f"Property {key} not found.")
            return

        self.tracks[key].clear_clips(tag)
    
    def stop_property_targeting(self, key: str) -> None:
        self.tracks[key].stop_target()

    def forget_property(self, key: str) -> None:
        if key not in self.tracks:
            return

        del self.tracks[key]

    def stop_all(self) -> None:
        for track in self.tracks.values():
            track.clear_clips()

    def tick(self) -> None:
        current_ms        = self.stopwatch.elapsed()
        delta_ms          = current_ms - self.last_tick_ms
        self.last_tick_ms = current_ms

        if delta_ms > 100:
            delta_ms = 16

        for track in list(self.tracks.values()):
            track.update(delta_ms)

        self.updated.emit()

    def clear(self) -> None:
        logger.debug("Clearing animation engine.")

        if self.ticker is not None:
            self.ticker.stop()

        self.running    = False
        self.ticker     = None
        self.active_users = 0

        self.tracks.clear()

# Singleton Access

ui_engine = AnimationEngine("pyqt6")