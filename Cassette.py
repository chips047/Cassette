import os
import sys
import time
import random
import traceback

import multiprocessing as mp
from loguru import logger

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS

else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

logger.debug(f"Current working directory: {os.getcwd()}")

start = time.perf_counter()
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
end = time.perf_counter()

logger.debug(f"PyQt5 imported successfully. Time taken: {end - start:.2f} seconds")

start = time.perf_counter()
from System import UI
from System import Utils
from System import Styles
from System import Player
end = time.perf_counter()

logger.debug(f"System modules imported successfully. Time taken: {end - start:.2f} seconds")

start = time.perf_counter()
from System.Constants import *
from System.ProjectMenu import MainMenu
from System.Compositor import CompositorWidget
end = time.perf_counter()

logger.debug(f"Project modules imported successfully. Time taken: {end - start:.2f} seconds")

processing_exception = False

def handle_exception(exc_type, exc_value, exc_traceback):
    global processing_exception
    
    if processing_exception:
        return
    
    processing_exception = True
    
    try:
        logger.error(str('\n'.join(traceback.format_exception(exc_type, exc_value, exc_traceback))))
        UI.ErrorWindow(f"Panic: {exc_value}", str('\n'.join(traceback.format_exception(exc_type, exc_value, exc_traceback))) + "\nCassette will now close.", "No way").exec_()
    
    except Exception as e:
        print(f"Critical failure in error handler: {e}")
    
    finally:
        processing_exception = False

sys.excepthook = handle_exception

class EasterEggManager:
    CHANCE = 0.005
    
    DATA = [
        {
            "content": "System/Media/Anomaly.png", 
            "sound": "NOK/Anomaly", 
            "duration": 7500,
            "fade": 200
        },
        {
            "content": "do you hear this sound"
        }
    ]

    @staticmethod
    def get_egg():
        if random.random() < EasterEggManager.CHANCE:
            return random.choice(EasterEggManager.DATA)
        
        return None

    @staticmethod
    def is_image(content: str):
        valid_ext = ('.png', '.jpg', '.jpeg', '.bmp')
        return content.endswith(valid_ext)

