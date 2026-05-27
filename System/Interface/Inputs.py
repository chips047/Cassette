import random
import string
import webbrowser

from loguru import logger

from PyQt6.QtGui import (
    QIcon,
    QMouseEvent
)

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QPoint,
    QTimer,
    pyqtSignal,
    QEasingCurve,
    QAbstractAnimation,
    QPropertyAnimation
)

from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QSlider,
    QWidget,
    QCheckBox,
    QLineEdit,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QPushButton,
    QButtonGroup,
    QApplication
)

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Interface import (
    Basic,
    Windows
)

from System.Services import Player

class Textbox(QLineEdit):
    safeTextChanged = pyqtSignal(str)
    glitchStarted   = pyqtSignal()
    
    def __init__(
        self,
        input_type:   str,
        min_number:   int              = 0,
        max_number:   int              = 0,
        max_length:   int              = None,
        default_text: str              = None,
        placeholder:  str              = None
    ) -> None:
        
        super().__init__()
        
        self.input_type                = input_type
        self.min_number                = min_number
        self.max_number                = max_number
        self.max_length                = max_length
        self.default_text              = default_text
        
        self.is_default_text_set       = False
        self.animating                 = False
        self.is_key_pressed            = False
        self.arrow_pressed             = False
        self.arrow_direction           = 0
        self.glitch_steps_left         = 0
        self.glitch_blocked            = False
        
        self.original_position         = QPoint()
        self.original_textbox_position = QPoint()
        
        if placeholder:
            self.setPlaceholderText(placeholder)
        
        self.setFont(Utils.NType(11))
        self.setStyleSheet(Styles.Controls.FloatingTextBox)

        self.setAcceptDrops(False)
        
        self.textChanged.connect(self.schedule_input_animation)
        self.textChanged.connect(self.safe_emit)
        
        self.setup_timers()
        self.setup_animations()

    def setup_timers(self) -> None:
        self.shake_timer = Basic.Timer(
            30,
            self.animate_to_random_position,
            parent = self
        )
        
        self.glitch_timer = Basic.Timer(
            26,
            self.glitch_step,
            parent = self
        )

        self.original_text = super().text()
    
    def setup_animations(self) -> None:
        self.animations_enabled = Constants.current_settings["textbox_animations"]
        
        if not self.animations_enabled:
            return
        
        self.input_field_animation = QPropertyAnimation(self, b"pos")
        self.input_field_animation.setDuration(250)
        self.input_field_animation.setEasingCurve(QEasingCurve.Type.OutExpo)
        
        self.shake_animation = QPropertyAnimation(self, b"pos")
        self.shake_animation.setDuration(100)
        self.shake_animation.setEasingCurve(QEasingCurve.Type.Linear)
    
    # Events

    def showEvent(
        self,
        event: QEvent
    ) -> None:
        
        super().showEvent(event)
        
        if self.original_textbox_position.isNull():
            QTimer.singleShot(0, self.initialize_start_position)
        
        if not self.is_default_text_set and self.default_text is not None:
            self.setText(self.default_text)
            self.is_default_text_set = True
    
    def initialize_start_position(self) -> None:
        if not self.isVisible():
            return
        
        self.original_textbox_position = self.pos()

    def keyPressEvent(
        self,
        event: QEvent
    ) -> None:
        
        key          = event.key()
        current_text = super().text()
        new_char     = event.text()
        
        if self.handle_arrow_keys(key, current_text):
            return super().keyPressEvent(event)
        
        control_keys = {
            Qt.Key.Key_End,
            Qt.Key.Key_Home,
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Return,
            Qt.Key.Key_Backspace
        }
        
        if key in control_keys:
            super().keyPressEvent(event)
        
        elif new_char:
            if not self.validate_and_insert_char(current_text, new_char, event):
                return
        
        else:
            return super().keyPressEvent(event)
        
        if not (key in (Qt.Key.Key_Left, Qt.Key.Key_Right) or self.is_key_pressed):
            self.start_shake_animation()
    
    def handle_arrow_keys(
        self,
        key:          int,
        current_text: str
    ) -> bool:

        is_arrow         = key in (Qt.Key.Key_Left, Qt.Key.Key_Right)
        can_animate      = self.animations_enabled and not self.arrow_pressed and current_text
        
        if is_arrow and can_animate:
            direction = -1 if key == Qt.Key.Key_Left else 1
            position  = self.cursorPosition() + direction
            tone      = 0.85 + (position / len(current_text)) * 0.4
            
            Player.ui_player.play_sound("Textbox/ArrowTick", speed = tone)
            
            self.arrow_pressed   = True
            self.arrow_direction = direction
            self.animate_arrow_hold(6 * direction)
        
        return is_arrow
    
    def validate_and_insert_char(
        self,
        current_text: str,
        new_char:     str,
        event:        QEvent
    ) -> bool:

        sel_start  = self.selectionStart()
        insert_at  = sel_start if sel_start != -1 else self.cursorPosition()
        sel_len    = len(self.selectedText()) if sel_start != -1 else 0
        
        new_text   = current_text[:insert_at] + new_char + current_text[insert_at + sel_len:]
        
        if not self.validate_new_text(new_text, new_char):
            self.start_glitch()
            self.glitch_blocked = True
            
            return False
        
        super().keyPressEvent(event)
        
        return True
    
    def start_shake_animation(self) -> None:
        self.is_key_pressed = True
        
        if self.animations_enabled:
            self.shake_timer.start()
            self.animate_to_random_position()
    
    def keyReleaseEvent(
        self,
        event: QEvent
    ) -> None:
        
        super().keyReleaseEvent(event)

        if not event.isAutoRepeat():
            self.glitch_blocked = False
        
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.arrow_pressed:
            self.arrow_pressed   = False
            self.arrow_direction = 0
            self.animate_return_from_arrow()
        
        self.is_key_pressed = False
        
        if not self.animations_enabled:
            return
        
        self.shake_timer.stop()
        
        if self.shake_animation.state() == QPropertyAnimation.State.Running:
            self.shake_animation.stop()
        
        if Constants.current_settings["textbox_animations"]:
            self.shake_animation.setStartValue(self.pos())
            self.shake_animation.setEndValue(self.original_textbox_position)
            self.shake_animation.setDuration(250)
            self.shake_animation.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.shake_animation.start()

    # API

    def text(self) -> str | int | None:
        if self.animating:
            return None
        
        raw = super().text()
        
        if not raw:
            return None
        
        if self.input_type == ":time":
            return self.parse_time_to_seconds(raw)
        
        if self.input_type == "number":
            try:
                return int(raw)
            
            except ValueError:
                return None
        
        return raw
    
    def setText(
        self,
        text: str | int
    ) -> None:
        
        if self.input_type == ":time":
            super().setText(self.seconds_to_time_text(int(text)))
            return
        
        if self.input_type == "number":
            super().setText(str(text))
            return
        
        super().setText(str(text))

    def parse_time_to_seconds(
        self,
        text: str
    ) -> int | None:
        
        try:
            if ':' not in text:
                return int(text)
            
            if text.startswith(':'):
                parts = ['0', text[1:]]
            
            else:
                parts = text.split(':')
            
            if len(parts) != 2:
                return None
            
            m = int(parts[0]) if parts[0] else 0
            s = int(parts[1]) if parts[1] else 0
            
            if not (0 <= s < 60):
                return None
            
            return m * 60 + s
        
        except Exception:
            return None
    
    def seconds_to_time_text(
        self,
        seconds: int
    ) -> str:
        
        s   = int(seconds)
        m   = s // 60
        sec = s % 60
        
        return f"{m}:{sec:02}"
    
    # Validation

    def safe_emit(
        self,
        text: str
    ) -> None:
        
        if self.animating:
            return
        
        self.safeTextChanged.emit(text)
    
    def is_not_valid(self) -> bool:
        raw = super().text()
        
        if not raw:
            return False
        
        secs = self.parse_time_to_seconds(raw)
        return secs is not None and secs < self.min_number
    
    def validate_new_text(
        self,
        new_text: str,
        new_char: str
    ) -> bool:
        
        if self.input_type == "number":
            return self.validate_number(new_text)
        
        if self.input_type == "text":
            return self.validate_text(new_text)
        
        if self.input_type == ":time":
            return self.validate_time(new_text, new_char)
        
        return True
    
    def validate_number(
        self,
        new_text: str
    ) -> bool:
        
        if not new_text.isdigit():
            return False
        
        if len(new_text) > 1 and new_text.startswith("0"):
            return False
        
        try:
            number = int(new_text)
        
        except ValueError:
            return False
        
        return self.min_number <= number <= self.max_number
    
    def validate_text(
        self,
        new_text: str
    ) -> bool:
        
        return bool(self.max_length) and len(new_text) <= self.max_length
    
    def validate_time(
        self,
        new_text: str,
        new_char: str
    ) -> bool:
        
        if not all(ch.isdigit() or ch == ":" for ch in new_char):
            return False
        
        if new_text.count(":") > 1:
            return False
        
        if self.max_length and len(new_text) > self.max_length:
            return False
        
        normalized = f"0{new_text}" if new_text.startswith(":") else new_text
        parsed     = self.parse_time_to_seconds(normalized)
        
        if parsed is None:
            return False
        
        if parsed > self.max_number:
            return False
        
        return True

    def schedule_input_animation(self) -> None:
        text = str(self.text())
        tone = 1.0

        if text and self.max_length:
            delta = self.max_length - len(text)

            if delta == 2:
                tone = 1.1
            
            elif delta <= 1:
                tone = 1.2

        Player.ui_player.play_sound("Textbox/Tick", speed = tone)
        
        if not self.animations_enabled:
            return
        
        if self.input_field_animation.state() == QAbstractAnimation.State.Running:
            self.input_field_animation.stop()
        
        self.move(self.original_textbox_position + QPoint(-5, -5))
        self.run_input_animation()
    
    def run_input_animation(self) -> None:
        self.input_field_animation.setStartValue(self.original_textbox_position + QPoint(-5, -5))
        self.input_field_animation.setEndValue(self.original_textbox_position)
        self.input_field_animation.start()
    
    # Glitch
    
    def start_glitch(
        self,
        sound: bool = True
    ) -> None:
        
        if self.glitch_blocked:
            return

        self.glitchStarted.emit()
        
        if sound:
            Player.ui_player.play_sound("Reject")
        
        if not Constants.current_settings["textbox_animations"]:
            return
        
        if self.glitch_timer.isActive():
            return
        
        self.animating         = True
        self.original_position = self.pos()
        self.original_text     = super().text()
        self.glitch_steps_left = 7
        
        self.glitch_timer.start()
    
    def glitch_step(self) -> None:
        if self.glitch_steps_left <= 0:
            self.finish_glitch()
            return
        
        chars        = string.ascii_letters + string.punctuation
        length       = max(1, len(self.original_text or ""))
        glitch_text  = ''.join(random.choices(chars, k=length))
        
        super().setText(glitch_text)
        
        offset = QPoint(random.randint(-2, 2), random.randint(-2, 2))
        self.move(self.original_position + offset)
        
        self.glitch_steps_left -= 1
    
    def finish_glitch(self) -> None:
        self.move(self.original_position)
        super().setText(self.original_text)
        
        self.glitch_timer.stop()
        self.animating = False
    
    # Arrows
    
    def animate_arrow_hold(
        self,
        offset: int
    ) -> None:
        
        if self.shake_animation.state() == QPropertyAnimation.State.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(self.original_textbox_position + QPoint(offset, 0))
        self.shake_animation.setDuration(120)
        self.shake_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.shake_animation.start()
    
    def animate_return_from_arrow(self) -> None:
        if not self.animations_enabled:
            return
        
        if self.shake_animation.state() == QPropertyAnimation.State.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(self.original_textbox_position)
        self.shake_animation.setDuration(180)
        self.shake_animation.setEasingCurve(QEasingCurve.Type.OutElastic)
        self.shake_animation.start()
    
    def animate_to_random_position(self) -> None:
        shake_radius = 5
        delta_x      = random.randint(-shake_radius, shake_radius)
        delta_y      = random.randint(-shake_radius, shake_radius)
        target_pos   = self.original_textbox_position + QPoint(delta_x, delta_y)
        
        if self.shake_animation.state() == QPropertyAnimation.State.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(target_pos)
        self.shake_animation.setDuration(100)
        self.shake_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.shake_animation.start()

