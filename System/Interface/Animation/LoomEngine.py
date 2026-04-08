from __future__ import annotations

import math
import time
import threading

from enum import Enum

from loguru import logger

from collections.abc import (
    Callable,
    Iterable
)

# Signals

class EventSignal:
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

        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def emit(self, *arguments: object, **keywords: object) -> None:
        for callback in list(self.callbacks):
            try:
                callback(*arguments, **keywords)

            except Exception as exception:
                logger.error(f"Signal callback failed: {exception}")


# Geometry

class Point:
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


# Backend

class PureElapsedTimer:
    def __init__(self) -> None:
        self.started_at = time.perf_counter()

    def start(self) -> None:
        self.started_at = time.perf_counter()

    def elapsed(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)


class QtTimerHandle:
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

    def set_interval(self, interval_ms: int) -> None:
        self.timer.setInterval(interval_ms)


class PureTimerHandle:
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
                logger.error(f"Timer callback failed: {exception}")

            remaining = next_tick - time.perf_counter()

            if remaining > 0:
                self.stop_event.wait(remaining)

        self.running = False

    def start(self) -> None:
        if self.running:
            return

        self.stop_event.clear()
        self.thread  = threading.Thread(target=self.run, daemon=True)
        self.running = True
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

        if self.thread is None:
            return

        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=1.0)

        self.running = False

    def set_interval(self, interval_ms: int) -> None:
        self.interval_ms = interval_ms


