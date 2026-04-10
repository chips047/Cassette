from __future__ import annotations

import re
import math
import time
import aubio
import queue
import numpy
import random
import miniaudio
import soundfile
import threading

from loguru import logger
from pathlib import Path

from System.Common import Utils

from PyQt5.QtCore import (
    QTimer,
    QObject,
    pyqtSignal
)

from System.Interface.Animation.LoomEngine import (
    Easing,
    MixMode,
    AnimationEngine
)

def thread_excepthook(arguments) -> None:
    logger.exception(
        "Unhandled exception in thread %s",
        arguments.thread.name,
        exc_info = (
            arguments.exc_type,
            arguments.exc_value,
            arguments.exc_traceback
        )
    )

threading.excepthook = thread_excepthook

# Audio Playback

class PlaybackManager(QObject):
    playback_state_changed = pyqtSignal(bool)
    audio_loaded           = pyqtSignal(numpy.ndarray, int, float)
    speed_changed          = pyqtSignal(float)

    beat_normal            = pyqtSignal(float)
    beat_heavy             = pyqtSignal(float)

    def __init__(
            self,
            *arguments,
            **keywords
        ) -> None:

        super().__init__(*arguments, **keywords)

        self.is_playing = False

        self.playback_start_audio_ms  = 0
        self.playback_start_wall_time = 0

        self.lock          = threading.RLock()
        self.stream        = None
        self.mix_generator = None

        self.setup_effect_properties()
        self.reset_playback_state()
        self.setup_beat_detection()
    
    @property
    def speed(self):
        return self.loom.get_property_value("speed")
    
    @property
    def volume(self):
        return self.loom.get_property_value("volume")

    # Beat Detection

    def beat_emitter_worker(self) -> None:
        while True:
            item = self.beat_queue.get()

            if item is None:
                break

            is_heavy, rms = item

            if is_heavy:
                self.beat_heavy.emit(rms)

            self.beat_normal.emit(rms)

    # Setup

    def setup_beat_detection(self) -> None:
        self.win_s = 2048
        self.hop_s = 512

        self.beat_queue  = None
        self.beat_thread = None

        self.last_heavy_time     = 0
        self.heavy_cooldown      = 0.3
        self.heavy_rms_threshold = 0.2

        self.onset_detector = aubio.onset("mkl", self.win_s, self.hop_s, self.fs or 44100)
        self.onset_detector.set_threshold(0.345)

        self.beat_queue = queue.Queue(maxsize = 100)

        self.beat_thread = threading.Thread(
            target = self.beat_emitter_worker,
            daemon = True
        )

        self.beat_thread.start()

    def setup_effect_properties(self) -> None:
        self.loom = AnimationEngine(fps = 60)

        self.loom.add_properties(
            [
                ("speed",               1.0,    MixMode.NOMIX, self.update_playback_start),
                ("volume",              1.0,    MixMode.NOMIX),
                ("channel_delay_left",  0.0,    MixMode.NOMIX),
                ("channel_delay_right", 0.0,    MixMode.NOMIX),
                ("midpass_center",      1000.0, MixMode.NOMIX),
                ("midpass_q",           1.0,    MixMode.NOMIX),
                ("midpass_mix",         0.0,    MixMode.NOMIX),
                ("midpass_gain",        1.0,    MixMode.NOMIX),
                ("bitcrush_bits",       16,     MixMode.NOMIX),
                ("bitcrush_downsample", 1,      MixMode.NOMIX),
                ("bitcrush_mix",        0.0,    MixMode.NOMIX)
            ]
        )

    def reset_playback_state(self) -> None:
        defaults = {
            "speed":               1.0,
            "volume":              1.0,
            "channel_delay_left":  0.0,
            "channel_delay_right": 0.0,
            "midpass_center":      1000.0,
            "midpass_q":           1.0,
            "midpass_mix":         0.0,
            "midpass_gain":        1.0,
            "bitcrush_bits":       16,
            "bitcrush_downsample": 1,
            "bitcrush_mix":        0.0
        }

        for property, value in defaults.items():
            self.loom.set_property_base_value(property, value)

        self.fs                  = 44100
        self.position            = 0.0
        self.is_playing          = False
        self.duration_ms         = 0

        self.track_peak_level    = 1.0
        self.current_audio_level = 0.0
        self.filter_states       = None

    # Audio Loading

    def load_audio(self, path: str) -> None:
        data, fs = soundfile.read(path, dtype = 'float32')

        if data.ndim == 1:
            data = numpy.column_stack((data, data))

        self.load_audio_from_data(data, fs)

    def load_audio_from_data(
            self,
            data: numpy.ndarray,
            fs:   int
        ) -> None:

        fs_changed = self.fs != fs

        with self.lock:
            self.reset_playback_state()

            self.fs          = fs
            self.data        = data
            self.duration_ms = len(self.data) / self.fs * 1000

            if self.data.ndim == 1:
                self.data = numpy.stack([self.data, self.data], axis = -1)
            
            self.filter_states = numpy.zeros((self.data.shape[1], 4), dtype='float64')

        if fs_changed or not self.stream:
            self.open_stream()

        self.audio_loaded.emit(
            self.data,
            self.fs,
            len(self.data) / self.fs
        )

    def open_stream(self) -> None:
        self.close_stream()

        max_abs = numpy.max(numpy.abs(self.data))

        with self.lock:
            self.filter_states    = numpy.zeros((self.data.shape[1], 4), dtype = 'float64')
            self.track_peak_level = max(max_abs, 1e-6)

        self.stream = miniaudio.PlaybackDevice(
            output_format    = miniaudio.SampleFormat.SIGNED16,
            nchannels        = self.data.shape[1],
            sample_rate      = self.fs,
            buffersize_msec  = 15,
            callback_periods = 4,
            thread_prio      = miniaudio.ThreadPriority.HIGHEST
        )

        self.mix_generator = self.create_playback_generator()
        next(self.mix_generator)

        self.stream.start(self.mix_generator)
    
    def close_stream(self) -> None:
        try:
            if not self.stream:
                return

            self.stream.stop()
            self.stream.close()

            self.stream        = None
            self.mix_generator = None
        
        except Exception as error:
            logger.error(f"Failed to close the stream: {error}")

    # Position Tracking

    def get_position(self) -> float:
        elapsed_ms = (time.time() - self.playback_start_wall_time) * 1000
        return self.playback_start_audio_ms + elapsed_ms * self.loom.get_property_value("speed")

    def update_playback_start(self, speed: float) -> None:
        self.speed_changed.emit(speed)

        self.playback_start_audio_ms  = self.get_position()
        self.playback_start_wall_time = time.time()

    # Playback Control

    def toggle_playback(self, ms: float = None) -> None:
        if self.is_playing:
            self.stop()
        
        else:
            self.play(ms)

    def stop(self) -> None:
        with self.lock:
            self.is_playing = False

        self.playback_state_changed.emit(False)

    def play(self, start_position_ms: float) -> None:
        self.playback_state_changed.emit(True)

        with self.lock:
            self.position   = int(start_position_ms * self.fs / 1000)
            self.is_playing = True

        self.playback_start_audio_ms  = start_position_ms
        self.playback_start_wall_time = time.time()

    # Audio Processing

    def generate_resampled_block(
            self,
            frames:  int,
            context: dict
        ) -> numpy.ndarray:

        channels = self.data.shape[1]
        time     = numpy.arange(frames, dtype = 'float32')

        base_indices  = context["position"] + time * context["speed"]
        delay_samples = (context["delays"] * context["fs"] / 1000.0).astype('float32')

        result              = numpy.empty((frames, channels), dtype = 'float32')
        max_index_minus_one = context["max_index"] - 1

        for channel in range(channels):
            channel_position = base_indices - delay_samples[channel]

            index_integer = channel_position.astype(numpy.int32)
            index_float   = channel_position - index_integer

            valid_mask = (index_integer >= 0) & (index_integer < max_index_minus_one)

            safe_index = index_integer[valid_mask]
            sample_0   = self.data[safe_index, channel]
            sample_1   = self.data[safe_index + 1, channel]

            channel_result             = numpy.zeros(frames, dtype = 'float32')
            channel_result[valid_mask] = sample_0 + index_float[valid_mask] * (sample_1 - sample_0)

            end_mask                   = index_integer >= max_index_minus_one
            channel_result[end_mask]   = self.data[context["max_index"], channel]

            result[:, channel] = channel_result

        return result

    def apply_midpass_filter(
            self,
            block:   numpy.ndarray,
            context: dict,
            states:  object
        ) -> numpy.ndarray:

        mix = context["filter_mix"]
        gain = context["filter_gain"]
        
        a, b = self.compute_biquad_bandpass(
            context["midpass_center"],
            context["midpass_q"]
        )

        if mix <= 0:
            return block

        b0, b1, b2 = b
        a1, a2     = a

        filtered = numpy.empty_like(block)

        for channel in range(block.shape[1]):
            x = block[:, channel]
            y = numpy.empty(len(x), dtype = 'float32')

            x1, x2, y1, y2 = states[channel]

            for n in range(len(x)):
                yn   = b0 * x[n] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                y[n] = yn

                x2 = x1
                x1 = x[n]
                y2 = y1
                y1 = yn

            states[channel]      = [x1, x2, y1, y2]
            filtered[:, channel] = y

        return (1.0 - mix) * block + (mix * filtered * gain)

    def apply_bitcrush(
            self,
            block:   numpy.ndarray,
            context: dict
        ) -> numpy.ndarray:

        mix = context["bc_mix"]

        if mix <= 0:
            return block

        down       = max(1, int(context["bc_down"]))
        bits       = max(1, min(24, context["bc_bits"]))
        levels     = (1 << int(bits)) - 1
        inv_levels = 1.0 / levels

        if down > 1:
            original_shape = block.shape
            new_len        = (len(block) // down) * down
            reduced        = block[:new_len].reshape(-1, down, original_shape[1])
            crushed        = numpy.repeat(reduced[:, 0, :], down, axis = 0)

            if len(block) > new_len:
                last_val = block[new_len:new_len + 1]
                padding  = numpy.repeat(last_val, len(block) - new_len, axis = 0)
                crushed  = numpy.vstack([crushed, padding])

        else:
            crushed = block.copy()

        crushed = numpy.round((crushed + 1.0) * 0.5 * levels) * inv_levels
        crushed = crushed * 2.0 - 1.0

        return (1.0 - mix) * block + mix * crushed

    def process_audio_chunk(self, frames: int) -> numpy.ndarray:
        ctx = {
            "position":       self.position,
            "speed":          self.loom.get_property_value("speed"),
            "volume":         self.loom.get_property_value("volume"),
            "fs":             self.fs,
            
            "max_index":      len(self.data) - 1,
            
            "delays":         numpy.array(
                                    [
                                        self.loom.get_property_value("channel_delay_left"),
                                        self.loom.get_property_value("channel_delay_right")
                                    ], dtype = 'float64'
                                ),
            
            "midpass_q":      self.loom.get_property_value("midpass_q"),
            "filter_mix":     self.loom.get_property_value("midpass_mix"),
            "filter_gain":    self.loom.get_property_value("midpass_gain"),
            "midpass_center": self.loom.get_property_value("midpass_center"),
            
            "bc_mix":         self.loom.get_property_value("bitcrush_mix"),
            "bc_bits":        self.loom.get_property_value("bitcrush_bits"),
            "bc_down":        self.loom.get_property_value("bitcrush_downsample")
        }

        block = self.generate_resampled_block(frames, ctx)

        self.process_beat_detection(block)

        if self.filter_states is not None:
            block = self.apply_midpass_filter(block, ctx, self.filter_states)

        block = self.apply_bitcrush(block, ctx)

        block *= ctx["volume"]

        self.position += frames * ctx["speed"]
        self.current_audio_level = float(numpy.max(numpy.abs(block)) / self.track_peak_level)

        if self.position >= len(self.data):
            self.stop()

        return block

    def create_playback_generator(self) -> object:
        data = yield b""

        while True:
            frames = data

            with self.lock:
                if not self.is_playing or self.data is None:
                    channels = self.data.shape[1] if self.data is not None else 2
                    block = numpy.zeros((frames, channels), dtype='float32')
                
                else:
                    block = self.process_audio_chunk(frames)

            block = numpy.clip(block, -1.0, 1.0)
            pcm = (block * 32767.0).astype(numpy.int16)
            data = yield pcm.tobytes()

    # Beat Detection

    def process_beat_detection(self, block: numpy.ndarray) -> None:
        mono = numpy.mean(block, axis = 1).astype('float32')

        for i in range(0, len(mono), self.hop_s):
            segment = mono[i:i + self.hop_s]

            if len(segment) < self.hop_s:
                break

            is_onset = self.onset_detector(segment)

            if not is_onset:
                continue

            rms = numpy.sqrt(numpy.mean(segment ** 2))
            current_time = time.time()
            is_heavy = False

            if (current_time - self.last_heavy_time) > self.heavy_cooldown:
                if rms > self.heavy_rms_threshold:
                    is_heavy = True
                    self.last_heavy_time = current_time

            try:
                self.beat_queue.put_nowait((is_heavy, float(rms)))

            except queue.Full:
                pass
    
    # Biquad Filter

    def compute_biquad_bandpass(
            self,
            center_hz: float,
            q:         float
        ) -> tuple:

        fs = float(self.fs)

        if fs is None or fs <= 0:
            return (1.0, 0.0, 0.0), (0.0, 0.0)

        omega = 2.0 * math.pi * (center_hz / fs)
        sn    = math.sin(omega)
        cs    = math.cos(omega)
        alpha = sn / (2.0 * q)

        b0 = alpha
        b1 = 0.0
        b2 = -alpha
        a0 = 1.0 + alpha
        a1 = -2.0 * cs
        a2 = 1.0 - alpha

        b0 /= a0
        b1 /= a0
        b2 /= a0
        a1 /= a0
        a2 /= a0

        return (a1, a2), (b0, b1, b2)

    def get_current_audio_level(self) -> float:
        return self.current_audio_level

    # API
    # Channel Delay

    def set_channel_delay(
            self,
            left_to_ms:    float  = None,
            right_to_ms:   float  = None,
            duration_ms:   int    = 0,
            easing:        Easing = Easing.smooth
        ) -> None:

        if (
            not left_to_ms and
            not right_to_ms
        ): return

        if left_to_ms is None:
            left_to_ms = self.loom.get_property_value("channel_delay_left")

        if right_to_ms is None:
            right_to_ms = self.loom.get_property_value("channel_delay_right")

        if not duration_ms:
            self.loom.set_property_base_value("channel_delay_left", left_to_ms)
            self.loom.set_property_base_value("channel_delay_right", right_to_ms)

            return

        self.loom.set_target_value("channel_delay_left",  left_to_ms,  duration_ms, easing)
        self.loom.set_target_value("channel_delay_right", right_to_ms, duration_ms, easing)

    # Speed Control

    def set_speed(
            self,
            new_speed:          float,
            duration_ms:        int    = 0,
            easing:             Easing = Easing.smooth,
            cleanup_on_finish:  bool   = False,
            shutdown_on_finish: bool   = False
        ) -> None:

        self.update_playback_start(new_speed)

        if not duration_ms:
            self.loom.set_property_base_value("speed", new_speed)

            if cleanup_on_finish:
                self.reset_playback_state()
            
            elif shutdown_on_finish:
                self.full_shutdown()

            return

        self.loom.set_target_value("speed", new_speed, duration_ms, easing)

        if cleanup_on_finish:
            QTimer.singleShot(duration_ms, self.reset_playback_state)
        
        elif shutdown_on_finish:
            QTimer.singleShot(duration_ms, self.full_shutdown)

    # Volume Control

    def set_volume(
            self,
            volume:      float,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        if not duration_ms:
            self.loom.set_property_base_value("volume", max(0.0, min(volume, 1.0)))

            return

        self.loom.set_target_value("volume", volume, duration_ms, easing)

    # Bitcrush Effect

    def set_bitcrush(
            self,
            bits:        int    = 24,
            downsample:  int    = 1,
            mix:         float  = 0.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        if not duration_ms:
            self.loom.set_property_base_value("bitcrush_bits", bits)
            self.loom.set_property_base_value("bitcrush_downsample", downsample)
            self.loom.set_property_base_value("bitcrush_mix", mix)
            
            return

        self.loom.set_target_value("bitcrush_bits",       bits,       duration_ms, easing)
        self.loom.set_target_value("bitcrush_downsample", downsample, duration_ms, easing)
        self.loom.set_target_value("bitcrush_mix",        mix,        duration_ms, easing)

    # Midpass Effect

    def set_midpass(
        self,
        q:           float  = 1.0,
        mix:         float  = 1.0,
        gain:        float  = 1.0,
        center_hz:   float  = 1000.0,
        duration_ms: int    = 0,
        easing:      Easing = Easing.smooth
    ) -> None:

        if not duration_ms:
            self.loom.set_property_base_value("midpass_center", center_hz)
            self.loom.set_property_base_value("midpass_q",      q)
            self.loom.set_property_base_value("midpass_mix",    mix)
            self.loom.set_property_base_value("midpass_gain",   gain)

            if mix == 0.0 and self.filter_states is not None:
                with self.lock:
                    self.filter_states.fill(0.0)

            return

        self.loom.set_target_value("midpass_center", center_hz, duration_ms, easing)
        self.loom.set_target_value("midpass_q",      q,         duration_ms, easing)
        self.loom.set_target_value("midpass_mix",    mix,       duration_ms, easing)
        self.loom.set_target_value("midpass_gain",   gain,      duration_ms, easing)

        if mix == 0.0 and self.filter_states is not None:
            QTimer.singleShot(
                duration_ms,
                lambda: self.filter_states.fill(0.0)
            )

    # Cleanup

    def full_shutdown(self) -> None:
        self.reset_playback_state()
        self.loom.clear()

        with self.lock:
            self.close_stream()

            if self.beat_queue:
                self.beat_queue.put(None)

# UI Sound Player

class UISound:
    def __init__(
            self,
            sound_id: int,
            manager:  UISoundManager
        ) -> None:

        self.sound_id = sound_id
        self.manager  = manager

    def set_speed(self, new_speed: float) -> None:
        self.manager.set_speed(self.sound_id, new_speed)

    def set_volume(self, new_volume: float) -> None:
        self.manager.set_volume(self.sound_id, new_volume)

    def stop(self) -> None:
        self.manager.stop_sound(self.sound_id)

class UISoundManager:
    def __init__(self) -> None:
        self.preloaded     = {}
        self.active_sounds = {}

        self.lock          = threading.RLock()

        self.sample_rate   = 44100
        self.channels      = 2

        self.next_sound_id = 0
        self.device        = None

    def ensure_device(self):
        if self.device:
            return

        self.device = miniaudio.PlaybackDevice(
            output_format    = miniaudio.SampleFormat.SIGNED16,
            nchannels        = self.channels,
            sample_rate      = self.sample_rate,
            buffersize_msec  = 15,
            callback_periods = 4,
            thread_prio      = miniaudio.ThreadPriority.HIGHEST
        )

        self.mix_generator = self.create_mix_generator()
        next(self.mix_generator)

        self.device.start(self.mix_generator)

    def preload(
            self,
            path: str,
            name: str
        ) -> None:

        if name in self.preloaded:
            logger.warning(f"{name} is already existing. Sound was not loaded")
            return

        data, fs = soundfile.read(path, dtype = 'float32')

        if data.ndim == 1:
            data = numpy.column_stack((data, data))

        if fs != self.sample_rate:
            logger.warning(f"Sampling rate for {name} does not match player's sampling rate. Resampling...")

            ratio       = self.sample_rate / fs
            num_samples = int(len(data) * ratio + 0.5)

            if num_samples < 1:
                num_samples = 1

            indices   = numpy.linspace(0, len(data) - 1, num_samples, endpoint = False)
            resampled = numpy.empty((num_samples, self.channels), dtype = 'float32')

            for channel in range(self.channels):
                resampled[:, channel] = numpy.interp(
                    indices,
                    numpy.arange(len(data)),
                    data[:, channel]
                )

            data = resampled

        self.preloaded[name] = data
        logger.success(f"{name} loaded")

    def play_sound(
        self,
        name:                   str,
        loop:                   bool  = False,
        speed:                  float = 1.0,
        volume:                 float = 1.0,
        enable_tone_randomizer: bool  = True,
        tone_spread:            float = 0.04
    ) -> UISound:

        if name not in self.preloaded:
            return UISound(-1, self)

        self.ensure_device()

        sound_id = self.next_sound_id
        self.next_sound_id += 1

        if speed == 1.0 and enable_tone_randomizer:
            speed = random.uniform(1.0 + tone_spread, 1.0 - tone_spread)

        instance = {
            "data":     self.preloaded[name],
            "position": 0.0,
            "speed":    speed,
            "volume":   volume,
            "loop":     loop,
            "active":   True
        }

        with self.lock:
            while len(self.active_sounds) >= 60:
                oldest_id = next(iter(self.active_sounds))
                self.active_sounds[oldest_id]["active"] = False
                
                del self.active_sounds[oldest_id]

            self.active_sounds[sound_id] = instance

        return UISound(sound_id, self)

    def stop_sound(self, sound_id: int) -> None:
        with self.lock:
            sound = self.active_sounds.pop(sound_id, None)
            
            if sound:
                sound["active"] = False

    def set_speed(
            self,
            sound_id:  int,
            speed:     float
        ) -> None:

        with self.lock:
            sound = self.active_sounds.get(sound_id)
            
            if sound:
                sound["speed"] = speed

    def set_volume(
            self,
            sound_id:   int,
            new_volume: float
        ) -> None:

        with self.lock:
            sound = self.active_sounds.get(sound_id)
            
            if sound:
                sound["volume"] = new_volume

    def stop_all(self) -> None:
        with self.lock:
            for sound in self.active_sounds.values():
                sound["active"] = False
            
            self.active_sounds.clear()

    def cleanup(self) -> None:
        if not self.device:
            return
        
        self.device.stop()
        self.device.close()
        self.device = None

    def create_mix_generator(self) -> object:
        data = yield b""

        while True:
            frames = data
            block  = numpy.zeros((frames, self.channels), dtype = 'float32')

            with self.lock:
                for sound_id in list(self.active_sounds.keys()):
                    sound = self.active_sounds.get(sound_id)
                    
                    if sound is None:
                        continue

                    if not sound["active"]:
                        del self.active_sounds[sound_id]
                        continue

                    sound_block = self.get_resampled_block(sound, frames)

                    if sound_block is None:
                        sound["active"] = False
                        del self.active_sounds[sound_id]
                        continue

                    block += sound_block * sound["volume"]

            block = numpy.clip(block, -1.0, 1.0)
            pcm   = (block * 32767.0).astype(numpy.int16)
            data  = yield pcm.tobytes()

    def get_resampled_block(
            self,
            sound:  dict,
            frames: int
        ) -> numpy.ndarray | None:

        data = sound["data"]

        if len(data) == 0:
            return None

        position   = sound["position"]
        speed      = sound["speed"]
        max_index  = len(data) - 1

        if position >= max_index and not sound["loop"]:
            return None

        t             = numpy.arange(frames, dtype = 'float32')
        base_indices  = position + t * speed
        result        = numpy.empty((frames, self.channels), dtype = 'float32')

        for channel in range(self.channels):
            channel_position = base_indices
            index_integer    = channel_position.astype(numpy.int32)
            index_float      = channel_position - index_integer
            valid            = (index_integer >= 0) & (index_integer < max_index)
            channel_result   = numpy.zeros(frames, dtype = 'float32')

            if numpy.any(valid):
                safe                  = index_integer[valid]
                sample_0              = data[safe, channel]
                sample_1              = data[safe + 1, channel]
                channel_result[valid] = sample_0 + index_float[valid] * (sample_1 - sample_0)

            beyond = index_integer >= max_index
            channel_result[beyond]  = data[max_index, channel] if max_index >= 0 else 0.0
            result[:, channel]      = channel_result

        new_position = position + frames * speed

        if new_position >= len(data):
            if sound["loop"]:
                new_position = new_position % len(data)
            
            else:
                new_position = len(data)

        sound["position"] = new_position

        return result

def shift_right_unsigned(value: int, amount: int) -> int:
    return (value % 0x100000000) >> (amount & 0x1F)

class ByteBeatPlayer:
    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate       = sample_rate
        self.channels          = 1
        self.device            = None
        self.lock              = threading.RLock()
        
        self.formula_bytecode  = None
        self.time_index        = 0
        self.volume            = 0.3
        self.time_scale        = 8000 / self.sample_rate

        self.current_intensity = 0.0
        
        self.execution_context = {
            "int":    int,
            "math":   math,
            "sin":    math.sin,
            "js_shr": shift_right_unsigned,
            "__builtins__": None,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "atan2": math.atan2,
            "sqrt": math.sqrt,
            "exp": math.exp,
            "log": math.log,
            "log10": math.log10,
            "ceil": math.ceil,
            "floor": math.floor,
            "PI": math.pi,
            "E": math.e,
            "random": numpy.random.random,
            "parseInt": lambda s, r=10: int(str(s), r),
            "js_shr": shift_right_unsigned,
            "__builtins__": None
        }

    def preprocess_formula(self, formula: str) -> str:
        result = formula
        
        result = result.replace("&&", " and ")
        result = result.replace("||", " or ")
        result = result.replace("!", " not ")
        
        result = re.sub(r"(\S+)\s*>>>\s*(\S+)", r"js_shr(\1, \2)", result)
        
        result = result.replace("floor", "int")
        result = result.replace("sin", "math.sin")
        
        return result

    def set_formula(self, formula_string: str) -> None:
        try:
            processed_formula = self.preprocess_formula(formula_string)
            compiled          = compile(processed_formula, "<string>", "eval")
        
        except:
            logger.error(f"Formula incorrect: {formula_string}")
            return
        
        with self.lock:
            self.formula_bytecode = compiled
            self.time_index       = 0

    def ensure_device(self) -> None:
        if self.device:
            return

        self.device = miniaudio.PlaybackDevice(
            output_format = miniaudio.SampleFormat.SIGNED16,
            nchannels     = self.channels,
            sample_rate   = self.sample_rate
        )
        
        self.generator = self.create_generator()
        next(self.generator)
        
        self.device.start(self.generator)

    def generate_silence_block(self, number_of_frames: int) -> bytes:
        silence_buffer = numpy.zeros(number_of_frames, dtype = numpy.int16)
        
        return silence_buffer.tobytes()

    def calculate_single_sample(self, time_value: int) -> int:
        self.execution_context["t"] = time_value
        
        try:
            calculation_result = eval(self.formula_bytecode, self.execution_context)
            byte_value         = int(calculation_result) & 255
            
            return int((byte_value - 128) * 254 * self.volume)
        
        except Exception:
            return 0

    def process_audio_block(self, number_of_frames: int) -> bytes:
        output_buffer = numpy.zeros(number_of_frames, dtype = numpy.int16)
        
        with self.lock:
            for index in range(number_of_frames):
                scaled_time = int(self.time_index * self.time_scale)
                output_buffer[index] = self.calculate_single_sample(scaled_time)
                
                self.time_index += 1
            
            if number_of_frames > 0:
                normalized = output_buffer.astype(numpy.float32) / 32768.0
                rms        = float(numpy.sqrt(numpy.mean(normalized ** 2)))

                self.current_intensity = rms * 2.0
        
        return output_buffer.tobytes()

    def create_generator(self) -> object:
        number_of_frames = yield b""
        
        while True:
            if self.formula_bytecode is None:
                number_of_frames = yield self.generate_silence_block(number_of_frames)
                continue

            number_of_frames = yield self.process_audio_block(number_of_frames)

    def get_current_intensity(self):
        return self.current_intensity

    def play(self) -> None:
        self.ensure_device()

    def cleanup(self) -> None:
        if self.device:
            self.device.stop()
            self.device.close()
        
        self.device           = None
        self.formula_bytecode = None
        self.time_index       = 0
        
        self.execution_context["t"] = 0

# Singletons

player    = PlaybackManager()
ui_player = UISoundManager()

# Preload

prefix    = "System/Assets/Sounds"
base_path = Utils.get_resource_path(prefix)
base      = Path(base_path)

sounds = []

for path in base.rglob("*.wav"):
    rel  = path.relative_to(base).as_posix()
    name = rel[:-4]
    full_path = Utils.get_resource_path(f"{prefix}/{rel}")
    
    sounds.append((full_path, name))

for path, name in sounds:
    ui_player.preload(path, name)