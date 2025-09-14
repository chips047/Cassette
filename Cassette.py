try:
    import os
    import sys
    
    #sys.stdout = open(os.devnull, 'w')
    #sys.stderr = open(os.devnull, 'w')
    
    #os.environ["QT_FONT_DPI"] = "120"
    #os.environ["QT_SCALE_FACTOR"] = "2"
    sys.path.insert(0, os.path.dirname(__file__))

    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
    
    from System import Styles

except ModuleNotFoundError as e:
    from System import Utils

os.chdir(os.path.dirname(os.path.abspath(__file__)))

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
QApplication.setAttribute(Qt.AA_UseDesktopOpenGL) 

app = QApplication(sys.argv)

from System import Utils
from loguru import logger
from System.Constants import *
from System.ProjectMenu import MainMenu
from System.Compositor import CompositorWidget

app.setWindowIcon(Utils.Icons.WindowIcon)

class ApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cassette")
        self.resize(1280, 800)
        logger.info("Starting up...")

        prepare_default_settings(SettingsDict)
        load_settings()
        
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.main_menu_widget = MainMenu(self)
        self.compositor_widget = CompositorWidget()

        self.stack.addWidget(self.main_menu_widget)
        self.stack.addWidget(self.compositor_widget)

        self.main_menu_widget.composition_created.connect(self.show_compositor)
        self.compositor_widget.back_to_main_menu_requested.connect(self.hide_compositor_and_show_main_menu)

        self.stack.setCurrentWidget(self.main_menu_widget)
        self.setStyleSheet(f"background-color: {Styles.Colors.background};")
        self.center_window()

    def center_window(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def fade_out(self, widget):
        logger.info("Fading out")
        
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)

        self.anim_out = QPropertyAnimation(effect, b"opacity")
        self.anim_out.setDuration(300)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.OutCubic)
        return self.anim_out

    def fade_in(self, widget):
        logger.info("Fading in")
        
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)

        effect.setOpacity(0.0) 
        
        self.anim_in = QPropertyAnimation(effect, b"opacity")
        self.anim_in.setDuration(400)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.setEasingCurve(QEasingCurve.InCubic)
        return self.anim_in

    @pyqtSlot(object)
    def show_compositor(self, composition):
        self.compositor_widget.initialize_compositor(composition.cropped_audiofile_path, composition)
        anim_out_menu = self.fade_out(self.main_menu_widget)

        def on_fade_out_finished():
            self.main_menu_widget.setVisible(False)
            self.main_menu_widget.setGraphicsEffect(None)

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

            anim_in_compositor = self.fade_in(self.compositor_widget)
            anim_in_compositor.start()

            Utils.ui_sound("Eject")
            self.anim_move.start(QAbstractAnimation.DeleteWhenStopped)

        anim_out_menu.finished.connect(on_fade_out_finished)
        anim_out_menu.start()
    
    @pyqtSlot()
    def hide_compositor_and_show_main_menu(self):
        if hasattr(self.compositor_widget, "composition"):
            try:
                self.compositor_widget.composition.syncer.stop_scanning_loop()
            
            except Exception:
                pass

        logger.info("Fading out compositor")
        self.anim_out_compositor = self.fade_out(self.compositor_widget)

        def on_fade_out_compositor_finished():
            self.compositor_widget.setVisible(False)
            self.compositor_widget.cleanup()

            initial_main_menu_geometry = self.stack.geometry()
            offset_y = 350
            self.main_menu_widget.setGeometry(
                initial_main_menu_geometry.x(),
                initial_main_menu_geometry.y() + offset_y,
                initial_main_menu_geometry.width(),
                initial_main_menu_geometry.height()
            )

            self.stack.setCurrentWidget(self.main_menu_widget)
            self.main_menu_widget.setVisible(True)

            menu_effect = self.main_menu_widget.graphicsEffect()
            if not isinstance(menu_effect, QGraphicsOpacityEffect):
                menu_effect = QGraphicsOpacityEffect(self.main_menu_widget)
                self.main_menu_widget.setGraphicsEffect(menu_effect)
            
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

            Utils.ui_sound("Eject")

            self.anim_in_main_menu.start()
            self.anim_move_main_menu.start()

        self.anim_out_compositor.finished.connect(on_fade_out_compositor_finished)
        self.anim_out_compositor.start()
    
    def closeEvent(self, event):
        self.compositor_widget.closeEvent(event)
        super().closeEvent(event)

if __name__ == '__main__':
    if os.path.exists("System/Fonts/NDot57.otf"):
        QFontDatabase.addApplicationFont("System/Fonts/NDot57.otf")
        logger.info("Loaded font")
    
    if os.path.exists("System/Fonts/NType82.otf"):
        QFontDatabase.addApplicationFont("System/Fonts/NType82.otf")
        logger.info("Loaded font")

    main_window = ApplicationWindow()
    main_window.show()

    Utils.ui_sound("Start")
    sys.exit(app.exec_())