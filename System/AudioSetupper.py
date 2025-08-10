import re
import time
import pygame
import librosa

import numpy as np

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from .Constants import *

from . import UI
from . import Utils
from . import Styles
from . import BPMAnalyze

class AudioLoaderWorker(QObject):
    dataReady = pyqtSignal(np.ndarray, int, list)

    def __init__(self, file_path, target_width, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.target_width = target_width

    @pyqtSlot()
    def run(self):
        audio_data, sampling_rate = librosa.load(self.file_path, sr=44100)

        peaks = []
        if audio_data is not None and len(audio_data) > 0 and self.target_width > 0:
            num_peaks = self.target_width * 2
            samples_per_peak = max(1, len(audio_data) // num_peaks)
            for i in range(0, len(audio_data), samples_per_peak):
                chunk = audio_data[i:i + samples_per_peak]
                if len(chunk) > 0:
                    peaks.append(np.max(np.abs(chunk)))
        
        self.dataReady.emit(audio_data, sampling_rate, peaks)

class TrimmingWaveformWidget(QWidget):
    regionChanged = pyqtSignal(float, float)
    playbackPositionClicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_data = None
        self.sampling_rate = 0
        self.duration = 0
        self.peaks = []
        self.is_loading = True

        self.start_time = 0.0
        self.end_time = 0.0

        self.dragging_handle = None
        self._playback_position = self.start_time

        self.setMinimumHeight(80)

    def set_data(self, audio_data, sampling_rate, peaks):
        self.audio_data = audio_data
        self.sampling_rate = sampling_rate
        self.peaks = peaks
        self.duration = len(self.audio_data) / self.sampling_rate if self.sampling_rate > 0 else 0
        self.end_time = self.duration
        self.is_loading = False
        self.update()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#2b2b2b"))
        
        if self.is_loading:
            painter.setPen(QColor("#888"))
            painter.setFont(Utils.NType(15))
            painter.drawText(self.rect(), Qt.AlignCenter, "Loading the audio...")
            return

        if self.peaks:
            path = QPainterPath()
            center_y = self.height() / 2
            path.moveTo(0, center_y)

            for i, peak in enumerate(self.peaks):
                x = (i / len(self.peaks)) * self.width() if len(self.peaks) > 0 else 0
                h = peak * center_y
                path.lineTo(x, center_y - h)

            for i, peak in reversed(list(enumerate(self.peaks))):
                x = (i / len(self.peaks)) * self.width() if len(self.peaks) > 0 else 0
                h = peak * center_y
                path.lineTo(x, center_y + h)

            path.closeSubpath()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#555"))
            painter.drawPath(path)

        start_x = (self.start_time / self.duration) * self.width() if self.duration > 0 else 0
        end_x = (self.end_time / self.duration) * self.width() if self.duration > 0 else 0

        painter.setBrush(QColor(100, 150, 255, 70))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(QPointF(start_x, 0), QPointF(end_x, self.height())))

        painter.setPen(QPen(QColor("#aaffff"), 2))
        painter.drawLine(int(start_x), 0, int(start_x), self.height())
        painter.drawLine(int(end_x), 0, int(end_x), self.height())

        painter.setBrush(QColor("#aaffff"))
        painter.drawPolygon(QPolygonF([QPointF(start_x,0), QPointF(start_x-5, 5), QPointF(start_x+5, 5)]))
        painter.drawPolygon(QPolygonF([QPointF(end_x,0), QPointF(end_x-5, 5), QPointF(end_x+5, 5)]))

        playhead_x = (self._playback_position / self.duration) * self.width() if self.duration > 0 else 0
        width = getattr(self, '_pulsating_width', 2)
        color = QColor(Styles.Colors.nothing_accent) if getattr(self, '_is_playing', False) else QColor(180, 255, 255, 120)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRect(QRectF(playhead_x - width/2, 0, width, self.height()))

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
                self.set_playback_position(time_pos)
                self.playbackPositionClicked.emit(self.playback_position)

    def mouseMoveEvent(self, event):
        if self.dragging_handle:
            x = event.pos().x()
            time = (x / self.width()) * self.duration if self.duration > 0 else 0
            time = max(0, min(self.duration, time))

            if self.dragging_handle == 'start':
                self.start_time = min(time, self.end_time - 0.01)
                
                if self.playback_position < self.start_time:
                    self.set_playback_position(self.start_time)
            
            elif self.dragging_handle == 'end':
                self.end_time = max(time, self.start_time + 0.01)
                if self.playback_position > self.end_time:
                    self.set_playback_position(self.end_time)

            self.regionChanged.emit(self.start_time, self.end_time)
            self.update()

    def mouseReleaseEvent(self, event):
        self.dragging_handle = None

    def set_times(self, start, end):
        self.start_time = start
        self.end_time = end
        self.update()

    @property
    def playback_position(self):
        return getattr(self, '_playback_position', self.start_time)

    def set_playback_position(self, pos):
        self._playback_position = max(0, min(self.duration, pos))
        self.update()

    @property
    def pulsating_width(self):
        return getattr(self, '_pulsating_width', 2)

    def set_pulsating_width(self, width):
        self._pulsating_width = width
        self.update()

    def set_is_playing(self, is_playing):
        self._is_playing = is_playing
        self.update()

class AudioSetupDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(file_path.split("/")[-1])
        self.setMinimumWidth(700)
        self.setFixedHeight(215)
        self.resize(700, 215)
        
        self.file_path = file_path
        self.audio_data = None
        self.sampling_rate = 22050
        self.sound_object = None
        self.is_playing = False
        self.playback_start_time_in_channel = 0
        self.playback_start_position = 0

        self.setStyleSheet(Styles.Controls.AudioSetupper)

        pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=2048)
        Utils.ui_sound("MenuOpen")

        self.audio_data = None
        self.sampling_rate = 44100
        self.start_time_sec = 0.0
        self.end_time_sec = 1.0

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        self.trim_widget = TrimmingWaveformWidget()
        self.trim_widget.regionChanged.connect(self.update_texboxes)
        self.layout.addWidget(self.trim_widget)

        playback_layout = QHBoxLayout()
        self.start_time_label = UI.AnimatedLineEdit(0, int(self.end_time_sec - 1), 5, ":time")
        self.start_time_label.setFixedSize(70, 40)
        self.start_time_label.setText(0)
        self.start_time_label.textChanged.connect(self.edit_start_time)
        
        self.end_time_label = UI.AnimatedLineEdit(1, self.end_time_sec, 5, ":time")
        self.end_time_label.setFixedSize(70, 40)
        self.end_time_label.setText(int(self.end_time_sec))
        self.end_time_label.textChanged.connect(self.edit_end_time)
        
        self.fade_in_textbox = UI.AnimatedLineEdit(0, 5000, None, "number", "0", "Fade in (Ms)")
        self.fade_in_textbox.setFixedHeight(40)
        self.fade_in_textbox.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        
        self.fade_out_textbox = UI.AnimatedLineEdit(0, 5000, None, "number", "0", "Fade out (Ms)")
        self.fade_out_textbox.setFixedHeight(40)
        self.fade_out_textbox.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        
        self.bpm_input = UI.AnimatedLineEdit(1, 400, None, "number", None, "Counting BPM... 120")
        self.bpm_input.setMinimumWidth(57)
        self.bpm_input.setMaximumWidth(203)
        self.bpm_input.setFixedHeight(Styles.Metrics.element_height)
        self.bpm_input.setStyleSheet("""
            background-color: #2b2b2b;
            color: #fff;
            padding: 8px 12px;
            border-radius: 12px;
        """)

        self.bpm_anim_timer = QTimer(self)
        self.bpm_anim_timer.timeout.connect(self.animate_bpm_spinbox)
        self.bpm_animating = True
        self.bpm_anim_timer.start(14)
        self._bpm_anim_target = np.random.randint(60, 180)
        self._bpm_real_target = None
        self._bpm_anim_speed = 14

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
        self.layout.addLayout(playback_layout)
        self.layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(10)
        
        self.model_selector = UI.Selector(["1", "2", "2a", "3a"])

        self.cancel_button = UI.Button("Cancel")
        self.ok_button = UI.NothingButton("Ok")
        
        self.ok_button.setMaximumWidth(70)
        self.cancel_button.setMaximumWidth(100)
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.close)
        self.play_button.setEnabled(False)
        self.ok_button.setEnabled(False)

        settings_layout.addWidget(self.bpm_input)
        settings_layout.addWidget(self.model_selector)
        settings_layout.addStretch()
        settings_layout.addWidget(self.cancel_button)
        settings_layout.addWidget(self.ok_button)

        self.layout.addLayout(settings_layout)

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self.update_playback)

        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.pulse)
        self.pulse_direction = 1

        self.bpm_worker = BPMAnalyze.BPMWorker(self.file_path)
        self.bpm_worker.bpm_ready.connect(self.on_bpm_ready)
        self.bpm_worker.start()

        self.bpm_input.safeTextChanged.connect(self.on_bpm_changed)
        self.bpm_input.installEventFilter(self)
        
        self.bpm_remove_timer = QTimer(self)
        self.bpm_remove_timer.timeout.connect(self._bpm_remove_step)
        self._bpm_final_bpm = None
        
        self.thread = QThread()
        self.worker = AudioLoaderWorker(self.file_path, self.width())
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.dataReady.connect(self.on_audio_loaded)
        self.worker.dataReady.connect(self.thread.quit)
        self.worker.dataReady.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
    
    @pyqtSlot(np.ndarray, int, list)
    def on_audio_loaded(self, audio_data, sampling_rate, peaks):
        self.audio_data = audio_data
        self.sampling_rate = sampling_rate
        
        self.trim_widget.set_data(audio_data, sampling_rate, peaks)
        
        self.end_time_sec = self.trim_widget.duration
        self.end_time_label.max_number = self.end_time_sec
        self.end_time_label.setText(int(self.end_time_sec))
        self.update_texboxes(self.trim_widget.start_time, self.trim_widget.end_time)

        self.play_button.setEnabled(True)
        self.ok_button.setEnabled(True)
    
    def shrink_bpm_input(self):
        anim = QPropertyAnimation(self.bpm_input, b"maximumWidth")
        anim.setDuration(300)
        anim.setStartValue(self.bpm_input.width())
        anim.setEndValue(57)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
    
        self._bpm_shrink_anim = anim

    def update_texboxes(self, start, end):
        self.start_time_label.blockSignals(True)
        self.end_time_label.blockSignals(True)
        
        self.start_time_label.setText(int(start))
        self.end_time_label.setText(int(end))
        
        self.start_time_label.blockSignals(False)
        self.end_time_label.blockSignals(False)

    def eventFilter(self, obj, event):
        if isinstance(obj, QSpinBox) and isinstance(event, QInputMethodQueryEvent):
            if self.bpm_anim_timer.isActive():
                self.bpm_anim_timer.stop()
                self.stop_bpm_worker()
                self._bpm_real_target = None
                self.bpm_animating = False

        return super().eventFilter(obj, event)
    
    def stop_bpm_worker(self):
        if self.bpm_worker and self.bpm_worker.isRunning():
            self.bpm_worker.requestInterruption()
            self.bpm_worker = None
        
    def closeEvent(self, event):
        self.stop_playback()
        self.stop_bpm_worker()
        self.stop_bpm_animation()
        super().closeEvent(event)

    def edit_start_time(self):
        current_text = self.start_time_label.time_text_to_seconds()
        
        if current_text:
            self.trim_widget.start_time = current_text
            self.trim_widget.update()

            self.end_time_label.min_number = self.start_time_label.time_text_to_seconds()

    def edit_end_time(self):
        current_text = self.end_time_label.time_text_to_seconds()
        
        if current_text:
            self.trim_widget.end_time = current_text
            self.trim_widget.update()

            self.start_time_label.max_number = current_text - 1

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

    def accept(self):
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
        super().accept()

    def on_bpm_ready(self, bpm, first_beat_offset_sec, snapped_times):
        self.snapped_times = snapped_times
        self.first_beat_offset_sec = first_beat_offset_sec

        self._bpm_final_bpm = str(int(bpm))
        self.bpm_anim_timer.stop()
        self.bpm_animating = False

        self.bpm_input.setPlaceholderText(f"Counting BPM {self._bpm_final_bpm}")
        self.bpm_remove_timer.start(60)

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
                self.bpm_input.setPlaceholderText("")
                self.shrink_bpm_input()
        
        else:
            self.bpm_input.setPlaceholderText(current[1:])

    def on_bpm_changed(self, value):
        value = int(value)
        
        if self.is_playing:
            interval = 60000 / value if value > 0 else 500
            self.pulse_timer.stop()
            self.pulse_timer.start(int(interval))

    def toggle_playback(self):
        if self.is_playing:
            self.stop_playback()
        else:
            self.play_selection()

    def play_selection(self):
        if self.audio_data is None or not self.audio_data.any(): return
        current_playback_sec = self.trim_widget.playback_position
        
        if not (self.trim_widget.start_time <= current_playback_sec < self.trim_widget.end_time):
            current_playback_sec = self.trim_widget.start_time
            self.trim_widget.set_playback_position(current_playback_sec)

        start_sample = int(current_playback_sec * self.sampling_rate)

        if start_sample >= len(self.audio_data):
            start_sample = int(self.trim_widget.start_time * self.sampling_rate)
            self.trim_widget.set_playback_position(self.trim_widget.start_time)

        segment = self.audio_data[start_sample:]

        if np.max(np.abs(segment)) > 0:
            sound_data_int = np.int16(segment / np.max(np.abs(segment)) * 32767)
        
        else:
            sound_data_int = np.zeros_like(segment, dtype=np.int16)

        mixer_init = pygame.mixer.get_init()
        
        if mixer_init is not None:
            _, _, channels = mixer_init
        else:
            channels = 1

        if channels == 2:
            if sound_data_int.ndim == 1:
                sound_data_for_pygame = np.column_stack([sound_data_int, sound_data_int])
            else:
                sound_data_for_pygame = sound_data_int

        else:
            if sound_data_int.ndim == 1:
                sound_data_for_pygame = sound_data_int
            else:
                sound_data_for_pygame = sound_data_int[:, 0]

        self.sound_object = pygame.sndarray.make_sound(sound_data_for_pygame)

        self.is_playing = True
        self.sound_object.play()
        self.playback_start_time_in_channel = time.time()
        self.playback_start_position = current_playback_sec

        self.play_button.setIcon(self.pause_icon)
        self.trim_widget.set_is_playing(True)
        self.playback_timer.start(14)

        bpm = self.bpm_input.text()
        if bpm:
            bpm = int(bpm)
            
            if bpm > 0:
                interval = 60000 / (bpm * 2)
                self.pulse_timer.start(int(interval))

    def stop_playback(self):
        self.is_playing = False
        pygame.mixer.stop()

        self.play_button.setIcon(self.play_icon)
        self.trim_widget.set_is_playing(False)
        self.playback_timer.stop()
        self.pulse_timer.stop()
        self.trim_widget.set_pulsating_width(2)

    def update_playback(self):
        if self.is_playing and pygame.mixer.get_busy():
            elapsed_time_sec = time.time() - self.playback_start_time_in_channel
            current_pos_sec = self.playback_start_position + elapsed_time_sec

            if current_pos_sec >= self.trim_widget.end_time:
                current_pos_sec = self.trim_widget.end_time
                
                self.stop_playback()
                self.trim_widget.set_playback_position(current_pos_sec)
            
            else:
                 self.trim_widget.set_playback_position(current_pos_sec)

        elif self.is_playing:
            self.trim_widget.set_playback_position(self.trim_widget.end_time)
            self.stop_playback()


    def pulse(self):
        current_width = self.trim_widget.pulsating_width
        if current_width == 4:
            self.trim_widget.set_pulsating_width(2)
        else:
            self.trim_widget.set_pulsating_width(4)

    def get_settings(self):
        if not hasattr(self, 'start_sample'):
            self.start_sample = int(self.trim_widget.start_time * self.sampling_rate)
        
        if not hasattr(self, 'end_sample'):
            self.end_sample = int(self.trim_widget.end_time * self.sampling_rate)
            
        return {
            "audio": {
                "start_sample": self.start_sample,
                "end_sample": self.end_sample,
                
                "audio_data": self.audio_data,
                "sampling_rate": self.sampling_rate,
                
                "fade_in": self.fade_in_textbox.text(),
                "fade_out": self.fade_out_textbox.text(),
                "duration": self.trim_widget.end_time - self.trim_widget.start_time,
                
                "bpm": self.bpm_input.text() or 120,
                "beats": self.snapped_times
            },
            
            "model": number_model_to_model(self.model_selector.currentText()),
        }