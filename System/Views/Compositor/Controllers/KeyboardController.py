from __future__ import annotations

import time
import random

from functools import partial

from PyQt6.QtGui import (
    QShortcut,
    QKeySequence
)

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QObject,
    pyqtSignal
)

from System.Common import Constants

from System.Services          import Player
from System.Interface         import Timing
from System.Interface.Windows import ErrorWindow

from .. import Timeline

# Keyboard Controller

class KeyboardController(QObject):
    undo_requested               = pyqtSignal()
    redo_requested               = pyqtSignal()
    copy_requested               = pyqtSignal()
    paste_requested              = pyqtSignal()
    cut_requested                = pyqtSignal()
    duplicate_requested          = pyqtSignal()
    select_all_requested         = pyqtSignal()
    select_track_requested       = pyqtSignal()
    delete_requested             = pyqtSignal()
    escape_requested             = pyqtSignal()
    speed_cycle_requested        = pyqtSignal()
    effect_cycle_requested       = pyqtSignal()
    playground_requested         = pyqtSignal()
    brightness_dialog_requested  = pyqtSignal()
    duration_dialog_requested    = pyqtSignal()
    segments_dialog_requested    = pyqtSignal()
    shift_segments_requested     = pyqtSignal(int)
    scale_requested              = pyqtSignal(float)
    brightness_adjust_requested  = pyqtSignal(int)
    align_glyph_ends_requested   = pyqtSignal()
    align_glyph_starts_requested = pyqtSignal()
    navigate_glyph_requested     = pyqtSignal(int)
    spawn_track_glyph_requested  = pyqtSignal(str)
    move_track_up_requested      = pyqtSignal()
    move_track_down_requested    = pyqtSignal()
    zoom_selection_requested     = pyqtSignal()
    zoom_fit_requested           = pyqtSignal()

    TRACK_KEY_MAPPINGS: dict[Qt.Key, str] = {
        Qt.Key.Key_A:     Constants.MASTER_TRACK_IDENTIFIER,
        Qt.Key.Key_1:     "1",
        Qt.Key.Key_2:     "2",
        Qt.Key.Key_3:     "3",
        Qt.Key.Key_4:     "4",
        Qt.Key.Key_5:     "5",
        Qt.Key.Key_6:     "6",
        Qt.Key.Key_7:     "7",
        Qt.Key.Key_8:     "8",
        Qt.Key.Key_9:     "9",
        Qt.Key.Key_0:     "10",
        Qt.Key.Key_Minus: "11"
    }

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor        = conductor
        self.playback_manager = conductor.playback_manager

        self.conductor.installEventFilter(self)

        self.move_increment = Constants.current_settings["arrow_increment"]
        self.shortcuts      = []

        self.space_press_times: list[float] = []
        self.easter_egg_active: bool        = False

        self.space_hold_timer = Timing.Timer(
            interval    = 800,
            callback    = self.trigger_space_easter_egg,
            single_shot = True,
            parent      = self
        )

        self.setup_track_hotkeys()
        self.setup_hotkeys()

    # Hotkey Setup

    def bind(
            self,
            key:         QKeySequence | Qt.Key | int,
            action:      object,
            auto_repeat: bool = True
        ) -> None:

        shortcut = QShortcut(QKeySequence(key), self.conductor)
        shortcut.setAutoRepeat(auto_repeat)
        shortcut.activated.connect(action)

        self.shortcuts.append(shortcut)

    # Setup

    def setup_hotkeys(self) -> None:
        base_shortcuts = [
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Z,                                     self.undo_requested.emit,               True),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Y,                                     self.redo_requested.emit,               True),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Z, self.redo_requested.emit,               True),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_C,     self.copy_requested.emit,            False),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_V,     self.paste_requested.emit,           True),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_X,     self.cut_requested.emit,              False),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_D,     self.handle_duplicate,               False),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_E,     self.handle_align_glyph_ends,        False),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_S,     self.handle_align_glyph_starts,      False),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Left,  lambda: self.handle_navigate_glyph(-1), False),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Right, lambda: self.handle_navigate_glyph(1),  False),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_F11,   self.playground_requested.emit,      False),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_A,                                     self.handle_select_all,   False),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_A, self.handle_select_track, False),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Equal, lambda: self.scale_requested.emit(100.0),  True),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Minus, lambda: self.scale_requested.emit(-100.0), True),

            (Qt.Key.Key_F,                                     self.handle_zoom_fit,       False),
            (Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_F, self.handle_zoom_selection, False),

            (Qt.Key.Key_Up,   self.handle_move_track_up,   True),
            (Qt.Key.Key_Down, self.handle_move_track_down, True),

            (Qt.Key.Key_Space,                                       self.handle_playback_toggle,                    False),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Space, self.handle_loop_playback_toggle,               False),
            (Qt.Key.Key_Left,                                        self.handle_arrow_left,                         True),
            (Qt.Key.Key_Right,                                       self.handle_arrow_right,                        True),
            (Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Left,    self.handle_shift_arrow_left,                   True),
            (Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Right,   self.handle_shift_arrow_right,                  True),
            (Qt.KeyboardModifier.AltModifier | Qt.Key.Key_Left,      lambda: self.shift_segments_requested.emit(-1), True),
            (Qt.KeyboardModifier.AltModifier | Qt.Key.Key_Right,     lambda: self.shift_segments_requested.emit(1),  True),
            (Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_S,       self.open_segments_editor,                      False),

            (Qt.Key.Key_Delete,    self.handle_deletion, True),
            (Qt.Key.Key_Backspace, self.handle_deletion, True),

            (Qt.Key.Key_S,            self.speed_cycle_requested.emit,            False),
            (Qt.Key.Key_E,            self.effect_cycle_requested.emit,           False),
            (Qt.Key.Key_B,            self.open_brightness_editor,                False),
            (Qt.Key.Key_D,            self.open_duration_editor,                  False),
            (Qt.Key.Key_BracketLeft,  lambda: self.adjust_brightness_by_step(-1), True),
            (Qt.Key.Key_BracketRight, lambda: self.adjust_brightness_by_step(1),  True),

            (Qt.Key.Key_Escape, self.escape_requested.emit, False),

            (Qt.Key.Key_Home, self.go_to_start, False),
            (Qt.Key.Key_End,  self.go_to_end,   False)
        ]

        for key_combination, callback, auto_repeat in base_shortcuts:
            self.bind(key_combination, callback, auto_repeat = auto_repeat)

    def setup_track_hotkeys(self) -> None:
        for key, track_identifier in self.TRACK_KEY_MAPPINGS.items():
            self.bind(key, partial(self.spawn_track_glyph_requested.emit, track_identifier), auto_repeat = False)

    # Event Filter

    def eventFilter(
            self,
            watched: QObject,
            event:   QEvent
        ) -> bool:

        event_type = event.type()

        if event_type == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                self.space_hold_timer.start(800)

        elif event_type == QEvent.Type.KeyRelease:
            if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                self.space_hold_timer.stop()

            if event.isAutoRepeat():
                return super().eventFilter(watched, event)

            key_code = event.key()

            if key_code == Qt.Key.Key_Home:
                Player.ui_player.release_sound("playhead_home")

            elif key_code == Qt.Key.Key_End:
                Player.ui_player.release_sound("playhead_end")

            elif key_code == Qt.Key.Key_B:
                Player.ui_player.release_sound("warning_brightness")

            elif key_code == Qt.Key.Key_D:
                Player.ui_player.release_sound("warning_duration")
                Player.ui_player.release_sound("warning_duplicate")

            elif key_code in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                Player.ui_player.release_sound("glyph_deletion")

            elif key_code in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                Player.ui_player.release_sound("warning_move_track")

            elif key_code in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight):
                Player.ui_player.release_sound("warning_brightness")

            elif key_code == Qt.Key.Key_F:
                Player.ui_player.release_sound("warning_zoom_selection")
                Player.ui_player.release_sound("warning_already_zoomed")

            elif key_code == Qt.Key.Key_S:
                Player.ui_player.release_sound("warning_segments")

        return super().eventFilter(watched, event)

    def trigger_space_easter_egg(self) -> None:
        if self.easter_egg_active:
            return

        self.easter_egg_active = True
        self.space_hold_timer.stop()
        self.space_press_times.clear()

        if self.playback_manager.is_playing:
            self.playback_manager.toggle_playback(self.conductor.get_playhead_position_ms())

        try:
            ErrorWindow("Uhm", "Why?").exec()

        finally:
            self.easter_egg_active = False
            self.space_press_times.clear()
            self.space_hold_timer.stop()

    # Arrow Navigation and Nudge Handlers

    def handle_navigate_glyph(self, direction: int) -> None:
        if self.playback_manager.is_playing:
            return

        self.navigate_glyph_requested.emit(direction)

    def handle_select_all(self) -> None:
        if self.playback_manager.is_playing:
            return

        self.select_all_requested.emit()

    def handle_select_track(self) -> None:
        if self.playback_manager.is_playing:
            return

        self.select_track_requested.emit()

    def handle_arrow_left(self) -> None:
        if self.conductor.scene.selectedItems():
            self.conductor.glyph_controller.nudge_selected_glyphs_horizontal(-10)
            return

        self.handle_manual_playhead_move(-self.move_increment)

    def handle_arrow_right(self) -> None:
        if self.conductor.scene.selectedItems():
            self.conductor.glyph_controller.nudge_selected_glyphs_horizontal(10)
            return

        self.handle_manual_playhead_move(self.move_increment)

    def handle_shift_arrow_left(self) -> None:
        if self.conductor.scene.selectedItems():
            self.conductor.glyph_controller.nudge_selected_glyphs_duration(-10)
            return

        self.handle_manual_playhead_move(-self.move_increment * 10)

    def handle_shift_arrow_right(self) -> None:
        if self.conductor.scene.selectedItems():
            self.conductor.glyph_controller.nudge_selected_glyphs_duration(10)
            return

        self.handle_manual_playhead_move(self.move_increment * 10)

    # Playhead

    def handle_loop_playback_toggle(self) -> None:
        if self.playback_manager.is_playing:
            self.playback_manager.loop = not self.playback_manager.loop
            status = "enabled" if self.playback_manager.loop else "disabled"
            self.conductor.tooltip.show_tooltip_at(f"Loop {status}", plan_hide = True)

            return

        self.playback_manager.loop = True
        self.conductor.tooltip.show_tooltip_at("Loop playback started", plan_hide = True)

        position_ms = self.conductor.get_playhead_position_ms()
        duration_ms = self.playback_manager.duration_ms

        if duration_ms > 0 and position_ms >= (duration_ms - 50.0):
            self.conductor.set_playhead_position_ms(0.0)
            self.conductor.horizontalScrollBar().setValue(0)
            self.conductor.scroll_to_playhead()
            position_ms = 0.0

        self.playback_manager.toggle_playback(position_ms)

    def handle_playback_toggle(self) -> None:
        if not self.playback_manager.is_playing:
            self.playback_manager.loop = False
        
        current_time           = time.time()
        self.space_press_times = [press_time for press_time in self.space_press_times if current_time - press_time <= 1.5]
        self.space_press_times.append(current_time)

        if len(self.space_press_times) >= 10:
            self.trigger_space_easter_egg()
            return

        position_ms = self.conductor.get_playhead_position_ms()
        duration_ms = self.playback_manager.duration_ms

        is_at_end = duration_ms > 0 and position_ms >= (duration_ms - 50.0)

        if is_at_end:
            self.conductor.set_playhead_position_ms(0.0)
            self.conductor.horizontalScrollBar().setValue(0)
            self.conductor.scroll_to_playhead()
            self.playback_manager.toggle_playback(0.0)

            return

        self.playback_manager.toggle_playback(position_ms)

    def handle_manual_playhead_move(self, delta_px: int) -> None:
        if self.playback_manager.is_playing:
            return

        tone = 1.0 + delta_px / 200.0
        pan  = self.calculate_playhead_pan()

        Player.ui_player.play_sound(
            "Controls/Playhead/Move",
            speed       = tone,
            volume      = 0.2,
            pan         = pan,
            setting_key = "playhead_sounds"
        )

        current_position_x = self.conductor.get_playhead_position_px()
        target_position_x  = max(0.0, min(self.conductor.total_content_width, current_position_x + delta_px))

        self.conductor.set_playhead_position_px(target_position_x, True)

    def calculate_playhead_pan(self) -> float:
        viewport_width = self.conductor.viewport().width()

        if viewport_width <= 0:
            return 0.0

        scene_position_x = self.conductor.get_playhead_position_px()
        view_position_x  = scene_position_x - self.conductor.horizontalScrollBar().value()
        ratio            = view_position_x / viewport_width

        return max(-1.0, min(1.0, (ratio - 0.5) * 2.0))

    def adjust_brightness_by_step(self, direction_factor: int) -> None:
        step_value = int(Constants.current_settings.get("brightness_step", 5))
        self.handle_brightness_adjust(direction_factor * step_value)

    def jump_to_position(
            self,
            position_ms: float,
            sound_name:  str,
            lock_tag:    str
        ) -> None:

        Player.ui_player.play_sound(
            sound_name,
            volume      = 0.5,
            lock_tag    = lock_tag,
            setting_key = "timeline_jump_sounds"
        )

        self.conductor.set_playhead_position_ms(position_ms, True)
        self.conductor.scroll_to_playhead()

    def go_to_start(self) -> None:
        self.jump_to_position(0.0, "Controls/Playhead/Forward", "playhead_home")

    def go_to_end(self) -> None:
        self.jump_to_position(self.playback_manager.duration_ms, "Controls/Playhead/Backward", "playhead_end")

    # Glyph Actions

    def handle_deletion(self) -> None:
        self.delete_requested.emit()
        Player.ui_player.play_sound("Controls/Glyphs/Delete", setting_key = "glyph_deletion_sound", lock_tag = "glyph_deletion")

    def handle_move_track_up(self) -> None:
        if not self.ensure_selection("warning_move_track"):
            return

        self.move_track_up_requested.emit()

    def handle_move_track_down(self) -> None:
        if not self.ensure_selection("warning_move_track"):
            return

        self.move_track_down_requested.emit()

    def handle_brightness_adjust(self, delta: int) -> None:
        if not self.ensure_selection("warning_brightness"):
            return

        self.brightness_adjust_requested.emit(delta)

    def handle_zoom_selection(self) -> None:
        if not self.ensure_selection("warning_zoom_selection"):
            return

        self.zoom_selection_requested.emit()

    def handle_zoom_fit(self) -> None:
        self.zoom_fit_requested.emit()

    def open_brightness_editor(self) -> None:
        if not self.ensure_selection("warning_brightness"):
            return

        self.brightness_dialog_requested.emit()

    def handle_duplicate(self) -> None:
        if not self.ensure_selection("warning_duplicate"):
            return

        self.duplicate_requested.emit()

    def open_duration_editor(self) -> None:
        if not self.ensure_selection("warning_duration"):
            return

        self.duration_dialog_requested.emit()

    def open_segments_editor(self) -> None:
        if not self.ensure_selection("warning_segments"):
            return

        selected_items = self.conductor.glyph_controller.get_selected_glyph_items()
        device         = Constants.DEVICES[self.conductor.composition.model]

        glyphs = [
            glyph
            for item in selected_items
            if (glyph := self.conductor.composition.get_glyph(item.glyph_id)) is not None
        ]

        if not glyphs:
            return

        if any(not device.get_track_segment_count(glyph["track"]) for glyph in glyphs):
            warning_index = random.randint(1, 4)
            Player.ui_player.play_sound(
                name     = f"Alerts/Warnings/Warning{warning_index}",
                lock_tag = "warning_segments"
            )

            message = (
                "Selected glyph does not support segments."
                if len(glyphs) == 1
                else "Selection contains non - segmented glyphs."
            )

            self.conductor.tooltip.show_tooltip_at(message, plan_hide = True)

            return

        first_track = glyphs[0]["track"]

        if any(glyph["track"] != first_track for glyph in glyphs):
            warning_index = random.randint(1, 4)

            Player.ui_player.play_sound(
                f"Alerts/Warnings/Warning{warning_index}",
                lock_tag = "warning_segments"
            )

            self.conductor.tooltip.show_tooltip_at("Selected glyphs must be on the same track.", plan_hide = True)

            return

        self.segments_dialog_requested.emit()

    def handle_align_glyph_ends(self) -> None:
        if not self.ensure_selection("warning_align_ends"):
            return

        self.align_glyph_ends_requested.emit()

    def handle_align_glyph_starts(self) -> None:
        if not self.ensure_selection("warning_align_starts"):
            return

        self.align_glyph_starts_requested.emit()

    def ensure_selection(self, lock_tag: str = "warning") -> bool:
        if not self.conductor.scene.selectedItems():
            warning_index = random.randint(1, 4)

            Player.ui_player.play_sound(
                f"Alerts/Warnings/Warning{warning_index}",
                lock_tag = lock_tag
            )

            self.conductor.tooltip.show_tooltip_at("No glyphs selected.", plan_hide = True)

            return False

        return True

    # Cleanup

    def cleanup_shortcuts(self) -> None:
        self.conductor.removeEventFilter(self)
        self.space_hold_timer.stop()

        for shortcut in self.shortcuts:
            shortcut.activated.disconnect()
            shortcut.deleteLater()

        self.shortcuts.clear()