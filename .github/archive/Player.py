from __future__ import annotations

import re
import math
import time
import queue
import aubio
import numpy
import random
import miniaudio
import soundfile
import threading

from pathlib import Path
from loguru import logger

from PyQt6.QtCore import (
    QTimer,
    QObject,
    pyqtSignal
)

from System.Common import Utils

from System.Interface.Animation.LoomEngine import (
    Easing,
    MixMode,
    AnimationEngine
)

from System.Accelerated.PlayerFunctions import (
    resample_block,
    apply_noise_mix,
    apply_eq_triple,
    mix_audio_blocks,
    apply_biquad_block,
    apply_reverb_block,
    apply_bitcrush_block,
    process_ui_sound_fast,
    generate_colored_noise,
    process_ui_sound_interp,
    apply_glitch_noise_block,
    calculate_peaking_coefficients,
    calculate_bandpass_coefficients,
    calculate_lowshelf_coefficients,
    calculate_highshelf_coefficients
)

def thread_excepthook(arguments: object) -> None:
    logger.exception(
        "Unhandled exception in thread {}",
        arguments.thread.name,

        exc_info = (
            arguments.exc_type,
            arguments.exc_value,
            arguments.exc_traceback
        )
    )

threading.excepthook = thread_excepthook

class PlaybackManager(QObject):
    playback_state_changed = pyqtSignal(bool)
    audio_loaded           = pyqtSignal(numpy.ndarray, int, float)
    speed_changed          = pyqtSignal(float)
    beat_normal            = pyqtSignal(float)
    beat_heavy             = pyqtSignal(float)

    def __init__(
            self,
            *arguments: object,
            **keywords: object
        ) -> None:

        super().__init__(*arguments, **keywords)

        self.lock                     = threading.RLock()
        self.stream                   = None
        self.mix_generator            = None
        self.beat_queue               = None
        self.beat_thread              = None
        self.onset_detector           = None

        self.data                     = None
        self.fs                       = 44100
        self.position                 = 0.0
        self.duration_ms              = 0.0
        self.is_playing               = False
        self.track_peak_level         = 1.0
        self.current_audio_level      = 0.0
        self.playback_start_audio_ms  = 0.0
        self.playback_start_wall_time = 0.0

        self.filter_states            = None
        self.eq_low_states            = None
        self.eq_mid_states            = None
        self.eq_high_states           = None

        self.is_glitching             = False
        self.glitch_frames_remaining  = 0
        self.glitch_saved_position    = 0.0
        self.glitch_mode              = "random"
        self.glitch_active_mode       = "noise"
        self.glitch_total_frames      = 0
        self.glitch_elapsed_frames    = 0
        self.glitch_noise_color       = "pink"

        self.setup_effect_properties()
        self.reset_playback_state()
        self.setup_beat_detection()

    # Properties

    @property
    def speed(self) -> float:
        return self.loom.get_property_value("speed")

    @property
    def volume(self) -> float:
        return self.loom.get_property_value("volume")

    # Setup

    def setup_effect_properties(self) -> None:
        self.loom = AnimationEngine(fps = 60)

        self.loom.add_properties(
            [
                ("speed",                   1.0,    MixMode.NOMIX, self.update_playback_start),
                ("volume",                  1.0,    MixMode.NOMIX),
                ("channel_delay_left",      0.0,    MixMode.NOMIX),
                ("channel_delay_right",     0.0,    MixMode.NOMIX),
                ("midpass_center",          1000.0, MixMode.NOMIX),
                ("midpass_q",               1.0,    MixMode.NOMIX),
                ("midpass_mix",             0.0,    MixMode.NOMIX),
                ("midpass_gain",            1.0,    MixMode.NOMIX),
                ("bitcrush_bits",           16,     MixMode.NOMIX),
                ("bitcrush_downsample",     1,      MixMode.NOMIX),
                ("bitcrush_mix",            0.0,    MixMode.NOMIX),
                ("eq_low",                  1.0,    MixMode.NOMIX),
                ("eq_mid",                  1.0,    MixMode.NOMIX),
                ("eq_high",                 1.0,    MixMode.NOMIX),
                ("noise_mix",               0.0,    MixMode.NOMIX),
                ("reverb_mix",              0.0,    MixMode.NOMIX),
                ("glitch_intensity",        0.0,    MixMode.NOMIX),
                ("glitch_noise_mix",        0.0,   MixMode.NOMIX),
                ("glitch_noise_attack_ms",  180.0,   MixMode.NOMIX),
                ("glitch_voice_mix",        0.0,    MixMode.NOMIX),
                ("glitch_voice_delay_ms",   140.0,   MixMode.NOMIX),
            ]
        )

    def set_property(
            self,
            property_name: str,
            value:         float,
            duration_ms:   int             = 0,
            easing:        Easing          = Easing.smooth,
            on_finish:     callable | None = None
        ) -> None:

        if duration_ms <= 0:
            self.loom.set_property_base_value(property_name, value)

            if on_finish:
                on_finish()

            return

        self.loom.set_target_value(property_name, value, duration_ms, easing)

        if on_finish:
            QTimer.singleShot(duration_ms, on_finish)

    def reset_playback_state(self) -> None:
        defaults = {
            "speed":                   1.0,
            "volume":                  1.0,
            "channel_delay_left":      0.0,
            "channel_delay_right":     0.0,
            "midpass_center":          1000.0,
            "midpass_q":               1.0,
            "midpass_mix":             0.0,
            "midpass_gain":            1.0,
            "bitcrush_bits":           16,
            "bitcrush_downsample":     1,
            "bitcrush_mix":            0.0,
            "eq_low":                  1.0,
            "eq_mid":                  1.0,
            "eq_high":                 1.0,
            "noise_mix":               0.0,
            "reverb_mix":              0.0,
            "glitch_intensity":        0.0,
            "glitch_noise_mix":        0.0,
            "glitch_noise_attack_ms":  180.0,
            "glitch_voice_mix":        0.0,
            "glitch_voice_delay_ms":   140.0,
        }

        for property_name, value in defaults.items():
            self.loom.set_property_base_value(property_name, value)

        self.position            = 0.0
        self.is_playing          = False
        self.duration_ms         = 0.0
        self.track_peak_level    = 1.0
        self.current_audio_level = 0.0
        self.filter_states       = None
        self.eq_low_states       = None
        self.eq_mid_states       = None
        self.eq_high_states      = None

        self.is_glitching            = False
        self.glitch_frames_remaining = 0
        self.glitch_saved_position   = 0.0
        self.glitch_mode             = "random"
        self.glitch_active_mode      = "noise"
        self.glitch_total_frames     = 0
        self.glitch_elapsed_frames   = 0
        self.glitch_noise_color      = "pink"

    def setup_beat_detection(self) -> None:
        self.window_size         = 2048
        self.hop_size            = 512
        self.last_heavy_time     = 0.0
        self.heavy_cooldown      = 0.3
        self.heavy_rms_threshold = 0.2

        self.onset_detector = aubio.onset(
            "mkl",
            self.window_size,
            self.hop_size,
            self.fs
        )

        self.onset_detector.set_threshold(0.345)

        self.beat_queue = queue.Queue(maxsize = 100)

        self.beat_thread = threading.Thread(
            target = self.beat_emitter_worker,
            daemon = True
        )

        self.beat_thread.start()

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

    # Loading

    def load_audio(self, path: str) -> None:
        data, fs = soundfile.read(path, dtype = "float32")
        self.load_audio_from_data(data, fs)

    def load_audio_from_data(
            self,
            data: numpy.ndarray,
            fs:   int
        ) -> None:

        if data.ndim == 1:
            data = numpy.column_stack((data, data))

        data = numpy.ascontiguousarray(data, dtype = numpy.float32)

        with self.lock:
            self.reset_playback_state()

            self.fs          = fs
            self.data        = data
            self.duration_ms = (len(data) / fs) * 1000.0

            channels = data.shape[1]

            self.filter_states  = numpy.zeros((channels, 4), dtype = numpy.float64)
            self.eq_low_states  = numpy.zeros((channels, 4), dtype = numpy.float64)
            self.eq_mid_states  = numpy.zeros((channels, 4), dtype = numpy.float64)
            self.eq_high_states = numpy.zeros((channels, 4), dtype = numpy.float64)

            peak_level            = float(numpy.max(numpy.abs(data)))
            self.track_peak_level = max(peak_level, 1e-6)

        if self.stream is None:
            self.open_stream()

        self.audio_loaded.emit(
            self.data,
            self.fs,
            len(self.data) / self.fs
        )

    def open_stream(self) -> None:
        self.close_stream()

        with self.lock:
            if self.data is None:
                return

            channels = self.data.shape[1]

        self.stream = miniaudio.PlaybackDevice(
            output_format    = miniaudio.SampleFormat.SIGNED16,
            nchannels        = channels,
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
            if self.stream is None:
                return

            self.stream.stop()
            self.stream.close()

        except Exception as error:
            logger.error("Failed to close the stream: {}", error)

        finally:
            self.stream        = None
            self.mix_generator = None

    # Playback

    def get_position(self) -> float:
        if self.is_glitching:
            return (self.glitch_saved_position / self.fs) * 1000.0

        elapsed_ms = (time.time() - self.playback_start_wall_time) * 1000.0
        return self.playback_start_audio_ms + (elapsed_ms * self.speed)

    def update_playback_start(self, speed: float) -> None:
        self.speed_changed.emit(speed)
        self.playback_start_audio_ms  = self.get_position()
        self.playback_start_wall_time = time.time()

    def toggle_playback(self, ms: float | None = None) -> None:
        if self.is_playing:
            self.stop()
            return

        self.play(ms)

    def stop(self) -> None:
        with self.lock:
            self.is_playing = False

        self.playback_state_changed.emit(False)

    def play(self, start_position_ms: float = 0.0) -> None:
        with self.lock:
            if self.data is None:
                return

            self.position   = (start_position_ms * self.fs) / 1000.0
            self.is_playing = True

        self.playback_state_changed.emit(True)
        self.playback_start_audio_ms  = start_position_ms
        self.playback_start_wall_time = time.time()

    # Processing

    def compute_eq_coefficients(self) -> tuple[
            tuple[float, float, float, float, float, float],
            tuple[float, float, float, float, float, float],
            tuple[float, float, float, float, float, float]
        ]:

        return (
            calculate_lowshelf_coefficients(
                250.0,
                self.loom.get_property_value("eq_low"),
                float(self.fs)
            ),

            calculate_peaking_coefficients(
                1000.0,
                self.loom.get_property_value("eq_mid"),
                1.0,
                float(self.fs)
            ),

            calculate_highshelf_coefficients(
                4000.0,
                self.loom.get_property_value("eq_high"),
                float(self.fs)
            )
        )

    def generate_resampled_block(
            self,
            frames:  int,
            context: dict
        ) -> numpy.ndarray:

        return resample_block(
            self.data,
            context["position"],
            context["speed"],
            context["delays"],
            frames
        )

    def apply_eq(
            self,
            block:   numpy.ndarray,
            context: dict
        ) -> numpy.ndarray:

        low  = context["eq_low"]
        mid  = context["eq_mid"]
        high = context["eq_high"]

        if abs(low - 1.0) < 0.01 and abs(mid - 1.0) < 0.01 and abs(high - 1.0) < 0.01:
            return block

        low_coefficients, mid_coefficients, high_coefficients = self.compute_eq_coefficients()

        return apply_eq_triple(
            block,
            low, mid, high,
            low_coefficients[0],  low_coefficients[1],  low_coefficients[2],
            low_coefficients[3],  low_coefficients[4],
            mid_coefficients[0],  mid_coefficients[1],  mid_coefficients[2],
            mid_coefficients[3],  mid_coefficients[4],
            high_coefficients[0], high_coefficients[1], high_coefficients[2],
            high_coefficients[3], high_coefficients[4],
            self.eq_low_states,
            self.eq_mid_states,
            self.eq_high_states
        )

    def apply_reverb_and_noise(
            self,
            block:   numpy.ndarray,
            context: dict
        ) -> numpy.ndarray:

        reverb_mix = context["reverb_mix"]
        noise_mix  = context["noise_mix"]

        if reverb_mix <= 0.0 and noise_mix <= 0.0:
            return block

        result = block

        if reverb_mix > 0.0:
            result = self.apply_reverb(result, context)

        if noise_mix > 0.0:
            result = apply_noise_mix(result, noise_mix)

        return result

    def apply_reverb(
            self,
            block:   numpy.ndarray,
            context: dict
        ) -> numpy.ndarray:

        delay_one   = int(self.fs * 0.04)
        delay_two   = int(self.fs * 0.08)
        zero_delays = numpy.zeros(2, dtype = numpy.float64)

        tap_one = resample_block(
            self.data,
            max(0.0, context["position"] - delay_one),
            context["speed"],
            zero_delays,
            len(block)
        )

        tap_two = resample_block(
            self.data,
            max(0.0, context["position"] - delay_two),
            context["speed"],
            zero_delays,
            len(block)
        )

        return apply_reverb_block(block, tap_one, tap_two, context["reverb_mix"])

    def apply_noise(
            self,
            block:     numpy.ndarray,
            noise_mix: float
        ) -> numpy.ndarray:

        return apply_noise_mix(block, noise_mix)

    def apply_midpass_filter(
            self,
            block:   numpy.ndarray,
            context: dict
        ) -> numpy.ndarray:

        mix = context["filter_mix"]

        if mix <= 0.0:
            return block

        coefficients = calculate_bandpass_coefficients(
            float(context["midpass_center"]),
            float(context["midpass_q"]),
            float(self.fs)
        )

        filtered = apply_biquad_block(
            block,
            coefficients[0] * context["filter_gain"],
            coefficients[1] * context["filter_gain"],
            coefficients[2] * context["filter_gain"],
            coefficients[3],
            coefficients[4],
            self.filter_states
        )

        return mix_audio_blocks(block, filtered, mix)

    def apply_bitcrush(
            self,
            block:   numpy.ndarray,
            context: dict
        ) -> numpy.ndarray:

        return apply_bitcrush_block(
            block,
            float(context["bitcrush_mix"]),
            int(context["bitcrush_bits"]),
            int(context["bitcrush_downsample"])
        )
    
    def generate_noise_block(
            self,
            frames:      int,
            channels:    int,
            noise_color: str
        ) -> numpy.ndarray:

        return generate_colored_noise(frames, channels, noise_color)

    def get_glitch_noise_attack_gain(self) -> float:
        attack_ms = float(self.loom.get_property_value("glitch_noise_attack_ms"))

        if attack_ms <= 0.0:
            return 1.0

        attack_frames = max(1, int((self.fs * attack_ms) / 1000.0))
        
        return max(0.0, min(1.0, self.glitch_elapsed_frames / attack_frames))

    def apply_glitch_noise(
            self,
            block:       numpy.ndarray,
            noise_mix:   float,
            noise_color: str
        ) -> numpy.ndarray:

        if noise_mix <= 0.0:
            return block

        noise = generate_colored_noise(block.shape[0], block.shape[1], noise_color)
        return mix_audio_blocks(block, noise, noise_mix)

    def apply_voice_echo(
            self,
            block:   numpy.ndarray,
            context: dict
        ) -> numpy.ndarray:

        voice_mix = float(self.loom.get_property_value("glitch_voice_mix"))
        
        if voice_mix <= 0.0:
            return block

        delay_ms    = float(self.loom.get_property_value("glitch_voice_delay_ms"))
        delay_frames = int((self.fs * delay_ms) / 1000.0)
        echo_position = max(0.0, context["position"] - delay_frames)

        echo_context = {
            **context,
            "position": echo_position,
            "delays": numpy.zeros(2, dtype = numpy.float64)
        }

        echo_block = self.generate_resampled_block(len(block), echo_context)

        coefficients = calculate_bandpass_coefficients(
            1200.0,
            0.9,
            float(self.fs)
        )

        voice_states = numpy.zeros((block.shape[1], 4), dtype = numpy.float64)

        voice_block = apply_biquad_block(
            echo_block,
            coefficients[0],
            coefficients[1],
            coefficients[2],
            coefficients[3],
            coefficients[4],
            voice_states
        )

        return mix_audio_blocks(block, voice_block, voice_mix * 0.35)

    def generate_glitch_block(
            self,
            frames:  int,
            context: dict
        ) -> numpy.ndarray:

        mode     = self.glitch_active_mode
        channels = self.data.shape[1]

        if mode == "stutter":
            snippet_length   = int(self.fs * 0.05)
            stutter_position = max(0.0, self.glitch_saved_position - snippet_length)

            glitch_context = {
                **context,
                "position": stutter_position,
                "speed":    1.0,
                "delays":   numpy.zeros(2, dtype = numpy.float64)
            }

            block    = self.generate_resampled_block(frames, glitch_context)
            envelope = (numpy.sin(numpy.linspace(0.0, 10.0, frames)) > 0.0).astype(numpy.float32)
            block   *= envelope[:, numpy.newaxis]

            return apply_bitcrush_block(block, 0.8, 4, 4)

        if mode == "random_jump":
            random_position = random.uniform(0.0, max(0.0, len(self.data) - frames - 1))

            glitch_context = {
                **context,
                "position": random_position,
                "speed":    random.uniform(0.5, 1.5),
                "delays":   numpy.zeros(2, dtype = numpy.float64)
            }

            block = self.generate_resampled_block(frames, glitch_context)
            
            return apply_bitcrush_block(block, 0.8, 4, 4)

        base_block = self.generate_resampled_block(frames, context)

        if mode == "noise":
            noise_mix = float(self.loom.get_property_value("glitch_noise_mix"))
            noise_mix *= self.get_glitch_noise_attack_gain()
            
            return self.apply_glitch_noise(base_block, noise_mix, self.glitch_noise_color)

        if mode == "voice_echo":
            noise_mix = float(self.loom.get_property_value("glitch_noise_mix"))
            noise_mix *= self.get_glitch_noise_attack_gain()

            block = self.apply_glitch_noise(base_block, noise_mix, self.glitch_noise_color)
            
            return self.apply_voice_echo(block, context)

        return base_block

    def process_beat_detection(self, block: numpy.ndarray) -> None:
        if self.onset_detector is None:
            return

        mono = numpy.mean(block, axis = 1).astype(numpy.float32)

        for start_index in range(0, len(mono), self.hop_size):
            segment = mono[start_index:start_index + self.hop_size]

            if len(segment) < self.hop_size:
                break

            if not self.onset_detector(segment):
                continue

            rms          = float(numpy.sqrt(numpy.mean(segment ** 2)))
            current_time = time.time()
            is_heavy     = False

            if (current_time - self.last_heavy_time) > self.heavy_cooldown and rms > self.heavy_rms_threshold:
                is_heavy             = True
                self.last_heavy_time = current_time

            try:
                self.beat_queue.put_nowait((is_heavy, rms))

            except queue.Full:
                pass

    def process_audio_chunk(self, frames: int) -> numpy.ndarray:
        context = {
            "position":                self.position,
            "speed":                   self.speed,
            "volume":                  self.volume,
            "fs":                      self.fs,
            "max_index":               len(self.data) - 1,
            "delays":                  numpy.array(
                                           [
                                               self.loom.get_property_value("channel_delay_left"),
                                               self.loom.get_property_value("channel_delay_right")
                                           ],
                                           dtype = numpy.float64
                                       ),
            "midpass_q":               self.loom.get_property_value("midpass_q"),
            "filter_mix":              self.loom.get_property_value("midpass_mix"),
            "filter_gain":             self.loom.get_property_value("midpass_gain"),
            "midpass_center":          self.loom.get_property_value("midpass_center"),
            "bitcrush_mix":            self.loom.get_property_value("bitcrush_mix"),
            "bitcrush_bits":           self.loom.get_property_value("bitcrush_bits"),
            "bitcrush_downsample":     self.loom.get_property_value("bitcrush_downsample"),
            "eq_low":                  self.loom.get_property_value("eq_low"),
            "eq_mid":                  self.loom.get_property_value("eq_mid"),
            "eq_high":                 self.loom.get_property_value("eq_high"),
            "reverb_mix":              self.loom.get_property_value("reverb_mix"),
            "noise_mix":               self.loom.get_property_value("noise_mix"),
            "glitch_intensity":        self.loom.get_property_value("glitch_intensity"),
            "glitch_noise_mix":        self.loom.get_property_value("glitch_noise_mix"),
            "glitch_noise_attack_ms":  self.loom.get_property_value("glitch_noise_attack_ms"),
            "glitch_voice_mix":        self.loom.get_property_value("glitch_voice_mix"),
            "glitch_voice_delay_ms":   self.loom.get_property_value("glitch_voice_delay_ms"),
        }

        self.check_start_glitch(context["glitch_intensity"])

        block = self.generate_audio_block(frames, context)

        self.process_beat_detection(block)

        block = self.apply_eq(block, context)
        block = self.apply_reverb_and_noise(block, context)
        block = self.apply_midpass_filter(block, context)
        block = self.apply_bitcrush(block, context)

        block                    *= context["volume"]
        self.current_audio_level  = float(numpy.max(numpy.abs(block)) / self.track_peak_level)

        if self.data is not None and self.position >= len(self.data) and not self.is_glitching:
            self.stop()

        return block

    def check_start_glitch(self, glitch_intensity: float) -> None:
        if glitch_intensity <= 0.0 or self.is_glitching:
            return

        if random.random() >= 0.005 * glitch_intensity:
            return

        self.is_glitching            = True
        self.glitch_frames_remaining = int(self.fs * random.uniform(0.1, 0.6))
        self.glitch_total_frames     = self.glitch_frames_remaining
        self.glitch_elapsed_frames    = 0
        self.glitch_saved_position    = self.position

        mode = self.glitch_mode
        
        if mode == "random":
            mode = random.choice(["stutter", "random_jump", "noise", "voice_echo"])

        self.glitch_active_mode = mode

    def generate_audio_block(
            self,
            frames:  int,
            context: dict
        ) -> numpy.ndarray:

        if self.is_glitching:
            block = self.generate_glitch_block(frames, context)

            self.glitch_elapsed_frames    += frames
            self.glitch_frames_remaining  -= frames
            self.position                 += frames * context["speed"]

            if self.glitch_frames_remaining <= 0:
                self.is_glitching       = False
                self.glitch_active_mode = "noise"

            return block

        block = self.generate_resampled_block(frames, context)
        self.position += frames * context["speed"]

        return block

    def create_playback_generator(self) -> object:
        frames = yield b""

        while True:
            with self.lock:
                if not self.is_playing or self.data is None:
                    block = self.create_silence_block(frames)
                
                else:
                    block = self.process_audio_chunk(frames)

            block  = numpy.clip(block, -1.0, 1.0)
            pcm    = (block * 32767.0).astype(numpy.int16)
            frames = yield pcm.tobytes()

    def create_silence_block(self, frames: int) -> numpy.ndarray:
        if self.data is None:
            return numpy.zeros((frames, 2), dtype = numpy.float32)

        channels = self.data.shape[1]
        return numpy.zeros((frames, channels), dtype = numpy.float32)

    def get_current_audio_level(self) -> float:
        return self.current_audio_level

    # Effects

    def set_channel_delay(
            self,
            left_to_ms:  float | None = None,
            right_to_ms: float | None = None,
            duration_ms: int          = 0,
            easing:      Easing       = Easing.smooth
        ) -> None:

        if left_to_ms is None and right_to_ms is None:
            return

        if left_to_ms is None:
            left_to_ms = self.loom.get_property_value("channel_delay_left")

        if right_to_ms is None:
            right_to_ms = self.loom.get_property_value("channel_delay_right")

        if duration_ms <= 0:
            self.loom.set_property_base_value("channel_delay_left",  left_to_ms)
            self.loom.set_property_base_value("channel_delay_right", right_to_ms)
            
            return

        self.loom.set_target_value("channel_delay_left",  left_to_ms,  duration_ms, easing)
        self.loom.set_target_value("channel_delay_right", right_to_ms, duration_ms, easing)

    def set_speed(
            self,
            new_speed:          float,
            duration_ms:        int    = 0,
            easing:             Easing = Easing.smooth,
            cleanup_on_finish:  bool   = False,
            shutdown_on_finish: bool   = False
        ) -> None:

        self.update_playback_start(new_speed)
        callback = self.get_speed_callback(cleanup_on_finish, shutdown_on_finish)
        self.set_property("speed", new_speed, duration_ms, easing, callback)

    def get_speed_callback(
            self,
            cleanup:  bool,
            shutdown: bool
        ) -> callable | None:

        if cleanup:
            return self.reset_playback_state

        if shutdown:
            return self.full_shutdown

        return None

    def set_volume(
            self,
            volume:      float,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        volume = max(0.0, min(volume, 1.0))
        self.set_property("volume", volume, duration_ms, easing)

    def set_bitcrush(
            self,
            bits:        int    = 24,
            downsample:  int    = 1,
            mix:         float  = 0.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        if duration_ms <= 0:
            self.loom.set_property_base_value("bitcrush_bits",       bits)
            self.loom.set_property_base_value("bitcrush_downsample", downsample)
            self.loom.set_property_base_value("bitcrush_mix",        mix)
            
            return

        self.loom.set_target_value("bitcrush_bits",       float(bits),       duration_ms, easing)
        self.loom.set_target_value("bitcrush_downsample", float(downsample), duration_ms, easing)
        self.loom.set_target_value("bitcrush_mix",        mix,               duration_ms, easing)

    def set_midpass(
            self,
            q:           float  = 1.0,
            mix:         float  = 1.0,
            gain:        float  = 1.0,
            center_hz:   float  = 1000.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        if duration_ms <= 0:
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
            QTimer.singleShot(duration_ms, lambda: self.filter_states.fill(0.0))

    def set_eq(
            self,
            low:         float  = 1.0,
            mid:         float  = 1.0,
            high:        float  = 1.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        low  = max(0.0, low)
        mid  = max(0.0, mid)
        high = max(0.0, high)

        if duration_ms <= 0:
            self.loom.set_property_base_value("eq_low",  low)
            self.loom.set_property_base_value("eq_mid",  mid)
            self.loom.set_property_base_value("eq_high", high)
            
            return

        self.loom.set_target_value("eq_low",  low,  duration_ms, easing)
        self.loom.set_target_value("eq_mid",  mid,  duration_ms, easing)
        self.loom.set_target_value("eq_high", high, duration_ms, easing)

    def set_noise(
            self,
            mix:         float  = 0.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        mix = max(0.0, min(1.0, mix))
        self.set_property("noise_mix", mix, duration_ms, easing)

    def set_reverb(
            self,
            mix:         float  = 0.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        mix = max(0.0, min(1.0, mix))
        self.set_property("reverb_mix", mix, duration_ms, easing)

    def set_car_radio(
            self,
            active:      bool,
            duration_ms: int    = 1500,
            easing:      Easing = Easing.smooth
        ) -> None:

        if active:
            self.set_car_radio_active(duration_ms, easing)
            return

        self.set_car_radio_inactive(duration_ms, easing)

    def set_car_radio_active(
            self,
            duration_ms: int,
            easing:      Easing
        ) -> None:

        self.set_eq(low = 1.6, mid = 1.0, high = 0.7, duration_ms = duration_ms, easing = easing)
        self.set_reverb(mix = 0.35, duration_ms = duration_ms, easing = easing)
        self.set_noise(mix = 0.04, duration_ms = duration_ms, easing = easing)

    def set_car_radio_inactive(
            self,
            duration_ms: int,
            easing:      Easing
        ) -> None:

        self.set_eq(low = 1.0, mid = 1.0, high = 1.0, duration_ms = duration_ms, easing = easing)
        self.set_reverb(mix = 0.0, duration_ms = duration_ms, easing = easing)
        self.set_noise(mix = 0.0, duration_ms = duration_ms, easing = easing)

    def set_glitch(
            self,
            intensity:   float         = 0.0,
            mode:        str    | None = None,
            duration_ms: int           = 0,
            easing:      Easing        = Easing.smooth
        ) -> None:

        if mode is not None:
            self.set_glitch_mode(mode)

        intensity = max(0.0, intensity)
        self.set_property("glitch_intensity", intensity, duration_ms, easing)
    
    def set_glitch_mode(self, mode: str) -> None:
        if mode not in {"random", "stutter", "random_jump", "noise", "voice_echo"}:
            mode = "random"
        
        self.glitch_mode = mode
    
    def set_glitch_noise(
            self,
            mix:         float  = 0.0,
            color:       str    = "pink",
            attack_ms:   float  = 180.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        self.glitch_noise_color = color if color in {"white", "pink", "brown"} else "pink"

        self.set_property("glitch_noise_mix",       max(0.0, min(1.0, mix)), duration_ms, easing)
        self.set_property("glitch_noise_attack_ms", max(0.0, attack_ms),     duration_ms, easing)

    def set_glitch_voice_echo(
            self,
            mix:         float  = 0.06,
            delay_ms:    float  = 140.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:
    
        self.set_property("glitch_voice_mix",      max(0.0, min(1.0, mix)), duration_ms, easing)
        self.set_property("glitch_voice_delay_ms", max(0.0, delay_ms),      duration_ms, easing)

    # Shutdown

    def full_shutdown(self) -> None:
        self.reset_playback_state()
        self.loom.clear()

        with self.lock:
            self.close_stream()

            if self.beat_queue is None:
                return

            try:
                self.beat_queue.put_nowait(None)

            except queue.Full:
                pass

class UISound:
    def __init__(self, sound_id: int, manager: UISoundManager) -> None:
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
        self.mix_generator = None

    def ensure_device(self) -> None:
        if self.device is not None:
            return

        self.device = miniaudio.PlaybackDevice(
            output_format    = miniaudio.SampleFormat.SIGNED16,
            nchannels        = self.channels,
            sample_rate      = self.sample_rate,
            buffersize_msec  = 30,
            callback_periods = 4,
            thread_prio      = miniaudio.ThreadPriority.HIGHEST
        )

        self.mix_generator = self.create_mix_generator()
        next(self.mix_generator)
        self.device.start(self.mix_generator)

    def preload(self, path: str, name: str) -> None:
        if name in self.preloaded:
            return

        data, fs = soundfile.read(path, dtype="float32")

        if data.ndim == 1:
            data = numpy.column_stack((data, data))

        data = numpy.ascontiguousarray(data, dtype=numpy.float32)

        if fs != self.sample_rate:
            data = self.resample_data(data, fs, name)

        self.preloaded[name] = data
        logger.success(f"{name} loaded")

    def resample_data(
            self,
            data: numpy.ndarray,
            fs:   int,
            name: str
        ) -> numpy.ndarray:
        
        ratio        = self.sample_rate / fs
        num_samples  = max(1, int(len(data) * ratio + 0.5))
        source_index = numpy.linspace(0, len(data) - 1, num_samples, endpoint=False)
        resampled    = numpy.empty((num_samples, self.channels), dtype=numpy.float32)

        for channel_index in range(self.channels):
            resampled[:, channel_index] = numpy.interp(
                source_index,
                numpy.arange(len(data)),
                data[:, channel_index]
            )
        
        return numpy.ascontiguousarray(resampled, dtype=numpy.float32)

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

        with self.lock:
            sound_id = self.next_sound_id
            self.next_sound_id += 1

            if speed == 1.0 and enable_tone_randomizer:
                speed = random.uniform(1.0 - tone_spread, 1.0 + tone_spread)

            self.cleanup_old_sounds()
            
            self.active_sounds[sound_id] = {
                "data":     self.preloaded[name],
                "position": 0.0,
                "speed":    float(speed),
                "volume":   float(volume),
                "loop":     loop,
            }

        return UISound(sound_id, self)

    def cleanup_old_sounds(self) -> None:
        while len(self.active_sounds) >= 16:
            oldest = next(iter(self.active_sounds))
            del self.active_sounds[oldest]

    def stop_sound(self, sound_id: int) -> None:
        with self.lock:
            self.active_sounds.pop(sound_id, None)

    def set_speed(self, sound_id: int, speed: float) -> None:
        with self.lock:
            if sound_id in self.active_sounds:
                self.active_sounds[sound_id]["speed"] = float(speed)

    def set_volume(self, sound_id: int, new_volume: float) -> None:
        with self.lock:
            if sound_id in self.active_sounds:
                self.active_sounds[sound_id]["volume"] = float(new_volume)

    def stop_all(self) -> None:
        with self.lock:
            self.active_sounds.clear()

    def cleanup(self) -> None:
        if self.device is None:
            return
        
        self.device.stop()
        self.device.close()

        self.device        = None
        self.mix_generator = None
    
    def create_mix_generator(self):
        frames = yield b""

        while True:
            with self.lock:
                snapshots = [
                    (
                        s_id,
                        snd["data"],
                        snd["position"],
                        snd["speed"],
                        snd["volume"],
                        snd["loop"]
                    )
                    for s_id, snd in self.active_sounds.items()
                ]

            master_block = numpy.zeros((frames, self.channels), dtype = numpy.float32)
            updates      = []
            to_remove    = []

            for s_id, data, pos, spd, vol, loop in snapshots:
                if spd == 1.0:
                    sound_block, new_pos, is_active = process_ui_sound_fast(
                        data,
                        float(pos),
                        float(vol),
                        frames,
                        loop
                    )
                
                else:
                    sound_block, new_pos, is_active = process_ui_sound_interp(
                        data,
                        float(pos),
                        float(spd),
                        float(vol),
                        frames,
                        loop
                    )
                
                master_block += sound_block
                
                if is_active:
                    updates.append((s_id, new_pos))
                
                else:
                    to_remove.append(s_id)

            with self.lock:
                for s_id, new_pos in updates:
                    if s_id in self.active_sounds:
                        self.active_sounds[s_id]["position"] = new_pos
                
                for s_id in to_remove:
                    self.active_sounds.pop(s_id, None)

            numpy.clip(master_block, -1.0, 1.0, out = master_block)
            pcm    = (master_block * 32767.0).astype(numpy.int16)
            frames = yield pcm.tobytes()

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
            "int":          int,
            "math":         math,
            "sin":          math.sin,
            "cos":          math.cos,
            "tan":          math.tan,
            "asin":         math.asin,
            "acos":         math.acos,
            "atan":         math.atan,
            "atan2":        math.atan2,
            "sqrt":         math.sqrt,
            "exp":          math.exp,
            "log":          math.log,
            "log10":        math.log10,
            "ceil":         math.ceil,
            "floor":        math.floor,
            "PI":           math.pi,
            "E":            math.e,
            "random":       numpy.random.random,
            "parseInt":     lambda value, radix = 10: int(str(value), radix),
            "js_shr":       shift_right_unsigned,
            "__builtins__": None
        }

    # Setup

    def preprocess_formula(self, formula: str) -> str:
        result = formula
        result = result.replace("&&", " and ")
        result = result.replace("||", " or ")
        result = re.sub(r"(\S+)\s*>>>\s*(\S+)", r"js_shr(\1, \2)", result)
        result = result.replace("floor", "int")

        return result

    def set_formula(self, formula_string: str) -> None:
        try:
            processed_formula = self.preprocess_formula(formula_string)
            compiled_formula  = compile(processed_formula, "<string>", "eval")

        except Exception:
            logger.error("Formula incorrect: {}", formula_string)
            return

        with self.lock:
            self.formula_bytecode = compiled_formula
            self.time_index       = 0

    def ensure_device(self) -> None:
        if self.device is not None:
            return

        self.device = miniaudio.PlaybackDevice(
            output_format = miniaudio.SampleFormat.SIGNED16,
            nchannels     = self.channels,
            sample_rate   = self.sample_rate
        )

        self.generator = self.create_generator()
        next(self.generator)
        self.device.start(self.generator)

    # Playback

    def play(self) -> None:
        self.ensure_device()

    # Processing

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
            for frame_index in range(number_of_frames):
                scaled_time                    = int(self.time_index * self.time_scale)
                output_buffer[frame_index]     = self.calculate_single_sample(scaled_time)
                self.time_index               += 1

            self.update_intensity(output_buffer, number_of_frames)

        return output_buffer.tobytes()

    def update_intensity(
            self,
            output_buffer: numpy.ndarray,
            count:         int
        ) -> None:

        if count <= 0:
            return

        normalized             = output_buffer.astype(numpy.float32) / 32768.0
        rms                    = float(numpy.sqrt(numpy.mean(normalized ** 2)))
        self.current_intensity = rms * 2.0

    def create_generator(self) -> object:
        number_of_frames = yield b""

        while True:
            if self.formula_bytecode is None:
                number_of_frames = yield self.generate_silence_block(number_of_frames)
                continue

            number_of_frames = yield self.process_audio_block(number_of_frames)

    # State

    def get_current_intensity(self) -> float:
        return self.current_intensity

    # Shutdown

    def cleanup(self) -> None:
        if self.device is not None:
            self.device.stop()
            self.device.close()

        self.device                         = None
        self.formula_bytecode               = None
        self.time_index                     = 0
        self.execution_context["t"]         = 0

player    = PlaybackManager()
ui_player = UISoundManager()

prefix    = "System/Assets/Sounds"
base_path = Utils.get_resource_path(prefix)
base      = Path(base_path)

sounds = []

for path in base.rglob("*.wav"):
    relative_path = path.relative_to(base).as_posix()
    name          = relative_path[:-4]
    full_path     = Utils.get_resource_path(f"{prefix}/{relative_path}")
    sounds.append((full_path, name))

for path, name in sounds:
    ui_player.preload(path, name)