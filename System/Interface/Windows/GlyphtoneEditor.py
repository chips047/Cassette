import random

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout
)

from System.Common   import Utils
from System.Services import Encoder

from System.Interface.Windows import AudioEditorBase

# Glyphtone Editor

class GlyphtoneEditor(AudioEditorBase):
    def __init__(
            self,
            audio_path: str,
            parent:     QWidget | None = None
        ) -> None:

        self.audio_path     = audio_path
        self.saved_settings = {}
        self.folder_id      = None

        super().__init__(
            "Glyphtone Editor",
            parent                     = parent,
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.setup_ui()
        self.run_loading_pipeline(audio_path)
        self.adjustSize()

    def setup_ui(self) -> None:
        self.setup_trim_section()
        self.setup_action_buttons("Confirm", "Cancel")

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.cancel_button)
        bottom_layout.addWidget(self.ok_button)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(self.build_playback_row())
        self.content_layout.addLayout(bottom_layout)

    def accept_callback(self) -> None:
        if not self.validate_trim():
            self.ok_button.start_glitch()
            return

        trim = self.get_trim_settings()

        self.saved_settings = {
            **trim,
            "duration": self.trim_widget.end_time_sec - self.trim_widget.start_time_sec
        }

        if self.folder_id is None:
            self.folder_id = random.randint(0, 99999999)

        source        = self.audio_path
        output        = Utils.get_user_path(f"Editor/{self.folder_id}/Cropped.ogg", "Cassette/Songs")
        output_folder = Utils.get_user_path(f"Editor/{self.folder_id}", "Cassette/Songs")

        Encoder.trim_glyphs_ogg(
            source,
            output,
            int(self.saved_settings["start_ms"]),
            int(self.saved_settings["end_ms"]),
            self.fade_in_textbox.text()  or 0,
            self.fade_out_textbox.text() or 0
        )

        self.on_ok()
        Utils.open_file(output_folder)