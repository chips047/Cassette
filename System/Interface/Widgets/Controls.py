from __future__ import annotations

from time import monotonic

from PyQt6.QtGui import (
    QIcon,
    QColor,
    QPainter,
    QMouseEvent,
    QPaintEvent,
    QWheelEvent,
    QFontMetrics
)

from PyQt6.QtCore import (
    Qt,
    QSize,
    QRectF,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSizePolicy,
    QApplication
)

from System.Common import (
    Dev,
    Utils,
    Styles
)

from System.Services import (
    Player,
    Haptics
)

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine
)

# Base Control Container

class BaseControlContainer(QWidget):
    def __init__(
            self,
            inner_layout_type: type           = QVBoxLayout,
            parent:            QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.setContentsMargins(0, 0, 0, 0)

        self.setup_attributes()
        self.setup_layout(inner_layout_type)

    def setup_attributes(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.setWindowFlags(
            self.windowFlags()                |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint
        )

    def setup_layout(self, inner_layout_type: type) -> None:
        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.container_background = QFrame(self)
        self.container_background.setStyleSheet(Styles.Controls.SliderBackground)

        self.inner_layout = inner_layout_type(self.container_background)

        self.inner_layout.setContentsMargins(12, 8, 12, 8)
        self.inner_layout.setSpacing(8)

        main_layout.addWidget(self.container_background)

# Base Control Widget

class BaseControlWidget(QWidget):
    def __init__(
            self,
            icon:              QIcon   | None = None,
            static_label_text: str     | None = None,
            parent:            QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.static_label_text = static_label_text
        self.icon              = icon
        self.top_label         = None
        self.icon_label        = None
        self.value_label       = None

        self.setup_user_interface()

    def setup_user_interface(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(120)

        self.main_layout = QHBoxLayout(self)

        self.main_layout.setContentsMargins(8, 0, 6, 0)
        self.main_layout.setSpacing(6)

        self.labels_layout = QVBoxLayout()

        self.labels_layout.setContentsMargins(0, 0, 0, 3)
        self.labels_layout.setSpacing(0)
        self.labels_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.setup_top_label()
        self.setup_value_label()

        self.main_layout.addLayout(self.labels_layout)
        self.main_layout.addStretch()

        if self.icon:
            self.setup_icon()

    def setup_top_label(self) -> None:
        if not self.static_label_text:
            return

        self.top_label = QLabel(self.static_label_text)

        self.top_label.setFont(Utils.NDot(9))
        self.top_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.top_label.setStyleSheet(Styles.Other.SecondFont + Styles.Other.Transparent)
        self.top_label.setContentsMargins(0, 0, 0, 0)
        self.top_label.setFixedHeight(18)

        self.labels_layout.addWidget(self.top_label)

    def setup_value_label(self) -> None:
        self.value_label = QLabel()

        self.value_label.setFont(Utils.NDot(10))
        self.value_label.setStyleSheet(Styles.Other.Font + Styles.Other.Transparent)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setContentsMargins(0, 0, 0, 0)
        self.value_label.setFixedHeight(18)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.labels_layout.addWidget(self.value_label)

    def setup_icon(self) -> None:
        if not self.icon:
            return

        self.icon_label = QLabel()
        pixmap          = self.icon.pixmap(20, 20)

        self.icon_label.setPixmap(pixmap)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedWidth(25)
        self.icon_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.icon_label.setStyleSheet(Styles.Other.Transparent)

        self.main_layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

    def sizeHint(self) -> QSize:
        return QSize(self.minimumWidth(), Styles.Metrics.ElementHeight)

@Dev.track_ram
class DraggableValueControl(BaseControlWidget):
    valueChanged = pyqtSignal(int)

    def __init__(
            self,
            icon:              QIcon   | None = None,
            static_label_text: str     | None = None,
            initial_value:     int            = 100,
            minimum_value:     int            = 0,
            maximum_value:     int            = 200,
            step:              int            = 5,
            unit_suffix:       str            = "",
            parent:            QWidget | None = None
        ) -> None:

        super().__init__(icon, static_label_text, parent)

        self.initial_value                  = initial_value
        self.current_value                  = initial_value
        self.minimum_value                  = minimum_value
        self.maximum_value                  = maximum_value
        self.step                           = step
        self.unit_suffix                    = unit_suffix

        self.dragging                       = False
        self.drag_start_horizontal_position = 0
        self.drag_start_value               = 0

        self.wheel_accumulator              = 0.0

        self.last_sound_timestamp_seconds   = 0.0
        self.minimum_sound_interval_seconds = 1.0 / 20.0

        self.update_value_label()
        self.setStyleSheet(Styles.Controls.ValueControl)

    # Audio Feedback

    # Audio & Haptic Feedback

    def play_tick_sound(self) -> None:
        current_timestamp_seconds = monotonic()
        time_difference_seconds   = current_timestamp_seconds - self.last_sound_timestamp_seconds

        if time_difference_seconds < self.minimum_sound_interval_seconds:
            return

        self.last_sound_timestamp_seconds = current_timestamp_seconds

        Player.ui_player.play_sound("Alerts/Clicks/Toggle3")

        modifiers = QApplication.keyboardModifiers()

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            Haptics.ui_haptics.snap()

        else:
            Haptics.ui_haptics.step()

    # Value Management

    def update_value_label(self) -> None:
        self.value_label.setText(f"{self.current_value}{self.unit_suffix}")

    def apply_value(self, target_value: int) -> None:
        clamped_value = max(self.minimum_value, min(self.maximum_value, target_value))

        if clamped_value == self.current_value:
            return

        self.current_value = clamped_value
        self.update_value_label()

        self.play_tick_sound()

        self.valueChanged.emit(self.current_value)

    # Helpers

    def resolve_effective_step(self) -> int:
        modifiers = QApplication.keyboardModifiers()

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            return self.step * 5

        return self.step

    # Events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        self.dragging                       = True
        self.drag_start_horizontal_position = event.pos().x()
        self.drag_start_value               = self.current_value
        self.last_sound_timestamp_seconds   = 0.0

        self.setCursor(Qt.CursorShape.SizeHorCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.dragging:
            return

        effective_step      = self.resolve_effective_step()
        pixels_per_step     = 10
        horizontal_delta_px = event.pos().x() - self.drag_start_horizontal_position
        steps               = horizontal_delta_px // pixels_per_step

        calculated_value    = self.drag_start_value + steps * effective_step
        rounded_value       = int(round(calculated_value / effective_step)) * effective_step

        self.apply_value(rounded_value)

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if not self.dragging:
            return

        self.dragging = False
        self.setCursor(Qt.CursorShape.ArrowCursor)

        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        pixel_delta = event.pixelDelta().y()

        if pixel_delta != 0:
            self.wheel_accumulator += float(pixel_delta)

        else:
            angle_delta = event.angleDelta().y()

            if angle_delta == 0:
                angle_delta = event.angleDelta().x()

            self.wheel_accumulator += float(angle_delta) / 12.0

        threshold = 10.0

        if abs(self.wheel_accumulator) < threshold:
            event.accept()
            return

        steps                   = int(self.wheel_accumulator / threshold)
        self.wheel_accumulator -= float(steps) * threshold

        effective_step          = self.resolve_effective_step()
        calculated_value        = self.current_value + steps * effective_step

        self.apply_value(calculated_value)

        event.accept()

    # State Management

    def reset(self) -> None:
        self.current_value = self.initial_value
        self.update_value_label()

@Dev.track_ram
class RollingTextLabel(Lifecycle.LoomAnimationMixin, QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.current_text  = ""
        self.previous_text = ""
        self.text_font     = Utils.NDot(10)

        self.setFont(self.text_font)
        self.setFixedHeight(18)

        self.setup_animation()

    # Setup

    def setup_animation(self) -> None:
        self.scroll_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "text_scroll_offset",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_scroll_offset_changed
        )

    # Callbacks

    def on_scroll_offset_changed(self, value: float) -> None:
        self.update()

    # Text Management

    def set_immediate_text(self, text: str) -> None:
        self.scroll_handle.stop_targeting()
        self.scroll_handle.set_base(0.0)

        self.current_text  = text
        self.previous_text = text

        self.update()

    def scroll_to_text(self, new_text: str) -> None:
        if new_text == self.current_text and self.scroll_handle.value == 0.0:
            return

        self.previous_text = self.current_text
        self.current_text  = new_text

        self.scroll_handle.stop_targeting()
        self.scroll_handle.set_base(0.0)

        self.scroll_handle.set_target(
            value                      = 1.0,
            duration_ms                = 220,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    # Painting

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)

        painter.setClipRect(self.rect())
        painter.setFont(self.font())

        widget_width_px    = float(self.width())
        widget_height_px   = float(self.height())
        offset_ratio       = float(self.scroll_handle.value)
        text_color         = QColor(Styles.Colors.FontColor)
        vertical_offset_px = 0.0

        draw_rectangle     = QRectF(0.0, vertical_offset_px, widget_width_px, widget_height_px)

        if offset_ratio <= 0.0 or offset_ratio >= 1.0:
            painter.setPen(text_color)
            painter.drawText(
                draw_rectangle,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.current_text
            )
            painter.end()

            return

        previous_alpha = max(0, min(255, int(255.0 * (1.0 - offset_ratio))))
        previous_color = QColor(text_color)
        previous_color.setAlpha(previous_alpha)

        previous_vertical_position_px = -offset_ratio * widget_height_px

        painter.setPen(previous_color)
        painter.drawText(
            QRectF(0.0, previous_vertical_position_px + vertical_offset_px, widget_width_px, widget_height_px),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.previous_text
        )

        current_alpha = max(0, min(255, int(255.0 * offset_ratio)))
        current_color = QColor(text_color)
        current_color.setAlpha(current_alpha)

        current_vertical_position_px = (1.0 - offset_ratio) * widget_height_px

        painter.setPen(current_color)
        painter.drawText(
            QRectF(0.0, current_vertical_position_px + vertical_offset_px, widget_width_px, widget_height_px),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.current_text
        )

        painter.end()

# Cycle Button

@Dev.track_ram
class CycleButton(BaseControlWidget):
    state_changed = pyqtSignal(str, object)

    def __init__(
            self,
            icon:              QIcon                    | None = None,
            static_label_text: str                      | None = None,
            states:            list[tuple[str, object]] | None = None,
            parent:            QWidget                  | None = None
        ) -> None:

        self.states              = states if states is not None else [("1x", 1.0)]
        self.current_state_index = 0
        self.rolling_label       = None

        super().__init__(icon, static_label_text, parent)

        self.apply_optimal_width()
        self.show_state(emit = False, animated = False)

        self.setStyleSheet(Styles.Controls.CycleButton)

    def setup_value_label(self) -> None:
        self.rolling_label = RollingTextLabel(self)
        self.value_label   = self.rolling_label

        self.labels_layout.addWidget(self.rolling_label)

    # Geometry

    def apply_optimal_width(self) -> None:
        font_metrics = QFontMetrics(Utils.NDot(10))

        maximum_text_width_px = max(
            (font_metrics.horizontalAdvance(display_text) for display_text, _ in self.states),
            default = 40
        )

        self.rolling_label.setFixedWidth(maximum_text_width_px + 2)

        top_text_width_px = 0

        if self.static_label_text:
            top_font_metrics  = QFontMetrics(Utils.NDot(9))
            top_text_width_px = top_font_metrics.horizontalAdvance(self.static_label_text)

        text_column_width_px  = max(maximum_text_width_px, top_text_width_px)
        icon_width_px         = 20 if self.icon else 0
        margins_width_px      = 14
        spacing_width_px      = 6

        optimal_width_px      = max(margins_width_px + text_column_width_px + spacing_width_px + icon_width_px, 96)

        self.setFixedWidth(optimal_width_px)

    # Events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)

            return

        self.next_state()
        event.accept()

    # State Management

    def cycle_state(self) -> None:
        self.current_state_index = (self.current_state_index + 1) % len(self.states)

    def next_state(self) -> None:
        self.cycle_state()
        self.show_state(emit = True, animated = True)

        Player.ui_player.play_sound("Alerts/Clicks/Toggle3")

    def show_state(
            self,
            emit:     bool = True,
            animated: bool = True
        ) -> None:

        display_text, value = self.states[self.current_state_index]

        if animated:
            self.rolling_label.scroll_to_text(display_text)

        else:
            self.rolling_label.set_immediate_text(display_text)

        if emit:
            self.state_changed.emit(display_text, value)

    def reset(self) -> None:
        self.current_state_index = 0
        self.show_state(emit = False, animated = False)

    def get_current_value(self) -> object:
        return self.states[self.current_state_index][1]