import random

from PyQt6.QtCore    import pyqtSignal
from PyQt6.QtWidgets import QWidget

from System.Common import Constants

from System.Services import (
    Player,
    ProjectSaver
)

from System.Interface import Widgets

from System.Interface.Windows import FloatingWindowGPU

# Export Dialog Window

class ExportDialogWindow(FloatingWindowGPU):
    selectionChanged = pyqtSignal(str)

    def __init__(
            self,
            composition: ProjectSaver.Composition,
            parent:      QWidget | None = None
        ) -> None:

        super().__init__("Export?", parent = parent)

        self.composition = composition

        original_model         = Constants.DEVICES[composition.model].short_name
        choices                = Constants.DEVICES[composition.model].port_variants + [original_model]

        self.combobox          = Widgets.Selector(choices, default_index = len(choices) - 1)
        self.watermark_textbox = Widgets.Textbox("text", max_length = 12, placeholder = "Dot Watermark")

        button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, random.choice(Constants.NO_TEXTS), self.on_cancel),
                (Widgets.ButtonWithOutline, "Export to every model",           self.export_all),
                (Widgets.NothingButton,     "Tape it",                         self.export)
            ]
        )

        self.content_layout.addWidget(self.combobox)
        self.content_layout.addWidget(self.watermark_textbox)
        self.content_layout.addLayout(button_row)

    def export(self) -> None:
        Player.ui_player.play_sound("App/ExportStart")

        model     = self.combobox.current_text()
        watermark = self.watermark_textbox.text() or "Cassette"

        self.composition.export(
            watermark,
            Constants.NUMBER_TO_CODE[model],
            open_folder = True
        )

    def export_all(self) -> None:
        if self.is_closing:
            return

        watermark = self.watermark_textbox.text() or "Cassette"

        self.on_ok()
        self.composition.export_all(watermark)