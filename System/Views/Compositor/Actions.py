import copy

from System.Services import GlyphEffects

# Modifications

class ActionModify:
    FIELDS = [
        {
            "key":      "track",
            "label":    lambda glyph: f"track {glyph['track']}",
            "template": "moving from {before} to {after}"
        },
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

    # Initialization Section

    def __init__(
            self,
            controller:   object,
            before_state: dict[int, dict],
            after_state:  dict[int, dict]
        ) -> None:

        self.controller           = controller
        self.composition          = controller.composition
        self.glyphs_before_modify = copy.deepcopy(before_state)
        self.glyphs_after_modify  = copy.deepcopy(after_state)

    # Description Section

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
        glyph_after  = after_glyphs.get(target_glyph_id) or {}

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

    # Execution Section

    def undo(self) -> None:
        self.composition.start_batching()

        try:
            self.composition.update_bunch_of_glyphs(copy.deepcopy(self.glyphs_before_modify))
            self.controller.update_glyphs(self.glyphs_before_modify, animate_movement = True)

        finally:
            self.composition.stop_batching()

    def redo(self) -> None:
        self.composition.start_batching()

        try:
            self.composition.update_bunch_of_glyphs(copy.deepcopy(self.glyphs_after_modify))
            self.controller.update_glyphs(self.glyphs_after_modify, animate_movement = True)

        finally:
            self.composition.stop_batching()

# Additions

class ActionAdd:

    # Initialization Section

    def __init__(
            self,
            controller:   object,
            added_glyphs: dict[int, dict]
        ) -> None:

        self.controller   = controller
        self.composition  = controller.composition
        self.added_glyphs = copy.deepcopy(added_glyphs)

    # Description Section

    def get_description(self) -> str:
        count = len(self.added_glyphs)

        return f"addition of {count} glyph{'s' if count != 1 else ''}"

    # Execution Section

    def undo(self) -> None:
        for glyph_id in self.added_glyphs:
            self.controller.glyph_items[glyph_id].prepare_for_despawn()

        self.controller.delete_glyphs(list(self.added_glyphs.keys()), push_undo = False)

    def redo(self) -> None:
        self.composition.start_batching()

        try:
            self.composition.update_bunch_of_glyphs(copy.deepcopy(self.added_glyphs))
            self.controller.create_glyph_items(list(self.added_glyphs.keys()), reset_selection = False)
            self.controller.elements_changed.emit()

        finally:
            self.composition.stop_batching()

# Deletions

class ActionDelete:

    # Initialization Section

    def __init__(
            self,
            controller:     object,
            deleted_glyphs: dict[int, dict]
        ) -> None:

        self.controller     = controller
        self.composition    = controller.composition
        self.deleted_glyphs = copy.deepcopy(deleted_glyphs)

    # Description Section

    def get_description(self) -> str:
        count = len(self.deleted_glyphs)

        return f"deletion of {count} glyph{'s' if count != 1 else ''}"

    # Execution Section

    def undo(self) -> None:
        self.composition.start_batching()

        try:
            self.composition.update_bunch_of_glyphs(copy.deepcopy(self.deleted_glyphs))
            self.controller.create_glyph_items(list(self.deleted_glyphs.keys()), reset_selection = False)
            self.controller.elements_changed.emit()

        finally:
            self.composition.stop_batching()

    def redo(self) -> None:
        self.controller.delete_glyphs(list(self.deleted_glyphs.keys()), push_undo = False)

# Keyframe Group Commands

class EditFadeKeyframesCommand:

    # Initialization Section

    def __init__(
            self,
            controller:     object,
            mutations_data: dict[int, tuple[list[tuple[float, int]], list[tuple[float, int]]]] | int,
            old_keyframes:  list[tuple[float, int]] | None = None,
            new_keyframes:  list[tuple[float, int]] | None = None
        ) -> None:

        self.controller  = controller
        self.composition = controller.composition

        if isinstance(mutations_data, int):
            self.mutations = {
                mutations_data: (
                    copy.deepcopy(old_keyframes),
                    copy.deepcopy(new_keyframes)
                )
            }

        else:
            self.mutations = copy.deepcopy(mutations_data)

    # Execution Section

    def undo(self) -> None:
        self.composition.start_batching()

        try:
            for glyph_identifier, (old_keyframes, _) in self.mutations.items():
                self.apply_glyph_keyframes(glyph_identifier, old_keyframes)

            self.controller.update_glyphs(list(self.mutations.keys()), animate_movement = True)

        finally:
            self.composition.stop_batching()

    def redo(self) -> None:
        self.composition.start_batching()

        try:
            for glyph_identifier, (_, new_keyframes) in self.mutations.items():
                self.apply_glyph_keyframes(glyph_identifier, new_keyframes)

            self.controller.update_glyphs(list(self.mutations.keys()), animate_movement = True)

        finally:
            self.composition.stop_batching()

    # Description Section

    def get_description(self) -> str:
        count = len(self.mutations)

        if count <= 1:
            return "editing fade keyframes"

        return f"editing fade keyframes on {count} glyphs"

    # Application Section

    def apply_glyph_keyframes(
            self,
            glyph_identifier: int,
            keyframes:        list[tuple[float, int]]
        ) -> None:

        glyph = self.composition.get_glyph(glyph_identifier)

        if glyph is None:
            return

        clean_keyframes = [
            (round(float(time_fraction), 2), int(round(float(brightness_value))))
            for time_fraction, brightness_value in keyframes
        ]

        if "effect" in glyph and glyph["effect"]["name"] == "Fade":
            new_settings  = {**glyph["effect"]["settings"], "keyframes": clean_keyframes}
            updated_glyph = GlyphEffects.apply_visual_effect(glyph, "Fade", new_settings)

            self.composition.replace_glyph(glyph_identifier, updated_glyph)

            return

        updated_glyph = copy.deepcopy(glyph)
        updated_glyph.pop("brightness", None)
        updated_glyph["keyframes"] = clean_keyframes
        updated_glyph["easing"]    = glyph.get("easing", "linear")

        self.composition.replace_glyph(glyph_identifier, updated_glyph)