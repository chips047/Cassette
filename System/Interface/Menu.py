from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System.Common import Styles
from System.Common.Constants import *

from System.Components import GlyphEffects

from loguru import logger

from System.Interface import Inputs
from System.Interface import Basic
from System.Interface import Widgets

class ContextMenu(QMenu):
    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setStyleSheet(Styles.Menus.RMB_element)
        
        self._apply_styling(self)
        self._populate(self, entries)

    def _apply_styling(self, menu: QMenu):
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        menu.setWindowFlags(
            menu.windowFlags() | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.NoDropShadowWindowHint
        )

    def _populate(self, parent_menu: QMenu, entries: list):
        logger.debug("Populating Context Menu:")

        for label, handler in entries:
            logger.debug(f"Adding entry: {label}")
            self._add_entry(parent_menu, label, handler)

    def _add_entry(self, menu: QMenu, label: str, handler):
        if label == "-":
            menu.addSeparator()
            return

        if isinstance(handler, list):
            submenu = menu.addMenu(label)
            self._apply_styling(submenu)
            self._populate(submenu, handler)
            
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

    def exec_and_cleanup(self, global_pos):
        try:
            logger.debug("Showing Context Menu")
            return self.exec(global_pos)
        
        finally:
            self.deleteLater()

class EffectPreviewWidget(QWidget):
    apply_requested = pyqtSignal(str, dict)

    def __init__(self, effect_name, config, glyph, parent=None):
        super().__init__(parent)
        self.effect_name = effect_name
        self.config = config
        self.glyph = glyph
        self.controls = {}
        
        self.effect_info = GlyphEffects.EffectsConfig.get(self.effect_name, {})

        self.setup_ui()
        self.populate_controls()
        self.on_control_changed()

        logger.debug(f"Created Effect Previewer for {effect_name}")

    def setup_ui(self):
        self.setFixedWidth(500)
        self.setStyleSheet(Styles.Controls.EffectSetupper)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(15)

        self.live_preview_bar = Widgets.ScheduledSegmentedBar(30, loop = True)
        self.main_layout.addWidget(self.live_preview_bar)

        self.apply_button = Basic.NothingButton("Apply")
        self.apply_button.clicked.connect(self.on_apply)

    def populate_controls(self):
        types_map = {
            "checkbox": (Inputs.Checkbox, "stateChanged"),
            "slider":   (Inputs.SliderWithLabel, "valueChanged"),
            "selector": (Inputs.SelectorWithLabel, "selectionChanged")
        }

        logger.debug(f"Populating controls for Effect {self.effect_name}")

        for item in self.effect_info.get("settings", []):
            logger.debug(f"Adding control: {item['title']}")
            itype = item.get("type")

            widget_class, signal_name = types_map[itype]
            
            if itype == "slider":
                widget = widget_class(item["title"], item["min"], item["max"], item["default"])
                change_signal = widget.slider.valueChanged 
            
            elif itype == "selector":
                widget = widget_class(item["title"], item["map"], item["default"])
                change_signal = getattr(widget, signal_name)
            
            elif itype == "checkbox":
                widget = widget_class(item["title"], item["default"])
                change_signal = getattr(widget, signal_name)

            change_signal.connect(self.on_control_changed)
            
            self.main_layout.addWidget(widget)
            self.controls[item["key"]] = widget

        self.main_layout.addWidget(self.apply_button)

    def get_settings(self):
        settings = {}
        
        for key, widget in self.controls.items():
            if isinstance(widget, Inputs.Checkbox):
                settings[key] = widget.isChecked()
            
            elif isinstance(widget, Inputs.SliderWithLabel):
                settings[key] = widget.value()
            
            elif isinstance(widget, Inputs.SelectorWithLabel):
                settings[key] = widget.currentData()
        
        return settings

    def _generate_effect_track(self):
        logger.debug("Setting new effect track...")

        settings = self.get_settings()

        glyph = GlyphEffects.generate_glyph_dict(
            duration = max(self.glyph["duration"], 3000),
            brightness = self.glyph["brightness"]
        )

        track_data = GlyphEffects.effect_to_glyph(
            GlyphEffects.effectCallback(self.effect_name, settings, glyph),
            60,
            "PREVIEW"
        )

        self.live_preview_bar.set_schedule(track_data)

    def on_control_changed(self, *args):
        self.apply_button.setText("Apply")
        self.apply_button.setDisabled(False)

        self._generate_effect_track()

    def on_apply(self):
        self.apply_button.setText("Applied")
        self.apply_button.setDisabled(True)

        self.apply_requested.emit(self.effect_name, self.get_settings())

    def showEvent(self, event):
        super().showEvent(event)

        logger.debug(f"Starting Effect Visualizer on {self.effect_name}")
        self.live_preview_bar.play()

    def hideEvent(self, event):
        super().hideEvent(event)

        logger.debug(f"Stopping Effect Visualizer on {self.effect_name}")
        self.live_preview_bar.stop()

    def mousePressEvent(self, event):
        event.accept()