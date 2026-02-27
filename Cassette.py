import os
import sys
import math
import time
import random
import traceback

from datetime import datetime

from loguru import logger

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QStackedWidget, QGraphicsOpacityEffect
)

from PyQt5.QtGui import (
    QColor, QPixmap, QPainter,
    QFontMetrics, QSurfaceFormat, QFontDatabase,
    QIcon
)

from PyQt5.QtCore import (
    Qt, pyqtSignal, pyqtProperty,
    pyqtSlot, QPropertyAnimation, QEasingCurve,
    QTimer, QRect, QSettings
)

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS

else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

logger.debug(f"Current working directory: {os.getcwd()}")

from System.Common import Utils
from System.Common import Styles
from System.Components import Player

from System.Interface import Windows

from System.Common.Constants import *
from System.ProjectMenu import MainMenu
from System.Compositor import CompositorWidget

processing_exception = False

def handle_exception(exc_type, exc_value, exc_traceback):
    global processing_exception
    
    if processing_exception:
        return
    
    processing_exception = True
    
    try:
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.error(f"Uncaught exception: {error_msg}")
        
        Windows.ErrorWindow(
            f"Panic: {exc_value}" if random.random() > 0.005 else "0x000000DEAD", 
            f"{error_msg}\nCassette will now close.", 
            "No way"
        ).exec_()
    
    except Exception as e:
        logger.critical(f"Critical failure in error handler: {e}")
    
    finally:
        processing_exception = False

sys.excepthook = handle_exception

