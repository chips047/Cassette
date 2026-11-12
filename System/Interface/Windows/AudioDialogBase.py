from __future__ import annotations

import os
import math
import random

from pathlib import Path
from loguru  import logger

from PyQt6.QtCore import (
    Qt,
    QSize,
    QEvent,
    QTimer,
    QObject,
    QThread
)

from PyQt6.QtGui import (
    QIcon,
    QKeyEvent,
    QShowEvent,
    QCloseEvent
)

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton
)

from System.Common import (
    Utils,
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

from System.Interface.Animation           import LoomEngine
from System.Interface.Windows.ErrorWindow import ErrorWindow
from System.Interface.Windows.Helpers     import (
    make_fade_textbox,
    make_time_textbox
)

from System.Interface.Windows.FloatingWindowGPU import FloatingWindowGPU

# Pipeline

class AudioLoadingDialog(FloatingWindowGPU):
    def launch_worker_thread(
            self,
            worker:            QObject,
            finished_callback: object,
            error_callback:    object,
            priority:          QThread.Priority = QThread.Priority.LowPriority
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

    # Pipeline

    def run_loading_pipeline(
            self,
            file_path: str
        ) -> None:

        self.cached_wav_path = None
        self.audio_path      = file_path

        self.player.emergency_stop(600)
        self.on_loading_started()

        self.prepare_worker = Workers.PrepareWorker(file_path)
        self.prepare_thread = self.launch_worker_thread(
            self.prepare_worker,
            self.on_prepare_success,
            self.on_load_failed,
            QThread.Priority.LowPriority
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

    def is_thread_running(self, thread: QThread | None) -> bool:
        if not thread:
            return False

        try:
            return thread.isRunning()

        except RuntimeError:
            return False

    def cleanup_threads(self, threads: list[QThread | None]) -> None:
        threads_to_wait = []

        for thread in threads:
            if not self.is_thread_running(thread):
                continue

            try:
                thread.quit()
                threads_to_wait.append(thread)

            except RuntimeError:
                pass

        if not threads_to_wait:
            self.safe_delete_cache()

            return

        self.wait_and_cleanup(threads_to_wait)

    def wait_and_cleanup(self, threads: list[QThread]) -> None:
        for thread in threads:
            try:
                thread.wait(500)

            except RuntimeError:
                pass

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

# Audio Editor

class AudioEditorBase(AudioLoadingDialog):
    def setup_trim_section(self) -> None:
        self.is_cleaning_up     = False
        self.trim_widget        = Widgets.TrimmingWaveformWidget()

        self.start_time_textbox = make_time_textbox()
        self.end_time_textbox   = make_time_textbox()
        self.fade_in_textbox    = make_fade_textbox("Fade in (ms)")
        self.fade_out_textbox   = make_fade_textbox("Fade out (ms)")

        self.fade_in_selector   = Widgets.Selector(["Fade", "Filter", "Speed"], default_index = 0)
        self.fade_out_selector  = Widgets.Selector(["Speed", "Filter", "Fade"], default_index = 2)

        self.configure_compact_selector(self.fade_in_selector)
        self.configure_compact_selector(self.fade_out_selector)

        self.start_time_textbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.end_time_textbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fade_out_textbox.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.play_icon  = QIcon("System/Assets/Icons/Audio/Play.png")
        self.pause_icon = QIcon("System/Assets/Icons/Audio/Pause.png")

        self.play_button = QPushButton()
        self.play_button.setStyleSheet("background-color: transparent; border: none;")
        self.play_button.setIcon(self.play_icon)
        self.play_button.setIconSize(QSize(36, 36))
        self.play_button.setFixedSize(36, 36)
        self.play_button.setEnabled(False)
        self.play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.playback_timer = Timing.Timer(
            interval    = Constants.FPS_60,
            callback    = self.update_playback,
            parent      = self,
            fps_managed = True
        )

        self.trim_widget.regionChanged.connect(self.update_textboxes)
        self.end_time_textbox.safeTextChanged.connect(self.edit_end_time)
        self.start_time_textbox.safeTextChanged.connect(self.edit_start_time)
        self.fade_in_selector.selectionChanged.connect(self.on_effect_selector_changed)
        self.fade_out_selector.selectionChanged.connect(self.on_effect_selector_changed)
        self.play_button.clicked.connect(self.toggle_playback)

    def configure_compact_selector(
            self,
            selector: Widgets.Selector,
            width_px: int = 180
        ) -> None:

        selector_font = Utils.NType(10)

        selector.setFont(selector_font)
        selector.setFixedWidth(width_px)
        selector.setFixedHeight(32)

        selector.strip.setFixedWidth(width_px)
        selector.strip.setFixedHeight(32)

    def setup_action_buttons(
            self,
            ok_text:     str = "Ok",
            cancel_text: str = "Cancel"
        ) -> None:

        self.cancel_button = Widgets.ButtonWithOutline(cancel_text)
        self.ok_button     = Widgets.NothingButton(ok_text)

        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.on_cancel)

    def build_playback_row(self) -> QHBoxLayout:
        row_layout = QHBoxLayout()

        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        center = Qt.AlignmentFlag.AlignVCenter

        row_layout.addWidget(self.start_time_textbox, 0, center)
        row_layout.addWidget(self.fade_in_selector,   0, center)
        row_layout.addWidget(self.fade_in_textbox,    0, center)
        row_layout.addWidget(self.play_button,        0, center)
        row_layout.addWidget(self.fade_out_textbox,   0, center)
        row_layout.addWidget(self.fade_out_selector,  0, center)
        row_layout.addWidget(self.end_time_textbox,   0, center)

        return row_layout

    def on_loading_started(self) -> None:
        self.trim_widget.start_loading()

    def on_loading_failed(self, message: str) -> None:
        self.trim_widget.show_error()

    def on_load_finished(self, result: tuple) -> None:
        try:
            if len(result) == 4:
                data, sample_rate, waveform_data, peak_amplitude = result

            else:
                data, sample_rate, waveform_data = result
                peak_amplitude = None

            def on_audio_ready_callback() -> None:
                Player.ui_player.play_sound("Alerts/AudioLoaded")
                self.trim_widget.set_data(data, sample_rate, waveform_data)

                self.end_time_textbox.max_number = self.trim_widget.duration_sec
                self.end_time_textbox.setText(max(1, math.ceil(self.trim_widget.duration_sec)))

                self.update_textboxes(self.trim_widget.start_time_sec, self.trim_widget.end_time_sec)

                self.play_button.setEnabled(True)
                self.on_audio_ready()

            self.player.load_audio_from_data(
                data           = data,
                sample_rate    = sample_rate,
                on_ready       = on_audio_ready_callback,
                peak_amplitude = peak_amplitude
            )

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

        self.trim_widget.set_playback_position(start_seconds, animate = True)
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

        self.trim_widget.set_playback_position(start_seconds, animate = True)
        self.trim_widget.end_time_sec = end_seconds
        self.trim_widget.update()

        self.start_time_textbox.max_number = end_seconds - 1

    def on_effect_selector_changed(self, *arguments: object) -> None:
        if not self.player.is_playing:
            return

        current_position_ms = self.player.get_position()
        self.apply_preview_effects(current_position_ms, force = True)

    def reset_preview_effects(self) -> None:
        self.player.set_volume(1.0, duration_ms = 0)
        self.player.set_speed(1.0, duration_ms = 0, update_base = False)
        self.player.set_passes([], mix = 0.0, duration_ms = 0)

    def apply_preview_effects(
            self,
            position_ms: float,
            force:       bool = False
        ) -> None:

        start_ms = self.trim_widget.start_time_sec * 1000.0
        end_ms   = self.trim_widget.end_time_sec   * 1000.0

        elapsed_ms   = max(0.0, position_ms - start_ms)
        remaining_ms = max(0.0, end_ms - position_ms)

        fade_in_ms  = float(self.fade_in_textbox.text()  or 0)
        fade_out_ms = float(self.fade_out_textbox.text() or 0)

        fade_in_type  = self.fade_in_selector.current_text().lower()
        fade_out_type = self.fade_out_selector.current_text().lower()

        volume = 1.0

        if fade_in_type == "fade" and fade_in_ms > 0 and elapsed_ms < fade_in_ms:
            volume *= (elapsed_ms / fade_in_ms)

        if fade_out_type == "fade" and fade_out_ms > 0 and remaining_ms < fade_out_ms:
            volume *= (remaining_ms / fade_out_ms)

        target_volume = max(0.0, min(1.0, volume))
        self.player.set_volume(target_volume, duration_ms = 0)

        filter_in  = 0.0
        filter_out = 0.0

        if fade_in_type == "filter" and fade_in_ms > 0 and elapsed_ms < fade_in_ms:
            filter_in = 1.0 - (elapsed_ms / fade_in_ms)

        if fade_out_type == "filter" and fade_out_ms > 0 and remaining_ms < fade_out_ms:
            filter_out = 1.0 - (remaining_ms / fade_out_ms)

        filter_factor = max(filter_in, filter_out)

        if filter_factor > 0.01:
            cutoff_frequency = 250.0 + (1.0 - filter_factor) * 4500.0
            self.player.set_passes([cutoff_frequency], q = 1.2, mix = filter_factor, gain = 1.0, duration_ms = 0)

        elif force or self.player.pass_mix_property.value > 0.0:
            self.player.set_passes([], mix = 0.0, duration_ms = 0)

        minimum_speed = 0.08
        speed_in      = 1.0
        speed_out     = 1.0

        if fade_in_type == "speed" and fade_in_ms > 0:
            audio_intro_threshold = ((1.0 + minimum_speed) / 2.0) * fade_in_ms

            if elapsed_ms < audio_intro_threshold:
                speed_ratio = elapsed_ms / fade_in_ms
                speed_in    = math.sqrt(minimum_speed ** 2 + 2.0 * (1.0 - minimum_speed) * speed_ratio)

        if fade_out_type == "speed" and fade_out_ms > 0:
            audio_outro_threshold = ((1.0 + minimum_speed) / 2.0) * fade_out_ms

            if remaining_ms < audio_outro_threshold:
                speed_ratio = remaining_ms / fade_out_ms
                speed_out   = math.sqrt(minimum_speed ** 2 + 2.0 * (1.0 - minimum_speed) * speed_ratio)

        target_speed = min(speed_in, speed_out)
        target_speed = max(minimum_speed, min(1.0, target_speed))

        if force or abs(self.player.speed - target_speed) > 0.015:
            self.player.set_speed(target_speed, duration_ms = 0, update_base = False)

    # Playback

    def toggle_playback(self) -> None:
        if self.is_closing or self.is_cleaning_up:
            return

        if self.player.is_playing:
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time_sec, animate = True)

            return

        self.play_selection()

    def play_selection(self) -> None:
        current_position = self.trim_widget.playback_position

        if not (self.trim_widget.start_time_sec <= current_position < self.trim_widget.end_time_sec):
            current_position = self.trim_widget.start_time_sec
            self.trim_widget.set_playback_position(current_position, animate = False)

        self.apply_preview_effects(current_position * 1000.0, force = True)
        self.player.play(current_position * 1000.0)
        self.play_button.setIcon(self.pause_icon)
        self.trim_widget.set_is_playing(True)
        self.playback_timer.start()

    def stop_playback(self) -> None:
        self.player.stop()
        self.reset_preview_effects()
        self.play_button.setIcon(self.play_icon)
        self.trim_widget.set_is_playing(False)
        self.playback_timer.stop()

    def update_playback(self) -> None:
        if not self.player.is_playing:
            self.trim_widget.set_playback_position(self.trim_widget.start_time_sec, animate = True)
            self.stop_playback()

            return

        current_position_ms = self.player.get_position()

        if current_position_ms > self.trim_widget.end_time_sec * 1000:
            self.trim_widget.set_playback_position(self.trim_widget.start_time_sec, animate = True)
            self.toggle_playback()

            return

        self.apply_preview_effects(current_position_ms)
        self.trim_widget.set_playback_position(current_position_ms / 1000.0, animate = False)

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
            "start_ms":      self.trim_widget.start_time_sec * 1000.0,
            "end_ms":        self.trim_widget.end_time_sec   * 1000.0,
            "fade_in":       int(self.fade_in_textbox.text() or 0),
            "fade_out":      int(self.fade_out_textbox.text() or 0),
            "fade_in_type":  self.fade_in_selector.current_text().lower(),
            "fade_out_type": self.fade_out_selector.current_text().lower()
        }

    def get_threads(self) -> list[QThread | None]:
        return [self.prepare_thread, self.load_thread]

    # Events

    def eventFilter(
            self,
            watched: QObject,
            event:   QEvent
        ) -> bool:

        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)

        if event.key() != Qt.Key.Key_Space or event.isAutoRepeat():
            return super().eventFilter(watched, event)

        if self.is_closing or self.is_cleaning_up or not self.play_button.isEnabled():
            return True

        self.toggle_playback()

        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if not self.is_closing and not self.is_cleaning_up and self.play_button.isEnabled():
                self.toggle_playback()

            event.accept()

            return

        super().keyPressEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)

        self.installEventFilter(self)

        for child_widget in self.findChildren(QWidget):
            child_widget.installEventFilter(self)

    # Lifecycle Handlers

    def request_close(self) -> None:
        self.play_button.setEnabled(False)
        self.cleanup_audio()

        super().request_close()

    def cleanup_audio(self) -> None:
        if self.is_cleaning_up:
            return

        self.is_cleaning_up = True
        self.play_button.setEnabled(False)

        self.playback_timer.stop()
        self.trim_widget.set_is_playing(False)

        if self.player.is_playing:
            self.player.fade_out_and_stop(
                duration_ms = 6000,
                easing      = LoomEngine.Easing.ease_out_quart,
                on_finish   = self.reset_preview_effects
            )

        else:
            self.player.stop()
            self.reset_preview_effects()

        self.cleanup_threads(self.get_threads())

        self.prepare_worker = None
        self.load_worker    = None
        self.prepare_thread = None
        self.load_thread    = None

    def on_cancel(self) -> None:
        self.cleanup_audio()
        super().on_cancel()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cleanup_audio()
        super().closeEvent(event)

# BPM Editor

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
        self.bpm_input.setStyleSheet(Styles.Controls.FloatingTextBox)

        self.bpm_animation_timer = Timing.Timer(
            interval   = Constants.FPS_30,
            callback   = self.animate_bpm_spinbox,
            auto_start = True,
            parent     = self
        )

        self.bpm_remove_timer = Timing.Timer(
            interval   = 0,
            callback   = self.bpm_remove_step,
            parent     = self
        )

        if self.animations_active:
            self.bpm_textbox_width = LoomEngine.ui_engine.bind(
                owner      = self,
                name       = "bpm_textbox_width",
                base_value = self.bpm_input.width(),
                mix_mode   = LoomEngine.MixMode.REPLACE,
                on_change  = self.bpm_input.setFixedWidth
            )

        self.bpm_input.safeTextChanged.connect(self.on_bpm_changed)

    def on_prepare_success(self, cached_wav_path: str) -> None:
        super().on_prepare_success(cached_wav_path)
        self.start_bpm_pipeline()

    def is_bpm_thread_running(self) -> bool:
        return self.is_thread_running(self.bpm_thread)

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
                Player.ui_player.play_sound(".vault/NOK/Gambling")

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