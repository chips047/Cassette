import random
import string

from PyQt6.QtGui import (
    QIcon,
    QPainter,
    QPaintEvent,
    QFontMetrics,
    QMouseEvent
)

from PyQt6.QtCore import (
    Qt,
    QSize,
    QEvent,
    QPoint,
    QObject,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QStyle,
    QWidget,
    QPushButton,
    QHBoxLayout,
    QStyleOptionButton
)
from loguru import logger

from System.Common import (
    Dev,
    Utils,
    Styles,
    Constants
)

from System.Services import Player

from System.Interface.Animation import Lifecycle

from System.Interface.Animation.LoomEngine import (
    Easing,
    MixMode,
    ui_engine
)

# Buttons

class BaseButton(Lifecycle.LoomAnimationMixin, QPushButton):
    right_clicked  = pyqtSignal()
    middle_clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    glitch_started = pyqtSignal()

    glitch_step_count = 7
    glitch_step_ms    = 24

    def __init__(
            self,
            text:                  str     = None,
            icon:                  QIcon   = None,
            parent:                QWidget = None,
            enable_glitch_effect:  bool    = False
        ) -> None:

        if icon:
            super().__init__(icon, text, parent)

        else:
            super().__init__(text, parent)

        self.fast_clicked          = False
        self.glitch_effect_enabled = enable_glitch_effect

        self.press_scale_handle = ui_engine.bind(
            owner      = self,
            name       = "pressScale",
            base_value = 1.0,
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_press_scale_changed
        )

        if enable_glitch_effect:
            self.setup_glitch_effect()

        self.pressed.connect(self.animate_press)
        self.released.connect(self.animate_release)

    def setup_glitch_effect(self) -> None:
        self.original_button_text = super().text()
        self.original_position    = None
        self.original_size        = None
        self.glitch_sound_locked  = False
        self.is_glitching         = False

        self.glitch_handle = ui_engine.bind(
            owner      = self,
            name       = "glitch",
            base_value = (self.original_button_text, QPoint(0, 0), QSize(0, 0)),
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_glitch_frame_changed
        )

        self.installEventFilter(self)

    def on_press_scale_changed(self, value: float) -> None:
        self.update()

    def animate_press(self) -> None:
        self.press_scale_handle.set_target(
            value           = 0.97,
            duration_ms     = 100,
            easing_function = Easing.ease_out_cubic
        )

    def animate_release(self) -> None:
        self.press_scale_handle.set_target(
            value           = 1.0,
            duration_ms     = 100,
            easing_function = Easing.ease_out_cubic
        )

    def on_glitch_frame_changed(self, frame: tuple) -> None:
        text, position_offset, size_offset = frame

        self.setText(text)
        self.move(self.original_position + position_offset)

        self.resize(
            QSize(
                max(10, self.original_size.width()  + size_offset.width()),
                max(10, self.original_size.height() + size_offset.height())
            )
        )

    def build_glitch_frames(self) -> list[tuple[int, tuple]]:
        font_metrics     = QFontMetrics(self.font())
        average_width    = font_metrics.averageCharWidth()
        estimated_length = max(1, min(200, self.width() // average_width))

        frames = []

        for _ in range(self.glitch_step_count):
            frames.append(
                (
                    self.glitch_step_ms,
                    (
                        self.random_ass_text(estimated_length),
                        QPoint(random.randint(-3, 3), random.randint(-4, 4)),
                        QSize(random.randint(-4, 4), random.randint(-2, 2))
                    )
                )
            )

        return frames

    def start_glitch(self) -> None:
        if not self.glitch_sound_locked:
            Player.ui_player.play_sound("Reject")

        self.glitch_started.emit()

        if self.is_glitching:
            return

        self.is_glitching      = True
        self.original_position = self.pos()
        self.original_size     = self.size()

        self.setFixedSize(self.original_size)

        self.glitch_handle.play_steps(
            steps    = self.build_glitch_frames(),
            finished = self.finish_glitch
        )

    def finish_glitch(self) -> None:
        self.move(self.original_position)
        self.resize(self.original_size)
        self.setText(self.original_button_text)

        self.is_glitching = False

    def block_glitch_sound(self) -> None:
        self.glitch_sound_locked = True

    def unblock_glitch_sound(self) -> None:
        self.glitch_sound_locked = False

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        press_scale = self.press_scale_handle.value

        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(press_scale, press_scale)
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

    def random_ass_text(self, length: int) -> str:
        characters = string.ascii_letters + string.digits
        return "".join(random.choices(characters, k = length))

class RectangularButton(BaseButton):
    def __init__(
            self,
            text:                  str     = None,
            icon:                  QIcon   = None,
            parent:                QWidget = None,
            enable_glitch_effect:  bool    = True
        ) -> None:

        super().__init__(text, icon, parent, enable_glitch_effect)

        self.setFont(Utils.NType(10))
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

@Dev.track_ram
class NothingButton(RectangularButton):
    def __init__(
            self,
            text:                  str     = None,
            icon:                  QIcon   = None,
            parent:                QWidget = None,
            enable_glitch_effect:  bool    = True
        ) -> None:

        super().__init__(text, icon, parent, enable_glitch_effect)
        self.setStyleSheet(Styles.Buttons.NothingStyledButton)

@Dev.track_ram
class Button(RectangularButton):
    def __init__(
            self,
            text:                  str     = None,
            icon:                  QIcon   = None,
            parent:                QWidget = None,
            enable_glitch_effect:  bool    = True
        ) -> None:

        super().__init__(text, icon, parent, enable_glitch_effect)
        self.setStyleSheet(Styles.Buttons.NormalButton)

@Dev.track_ram
class ButtonWithOutline(RectangularButton):
    def __init__(
            self,
            text:                  str     = None,
            icon:                  QIcon   = None,
            parent:                QWidget = None,
            enable_glitch_effect:  bool    = True
        ) -> None:

        super().__init__(text, icon, parent, enable_glitch_effect)
        self.setStyleSheet(Styles.Buttons.NormalButtonWithBorder)

@Dev.track_ram
class ButtonWithOutlineSlim(RectangularButton):
    def __init__(
            self,
            text:                  str     = None,
            icon:                  QIcon   = None,
            parent:                QWidget = None,
            enable_glitch_effect: bool    = True
        ) -> None:

        super().__init__(text, icon, parent, enable_glitch_effect)
        self.setStyleSheet(Styles.Buttons.NormalButtonWithBorderSlim)
        self.setFixedHeight(28)

@Dev.track_ram
class IconButtonSmall(RectangularButton):
    def __init__(
            self,
            icon:                  QIcon   = None,
            parent:                QWidget = None,
            enable_glitch_effect:  bool    = True
        ) -> None:

        super().__init__(icon = icon, parent = parent, enable_glitch_effect = enable_glitch_effect)

        self.setFixedSize(53, 28)
        self.setIconSize(QSize(22, 22))
        self.setStyleSheet(Styles.Buttons.MainMenu.SmallButton)

@Dev.track_ram
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
            class_name, text, callback, glitch = self.unpack_button_item(item)

            button = class_name(
                text                  = text,
                enable_glitch_effect = glitch
            )

            button.setMinimumWidth(120)
            button.clicked.connect(callback)

            self.addWidget(button)

            self.buttons[text] = button

    def unpack_button_item(self, item: tuple) -> tuple:
        if len(item) == 4:
            return item

        class_name, text, callback = item

        return class_name, text, callback, True

    def get_button(self, text: str) -> RectangularButton | None:
        return self.buttons.get(text)

@Dev.track_ram
class NavButton(BaseButton):
    def __init__(
            self,
            text:   str,
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

@Dev.track_ram
class OptionButton(BaseButton):
    def __init__(
            self,
            text:     str,
            accent:   bool   = False,
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