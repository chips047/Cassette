import time
import pygame
import librosa

import numpy as np

from PyQt5.QtCore import *
from System.Constants import *

class PlaybackManager(QObject):
    playback_position_updated = pyqtSignal(float)
    playback_state_changed = pyqtSignal(bool)
    audio_loaded = pyqtSignal(np.ndarray, int, float)
    status_message_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_data = None
        self._sampling_rate = SAMPLING_RATE
        self._current_playback_speed_multiplier = 1.0
        self._is_playing = False
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(FPS_60)
        self._playback_timer.timeout.connect(self._update_playback_position)
        self._playback_start_audio_ms = 0
        self._playback_start_wall_time = 0

        try:
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.init()
        
        except Exception as e:
            self.status_message_requested.emit(f"Could not initialize audio playback (Pygame Mixer): {e}.", 0)

    @property
    def is_playing(self):
        return self._is_playing

    @property
    def audio_data(self):
        return self._audio_data

    @property
    def sampling_rate(self):
        return self._sampling_rate

    def load_audio(self, file_path):
        try:
            y, sr = librosa.load(file_path, sr=None)

            self._audio_data = y
            self._sampling_rate = sr

            pygame.mixer.quit()
            pygame.mixer.init(frequency=self._sampling_rate, channels=1 if y.ndim == 1 else 2)

            self.playback_position_updated.emit(0.0)
            self.audio_loaded.emit(self._audio_data, self._sampling_rate, len(self._audio_data) / self._sampling_rate)
            
            return True
        
        except Exception as e:
            self.status_message_requested.emit(f"Failed to load the audio: {str(e)}", 0)
            self.audio_loaded.emit(None, 0, 0)

    def toggle_playback(self, current_playhead_ms):
        if self._is_playing:
            self.stop_playback()
        
        else:
            self.start_playback(current_playhead_ms)

    def start_playback(self, current_playhead_ms):
        if self._audio_data is None or self._is_playing:
            return

        self._playback_start_audio_ms = current_playhead_ms

        try:
            playback_rate = self._current_playback_speed_multiplier
            slowed_sampling_rate = int(self._sampling_rate * playback_rate)

            pygame.mixer.quit()
            pygame.mixer.init(frequency=slowed_sampling_rate, channels=1 if self._audio_data.ndim == 1 else 2)

            start_sample_offset = int((self._playback_start_audio_ms / 1000.0) * self._sampling_rate)
            segment_to_play = self._audio_data[start_sample_offset:]

            if len(segment_to_play) == 0:
                self.status_message_requested.emit("Nothing to play from current position.", 3000)
                return

            sound_data = np.int16(segment_to_play / np.max(np.abs(segment_to_play)) * 32767)

            if sound_data.ndim == 1:
                sound_data = np.column_stack([sound_data, sound_data])

            sound = pygame.sndarray.make_sound(sound_data.copy(order='C'))
            sound.play()

            self._playback_start_wall_time = time.time()
            self._playback_timer.start(14)
            self._is_playing = True
            self.playback_state_changed.emit(True)

        except Exception as e:
            self.status_message_requested.emit(f"Error during playback: {e}", 0)
            self._is_playing = False
            self.playback_state_changed.emit(False)

    def stop_playback(self):
        if self._is_playing:
            pygame.mixer.stop()
            self._is_playing = False
            self._playback_timer.stop()
            self.playback_state_changed.emit(False)
            self.status_message_requested.emit("Paused.", 2000)

    def set_playback_speed_multiplier(self, speed_multiplier):
        self._current_playback_speed_multiplier = speed_multiplier
        
        if self._is_playing:
            current_playhead_ms = self._playback_start_audio_ms + (time.time() - self._playback_start_wall_time) * 1000.0 * self._current_playback_speed_multiplier
            self.stop_playback()
            self.start_playback(current_playhead_ms)

    def _update_playback_position(self):
        if self._is_playing and self._audio_data is not None:
            current_wall_time = time.time()
            elapsed_wall_time_ms = (current_wall_time - self._playback_start_wall_time) * 1000.0

            current_audio_ms_offset = elapsed_wall_time_ms * self._current_playback_speed_multiplier
            new_playhead_ms = self._playback_start_audio_ms + current_audio_ms_offset

            audio_duration_ms = (len(self._audio_data) / self._sampling_rate) * 1000.0

            if new_playhead_ms >= audio_duration_ms:
                self.playback_position_updated.emit(audio_duration_ms)
                self.stop_playback()
                self.status_message_requested.emit("Playback finished.", 3000)
            
            else:
                self.playback_position_updated.emit(new_playhead_ms)