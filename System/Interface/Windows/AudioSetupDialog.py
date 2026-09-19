from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout
)

from System.Common    import Constants
from System.Services  import Player
from System.Interface import Widgets

from System.Interface.Windows import BPMEditorBase

# Audio Setup Layout

class AudioSetupDialog(BPMEditorBase):
    def __init__(
            self,
            audio_path: str,
            parent:     QWidget | None = None
        ) -> None:

        self.audio_path     = audio_path
        self.filename       = audio_path.split("/")[-1]
        self.saved_settings = {}
        self.beat_counter   = 0

        super().__init__(
            "Audio",
            parent                     = parent,
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.title_label.setText(self.filename)
        self.setup_audio_layout()
        self.run_loading_pipeline(audio_path)
        self.adjustSize()

    def setup_audio_layout(self) -> None:
        self.setup_trim_section()
        self.setup_bpm_section()
        self.setup_action_buttons("Ok", "Cancel")

        self.ok_button.setMaximumWidth(56)
        self.cancel_button.setMaximumWidth(80)

        self.model_selector = Widgets.Selector(["1", "2", "2a", "3a", "4a", "4b"])
        self.model_selector.setMinimumWidth(240)

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(8)
        settings_layout.addWidget(self.bpm_input)
        settings_layout.addWidget(self.model_selector)
        settings_layout.addStretch()
        settings_layout.addWidget(self.cancel_button)
        settings_layout.addWidget(self.ok_button)

        Player.bpm_informer.beat_16.connect(self.update_title_beat)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(self.build_playback_row())
        self.content_layout.addLayout(settings_layout)

    def toggle_playback(self) -> None:
        if self.player.is_playing:
            self.title_label.setText(self.filename)
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time_sec)

        else:
            self.play_selection()

    def stop_playback(self) -> None:
        super().stop_playback()
        self.beat_counter = 0

    def update_title_beat(self) -> None:
        if not self.player.is_playing:
            return

        current_position_seconds = self.player.get_position() / 1000
        self.title_label.setText(f"{current_position_seconds:.3f}")

        audio_level = self.player.get_current_audio_level()

        if audio_level < 0.03:
            return

        self.beat_counter = (self.beat_counter + 1) % 4

        if self.beat_counter == 0:
            self.pulse_title(peak_scale = 1.4, duration_ms = 200)

        else:
            self.pulse_title(peak_scale = 1.1, duration_ms = 120)

    def really_close(self) -> None:
        Player.bpm_informer.beat_16.disconnect(self.update_title_beat)
        super().really_close()

    def accept_callback(self) -> None:
        if not self.validate_trim():
            self.ok_button.start_glitch()
            return

        self.saved_settings = self.get_settings()
        self.cleanup_audio()

        super().on_ok()

    def get_settings(self) -> dict:
        return {
            "audio": {**self.get_trim_settings(), **self.get_bpm_settings()},
            "model": Constants.NUMBER_TO_CODE[self.model_selector.current_text()]
        }