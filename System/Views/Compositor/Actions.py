from __future__ import annotations

import copy

from typing import *

if TYPE_CHECKING:
    from . import Controllers

from System.Services import (
    ProjectSaver,
    GlyphEffects
)

GlyphState = dict[int, dict]

class FieldConfig(TypedDict):
    key:      str
    label:    Callable[[dict], str]
    template: str

class ActionModify:
    FIELDS: list[FieldConfig] = [
        {
            "key":      "segments",
            "label":    lambda g: ", ".join(map(lambda x: str(x + 1), g["segments"])) if g.get("segments") else "all",
            "template": "setting segments from {b} to {a}",
        },
        {
            "key":      "effect",
            "label":    lambda g: f"{g['effect']['name']} effect" if g.get("effect") else "no effect",
            "template": "setting effect from {b} to {a}",
        },
        {
            "key":      "duration",
            "label":    lambda g: f"{g['duration']}ms",
            "template": "setting duration from {b} to {a}",
        },
        {
            "key":      "brightness",
            "label":    lambda g: f"{g.get('brightness', 0)}%",
            "template": "setting brightness from {b} to {a}",
        },
        {
            "key":      "start",
            "label":    lambda g: f"{g['start']}ms",
            "template": "move from {b} to {a}",
        },
    ]

    def __init__(
        self,
        controller:   Controllers.GlyphController,
        before_state: GlyphState,
        after_state:  GlyphState,
    ) -> None:
        
        self.controller = controller

        self.composition:          ProjectSaver.Composition = controller.composition
        self.glyphs_before_modify: GlyphState               = copy.deepcopy(before_state)
        self.glyphs_after_modify:  GlyphState               = copy.deepcopy(after_state)

    def get_description(self) -> str:
        before  = self.glyphs_before_modify
        after   = self.glyphs_after_modify
        all_ids = set(before) | set(after)

        if not all_ids:
            return "nothing"

        target_id = next(
            (gid for gid in all_ids if before.get(gid) != after.get(gid)),
            next(iter(all_ids)),
        )

        b_glyph = before.get(target_id) or {}
        a_glyph = after.get(target_id)  or {}

        for field in self.FIELDS:
            key   = field["key"]
            val_b = b_glyph.get(key)
            val_a = a_glyph.get(key)

            if val_b == val_a:
                continue

            b_label = field["label"](b_glyph)
            a_label = field["label"](a_glyph)

            if key == "effect" and b_label == a_label:
                return "effect modify"

            return field["template"].format(b=b_label, a=a_label)

        return "nothing"

    def undo(self) -> None:
        self.composition.update_bunch_of_glyphs(copy.deepcopy(self.glyphs_before_modify))
        self.controller.update_glyphs(self.glyphs_before_modify)

    def redo(self) -> None:
        self.composition.update_bunch_of_glyphs(copy.deepcopy(self.glyphs_after_modify))
        self.controller.update_glyphs(self.glyphs_after_modify)

class ActionAdd:
    def __init__(
        self,
        controller:   Controllers.GlyphController,
        added_glyphs: GlyphState
    ) -> None:
        
        self.controller = controller

        self.composition:  ProjectSaver.Composition = controller.composition
        self.added_glyphs: GlyphState               = copy.deepcopy(added_glyphs)

    def get_description(self) -> str:
        count = len(self.added_glyphs)
        return f"addition of {count} glyph{'s' if count != 1 else ''}"

    def undo(self) -> None:
        for gid in self.added_glyphs:
            self.controller.glyph_items[gid].prepare_for_despawn()

        self.controller.delete_glyphs(self.added_glyphs.keys(), push_undo=False)

    def redo(self) -> None:
        self.composition.update_bunch_of_glyphs(copy.deepcopy(self.added_glyphs))
        self.controller.create_glyph_items(self.added_glyphs.keys(), reset_selection=False)
        self.controller.elements_changed.emit()

class ActionDelete:
    def __init__(
        self,
        controller:     Controllers.GlyphController,
        deleted_glyphs: GlyphState,
    ) -> None:
        
        self.controller = controller

        self.composition:    ProjectSaver.Composition = controller.composition
        self.deleted_glyphs: GlyphState               = deleted_glyphs

    def get_description(self) -> str:
        count = len(self.deleted_glyphs)
        return f"deletion of {count} glyph{'s' if count != 1 else ''}"

    def undo(self) -> None:
        self.composition.update_bunch_of_glyphs(copy.deepcopy(self.deleted_glyphs))
        self.controller.create_glyph_items(self.deleted_glyphs, reset_selection=False)
        self.controller.elements_changed.emit()

    def redo(self) -> None:
        self.controller.delete_glyphs(list(self.deleted_glyphs.keys()), push_undo=False)

class EditFadeKeyframesCommand:
    def __init__(
        self,
        composition:   ProjectSaver.Composition,
        glyph_id:      int,
        old_keyframes: list[tuple[float, int]],
        new_keyframes: list[tuple[float, int]],
    ) -> None:
        
        self.composition   = composition
        self.glyph_id      = glyph_id
        self.old_keyframes = old_keyframes
        self.new_keyframes = new_keyframes

    def get_description(self) -> str:
        return "editing fade keyframes"

    def redo(self) -> None:
        self.apply(self.new_keyframes)

    def undo(self) -> None:
        self.apply(self.old_keyframes)

    def apply(self, keyframes: list[tuple[float, int]]) -> None:
        glyph = self.composition.get_glyph(self.glyph_id)

        if glyph is None:
            return

        effect = glyph.get("effect")

        if not effect or effect.get("name") != "Fade":
            return

        new_settings  = {**effect["settings"], "keyframes": list(keyframes)}
        updated_glyph = GlyphEffects.apply_visual_effect(glyph, "Fade", new_settings)

        self.composition.replace_glyph(self.glyph_id, updated_glyph)