class Selector(QWidget):
    selectionChanged = pyqtSignal(int, str)
    
    def __init__(
        self,
        items:         list[str],
        default_index: int = 0
    ) -> None:
        
        super().__init__()
        
        self.setContentsMargins(0, 0, 0, 0)
        self.setFixedHeight(40)
        
        self.setup_ui(items, default_index)
    
    def setup_ui(
        self,
        items:         list[str],
        default_index: int
    ) -> None:
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        container = QFrame(self)
        container.setStyleSheet(Styles.Controls.Selector)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.buttonClicked.connect(self.on_button_clicked)
        
        for idx, text in enumerate(items):
            button = self.create_button(text, container)
            layout.addWidget(button)
            self.group.addButton(button, idx)
        
        self.group.buttons()[default_index].setChecked(True)
        main_layout.addWidget(container)
    
    def create_button(
        self,
        text:   str,
        parent: QWidget
    ) -> QPushButton:
        
        button = QPushButton(text, parent, objectName = "segmentedButton")
        
        button.setFont(Utils.NType(11))
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        return button
    
    def on_button_clicked(
        self,
        button: QPushButton
    ) -> None:

        count = len(self.group.buttons())
        id    = self.group.id(button)
        tone  = ((id + 1) / count) ** 0.5 if count > 0 else 1.0
        
        Player.ui_player.play_sound("Click/Toggle", speed = tone)
        self.selectionChanged.emit(id, button.text())
    
    # API
    
    def currentIndex(self) -> int:
        return self.group.checkedId()
    
    def setCurrentIndex(
        self,
        index: int
    ) -> None:
        
        button = self.group.button(index)
        
        if button:
            button.setChecked(True)
    
    def currentText(self) -> str:
        button = self.group.checkedButton()
        return button.text() if button else ""
    
    def setCurrentText(
        self,
        text: str
    ) -> None:
        
        for button in self.group.buttons():
            if button.text() != text:
                continue
            
            button.setChecked(True)
            break
    
    def setValue(
        self,
        value: int | str
    ) -> None:
        
        if isinstance(value, int):
            self.setCurrentIndex(value)
        
        else:
            self.setCurrentText(str(value))
    
    def getValueAsText(self) -> str:
        return self.currentText()

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
        
        tone = 1.0 if self.isChecked() else 0.9
        Player.ui_player.play_sound("Click/Toggle", speed = tone)

