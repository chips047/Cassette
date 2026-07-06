import os
import re
import sys
import time
import random
import traceback

from datetime import datetime
from functools import partial

from loguru import logger

logger.debug("Imported standard libraries")

if getattr(sys, "frozen", False):
    base_directory = sys._MEIPASS

else:
    base_directory = os.path.dirname(os.path.abspath(__file__))

os.chdir(base_directory)
sys.path.insert(0, base_directory)

logger.debug(f"Set base directory: {base_directory}")
logger.debug(f"Mode determination: {'Frozen' if getattr(sys, 'frozen', False) else 'Script'}")

from PyQt6.QtCore import (
    Qt,
    QRect,
    QTimer,
    pyqtSlot,
    pyqtSignal,
    pyqtProperty,
    QEasingCurve,
    QPropertyAnimation
)

from PyQt6.QtGui import (
    QIcon,
    QColor,
    QPixmap,
    QPainter,
    QMoveEvent,
    QCloseEvent,
    QPaintEvent,
    QResizeEvent,
    QFontMetrics,
    QFontDatabase,
    QSurfaceFormat
)

from PyQt6.QtWidgets import (
    QWidget,
    QMainWindow,
    QApplication,
    QStackedWidget,
    QGraphicsOpacityEffect
)

logger.debug("Imported PyQt6 modules")

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Interface import (
    Timing,
    Windows
)

from System.Services import (
    Player,
    ProjectSaver
)

from System.Views.ProjectMenu import MainMenu
from System.Views.Compositor import CompositorWidget

logger.debug("Imported system modules")

# Initialization

is_processing_exception = False

def handle_exception(
    exception_type:      object,
    exception_value:     object,
    exception_traceback: object,
) -> None:

    global is_processing_exception

    if is_processing_exception:
        return

    is_processing_exception = True

    try:
        error_message = "".join(
            traceback.format_exception(
                exception_type,
                exception_value,
                exception_traceback,
            )
        )

        if "KeyboardInterrupt" in error_message:
            exit()
            return

        logger.error(f"Uncaught exception: {error_message}\n\n>>> Trying hard to not crash the program <<<")

        title = (
            f"Panic: {exception_value}"
            if random.random() > 0.005
            else "0x000000DEAD"
        )


        Windows.ErrorWindow(
            title,
            error_message,
            "No way"
        ).exec()

    except Exception as failure:
        logger.critical(f"Critical failure in error handler: {failure}\n\nError window may not have been displayed.")

    finally:
        is_processing_exception = False

sys.excepthook = handle_exception

# Logic Classes

