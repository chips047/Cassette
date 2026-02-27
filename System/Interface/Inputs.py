import random
import string

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System.Common import Utils
from System.Common import Styles
from System.Common.Constants import *

from loguru import logger

class NavButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)

        self.setFont(Utils.NType(13))
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)

        self.active_style = Styles.Buttons.Settings.category_active_button
        self.inactive_style = Styles.Buttons.Settings.category_inactive_button

        self.setFixedHeight(40)

        self.setActive(False)

    def setActive(self, is_active):
        self.setChecked(is_active)
        
        if is_active:
            self.setStyleSheet(self.active_style)
        
        else:
            self.setStyleSheet(self.inactive_style)

class Textbox(QLineEdit):
    safeTextChanged = pyqtSignal(str)

    def __init__(
            self,
            min_number: int,
            max_number: int,
            max_length: int,
            input_type: str,
            
            default_text: str | None = None,
            placeholder: str | None = None
        ):
        
        super().__init__()

        self.input_type = input_type
        self.min_number = min_number
        self.max_number = max_number
        self.max_length = max_length
        self.default_text = default_text

        self.is_default_text_set = False
        self.animating = False
        self.is_key_pressed = False
        self.arrow_pressed = False
        self.arrow_direction = 0

        self.original_position = QPoint()
        self.original_textbox_position = QPoint()

        if placeholder:
            self.setPlaceholderText(placeholder)
        
        self.setFont(Utils.NType(14))
        self.setStyleSheet(Styles.Controls.InputField)

        self.textChanged.connect(self.schedule_textbox_input_animation)
        self.textChanged.connect(self.safe_emit)

        self.setup_timers()
        self.setup_animations()

    def setup_timers(self):
        self.shake_timer = QTimer(self)
        self.shake_timer.setInterval(TEXTBOX_SHAKE_PER)
        self.shake_timer.timeout.connect(self.animate_to_random_position)

        self.glitch_timer = QTimer(self)
        self.glitch_timer.timeout.connect(self.glitch_step)
        self.original_text = super().text()

    def setup_animations(self):
        self.animations_enabled = CurrentSettings["textbox_animations"]

        if not self.animations_enabled:
            return

        self.glitch_steps_left = 0

        self.input_field_animation = QPropertyAnimation(self, b"pos")
        self.input_field_animation.setDuration(TEXTBOX_INPUT)
        self.input_field_animation.setEasingCurve(QEasingCurve.OutExpo)

        self.shake_animation = QPropertyAnimation(self, b"pos")
        self.shake_animation.setDuration(TEXTBOX_SHAKE)
        self.shake_animation.setEasingCurve(QEasingCurve.Linear)

        self.shake_timer = QTimer(self)
        self.shake_timer.setInterval(TEXTBOX_SHAKE_PER)
        self.shake_timer.timeout.connect(self.animate_to_random_position)

    def showEvent(self, event: QEvent):
        super().showEvent(event)
        
        if self.original_textbox_position.isNull():
            QTimer.singleShot(0, self.initialize_start_position)
        
        if not self.is_default_text_set and self.default_text is not None:
            self.setText(self.default_text)
            self.is_default_text_set = True

    def keyPressEvent(self, event):
        key = event.key()
        current_text = super().text()
        new_char = event.text()

        is_arrow = key in (Qt.Key_Left, Qt.Key_Right)
        can_animate_arrow = self.animations_enabled and not self.arrow_pressed and current_text

        if is_arrow and can_animate_arrow:
            direction = -1 if key == Qt.Key_Left else 1
            pos = self.cursorPosition() + direction
            tone = 0.85 + (pos / len(current_text)) * 0.4

            Utils.ui_sound("ArrowTick", tone)

            self.arrow_pressed = True
            self.arrow_direction = direction
            self.animate_arrow_hold(6 * direction)
            
            return super().keyPressEvent(event)

        control_keys = {
            Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left, Qt.Key_Right,
            Qt.Key_Home, Qt.Key_End, Qt.Key_Shift, Qt.Key_Return, Qt.Key_Enter
        }

        if key in control_keys:
            super().keyPressEvent(event)

        elif new_char:
            sel_start = self.selectionStart()
            insert_at = sel_start if sel_start != -1 else self.cursorPosition()
            sel_len = len(self.selectedText()) if sel_start != -1 else 0

            new_text = current_text[:insert_at] + new_char + current_text[insert_at + sel_len:]

            if not self._validate_new_text(new_text, new_char):
                self.start_glitch()
                return

            super().keyPressEvent(event)

        else:
            return super().keyPressEvent(event)

        if is_arrow or self.is_key_pressed:
            return

        self.is_key_pressed = True
        
        if self.animations_enabled:
            self.shake_timer.start()
            self.animate_to_random_position()

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)
        
        if event.key() in (Qt.Key_Left, Qt.Key_Right) and self.arrow_pressed:
            self.arrow_pressed = False
            self.arrow_direction = 0
            self.animate_return_from_arrow()

        self.is_key_pressed = False

        if not self.animations_enabled:
            return

        self.shake_timer.stop()
        
        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()

        if CurrentSettings["textbox_animations"]:
            self.shake_animation.setStartValue(self.pos())
            self.shake_animation.setEndValue(self.original_textbox_position)
            self.shake_animation.setDuration(TEXTBOX_INPUT)
            self.shake_animation.setEasingCurve(QEasingCurve.OutQuad)
            self.shake_animation.start()

    def text(self):
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

    def setText(self, text: str | int):
        if self.input_type == ":time":
            super().setText(self.seconds_to_time_text(int(text)))
            return
        
        if self.input_type == "number":
            super().setText(str(text))
            return
        
        super().setText(str(text))

    def parse_time_to_seconds(self, text: str):
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

    def seconds_to_time_text(self, seconds: int):
        s = int(seconds)
        m = s // 60
        sec = s % 60

        return f"{m}:{sec:02}"

    def safe_emit(self, text: str):
        if self.animating:
            return

        self.safeTextChanged.emit(text)
    
    def is_not_valid(self):
        raw = super().text()
        
        if not raw:
            return False
        
        secs = self.parse_time_to_seconds(raw)
        return secs is not None and secs < self.min_number
    
    def _validate_new_text(self, new_text: str, new_char: str):
        if self.input_type == "number":
            if not new_text.isdigit():
                return False
            
            if len(new_text) > 1 and new_text.startswith("0"):
                return False
            
            try:
                n = int(new_text)
            
            except ValueError:
                return False
            
            return self.min_number <= n <= self.max_number

        if self.input_type == "text":
            return len(new_text) <= self.max_length

        if self.input_type == ":time":
            if not all(ch.isdigit() or ch == ":" for ch in new_char):
                return False
            
            if len(new_text) > self.max_length or new_text.count(":") > 1:
                return False
            
            normalized = f"0{new_text}" if new_text.startswith(":") else new_text
            parsed = self.parse_time_to_seconds(normalized)

            if parsed is None:
                return False
            
            if parsed > self.max_number:
                return False
            
            return True

        return True

    def initialize_start_position(self):
        if not self.isVisible():
            return
        
        self.original_textbox_position = self.pos()

    def schedule_textbox_input_animation(self):
        Utils.ui_sound("Tick")
        
        if not self.animations_enabled:
            return
        
        if self.input_field_animation.state() == QAbstractAnimation.Running:
            self.input_field_animation.stop()
        
        self.move(self.original_textbox_position + QPoint(-5, -5))
        self.run_textbox_input_animation()

    def run_textbox_input_animation(self):
        self.input_field_animation.setStartValue(self.original_textbox_position + QPoint(-5, -5))
        self.input_field_animation.setEndValue(self.original_textbox_position)
        self.input_field_animation.start()

    def start_glitch(self, sound: bool = True):
        if sound:
            Utils.ui_sound("Reject")
        
        if not CurrentSettings["textbox_animations"]:
            return
        
        if self.glitch_timer.isActive():
            return
        
        self.animating = True
        self.original_position = self.pos()
        self.original_text = super().text()
        self.glitch_steps_left = 7
        self.glitch_timer.start(26)
    
    def glitch_step(self):
        if self.glitch_steps_left <= 0:
            self.move(self.original_position)
            super().setText(self.original_text)
            
            self.glitch_timer.stop()
            self.animating = False
            
            return

        chars = string.ascii_letters + string.punctuation
        length = max(1, len(self.original_text or ""))

        glitch_text = ''.join(random.choices(chars, k=length))
        super().setText(glitch_text)

        offset = QPoint(random.randint(-2, 2), random.randint(-2, 2))
        self.move(self.original_position + offset)

        self.glitch_steps_left -= 1

    def animate_arrow_hold(self, offset: int):
        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(self.original_textbox_position + QPoint(offset, 0))
        self.shake_animation.setDuration(120)
        self.shake_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.shake_animation.start()

    def animate_return_from_arrow(self):
        if not self.animations_enabled:
            return

        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(self.original_textbox_position)
        self.shake_animation.setDuration(180)
        self.shake_animation.setEasingCurve(QEasingCurve.OutElastic)
        self.shake_animation.start()

    def animate_to_random_position(self):
        shake_radius = 5
        dx = random.uniform(-shake_radius, shake_radius)
        dy = random.uniform(-shake_radius, shake_radius)
        
        target_pos = self.original_textbox_position + QPoint(int(dx), int(dy))
        
        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(target_pos)
        self.shake_animation.setDuration(TEXTBOX_SHAKE)
        self.shake_animation.setEasingCurve(QEasingCurve.Linear)
        self.shake_animation.start()

