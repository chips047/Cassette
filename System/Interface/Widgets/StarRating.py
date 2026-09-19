import math

from PyQt6.QtCore import (
    Qt,
    pyqtSignal
)

from PyQt6.QtGui import (
    QPen,
    QColor,
    QPainter,
    QPaintEvent,
    QMouseEvent,
    QPainterPath
)

from PyQt6.QtWidgets import (
    QWidget,
    QSizePolicy
)

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine
)

from System.Services import Player

class StarRatingWidget(Lifecycle.LoomAnimationMixin, QWidget):
    rating_changed = pyqtSignal(int)

    star_count:     int   = 5
    star_spacing:   float = 46.0
    outer_radius:   float = 14.0
    left_margin_px: float = 24.0

    def __init__(
            self,
            initial_rating: int            = 5,
            parent:         QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.current_rating = initial_rating
        self.fill_handles   = []
        self.scale_handles  = []

        self.setup_user_interface()
        self.setup_animation_handles()

    # User Interface Setup

    def setup_user_interface(self) -> None:
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

    def setup_animation_handles(self) -> None:
        for star_index in range(self.star_count):
            initial_fill = 1.0 if star_index < self.current_rating else 0.0

            fill_handle = LoomEngine.ui_engine.bind(
                owner      = self,
                name       = f"star_fill_{star_index}",
                base_value = initial_fill,
                mix_mode   = LoomEngine.MixMode.REPLACE,
                on_change  = lambda value: self.update()
            )
            self.fill_handles.append(fill_handle)

            scale_handle = LoomEngine.ui_engine.bind(
                owner      = self,
                name       = f"star_scale_{star_index}",
                base_value = 1.0,
                mix_mode   = LoomEngine.MixMode.REPLACE,
                on_change  = lambda value: self.update()
            )
            self.scale_handles.append(scale_handle)

    # Geometry Calculation

    def calculate_star_center_x(self, star_index: int) -> float:
        return self.left_margin_px + star_index * self.star_spacing

    def generate_star_path(
            self,
            center_x:     float,
            center_y:     float,
            outer_radius: float,
            scale_factor: float
        ) -> QPainterPath:

        path         = QPainterPath()
        scaled_outer = outer_radius * scale_factor
        scaled_inner = scaled_outer * 0.46
        angle_step   = math.pi / 5.0
        start_angle  = -math.pi / 2.0

        initial_x = center_x + scaled_outer * math.cos(start_angle)
        initial_y = center_y + scaled_outer * math.sin(start_angle)
        path.moveTo(initial_x, initial_y)

        for step_index in range(1, 10):
            current_radius = scaled_inner if step_index % 2 != 0 else scaled_outer
            current_angle  = start_angle + step_index * angle_step
            point_x        = center_x + current_radius * math.cos(current_angle)
            point_y        = center_y + current_radius * math.sin(current_angle)
            path.lineTo(point_x, point_y)

        path.closeSubpath()

        return path

    # Render

    def paintEvent(self, event: QPaintEvent) -> None:
        painter  = QPainter(self)
        center_y = float(self.height()) / 2.0

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for star_index in range(self.star_count):
            center_x    = self.calculate_star_center_x(star_index)
            scale_value = float(self.scale_handles[star_index].value)
            fill_ratio  = float(self.fill_handles[star_index].value)

            star_path = self.generate_star_path(
                center_x,
                center_y,
                self.outer_radius,
                scale_value
            )

            border_alpha = int(45 + fill_ratio * 190)
            fill_alpha   = int(fill_ratio * 240)

            star_pen   = QPen(QColor(255, 255, 255, border_alpha), 1.6)
            star_brush = QColor(255, 255, 255, fill_alpha)

            painter.setPen(star_pen)
            painter.setBrush(star_brush)
            painter.drawPath(star_path)

        painter.end()

    # Interaction

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        click_x         = event.position().x()
        relative_offset = click_x - self.left_margin_px
        resolved_index  = round(relative_offset / self.star_spacing)
        clamped_index   = max(0, min(self.star_count - 1, resolved_index))

        self.apply_rating(clamped_index + 1)

    def apply_rating(self, rating_value: int) -> None:
        self.current_rating = rating_value
        target_index        = rating_value - 1

        peak_scale  = 0.7 + (target_index / 4.0) * 0.8
        sound_pitch = 0.72 + (rating_value / 5.0) * 0.58
        sound_pan   = (target_index / 4.0) * 1.8 - 0.9

        self.scale_handles[target_index].play_curve(
            keyframes       = [
                (0.0, 1.0),
                (0.45, peak_scale),
                (1.0, 1.0)
            ],
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        for star_index in range(self.star_count):
            target_fill = 1.0 if star_index < rating_value else 0.0

            self.fill_handles[star_index].set_target(
                value           = target_fill,
                duration_ms     = 220 + star_index * 24,
                easing_function = LoomEngine.Easing.ease_out_cubic
            )

        Player.ui_player.play_sound(
            "Click/Toggle2",
            speed  = sound_pitch,
            pan    = sound_pan,
            volume = 0.75
        )

        self.rating_changed.emit(rating_value)

    # API

    def value(self) -> int:
        return self.current_rating

    def set_value(self, rating_value: int) -> None:
        clamped_value = max(1, min(self.star_count, rating_value))
        self.apply_rating(clamped_value)