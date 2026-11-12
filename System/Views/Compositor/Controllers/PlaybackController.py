from __future__ import annotations

import time

from PyQt6.QtCore import (
    QObject,
    pyqtSignal
)

from System.Interface import Timing
from System.Common    import Constants

from .. import Timeline

# Playback Controller Class

class PlaybackController(QObject):
    playhead_moved_ms         = pyqtSignal(float)
    playhead_moved_normalized = pyqtSignal(float)
    playhead_updated_px       = pyqtSignal(float)
    playback_started          = pyqtSignal()
    playback_stopped          = pyqtSignal()

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor                 = conductor
        self.playback_manager          = conductor.playback_manager
        
        self.pending_start_position_ms = 0.0
        self.playhead_start_ms         = 0.0
        self.playhead_start_time       = 0.0
        self.initial_start_position_ms = 0.0

        self.playhead_timer = Timing.Timer(
            interval    = Constants.FPS_120,
            callback    = self.on_playback_position_updated,
            fps_managed = True
        )

        self.delay_timer = Timing.Timer(
            callback    = self.on_delay_finished,
            single_shot = True,
            parent      = self
        )

    # Audio Delay

    def get_audio_delay_ms(self) -> float:
        delay_value = Constants.current_settings.get("audio_delay_ms", 0)

        return float(delay_value)

    # Position Management

    def get_playhead_position_px(self) -> float:
        return self.conductor.playhead.pos().x()

    def get_target_playhead_position_px(self) -> float:
        return self.conductor.playhead.target_horizontal_px

    def set_playhead_position_px(
            self,
            position_px: float,
            animate:     bool = False
        ) -> None:

        target_position_x = max(0.0, min(position_px, self.conductor.total_content_width))
        self.conductor.playhead.set_target_x(target_position_x, animate)

        if not self.playback_manager.is_playing:
            position_ms = (target_position_x / self.conductor.px_per_sec) * 1000.0
            self.playhead_moved_ms.emit(position_ms)

        if self.conductor.total_content_width > 0:
            normalized_position = target_position_x / self.conductor.total_content_width
            self.playhead_moved_normalized.emit(normalized_position)

    def get_playhead_position_ms(self) -> float:
        return (self.conductor.playhead.pos().x() / self.conductor.px_per_sec) * 1000.0

    def set_playhead_position_ms(
            self,
            position_ms: float,
            animate:     bool = False
        ) -> None:

        position_px = (position_ms / 1000.0) * self.conductor.px_per_sec
        self.set_playhead_position_px(position_px, animate)

    # Playback Tracking

    def compute_playhead_position_ms(self) -> float:
        elapsed_sec = time.perf_counter() - self.playhead_start_time
        position_ms = self.playhead_start_ms + (elapsed_sec * 1000.0 * self.playback_manager.speed)
        duration_ms = self.playback_manager.duration_ms

        if duration_ms > 0:
            if self.playback_manager.loop and position_ms >= duration_ms:
                overshoot = position_ms - duration_ms
                speed = max(0.01, self.playback_manager.speed)
                
                self.playhead_start_ms = 0.0
                self.playhead_start_time = time.perf_counter() - (overshoot / (1000.0 * speed))
                position_ms = overshoot

                if self.conductor.composition:
                    self.conductor.composition.syncer.play(0.0)
                
                if self.conductor.glyph_visualizer:
                    self.conductor.glyph_visualizer.play_all(0.0)

            else:
                position_ms = min(duration_ms, position_ms)

        return max(0.0, position_ms)

    def on_playback_position_updated(self) -> None:
        position_ms        = self.compute_playhead_position_ms()
        true_position_x_px = (position_ms / 1000.0) * self.conductor.px_per_sec

        self.set_playhead_position_px(true_position_x_px)
        self.playhead_updated_px.emit(true_position_x_px)

    def handle_view_synchronized(self) -> None:
        if not self.playback_manager.is_playing:
            return

        self.on_playback_position_updated()

    # Playback Control

    def on_playback_state_changed(self, is_playing: bool) -> None:
        if not is_playing:
            self.stop_playback()

            return

        duration_ms = self.playback_manager.duration_ms

        if duration_ms > 0 and self.get_playhead_position_ms() >= (duration_ms - 50.0):
            self.set_playhead_position_ms(0.0)

        self.initial_start_position_ms = self.get_playhead_position_ms()
        self.start_playback()
        self.playback_started.emit()

    def start_playback(self) -> None:
        if self.delay_timer.isActive():
            self.delay_timer.stop()

        position_ms = self.get_playhead_position_ms()
        delay_ms    = self.get_audio_delay_ms()

        self.pending_start_position_ms = position_ms

        if self.conductor.composition:
            self.conductor.composition.syncer.play(position_ms)

        if delay_ms > 0:
            self.delay_timer.setInterval(int(delay_ms))
            self.delay_timer.start()

        else:
            self.on_delay_finished()

    def on_delay_finished(self) -> None:
        position_ms = self.pending_start_position_ms

        self.playhead_start_ms   = position_ms
        self.playhead_start_time = time.perf_counter()

        self.playhead_timer.start()

        if self.conductor.glyph_visualizer and self.conductor.composition:
            self.conductor.glyph_visualizer.set_schedule(self.conductor.composition.glyphs.visualizator_data)
            self.conductor.glyph_visualizer.play_all(position_ms)

    def on_playback_speed_changed(self, speed: float) -> None:
        if not self.playhead_timer.isActive():
            return

        self.playhead_start_ms   = self.compute_playhead_position_ms()
        self.playhead_start_time = time.perf_counter()

    def stop_playback(self) -> None:
        self.playback_manager.loop = False
        
        if self.delay_timer.isActive():
            self.delay_timer.stop()

        self.playhead_timer.stop()

        if self.conductor.glyph_visualizer:
            self.conductor.glyph_visualizer.stop_all()

        if self.conductor.composition:
            self.conductor.composition.syncer.stop()

        stop_mode = Constants.current_settings.get("playback_stop_mode", "pause")

        if stop_mode == "return":
            self.set_playhead_position_ms(self.initial_start_position_ms)

        else:
            duration_ms = self.playback_manager.duration_ms

            if duration_ms > 0:
                engine_position_ms = self.playback_manager.get_position()
                current_ms         = self.get_playhead_position_ms()

                if engine_position_ms >= (duration_ms - 5.0) or (duration_ms - current_ms) <= 60.0:
                    self.set_playhead_position_ms(duration_ms)

        self.playback_stopped.emit()

    # Lifecycle

    def attach_playback_signals(self) -> None:
        self.playback_manager.playback_state_changed.connect(self.on_playback_state_changed)
        self.playback_manager.speed_changed.connect(self.on_playback_speed_changed)

    def cleanup(self) -> None:
        if self.delay_timer.isActive():
            self.delay_timer.stop()

        self.playhead_timer.stop()

        try:
            self.playback_manager.playback_state_changed.disconnect(self.on_playback_state_changed)

        except (TypeError, RuntimeError):
            pass

        try:
            self.playback_manager.speed_changed.disconnect(self.on_playback_speed_changed)

        except (TypeError, RuntimeError):
            pass

        self.set_playhead_position_px(0.0)