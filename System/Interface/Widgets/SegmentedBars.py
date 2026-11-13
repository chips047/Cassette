from __future__ import annotations

import math
import time
import bisect

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QRectF,
    QPointF,
    pyqtSignal,
    QElapsedTimer
)

from PyQt6.QtGui import (
    QColor,
    QPainter,
    QWheelEvent,
    QPaintEvent,
    QMouseEvent,
    QResizeEvent,
    QPainterPath
)

from PyQt6.QtWidgets import QWidget

from System.Common import (
    Dev,
    Styles,
    Constants
)

from System.Services import (
    Player,
    Haptics
)

from System.Interface import Timing

def evaluate_keyframes(
        keyframes:       list[tuple[float, float]],
        progress:        float,
        easing_function: object
    ) -> float:

    if progress <= keyframes[0][0]:
        return float(keyframes[0][1])

    if progress >= keyframes[-1][0]:
        return float(keyframes[-1][1])

    keyframe_times = [keyframe[0] for keyframe in keyframes]
    index          = bisect.bisect_right(keyframe_times, progress) - 1

    time_start, value_start = keyframes[index]
    time_end, value_end     = keyframes[index + 1]

    segment_duration = time_end - time_start

    if segment_duration <= 0.0:
        return float(value_end)

    local_progress = (progress - time_start) / segment_duration

    return float(value_start + (value_end - value_start) * easing_function(local_progress))

def blend_colors(
        first_color:     QColor,
        second_color:    QColor,
        progress_factor: float
    ) -> QColor:

    clamped_factor = max(0.0, min(1.0, float(progress_factor)))

    red_channel   = int(first_color.red()   + (second_color.red()   - first_color.red())   * clamped_factor)
    green_channel = int(first_color.green() + (second_color.green() - first_color.green()) * clamped_factor)
    blue_channel  = int(first_color.blue()  + (second_color.blue()  - first_color.blue())  * clamped_factor)
    alpha_channel = int(first_color.alpha() + (second_color.alpha() - first_color.alpha()) * clamped_factor)

    return QColor(red_channel, green_channel, blue_channel, alpha_channel)

class BaseSegmentedBar(QWidget):
    CORNER_RADIUS = 10.0

    def __init__(
            self,
            number_of_segments: int,
            base_thickness_px:  int
        ) -> None:

        super().__init__()

        self.amount_of_segments = max(1, number_of_segments)
        self.cached_paths       = []

        self.setFixedHeight(base_thickness_px)

    # Path Building

    def update_paths(self) -> None:
        amount    = self.amount_of_segments
        width_px  = self.width() / amount
        height_px = float(self.height())
        last      = amount - 1

        self.cached_paths = [
            self.build_segment_path(
                segment_index,
                width_px,
                height_px,
                last
            )
            for segment_index in range(amount)
        ]

    def build_segment_path(
            self,
            index:            int,
            segment_width_px: float,
            height_px:        float,
            last_index:       int
        ) -> QPainterPath:

        width_px  = segment_width_px if index == last_index else segment_width_px + 1
        rectangle = QRectF(index * segment_width_px, 0, width_px, height_px)
        radius    = self.CORNER_RADIUS
        path      = QPainterPath()

        if index == 0 and index == last_index:
            path.addRoundedRect(rectangle, radius, radius)

            return path

        if index == 0:
            path.moveTo(rectangle.topRight())
            path.lineTo(rectangle.topLeft() + QPointF(radius, 0))
            path.quadTo(rectangle.topLeft(), rectangle.topLeft() + QPointF(0, radius))
            path.lineTo(rectangle.bottomLeft() + QPointF(0, -radius))
            path.quadTo(rectangle.bottomLeft(), rectangle.bottomLeft() + QPointF(radius, 0))
            path.lineTo(rectangle.bottomRight())
            path.closeSubpath()

            return path

        if index == last_index:
            path.moveTo(rectangle.topLeft())
            path.lineTo(rectangle.topRight() - QPointF(radius, 0))
            path.quadTo(rectangle.topRight(), rectangle.topRight() + QPointF(0, radius))
            path.lineTo(rectangle.bottomRight() - QPointF(0, radius))
            path.quadTo(rectangle.bottomRight(), rectangle.bottomRight() - QPointF(radius, 0))
            path.lineTo(rectangle.bottomLeft())
            path.closeSubpath()

            return path

        path.addRect(rectangle)

        return path

    # Events

    def paintEvent(self, event: QPaintEvent) -> None:
        if len(self.cached_paths) != self.amount_of_segments:
            self.update_paths()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        for index, path in enumerate(self.cached_paths):
            painter.setBrush(self.segment_color(index))
            painter.drawPath(path)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update_paths()

    def segment_color(self, index: int) -> QColor:
        return QColor(Qt.GlobalColor.white)

