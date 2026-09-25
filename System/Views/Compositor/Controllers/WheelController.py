from __future__ import annotations

from PyQt6.QtCore import (
    Qt,
    QEvent
)

from System.Common import Constants

from .. import Timeline

class WheelController:
    # Initialization Section

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        self.conductor                  = conductor
        self.horizontal_velocity        = 0.0
        self.horizontal_target_velocity = 0.0
        self.vertical_velocity          = 0.0
        self.vertical_target_velocity   = 0.0

        self.zoom_step              = Constants.current_settings["zoom_step"]
        self.scroll_acceleration    = Constants.current_settings["scroll_acceleration"]
        self.trackpad_scroll_mode   = Constants.current_settings["trackpad_scroll_mode"]
        self.scroll_smoothing       = Constants.current_settings["scroll_smoothing"]
        self.scroll_inertia         = Constants.current_settings["scroll_inertia"]
        self.scroll_blocked         = False
        self.scale_animation_active = False

    # State Management Section

    def set_scale_animation_active(self, is_active: bool) -> None:
        self.scale_animation_active = is_active

    def stop_smooth_scroll(self) -> None:
        self.horizontal_velocity        = 0.0
        self.horizontal_target_velocity = 0.0
        self.vertical_velocity          = 0.0
        self.vertical_target_velocity   = 0.0

    def block_scroll(self) -> None:
        self.scroll_blocked = True

    # Event Processing Section

    def process_wheel_event(self, event: QEvent) -> None:
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

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            vertical_delta = event.angleDelta().y()
            vertical_bar   = self.conductor.verticalScrollBar()

            vertical_bar.setValue(vertical_bar.value() - vertical_delta)
            self.conductor.content_scrolled.emit(abs(vertical_delta))

            event.accept()
            return

        if self.conductor.playback_manager.is_playing:
            event.accept()
            return

        if event.phase() == Qt.ScrollPhase.ScrollMomentum and not self.scroll_inertia:
            event.accept()
            return

        pixel_delta = event.pixelDelta()
        is_trackpad = not pixel_delta.isNull()

        if is_trackpad and self.trackpad_scroll_mode == "directional":
            self.horizontal_target_velocity += -pixel_delta.x()
            self.vertical_target_velocity   += -pixel_delta.y()

            magnitude = abs(pixel_delta.x()) + abs(pixel_delta.y())

        else:
            delta = event.angleDelta().y()
            self.horizontal_target_velocity += -delta * self.scroll_acceleration

            magnitude = abs(delta)

        self.conductor.start_scroll_tick()
        self.conductor.content_scrolled.emit(magnitude)

        event.accept()

    def process_pinch_event(self, scale_delta: float) -> None:
        self.stop_smooth_scroll()
        self.conductor.scale_view(scale_delta * Constants.PINCH_ZOOM_SENSITIVITY)

    # Scroll Ticking Section

    def tick(self) -> bool:
        if self.scale_animation_active:
            self.stop_smooth_scroll()
            return True

        if self.scroll_smoothing:
            self.horizontal_velocity += (self.horizontal_target_velocity - self.horizontal_velocity) * 0.2
            self.vertical_velocity   += (self.vertical_target_velocity   - self.vertical_velocity)   * 0.2

        else:
            self.horizontal_velocity = self.horizontal_target_velocity
            self.vertical_velocity   = self.vertical_target_velocity

        horizontal_bar = self.conductor.horizontalScrollBar()
        vertical_bar   = self.conductor.verticalScrollBar()

        horizontal_bar.setValue(int(horizontal_bar.value() + self.horizontal_velocity))
        vertical_bar.setValue(int(vertical_bar.value()     + self.vertical_velocity))

        if self.scroll_inertia:
            self.horizontal_target_velocity *= 0.9
            self.vertical_target_velocity   *= 0.9

        else:
            self.horizontal_target_velocity = 0.0
            self.vertical_target_velocity   = 0.0

        is_idle = (
            abs(self.horizontal_velocity)        < 0.2 and
            abs(self.horizontal_target_velocity) < 0.2 and
            abs(self.vertical_velocity)          < 0.2 and
            abs(self.vertical_target_velocity)   < 0.2
        )

        if is_idle:
            self.stop_smooth_scroll()
            return True

        return False