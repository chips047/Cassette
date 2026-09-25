from __future__ import annotations

import random

from PyQt6.QtGui import (
    QCursor,
    QPixmap
)

from PyQt6.QtCore import (
    QObject,
    pyqtSignal
)

from System.Common import Constants

from System.Services import Player

from System.Interface import Timing

from .. import Timeline

class ScaleController(QObject):
    zoom_changed            = pyqtSignal(float)
    scale_started           = pyqtSignal()
    scale_finished          = pyqtSignal()
    scale_updated           = pyqtSignal()
    view_synchronized       = pyqtSignal()
    animation_state_changed = pyqtSignal(bool)

    # Initialization Section

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor = conductor

        self.px_per_sec             = Constants.current_settings["default_scaling"]
        self.target_px_per_sec      = self.px_per_sec
        self.scale_anim_active      = False
        self.scale_anim_anchor_ms   = 0.0
        self.scale_anim_anchor_view = 0.0

        self.waveform_anim_timer = Timing.Timer(
            Constants.FPS_120,
            self.on_waveform_anim_tick,
            fps_managed = True
        )

        self.tile_fade_subframe = 0

        self.frozen_tiles:               dict[int, QPixmap] = {}
        self.frozen_px_per_sec:          float              = self.px_per_sec
        self.frozen_fallback_tiles:      dict[int, QPixmap] = {}
        self.frozen_fallback_px_per_sec: float              = self.px_per_sec
        self.tile_fade_alphas:           dict[int, float]   = {}

    # Scaling Section

    def scale_view(
            self,
            delta:             float        = 0.0,
            force_update:      bool         = False,
            anchor_viewport_x: float | None = None
        ) -> None:
        if not self.conductor.total_content_width:
            return

        viewport_width = self.conductor.viewport().width()
        current_scroll = self.conductor.horizontalScrollBar().value()

        duration_sec       = max(self.conductor.playback_manager.duration_ms / 1000.0, 0.001)
        fit_px_per_sec     = viewport_width / duration_sec
        minimum_px_per_sec = max(fit_px_per_sec, 20.0)
        new_target         = max(minimum_px_per_sec, self.target_px_per_sec + delta)

        if self.target_px_per_sec == new_target and not force_update:
            return

        magnitude = abs(new_target - self.target_px_per_sec)

        self.target_px_per_sec = new_target
        self.zoom_changed.emit(magnitude)

        if not self.scale_anim_active:
            resolved_anchor_x = anchor_viewport_x

            if resolved_anchor_x is None:
                mouse_local = self.conductor.viewport().mapFromGlobal(QCursor.pos())

                if 0 <= mouse_local.x() <= viewport_width:
                    resolved_anchor_x = float(mouse_local.x())

                else:
                    resolved_anchor_x = viewport_width / 2.0

            scene_anchor_px             = current_scroll + resolved_anchor_x
            self.scale_anim_anchor_ms   = (scene_anchor_px / self.px_per_sec) * 1000.0
            self.scale_anim_anchor_view = resolved_anchor_x
            self.frozen_px_per_sec      = self.px_per_sec

            self.tile_fade_subframe = 0
            self.tile_fade_alphas.clear()
            self.frozen_fallback_tiles.clear()

            self.scale_started.emit()

        self.scale_anim_active = True
        self.animation_state_changed.emit(True)

        if not self.waveform_anim_timer.isActive():
            self.waveform_anim_timer.start()

    def zoom_to_selection(self) -> None:
        selected_items = self.conductor.scene.selectedItems()

        if not selected_items:
            warning_index = random.randint(1, 4)

            Player.ui_player.play_sound(
                f"Signals/Warning/Warning{warning_index}",
                lock_tag = "warning_zoom_selection"
            )

            self.conductor.tooltip.show_tooltip_at("No glyphs selected.", plan_hide = True)

            return

        min_start_ms = min(item.start_ms for item in selected_items)
        max_end_ms   = max(item.start_ms + item.duration_ms for item in selected_items)
        duration_ms  = max(10.0, float(max_end_ms - min_start_ms))

        viewport_width  = float(self.conductor.viewport().width())
        padding_px      = 120.0
        usable_width_px = max(50.0, viewport_width - padding_px)

        target_scaling = usable_width_px / (duration_ms / 1000.0)
        target_scaling = max(20.0, min(3000.0, target_scaling))

        center_ms = min_start_ms + (duration_ms / 2.0)

        current_scroll       = float(self.conductor.horizontalScrollBar().value())
        target_scroll        = round((center_ms / 1000.0) * target_scaling - viewport_width / 2.0)
        maximum_scroll       = float(self.conductor.horizontalScrollBar().maximum())
        expected_scroll      = max(0.0, min(maximum_scroll, float(target_scroll)))

        scale_matches        = abs(self.px_per_sec - target_scaling) < 0.5
        scroll_matches       = abs(current_scroll - expected_scroll) <= 2.0
        is_already_targeting = abs(self.target_px_per_sec - target_scaling) < 0.5

        if (scale_matches and scroll_matches) or (self.scale_anim_active and is_already_targeting):
            warning_index = random.randint(1, 4)

            Player.ui_player.play_sound(
                f"Signals/Warning/Warning{warning_index}",
                lock_tag = "warning_already_zoomed"
            )

            self.conductor.tooltip.show_tooltip_at("Already zoomed to selection.", plan_hide = True)

            return

        self.target_px_per_sec      = target_scaling
        self.scale_anim_anchor_ms   = center_ms
        self.scale_anim_anchor_view = viewport_width / 2.0
        self.frozen_px_per_sec      = self.px_per_sec

        self.scale_anim_active = True
        self.animation_state_changed.emit(True)
        self.scale_started.emit()

        if not self.waveform_anim_timer.isActive():
            self.waveform_anim_timer.start()

    def zoom_to_fit(self) -> None:
        total_duration_ms = self.conductor.playback_manager.duration_ms

        if total_duration_ms <= 0.0:
            return

        viewport_width  = float(self.conductor.viewport().width())
        padding_px      = 40.0
        usable_width_px = max(50.0, viewport_width - padding_px)

        target_scaling = usable_width_px / (total_duration_ms / 1000.0)
        target_scaling = max(20.0, target_scaling)

        self.target_px_per_sec      = target_scaling
        self.scale_anim_anchor_ms   = total_duration_ms / 2.0
        self.scale_anim_anchor_view = viewport_width / 2.0
        self.frozen_px_per_sec      = self.px_per_sec

        self.scale_anim_active = True
        self.animation_state_changed.emit(True)
        self.scale_started.emit()

        if not self.waveform_anim_timer.isActive():
            self.waveform_anim_timer.start()

    def set_frozen_tiles(self, tiles: dict[int, QPixmap]) -> None:
        self.frozen_tiles = tiles

    def on_tile_ready(
            self,
            tile_index: int,
            pixmap:     QPixmap
        ) -> None:
        if self.scale_anim_active:
            self.frozen_tiles.setdefault(tile_index, pixmap)

        if self.frozen_fallback_tiles:
            self.tile_fade_alphas[tile_index] = 0.0

            if not self.waveform_anim_timer.isActive():
                self.waveform_anim_timer.start()

    # Animation Updates Section

    def on_waveform_anim_tick(self) -> None:
        if self.scale_anim_active:
            self.step_scale_animation()
            return

        self.tile_fade_subframe += 1

        if self.tile_fade_subframe < 2:
            return

        self.tile_fade_subframe = 0

        if self.step_tile_fade():
            self.waveform_anim_timer.stop()
            self.conductor.cached_beat_lines.clear()

    def step_scale_animation(self) -> None:
        difference          = self.target_px_per_sec - self.px_per_sec
        current_playhead_ms = self.conductor.get_playhead_position_ms()

        if abs(difference) < 0.3:
            self.px_per_sec        = self.target_px_per_sec
            self.scale_anim_active = False
            self.animation_state_changed.emit(False)
            self.conductor.cached_beat_lines.clear()
            self.finish_scale_change(current_playhead_ms)

            return

        self.px_per_sec += difference * 0.18
        self.conductor.cached_beat_lines.clear()
        self.apply_intermediate_scale(current_playhead_ms)

    def apply_intermediate_scale(self, current_playhead_ms: float) -> None:
        self.conductor.update_scene_rect()
        self.synchronize_view_after_scale(current_playhead_ms)
        self.scale_updated.emit()
        self.conductor.viewport().update()

    def finish_scale_change(self, current_playhead_ms: float) -> None:
        self.tile_fade_subframe         = 0
        self.tile_fade_alphas.clear()
        self.frozen_fallback_tiles      = dict(self.frozen_tiles)
        self.frozen_fallback_px_per_sec = self.frozen_px_per_sec
        self.frozen_tiles.clear()

        self.conductor.cached_beat_lines.clear()
        self.conductor.update_scene_rect()
        self.synchronize_view_after_scale(current_playhead_ms)

        self.scale_finished.emit()
        self.conductor.viewport().update()

    def synchronize_view_after_scale(self, current_playhead_ms: float) -> None:
        self.update_scroll_to_anchor()
        self.conductor.set_playhead_position_ms(current_playhead_ms)
        self.view_synchronized.emit()

        if not self.conductor.playback_manager.is_playing:
            self.update_scroll_to_anchor()
            self.conductor.set_playhead_position_ms(current_playhead_ms)

    def step_tile_fade(self) -> bool:
        if not self.tile_fade_alphas:
            self.frozen_fallback_tiles.clear()
            return True

        completed_indices = [
            index
            for index, alpha in self.tile_fade_alphas.items()
            if alpha >= 1.0
        ]

        for index in completed_indices:
            del self.tile_fade_alphas[index]

        for index in self.tile_fade_alphas:
            self.tile_fade_alphas[index] = min(1.0, self.tile_fade_alphas[index] + 0.09)

        self.conductor.viewport().update()
        return not self.tile_fade_alphas

    def update_scroll_to_anchor(self) -> None:
        new_anchor_scene_px = (self.scale_anim_anchor_ms / 1000.0) * self.px_per_sec
        new_scroll_value    = round(new_anchor_scene_px - self.scale_anim_anchor_view)

        self.conductor.horizontalScrollBar().setValue(new_scroll_value)

    # Cleanup Section

    def cleanup(self) -> None:
        self.waveform_anim_timer.stop()
        self.scale_anim_active = False
        self.animation_state_changed.emit(False)
        self.frozen_tiles.clear()
        self.frozen_fallback_tiles.clear()
        self.tile_fade_alphas.clear()