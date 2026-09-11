import random

from PyQt6.QtWidgets import (
    QWidget,
    QApplication
)

from System.Services import Player

from System.Interface import Widgets

from System.Interface.Animation import LoomEngine
from System.Interface.Windows   import FloatingWindowGPU

# Error Window

class ErrorWindow(FloatingWindowGPU):
    def __init__(
            self,
            title:       str,
            description: str,
            button_text: str            = "Cool",
            parent:      QWidget | None = None
        ) -> None:

        super().__init__(title, parent = parent)

        ok_button   = Widgets.NothingButton(button_text)
        copy_button = Widgets.ButtonWithOutline("Copy error details")

        self.description_label = Widgets.DescriptionLabel(description, 600)

        self.content_layout.addWidget(self.description_label)
        self.content_layout.addWidget(copy_button)
        self.content_layout.addWidget(ok_button)

        ok_button.clicked.connect(self.on_ok)
        copy_button.clicked.connect(self.copy_error_details)

        self.description_label.setMaximumSize(900, 800)
        self.title_label.start_glitch()

    def copy_error_details(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.description_label.text())

    def open_window(self) -> None:
        if random.random() <= 0.995:
            super().open_window()
            return

        self.adjustSize()
        self.center_window()
        
        self.is_ready = True

        Player.ui_player.play_sound("Packs/NOK/Death")

        self.title_label.start_glitch(4000)

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.5), (1.0, 1.0)],
            duration_ms     = 12000,
            easing_function = LoomEngine.Easing.ease_out_quart
        )

        self.opacity_content_property.set_base(1.0)

        self.opacity_background_property.play_curve(
            keyframes       = [(0.0, 0.0), (1.0, 1.0)],
            duration_ms     = 3000,
            easing_function = LoomEngine.Easing.linear
        )