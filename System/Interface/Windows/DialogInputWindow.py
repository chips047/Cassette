import random

from PyQt6.QtCore    import QTimer
from PyQt6.QtWidgets import QWidget

from System.Common   import Constants
from System.Services import Player

from System.Interface import Widgets

from System.Interface.Windows import FloatingWindowGPU

# Dialog Input Window

class DialogInputWindow(FloatingWindowGPU):
    def __init__(
            self,
            title:       str            = "Input Dialog",
            placeholder: str            = "Type something...",
            min_number:  int            = 0,
            max_number:  int            = 100,
            max_length:  int            = 100,
            input_type:  str            = "number",
            parent:      QWidget | None = None
        ) -> None:

        super().__init__(title, parent = parent)

        self.close_attempt_count = 0

        self.input_field = Widgets.Textbox(input_type, min_number, max_number, max_length)
        self.input_field.setMinimumWidth(160)
        self.input_field.setPlaceholderText(placeholder)

        self.button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, random.choice(Constants.NO_TEXTS), self.on_cancel),
                (Widgets.NothingButton,     random.choice(Constants.OK_TEXTS), self.on_ok)
            ]
        )

        self.button_row.get_button_by_number(1).block_glitch_sound()

        self.content_layout.addWidget(self.input_field)
        self.content_layout.addLayout(self.button_row)

        self.input_field.returnPressed.connect(self.on_ok)

    def on_ok(self) -> None:
        if not self.input_field.text():
            self.button_row.get_button_by_number(1).start_glitch()
            self.play_disturb_animation()
            self.process_easter_egg()
            return

        super().on_ok()

    def process_easter_egg(self) -> None:
        self.close_attempt_count += 1

        if random.random() > 0.5:
            return

        if self.close_attempt_count == 50:
            Player.ui_player.play_sound("Packs/NOK/WAYD")

            if self.title_label:
                self.title_label.setText("What are you doing?")

        if self.close_attempt_count == 70:
            Player.ui_player.play_sound("Packs/NOK/HCYLWY")

            if self.title_label:
                self.title_label.setText("???")

        if self.close_attempt_count > 70:
            self.chaos_mode()

        if self.close_attempt_count == 100 and self.title_label:
            Player.ui_player.play_sound("Packs/NOK/ONYD")
            self.title_label.setText("Dividing by zero: 3")

            QTimer.singleShot(1000, lambda: self.title_label.setText("Dividing by zero: 2"))
            QTimer.singleShot(2000, lambda: self.title_label.setText("Dividing by zero: 1"))
            QTimer.singleShot(2100, lambda: Player.ui_player.play_sound("Packs/NOK/Charging"))
            QTimer.singleShot(2500, lambda: self.title_label.setText("LMAO"))
            QTimer.singleShot(3000, lambda: 1 / 0)

    def get_text(self) -> str:
        return self.input_field.text()