class BackendAdapter:
    def __init__(self, backend: str | None) -> None:
        self.name                 = (backend or "pure").lower()
        self.is_pure              = self.name in {"pure", "none"}
        self.is_qt                = self.name in {"pyqt5", "pyqt6", "pyside2", "pyside6"}
        
        self.qt_timer_type        = None
        self.qt_single_shot       = None
        self.qt_elapsed_timer     = None
        self.qt_application_type  = None
        
        self.qt_point_type        = None
        self.qt_rect_type         = None
        self.qt_size_type         = None
        self.qt_color_type        = None
        self.qt_pointf_type       = None
        self.qt_rectf_type        = None
        self.qt_sizef_type        = None

        if self.is_qt:
            self.load_qt_backend()

    def load_qt_backend(self) -> None:
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

        self.qt_timer_type        = QTimer
        self.qt_single_shot       = QTimer.singleShot
        self.qt_elapsed_timer     = QElapsedTimer
        self.qt_application_type  = QCoreApplication
        
        self.qt_point_type        = QPoint
        self.qt_rect_type         = QRect
        self.qt_size_type         = QSize
        self.qt_color_type        = QColor
        self.qt_pointf_type       = QPointF
        self.qt_rectf_type        = QRectF
        self.qt_sizef_type        = QSizeF

    def has_qt_application(self) -> bool:
        if not self.is_qt:
            return False

        return self.qt_application_type.instance() is not None

    def create_elapsed_timer(self) -> object:
        if self.is_qt:
            timer = self.qt_elapsed_timer()
            timer.start()
            return timer

        return PureElapsedTimer()

    def create_timer(
            self,
            callback:    Callable[[], object],
            interval_ms: int
        ) -> object:

        if self.is_qt:
            if not self.has_qt_application():
                return None

            return QtTimerHandle(
                callback    = callback,
                interval_ms = interval_ms,
                timer_type  = self.qt_timer_type
            )

        return PureTimerHandle(
            callback    = callback,
            interval_ms = interval_ms
        )

    def schedule_callback(self, callback: Callable[[], object]) -> None:
        if self.is_qt and self.has_qt_application():
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
        s         = period / (2 * math.pi) * math.asin(1.0 / amplitude)

        return amplitude * math.pow(2, -10 * t) * math.sin((t - s) * (2 * math.pi) / period) + 1.0

    @staticmethod
    def very_bouncy(t: float) -> float:
        if t == 0:
            return 0.0

        if t == 1:
            return 1.0

        period = 0.35
        s      = period / 4

        return math.pow(2, -7 * t) * math.sin((t - s) * (2 * math.pi) / period) + 1

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
        c1 = 1.70158
        c3 = c1 + 1

        return c3 * t * t * t - c1 * t * t

    @staticmethod
    def ease_out_back(t: float) -> float:
        c1 = 2.0
        c3 = c1 + 1

        return 1 + c3 * math.pow(t - 1, 3) + c1 * math.pow(t - 1, 2)

    @staticmethod
    def ease_in_out_back(t: float) -> float:
        c1 = 1.70158
        c2 = c1 * 1.525

        if t < 0.5:
            return (math.pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2

        return (math.pow(2 * t - 2, 2) * ((c2 + 1) * (2 * t - 2) + c2) + 2) / 2

    @staticmethod
    def ease_out_elastic(t: float) -> float:
        if t == 0:
            return 0.0

        if t == 1:
            return 1.0

        c4 = (2 * math.pi) / 3

        return math.pow(2, -10 * t) * math.sin((t * 10 - 0.75) * c4) + 1

    @staticmethod
    def ease_out_bounce(t: float) -> float:
        n1 = 7.5625
        d1 = 2.75

        if t < 1 / d1:
            return n1 * t * t

        if t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75

        if t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375

        t -= 2.625 / d1

        return n1 * t * t + 0.984375

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
        if t == 0:
            return 0.0

        return math.pow(2, 10 * (t - 1))

    @staticmethod
    def ease_out_expo(t: float) -> float:
        if t == 1:
            return 1.0

        return 1 - math.pow(2, -10 * t)

    @staticmethod
    def ease_in_out_expo(t: float) -> float:
        if t == 0:
            return 0.0

        if t == 1:
            return 1.0

        if t < 0.5:
            return math.pow(2, 20 * t - 10) / 2

        return (2 - math.pow(2, -20 * t + 10)) / 2


# Mix Modes

class MixMode(Enum):
    ADD      = 0
    MULTIPLY = 1
    NOMIX    = 2


# Animation Math

class AnimMath:
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
            and not AnimMath.is_rect_like(value)
        )

    @staticmethod
    def is_point_like(value: object) -> bool:
        return (
            all(hasattr(value, attribute) for attribute in ("x", "y"))
            and not AnimMath.is_rect_like(value)
        )

    @staticmethod
    def component_value(value: object, name: str) -> float:
        component = getattr(value, name)

        if callable(component):
            return component()

        return component

    @staticmethod
    def construct_like(value: object, *arguments: object) -> object:
        try:
            return type(value)(*arguments)

        except (TypeError, ValueError):
            return type(value)(*[int(argument) for argument in arguments])

    @staticmethod
    def lerp(
            a: object,
            b: object,
            t: float
        ) -> object:

        if AnimMath.is_number(a):
            return a + (b - a) * t

        if AnimMath.is_point_like(a):
            x = AnimMath.component_value(a, "x") + (AnimMath.component_value(b, "x") - AnimMath.component_value(a, "x")) * t
            y = AnimMath.component_value(a, "y") + (AnimMath.component_value(b, "y") - AnimMath.component_value(a, "y")) * t

            return AnimMath.construct_like(a, x, y)

        if AnimMath.is_size_like(a):
            width  = AnimMath.component_value(a, "width")  + (AnimMath.component_value(b, "width")  - AnimMath.component_value(a, "width"))  * t
            height = AnimMath.component_value(a, "height") + (AnimMath.component_value(b, "height") - AnimMath.component_value(a, "height")) * t

            return AnimMath.construct_like(a, width, height)

        if AnimMath.is_rect_like(a):
            x      = AnimMath.component_value(a, "x")      + (AnimMath.component_value(b, "x")      - AnimMath.component_value(a, "x"))      * t
            y      = AnimMath.component_value(a, "y")      + (AnimMath.component_value(b, "y")      - AnimMath.component_value(a, "y"))      * t
            width  = AnimMath.component_value(a, "width")  + (AnimMath.component_value(b, "width")  - AnimMath.component_value(a, "width"))  * t
            height = AnimMath.component_value(a, "height") + (AnimMath.component_value(b, "height") - AnimMath.component_value(a, "height")) * t

            return AnimMath.construct_like(a, x, y, width, height)

        if AnimMath.is_color_like(a):
            red   = int(AnimMath.component_value(a, "red")   + (AnimMath.component_value(b, "red")   - AnimMath.component_value(a, "red"))   * t)
            green = int(AnimMath.component_value(a, "green") + (AnimMath.component_value(b, "green") - AnimMath.component_value(a, "green")) * t)
            blue  = int(AnimMath.component_value(a, "blue")  + (AnimMath.component_value(b, "blue")  - AnimMath.component_value(a, "blue"))  * t)
            alpha = int(AnimMath.component_value(a, "alpha") + (AnimMath.component_value(b, "alpha") - AnimMath.component_value(a, "alpha")) * t)

            return AnimMath.construct_like(a, red, green, blue, alpha)

        return a

    @staticmethod
    def add(
            a: object,
            b: object
        ) -> object:

        if AnimMath.is_number(a):
            return a + b

        if AnimMath.is_point_like(a):
            return AnimMath.construct_like(
                a,
                AnimMath.component_value(a, "x") + AnimMath.component_value(b, "x"),
                AnimMath.component_value(a, "y") + AnimMath.component_value(b, "y")
            )

        if AnimMath.is_size_like(a):
            return AnimMath.construct_like(
                a,
                AnimMath.component_value(a, "width")  + AnimMath.component_value(b, "width"),
                AnimMath.component_value(a, "height") + AnimMath.component_value(b, "height")
            )

        if AnimMath.is_rect_like(a):
            return AnimMath.construct_like(
                a,
                AnimMath.component_value(a, "x")      + AnimMath.component_value(b, "x"),
                AnimMath.component_value(a, "y")      + AnimMath.component_value(b, "y"),
                AnimMath.component_value(a, "width")  + AnimMath.component_value(b, "width"),
                AnimMath.component_value(a, "height") + AnimMath.component_value(b, "height")
            )

        if AnimMath.is_color_like(a):
            return AnimMath.construct_like(
                a,
                min(255, int(AnimMath.component_value(a, "red")   + AnimMath.component_value(b, "red"))),
                min(255, int(AnimMath.component_value(a, "green") + AnimMath.component_value(b, "green"))),
                min(255, int(AnimMath.component_value(a, "blue")  + AnimMath.component_value(b, "blue"))),
                min(255, int(AnimMath.component_value(a, "alpha") + AnimMath.component_value(b, "alpha")))
            )

        return b

    @staticmethod
    def mul(
            a: object,
            b: object
        ) -> object:

        if AnimMath.is_number(a):
            return a * b

        if AnimMath.is_point_like(a):
            return AnimMath.construct_like(
                a,
                AnimMath.component_value(a, "x") * AnimMath.component_value(b, "x"),
                AnimMath.component_value(a, "y") * AnimMath.component_value(b, "y")
            )

        if AnimMath.is_size_like(a):
            return AnimMath.construct_like(
                a,
                AnimMath.component_value(a, "width")  * AnimMath.component_value(b, "width"),
                AnimMath.component_value(a, "height") * AnimMath.component_value(b, "height")
            )

        if AnimMath.is_rect_like(a):
            return AnimMath.construct_like(
                a,
                AnimMath.component_value(a, "x")      * AnimMath.component_value(b, "x"),
                AnimMath.component_value(a, "y")      * AnimMath.component_value(b, "y"),
                AnimMath.component_value(a, "width")  * AnimMath.component_value(b, "width"),
                AnimMath.component_value(a, "height") * AnimMath.component_value(b, "height")
            )

        if AnimMath.is_color_like(a):
            return AnimMath.construct_like(
                a,
                int(AnimMath.component_value(a, "red")   * AnimMath.component_value(b, "red")   / 255),
                int(AnimMath.component_value(a, "green") * AnimMath.component_value(b, "green") / 255),
                int(AnimMath.component_value(a, "blue")  * AnimMath.component_value(b, "blue")  / 255),
                int(AnimMath.component_value(a, "alpha") * AnimMath.component_value(b, "alpha") / 255)
            )

        return b

    @staticmethod
    def is_diff(
            a:         object,
            b:         object,
            tolerance: float = 0.0001
        ) -> bool:

        if type(a) != type(b):
            return True

        if AnimMath.is_number(a):
            return abs(a - b) > tolerance

        if AnimMath.is_point_like(a):
            return (
                abs(AnimMath.component_value(a, "x") - AnimMath.component_value(b, "x")) > tolerance or
                abs(AnimMath.component_value(a, "y") - AnimMath.component_value(b, "y")) > tolerance
            )

        if AnimMath.is_size_like(a):
            return (
                abs(AnimMath.component_value(a, "width")  - AnimMath.component_value(b, "width"))  > tolerance or
                abs(AnimMath.component_value(a, "height") - AnimMath.component_value(b, "height")) > tolerance
            )

        if AnimMath.is_rect_like(a):
            return (
                abs(AnimMath.component_value(a, "x")      - AnimMath.component_value(b, "x"))      > tolerance or
                abs(AnimMath.component_value(a, "y")      - AnimMath.component_value(b, "y"))      > tolerance or
                abs(AnimMath.component_value(a, "width")  - AnimMath.component_value(b, "width"))  > tolerance or
                abs(AnimMath.component_value(a, "height") - AnimMath.component_value(b, "height")) > tolerance
            )

        if AnimMath.is_color_like(a):
            return (
                abs(AnimMath.component_value(a, "red")   - AnimMath.component_value(b, "red"))   > tolerance or
                abs(AnimMath.component_value(a, "green") - AnimMath.component_value(b, "green")) > tolerance or
                abs(AnimMath.component_value(a, "blue")  - AnimMath.component_value(b, "blue"))  > tolerance or
                abs(AnimMath.component_value(a, "alpha") - AnimMath.component_value(b, "alpha")) > tolerance
            )

        return a != b


