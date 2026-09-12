from __future__ import annotations

from loguru import logger

from PyQt6.QtGui import QContextMenuEvent

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPoint,
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

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor = conductor

    # Event Handling

    def handle_context_menu(self, event: QContextMenuEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            return

        try:
            scene_position   = self.conductor.mapToScene(event.pos())
            item_under_mouse = self.conductor.scene.itemAt(scene_position, self.conductor.transform())

            if not isinstance(item_under_mouse, Widgets.GlyphItem):
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
                "Menu/Open",
                pan         = current_pan,
                setting_key = "context_menu_sounds"
            )

            self.context_menu_opened.emit()
            self.conductor.update()

            effects, can_show_segments = self.resolve_effect_options(
                selected_ids,
                selected_items
            )

            effect_entries = [
                self.make_effect_entry(
                    effect_name,
                    config,
                    clicked_glyph,
                    selected_ids
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

        has_non_segmented = any(
            not device.get_track_segment_count(glyph["track"])
            for glyph in glyphs
        )

        has_segmented = all(
            device.get_track_segment_count(glyph["track"])
            for glyph in glyphs
        )

        has_custom_segments = any(
            GlyphEffects.is_segment_edited(glyph)
            for glyph in glyphs
        )

        first_track = selected_items[0].track
        same_track  = all(item.track == first_track for item in selected_items)

        can_show_segments = has_segmented and same_track

        if has_non_segmented:
            effects = GlyphEffects.get_non_segmented_effects()

        elif has_custom_segments:
            effects = GlyphEffects.get_segmentation_supported_effects()

        else:
            effects = GlyphEffects.get_all_effects()

        return effects, can_show_segments

    def make_effect_entry(
            self,
            effect_name:   str,
            config:        dict,
            clicked_glyph: dict,
            selected_ids:  list[int]
        ) -> tuple[str, list]:

        preview = Menu.EffectPreviewWidget(
            effect_name,
            config,
            clicked_glyph
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

        popup = Windows.SegmentEditor(
            "Segments",
            track_count,
            first_glyph.get("segments")
        )

        if not popup.exec():
            return

        self.apply_segments_requested.emit(selected_ids, popup.segments())