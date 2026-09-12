from __future__ import annotations

import copy

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QObject,
    pyqtSignal
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
    Timing,
    Widgets,
    Windows
)

from System.Interface.Animation import LoomEngine
from .OcclusionController       import OcclusionController

from .. import (
    Actions,
    Timeline
)

class GlyphController(QObject):
    elements_changed       = pyqtSignal()
    glyph_changed          = pyqtSignal(int)
    glyph_spawned          = pyqtSignal()
    glyph_moved_or_resized = pyqtSignal(str)
    glyph_drag_progress    = pyqtSignal(str, float)
    glyph_deleted          = pyqtSignal()
    glyph_property_changed = pyqtSignal(str)
    glyph_keyframe_edited  = pyqtSignal()
    drag_state_changed     = pyqtSignal(bool)

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__()

        self.conductor   = conductor
        self.composition = conductor.composition

        self.copied_data     = []
        self.glyph_items     = {}
        self.drag_session    = {}
        self.expanded_stack  = None

        self.expand_animations      = []
        self.collapse_animations    = []
        self.collapse_refresh_timer = None

        self.hovered_item = None
        self.hover_timer  = Timing.Timer(
            1000,
            self.on_hover_timeout,
            single_shot = True,
            parent      = self
        )

        self.occlusion_controller = OcclusionController()

        self.track_map = {
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

        self.undo_stack        = []
        self.redo_stack        = []
        self.is_processing     = False
        self.max_history       = 1000
        self.temp_before_state = {}
        self.current_drag_mode = None

    # HoverManagement

    def set_hovered_item(self, item: object) -> None:
        self.hovered_item = item
        self.hover_timer.start()

    def clear_hovered_item(self) -> None:
        self.hovered_item = None
        self.hover_timer.stop()

    def on_hover_timeout(self) -> None:
        if not self.hovered_item:
            return

        self.conductor.tooltip.show_hover_tooltip(self.hovered_item)

    # SelectionManagement

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

    def select_all_glyphs(self) -> None:
        for item in self.glyph_items.values():
            item.setSelected(True)

    # ModificationAndHistory

    def modify_selected_glyphs(
            self,
            property_name:  str,
            property_value: object
        ) -> None:

        selected_glyph_ids = self.get_selected_glyph_ids()

        if not selected_glyph_ids:
            return

        before_state = {
            glyph_id: copy.deepcopy(data)
            for glyph_id in selected_glyph_ids
            if (data := self.composition.get_glyph(glyph_id)) is not None
        }

        after_state = {
            glyph_id: {**copy.deepcopy(data), property_name: property_value}
            for glyph_id, data in before_state.items()
            if data.get(property_name) != property_value
        }

        if not after_state:
            return

        self.composition.start_batching()

        try:
            self.push_action(Actions.ActionModify(self, before_state, after_state))
            self.composition.update_bunch_of_glyphs(after_state)
            self.update_glyphs(after_state)

            self.elements_changed.emit()
            self.glyph_property_changed.emit(property_name)

            if property_name in ("start", "duration", "track"):
                self.refresh_all_occlusion()

        finally:
            self.composition.stop_batching()

    def apply_effect_to_glyphs(
            self,
            effect_name:  str,
            settings:     dict,
            selected_ids: list[int]
        ) -> None:

        before_state: dict[int, dict] = {}
        after_state:  dict[int, dict] = {}

        for glyph_id in selected_ids:
            element = self.composition.get_glyph(glyph_id)

            if not element:
                continue

            before_state[glyph_id] = copy.deepcopy(element)
            after_state[glyph_id]  = GlyphEffects.apply_visual_effect(element, effect_name, settings)

        if not after_state:
            return

        self.composition.update_bunch_of_glyphs(after_state)

        self.push_action(
            Actions.ActionModify(
                self,
                before_state,
                after_state
            )
        )

        self.update_glyphs(selected_ids)

    def apply_segments_to_glyphs(
            self,
            selected_ids: list[int],
            segments:     list[bool]
        ) -> None:

        original_glyphs = {
            glyph_id: self.composition.get_glyph(glyph_id)
            for glyph_id in selected_ids
        }

        turned_on     = [index for index, segment in enumerate(segments) if segment]
        all_turned_on = all(segments)

        before_state = {
            glyph_id: copy.deepcopy(original_glyphs[glyph_id])
            for glyph_id in selected_ids
        }
        after_state: dict[int, dict] = {}

        for glyph_id in selected_ids:
            new_glyph = copy.deepcopy(original_glyphs[glyph_id])

            if all_turned_on:
                new_glyph.pop("segments", None)

            else:
                new_glyph["segments"] = turned_on

            after_state[glyph_id] = new_glyph

        first_id      = selected_ids[0]
        first_glyph   = original_glyphs[first_id]
        effect_data   = first_glyph.get("effect")
        effect_name   = effect_data.get("name") if effect_data else None
        effect_config = GlyphEffects.EffectsConfig.get(effect_name, {}) if effect_name else {}

        if effect_name and not effect_config.get("supports_segmentation", True):
            Windows.ErrorWindow(
                "Effect has been reset",
                "Heads up: custom segmentation doesn't work with applied effect, so we reset the effect."
            ).exec()

            for glyph_id in selected_ids:
                after_state[glyph_id].pop("effect", None)

        modified_before = {
            glyph_id: before_state[glyph_id]
            for glyph_id in selected_ids
            if before_state[glyph_id] != after_state[glyph_id]
        }

        modified_after = {
            glyph_id: after_state[glyph_id]
            for glyph_id in selected_ids
            if before_state[glyph_id] != after_state[glyph_id]
        }

        if not modified_after:
            return

        self.composition.update_bunch_of_glyphs(modified_after)

        self.push_action(
            Actions.ActionModify(self, modified_before, modified_after)
        )
        self.update_glyphs(selected_ids)

    def adjust_keyframes_brightness(
            self,
            keyframes: list[tuple[float, int]],
            delta:     int
        ) -> list[tuple[float, int]] | None:

        adjusted_keyframes = [
            (
                round(float(time_fraction), 2),
                max(0, min(100, int(round(float(brightness_value))) + delta))
            )
            for time_fraction, brightness_value in keyframes
        ]

        normalized_keyframes = [
            (
                round(float(time_fraction), 2),
                int(round(float(brightness_value)))
            )
            for time_fraction, brightness_value in keyframes
        ]

        if adjusted_keyframes == normalized_keyframes:
            return None

        return adjusted_keyframes

    def adjust_selected_brightness(self, delta: int) -> None:
        selected_glyph_identifiers = self.get_selected_glyph_ids()

        if not selected_glyph_identifiers:
            return

        before_state = {}
        after_state  = {}

        self.composition.start_batching()

        try:
            for glyph_identifier in selected_glyph_identifiers:
                glyph_data = self.composition.get_glyph(glyph_identifier)
                glyph_item = self.glyph_items.get(glyph_identifier)

                if not glyph_data:
                    continue

                if glyph_item and glyph_item.keyframes:
                    new_keyframes = self.adjust_keyframes_brightness(glyph_item.keyframes, delta)

                    if new_keyframes is None:
                        continue

                    before_state[glyph_identifier] = copy.deepcopy(glyph_data)

                    if "effect" in glyph_data and glyph_data["effect"].get("name") == "Fade":
                        effect_settings = glyph_data["effect"].get("settings", {})
                        new_settings    = {**effect_settings, "keyframes": new_keyframes}

                        after_state[glyph_identifier] = GlyphEffects.apply_visual_effect(
                            copy.deepcopy(glyph_data),
                            "Fade",
                            new_settings
                        )

                    elif "keyframes" in glyph_data:
                        after_state[glyph_identifier] = {
                            **copy.deepcopy(glyph_data),
                            "keyframes": new_keyframes
                        }

                elif "brightness" in glyph_data:
                    current_brightness = glyph_data["brightness"]
                    new_brightness     = max(0, min(100, current_brightness + delta))

                    if new_brightness == current_brightness:
                        continue

                    before_state[glyph_identifier] = copy.deepcopy(glyph_data)
                    after_state[glyph_identifier]  = {
                        **copy.deepcopy(glyph_data),
                        "brightness": new_brightness
                    }

            if after_state:
                self.push_action(Actions.ActionModify(self, before_state, after_state))
                self.composition.update_bunch_of_glyphs(after_state)
                self.update_glyphs(after_state)

                for glyph_id in after_state:
                    if item := self.glyph_items.get(glyph_id):
                        item.update()

                self.elements_changed.emit()
                self.glyph_property_changed.emit("brightness")

                direction_sound = "Higher" if delta > 0 else "Lower"
                target_sound    = f"Glyphs/Brightness/{direction_sound}"

                Player.ui_player.play_sound(target_sound, setting_key = "brightness_adjustment_sounds")

                delta_prefix = "+" if delta > 0 else ""
                
                if len(after_state) == 1:
                    target_glyph_id = next(iter(after_state))
                    item_ref        = self.glyph_items[target_glyph_id]
                    target_data     = after_state[target_glyph_id]

                    if item_ref.keyframes:
                        tooltip_message = f"Keyframes: {delta_prefix}{delta}%"

                    else:
                        tooltip_message = f"Brightness: {target_data.get('brightness', 100)}%"

                    self.conductor.tooltip.show_tooltip_at(
                        tooltip_message,
                        item_ref,
                        True
                    )
                
                else:
                    last_glyph_id = selected_glyph_identifiers[-1]
                    item_ref      = self.glyph_items.get(last_glyph_id)
                    
                    if item_ref:
                        tooltip_message = f"Brightness: {delta_prefix}{delta}% ({len(after_state)} glyphs)"
                        self.conductor.tooltip.show_tooltip_at(
                            tooltip_message,
                            item_ref,
                            True
                        )

        finally:
            self.composition.stop_batching()

    def push_action(
            self,
            action: Actions.ActionAdd | Actions.ActionModify | Actions.ActionDelete | Actions.EditFadeKeyframesCommand
        ) -> None:

        if isinstance(action, Actions.ActionModify) and action.glyphs_before_modify == action.glyphs_after_modify:
            return

        self.undo_stack.append(action)
        self.redo_stack.clear()

        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

    def undo(self) -> None:
        if not self.undo_stack:
            self.conductor.tooltip.show_tooltip_at("Nothing to undo.", plan_hide = True)
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
            self.conductor.tooltip.show_tooltip_at(f"Undo {detail}", plan_hide = True)

        finally:
            self.refresh_all_occlusion()
            self.is_processing = False
            self.conductor.update()

    def redo(self) -> None:
        if not self.redo_stack:
            self.conductor.tooltip.show_tooltip_at("Nothing to redo.", plan_hide = True)
            return

        if self.is_processing:
            return

        self.is_processing = True

        try:
            action = self.redo_stack.pop()
            action.redo()
            self.undo_stack.append(action)
            self.elements_changed.emit()

            detail = action.get_description()
            self.conductor.tooltip.show_tooltip_at(f"Redo {detail}", plan_hide = True)

        finally:
            self.refresh_all_occlusion()
            self.is_processing = False
            self.conductor.update()

    # GlyphManagement

    def update_glyphs(
            self,
            glyph_ids:        dict[int, dict] | list[int] | None = None,
            animate_movement: bool                               = False
        ) -> None:

        if glyph_ids:
            for glyph_id in glyph_ids:
                if glyph_id in self.glyph_items:
                    self.glyph_items[glyph_id].update_geometry(animate_movement = animate_movement)

            return

        for glyph in self.glyph_items.values():
            glyph.update_geometry(animate_movement = animate_movement)

    def update_all_glyphs(self) -> None:
        self.update_glyphs()

    def clear_glyphs(self) -> None:
        for item in self.glyph_items.values():
            item.remove_glyph(False)

        self.glyph_items.clear()
        self.occlusion_controller.track_intervals.clear()
        self.occlusion_controller.occluded_glyphs.clear()

        self.elements_changed.emit()

    def delete_selected_glyphs(self) -> None:
        self.delete_glyphs(self.get_selected_glyph_ids())

    def delete_glyphs(
            self,
            glyph_ids: list[int],
            push_undo: bool = True
        ) -> None:

        if not glyph_ids:
            return

        deleted_batch   = {}
        affected_tracks = set()

        for glyph_id in glyph_ids:
            data = self.composition.get_glyph(glyph_id)

            if data:
                deleted_batch[glyph_id] = copy.deepcopy(data)
                affected_tracks.add(data["track"])

        deleted_items = [self.glyph_items.pop(glyph_id, None) for glyph_id in glyph_ids]
        deleted_items = [item for item in deleted_items if item]

        for item in deleted_items:
            item.remove_glyph()

        self.composition.delete_bunch_of_glyphs(glyph_ids)

        if push_undo and deleted_batch:
            self.push_action(Actions.ActionDelete(self, deleted_batch))

        self.glyph_deleted.emit()
        self.elements_changed.emit()
        self.refresh_stack_indicators(force = True)

        for track in affected_tracks:
            self.refresh_occlusion_for_track(track)

    def spawn_glyph_on_track(self, track_index: str) -> None:
        if track_index not in self.composition.track_names:
            return

        current_playhead_ms = int(self.conductor.get_playhead_position_ms())
        audio_delay_ms      = Constants.current_settings.get("audio_delay_ms", 0)

        if self.conductor.playback_manager.is_playing and audio_delay_ms != 0:
            current_playhead_ms = max(0, current_playhead_ms + audio_delay_ms)

        remaining_time  = max(0, Player.player.duration_ms - current_playhead_ms)
        actual_duration = min(self.composition.duration_ms, remaining_time)

        if actual_duration <= 0:
            return

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

    def duplicate_selected_glyphs(self) -> None:
        self.copy_glyphs()
        Player.ui_player.play_sound("Glyphs/Duplicate", setting_key = "glyph_duplication_sound")
        self.paste_glyphs()

    def paste_glyphs(self) -> None:
        if not self.copied_data or self.is_processing:
            return

        self.is_processing = True

        try:
            current_playhead_ms = self.conductor.get_playhead_position_ms()
            copied_start_ms     = min(glyph_data["start"] for glyph_data in self.copied_data)
            time_offset         = int(current_playhead_ms - copied_start_ms)
            audio_duration_ms   = self.conductor.playback_manager.duration_ms

            self.conductor.scene.clearSelection()

            new_added_glyphs = {}
            new_ids          = []

            self.composition.start_batching()

            for glyph_data in self.copied_data:
                result = self.composition.copy_glyph(glyph_data, time_offset, audio_duration_ms)

                if (new_id := result[0]) is not None:
                    new_ids.append(new_id)
                    new_added_glyphs[new_id] = result[1]

            self.composition.stop_batching()

            if not new_ids:
                return

            self.create_glyph_items(new_ids, reset_selection = False)
            self.push_action(Actions.ActionAdd(self, new_added_glyphs))
            self.elements_changed.emit()

        finally:
            self.is_processing = False

    def create_glyph_items(
            self,
            glyph_ids:       list[int],
            reset_selection: bool = True,
            set_selected:    bool = True,
            animate_spawn:   bool = True
        ) -> None:

        if reset_selection:
            self.conductor.scene.clearSelection()

        for glyph_id in glyph_ids:
            item = Widgets.GlyphItem(glyph_id, self.conductor, animate_spawn)

            self.glyph_items[glyph_id] = item
            self.conductor.scene.addItem(item)

            if set_selected:
                item.was_clicked = True
                item.setSelected(True)

            item.update()

        QTimer.singleShot(0, lambda: self.refresh_stack_indicators(force = True))

        if self.expanded_stack:
            new_ids = list(glyph_ids)
            QTimer.singleShot(0, lambda: self.handle_spawned_while_expanded(new_ids))

        self.refresh_all_occlusion()

    def handle_spawned_while_expanded(self, new_glyph_ids: list[int]) -> None:
        if not self.expanded_stack:
            return

        try:
            representative_id = next(iter(self.expanded_stack))

        except StopIteration:
            return

        group = self.get_overlapping_group(representative_id)

        if len(group) > 1:
            self.stop_running_stack_animations()
            self.sort_stack_group(group)
            self.expanded_stack = frozenset(group)

            stack_items = [self.glyph_items[glyph_id] for glyph_id in group if glyph_id in self.glyph_items]
            self.occlusion_controller.reveal_glyphs(stack_items)

            first_item = self.glyph_items.get(group[0])

            if first_item is None:
                return

            base_y     = float(first_item.fixed_y_px)
            box_height = float(Styles.Metrics.Tracks.BoxHeight)

            direction, step = self.calculate_expansion_params(len(group), base_y, box_height)
            self.animate_stack_items(group, step, direction, len(group))

    def handle_escape(self) -> None:
        if self.expanded_stack:
            self.collapse_stack()
            return

        self.conductor.scene.clearSelection()

    # DragOperations

    def start_drag(self) -> None:
        self.drag_session      = {}
        self.temp_before_state = {}
        self.current_drag_mode = None
        selected_glyph_items   = self.get_selected_glyph_items()

        if not selected_glyph_items:
            return

        self.drag_state_changed.emit(True)
        self.composition.start_batching()

        for item in selected_glyph_items:
            self.drag_session[item] = {
                "start":    item.start_ms,
                "duration": item.duration_ms,
            }

            if data := self.composition.get_glyph(item.glyph_id):
                self.temp_before_state[item.glyph_id] = copy.deepcopy(data)

    def end_drag(self) -> None:
        try:
            if not self.drag_session:
                return

            after_state = {
                item.glyph_id: copy.deepcopy(data)
                for item in self.drag_session
                if (data := self.composition.get_glyph(item.glyph_id)) is not None
            }

            actually_moved = any(
                after_state.get(glyph_id) != self.temp_before_state.get(glyph_id)
                for glyph_id in after_state
            )

            if actually_moved:
                self.push_action(Actions.ActionModify(self, self.temp_before_state, after_state))

            drag_mode = self.current_drag_mode

            self.refresh_stack_indicators(force = True)
            self.refresh_all_occlusion()

            if actually_moved and drag_mode:
                self.glyph_moved_or_resized.emit(drag_mode)

        finally:
            self.drag_session.clear()
            self.temp_before_state.clear()

            self.current_drag_mode = None

            if self.composition.batching_mode:
                self.composition.stop_batching()
            
            self.drag_state_changed.emit(False)

    def update_drag_state(
            self,
            delta_ms:        float,
            mode:            str,
            active_item_ref: Widgets.GlyphItem
        ) -> None:

        audio_duration  = self.conductor.playback_manager.duration_ms
        popup_text      = ""
        affected_tracks = set()

        self.current_drag_mode = mode
        self.glyph_drag_progress.emit(mode, delta_ms)

        for item, initial in self.drag_session.items():
            target_data = self.composition.get_glyph(item.glyph_id)

            if target_data is None:
                continue

            affected_tracks.add(target_data["track"])
            initial_start    = initial["start"]
            initial_duration = initial["duration"]

            if mode == "move":
                new_start            = int(max(0, min(initial_start + delta_ms, audio_duration - initial_duration)))
                target_data["start"] = new_start
                value_to_show        = new_start

            elif mode == "resize_right":
                new_duration            = int(max(10, min(initial_duration + delta_ms, audio_duration - initial_start)))
                target_data["duration"] = new_duration
                value_to_show           = new_duration

            elif mode == "resize_left":
                original_end_ms = initial_start + initial_duration
                new_start       = int(max(0, min(initial_start + delta_ms, original_end_ms - 10)))
                new_duration    = original_end_ms - new_start
                value_to_show   = new_duration

                target_data["start"]    = new_start
                target_data["duration"] = new_duration

            if item == active_item_ref:
                popup_text = f"{value_to_show} ms"

            item.update_drag_geometry()
            self.composition.glyphs.mark_dirty(item.glyph_id)

        if popup_text:
            self.conductor.tooltip.show_tooltip_at(popup_text, active_item_ref)

    def end_drag(self) -> None:
        if not self.drag_session:
            return

        after_state = {
            item.glyph_id: copy.deepcopy(data)
            for item in self.drag_session
            if (data := self.composition.get_glyph(item.glyph_id)) is not None
        }

        actually_moved = any(
            after_state.get(glyph_id) != self.temp_before_state.get(glyph_id)
            for glyph_id in after_state
        )

        if actually_moved:
            self.push_action(Actions.ActionModify(self, self.temp_before_state, after_state))

        self.composition.stop_batching()

        drag_mode = self.current_drag_mode

        self.drag_session.clear()
        self.temp_before_state.clear()
        self.current_drag_mode = None

        self.refresh_stack_indicators(force = True)
        self.refresh_all_occlusion()

        self.drag_state_changed.emit(False)

        if actually_moved and drag_mode:
            self.glyph_moved_or_resized.emit(drag_mode)

    # Keyframes

    def commit_fade_keyframes(
            self,
            glyph_id:      int,
            old_keyframes: list[tuple[float, int]],
            new_keyframes: list[tuple[float, int]]
        ) -> None:

        original_glyph = self.conductor.composition.get_glyph(glyph_id)

        if original_glyph is None:
            return

        effect = original_glyph.get("effect", {})

        if effect.get("name") != "Fade":
            return

        clean_old = [(round(float(time_part), 2), int(round(float(brightness_part)))) for time_part, brightness_part in old_keyframes]
        clean_new = [(round(float(time_part), 2), int(round(float(brightness_part)))) for time_part, brightness_part in new_keyframes]

        settings     = effect["settings"]
        new_glyph    = copy.deepcopy(original_glyph)
        new_settings = {**settings, "keyframes": clean_new}

        new_glyph = GlyphEffects.apply_visual_effect(new_glyph, "Fade", new_settings)
        self.conductor.composition.replace_glyph(glyph_id, new_glyph)

        self.push_action(
            Actions.EditFadeKeyframesCommand(
                self,
                glyph_id,
                clean_old,
                clean_new
            )
        )

    # StackingAndGroups

    def get_overlapping_group(self, glyph_id: int) -> list[int]:
        data = self.composition.get_glyph(glyph_id)

        if not data:
            return [glyph_id]

        track = data["track"]
        start = data["start"]
        end   = start + data["duration"]
        group = [glyph_id]

        for candidate_id in self.glyph_items:
            if candidate_id == glyph_id:
                continue

            other = self.composition.get_glyph(candidate_id)

            if not other or other["track"] != track:
                continue

            other_start = other["start"]
            other_end   = other_start + other["duration"]

            if other_start < end and other_end > start:
                group.append(candidate_id)

        return group

    def refresh_stack_indicators(self, force: bool = False) -> None:
        if self.expanded_stack and not force:
            return

        by_track = {}

        for glyph_id in self.glyph_items:
            data = self.composition.get_glyph(glyph_id)

            if not data:
                continue

            start = data["start"]
            by_track.setdefault(data["track"], []).append((start, start + data["duration"], glyph_id))

        stacks = {glyph_id: 0 for glyph_id in self.glyph_items}

        for entries in by_track.values():
            entries.sort()
            count = len(entries)

            for first_index in range(count):
                start_a, end_a, glyph_id_a = entries[first_index]

                for second_index in range(first_index + 1, count):
                    start_b, end_b, glyph_id_b = entries[second_index]

                    if start_b >= end_a:
                        break

                    stacks[glyph_id_a] += 1
                    stacks[glyph_id_b] += 1

        for glyph_id, item in self.glyph_items.items():
            depth = stacks.get(glyph_id, 0)
            item.set_stack_depth(depth)

    def stop_running_stack_animations(self) -> None:
        for animation_handle in self.expand_animations + self.collapse_animations:
            try:
                animation_handle.stop_targeting()

            except Exception:
                pass

        self.expand_animations.clear()
        self.collapse_animations.clear()

        if self.collapse_refresh_timer:
            self.collapse_refresh_timer.stop()
            self.collapse_refresh_timer = None

    def sort_stack_group(self, group: list[int]) -> None:
        def sort_key(glyph_id: int) -> tuple:
            glyph = self.composition.get_glyph(glyph_id)
            return (glyph["start"] if glyph else 0, glyph_id)

        group.sort(key = sort_key)

    def calculate_expansion_params(
            self,
            group_size: int,
            base_y:     float,
            box_height: float
        ) -> tuple[float, float]:

        base_step  = Styles.Metrics.Tracks.BoxHeight + Styles.Metrics.Tracks.BoxSpacing + 6
        scene      = self.conductor.scene
        scene_rect = scene.sceneRect()

        boundary_margin = 15.0

        space_below = max(0.0, scene_rect.bottom() - (base_y + box_height) - boundary_margin)
        space_above = max(0.0, base_y - scene_rect.top() - boundary_margin)

        if space_below >= space_above:
            direction      = 1.0
            available_span = space_below

        else:
            direction      = -1.0
            available_span = space_above

        if group_size > 1:
            max_step_by_space = available_span / float(group_size - 1) if available_span > 0 else 0.0
            step              = min(base_step, max_step_by_space) if max_step_by_space > 0 else 0.0

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

        pixels_per_second = 500.0
        minimum_duration  = 180

        for index, glyph_id in enumerate(group):
            item = self.glyph_items.get(glyph_id)

            if not item:
                continue

            target_offset  = direction * float(index * step)
            current_offset = float(item.property("stackYOffset") or 0.0)
            distance       = abs(target_offset - current_offset)

            duration = max(minimum_duration, int((distance / pixels_per_second) * 1000.0))

            item.setZValue(float(group_size - index))

            handle = item.stack_y_offset_handle
            handle.set_target(
                value                      = target_offset,
                duration_ms                = duration,
                easing_function            = LoomEngine.Easing.ease_out_expo,
                multiply_duration_by_speed = False
            )

            self.expand_animations.append(handle)

    def expand_stack(self, glyph_id: int) -> None:
        group = self.get_overlapping_group(glyph_id)

        if len(group) <= 1:
            return

        self.stop_running_stack_animations()

        self.sort_stack_group(group)
        self.expanded_stack = frozenset(group)

        stack_items = [self.glyph_items[target_id] for target_id in group if target_id in self.glyph_items]
        self.occlusion_controller.reveal_glyphs(stack_items)

        group_size = len(group)

        if group_size <= 1:
            return

        first_item = self.glyph_items.get(group[0])

        if first_item is None:
            return

        base_y     = float(first_item.fixed_y_px)
        box_height = float(Styles.Metrics.Tracks.BoxHeight)

        direction, step = self.calculate_expansion_params(group_size, base_y, box_height)

        self.animate_stack_items(group, step, direction, group_size)

        Player.ui_player.play_sound("Glyphs/Stack/Expand", setting_key = "glyph_stack_sounds")

    def collapse_stack_items(self, group: list[int]) -> None:
        collapse_duration = 220

        for glyph_id in group:
            item = self.glyph_items.get(glyph_id)

            if not item:
                continue

            handle = item.stack_y_offset_handle
            handle.set_target(
                value                      = 0.0,
                duration_ms                = collapse_duration,
                easing_function            = LoomEngine.Easing.ease_out_cubic,
                multiply_duration_by_speed = False
            )

            self.collapse_animations.append(handle)

            item.setZValue(0.0)

    def collapse_stack(self) -> None:
        if not self.expanded_stack:
            return

        self.stop_running_stack_animations()

        group               = list(self.expanded_stack)
        self.expanded_stack = None

        self.collapse_stack_items(group)

        QTimer.singleShot(230, self.finish_stack_collapse)
        Player.ui_player.play_sound("Glyphs/Stack/Collapse", setting_key = "glyph_stack_sounds")

    def finish_stack_collapse(self) -> None:
        self.refresh_stack_indicators()
        self.refresh_all_occlusion()

    # OcclusionUpdates

    def refresh_occlusion_for_track(self, track_index: str) -> None:
        items_on_track = [
            item for glyph_id, item in self.glyph_items.items()
            if (data := self.composition.get_glyph(glyph_id)) and data["track"] == track_index
        ]

        self.occlusion_controller.update_track_occlusion(
            track_index,
            items_on_track,
            expanded_stack = self.expanded_stack
        )

    def refresh_all_occlusion(self) -> None:
        by_track = {}

        for glyph_id, item in self.glyph_items.items():
            if data := self.composition.get_glyph(glyph_id):
                by_track.setdefault(data["track"], []).append(item)

        for track_id, items in by_track.items():
            self.occlusion_controller.update_track_occlusion(
                track_id,
                items,
                expanded_stack = self.expanded_stack
            )