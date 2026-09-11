import time
import random

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QTimer,
    QObject
)

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QApplication
)

from System.Common import Dev
from System.Services import Player
from System.Interface import Widgets

@Dev.track_ram
class DelaySetupper(Widgets.BaseControlContainer):
    metronome_bpm:      int = 120

    warmup_tap_count:   int = 3
    required_tap_count: int = 6

    def __init__(
            self,
            description: str,
            default_ms:  int = 0
        ) -> None:

        super().__init__(inner_layout_type = QHBoxLayout)

        self.beat_interval_ms   = 60000.0 / self.metronome_bpm

        self.is_calibrating     = False
        self.tap_timestamps     = []
        self.actual_click_times = []

        self.beat_timer = QTimer(self)
        self.beat_timer.setInterval(int(self.beat_interval_ms))
        self.beat_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.beat_timer.timeout.connect(self.play_click)

        self.setup_ui(description, default_ms)

    def setup_ui(
            self,
            description: str,
            default_ms:  int
        ) -> None:

        self.inner_layout.setContentsMargins(10, 10, 10, 10)
        self.inner_layout.setSpacing(10)

        self.label            = Widgets.DescriptionLabel(description)
        self.delay_textbox    = Widgets.Textbox(
            input_type   = "number",
            min_number   = 0,
            max_number   = 1000,
            default_text = str(default_ms)
        )

        self.delay_textbox.setFixedSize(60, 40)
        self.delay_textbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.reset_button     = Widgets.ButtonWithOutline("Reset")
        self.calibrate_button = Widgets.ButtonWithOutline("Calibrate")

        self.reset_button.setMinimumWidth(80)
        self.reset_button.clicked.connect(self.reset_delay)

        self.calibrate_button.setMinimumWidth(140)
        self.calibrate_button.clicked.connect(self.toggle_calibration)

        self.inner_layout.addWidget(self.label)
        self.inner_layout.addStretch()
        self.inner_layout.addWidget(self.delay_textbox)
        self.inner_layout.addWidget(self.reset_button)
        self.inner_layout.addWidget(self.calibrate_button)

    def play_click(self) -> None:
        self.actual_click_times.append(time.time() * 1000.0)
        Player.player.play(0.0)

    # Calibration

    def reset_delay(self) -> None:
        if self.current_value() == 0:
            self.reset_button.start_glitch()
            self.delay_textbox.start_glitch(sound = False)

            return

        self.delay_textbox.start_glitch(
            duration_ms = 580,
            interval_ms = 70,
            wiggle      = True,
            sound       = False
        )

        QTimer.singleShot(580, self.on_delay_reset)
        Player.ui_player.play_sound("Signals/Success/DelayFound")

    def on_delay_reset(self) -> None:
        self.delay_textbox.setText("0")
        self.on_delay_set()

    def toggle_calibration(self) -> None:
        if self.is_calibrating:
            self.stop_calibration()
            self.calibrate_button.setText("Calibrate")

            return

        self.start_calibration()

    def start_calibration(self) -> None:
        self.is_calibrating     = True
        self.tap_timestamps     = []
        self.actual_click_times = []

        self.calibrate_button.setText("Press Space")

        Player.player.load_audio("System/Assets/Sounds/Feedback/DelayTick.wav")

        self.play_click()
        self.beat_timer.start()

        QApplication.instance().installEventFilter(self)

    def stop_calibration(self) -> None:
        if not self.is_calibrating:
            return

        self.is_calibrating = False
        self.calibrate_button.clearFocus()

        QApplication.instance().removeEventFilter(self)

        self.beat_timer.stop()
        Player.player.stop()

    def eventFilter(
            self,
            watched: QObject,
            event:   QEvent
        ) -> bool:

        if not self.is_calibrating:
            return super().eventFilter(watched, event)

        if event.type() != QEvent.Type.KeyPress or event.key() != Qt.Key.Key_Space:
            return super().eventFilter(watched, event)

        self.register_tap()

        return True

    def register_tap(self) -> None:
        timestamp = time.time() * 1000.0

        if self.tap_timestamps and (timestamp - self.tap_timestamps[-1]) < 250:
            self.stop_calibration()

            self.calibrate_button.setText(
                random.choice(
                    [
                        "Too fast",
                        "Slow down",
                        "Too quick",
                        "Ease up"
                    ]
                )
            )

            self.calibrate_button.start_glitch()

            return

        self.tap_timestamps.append(timestamp)
        self.calibrate_button.animate_punch()

        if random.random() > 0.995:
            self.calibrate_button.setText("Good boy.")

        else:
            self.calibrate_button.setText(
                random.choice(
                    [
                        "Tap",
                        "More",
                        "Even more",
                        "Click",
                        "Press",
                        "Yo",
                        "Good",
                        "Perfect"
                    ]
                )
            )

        if len(self.tap_timestamps) < self.warmup_tap_count + self.required_tap_count:
            return

        self.finish_calibration()

    def finish_calibration(self) -> None:
        offset_ms = self.calculate_average_offset()

        self.stop_calibration()

        if offset_ms is None:
            return

        clamped_offset_ms = max(0, min(1000, offset_ms))

        self.delay_textbox.setText(str(clamped_offset_ms))
        self.delay_textbox.start_glitch(
            duration_ms = 580,
            interval_ms = 70,
            wiggle      = True,
            sound       = False
        )

        self.calibrate_button.setText("Calibrated")

        QTimer.singleShot(580, self.on_delay_set)
        Player.ui_player.play_sound("Signals/Success/DelayFound")

    def on_delay_set(self) -> None:
        self.delay_textbox.pulse_scale(1.5, 200)
        Player.ui_player.play_sound("Signals/Success/DelayFoundFinal")

    def calculate_average_offset(self) -> int | None:
        relevant_taps = self.tap_timestamps[self.warmup_tap_count :]

        if not relevant_taps:
            return None

        offsets = []

        bias_shift = self.beat_interval_ms * 0.35

        for tap_time_ms in relevant_taps:
            biased_tap = tap_time_ms - bias_shift

            closest_click = min(
                self.actual_click_times,
                key = lambda click: abs(biased_tap - click)
            )

            offsets.append(tap_time_ms - closest_click)

        offsets.sort()

        trim_count = max(1, len(offsets) // 5)

        if len(offsets) > trim_count * 2:
            offsets = offsets[trim_count : -trim_count]

        return int(sum(offsets) / len(offsets))

    # Value

    def current_value(self) -> int:
        value = self.delay_textbox.text()

        if value is None:
            return 0

        return int(value)