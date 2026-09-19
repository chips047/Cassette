import os
import math
import random

from pathlib import Path
from loguru  import logger

from PyQt6.QtCore import (
    Qt,
    QSize,
    QTimer,
    QObject,
    QThread
)

from PyQt6.QtGui import (
    QIcon,
    QCloseEvent
)

from PyQt6.QtWidgets import (
    QPushButton,
    QHBoxLayout
)

from System.Common import (
    Styles,
    Constants
)

from System.Services import (
    Player,
    Workers
)

from System.Interface import (
    Timing,
    Widgets
)

from System.Interface.Animation import LoomEngine

from System.Interface.Windows.ErrorWindow       import ErrorWindow
from System.Interface.Windows.FloatingWindowGPU import FloatingWindowGPU

from System.Interface.Windows.Helpers import (
    make_fade_textbox,
    make_time_textbox
)

# Pipeline Execution

class AudioLoadingDialog(FloatingWindowGPU):
    def launch_worker_thread(
            self,
            worker:            QObject,
            finished_callback: object,
            error_callback:    object,
            priority:          QThread.Priority = QThread.Priority.InheritPriority
        ) -> QThread:

        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        worker.finished.connect(finished_callback)
        worker.error.connect(error_callback)

        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start(priority)

        return thread

    def run_loading_pipeline(self, file_path: str) -> None:
        self.cached_wav_path = None
        self.audio_path      = file_path

        self.on_loading_started()

        self.prepare_worker = Workers.PrepareWorker(file_path)
        self.prepare_thread = self.launch_worker_thread(
            self.prepare_worker,
            self.on_prepare_success,
            self.on_load_failed
        )

        self.load_thread = None
        self.load_worker = None

    def on_loading_started(self) -> None:
        pass

    def on_loading_failed(self, message: str) -> None:
        pass

    def on_prepare_success(self, cached_wav_path: str) -> None:
        self.cached_wav_path = cached_wav_path

        self.load_worker = Workers.LoadAudioWorker(self.cached_wav_path)
        self.load_thread = self.launch_worker_thread(
            self.load_worker,
            self.on_load_finished,
            self.on_load_failed,
            QThread.Priority.LowPriority
        )

    def on_load_finished(self, result: tuple) -> None:
        pass

    def on_load_failed(self, message: str) -> None:
        self.on_loading_failed(message)

        window = ErrorWindow("Load Error", message)
        window.destroyed.connect(self.close)
        window.exec()

    def cleanup_threads(self, threads: list[QThread | None]) -> None:
        threads_to_wait = []

        for thread in threads:
            try:
                if not thread or not thread.isRunning():
                    continue

                threads_to_wait.append(thread)
                thread.quit()

            except Exception:
                pass

        if not threads_to_wait:
            self.safe_delete_cache()
            return

        self.wait_and_cleanup(threads_to_wait)

    def wait_and_cleanup(self, threads: list[QThread]) -> None:
        for thread in threads:
            thread.wait(500)

        self.safe_delete_cache()

    def safe_delete_cache(self) -> None:
        if not self.cached_wav_path:
            return

        cached_wav_normalized = str(Path(self.cached_wav_path).resolve())
        audio_path_normalized = str(Path(self.audio_path).resolve()) if self.audio_path else None

        if cached_wav_normalized == audio_path_normalized:
            return

        try:
            if os.path.exists(self.cached_wav_path):
                os.unlink(self.cached_wav_path)
                logger.info(f"Cache deleted: {self.cached_wav_path}")

        except Exception as error:
            logger.warning(f"Could not delete cache yet, retrying... {error}")
            QTimer.singleShot(1000, self.safe_delete_cache)

# Audio Editor Layout

