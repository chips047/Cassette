from __future__ import annotations

import time

from PyQt6.QtCore import (
    QTimer,
    QObject,
    pyqtSignal
)

from System.Common import Constants
from System.Interface import Timing

from .. import Timeline

class PlaybackController(QObject):
    playhead_moved_ms         = pyqtSignal(float)
    playhead_moved_normalized = pyqtSignal(float)

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor                 = conductor
        self.playback_manager          = conductor.playback_manager
        self.delay_timer               = QTimer(self)
        self.playhead_timer            = Timing.Timer(Constants.FPS_120, self.on_playback_position_updated, fps_managed = True)
        self.pending_start_position_ms = 0.0
        self.playhead_start_ms         = 0.0
        self.playhead_start_time       = 0.0
        self.is_auto_scroll_active     = False

        self.delay_timer.setSingleShot(True)
        self.delay_timer.timeout.connect(self.on_delay_finished)

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

    # Scrolling

    def scroll_to_playhead(self) -> None:
        if self.playback_manager.is_playing:
            return

        horizontal_bar = self.conductor.horizontalScrollBar()
        playhead_x     = self.get_target_playhead_position_px()
        viewport_width = self.conductor.viewport().width()
        target_scroll  = int(playhead_x - viewport_width / 2.0)

        horizontal_bar.setValue(target_scroll)

    def scroll_to_normalized_position(self, normalized_position: float) -> None:
        if self.playback_manager.is_playing:
            self.playback_manager.toggle_playback()

        horizontal_bar = self.conductor.horizontalScrollBar()
        target_scroll  = int(normalized_position * self.conductor.total_content_width - self.conductor.width() / 2.0)
        horizontal_bar.setValue(target_scroll)

        self.set_playhead_position_px(normalized_position * self.conductor.total_content_width)

    def sync_scroll_to_playhead(self) -> None:
        viewport_width       = self.conductor.viewport().width()
        offset_ratio         = Constants.current_settings["playhead_position"]
        target_visual_offset = int(viewport_width * offset_ratio)
        target_scroll        = int(self.get_playhead_position_px()) - target_visual_offset

        self.conductor.horizontalScrollBar().setValue(target_scroll)

    # Playback Tracking

    def compute_playhead_position_ms(self) -> float:
        elapsed_sec = time.perf_counter() - self.playhead_start_time
        position_ms = self.playhead_start_ms + (elapsed_sec * 1000.0 * self.playback_manager.speed)
        duration_ms = self.playback_manager.duration_ms

        if duration_ms > 0:
            position_ms = min(duration_ms, position_ms)

        return max(0.0, position_ms)

    def on_playback_position_updated(self) -> None:
        position_ms        = self.compute_playhead_position_ms()
        true_position_x_px = (position_ms / 1000.0) * self.conductor.px_per_sec

        self.set_playhead_position_px(true_position_x_px)

        horizontal_bar = self.conductor.horizontalScrollBar()
        viewport_width = self.conductor.viewport().width()
        offset_ratio   = Constants.current_settings["playhead_position"]
        target_scroll  = round(true_position_x_px - viewport_width * offset_ratio)

        if not self.is_auto_scroll_active:
            if true_position_x_px < (horizontal_bar.value() + int(viewport_width * offset_ratio)):
                return

            self.is_auto_scroll_active = True

        horizontal_bar.setValue(target_scroll)

    def on_playback_state_changed(self, is_playing: bool) -> None:
        if not is_playing:
            self.stop_playback()
            return

        duration_ms = self.playback_manager.duration_ms

        if duration_ms > 0 and self.get_playhead_position_ms() >= (duration_ms - 50.0):
            self.set_playhead_position_ms(0.0)
            self.conductor.horizontalScrollBar().setValue(0)

        self.start_playback()

        horizontal_bar = self.conductor.horizontalScrollBar()
        playhead_x     = self.get_playhead_position_px()
        viewport_width = self.conductor.viewport().width()

        if playhead_x < horizontal_bar.value() or playhead_x > (horizontal_bar.value() + viewport_width):
            self.is_auto_scroll_active = True
            self.sync_scroll_to_playhead()

        else:
            self.is_auto_scroll_active = False

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
        if self.delay_timer.isActive():
            self.delay_timer.stop()

        self.playhead_timer.stop()

        if self.conductor.glyph_visualizer:
            self.conductor.glyph_visualizer.stop_all()

        if self.conductor.composition:
            self.conductor.composition.syncer.stop()

        duration_ms = self.playback_manager.duration_ms

        if duration_ms > 0:
            engine_position_ms = self.playback_manager.get_position()
            current_ms         = self.get_playhead_position_ms()

            if engine_position_ms >= (duration_ms - 5.0) or (duration_ms - current_ms) <= 60.0:
                self.set_playhead_position_ms(duration_ms)

                if self.is_auto_scroll_active:
                    self.sync_scroll_to_playhead()

        self.is_auto_scroll_active = False

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
        self.conductor.horizontalScrollBar().setValue(0)