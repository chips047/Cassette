import os
import re

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout
)

from System.Services import (
    Player,
    ProjectSaver
)

from System.Interface import Widgets

from System.Interface.Windows import TrimWarningDialog
from System.Interface.Windows import BPMEditorBase

# Existing Audio Setup Dialog

class ExistingAudioSetupDialog(BPMEditorBase):
    def __init__(
            self,
            composition: ProjectSaver.Composition,
            parent:      QWidget | None = None
        ) -> None:
        
        self.composition    = composition
        self.audio_path     = composition.full_song_path
        self.filename       = os.path.basename(self.audio_path)
        self.saved_settings = {}

        super().__init__(
            "Audio",
            parent                     = parent,
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.title_label.setText(self.filename)
        self.setup_audio_layout()
        self.run_loading_pipeline(self.audio_path)
        self.adjustSize()

    def setup_audio_layout(self) -> None:
        self.setup_trim_section()
        self.setup_bpm_section()
        self.setup_action_buttons("Ok", "Cancel")

        self.ok_button.setMaximumWidth(56)
        self.cancel_button.setMaximumWidth(80)

        self.auto_bpm_button = Widgets.ButtonWithOutline("Auto")
        self.auto_bpm_button.setMaximumWidth(80)
        self.auto_bpm_button.clicked.connect(self.on_auto_detect_bpm)

        bpm_layout = QHBoxLayout()
        bpm_layout.setSpacing(8)
        bpm_layout.addWidget(self.bpm_input)
        bpm_layout.addWidget(self.auto_bpm_button)

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(8)
        settings_layout.addLayout(bpm_layout)
        settings_layout.addStretch()
        settings_layout.addWidget(self.cancel_button)
        settings_layout.addWidget(self.ok_button)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(self.build_playback_row())
        self.content_layout.addLayout(settings_layout)

    def on_auto_detect_bpm(self) -> None:
        if self.detected_bpm is not None:
            self.bpm_input.setText(str(self.detected_bpm))
            Player.bpm_informer.set_bpm(self.detected_bpm)
            return

        if self.is_bpm_thread_running():
            return

        self.bpm_input.setText("")
        self.bpm_input.setPlaceholderText("Counting BPM...")
        self.start_bpm_pipeline()

    def on_audio_ready(self) -> None:
        super().on_audio_ready()

        current_start = float(self.composition.start_ms or 0) / 1000.0
        current_end   = float(self.composition.end_ms) / 1000.0 if self.composition.end_ms is not None else self.trim_widget.duration_sec

        self.trim_widget.set_times(current_start, current_end)
        self.update_textboxes(current_start, current_end)

        self.fade_in_textbox.setText(str(self.composition.fade_in_duration or 0))
        self.fade_out_textbox.setText(str(self.composition.fade_out_duration or 0))

        if self.composition.bpm:
            self.bpm_input.setText(str(self.composition.bpm))
            Player.bpm_informer.set_bpm(int(self.composition.bpm))

    def get_bpm_value(self) -> int:
        bpm_text = str(self.bpm_input.text() or "").strip()

        if bpm_text.isdigit():
            return int(bpm_text)

        placeholder = str(self.bpm_input.placeholderText() or "")
        digits      = re.findall(r"(\d+)", placeholder)

        if digits:
            return int(digits[-1])

        return int(self.composition.bpm or 120)

    def accept_callback(self) -> None:
        if not self.validate_trim():
            self.ok_button.start_glitch()
            return

        trim = self.get_trim_settings()

        removed_glyph_count = self.composition.count_glyphs_outside_range(
            int(trim["start_ms"]),
            int(trim["end_ms"])
        )

        if removed_glyph_count > 0:
            if not TrimWarningDialog(removed_glyph_count).exec():
                return

        self.saved_settings = {
            **trim,
            **self.get_bpm_settings()
        }

        self.cleanup_audio()
        super().on_ok()