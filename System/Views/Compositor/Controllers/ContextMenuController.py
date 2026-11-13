from __future__ import annotations

from loguru import logger

from PyQt6.QtGui import QContextMenuEvent

from PyQt6.QtCore import (
    Qt,
    QPoint,
    QTimer,
    QObject,
    pyqtSignal
)

from System.Common import Constants

from System.Services import (
    Player,
    GlyphEffects
)

from System.Interface import (
    Menu,
    Widgets,
    Windows
)

from .. import Timeline

# Context Menu Controller

class ContextMenuController(QObject):
    context_menu_opened       = pyqtSignal()
    dialog_cancelled          = pyqtSignal(str)
    delete_requested          = pyqtSignal()
    copy_requested            = pyqtSignal()
    paste_requested           = pyqtSignal()
    cut_requested             = pyqtSignal()
    modify_property_requested = pyqtSignal(str, object)
    apply_effect_requested    = pyqtSignal(str, dict, list)
    apply_segments_requested  = pyqtSignal(list, list)
    reset_segments_requested  = pyqtSignal()

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor = conductor

    # Event Handling

    def handle_context_menu(self, event: QContextMenuEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            return

        try:
            scene_position = self.conductor.mapToScene(event.pos())

            items_at_pos     = self.conductor.scene.items(scene_position)
            item_under_mouse = next(
                (item for item in items_at_pos if isinstance(item, Widgets.GlyphItem)),
                None
            )

            if not item_under_mouse:
                return

            if not item_under_mouse.isSelected():
                self.conductor.scene.clearSelection()
                item_under_mouse.setSelected(True)

            selected_items = [
                item
                for item in self.conductor.scene.selectedItems()
                if isinstance(item, Widgets.GlyphItem)
            ]

            selected_ids = [item.glyph_id for item in selected_items]

            clicked_glyph = self.conductor.composition.get_glyph(item_under_mouse.glyph_id)

            if not clicked_glyph:
                return

            current_pan = self.calculate_window_pan(event.globalPos())

            Player.ui_player.play_sound(
                "Controls/ContextMenu/Open",
                pan         = current_pan,
                setting_key = "context_menu_sounds"
            )

            self.context_menu_opened.emit()
            self.conductor.update()

            preview_glyph, segment_count, bpm, model = self.resolve_preview_parameters(
                selected_ids,
                clicked_glyph
            )

            effects, can_show_segments = self.resolve_effect_options(
                selected_ids,
                selected_items
            )

            effect_entries = [
                self.make_effect_entry(
                    effect_name   = effect_name,
                    config        = config,
                    preview_glyph = preview_glyph,
                    selected_ids  = selected_ids,
                    bpm           = bpm,
                    model         = model,
                    segment_count = segment_count
                )
                for effect_name, config in effects.items()
            ]

            entries: list = [
                ("Delete",               self.delete_requested.emit),
                ("Copy",                 self.copy_requested.emit),
                ("Paste",                self.paste_requested.emit),
                ("Cut",                  self.cut_requested.emit),
                ("-",                    None),
                ("Change Brightness...", lambda: QTimer.singleShot(0, self.brightness_control_popup)),
                ("Change Duration...",   lambda: QTimer.singleShot(0, self.duration_control_popup)),
                ("-",                    None),
                ("Effect",               effect_entries)
            ]

            if can_show_segments:
                entries.append(
                    (
                        "Segments...",
                        lambda: QTimer.singleShot(0, self.segment_control_popup)
                    )
                )

            device = Constants.DEVICES[self.conductor.composition.model]

            all_tracks_support_segments = all(
                device.can_edit_track_segments(item.track)
                for item in selected_items
            )

            has_custom_segments = any(
                GlyphEffects.is_segment_edited(glyph)
                for glyph_id in selected_ids
                if (glyph := self.conductor.composition.get_glyph(glyph_id)) is not None
            )

            if all_tracks_support_segments and has_custom_segments:
                entries.append(
                    (
                        "Reset segments",
                        lambda: QTimer.singleShot(0, self.reset_segments_requested.emit)
                    )
                )

            menu = Menu.ContextMenu(
                entries,
                self.conductor,
                pan = current_pan
            )
            menu.exec(event.globalPos())
            menu.deleteLater()

        except Exception as error:
            logger.error(f"Context menu error: {error}")

            Windows.ErrorWindow(
                "Context Menu Error",
                "An unexpected error occurred while opening the context menu."
            ).exec()

    # Preview Resolution

    def resolve_preview_parameters(
            self,
            selected_ids:  list[int],
            clicked_glyph: dict
        ) -> tuple[dict, int, float | int, str]:

        composition = self.conductor.composition
        device      = Constants.DEVICES[composition.model]

        selected_glyphs = [
            glyph
            for glyph_id in selected_ids
            if (glyph := composition.get_glyph(glyph_id)) is not None
        ]

        if not selected_glyphs:
            selected_glyphs = [clicked_glyph]

        def get_glyph_track_segment_count(glyph_dictionary: dict) -> int:
            segment_count = device.get_track_segment_count(glyph_dictionary["track"])

            return segment_count if segment_count else 0

        has_unsegmented_glyph = any(
            get_glyph_track_segment_count(glyph_dictionary) == 0
            for glyph_dictionary in selected_glyphs
        )

        bpm   = composition.bpm if composition.bpm else 120
        model = composition.model

        if has_unsegmented_glyph:
            unsegmented_glyph = next(
                (
                    glyph_dictionary
                    for glyph_dictionary in selected_glyphs
                    if get_glyph_track_segment_count(glyph_dictionary) == 0
                ),
                clicked_glyph
            )

            return unsegmented_glyph, 1, bpm, model

        segment_counts = [
            get_glyph_track_segment_count(glyph_dictionary)
            for glyph_dictionary in selected_glyphs
        ]

        if len(set(segment_counts)) == 1:
            return clicked_glyph, segment_counts[0], bpm, model

        clicked_count = get_glyph_track_segment_count(clicked_glyph)

        if clicked_count > 0:
            return clicked_glyph, clicked_count, bpm, model

        return selected_glyphs[0], segment_counts[0], bpm, model

    # Pan Calculation

    def calculate_window_pan(self, global_position: QPoint) -> float:
        window = self.conductor.window()

        if not window:
            return 0.0

        window_rectangle = window.geometry()

        if window_rectangle.width() <= 0:
            return 0.0

        relative_x = (global_position.x() - window_rectangle.x()) / window_rectangle.width()

        return max(-1.0, min(1.0, relative_x * 2.0 - 1.0))

    # Effect Resolution

    def resolve_effect_options(
            self,
            selected_ids:   list[int],
            selected_items: list[Widgets.GlyphItem]
        ) -> tuple[dict, bool]:

        if not selected_ids or not selected_items:
            return {}, False

        glyphs = [
            glyph
            for glyph_id in selected_ids
            if (glyph := self.conductor.composition.get_glyph(glyph_id)) is not None
        ]

        if not glyphs:
            return {}, False

        device = Constants.DEVICES[self.conductor.composition.model]

        has_custom_segments = any(
            GlyphEffects.is_segment_edited(glyph)
            for glyph in glyphs
        )

        first_track = selected_items[0].track
        same_track  = all(item.track == first_track for item in selected_items)

        if not same_track:
            available = GlyphEffects.get_non_segmented_effects()

            return available, False

        return GlyphEffects.get_effects_for_track(device, first_track, has_custom_segments)

    def make_effect_entry(
            self,
            effect_name:   str,
            config:        dict,
            preview_glyph: dict,
            selected_ids:  list[int],
            bpm:           float | int,
            model:         str,
            segment_count: int
        ) -> tuple[str, list]:

        preview = Menu.EffectPreviewWidget(
            effect_name   = effect_name,
            config        = config,
            glyph         = preview_glyph,
            bpm           = bpm,
            model         = model,
            segment_count = segment_count
        )

        preview.apply_requested.connect(
            lambda name, settings: self.apply_effect_requested.emit(
                name,
                settings,
                selected_ids
            )
        )

        return (
            effect_name,
            [
                ("Preview", preview)
            ]
        )

    # Popups

    def control_popup(
            self,
            title:     str,
            label:     str,
            key:       str,
            min_value: int        = 1,
            max_value: int | None = None
        ) -> None:

        dialog = Windows.DialogInputWindow(
            title,
            label,
            min_value,
            max_value
        )

        if not dialog.exec():
            self.dialog_cancelled.emit(key)

            return

        self.modify_property_requested.emit(key, dialog.get_text())

    def brightness_control_popup(self) -> None:
        self.control_popup("Brightness", "Percent", "brightness", max_value = 100)

    def duration_control_popup(self) -> None:
        self.control_popup("Duration", "Duration (ms)", "duration", min_value = 1, max_value = 10000)

    def segment_control_popup(self) -> None:
        selected_items = [
            item
            for item in self.conductor.scene.selectedItems()
            if isinstance(item, Widgets.GlyphItem)
        ]
        selected_ids = [item.glyph_id for item in selected_items]

        if not selected_ids:
            return

        first_id    = selected_ids[0]
        first_glyph = self.conductor.composition.get_glyph(first_id)

        if not first_glyph:
            return

        device      = Constants.DEVICES[self.conductor.composition.model]
        track_count = device.get_track_segment_count(first_glyph["track"])

        if not track_count:
            return

        if device.is_matrix and device.is_master_track(first_glyph["track"]):
            popup = Windows.MatrixSegmentEditor(
                "Segments",
                device,
                first_glyph.get("segments"),
                first_glyph.get("segment_levels")
            )

        else:
            popup = Windows.SegmentEditor(
                "Segments",
                track_count,
                first_glyph.get("segments"),
                first_glyph.get("segment_levels")
            )

        if not popup.exec():
            return

        self.apply_segments_requested.emit(selected_ids, popup.segments())