class EasterEggManager:
    CHANCE = 0.005
    
    STARTUP_DATA = [
        {"content": "System/Assets/Image/Anomaly.png", "sound": "NOK/Anomaly", "duration": 7500, "fade": 200},
        {"content": "System/Assets/Image/IEYTD2.png", "scale": False},
        {"content": "First, there was The Void"},
        {"content": "The best of the best, still die like the rest"},
        {"content": "The cake is a lie The cake is a lie The cake is a lie"}
    ]

    def __init__(self, window: QMainWindow):
        self.window = window

        self.shake_history = []
        self.shake_sound_count = 0
        self.shake_threshold = 1500
        self.last_shake_x = 0
        self.shake_direction = 0
        self.shake_direction_changes = 0
        self.last_shake_time = 0
        
        self.last_area = window.width() * window.height()
        self.last_accordion_time = 0
        self.resize_direction = 0
        self.direction_changes = 0
        self.last_change_time = 0
        self.is_accordion_active = False

        self.accordion_stop_timer = QTimer()
        self.accordion_stop_timer.setInterval(2000)
        self.accordion_stop_timer.setSingleShot(True)
        self.accordion_stop_timer.timeout.connect(self.stop_accordion_sound)

        self.shake_stop_timer = QTimer()
        self.shake_stop_timer.setInterval(2000)
        self.shake_stop_timer.setSingleShot(True)
        self.shake_stop_timer.timeout.connect(self.stop_shake_sound)

    def handle_shake(self, x, y):
        now = time.time()
        
        dx = x - self.last_shake_x
        self.last_shake_x = x

        if abs(dx) < 5:
            return

        current_dir = 1 if dx > 0 else -1

        if current_dir != self.shake_direction:
            if now - self.last_shake_time > 0.8:
                self.shake_direction_changes = 0
            
            self.shake_direction = current_dir
            self.shake_direction_changes += 1
            self.last_shake_time = now

            if self.shake_direction_changes >= 10:
                self.shake_stop_timer.stop()
                self.shake_stop_timer.start()

                sound_index = min(5, (self.shake_direction_changes // 2)) 
                if sound_index < 1: sound_index = random.randint(1, 5)

                Utils.ui_sound(f"NOK/Shake{sound_index}", random_spread=0.35)
                
                self.shake_sound_count += 1
                
                if self.shake_sound_count > 50:
                    logger.critical("Too much shaking! Emergency exit.")
                    self.window.close()

    def handle_resize_accordion(self, width, height):
        now = time.time()
        current_area = width * height
        
        dt = now - self.last_accordion_time if self.last_accordion_time > 0 else 0.01
        area_diff = current_area - self.last_area
        
        velocity = abs(area_diff) / dt
        
        MIN_VELOCITY = 50000
        MAX_VELOCITY = 2000000
        
        if abs(area_diff) < 200 or velocity < MIN_VELOCITY:
            self.last_area = current_area
            self.last_accordion_time = now

            return

        current_direction = 1 if area_diff > 0 else -1

        if current_direction != self.resize_direction:
            self.direction_changes += 1
            self.resize_direction = current_direction
            
            if now - self.last_change_time > 1.0:
                self.direction_changes = 1
            
            self.last_change_time = now

            if self.direction_changes >= 10:
                self.is_accordion_active = True

        if self.is_accordion_active:
            self.accordion_stop_timer.stop()
            self.accordion_stop_timer.start()

            volume = (velocity - MIN_VELOCITY) / (MAX_VELOCITY - MIN_VELOCITY)
            volume = max(0.1, min(1.0, volume))
            
            sound_type = "Out" if current_direction > 0 else "In"
            
            Utils.ui_sound(f"NOK/Accordion{sound_type}", volume=volume)

        self.last_area = current_area
        self.last_accordion_time = now

    def stop_accordion_sound(self):
        self.direction_changes = 0
        self.is_accordion_active = False
    
    def stop_shake_sound(self):
        self.shake_history = []
        self.shake_sound_count = 0
        self.shake_direction_changes = 0

    def check_calendar_events(self):
        now = datetime.now()

        if now.day == 8 and now.month == 6:
            Windows.ErrorWindow(
                "Wow!",
                "Today is a vacuum cleaner day! Enjoy!"
            ).exec_()
        
        if now.day == 4 and now.month == 5:
            Windows.ErrorWindow(
                "><",
                "my birthady"
            ).exec_()

    @staticmethod
    def is_image(content: str):
        return content.lower().endswith('.png')

    @staticmethod
    def get_startup_egg():
        if random.random() < EasterEggManager.CHANCE:
            return random.choice(EasterEggManager.STARTUP_DATA)
        
        return None

class StartupFadeOverlay(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._bg_opacity = 1.0
        self.current_pixmap = None
        self.current_text = None
        
        self.bg_anim = Utils.Animations.make_animation(
            self,
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            
            b"bgOpacity", 700,
            QEasingCurve.OutCubic
        )

        self.bg_anim.finished.connect(self._on_finished)

    @pyqtProperty(float)
    def bgOpacity(self):
        return self._bg_opacity

    @bgOpacity.setter
    def bgOpacity(self, v: float):
        self._bg_opacity = float(v)
        self.update()

    def start(self, default_hold_ms=600):
        self.setGeometry(self.parent().rect())
        self.show()
        
        is_first_start = CurrentSettings.get("new_user", True)
        wait_time = default_hold_ms
        self.font = Utils.NType(30 if is_first_start else 10)

        if is_first_start:
            self.current_text = "Get ready."
            self.text_rect = self.rect()
            
            settings = QSettings("chips047", "Cassette")
            settings.setValue("new_user", False)
            settings.sync()
            load_settings()
        
        else:
            egg = EasterEggManager.get_startup_egg()
            
            if not egg:
                Utils.ui_sound("Startup", volume=1.0)
                QTimer.singleShot(wait_time, self.bg_anim.start)
                return

            content = egg["content"]
            wait_time = egg.get("duration", default_hold_ms)
            
            if EasterEggManager.is_image(content):
                pix = QPixmap(content)

                if egg.get("scale", True):
                    self.current_pixmap = pix.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                else:
                    self.current_pixmap = pix
            
            else:
                self.current_text = content
                metrics = QFontMetrics(self.font)
                rect_size = metrics.boundingRect(self.current_text)
                tw, th = rect_size.width() + 20, rect_size.height() + 20
                
                margin = 80
                rx = random.randint(margin, max(margin, self.width() - tw - margin))
                ry = random.randint(margin, max(margin, self.height() - th - margin))
                self.text_rect = QRect(rx, ry, tw, th)
            
            if "fade" in egg:
                self.bg_anim.setDuration(egg["fade"])
            
            if "sound" in egg:
                Utils.ui_sound(egg["sound"], 1.0)

        Utils.ui_sound("Startup")
        QTimer.singleShot(wait_time, self.bg_anim.start)

    def _on_finished(self):
        self.close()
        self.finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        alpha = int(self._bg_opacity * 255)
        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))
        painter.setOpacity(self._bg_opacity)

        if self.current_pixmap and not self.current_pixmap.isNull():
            x = (self.width() - self.current_pixmap.width()) // 2
            y = (self.height() - self.current_pixmap.height()) // 2
            painter.drawPixmap(x, y, self.current_pixmap)

        elif self.current_text:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(self.font)
            painter.drawText(self.text_rect, Qt.AlignCenter, self.current_text)

class ApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ee_manager = EasterEggManager(self)

        self.setWindowTitle("Cassette")
        self.resize(1280, 800)
        logger.debug("Initializing ApplicationWindow...")
        
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.main_menu_widget = MainMenu(self)
        self.compositor_widget = CompositorWidget(self)

        for widget, opacity in [(self.main_menu_widget, 1.0), (self.compositor_widget, 0.0)]:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(opacity)
            widget.setGraphicsEffect(effect)
            
            self.stack.addWidget(widget)

        self.main_menu_widget.composition_created.connect(self.show_compositor)
        self.compositor_widget.back_to_main_menu_requested.connect(self.show_main_menu)

        self.stack.setCurrentWidget(self.main_menu_widget)
        self.setStyleSheet(f"background-color: {Styles.Colors.background};")

        self.intro_overlay = StartupFadeOverlay(self)
        self.intro_overlay.finished.connect(self.ee_manager.check_calendar_events)
        
        self.is_closing = False

        self.setup_animations()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.ee_manager.handle_shake(
            event.pos().x(),
            event.pos().y()
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.ee_manager.handle_resize_accordion(
            event.size().width(),
            event.size().height()
        )

    def setup_animations(self):
        self.main_menu_fadeout = QPropertyAnimation(self.main_menu_widget.graphicsEffect(), b"opacity")
        self.main_menu_fadeout.setDuration(300)
        self.main_menu_fadeout.setStartValue(1.0)
        self.main_menu_fadeout.setEndValue(0.0)
        self.main_menu_fadeout.setEasingCurve(QEasingCurve.OutCubic)

        self.compositor_fadeout = QPropertyAnimation(self.compositor_widget.graphicsEffect(), b"opacity")
        self.compositor_fadeout.setDuration(300)
        self.compositor_fadeout.setStartValue(1.0)
        self.compositor_fadeout.setEndValue(0.0)
        self.compositor_fadeout.setEasingCurve(QEasingCurve.OutCubic)

        self.entry_move_animation = QPropertyAnimation(None, b"geometry")
        self.entry_move_animation.setDuration(700)
        self.entry_move_animation.setEasingCurve(QEasingCurve.OutElastic)
        
        self.entry_fade_animation = QPropertyAnimation(None, b"opacity")
        self.entry_fade_animation.setDuration(400)
        self.entry_fade_animation.setEasingCurve(QEasingCurve.OutCubic)

        self.main_menu_fadeout.finished.connect(self.on_transition_to_compositor)
        self.compositor_fadeout.finished.connect(self.on_transition_to_main_menu)

    def on_transition_to_compositor(self):
        self.main_menu_widget.setVisible(False)
        self._perform_widget_entry(self.compositor_widget)

    def on_transition_to_main_menu(self):
        self.compositor_widget.setVisible(False)
        self.compositor_widget.content_widget.unload_composition()
        self._perform_widget_entry(self.main_menu_widget)

    @pyqtSlot(object)
    def show_compositor(self, composition):
        self.compositor_widget.load_composition(composition)
        self.main_menu_fadeout.start()

    @pyqtSlot()
    def show_main_menu(self):
        self.compositor_fadeout.start()

    def _perform_widget_entry(self, widget):
        self.stack.setCurrentWidget(widget)
        widget.setVisible(True)
        
        rect = self.stack.geometry()
        offset_y = 150

        self.entry_move_animation.setTargetObject(widget)

        self.entry_move_animation.setStartValue(
            QRect(
                rect.x(),
                rect.y() + offset_y,
                rect.width(),
                rect.height()
            )
        )

        self.entry_move_animation.setEndValue(rect)

        self.entry_fade_animation.setTargetObject(widget.graphicsEffect())
        self.entry_fade_animation.setStartValue(0.0)
        self.entry_fade_animation.setEndValue(1.0)

        Utils.ui_sound("Eject")

        self.entry_move_animation.start()
        self.entry_fade_animation.start()

    def closeEvent(self, event):
        event.ignore()
        self.initiate_shutdown()

    def close(self):
        self.initiate_shutdown()

    def _exit_effects(self):
        Utils.ui_sound("Close")
        content = self.compositor_widget.content_widget
        
        if content.composition:
            content.glyph_visualizer.exit(False)
            return True
        
        return False

    def initiate_shutdown(self):
        if self.is_closing:
            return

        self.is_closing = True

        self.hide()
        
        content = self.compositor_widget.content_widget
        mult = CurrentSettings.get("animation_multiplier", 1.0)
        
        if content.composition:
            content.composition.syncer.exit_app()

        if Player.player.is_playing and content.global_waveform_max > 1e-6:
            Player.player.tape(end_speed=0.0, duration=3.0, cleanup_on_finish=True)
            
            close_vis_timeout = int(mult * 1700)
            
            QTimer.singleShot(close_vis_timeout, self._exit_effects)
            QTimer.singleShot(close_vis_timeout + 1500, QApplication.instance().quit)
        
        else:
            duration = int(1800 * mult) if self._exit_effects() else 1800
            QTimer.singleShot(duration, QApplication.instance().quit)

def main():
    fmt = QSurfaceFormat()
    fmt.setVersion(4, 1)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions, False)

    prepare_default_settings(SettingsDict)
    load_settings()

    if CurrentSettings.get("msaa"):
        fmt.setSamples(CurrentSettings["msaa"])
    
    QSurfaceFormat.setDefaultFormat(fmt)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    fonts = ["System/Assets/Fonts/NDot57.otf", "System/Assets/Fonts/NType82.otf"]
    
    for font in fonts:
        if QFontDatabase.addApplicationFont(font) != -1:
            continue
        
        logger.error(f"Failed to load font: {font}")

    icon_ext = {"win32": "ico", "darwin": "icns"}.get(sys.platform, "png")
    app.setWindowIcon(QIcon(f"System/Assets/Icons/Cassette/AppIcon.{icon_ext}"))

    main_window = ApplicationWindow()
    main_window.show() 
    main_window.intro_overlay.start(670)

    sys.exit(app.exec_())

if __name__ == '__main__':
    logger.debug(f"Main Process PID: {os.getpid()}")
    main()