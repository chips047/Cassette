from __future__ import annotations

import copy
import random

from functools import partial

from PyQt6.QtGui import (
    QCursor,
    QKeyEvent,
    QShortcut,
    QMouseEvent,
    QKeySequence
)

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QEvent,
    QPoint,
    QRectF,
    QPointF,
    QObject,
    pyqtSignal,
    QEasingCurve,
    QPropertyAnimation
)

from PyQt6.QtWidgets import (
    QApplication
)

from System.Common import (
    Styles,
    Constants
)

from System.Services import (
    Player,
    GlyphEffects
)

from System.Interface import (
    Basic,
    Widgets
)

from . import (
    Widget,
    Actions,
    Timeline
)

class KeyboardController(QObject):
    def __init__(
        self,
        compositor: Widget.CompositorWidget,
        conductor:  Timeline.ScrollableContent,
    ) -> None:
        
        super().__init__()

        self.conductor  = conductor
        self.compositor = compositor

        self.glyph_controller: GlyphController        = conductor.glyph_controller
        self.playback_manager: Player.PlaybackManager = conductor.playback_manager

        self.conductor.installEventFilter(self)

        self.move_increment = Constants.current_settings["arrow_increment"]
        self.shortcuts      = []

        self.base_shortcuts = [
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Z,                                      self.glyph_controller.undo),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Y,                                      self.glyph_controller.redo),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Z,  self.glyph_controller.redo),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_C,   self.glyph_controller.copy_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_V,   self.glyph_controller.paste_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_X,   self.glyph_controller.cut_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_D,   self.duplicate_selected_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_F11, self.compositor.open_playground_window),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_A,                                     self.glyph_controller.select_all_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_A, self.glyph_controller.select_all_on_same_track),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Equal,                                  lambda: self.conductor.scale_view(100)),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Minus,                                  lambda: self.conductor.scale_view(-100)),

            (Qt.Key.Key_Space,                                    self.handle_playback_toggle),
            (Qt.Key.Key_Left,                                     lambda: self.handle_manual_playhead_move(-self.move_increment)),
            (Qt.Key.Key_Right,                                    lambda: self.handle_manual_playhead_move(self.move_increment)),
            (Qt.KeyboardModifier.ShiftModifier |Qt.Key.Key_Left,  lambda: self.handle_manual_playhead_move(-self.move_increment * 10)),
            (Qt.KeyboardModifier.ShiftModifier |Qt.Key.Key_Right, lambda: self.handle_manual_playhead_move(self.move_increment * 10)),

            (Qt.Key.Key_Delete,    self.glyph_controller.delete_selected_glyphs),
            (Qt.Key.Key_Backspace, self.glyph_controller.delete_selected_glyphs),

            (Qt.Key.Key_S, self.compositor.playspeed_button.next_state),
            (Qt.Key.Key_B, self.open_brightness_editor),
            (Qt.Key.Key_BracketLeft,  lambda: self.glyph_controller.adjust_selected_brightness(-5)),
            (Qt.Key.Key_BracketRight, lambda: self.glyph_controller.adjust_selected_brightness(5)),
            (Qt.Key.Key_D, self.open_duration_editor),

            (Qt.Key.Key_Escape, self.handle_escape),

            (Qt.Key.Key_Home, self.go_to_start),
            (Qt.Key.Key_End,  self.go_to_end),
        ]

        self.setup_track_hotkeys()
        self.setup_hotkeys(self.base_shortcuts)

    def bind(self, key: QKeySequence, action: object) -> None:
        shortcut = QShortcut(QKeySequence(key), self.conductor)
        shortcut.activated.connect(action)
        
        self.shortcuts.append(shortcut)

    def setup_hotkeys(self, hotkeys: list[tuple[QKeySequence, object]]) -> None:
        for key, function in hotkeys:
            self.bind(key, function)

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

        return super().eventFilter(watched, event)

    def setup_track_hotkeys(self) -> None:
        for key, track_id in self.glyph_controller.track_map.items():
            self.bind(key, partial(self.glyph_controller.spawn_glyph_on_track, track_id))

    def handle_playback_toggle(self) -> None:
        pos       = self.conductor.get_playhead_position_ms()
        duration  = self.playback_manager.duration_ms
        is_at_end = pos >= (duration - 15)

        if is_at_end:
            pos = 0
            self.conductor.set_playhead_position_ms(pos)

        self.playback_manager.toggle_playback(pos)

    def handle_manual_playhead_move(self, delta_px: int) -> None:
        if self.playback_manager.is_playing:
            return
        
        tone = 1.0 + delta_px / 200
        Player.ui_player.play_sound(
            "Feedback/PlayheadMove",
            speed  = tone,
            volume = 0.2
        )

        current_x = self.conductor.get_playhead_position_px()
        target_x  = max(0, min(self.conductor.total_content_width, current_x + delta_px))

        self.conductor.set_playhead_position_px(target_x, True)

    def open_brightness_editor(self) -> None:
        if not self.ensure_selection("warning_brightness"):
            return

        self.conductor.brightness_control_popup()

    def duplicate_selected_glyphs(self) -> None:
        if not self.ensure_selection("warning_duplicate"):
            return

        self.glyph_controller.copy_glyphs()
        self.glyph_controller.paste_glyphs()

    def open_duration_editor(self) -> None:
        if not self.ensure_selection("warning_duration"):
            return

        self.conductor.duration_control_popup()

    def ensure_selection(self, lock_tag: str = "warning") -> bool:
        if not self.conductor.scene.selectedItems():
            Player.ui_player.play_sound(
                f"Signals/Warning/Warning{random.randint(1, 4)}",
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
    
    def go_to_start(self) -> None:
        Player.ui_player.play_sound(
            "Feedback/PlayheadForward",
            volume   = 0.5,
            lock_tag = "playhead_home"
        )

        self.conductor.set_playhead_position_ms(0, True)
        self.conductor.scroll_to_playhead()
    
    def go_to_end(self) -> None:
        Player.ui_player.play_sound(
            "Feedback/PlayheadBackward",
            volume   = 0.5,
            lock_tag = "playhead_end"
        )

        self.conductor.set_playhead_position_ms(self.playback_manager.duration_ms, True)
        self.conductor.scroll_to_playhead()

    def cleanup_shortcuts(self) -> None:
        self.conductor.removeEventFilter(self)

        for shortcut in self.shortcuts:
            shortcut.activated.disconnect()
            shortcut.deleteLater()

        self.shortcuts = []

class WheelController:
    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        self.conductor = conductor

        self.scroll_velocity        = 0
        self.scroll_target_velocity = 0

        self.zoom_step           = Constants.current_settings["zoom_step"]
        self.scroll_acceleration = Constants.current_settings["scroll_acceleration"]

    def process_wheel_event(self, event: QEvent) -> None:
        delta     = event.angleDelta().y()
        modifiers = event.modifiers()

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self.stop_smooth_scroll()
            self.conductor.scale_view(self.zoom_step if delta > 0 else -self.zoom_step)

        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            v_bar = self.conductor.verticalScrollBar()
            v_bar.setValue(v_bar.value() - delta)

        else:
            if self.conductor.playback_manager.is_playing:
                return event.accept()

            self.scroll_target_velocity += -delta * self.scroll_acceleration
            self.conductor.start_scroll_tick()

        event.accept()

    def tick(self) -> bool:
        if self.conductor.scale_anim_active:
            self.scroll_velocity        = 0
            self.scroll_target_velocity = 0
            return True

        self.scroll_velocity += (self.scroll_target_velocity - self.scroll_velocity) * 0.2

        h_bar = self.conductor.horizontalScrollBar()
        h_bar.setValue(int(h_bar.value() + self.scroll_velocity))

        self.scroll_target_velocity *= 0.9

        if abs(self.scroll_velocity) < 0.2 and abs(self.scroll_target_velocity) < 0.2:
            self.scroll_velocity        = 0
            self.scroll_target_velocity = 0
            return True

        return False

    def stop_smooth_scroll(self) -> None:
        self.scroll_velocity        = 0
        self.scroll_target_velocity = 0

class GlyphController(QObject):
    elements_changed       = pyqtSignal()
    glyph_changed          = pyqtSignal(int)

    glyph_spawned          = pyqtSignal()
    glyph_moved_or_resized = pyqtSignal()
    glyph_deleted          = pyqtSignal()

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__()

        self.conductor   = conductor
        self.composition = conductor.composition

        self.copied_data:             list[dict]                    = []
        self.glyph_items:             dict[int, Widgets.GlyphItem]  = {}
        self.drag_session:            dict[Widgets.GlyphItem, dict] = {}

        self.expanded_stack:          frozenset[int] | None         = None

        self.expand_animations:       list[QPropertyAnimation]      = []

        self.collapse_animations:     list[QPropertyAnimation]      = []
        self.collapse_refresh_timer:  QTimer | None                 = None

        self.track_map = {
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

        self.undo_stack        = []
        self.redo_stack        = []
        self.is_processing     = False
        self.max_history       = 1000
        self.temp_before_state = {}

    def get_selected_glyph_items(self) -> list[Widgets.GlyphItem]:
        valid_items = set(self.glyph_items.values())

        return [
            item for item in self.conductor.scene.selectedItems()
            if item in valid_items
        ]

    def get_selected_glyph_ids(self) -> list[int]:
        return [item.glyph_id for item in self.get_selected_glyph_items()]
    
    def select_all_on_same_track(self) -> None:
        selected = self.get_selected_glyph_items()

        if not selected:
            return

        target_track = selected[0].track

        for item in self.glyph_items.values():
            item.setSelected(item.track == target_track)

    def modify_selected_glyphs(self, key: str, value: object) -> None:
        selected_glyph_ids = self.get_selected_glyph_ids()

        if not selected_glyph_ids:
            return

        before_state = {
            gid: copy.deepcopy(data)
            for gid in selected_glyph_ids
            if (data := self.composition.get_glyph(gid))
        }

        after_state = {
            gid: {**copy.deepcopy(data), key: value}
            for gid, data in before_state.items()
            if data.get(key) != value
        }

        if not after_state:
            return

        self.push_action(Actions.ActionModify(self, before_state, after_state))
        self.composition.update_bunch_of_glyphs(after_state)
        self.update_glyphs(after_state)
        self.elements_changed.emit()

    def adjust_selected_brightness(self, delta: int) -> None:
        selected_glyph_identifiers = self.get_selected_glyph_ids()

        if not selected_glyph_identifiers:
            return

        before_state = {}
        after_state  = {}

        self.composition.start_batching()

        for glyph_identifier in selected_glyph_identifiers:
            glyph_data = self.composition.get_glyph(glyph_identifier)

            if not glyph_data:
                continue

            current_brightness = glyph_data["brightness"]
            new_brightness     = max(0, min(100, current_brightness + delta))

            if new_brightness == current_brightness:
                continue

            before_state[glyph_identifier] = copy.deepcopy(glyph_data)
            after_state[glyph_identifier]  = {**copy.deepcopy(glyph_data), "brightness": new_brightness}

        if after_state:
            self.push_action(Actions.ActionModify(self, before_state, after_state))
            self.composition.update_bunch_of_glyphs(after_state)
            self.update_glyphs(after_state)
            self.elements_changed.emit()

            target_sound = f"Glyphs/Brightness/{'Lower' if delta < 0 else 'Higher'}"
            Player.ui_player.play_sound(target_sound)

            if len(after_state) == 1:
                target_glyph_id = next(iter(after_state))
                glyph_item      = self.glyph_items[target_glyph_id]

                self.conductor.tooltip.show_tooltip_at(
                    f"Brightness: {after_state[target_glyph_id]['brightness']}%",
                    glyph_item
                )

        self.composition.stop_batching()

    def push_action(
        self,
        action: Actions.ActionAdd    |
                Actions.ActionModify |
                Actions.ActionDelete |
                Actions.EditFadeKeyframesCommand
    ) -> None:
        
        if isinstance(action, Actions.ActionModify) and action.glyphs_before_modify == action.glyphs_after_modify:
            return

        self.undo_stack.append(action)
        self.redo_stack.clear()

        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

    def undo(self) -> None:
        if not self.undo_stack:
            self.conductor.tooltip.show_tooltip_at("Nothing to undo.", plan_hide=True)
            return

        if self.is_processing:
            return

        self.is_processing = True

        try:
            action = self.undo_stack.pop()
            action.undo()
            self.redo_stack.append(action)
            self.elements_changed.emit()

            detail = action.get_description()
            self.conductor.tooltip.show_tooltip_at(f"Undo {detail}", plan_hide=True)

        finally:
            self.is_processing = False

    def redo(self) -> None:
        if not self.redo_stack:
            self.conductor.tooltip.show_tooltip_at("Nothing to redo.", plan_hide=True)
            return

        if self.is_processing:
            return

        self.is_processing = True

        try:
            action = self.redo_stack.pop()
            action.redo()
            self.undo_stack.append(action)

            detail = action.get_description()
            self.conductor.tooltip.show_tooltip_at(f"Redo {detail}", plan_hide=True)

        finally:
            self.is_processing = False

    def update_glyphs(self, glyph_ids: dict[int, dict] | None = None) -> None:
        if glyph_ids:
            for gid in glyph_ids:
                self.glyph_items[gid].update_geometry()
            return

        for glyph in self.glyph_items.values():
            glyph.update_geometry()

    def clear_glyphs(self) -> None:
        for item in self.glyph_items.values():
            item.remove_glyph(False)

        self.glyph_items.clear()
        self.elements_changed.emit()

    def delete_selected_glyphs(self) -> None:
        self.delete_glyphs(self.get_selected_glyph_ids())

    def delete_glyphs(self, glyph_ids: list[int], push_undo: bool = True) -> None:
        if not glyph_ids:
            return

        deleted_batch = {
            gid: copy.deepcopy(data)
            for gid in glyph_ids
            if (data := self.composition.get_glyph(gid))
        }

        deleted_items = [self.glyph_items.pop(gid, None) for gid in glyph_ids]
        deleted_items = [item for item in deleted_items if item]

        for item in deleted_items:
            item.remove_glyph()

        self.composition.delete_bunch_of_glyphs(glyph_ids)

        if push_undo and deleted_batch:
            self.push_action(Actions.ActionDelete(self, deleted_batch))

        self.glyph_deleted.emit()
        self.elements_changed.emit()
        self.refresh_stack_indicators()

    def spawn_glyph_on_track(self, track_index: int) -> None:
        if int(track_index) > self.composition.track_number:
            return

        current_playhead_ms = int(self.conductor.get_playhead_position_ms())
        remaining_time      = max(0, Player.player.duration_ms - current_playhead_ms)
        actual_duration     = min(self.composition.duration_ms, remaining_time)

        if actual_duration <= 0:
            return
        
        if self.conductor.playback_manager.is_playing:
            current_playhead_ms -= 110

        new_id, new_data = self.composition.new_glyph(track_index, current_playhead_ms, actual_duration)

        self.create_glyph_items([new_id])
        self.push_action(Actions.ActionAdd(self, {new_id: new_data}))

        self.composition.syncer.pulse_track(track_index)
        
        self.glyph_spawned.emit()
        self.elements_changed.emit()

    def copy_glyphs(self) -> None:
        selected_glyph_items = self.get_selected_glyph_items()
        self.copied_data     = []

        for item in selected_glyph_items:
            if data := self.composition.get_glyph(item.glyph_id):
                self.copied_data.append(copy.deepcopy(data))

    def cut_glyphs(self) -> None:
        self.copy_glyphs()
        self.delete_selected_glyphs()

    def paste_glyphs(self) -> None:
        if not self.copied_data or self.is_processing:
            return

        self.is_processing = True

        try:
            current_playhead_ms = self.conductor.get_playhead_position_ms()
            copied_start_ms     = min(d['start'] for d in self.copied_data)
            time_offset         = int(current_playhead_ms - copied_start_ms)
            audio_duration_ms   = self.conductor.playback_manager.duration_ms

            self.conductor.scene.clearSelection()

            new_added_glyphs = {}
            new_ids          = []

            self.composition.start_batching()

            for glyph_data in self.copied_data:
                res = self.composition.copy_glyph(glyph_data, time_offset, audio_duration_ms)

                if (new_id := res[0]) is not None:
                    new_ids.append(new_id)
                    new_added_glyphs[new_id] = res[1]
            
            self.composition.stop_batching()

            if not new_ids:
                return

            self.create_glyph_items(new_ids, reset_selection=False)
            self.push_action(Actions.ActionAdd(self, new_added_glyphs))
            self.elements_changed.emit()

        finally:
            self.is_processing = False

    def create_glyph_items(
        self,
        glyphs_id:       list[int],
        reset_selection: bool = True,
        set_selected:    bool = True,
        animate_spawn:   bool = True
    ) -> None:
        
        for glyph_id in glyphs_id:
            item = Widgets.GlyphItem(glyph_id, self.conductor, animate_spawn)

            self.glyph_items[glyph_id] = item
            self.conductor.scene.addItem(item)

            if reset_selection:
                self.conductor.scene.clearSelection()

            item.setSelected(set_selected)
            item.update()
        
        QTimer.singleShot(0, self.refresh_stack_indicators)

    def start_drag(self) -> None:
        self.drag_session      = {}
        self.temp_before_state = {}
        selected_glyph_items   = self.get_selected_glyph_items()

        for item in selected_glyph_items:
            self.drag_session[item] = {
                'start':    item.start_ms,
                'duration': item.duration_ms,
            }

            if data := self.composition.get_glyph(item.glyph_id):
                self.temp_before_state[item.glyph_id] = copy.deepcopy(data)

    def update_drag_state(
        self,
        delta_ms:        float,
        mode:            str,
        active_item_ref: Widgets.GlyphItem,
    ) -> None:
        
        audio_duration = self.conductor.playback_manager.duration_ms
        popup_text     = ""

        self.composition.start_batching()

        clamp = lambda val, min_v, max_v: int(max(min_v, min(val, max_v)))

        for item, initial in self.drag_session.items():
            if (target_data := self.composition.get_glyph(item.glyph_id)) is None:
                continue

            initial_start, initial_dur = initial['start'], initial['duration']

            if mode == 'move':
                new_start            = clamp(initial_start + delta_ms, 0, audio_duration - initial_dur)
                target_data["start"] = new_start
                value_to_show        = new_start

            elif mode == 'resize_right':
                new_dur                  = clamp(initial_dur + delta_ms, 10, audio_duration - initial_start)
                target_data["duration"]  = new_dur
                value_to_show            = new_dur

            elif mode == 'resize_left':
                orig_end      = initial_start + initial_dur
                new_start     = clamp(initial_start + delta_ms, 0, orig_end - 10)
                new_dur       = orig_end - new_start
                value_to_show = new_dur

                target_data.update({"start": new_start, "duration": new_dur})

            if item == active_item_ref:
                popup_text = f"{value_to_show} ms"

            item.update_geometry()
            self.composition.glyphs.mark_dirty(item.glyph_id)

        if popup_text:
            self.conductor.tooltip.show_tooltip_at(popup_text, active_item_ref)

    def end_drag(self) -> None:
        if not self.drag_session:
            return

        after_state = {
            gid: copy.deepcopy(data)
            for item in self.drag_session
            if (data := self.composition.get_glyph(gid := item.glyph_id))
        }
        
        actually_moved = any(
            after_state.get(gid) != self.temp_before_state.get(gid)
            for gid in after_state
        )

        if actually_moved:
            self.push_action(Actions.ActionModify(self, self.temp_before_state, after_state))

        self.composition.stop_batching()

        self.drag_session      = {}
        self.temp_before_state = {}

        self.glyph_moved_or_resized.emit()

    def commit_fade_keyframes(self, glyph_id: int, new_keyframes: list[tuple[float, int]]) -> None:
        original_glyph = self.conductor.composition.get_glyph(glyph_id)

        if original_glyph is None:
            return

        effect = original_glyph.get("effect", {})

        if effect.get("name") != "Fade":
            return

        settings      = effect["settings"]
        old_keyframes = settings["keyframes"]
        new_glyph     = copy.deepcopy(original_glyph)
        new_settings  = {**settings, "keyframes": new_keyframes}

        new_glyph = GlyphEffects.apply_visual_effect(new_glyph, "Fade", new_settings)
        self.conductor.composition.replace_glyph(glyph_id, new_glyph)

        self.push_action(
            Actions.EditFadeKeyframesCommand(
                self.conductor.composition,
                glyph_id,
                old_keyframes,
                new_keyframes,
            )
        )
    
    def select_all_glyphs(self) -> None:
        for item in self.glyph_items.values():
            item.setSelected(True)
    
    def get_overlapping_group(self, glyph_id: int) -> list[int]:
        data = self.composition.get_glyph(glyph_id)
    
        if not data:
            return [glyph_id]
    
        track = data['track']
        start = data['start']
        end   = start + data['duration']
        group = [glyph_id]
    
        for gid in self.glyph_items:
            if gid == glyph_id:
                continue
            
            other = self.composition.get_glyph(gid)
    
            if not other or other['track'] != track:
                continue
            
            other_start = other['start']
            other_end   = other_start + other['duration']
    
            if other_start < end and other_end > start:
                group.append(gid)
    
        return group
    
    def refresh_stack_indicators(self) -> None:
        if self.expanded_stack:
            return

        by_track: dict[int, list[tuple[int, int, int]]] = {}
        
        for gid in self.glyph_items:
            data = self.composition.get_glyph(gid)
            
            if not data:
                continue
            
            start = data['start']
            by_track.setdefault(data['track'], []).append((start, start + data['duration'], gid))

        stacks: dict[int, int] = {gid: 0 for gid in self.glyph_items}

        for entries in by_track.values():
            entries.sort()
            count = len(entries)
            
            for i in range(count):
                start_a, end_a, gid_a = entries[i]
                
                for j in range(i + 1, count):
                    start_b, _, gid_b = entries[j]
                    
                    if start_b >= end_a:
                        break
                    
                    stacks[gid_a] += 1
                    stacks[gid_b] += 1

        for gid, item in self.glyph_items.items():
            depth = stacks.get(gid, 0)
            item.set_stack_depth(depth)
    
    def stop_running_stack_animations(self) -> None:
        for animation in self.expand_animations:
            animation.stop()
        
        self.expand_animations = []

        for animation in self.collapse_animations:
            animation.stop()
        
        self.collapse_animations = []

        if self.collapse_refresh_timer:
            self.collapse_refresh_timer.stop()
            self.collapse_refresh_timer = None

    def sort_stack_group(self, group: list[int]) -> None:
        def sort_key(gid: int) -> tuple:
            glyph = self.composition.get_glyph(gid)
            return (glyph["start"] if glyph else 0, gid)

        group.sort(key=sort_key)

    def calculate_expansion_params(
        self,
        group_size: int,
        base_y:     float,
        box_h:      float
    ) -> tuple[float, float]:

        base_step = Styles.Metrics.Tracks.BoxHeight + Styles.Metrics.Tracks.BoxSpacing + 6

        scene = self.conductor.scene
        scene_rect = scene.sceneRect()

        BOUNDARY_MARGIN = 15

        space_below = max(0.0, scene_rect.bottom() - (base_y + box_h) - BOUNDARY_MARGIN)
        space_above = max(0.0, base_y - scene_rect.top() - BOUNDARY_MARGIN)

        if space_below >= space_above:
            direction = 1.0
            available_span = space_below
        
        else:
            direction = -1.0
            available_span = space_above

        if group_size > 1:
            max_step_by_space = available_span / float(group_size - 1) if available_span > 0 else 0.0
            step = min(base_step, max_step_by_space) if max_step_by_space > 0 else 0.0
        
        else:
            step = 0.0

        return direction, step

    def animate_stack_items(
        self,
        group:      list[int],
        step:       float,
        direction:  float,
        group_size: int
    ) -> None:
        
        PIXELS_PER_SECOND = 500.0
        MIN_DURATION = 180

        for index, gid in enumerate(group):
            item = self.glyph_items.get(gid)
            
            if not item:
                continue

            target_offset  = direction * float(index * step)
            current_offset = float(item.property("stackYOffset") or 0.0)
            distance       = abs(target_offset - current_offset)

            duration = max(MIN_DURATION, int((distance / PIXELS_PER_SECOND) * 1000.0))

            item.setZValue(float(group_size - index))

            animation = QPropertyAnimation(item, b"stackYOffset")
            animation.setDuration(duration)
            animation.setStartValue(current_offset)
            animation.setEndValue(target_offset)
            animation.setEasingCurve(QEasingCurve.Type.OutExpo)
            animation.setParent(item)

            self.expand_animations.append(animation)
            animation.start()

    def expand_stack(self, glyph_id: int) -> None:
        group = self.get_overlapping_group(glyph_id)

        if len(group) <= 1:
            return

        self.stop_running_stack_animations()

        self.sort_stack_group(group)
        self.expanded_stack = frozenset(group)

        group_size = len(group)
        
        if group_size <= 1:
            return

        first_item = self.glyph_items.get(group[0])
        
        if first_item is None:
            return

        base_y = float(first_item.fixed_y)
        box_h = float(Styles.Metrics.Tracks.BoxHeight)

        direction, step = self.calculate_expansion_params(group_size, base_y, box_h)

        self.animate_stack_items(group, direction, step, group_size)

        Player.ui_player.play_sound("Glyphs/Stack/Expand")
    
    def collapse_stack_items(self, group: list[int]) -> None:
        COLLAPSE_DURATION = 220

        for gid in group:
            item = self.glyph_items.get(gid)

            if not item:
                continue

            animation = QPropertyAnimation(item, b"stackYOffset")
            animation.setDuration(COLLAPSE_DURATION)
            animation.setEndValue(0.0)
            animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            animation.setParent(item)

            self.collapse_animations.append(animation)
            animation.start()

            item.setZValue(0.0)

    def collapse_stack(self) -> None:
        if not self.expanded_stack:
            return

        self.stop_running_stack_animations()

        group = list(self.expanded_stack)
        self.expanded_stack = None

        self.collapse_stack_items(group)

        QTimer.singleShot(230, self.refresh_stack_indicators)

        Player.ui_player.play_sound("Glyphs/Stack/Collapse")

class AutoScroller:
    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        self.conductor          = conductor
        self.damping            = 0.90
        self.max_speed          = 30.0
        self.scroll_margin      = 100
        self.acceleration_curve = 2.0

        self.velocity           = 0.0
        self.is_dragging        = False
        self.position           = float(self.conductor.horizontalScrollBar().value())

        self.rewind_sound    = None

    def process_pos(self, global_pos: QPoint) -> None:
        if self.conductor.playback_manager.is_playing:
            return

        view_pos        = self.conductor.viewport().mapFromGlobal(global_pos)
        viewport_w      = self.conductor.viewport().width()
        target_velocity = 0.0

        if view_pos.x() < self.scroll_margin:
            ratio = max(0.0, min(1.0, (self.scroll_margin - view_pos.x()) / self.scroll_margin))
            target_velocity = -self.max_speed * (ratio ** self.acceleration_curve)

        elif view_pos.x() > viewport_w - self.scroll_margin:
            dist_from_right = view_pos.x() - (viewport_w - self.scroll_margin)
            ratio           = max(0.0, min(1.0, dist_from_right / self.scroll_margin))
            target_velocity = self.max_speed * (ratio ** self.acceleration_curve)

        h_bar    = self.conductor.horizontalScrollBar()
        at_limit = (
            (target_velocity < -0.1 and h_bar.value() <= h_bar.minimum()) or
            (target_velocity > 0.1  and h_bar.value() >= h_bar.maximum())
        )

        self.velocity = target_velocity
        self.position = float(h_bar.value())

        if abs(self.velocity) > 0.1 and not at_limit:
            sound_speed = min(max(abs(self.velocity / 14), 0.5), 1.7)

            if not self.is_dragging:
                Player.ui_player.play_sound("Rewind/Start")
                self.rewind_sound = Player.ui_player.play_sound("Rewind/Rewind2", True, sound_speed)
                self.is_dragging  = True
            
            elif self.rewind_sound:
                self.rewind_sound.set_speed(sound_speed)

            self.conductor.start_scroll_tick()
        
        else:
            if self.is_dragging:
                self.stop_drag(silent = at_limit)

    def stop_drag(self, silent: bool = False) -> None:
        self.is_dragging = False

        if self.rewind_sound:
            if not silent:
                Player.ui_player.play_sound("Rewind/Stop")

            self.rewind_sound.stop()
            self.rewind_sound = None

    def tick(self) -> bool:
        if self.conductor.playback_manager.is_playing:
            return True

        if not self.is_dragging and abs(self.velocity) < 0.1:
            self.velocity = 0.0
            return True

        h_bar          = self.conductor.horizontalScrollBar()
        self.position += self.velocity
        self.position  = max(h_bar.minimum(), min(h_bar.maximum(), self.position))

        h_bar.setValue(int(self.position))

        if self.is_dragging:
            return self.velocity == 0

        self.velocity *= self.damping

        if abs(self.velocity) > 0.5:
            return False

        self.velocity = 0
        return True

class MouseController:
    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        self.conductor            = conductor
        self.is_marquee_selecting = False
        self.auto_scroller        = AutoScroller(conductor)

        self.playback_manager: Player.PlaybackManager = conductor.playback_manager

    def stop_auto_scroll_drag(self) -> None:
        self.auto_scroller.stop_drag()

    def start_marquee(self, event: QMouseEvent) -> None:
        self.conductor.marquee_item.start_marquee(self.conductor.mapToScene(event.pos()))
        self.is_marquee_selecting = True

    def end_marquee(self, event: QMouseEvent) -> None:
        if not self.is_marquee_selecting:
            return

        self.conductor.marquee_item.end_marquee()
        self.is_marquee_selecting = False
        self.stop_auto_scroll_drag()

    def marquee_tick(self, event: QMouseEvent) -> None:
        if not self.is_marquee_selecting:
            return

        self.conductor.marquee_item.update_end_point(
            self.conductor.mapToScene(event.pos()),
            animate = (
                not self.playback_manager.is_playing and
                not self.auto_scroller.is_dragging
            )
        )

        self.auto_scroller.process_pos(self.conductor.viewport().mapToGlobal(event.pos()))

    def handle_ruler_press(self, event: QMouseEvent) -> None:
        if self.playback_manager.is_playing:
            return

        new_x = self.conductor.mapToScene(event.pos()).x()

        if self.conductor.get_playhead_position_px() != new_x:
            self.conductor.set_playhead_position_px(new_x, True)

    def handle_ruler_hover(self, event: QMouseEvent) -> None:
        y              = event.position().y()
        playhead_hover = self.conductor.playhead_hover
        waveform_end   = Styles.Metrics.Waveform.Height + Styles.Metrics.Tracks.RulerHeight

        if waveform_end > y > 0:
            if not playhead_hover.isVisible():
                playhead_hover.show()

            playhead_hover.setPos(self.conductor.mapToScene(event.pos()).x(), 0)

        else:
            if playhead_hover.isVisible():
                playhead_hover.hide()

    def force_mouse_update(self) -> None:
        global_pos = QCursor.pos()
        local_pos  = self.conductor.viewport().mapFromGlobal(global_pos)

        fake_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(local_pos),
            QPointF(global_pos),
            Qt.MouseButton.NoButton,
            QApplication.mouseButtons(),
            QApplication.keyboardModifiers()
        )

        self.process_mouse_move_event(fake_event)

    def process_mouse_press_event(self, event: QMouseEvent) -> None:
        ruler_area = QRectF(
            0, 0,
            self.conductor.width(),
            Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height,
        )

        if ruler_area.contains(event.position()):
            self.handle_ruler_press(event)
            return event.accept()

        scene_pos = self.conductor.mapToScene(event.pos())

        if self.conductor.scene.itemAt(scene_pos, self.conductor.transform()):
            return event.ignore()

        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.conductor.scene.clearSelection()

        self.start_marquee(event)
        event.accept()

    def process_mouse_move_event(self, event: QMouseEvent) -> None:
        self.marquee_tick(event)
        self.handle_ruler_hover(event)

    def process_mouse_release_event(self, event: QMouseEvent) -> None:
        self.end_marquee(event)

    def process_mouse_leave_event(self, event: QMouseEvent) -> None:
        self.conductor.playhead_hover.hide()