class WindowEffectManager:
    CHANCE = 0.005

    STARTUP_DATA = [
        {
            "content": "System/Assets/Image/Anomaly.png",
            "sound": "Packs/NOK/Anomaly",
            "duration": 7500,
            "fade": 200,
        },
        {
            "content": "System/Assets/Image/IEYTD2.png",
            "scale": False,
        },
        {
            "content": "First, there was The Void",
        },
        {
            "content": "The best of the best, still die like the rest",
        },
        {
            "content": "The cake is a lie The cake is a lie The cake is a lie",
        },
        {
            "content": "Please",
            "sound": "Packs/NOK/ThreeTone",
        }
    ]

    def __init__(self, window: QMainWindow) -> None:
        self.window                  = window

        self.shake_sound_count       = 0
        self.shake_threshold         = 1500
        self.last_shake_x_position   = 0
        self.shake_direction         = 0
        self.shake_direction_changes = 0
        self.last_shake_time         = 0

        self.last_area               = window.width() * window.height()
        self.resize_direction        = 0
        self.direction_changes       = 0
        self.last_change_time        = 0
        self.last_accordion_time     = 0
        self.is_accordion_active     = False

        self.accordion_stop_timer = Timing.Timer(
            2000,
            self.reset_accordion_state,
            single_shot = True
        )

        self.shake_stop_timer = Timing.Timer(
            2000,
            self.reset_shake_state,
            single_shot = True
        )

    def process_window_move(
        self,
        horizontal_position: int,
        vertical_position:   int
    ) -> None:

        del vertical_position

        current_time     = time.time()
        horizontal_delta = horizontal_position - self.last_shake_x_position

        self.last_shake_x_position = horizontal_position

        if abs(horizontal_delta) < 5:
            return

        current_direction = 1 if horizontal_delta > 0 else -1

        if current_direction == self.shake_direction:
            return

        if current_time - self.last_shake_time > 0.8:
            self.shake_direction_changes = 0

        self.shake_direction = current_direction
        self.shake_direction_changes += 1
        self.last_shake_time = current_time

        if self.shake_direction_changes < 10:
            return

        self.shake_stop_timer.stop()
        self.shake_stop_timer.start()

        sound_index = min(5, self.shake_direction_changes // 2)

        if sound_index < 1:
            sound_index = random.randint(1, 5)

        Player.ui_player.play_sound(
            f"Packs/NOK/Shake{sound_index}",
            tone_spread = 0.35
        )

        self.shake_sound_count += 1

        if self.shake_sound_count > 50:
            logger.critical("Too much shaking! Emergency exit.")
            self.window.close()

    def process_window_resize(
        self,
        width:  int,
        height: int
    ) -> None:

        current_time = time.time()
        current_area = width * height

        if self.last_accordion_time > 0:
            delta_time = current_time - self.last_accordion_time
        
        else:
            delta_time = 0.01

        area_difference = current_area - self.last_area
        velocity = abs(area_difference) / delta_time

        minimum_velocity = 50000
        maximum_velocity = 2000000

        if abs(area_difference) < 200 or velocity < minimum_velocity:
            self.last_area = current_area
            self.last_accordion_time = current_time
            
            return

        current_direction = 1 if area_difference > 0 else -1

        if current_direction != self.resize_direction:
            self.direction_changes += 1
            self.resize_direction   = current_direction

            if current_time - self.last_change_time > 1.0:
                self.direction_changes = 1

            self.last_change_time = current_time

            if self.direction_changes >= 10:
                self.is_accordion_active = True

        if not self.is_accordion_active:
            self.last_area = current_area
            self.last_accordion_time = current_time
            
            return

        self.accordion_stop_timer.stop()
        self.accordion_stop_timer.start()

        volume = (velocity - minimum_velocity) / (maximum_velocity - minimum_velocity)
        volume = max(0.1, min(1.0, volume))

        sound_type = "Out" if current_direction > 0 else "In"

        Player.ui_player.play_sound(
            f"Packs/NOK/Accordion{sound_type}",
            volume = volume
        )

        self.last_area = current_area
        self.last_accordion_time = current_time

    def reset_accordion_state(self) -> None:
        self.direction_changes   = 0
        self.is_accordion_active = False

    def reset_shake_state(self) -> None:
        self.shake_sound_count       = 0
        self.shake_direction_changes = 0

    def check_calendar_events(self) -> None:
        current_time = datetime.now()

        if current_time.day == 8 and current_time.month == 6:
            Windows.ErrorWindow(
                "Wow!",
                "Today is a vacuum cleaner day! Enjoy!"
            ).exec()

        if current_time.day == 4 and current_time.month == 5:
            Windows.ErrorWindow(
                "><",
                "my birthady, 4 may `:)`"
            ).exec()

    @staticmethod
    def is_image(content: str) -> bool:
        return content.lower().endswith(".png")

    @staticmethod
    def choose_startup_egg() -> dict[str, object] | None:
        if random.random() < WindowEffectManager.CHANCE:
            return random.choice(WindowEffectManager.STARTUP_DATA)

        return None

# UI Components

class StartupFadeOverlay(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.background_opacity = 1.0
        self.current_pixmap     = None
        self.current_text       = None
        self.text_rectangle     = None
        self.font               = None

        self.background_fade_animation = QPropertyAnimation(
            self,
            b"backgroundOpacity"
        )

        self.background_fade_animation.setDuration(700)
        self.background_fade_animation.setStartValue(1.0)
        self.background_fade_animation.setEndValue(0.0)
        self.background_fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.background_fade_animation.finished.connect(self.handle_fade_finished)

    @pyqtProperty(float)
    def backgroundOpacity(self) -> float:
        return self.background_opacity

    @backgroundOpacity.setter
    def backgroundOpacity(self, value: float) -> None:
        self.background_opacity = float(value)
        self.update()

    def start_overlay(self, default_hold_ms: int = 600) -> None:
        logger.debug("Starting startup fade overlay")

        parent_widget = self.parentWidget()

        if parent_widget is None:
            return

        self.setGeometry(parent_widget.rect())
        self.show()
 
        is_new_user = Constants.current_settings.get("_new_user", True)
        hold_time   = default_hold_ms
        self.font   = Utils.NType(30 if is_new_user else 10)

        if is_new_user:
            self.current_text    = "Get ready."
            self.text_rectangle  = self.rect()
            
            Constants.current_settings.set_value("_new_user", False)

            Player.ui_player.play_sound("App/Startup", setting_key = "startup_sound")

            QTimer.singleShot(
                hold_time,
                self.background_fade_animation.start
            )

            return

        startup_egg = WindowEffectManager.choose_startup_egg()

        if startup_egg is None:
            Player.ui_player.play_sound("App/Startup", setting_key = "startup_sound")

            QTimer.singleShot(
                hold_time,
                self.background_fade_animation.start
            )

            return

        content   = startup_egg["content"]
        hold_time = startup_egg.get("duration", default_hold_ms)

        if WindowEffectManager.is_image(content):
            pixmap = QPixmap(content)

            if startup_egg.get("scale", True):
                self.current_pixmap = pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            
            else:
                self.current_pixmap = pixmap

        else:
            self.current_text = content

            metrics      = QFontMetrics(self.font)
            rectangle    = metrics.boundingRect(self.current_text)
            text_width   = rectangle.width() + 20
            text_height  = rectangle.height() + 20
            margin       = 80

            random_x_position = random.randint(
                margin,
                max(margin, self.width() - text_width - margin)
            )

            random_y_position = random.randint(
                margin,
                max(margin, self.height() - text_height - margin)
            )

            self.text_rectangle = QRect(
                random_x_position,
                random_y_position,
                text_width,
                text_height
            )

        if "fade" in startup_egg:
            self.background_fade_animation.setDuration(startup_egg["fade"])

        if "sound" in startup_egg:
            Player.ui_player.play_sound(
                startup_egg["sound"],
                enable_tone_randomizer = False
            )
        
        else:
            Player.ui_player.play_sound("App/Startup", setting_key = "startup_sound")

        QTimer.singleShot(
            hold_time,
            self.background_fade_animation.start
        )

    def handle_fade_finished(self) -> None:
        logger.debug("Startup fade animation finished, closing overlay")

        self.close()
        self.finished.emit()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )

        background_alpha = int(self.background_opacity * 255)

        painter.fillRect(self.rect(), QColor(0, 0, 0, background_alpha))
        painter.setOpacity(self.background_opacity)

        if self.current_pixmap and not self.current_pixmap.isNull():
            center_x = (self.width() - self.current_pixmap.width()) // 2
            center_y = (self.height() - self.current_pixmap.height()) // 2

            painter.drawPixmap(center_x, center_y, self.current_pixmap)

            return

        if self.current_text and self.text_rectangle is not None:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(self.font)
            painter.drawText(self.text_rectangle, Qt.AlignmentFlag.AlignCenter, self.current_text)

class ApplicationWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.effect_manager = WindowEffectManager(self)

        self.setWindowTitle("Cassette")
        self.resize(1000, 640)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.main_menu_widget  = MainMenu(self)
        self.compositor_widget = CompositorWidget(self)

        for widget, opacity in (
            (self.main_menu_widget, 1.0),
            (self.compositor_widget, 0.0)
        ):
            
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(opacity)
            widget.setGraphicsEffect(effect)
            self.stack.addWidget(widget)

        self.main_menu_widget.edit_requested.connect(self.on_edit_requested)
        self.main_menu_widget.composition_created.connect(self.show_compositor_view)
        self.compositor_widget.back_to_main_menu_requested.connect(self.show_main_menu_view)

        self.stack.setCurrentWidget(self.main_menu_widget)
        self.setStyleSheet(f"background-color: {Styles.Colors.Background};")

        self.intro_overlay = StartupFadeOverlay(self)
        self.intro_overlay.finished.connect(self.handle_intro_finished)

        self.is_closing = False

        self.setup_animations()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)

        self.effect_manager.process_window_move(
            event.pos().x(),
            event.pos().y()
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self.effect_manager.process_window_resize(
            event.size().width(),
            event.size().height()
        )

        if self.intro_overlay is None:
            return

        self.intro_overlay.resize(
            event.size().width(),
            event.size().height()
        )
    
    # Actions

    def show_update_info(self, info: dict) -> None:
        version     = info.get("tag_name", "unknown")
        changelog   = info.get("body", "No changelog available.")
        release_url = info.get("html_url", Constants.GITHUB_LINK)

        if version == open(Utils.get_resource_path("version")).read():
            return

        last_notified_version = Constants.current_settings.get("_last_notified_update")

        if version == last_notified_version:
            return

        Windows.UpdateWindow(
            version,
            changelog,
            release_url
        ).exec()

        Constants.current_settings.set_value("_last_notified_update", version)

    # Animations

    def setup_animations(self) -> None:
        self.entry_move_animation  = QPropertyAnimation(None, b"geometry")
        self.entry_fade_animation  = QPropertyAnimation(None, b"opacity")

        self.main_menu_fadeout = QPropertyAnimation(
            self.main_menu_widget.graphicsEffect(),
            b"opacity"
        )

        self.compositor_fadeout = QPropertyAnimation(
            self.compositor_widget.graphicsEffect(),
            b"opacity"
        )

        self.main_menu_fadeout.setDuration(300)
        self.main_menu_fadeout.setStartValue(1.0)
        self.main_menu_fadeout.setEndValue(0.0)
        self.main_menu_fadeout.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.compositor_fadeout.setDuration(300)
        self.compositor_fadeout.setStartValue(1.0)
        self.compositor_fadeout.setEndValue(0.0)
        self.compositor_fadeout.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.entry_move_animation.setDuration(1000)
        self.entry_move_animation.setEasingCurve(QEasingCurve.Type.OutElastic)

        self.entry_fade_animation.setDuration(400)
        self.entry_fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.main_menu_fadeout.finished.connect(self.handle_main_menu_fadeout_finished)
        self.compositor_fadeout.finished.connect(self.handle_compositor_fadeout_finished)

    @pyqtSlot(ProjectSaver.Composition)
    def show_compositor_view(self, composition: ProjectSaver.Composition) -> None:
        self.compositor_widget.load_composition(composition)
        self.main_menu_fadeout.start()

    @pyqtSlot(str)
    def on_edit_requested(self, project_id: str) -> None:
        self.main_menu_fadeout.start()

        QTimer.singleShot(
            1000,
            partial(self.load_project_after_transition, project_id)
        )

    def load_project_after_transition(self, project_id: str) -> None:
        try:
            logger.info(f"Loading project {project_id}...")
            composition = ProjectSaver.Composition(id = project_id)
            self.compositor_widget.load_composition(composition)
            self.show_compositor_view_after_transition()

        except Exception as exception:
            logger.error(f"Failed to load project: {exception}")
            self.restore_main_menu_after_failed_load()

    def restore_main_menu_after_failed_load(self) -> None:
        self.main_menu_widget.setEnabled(True)
        self.animate_widget_entry(self.main_menu_widget)

        Player.ui_player.play_sound(f"Signals/Error/Critical{random.randint(1, 3)}")

    def show_compositor_view_after_transition(self) -> None:
        self.main_menu_widget.setVisible(False)
        self.animate_widget_entry(self.compositor_widget)

        Player.ui_player.play_sound("App/Eject")

    def show_main_menu_view_after_transition(self) -> None:
        self.compositor_widget.setVisible(False)
        self.compositor_widget.content_widget.unload_composition()
        self.animate_widget_entry(self.main_menu_widget)

        Player.ui_player.play_sound("App/Eject")

    @pyqtSlot()
    def handle_main_menu_fadeout_finished(self) -> None:
        if self.compositor_widget.content_widget.composition:
            self.show_compositor_view_after_transition()

    @pyqtSlot()
    def handle_compositor_fadeout_finished(self) -> None:
        self.show_main_menu_view_after_transition()

    @pyqtSlot()
    def show_main_menu_view(self) -> None:
        self.main_menu_widget.setEnabled(True)
        self.compositor_fadeout.start()

    def animate_widget_entry(self, widget: QWidget) -> None:
        self.stack.setCurrentWidget(widget)
        widget.setVisible(True)

        stack_rectangle = self.stack.geometry()
        vertical_offset = 150 

        self.entry_move_animation.setTargetObject(widget)
        self.entry_move_animation.setStartValue(
            QRect(
                stack_rectangle.x(),
                stack_rectangle.y() + vertical_offset,
                stack_rectangle.width(),
                stack_rectangle.height()
            )
        )

        self.entry_move_animation.setEndValue(stack_rectangle)

        self.entry_fade_animation.setTargetObject(widget.graphicsEffect())
        self.entry_fade_animation.setStartValue(0.0)
        self.entry_fade_animation.setEndValue(1.0)

        self.entry_move_animation.start()
        self.entry_fade_animation.start()

    @pyqtSlot()
    def handle_intro_finished(self) -> None:
        self.intro_overlay = None
        self.effect_manager.check_calendar_events()

        self.update_thread = Utils.UpdateChecker()
        self.update_thread.info_received.connect(self.show_update_info)
        self.update_thread.fetch_latest_release()

    # Lifecycle

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.begin_shutdown()

    def close(self) -> None:
        self.begin_shutdown()

    def play_exit_effects(self) -> bool:
        Player.ui_player.play_sound("App/Close", setting_key = "shutdown_sound")

        content = self.compositor_widget.content_widget

        if not content.composition:
            return False
        
        content.glyph_visualizer.exit(False)
        
        return True

    def begin_shutdown(self) -> None:
        if self.is_closing:
            logger.warning("Shutdown already in progress, ignoring additional close request.")
            return

        self.is_closing = True
        self.hide()

        content_widget       = self.compositor_widget.content_widget
        animation_multiplier = Constants.current_settings.get("animation_multiplier", 1.0)

        if content_widget.composition:
            content_widget.composition.syncer.exit_app()
            logger.debug("Signaled Cassette Receiver to exit")

        if Player.player.is_playing and content_widget.global_waveform_max > 1e-6:
            logger.debug("Playing exit effects with audio slowdown")

            Player.player.set_speed(0.0, 3000)

            timeout = int(animation_multiplier * 1700)

            QTimer.singleShot(timeout, self.play_exit_effects)
            QTimer.singleShot(timeout + 1700, self.complete_shutdown)

            return

        duration = int(1800 * animation_multiplier) if self.play_exit_effects() else 1800

        QTimer.singleShot(duration, self.complete_shutdown)

    def complete_shutdown(self) -> None:
        logger.debug("Completing shutdown process, cleaning up resources")

        Player.ui_player.cleanup()
        Player.player.full_shutdown()

        application = QApplication.instance()

        if application is not None:
            logger.debug("Exiting application. Bye.")
            application.quit()

# Main Execution

def main() -> None:
    logger.debug("Configuring OpenGL surface format")

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)

    surface_format = QSurfaceFormat()
    surface_format.setVersion(4, 1)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface_format.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions, False)
    surface_format.setSwapBehavior(QSurfaceFormat.SwapBehavior.TripleBuffer)
    surface_format.setSwapInterval(1)

    logger.debug("Configuring application settings")

    Constants.prepare_default_settings(Constants.SettingsDict)
    Constants.load_settings()

    ui_scale_factor = Constants.current_settings.get("ui_scale_factor", 1.0)
    ui_scale_factor = float(ui_scale_factor)

    if ui_scale_factor > 0:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
        os.environ["QT_SCALE_FACTOR"] = str(ui_scale_factor)
        logger.debug(f"Applied Qt UI scale factor: {ui_scale_factor}")

    if Constants.current_settings.get("msaa"):
        logger.debug(f"Enabling MSAA with {Constants.current_settings['msaa']} samples")
        surface_format.setSamples(Constants.current_settings["msaa"])

    QSurfaceFormat.setDefaultFormat(surface_format)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    application = QApplication(sys.argv)
    application.setStyle("Fusion")

    font_paths = [
        "System/Assets/Fonts/NDot57.otf",
        "System/Assets/Fonts/NType82.otf"
    ]

    for font_path in font_paths:
        if QFontDatabase.addApplicationFont(font_path) != -1:
            logger.debug(f"Loaded font: {font_path}")
            continue

        logger.error(f"Failed to load font: {font_path}")

    platform_extension = {"win32": "ico", "darwin": "icns"}.get(sys.platform, "png")
    application_icon   = QIcon(f"System/Assets/Icons/Cassette/AppIcon.{platform_extension}")

    application.setWindowIcon(application_icon)

    main_window = ApplicationWindow()
    main_window.show()
    main_window.intro_overlay.start_overlay(670)

    sys.exit(application.exec())

if __name__ == "__main__":
    logger.debug("Hello.")
    main()