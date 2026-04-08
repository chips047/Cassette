from __future__ import annotations

from loguru import logger

from PyQt5.QtGui import QIcon

from PyQt5.QtCore import (
    Qt,
    pyqtSignal
)

from PyQt5.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout
)

from . import Timeline

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Services import (
    Player,
    ProjectSaver
)

from System.Interface import (
    Basic,
    Inputs,
    Windows,
    Widgets
)

class CompositorWidget(QWidget):
    back_to_main_menu_requested = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet("background-color: #1e1e1e;")

        self.playback_manager = Player.player

        self.overall_layout = QVBoxLayout(self)
        self.overall_layout.setContentsMargins(10, 10, 10, 10)
        self.overall_layout.setSpacing(10)

        self.build_controls()
        self.setup_layout()
        self.connect_signals()
        self.configure_focus()

    # Setup

    def build_controls(self) -> None:
        self.top_control_bar_widget = QWidget()
        self.top_control_bar_layout = QHBoxLayout(self.top_control_bar_widget)
        self.top_control_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.top_control_bar_layout.setSpacing(10)

        self.eject_button        = Basic.Button("Eject")
        self.export_button       = Basic.NothingButton("Export")
        self.top_status_label    = QLabel(Constants.STATUS_BAR_DEFAULT)
        self.mini_preview_widget = Widgets.MiniWaveformPreview()

        self.glyph_dur_control = Inputs.DraggableValueControl(
            QIcon("System/Assets/Icons/Compositor/Duration.png"),
            "duration", 100, 5, 5000, 5, "ms"
        )
        
        self.brightness_control = Inputs.DraggableValueControl(
            QIcon("System/Assets/Icons/Compositor/Brightness.png"),
            "brightness", 100, 5, 100, 5, "%"
        )
        
        self.playspeed_button = Inputs.CycleButton(
            QIcon("System/Assets/Icons/Compositor/Speed.png"),
            "speed", [("1x", 1.0), ("0.5x", 0.5), ("0.2x", 0.2)]
        )
        
        self.default_effect = Inputs.CycleButton(
            QIcon("System/Assets/Icons/Compositor/Effect.png"),
            "effect", [
                ("None", "none"),
                ("Fade out", "fade_out"),
                ("Fade in", "fade_in"),
                ("Fade in out", "fade_in_out")
            ]
        )

        self.top_status_label.setFont(Utils.NDot(14))
        self.top_status_label.setMinimumHeight(Styles.Metrics.ElementHeight)
        self.top_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.top_status_label.setStyleSheet(Styles.Other.StatusBar)

    def setup_layout(self) -> None:
        bar = self.top_control_bar_layout
        
        bar.addWidget(self.eject_button)
        bar.addWidget(self.mini_preview_widget, 1)
        bar.addWidget(self.glyph_dur_control)
        bar.addWidget(self.brightness_control)
        bar.addWidget(self.playspeed_button)
        bar.addWidget(self.default_effect)
        bar.addWidget(self.export_button)

        self.overall_layout.addWidget(self.top_control_bar_widget)
        self.overall_layout.addWidget(self.top_status_label)

        self.content_widget = Timeline.ScrollableContent(self)
        self.overall_layout.addWidget(self.content_widget)

    def connect_signals(self) -> None:
        self.export_button.clicked.connect(self.export_ringtone)
        self.eject_button.clicked.connect(self.unload_composition)

        self.playspeed_button.state_changed.connect      (lambda _, speed:  self.playback_manager.set_speed(speed, 2000))
        self.default_effect.state_changed.connect        (lambda _, effect: self.content_widget.composition.set_default_effect(effect))
        self.mini_preview_widget.preview_clicked.connect (                  self.content_widget.scroll_to_normalized_position)
        self.glyph_dur_control.valueChanged.connect      (lambda ms:        self.content_widget.composition.set_duration(ms))
        self.brightness_control.valueChanged.connect     (lambda percent:   self.content_widget.composition.set_brightness(percent))

    def configure_focus(self) -> None:
        for child in self.findChildren(QWidget):
            if child is self.content_widget:
                continue
            
            child.setFocusPolicy(Qt.NoFocus)

        self.content_widget.setFocusPolicy(Qt.StrongFocus)

    # Lifecycle

    def load_composition(self, composition: ProjectSaver.Composition) -> None:
        path = composition.get_playback_audio_path()
        self.playback_manager.load_audio(path)
        self.content_widget.load_composition(composition)

        self.content_widget.playhead_moved.connect(
            self.mini_preview_widget.set_playhead_position
        )
        self.mini_preview_widget.set_audio_data(self.playback_manager.data)

        self.on_elements_changed()
        self.window().activateWindow()
        self.content_widget.check_tutorial()

    def unload_composition(self) -> None:
        logger.warning("Unloading composition from compositor widget and clearing state")

        self.back_to_main_menu_requested.emit()

        if self.playback_manager.is_playing:
            self.content_widget.playhead_timer.stop()
            self.playback_manager.set_speed(0.0, 3000, Player.Easing.ease_out_quart)

        self.content_widget.composition.syncer.stop()

        self.content_widget.playhead_moved.disconnect(self.mini_preview_widget.set_playhead_position)

        self.mini_preview_widget.audio_data = None

        self.default_effect.reset()
        self.playspeed_button.reset()
        self.glyph_dur_control.reset()
        self.brightness_control.reset()

    # Misc

    def export_ringtone(self) -> None:
        Windows.ExportDialogWindow(
            self.content_widget.composition,
            self.content_widget.composition.bpm,
            self.playback_manager
        ).exec_()

    def on_elements_changed(self) -> None:
        has_glyphs = bool(self.content_widget.glyph_controller.glyph_items)
        self.export_button.setEnabled(has_glyphs)

    @staticmethod
    def open_playground_window() -> None:
        Windows.Playground().exec_()