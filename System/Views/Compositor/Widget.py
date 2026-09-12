
from __future__ import annotations

from loguru import logger

from PyQt6.QtGui import QIcon

from PyQt6.QtCore import (
    Qt,
    QTimer,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout
)

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
    Widgets,
    Windows
)

from . import Timeline

class CompositorWidget(QWidget):
    back_to_main_menu_requested = pyqtSignal()
    loading_finished            = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet("background-color: #1e1e1e;")

        self.playback_manager = Player.player

        self.is_ejecting                   = False
        self.pending_mini_preview_position = None

        self.overall_layout = QVBoxLayout(self)
        self.overall_layout.setContentsMargins(8, 8, 8, 8)
        self.overall_layout.setSpacing(8)

        self.build_controls()
        self.setup_layout()
        self.connect_signals()
        self.configure_focus()

    # Setup

    def build_controls(self) -> None:
        self.top_control_bar_widget = QWidget()
        self.top_control_bar_layout = QHBoxLayout(self.top_control_bar_widget)
        self.top_control_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.top_control_bar_layout.setSpacing(8)

        self.eject_button        = Widgets.Button("Eject")
        self.export_button       = Widgets.NothingButton("Export")
        self.top_status_label    = QLabel(Constants.STATUS_BAR_DEFAULT)
        self.mini_preview_widget = Widgets.MiniWaveformPreview()

        self.glyph_dur_control = Widgets.DraggableValueControl(
            QIcon("System/Assets/Icons/Compositor/Duration.png"),
            "duration",
            100,
            5,
            5000,
            5,
            "ms"
        )

        self.brightness_control = Widgets.DraggableValueControl(
            QIcon("System/Assets/Icons/Compositor/Brightness.png"),
            "brightness",
            100,
            5,
            100,
            5,
            "%"
        )

        self.playspeed_button = Widgets.CycleButton(
            QIcon("System/Assets/Icons/Compositor/Speed.png"),
            "speed",
            [("1x", 1.0), ("0.5x", 0.5), ("0.2x", 0.2)]
        )

        self.default_effect = Widgets.CycleButton(
            QIcon("System/Assets/Icons/Compositor/Effect.png"),
            "effect",
            [
                ("None", "none"),
                ("Fade out", "fade_out"),
                ("Fade in", "fade_in"),
                ("Fade in out", "fade_in_out")
            ]
        )

        self.top_status_label.setFont(Utils.NDot(11))
        self.top_status_label.setMinimumHeight(Styles.Metrics.ElementHeight)
        self.top_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.top_status_label.setStyleSheet(Styles.Other.StatusBar)

    def setup_layout(self) -> None:
        control_bar = self.top_control_bar_layout

        control_bar.addWidget(self.eject_button)
        control_bar.addWidget(self.mini_preview_widget, 1)
        control_bar.addWidget(self.glyph_dur_control)
        control_bar.addWidget(self.brightness_control)
        control_bar.addWidget(self.playspeed_button)
        control_bar.addWidget(self.default_effect)
        control_bar.addWidget(self.export_button)

        self.overall_layout.addWidget(self.top_control_bar_widget)
        self.overall_layout.addWidget(self.top_status_label)

        self.content_widget = Timeline.ScrollableContent(self)
        self.overall_layout.addWidget(self.content_widget)

    def connect_signals(self) -> None:
        self.export_button.clicked.connect(self.export_ringtone)
        self.eject_button.clicked.connect(self.unload_composition)

        self.playspeed_button.state_changed.connect(self.on_playspeed_state_changed)
        self.default_effect.state_changed.connect(self.on_default_effect_changed)

        self.content_widget.playhead_moved_normalized.connect(self.on_playhead_position_changed)
        self.content_widget.speed_cycle_requested.connect(self.playspeed_button.next_state)
        self.content_widget.playground_requested.connect(self.open_playground_window)

        self.mini_preview_widget.preview_clicked.connect(self.content_widget.scroll_to_normalized_position)
        self.glyph_dur_control.valueChanged.connect(self.on_duration_control_changed)
        self.brightness_control.valueChanged.connect(self.on_brightness_control_changed)

        Player.bpm_informer.beat_4.connect(self.apply_mini_preview_position)

    def configure_focus(self) -> None:
        for child_widget in self.findChildren(QWidget):
            if child_widget is self.content_widget:
                continue

            child_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.content_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # Slots

    def on_playspeed_state_changed(
            self,
            state_index: int,
            speed_value: float
        ) -> None:
        self.playback_manager.set_speed(speed_value, 700)
        self.content_widget.speed_control_used.emit()

    def on_default_effect_changed(
            self,
            state_index:  int,
            effect_value: str
        ) -> None:
        if not self.content_widget.composition:
            return

        self.content_widget.composition.set_default_effect(effect_value)

    def on_duration_control_changed(self, duration_ms: int) -> None:
        if not self.content_widget.composition:
            return

        self.content_widget.composition.set_duration(duration_ms)

    def on_brightness_control_changed(self, brightness_percent: int) -> None:
        if not self.content_widget.composition:
            return

        self.content_widget.composition.set_brightness(brightness_percent)

    # Lifecycle

    def load_composition(self, composition: ProjectSaver.Composition) -> None:
        if self.is_ejecting:
            self.interrupt_eject_and_load(composition)
            return

        self.finish_composition_loading(composition)

    def interrupt_eject_and_load(self, composition: ProjectSaver.Composition) -> None:
        logger.debug("Eject fade interrupted by a new project load, fast-forwarding audio slowdown")

        self.is_ejecting = False

        self.content_widget.playhead_timer.stop()

        self.playback_manager.set_speed(
            0.0,
            Constants.INTERRUPTED_FADE_DURATION_MS,
            Player.Easing.ease_out_quart,
            use_engine_multiplier = False
        )

        QTimer.singleShot(
            Constants.INTERRUPTED_FADE_DURATION_MS,
            lambda: self.finish_composition_loading(composition)
        )

    def finish_composition_loading(self, composition: ProjectSaver.Composition) -> None:
        self.is_ejecting = False

        audio_path = composition.get_playback_audio_path()

        Player.bpm_informer.set_bpm(composition.bpm)
        self.playback_manager.load_audio(audio_path)

        self.content_widget.load_composition(composition)

        self.mini_preview_widget.set_audio_data(self.playback_manager.data)
        self.content_widget.playhead_moved_normalized.connect(self.on_playhead_position_changed)

        self.on_elements_changed()

        self.setEnabled(True)

        self.loading_finished.emit()

        self.window().activateWindow()
        self.content_widget.check_tutorial()

    def unload_composition(self) -> None:
        logger.warning("Unloading composition from compositor widget and clearing state")

        self.close_active_tutorial()

        self.setEnabled(False)

        self.back_to_main_menu_requested.emit()

        if self.playback_manager.is_playing:
            self.is_ejecting = True

            self.content_widget.playhead_timer.stop()
            self.playback_manager.set_speed(
                0.0,
                Constants.EJECT_FADE_DURATION_MS,
                Player.Easing.ease_out_quart,
                use_engine_multiplier = True
            )

            animation_multiplier = Constants.current_settings.get("animation_multiplier", 1.0)
            scaled_fade_duration = int(Constants.EJECT_FADE_DURATION_MS * animation_multiplier)

            QTimer.singleShot(scaled_fade_duration, self.clear_ejecting_flag)

        self.content_widget.composition.syncer.stop()

        self.content_widget.playhead_moved_normalized.disconnect(self.on_playhead_position_changed)
        self.pending_mini_preview_position = None

        self.mini_preview_widget.audio = None
        self.mini_preview_widget.set_playhead_position(0.0)

        self.default_effect.reset()
        self.playspeed_button.reset()
        self.glyph_dur_control.reset()
        self.brightness_control.reset()

    def clear_ejecting_flag(self) -> None:
        self.is_ejecting = False

    def close_active_tutorial(self) -> None:
        tutorial = self.content_widget.tutorial_window

        if tutorial is None:
            return

        tutorial.eject_close()
        self.content_widget.tutorial_window = None

    def on_playhead_position_changed(self, normalized_position: float) -> None:
        current_position = self.pending_mini_preview_position

        if current_position is None:
            current_position = self.mini_preview_widget.playhead_position

        preview_width = max(1, self.mini_preview_widget.width())
        threshold     = 1.0 / float(preview_width)

        if abs(normalized_position - current_position) < threshold:
            return

        self.pending_mini_preview_position = normalized_position

    def apply_mini_preview_position(self) -> None:
        if self.pending_mini_preview_position is None:
            return

        target_position                    = self.pending_mini_preview_position
        self.pending_mini_preview_position = None
        self.mini_preview_widget.set_playhead_position(target_position)

    # Misc

    def export_ringtone(self) -> None:
        Windows.ExportDialogWindow(self.content_widget.composition).exec()

    def on_elements_changed(self) -> None:
        has_glyphs = bool(self.content_widget.glyph_controller and self.content_widget.glyph_controller.glyph_items)
        self.export_button.setEnabled(has_glyphs)

    @staticmethod
    def open_playground_window() -> None:
        Windows.Playground().exec()