# Animation

class AnimationInstance:
    def __init__(
            self,
            scheduler:         Callable[[Callable[[], object]], None],
            keyframes:         list[tuple[float, object]],
            duration_ms:       int,
            easing_function:   Callable[[float], float],
            finished_callback: Callable[[], object] | None = None
        ) -> None:

        self.scheduler         = scheduler
        self.keyframes         = sorted(keyframes, key=lambda item: item[0])
        self.duration          = duration_ms
        self.easing            = easing_function
        self.elapsed           = 0
        self.is_finished       = False
        self.finished_callback = finished_callback
        self.updated           = EventSignal()

    def update(self, delta_ms: int) -> None:
        self.elapsed += delta_ms
        self.updated.emit()

        if self.elapsed < self.duration:
            return

        self.elapsed     = self.duration
        self.is_finished = True

        if self.finished_callback is None:
            return

        callback               = self.finished_callback
        self.finished_callback = None
        self.scheduler(callback)

    def get_value(self) -> object:
        if not self.keyframes:
            return 0

        if len(self.keyframes) == 1:
            return self.keyframes[0][1]

        progress       = self.elapsed / self.duration if self.duration > 0 else 1.0
        eased_progress = self.easing(progress)

        if eased_progress <= self.keyframes[0][0]:
            left_frame  = self.keyframes[0]
            right_frame = self.keyframes[1]

            segment_duration = right_frame[0] - left_frame[0]

            if segment_duration == 0:
                return right_frame[1]

            local_progress = (eased_progress - left_frame[0]) / segment_duration

            return AnimMath.lerp(left_frame[1], right_frame[1], local_progress)

        if eased_progress >= self.keyframes[-1][0]:
            left_frame  = self.keyframes[-2]
            right_frame = self.keyframes[-1]

            segment_duration = right_frame[0] - left_frame[0]

            if segment_duration == 0:
                return right_frame[1]

            local_progress = (eased_progress - left_frame[0]) / segment_duration

            return AnimMath.lerp(left_frame[1], right_frame[1], local_progress)

        for index in range(len(self.keyframes) - 1):
            left_frame  = self.keyframes[index]
            right_frame = self.keyframes[index + 1]

            if not (left_frame[0] <= eased_progress <= right_frame[0]):
                continue

            segment_duration = right_frame[0] - left_frame[0]

            if segment_duration == 0:
                return right_frame[1]

            local_progress = (eased_progress - left_frame[0]) / segment_duration

            return AnimMath.lerp(left_frame[1], right_frame[1], local_progress)

        return self.keyframes[-1][1]


