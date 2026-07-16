import re
import random
import string

from PyQt6.QtGui import (
    QPainter,
    QTransform
)

from PyQt6.QtCore import (
    Qt,
    QEvent,
    pyqtSignal
)

from PyQt6.QtWidgets import QLabel

from System.Common import (
    Dev,
    Utils,
    Styles
)

from System.Interface.Animation import Lifecycle

from System.Interface.Animation.LoomEngine import (
    Easing,
    MixMode,
    ui_engine
)

from System.Interface.Timing import Timer

# Labels

@Dev.track_ram
class TitleLabel(Lifecycle.LoomAnimationMixin, QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)

        self.setContentsMargins(0, 0, 0, 4)
        self.setFont(Utils.NType(12))
        self.setStyleSheet(Styles.Other.Font)

        self.original_text  = text
        self.solved_indices = set()

        self.characters    = string.ascii_uppercase
        self.decode_chance = 0.2

        self.scale_handle = ui_engine.bind(
            owner      = self,
            name       = "titleScale",
            base_value = 1.0,
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_transform_changed
        )

        self.rotation_handle = ui_engine.bind(
            owner      = self,
            name       = "titleRotation",
            base_value = 0.0,
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_transform_changed
        )

        self.glitch_timer = Timer(
            interval = 24,
            callback = self.text_glitch_step,
            parent   = self
        )

    def start_glitch(
            self,
            decode_chance: float = 0.2,
            interval:      int   = 24
        ) -> None:

        self.decode_chance = decode_chance

        self.solved_indices.clear()
        self.glitch_timer.start(interval)

    def text_glitch_step(self) -> None:
        new_text = []

        for index, character in enumerate(self.original_text):
            if index in self.solved_indices or character == " ":
                new_text.append(character)
                continue

            if random.random() < self.decode_chance:
                self.solved_indices.add(index)
                new_text.append(character)
                continue

            new_text.append(random.choice(self.characters))

        self.setText("".join(new_text))

        if len(self.solved_indices) < len(self.original_text.replace(" ", "")):
            return

        self.setText(self.original_text)
        self.glitch_timer.stop()

    def set_scale(
            self,
            value:       float,
            duration_ms: int   = 200
        ) -> None:

        self.scale_handle.set_target(value, duration_ms = duration_ms)

    def set_rotation(
            self,
            value:       float,
            duration_ms: int   = 200
        ) -> None:

        self.rotation_handle.set_target(value, duration_ms = duration_ms)

    def pulse_scale(
            self,
            peak_scale:  float = 1.2,
            duration_ms: int   = 100
        ) -> None:

        self.scale_handle.play_curve(
            keyframes       = [(0.0, 1.0), (0.5, peak_scale), (1.0, 1.0)],
            duration_ms     = duration_ms,
            easing_function = Easing.ease_out_cubic
        )

    def pulse_rotation(
            self,
            peak_angle:  float,
            duration_ms: int = 100
        ) -> None:

        self.rotation_handle.play_curve(
            keyframes       = [(0.0, 0.0), (0.5, peak_angle), (1.0, 0.0)],
            duration_ms     = duration_ms,
            easing_function = Easing.ease_out_cubic
        )

    def on_transform_changed(self, value: float) -> None:
        self.update()

    def paintEvent(self, event: QEvent) -> None:
        painter = QPainter(self)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rectangle = self.contentsRect()
        alignment = self.alignment()

        center_x = rectangle.width()  / 2.0
        center_y = rectangle.height() / 2.0

        if alignment & Qt.AlignmentFlag.AlignLeft:
            position_x = 0.0

        elif alignment & Qt.AlignmentFlag.AlignRight:
            position_x = float(rectangle.width())

        else:
            position_x = center_x

        scale    = self.scale_handle.value
        rotation = self.rotation_handle.value

        transform = QTransform()

        transform.translate(position_x, center_y)
        transform.scale(scale, scale)
        transform.translate(-position_x, -center_y)
        transform.translate(center_x, center_y)
        transform.rotate(rotation)
        transform.translate(-center_x, -center_y)

        painter.setTransform(transform)
        painter.setPen(self.palette().windowText().color())
        painter.setFont(self.font())

        text_flags = alignment | (Qt.TextFlag.TextWordWrap if self.wordWrap() else 0)

        painter.drawText(rectangle, text_flags, self.text())
        painter.end()

@Dev.track_ram
class DescriptionLabel(QLabel):
    def __init__(
            self,
            text:          str,
            maximum_width: int | None = None
        ) -> None:

        super().__init__(self.formatted(text))

        self.setFont(Utils.NType(10))
        self.setStyleSheet(Styles.Other.SecondFont)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)

        if not maximum_width:
            return

        self.setMaximumWidth(maximum_width)

    def formatted(self, text: str) -> str:
        text = re.sub(r"`([^`]*)`", r'<span style="color:white;">\1</span>', text)
        text = text.replace("\n", "<br>")

        return text

    def setText(self, text: str) -> None:
        super().setText(self.formatted(text))

@Dev.track_ram
class Image(QLabel):
    clicked = pyqtSignal()

    def __init__(self, pixmap: object) -> None:
        super().__init__()

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_image(pixmap)

    def update_image(self, pixmap: object) -> None:
        self.setPixmap(pixmap)

    def mousePressEvent(self, event: QEvent) -> None:
        self.clicked.emit()