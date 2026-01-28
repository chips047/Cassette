import re
import math
import random

import numpy as np

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from loguru import logger
from .Constants import *

from . import UI
from . import Utils
from . import Styles
from . import Audio
from . import Player

import multiprocessing as mp

def _proc_analyze_bpm(file_path, queue):
    try:
        bpm, peaks = Audio.analyze_bpm_and_beats(file_path)
        queue.put(("SUCCESS", (bpm, peaks)))
    
    except Exception as e:
        queue.put(("ERROR", str(e)))

def _proc_load_audio(file_path, queue):
    try:
        data, fs = Audio.load_audio(file_path)
        audio_calc = data.astype(np.float32)
        
        if audio_calc.ndim > 1:
            audio_calc = np.mean(audio_calc, axis=1)

        audio_calc = audio_calc - np.mean(audio_calc)
        max_val = np.max(np.abs(audio_calc))
        if max_val > 0:
            audio_calc = audio_calc / max_val

        samples_per_pixel = len(audio_calc) / 1000
        step = max(1, int(np.ceil(samples_per_pixel)))
        
        padded_len = ((len(audio_calc) + step - 1) // step) * step
        padded = np.pad(audio_calc, (0, padded_len - len(audio_calc)), mode="constant")
        reshaped = padded.reshape(-1, step)

        waveform_data = np.mean(np.abs(reshaped), axis=1)
        waveform_data = Utils.gaussian_filter1d_np(waveform_data, sigma=2)
        
        queue.put(("SUCCESS", (data, fs, waveform_data)))
    
    except Exception as e:
        queue.put(("ERROR", str(e)))

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
        
        self.waveform_amplitudes = []

        self.dragging_handle = None
        self._playback_position = 0.0

        self.setMinimumHeight(80)

    def _generate_pixmap(self):
        width = self.width()
        height = self.height()
        y_center = height / 2.0

        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(Styles.Colors.Floating.background))

        if len(self.waveform_amplitudes) == 0:
            self.waveform_pixmap = pixmap
            return

        painter = QPainter(pixmap)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        amplitudes_top = y_center - self.waveform_amplitudes * y_center
        amplitudes_bottom = y_center + self.waveform_amplitudes * y_center

        path = QPainterPath()
        
        x_step = width / len(self.waveform_amplitudes)

        for i in range(len(amplitudes_top)):
            x = i * x_step
            y = max(0, min(height, amplitudes_top[i]))
            
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        for i in reversed(range(len(amplitudes_bottom))):
            x = i * x_step
            y = max(0, min(height, amplitudes_bottom[i]))
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

    def set_data(self, audio_data, sampling_rate, waveform_amplitudes):
        self.audio_data = audio_data
        self.sampling_rate = sampling_rate
        self.waveform_amplitudes = waveform_amplitudes
        
        self.duration = len(audio_data) / sampling_rate if sampling_rate > 0 else 0
        self.end_time = self.duration
        self.is_loading = False

        self._generate_pixmap()
        self.update()
    
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
                
                logger.info(f"Placed playback on {time_pos}")
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
        dur = self.duration
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
        return self._playback_position

    def set_playback_position(self, pos):
        self._playback_position = max(0, min(self.duration, pos))
        self.update()

    def set_is_playing(self, is_playing):
        self._is_playing = is_playing
        self.update()