class PropertyNode:
    def __init__(
            self,
            scheduler:      Callable[[Callable[[], object]], None],
            base_value:     object,
            mode:           MixMode,
            backend:        BackendAdapter | None = None,
            damper_enabled: bool                  = False,
            lerp_factor:    float                 = 0.1
        ) -> None:

        self.scheduler      = scheduler
        self.mode           = mode
        self.backend        = backend
        
        self.animations     = []
        
        self.damper_enabled = damper_enabled
        self.lerp_factor    = lerp_factor
        
        self.base_value     = base_value
        self.cached_value   = base_value
        self.target_value   = base_value
        
        self.is_targeting   = False
        
        self.target_start    = base_value
        self.target_end      = base_value
        self.target_duration = 0
        self.target_elapsed  = 0
        self.target_easing   = Easing.linear
        
        self.updated        = EventSignal()

        self.lerp_func = self.choose_lerp_func(base_value)
    
    def choose_lerp_func(self, value: object):
        qt = self.backend if (self.backend and self.backend.is_qt) else None
        v_type = type(value)

        int_points   = (qt.qt_point_type,) if qt else ()
        float_points = (Point, qt.qt_pointf_type) if qt else (Point,)

        int_sizes   = (qt.qt_size_type,) if qt else ()
        float_sizes = (Size, qt.qt_sizef_type) if qt else (Size,)

        int_rects   = (qt.qt_rect_type,) if qt else ()
        float_rects = (Rect, qt.qt_rectf_type) if qt else (Rect,)

        color_types = (Color, qt.qt_color_type) if qt else (Color,)

        is_int_target = isinstance(value, (int, *int_points, *int_sizes, *int_rects, *color_types))
        
        cast = int if is_int_target else lambda x: x
        
        if isinstance(value, (int, float)):
            return lambda a, b, t: cast(a + (b - a) * t)

        if isinstance(value, int_points + float_points):
            return lambda a, b, t: v_type(
                cast(a.x() + (b.x() - a.x()) * t),
                cast(a.y() + (b.y() - a.y()) * t)
            )

        if isinstance(value, int_sizes + float_sizes):
            return lambda a, b, t: v_type(
                cast(a.width() + (b.width() - a.width()) * t),
                cast(a.height() + (b.height() - a.height()) * t)
            )

        if isinstance(value, int_rects + float_rects):
            return lambda a, b, t: v_type(
                cast(a.x() + (b.x() - a.x()) * t),
                cast(a.y() + (b.y() - a.y()) * t),
                cast(a.width() + (b.width() - a.width()) * t),
                cast(a.height() + (b.height() - a.height()) * t)
            )

        if isinstance(value, color_types):
            return lambda a, b, t: v_type(
                int(a.red() + (b.red() - a.red()) * t),
                int(a.green() + (b.green() - a.green()) * t),
                int(a.blue() + (b.blue() - a.blue()) * t),
                int(a.alpha() + (b.alpha() - a.alpha()) * t)
            )

        logger.error(f"{v_type} is an unsupported type for animations.")
        return lambda a, b, t: a

    def set_base_value(self, value: object) -> None:
        self.is_targeting = False
        self.base_value   = value
        self.cached_value = value
        self.lerp_func    = self.choose_lerp_func(value)

        self.animations.clear()

        self.updated.emit(self.cached_value)

    def set_target(
            self,
            value:           object,
            duration:        int,
            easing_function: Callable[[float], float]
        ) -> None:

        self.target_start    = self.cached_value
        self.target_end      = value
        self.target_duration = duration
        self.target_elapsed  = 0
        self.target_easing   = easing_function
        self.is_targeting    = True

        if self.mode == MixMode.NOMIX:
            self.animations.clear()

    def update(self, delta_ms: int) -> None:
        running_animations = []

        for animation in self.animations:
            animation.update(delta_ms)

            if not animation.is_finished:
                running_animations.append(animation)
                continue

            final_value = animation.get_value()

            if self.mode == MixMode.MULTIPLY:
                self.base_value = AnimMath.mul(self.base_value, final_value)

            elif self.mode == MixMode.ADD:
                self.base_value = AnimMath.add(self.base_value, final_value)

            elif self.mode == MixMode.NOMIX:
                self.base_value = final_value

        self.animations = running_animations

        target = self.base_value

        if self.is_targeting:
            self.target_elapsed += delta_ms
            progress       = min(1.0, self.target_elapsed / self.target_duration) if self.target_duration > 0 else 1.0
            eased_progress = self.target_easing(progress)
            target         = self.lerp_func(self.target_start, self.target_end, eased_progress)

            if progress >= 1.0:
                self.is_targeting = False
                self.base_value   = self.target_end

        if self.mode == MixMode.NOMIX:
            if self.animations:
                target = self.animations[-1].get_value()

        else:
            for animation in self.animations:
                value = animation.get_value()

                if self.mode == MixMode.MULTIPLY:
                    target = AnimMath.mul(target, value)

                elif self.mode == MixMode.ADD:
                    target = AnimMath.add(target, value)

        self.target_value = target

        if self.damper_enabled:
            actual_lerp       = min(1.0, self.lerp_factor * (delta_ms / 16.0))
            self.cached_value = self.lerp_func(self.cached_value, self.target_value, actual_lerp)
        
        else:
            self.cached_value = self.target_value

        should_update = (
            AnimMath.is_diff(self.cached_value, self.target_value) or
            bool(self.animations) or
            self.is_targeting
        )

        if should_update:
            self.updated.emit(self.cached_value)

    def add_animation(
            self,
            animation:     AnimationInstance,
            snap_to_start: bool = True
        ) -> None:

        if self.mode == MixMode.NOMIX:
            self.animations.clear()

        self.animations.append(animation)

        if not (snap_to_start and animation.keyframes):
            return

        first_value = animation.keyframes[0][1]

        if self.mode == MixMode.MULTIPLY:
            self.cached_value = AnimMath.mul(self.base_value, first_value)

        elif self.mode == MixMode.ADD:
            self.cached_value = AnimMath.add(self.base_value, first_value)

        elif self.mode == MixMode.NOMIX:
            self.cached_value = first_value

        self.updated.emit(self.cached_value)

    def value(self) -> object:
        return self.cached_value

    def clear_animations(self) -> None:
        self.animations.clear()
        self.cached_value = self.base_value

        self.updated.emit(self.cached_value)

