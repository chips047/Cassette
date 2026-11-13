from __future__ import annotations

from loguru import logger

from PyQt6.QtCore import (
    Qt,
    pyqtSignal
)

from PyQt6.QtGui import (
    QAction,
    QHideEvent,
    QShowEvent,
    QMouseEvent,
    QGuiApplication
)

from PyQt6.QtWidgets import (
    QMenu,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidgetAction
)

from System.Common import (
    Dev,
    Styles,
    Constants
)

from System.Services import (
    Player,
    GlyphEffects
)

from System.Interface import Widgets

@Dev.track_ram
class ContextMenu(QMenu):
    def __init__(
            self,
            entries: list,
            parent:  QWidget | None = None,
            pan:     float          = 0.0
        ) -> None:

        super().__init__(parent)

        self.entries = entries
        self.pan     = pan

        self.setStyleSheet(Styles.Menus.ContextMenu)
        self.apply_styling(self)
        self.populate(self, self.entries)

        self.aboutToHide.connect(self.close_sound)

    # Styling

    def apply_styling(self, menu: QMenu) -> None:
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        menu.setWindowFlags(
            menu.windowFlags()                |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint
        )

    # Menu Construction

    def populate(
            self,
            menu:    QMenu,
            entries: list
        ) -> None:

        for label, handler in entries:
            self.add_entry(menu, label, handler)

    def add_entry(
            self,
            menu:    QMenu,
            label:   str,
            handler: object
        ) -> None:

        if label == "-":
            menu.addSeparator()

            return

        if isinstance(handler, list):
            submenu = menu.addMenu(label)
            self.apply_styling(submenu)
            self.populate(submenu, handler)

            return

        if isinstance(handler, QWidget):
            action = QWidgetAction(menu)
            action.setDefaultWidget(handler)
            menu.addAction(action)

            return

        action = QAction(label, menu)

        if callable(handler):
            action.triggered.connect(handler)

        else:
            action.setEnabled(False)

        menu.addAction(action)

    # Audio Feedback

    def close_sound(self) -> None:
        Player.ui_player.play_sound(
            "Controls/ContextMenu/Close",
            pan         = self.pan,
            setting_key = "context_menu_sounds"
        )

@Dev.track_ram
class EffectPreviewWidget(QWidget):
    apply_requested = pyqtSignal(str, dict)

    def __init__(
            self,
            effect_name:   str,
            config:        dict,
            glyph:         dict,
            bpm:           float | int    = 120,
            model:         str | None     = None,
            segment_count: int            = 1,
            parent:        QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.effect_name   = effect_name
        self.config        = config
        self.glyph         = glyph
        self.bpm           = bpm
        self.model         = model
        self.segment_count = max(1, segment_count)
        self.controls      = {}
        self.effect_info   = GlyphEffects.EffectsConfig.get(self.effect_name, {})

        device                 = Constants.DEVICES.get(self.model) if self.model else None
        is_matrix_device       = bool(device and device.is_matrix)
        is_matrix_effect       = bool(self.effect_info.get("matrix_only", False))
        is_master_track        = bool(device and device.is_master_track(self.glyph["track"]))
        self.is_matrix_preview = is_matrix_device and (is_master_track or is_matrix_effect)
        self.matrix_device     = device

        self.setup_user_interface()
        self.populate_controls()
        self.on_control_changed()

    # User Interface

    def calculate_optimal_matrix_size(self) -> int:
        maximum_width_px = 534
        screen           = QGuiApplication.primaryScreen()
        screen_height_px = screen.availableGeometry().height() if screen else 900
    
        control_items_count = len(self.effect_info.get("settings", []))
        controls_height_px  = control_items_count * 68 + 120
    
        available_vertical_space = screen_height_px - controls_height_px - 80
    
        return max(140, min(maximum_width_px, available_vertical_space))
    
    def setup_user_interface(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
        self.setFixedWidth(550)
        self.setStyleSheet(Styles.Controls.EffectSetupper)
    
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(10)
    
        if self.is_matrix_preview and self.matrix_device:
            optimal_size      = self.calculate_optimal_matrix_size()
            self.live_preview = Widgets.ScheduledMatrixPreview(
                device          = self.matrix_device,
                preview_size_px = optimal_size,
                loop            = True
            )
    
            preview_wrapper = QHBoxLayout()
            preview_wrapper.setContentsMargins(0, 0, 0, 0)
            preview_wrapper.addStretch()
            preview_wrapper.addWidget(self.live_preview)
            preview_wrapper.addStretch()
    
            self.main_layout.addLayout(preview_wrapper)
    
        else:
            self.live_preview = Widgets.ScheduledSegmentedBar(self.segment_count, loop = True)
            self.main_layout.addWidget(self.live_preview)
    
        self.apply_button = Widgets.NothingButton("Apply")
        self.apply_button.clicked.connect(self.on_apply)

    def populate_controls(self) -> None:
        types_map = {
            "checkbox": (Widgets.Checkbox,          "stateChanged"),
            "slider":   (Widgets.SliderWithLabel,   "valueChanged"),
            "selector": (Widgets.SelectorWithLabel, "selectionChanged")
        }

        for item in self.effect_info.get("settings", []):
            item_type                 = item.get("type")
            widget_class, signal_name = types_map[item_type]

            if item_type == "slider":
                widget = widget_class(item["title"], item["min"], item["max"], item["default"])

            elif item_type == "selector":
                widget = widget_class(item["title"], item["map"], item["default"])

            elif item_type == "checkbox":
                widget = widget_class(item["title"], item["default"])

            change_signal = getattr(widget, signal_name)
            change_signal.connect(self.on_control_changed)

            self.main_layout.addWidget(widget)
            self.controls[item["key"]] = widget

        self.main_layout.addWidget(self.apply_button)

    # State and Track Generation

    def get_settings(self) -> dict:
        settings = {}

        for key, widget in self.controls.items():
            if isinstance(widget, Widgets.Checkbox):
                settings[key] = widget.isChecked()

            elif isinstance(widget, Widgets.SliderWithLabel):
                settings[key] = widget.value()

            elif isinstance(widget, Widgets.SelectorWithLabel):
                settings[key] = widget.current_data()

        return settings

    def generate_effect_track(self) -> None:
        settings   = self.get_settings()
        brightness = self.glyph["brightness"] if "brightness" in self.glyph else 100

        preview_glyph = {
            "track":      self.glyph["track"],
            "start":      0,
            "duration":   max(self.glyph["duration"], 3000),
            "brightness": brightness
        }

        if self.segment_count > 1 and "segments" in self.glyph:
            preview_glyph["segments"] = list(self.glyph["segments"])

        applied_glyph = GlyphEffects.apply_visual_effect(
            preview_glyph,
            self.effect_name,
            settings
        )

        track_data = GlyphEffects.effect_to_glyph(
            applied_glyph,
            self.bpm,
            self.model
        )

        self.live_preview.set_schedule(track_data)

    # Event Handlers

    def mousePressEvent(self, event: QMouseEvent) -> None:
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        event.accept()

    def on_control_changed(self, *arguments: object) -> None:
        self.apply_button.setText("Apply")
        self.apply_button.setDisabled(False)

        self.generate_effect_track()

    def on_apply(self) -> None:
        self.apply_button.setText("Applied")
        self.apply_button.setDisabled(True)

        self.apply_requested.emit(self.effect_name, self.get_settings())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)

        logger.debug(f"Starting Effect Visualizer on {self.effect_name}")
        self.live_preview.play()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)

        logger.debug(f"Stopping Effect Visualizer on {self.effect_name}")
        self.live_preview.stop()