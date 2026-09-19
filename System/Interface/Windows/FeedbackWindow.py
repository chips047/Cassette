from __future__ import annotations

import random
import platform

from PyQt6.QtCore import QTimer

from PyQt6.QtWidgets import QWidget

from System.Common import Dev

from System.Services import (
    Player,
    Workers
)

from System.Interface           import Widgets
from System.Interface.Animation import LoomEngine

from .FloatingWindowGPU import FloatingWindowGPU

# Feedback Window

@Dev.track_ram
class FeedbackWindow(FloatingWindowGPU):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title  = "Feedback",
            parent = parent
        )

        self.endpoint_url        = "https://cassette-feedback.chips-furs.workers.dev"
        self.request_in_progress = False
        self.network_worker      = None
        self.transmit_sound      = None

        self.setup_controls()
        self.setup_audio_animations()
        self.initialize_pulse_idle_state()

    # Controls Setup

    def on_rating_changed(self, stars: int) -> None:
        texts = {
            1: [
                "Fuck.",
                "Are you serious?",
                "Emotional damage.",
                "Sad.",
                "Delete me."
            ],

            2: [
                "Mhm.",
                "Could be worse.",
                "Well, that sucks.",
                "At least it launched.",
                "Mid as hell."
            ],

            3: [
                "Interesting.",
                "It works, I guess.",
                "Not great.",
                "Fair enough.",
                "Could be better."
            ],

            4: [
                "Thanks :)",
                "Pretty damn good.",
                "Almost perfect!",
                "Appreciate it!",
                "Now we're talking."
            ],

            5: [
                "No fucking way",
                "LES GOOOOO!",
                "Holy shit.",
                "Can I hug you?",
                "Perfection."
            ]
        }

        options = texts.get(stars, ["Send"])
        self.button_row_layout.get_button_by_number(1).setText(random.choice(options))

    def setup_controls(self) -> None:
        self.star_rating_widget = Widgets.StarRatingWidget(
            initial_rating = 5,
            parent         = self
        )

        self.star_rating_widget.rating_changed.connect(self.on_rating_changed)
        self.star_rating_widget.setMinimumWidth(400)

        self.contact_textbox = Widgets.Textbox(
            input_type  = "text",
            max_length  = 64,
            placeholder = "Telegram / Discord (Optional)"
        )

        self.message_textbox = Widgets.Textbox(
            input_type  = "text",
            max_length  = 500,
            placeholder = "Your thoughts or report."
        )

        self.button_row_layout = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "Cancel",   self.handle_cancel_clicked),
                (Widgets.NothingButton,     "Transmit", self.handle_send_clicked)
            ]
        )

        self.pulse_status_widget = Widgets.PulseStatusWidget(self)
        self.pulse_status_widget.setFixedHeight(40)

        self.content_layout.addWidget(self.star_rating_widget)
        self.content_layout.addWidget(self.contact_textbox)
        self.content_layout.addWidget(self.message_textbox)
        self.content_layout.addWidget(self.pulse_status_widget)
        self.content_layout.addLayout(self.button_row_layout)

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

    # Action Handlers

    def handle_cancel_clicked(self) -> None:
        if self.request_in_progress:
            return

        self.cleanup_transmit_sound()
        self.reject()

    def handle_send_clicked(self) -> None:
        if self.request_in_progress:
            return

        raw_message      = self.message_textbox.text()
        resolved_message = str(raw_message).strip() if raw_message else "No description provided"

        self.begin_transmission_state()
        self.dispatch_network_request(resolved_message)

    # Network Dispatching

    def dispatch_network_request(self, message_content: str) -> None:
        contact_value    = self.contact_textbox.text()
        resolved_contact = str(contact_value).strip() if contact_value else "Anonymous"
        rating_value     = f"{self.star_rating_widget.value()} / 5"

        with open("version", "r", encoding = "utf-8") as version_file:
            application_version = version_file.read().strip()

        system_platform = f"{platform.system()} {platform.release()} ({platform.machine()}). Cassette Version: {application_version}"

        text = f"""
*System Info:* `{system_platform}`
*Rating:* {rating_value}
*From:* {resolved_contact}

```{message_content}```
"""

        payload_dictionary = {
            "text": text
        }

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