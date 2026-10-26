from __future__ import annotations

from time   import monotonic
from random import randint

from PyQt6.QtGui import (
    QHideEvent,
    QShowEvent,
    QMouseEvent,
    QWheelEvent
)

from PyQt6.QtCore import (
    Qt,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QLabel,
    QSlider,
    QHBoxLayout
)

from System.Common import (
    Dev,
    Utils,
    Styles
)

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine
)

from System.Services import (
    Player,
    Haptics
)

from System.Interface import Widgets

# Direct Jump Slider

class DirectJumpSlider(QSlider):
    def __init__(
            self,
            orientation: Qt.Orientation,
            parent:      Widgets.BaseControlContainer | None = None
        ) -> None:

        super().__init__(orientation, parent)

        self.setFixedHeight(26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def update_position_from_mouse(self, mouse_horizontal_position: float) -> None:
        if self.maximum() <= self.minimum():
            return

        total_width = self.width()

        if total_width <= 0:
            return

        clamped_position = max(0.0, min(float(total_width), mouse_horizontal_position))
        progress_ratio   = clamped_position / total_width

        if self.invertedAppearance():
            progress_ratio = 1.0 - progress_ratio

        calculated_value = self.minimum() + progress_ratio * (self.maximum() - self.minimum())
        rounded_value    = int(round(calculated_value))

        self.setValue(rounded_value)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        self.setFocus()
        self.setSliderDown(True)
        self.sliderPressed.emit()

        self.update_position_from_mouse(event.position().x())

        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.isSliderDown():
            super().mouseMoveEvent(event)
            return

        self.update_position_from_mouse(event.position().x())

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        self.setSliderDown(False)
        self.sliderReleased.emit()

        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

# Slider With Label

@Dev.track_ram
class SliderWithLabel(Lifecycle.LoomAnimationMixin, Widgets.BaseControlContainer):
    valueChanged = pyqtSignal(int)

    def __init__(
            self,
            description:   str,
            minimum_value: int,
            maximum_value: int,
            default_value: int
        ) -> None:

        super().__init__()

        self.minimum_value                  = minimum_value
        self.maximum_value                  = maximum_value
        self.target_value                   = default_value
        self.show_animation_pending         = True
        self.slider_is_dragging             = False
        self.wheel_accumulator              = 0.0
        self.last_sound_timestamp_seconds   = 0.0
        self.minimum_sound_interval_seconds = 1.0 / 15.0

        self.setMaximumHeight(68)
        self.inner_layout.setContentsMargins(12, 8, 12, 8)
        self.inner_layout.setSpacing(6)

        self.setup_label(description)
        self.setup_slider(default_value)
        self.setup_animation_handle()

        self.slider.sliderPressed.connect(self.handle_slider_pressed)
        self.slider.sliderReleased.connect(self.handle_slider_released)
        self.slider.valueChanged.connect(self.handle_slider_value_changed)

    # Setup Methods

    def create_label(
            self,
            text:           str,
            font_size:      int,
            alignment_flag: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft
        ) -> QLabel:

        label = QLabel(text)

        label.setFont(Utils.NType(font_size))
        label.setStyleSheet("color: #dddddd; padding: 0px; border: none;")
        label.setAlignment(alignment_flag)

        return label

    def setup_label(self, description: str) -> None:
        self.description_label = self.create_label(description, 11)

        self.inner_layout.addWidget(self.description_label)

    def setup_slider(self, default_value: int) -> None:
        slider_value_layout = QHBoxLayout()

        slider_value_layout.setContentsMargins(0, 0, 0, 0)
        slider_value_layout.setSpacing(12)

        self.slider = DirectJumpSlider(Qt.Orientation.Horizontal, self.container_background)

        self.slider.setRange(self.minimum_value, self.maximum_value)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setValue(default_value)
        self.slider.setStyleSheet(Styles.Controls.Slider)

        slider_value_layout.addWidget(self.slider, 1)

        self.value_label = self.create_label(
            str(default_value),
            12,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        slider_value_layout.addWidget(self.value_label, 0)

        self.inner_layout.addLayout(slider_value_layout)

    def setup_animation_handle(self) -> None:
        self.value_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "slider_value",
            base_value = self.slider.value(),
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_animated_value_changed
        )

    # Audio Feedback

    def play_slider_tick_sound(self, current_value: int) -> None:
        if self.maximum_value <= self.minimum_value:
            return

        current_timestamp_seconds = monotonic()
        time_difference_seconds   = current_timestamp_seconds - self.last_sound_timestamp_seconds

        if time_difference_seconds < self.minimum_sound_interval_seconds:
            return

        self.last_sound_timestamp_seconds = current_timestamp_seconds

        progress_ratio = (current_value - self.minimum_value) / (self.maximum_value - self.minimum_value)
        playback_speed = progress_ratio + 0.7
        stereo_pan     = progress_ratio * 2.0 - 1.0
        sound_variant  = randint(1, 3)

        if self.slider.invertedAppearance():
            stereo_pan = -stereo_pan

        Player.ui_player.play_sound(
            f"Controls/Slider/Tick{sound_variant}",
            speed  = playback_speed,
            volume = 0.8,
            pan    = stereo_pan
        )

        Haptics.ui_haptics.step()

    # Event Handlers

    def handle_slider_pressed(self) -> None:
        self.slider_is_dragging           = True
        self.last_sound_timestamp_seconds = 0.0

        self.value_handle.stop_targeting()

    def handle_slider_released(self) -> None:
        self.slider_is_dragging = False

    def handle_slider_value_changed(self, value: int) -> None:
        self.target_value = value
        self.value_label.setText(str(value))
        self.valueChanged.emit(value)

        if not self.slider_is_dragging:
            return

        self.play_slider_tick_sound(value)

    # Animation Logic

    def on_animated_value_changed(self, value: float) -> None:
        rounded_value = int(round(value))

        self.slider.blockSignals(True)
        self.slider.setValue(rounded_value)
        self.slider.blockSignals(False)

        self.value_label.setText(str(rounded_value))

    def start_value_animation(self, target_value: int) -> None:
        self.value_handle.set_target(
            value           = target_value,
            duration_ms     = 450,
            easing_function = LoomEngine.Easing.ease_out_quint
        )

    def play_show_animation(self) -> None:
        if self.slider_is_dragging:
            return

        self.value_handle.stop()
        self.value_handle.set_base(self.minimum_value)

        self.start_value_animation(self.target_value)

    def animate_to_value(self, value: int) -> None:
        self.target_value = self.clamp_value(value)

        if self.slider_is_dragging:
            return

        self.start_value_animation(self.target_value)

    # Lifecycle Events

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)

        if not self.show_animation_pending:
            return

        self.show_animation_pending = False

        self.play_show_animation()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)

        self.show_animation_pending = True
        self.slider_is_dragging     = False

        self.value_handle.stop()

    def wheelEvent(self, event: QWheelEvent) -> None:
        is_horizontal = event.angleDelta().x() != 0 or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if not is_horizontal:
            event.ignore()
            return

        delta = event.angleDelta().x() if event.angleDelta().x() != 0 else event.angleDelta().y()

        if delta == 0:
            event.ignore()
            return

        self.wheel_accumulator += delta
        threshold               = 120.0

        if abs(self.wheel_accumulator) < threshold:
            event.accept()
            return

        steps                  = int(self.wheel_accumulator / threshold)
        self.wheel_accumulator = 0.0

        direction = 1 if steps > 0 else -1
        new_value = self.clamp_value(self.value() + direction)

        if new_value == self.value():
            event.accept()
            return

        self.setValue(new_value, animated = False)
        self.play_slider_tick_sound(new_value)

        event.accept()

    # Getters and Setters

    def value(self) -> int:
        if self.slider_is_dragging:
            return self.slider.value()

        return self.target_value

    def setValue(
            self,
            value:    int | float | str,
            animated: bool = True
        ) -> None:

        target_value = self.parse_value(value)
        target_value = self.clamp_value(target_value)

        self.target_value = target_value
        self.value_label.setText(str(target_value))

        if animated and self.isVisible():
            self.animate_to_value(target_value)
            return

        self.value_handle.stop_targeting()
        self.value_handle.set_base(target_value)

        self.slider.blockSignals(True)
        self.slider.setValue(self.minimum_value if self.show_animation_pending else target_value)
        self.slider.blockSignals(False)

        self.valueChanged.emit(target_value)

    def getValueAsText(self) -> str:
        return str(self.value())

    # Helpers

    def clamp_value(self, value: int) -> int:
        return max(self.minimum_value, min(self.maximum_value, value))

    def parse_value(self, value: int | float | str) -> int:
        if isinstance(value, (int, float)):
            return int(value)

        if isinstance(value, str) and value.isdigit():
            return int(value)

        return self.target_value