class AnimationEngine:
    def __init__(
            self,
            backend: str | None = None,
            fps:     int        = 120
        ) -> None:

        self.backend             = BackendAdapter(backend)
        self.properties          = {}
        self.elapsed_timer       = self.backend.create_elapsed_timer()
        self.last_time           = 0
        self.duration_multiplier = 1.0
        self.fps                 = fps
        self.interval_ms         = max(1, 1000 // max(1, fps))
        self.timer_handle        = None
        self.running             = False
        self.updated             = EventSignal()

        if self.backend.is_pure or self.backend.has_qt_application():
            self.ensure_timer()
            self.start()

    def ensure_timer(self) -> None:
        if self.timer_handle is not None:
            return

        self.timer_handle = self.backend.create_timer(
            callback    = self.tick,
            interval_ms = self.interval_ms
        )

    def set_multiplier(self, value: float = 1.0) -> None:
        self.duration_multiplier = value

    def set_fps(self, fps: int) -> None:
        self.fps         = fps
        self.interval_ms = max(1, 1000 // max(1, fps))

        if self.timer_handle is not None:
            self.timer_handle.set_interval(self.interval_ms)

    def start(self) -> None:
        if self.running:
            return

        if self.backend.is_qt and not self.backend.has_qt_application():
            logger.debug("Qt application is not ready yet. Engine start is delayed.")
            return

        self.ensure_timer()

        if self.timer_handle is None:
            logger.debug("Timer was not created.")
            return

        self.elapsed_timer.start()
        self.last_time = 0
        self.timer_handle.start()
        self.running = True

    def pause(self) -> None:
        if not self.running:
            return

        logger.debug("Animation engine paused.")
        self.timer_handle.stop()
        self.running = False

    def resume(self) -> None:
        if self.running:
            return

        if self.backend.is_qt and not self.backend.has_qt_application():
            logger.warning("Qt application is not ready yet. Engine resume is delayed.")
            return

        self.ensure_timer()

        if self.timer_handle is None:
            return

        self.last_time = self.elapsed_timer.elapsed()
        self.timer_handle.start()
        self.running = True

    def set_property_base_value(
            self,
            name:  str,
            value: object
        ) -> None:
        
        if name not in self.properties:
            logger.error(f"Property {name} not found.")
            return

        self.properties[name].set_base_value(value)

    def set_target_value(
            self,
            name:            str,
            value:           object,
            duration:        int                      = 500,
            easing_function: Callable[[float], float] = Easing.smooth
        ) -> None:

        if name not in self.properties:
            logger.error(f"Property {name} not found.")
            return

        final_duration = int(duration * self.duration_multiplier)
        self.properties[name].set_target(value, final_duration, easing_function)

    def add_property(
            self,
            name:           str,
            base_value:     object,
            mode:           MixMode,
            on_update:      Callable[[], object] | None = None,
            damper_enabled: bool                        = False,
            lerp_factor:    float                       = 0.1
        ) -> None:

        node = PropertyNode(
            scheduler      = self.backend.schedule_callback,
            base_value     = base_value,
            mode           = mode,
            backend        = self.backend,
            damper_enabled = damper_enabled,
            lerp_factor    = lerp_factor
        )

        if on_update is not None:
            node.updated.connect(on_update)

        self.properties[name] = node

    def add_properties(self, properties: Iterable[tuple]) -> None:
        for property_item in properties:
            self.add_property(*property_item)

    def get_property_value(self, name: str) -> object:
        if name not in self.properties:
            logger.error(f"Property {name} not found.")
            return None

        return self.properties[name].value()

    def animate(
            self,
            name:                     str,
            keyframes:                list[tuple[float, object]],
            duration:                 int,
            easing_function:          Callable[[float], float]    = Easing.linear,
            finished:                 Callable[[], object] | None = None,
            do_not_multiply_duration: bool                        = False,
            snap_to_start:            bool                        = False
        ) -> None:

        if name not in self.properties:
            logger.error(f"Property {name} not found.")
            return

        final_duration = duration if do_not_multiply_duration else int(duration * self.duration_multiplier)

        animation = AnimationInstance(
            scheduler         = self.backend.schedule_callback,
            keyframes         = keyframes,
            duration_ms       = final_duration,
            easing_function   = easing_function,
            finished_callback = finished
        )

        self.properties[name].add_animation(animation, snap_to_start)

    def tick(self) -> None:
        current_time   = self.elapsed_timer.elapsed()
        delta_ms       = current_time - self.last_time
        self.last_time = current_time

        if delta_ms > 100:
            delta_ms = 16

        for property_node in list(self.properties.values()):
            property_node.update(delta_ms)

        self.updated.emit()

    def clear(self) -> None:
        logger.debug("Clearing animation engine.")

        if self.timer_handle is not None:
            self.timer_handle.stop()

        self.running      = False
        self.timer_handle = None

        self.properties.clear()