class StartupFadeOverlay(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setParent(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        self._bg_opacity = 1.0
        self.color = QColor(0, 0, 0)
        
        self.current_pixmap = None
        self.current_text = None
        self.sound_effect = None
        
        self.text_rect = self.rect()
        
        if parent:
            self.setGeometry(parent.rect())
        
        self.raise_()

        self.bg_anim = QPropertyAnimation(self, b"bgOpacity", self)
        self.bg_anim.setDuration(700)
        self.bg_anim.setStartValue(1.0)
        self.bg_anim.setEndValue(0.0)
        self.bg_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.bg_anim.finished.connect(self._on_finished)

    @pyqtProperty(float)
    def bgOpacity(self):
        return self._bg_opacity

    @bgOpacity.setter
    def bgOpacity(self, v: float):
        self._bg_opacity = float(v)
        self.update()

    def start(self, default_hold_ms = 600):
        self.setGeometry(self.parent().rect())
        self.show()
        self.adjustSize()
        
        is_first_start = CurrentSettings.get("new_user", True)
        
        wait_time = default_hold_ms
        egg = None

        if is_first_start:
            self.current_text = "Get ready."
            self.text_rect = self.rect()
            
            settings = QSettings("chips047", "Cassette")
            settings.setValue("new_user", False)
            settings.sync()
            load_settings()
        
        else:
            egg = EasterEggManager.get_egg()
            
            if not egg:
                Utils.ui_sound("Startup", volume = 0.35 if is_first_start else 1.0)
                return QTimer.singleShot(wait_time, self.bg_anim.start)
            
            content = egg["content"]
            wait_time = egg.get("duration", default_hold_ms)
                
            if EasterEggManager.is_image(content):
                self.current_pixmap = QPixmap(content)
                
            else:
                self.current_text = content
                
                font = Utils.NType(10)
                metrics = QFontMetrics(font)

                rect_size = metrics.boundingRect(self.current_text)
                tw = rect_size.width() + 20
                th = rect_size.height() + 20
                
                margin = 80
                
                limit_x = max(margin, self.width() - tw - margin)
                limit_y = max(margin, self.height() - th - margin)
                
                rx = random.randint(margin, limit_x)
                ry = random.randint(margin, limit_y)
                
                self.text_rect = QRect(rx, ry, tw, th)
            
            if egg.get("fade"):
                self.bg_anim.setDuration(egg["fade"])
            
            if egg.get("sound"):
                Utils.ui_sound(egg["sound"], 1.0)

        Utils.ui_sound("Startup")
        QTimer.singleShot(wait_time, self.bg_anim.start)

    def _on_finished(self):
        self.close()
        self.finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        alpha = int(self._bg_opacity * 255)
        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))
        painter.setOpacity(self._bg_opacity)

        if self.current_pixmap and not self.current_pixmap.isNull():
            scaled = self.current_pixmap.scaled(
                self.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            
            painter.drawPixmap(x, y, scaled)

        elif self.current_text:
            text_color = QColor(255, 255, 255, 255)
            
            painter.setPen(text_color)
            painter.setFont(Utils.NType(10))
            
            painter.drawText(self.text_rect, Qt.AlignCenter, self.current_text)

class ApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cassette")
        self.resize(1280, 800)
        logger.debug("Starting up...")
        
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.main_menu_widget = MainMenu(self)
        self.compositor_widget = CompositorWidget(self)

        main_menu_effect = QGraphicsOpacityEffect(self.main_menu_widget)
        main_menu_effect.setOpacity(1.0)
        self.main_menu_widget.setGraphicsEffect(main_menu_effect)

        compositor_effect = QGraphicsOpacityEffect(self.compositor_widget)
        compositor_effect.setOpacity(0.0)
        self.compositor_widget.setGraphicsEffect(compositor_effect)

        self.stack.addWidget(self.main_menu_widget)
        self.stack.addWidget(self.compositor_widget)

        self.main_menu_widget.composition_created.connect(self.show_compositor)
        self.compositor_widget.back_to_main_menu_requested.connect(self.hide_compositor_and_show_main_menu)

        self.stack.setCurrentWidget(self.main_menu_widget)
        self.setStyleSheet(f"background-color: {Styles.Colors.background};")

        self.intro_overlay = StartupFadeOverlay(self)
        
        #self._memory_leak_test()

    def _memory_leak_test(self):
        for i in range(100):
            window = UI.ErrorWindow(
                "Hm",
                "Tf?"
            )
            
            QTimer.singleShot(500, window.start_exit_animation)
            window.exec_()

    def fade_out(self, widget):
        logger.debug("Fading out")
        
        effect = widget.graphicsEffect()
        effect.setOpacity(1.0)

        self.anim_out = QPropertyAnimation(effect, b"opacity")
        self.anim_out.setDuration(300)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.OutCubic)
        
        return self.anim_out

    def fade_in(self, widget):
        logger.debug("Fading in")
        
        effect = widget.graphicsEffect()
        effect.setOpacity(0.0) 
        
        self.anim_in = QPropertyAnimation(effect, b"opacity")
        self.anim_in.setDuration(400)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.setEasingCurve(QEasingCurve.InCubic)
        return self.anim_in

    @pyqtSlot(object)
    def show_compositor(self, composition):
        self.compositor_widget.load_composition(composition)
        anim_out_menu = self.fade_out(self.main_menu_widget)

        def on_fade_out_finished():
            self.main_menu_widget.setVisible(False)
            self.stack.setCurrentWidget(self.compositor_widget)

            initial_compositor_geometry = self.stack.geometry()
            offset_y = 350
            self.compositor_widget.setGeometry(
                initial_compositor_geometry.x(),
                initial_compositor_geometry.y() + offset_y,
                initial_compositor_geometry.width(),
                initial_compositor_geometry.height()
            )

            self.anim_move = QPropertyAnimation(self.compositor_widget, b"geometry")
            self.anim_move.setDuration(700)
            self.anim_move.setStartValue(QRect(
                initial_compositor_geometry.x(),
                initial_compositor_geometry.y() + offset_y,
                initial_compositor_geometry.width(),
                initial_compositor_geometry.height()
            ))

            self.anim_move.setEndValue(initial_compositor_geometry)
            self.anim_move.setEasingCurve(QEasingCurve.OutElastic)

            self.anim_move.finished.connect(self.compositor_widget.content_widget.check_tutorial)

            anim_in_compositor = self.fade_in(self.compositor_widget)
            anim_in_compositor.start()

            Utils.ui_sound("Eject")
            self.anim_move.start(QAbstractAnimation.DeleteWhenStopped)

        anim_out_menu.finished.connect(on_fade_out_finished)
        anim_out_menu.start()
    
    @pyqtSlot()
    def hide_compositor_and_show_main_menu(self):
        logger.debug("Fading out compositor")
        self.anim_out_compositor = self.fade_out(self.compositor_widget)

        def on_fade_out_compositor_finished():
            self.compositor_widget.setVisible(False)
            self.compositor_widget.content_widget.unload_composition()

            initial_main_menu_geometry = self.stack.geometry()
            offset_y = 350
            self.main_menu_widget.setGeometry(
                initial_main_menu_geometry.x(),
                initial_main_menu_geometry.y() + offset_y,
                initial_main_menu_geometry.width(),
                initial_main_menu_geometry.height()
            )

            logger.warning("Switching to main menu widget")
            self.stack.setCurrentWidget(self.main_menu_widget)
            self.main_menu_widget.setVisible(True)

            logger.warning("Showing main menu")

            menu_effect = self.main_menu_widget.graphicsEffect()
            menu_effect.setOpacity(0.0)

            self.anim_in_main_menu = QPropertyAnimation(menu_effect, b"opacity")
            self.anim_in_main_menu.setDuration(500)
            self.anim_in_main_menu.setStartValue(0.0)
            self.anim_in_main_menu.setEndValue(1.0)
            self.anim_in_main_menu.setEasingCurve(QEasingCurve.InCubic)

            self.anim_move_main_menu = QPropertyAnimation(self.main_menu_widget, b"geometry")
            self.anim_move_main_menu.setDuration(700)
            self.anim_move_main_menu.setStartValue(
                QRect(
                    initial_main_menu_geometry.x(),
                    initial_main_menu_geometry.y() + offset_y,
                    initial_main_menu_geometry.width(),
                    initial_main_menu_geometry.height()
                )
            )

            self.anim_move_main_menu.setEndValue(initial_main_menu_geometry)
            self.anim_move_main_menu.setEasingCurve(QEasingCurve.OutElastic)

            logger.warning("Animating main menu into view")

            Utils.ui_sound("Eject")

            self.anim_in_main_menu.start()
            self.anim_move_main_menu.start()

        self.anim_out_compositor.finished.connect(on_fade_out_compositor_finished)
        self.anim_out_compositor.start()
    
    def _exit_effects(self):
        Utils.ui_sound("Close")
        
        if self.compositor_widget.content_widget.composition:
            self.compositor_widget.content_widget.glyph_visualizer.exit(False)
    
    def closeEvent(self, event):
        logger.warning(f"- - - Alt F4 pressed - - -")
        
        event.ignore()
        self.hide()
        
        if self.compositor_widget.content_widget.composition:
            self.compositor_widget.content_widget.composition.syncer.exit_app()

        if Player.player.is_playing:
            if self.compositor_widget.content_widget.global_waveform_max == 1e-6:
                self._exit_effects()
                QTimer.singleShot(1800, QApplication.instance().quit)
                
                return
            
            Player.player.tape(end_speed = 0.0, duration = 3.0, cleanup_on_finish = True)

            logger.debug("Window hidden, app will close in 3 seconds...")
            
            close_visualizer_timeout = CurrentSettings["animation_multiplier"] * 1700

            QTimer.singleShot(close_visualizer_timeout, self._exit_effects)
            QTimer.singleShot(1500 + close_visualizer_timeout, QApplication.instance().quit)
        
        else:
            close_visualizer_duration = CurrentSettings["animation_multiplier"] * 1800
            
            self._exit_effects()
            QTimer.singleShot(close_visualizer_duration, QApplication.instance().quit)