class AudioEditorBase(AudioLoadingDialog):
    def setup_trim_section(self) -> None:
        self.trim_widget        = Widgets.TrimmingWaveformWidget()
        self.start_time_textbox = make_time_textbox()
        self.end_time_textbox   = make_time_textbox()
        self.fade_in_textbox    = make_fade_textbox("Fade in (ms)")
        self.fade_out_textbox   = make_fade_textbox("Fade out (ms)")

        self.play_icon  = QIcon("System/Assets/Icons/Audio/Play.png")
        self.pause_icon = QIcon("System/Assets/Icons/Audio/Pause.png")

        self.play_button = QPushButton()
        self.play_button.setStyleSheet("background-color: transparent; border: none;")
        self.play_button.setIcon(self.play_icon)
        self.play_button.setIconSize(QSize(36, 36))
        self.play_button.setFixedSize(36, 36)
        self.play_button.setEnabled(False)

        self.playback_timer = Timing.Timer(Constants.FPS_60, self.update_playback, parent = self)

        self.trim_widget.regionChanged.connect(self.update_textboxes)
        self.end_time_textbox.safeTextChanged.connect(self.edit_end_time)
        self.start_time_textbox.safeTextChanged.connect(self.edit_start_time)
        self.play_button.clicked.connect(self.toggle_playback)

    def setup_action_buttons(
            self,
            ok_text:     str = "Ok",
            cancel_text: str = "Cancel"
        ) -> None:

        self.cancel_button = Widgets.ButtonWithOutline(cancel_text)
        self.ok_button     = Widgets.NothingButton(ok_text)

        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.close)

    def build_playback_row(self) -> QHBoxLayout:
        row_layout = QHBoxLayout()

        row_layout.addWidget(self.start_time_textbox)
        row_layout.addWidget(self.fade_in_textbox)
        row_layout.addWidget(self.play_button)
        row_layout.addWidget(self.fade_out_textbox)
        row_layout.addWidget(self.end_time_textbox)

        return row_layout

    def on_loading_started(self) -> None:
        self.trim_widget.start_loading()

    def on_loading_failed(self, message: str) -> None:
        self.trim_widget.show_error()

    def on_load_finished(self, result: tuple) -> None:
        try:
            data, sample_rate, waveform_data = result

            self.player.load_audio_from_data(data, sample_rate)
            self.trim_widget.set_data(data, sample_rate, waveform_data)

            self.end_time_textbox.max_number = self.trim_widget.duration_sec
            self.end_time_textbox.setText(max(1, math.ceil(self.trim_widget.duration_sec)))

            self.update_textboxes(self.trim_widget.start_time_sec, self.trim_widget.end_time_sec)

            self.play_button.setEnabled(True)
            self.on_audio_ready()

        except Exception as error:
            self.trim_widget.show_error()
            ErrorWindow("Load Error", str(error)).exec()

    def on_audio_ready(self) -> None:
        self.ok_button.setEnabled(True)

    def update_textboxes(
            self,
            start: float,
            end:   float
        ) -> None:

        self.start_time_textbox.blockSignals(True)
        self.end_time_textbox.blockSignals(True)

        self.start_time_textbox.setText(int(round(start)))
        self.end_time_textbox.setText(max(1, int(round(end))))

        self.start_time_textbox.blockSignals(False)
        self.end_time_textbox.blockSignals(False)

        self.start_time_textbox.max_number = int(round(end - 1))
        self.end_time_textbox.min_number   = int(round(start))

    def edit_start_time(self) -> None:
        start_seconds = self.start_time_textbox.text()

        if not start_seconds:
            return

        self.trim_widget.set_playback_position(start_seconds)
        self.trim_widget.start_time_sec = start_seconds
        self.trim_widget.update()

        self.end_time_textbox.min_number = start_seconds

    def edit_end_time(self) -> None:
        end_seconds   = self.end_time_textbox.text()
        start_seconds = self.start_time_textbox.text()

        if end_seconds is None or start_seconds is None:
            return

        if start_seconds >= end_seconds:
            return

        self.trim_widget.set_playback_position(start_seconds)
        self.trim_widget.end_time_sec = end_seconds
        self.trim_widget.update()

        self.start_time_textbox.max_number = end_seconds - 1

    def toggle_playback(self) -> None:
        if self.player.is_playing:
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time_sec)

        else:
            self.play_selection()

    def play_selection(self) -> None:
        current_position = self.trim_widget.playback_position

        if not (self.trim_widget.start_time_sec <= current_position < self.trim_widget.end_time_sec):
            current_position = self.trim_widget.start_time_sec
            self.trim_widget.set_playback_position(current_position)

        self.player.play(current_position * 1000)
        self.play_button.setIcon(self.pause_icon)
        self.trim_widget.set_is_playing(True)
        self.playback_timer.start()

    def stop_playback(self) -> None:
        self.player.stop()
        self.play_button.setIcon(self.play_icon)
        self.trim_widget.set_is_playing(False)
        self.playback_timer.stop()

    def update_playback(self) -> None:
        if not self.player.is_playing:
            self.trim_widget.set_playback_position(0)
            self.stop_playback()
            return

        current_position_ms = self.player.get_position()

        if current_position_ms > self.trim_widget.end_time_sec * 1000:
            self.trim_widget.set_playback_position(self.trim_widget.start_time_sec)
            self.toggle_playback()
            return

        self.trim_widget.set_playback_position(current_position_ms / 1000)

    def validate_trim(self) -> bool:
        if self.end_time_textbox.is_not_valid() or not self.end_time_textbox.text():
            self.end_time_textbox.start_glitch(False)
            return False

        if self.start_time_textbox.text() is None:
            self.start_time_textbox.start_glitch(False)
            return False

        return True

    def get_trim_settings(self) -> dict:
        return {
            "start_ms": self.trim_widget.start_time_sec * 1000,
            "end_ms":   self.trim_widget.end_time_sec   * 1000,
            "fade_in":  self.fade_in_textbox.text(),
            "fade_out": self.fade_out_textbox.text()
        }

    def get_threads(self) -> list[QThread | None]:
        return [self.prepare_thread, self.load_thread]

    def cleanup_audio(self) -> None:
        self.playback_timer.stop()
        self.trim_widget.audio_data = None

        if self.player.is_playing:
            self.player.set_speed(0.0, 3000)

        self.cleanup_threads(self.get_threads())

        self.prepare_worker = None
        self.load_worker    = None
        self.prepare_thread = None
        self.load_thread    = None

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cleanup_audio()
        super().on_cancel()
        super().closeEvent(event)