class AudioSetupDialog(UI.FloatingWindowGPU):
    def __init__(self, file_path):
        self.player = Player.player
        
        super().__init__(
            "Audio",
            player = self.player,
            max_tilt_angle = 8,
            enable_audioplayer_effects = False
        )   
        
        self.file_path = file_path
        self.sampling_rate = 0
        self.end_time_sec = 1.0
        self._bpm_anim_target = None
        
        self.settings = {}
        self.snapped_times = None

        self.setStyleSheet(Styles.Controls.AudioSetupper)

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self.update_playback)
        
        self.setup_audio_layout()
        self.setup_animations()
        self.run_tasks(file_path)

        self.adjustSize()
    
    def run_tasks(self, audiofile):
        self.load_queue = mp.Queue()
        self.bpm_queue = mp.Queue()
        
        self.load_process = mp.Process(target=_proc_load_audio, args=(audiofile, self.load_queue))
        self.bpm_process = mp.Process(target = _proc_analyze_bpm, args = (audiofile, self.bpm_queue))

        self.process_monitor_timer = QTimer(self)
        self.process_monitor_timer.timeout.connect(self.poll_processes)
        self.process_monitor_timer.start(100)

        self.load_process.start()
        self.bpm_process.start()
    
    def setup_animations(self):
        self.bpm_remove_timer = QTimer(self)
        self.bpm_remove_timer.timeout.connect(self._bpm_remove_step)
        
        self.bpm_anim_timer = QTimer(self)
        self.bpm_anim_timer.timeout.connect(self.animate_bpm_spinbox)
        self.bpm_anim_timer.start(FPS_30)
    
    def setup_audio_layout(self):
        playback_layout = QHBoxLayout()
        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(10)

        self.trim_widget = TrimmingWaveformWidget()
        self.start_time_label = UI.Textbox(0, 0, 5, ":time")
        self.end_time_label = UI.Textbox(0, 0, 5, ":time")
        self.fade_in_textbox = UI.Textbox(0, 5000, None, "number", None, "Fade in (Ms)")
        self.fade_out_textbox = UI.Textbox(0, 5000, None, "number", None, "Fade out (Ms)")
        self.bpm_input = UI.Textbox(1, 400, None, "number", None, "Counting BPM... 120")        
        
        self.bpm_input.setMaximumWidth(205)
        self.bpm_input.setFixedHeight(Styles.Metrics.element_height)
        self.bpm_input.setStyleSheet(Styles.Controls.FloatingTextBoxRound)

        for textbox in [self.start_time_label, self.end_time_label]:
            textbox.setFixedWidth(70)

        for textbox in [self.fade_in_textbox, self.fade_out_textbox, self.start_time_label, self.end_time_label]:
            textbox.setStyleSheet(Styles.Controls.FloatingTextBox)
            textbox.setFixedHeight(40)
        
        self.play_button = QPushButton()
        self.play_button.setObjectName("play_button")
        
        self.play_icon = QIcon(QIcon("System/Icons/Play.png"))
        self.pause_icon = QIcon(QIcon("System/Icons/Pause.png"))
        
        self.play_button.setIcon(self.play_icon)
        self.play_button.setIconSize(QSize(45, 45))

        playback_layout.addWidget(self.start_time_label)
        playback_layout.addWidget(self.fade_in_textbox)
        playback_layout.addWidget(self.play_button)
        playback_layout.addWidget(self.fade_out_textbox)
        playback_layout.addWidget(self.end_time_label)
        
        # Settings Layout
        self.model_selector = UI.Selector(["1", "2", "2a", "3a"])

        self.cancel_button = UI.ButtonWithOutline("Cancel")
        self.ok_button = UI.NothingButton("Ok")
        
        self.ok_button.setMaximumWidth(70)
        self.play_button.setFixedSize(45, 45)
        self.cancel_button.setMaximumWidth(100)
        self.model_selector.setMinimumWidth(300)
        
        self.play_button.setEnabled(False)
        self.ok_button.setEnabled(False)

        settings_layout.addWidget(self.bpm_input)
        settings_layout.addWidget(self.model_selector)
        settings_layout.addStretch()
        settings_layout.addWidget(self.cancel_button)
        settings_layout.addWidget(self.ok_button)

        # Connecting
        self.start_time_label.textChanged.connect(self.edit_start_time)
        self.end_time_label.textChanged.connect(self.edit_end_time)
        self.play_button.clicked.connect(self.toggle_playback)
        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.reject_callback)
        self.trim_widget.regionChanged.connect(self.update_texboxes)
        self.bpm_input.safeTextChanged.connect(self.on_bpm_changed)

        # Content Layout Adding
        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(playback_layout)
        self.content_layout.addLayout(settings_layout)
    
    def poll_processes(self):
        if self.load_queue and not self.load_queue.empty():
            status, result = self.load_queue.get()
            
            if status == "SUCCESS":
                data, fs, waveform_data = result
                
                self.player.load_audio_from_data(data, fs)
                self.on_audio_loaded(data, fs, waveform_data)
            
            else:
                logger.error(f"Audio load error: {result}")
            
            self.load_process.join()
        
        if not self.bpm_queue.empty():
            status, result = self.bpm_queue.get()
            
            if status == "SUCCESS":
                self.on_bpm_ready(*result)
            
            else:
                logger.error(f"BPM error: {result}")
            
            self.bpm_process.join()
            
        if not self.bpm_process.is_alive() and not self.load_process.is_alive():
            self.process_monitor_timer.stop()
    
    def on_audio_loaded(self, audio_data, sampling_rate, waveform_data):
        logger.info("Audio loaded.")
        self.sampling_rate = sampling_rate
        
        self.trim_widget.set_data(audio_data, sampling_rate, waveform_data)
        
        self.end_time_sec = self.trim_widget.duration
        self.end_time_label.max_number = self.end_time_sec
        self.end_time_label.setText(max(1, math.ceil(self.end_time_sec)))

        self.update_texboxes(self.trim_widget.start_time, self.trim_widget.end_time)

        self.play_button.setEnabled(True)
        self.ok_button.setEnabled(True)

    def on_bpm_ready(self, bpm, snapped_times):
        logger.info(f"BPM found: {bpm}")
        self.snapped_times = snapped_times
        
        self.bpm_anim_timer.stop()

        if bpm:
            remove_interval = round(60000 / bpm / 4)
            self.bpm_input.setPlaceholderText(f"Counting BPM {round(bpm)}")
            self.bpm_remove_timer.start(remove_interval)
            
            return

        self.bpm_input.setPlaceholderText("Counting BPM 0")
        self.bpm_remove_timer.start(30)

        if random.randint(1, 500) == 500:
            Utils.ui_sound("Gambling")

    def get_perfect_width(self):
        text = str(self.bpm_input.text() or self.bpm_input.placeholderText())
        
        metrics = self.bpm_input.fontMetrics()
        text_width = metrics.horizontalAdvance(text)

        padding = 29.5
        return round(text_width + padding)
    
    def shrink_bpm_input(self):
        logger.info("Shrinking BPM section...")
        
        self.bpm_shrink_animation = QPropertyAnimation(self.bpm_input, b"maximumWidth")
        self.bpm_shrink_animation.setDuration(300)
        self.bpm_shrink_animation.setStartValue(self.bpm_input.width())
        self.bpm_shrink_animation.setEndValue(self.get_perfect_width())
        self.bpm_shrink_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.bpm_shrink_animation.start()

    def update_texboxes(self, start, end):
        self.start_time_label.blockSignals(True)
        self.end_time_label.blockSignals(True)
        
        self.start_time_label.setText(int(round(start)))
        self.end_time_label.setText(max(1, int(round(end))))
        
        self.start_time_label.blockSignals(False)
        self.end_time_label.blockSignals(False)

        self.start_time_label.max_number = int(round(end - 1))
        self.end_time_label.min_number = int(round(start))

    def edit_start_time(self):
        start_s = self.start_time_label.text()
        
        if start_s:
            self.trim_widget.set_playback_position(start_s)

            self.trim_widget.start_time = start_s
            self.trim_widget.update()

            self.end_time_label.min_number = self.start_time_label.text()

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

    def animate_bpm_spinbox(self):
        current = int(self.bpm_input.placeholderText().split(" ")[-1])
        
        if current == self._bpm_anim_target or not self._bpm_anim_target:
            self._bpm_anim_target = np.random.randint(60, 180)

        target = self._bpm_anim_target
        current += 1 if current < target else -1 if current > target else 0
        
        self.bpm_input.setPlaceholderText(f"Counting BPM {current}")

    def _bpm_remove_step(self):
        current = self.bpm_input.placeholderText()
        match = re.search(r"\d{2,3}$", current)

        if not match:
            return self.bpm_input.setPlaceholderText(current[2:])

        bpm_digits = match.group()
        bpm_start_index = match.start()

        if current == bpm_digits:
            self.bpm_remove_timer.stop()
            self.bpm_input.setText(bpm_digits)
            self.bpm_input.setPlaceholderText("BPM")
            self.shrink_bpm_input()
            
            return

        remaining_before_digits = bpm_start_index
        step = min(2, remaining_before_digits)

        new_text = current[step:]
        self.bpm_input.setPlaceholderText(new_text)
    
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
            self.trim_widget.set_playback_position(0)
            self.stop_playback()

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
        
        self.saved_settings = self.get_settings()

        self.cleanup()
        super().on_ok()
    
    def reject_callback(self):
        self.cleanup(True)
        super().on_cancel()

    def get_settings(self):
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
    
    def cleanup(self, cancelled = False):
        if self.load_process.is_alive():
            self.load_process.terminate()
        
        if self.bpm_process.is_alive():
            self.bpm_process.terminate()
        
        if self.process_monitor_timer.isActive():
            self.process_monitor_timer.stop()
        
        if self.player.is_playing:
            self.player.tape(duration = 1.0 if not cancelled else 3.0, end_speed = 0.0)
        
        # If crashes, restore the lines.

        self.playback_timer.stop()
        self.bpm_anim_timer.stop()
        self.bpm_remove_timer.stop()
        
        self.trim_widget.audio_data = None
        self.trim_widget.smooth_top = []
        self.trim_widget.smooth_bottom = []