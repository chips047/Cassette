import sys
import time
import math
import traceback
import threading

import numpy as np
import soundfile as sf
import sounddevice as sd

from loguru import logger

from PyQt5.QtCore import *
from System.Constants import *

def thread_excepthook(args):
    logger.exception(
        "Unhandled exception in thread %s", args.thread.name,
        exc_info = (args.exc_type, args.exc_value, args.exc_traceback)
    )

threading.excepthook = thread_excepthook

class PlaybackManager(QObject):
    playback_state_changed = pyqtSignal(bool)
    audio_loaded = pyqtSignal(np.ndarray, int, float)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.is_playing = False
        self.playback_start_audio_ms = 0
        self.playback_start_wall_time = 0 # Why do I use this? Because some players update their UI 120 frames per second. And for smoothness we need smooth timing.
        
        self.thread = None
        self.stream = None
        self.lock = threading.RLock()

        self._delay_timer = QTimer()
        self._mid_timer = QTimer()
        self._bc_timer = QTimer()
        self._speed_timer = QTimer()
        self._volume_timer = QTimer()
        
        self._delay_timer.timeout.connect(self._delay_tick)
        self._mid_timer.timeout.connect(self._midpass_tick)
        self._bc_timer.timeout.connect(self._bitcrush_tick)
        self._speed_timer.timeout.connect(self._speed_tick)
        self._volume_timer.timeout.connect(self._volume_tick)
        self._mid_timer.timeout.connect(self._midpass_tick)
    
    def _setup_parameters(self):
        self.fade_factor = 1.0
        self.position = 0.0
        self.speed = 1.0
        self.is_playing = False
        self.duration_ms = 0
        self.volume = 1.0
        self.fs = None

        self.cleanup_on_finished = False

        self.midpass_enabled = False
        self.midpass_center = 1000.0
        self.midpass_q = 1.0
        self.midpass_gain = 1.0
        self.midpass_mix = 0.0
        self._b = [1.0, 0.0, 0.0]
        self._a = [1.0, 0.0]
        self._filter_states = None

        self.bitcrush_enabled = False
        self._bitcrush_bits = 16
        self._bitcrush_downsample = 1
        self._bitcrush_mix = 0.0

        self._bc_steps = 0
        self._bc_step = 0
        self._bc_start = None
        self._bc_target = None
        self._bitcrush_state = None

        self._channel_delays_ms = np.array([0.0, 0.0], dtype='float64')
        self._delay_steps = 0
        self._delay_step = 0
        self._delay_start = np.array([0.0, 0.0], dtype='float64')
        self._delay_target = np.array([0.0, 0.0], dtype='float64')

        self._track_peak_level = 1.0 
        self._current_audio_level = 0.0

    def load_audio(self, path):
        try:
            if self.stream:
                self.cleanup()
            
            self._setup_parameters()

            self.data, self.fs = sf.read(path, dtype='float32')
            self.duration_ms = len(self.data) / self.fs * 1000

            if self.data.ndim == 1:
                self.data = np.stack([self.data, self.data], axis=-1)

            self._open_stream()
            
            self.audio_loaded.emit(self.data, self.fs, len(self.data) / self.fs)
        
        except Exception as e:
            logger.error(f"Something went wrong while loading the audio: {traceback.format_exc()}")

    def load_audio_from_data(self, data, fs):
        try:
            if self.stream:
                self.cleanup()
            
            self._setup_parameters()
            
            self.fs = fs
            self.data = data
            self.duration_ms = len(self.data) / self.fs * 1000

            if self.data.ndim == 1:
                self.data = np.stack([self.data, self.data], axis = -1)
            
            self._open_stream()
            
            self.audio_loaded.emit(self.data, self.fs, len(self.data) / self.fs)
            
        except Exception as e:
            logger.error(f"Error initializing from data: {traceback.format_exc()}")

    def _open_stream(self):
        self.stream = sd.OutputStream(
            channels = self.data.shape[1],
            samplerate = self.fs,
            blocksize = 256 if not sys.platform == "linux" else 512,
            latency = "low",
            callback = self.audio_callback
        )
        
        max_abs = np.max(np.abs(self.data))
        with self.lock:
            self._track_peak_level = max(max_abs, 1e-6)
            channels = self.data.shape[1]
            self._filter_states = np.zeros((channels, 4), dtype='float64')
        
        self.stream.start()

    def smooth_channel_delay(self, left_from_ms = None, left_to_ms = None, right_from_ms = None, right_to_ms = None, duration = 0.5, steps = 50):
        if left_from_ms is None:
            left_from_ms = self._channel_delays_ms[0]
        
        if left_to_ms is None:
            left_to_ms = self._channel_delays_ms[0]
        
        if right_from_ms is None:
            right_from_ms = self._channel_delays_ms[1]
        
        if right_to_ms is None:
            right_to_ms = self._channel_delays_ms[1]
        
        steps = max(1, int(steps))
        duration = max(0.0, float(duration))

        if duration == 0.0 or steps <= 1:
            with self.lock:
                self._channel_delays_ms[0] = max(0.0, float(left_to_ms))
                self._channel_delays_ms[1] = max(0.0, float(right_to_ms))
            
            return

        with self.lock:
            self._delay_start = np.array([max(0.0, float(left_from_ms)), max(0.0, float(right_from_ms))], dtype='float64')
            self._delay_target = np.array([max(0.0, float(left_to_ms)), max(0.0, float(right_to_ms))], dtype='float64')

            self._delay_steps = steps
            self._delay_step = 0

        interval_ms = max(1, int((duration / float(self._delay_steps)) * 1000.0))

        self._delay_timer.stop()
        self._delay_timer.setInterval(interval_ms)
        self._delay_timer.start()
    
    def _delay_tick(self):
        i = self._delay_step
        steps = self._delay_steps

        if i >= steps:
            with self.lock:
                self._channel_delays_ms[:] = self._delay_target
            
            self._delay_timer.stop()
            return

        if steps > 1:
            t = float(i) / float(steps - 1)
        
        else:
            t = 1.0
        
        eased = t * t * (3.0 - 2.0 * t)
        new = self._delay_start + (self._delay_target - self._delay_start) * eased

        with self.lock:
            self._channel_delays_ms[:] = new

        self._delay_step += 1

    def _compute_biquad_bandpass(self, center_hz, q):
        fs = float(self.fs)
        if fs is None or fs <= 0:
            return (1.0, 0.0, 0.0), (0.0, 0.0)
        
        omega = 2.0 * math.pi * (center_hz / fs)
        sn = math.sin(omega)
        cs = math.cos(omega)
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

        return (b0, b1, b2), (a1, a2)

    def get_position_ms(self):
        elapsed_ms = (time.time() - self.playback_start_wall_time) * 1000
        return self.playback_start_audio_ms + elapsed_ms * self.speed

    def _update_playback_start(self):
        self.playback_start_audio_ms = self.get_position_ms()
        self.playback_start_wall_time = time.time()
    
    def toggle_playback(self, ms = None):
        if self.is_playing:
            self.stop()
        
        else:
            self.play(ms)
    
    def stop(self):        
        with self.lock:
            self.is_playing = False

        self.playback_state_changed.emit(False)
    
    def play(self, start_pos_ms):
        self.playback_state_changed.emit(True)
        
        with self.lock:
            self.position = int(start_pos_ms * self.fs / 1000)
            self.is_playing = True
        
        self.playback_start_audio_ms = start_pos_ms
        self.playback_start_wall_time = time.time()
    
    def set_speed(self, new_speed, steps = 50, duration = 0.0, stop_on_end = False):
        self._update_playback_start()

        if duration == 0.0:
            with self.lock:
                self.speed = new_speed
            
            return
        
        interval = duration / steps
        self._target_speed = new_speed
        self._speed_steps = steps
        self._speed_step = 0
        self._speed_start = self.speed
        self._stop_on_end = stop_on_end

        self._speed_timer.stop()
        self._speed_timer.setInterval(int(interval * 1000))
        self._speed_timer.start()
    
    def set_volume(self, volume, duration = 0.0, steps = 50):
        if duration == 0.0:
            with self.lock:
                self.volume = max(0.0, min(volume, 1.0))
            
            return
        
        interval = duration / steps
        self._target_volume = volume
        self._volume_steps = steps
        self._volume_step = 0
        self._volume_start = self.volume

        self._volume_timer.stop()
        self._volume_timer.setInterval(int(interval * 1000))
        self._volume_timer.start()

    def _generate_resampled_block(self, frames, ctx):
        channels = self.data.shape[1]
        t = np.arange(frames, dtype='float32')
        base_indices = ctx["pos"] + t * ctx["speed"]
        
        delay_samples = (ctx["delays"] * ctx["fs"] / 1000.0).astype('float32')
        
        res = np.empty((frames, channels), dtype='float32')
        max_idx_minus_one = ctx["max_idx"] - 1

        for ch in range(channels):
            ch_pos = base_indices - delay_samples[ch]
            
            idx_i = ch_pos.astype(np.int32)
            idx_f = ch_pos - idx_i
            
            valid_mask = (idx_i >= 0) & (idx_i < max_idx_minus_one)
            
            safe_idx = idx_i[valid_mask]
            s0 = self.data[safe_idx, ch]
            s1 = self.data[safe_idx + 1, ch]
            
            ch_res = np.zeros(frames, dtype='float32')
            ch_res[valid_mask] = s0 + idx_f[valid_mask] * (s1 - s0)
            
            end_mask = idx_i >= max_idx_minus_one
            ch_res[end_mask] = self.data[ctx["max_idx"], ch]
            
            res[:, ch] = ch_res
            
        return res

    def _apply_midpass_filter(self, block, ctx, states):
        mix = ctx["filter_mix"]
        if mix <= 0: return block
        
        b = ctx["filter_b"]
        a = ctx["filter_a"]
        gain = ctx["filter_gain"]
        
        b0, b1, b2 = b
        a1, a2 = a
        
        filtered = np.empty_like(block)
        for ch in range(block.shape[1]):
            x = block[:, ch]
            y = np.empty(len(x), dtype='float32')
            x1, x2, y1, y2 = states[ch]
            
            for n in range(len(x)):
                yn = b0 * x[n] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                y[n] = yn
                x2 = x1
                x1 = x[n]
                y2 = y1
                y1 = yn
            
            states[ch] = [x1, x2, y1, y2]
            filtered[:, ch] = y
            
        return (1.0 - mix) * block + (mix * filtered * gain)

    def _apply_bitcrush(self, block, ctx, states):
        mix = ctx["bc_mix"]
        if mix <= 0: return block
        
        down = max(1, int(ctx["bc_down"]))
        bits = max(1, min(24, ctx["bc_bits"]))
        levels = (1 << int(bits)) - 1
        inv_levels = 1.0 / levels

        if down > 1:
            original_shape = block.shape
            new_len = (len(block) // down) * down
            reduced = block[:new_len].reshape(-1, down, original_shape[1])
            crushed = np.repeat(reduced[:, 0, :], down, axis=0)
            
            if len(block) > new_len:
                last_val = block[new_len:new_len+1]
                padding = np.repeat(last_val, len(block) - new_len, axis=0)
                crushed = np.vstack([crushed, padding])
        
        else:
            crushed = block.copy()
            
        crushed = np.round((crushed + 1.0) * 0.5 * levels) * inv_levels
        crushed = crushed * 2.0 - 1.0
        
        return (1.0 - mix) * block + mix * crushed

    def audio_callback(self, outdata, frames, time_info, status):
        if status:
            logger.warning(f"Status: {status}")

        with self.lock:
            if not self.is_playing or self.data is None:
                outdata.fill(0)
                return
            
            ctx = {
                "pos": self.position,
                "speed": self.speed,
                "volume": self.volume * self.fade_factor,
                "delays": self._channel_delays_ms,
                "fs": self.fs,
                "max_idx": len(self.data) - 1,
                "do_mid": self.midpass_enabled,
                "do_bit": self.bitcrush_enabled,
                "filter_b": self._b,
                "filter_a": self._a,
                "filter_mix": self.midpass_mix,
                "filter_gain": self.midpass_gain,
                "bc_bits": self._bitcrush_bits,
                "bc_down": self._bitcrush_downsample,
                "bc_mix": self._bitcrush_mix
            }
            f_states = self._filter_states
            bc_states = self._bitcrush_state

        block = self._generate_resampled_block(frames, ctx)

        if ctx["do_mid"] and f_states is not None:
            block = self._apply_midpass_filter(block, ctx, f_states)

        if ctx["do_bit"]:
            block = self._apply_bitcrush(block, ctx, bc_states)

        block *= ctx["volume"]
        outdata[:] = block
        
        with self.lock:
            self.position += frames * ctx["speed"]
            self._current_audio_level = np.max(np.abs(block)) / self._track_peak_level
            
            if self.position >= ctx["max_idx"]:
                self.is_playing = False
                QMetaObject.invokeMethod(self, "stop", Qt.QueuedConnection)

    def get_current_audio_level(self):
        with self.lock:
            return self._current_audio_level

    def tape(
            self,
            start_fade = None,
            end_fade = None,
            start_speed = None,
            end_speed = None,
            start_ms = None,
            duration = 1.5,
            steps = 100,
            cleanup_on_finish = False
        ):

        if not self.is_playing:
            self.play(start_ms or 0)
        
        self.cleanup_on_finished = cleanup_on_finish

        self.set_volume(start_fade if start_fade is not None else self.volume)
        self.set_speed(start_speed if start_speed is not None else self.speed)

        self.set_volume(end_fade if end_fade is not None else self.volume, duration)
        self.set_speed(end_speed if end_speed is not None else self.speed, steps, duration)
    
    def set_channel_delay_ms(self, left_ms: float, right_ms: float):
        with self.lock:
            self._channel_delays_ms[0] = float(left_ms)
            self._channel_delays_ms[1] = float(right_ms)
    
    def enable_bitcrush(self, bits = 8, downsample = 4, mix = 1.0, duration = 0.0, steps = 50):
        with self.lock:
            if self._bitcrush_state is None and self.data is not None:
                channels = self.data.shape[1]
                self._bitcrush_state = np.zeros((channels, 2), dtype='float64')

            if duration == 0.0 or steps <= 0:
                self._bitcrush_bits = bits
                self._bitcrush_downsample = downsample
                self._bitcrush_mix = mix

                self.bitcrush_enabled = True
                return

            self._bc_start = {
                "bits": float(self._bitcrush_bits),
                "down": float(self._bitcrush_downsample),
                "mix": float(self._bitcrush_mix)
            }

            self._bc_target = {
                "bits": float(bits),
                "down": float(max(1, int(downsample))),
                "mix": float(max(0.0, min(1.0, mix)))
            }

            self._bc_steps = max(1, int(steps))
            self._bc_step = 0

            self.bitcrush_enabled = True

        interval_ms = max(1, int((duration / self._bc_steps) * 1000))

        self._bc_timer.stop()
        self._bc_timer.setInterval(interval_ms)
        self._bc_timer.start()
    
    def enable_midpass(self, center_hz = 1000.0, q = 1.0, mix = 1.0, gain = 1.0, duration = 0.0, steps=50):
        with self.lock:
            if duration == 0.0 or steps <= 0:
                self.midpass_enabled = True
                self.midpass_center = float(center_hz)
                self.midpass_q = float(q)
                self.midpass_mix = float(min(max(mix, 0.0), 1.0))
                self.midpass_gain = float(gain)
                self._b, self._a = self._compute_biquad_bandpass(self.midpass_center, self.midpass_q)

                return

            self._mid_target = {
                "center": float(center_hz),
                "q": float(q),
                "mix": float(max(0.0, min(mix, 1.0))),
                "gain": float(gain)
            }

            self._mid_start = {
                "center": float(self.midpass_center),
                "q": float(self.midpass_q),
                "mix": float(self.midpass_mix),
                "gain": float(self.midpass_gain)
            }

            self._mid_steps = max(1, int(steps))
            self._mid_step = 0
            interval_ms = max(1, int((duration / self._mid_steps) * 1000))

            self._b, self._a = self._compute_biquad_bandpass(self.midpass_center, self.midpass_q)

            if self._filter_states is None and self.data is not None:
                channels = self.data.shape[1]
                self._filter_states = np.zeros((channels, 4), dtype='float64')

            self.midpass_enabled = True

            self._mid_timer.stop()
            self._mid_timer.setInterval(interval_ms)
            self._mid_timer.start()

    def disable_bitcrush(self, duration = 0.0, steps = 50):
        with self.lock:
            if not self.bitcrush_enabled:
                return
            
            if duration == 0.0 or steps <= 0:
                self._bitcrush_bits = 24.0
                self._bitcrush_downsample = 1.0
                self._bitcrush_mix = 0.0

                self.bitcrush_enabled = False
                return

            self._bc_start = {
                "bits": float(self._bitcrush_bits),
                "down": float(self._bitcrush_downsample),
                "mix": float(self._bitcrush_mix)
            }

            self._bc_target = {
                "bits": 24.0,
                "down": 1.0,
                "mix": 0.0
            }

            self._bc_steps = steps
            self._bc_step = 0

        interval_ms = max(1, int((duration / self._bc_steps) * 1000))

        self._bc_timer.stop()
        self._bc_timer.setInterval(interval_ms)
        self._bc_timer.start()
    
    def disable_midpass(self, duration = 0.0, steps = 50):
        if duration == 0:
            with self.lock:
                self.midpass_enabled = False
                if self._filter_states is not None:
                    self._filter_states.fill(0.0)
            
            return

        with self.lock:
            self._mid_target = {
                "center": float(self.midpass_center),
                "q": float(self.midpass_q),
                "mix": 0.0,
                "gain": 0.0
            }

            self._mid_start = {
                "center": float(self.midpass_center),
                "q": float(self.midpass_q),
                "mix": float(self.midpass_mix),
                "gain": float(self.midpass_gain)
            }

            self._mid_steps = max(1, int(steps))
            self._mid_step = 0
            interval_ms = max(1, int((duration / self._mid_steps) * 1000))

            self._mid_timer.stop()
            self._mid_timer.setInterval(interval_ms)
            self._mid_timer.start()
    
    def _volume_tick(self):
        with self.lock:
            t = self._volume_step / self._volume_steps
            eased = 1 - (1 - t) ** 3

            if self._volume_step > self._volume_steps:
                self.volume = self._target_volume
                self._volume_timer.stop()
                return

            new_volume = self._volume_start + (self._target_volume - self._volume_start) * eased
            self._update_playback_start()
            self.volume = new_volume

            self._volume_step += 1

    def _speed_tick(self):
        with self.lock:
            t = self._speed_step / self._speed_steps
            eased = 1 - (1 - t) ** 3

            if self._speed_step > self._speed_steps:
                self.speed = self._target_speed
                self._speed_timer.stop()

                if self._stop_on_end:
                    self.stop()
                
                if self.cleanup_on_finished:
                    self.cleanup()

                return

            new_speed = self._speed_start + (self._target_speed - self._speed_start) * eased
            self._update_playback_start()
            self.speed = new_speed

            self._speed_step += 1
    
    def _bitcrush_tick(self):
        i = self._bc_step
        steps = self._bc_steps

        if i >= steps:
            self._bitcrush_bits = self._bc_target["bits"]
            self._bitcrush_downsample = self._bc_target["down"]
            self._bitcrush_mix = self._bc_target["mix"]

            self._bc_timer.stop()
            return

        t = i / float(steps)
        eased = t * t * (3.0 - 2.0 * t)

        with self.lock:
            b0 = self._bc_start["bits"]; b1 = self._bc_target["bits"]
            d0 = self._bc_start["down"]; d1 = self._bc_target["down"]
            m0 = self._bc_start["mix"]; m1 = self._bc_target["mix"]

            self._bitcrush_bits = int(round(b0 + (b1 - b0) * eased))
            self._bitcrush_downsample = max(1, int(round(d0 + (d1 - d0) * eased)))
            self._bitcrush_mix = float(m0 + (m1 - m0) * eased)

        self._bc_step += 1

    def _midpass_tick(self):
        i = self._mid_step
        steps = self._mid_steps

        if i >= steps:
            with self.lock:
                self.midpass_center = float(self._mid_target["center"])
                self.midpass_q = float(self._mid_target["q"])
                self.midpass_mix = float(self._mid_target["mix"])
                self.midpass_gain = float(self._mid_target["gain"])
                self._b, self._a = self._compute_biquad_bandpass(self.midpass_center, self.midpass_q)

                if self._mid_target["mix"] == 0.0:
                    self.midpass_enabled = False
            
            self._mid_timer.stop()
            return

        denom = float(max(1, steps - 1))
        t = float(i) / denom
        eased = t * t * (3.0 - 2.0 * t)

        with self.lock:
            c0 = self._mid_start["center"]; c1 = self._mid_target["center"]
            q0 = self._mid_start["q"]; q1 = self._mid_target["q"]
            m0 = self._mid_start["mix"]; m1 = self._mid_target["mix"]
            g0 = self._mid_start["gain"]; g1 = self._mid_target["gain"]

            new_center = c0 + (c1 - c0) * eased
            new_q = q0 + (q1 - q0) * eased
            new_mix = m0 + (m1 - m0) * eased
            new_gain = g0 + (g1 - g0) * eased

            self.midpass_center = float(new_center)
            self.midpass_q = float(max(0.001, new_q))
            self.midpass_mix = float(max(0.0, min(1.0, new_mix)))
            self.midpass_gain = float(new_gain)

            self._b, self._a = self._compute_biquad_bandpass(self.midpass_center, self.midpass_q)

        self._mid_step += 1
    
    def toggle_playback(self, ms = None):
        if self.is_playing:
            self.stop()
        
        else:
            self.play(ms)
    
    def cleanup(self):
        with self.lock:
            try:
                if self.stream:
                    self.stream.abort()
                    self.stream.close()
                    self.stream = None
            
            except Exception:
                logger.error(f"Error during stream cleanup: {traceback.format_exc()}")
            
            self.stream = None
            
            self._bc_timer.stop()
            self._mid_timer.stop()
            self._speed_timer.stop()
            self._volume_timer.stop()

            self.is_playing = False

            self.data = None
            self.fs = None
            self._filter_states = None
            self._bitcrush_state = None
            self.position = 0.0

player = PlaybackManager()