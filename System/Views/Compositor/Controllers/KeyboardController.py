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
    QTimer,
    pyqtSignal
)

from System.Common import Constants
from System.Services import Player

from System.Interface.Windows import ErrorWindow

from .. import Timeline

class KeyboardController(QObject):
    undo_requested              = pyqtSignal()
    redo_requested              = pyqtSignal()
    copy_requested              = pyqtSignal()
    paste_requested             = pyqtSignal()
    cut_requested               = pyqtSignal()
    duplicate_requested         = pyqtSignal()
    select_all_requested        = pyqtSignal()
    select_track_requested      = pyqtSignal()
    delete_requested            = pyqtSignal()
    escape_requested            = pyqtSignal()
    speed_cycle_requested       = pyqtSignal()
    playground_requested        = pyqtSignal()
    brightness_dialog_requested = pyqtSignal()
    duration_dialog_requested   = pyqtSignal()
    scale_requested             = pyqtSignal(float)
    brightness_adjust_requested = pyqtSignal(int)
    spawn_track_glyph_requested = pyqtSignal(str)

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
        self.ee_active:         bool        = False

        self.space_hold_timer = QTimer(self)
        self.space_hold_timer.setSingleShot(True)
        self.space_hold_timer.timeout.connect(self.trigger_space_ee)

        self.setup_track_hotkeys()
        self.setup_hotkeys()

    # Hotkey Setup

    def bind(
            self,
            key:    QKeySequence | Qt.Key | int,
            action: object
        ) -> None:

        shortcut = QShortcut(QKeySequence(key), self.conductor)
        shortcut.activated.connect(action)

        self.shortcuts.append(shortcut)

    def setup_hotkeys(self) -> None:
        base_shortcuts = [
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Z,                                     self.undo_requested.emit),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Y,                                     self.redo_requested.emit),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Z, self.redo_requested.emit),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_C,   self.copy_requested.emit),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_V,   self.paste_requested.emit),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_X,   self.cut_requested.emit),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_D,   self.handle_duplicate),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_F11, self.playground_requested.emit),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_A,                                     self.select_all_requested.emit),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_A, self.select_track_requested.emit),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Equal, lambda: self.scale_requested.emit(100.0)),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Minus, lambda: self.scale_requested.emit(-100.0)),

            (Qt.Key.Key_Space,                                     self.handle_playback_toggle),
            (Qt.Key.Key_Left,                                      lambda: self.handle_manual_playhead_move(-self.move_increment)),
            (Qt.Key.Key_Right,                                     lambda: self.handle_manual_playhead_move(self.move_increment)),
            (Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Left,  lambda: self.handle_manual_playhead_move(-self.move_increment * 10)),
            (Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Right, lambda: self.handle_manual_playhead_move(self.move_increment * 10)),

            (Qt.Key.Key_Delete,    self.handle_deletion),
            (Qt.Key.Key_Backspace, self.handle_deletion),

            (Qt.Key.Key_S,            self.speed_cycle_requested.emit),
            (Qt.Key.Key_B,            self.open_brightness_editor),
            (Qt.Key.Key_D,            self.open_duration_editor),
            (Qt.Key.Key_BracketLeft,  lambda: self.brightness_adjust_requested.emit(-5)),
            (Qt.Key.Key_BracketRight, lambda: self.brightness_adjust_requested.emit(5)),

            (Qt.Key.Key_Escape, self.escape_requested.emit),

            (Qt.Key.Key_Home, self.go_to_start),
            (Qt.Key.Key_End,  self.go_to_end)
        ]

        for key_combination, callback in base_shortcuts:
            self.bind(key_combination, callback)

    def setup_track_hotkeys(self) -> None:
        for key, track_identifier in self.TRACK_KEY_MAPPINGS.items():
            self.bind(key, partial(self.spawn_track_glyph_requested.emit, track_identifier))

    # Event Handling

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

        return super().eventFilter(watched, event)

    def trigger_space_ee(self) -> None:
        if self.ee_active:
            return

        self.ee_active = True
        self.space_hold_timer.stop()
        self.space_press_times.clear()

        if self.playback_manager.is_playing:
            self.playback_manager.toggle_playback(self.conductor.get_playhead_position_ms())

        try:
            ErrorWindow("Uhm", "Why?").exec()

        finally:
            self.ee_active = False
            self.space_press_times.clear()
            self.space_hold_timer.stop()

    # Playhead Management

    def handle_playback_toggle(self) -> None:
        current_time = time.time()
        self.space_press_times = [t for t in self.space_press_times if current_time - t <= 1.5]
        self.space_press_times.append(current_time)

        if len(self.space_press_times) >= 5:
            self.trigger_space_ee()
            return

        position_ms        = self.conductor.get_playhead_position_ms()
        duration_ms        = self.playback_manager.duration_ms
        engine_position_ms = self.playback_manager.get_position()

        is_at_end = duration_ms > 0 and (
            position_ms        >= (duration_ms - 50.0) or
            engine_position_ms >= (duration_ms - 50.0)
        )

        if is_at_end:
            self.conductor.set_playhead_position_ms(0.0)
            self.conductor.horizontalScrollBar().setValue(0)
            self.conductor.scroll_to_playhead()
            self.playback_manager.toggle_playback(0.0)
            
            return

        if not self.playback_manager.is_playing:
            delay_ms = self.conductor.get_audio_delay_ms()

            if abs(engine_position_ms - delay_ms - position_ms) < 1.0:
                position_ms = engine_position_ms

        self.playback_manager.toggle_playback(position_ms)

    def handle_manual_playhead_move(self, delta_px: int) -> None:
        if self.playback_manager.is_playing:
            return

        tone = 1.0 + delta_px / 200.0
        pan  = self.calculate_playhead_pan()

        Player.ui_player.play_sound(
            "Feedback/PlayheadMove",
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
        self.jump_to_position(0.0, "Feedback/PlayheadForward", "playhead_home")

    def go_to_end(self) -> None:
        self.jump_to_position(self.playback_manager.duration_ms, "Feedback/PlayheadBackward", "playhead_end")

    # Glyph Actions

    def handle_deletion(self) -> None:
        self.delete_requested.emit()
        Player.ui_player.play_sound("Glyphs/Delete", setting_key = "glyph_deletion_sound", lock_tag = "glyph_deletion")

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

    def ensure_selection(self, lock_tag: str = "warning") -> bool:
        if not self.conductor.scene.selectedItems():
            warning_index = random.randint(1, 4)

            Player.ui_player.play_sound(
                f"Signals/Warning/Warning{warning_index}",
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