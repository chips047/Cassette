from __future__ import annotations

import os
import sys
import time
import random
import threading
import traceback

from datetime  import datetime
from functools import partial

from loguru import logger

from PyQt6.QtCore import (
    Qt,
    QRect,
    QTimer,
    pyqtSlot,
    pyqtSignal,
    QEasingCurve,
    pyqtProperty,
    QPropertyAnimation
)

from PyQt6.QtGui import (
    QIcon,
    QColor,
    QPixmap,
    QPainter,
    QShortcut,
    QMoveEvent,
    QCloseEvent,
    QPaintEvent,
    QFontMetrics,
    QKeySequence,
    QResizeEvent,
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

from System.Interface.Animation.WindowAnimator import WindowAnimator

from System.Views.Editor      import AuditContainerWidget
from System.Views.Compositor  import CompositorWidget
from System.Views.ProjectMenu import MainMenu

if getattr(sys, "frozen", False):
    base_directory = sys._MEIPASS

else:
    base_directory = os.path.dirname(os.path.abspath(__file__))

os.chdir(base_directory)
sys.path.insert(0, base_directory)

# Exception Handling

is_processing_exception = False


def handle_exception(
        exception_type:      type[BaseException],
        exception_value:     BaseException,
        exception_traceback: object
    ) -> None:

    global is_processing_exception

    if is_processing_exception:
        return

    is_processing_exception = True

    try:
        if issubclass(exception_type, KeyboardInterrupt):
            sys.__excepthook__(exception_type, exception_value, exception_traceback)

            return

        logger.opt(
            exception = (exception_type, exception_value, exception_traceback)
        ).critical("Fatal crash: Uncaught exception in main thread")

        error_message = "".join(
            traceback.format_exception(
                exception_type,
                exception_value,
                exception_traceback,
            )
        )

        title = (
            f"Fatal Error: {exception_value}"
            if random.random() > 0.005
            else "0x000000DEAD"
        )

        Windows.ErrorWindow(
            title,
            error_message,
            "OH WELL",
            True
        ).exec()

    except Exception as failure:
        logger.critical(f"Critical failure in error handler: {failure}")

    finally:
        is_processing_exception = False


def handle_thread_exception(arguments: threading.ExceptHookArgs) -> None:
    logger.opt(
        exception = (arguments.exc_type, arguments.exc_value, arguments.exc_traceback)
    ).critical(f"Fatal crash in background thread '{arguments.thread.name}'")


sys.excepthook       = handle_exception
threading.excepthook = handle_thread_exception
Utils.setup_exe_logging()

# Window Effects

class WindowEffectManager:
    CHANCE = 0.005

    STARTUP_EASTER_EGGS = [
        {
            "name":    "bunny",
            "content": "System/Assets/Image/Woah.png"
        },
        {
            "name":    "walter",
            "content": "find the walter..."
        },
        {
            "name":     "anomaly_img",
            "content":  "System/Assets/Image/Anomaly.png",
            "sound":    ".vault/NOK/Anomaly",
            "duration": 7500,
            "fade":     200,
        },
        {
            "name":    "ieytd2_img",
            "content": "System/Assets/Image/IEYTD2.png",
            "scale":   False,
        },
        {
            "name":    "the_void_text",
            "content": "First, there was The Void",
        },
        {
            "name":    "die_like_rest_text",
            "content": "The best of the best, still die like the rest",
        },
        {
            "name":    "cake_lie_text",
            "content": "The cake is a lie The cake is a lie The cake is a lie",
        },
        {
            "name":    "please_text",
            "content": "Please",
            "sound":   ".vault/NOK/ThreeTone",
        },
    ]

    def __init__(self, window: QMainWindow) -> None:
        self.window = window

        self.shake_sound_count              = 0
        self.shake_threshold                = 1500
        self.last_shake_horizontal_position = 0
        self.shake_direction                = 0
        self.shake_direction_changes        = 0
        self.last_shake_time                = 0.0

        self.last_window_area    = window.width() * window.height()
        self.resize_direction    = 0
        self.direction_changes   = 0
        self.last_change_time    = 0.0
        self.last_accordion_time = 0.0
        self.is_accordion_active = False

        self.accordion_stop_timer = Timing.Timer(
            interval    = 2000,
            callback    = self.reset_accordion_state,
            single_shot = True
        )

        self.shake_stop_timer = Timing.Timer(
            interval    = 2000,
            callback    = self.reset_shake_state,
            single_shot = True
        )

    def process_window_move(
            self,
            horizontal_position:      int,
            unused_vertical_position: int
        ) -> None:

        current_time     = time.time()
        horizontal_delta = horizontal_position - self.last_shake_horizontal_position

        self.last_shake_horizontal_position = horizontal_position

        if abs(horizontal_delta) < 5:
            return

        current_direction = 1 if horizontal_delta > 0 else -1

        if current_direction == self.shake_direction:
            return

        if current_time - self.last_shake_time > 0.8:
            self.shake_direction_changes = 0

        self.shake_direction         = current_direction
        self.shake_direction_changes += 1
        self.last_shake_time         = current_time

        if self.shake_direction_changes < 10:
            return

        self.shake_stop_timer.stop()
        self.shake_stop_timer.start()

        sound_index = min(5, self.shake_direction_changes // 2)

        if sound_index < 1:
            sound_index = random.randint(1, 5)

        Player.ui_player.play_sound(
            f".vault/NOK/Shake{sound_index}",
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
        delta_time   = (current_time - self.last_accordion_time) if self.last_accordion_time > 0.0 else 0.01

        area_difference = current_area - self.last_window_area
        velocity        = abs(area_difference) / delta_time

        minimum_velocity = 50000
        maximum_velocity = 2000000

        if abs(area_difference) < 200 or velocity < minimum_velocity:
            self.last_window_area    = current_area
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
            self.last_window_area    = current_area
            self.last_accordion_time = current_time

            return

        self.accordion_stop_timer.stop()
        self.accordion_stop_timer.start()

        volume = (velocity - minimum_velocity) / (maximum_velocity - minimum_velocity)
        volume = max(0.1, min(1.0, volume))

        sound_type = "Out" if current_direction > 0 else "In"

        Player.ui_player.play_sound(
            f".vault/NOK/Accordion{sound_type}",
            volume = volume
        )

        self.last_window_area    = current_area
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
    def choose_startup_easter_egg() -> dict[str, object] | None:
        if random.random() > WindowEffectManager.CHANCE:
            return None

        available_easter_eggs = []

        for easter_egg in WindowEffectManager.STARTUP_EASTER_EGGS:
            setting_key = f"_{easter_egg['name']}_seen"

            if not Constants.current_settings.get(setting_key, False):
                available_easter_eggs.append(easter_egg)

        if not available_easter_eggs:
            return None

        chosen_easter_egg = random.choice(available_easter_eggs)
        setting_key       = f"_{chosen_easter_egg['name']}_seen"

        Constants.current_settings.set_value(setting_key, True)

        return chosen_easter_egg

# Startup Overlay

class StartupFadeOverlay(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.background_opacity  = 1.0
        self.current_pixmap      = None

        self.main_text           = None
        self.main_text_rectangle = None
        self.main_font           = None

        self.easter_egg_text           = None
        self.easter_egg_text_rectangle = None
        self.easter_egg_font           = None

        self.background_fade_animation = QPropertyAnimation(
            self,
            b"backgroundOpacity"
        )

        self.background_fade_animation.setDuration(400)
        self.background_fade_animation.setStartValue(1.0)
        self.background_fade_animation.setEndValue(0.0)
        self.background_fade_animation.setEasingCurve(QEasingCurve.Type.OutExpo)
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

        is_new_user  = Constants.current_settings.get("_new_user", True)
        hold_time_ms = default_hold_ms

        self.main_font       = Utils.NType(30)
        self.easter_egg_font = Utils.NType(9)

        if is_new_user:
            Constants.current_settings.set_value("_is_og_user", False)
            self.main_text           = "Get ready."
            self.main_text_rectangle = self.rect()

            Constants.current_settings.set_value("_new_user", False)

            Player.ui_player.play_sound(
                "App/Start",
                setting_key            = "startup_sound",
                enable_tone_randomizer = False,
                volume                 = 0.5
            )

            QTimer.singleShot(
                hold_time_ms,
                self.background_fade_animation.start
            )

            return

        startup_easter_egg = WindowEffectManager.choose_startup_easter_egg()

        if startup_easter_egg is None:
            self.main_text           = "Cassette"
            self.main_text_rectangle = self.rect()

            Player.ui_player.play_sound(
                "App/Start",
                setting_key            = "startup_sound",
                enable_tone_randomizer = False
            )

            QTimer.singleShot(
                hold_time_ms,
                self.background_fade_animation.start
            )

            return

        content      = startup_easter_egg["content"]
        hold_time_ms = int(startup_easter_egg.get("duration", default_hold_ms))

        if WindowEffectManager.is_image(str(content)):
            self.main_text = None
            pixmap         = QPixmap(str(content))

            if startup_easter_egg.get("scale", True):
                self.current_pixmap = pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )

            else:
                self.current_pixmap = pixmap

        else:
            self.main_text               = "Cassette"
            self.main_text_rectangle     = self.rect()
            self.easter_egg_text         = str(content)

            metrics     = QFontMetrics(self.easter_egg_font)
            rectangle   = metrics.boundingRect(self.easter_egg_text)
            text_width  = rectangle.width() + 20
            text_height = rectangle.height() + 20
            margin_px   = 80

            random_horizontal_position = random.randint(
                margin_px,
                max(margin_px, self.width() - text_width - margin_px)
            )

            random_vertical_position = random.randint(
                margin_px,
                max(margin_px, self.height() - text_height - margin_px)
            )

            self.easter_egg_text_rectangle = QRect(
                random_horizontal_position,
                random_vertical_position,
                text_width,
                text_height
            )

        if "fade" in startup_easter_egg:
            self.background_fade_animation.setDuration(int(startup_easter_egg["fade"]))

        sound_name = startup_easter_egg.get("sound", "App/Start")

        Player.ui_player.play_sound(
            sound_name,
            setting_key            = "startup_sound" if sound_name == "App/Start" else None,
            enable_tone_randomizer = False
        )

        QTimer.singleShot(
            hold_time_ms,
            self.background_fade_animation.start
        )

    def handle_fade_finished(self) -> None:
        logger.debug("Startup fade animation finished, closing overlay")

        self.close()
        self.finished.emit()

    def paintEvent(self, unused_event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing     |
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

        painter.setPen(QColor(255, 255, 255))

        if self.main_text and self.main_text_rectangle:
            painter.setFont(self.main_font)
            painter.drawText(self.main_text_rectangle, int(Qt.AlignmentFlag.AlignCenter), self.main_text)

        if self.easter_egg_text and self.easter_egg_text_rectangle:
            painter.setFont(self.easter_egg_font)
            painter.drawText(self.easter_egg_text_rectangle, int(Qt.AlignmentFlag.AlignCenter), self.easter_egg_text)

# Main Window

class ApplicationWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.effect_manager       = WindowEffectManager(self)
        self.is_closing           = False
        self.is_shutdown_complete = False

        self.setWindowTitle("Cassette")
        self.resize(1000, 640)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.animator = WindowAnimator(self)

        self.main_menu_widget       = MainMenu(self)
        self.compositor_widget      = CompositorWidget(self)
        self.audit_container_widget = None

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
        self.compositor_widget.loading_finished.connect(self.show_compositor_view_after_transition)

        self.stack.setCurrentWidget(self.main_menu_widget)
        self.setStyleSheet(f"background-color: {Styles.Colors.Background};")

        self.intro_overlay = StartupFadeOverlay(self)
        self.intro_overlay.finished.connect(self.handle_intro_finished)

        self.setup_animations()
        self.setup_screenshot_shortcut()

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

        for index in range(self.stack.count()):
            page = self.stack.widget(index)
            page.resize(self.stack.size())

            if page.layout():
                page.layout().activate()

        if self.entry_move_animation.state() == QPropertyAnimation.State.Running:
            self.sync_entry_animation_geometry()

        if self.intro_overlay is None:
            return

        self.intro_overlay.resize(
            event.size().width(),
            event.size().height()
        )

    # Screenshot Management

    def setup_screenshot_shortcut(self) -> None:
        self.screenshot_shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.screenshot_shortcut.activated.connect(self.capture_4k_screenshot)

    def capture_4k_screenshot(self) -> None:
        target_width  = 3840
        source_width  = self.width()
        source_height = self.height()

        if source_width <= 0 or source_height <= 0:
            logger.warning("Cannot capture screenshot, window has invalid size")

            return

        scale_factor  = target_width / float(source_width)
        target_height = round(source_height * scale_factor)

        pixmap = QPixmap(target_width, target_height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing          |
            QPainter.RenderHint.TextAntialiasing      |
            QPainter.RenderHint.SmoothPixmapTransform
        )

        painter.scale(scale_factor, scale_factor)
        self.render(painter)
        painter.end()

        screenshots_directory = os.path.join(base_directory, "Screenshots")
        os.makedirs(screenshots_directory, exist_ok = True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = os.path.join(screenshots_directory, f"Cassette_4K_{timestamp}.png")

        did_save_successfully = pixmap.save(file_path, "PNG")

        if did_save_successfully:
            logger.info(f"Saved 4K screenshot: {file_path} ({target_width}x{target_height}, scale {scale_factor:.2f}x)")
            Player.ui_player.play_sound("App/Eject")

        else:
            logger.error(f"Failed to save 4K screenshot to: {file_path}")

    # Updates and Data

    def process_new_songs_data(self, information: str) -> None:
        with open("System/Assets/Songs.txt", "w", encoding = "utf-8") as file:
            file.write(information)

    def process_new_about_data(self, information: str) -> None:
        with open("System/Assets/About.txt", "w", encoding = "utf-8") as file:
            file.write(information)

    def show_update_info(self, information: dict[str, object]) -> None:
        version_tag = str(information.get("tag_name", "unknown"))
        changelog   = str(information.get("body", "No changelog available."))
        release_url = str(information.get("html_url", Constants.GITHUB_LINK))

        current_version_file_path = Utils.get_resource_path("version")

        if not os.path.exists(current_version_file_path):
            return

        with open(current_version_file_path, "r", encoding = "utf-8") as version_file:
            current_version = version_file.read().strip()

        if not Utils.is_newer_version(version_tag, current_version):
            return

        last_notified_version = Constants.current_settings.get("_last_notified_update")

        if version_tag == last_notified_version:
            return

        Windows.UpdateWindow(
            version             = version_tag,
            changelog           = changelog,
            url                 = release_url,
            release_information = information
        ).exec()

        Constants.current_settings.set_value("_last_notified_update", version_tag)

    # Animations

    @staticmethod
    def create_fadeout_animation(target_effect: QGraphicsOpacityEffect) -> QPropertyAnimation:
        animation = QPropertyAnimation(target_effect, b"opacity")
        animation.setDuration(300)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        return animation

    def setup_animations(self) -> None:
        self.entry_move_animation = QPropertyAnimation(None, b"geometry")
        self.entry_fade_animation = QPropertyAnimation(None, b"opacity")

        self.main_menu_fadeout  = self.create_fadeout_animation(self.main_menu_widget.graphicsEffect())
        self.compositor_fadeout = self.create_fadeout_animation(self.compositor_widget.graphicsEffect())

        self.entry_move_animation.setDuration(1000)
        self.entry_move_animation.setEasingCurve(QEasingCurve.Type.OutElastic)

        self.entry_fade_animation.setDuration(400)
        self.entry_fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.compositor_fadeout.finished.connect(self.handle_compositor_fadeout_finished)

    # View Transitions

    def handle_resource_loaded(
            self,
            resource_identifier: str,
            data:                object
        ) -> None:

        if resource_identifier == "release" and isinstance(data, dict):
            self.show_update_info(data)

        elif resource_identifier == "songs":
            self.process_new_songs_data(str(data))

        elif resource_identifier == "about":
            self.process_new_about_data(str(data))

    @pyqtSlot(ProjectSaver.Composition)
    def show_compositor_view(self, composition: ProjectSaver.Composition) -> None:
        self.compositor_widget.load_composition(composition)

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
            composition = ProjectSaver.Composition(identifier = int(project_id))
            self.compositor_widget.load_composition(composition)

        except Exception as exception:
            logger.error(f"Failed to load project: {exception}")
            self.restore_main_menu_after_failed_load()

    def restore_main_menu_after_failed_load(self) -> None:
        self.main_menu_widget.setEnabled(True)
        self.animate_widget_entry(self.main_menu_widget)

        Player.ui_player.play_sound(f"Alerts/Errors/Critical{random.randint(1, 3)}")

    @pyqtSlot()
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
    def handle_compositor_fadeout_finished(self) -> None:
        self.show_main_menu_view_after_transition()

    @pyqtSlot()
    def show_main_menu_view(self) -> None:
        self.main_menu_widget.setEnabled(True)
        self.compositor_fadeout.start()

    def animate_widget_entry(self, widget: QWidget) -> None:
        self.stack.setCurrentWidget(widget)
        widget.setVisible(True)

        self.entry_move_animation.setTargetObject(widget)
        self.sync_entry_animation_geometry()

        self.entry_fade_animation.setTargetObject(widget.graphicsEffect())
        self.entry_fade_animation.setStartValue(0.0)
        self.entry_fade_animation.setEndValue(1.0)

        self.entry_move_animation.start()
        self.entry_fade_animation.start()

    def sync_entry_animation_geometry(self) -> None:
        stack_rectangle = self.stack.geometry()

        self.entry_move_animation.setStartValue(
            QRect(
                stack_rectangle.x(),
                stack_rectangle.y() + Constants.ENTRY_VERTICAL_OFFSET_PX,
                stack_rectangle.width(),
                stack_rectangle.height()
            )
        )

        self.entry_move_animation.setEndValue(stack_rectangle)

    @pyqtSlot()
    def handle_intro_finished(self) -> None:
        self.intro_overlay = None
        self.effect_manager.check_calendar_events()

        self.update_thread = Utils.UpdateChecker()
        self.update_thread.resource_loaded.connect(self.handle_resource_loaded)
        self.update_thread.fetch_all()

        if Windows.should_show_version_prank():
            QTimer.singleShot(600, self.display_version_prank_window)

        is_backrooms_seen = bool(Constants.current_settings.get("_backrooms_seen", False))

        if not is_backrooms_seen and random.random() < 0.008:
            Constants.current_settings.set_value("_backrooms_seen", True)
            QTimer.singleShot(1000, self.trigger_audit_collapse_easter_egg)

    def trigger_audit_collapse_easter_egg(self) -> None:
        animator = WindowAnimator.get()

        if animator is None:
            return

        Player.ui_player.play_sound(
            name                   = ".vault/Anomaly/Connection",
            enable_tone_randomizer = False
        )

        QTimer.singleShot(500, lambda: animator.start_corrupt_collapse(4500, on_finished = self.switch_to_audit_view))

    def display_version_prank_window(self) -> None:
        prank_window = Windows.VersionPrankWindow(parent = self)
        prank_window.exec()

    def switch_to_audit_view(self) -> None:
        self.audit_container_widget = AuditContainerWidget(self)
        self.stack.addWidget(self.audit_container_widget)
        self.stack.setCurrentWidget(self.audit_container_widget)

        animator = WindowAnimator.get()

        if animator is not None:
            animator.finish_visual_transformation()

        self.audit_container_widget.setFocus()

    # Application Lifecycle

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()

        if self.is_closing:
            return

        if self.stack.currentWidget() == self.main_menu_widget:
            return self.begin_shutdown()

        if not Constants.current_settings.get("quit_dialog"):
            return self.begin_shutdown()

        quit_window   = Windows.QuitWindow()
        quit_accepted = quit_window.exec()

        if not quit_accepted:
            return

        self.begin_shutdown()

    def close(self) -> None:
        close_event = QCloseEvent()
        self.closeEvent(close_event)

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

        content_widget = self.compositor_widget.content_widget

        if content_widget.composition:
            content_widget.composition.update_progress()
            content_widget.composition.syncer.exit_app()
            logger.debug("Signaled Cassette Receiver to exit")

        has_audio_to_fade = Player.player.is_playing and content_widget.composition

        if has_audio_to_fade:
            self.shutdown_with_audio_fade()

        else:
            self.shutdown_without_audio_fade()

    def shutdown_with_audio_fade(self) -> None:
        logger.debug("Playing exit effects with audio slowdown")

        animation_multiplier = Constants.current_settings.get("animation_multiplier", 1.0)
        player               = Player.player

        remaining_ms  = max(0.0, player.duration_ms - player.get_position())
        fade_duration = Constants.EXIT_FADE_BASE_MS     * animation_multiplier
        effects_delay = Constants.EXIT_EFFECTS_DELAY_MS * animation_multiplier
        quit_delay    = effects_delay * 2

        if quit_delay > remaining_ms:
            scale = remaining_ms / quit_delay if quit_delay else 0.0

            fade_duration *= scale
            effects_delay *= scale
            quit_delay    *= scale

        quit_delay = max(quit_delay, effects_delay + Constants.EXIT_CLOSE_SOUND_DURATION_MS)

        fade_duration = int(fade_duration)
        effects_delay = int(effects_delay)
        quit_delay    = int(quit_delay)

        Player.player.set_speed(0.0, fade_duration, use_engine_multiplier = False)

        self.exit_effects_timer = QTimer(self)
        self.exit_effects_timer.setSingleShot(True)
        self.exit_effects_timer.timeout.connect(self.play_exit_effects)
        self.exit_effects_timer.start(effects_delay)

        self.exit_quit_timer = QTimer(self)
        self.exit_quit_timer.setSingleShot(True)
        self.exit_quit_timer.timeout.connect(self.complete_shutdown)
        self.exit_quit_timer.start(quit_delay)

    def shutdown_without_audio_fade(self) -> None:
        animation_multiplier = Constants.current_settings.get("animation_multiplier", 1.0)
        has_exit_effects     = self.play_exit_effects()

        duration = (
            int(Constants.NO_AUDIO_EXIT_DELAY_MS * animation_multiplier)
            if has_exit_effects
            else Constants.NO_AUDIO_EXIT_DELAY_MS
        )

        QTimer.singleShot(duration, self.complete_shutdown)

    def complete_shutdown(self) -> None:
        if self.is_shutdown_complete:
            return

        self.is_shutdown_complete = True

        logger.debug("Completing shutdown process, cleaning up resources")

        Player.player.full_shutdown()

        application = QApplication.instance()

        if application:
            logger.debug("Exiting application. Bye.")
            application.quit()

        sys.exit(0)

# Application Entry

def main() -> None:
    logger.debug("Configuring OpenGL surface format")

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)

    surface_format = QSurfaceFormat()
    surface_format.setVersion(4, 1)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface_format.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions, False)
    surface_format.setSwapBehavior(QSurfaceFormat.SwapBehavior.TripleBuffer)

    if Constants.current_settings.get("msaa"):
        logger.debug(f"Enabling MSAA with {Constants.current_settings['msaa']} samples")
        surface_format.setSamples(Constants.current_settings["msaa"])

    QSurfaceFormat.setDefaultFormat(surface_format)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    application = QApplication(sys.argv)
    application.setStyle("Fusion")

    logger.debug("Configuring application settings")
    Constants.prepare_default_settings(Constants.SettingsDict())
    Constants.load_settings()

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
    main_window.intro_overlay.start_overlay(200)

    sys.exit(application.exec())

if __name__ == "__main__":
    logger.debug("Hello.")
    main()