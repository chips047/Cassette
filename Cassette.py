import os
import sys
import subprocess

import multiprocessing as mp
from loguru import logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

if sys.platform == "win32":
    # It prevents appearing of CMD because of pydub ffmpeg operations.
    
    class NoWindowPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
            super().__init__(*args, **kwargs)

    subprocess.Popen = NoWindowPopen

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System import UI
from System import Utils
from System import Styles
from System import Player

from System.Constants import *
from System.ProjectMenu import MainMenu
from System.Compositor import CompositorWidget

def is_ffmpeg_installed():
    envdir_list = [os.curdir] + os.environ["PATH"].split(os.pathsep)
    ffmpeg_found = False

    for envdir in envdir_list:
        if "ffmpeg" in envdir.lower():
            ffmpeg_found = True
            break
    
    return ffmpeg_found

class StartupFadeOverlay(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setParent(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        self._bg_opacity = 1.0
        self.color = QColor(0, 0, 0)
        
        self.setGeometry(parent.rect())
        self.raise_()

        self.bg_anim = QPropertyAnimation(self, b"bgOpacity", self)
        self.bg_anim.setDuration(700)
        self.bg_anim.setStartValue(1.0)
        self.bg_anim.setEndValue(0.0)
        self.bg_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.bg_anim.finished.connect(self._on_finished)

    @pyqtProperty(float) # type: ignore
    def bgOpacity(self):
        return self._bg_opacity

    @bgOpacity.setter
    def bgOpacity(self, v: float):
        self._bg_opacity = float(v)
        self.update()

    def start(self, hold_ms = 600):
        self.setGeometry(self.parent().rect())
        self.show()
        
        QTimer.singleShot(hold_ms, self.bg_anim.start)

    def _on_finished(self):
        self.close()
        self.finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        alpha = int(self._bg_opacity * 255)
        self.color.setAlpha(alpha) 
        painter.fillRect(self.rect(), self.color)

class ApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cassette")
        self.resize(1280, 800)
        logger.info("Starting up...")
        
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
        
        if not is_ffmpeg_installed():
            UI.ErrorWindow(
                "FFmpeg?",
                "FFmpeg was not found. Audio can't be loaded, but the main menu will still work.\n\nTo install FFmpeg on Linux, use your package manager, for example:\n-- Ubuntu/Debian: sudo apt install ffmpeg\n-- Arch: sudo pacman -S ffmpeg\n-- Fedora: sudo dnf install ffmpeg\n\nTo install FFmpeg on Windows, use PowerShell:\n-- winget install ffmpeg\n\nRestart the app after installation."
            ).exec_()
        
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
        logger.info("Fading out")
        
        effect = widget.graphicsEffect()
        effect.setOpacity(1.0)

        self.anim_out = QPropertyAnimation(effect, b"opacity")
        self.anim_out.setDuration(300)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.OutCubic)
        
        return self.anim_out

    def fade_in(self, widget):
        logger.info("Fading in")
        
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
        logger.info("Fading out compositor")
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
        event.ignore()
        self.hide()
        
        if self.compositor_widget.content_widget.composition:
            self.compositor_widget.content_widget.composition.syncer.exit_app()

        if Player.player.is_playing:
            Player.player.tape(end_speed = 0.0, duration = 3.0, cleanup_on_finish = True)
        
            logger.info("Window hidden, app will close in 3 seconds...")
            QTimer.singleShot(1700, self._exit_effects)
            QTimer.singleShot(3200, QApplication.instance().quit)
        
        else:
            self._exit_effects()
            QTimer.singleShot(1800, QApplication.instance().quit)

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL) 

    app = QApplication(sys.argv)

    prepare_default_settings(SettingsDict)
    load_settings()

    if CurrentSettings.get("msaa"):
        fmt = QSurfaceFormat()
        fmt.setSamples(CurrentSettings["msaa"])
        QSurfaceFormat.setDefaultFormat(fmt)

    if os.path.exists("System/Fonts/NDot57.otf"):
        QFontDatabase.addApplicationFont("System/Fonts/NDot57.otf")
        logger.info("Loaded font NDot57.otf")
    
    if os.path.exists("System/Fonts/NType82.otf"):
        QFontDatabase.addApplicationFont("System/Fonts/NType82.otf")
        logger.info("Loaded font NType82.otf")

    app.setWindowIcon(QIcon("System/Icons/Icon256.ico"))

    main_window = ApplicationWindow()
    main_window.show() 
    main_window.intro_overlay.start(670)

    Utils.ui_sound("Startup")
    sys.exit(app.exec_())

if __name__ == '__main__':
    mp.freeze_support()
    
    pid = os.getpid()
    logger.info(f"Main Process PID: {pid}")
    
    main()