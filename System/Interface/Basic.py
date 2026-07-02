import re
import random
import string

from loguru import logger

from PyQt6.QtGui import (
    QIcon,
    QPainter,
    QTransform,
    QPaintEvent,
    QFontMetrics,
    QMouseEvent
)

from PyQt6.QtCore import (
    Qt,
    QSize,
    QEvent,
    QPoint,
    QTimer,
    QObject,
    pyqtSignal,
    QEasingCurve,
    pyqtProperty,
    QPropertyAnimation
)

from PyQt6.QtWidgets import (
    QLabel,
    QStyle,
    QWidget,
    QPushButton,
    QHBoxLayout,
    QStyleOptionButton
)

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Services import Player

# Logic Classes

class Timer(QTimer):
    def __init__(
        self,
        interval   : int    = 1000,
        callback   : object = None,
        auto_start : bool   = False,
        single_shot: bool   = False,
        parent     : QTimer = None
    ) -> None:

        super().__init__(parent)

        self.setInterval(interval)
        self.setSingleShot(single_shot)

        if interval < 15:
            logger.debug(f"Creating {interval}ms timer with precise profile")
            self.setTimerType(Qt.TimerType.PreciseTimer)

        if callback:
            self.timeout.connect(callback)

        if auto_start:
            self.start()

# Buttons

class BaseButton(QPushButton):
    right_clicked  = pyqtSignal()
    middle_clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    glitch_started = pyqtSignal()

    def __init__(
        self,
        text                : str     = None,
        icon                : QIcon   = None,
        parent              : QWidget = None,
        enable_glitch_effect: bool    = False
    ) -> None: 

        if icon:
            super().__init__(icon, text, parent)

        else:
            super().__init__(text, parent)

        self.press_scale  = 1.0
        self.fast_clicked = False
        
        self.setup_press_animation()

        if enable_glitch_effect:
            self.setup_glitch_effect()

        self.pressed.connect(self.animate_press)
        self.released.connect(self.animate_release)

    def setup_press_animation(self) -> None:
        self.press_animation = QPropertyAnimation(self, b"pressScale")
        self.press_animation.setDuration(100)
        self.press_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    
    def setup_glitch_effect(self) -> None:
        self.glitch_timer = Timer(
            interval      = 24,
            callback      = self.glitch_step,
            parent        = self
        )

        self.original_button_text = super().text()

        self.glitch_steps_left    = 0

        self.original_position    = None
        self.original_size        = None

        self.glitch_sound_locked  = False

        self.installEventFilter(self)

    @pyqtProperty(float)
    def pressScale(self) -> float:
        return self.press_scale

    @pressScale.setter
    def pressScale(self, value: float) -> None:
        self.press_scale = value
        self.update()

    def animate_press(self) -> None:
        self.press_animation.stop()
        self.press_animation.setEndValue(0.97)
        self.press_animation.start()

    def animate_release(self) -> None:
        self.press_animation.stop()
        self.press_animation.setEndValue(1.0)
        self.press_animation.start()
    
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
        if not self.glitch_sound_locked:
            Player.ui_player.play_sound("Reject")

        self.glitch_started.emit()

        if self.glitch_timer.isActive():
            return

        self.original_position = self.pos()
        self.original_size     = self.size()

        self.setFixedSize(self.original_size)

        self.glitch_steps_left = 7

        self.glitch_timer.start()
    
    def block_glitch_sound(self) -> None:
        self.glitch_sound_locked = True
    
    def unblock_glitch_sound(self) -> None:
        self.glitch_sound_locked = False

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(self.press_scale, self.press_scale)
        painter.translate(-self.width() / 2, -self.height() / 2)

        option = QStyleOptionButton()
        self.initStyleOption(option)

        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.middle_clicked.emit()

        if event.button() == Qt.MouseButton.LeftButton:
            if Constants.current_settings["mouse_click_behavior"] == "fast":
                self.setDown(True)
                self.pressed.emit()
                self.clicked.emit()

                self.fast_clicked = True

                return
            
            else:
                self.fast_clicked = False
                
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.fast_clicked:
            self.setDown(False)
            self.released.emit()

            self.fast_clicked = False

            return
            
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        
        super().mouseDoubleClickEvent(event)
    
    def eventFilter(
        self,
        target_object: QObject,
        event        : QEvent
    ) -> bool:
        
        if target_object != self:
            return super().eventFilter(target_object, event)

        if event.type() != QEvent.Type.MouseButtonPress:
            return super().eventFilter(target_object, event)

        if self.isEnabled():
            return super().eventFilter(target_object, event)
        
        self.start_glitch()
        
        return True
    
    def random_ass_text(self, length: int) -> str:
        """Watching at my code? Do you like it? I tried my best."""

        characters = string.ascii_letters + string.digits
        return "".join(random.choices(characters, k = length))

