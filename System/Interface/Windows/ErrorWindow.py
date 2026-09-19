from __future__ import annotations

import json
import random
import platform

from PyQt6.QtCore import QTimer

from PyQt6.QtWidgets import (
    QWidget,
    QApplication
)

from System.Common import Dev

from System.Services import (
    Player,
    Workers
)

from System.Interface import Widgets
from System.Interface.Animation import LoomEngine
from System.Interface.Windows import FloatingWindowGPU

# Error Window

@Dev.track_ram
class ErrorWindow(FloatingWindowGPU):
    def __init__(
            self,
            title:            str,
            description_text: str,
            button_text:      str            = "Cool",
            allow_report:     bool           = False,
            parent:           QWidget | None = None
        ) -> None:

        super().__init__(title, parent = parent)

        self.description_text      = description_text
        self.allow_report          = allow_report
        self.endpoint_url          = "https://cassette-feedback.chips-furs.workers.dev"
        self.request_in_progress   = False
        self.network_worker        = None
        self.transmit_sound        = None
        self.sound_speed_handle    = None
        self.user_action_textbox   = None
        self.inspect_data_button   = None
        self.payload_preview_label = None
        self.pulse_status_widget   = None
        self.button_row_layout     = None
        self.description_label     = None

        self.title_label.start_glitch()

        if not self.allow_report:
            self.setup_simple_mode(button_text)

        else:
            self.setup_report_mode()
            self.setup_audio_animations()
            self.initialize_pulse_idle_state()

    # Simple Mode Setup

    def setup_simple_mode(self, button_text: str) -> None:
        self.description_label = Widgets.DescriptionLabel(self.description_text, 600)
        self.description_label.setMaximumSize(900, 800)

        copy_button = Widgets.ButtonWithOutline("Copy error details")
        ok_button   = Widgets.NothingButton(button_text)

        copy_button.clicked.connect(self.copy_error_details)
        ok_button.clicked.connect(self.on_ok)

        self.content_layout.addWidget(self.description_label)
        self.content_layout.addWidget(copy_button)
        self.content_layout.addWidget(ok_button)

    # Report Mode Setup

    def setup_report_mode(self) -> None:
        self.description_label = Widgets.DescriptionLabel(self.description_text, 600)
        self.description_label.setMaximumSize(900, 400)

        self.user_action_textbox = Widgets.Textbox(
            input_type  = "text",
            max_length  = 500,
            placeholder = "What were you doing when this happened?"
        )

        self.user_action_textbox.textChanged.connect(self.handle_user_action_changed)

        self.inspect_data_button = Widgets.ButtonWithOutline("Inspect data to be sent")
        self.inspect_data_button.clicked.connect(self.toggle_payload_inspection)

        self.payload_preview_label = Widgets.DescriptionLabel("", 600)
        self.payload_preview_label.setMaximumSize(900, 250)
        self.payload_preview_label.setVisible(False)

        self.refresh_payload_preview()

        self.pulse_status_widget = Widgets.PulseStatusWidget(self)
        self.pulse_status_widget.setFixedHeight(40)

        self.button_row_layout = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "Do not report", self.handle_cancel_clicked),
                (Widgets.ButtonWithOutline, "Copy details",  self.copy_error_details),
                (Widgets.NothingButton,     "Send report",   self.handle_send_clicked)
            ]
        )

        self.content_layout.addWidget(self.description_label)
        self.content_layout.addWidget(self.user_action_textbox)
        self.content_layout.addWidget(self.inspect_data_button)
        self.content_layout.addWidget(self.payload_preview_label)
        self.content_layout.addWidget(self.pulse_status_widget)
        self.content_layout.addLayout(self.button_row_layout)

    # Audio Animations

    def setup_audio_animations(self) -> None:
        self.sound_speed_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "transmitSoundSpeed",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.handle_transmit_sound_speed_changed
        )

    def initialize_pulse_idle_state(self) -> None:
        self.pulse_status_widget.flatten_handle.set_base(0.0)
        self.pulse_status_widget.set_amplitude(14.0)

    # Payload Inspector

    def read_application_version(self) -> str:
        with open("version", "r", encoding = "utf-8") as version_file:
            return version_file.read().strip()

    def build_payload_dictionary(self) -> dict:
        user_text = ""

        if self.user_action_textbox is not None:
            raw_text  = self.user_action_textbox.text()
            user_text = str(raw_text).strip() if raw_text else ""

        version_string  = self.read_application_version()
        system_platform = f"{platform.system()} {platform.release()} ({platform.machine()}). Cassette Version: {version_string}"

        text = f"""
An error encountered!

*System Info:* `{system_platform}`

*Error:* ```\n{self.description_text}```

*What user did before the problem:* ```\n{user_text or "No reproduction steps provided"}```"""

        return {
            "text": text
        }

    def refresh_payload_preview(self) -> None:
        formatted_json = json.dumps(
            self.build_payload_dictionary(),
            indent       = 2,
            ensure_ascii = False
        )

        self.payload_preview_label.setText(formatted_json)

    def handle_user_action_changed(self) -> None:
        if not self.payload_preview_label.isVisible():
            return

        self.refresh_payload_preview()

    def toggle_payload_inspection(self) -> None:
        will_be_visible = not self.payload_preview_label.isVisible()

        if will_be_visible:
            self.refresh_payload_preview()
            self.inspect_data_button.setText("Hide data to be sent")

        else:
            self.inspect_data_button.setText("Inspect data to be sent")

        self.payload_preview_label.setVisible(will_be_visible)
        self.adjustSize()

    # Audio Handlers

    def handle_transmit_sound_speed_changed(self, speed_value: float) -> None:
        if self.transmit_sound is None:
            return

        self.transmit_sound.set_speed(speed_value)

    def stop_transmission_sound(self, duration_ms: int = 380) -> None:
        if self.transmit_sound is None:
            return

        self.sound_speed_handle.set_target(
            value           = 0.2,
            duration_ms     = duration_ms,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        QTimer.singleShot(duration_ms, self.cleanup_transmit_sound)

    def cleanup_transmit_sound(self) -> None:
        if self.transmit_sound is None:
            return

        self.transmit_sound.stop()
        self.transmit_sound = None

    # User Actions

    def copy_error_details(self) -> None:
        clipboard = QApplication.clipboard()

        if not self.allow_report:
            clipboard.setText(self.description_label.text())
            return

        serialized_payload = json.dumps(
            self.build_payload_dictionary(),
            indent       = 2,
            ensure_ascii = False
        )

        clipboard.setText(serialized_payload)

    def handle_cancel_clicked(self) -> None:
        if self.request_in_progress:
            return

        self.cleanup_transmit_sound()
        self.reject()

    def handle_send_clicked(self) -> None:
        if not self.user_action_textbox.text():
            self.user_action_textbox.start_glitch()
            return

        if self.request_in_progress:
            return

        self.begin_transmission_state()
        self.dispatch_network_request()

    # Network Dispatching

    def dispatch_network_request(self) -> None:
        payload_dictionary = self.build_payload_dictionary()

        self.network_worker = Workers.NetworkReportWorker(
            endpoint_url       = self.endpoint_url,
            payload_dictionary = payload_dictionary,
            parent             = self
        )

        self.network_worker.request_succeeded.connect(self.handle_request_success)
        self.network_worker.request_failed.connect(self.handle_request_failure)
        self.network_worker.start()

    # State Transitions

    def begin_transmission_state(self) -> None:
        self.request_in_progress = True

        self.button_row_layout.disable_buttons()

        loading_ratio       = 0.4
        initial_sound_speed = 0.0
        target_sound_speed  = 1.0

        self.pulse_status_widget.transition_to_white(duration_ms = 200)
        self.pulse_status_widget.unflatten(duration_ms = 450)
        self.pulse_status_widget.transition_to_sine(duration_ms = 500)
        self.pulse_status_widget.set_loading_speed_ratio(loading_ratio, duration_ms = 500)

        self.transmit_sound = Player.ui_player.play_sound(
            "Feedback/TransmitLoop",
            loop  = True,
            speed = initial_sound_speed
        )

        self.sound_speed_handle.set_base(initial_sound_speed)
        self.sound_speed_handle.set_target(
            value           = target_sound_speed,
            duration_ms     = 750,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    def handle_request_success(self) -> None:
        self.request_in_progress = False

        self.pulse_status_widget.flatten(duration_ms = 400)
        self.stop_transmission_sound(duration_ms = 350)

        QTimer.singleShot(750, self.accept)

    def handle_request_failure(self, failure_reason: str) -> None:
        self.request_in_progress = False

        self.button_row_layout.enable_buttons()

        self.pulse_status_widget.transition_to_red(duration_ms = 250)
        self.pulse_status_widget.set_mode(Widgets.WaveMode.PULSE)
        self.pulse_status_widget.transition_to_pulse()

        self.stop_transmission_sound(duration_ms = 260)

        self.start_shake()
        QTimer.singleShot(260, self.stop_shake)

        Player.ui_player.play_sound("Signals/Error/TransmitFailed")

    # Window Lifecycle

    def open_window(self) -> None:
        if random.random() <= 0.995:
            super().open_window()
            return

        self.adjustSize()
        self.center_window()

        self.is_ready = True

        Player.ui_player.play_sound("Packs/NOK/Death")

        self.title_label.start_glitch(4000)

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.5), (1.0, 1.0)],
            duration_ms     = 12000,
            easing_function = LoomEngine.Easing.ease_out_quart
        )

        self.opacity_content_property.set_base(1.0)

        self.opacity_background_property.play_curve(
            keyframes       = [(0.0, 0.0), (1.0, 1.0)],
            duration_ms     = 3000,
            easing_function = LoomEngine.Easing.linear
        )