@Dev.track_ram
class ScheduledSegmentedBar(BaseSegmentedBar):
    def __init__(
            self,
            number_of_segments: int  = 30,
            base_thickness_px:  int  = 20,
            loop:               bool = False
        ) -> None:

        super().__init__(number_of_segments, base_thickness_px)

        self.loop            = bool(loop)
        self.schedule        = []
        self.duration_ms     = 0
        self.start_offset_ms = 0
        self.levels          = [0.0] * self.amount_of_segments
        self.color_off       = QColor("#404040")
        self.color_on        = QColor("#ffffff")

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet(Styles.Other.Transparent)

        self.elapsed_timer = QElapsedTimer()

        self.timer = Timing.Timer(
            interval    = Constants.FPS_60,
            callback    = self.tick,
            parent      = self,
            fps_managed = True
        )

    # Override

    def segment_color(self, index: int) -> QColor:
        factor = max(0.0, min(self.levels[index] / 100.0, 1.0))

        return blend_colors(self.color_off, self.color_on, factor)

    # Helpers

    def active_indices(self, item: dict) -> range | list[int]:
        segments = item.get("segments")

        if segments is None:
            return range(self.amount_of_segments)

        return [index for index in segments if 0 <= index < self.amount_of_segments]

    # Api

    def set_schedule(self, schedule: list) -> None:
        self.schedule    = schedule or []
        self.duration_ms = max(
            (
                item["start"] + item["duration"]
                for item in self.schedule
            ),
            default = 0
        )

    def play(self, start_offset_ms: int = 0) -> None:
        self.start_offset_ms = int(start_offset_ms)

        self.elapsed_timer.start()
        self.timer.start()

    def stop(self, clear_levels: bool = True) -> None:
        self.timer.stop()

        if clear_levels:
            self.levels = [0.0] * self.amount_of_segments
            self.update()

    def is_playing(self) -> bool:
        return self.timer.isActive()

    def set_colors(
            self,
            off_color: QColor | None = None,
            on_color:  QColor | None = None
        ) -> None:

        if off_color:
            self.color_off = off_color

        if on_color:
            self.color_on = on_color

        self.update()

    # Tick

    # Tick

    def tick(self) -> None:
        if not self.timer.isActive():
            return

        current_time_ms = int(self.elapsed_timer.elapsed()) + int(self.start_offset_ms)

        if self.duration_ms and current_time_ms >= self.duration_ms:
            if self.loop:
                self.elapsed_timer.restart()
                self.start_offset_ms = 0

            else:
                self.stop()

            return

        new_levels = [0.0] * self.amount_of_segments

        for item in self.schedule:
            time_start_ms = int(item["start"])
            duration_ms   = int(item["duration"])

            if duration_ms <= 0:
                continue

            if not (time_start_ms <= current_time_ms <= time_start_ms + duration_ms):
                continue

            progress_factor = (current_time_ms - time_start_ms) / duration_ms
            keyframes       = item.get("keyframes")
            easing_name     = item.get("easing", "linear")
            easing_function = Constants.VISUAL_EASINGS.get(easing_name, Constants.VISUAL_EASINGS["linear"])

            calculated_value = (
                evaluate_keyframes(keyframes, progress_factor, easing_function)
                if keyframes
                else float(item["brightness"])
            )

            segment_levels = item.get("segment_levels")
            active_list    = item.get("segments")

            if segment_levels is not None and active_list is not None and len(segment_levels) == len(active_list):
                for segment_index, level_multiplier in zip(active_list, segment_levels):
                    if not (0 <= segment_index < self.amount_of_segments):
                        continue

                    scaled_value = calculated_value * float(level_multiplier)

                    if scaled_value > new_levels[segment_index]:
                        new_levels[segment_index] = scaled_value

            else:
                for segment_index in self.active_indices(item):
                    if calculated_value > new_levels[segment_index]:
                        new_levels[segment_index] = calculated_value

        if new_levels != self.levels:
            self.levels = new_levels
            self.update()

