import random

from PyQt6.QtGui import QPixmap

from PyQt6.QtWidgets import (
    QWidget,
    QMessageBox
)

from System.Services import Player

from System.Interface import (
    Timing,
    Widgets
)

from System.Interface.Windows import FloatingWindowGPU

# Walter Window

class WalterWindow(FloatingWindowGPU):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("walter.", parent = parent)

        self.path_open   = "System/Assets/Image/Walter"
        self.path_closed = "System/Assets/Image/WalterClosed"

        self.is_walter_closed = True

        self.walter        = QPixmap(self.path_open)
        self.walter_closed = QPixmap(self.path_closed)

        self.label = Widgets.DescriptionLabel("Turn on the Waltuh, yes, click it.")
        self.image = Widgets.Image(self.walter_closed)

        self.content_layout.addWidget(self.image)
        self.content_layout.addWidget(self.label)

        self.chaos_timer = Timing.Timer(20,   self.chaos_mode,        parent = self)
        self.stop_timer  = Timing.Timer(8500, self.chaos_timer.stop,  True, parent = self)

        self.image.clicked.connect(self.switch_walter)

    def switch_walter(self) -> None:
        self.is_walter_closed = not self.is_walter_closed

        current_pixmap = self.walter_closed if self.is_walter_closed else self.walter
        self.image.update_image(current_pixmap)

        if self.is_walter_closed:
            self.label.setText("Don't do that.")
            self.chaos_timer.stop()
            self.stop_timer.stop()
            return

        Player.ui_player.play_sound("Packs/NOK/HEVCharger", speed = 1.0, enable_tone_randomizer = False)
        self.label.setText("Such a good boy.")
        self.chaos_timer.start()
        self.stop_timer.start()

        if random.random() > 0.4:
            self.spam_errors()

    def spam_errors(self) -> None:
        for offset_index in range(12):
            message_box = QMessageBox()
            message_box.setIcon(QMessageBox.Icon.Critical)
            message_box.setWindowTitle("walthu")
            message_box.setText("waltuyh")
            message_box.setInformativeText("the waltuh")
            message_box.move(100 + (offset_index * 30), 100 + (offset_index * 30))
            message_box.show()

        for offset_index in range(12):
            message_box = QMessageBox()
            message_box.setIcon(QMessageBox.Icon.Critical)
            message_box.setWindowTitle("walthu")
            message_box.setText("waltuyh")
            message_box.setInformativeText("the waltuh")
            message_box.move(1000 - (offset_index * 30), 1000 - (offset_index * 30))
            message_box.show()