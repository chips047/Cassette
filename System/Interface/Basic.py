import re
import random
import string

from loguru import logger

from PyQt6.QtGui import (
    QIcon,
    QPainter,
    QTransform,
    QFontMetrics
)

from PyQt6.QtCore import (
    Qt,
    QSize,
    QPoint,
    QEvent,
    QTimer,
    QObject,
    pyqtSignal,
    pyqtProperty
)

from PyQt6.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QPushButton
)

from System.Common import (
    Utils,
    Styles
)

from System.Services import Player

class Timer(QTimer):
    def __init__(
        self,
        interval:    int    = 1000,
        callback:    object = None,
        auto_start:  bool   = False,
        single_shot: bool   = False,
        parent:      QTimer = None
    ) -> None:

        super().__init__(parent)

        self.setInterval(interval)
        self.setSingleShot(single_shot)

        if callback:
            self.timeout.connect(callback)

        if auto_start:
            self.start()

class GlitchyButton(QPushButton):
    glitch_started = pyqtSignal()

    def __init__(
        self,
        title:               str   = None,
        enable_glitch_sound: bool  = True,
        icon:                QIcon = None
    ) -> None:

        super().__init__(title)

        self.glitch_timer = Timer(
            interval = 24,
            callback = self.glitch_step,
            parent   = self
        )
        
        self.glitch_steps_left = 0

        self.original_position = None
        self.original_size     = None

        self.enable_glitch_sound  = enable_glitch_sound
        self.original_button_text = super().text()

        if icon:
            self.setIcon(icon)
        
        self.setFont(Utils.NType(10))
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.installEventFilter(self)

    def random_ass_text(self, length: int) -> str:
        characters = string.ascii_letters + string.digits
        return "".join(random.choices(characters, k = length))
    
    def glitch_step(self) -> None:
        if self.glitch_steps_left <= 0:
            self.move(self.original_position)
            self.resize(self.original_size)
            self.setText(self.original_button_text)
            
            self.glitch_timer.stop()
            
            return

        font_metrics     = QFontMetrics(self.font())
        average_width    = font_metrics.averageCharWidth()
        estimated_length = self.width() // average_width
        estimated_length = max(1, min(200, estimated_length))

        self.setText(self.random_ass_text(estimated_length))

        difference_x      = random.randint(-3, 3)
        difference_y      = random.randint(-4, 4)
        difference_width  = random.randint(-4, 4)
        difference_height = random.randint(-2, 2)

        self.move(self.original_position + QPoint(difference_x, difference_y))

        self.resize(
            QSize(
                max(10, self.original_size.width()  + difference_width),
                max(10, self.original_size.height() + difference_height)
            )
        )

        self.glitch_steps_left = self.glitch_steps_left - 1

    def start_glitch(self) -> None:
        if self.enable_glitch_sound:
            Player.ui_player.play_sound("Reject")

        self.glitch_started.emit()

        if self.glitch_timer.isActive():
            return

        self.original_position = self.pos()
        self.original_size     = self.size()

        self.setFixedSize(self.original_size)

        self.glitch_steps_left = 7

        self.glitch_timer.start()
    
    def eventFilter(
        self,
        target_object: QObject,
        event:         QEvent
    ) -> bool:
        
        if target_object != self:
            return super().eventFilter(target_object, event)

        if event.type() != QEvent.Type.MouseButtonPress:
            return super().eventFilter(target_object, event)

        if self.isEnabled():
            return super().eventFilter(target_object, event)
        
        self.start_glitch()
        
        return True

class NothingButton(GlitchyButton):
    def __init__(
        self,
        title:               str   = None,
        enable_glitch_sound: bool  = True,
        icon:                QIcon = None
    ) -> None:

        super().__init__(title, enable_glitch_sound, icon)

        self.setStyleSheet(Styles.Buttons.NothingStyledButton)

class Button(GlitchyButton):
    def __init__(
        self,
        title:               str   = None,
        enable_glitch_sound: bool  = True,
        icon:                QIcon = None
    ) -> None:

        super().__init__(title, enable_glitch_sound, icon)

        self.setStyleSheet(Styles.Buttons.NormalButton)

class ButtonWithOutline(GlitchyButton):
    def __init__(
        self,
        title:               str   = None,
        enable_glitch_sound: bool  = True,
        icon:                QIcon = None
    ) -> None:

        super().__init__(title, enable_glitch_sound, icon)

        self.setStyleSheet(Styles.Buttons.NormalButtonWithBorder)

