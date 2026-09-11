import re
import random
import string

from PyQt6.QtGui import (
    QPainter,
    QTransform,
    QTextDocument
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

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine
)

from System.Interface.Timing import Timer

class TextGlitchMixin:
    def init_glitch(self, text: str) -> None:
        self.glitch_original_text  = text
        self.glitch_solved_indices = set()
        self.glitch_characters     = string.ascii_uppercase

        self.glitch_duration_ms    = 1000
        self.glitch_interval       = 24
        self.glitch_total_ticks    = 1
        self.glitch_current_tick   = 0

        self.glitch_timer = Timer(
            interval = self.glitch_interval,
            callback = self.glitch_step,
            parent   = self
        )

    def start_glitch(
            self,
            duration_ms: int = 1000,
            interval:    int = 24
        ) -> None:

        self.glitch_duration_ms  = duration_ms
        self.glitch_interval     = interval
        self.glitch_total_ticks  = max(1, round(duration_ms / interval))
        self.glitch_current_tick = 0

        self.glitch_solved_indices.clear()

        for index, char in enumerate(self.glitch_original_text):
            if char in " `\n":
                self.glitch_solved_indices.add(index)

        self.glitch_timer.start(interval)

    def glitch_step(self) -> None:
        self.glitch_current_tick += 1

        glitchable_indices = [
            i for i, char in enumerate(self.glitch_original_text)
            if char not in " `\n"
        ]
        total_glitchable = len(glitchable_indices)

        progress = min(self.glitch_current_tick / self.glitch_total_ticks, 1.0)

        if total_glitchable == 0 or progress >= 1.0:
            self.setText(self.glitch_original_text)
            self.glitch_timer.stop()
            return

        expected_solved = round(total_glitchable * progress)

        non_glitchable_count = len(self.glitch_original_text) - total_glitchable
        current_solved       = len(self.glitch_solved_indices) - non_glitchable_count

        needed = expected_solved - current_solved

        if needed > 0:
            unsolved = list(set(glitchable_indices) - self.glitch_solved_indices)
            if unsolved:
                to_solve = random.sample(unsolved, min(needed, len(unsolved)))
                self.glitch_solved_indices.update(to_solve)

        new_text = []

        for index, character in enumerate(self.glitch_original_text):
            if index in self.glitch_solved_indices:
                new_text.append(character)
            
            else:
                new_text.append(random.choice(self.glitch_characters))

        self.setText("".join(new_text))

    def update_glitch_source_text(self, text: str) -> None:
        self.glitch_original_text = text

class TransformAnimationMixin:
    def init_transform_animation(self) -> None:
        self.animation_alignment = None
        
        self.scale_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "scale",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_transform_changed
        )

        self.rotation_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "rotation",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_transform_changed
        )

    def set_animation_alignment(self, alignment: Qt.AlignmentFlag | int) -> None:
        self.animation_alignment = alignment
        self.update()

    def set_scale(self, value: float, duration_ms: int = 200) -> None:
        self.scale_handle.set_target(value, duration_ms = duration_ms)

    def set_rotation(self, value: float, duration_ms: int = 200) -> None:
        self.rotation_handle.set_target(value, duration_ms = duration_ms)

    def pulse_scale(self, peak_scale: float = 1.2, duration_ms: int = 100) -> None:
        self.scale_handle.play_curve(
            keyframes                  = [(0.0, 1.0), (0.5, peak_scale), (1.0, 1.0)],
            duration_ms                = duration_ms,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def pulse_rotation(self, peak_angle: float, duration_ms: int = 100) -> None:
        self.rotation_handle.play_curve(
            keyframes       = [(0.0, 0.0), (0.5, peak_angle), (1.0, 0.0)],
            duration_ms     = duration_ms,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    def on_transform_changed(self, value: float) -> None:
        self.update()

    def build_paint_transform(self, rectangle: object, text_alignment: object) -> QTransform:
        alignment = self.animation_alignment if self.animation_alignment is not None else text_alignment

        if alignment & Qt.AlignmentFlag.AlignLeft:
            origin_x = 0.0

        elif alignment & Qt.AlignmentFlag.AlignRight:
            origin_x = float(rectangle.width())
        
        else:
            origin_x = rectangle.width() / 2.0

        if alignment & Qt.AlignmentFlag.AlignTop:
            origin_y = 0.0

        elif alignment & Qt.AlignmentFlag.AlignBottom:
            origin_y = float(rectangle.height())
        
        else:
            origin_y = rectangle.height() / 2.0

        scale     = self.scale_handle.value
        rotation  = self.rotation_handle.value
        transform = QTransform()

        transform.translate(origin_x, origin_y)
        transform.scale(scale, scale)
        transform.rotate(rotation)
        transform.translate(-origin_x, -origin_y)

        return transform

    def paint_transformed(self, draw_content: object) -> None:
        painter = QPainter(self)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rectangle = self.contentsRect()
        alignment = self.alignment()

        painter.setTransform(self.build_paint_transform(rectangle, alignment))

        draw_content(painter, rectangle, alignment)

        painter.end()

@Dev.track_ram
class TitleLabel(Lifecycle.LoomAnimationMixin, TextGlitchMixin, TransformAnimationMixin, QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)

        self.init_glitch(text)
        self.init_transform_animation()

        self.setContentsMargins(0, 0, 0, 4)
        self.setFont(Utils.NType(12))
        self.setStyleSheet(Styles.Other.Font)

    def paintEvent(self, event: QEvent) -> None:
        self.paint_transformed(self.draw_content)

    def draw_content(self, painter: QPainter, rectangle: object, alignment: object) -> None:
        painter.setPen(self.palette().windowText().color())
        painter.setFont(self.font())

        text_flags = alignment | (Qt.TextFlag.TextWordWrap if self.wordWrap() else 0)

        painter.drawText(rectangle, text_flags, self.text())

@Dev.track_ram
class DescriptionLabel(TextGlitchMixin, TransformAnimationMixin, QLabel):
    def __init__(
            self,
            text:          str,
            maximum_width: int | None = None
        ) -> None:

        super().__init__(self.formatted(text))

        self.init_glitch(text)
        self.init_transform_animation()

        self.setFont(Utils.NType(10))
        self.setStyleSheet(Styles.Other.SecondFont)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setStyleSheet(Styles.Other.Label)
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

        if not self.glitch_timer.isActive():
            self.update_glitch_source_text(text)

    def paintEvent(self, event: QEvent) -> None:
        self.paint_transformed(self.draw_content)

    def draw_content(self, painter: QPainter, rectangle: object, alignment: object) -> None:
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(self.font())
        document.setTextWidth(rectangle.width())
        document.setHtml(self.text())

        document_height = document.size().height()

        if alignment & Qt.AlignmentFlag.AlignVCenter:
            offset_y = (rectangle.height() - document_height) / 2.0

        elif alignment & Qt.AlignmentFlag.AlignBottom:
            offset_y = rectangle.height() - document_height

        else:
            offset_y = 0.0

        painter.save()
        painter.translate(rectangle.topLeft())
        painter.translate(0, offset_y)
        document.drawContents(painter)
        painter.restore()

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