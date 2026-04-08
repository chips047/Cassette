from __future__ import annotations

import copy

from functools import partial

from PyQt5.QtGui import (
    QCursor,
    QMouseEvent,
    QKeySequence
)

from PyQt5.QtCore import (
    Qt,
    QEvent,
    QPoint,
    QRectF,
    QObject,
    pyqtSignal
)

from PyQt5.QtWidgets import (
    QShortcut,
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

        self.move_increment = Constants.CURRENT_SETTINGS["arrow_increment"]
        self.shortcuts      = []

        self.base_shortcuts = [
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Z,                                      self.glyph_controller.undo),
            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier + Qt.Key.Key_Z, self.glyph_controller.redo),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Y,                                      self.glyph_controller.redo),

            (Qt.Key.Key_Space, self.handle_playback_toggle),
            (Qt.Key.Key_Left,  lambda: self.handle_manual_playhead_move(-self.move_increment)),
            (Qt.Key.Key_Right, lambda: self.handle_manual_playhead_move(self.move_increment)),

            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_C, self.glyph_controller.copy_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_V, self.glyph_controller.paste_glyphs),
            (Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_X, self.glyph_controller.cut_glyphs),

            (Qt.Key.Key_Delete,    self.glyph_controller.delete_selected_glyphs),
            (Qt.Key.Key_Backspace, self.glyph_controller.delete_selected_glyphs),

            (Qt.Key.Key_S, self.compositor.playspeed_button.next_state),
            (Qt.Key.Key_B, self.open_brightness_editor),
            (Qt.Key.Key_D, self.open_duration_editor),

            (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier + Qt.Key.Key_E, self.compositor.open_playground_window)
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

        current_x = self.conductor.get_playhead_position_px()
        target_x  = max(0, min(self.conductor.total_content_width, current_x + delta_px))

        self.conductor.set_playhead_position_px(target_x)

    def open_brightness_editor(self) -> None:
        if not self.ensure_selection():
            return

        self.conductor.brightness_control_popup()

    def open_duration_editor(self) -> None:
        if not self.ensure_selection():
            return

        self.conductor.duration_control_popup()

    def ensure_selection(self) -> bool:
        if not self.conductor.scene.selectedItems():
            self.conductor.tooltip.show_tooltip_at("No glyphs selected.", plan_hide=True)
            return False

        return True

    def cleanup_shortcuts(self) -> None:
        for shortcut in self.shortcuts:
            shortcut.activated.disconnect()
            shortcut.deleteLater()

        self.shortcuts = []

class WheelController:
    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        self.conductor = conductor

        self.scroll_velocity        = 0
        self.scroll_target_velocity = 0

        self.zoom_step           = Constants.CURRENT_SETTINGS["zoom_step"]
        self.scroll_acceleration = Constants.CURRENT_SETTINGS["scroll_acceleration"]

        self.scroll_timer = Basic.Timer(
            Constants.FPS_120,
            self.update_smooth_scroll,
            parent = conductor
        )

    def process_wheel_event(self, event: QEvent) -> None:
        delta     = event.angleDelta().y()
        modifiers = event.modifiers()

        if modifiers & Qt.ControlModifier:
            self.conductor.scale_view(self.zoom_step if delta > 0 else -self.zoom_step)

        elif modifiers & Qt.ShiftModifier:
            v_bar = self.conductor.verticalScrollBar()
            v_bar.setValue(v_bar.value() - delta)

        else:
            if self.conductor.playback_manager.is_playing:
                return event.accept()

            self.scroll_target_velocity += -delta * self.scroll_acceleration

            if not self.scroll_timer.isActive():
                self.scroll_timer.start()

        event.accept()

    def update_smooth_scroll(self) -> None:
        self.scroll_velocity += (self.scroll_target_velocity - self.scroll_velocity) * 0.2

        h_bar = self.conductor.horizontalScrollBar()
        h_bar.setValue(int(h_bar.value() + self.scroll_velocity))

        self.scroll_target_velocity *= 0.9

        if abs(self.scroll_velocity) < 0.2 and abs(self.scroll_target_velocity) < 0.2:
            self.scroll_timer.stop()
            self.scroll_velocity        = 0
            self.scroll_target_velocity = 0

