from __future__ import annotations

import random

from functools import partial

from PyQt6.QtGui import (
    QShortcut,
    QKeySequence
)

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QObject
)

from System.Common   import Constants
from System.Services import Player

from .GlyphController import GlyphController

from .. import (
    Widget,
    Timeline
)

class KeyboardController(QObject):
    def __init__(
            self,
            compositor: Widget.CompositorWidget,
            conductor:  Timeline.ScrollableContent
        ) -> None:

        super().__init__()

        self.conductor        = conductor
        self.compositor       = compositor
        self.glyph_controller = conductor.glyph_controller
        self.playback_manager = conductor.playback_manager

        self.conductor.installEventFilter(self)

        self.move_increment = Constants.current_settings["arrow_increment"]
        self.shortcuts      = []

        self.base_shortcuts = [
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Z,                                     self.glyph_controller.undo),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Y,                                     self.glyph_controller.redo),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Z, self.glyph_controller.redo),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_C,   self.glyph_controller.copy_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_V,   self.glyph_controller.paste_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_X,   self.glyph_controller.cut_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_D,   self.duplicate_selected_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_F11, self.compositor.open_playground_window),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_A,                                     self.glyph_controller.select_all_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_A, self.glyph_controller.select_all_on_same_track),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Equal, lambda: self.conductor.scale_view(100)),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Minus, lambda: self.conductor.scale_view(-100)),

            (Qt.Key.Key_Space,                                     self.handle_playback_toggle),
            (Qt.Key.Key_Left,                                      lambda: self.handle_manual_playhead_move(-self.move_increment)),
            (Qt.Key.Key_Right,                                     lambda: self.handle_manual_playhead_move(self.move_increment)),
            (Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Left,  lambda: self.handle_manual_playhead_move(-self.move_increment * 10)),
            (Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Right, lambda: self.handle_manual_playhead_move(self.move_increment * 10)),

            (Qt.Key.Key_Delete,    self.handle_deletion),
            (Qt.Key.Key_Backspace, self.handle_deletion),

            (Qt.Key.Key_S,            self.compositor.playspeed_button.next_state),
            (Qt.Key.Key_B,            self.open_brightness_editor),
            (Qt.Key.Key_D,            self.open_duration_editor),
            (Qt.Key.Key_BracketLeft,  lambda: self.glyph_controller.adjust_selected_brightness(-5)),
            (Qt.Key.Key_BracketRight, lambda: self.glyph_controller.adjust_selected_brightness(5)),

            (Qt.Key.Key_Escape, self.handle_escape),

            (Qt.Key.Key_Home, self.go_to_start),
            (Qt.Key.Key_End,  self.go_to_end),
        ]

        self.setup_track_hotkeys()
        self.setup_hotkeys(self.base_shortcuts)

    # HotkeySetup

    def bind(
            self,
            key:    QKeySequence | Qt.Key | int,
            action: object
        ) -> None:

        shortcut = QShortcut(QKeySequence(key), self.conductor)
        shortcut.activated.connect(action)

        self.shortcuts.append(shortcut)

    def setup_hotkeys(self, hotkeys: list[tuple[QKeySequence | Qt.Key | int, object]]) -> None:
        for key, function in hotkeys:
            self.bind(key, function)

    def setup_track_hotkeys(self) -> None:
        for key, track_id in self.glyph_controller.track_map.items():
            self.bind(key, partial(self.glyph_controller.spawn_glyph_on_track, track_id))

    # EventHandling

    def eventFilter(
            self,
            watched: QObject,
            event:   QEvent
        ) -> bool:

        if event.type() != QEvent.Type.KeyRelease:
            return super().eventFilter(watched, event)

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

    # PlayheadManagement

    def handle_playback_toggle(self) -> None:
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

        tone = 1.0 + delta_px / 200
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

        return max(-1.0, min(1.0, (ratio - 0.5) * 2))

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

    # GlyphActions

    def handle_deletion(self) -> None:
        self.glyph_controller.delete_selected_glyphs()
        Player.ui_player.play_sound("Glyphs/Delete", setting_key = "glyph_deletion_sound", lock_tag = "glyph_deletion")

    def open_brightness_editor(self) -> None:
        if not self.ensure_selection("warning_brightness"):
            return

        self.conductor.brightness_control_popup()

    def duplicate_selected_glyphs(self) -> None:
        if not self.ensure_selection("warning_duplicate"):
            return

        self.glyph_controller.copy_glyphs()
        Player.ui_player.play_sound("Glyphs/Duplicate", setting_key = "glyph_duplication_sound")
        self.glyph_controller.paste_glyphs()

    def open_duration_editor(self) -> None:
        if not self.ensure_selection("warning_duration"):
            return

        self.conductor.duration_control_popup()

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

    def handle_escape(self) -> None:
        if self.glyph_controller.expanded_stack:
            self.glyph_controller.collapse_stack()

            return

        self.conductor.scene.clearSelection()

    # Cleanup

    def cleanup_shortcuts(self) -> None:
        self.conductor.removeEventFilter(self)

        for shortcut in self.shortcuts:
            shortcut.activated.disconnect()
            shortcut.deleteLater()

        self.shortcuts.clear()