from __future__ import annotations

from PyQt6.QtCore import (
    Qt,
    QSize
)

from PyQt6.QtGui import (
    QWheelEvent,
    QResizeEvent
)

from PyQt6.QtWidgets import (
    QWidget,
    QScrollArea,
    QVBoxLayout
)

from System.Common import (
    Dev,
    Constants
)

from System.Interface import Timing

@Dev.track_ram
class ContentCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.layout_manager = QVBoxLayout(self)
        self.layout_manager.setContentsMargins(0, 0, 0, 0)
        self.layout_manager.setSpacing(12)
        self.layout_manager.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

    def sizeHint(self) -> QSize:
        size_hint = self.layout_manager.sizeHint()

        return QSize(size_hint.width(), size_hint.height())

@Dev.track_ram
class ElasticScrollArea(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.raw_scroll_position = 0.0
        self.velocity_speed      = 0.0
        self.scrolling_is_active = False

        self.setStyleSheet("background: transparent;")

        self.setup_canvas()
        self.setup_timers()
        self.viewport().installEventFilter(self)

    # Setup

    def setup_canvas(self) -> None:
        self.canvas         = QWidget(self.viewport())
        self.layout_manager = QVBoxLayout(self.canvas)

        self.layout_manager.setContentsMargins(0, 8, 0, 8)
        self.layout_manager.setSpacing(12)
        self.layout_manager.setAlignment(Qt.AlignmentFlag.AlignTop)

    def setup_timers(self) -> None:
        self.idle_timer = Timing.Timer(
            Constants.USER_SCROLL_IDLE_TIMEOUT,
            self.handle_scroll_finished,
            single_shot = True,
            parent      = self
        )

        self.animation_timer = Timing.Timer(
            Constants.ANIMATION_TICK_INTERVAL,
            self.process_animation_tick,
            parent = self
        )

    # Widget Management

    def add_widget(self, widget: QWidget) -> None:
        self.layout_manager.addWidget(widget)

    def get_required_width(self) -> int:
        maximum_width_px = 0

        for index in range(self.layout_manager.count()):
            layout_item = self.layout_manager.itemAt(index)
            widget      = layout_item.widget() if layout_item else None

            if not widget:
                continue

            hint = widget.sizeHint()

            if hint.width() > maximum_width_px:
                maximum_width_px = hint.width()

        return max(maximum_width_px, 400)

    # Events

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update_canvas_geometry()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta_y    = event.angleDelta().y()
        limit_px   = self.calculate_maximum_scroll()
        resistance = self.calculate_resistance(limit_px)

        self.velocity_speed     -= (delta_y * Constants.current_settings.get("wheel_scroll_sensitivity", 1.0) / 8.0) * resistance
        self.scrolling_is_active = True

        self.idle_timer.start(Constants.USER_SCROLL_IDLE_TIMEOUT)

        if not self.animation_timer.isActive():
            self.animation_timer.start()

        event.accept()

    def hideEvent(self, event) -> None:
        self.animation_timer.stop()
        super().hideEvent(event)

    # Animation

    def process_animation_tick(self) -> None:
        limit_px                  = self.calculate_maximum_scroll()
        self.raw_scroll_position += self.velocity_speed

        overshoot_px = self.calculate_overshoot(limit_px)

        self.update_velocity(overshoot_px)
        self.apply_content_position()

        should_stop = (
            abs(self.velocity_speed) < 0.01 and
            abs(overshoot_px) < 0.1 and
            not self.scrolling_is_active
        )

        if should_stop:
            self.raw_scroll_position = max(0.0, min(limit_px, self.raw_scroll_position))
            self.apply_content_position()
            self.animation_timer.stop()

    # Calculation

    def update_canvas_geometry(self) -> None:
        viewport_width_px = self.viewport().width()
        canvas_height_px  = self.layout_manager.sizeHint().height()

        self.canvas.resize(viewport_width_px, canvas_height_px)

    def calculate_maximum_scroll(self) -> float:
        maximum_scroll_px = max(0, self.canvas.height() - self.viewport().height())

        return float(maximum_scroll_px)

    def handle_scroll_finished(self) -> None:
        self.scrolling_is_active = False

    def apply_content_position(self) -> None:
        limit_px = self.calculate_maximum_scroll()
        raw_px   = self.raw_scroll_position
        y_px     = -self.calculate_position(raw_px, limit_px)

        self.canvas.move(0, int(y_px))

    def calculate_resistance(self, limit_px: float) -> float:
        if self.raw_scroll_position >= 0 and self.raw_scroll_position <= limit_px:
            return 1.0

        if self.raw_scroll_position < 0:
            excess_px = abs(self.raw_scroll_position)

        else:
            excess_px = self.raw_scroll_position - limit_px

        return max(0.05, 1.0 / (1.0 + excess_px / (Constants.VISUAL_RESISTANCE_STRENGTH * 0.5))) * 0.3

    def calculate_overshoot(self, limit_px: float) -> float:
        if self.raw_scroll_position < 0.0:
            return self.raw_scroll_position

        if self.raw_scroll_position > limit_px:
            return self.raw_scroll_position - limit_px

        return 0.0

    def update_velocity(self, overshoot_px: float) -> None:
        if overshoot_px == 0.0:
            self.velocity_speed *= Constants.current_settings.get("inertia_deceleration_factor", Constants.INERTIA_DECELERATION_RATE)

            return

        if self.scrolling_is_active:
            self.velocity_speed *= 0.8

        else:
            spring_force        = -overshoot_px      * Constants.SPRING_STIFFNESS
            damping_force       = -self.velocity_speed * Constants.SPRING_DAMPING_FACTOR
            self.velocity_speed += spring_force + damping_force

    def calculate_position(
            self,
            raw_px:   float,
            limit_px: float
        ) -> float:

        if raw_px < 0.0:
            return raw_px / (1.0 + abs(raw_px) / Constants.VISUAL_RESISTANCE_STRENGTH)

        if raw_px > limit_px:
            excess_px = raw_px - limit_px

            return limit_px + (excess_px / (1.0 + excess_px / Constants.VISUAL_RESISTANCE_STRENGTH))

        return raw_px