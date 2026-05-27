from PyQt6.QtCore import (
    Qt,
    pyqtSignal
)

from PyQt6.QtGui import (
    QAction,
    QHideEvent,
    QShowEvent
)

from PyQt6.QtWidgets import (
    QMenu,
    QWidget,
    QVBoxLayout,
    QWidgetAction
)

from loguru import logger

from System.Common import Styles

from System.Services import (
    Player,
    GlyphEffects
)

from System.Interface import (
    Basic,
    Inputs,
    Widgets
)

class ContextMenu(QMenu):
    def __init__(
        self,
        entries: list,
        parent:  QWidget | None = None
    ) -> None:

        super().__init__(parent)

        self.entries = entries

        self.setStyleSheet(Styles.Menus.ContextMenu)
        
        self.apply_styling(self)
        self.populate(self, self.entries)
        
        self.aboutToHide.connect(self.close_sound)

    def apply_styling(self, menu: QMenu) -> None:
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        menu.setWindowFlags(
            menu.windowFlags()        |
            Qt.WindowType.FramelessWindowHint    |
            Qt.WindowType.NoDropShadowWindowHint
        )

    def populate(
        self,
        menu:    QMenu,
        entries: list
    ) -> None:

        logger.debug("Populating Context Menu:")

        for label, handler in entries:
            logger.debug(f"Adding entry: {label}")
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
    
    def close_sound(self) -> None:
        Player.ui_player.play_sound("Menu/Close")

class EffectPreviewWidget(QWidget):
    apply_requested: pyqtSignal = pyqtSignal(str, dict)

    def __init__(
        self,
        effect_name: str,
        config:      dict,
        glyph:       dict,
        parent:      QWidget | None = None
    ) -> None:

        super().__init__(parent)

        self.effect_name = effect_name
        self.config      = config
        self.glyph       = glyph
        self.controls    = {}

        self.effect_info: dict = GlyphEffects.EffectsConfig.get(self.effect_name, {})

        self.setup_ui()
        self.populate_controls()
        self.on_control_changed()

        logger.debug(f"Created Effect Previewer for {effect_name}")

    def setup_ui(self) -> None:
        self.setFixedWidth(400)
        self.setStyleSheet(Styles.Controls.EffectSetupper)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(12)

        self.live_preview_bar = Widgets.ScheduledSegmentedBar(30, loop = True)
        self.main_layout.addWidget(self.live_preview_bar)

        self.apply_button = Basic.NothingButton("Apply")
        self.apply_button.clicked.connect(self.on_apply)

    def populate_controls(self) -> None:
        types_map = {
            "checkbox": (Inputs.Checkbox,          "stateChanged"),
            "slider":   (Inputs.SliderWithLabel,   "valueChanged"),
            "selector": (Inputs.SelectorWithLabel, "selectionChanged")
        }

        logger.debug(f"Populating controls for Effect {self.effect_name}")

        for item in self.effect_info["settings"]:
            logger.debug(f"Adding control: {item['title']}")

            item_type = item.get("type")
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

    def get_settings(self) -> dict:
        settings = {}

        for key, widget in self.controls.items():
            if isinstance(widget, Inputs.Checkbox):
                settings[key] = widget.isChecked()

            elif isinstance(widget, Inputs.SliderWithLabel):
                settings[key] = widget.value()

            elif isinstance(widget, Inputs.SelectorWithLabel):
                settings[key] = widget.currentData()

        return settings

    def generate_effect_track(self) -> None:
        logger.debug("Setting new effect track...")

        settings = self.get_settings()

        glyph = GlyphEffects.generate_glyph_dict(
            duration   = max(self.glyph["duration"], 3000),
            brightness = self.glyph["brightness"]
        )

        track_data = GlyphEffects.effect_to_glyph(
            GlyphEffects.apply_visual_effect(glyph, self.effect_name, settings),
            60,
            "PREVIEW"
        )

        self.live_preview_bar.set_schedule(track_data)

    def on_control_changed(self, *args) -> None:
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
        self.live_preview_bar.play()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)

        logger.debug(f"Stopping Effect Visualizer on {self.effect_name}")
        self.live_preview_bar.stop()