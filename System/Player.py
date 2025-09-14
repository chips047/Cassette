import time
import pygame

import numpy as np

from PyQt5.QtCore import *
from System.Constants import *

from System import Audio

class PlaybackManager(QObject):
    playback_position_updated = pyqtSignal(float)
    playback_state_changed = pyqtSignal(bool)
    audio_loaded = pyqtSignal(np.ndarray, int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_data = None
        self.sampling_rate = SAMPLING_RATE
        self.current_playback_speed_multiplier = 1.0
        self.is_playing = False
        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(FPS_120)
        self.playback_timer.timeout.connect(self._update_playback_position)
        self.playback_start_audio_ms = 0
        self.playback_start_wall_time = 0
        self.playback_current_position = 0

        try:
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.init()
        
        except Exception as e:
            pass

    def load_audio(self, file_path):
        try:
            y, sr = Audio.load_audio(file_path)

            self.audio_data = y
            self.sampling_rate = sr

            pygame.mixer.quit()
            pygame.mixer.init(self.sampling_rate, channels=1 if y.ndim == 1 else 2)

            self.playback_position_updated.emit(0.0)
            
            
            if self.audio_data.dtype != np.int16:
                max_val = np.max(np.abs(self.audio_data))
                self.audio_data = np.int16(self.audio_data / max_val * 32767)
            
            if self.audio_data.ndim == 1:
                self.audio_data = np.column_stack([self.audio_data, self.audio_data])
            
            self.audio_data = np.ascontiguousarray(self.audio_data)
            self.audio_loaded.emit(self.audio_data, self.sampling_rate, len(self.audio_data) / self.sampling_rate)
            
            return True
        
        except Exception as e:
            self.audio_loaded.emit(None, 0, 0)

    def toggle_playback(self, current_playhead_ms):
        if self.is_playing:
            self.stop_playback()
        
        else:
            self.start_playback(current_playhead_ms)

    def start_playback(self, current_playhead_ms):
        if self.audio_data is None or self.is_playing:
            return

        self.playback_start_audio_ms = current_playhead_ms

        try:
            sampling_rate = self.sampling_rate
            if self.current_playback_speed_multiplier != 1.0:
                playback_rate = self.current_playback_speed_multiplier
                sampling_rate = int(self.sampling_rate * playback_rate)

                pygame.mixer.quit()
                pygame.mixer.init(sampling_rate)

            start_sample_offset = int((self.playback_start_audio_ms / 1000.0) * self.sampling_rate)
            segment_to_play = self.audio_data[start_sample_offset:]

            if len(segment_to_play) == 0:
                self.start_playback(0)
                return

            sound = pygame.sndarray.make_sound(segment_to_play)
            sound.play()

            self.playback_start_wall_time = time.time()
            self.playback_timer.start()
            self.is_playing = True
            self.playback_state_changed.emit(True)

        except Exception as e:
            self.is_playing = False
            self.playback_state_changed.emit(False)
    
    def play_tail_with_tape_stop(self):
        start = time.time()

        sr = int(self.sampling_rate)
        start_sample_offset = int((self.playback_current_position / 1000.0) * sr)
        if start_sample_offset >= len(self.audio_data):
            return

        end_idx = min(len(self.audio_data), start_sample_offset + int(1 * sr)) # magic bro

        src_segment = self.audio_data[start_sample_offset:end_idx]
        processed_seg = Audio.variable_tape_stop_array(src_segment, sr)

        pygame.mixer.stop()
        sound = pygame.sndarray.make_sound(processed_seg.copy())
        sound.play()

        end = time.time()

    def stop_playback(self):
        if self.is_playing:
            pygame.mixer.stop()
            self.is_playing = False
            self.playback_timer.stop()
            self.playback_state_changed.emit(False)

    def set_playback_speed_multiplier(self, speed_multiplier):
        self.current_playback_speed_multiplier = speed_multiplier
        
        if self.is_playing:
            self.stop_playback()
            self.start_playback(self.playback_current_position)

    def _update_playback_position(self):
        if self.is_playing and self.audio_data is not None:
            current_wall_time = time.time()
            elapsed_wall_time_ms = (current_wall_time - self.playback_start_wall_time) * 1000.0

            current_audio_ms_offset = elapsed_wall_time_ms * self.current_playback_speed_multiplier
            new_playhead_ms = self.playback_start_audio_ms + current_audio_ms_offset

            audio_duration_ms = (len(self.audio_data) / self.sampling_rate) * 1000.0

            if new_playhead_ms >= audio_duration_ms:
                self.playback_position_updated.emit(audio_duration_ms)
                self.stop_playback()
            
            else:
                self.playback_position_updated.emit(new_playhead_ms)
                self.playback_current_position = new_playhead_ms