@Dev.track_ram
class SegmentedBar(BaseSegmentedBar):
    segment_changed = pyqtSignal()

    def __init__(
            self,
            amount_of_zones: int,
            defaults:        list[int]   | None = None,
            default_levels:  list[float] | None = None
        ) -> None:

        super().__init__(amount_of_zones, 18)

        self.binary_mode   = False
        self.brush_level   = 1.0
        self.levels        = self.build_initial_levels(amount_of_zones, defaults, default_levels)
        self.is_pressed    = False
        self.hovered_index = None
        self.last_index    = None
        self.drag_target   = None

        self.cached_active_color = QColor(Styles.Colors.FontColor)
        self.cached_hover_color  = QColor(Styles.Colors.GlassBorder).lighter(130)
        self.cached_border_color = QColor(Styles.Colors.GlassBorder)

        self.setMouseTracking(True)

    # Helpers

    @staticmethod
    def build_initial_levels(
            amount_of_zones: int,
            defaults:        list[int]   | None,
            default_levels:  list[float] | None
        ) -> list[float]:

        if defaults is None:
            return [1.0] * amount_of_zones

        levels = [0.0] * amount_of_zones

        if default_levels is not None and len(default_levels) == len(defaults):
            for segment_index, level_value in zip(defaults, default_levels):
                if 0 <= segment_index < amount_of_zones:
                    levels[segment_index] = max(0.0, min(1.0, float(level_value)))

            return levels

        for segment_index in defaults:
            if 0 <= segment_index < amount_of_zones:
                levels[segment_index] = 1.0

        return levels

    @property
    def active(self) -> list[bool]:
        return [level > 0.0 for level in self.levels]

    def segment_color(self, index: int) -> QColor:
        level = self.levels[index]

        if level > 0.0:
            color = blend_colors(self.cached_border_color, self.cached_active_color, level)

            if self.hovered_index == index:
                return color.lighter(115)

            return color

        if self.hovered_index == index:
            return self.cached_hover_color

        return self.cached_border_color

    def get_index(self, horizontal_position_px: int) -> int:
        segment_width_px = self.width() / self.amount_of_segments

        return max(0, min(self.amount_of_segments - 1, int(horizontal_position_px / segment_width_px)))

    def handle_drag(self, index: int) -> None:
        if index == self.last_index:
            return

        start_index, end_index = sorted((self.last_index, index))
        state_changed          = False

        for segment_index in range(start_index, end_index + 1):
            if abs(self.levels[segment_index] - self.drag_target) < 0.005:
                continue

            self.levels[segment_index] = self.drag_target
            self.play_toggle_sound(segment_index, alternate = True)

            state_changed = True

        if state_changed:
            self.segment_changed.emit()
            self.update()

        self.last_index = index

    def handle_hover(self, index: int) -> None:
        if self.hovered_index == index:
            return

        self.hovered_index = index
        self.update()

    def play_toggle_sound(
            self,
            index:     int,
            alternate: bool = False
        ) -> None:

        tone_speed  = index / self.amount_of_segments + 0.5
        tone_speed += 0.05 if self.levels[index] > 0.0 else 0.0

        Player.ui_player.play_sound("Alerts/Clicks/Toggle3" if alternate else "Alerts/Clicks/Toggle1", speed = tone_speed)

        Haptics.ui_haptics.step()

    # Events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            super().mousePressEvent(event)

            return

        self.is_pressed = True
        index           = self.get_index(event.pos().x())

        if not (0 <= index < self.amount_of_segments):
            return

        if event.button() == Qt.MouseButton.RightButton:
            new_level = 0.0

        elif self.binary_mode:
            new_level = 0.0 if self.levels[index] > 0.0 else 1.0

        else:
            is_same_brush = self.levels[index] > 0.0 and abs(self.levels[index] - self.brush_level) < 0.03
            new_level     = 0.0 if is_same_brush else self.brush_level

        self.levels[index] = new_level
        self.drag_target   = new_level
        self.last_index    = index

        self.play_toggle_sound(index)
        self.segment_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.is_pressed  = False
        self.last_index  = None
        self.drag_target = None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.amount_of_segments <= 0:
            return

        index = self.get_index(event.pos().x())

        if self.is_pressed and self.drag_target is not None and self.last_index is not None:
            self.handle_drag(index)

        else:
            self.handle_hover(index)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.binary_mode:
            super().wheelEvent(event)

            return

        delta = event.angleDelta().y() or event.angleDelta().x()

        if delta == 0:
            super().wheelEvent(event)

            return

        index = self.get_index(int(event.position().x()))

        if not (0 <= index < self.amount_of_segments):
            return

        step               = 0.1 if delta > 0 else -0.1
        new_level          = round(max(0.0, min(1.0, self.levels[index] + step)), 2)

        if abs(new_level - self.levels[index]) < 0.005:
            event.accept()

            return

        self.levels[index] = new_level

        self.play_toggle_sound(index, alternate = True)
        self.segment_changed.emit()
        self.update()
        event.accept()

    # Api

    def set_binary_mode(self, enabled: bool) -> None:
        self.binary_mode = enabled

        if not enabled:
            return

        new_levels = [1.0 if level >= 0.5 else 0.0 for level in self.levels]

        if not any(new_levels) and any(level > 0.0 for level in self.levels):
            new_levels = [1.0 if level > 0.0 else 0.0 for level in self.levels]

        if new_levels != self.levels:
            self.levels = new_levels
            self.segment_changed.emit()
            self.update()

    def set_brush_level(self, level: float) -> None:
        self.brush_level = max(0.05, min(1.0, float(level)))

    def enable_all(self) -> None:
        self.levels = [1.0] * self.amount_of_segments
        self.segment_changed.emit()
        self.update()

        Player.ui_player.play_sound("Alerts/Clicks/Toggle1", speed = 1.0, enable_tone_randomizer = False)

    def disable_all(self) -> None:
        self.levels = [0.0] * self.amount_of_segments
        self.segment_changed.emit()
        self.update()

        Player.ui_player.play_sound("Alerts/Clicks/Toggle1", speed = 0.7, enable_tone_randomizer = False)

    def zebra(self) -> None:
        self.levels = [1.0 if index % 2 == 0 else 0.0 for index in range(self.amount_of_segments)]
        self.segment_changed.emit()
        self.update()

        Player.ui_player.play_sound("Alerts/Clicks/Toggle3")

    def invert(self) -> None:
        self.levels = [round(1.0 - level, 3) for level in self.levels]
        self.segment_changed.emit()
        self.update()

        Player.ui_player.play_sound("Alerts/Clicks/Toggle3")

