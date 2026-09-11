from __future__ import annotations

import copy

from System.Services import (
    ProjectSaver,
    GlyphEffects
)

class ActionModify:
    FIELDS = [
        {
            "key":      "segments",
            "label":    lambda glyph: ", ".join(map(lambda segment_index: str(segment_index + 1), glyph["segments"])) if glyph.get("segments") else "all",
            "template": "setting segments from {before} to {after}"
        },
        {
            "key":      "effect",
            "label":    lambda glyph: f"{glyph['effect']['name']} effect" if glyph.get("effect") else "no effect",
            "template": "setting effect from {before} to {after}"
        },
        {
            "key":      "duration",
            "label":    lambda glyph: f"{glyph['duration']}ms",
            "template": "setting duration from {before} to {after}"
        },
        {
            "key":      "brightness",
            "label":    lambda glyph: f"{glyph.get('brightness', 0)}%",
            "template": "setting brightness from {before} to {after}"
        },
        {
            "key":      "start",
            "label":    lambda glyph: f"{glyph['start']}ms",
            "template": "move from {before} to {after}"
        }
    ]

    def __init__(
            self,
            controller:   object,
            before_state: dict[int, dict],
            after_state:  dict[int, dict]
        ) -> None:

        self.controller = controller

        self.composition:          ProjectSaver.Composition = controller.composition
        self.glyphs_before_modify: dict[int, dict]          = copy.deepcopy(before_state)
        self.glyphs_after_modify:  dict[int, dict]          = copy.deepcopy(after_state)

    def get_description(self) -> str:
        before_glyphs = self.glyphs_before_modify
        after_glyphs  = self.glyphs_after_modify
        all_glyph_ids = set(before_glyphs) | set(after_glyphs)

        if not all_glyph_ids:
            return "nothing"

        target_glyph_id = next(
            (glyph_id for glyph_id in all_glyph_ids if before_glyphs.get(glyph_id) != after_glyphs.get(glyph_id)),
            next(iter(all_glyph_ids))
        )

        glyph_before = before_glyphs.get(target_glyph_id) or {}
        glyph_after  = after_glyphs.get(target_glyph_id)  or {}

        for field in self.FIELDS:
            key          = field["key"]
            value_before = glyph_before.get(key)
            value_after  = glyph_after.get(key)

            if value_before == value_after:
                continue

            label_before = field["label"](glyph_before)
            label_after  = field["label"](glyph_after)

            if key == "effect" and label_before == label_after:
                return "effect modify"

            return field["template"].format(before = label_before, after = label_after)

        return "nothing"

    def undo(self) -> None:
        self.composition.update_bunch_of_glyphs(copy.deepcopy(self.glyphs_before_modify))
        self.controller.update_glyphs(self.glyphs_before_modify, animate_movement = True)

    def redo(self) -> None:
        self.composition.update_bunch_of_glyphs(copy.deepcopy(self.glyphs_after_modify))
        self.controller.update_glyphs(self.glyphs_after_modify, animate_movement = True)

class ActionAdd:
    def __init__(
            self,
            controller:   object,
            added_glyphs: dict[int, dict]
        ) -> None:

        self.controller = controller

        self.composition:  ProjectSaver.Composition = controller.composition
        self.added_glyphs: dict[int, dict]          = copy.deepcopy(added_glyphs)

    def get_description(self) -> str:
        count = len(self.added_glyphs)
        return f"addition of {count} glyph{'s' if count != 1 else ''}"

    def undo(self) -> None:
        for glyph_id in self.added_glyphs:
            self.controller.glyph_items[glyph_id].prepare_for_despawn()

        self.controller.delete_glyphs(list(self.added_glyphs.keys()), push_undo = False)

    def redo(self) -> None:
        self.composition.update_bunch_of_glyphs(copy.deepcopy(self.added_glyphs))
        self.controller.create_glyph_items(list(self.added_glyphs.keys()), reset_selection = False)
        self.controller.elements_changed.emit()

class ActionDelete:
    def __init__(
            self,
            controller:     object,
            deleted_glyphs: dict[int, dict]
        ) -> None:

        self.controller = controller

        self.composition:    ProjectSaver.Composition = controller.composition
        self.deleted_glyphs: dict[int, dict]          = deleted_glyphs

    def get_description(self) -> str:
        count = len(self.deleted_glyphs)
        return f"deletion of {count} glyph{'s' if count != 1 else ''}"

    def undo(self) -> None:
        self.composition.update_bunch_of_glyphs(copy.deepcopy(self.deleted_glyphs))
        self.controller.create_glyph_items(list(self.deleted_glyphs.keys()), reset_selection = False)
        self.controller.elements_changed.emit()

    def redo(self) -> None:
        self.controller.delete_glyphs(list(self.deleted_glyphs.keys()), push_undo = False)

class EditFadeKeyframesCommand:
    def __init__(
            self,
            controller:    object,
            glyph_id:      int,
            old_keyframes: list[tuple[float, int]],
            new_keyframes: list[tuple[float, int]]
        ) -> None:

        self.controller    = controller
        self.composition   = controller.composition
        self.glyph_id      = glyph_id
        self.old_keyframes = copy.deepcopy(old_keyframes)
        self.new_keyframes = copy.deepcopy(new_keyframes)

    def undo(self) -> None:
        self.apply(self.old_keyframes)

    def redo(self) -> None:
        self.apply(self.new_keyframes)

    def get_description(self) -> str:
        return "editing fade keyframes"

    def apply(self, keyframes: list[tuple[float, int]]) -> None:
        glyph = self.composition.get_glyph(self.glyph_id)

        if glyph is None:
            return

        effect = glyph.get("effect")

        if not effect or effect.get("name") != "Fade":
            return

        clean_keyframes = [(round(float(time_part), 2), int(round(float(brightness_part)))) for time_part, brightness_part in keyframes]
        new_settings    = {**effect["settings"], "keyframes": clean_keyframes}
        updated_glyph   = GlyphEffects.apply_visual_effect(glyph, "Fade", new_settings)

        self.composition.replace_glyph(self.glyph_id, updated_glyph)
        self.controller.update_glyphs([self.glyph_id])