import random
import mimetypes

from PyQt6.QtGui import (
    QDropEvent,
    QDragEnterEvent
)

from PyQt6.QtWidgets import (
    QWidget,
    QFileDialog,
    QHBoxLayout
)

from System.Services import (
    Player,
    Encoder
)

from System.Interface import Widgets

from System.Interface.Windows import (
    ErrorWindow,
    BPMEditorBase
)

# Import Window Layout

class ImportWindow(BPMEditorBase):
    def __init__(self, parent: QWidget | None = None) -> None:
        self.audio_path      = None
        self.save_path       = None
        self.cached_wav_path = None

        self.prepare_thread  = None
        self.load_thread     = None

        self.drag_loop_sound = None

        super().__init__(
            "Import",
            parent                     = parent,
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.setAcceptDrops(True)

        self.setup_import_ui()
        self.adjustSize()

    def setup_import_ui(self) -> None:
        self.setup_trim_section()
        self.setup_bpm_section()
        self.setup_action_buttons("Import!", "Later, gator")

        self.audio_path_button = Widgets.ButtonWithOutlineSlim("Audiofile")
        self.save_path_button  = Widgets.ButtonWithOutlineSlim("Savefile")

        for button in [self.audio_path_button, self.save_path_button]:
            button.setMinimumWidth(240)
            button.block_glitch_sound()

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(self.audio_path_button)
        path_row.addWidget(self.save_path_button)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addWidget(self.bpm_input)
        bottom_row.addStretch()
        bottom_row.addWidget(self.cancel_button)
        bottom_row.addWidget(self.ok_button)

        playback_row = self.build_playback_row()

        self.audio_path_button.pressed.connect(self.ask_for_audio)
        self.save_path_button.pressed.connect(self.ask_for_savefile)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(path_row)
        self.content_layout.addLayout(playback_row)
        self.content_layout.addLayout(bottom_row)

    def ask_for_file(
            self,
            types:     list[str],
            type_name: str
        ) -> str | None:

        options   = QFileDialog.Option.ReadOnly
        file_path = None

        dialog = QFileDialog(
            self,
            "Open Audio File",
            "",
            f"{type_name} ({' '.join(types)});;All Files (*)"
        )

        dialog.setOptions(options)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            file_path = dialog.selectedFiles()[0]

        return file_path

    def ask_for_audio(self) -> None:
        file_path = self.ask_for_file(
            [
                "*.wav", "*.mp3", "*.ogg",
                "*.flac", "*.opus", "*.mp4",
                "*.mkv", "*.mov"
            ],
            "Audiofile"
        )

        if not file_path:
            return

        self.audio_path = file_path
        self.audio_path_button.setText(file_path.split("/")[-1])

        self.run_loading_pipeline(file_path)

    def ask_for_savefile(self) -> None:
        file_path = self.ask_for_file(
            ["*.json", "*.txt"],
            "BNGC Save File or Labels File"
        )

        if not file_path:
            return

        self.save_path = file_path
        self.save_path_button.setText(file_path.split("/")[-1])

        self.refresh_import_button()

    def on_audio_ready(self) -> None:
        self.refresh_import_button()

    def refresh_import_button(self) -> None:
        self.ok_button.setEnabled(
            self.audio_path is not None and
            self.save_path is not None
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        Player.ui_player.play_sound(
            "DragDrop/DragDrop",
            speed       = 1.03,
            setting_key = "drag_drop_sounds"
        )

        if not self.drag_loop_sound:
            self.drag_loop_sound = Player.ui_player.play_sound(
                "DragDrop/Loop",
                loop        = True,
                setting_key = "drag_drop_sounds"
            )

        self.move_start_animation()
        self.start_shake()
        
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: object) -> None:
        Player.ui_player.play_sound(
            "DragDrop/DragDrop",
            speed       = 0.94,
            setting_key = "drag_drop_sounds"
        )

        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        self.move_end_animation()
        self.stop_shake()

    def dropEvent(self, event: QDropEvent) -> None:
        Player.ui_player.play_sound(
            "DragDrop/DragDrop",
            speed       = 0.94,
            setting_key = "drag_drop_sounds"
        )

        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        found_valid_file = False

        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            mime_type = mimetypes.guess_type(file_path)[0]

            if not mime_type:
                continue

            is_audio_video = "audio" in mime_type or "video" in mime_type
            is_save_file   = mime_type in ["text/plain", "application/json"]

            if is_audio_video:
                self.audio_path = file_path
                self.audio_path_button.setText(file_path.split("/")[-1])

                self.run_loading_pipeline(file_path)
                found_valid_file = True

            elif is_save_file:
                self.save_path = file_path
                self.save_path_button.setText(file_path.split("/")[-1])

                self.refresh_import_button()
                found_valid_file = True

        if not found_valid_file:
            Player.ui_player.play_sound("Signals/Error/MegaCritical")
            self.title_label.setText(
                random.choice(
                    [
                        "Uhhm, no.",
                        "Huh?",
                        "How do I read that?",
                        "That's not music or video.",
                        "I only eat audio and video files.",
                        "Nice try, but no.",
                        "Wrong tape.",
                        "Unsupported format.",
                        "Maybe try a .wav or .mp4?"
                    ]
                )
            )

        else:
            self.title_label.setText("Import")

        self.move_end_animation()
        self.stop_shake()
        self.refresh_import_button()

    def accept_callback(self) -> None:
        if not self.validate_trim():
            self.ok_button.start_glitch()
            return

        try:
            model, glyphs = Encoder.convert_to_glyphs(
                self.save_path,
                int(self.trim_widget.start_time_sec * 1000),
                int(self.trim_widget.end_time_sec * 1000)
            )

        except Encoder.ZeroGlyphsError:
            ErrorWindow("No glyphs?", "The save file doesn't contain any valid glyphs. File may be corrupted.").exec()
            return

        except Encoder.LabelsNoModelError:
            ErrorWindow("Woops.", "Unable to determine the model from the save file. File may be corrupted.").exec()
            return

        except Encoder.UnknownFileFormatError:
            ErrorWindow("Woops.", "Unknown file format. Make sure you are importing a valid save file.").exec()
            return

        bpm_settings = self.get_bpm_settings()

        self.saved_settings = {
            "model": model,
            "audio": {
                "bpm":      bpm_settings["bpm"],
                "beats":    bpm_settings["beats"],
                "start_ms": self.trim_widget.start_time_sec * 1000,
                "end_ms":   self.trim_widget.end_time_sec   * 1000,
                "fade_in":  self.fade_in_textbox.text(),
                "fade_out": self.fade_out_textbox.text()
            },
            "glyphs": glyphs
        }

        self.cleanup_audio()
        super().on_ok()