# Scheduled Matrix Preview

@Dev.track_ram
class ScheduledMatrixPreview(QWidget):
    def __init__(
            self,
            device:          object,
            preview_size_px: int            = 160,
            loop:            bool           = True,
            parent:          QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.device          = device
        self.loop            = bool(loop)
        self.schedule        = []
        self.duration_ms     = 0.0
        self.start_offset_ms = 0.0
        self.preview_size_px = preview_size_px

        self.total_leds      = device.columns
        self.levels          = [0.0] * self.total_leds

        self.color_off       = QColor(Styles.Colors.GlassBorder)
        self.color_on        = QColor(255, 255, 255)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(Styles.Other.Transparent)
        self.setFixedSize(preview_size_px, preview_size_px)

        self.elapsed_timer = QElapsedTimer()

        self.timer = Timing.Timer(
            interval    = Constants.FPS_60,
            callback    = self.tick,
            parent      = self,
            fps_managed = True
        )

    # Size Adaptation

    def set_adaptive_size(self, size_px: int) -> None:
        self.preview_size_px = max(100, size_px)
        self.setFixedSize(self.preview_size_px, self.preview_size_px)
        self.update()

    # Schedule & Controls

    def set_schedule(self, schedule: list) -> None:
        self.schedule    = schedule or []
        self.duration_ms = float(
            max(
                (
                    item["start"] + item["duration"]
                    for item in self.schedule
                ),
                default = 0.0
            )
        )

    def play(self, start_offset_ms: float = 0.0) -> None:
        self.start_offset_ms = float(start_offset_ms)

        self.elapsed_timer.start()
        self.timer.start()

    def stop(self, clear_levels: bool = True) -> None:
        self.timer.stop()

        if clear_levels:
            self.levels = [0.0] * self.total_leds
            self.update()

    def is_playing(self) -> bool:
        return self.timer.isActive()

    # Active Indices

    def active_indices(self, item: dict) -> range | list[int]:
        segments = item.get("segments")

        if segments is None:
            return range(self.total_leds)

        return [index for index in segments if 0 <= index < self.total_leds]

    # Simulation Tick

    def tick(self) -> None:
        if not self.timer.isActive():
            return

        current_time_ms = float(self.elapsed_timer.elapsed()) + self.start_offset_ms

        if self.duration_ms > 0.0 and current_time_ms >= self.duration_ms:
            if self.loop:
                self.elapsed_timer.restart()
                self.start_offset_ms = 0.0
                current_time_ms      = 0.0

            else:
                self.stop()

                return

        new_levels = [0.0] * self.total_leds

        for item in self.schedule:
            time_start_ms = float(item["start"])
            duration_ms   = float(item["duration"])

            if duration_ms <= 0.0:
                continue

            if not (time_start_ms <= current_time_ms <= time_start_ms + duration_ms + 0.5):
                continue

            progress_factor = max(0.0, min(1.0, (current_time_ms - time_start_ms) / duration_ms))
            keyframes       = item.get("keyframes")

            if keyframes:
                easing_name      = item.get("easing", "linear")
                easing_function  = Constants.VISUAL_EASINGS.get(easing_name, Constants.VISUAL_EASINGS["linear"])
                calculated_value = evaluate_keyframes(keyframes, progress_factor, easing_function)

            else:
                calculated_value = float(item["brightness"])

            segment_levels = item.get("segment_levels")
            active_list    = item.get("segments")

            if segment_levels is not None and active_list is not None and len(segment_levels) == len(active_list):
                for segment_index, level_multiplier in zip(active_list, segment_levels):
                    if not (0 <= segment_index < self.total_leds):
                        continue

                    scaled_value = calculated_value * float(level_multiplier)

                    if scaled_value > new_levels[segment_index]:
                        new_levels[segment_index] = scaled_value

            else:
                for segment_index in self.active_indices(item):
                    if calculated_value > new_levels[segment_index]:
                        new_levels[segment_index] = calculated_value

        if new_levels != self.levels:
            self.levels = new_levels
            self.update()

    # Painting

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        center_coordinate = float(self.width()) / 2.0
        padding           = 16.0
        drawing_radius    = (float(self.width()) - padding) / 2.0

        maximum_rows = len(self.device.matrix_rows) if self.device.matrix_rows else 25
        dot_radius   = max(1.5, (drawing_radius / float(maximum_rows)) * 0.76)

        coordinates = self.device.matrix_led_coordinates

        for led_index, (normalized_x, normalized_y) in enumerate(coordinates):
            if led_index >= self.total_leds:
                break

            pixel_x = center_coordinate + normalized_x * drawing_radius
            pixel_y = center_coordinate + normalized_y * drawing_radius

            factor    = max(0.0, min(self.levels[led_index] / 100.0, 1.0))
            led_color = blend_colors(self.color_off, self.color_on, factor)

            painter.setBrush(led_color)
            painter.drawEllipse(QPointF(pixel_x, pixel_y), dot_radius, dot_radius)

        painter.end()

@Dev.track_ram
class MatrixSegmentBar(QWidget):
    segment_changed = pyqtSignal()

    def __init__(
            self,
            device:          object,
            defaults:        list[int]   | None = None,
            default_levels:  list[float] | None = None,
            preview_size_px: int                = 380
        ) -> None:

        super().__init__()

        self.device             = device
        self.total_leds         = device.columns
        self.coordinates        = device.matrix_led_coordinates
        self.preview_size_px    = preview_size_px
        self.binary_mode        = False
        self.brush_level        = 1.0
        self.levels             = SegmentedBar.build_initial_levels(self.total_leds, defaults, default_levels)

        self.is_pressed         = False
        self.hovered_index      = None
        self.last_pos           = None
        self.drag_target        = None
        self.last_sound_sec     = 0.0

        self.cached_active_color = QColor(Styles.Colors.FontColor)
        self.cached_hover_color  = QColor(Styles.Colors.GlassBorder).lighter(135)
        self.cached_border_color = QColor(Styles.Colors.GlassBorder)

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(Styles.Other.Transparent)
        self.setFixedSize(self.preview_size_px, self.preview_size_px)

    @property
    def active(self) -> list[bool]:
        return [level > 0.0 for level in self.levels]

    # Geometry

    def get_geometry_metrics(self) -> tuple[float, float, float]:
        center_coordinate = float(self.width()) / 2.0
        padding           = 20.0
        drawing_radius    = (float(self.width()) - padding) / 2.0
        maximum_rows      = len(self.device.matrix_rows) if self.device.matrix_rows else 25
        dot_radius        = max(3.0, (drawing_radius / float(maximum_rows)) * 0.88)

        return center_coordinate, drawing_radius, dot_radius

    def get_index(self, position: QPointF) -> int | None:
        center_coordinate, drawing_radius, _ = self.get_geometry_metrics()
        maximum_rows                         = len(self.device.matrix_rows) if self.device.matrix_rows else 25
        cell_step                            = (drawing_radius * 2.0) / float(max(1, maximum_rows - 1))
        hit_limit_squared                    = (cell_step * 0.85) ** 2

        best_index    = None
        best_distance = hit_limit_squared

        for led_index, (normalized_x, normalized_y) in enumerate(self.coordinates):
            if led_index >= self.total_leds:
                break

            pixel_x = center_coordinate + normalized_x * drawing_radius
            pixel_y = center_coordinate + normalized_y * drawing_radius

            delta_x          = position.x() - pixel_x
            delta_y          = position.y() - pixel_y
            distance_squared = delta_x * delta_x + delta_y * delta_y

            if distance_squared <= best_distance:
                best_distance = distance_squared
                best_index    = led_index

        return best_index

    # Interaction Helpers

    def play_toggle_sound(
            self,
            index:     int,
            alternate: bool = False
        ) -> None:

        now = time.monotonic()

        if alternate and (now - self.last_sound_sec) < 0.03:
            return

        self.last_sound_sec = now

        tone_speed  = (index / max(1, self.total_leds)) * 0.5 + 0.75
        tone_speed += 0.05 if self.levels[index] > 0.0 else 0.0

        Player.ui_player.play_sound(
            "Alerts/Clicks/Toggle3" if alternate else "Alerts/Clicks/Toggle1",
            speed = tone_speed
        )

        Haptics.ui_haptics.step()

    def handle_drag(self, position: QPointF) -> None:
        if self.last_pos is None:
            self.last_pos = position

            return

        _, _, dot_radius = self.get_geometry_metrics()
        delta_x          = position.x() - self.last_pos.x()
        delta_y          = position.y() - self.last_pos.y()
        distance         = math.hypot(delta_x, delta_y)

        step_px       = max(2.0, dot_radius * 0.65)
        steps_count   = max(1, int(math.ceil(distance / step_px)))
        state_changed = False
        last_changed  = None

        for step_index in range(1, steps_count + 1):
            ratio       = step_index / float(steps_count)
            sample_pos  = QPointF(self.last_pos.x() + delta_x * ratio, self.last_pos.y() + delta_y * ratio)
            pixel_index = self.get_index(sample_pos)

            if pixel_index is None or abs(self.levels[pixel_index] - self.drag_target) < 0.005:
                continue

            self.levels[pixel_index] = self.drag_target
            state_changed            = True
            last_changed             = pixel_index

        self.last_pos = position

        if state_changed and last_changed is not None:
            self.play_toggle_sound(last_changed, alternate = True)
            self.segment_changed.emit()
            self.update()

    def handle_hover(self, index: int | None) -> None:
        if self.hovered_index == index:
            return

        self.hovered_index = index
        self.update()

    # Events

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        center_coordinate, drawing_radius, dot_radius = self.get_geometry_metrics()

        for led_index, (normalized_x, normalized_y) in enumerate(self.coordinates):
            if led_index >= self.total_leds:
                break

            pixel_x = center_coordinate + normalized_x * drawing_radius
            pixel_y = center_coordinate + normalized_y * drawing_radius
            level   = self.levels[led_index]

            if level > 0.0:
                color = blend_colors(self.cached_border_color, self.cached_active_color, level)

                if self.hovered_index == led_index:
                    color = color.lighter(115)

            elif self.hovered_index == led_index:
                color = self.cached_hover_color

            else:
                color = self.cached_border_color

            painter.setBrush(color)
            painter.drawEllipse(QPointF(pixel_x, pixel_y), dot_radius, dot_radius)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            super().mousePressEvent(event)

            return

        position = event.position()
        index    = self.get_index(position)

        if index is None:
            return

        self.is_pressed = True

        if event.button() == Qt.MouseButton.RightButton:
            new_level = 0.0

        elif self.binary_mode:
            new_level = 0.0 if self.levels[index] > 0.0 else 1.0

        else:
            is_same_brush = self.levels[index] > 0.0 and abs(self.levels[index] - self.brush_level) < 0.03
            new_level     = 0.0 if is_same_brush else self.brush_level

        self.levels[index] = new_level
        self.drag_target   = new_level
        self.last_pos      = position

        self.play_toggle_sound(index)
        self.segment_changed.emit()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        position = event.position()

        if self.is_pressed and self.drag_target is not None:
            self.handle_drag(position)

            return

        self.handle_hover(self.get_index(position))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.is_pressed  = False
        self.last_pos    = None
        self.drag_target = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.binary_mode:
            super().wheelEvent(event)

            return

        delta = event.angleDelta().y() or event.angleDelta().x()

        if delta == 0:
            super().wheelEvent(event)

            return

        index = self.get_index(event.position())

        if index is None:
            event.accept()

            return

        step               = 0.1 if delta > 0 else -0.1
        new_level          = round(max(0.0, min(1.0, self.levels[index] + step)), 2)

        if abs(new_level - self.levels[index]) < 0.005:
            event.accept()

            return

        self.levels[index] = new_level

        self.play_toggle_sound(index, alternate = True)
        self.segment_changed.emit()
        self.update()
        event.accept()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)

        self.hovered_index = None
        self.update()

    # API

    def set_binary_mode(self, enabled: bool) -> None:
        self.binary_mode = enabled

        if not enabled:
            return

        new_levels = [1.0 if level >= 0.5 else 0.0 for level in self.levels]

        if not any(new_levels) and any(level > 0.0 for level in self.levels):
            new_levels = [1.0 if level > 0.0 else 0.0 for level in self.levels]

        if new_levels != self.levels:
            self.levels = new_levels
            self.segment_changed.emit()
            self.update()

    def set_brush_level(self, level: float) -> None:
        self.brush_level = max(0.05, min(1.0, float(level)))

    def set_active_mask(self, levels: list[bool] | list[float]) -> None:
        if len(levels) != self.total_leds:
            return

        self.levels = [max(0.0, min(1.0, float(value))) for value in levels]
        self.segment_changed.emit()
        self.update()

    def enable_all(self) -> None:
        self.levels = [1.0] * self.total_leds
        self.segment_changed.emit()
        self.update()

        Player.ui_player.play_sound("Alerts/Clicks/Toggle1", speed = 1.0, enable_tone_randomizer = False)

    def disable_all(self) -> None:
        self.levels = [0.0] * self.total_leds
        self.segment_changed.emit()
        self.update()

        Player.ui_player.play_sound("Alerts/Clicks/Toggle1", speed = 0.7, enable_tone_randomizer = False)

    def zebra(self) -> None:
        maximum_columns = max(self.device.matrix_rows) if self.device.matrix_rows else 1
        new_levels      = []

        for led_index in range(self.total_leds):
            if led_index < len(self.device.matrix_led_to_row_segment):
                row_str, segment_index = self.device.matrix_led_to_row_segment[led_index]
                row_index              = int(row_str) - 1
                row_width              = self.device.matrix_rows[row_index]
                start_column           = (maximum_columns - row_width) // 2
                column_index           = start_column + segment_index

                new_levels.append(1.0 if (row_index + column_index) % 2 == 0 else 0.0)

            else:
                new_levels.append(1.0 if led_index % 2 == 0 else 0.0)

        self.levels = new_levels
        self.segment_changed.emit()
        self.update()

        Player.ui_player.play_sound("Alerts/Clicks/Toggle3")

    def invert(self) -> None:
        self.levels = [round(1.0 - level, 3) for level in self.levels]
        self.segment_changed.emit()
        self.update()

        Player.ui_player.play_sound("Alerts/Clicks/Toggle3")