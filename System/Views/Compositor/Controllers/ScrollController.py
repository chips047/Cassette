from __future__ import annotations

from PyQt6.QtGui import QWheelEvent

from PyQt6.QtCore import (
    Qt,
    QPoint,
    QObject
)

from System.Common              import Constants
from System.Services            import Player
from System.Interface           import Timing
from System.Interface.Animation import LoomEngine

from .. import Timeline

# Unified Scroll Controller Class

class ScrollController(QObject):
    VERTICAL_SENSITIVITY_RATIO: float = 0.35

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor        = conductor
        self.playback_manager = conductor.playback_manager

        self.zoom_step                    = 20 * (Constants.current_settings["zoom_step_percent"] / 100.0)
        self.scroll_acceleration          = 0.3 * (Constants.current_settings["scroll_acceleration_percent"] / 100.0)
        self.vertical_scroll_acceleration = self.scroll_acceleration * self.VERTICAL_SENSITIVITY_RATIO
        self.trackpad_scroll_mode         = Constants.current_settings["trackpad_scroll_mode"]

        smoothing_percent     = float(Constants.current_settings.get("scroll_smoothing_percent", 100))
        self.scroll_smoothing = smoothing_percent > 0.0
        self.smoothing_factor = min(1.0, 0.2 * (100.0 / smoothing_percent)) if smoothing_percent > 0.0 else 1.0

        inertia_percent     = float(Constants.current_settings.get("scroll_inertia_percent", 100))
        self.scroll_inertia = inertia_percent > 0.0
        self.inertia_decay  = max(0.5, min(0.97, 1.0 - 0.1 * (100.0 / inertia_percent))) if inertia_percent > 0.0 else 0.0

        self.horizontal_velocity        = 0.0
        self.horizontal_target_velocity = 0.0
        self.horizontal_remainder       = 0.0
        self.vertical_velocity          = 0.0
        self.vertical_target_velocity   = 0.0
        self.vertical_remainder         = 0.0

        self.scroll_blocked         = False
        self.scale_animation_active = False

        self.drag_damping            = 0.90
        self.drag_max_speed          = 30.0
        self.drag_scroll_margin      = 100
        self.drag_acceleration_curve = 2.0
        self.drag_velocity           = 0.0
        self.drag_position           = float(self.conductor.horizontalScrollBar().value())
        self.drag_is_active          = False
        self.rewind_sound            = None

        self.is_auto_scroll_active  = False
        self.is_flying              = False
        self.is_scrubbing           = False
        self.flight_start_scroll_px = 0.0

        self.inactivity_timer = Timing.Timer(
            interval    = 3000,
            callback    = self.on_scroll_inactivity_timeout,
            single_shot = True,
            parent      = self
        )

        self.scrub_timer = Timing.Timer(
            callback    = self.on_scrub_completed,
            single_shot = True,
            parent      = self
        )

        self.flight_progress_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "flight_progress",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_flight_progress_changed
        )

        self.scrub_playhead_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "scrub_playhead",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_scrub_playhead_updated
        )

        self.scrub_camera_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "scrub_camera",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_scrub_camera_updated
        )

    # State Management

    def set_scale_animation_active(self, is_active: bool) -> None:
        self.scale_animation_active = is_active

    def stop_smooth_scroll(self) -> None:
        self.horizontal_velocity        = 0.0
        self.horizontal_target_velocity = 0.0
        self.horizontal_remainder       = 0.0
        self.vertical_velocity          = 0.0
        self.vertical_target_velocity   = 0.0
        self.vertical_remainder         = 0.0

    def block_scroll(self) -> None:
        self.scroll_blocked = True

    def notify_user_scroll(self) -> None:
        self.is_auto_scroll_active = False

        if self.is_flying:
            self.stop_camera_flight()

        if self.is_scrubbing:
            self.stop_scrubbing()

        self.inactivity_timer.start(3000)

    # Wheel and Gesture Processing

    def process_wheel_event(self, event: QWheelEvent) -> None:
        if self.scroll_blocked:
            return

        modifiers = event.modifiers()

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            delta             = event.angleDelta().y()
            anchor_viewport_x = float(event.position().x())

            self.stop_smooth_scroll()
            self.conductor.scale_view(
                delta             = self.zoom_step if delta > 0 else -self.zoom_step,
                anchor_viewport_x = anchor_viewport_x
            )

            event.accept()

            return

        if event.phase() == Qt.ScrollPhase.ScrollMomentum and not self.scroll_inertia:
            event.accept()

            return

        pixel_delta = event.pixelDelta()
        is_trackpad = not pixel_delta.isNull()

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            if is_trackpad and self.trackpad_scroll_mode == "directional":
                raw_vertical_delta              = float(pixel_delta.y() or pixel_delta.x())
                self.vertical_target_velocity  += -raw_vertical_delta * self.VERTICAL_SENSITIVITY_RATIO
                magnitude                       = abs(raw_vertical_delta)

            else:
                vertical_delta                  = event.angleDelta().y() or event.angleDelta().x()
                self.vertical_target_velocity  += -vertical_delta * self.vertical_scroll_acceleration
                magnitude                       = abs(vertical_delta)

            self.conductor.start_scroll_tick()
            self.conductor.content_scrolled.emit(magnitude)

            event.accept()

            return

        self.notify_user_scroll()

        if is_trackpad and self.trackpad_scroll_mode == "directional":
            self.horizontal_target_velocity += -pixel_delta.x()
            self.vertical_target_velocity   += -pixel_delta.y() * self.VERTICAL_SENSITIVITY_RATIO
            magnitude                        = abs(pixel_delta.x()) + abs(pixel_delta.y())

        else:
            delta = event.angleDelta().y()
            self.horizontal_target_velocity += -delta * self.scroll_acceleration
            magnitude                        = abs(delta)

        self.conductor.start_scroll_tick()
        self.conductor.content_scrolled.emit(magnitude)

        event.accept()

    def process_pinch_event(self, scale_delta: float) -> None:
        self.stop_smooth_scroll()
        self.conductor.scale_view(scale_delta * Constants.PINCH_ZOOM_SENSITIVITY)

    # Edge Drag Auto - Scroll

    def process_drag_position(self, global_position: QPoint) -> None:
        view_position   = self.conductor.viewport().mapFromGlobal(global_position)
        viewport_width  = self.conductor.viewport().width()
        target_velocity = 0.0

        if view_position.x() < self.drag_scroll_margin:
            ratio           = max(0.0, min(1.0, (self.drag_scroll_margin - view_position.x()) / self.drag_scroll_margin))
            target_velocity = -self.drag_max_speed * (ratio ** self.drag_acceleration_curve)

        elif view_position.x() > viewport_width - self.drag_scroll_margin:
            distance_from_right = view_position.x() - (viewport_width - self.drag_scroll_margin)
            ratio               = max(0.0, min(1.0, distance_from_right / self.drag_scroll_margin))
            target_velocity     = self.drag_max_speed * (ratio ** self.drag_acceleration_curve)

        horizontal_bar = self.conductor.horizontalScrollBar()
        is_at_limit    = (
            (target_velocity < -0.1 and horizontal_bar.value() <= horizontal_bar.minimum()) or
            (target_velocity > 0.1  and horizontal_bar.value() >= horizontal_bar.maximum())
        )

        self.drag_velocity = target_velocity
        self.drag_position = float(horizontal_bar.value())

        if abs(self.drag_velocity) > 0.1 and not is_at_limit:
            sound_speed = min(max(abs(self.drag_velocity / 14.0), 0.5), 1.7)

            if not self.drag_is_active:
                Player.ui_player.play_sound("Controls/Rewind/Start", setting_key = "rewind_sounds")

                self.rewind_sound = Player.ui_player.play_sound(
                    "Controls/Rewind/Loop",
                    True,
                    sound_speed,
                    setting_key = "rewind_sounds"
                )

                self.drag_is_active = True

            elif self.rewind_sound:
                self.rewind_sound.set_speed(sound_speed)

            self.notify_user_scroll()
            self.conductor.start_scroll_tick()

        elif self.drag_is_active:
            self.stop_drag(silent = is_at_limit)

    def stop_drag(self, silent: bool = False) -> None:
        self.drag_is_active = False

        if not self.rewind_sound:
            return

        if not silent:
            Player.ui_player.play_sound("Controls/Rewind/Stop", setting_key = "rewind_sounds")

        self.rewind_sound.stop()
        self.rewind_sound = None

    # Ticking

    def tick(self) -> bool:
        wheel_idle = self.tick_wheel()
        drag_idle  = self.tick_drag()

        return wheel_idle and drag_idle

    def tick_wheel(self) -> bool:
        if self.scale_animation_active:
            self.stop_smooth_scroll()

            return True

        if self.scroll_smoothing:
            self.horizontal_velocity += (self.horizontal_target_velocity - self.horizontal_velocity) * self.smoothing_factor
            self.vertical_velocity   += (self.vertical_target_velocity   - self.vertical_velocity)   * self.smoothing_factor

        else:
            self.horizontal_velocity = self.horizontal_target_velocity
            self.vertical_velocity   = self.vertical_target_velocity

        horizontal_bar = self.conductor.horizontalScrollBar()
        vertical_bar   = self.conductor.verticalScrollBar()

        horizontal_step           = self.horizontal_velocity + self.horizontal_remainder
        horizontal_pixels         = int(horizontal_step)
        self.horizontal_remainder = horizontal_step - horizontal_pixels

        vertical_step             = self.vertical_velocity + self.vertical_remainder
        vertical_pixels           = int(vertical_step)
        self.vertical_remainder   = vertical_step - vertical_pixels

        if horizontal_pixels != 0:
            horizontal_bar.setValue(horizontal_bar.value() + horizontal_pixels)

        if vertical_pixels != 0:
            vertical_bar.setValue(vertical_bar.value() + vertical_pixels)

        if self.scroll_inertia:
            self.horizontal_target_velocity *= self.inertia_decay
            self.vertical_target_velocity   *= self.inertia_decay

        else:
            self.horizontal_target_velocity = 0.0
            self.vertical_target_velocity   = 0.0

        is_idle = (
            abs(self.horizontal_velocity)        < 0.1 and
            abs(self.horizontal_target_velocity) < 0.1 and
            abs(self.vertical_velocity)          < 0.1 and
            abs(self.vertical_target_velocity)   < 0.1
        )

        if is_idle:
            self.stop_smooth_scroll()

            return True

        return False

    def tick_drag(self) -> bool:
        if not self.drag_is_active and abs(self.drag_velocity) < 0.1:
            self.drag_velocity = 0.0

            return True

        self.notify_user_scroll()

        horizontal_bar      = self.conductor.horizontalScrollBar()
        self.drag_position += self.drag_velocity
        self.drag_position  = max(float(horizontal_bar.minimum()), min(float(horizontal_bar.maximum()), self.drag_position))

        horizontal_bar.setValue(int(self.drag_position))

        if self.drag_is_active:
            return self.drag_velocity == 0.0

        self.drag_velocity *= self.drag_damping

        if abs(self.drag_velocity) > 0.5:
            return False

        self.drag_velocity = 0.0

        return True

    # LoomEngine Scrub Callbacks

    def on_scrub_playhead_updated(self, playhead_x_px: float) -> None:
        self.conductor.set_playhead_position_px(playhead_x_px, animate = False)

    def on_scrub_camera_updated(self, target_scroll_px: float) -> None:
        horizontal_bar = self.conductor.horizontalScrollBar()
        min_scroll     = horizontal_bar.minimum()
        max_scroll     = horizontal_bar.maximum()
        clamped        = max(min_scroll, min(max_scroll, int(round(target_scroll_px))))

        horizontal_bar.setValue(clamped)

    def on_scrub_completed(self) -> None:
        self.is_scrubbing = False

    def stop_scrubbing(self) -> None:
        self.is_scrubbing = False
        self.scrub_timer.stop()
        self.scrub_playhead_handle.stop_targeting()
        self.scrub_camera_handle.stop_targeting()

    # Camera Flight

    def start_camera_flight(self) -> None:
        self.inactivity_timer.stop()

        self.is_auto_scroll_active  = False
        self.is_flying              = True
        self.flight_start_scroll_px = float(self.conductor.horizontalScrollBar().value())

        current_playhead_px  = self.conductor.get_playhead_position_px()
        viewport_width       = float(self.conductor.viewport().width())
        offset_ratio         = float(Constants.current_settings["playhead_position"])
        target_visual_offset = viewport_width * offset_ratio
        target_scroll_px     = current_playhead_px - target_visual_offset

        distance_px = abs(target_scroll_px - self.flight_start_scroll_px)
        duration_ms = int(min(650, max(350, distance_px / 3.0)))

        self.flight_progress_handle.set_base(0.0)
        self.flight_progress_handle.set_target(
            value                      = 1.0,
            duration_ms                = duration_ms,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = True
        )

    def stop_camera_flight(self) -> None:
        self.is_flying = False
        self.flight_progress_handle.stop_targeting()

    def on_flight_progress_changed(self, progress: float) -> None:
        if not self.is_flying:
            return

        if not self.playback_manager.is_playing:
            self.stop_camera_flight()

            return

        horizontal_bar       = self.conductor.horizontalScrollBar()
        viewport_width       = float(self.conductor.viewport().width())
        offset_ratio         = float(Constants.current_settings["playhead_position"])
        target_visual_offset = viewport_width * offset_ratio

        current_playhead_px = self.conductor.get_playhead_position_px()
        target_scroll_px    = current_playhead_px - target_visual_offset

        min_scroll_px    = float(horizontal_bar.minimum())
        max_scroll_px    = float(horizontal_bar.maximum())
        target_scroll_px = max(min_scroll_px, min(max_scroll_px, target_scroll_px))

        next_scroll_px = self.flight_start_scroll_px + (target_scroll_px - self.flight_start_scroll_px) * progress
        next_scroll_px = max(min_scroll_px, min(max_scroll_px, next_scroll_px))

        horizontal_bar.setValue(int(round(next_scroll_px)))

        if progress >= 1.0:
            horizontal_bar.setValue(int(round(target_scroll_px)))

            self.is_flying             = False
            self.is_auto_scroll_active = True

            self.inactivity_timer.stop()
            self.sync_scroll_to_playhead()

    # Playhead Tracking

    def on_playhead_moved(self, playhead_position_px: float) -> None:
        if not self.playback_manager.is_playing:
            return

        if self.is_flying:
            return

        if self.is_scrubbing:
            return

        if self.inactivity_timer.isActive():
            return

        if not self.is_auto_scroll_active:
            return

        horizontal_bar       = self.conductor.horizontalScrollBar()
        viewport_width       = float(self.conductor.viewport().width())
        offset_ratio         = float(Constants.current_settings["playhead_position"])
        target_visual_offset = viewport_width * offset_ratio
        target_scroll        = round(playhead_position_px - target_visual_offset)

        min_scroll = horizontal_bar.minimum()
        max_scroll = horizontal_bar.maximum()
        clamped    = max(min_scroll, min(max_scroll, target_scroll))

        horizontal_bar.setValue(int(clamped))

    # User Inactivity Timeout

    def on_scroll_inactivity_timeout(self) -> None:
        self.is_scrubbing = False

        if not self.playback_manager.is_playing:
            return

        self.start_camera_flight()

    # Playback State

    def on_playback_started(self) -> None:
        self.stop_scrubbing()
        self.inactivity_timer.stop()

        horizontal_bar       = self.conductor.horizontalScrollBar()
        current_scroll       = float(horizontal_bar.value())
        playhead_x           = self.conductor.get_playhead_position_px()
        viewport_width       = float(self.conductor.viewport().width())
        offset_ratio         = float(Constants.current_settings["playhead_position"])
        target_visual_offset = viewport_width * offset_ratio

        target_scroll_px = playhead_x - target_visual_offset
        min_scroll_px    = float(horizontal_bar.minimum())
        max_scroll_px    = float(horizontal_bar.maximum())
        target_scroll_px = max(min_scroll_px, min(max_scroll_px, target_scroll_px))

        distance_px = abs(target_scroll_px - current_scroll)

        if distance_px > 10.0:
            self.start_camera_flight()

            return

        self.sync_scroll_to_playhead()
        self.is_auto_scroll_active = True

    def on_playback_stopped(self) -> None:
        self.stop_camera_flight()
        self.stop_scrubbing()
        self.inactivity_timer.stop()
        self.is_auto_scroll_active = False

        stop_mode = Constants.current_settings.get("playback_stop_mode", "pause")

        if stop_mode == "return":
            self.scroll_to_playhead()

    # Manual Scroll Commands

    def scroll_to_playhead(self) -> None:
        if self.playback_manager.is_playing:
            return

        horizontal_bar       = self.conductor.horizontalScrollBar()
        playhead_x           = self.conductor.get_target_playhead_position_px()
        viewport_width       = float(self.conductor.viewport().width())
        offset_ratio         = float(Constants.current_settings["playhead_position"])
        target_visual_offset = viewport_width * offset_ratio
        target_scroll        = int(playhead_x - target_visual_offset)

        horizontal_bar.setValue(target_scroll)

    def scroll_to_normalized_position(self, normalized_position: float) -> None:
        self.notify_user_scroll()

        total_width        = self.conductor.total_content_width
        target_playhead_px = normalized_position * total_width

        viewport_width       = float(self.conductor.viewport().width())
        offset_ratio         = float(Constants.current_settings["playhead_position"])
        target_visual_offset = viewport_width * offset_ratio
        target_scroll_px     = target_playhead_px - target_visual_offset

        current_playhead_px = self.conductor.get_playhead_position_px()
        distance_px         = abs(target_playhead_px - current_playhead_px)

        playhead_duration_ms = int(min(280, max(80, distance_px * 1)))
        camera_duration_ms   = int(min(450, max(200, playhead_duration_ms + 120)))

        self.is_scrubbing = True
        self.scrub_timer.start(camera_duration_ms)

        self.scrub_playhead_handle.set_target(
            value                      = target_playhead_px,
            duration_ms                = playhead_duration_ms,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

        self.scrub_camera_handle.set_target(
            value                      = target_scroll_px,
            duration_ms                = camera_duration_ms,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def sync_scroll_to_playhead(self) -> None:
        horizontal_bar       = self.conductor.horizontalScrollBar()
        viewport_width       = float(self.conductor.viewport().width())
        offset_ratio         = float(Constants.current_settings["playhead_position"])
        target_visual_offset = viewport_width * offset_ratio
        target_scroll        = int(self.conductor.get_playhead_position_px() - target_visual_offset)

        horizontal_bar.setValue(target_scroll)

    # Lifecycle

    def cleanup(self) -> None:
        self.stop_smooth_scroll()
        self.stop_drag(silent = True)