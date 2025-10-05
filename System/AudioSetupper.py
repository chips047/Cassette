import re
import time
import math
import random
import atexit

import numpy as np

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from loguru import logger
from .Constants import *

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from . import UI
from . import Utils
from . import Styles
from . import Audio
from . import Player

_SHARED_AUDIO_EXECUTOR = ThreadPoolExecutor(max_workers=2)
atexit.register(lambda: _SHARED_AUDIO_EXECUTOR.shutdown(wait=True))

def _audio_loader_task(file_path, target_width):
    audio_data, sampling_rate = Audio.load_audio(file_path)

    mins = len(audio_data) / sampling_rate / 60 if sampling_rate else 0
    long_audio = mins >= 10

    peaks = []
    
    if audio_data is not None and len(audio_data) > 0 and target_width > 0:
        num_peaks = target_width * 2
        samples_per_peak = max(1, len(audio_data) // num_peaks)
        
        for i in range(0, len(audio_data), samples_per_peak):
            chunk = audio_data[i:i + samples_per_peak]
            if len(chunk) > 0:
                peaks.append(np.max(np.abs(chunk)))

    return audio_data, sampling_rate, peaks, long_audio

class AudioLoader(QObject):
    dataReady = pyqtSignal(object, int, list)
    long_audio_detected = pyqtSignal()

    def __init__(self, file_path, target_width):
        super().__init__()
        self.file_path = file_path
        self.target_width = target_width
        self._executor = _SHARED_AUDIO_EXECUTOR
        self._future = None

    def start(self):
        if self._future is not None and not self._future.done():
            return

        self._future = self._executor.submit(_audio_loader_task, self.file_path, self.target_width)
        self._future.add_done_callback(self._on_done)

    @pyqtSlot()
    def stop(self):
        if self._future and not self._future.done():
            self._future.cancel()
        
        self._future = None

    def _on_done(self, future):
        try:
            audio_data, sampling_rate, peaks, long_audio = future.result()
        
        except concurrent.futures.CancelledError:
            return

        except Exception as e:
            print(f"Audio loading failed: {e}")
            return

        if long_audio:
            self.long_audio_detected.emit()

        self.dataReady.emit(audio_data, sampling_rate, peaks)

    def shutdown(self):
        if self._future and not self._future.done():
            self._future.cancel()
        
        self._future = None

class TrimmingWaveformWidget(QWidget):
    regionChanged = pyqtSignal(float, float)
    playbackPositionClicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sampling_rate = 0
        self.duration = 0
        self.peaks = []
        self.is_loading = True
        self.waveform_pixmap = None
        self._is_playing = False

        self.start_time = 0.0
        self.end_time = 0.0

        self.dragging_handle = None
        self._playback_position = self.start_time

        self.setMinimumHeight(80)

    def _generate_pixmap(self):
        if not hasattr(self, "smooth_top") or len(self.smooth_top) == 0:
            self.waveform_pixmap = None
            return

        width = self.width()
        height = self.height()

        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(Styles.Colors.Floating.background))

        painter = QPainter(pixmap)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        bar_width = width / len(self.smooth_top)
        path = QPainterPath()

        for i in range(len(self.smooth_top)):
            x = i * bar_width
            y = max(0, min(height, self.smooth_top[i]))
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        for i in reversed(range(len(self.smooth_bottom))):
            x = i * bar_width
            y = max(0, min(height, self.smooth_bottom[i]))
            path.lineTo(x, y)

        path.closeSubpath()

        outline_color = QColor(255, 255, 255, 90)
        painter.setPen(QPen(outline_color, 2.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        fill_color = QColor(255, 255, 255, 90)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(QColor(255, 255, 255, 160), 0.7))
        painter.drawPath(path)

        painter.end()
        self.waveform_pixmap = pixmap

    def set_data(self, audio_data, sampling_rate, peaks=None):
        self.audio_data = audio_data
        self.sampling_rate = sampling_rate
        self.duration = len(audio_data) / sampling_rate if sampling_rate > 0 else 0
        self.end_time = self.duration
        self.is_loading = False

        self._prepare_waveform()
        self.update()
    
    def _prepare_waveform(self, mode="avg"):
        width = self.width() if self.width() > 0 else 1000
        height = self.height() if self.height() > 0 else 80
        y_center = height / 2.0

        audio = self.audio_data.astype(np.float32)
        audio = audio - np.mean(audio)
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val

        samples_per_pixel = len(audio) / float(width)
        step = max(1, int(np.ceil(samples_per_pixel)))
        padded_len = ((len(audio) + step - 1) // step) * step
        padded = np.pad(audio, (0, padded_len - len(audio)), mode="constant")
        reshaped = padded.reshape(-1, step)

        if mode == "minmax":
            min_vals = np.min(reshaped, axis=1)
            max_vals = np.max(reshaped, axis=1)

            amplitudes_top = y_center - max_vals * y_center
            amplitudes_bottom = y_center - min_vals * y_center

        elif mode == "rms":
            rms_vals = np.sqrt(np.mean(reshaped**2, axis=1))
            amplitudes_top = y_center - rms_vals * y_center
            amplitudes_bottom = y_center + rms_vals * y_center

        elif mode == "avg":
            avg_vals = np.mean(np.abs(reshaped), axis=1)
            amplitudes_top = y_center - avg_vals * y_center
            amplitudes_bottom = y_center + avg_vals * y_center

        self.smooth_top = Utils.gaussian_filter1d_np(amplitudes_top, sigma=2)
        self.smooth_bottom = Utils.gaussian_filter1d_np(amplitudes_bottom, sigma=2)

        self._generate_pixmap()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(Styles.Colors.Floating.background))

        if self.is_loading:
            painter.setPen(QColor("#888"))
            painter.setFont(Utils.NType(15))
            painter.drawText(self.rect(), Qt.AlignCenter, "Loading the audio...")
            return

        if self.waveform_pixmap:
            painter.drawPixmap(0, 0, self.waveform_pixmap)

        start_x = (self.start_time / self.duration) * self.width() if self.duration > 0 else 0
        end_x = (self.end_time / self.duration) * self.width() if self.duration > 0 else 0

        start_x = max(0, min(self.width(), start_x))
        end_x = max(0, min(self.width(), end_x))

        painter.setBrush(QColor(255, 255, 255, 30))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(QPointF(start_x, 0), QPointF(end_x, self.height())), 10, 10)

        painter.setPen(QPen(QColor(Styles.Colors.nothing_accent), 2))
        painter.drawLine(int(start_x), 10, int(start_x), self.height() - 10)
        painter.drawLine(int(end_x), 10, int(end_x), self.height() - 10)

        playhead_x = (self._playback_position / self.duration) * self.width() if self.duration > 0 else 0
        width = 2
        color = QColor(Styles.Colors.nothing_accent)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRect(QRectF(playhead_x - width / 2, 0, width, self.height()))

    def mousePressEvent(self, event):
        x = event.pos().x()
        start_x = (self.start_time / self.duration) * self.width() if self.duration > 0 else 0
        end_x = (self.end_time / self.duration) * self.width() if self.duration > 0 else 0

        if abs(x - start_x) < 10:
            self.dragging_handle = 'start'
        
        elif abs(x - end_x) < 10:
            self.dragging_handle = 'end'
        
        else:
            self.dragging_handle = None
            
            if self.duration > 0:
                time_pos = (x / self.width()) * self.duration

                if not self._is_playing:
                    self.set_playback_position(time_pos)
                
                logger.info(f"Placing playback on {time_pos}")
                self.playbackPositionClicked.emit(self.playback_position)

    def mouseMoveEvent(self, event):
        if self.dragging_handle:
            x = event.pos().x()
            x = max(0, min(self.width(), x))
            
            time = (x / self.width()) * self.duration if self.duration > 0 else 0
            time = max(0, min(self.duration, time))

            if self.dragging_handle == 'start':
                self.start_time = min(time, self.end_time - 0.1)

                if not self._is_playing:
                    self.set_playback_position(self.start_time)

            elif self.dragging_handle == 'end':
                self.end_time = max(time, self.start_time + 0.1)
                self.end_time = min(self.end_time, self.duration if self.duration > 0 else self.end_time)

                if self.playback_position > self.end_time:
                    self.set_playback_position(self.end_time)

            self.regionChanged.emit(self.start_time, self.end_time)
            self.update()

    def mouseReleaseEvent(self, event):
        self.dragging_handle = None

    def set_times(self, start, end):
        dur = getattr(self, "duration", 0) or 0
        start = max(0.0, start)
        end = min(dur if dur > 0 else end, end)
        
        if end <= start + 0.01:
            end = start + 0.01
            if dur > 0 and end > dur:
                start = max(0.0, dur - 0.01)
                end = dur

        self.start_time = start
        self.end_time = end
        self.update()

    @property
    def playback_position(self):
        return getattr(self, '_playback_position', self.start_time)

    def set_playback_position(self, pos):
        self._playback_position = max(0, min(self.duration, pos))
        self.update()

    def set_is_playing(self, is_playing):
        self._is_playing = is_playing
        self.update()