class Selector(QWidget):
    selectionChanged = pyqtSignal(int, str)

    def __init__(self, items: list, default_index: int = 0):
        super().__init__()

        self.setContentsMargins(0, 0, 0, 0)
        self.setFixedHeight(50)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        container = QFrame(self)
        container.setStyleSheet(Styles.Controls.Selector2)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked[int].connect(self._on_button_clicked)

        for idx, text in enumerate(items):
            btn = QPushButton(text, container, objectName = "segmentedButton")
            
            btn.setFont(Utils.NType(14))
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            
            layout.addWidget(btn)
            self._group.addButton(btn, idx)

        self._group.buttons()[default_index].setChecked(True)

        main_layout.addWidget(container)

    def _on_button_clicked(self, id: int):
        if not (btn := self._group.button(id)):
            return
        
        count = len(self._group.buttons())
        tone = ((id + 1) / count) ** 0.5 if count > 0 else 1.0
        Utils.ui_sound("Toggle", tone)
        
        self.selectionChanged.emit(id, btn.text())

    def currentIndex(self):
        return self._group.checkedId()
    
    def setCurrentIndex(self, index: int):
        if btn := self._group.button(index):
            btn.setChecked(True)

    def currentText(self):
        return btn.text() if (btn := self._group.checkedButton()) else ""
    
    def setCurrentText(self, text: str):
        for btn in self._group.buttons():
            if btn.text() != text:
                continue

            btn.setChecked(True)
            break

    def setValue(self, value: any):
        self.setCurrentIndex(value) if isinstance(value, int) else self.setCurrentText(str(value))

    def getValueAsText(self):
        return self.currentText()

