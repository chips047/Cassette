import os
import sys
import time
import random
import traceback

from datetime import datetime

from loguru import logger

from PyQt5.QtCore import (
    Qt,
    QRect,
    QTimer,
    pyqtSlot,
    QSettings,
    pyqtSignal,
    pyqtProperty,
    QEasingCurve,
    QPropertyAnimation
)

from PyQt5.QtGui import (
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

from PyQt5.QtWidgets import (
    QWidget,
    QMainWindow,
    QApplication,
    QStackedWidget,
    QGraphicsOpacityEffect
)

# Initialization

if getattr(sys, "frozen", False):
    base_directory = sys._MEIPASS

else:
    base_directory = os.path.dirname(os.path.abspath(__file__))

os.chdir(base_directory)
sys.path.insert(0, base_directory)

from System.Common import (
    Utils,
    Styles
)

from System.Common.Constants import (
    SettingsDict,
    load_settings,
    CURRENT_SETTINGS,
    prepare_default_settings
)

from System.Interface import (
    Basic,
    Windows
)

from System.Services import (
    Player,
    ProjectSaver
)

from System.Views.ProjectMenu import MainMenu
from System.Views.Compositor import CompositorWidget

is_processing_exception = False

# System Functions

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

        logger.error(f"Uncaught exception: {error_message}")

        title = (
            f"Panic: {exception_value}"
            if random.random() > 0.005
            else "0x000000DEAD"
        )
        
        content = f"{error_message}\nCassette will now close."

        Windows.ErrorWindow(
            title,
            content,
            "No way",
        ).exec_()

    except Exception as failure:
        logger.critical(f"Critical failure in error handler: {failure}")

    finally:
        is_processing_exception = False

sys.excepthook = handle_exception

# Logic Classes

class EasterEggManager:
    CHANCE = 0.005

    STARTUP_DATA = [
        {
            "content":  "System/Assets/Image/Anomaly.png",
            "sound":    "Packs/NOK/Anomaly",
            "duration": 7500,
            "fade":     200,
        },
        {
            "content": "System/Assets/Image/IEYTD2.png",
            "scale":   False,
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
            "sound":   "Packs/NOK/ThreeTone"
        }
    ]

    def __init__(self, window: QMainWindow) -> None:
        self.window                  = window
        self.shake_history           = []
        self.shake_sound_count       = 0
        self.shake_threshold         = 1500
        self.last_shake_x_position   = 0
        self.shake_direction         = 0
        self.shake_direction_changes = 0
        self.last_shake_time         = 0

        self.last_area               = window.width() * window.height()
        self.last_accordion_time     = 0
        self.resize_direction        = 0
        self.direction_changes       = 0
        self.last_change_time        = 0
        self.is_accordion_active     = False

        self.accordion_stop_timer = Basic.Timer(
            2000,
            self.stop_accordion_sound,
            single_shot = True
        )

        self.shake_stop_timer = Basic.Timer(
            2000,
            self.stop_shake_sound,
            single_shot = True
        )

    def handle_shake(
        self,
        horizontal_position: int,
        vertical_position:   int,
    ) -> None:
        
        del vertical_position

        current_time       = time.time()
        horizontal_delta   = horizontal_position - self.last_shake_x_position

        self.last_shake_x_position = horizontal_position

        if abs(horizontal_delta) < 5:
            return

        current_direction = 1 if horizontal_delta > 0 else -1

        if current_direction == self.shake_direction:
            return

        if current_time - self.last_shake_time > 0.8:
            self.shake_direction_changes = 0

        self.shake_direction        = current_direction
        self.shake_direction_changes += 1
        self.last_shake_time        = current_time

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

    def handle_resize_accordion(
        self,
        width:  int,
        height: int,
    ) -> None:
        
        current_time    = time.time()
        current_area    = width * height
        delta_time      = current_time - self.last_accordion_time if self.last_accordion_time > 0 else 0.01
        area_difference = current_area - self.last_area
        velocity        = abs(area_difference) / delta_time

        minimum_velocity  = 50000
        maximum_velocity  = 2000000

        if abs(area_difference) < 200 or velocity < minimum_velocity:
            self.last_area           = current_area
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
            self.last_area           = current_area
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

        self.last_area           = current_area
        self.last_accordion_time = current_time

    def stop_accordion_sound(self) -> None:
        self.direction_changes   = 0
        self.is_accordion_active = False

    def stop_shake_sound(self) -> None:
        self.shake_history            = []
        self.shake_sound_count        = 0
        self.shake_direction_changes  = 0

    def check_calendar_events(self) -> None:
        current_time = datetime.now()

        if current_time.day == 8 and current_time.month == 6:
            Windows.ErrorWindow(
                "Wow!",
                "Today is a vacuum cleaner day! Enjoy!",
            ).exec_()

        if current_time.day == 4 and current_time.month == 5:
            Windows.ErrorWindow(
                "><",
                "my birthady",
            ).exec_()

    @staticmethod
    def is_image(content: str) -> bool:
        return content.lower().endswith(".png")

    @staticmethod
    def get_startup_egg() -> dict[str, object] | None:
        if random.random() < EasterEggManager.CHANCE:
            return random.choice(EasterEggManager.STARTUP_DATA)

        return None

# UI Components

class StartupFadeOverlay(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WA_DeleteOnClose)

        self.background_opacity        = 1.0
        self.current_pixmap            = None
        self.current_text              = None
        self.text_rect                 = None
        self.font                      = None

        self.background_fade_animation = QPropertyAnimation(self, b"bgOpacity")
        self.background_fade_animation.setDuration(700)
        self.background_fade_animation.setStartValue(1.0)
        self.background_fade_animation.setEndValue(0.0)
        self.background_fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.background_fade_animation.finished.connect(self.on_finished)

    @pyqtProperty(float)
    def bgOpacity(self) -> float:
        return self.background_opacity

    @bgOpacity.setter
    def bgOpacity(self, value: float) -> None:
        self.background_opacity = float(value)
        self.update()

    def start(self, default_hold_ms: int = 600) -> None:
        self.setGeometry(self.parent().rect())
        self.show()

        is_new_user = CURRENT_SETTINGS.get("new_user", True)
        wait_time   = default_hold_ms
        self.font   = Utils.NType(30 if is_new_user else 10)

        if is_new_user:
            self.current_text = "Get ready."
            self.text_rect    = self.rect()

            application_settings = QSettings("chips047", "Cassette")
            application_settings.setValue("new_user", False)
            application_settings.sync()

            load_settings()

            Player.ui_player.play_sound("App/Startup")

            QTimer.singleShot(
                wait_time,
                self.background_fade_animation.start,
            )
            
            return

        startup_egg = EasterEggManager.get_startup_egg()

        if startup_egg is None:
            Player.ui_player.play_sound(
                "App/Startup",
                enable_tone_randomizer=False,
            )
            
            QTimer.singleShot(
                wait_time,
                self.background_fade_animation.start,
            )
            
            return

        content   = startup_egg["content"]
        wait_time = startup_egg.get("duration", default_hold_ms)

        if EasterEggManager.is_image(content):
            pixmap = QPixmap(content)

            if startup_egg.get("scale", True):
                self.current_pixmap = pixmap.scaled(
                    self.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            
            else:
                self.current_pixmap = pixmap
        
        else:
            self.current_text = content

            metrics     = QFontMetrics(self.font)
            rectangle   = metrics.boundingRect(self.current_text)
            text_width  = rectangle.width() + 20
            text_height = rectangle.height() + 20

            margin             = 80
            
            random_x_position  = random.randint(
                margin,
                max(margin, self.width() - text_width - margin),
            )
            
            random_y_position  = random.randint(
                margin,
                max(margin, self.height() - text_height - margin),
            )

            self.text_rect = QRect(
                random_x_position,
                random_y_position,
                text_width,
                text_height,
            )

        if "fade" in startup_egg:
            self.background_fade_animation.setDuration(startup_egg["fade"])

        if "sound" in startup_egg:
            Player.ui_player.play_sound(
                startup_egg["sound"],
                enable_tone_randomizer = False
            )
        
        else:
            Player.ui_player.play_sound("App/Startup")
        
        QTimer.singleShot(
            wait_time,
            self.background_fade_animation.start,
        )

    def on_finished(self) -> None:
        self.close()
        self.finished.emit()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform,)

        alpha_value = int(self.background_opacity * 255)

        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha_value))
        painter.setOpacity(self.background_opacity)

        if self.current_pixmap and not self.current_pixmap.isNull():
            center_x = (self.width() - self.current_pixmap.width()) // 2
            center_y = (self.height() - self.current_pixmap.height()) // 2
            painter.drawPixmap(center_x, center_y, self.current_pixmap)
            
            return

        if self.current_text and self.text_rect is not None:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(self.font)
            painter.drawText(self.text_rect, Qt.AlignCenter, self.current_text)

class ApplicationWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.easter_egg_manager = EasterEggManager(self)

        self.setWindowTitle("Cassette")
        self.resize(1280, 800)

        self.stack               = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.main_menu_widget    = MainMenu(self)
        self.compositor_widget   = CompositorWidget(self)

        for widget, opacity in (
            (self.main_menu_widget, 1.0),
            (self.compositor_widget, 0.0),
        ):
            
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(opacity)
            widget.setGraphicsEffect(effect)
            self.stack.addWidget(widget)

        self.main_menu_widget.composition_created.connect(self.show_compositor)
        self.compositor_widget.back_to_main_menu_requested.connect(self.show_main_menu)

        self.stack.setCurrentWidget(self.main_menu_widget)
        self.setStyleSheet(f"background-color: {Styles.Colors.Background};")

        self.intro_overlay = StartupFadeOverlay(self)
        self.intro_overlay.finished.connect(self.on_intro_finished)

        self.is_closing = False

        self.setup_animations()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)

        self.easter_egg_manager.handle_shake(
            event.pos().x(),
            event.pos().y()
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        size = (
            event.size().width(),
            event.size().height()
        )

        self.easter_egg_manager.handle_resize_accordion(*size)

        if not self.intro_overlay:
            return

        self.intro_overlay.resize(*size)

    # Animations

    def setup_animations(self) -> None:
        self.entry_move_animation = QPropertyAnimation(None, b"geometry")
        self.entry_fade_animation = QPropertyAnimation(None, b"opacity")

        self.main_menu_fadeout = QPropertyAnimation(
            self.main_menu_widget.graphicsEffect(),
            b"opacity",
        )

        self.compositor_fadeout = QPropertyAnimation(
            self.compositor_widget.graphicsEffect(),
            b"opacity",
        )

        self.main_menu_fadeout.setDuration(300)
        self.main_menu_fadeout.setStartValue(1.0)
        self.main_menu_fadeout.setEndValue(0.0)
        self.main_menu_fadeout.setEasingCurve(QEasingCurve.OutCubic)

        self.compositor_fadeout.setDuration(300)
        self.compositor_fadeout.setStartValue(1.0)
        self.compositor_fadeout.setEndValue(0.0)
        self.compositor_fadeout.setEasingCurve(QEasingCurve.OutCubic)
        
        self.entry_move_animation.setDuration(700)
        self.entry_move_animation.setEasingCurve(QEasingCurve.OutElastic)
        
        self.entry_fade_animation.setDuration(400)
        self.entry_fade_animation.setEasingCurve(QEasingCurve.OutCubic)

        self.main_menu_fadeout.finished.connect(self.on_transition_to_compositor)
        self.compositor_fadeout.finished.connect(self.on_transition_to_main_menu)

    def on_transition_to_compositor(self) -> None:
        self.main_menu_widget.setVisible(False)
        self.perform_widget_entry(self.compositor_widget)

    def on_transition_to_main_menu(self) -> None:
        self.compositor_widget.setVisible(False)
        self.compositor_widget.content_widget.unload_composition()
        self.perform_widget_entry(self.main_menu_widget)

    @pyqtSlot(ProjectSaver.Composition)
    def show_compositor(self, composition: ProjectSaver.Composition) -> None:
        self.compositor_widget.load_composition(composition)
        self.main_menu_fadeout.start()

    @pyqtSlot()
    def show_main_menu(self) -> None:
        self.compositor_fadeout.start()

    def perform_widget_entry(self, widget: QWidget) -> None:
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
                stack_rectangle.height(),
            )
        )

        self.entry_move_animation.setEndValue(stack_rectangle)

        self.entry_fade_animation.setTargetObject(widget.graphicsEffect())
        self.entry_fade_animation.setStartValue(0.0)
        self.entry_fade_animation.setEndValue(1.0)

        Player.ui_player.play_sound("App/Eject")

        self.entry_move_animation.start()
        self.entry_fade_animation.start()
    
    @pyqtSlot()
    def on_intro_finished(self) -> None:
        self.intro_overlay = None
        self.easter_egg_manager.check_calendar_events()

    # Lifecycle

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.initiate_shutdown()

    def close(self) -> None:
        self.initiate_shutdown()

    def perform_exit_effects(self) -> bool:
        Player.ui_player.play_sound("App/Close")
        content = self.compositor_widget.content_widget

        if not content.composition:
            return False

        content.glyph_visualizer.exit(False)
        return True

    def initiate_shutdown(self) -> None:
        if self.is_closing:
            return

        self.is_closing = True
        self.hide()

        content_widget        = self.compositor_widget.content_widget
        animation_multiplier  = CURRENT_SETTINGS.get("animation_multiplier", 1.0)

        if content_widget.composition:
            content_widget.composition.syncer.exit_app()

        if Player.player.is_playing and content_widget.global_waveform_max > 1e-6:
            Player.player.set_speed(0.0, 3000)

            timeout = int(animation_multiplier * 1700)

            QTimer.singleShot(timeout, self.perform_exit_effects)
            QTimer.singleShot(timeout + 1500, self.final_close)

            return

        duration = int(1800 * animation_multiplier) if self.perform_exit_effects() else 1800

        QTimer.singleShot(duration, self.final_close)

    def final_close(self) -> None:
        Player.ui_player.cleanup()
        Player.player.full_shutdown()

        application = QApplication.instance()
        
        if application is not None:
            application.quit()

# Main Execution

def main() -> None:
    surface_format = QSurfaceFormat()
    surface_format.setVersion(4, 1)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface_format.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions, False)

    prepare_default_settings(SettingsDict)
    load_settings()

    if CURRENT_SETTINGS.get("msaa"):
        surface_format.setSamples(CURRENT_SETTINGS["msaa"])

    QSurfaceFormat.setDefaultFormat(surface_format)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

    application = QApplication(sys.argv)
    application.setStyle("Fusion")

    fonts = [
        "System/Assets/Fonts/NDot57.otf",
        "System/Assets/Fonts/NType82.otf",
    ]

    for font_path in fonts:
        if QFontDatabase.addApplicationFont(font_path) != -1:
            continue

        logger.error(f"Failed to load font: {font_path}")

    platform_extension = {"win32": "ico", "darwin": "icns"}.get(sys.platform, "png")
    application_icon   = QIcon(f"System/Assets/Icons/Cassette/AppIcon.{platform_extension}")

    application.setWindowIcon(application_icon)

    main_window = ApplicationWindow()
    main_window.show()
    main_window.intro_overlay.start(670)

    sys.exit(application.exec_())

if __name__ == "__main__":
    main()