class GlyphController(QObject):
    elements_changed = pyqtSignal()
    glyph_changed    = pyqtSignal(int)

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__()

        self.conductor   = conductor
        self.composition = conductor.composition

        self.copied_data:  list[dict]                    = []
        self.glyph_items:  dict[int, Widgets.GlyphItem]  = {}
        self.drag_session: dict[Widgets.GlyphItem, dict] = {}

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
            Qt.Key.Key_Minus: "11",
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

        self.elements_changed.emit()

    def spawn_glyph_on_track(self, track_index: int) -> None:
        if int(track_index) > self.composition.track_number:
            return

        current_playhead_ms = int(self.conductor.get_playhead_position_ms())
        remaining_time      = max(0, Player.player.duration_ms - current_playhead_ms)
        actual_duration     = min(self.composition.duration_ms, remaining_time)

        if actual_duration <= 0:
            return

        new_id, new_data = self.composition.new_glyph(track_index, current_playhead_ms, actual_duration)

        self.create_glyph_items([new_id])
        self.push_action(Actions.ActionAdd(self, {new_id: new_data}))
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
        animate_spawn:   bool = True,
    ) -> None:
        
        for glyph_id in glyphs_id:
            item = Widgets.GlyphItem(glyph_id, self.conductor, animate_spawn)

            self.glyph_items[glyph_id] = item
            self.conductor.scene.addItem(item)

            if reset_selection:
                self.conductor.scene.clearSelection()

            item.setSelected(set_selected)
            item.update()

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

        self.timer = Basic.Timer(
            Constants.FPS_120,
            self.update,
            parent = conductor
        )

    def process_pos(self, global_pos: QPoint) -> None:
        if self.conductor.playback_manager.is_playing:
            return
        
        sound_speed = min(max(abs(self.velocity / 14), 0.5), 1.7)

        if not self.is_dragging:
            self.rewind_sound = Player.ui_player.play_sound("Rewind2", True, sound_speed)
            self.is_dragging = True
        
        else:
            if self.rewind_sound:
                self.rewind_sound.set_speed(sound_speed)

        self.position   = float(self.conductor.horizontalScrollBar().value())
        view_pos        = self.conductor.mapFromGlobal(global_pos)
        viewport_w      = self.conductor.viewport().width()
        target_velocity = 0.0

        if view_pos.x() < self.scroll_margin:
            ratio = (self.scroll_margin - view_pos.x()) / self.scroll_margin
            ratio = max(0.0, min(1.0, ratio))

            target_velocity = -self.max_speed * (ratio ** self.acceleration_curve)

        elif view_pos.x() > viewport_w - self.scroll_margin:
            dist_from_right = view_pos.x() - (viewport_w - self.scroll_margin)
            ratio           = max(0.0, min(1.0, dist_from_right / self.scroll_margin))

            target_velocity = self.max_speed * (ratio ** self.acceleration_curve)

        self.velocity    = target_velocity
        self.is_dragging = True

        if abs(self.velocity) > 0.1 and not self.timer.isActive():
            self.timer.start()

    def stop_drag(self) -> None:
        self.is_dragging = False

        if self.rewind_sound:
            self.rewind_sound.stop()
            self.rewind_sound = None

    def update(self) -> None:
        if self.conductor.playback_manager.is_playing:
            return

        h_bar          = self.conductor.horizontalScrollBar()
        self.position += self.velocity
        self.position  = max(h_bar.minimum(), min(h_bar.maximum(), self.position))
        
        h_bar.setValue(int(self.position))

        if self.is_dragging:
            if self.velocity != 0:
                return

            self.timer.stop()

        else:
            self.velocity *= self.damping

            if abs(self.velocity) > 0.5:
                return

            self.velocity = 0
            self.timer.stop()

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

        self.conductor.marquee_item.update_end_point(self.conductor.mapToScene(event.pos()))
        self.auto_scroller.process_pos(event.globalPos())

    def handle_ruler_press(self, event: QMouseEvent) -> None:
        if self.playback_manager.is_playing:
            return

        new_x = self.conductor.mapToScene(event.pos()).x()

        if self.conductor.get_playhead_position_px() != new_x:
            self.conductor.set_playhead_position_px(new_x)

    def handle_ruler_hover(self, event: QMouseEvent) -> None:
        y              = event.y()
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
            QEvent.MouseMove,
            local_pos,
            global_pos,
            Qt.NoButton,
            QApplication.mouseButtons(),
            QApplication.keyboardModifiers(),
        )

        self.process_mouse_move_event(fake_event)

    def process_mouse_press_event(self, event: QMouseEvent) -> None:
        ruler_area = QRectF(
            0, 0,
            self.conductor.width(),
            Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height,
        )

        if ruler_area.contains(event.pos()):
            self.handle_ruler_press(event)
            return event.accept()

        scene_pos = self.conductor.mapToScene(event.pos())

        if self.conductor.scene.itemAt(scene_pos, self.conductor.transform()):
            return event.ignore()

        if not (event.modifiers() & Qt.ControlModifier):
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