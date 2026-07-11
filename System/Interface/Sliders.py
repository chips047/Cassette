from PyQt6.QtGui import (
    QShowEvent,
    QHideEvent
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

from System.Services import Player

from System.Interface.Animation import Lifecycle

from System.Interface.Animation.LoomEngine import (
    Easing,
    MixMode,
    ui_engine
)

from System.Interface.Controls import BaseControlContainer

# Slider With Label

@Dev.track_ram
class SliderWithLabel(Lifecycle.LoomAnimationMixin, BaseControlContainer):
    valueChanged = pyqtSignal(int)

    def __init__(
            self,
            description:   str,
            minimum_value: int,
            maximum_value: int,
            default_value: int
        ) -> None:

        super().__init__()

        self.minimum_value          = minimum_value
        self.maximum_value          = maximum_value
        self.target_value           = default_value
        self.show_animation_pending = True
        self.slider_is_dragging     = False

        self.setMaximumHeight(60)
        self.inner_layout.setContentsMargins(12, 8, 12, 4)
        self.inner_layout.setSpacing(4)

        self.setup_label(description)
        self.setup_slider(default_value)
        self.setup_animation_handle()

        self.slider.sliderPressed.connect(self.handle_slider_pressed)
        self.slider.sliderReleased.connect(self.handle_slider_released)
        self.slider.valueChanged.connect(self.handle_slider_value_changed)

    def setup_label(self, description: str) -> None:
        self.description_label = QLabel(description)
        self.description_label.setFont(Utils.NType(11))
        self.description_label.setStyleSheet("color: #ddd; padding: 0px; border: none;")

        self.inner_layout.addWidget(self.description_label)

    def setup_slider(self, default_value: int) -> None:
        slider_value_layout = QHBoxLayout()
        slider_value_layout.setContentsMargins(0, 0, 0, 0)
        slider_value_layout.setSpacing(12)

        self.slider = QSlider(Qt.Orientation.Horizontal, self.container_background)
        self.slider.setRange(self.minimum_value, self.maximum_value)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setValue(default_value)
        self.slider.setStyleSheet(Styles.Controls.Slider)

        slider_value_layout.addWidget(self.slider, 1)

        self.value_label = QLabel(str(default_value))
        self.value_label.setFont(Utils.NType(12))
        self.value_label.setStyleSheet("color: #dddddd; padding: 0px; border: none;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        slider_value_layout.addWidget(self.value_label, 0)

        self.inner_layout.addLayout(slider_value_layout)

    def setup_animation_handle(self) -> None:
        self.value_handle = ui_engine.bind(
            owner      = self,
            name       = "sliderValue",
            base_value = self.slider.value(),
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_animated_value_changed
        )

    def on_animated_value_changed(self, value: int) -> None:
        rounded_value = int(round(value))

        self.slider.blockSignals(True)
        self.slider.setValue(rounded_value)
        self.slider.blockSignals(False)

        self.value_label.setText(str(rounded_value))

    def clamp_value(self, value: int) -> int:
        return max(self.minimum_value, min(self.maximum_value, value))

    def handle_slider_pressed(self) -> None:
        self.slider_is_dragging = True
        self.value_handle.stop_targeting()

    def handle_slider_released(self) -> None:
        self.slider_is_dragging = False

    def handle_slider_value_changed(self, value: int) -> None:
        self.value_label.setText(str(value))
        self.valueChanged.emit(value)

        self.target_value       = self.slider.value()

        if not self.slider_is_dragging:
            return

        if self.maximum_value <= self.minimum_value:
            return

        if self.maximum_value >= 30:
            return

        tone = (value - self.minimum_value) / (self.maximum_value - self.minimum_value) + 0.1
        Player.ui_player.play_sound("Click/Toggle2", speed = tone)

    def play_show_animation(self) -> None:
        if self.slider_is_dragging:
            return

        self.value_handle.stop()
        self.value_handle.set_base(self.minimum_value)

        self.value_handle.set_target(
            value           = self.target_value,
            duration_ms     = 450,
            easing_function = Easing.ease_out_quint
        )

    def animate_to_value(self, value: int) -> None:
        self.target_value = self.clamp_value(value)

        if self.slider_is_dragging:
            return

        self.value_handle.set_target(
            value           = self.target_value,
            duration_ms     = 450,
            easing_function = Easing.ease_out_quint
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)

        if not self.show_animation_pending:
            return

        self.show_animation_pending = False
        self.play_show_animation()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)

        self.show_animation_pending = True
        self.slider_is_dragging      = False

        self.value_handle.stop()

    def value(self) -> int:
        return self.target_value

    def setValue(self, value: int | float | str) -> None:
        target_value = self.parse_value(value)
        target_value = self.clamp_value(target_value)

        self.target_value = target_value
        self.value_label.setText(str(target_value))

        if self.isVisible():
            self.animate_to_value(target_value)
            return

        self.slider.blockSignals(True)
        self.slider.setValue(self.minimum_value if self.show_animation_pending else target_value)
        self.slider.blockSignals(False)

    def parse_value(self, value: int | float | str) -> int:
        if isinstance(value, (int, float)):
            return int(value)

        if isinstance(value, str) and value.isdigit():
            return int(value)

        return self.target_value

    def getValueAsText(self) -> str:
        return str(self.value())