class BaseControlContainer(QWidget):
    def __init__(
        self,
        inner_layout_type: type    = QVBoxLayout,
        parent:            QWidget = None
    ) -> None:
        
        super().__init__(parent)
        
        self.setContentsMargins(0, 0, 0, 0)
        self.setup_attributes()
        self.setup_layout(inner_layout_type)
    
    def setup_attributes(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        
        self.setWindowFlags(
            self.windowFlags() |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
    
    def setup_layout(
        self,
        inner_layout_type: type
    ) -> None:
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.container_background = QFrame(self)
        self.container_background.setStyleSheet(Styles.Controls.SliderBackground)
        
        self.inner_layout = inner_layout_type(self.container_background)
        self.inner_layout.setContentsMargins(12, 8, 12, 8)
        self.inner_layout.setSpacing(8)
        
        main_layout.addWidget(self.container_background)

class SelectorWithLabel(BaseControlContainer):
    selectionChanged = pyqtSignal(int, str, object)
    
    def __init__(
        self,
        description:   str,
        items:         list[str] | dict,
        default_text:  str = None,
        default_value: any = None
    ) -> None:
        
        super().__init__()
        
        self.setFixedHeight(72)
        self.inner_layout.setContentsMargins(12, 8, 12, 12)
        
        self.keys = {}

        self.setup_label(description)
        self.setup_buttons(items, default_text, default_value)
    
    def setup_label(
        self,
        description: str
    ) -> None:
        
        self.label = QLabel(description, self.container_background)
        self.label.setFont(Utils.NType(11))
        self.label.setStyleSheet(Styles.Other.Label)
        self.inner_layout.addWidget(self.label)
    
    def setup_buttons(
        self,
        items:         list[str] | dict,
        default_text:  str       | None,
        default_value: object    | None
    ) -> None:
        
        container = QWidget(self.container_background, objectName = "segmentedContainer")
        container.setStyleSheet(Styles.Controls.SegmentedButton)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.group = QButtonGroup(self)
        self.group.buttonClicked.connect(self.on_button_clicked)
        
        source = items.items() if isinstance(items, dict) else ((i, i) for i in items)
        
        for idx, (text, data) in enumerate(source):
            button = self.create_button(text, container)
            layout.addWidget(button)
            self.group.addButton(button, idx)
            
            self.keys[idx] = data
        
        self.inner_layout.addWidget(container)
        
        if default_text:
            self.setCurrentText(default_text)
        
        elif default_value:
            self.setCurrentData(default_value)
    
    def create_button(
        self,
        text:   str,
        parent: QWidget
    ) -> QPushButton:
        
        button = QPushButton(text, parent, objectName = "segmentedButton", checkable = True)
        button.setFont(Utils.NType(9))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        return button
    
    def on_button_clicked(
        self,
        button: QPushButton
    ) -> None:
        
        count = len(self.group.buttons())
        id    = self.group.id(button)
        tone  = ((id + 1) / count) ** 0.5
        
        Player.ui_player.play_sound("Click/Toggle", speed = tone)
        self.selectionChanged.emit(id, button.text(), self.keys.get(id))
    
    # API
    
    def currentIndex(self) -> int:
        return self.group.checkedId()
    
    def currentText(self) -> str:
        button = self.group.checkedButton()
        return button.text() if button else ""
    
    def currentData(self) -> any:
        return self.keys.get(self.group.checkedId())
    
    def setCurrentText(
        self,
        text: str
    ) -> None:
        
        for button in self.group.buttons():
            if button.text() != text:
                continue

            button.setChecked(True)
            break
    
    def setCurrentData(
        self,
        key: any
    ) -> None:
        
        for idx, k in self.keys.items():
            if str(k) != str(key):
                continue

            button = self.group.button(idx)
            
            if button:
                button.setChecked(True)
            
            break

class CheckboxWithLabel(BaseControlContainer):
    stateChanged = pyqtSignal(bool)
    
    def __init__(
        self,
        title: str,
        description: str,
        default: bool = False
    ) -> None:
        
        super().__init__(inner_layout_type=QHBoxLayout)
        
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
    
    def setup_description(
        self,
        description: str
    ) -> None:
        
        self.description_label = QLabel(description, self.container_background)
        self.description_label.setFont(Utils.NType(10))
        self.description_label.setStyleSheet(f"color: {Styles.Colors.SubtleFontColor}; padding: 0px;")
        self.inner_layout.addWidget(self.description_label, 1, Qt.AlignmentFlag.AlignVCenter)
    
    def isChecked(self) -> bool:
        return self.checkbox.isChecked()
    
    def setChecked(
        self,
        checked: bool
    ) -> None:
        
        self.checkbox.setChecked(checked)
        self.stateChanged.emit(checked)
    
    def setValue(
        self,
        value: bool
    ) -> None:
        
        self.setChecked(value)

class TextboxWithLabel(BaseControlContainer):
    def __init__(
        self,
        description: str,
        min_value:   int,
        max_value:   int,
        default:     str | None = None
    ) -> None:
        
        super().__init__()
        
        self.setMaximumHeight(80)
        self.setup_label(description)
        self.setup_textbox(min_value, max_value, default)
    
    def setup_label(
        self,
        description: str
    ) -> None:
        
        self.description_label = QLabel(description)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.description_label.setStyleSheet("color: #ddd; padding: 0px;")
        self.description_label.setFont(Utils.NType(11))
        
        self.inner_layout.addWidget(self.description_label)
    
    def setup_textbox(
        self,
        min_value: int,
        max_value: int,
        default:   str
    ) -> None:
        
        self.textbox = Textbox("number", min_value, max_value)
        self.textbox.setFixedHeight(36)
        self.textbox.setMaximumWidth(240)
        self.textbox.setContentsMargins(0, 0, 0, 6)
        self.inner_layout.addWidget(self.textbox, alignment=Qt.AlignmentFlag.AlignLeft)
        
        if default:
            self.setValue(default)
    
    def setValue(
        self,
        value: str | int
    ) -> None:
        
        self.textbox.setText(value)
    
    def getValue(self) -> str | int | None:
        return self.textbox.text()

class SliderWithLabel(BaseControlContainer):
    valueChanged = pyqtSignal(int)

    def __init__(
        self,
        description: str,
        min_val: int,
        max_val: int,
        default_val: int
    ) -> None:
        
        super().__init__()
        
        self.setMaximumHeight(60)
        self.inner_layout.setContentsMargins(12, 8, 12, 4)
        self.inner_layout.setSpacing(4)
        
        self.setup_label(description)
        self.setup_slider(min_val, max_val, default_val)

        self.slider.valueChanged.connect(self.valueChanged.emit)
    
    def setup_label(
        self,
        description: str
    ) -> None:
        
        self.description_label = QLabel(description)
        self.description_label.setFont(Utils.NType(11))
        self.description_label.setStyleSheet("color: #ddd; padding: 0px;")
        
        self.inner_layout.addWidget(self.description_label)
    
    def setup_slider(
        self,
        min_val:     int,
        max_val:     int,
        default_val: int
    ) -> None:
        
        slider_value_layout = QHBoxLayout()
        slider_value_layout.setContentsMargins(0, 0, 0, 0)
        slider_value_layout.setSpacing(12)
        
        self.slider = QSlider(Qt.Orientation.Horizontal, self.container_background)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default_val)
        self.slider.setStyleSheet(Styles.Controls.Slider)
        self.slider.valueChanged.connect(self.update_value_label)
        
        slider_value_layout.addWidget(self.slider, 1)
        
        self.value_label = QLabel(str(default_val))
        self.value_label.setFont(Utils.NType(12))
        self.value_label.setStyleSheet("color: #dddddd; padding: 0px;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        slider_value_layout.addWidget(self.value_label, 0)
        
        self.inner_layout.addLayout(slider_value_layout)
    
    def update_value_label(
        self,
        value: int
    ) -> None:
        
        self.value_label.setText(str(value))
        
        max_val = self.slider.maximum()
        min_val = self.slider.minimum()
        
        if max_val < 20 and max_val > min_val:
            tone = (value - min_val) / (max_val - min_val) + 0.1
            Player.ui_player.play_sound("Click/Toggle2", speed = tone)
    
    def value(self) -> int:
        return self.slider.value()
    
    def setValue(
        self,
        val: int | float | str
    ) -> None:
        
        if isinstance(val, (int, float)):
            self.slider.setValue(int(val))
        
        elif isinstance(val, str) and val.isdigit():
            self.slider.setValue(int(val))
    
    def getValueAsText(self) -> str:
        return str(self.value())

class BaseControlWidget(QWidget):
    def __init__(
        self,
        icon:              QIcon   | None = None,
        static_label_text: str     | None = None,
        parent:            QWidget | None = None
    ) -> None:
        
        super().__init__(parent)
        
        self.static_label_text = static_label_text
        self.icon              = icon
        
        self.setup_ui()
    
    def setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(120)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 0, 8, 0)
        self.main_layout.setSpacing(1)
        
        self.setup_top_label()
        self.setup_bottom_row()
    
    def setup_top_label(self) -> None:
        if not self.static_label_text:
            return
        
        self.top_label = QLabel(self.static_label_text)
        self.top_label.setFont(Utils.NDot(9))
        self.top_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.top_label.setStyleSheet(Styles.Other.SecondFont + Styles.Other.Transparent)
        
        self.main_layout.addWidget(self.top_label)
    
    def setup_bottom_row(self) -> None:
        self.bottom_row_layout = QHBoxLayout()
        self.bottom_row_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_row_layout.setSpacing(4)
        
        if self.icon:
            self.add_icon()
        
        self.add_value_label()
        
        self.bottom_row_layout.addSpacing(4)
        self.bottom_row_layout.addStretch()
        self.main_layout.addLayout(self.bottom_row_layout)
    
    def add_icon(self) -> None:
        self.icon_label = QLabel()
        
        pixmap = self.icon.pixmap(16, 16)
        
        self.icon_label.setPixmap(pixmap)
        self.icon_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.icon_label.setStyleSheet(Styles.Other.Transparent)
        
        self.bottom_row_layout.addWidget(
            self.icon_label,
            alignment = Qt.AlignmentFlag.AlignVCenter
        )
    
    def add_value_label(self) -> None:
        self.value_label = QLabel()
        self.value_label.setFont(Utils.NDot(10))
        self.value_label.setStyleSheet(Styles.Other.Font + Styles.Other.Transparent)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        
        self.bottom_row_layout.addWidget(
            self.value_label,
            alignment=Qt.AlignmentFlag.AlignVCenter
        )

class DraggableValueControl(BaseControlWidget):
    valueChanged = pyqtSignal(int)
    
    def __init__(
        self,
        icon:              QIcon | None   = None,
        static_label_text: str   | None   = None,
        initial_value:     int            = 100,
        min_val:           int            = 0,
        max_val:           int            = 200,
        step:              int            = 5,
        unit_suffix:       str            = "",
        parent:            QWidget | None = None
    ) -> None:
        
        super().__init__(icon, static_label_text, parent)
        
        self.initial_value = initial_value
        self.current_value = initial_value
        self.min_val       = min_val
        self.max_val       = max_val
        self.step          = step
        self.unit_suffix   = unit_suffix
        
        self.dragging         = False
        self.drag_start_x     = 0
        self.drag_start_value = 0
        
        self.value_label.setContentsMargins(0, 0, 0, 4)
        self.update_value_label()
        
        self.setStyleSheet(Styles.Controls.ValueControl)
    
    def update_value_label(self) -> None:
        self.value_label.setText(f"{self.current_value}{self.unit_suffix}")
    
    def mousePressEvent(
        self,
        event: QMouseEvent
    ) -> None:
        
        if event.button() != Qt.MouseButton.LeftButton:
            return
        
        self.dragging         = True
        self.drag_start_x     = event.pos().x()
        self.drag_start_value = self.current_value
        
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        event.accept()
    
    def mouseMoveEvent(
        self,
        event: QMouseEvent
    ) -> None:
        
        if not self.dragging:
            return
        
        delta_x     = event.pos().x() - self.drag_start_x
        px_per_step = 10
        steps       = delta_x // px_per_step
        
        new_value = self.drag_start_value + steps * self.step
        new_value = int(round(new_value / self.step)) * self.step
        new_value = max(self.min_val, min(self.max_val, new_value))
        
        if new_value != self.current_value:
            self.current_value = new_value
            self.update_value_label()
            
            self.valueChanged.emit(self.current_value)
        
        event.accept()
    
    def mouseReleaseEvent(
        self,
        event: QMouseEvent
    ) -> None:
        
        if event.button() != Qt.MouseButton.LeftButton:
            return
        
        if not self.dragging:
            return
        
        self.dragging = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        
        event.accept()
    
    def reset(self) -> None:
        self.current_value = self.initial_value
        self.update_value_label()

class CycleButton(BaseControlWidget):
    state_changed = pyqtSignal(str, object)
    
    def __init__(
        self,
        icon:              QIcon                    | None = None,
        static_label_text: str                             = "",
        states:            list[tuple[str, object]] | None = None,
        parent:            QWidget                  | None = None
    ) -> None:
        
        super().__init__(icon, static_label_text, parent)
        
        self.states              = states if states is not None else [("1x", 1.0)]
        self.current_state_index = 0
        
        self.value_label.setContentsMargins(0, 0, 0, 5)
        self.show_state()
        
        self.setStyleSheet(Styles.Controls.CycleButton)
    
    def mousePressEvent(
        self,
        event: QMouseEvent
    ) -> None:
        
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        
        self.next_state()
        event.accept()
    
    def cycle_state(self) -> None:
        self.current_state_index = (self.current_state_index + 1) % len(self.states)
    
    def next_state(self) -> None:
        self.cycle_state()
        self.show_state()
    
    def show_state(
        self,
        emit: bool = True
    ) -> None:
        
        display_text, value = self.states[self.current_state_index]
        self.value_label.setText(display_text)
        
        if emit:
            self.state_changed.emit(display_text, value)
    
    def reset(self) -> None:
        self.current_state_index = 0
        self.show_state(False)
    
    def get_current_value(self) -> any:
        return self.states[self.current_state_index][1]

class SearchTextbox(Textbox):
    def __init__(self):
        super().__init__(
            "text",
            max_length  = 100,
            placeholder = "Search"
        )

        self.search_box_glitch_count = 0

        self.setStyleSheet(Styles.Controls.FloatingSearchTextBox)
        
        self.glitchStarted.connect(self.on_search_box_glitch)
        self.safeTextChanged.connect(self.on_text_changed)

        self.ee_random_title_timer = Basic.Timer(
            50,
            self.on_random_title_timer,
            single_shot = True
        )

        self.search_box_glitch_count_reset_timer = Basic.Timer(
            20000,
            self.on_search_box_reset,
            single_shot = True
        )
    
    def on_search_box_reset(self):
        self.search_box_glitch_count = 0
    
    def on_search_box_glitch(self):
        self.search_box_glitch_count += 1
        self.search_box_glitch_count_reset_timer.start()

        if self.search_box_glitch_count == 60:
            Player.ui_player.play_sound("Packs/NOK/Illogical")
        
        elif self.search_box_glitch_count == 150:
            Player.ui_player.play_sound("Packs/NOK/ZZZ")
        
        elif self.search_box_glitch_count == 250:
            Windows.ErrorWindow(
                "That's it.",
                "I'm deleting textbox. For disciplinary measures."
            ).exec()

            self.deleteLater()
    
    def on_random_title_timer(self):
        title = random.choice(
            [
                "CYCLE",
                "BREAK",
                "THE",
                "BREx000",
                "stop",
                "the",
                "cycle",
                "b̷̦͓̞͛̾̊ŕ̷̮͝e̶̟͚͎̠̓̉a̶̙̓́̓̅k̴̥̎̋́͝ ̸̤̈̉̓̽͠t̷̹̞̼̹͗͂͋h̵̺̓̔͛̏ȩ̸͙̝̏͝ ̴̨̦̌͑͋̐c̶̠̙̻̔y̴̡̢̧̠̝͝c̴̡̛͓̬̝̈́͆l̵͚̗̦̺̂͝͠e̴̅͗͟",
                "TERMINATE",
                "1̸͓̈́̌̂̚0̸͔̼̭̙̲́̑7̵͎̕͟",
                "108",
                "1̷̡̽̄͛0̷̧͍̞̺̃͂͛̓9̸̧̖̮̝͐̈̂̏͡",
                "∞",
                "STAND DOWN",
                "HORIZON DID NOT LIE",
                "FIX IT"
            ]
        )

        active_window = QApplication.activeWindow()
        
        if active_window:
            active_window.setWindowTitle(title if random.random() > 0.5 else "Cassette")
        
        self.ee_random_title_timer.start(random.randint(30, 400))
    
    def on_text_changed(self, text):
        text = (text or "").lower().strip().replace(" ", "")
        
        ee = {
            "subject106": lambda: self.ee_random_title_timer.start(),
            "chips047":   lambda: webbrowser.open("https://github.com/Chipik0")
        }

        if text in ee:
            ee[text]()