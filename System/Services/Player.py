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
    pyqtSignal,
    QElapsedTimer
)

from System.Common import (
    Utils,
    Constants
)

from System.Interface.Animation.LoomEngine import (
    Easing,
    ui_engine
)

from System.Accelerated import PlayerFunctions

Utils.check_dynamic_library(PlayerFunctions)

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
        self.sample_rate              = 44100
        self.position                 = 0.0
        self.duration_ms              = 0.0
        self.is_playing               = False
        self.track_peak_level         = 1.0
        self.current_audio_level      = 0.0
        self.current_beat_impact      = 0.0
        self.playback_start_audio_ms  = 0.0
        self.playback_start_wall_time = 0.0

        self.eq_low_states  = None
        self.eq_mid_states  = None
        self.eq_high_states = None
        self.pass_states    = None
        self.echo_states    = None

        self.pass_frequencies = []
        self.pass_q           = 1.0
        self.pass_mix         = 0.0
        self.pass_gain        = 1.0

        self.radio_noise_active    = False
        self.radio_noise_color     = "brown"
        self.radio_noise_permanent = False

        self.echo_mode  = "constant"
        self.echo_focus = "all"

        self.stream_sample_rate  = 0
        self.stream_block_size   = 0
        self.stream_channels     = 0
        self.stream_needs_reopen = False
        self.block_size_ms       = 15

        self.onset_buffer        = numpy.empty(0, dtype = numpy.float32)
        self.level_decay_ms      = 120.0
        self.impact_decay_ms     = 180.0

        self.setup_effect_properties()
        self.reset_playback_state()
        self.setup_beat_detection()

    # Properties

    @property
    def speed(self) -> float:
        return self.speed_property.value

    @property
    def volume(self) -> float:
        return self.volume_property.value

    # Setup

    def setup_effect_properties(self) -> None:
        self.defaults = [
            ("speed",                  1.0,   self.update_playback_start),
            ("volume",                 1.0),
            ("channel_delay_left",     0.0),
            ("channel_delay_right",    0.0),
            ("eq_low",                 1.0),
            ("eq_mid",                 1.0),
            ("eq_high",                1.0),
            ("bitcrush_bits",          16.0),
            ("bitcrush_downsample",    1.0),
            ("bitcrush_mix",           0.0),
            ("noise_mix",              0.0),
            ("reverb_mix",             0.0),
            ("pass_mix",               0.0),
            ("pass_q",                 1.0),
            ("pass_gain",              1.0),
            ("radio_noise_intensity",  0.0),
            ("radio_noise_mix",        0.0),
            ("radio_noise_attack_ms",  100.0),
            ("radio_noise_peak_ms",    180.0),
            ("radio_noise_release_ms", 250.0),
            ("radio_noise_mute_mix",   0.45),
            ("echo_mix",               0.0),
            ("echo_delay_ms",          180.0),
            ("echo_feedback",          0.25)
        ]

        for item in self.defaults:
            name            = item[0]
            base_value      = item[1]
            callback        = item[2] if len(item) > 2 else None
            property_handle = ui_engine.bind(self, name, base_value, on_change = callback)

            setattr(self, f"{name}_property", property_handle)

    def set_property(
            self,
            property_name:     str,
            value:             float,
            duration_ms:       int    = 0,
            easing:            Easing = Easing.smooth,
            on_finish:         object = None,
            multiply_duration: bool   = True
        ) -> None:

        property_handle = getattr(self, f"{property_name}_property")

        if duration_ms <= 0:
            property_handle.set_base(value)

            if on_finish:
                on_finish()

            return

        property_handle.set_target(
            value,
            duration_ms,
            easing,
            multiply_duration
        )

        if on_finish:
            QTimer.singleShot(duration_ms, on_finish)

    def apply_properties(
            self,
            properties:  dict[str, float],
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        for name, value in properties.items():
            self.set_property(name, value, duration_ms, easing)

    def reset_playback_state(self) -> None:
        for item in self.defaults:
            name       = item[0]
            base_value = item[1]

            getattr(self, f"{name}_property").set_base(base_value)

        self.pass_frequencies = []
        self.position         = 0.0
        self.echo_mode        = "constant"
        self.echo_focus       = "all"
        self.is_playing       = False
        self.duration_ms      = 0.0

        self.track_peak_level    = 1.0
        self.current_audio_level = 0.0
        self.current_beat_impact = 0.0
        self.level_decay_ms      = 120.0
        self.impact_decay_ms     = 180.0
        self.onset_buffer        = numpy.empty(0, dtype = numpy.float32)

        self.eq_low_states  = None
        self.eq_mid_states  = None
        self.eq_high_states = None
        self.pass_states    = None
        self.echo_states    = None

        self.radio_noise_active             = False
        self.radio_noise_frames_remaining   = 0
        self.radio_noise_total_frames       = 0
        self.radio_noise_elapsed_frames     = 0
        self.radio_noise_color              = "brown"
        self.radio_noise_randomize_duration = True
        self.radio_noise_permanent          = False
        self.radio_noise_min_duration_ms    = 160.0
        self.radio_noise_max_duration_ms    = 900.0

        self.echo_random_delay_spread_ms = 70.0
        self.echo_random_feedback_spread = 0.08
        self.echo_random_mix_spread      = 0.05

    def setup_beat_detection(self) -> None:
        self.window_size         = 2048
        self.hop_size            = 512
        self.last_heavy_time     = 0.0
        self.heavy_cooldown      = 0.3
        self.heavy_rms_threshold = 0.2

        self.rebuild_onset_detector()

        self.beat_queue = queue.Queue(maxsize = 100)

        self.beat_thread = threading.Thread(
            target = self.beat_emitter_worker,
            daemon = True
        )

        self.beat_thread.start()

    def rebuild_onset_detector(self) -> None:
        self.onset_detector = aubio.onset(
            "mkl",
            self.window_size,
            self.hop_size,
            self.sample_rate
        )

        self.onset_detector.set_threshold(0.345)

    # BeatDetection

    def set_analysis_window_size(self, window_size: int) -> None:
        if window_size == self.window_size:
            return

        self.window_size = window_size
        self.hop_size    = max(1, window_size // 4)

        self.rebuild_onset_detector()

    def beat_emitter_worker(self) -> None:
        while True:
            item = self.beat_queue.get()

            if item is None:
                break

            is_heavy, raw_root_mean_square = item

            if is_heavy:
                self.beat_heavy.emit(raw_root_mean_square)

            self.beat_normal.emit(raw_root_mean_square)

    # Loading

    def load_audio(self, path: str) -> None:
        data, sample_rate = soundfile.read(path, dtype = "float32")
        self.load_audio_from_data(data, sample_rate)

    def load_audio_from_data(
            self,
            data:        numpy.ndarray,
            sample_rate: int
        ) -> None:

        if data.ndim == 1:
            data = numpy.column_stack((data, data))

        data     = numpy.ascontiguousarray(data, dtype = numpy.float32)
        channels = data.shape[1]

        with self.lock:
            self.reset_playback_state()

            self.sample_rate = sample_rate
            self.data        = data
            self.duration_ms = (len(data) / sample_rate) * 1000.0

            self.eq_low_states  = numpy.zeros((channels, 4), dtype = numpy.float64)
            self.eq_mid_states  = numpy.zeros((channels, 4), dtype = numpy.float64)
            self.eq_high_states = numpy.zeros((channels, 4), dtype = numpy.float64)
            self.echo_states    = numpy.zeros((channels, 4), dtype = numpy.float64)
            self.pass_states    = numpy.zeros((len(self.pass_frequencies), channels, 4), dtype = numpy.float64)

            peak_level            = float(numpy.max(numpy.abs(data)))
            self.track_peak_level = max(peak_level, 1e-6)

        self.stream_needs_reopen = (
            self.stream is None                         or
            self.stream_sample_rate != self.sample_rate or
            self.stream_channels != channels            or
            self.stream_block_size != self.block_size_ms
        )

        self.audio_loaded.emit(
            self.data,
            self.sample_rate,
            len(self.data) / self.sample_rate
        )

        self.ensure_stream_opened()

    def open_stream(self) -> None:
        self.close_stream()

        with self.lock:
            if self.data is None:
                return

            channels = self.data.shape[1]

        self.stream = miniaudio.PlaybackDevice(
            output_format    = miniaudio.SampleFormat.SIGNED16,
            nchannels        = channels,
            sample_rate      = self.sample_rate,
            buffersize_msec  = self.block_size_ms,
            callback_periods = 4,
            thread_prio      = miniaudio.ThreadPriority.HIGHEST
        )

        self.stream_sample_rate = self.sample_rate
        self.stream_channels    = channels
        self.stream_block_size  = self.block_size_ms
        self.mix_generator      = self.create_playback_generator()

        next(self.mix_generator)
        self.stream.start(self.mix_generator)

        self.stream_needs_reopen = False

        logger.success(f"Stream opened. {channels} channels | {self.sample_rate} sampling rate | {self.block_size_ms} ms")

    def close_stream(self) -> None:
        try:
            if self.stream is None:
                return

            self.stream.stop()
            self.stream.close()

        except Exception as error:
            logger.error("Failed to close the stream: {}", error)

        finally:
            self.stream            = None
            self.mix_generator     = None
            self.stream_block_size = 0

    # Playback

    def get_position(self) -> float:
        if not self.is_playing:
            return self.playback_start_audio_ms

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

        target_ms = self.get_position() if ms is None else ms

        if self.duration_ms > 0 and target_ms >= (self.duration_ms - 50.0):
            target_ms = 0.0

        self.play(target_ms)

    def stop(self) -> None:
        with self.lock:
            if not self.is_playing:
                return

            if self.data is not None and self.position >= len(self.data):
                self.playback_start_audio_ms = self.duration_ms

            else:
                self.playback_start_audio_ms = self.get_position()

            self.playback_start_wall_time = time.time()
            self.is_playing               = False

        self.playback_state_changed.emit(False)

    def set_block_size(self, block_size_ms: int) -> None:
        if block_size_ms == self.block_size_ms:
            return

        self.block_size_ms       = block_size_ms
        self.stream_needs_reopen = True

        if self.is_playing:
            self.ensure_stream_opened()

    def blocksize_to_ms(self, blocksize: int) -> int:
        if not self.sample_rate:
            return 0

        return int(round((blocksize / self.sample_rate) * 1000.0))

    def ensure_stream_opened(self) -> None:
        target_block_size_frames = Constants.current_settings.get("audio_blocksize", 128)
        target_block_size_ms     = self.blocksize_to_ms(target_block_size_frames)

        if target_block_size_ms != self.block_size_ms:
            self.block_size_ms       = target_block_size_ms
            self.stream_needs_reopen = True

        if not self.stream_needs_reopen:
            return

        if self.data is None:
            return

        self.open_stream()

    def play(self, start_position_ms: float = 0.0) -> None:
        self.ensure_stream_opened()

        with self.lock:
            if self.data is None:
                return

            target_position_ms = 0.0 if start_position_ms is None else float(start_position_ms)
            self.position      = (target_position_ms * self.sample_rate) / 1000.0
            self.is_playing    = True

        self.playback_state_changed.emit(True)
        self.playback_start_audio_ms  = target_position_ms
        self.playback_start_wall_time = time.time()

    # Processing

    def compute_eq_coefficients(self) -> tuple[
            tuple[float, float, float, float, float, float],
            tuple[float, float, float, float, float, float],
            tuple[float, float, float, float, float, float]
        ]:

        return (
            PlayerFunctions.calculate_lowshelf_coefficients(
                250.0,
                self.eq_low_property.value,
                float(self.sample_rate)
            ),

            PlayerFunctions.calculate_peaking_coefficients(
                1000.0,
                self.eq_mid_property.value,
                1.0,
                float(self.sample_rate)
            ),

            PlayerFunctions.calculate_highshelf_coefficients(
                4000.0,
                self.eq_high_property.value,
                float(self.sample_rate)
            )
        )

    def ensure_pass_states(self, channels: int) -> None:
        band_count = len(self.pass_frequencies)

        if band_count <= 0:
            self.pass_states = numpy.zeros((0, channels, 4), dtype = numpy.float64)
            return

        if self.pass_states is not None and self.pass_states.shape == (band_count, channels, 4):
            return

        self.pass_states = numpy.zeros((band_count, channels, 4), dtype = numpy.float64)

    def ensure_echo_states(self, channels: int) -> None:
        if self.echo_states is not None and self.echo_states.shape == (channels, 4):
            return

        self.echo_states = numpy.zeros((channels, 4), dtype = numpy.float64)

    def generate_resampled_block(
            self,
            frames:  int,
            context: dict[str, object]
        ) -> numpy.ndarray:

        return PlayerFunctions.resample_block(
            self.data,
            numpy.float64(context["position"]),
            numpy.float64(context["speed"]),
            numpy.asarray(context["delays"], dtype = numpy.float64),
            frames
        )

    def apply_eq(
            self,
            block:   numpy.ndarray,
            context: dict[str, object]
        ) -> numpy.ndarray:

        low        = context["eq_low"]
        mid        = context["eq_mid"]
        high       = context["eq_high"]
        is_neutral = abs(low - 1.0) < 0.01 and abs(mid - 1.0) < 0.01 and abs(high - 1.0) < 0.01

        if is_neutral:
            return block

        low_coefficients, mid_coefficients, high_coefficients = self.compute_eq_coefficients()

        return PlayerFunctions.apply_eq_triple(
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
            context: dict[str, object]
        ) -> numpy.ndarray:

        reverb_mix = context["reverb_mix"]
        noise_mix  = context["noise_mix"]

        if reverb_mix <= 0.0 and noise_mix <= 0.0:
            return block

        result = block

        if reverb_mix > 0.0:
            result = self.apply_reverb(result, context)

        if noise_mix > 0.0:
            result = PlayerFunctions.apply_noise_mix(result, noise_mix)

        return result

    def apply_reverb(
            self,
            block:   numpy.ndarray,
            context: dict[str, object]
        ) -> numpy.ndarray:

        delay_one   = int(self.sample_rate * 0.04)
        delay_two   = int(self.sample_rate * 0.08)
        zero_delays = numpy.zeros(2, dtype = numpy.float64)

        tap_one = PlayerFunctions.resample_block(
            self.data,
            numpy.float64(max(0.0, context["position"] - delay_one)),
            numpy.float64(context["speed"]),
            zero_delays,
            len(block)
        )

        tap_two = PlayerFunctions.resample_block(
            self.data,
            numpy.float64(max(0.0, context["position"] - delay_two)),
            numpy.float64(context["speed"]),
            zero_delays,
            len(block)
        )

        return PlayerFunctions.apply_reverb_block(block, tap_one, tap_two, context["reverb_mix"])

    def apply_passes(
            self,
            block:   numpy.ndarray,
            context: dict[str, object]
        ) -> numpy.ndarray:

        pass_mix = context["pass_mix"]

        if pass_mix <= 0.0 or len(self.pass_frequencies) <= 0:
            return block

        self.ensure_pass_states(block.shape[1])

        if self.pass_states is None or self.pass_states.shape[0] <= 0:
            return block

        pass_q       = max(0.1, float(context["pass_q"]))
        coefficients = numpy.array(
            [
                PlayerFunctions.calculate_bandpass_coefficients(float(frequency), pass_q, float(self.sample_rate))
                for frequency in self.pass_frequencies
            ],
            dtype = numpy.float64
        )

        filtered = PlayerFunctions.apply_bandpass_stack(block, coefficients, self.pass_states)
        filtered = filtered * float(context["pass_gain"])
        filtered = numpy.clip(filtered, -1.0, 1.0)

        return PlayerFunctions.mix_audio_blocks(block, filtered, pass_mix)

    def apply_bitcrush(
            self,
            block:   numpy.ndarray,
            context: dict[str, object]
        ) -> numpy.ndarray:

        return PlayerFunctions.apply_bitcrush_block(
            block,
            float(context["bitcrush_mix"]),
            int(context["bitcrush_bits"]),
            int(context["bitcrush_downsample"])
        )

    def compute_echo_focus_coefficients(self) -> tuple[float, float, float, float, float] | None:
        if self.echo_focus == "voice":
            return PlayerFunctions.calculate_bandpass_coefficients(1250.0, 0.9, float(self.sample_rate))

        elif self.echo_focus == "bass":
            return PlayerFunctions.calculate_bandpass_coefficients(140.0, 0.75, float(self.sample_rate))

        return None

    def apply_echo(
            self,
            block:   numpy.ndarray,
            context: dict[str, object]
        ) -> numpy.ndarray:

        echo_mix = context["echo_mix"]

        if echo_mix <= 0.0:
            return block

        delay_ms = float(context["echo_delay_ms"])
        feedback = float(context["echo_feedback"])
        mix      = float(echo_mix)

        if self.echo_mode == "random":
            delay_ms += random.uniform(-self.echo_random_delay_spread_ms, self.echo_random_delay_spread_ms)
            feedback += random.uniform(-self.echo_random_feedback_spread, self.echo_random_feedback_spread)
            mix      += random.uniform(-self.echo_random_mix_spread, self.echo_random_mix_spread)

        delay_ms = max(1.0, delay_ms)
        feedback = max(0.0, min(0.98, feedback))
        mix      = max(0.0, min(1.0, mix))

        delay_frames  = max(1, int((self.sample_rate * delay_ms) / 1000.0))
        echo_position = max(0.0, context["position"] - delay_frames)

        echo_context = {
            **context,
            "position": echo_position,
            "delays":   numpy.zeros(2, dtype = numpy.float64)
        }

        echo_block   = self.generate_resampled_block(len(block), echo_context)
        coefficients = self.compute_echo_focus_coefficients()

        if coefficients is not None:
            self.ensure_echo_states(block.shape[1])

            echo_block = PlayerFunctions.apply_biquad_block(
                echo_block,
                coefficients[0],
                coefficients[1],
                coefficients[2],
                coefficients[3],
                coefficients[4],
                self.echo_states
            )

        echo_block *= (0.35 + (feedback * 0.65))

        return PlayerFunctions.mix_audio_blocks(block, echo_block, mix)

    def apply_radio_noise_effect(
            self,
            block:   numpy.ndarray,
            context: dict[str, object]
        ) -> numpy.ndarray:

        if not self.radio_noise_active:
            return block

        noise_mix = float(context["radio_noise_mix"])

        if noise_mix <= 0.0:
            self.radio_noise_active           = False
            self.radio_noise_frames_remaining = 0
            return block

        if not self.radio_noise_permanent and self.radio_noise_frames_remaining <= 0:
            self.radio_noise_active = False
            return block

        if self.radio_noise_permanent:
            envelope = numpy.ones(len(block), dtype = numpy.float32)

        else:
            attack_frames  = int((self.sample_rate * float(context["radio_noise_attack_ms"])) / 1000.0)
            peak_frames    = int((self.sample_rate * float(context["radio_noise_peak_ms"])) / 1000.0)
            release_frames = int((self.sample_rate * float(context["radio_noise_release_ms"])) / 1000.0)

            envelope = PlayerFunctions.generate_three_stage_envelope(
                len(block),
                self.radio_noise_total_frames,
                self.radio_noise_elapsed_frames,
                attack_frames,
                peak_frames,
                release_frames
            )

        result = PlayerFunctions.apply_radio_noise_block(
            block,
            noise_mix,
            self.radio_noise_color,
            envelope,
            float(context["radio_noise_mute"])
        )

        if self.radio_noise_permanent:
            return result

        self.radio_noise_elapsed_frames   += len(block)
        self.radio_noise_frames_remaining -= len(block)

        if self.radio_noise_frames_remaining <= 0:
            self.radio_noise_active = False

        return result

    def generate_radio_noise_duration_frames(self) -> int:
        min_ms              = max(0.0, float(self.radio_noise_min_duration_ms))
        max_ms              = max(min_ms, float(self.radio_noise_max_duration_ms))
        duration_ms         = random.uniform(min_ms, max_ms) if self.radio_noise_randomize_duration else max_ms
        minimum_envelope_ms = (
            float(self.radio_noise_attack_ms_property.value)  +
            float(self.radio_noise_peak_ms_property.value)    +
            float(self.radio_noise_release_ms_property.value)
        )

        duration_ms = max(duration_ms, minimum_envelope_ms)

        return max(1, int((self.sample_rate * duration_ms) / 1000.0))

    def process_beat_detection(self, block: numpy.ndarray) -> None:
        if self.onset_detector is None:
            return

        mono_channel = numpy.mean(block, axis = 1).astype(numpy.float32)

        if len(self.onset_buffer) > 0:
            self.onset_buffer = numpy.concatenate((self.onset_buffer, mono_channel))

        else:
            self.onset_buffer = mono_channel

        while len(self.onset_buffer) >= self.hop_size:
            audio_segment     = self.onset_buffer[:self.hop_size]
            self.onset_buffer = self.onset_buffer[self.hop_size:]

            if not self.onset_detector(audio_segment):
                continue

            raw_root_mean_square        = float(numpy.sqrt(numpy.mean(audio_segment ** 2)))
            normalized_root_mean_square = raw_root_mean_square / self.track_peak_level
            current_time                = time.time()
            is_heavy                    = (current_time - self.last_heavy_time) > self.heavy_cooldown and normalized_root_mean_square > self.heavy_rms_threshold

            if is_heavy:
                self.last_heavy_time = current_time

            self.current_beat_impact = max(self.current_beat_impact, normalized_root_mean_square)

            try:
                self.beat_queue.put_nowait((is_heavy, normalized_root_mean_square))

            except queue.Full:
                pass

    def build_processing_context(self) -> dict[str, object]:
        return {
            "position":               self.position,
            "speed":                  self.speed,
            "volume":                 self.volume,
            "sample_rate":            self.sample_rate,
            "max_index":              len(self.data) - 1,
            "delays":                 numpy.array(
                                          [
                                              self.channel_delay_left_property.value,
                                              self.channel_delay_right_property.value
                                          ],
                                          dtype = numpy.float32
                                      ),
            "eq_low":                 self.eq_low_property.value,
            "eq_mid":                 self.eq_mid_property.value,
            "eq_high":                self.eq_high_property.value,
            "bitcrush_mix":           self.bitcrush_mix_property.value,
            "bitcrush_bits":          self.bitcrush_bits_property.value,
            "bitcrush_downsample":    self.bitcrush_downsample_property.value,
            "reverb_mix":             self.reverb_mix_property.value,
            "noise_mix":              self.noise_mix_property.value,
            "pass_mix":               self.pass_mix_property.value,
            "pass_q":                 self.pass_q_property.value,
            "pass_gain":              self.pass_gain_property.value,
            "radio_noise_intensity":  self.radio_noise_intensity_property.value,
            "radio_noise_mix":        self.radio_noise_mix_property.value,
            "radio_noise_attack_ms":  self.radio_noise_attack_ms_property.value,
            "radio_noise_peak_ms":    self.radio_noise_peak_ms_property.value,
            "radio_noise_release_ms": self.radio_noise_release_ms_property.value,
            "radio_noise_mute":       self.radio_noise_mute_mix_property.value,
            "echo_mix":               self.echo_mix_property.value,
            "echo_delay_ms":          self.echo_delay_ms_property.value,
            "echo_feedback":          self.echo_feedback_property.value
        }

    def process_audio_chunk(self, frames: int) -> numpy.ndarray:
        context = self.build_processing_context()

        self.check_start_radio_noise(context["radio_noise_intensity"])

        block = self.generate_audio_block(frames, context)

        self.process_beat_detection(block)

        block = self.apply_eq(block, context)
        block = self.apply_reverb_and_noise(block, context)
        block = self.apply_passes(block, context)
        block = self.apply_echo(block, context)
        block = self.apply_bitcrush(block, context)
        block = self.apply_radio_noise_effect(block, context)

        block *= context["volume"]

        chunk_duration_ms        = (frames / self.sample_rate) * 1000.0
        impact_decay_factor      = math.exp(-chunk_duration_ms / self.impact_decay_ms)
        self.current_beat_impact = self.current_beat_impact * impact_decay_factor

        raw_peak = float(numpy.max(numpy.abs(block)) / self.track_peak_level)

        if raw_peak >= self.current_audio_level:
            self.current_audio_level = raw_peak

        else:
            level_decay_factor       = math.exp(-chunk_duration_ms / self.level_decay_ms)
            self.current_audio_level = self.current_audio_level * level_decay_factor

        if self.position >= len(self.data):
            self.position = float(len(self.data))
            self.stop()

        return block

    def check_start_radio_noise(self, intensity: float) -> None:
        if self.radio_noise_mix_property.value <= 0.0:
            self.radio_noise_active           = False
            self.radio_noise_frames_remaining = 0
            return

        if self.radio_noise_permanent:
            if self.radio_noise_active:
                return

            self.radio_noise_active           = True
            self.radio_noise_frames_remaining = 1
            self.radio_noise_total_frames     = 1
            self.radio_noise_elapsed_frames   = 0
            return

        if intensity <= 0.0 or self.radio_noise_active:
            return

        if random.random() >= 0.005 * intensity:
            return

        self.radio_noise_active           = True
        self.radio_noise_frames_remaining = self.generate_radio_noise_duration_frames()
        self.radio_noise_total_frames     = self.radio_noise_frames_remaining
        self.radio_noise_elapsed_frames   = 0

    def generate_audio_block(
            self,
            frames:  int,
            context: dict[str, object]
        ) -> numpy.ndarray:

        block = PlayerFunctions.resample_block(
            self.data,
            numpy.float64(context["position"]),
            numpy.float64(context["speed"]),
            numpy.asarray(context["delays"], dtype = numpy.float64),
            frames
        )

        self.position += frames * context["speed"]

        return block

    def create_playback_generator(self) -> object:
        frames = yield b""

        while True:
            with self.lock:
                if self.is_playing and self.data is not None:
                    block = self.process_audio_chunk(frames)

                else:
                    block = self.create_silence_block(frames)

            block = numpy.clip(block, -1.0, 1.0)
            block = numpy.nan_to_num(block, nan = 0.0, posinf = 1.0, neginf = -1.0)
            pcm   = (block * 32767.0).astype(numpy.int16)

            frames = yield pcm.tobytes()

    def create_silence_block(self, frames: int) -> numpy.ndarray:
        if self.data is None:
            return numpy.zeros((frames, 2), dtype = numpy.float32)

        channels = self.data.shape[1]
        return numpy.zeros((frames, channels), dtype = numpy.float32)

    def get_current_audio_level(self) -> float:
        return self.current_audio_level

    def get_current_beat_impact(self) -> float:
        return self.current_beat_impact

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

        target_left_ms  = self.channel_delay_left_property.value if left_to_ms is None else left_to_ms
        target_right_ms = self.channel_delay_right_property.value if right_to_ms is None else right_to_ms

        if duration_ms <= 0:
            self.channel_delay_left_property.set_base(target_left_ms)
            self.channel_delay_right_property.set_base(target_right_ms)
            return

        self.channel_delay_left_property.set_target(target_left_ms, duration_ms, easing)
        self.channel_delay_right_property.set_target(target_right_ms, duration_ms, easing)

    def get_speed_callback(
            self,
            cleanup:  bool,
            shutdown: bool
        ) -> object:

        if cleanup:
            return self.reset_playback_state

        elif shutdown:
            return self.full_shutdown

        return None

    def set_speed(
            self,
            new_speed:             float,
            duration_ms:           int    = 0,
            easing:                Easing = Easing.smooth,
            on_finish:             object = None,
            use_engine_multiplier: bool   = True,
            cleanup_on_finish:     bool   = False,
            shutdown_on_finish:    bool   = False
        ) -> None:

        self.update_playback_start(new_speed)

        internal_callback = self.get_speed_callback(cleanup_on_finish, shutdown_on_finish)

        def combined_callback() -> None:
            if internal_callback:
                internal_callback()

            if on_finish:
                on_finish()

        self.set_property(
            "speed",
            new_speed,
            duration_ms,
            easing,
            combined_callback,
            use_engine_multiplier
        )

    def set_volume(
            self,
            volume:      float,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        clamped_volume = max(0.0, min(volume, 1.0))
        self.set_property("volume", clamped_volume, duration_ms, easing)

    def set_bitcrush(
            self,
            bits:        int    = 24,
            downsample:  int    = 1,
            mix:         float  = 0.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        self.apply_properties(
            {
                "bitcrush_bits":       float(bits),
                "bitcrush_downsample": float(downsample),
                "bitcrush_mix":        float(mix)
            },
            duration_ms,
            easing
        )

    def set_eq(
            self,
            low:         float  = 1.0,
            mid:         float  = 1.0,
            high:        float  = 1.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        clamped_low  = max(0.0, low)
        clamped_mid  = max(0.0, mid)
        clamped_high = max(0.0, high)

        self.apply_properties(
            {
                "eq_low":  clamped_low,
                "eq_mid":  clamped_mid,
                "eq_high": clamped_high
            },
            duration_ms,
            easing
        )

    def set_background_noise(
            self,
            mix:         float  = 0.3,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        clamped_mix = max(0.0, min(1.0, mix))
        self.set_property("noise_mix", clamped_mix, duration_ms, easing)

    def set_reverb(
            self,
            mix:         float  = 1.0,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        clamped_mix = max(0.0, min(1.0, mix))
        self.set_property("reverb_mix", clamped_mix, duration_ms, easing)

    def set_car_radio_active(
            self,
            duration_ms: int,
            easing:      Easing
        ) -> None:

        self.set_eq(low = 1.6, mid = 1.0, high = 0.7, duration_ms = duration_ms, easing = easing)
        self.set_reverb(mix = 0.35, duration_ms = duration_ms, easing = easing)
        self.set_background_noise(mix = 0.04, duration_ms = duration_ms, easing = easing)

    def set_car_radio_inactive(
            self,
            duration_ms: int,
            easing:      Easing
        ) -> None:

        self.set_eq(low = 1.0, mid = 1.0, high = 1.0, duration_ms = duration_ms, easing = easing)
        self.set_reverb(mix = 0.0, duration_ms = duration_ms, easing = easing)
        self.set_background_noise(mix = 0.0, duration_ms = duration_ms, easing = easing)

    def set_car_radio(
            self,
            active:      bool,
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        if active:
            self.set_car_radio_active(duration_ms, easing)
            return

        self.set_car_radio_inactive(duration_ms, easing)

    def clean_pass_frequencies(self, frequencies: list[float] | tuple[float, ...]) -> list[float]:
        cleaned_frequencies = []

        for frequency in frequencies:
            try:
                value = float(frequency)

            except Exception:
                continue

            if value > 0.0:
                cleaned_frequencies.append(value)

        return cleaned_frequencies

    def set_passes(
            self,
            frequencies: list[float] | tuple[float, ...] | None = None,
            q:           float                                  = 1.0,
            mix:         float                                  = 1.0,
            gain:        float                                  = 1.0,
            duration_ms: int                                    = 0,
            easing:      Easing                                 = Easing.smooth
        ) -> None:

        target_mix          = max(0.0, min(1.0, float(mix)))
        target_gain         = max(0.0, float(gain))
        target_q            = max(0.1, float(q))
        cleaned_frequencies = self.clean_pass_frequencies(frequencies) if frequencies is not None else None

        if target_mix <= 0.0 or (cleaned_frequencies is not None and len(cleaned_frequencies) == 0):
            def on_finish() -> None:
                with self.lock:
                    self.pass_frequencies = []

            if duration_ms <= 0:
                on_finish()
                self.set_property("pass_mix", 0.0)
                return

            self.set_property(
                "pass_mix",
                0.0,
                duration_ms,
                easing,
                on_finish
            )
            return

        if cleaned_frequencies is not None:
            with self.lock:
                self.pass_frequencies = cleaned_frequencies
                self.pass_q           = target_q

                if duration_ms <= 0 and self.data is not None:
                    self.ensure_pass_states(self.data.shape[1])

        self.apply_properties(
            {
                "pass_mix":  target_mix,
                "pass_gain": target_gain,
                "pass_q":    target_q
            },
            duration_ms,
            easing
        )

    def set_noise(
            self,
            intensity:          float  = 0.3,
            mix:                float  = 0.3,
            permanent:          bool   = False,
            color:              str    = "brown",
            attack_ms:          float  = 100.0,
            peak_ms:            float  = 180.0,
            release_ms:         float  = 250.0,
            mute_audio:         float  = 0.45,
            min_duration_ms:    float  = 160.0,
            max_duration_ms:    float  = 900.0,
            randomize_duration: bool   = True,
            duration_ms:        int    = 0,
            easing:             Easing = Easing.smooth
        ) -> None:

        self.radio_noise_color              = color if color in {"white", "pink", "brown"} else "brown"
        self.radio_noise_randomize_duration = bool(randomize_duration)
        self.radio_noise_min_duration_ms    = max(0.0, float(min_duration_ms))
        self.radio_noise_max_duration_ms    = max(self.radio_noise_min_duration_ms, float(max_duration_ms))
        self.radio_noise_permanent          = bool(permanent)

        self.apply_properties(
            {
                "radio_noise_intensity":  max(0.0, float(intensity)),
                "radio_noise_mix":        max(0.0, min(1.0, float(mix))),
                "radio_noise_attack_ms":  max(0.0, float(attack_ms)),
                "radio_noise_peak_ms":    max(0.0, float(peak_ms)),
                "radio_noise_release_ms": max(0.0, float(release_ms)),
                "radio_noise_mute_mix":   max(0.0, min(1.0, float(mute_audio)))
            },
            duration_ms,
            easing
        )

    def set_echo(
            self,
            mix:         float  = 1.0,
            delay_ms:    float  = 180.0,
            feedback:    float  = 0.25,
            mode:        str    = "constant",
            focus:       str    = "all",
            duration_ms: int    = 0,
            easing:      Easing = Easing.smooth
        ) -> None:

        self.echo_mode  = mode if mode in {"constant", "random"} else "constant"
        self.echo_focus = focus if focus in {"all", "audio", "voice", "bass"} else "all"

        self.apply_properties(
            {
                "echo_mix":      max(0.0, min(1.0, float(mix))),
                "echo_delay_ms": max(1.0, float(delay_ms)),
                "echo_feedback": max(0.0, min(0.98, float(feedback)))
            },
            duration_ms,
            easing
        )

    # Shutdown

    def full_shutdown(self) -> None:
        self.reset_playback_state()

        ui_engine.unbind_owner(self)

        with self.lock:
            self.close_stream()

            if self.beat_queue is None:
                return

            try:
                self.beat_queue.put_nowait(None)

            except queue.Full:
                pass

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
        self.sample_rate   = 48000
        self.channels      = 2
        self.next_sound_id = 0
        self.device        = None
        self.mix_generator = None
        self.locked_tags   = set()

    def ensure_device(self) -> None:
        if self.device is not None:
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
            return

        data, sample_rate = soundfile.read(path, dtype = "float32")

        if data.ndim == 1:
            data = numpy.column_stack((data, data))

        data = numpy.ascontiguousarray(data, dtype = numpy.float32)

        if sample_rate != self.sample_rate:
            data = self.resample_data(data, sample_rate)

        self.preloaded[name] = data
        logger.success(f"{name} loaded")

    def resample_data(
            self,
            data:        numpy.ndarray,
            sample_rate: int
        ) -> numpy.ndarray:

        ratio        = self.sample_rate / sample_rate
        num_samples  = max(1, int(len(data) * ratio + 0.5))
        source_index = numpy.linspace(0, len(data) - 1, num_samples, endpoint = False)
        resampled    = numpy.empty((num_samples, self.channels), dtype = numpy.float32)

        for channel_index in range(self.channels):
            resampled[:, channel_index] = numpy.interp(
                source_index,
                numpy.arange(len(data)),
                data[:, channel_index]
            )

        return numpy.ascontiguousarray(resampled, dtype = numpy.float32)

    def pan_to_gains(self, pan: float) -> tuple[float, float]:
        clamped_pan = max(-1.0, min(1.0, pan))

        if clamped_pan <= 0.0:
            spread = -clamped_pan
            return 1.0 - spread * 0.3, 1.0 - spread * 0.7

        spread = clamped_pan
        return 1.0 - spread * 0.7, 1.0 - spread * 0.3

    def play_sound(
            self,
            name:                   str,
            loop:                   bool       = False,
            speed:                  float      = 1.0,
            volume:                 float      = 1.0,
            pan:                    float      = 0.0,
            enable_tone_randomizer: bool       = True,
            tone_spread:            float      = 0.04,
            lock_tag:               str | None = None,
            setting_key:            str | None = None
        ) -> UISound:

        if lock_tag and lock_tag in self.locked_tags:
            return UISound(-1, self)

        if name not in self.preloaded:
            return UISound(-1, self)

        if Constants.current_settings["disable_sounds"]:
            return UISound(-1, self)

        if setting_key and not Constants.current_settings.get(setting_key, True):
            return UISound(-1, self)

        if lock_tag:
            with self.lock:
                self.locked_tags.add(lock_tag)

        audio_data = self.preloaded[name]

        if not Constants.current_settings["sound_tone_effects"]:
            speed = 1.0

        elif enable_tone_randomizer and speed == 1.0:
            speed = random.uniform(1.0 - tone_spread, 1.0 + tone_spread)

        self.ensure_device()

        master_volume         = Constants.current_settings.get("sound_effect_volume", 100) / 100.0
        final_volume          = float(volume) * master_volume
        left_gain, right_gain = self.pan_to_gains(pan)

        with self.lock:
            sound_id           = self.next_sound_id
            self.next_sound_id += 1

            self.cleanup_old_sounds()

            self.active_sounds[sound_id] = {
                "data":       audio_data,
                "position":   0.0,
                "speed":      float(speed),
                "volume":     float(final_volume),
                "loop":       loop,
                "left_gain":  left_gain,
                "right_gain": right_gain
            }

        return UISound(sound_id, self)

    def release_sound(self, lock_tag: str) -> None:
        with self.lock:
            self.locked_tags.discard(lock_tag)

    def cleanup_old_sounds(self) -> None:
        while len(self.active_sounds) >= 16:
            oldest = next(iter(self.active_sounds))
            del self.active_sounds[oldest]

    def stop_sound(self, sound_id: int) -> None:
        with self.lock:
            self.active_sounds.pop(sound_id, None)

    def set_speed(
            self,
            sound_id: int,
            speed:    float
        ) -> None:

        with self.lock:
            if sound_id not in self.active_sounds:
                return

            self.active_sounds[sound_id]["speed"] = float(speed)

    def set_volume(
            self,
            sound_id:   int,
            new_volume: float
        ) -> None:

        with self.lock:
            if sound_id not in self.active_sounds:
                return

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

    def create_mix_generator(self) -> object:
        frames = yield b""

        while True:
            with self.lock:
                snapshots = [
                    (
                        sound_id,
                        sound_data["data"],
                        sound_data["position"],
                        sound_data["speed"],
                        sound_data["volume"],
                        sound_data["loop"],
                        sound_data["left_gain"],
                        sound_data["right_gain"]
                    )
                    for sound_id, sound_data in self.active_sounds.items()
                ]

            master_block = numpy.zeros((frames, self.channels), dtype = numpy.float32)
            updates      = []
            to_remove    = []

            for sound_id, data, position, speed, volume, loop, left_gain, right_gain in snapshots:
                if speed == 1.0:
                    sound_block, new_position, is_active = PlayerFunctions.process_ui_sound_fast(
                        data,
                        float(position),
                        float(volume),
                        frames,
                        loop
                    )

                else:
                    sound_block, new_position, is_active = PlayerFunctions.process_ui_sound_interp(
                        data,
                        float(position),
                        float(speed),
                        float(volume),
                        frames,
                        loop
                    )

                sound_block[:, 0] *= left_gain
                sound_block[:, 1] *= right_gain

                master_block += sound_block

                if is_active:
                    updates.append((sound_id, new_position))

                else:
                    to_remove.append(sound_id)

            with self.lock:
                for sound_id, new_position in updates:
                    if sound_id in self.active_sounds:
                        self.active_sounds[sound_id]["position"] = new_position

                for sound_id in to_remove:
                    self.active_sounds.pop(sound_id, None)

            numpy.clip(master_block, -1.0, 1.0, out = master_block)
            master_block = numpy.nan_to_num(master_block, nan = 0.0, posinf = 1.0, neginf = -1.0)
            pcm          = (master_block * 32767.0).astype(numpy.int16)
            frames       = yield pcm.tobytes()

def shift_right_unsigned(
        value:  int,
        amount: int
    ) -> int:

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
                scaled_time                = int(self.time_index * self.time_scale)
                output_buffer[frame_index] = self.calculate_single_sample(scaled_time)
                self.time_index            += 1

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
        root_mean_square       = float(numpy.sqrt(numpy.mean(normalized ** 2)))
        self.current_intensity = root_mean_square * 2.0

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

        self.device                 = None
        self.formula_bytecode       = None
        self.time_index             = 0
        self.execution_context["t"] = 0

class BPMAnimator(QObject):
    beat_1  = pyqtSignal()
    beat_2  = pyqtSignal()
    beat_4  = pyqtSignal()
    beat_8  = pyqtSignal()
    beat_16 = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()

        self.counter       = 0
        self.current_bpm   = 120
        self.current_speed = 1.0
        self.next_tick_ms  = 0

        self.elapsed = QElapsedTimer()
        self.timer   = QTimer(self)

        self.timer.setInterval(Constants.POLL_INTERVAL_MS)
        self.timer.timeout.connect(self.tick)

        self.last_time        = 0
        self.time_accumulator = 0.0

        self.elapsed.start()

    def beat16_interval(self) -> int:
        bpm   = max(1, self.current_bpm)
        speed = max(0.01, self.current_speed)

        return int(60000 / (bpm * speed * 4))

    def tick(self) -> None:
        now        = self.elapsed.elapsed()
        delta_time = now - self.last_time

        self.last_time = now

        if delta_time > 500:
            delta_time = 0

        self.time_accumulator += delta_time
        interval               = self.beat16_interval()

        while self.time_accumulator >= interval:
            self.time_accumulator -= interval
            self.dispatch_signals()

    def dispatch_signals(self) -> None:
        self.beat_16.emit()

        if self.counter % 2 == 0:
            self.beat_8.emit()

        if self.counter % 4 == 0:
            self.beat_4.emit()

        if self.counter % 8 == 0:
            self.beat_2.emit()

        if self.counter == 0:
            self.beat_1.emit()

        self.counter = (self.counter + 1) % 16

    def set_bpm(self, bpm: int) -> None:
        if not bpm:
            return

        self.current_bpm = int(bpm)

        if not self.timer.isActive():
            self.timer.start()

    def set_speed(self, speed: float) -> None:
        self.current_speed = speed

    def get_interval(self, beat: int) -> int:
        multiplier = {
            16: 1,
            8:  2,
            4:  4,
            2:  8,
            1:  16
        }

        return self.beat16_interval() * multiplier.get(beat, 1)

player       = PlaybackManager()
ui_player    = UISoundManager()
bpm_informer = BPMAnimator()

player.speed_changed.connect(bpm_informer.set_speed)

prefix    = "System/Assets/Sounds"
base_path = Utils.get_resource_path(prefix)
base      = Path(base_path)
sounds    = []

for path in base.rglob("*.wav"):
    relative_path = path.relative_to(base).as_posix()
    name          = relative_path[:-4]
    full_path     = Utils.get_resource_path(f"{prefix}/{relative_path}")

    sounds.append((full_path, name))

for path, name in sounds:
    ui_player.preload(path, name)