class ButtonWithOutlineSlim(GlitchyButton):
    def __init__(
        self,
        title:               str   = None,
        enable_glitch_sound: bool  = True,
        icon:                QIcon = None
    ) -> None:

        super().__init__(title, enable_glitch_sound, icon)

        self.setStyleSheet(Styles.Buttons.NormalButtonWithBorderSlim)
        self.setFixedHeight(28)

class IconButtonSmall(GlitchyButton):
    def __init__(
            self,
            icon:                QIcon,
            enable_glitch_sound: bool = True
        ):

        super().__init__(None, enable_glitch_sound, icon)

        self.setIcon(icon)
        self.setFixedSize(53, 28)
        self.setIconSize(QSize(22, 22))
        self.setStyleSheet(Styles.Buttons.MainMenu.SmallButton)

class ButtonRow(QHBoxLayout):
    def __init__(
        self,
        buttons: list[tuple],
        spacing: int = 10
    ) -> None:
        
        super().__init__()

        self.setSpacing(spacing)

        self.buttons: dict[str, GlitchyButton] = {}

        for item in buttons:
            if len(item) == 4:
                class_name, text, callback, glitch = item
            
            else:
                class_name, text, callback = item
                glitch                     = True

            button = class_name(
                title               = text,
                enable_glitch_sound = glitch
            )

            button.clicked.connect(callback)

            self.addWidget(button)

            self.buttons[text] = button

    def get_button(self, text: str) -> GlitchyButton | None:
        return self.buttons.get(text)

class NavButton(QPushButton):
    def __init__(
        self,
        text:   str,
        parent: QWidget = None
    ) -> None:
        
        super().__init__(parent)
        
        self.setText(text)
        self.setFont(Utils.NType(10))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(32)
        
        self.active_style   = Styles.Buttons.Settings.CategoryActiveButton
        self.inactive_style = Styles.Buttons.Settings.CategoryInactiveButton
        
        self.setActive(False)
    
    def setActive(self, is_active: bool) -> None:
        self.setChecked(is_active)
        style = self.active_style if is_active else self.inactive_style
        self.setStyleSheet(style)

class OptionButton(QPushButton):
    def __init__(
            self,
            text:     str,
            accent:   bool   = False,
            callback: object = None
        ) -> None:
        
        super().__init__(text)


        self.setStyleSheet(
            Styles.Buttons.MainMenu.AccentButton if accent
            else Styles.Buttons.MainMenu.NormalButton
        )

        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(Utils.NType(10))

        if callback:
            self.clicked.connect(callback)

class TitleLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)

        self.current_scale    = 1.0
        self.current_rotation = 0.0

        self.setContentsMargins(0, 0, 0, 4)
        self.setFont(Utils.NType(12))
        self.setStyleSheet(Styles.Other.Font)

        self.original_text  = text
        self.display_text   = list(text)
        self.solved_indices = set()

        self.characters = string.ascii_uppercase

        self.decode_chance = 0.2

        self.glitch_timer = Timer(
            interval = 24,
            callback = self.text_glitch_step,
            parent   = self
        )

    def start_glitch(self, decode_chance: float = 0.2, interval: int = 24) -> None:
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

    @pyqtProperty(float)
    def scale(self) -> float:
        return self.current_scale

    @scale.setter
    def scale(self, value: float) -> None:
        self.current_scale = value
        self.update()

    @pyqtProperty(float)
    def rotation(self) -> float:
        return self.current_rotation

    @rotation.setter
    def rotation(self, value: float) -> None:
        self.current_rotation = value
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

        transform = QTransform()

        transform.translate(position_x, center_y)
        transform.scale(self.current_scale, self.current_scale)
        transform.translate(-position_x, -center_y)
        transform.translate(center_x, center_y)
        transform.rotate(self.current_rotation)
        transform.translate(-center_x, -center_y)

        painter.setTransform(transform)
        painter.setPen(self.palette().windowText().color())
        painter.setFont(self.font())

        text_flags = alignment | (Qt.TextFlag.TextWordWrap if self.wordWrap() else 0)

        painter.drawText(rectangle, text_flags, self.text())

        painter.end()

class DescriptionLabel(QLabel):
    def __init__(
        self,
        text:          str,
        maximum_width: int | None = None
    ) -> None:
        
        text = re.sub(r"`([^`]*)`", r'<span style="color:white;">\1</span>', text)
        text = text.replace("\n", "<br>")

        super().__init__(text)

        self.setFont(Utils.NType(10))
        self.setStyleSheet(Styles.Other.SecondFont)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)

        if not maximum_width:
            return
        
        self.setMaximumWidth(maximum_width)
    
    def setText(self, text: str) -> None:
        text = re.sub(r"`([^`]*)`", r'<span style="color:white;">\1</span>', text)
        text = text.replace("\n", "<br>")

        return super().setText(text)

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