def main():
    start = time.perf_counter()
    fmt = QSurfaceFormat()
    fmt.setVersion(4, 1)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions, False)

    prepare_default_settings(SettingsDict)
    load_settings()

    if CurrentSettings.get("msaa"):
        fmt.setSamples(CurrentSettings["msaa"])
    
    QSurfaceFormat.setDefaultFormat(fmt)
    end = time.perf_counter()
    
    logger.debug(f"OpenGL format set. Time taken: {end - start:.2f} seconds")
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

    start = time.perf_counter()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    end = time.perf_counter()
    
    logger.debug(f"QApplication initialized. Time taken: {end - start:.2f} seconds")
    
    start = time.perf_counter()
    if os.path.exists("System/Fonts/NDot57.otf"):
        QFontDatabase.addApplicationFont("System/Fonts/NDot57.otf")
        logger.debug("Loaded font NDot57.otf")
    
    if os.path.exists("System/Fonts/NType82.otf"):
        QFontDatabase.addApplicationFont("System/Fonts/NType82.otf")
        logger.debug("Loaded font NType82.otf")
    end = time.perf_counter()
    
    logger.debug(f"Fonts loaded. Time taken: {end - start:.2f} seconds")

    icon_format = "ico" if sys.platform == "win32" else "icns"
    app.setWindowIcon(QIcon(f"System/Icons/Icon256.{icon_format}"))

    start = time.perf_counter()
    main_window = ApplicationWindow()
    main_window.show() 
    main_window.intro_overlay.start(670)
    end = time.perf_counter()
    
    logger.debug(f"Main window shown and intro started. Time taken: {end - start:.2f} seconds")

    sys.exit(app.exec_())

if __name__ == '__main__':
    start = time.perf_counter()
    mp.freeze_support()
    end = time.perf_counter()
    
    logger.debug(f"Freeze support initialized. Time taken: {end - start:.2f} seconds")
    
    pid = os.getpid()
    logger.debug(f"Main Process PID: {pid}")
    
    main()