class AudioSetupDialog(UI.FloatingWindow):
    def __init__(self, file_path):
        super().__init__("Audio", player = self, max_tilt_angle = 8)
        
        self.file_path = file_path
        self.sampling_rate = 22050
        self.playback_start_time_in_channel = 0
        self.playback_start_position = 0

        self.player = Player.Player()
        self.player.load_audio(file_path)

        self.setStyleSheet(Styles.Controls.AudioSetupper)

        self.start_time_sec = 0.0
        self.end_time_sec = 1.0

        self.trim_widget = TrimmingWaveformWidget()
        self.trim_widget.regionChanged.connect(self.update_texboxes)
        self.content_layout.addWidget(self.trim_widget)

        playback_layout = QHBoxLayout()

        self.start_time_label = UI.AnimatedLineEdit(0, int(self.end_time_sec - 1), 5, ":time")
        self.end_time_label = UI.AnimatedLineEdit(1, self.end_time_sec, 5, ":time")
        
        self.start_time_label.textChanged.connect(self.edit_start_time)
        self.end_time_label.textChanged.connect(self.edit_end_time)

        self.start_time_label.setText(0)
        self.end_time_label.setText(int(self.end_time_sec))
        
        self.fade_in_textbox = UI.AnimatedLineEdit(0, 5000, None, "number", "0", "Fade in (Ms)")
        self.fade_out_textbox = UI.AnimatedLineEdit(0, 5000, None, "number", "0", "Fade out (Ms)")

        self.fade_out_textbox.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.fade_in_textbox.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        
        self.bpm_input = UI.AnimatedLineEdit(1, 400, None, "number", None, "Counting BPM... 120")
        self.bpm_input.setMinimumWidth(63)
        self.bpm_input.setMaximumWidth(207)
        self.bpm_input.setFixedHeight(Styles.Metrics.element_height)
        self.bpm_input.setStyleSheet(Styles.Controls.FloatingTextBoxRound)

        for textbox in [self.start_time_label, self.end_time_label]:
            textbox.setFixedSize(70, 40)

        for textbox in [self.fade_in_textbox, self.fade_out_textbox]:
            textbox.setFixedHeight(40)

        for textbox in [self.fade_in_textbox, self.fade_out_textbox, self.start_time_label, self.end_time_label]:
            textbox.setStyleSheet(Styles.Controls.FloatingTextBox)

        self.bpm_anim_timer = QTimer(self)
        self.bpm_anim_timer.timeout.connect(self.animate_bpm_spinbox)
        self.bpm_animating = True
        self.bpm_anim_timer.start(7)
        self._bpm_anim_target = np.random.randint(60, 180)
        self._bpm_real_target = None
        self._bpm_anim_speed = 7

        self.settings = {}

        self.snapped_times = None

        self.play_button = QPushButton()
        self.play_button.setObjectName("play_button")
        self.play_icon = QIcon(Utils.Icons.Play)
        self.pause_icon = QIcon(Utils.Icons.Pause)
        self.play_button.setIcon(self.play_icon)
        self.play_button.setIconSize(QSize(45, 45))
        self.play_button.setFixedSize(45, 45)
        self.play_button.clicked.connect(self.toggle_playback)

        playback_layout.addWidget(self.start_time_label)
        playback_layout.addWidget(self.fade_in_textbox)
        playback_layout.addWidget(self.play_button)
        playback_layout.addWidget(self.fade_out_textbox)
        playback_layout.addWidget(self.end_time_label)
        self.content_layout.addLayout(playback_layout)

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(10)
        
        self.model_selector = UI.Selector(["1", "2", "2a", "3a"])
        self.model_selector.setMinimumWidth(300)

        self.cancel_button = UI.ButtonWithOutline("Cancel")
        self.ok_button = UI.NothingButton("Ok")
        
        self.ok_button.setMaximumWidth(70)
        self.cancel_button.setMaximumWidth(100)
        
        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.reject_callback)
        self.play_button.setEnabled(False)
        self.ok_button.setEnabled(False)

        settings_layout.addWidget(self.bpm_input)
        settings_layout.addWidget(self.model_selector)
        settings_layout.addStretch()
        settings_layout.addWidget(self.cancel_button)
        settings_layout.addWidget(self.ok_button)

        self.content_layout.addLayout(settings_layout)

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self.update_playback)

        self.bpm_worker = Audio.BPMWorkerProcess(self.file_path)
        self.bpm_worker.bpm_ready.connect(self.on_bpm_ready)
        self.bpm_worker.start()

        self.bpm_input.safeTextChanged.connect(self.on_bpm_changed)
        
        self.bpm_remove_timer = QTimer(self)
        self.bpm_remove_timer.timeout.connect(self._bpm_remove_step)
        self._bpm_final_bpm = None
        
        self.audio_loader = AudioLoader(self.file_path, self.width())
        self.audio_loader.dataReady.connect(self.on_audio_loaded)
        self.audio_loader.long_audio_detected.connect(
            lambda: UI.ErrorWindow("What the hell??", "Why so long???????").exec_()
        )
        self.audio_loader.start()

        logger.info("Loading audio...")
        self.adjustSize()
    
    def cleanup(self):
        if self.player.is_playing:
            self.player.tape(end_speed = 0.0, cleanup_on_finish = True)

        self.playback_timer.stop()
        self.bpm_anim_timer.stop()
        self.bpm_remove_timer.stop()

        if hasattr(self, "audio_loader"):
            self.audio_loader.shutdown()

        if hasattr(self, "bpm_worker"):
            self.bpm_worker.stop()
            try: self.bpm_worker.bpm_ready.disconnect()
            except TypeError: pass
        
        self.trim_widget.audio_data = None
        self.trim_widget.smooth_top = []
        self.trim_widget.smooth_bottom = []
    
    @pyqtSlot(np.ndarray, int, list)
    def on_audio_loaded(self, audio_data, sampling_rate, peaks):
        logger.info("Audio loaded.")
        self.sampling_rate = sampling_rate
        
        self.trim_widget.set_data(audio_data, sampling_rate, peaks)
        
        self.end_time_sec = self.trim_widget.duration
        self.end_time_label.max_number = self.end_time_sec
        self.end_time_label.setText(max(1, math.ceil(self.end_time_sec)))

        self.update_texboxes(self.trim_widget.start_time, self.trim_widget.end_time)

        self.play_button.setEnabled(True)
        self.ok_button.setEnabled(True)
    
    def shrink_bpm_input(self):
        logger.info("Shrinking BPM section...")
        anim = QPropertyAnimation(self.bpm_input, b"maximumWidth")
        anim.setDuration(300)
        anim.setStartValue(self.bpm_input.width())
        anim.setEndValue(63)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        
        self._bpm_shrink_anim = anim

    def update_texboxes(self, start, end):
        self.start_time_label.blockSignals(True)
        self.end_time_label.blockSignals(True)
        
        self.start_time_label.setText(int(round(start)))
        self.end_time_label.setText(max(1, int(round(end))))
        
        self.start_time_label.blockSignals(False)
        self.end_time_label.blockSignals(False)

        self.start_time_label.max_number = int(round(end - 1))
        self.end_time_label.min_number = int(round(start))
    
    def reject_callback(self):
        self.cleanup()
        super().on_cancel()

    def edit_start_time(self):
        start_s = self.start_time_label.time_text_to_seconds()
        
        if start_s:
            self.trim_widget.set_playback_position(start_s)

            self.trim_widget.start_time = start_s
            self.trim_widget.update()

            self.end_time_label.min_number = self.start_time_label.time_text_to_seconds()

    def edit_end_time(self):
        end_s = self.end_time_label.text()
        start_s = self.start_time_label.text()
        
        if end_s is None or start_s is None:
            return

        if end_s > start_s:
            self.trim_widget.set_playback_position(start_s)

            self.trim_widget.end_time = end_s
            self.trim_widget.update()

            self.start_time_label.max_number = end_s - 1

    def stop_bpm_animation(self):
        self.bpm_animating = False
        self._bpm_real_target = None
        self.bpm_anim_timer.stop()

    def animate_bpm_spinbox(self):
        FAST_INTERVAL = 20
        SLOW_BASE = 40
        STEP_PER_UNIT = 40

        if not self.bpm_animating and self._bpm_real_target is None:
            return

        current = int(self.bpm_input.placeholderText().split(" ")[-1])
        target = self._bpm_real_target if self._bpm_real_target is not None else self._bpm_anim_target

        current += 1 if current < target else -1 if current > target else 0
        self.bpm_input.setPlaceholderText(f"Counting BPM {current}")

        if self._bpm_real_target is not None:
            distance = abs(current - self._bpm_real_target)

            if distance == 0:
                self.bpm_anim_timer.stop()
                self._bpm_real_target = None
                return

            if distance > 5:
                new_speed = FAST_INTERVAL
            else:
                new_speed = SLOW_BASE + (5 - distance) * STEP_PER_UNIT

            if new_speed != self._bpm_anim_speed:
                self._bpm_anim_speed = new_speed
                self.bpm_anim_timer.setInterval(new_speed)

        else:
            if current == target:
                self._bpm_anim_target = np.random.randint(60, 180)

    def accept_callback(self):
        is_not_valid = self.end_time_label.is_not_valid()
        
        if is_not_valid or not self.end_time_label.text():
            self.end_time_label.start_glitch(False)
            self.ok_button.start_glitch()
            
            return
        
        if self.start_time_label.text() is None:
            self.start_time_label.start_glitch(False)
            self.ok_button.start_glitch()
            
            return
        
        self.start_sample = int(self.trim_widget.start_time * self.sampling_rate)
        self.end_sample = int(self.trim_widget.end_time * self.sampling_rate)
        self.saved_settings = self.get_settings()

        self.cleanup()
        super().on_ok()

    def on_bpm_ready(self, bpm, first_beat_offset_sec, snapped_times):
        logger.info("BPM found.")
        self.snapped_times = snapped_times
        self.first_beat_offset_sec = first_beat_offset_sec

        self._bpm_final_bpm = str(int(bpm))
        self.bpm_anim_timer.stop()
        self.bpm_animating = False

        self.bpm_input.setPlaceholderText(f"Counting BPM {self._bpm_final_bpm}")
        self.bpm_remove_timer.start(60)

        if bpm == 0:
            if random.randint(0, 500) == 500:
                Utils.ui_sound("Gambling")

    def _bpm_remove_step(self):
        current = self.bpm_input.placeholderText()

        match = re.search(r"\d{2,3}$", current)
        if match:
            bpm_digits = match.group()

            if current != bpm_digits:
                self.bpm_input.setPlaceholderText(current[1:])
            
            else:
                self.bpm_remove_timer.stop()
                self.bpm_input.setText(bpm_digits)
                self.update_bpm(int(bpm_digits))
                self.bpm_timer.start()
                self.bpm_input.setPlaceholderText("BPM")
                self.shrink_bpm_input()
        
        else:
            self.bpm_input.setPlaceholderText(current[1:])

    def on_bpm_changed(self, value):
        self.update_bpm(int(value))

    def toggle_playback(self):
        if self.player.is_playing:
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time)

        else:
            self.play_selection()

    def play_selection(self):
        current_playback_sec = self.trim_widget.playback_position
        
        if not (self.trim_widget.start_time <= current_playback_sec < self.trim_widget.end_time):
            current_playback_sec = self.trim_widget.start_time
            self.trim_widget.set_playback_position(current_playback_sec)
        
        self.player.play(current_playback_sec * 1000)

        self.playback_start_time_in_channel = time.time()
        self.playback_start_position = current_playback_sec

        self.play_button.setIcon(self.pause_icon)
        self.trim_widget.set_is_playing(True)
        self.playback_timer.start(14)

    def stop_playback(self):
        self.player.stop()

        self.play_button.setIcon(self.play_icon)
        self.trim_widget.set_is_playing(False)
        self.playback_timer.stop()

    def update_playback(self):
        if self.player.is_playing:
            current_pos_ms = self.player.get_position_ms()
            if current_pos_ms > self.trim_widget.end_time * 1000:
                self.trim_widget.set_playback_position(self.trim_widget.start_time)
                self.stop_playback()
                return

            self.trim_widget.set_playback_position(current_pos_ms / 1000)

        else:
            print("what")
            self.trim_widget.set_playback_position(0)
            self.stop_playback()

    def get_settings(self):
        if not hasattr(self, 'start_sample'):
            self.start_sample = int(self.trim_widget.start_time * self.sampling_rate)
        
        if not hasattr(self, 'end_sample'):
            self.end_sample = int(self.trim_widget.end_time * self.sampling_rate)
            
        return {
            "audio": {
                "start_ms": self.trim_widget.start_time * 1000,
                "end_ms": self.trim_widget.end_time * 1000,
                
                "audio_data": self.player.data,
                "sampling_rate": self.sampling_rate,
                
                "fade_in": self.fade_in_textbox.text(),
                "fade_out": self.fade_out_textbox.text(),
                "duration": self.trim_widget.end_time - self.trim_widget.start_time,
                
                "bpm": self.bpm_input.text() or 120,
                "beats": self.snapped_times
            },
            
            "model": number_model_to_code(self.model_selector.currentText()),
        }