class RectangularButton(BaseButton):
    def __init__(
        self,
        text                : str     = None,
        icon                : QIcon   = None,
        parent              : QWidget = None,
        enable_glitch_effect: bool    = True
    ) -> None:

        super().__init__(text, icon, parent, enable_glitch_effect)

        self.setFont(Utils.NType(10))
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

class NothingButton(RectangularButton):
    def __init__(
        self,
        text                : str     = None,
        icon                : QIcon   = None,
        parent              : QWidget = None,
        enable_glitch_effect: bool    = True
    ) -> None: 

        super().__init__(text, icon, parent, enable_glitch_effect)
        self.setStyleSheet(Styles.Buttons.NothingStyledButton)

class Button(RectangularButton):
    def __init__(
        self,
        text                : str     = None,
        icon                : QIcon   = None,
        parent              : QWidget = None,
        enable_glitch_effect: bool    = True
    ) -> None: 

        super().__init__(text, icon, parent, enable_glitch_effect)
        self.setStyleSheet(Styles.Buttons.NormalButton)

class ButtonWithOutline(RectangularButton):
    def __init__(
        self,
        text                : str     = None,
        icon                : QIcon   = None,
        parent              : QWidget = None,
        enable_glitch_effect: bool    = True
    ) -> None:

        super().__init__(text, icon, parent, enable_glitch_effect)
        self.setStyleSheet(Styles.Buttons.NormalButtonWithBorder)

class ButtonWithOutlineSlim(RectangularButton):
    def __init__(
        self,
        text                : str     = None,
        icon                : QIcon   = None,
        parent              : QWidget = None,
        enable_glitch_effect: bool    = True
    ) -> None:

        super().__init__(text, icon, parent, enable_glitch_effect)
        self.setStyleSheet(Styles.Buttons.NormalButtonWithBorderSlim)
        self.setFixedHeight(28)

class IconButtonSmall(RectangularButton):
    def __init__(
        self,
        icon                : QIcon   = None,
        parent              : QWidget = None,
        enable_glitch_effect: bool    = True
    ) -> None:

        super().__init__(icon = icon, parent = parent, enable_glitch_effect = enable_glitch_effect)

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

        self.buttons: dict[str, RectangularButton] = {}

        for item in buttons:
            if len(item) == 4:
                class_name, text, callback, glitch = item
            
            else:
                class_name, text, callback = item
                glitch                     = True

            button = class_name(
                text                 = text,
                enable_glitch_effect = glitch
            )

            button.clicked.connect(callback)

            self.addWidget(button)

            self.buttons[text] = button

    def get_button(self, text: str) -> RectangularButton | None:
        return self.buttons.get(text)

class NavButton(BaseButton):
    def __init__(
        self,
        text  : str,
        parent: QWidget = None
    ) -> None:
        
        super().__init__(text = text, parent = parent)
        
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

class OptionButton(BaseButton):
    def __init__(
            self,
            text    : str,
            accent  : bool   = False,
            callback: object = None
        ) -> None:
        
        super().__init__(text = text)
        
        self.setStyleSheet(
            Styles.Buttons.MainMenu.AccentButton if accent
            else Styles.Buttons.MainMenu.NormalButton
        )
        
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(Utils.NType(10))

        if callback:
            self.clicked.connect(callback)

# Labels

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
        text         : str,
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