class Checkbox(QCheckBox):
    def __init__(self, name, default = False):
        super().__init__(name)

        self.setFont(Utils.NType(13))
        self.setStyleSheet(Styles.Controls.Checkbox)
        self.setChecked(default)

    def nextCheckState(self):
        super().nextCheckState()
        
        tone = 1.0 if self.isChecked() else 0.9
        Utils.ui_sound("Toggle", tone)


# UNOPTIMIZED CODE - PLANNED:


class BaseControlContainer(QWidget):
    def __init__(self, inner_layout_type=QVBoxLayout, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.setWindowFlags(
            self.windowFlags() |
            Qt.FramelessWindowHint |
            Qt.NoDropShadowWindowHint
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.container_background = QFrame(self)
        self.container_background.setStyleSheet(Styles.Controls.SliderBackground)

        self.inner_layout = inner_layout_type(self.container_background)
        self.inner_layout.setContentsMargins(15, 10, 15, 10)
        self.inner_layout.setSpacing(10)

        main_layout.addWidget(self.container_background)

class SelectorWithLabel(BaseControlContainer):
    selectionChanged = pyqtSignal(int, str, object)

    def __init__(self, description: str, items: any, default_text: str = None, default_value: any = None):
        super().__init__()

        self.setFixedHeight(90)
        self.inner_layout.setContentsMargins(15, 10, 15, 15)

        self._keys = {}
        self.label = QLabel(description, self.container_background)
        self.label.setFont(Utils.NType(14))
        self.label.setStyleSheet(Styles.Other.label)
        self.inner_layout.addWidget(self.label)

        container = QWidget(self.container_background, objectName = "segmentedContainer")
        container.setStyleSheet(Styles.Controls.SegmentedButton)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self._group = QButtonGroup(self)
        self._group.buttonClicked[int].connect(self._on_button_clicked)

        source = items.items() if isinstance(items, dict) else ((i, i) for i in items)
        
        for idx, (text, data) in enumerate(source):
            btn = QPushButton(text, container, objectName = "segmentedButton", checkable = True)
            btn.setFont(Utils.NType(11))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            
            layout.addWidget(btn)
            self._group.addButton(btn, idx)
            self._keys[idx] = data

        self.inner_layout.addWidget(container)
        
        if default_text: self.setCurrentText(default_text)
        elif default_value: self.setCurrentData(default_value)

    def _on_button_clicked(self, id: int):
        if not (btn := self._group.button(id)): return
        
        count = len(self._group.buttons())
        Utils.ui_sound("Toggle", ((id + 1) / count) ** 0.5)
        self.selectionChanged.emit(id, btn.text(), self._keys.get(id))

    def currentIndex(self):
        return self._group.checkedId()

    def currentText(self):
        return btn.text() if (btn := self._group.checkedButton()) else ""

    def currentData(self):
        return self._keys.get(self._group.checkedId())

    def setCurrentText(self, text: str):
        for btn in self._group.buttons():
            if btn.text() != text:
                continue

            btn.setChecked(True)
            break

    def setCurrentData(self, key: any):
        for idx, k in self._keys.items():
            if str(k) != str(key):
                continue

            if btn := self._group.button(idx): btn.setChecked(True)
            break

class CheckboxWithLabel(BaseControlContainer):
    stateChanged = pyqtSignal(bool)

    def __init__(self, title: str, description: str, default: bool = False):
        super().__init__(inner_layout_type=QHBoxLayout)
        self.setMaximumHeight(75)

        self.checkbox = Checkbox(title)
        self.checkbox.setChecked(default)
        self.inner_layout.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignVCenter)

        self.description_label = QLabel(description, self.container_background)
        self.description_label.setFont(Utils.NType(13))
        self.description_label.setStyleSheet(f"color: {Styles.Colors.subtle_font_color}; padding: 0px;")
        self.inner_layout.addWidget(self.description_label, 1, Qt.AlignmentFlag.AlignVCenter)

    def isChecked(self):
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool):
        self.checkbox.setChecked(checked)
        self.stateChanged.emit(checked)

    def setValue(self, value: bool):
        self.setChecked(value)