# BPM Editor Layout

class BPMEditorBase(AudioEditorBase):
    def setup_bpm_section(self) -> None:
        self.bpm_thread   = None
        self.bpm_worker   = None
        self.detected_bpm = None

        self.bpm_text              = ""
        self.bpm_number_string     = ""
        self.bpm_animation_target  = None
        self.bpm_animation_current = 120
        self.snapped_times         = None

        self.bpm_input = Widgets.Textbox("number", 1, 400, placeholder = "Counting BPM... 120")
        self.bpm_input.setMaximumWidth(176)
        self.bpm_input.setFixedHeight(Styles.Metrics.ElementHeight)
        self.bpm_input.setStyleSheet(Styles.Controls.FloatingTextBoxRound)

        self.bpm_animation_timer = Timing.Timer(
            Constants.FPS_30,
            self.animate_bpm_spinbox,
            auto_start = True,
            parent     = self
        )

        self.bpm_remove_timer = Timing.Timer(
            0,
            self.bpm_remove_step,
            parent = self
        )

        if self.animations_active:
            self.bpm_textbox_width = LoomEngine.ui_engine.bind(
                owner      = self,
                name       = "bpmTextboxWidth",
                base_value = self.bpm_input.width(),
                mix_mode   = LoomEngine.MixMode.REPLACE,
                on_change  = self.bpm_input.setFixedWidth
            )

        self.bpm_input.safeTextChanged.connect(self.on_bpm_changed)

    def on_prepare_success(self, cached_wav_path: str) -> None:
        super().on_prepare_success(cached_wav_path)
        self.start_bpm_pipeline()

    def is_bpm_thread_running(self) -> bool:
        try:
            return bool(self.bpm_thread and self.bpm_thread.isRunning())

        except RuntimeError:
            return False

    def start_bpm_pipeline(self) -> None:
        self.bpm_worker = Workers.BPMWorker(self.cached_wav_path)
        self.bpm_thread = self.launch_worker_thread(
            self.bpm_worker,
            self.on_bpm_finished,
            self.on_bpm_failed,
            QThread.Priority.LowPriority
        )

    def on_bpm_failed(self, message: str) -> None:
        ErrorWindow("BPM error", message).exec()

    def on_bpm_finished(
            self,
            bpm:   float,
            peaks: list | None
        ) -> None:

        try:
            self.bpm_ready(bpm, peaks)

        except Exception as error:
            ErrorWindow("BPM Error", str(error)).exec()

    def bpm_ready(
            self,
            bpm:           float,
            snapped_times: list | None
        ) -> None:

        self.snapped_times = snapped_times
        self.bpm_animation_timer.stop()

        if not bpm:
            self.bpm_text          = "Counting BPM FAILURE"
            self.bpm_number_string = ""

            self.bpm_input.setPlaceholderText(self.bpm_text)
            self.bpm_remove_timer.start(100)

            if random.randint(1, 500) == 500:
                Player.ui_player.play_sound("Packs/NOK/Gambling")

            return

        bpm_value              = round(bpm)
        self.detected_bpm      = bpm_value
        self.bpm_text          = "Counting BPM "
        self.bpm_number_string = str(bpm_value)

        self.bpm_input.setPlaceholderText(f"{self.bpm_text}{self.bpm_number_string}")

        remove_interval = round(60000 / bpm / 8)
        self.bpm_remove_timer.start(remove_interval)

    def get_perfect_bpm_width(self) -> int:
        text       = str(self.bpm_input.text() or self.bpm_input.placeholderText() or "BPM")
        metrics    = self.bpm_input.fontMetrics()
        text_width = metrics.horizontalAdvance(text)

        return round(text_width + 33)

    def shrink_bpm_input(self) -> None:
        if not self.animations_active:
            return

        self.bpm_textbox_width.set_target(
            value           = self.get_perfect_bpm_width(),
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        QTimer.singleShot(270, self.on_bpm_animation_end)

    def on_bpm_animation_end(self) -> None:
        self.bpm_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def animate_bpm_spinbox(self) -> None:
        if not self.bpm_animation_target or self.bpm_animation_current == self.bpm_animation_target:
            self.bpm_animation_target = random.randint(60, 180)

        if self.bpm_animation_current < self.bpm_animation_target:
            self.bpm_animation_current += 1

        elif self.bpm_animation_current > self.bpm_animation_target:
            self.bpm_animation_current -= 1

        self.bpm_input.setPlaceholderText(f"Counting BPM {self.bpm_animation_current}")

    def finalize_bpm_placeholder(self) -> None:
        if self.bpm_number_string:
            self.bpm_input.setText(self.bpm_number_string)

        self.bpm_input.setPlaceholderText("BPM")

    def bpm_remove_step(self) -> None:
        if self.bpm_text:
            self.bpm_text = self.bpm_text[1:]
            self.bpm_input.setPlaceholderText(f"{self.bpm_text}{self.bpm_number_string}")
            return

        self.bpm_remove_timer.stop()
        
        self.finalize_bpm_placeholder()
        self.shrink_bpm_input()

    def on_bpm_changed(self, value: int | str) -> None:
        if not value or int(value) < 1:
            return

        Player.bpm_informer.set_bpm(int(value))

    def get_bpm_value(self) -> int:
        return int(self.bpm_input.text() or 120)

    def get_bpm_settings(self) -> dict:
        return {
            "bpm":   self.get_bpm_value(),
            "beats": self.snapped_times
        }

    def get_threads(self) -> list[QThread | None]:
        return [*super().get_threads(), self.bpm_thread]

    def cleanup_audio(self) -> None:
        self.bpm_animation_timer.stop()
        self.bpm_remove_timer.stop()

        super().cleanup_audio()

        self.bpm_worker = None
        self.bpm_thread = None