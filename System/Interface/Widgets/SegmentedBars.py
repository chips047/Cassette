from __future__ import annotations

import bisect

from PyQt6.QtCore import (
    Qt,
    QRectF,
    QPointF,
    pyqtSignal,
    QElapsedTimer
)

from PyQt6.QtGui import (
    QColor,
    QPainter,
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

from System.Services  import Player
from System.Interface import Timing

def evaluate_keyframes(
        keyframes:       list[tuple[float, float]],
        progress:        float,
        easing_function
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

        self.loop             = bool(loop)
        self.schedule         = []
        self.duration_ms      = 0
        self.start_offset_ms  = 0
        self.levels           = [0.0] * self.amount_of_segments
        self.color_off        = QColor("#404040")
        self.color_on         = QColor("#ffffff")

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet("background-color: transparent;")

        self.elapsed_timer = QElapsedTimer()

        self.timer = Timing.Timer(
            Constants.FPS_60,
            self.tick,
            parent = self
        )

    # Override

    def segment_color(self, index: int) -> QColor:
        factor = max(0.0, min(self.levels[index] / 100.0, 1.0))

        return blend_colors(self.color_off, self.color_on, factor)

    # Helpers

    def active_indices(self, item: dict) -> range | list[int]:
        segments = item.get("segments")

        if not segments:
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

            for segment_index in self.active_indices(item):
                if calculated_value < new_levels[segment_index]:
                    continue

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
            defaults:        list[int] | None = None
        ) -> None:

        super().__init__(amount_of_zones, 18)

        number_list        = defaults if defaults else list(range(amount_of_zones))
        self.active        = [index in number_list for index in range(amount_of_zones)]
        self.is_pressed    = False
        self.hovered_index = None
        self.last_index    = None
        self.drag_target   = None

        self.cached_active_color = QColor(Styles.Colors.FontColor)
        self.cached_hover_color  = QColor(Styles.Colors.GlassBorder).lighter(130)
        self.cached_border_color = QColor(Styles.Colors.GlassBorder)

    # Override

    def segment_color(self, index: int) -> QColor:
        if self.active[index]:
            return self.cached_active_color

        if self.hovered_index == index:
            return self.cached_hover_color

        return self.cached_border_color

    # Helpers

    def get_index(self, horizontal_position_px: int) -> int:
        segment_width_px = self.width() / self.amount_of_segments

        return max(0, min(self.amount_of_segments - 1, int(horizontal_position_px / segment_width_px)))

    def handle_drag(self, index: int) -> None:
        if index == self.last_index:
            return

        start_index, end_index = sorted((self.last_index, index))
        state_changed          = False

        for segment_index in range(start_index, end_index + 1):
            if self.active[segment_index] == self.drag_target:
                continue

            self.active[segment_index] = self.drag_target
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
        tone_speed += 0.05 if self.active[index] else 0.0

        Player.ui_player.play_sound("Click/Toggle3" if alternate else "Click/Toggle", speed = tone_speed)

    # Events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.is_pressed = True
        index           = self.get_index(event.pos().x())

        if not (0 <= index < self.amount_of_segments):
            return

        new_state          = not self.active[index]
        self.active[index] = new_state
        self.drag_target   = new_state
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

    # Api

    def enable_all(self) -> None:
        self.active = [True] * self.amount_of_segments
        self.segment_changed.emit()

        Player.ui_player.play_sound("Click/Toggle", speed = 1.0, enable_tone_randomizer = False)

    def disable_all(self) -> None:
        self.active = [False] * self.amount_of_segments
        self.segment_changed.emit()

        Player.ui_player.play_sound("Click/Toggle", speed = 0.7, enable_tone_randomizer = False)

    def zebra(self) -> None:
        self.active = [index % 2 == 0 for index in range(self.amount_of_segments)]
        self.segment_changed.emit()

        Player.ui_player.play_sound("Click/Toggle3")