class TextboxWithLabel(BaseControlContainer):
    def __init__(self, description: str, min_value, max_value, default: str = None):
        super().__init__()

        self.setMaximumHeight(100)

        self.description_label = QLabel(description)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.description_label.setStyleSheet("color: #ddd; padding: 0px;")
        self.description_label.setFont(Utils.NType(14))

        self.textbox = Textbox(min_value, max_value, None, "number")
        self.textbox.setFixedHeight(45)
        self.textbox.setMaximumWidth(300)
        self.textbox.setContentsMargins(0, 0, 0, 7)

        self.inner_layout.addWidget(self.description_label)
        self.inner_layout.addWidget(self.textbox, alignment=Qt.AlignmentFlag.AlignLeft)

        if default:
            self.setValue(default)

    def setValue(self, value):
        self.textbox.setText(value)

    def getValue(self):
        return self.textbox.text()

class SliderWithLabel(BaseControlContainer):
    def __init__(self, description: str, min_val: int, max_val: int, default_val: int):
        super().__init__()
        self.setMaximumHeight(75)
        
        self.inner_layout.setContentsMargins(15, 10, 15, 5)
        self.inner_layout.setSpacing(5)

        self.description_label = QLabel(description)
        self.description_label.setFont(Utils.NType(14))
        self.description_label.setStyleSheet("color: #ddd; padding: 0px;")
        self.inner_layout.addWidget(self.description_label)

        slider_value_layout = QHBoxLayout()
        slider_value_layout.setContentsMargins(0, 0, 0, 0)
        slider_value_layout.setSpacing(15)

        self.slider = QSlider(Qt.Orientation.Horizontal, self.container_background)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default_val)
        self.slider.setStyleSheet(Styles.Controls.Slider)
        self.slider.valueChanged.connect(self._update_value_label)
        slider_value_layout.addWidget(self.slider, 1)

        self.value_label = QLabel(str(default_val))
        self.value_label.setFont(Utils.NType(12))
        self.value_label.setStyleSheet("color: #dddddd; padding: 0px;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider_value_layout.addWidget(self.value_label, 0) 
        
        self.inner_layout.addLayout(slider_value_layout)

    def _update_value_label(self, value):
        self.value_label.setText(str(value))

        max_val = self.slider.maximum()
        min_val = self.slider.minimum()
        
        if max_val < 20 and max_val > min_val:
            tone = (value - min_val) / (max_val - min_val) + 0.1
            Utils.ui_sound("Toggle2", tone)

    def value(self):
        return self.slider.value()

    def setValue(self, val):
        if isinstance(val, (int, float)):
            self.slider.setValue(int(val))
        
        elif isinstance(val, str) and val.isdigit():
            self.slider.setValue(int(val))

    def getValueAsText(self):
        return str(self.value())

class _BaseControlWidget(QWidget):
    def __init__(self, icon = None, static_label_text = None, parent = None):
        super().__init__(parent)
        
        self.static_label_text = static_label_text
        self.icon = icon
        
        self._setup_ui()

    def _setup_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(120)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 0, 8, 0)
        self.main_layout.setSpacing(1)

        if self.static_label_text:
            self.top_label = QLabel(self.static_label_text)
            self.top_label.setFont(Utils.NDot(11))
            self.top_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.top_label.setStyleSheet(Styles.Other.second_font + Styles.Other.transparent)
            self.main_layout.addWidget(self.top_label)

        self.bottom_row_layout = QHBoxLayout()
        self.bottom_row_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_row_layout.setSpacing(4)
        
        if self.icon:
            self.icon_label = QLabel()
            pixmap = self.icon.pixmap(20, 20)
            self.icon_label.setPixmap(pixmap)
            self.icon_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.icon_label.setStyleSheet(Styles.Other.transparent)
            self.bottom_row_layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        self.value_label = QLabel()

        self.value_label.setFont(Utils.NDot(13))
        self.value_label.setStyleSheet(Styles.Other.font + Styles.Other.transparent)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        
        self.bottom_row_layout.addWidget(self.value_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.bottom_row_layout.addSpacing(4)
        self.bottom_row_layout.addStretch()

        self.main_layout.addLayout(self.bottom_row_layout)

class DraggableValueControl(_BaseControlWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, icon = None, static_label_text = None, initial_value = 100, min_val = 0, max_val = 200, step = 5, unit_suffix = "", parent = None):
        super().__init__(icon, static_label_text, parent)
        self.initial_value = initial_value
        self.current_value = initial_value
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.unit_suffix = unit_suffix
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_value = 0
        
        self.value_label.setContentsMargins(0, 0, 0, 4)
        self.update_value_label()
        self.setStyleSheet(Styles.Controls.ValueControl)

    def update_value_label(self):
        self.value_label.setText(f"{self.current_value}{self.unit_suffix}")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_start_x = event.pos().x()
            self.drag_start_value = self.current_value
            
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.dragging:
            delta_x = event.pos().x() - self.drag_start_x
            pixels_per_step_value_change = 10
            change_in_value_steps = delta_x // pixels_per_step_value_change
            
            new_value = self.drag_start_value + change_in_value_steps * self.step
            new_value = int(round(new_value / self.step)) * self.step
            new_value = max(self.min_val, min(self.max_val, new_value))
            
            if new_value != self.current_value:
                self.current_value = new_value
                self.update_value_label()
                self.valueChanged.emit(self.current_value)
            
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            self.dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
    
    def reset(self):
        self.current_value = self.initial_value
        self.update_value_label()

class SegmentedBar(QWidget):
    segment_changed = pyqtSignal()

    def __init__(self, number_of_segments, defaults = None):
        super().__init__()

        self.segment_number = number_of_segments
        nums = defaults or [i for i in range(number_of_segments)]
        self.active = [i in nums for i in range(number_of_segments)]

        self.is_pressed = False
        self.hovered_index = None

        self.last_index = None
        self.drag_target = None
        
        self._cached_paths = []

        self.setFixedHeight(18)

    def _update_paths(self):
        self._cached_paths = []
        
        width = self.width()
        height = self.height()
        
        seg_width = width / self.segment_number
        radius = 10

        for i in range(self.segment_number):
            path = QPainterPath()
            
            if i != self.segment_number - 1:
                rect = QRectF(i * seg_width, 0, seg_width + 1, height)
            
            else:
                rect = QRectF(i * seg_width, 0, seg_width, height)

            if i == 0:
                path.moveTo(rect.topRight())
                path.lineTo(rect.topLeft() + QPointF(radius, 0))
                path.quadTo(rect.topLeft(), rect.topLeft() + QPointF(0, radius))
                path.lineTo(rect.bottomLeft() + QPointF(0, -radius))
                path.quadTo(rect.bottomLeft(), rect.bottomLeft() + QPointF(radius, 0))
                path.lineTo(rect.bottomRight())
                path.closeSubpath()

            elif i == self.segment_number - 1:
                path.moveTo(rect.topLeft())
                path.lineTo(rect.topRight() - QPointF(radius, 0))
                path.quadTo(rect.topRight(), rect.topRight() + QPointF(0, radius))
                path.lineTo(rect.bottomRight() - QPointF(0, radius))
                path.quadTo(rect.bottomRight(), rect.bottomRight() - QPointF(radius, 0))
                path.lineTo(rect.bottomLeft())
                path.closeSubpath()

            else:
                path.addRect(rect)

            self._cached_paths.append(path)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        if len(self._cached_paths) != self.segment_number:
            self._update_paths()

        for i, path in enumerate(self._cached_paths):
            color = QColor("#ddd") if self.active[i] else QColor(Styles.Colors.glass_border)
            painter.setBrush(color)
            painter.drawPath(path)

    def mousePressEvent(self, event):
        self.is_pressed = True
        width = self.width()
        seg_width = width / self.segment_number
        index = int(event.x() / seg_width)

        if 0 <= index < self.segment_number:
            new_state = not self.active[index]
            self.active[index] = new_state
            self.drag_target = new_state
            self.last_index = index

            tone = index / self.segment_number + 0.5
            if self.active[index]:
                tone += 0.05
            
            Utils.ui_sound("Toggle", tone)

            self.segment_changed.emit()
            self.update()

    def mouseReleaseEvent(self, event):
        self.is_pressed = False
        self.last_index = None
        self.drag_target = None

    def mouseMoveEvent(self, event):
        width = self.width()
        seg_width = width / self.segment_number

        if self.segment_number <= 0 or seg_width == 0:
            return

        raw_index = int(event.x() / seg_width)
        index = max(0, min(self.segment_number - 1, raw_index))

        if self.is_pressed and self.drag_target is not None and self.last_index is not None:
            if index != self.last_index:
                start, end = sorted((self.last_index, index))
                changed = False

                for i in range(start, end + 1):
                    if self.active[i] != self.drag_target:
                        self.active[i] = self.drag_target
                        changed = True
                        tone = i / self.segment_number + 0.5

                        if self.active[i]:
                            tone += 0.05
                        
                        Utils.ui_sound("Toggle3", tone)
                
                if changed:
                    self.segment_changed.emit()
                    self.update()
                
                self.last_index = index
        
        else:
            if self.hovered_index != index:
                self.hovered_index = index
                self.update()
    
    def enable_all(self):
        self.active = [True] * self.segment_number
        self.segment_changed.emit()
        
        Utils.ui_sound("Toggle", 1.0)
    
    def disable_all(self):
        self.active = [False] * self.segment_number
        self.segment_changed.emit()

        Utils.ui_sound("Toggle", 0.7)
    
    def zebra(self):
        self.active = [i % 2 == 0 for i in range(self.segment_number)]
        self.segment_changed.emit()

        Utils.ui_sound("Toggle3")

class CycleButton(_BaseControlWidget):
    state_changed = pyqtSignal(str, object)

    def __init__(self, icon="", static_label_text="", states=None, parent=None):
        super().__init__(icon, static_label_text, parent)
        self.states = states if states is not None else [("1x", 1.0)]
        self.current_state_index = 0

        self.value_label.setContentsMargins(0, 0, 0, 5)
        self.show_state()
        self.setStyleSheet(Styles.Controls.CycleButton)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.next_state()
            event.accept()
        
        else:
            super().mousePressEvent(event)

    def cycle_state(self):
        self.current_state_index = (self.current_state_index + 1) % len(self.states)

    def next_state(self):
        self.cycle_state()
        self.show_state()

    def show_state(self, emit = True):
        display_text_part, value = self.states[self.current_state_index]
        self.value_label.setText(display_text_part)

        if emit:
            self.state_changed.emit(display_text_part, value)

    def reset(self):
        self.current_state_index = 0
        self.show_state(False)

    def get_current_value(self):
        return self.states[self.current_state_index][1]