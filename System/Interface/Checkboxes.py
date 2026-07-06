from PyQt6.QtCore import (
    Qt,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QLabel,
    QCheckBox,
    QHBoxLayout
)

from System.Common import (
    Dev,
    Utils,
    Styles
)

from System.Services import Player
from System.Interface.Controls import BaseControlContainer

# Checkbox

@Dev.track_ram
class Checkbox(QCheckBox):
    def __init__(
            self,
            name:    str,
            default: bool = False
        ) -> None:

        super().__init__(name)

        self.setFont(Utils.NType(10))
        self.setStyleSheet(Styles.Controls.Checkbox)
        self.setChecked(default)

    def nextCheckState(self) -> None:
        super().nextCheckState()

        tone = 1.0 if self.isChecked() else 0.82
        Player.ui_player.play_sound("Click/Checkbox", setting_key = "checkbox_sounds", speed = tone)

@Dev.track_ram
class CheckboxWithLabel(BaseControlContainer):
    stateChanged = pyqtSignal(bool)

    def __init__(
            self,
            title:       str,
            description: str,
            default:     bool = False
        ) -> None:

        super().__init__(inner_layout_type = QHBoxLayout)
 
        self.setMaximumHeight(60)
        self.setup_checkbox(title, default)
        self.setup_description(description)

    def setup_checkbox(
            self,
            title:   str,
            default: bool
        ) -> None:

        self.checkbox = Checkbox(title)
        self.checkbox.setChecked(default)
        self.inner_layout.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignVCenter)

    def setup_description(self, description: str) -> None:
        self.description_label = QLabel(description, self.container_background)
        self.description_label.setFont(Utils.NType(10))
        self.description_label.setStyleSheet(f"color: {Styles.Colors.SubtleFontColor}; padding: 0px; border: none;")
        self.inner_layout.addWidget(self.description_label, 1, Qt.AlignmentFlag.AlignVCenter)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)
        self.stateChanged.emit(checked)

    def setValue(self, value: bool) -> None:
        self.setChecked(value)