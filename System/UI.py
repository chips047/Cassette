import re
import copy
import time
import math
import random
import string
import traceback
import webbrowser

import numpy as np

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from . import Utils
from . import Styles
from . import Player
from . import GlyphEffects

from .Constants import *

MAX_SIZE = 16777215

def normalize_size(width, height, max_ref = 1500):
    return min(max(width, height) / max_ref, 1.0)

def get_scale(width, height, base_scale=1.4, min_scale=1.1, max_ref=1000):
    norm = normalize_size(width, height, max_ref)
    return min_scale + (base_scale - min_scale) * (1 - norm)

def get_rotation(width, height, base_angle=50, min_angle=10, max_ref=1600):
    norm = normalize_size(width, height, max_ref)
    max_angle = int(min_angle + (base_angle - min_angle) * (1 - norm))

    return random.choice(
        [
            random.randint(-max_angle, -int(max_angle / 2)),
            random.randint(int(max_angle / 2), max_angle)
        ]
    )

def get_optimal_tilt(width, height):
    coeff_w = 1100 / width
    coeff_h = 1100 / height

    tilt = int((coeff_h + coeff_w) * 8)
    return tilt

class GlitchyButton(QPushButton):
    glitch_started = pyqtSignal()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.glitch_timer = QTimer(self)
        self.glitch_timer.timeout.connect(self._glitch_step)
        self.glitch_steps_left = 0

        self.original_pos = None
        self.original_size = None
        
        self.original_button_text = super().text()
        
        self.setFont(Utils.NType(13))
        

        self.installEventFilter(self)
    
    def random_ass_text(self, length):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))

    def eventFilter(self, obj, event):
        if obj == self and event.type() == QEvent.MouseButtonPress:
            if not self.isEnabled():
                self.start_glitch()
                return True
        
        return super().eventFilter(obj, event)

    def start_glitch(self):
        Utils.ui_sound("Reject")
        self.glitch_started.emit()

        if self.glitch_timer.isActive():
            return

        self.original_pos = self.pos()
        self.original_size = self.size()
        self.setFixedSize(self.original_size)
        self.glitch_steps_left = 7
        self.glitch_timer.start(24)

    def _glitch_step(self):
        if self.glitch_steps_left <= 0:
            self.move(self.original_pos)
            self.resize(self.original_size)
            self.glitch_timer.stop()
            
            self.setText(self.original_button_text)
            return

        font_metrics = QFontMetrics(self.font())
        
        current_button_width = self.width() 
        average_char_width = font_metrics.averageCharWidth()

        estimated_length = current_button_width // average_char_width

        estimated_length = max(1, estimated_length) 
        estimated_length = min(200, estimated_length)

        self.setText(self.random_ass_text(estimated_length))
        dx = random.randint(-3, 3)
        dy = random.randint(-4, 4)
        dw = random.randint(-4, 4)
        dh = random.randint(-2, 2)

        new_pos = self.original_pos + QPoint(dx, dy)
        new_size = QSize(
            max(10, self.original_size.width() + dw),
            max(10, self.original_size.height() + dh)
        )

        self.move(new_pos)
        self.resize(new_size)

        self.glitch_steps_left -= 1

class NothingButton(GlitchyButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(Styles.Buttons.nothing_styled_button)

class Button(GlitchyButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(Styles.Buttons.normal_button)

class ButtonWithOutline(GlitchyButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(Styles.Buttons.normal_button_with_border)

class ButtonWithOutlineSlim(GlitchyButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(Styles.Buttons.normal_button_with_border_slim)

class Selector(QWidget):
    selection_changed = pyqtSignal(int, str)

    def __init__(
        self,
        items,
        *,
        default_index = 0,
        parent = None,
    ):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setFixedHeight(48)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        selector_container = QFrame(self)
        selector_container.setStyleSheet(Styles.Controls.Selector2)
        selector_layout = QHBoxLayout(selector_container)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(5)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked[int].connect(self._on_button_clicked)

        for idx, text in enumerate(items):
            btn = QPushButton(text, objectName = "segmentedButton", parent=selector_container)
            btn.setFont(Utils.NType(14))
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.setCursor(Qt.PointingHandCursor)
            selector_layout.addWidget(btn)
            self._group.addButton(btn, id = idx)

        buttons = self._group.buttons()
        if 0 <= default_index < len(buttons):
            buttons[default_index].setChecked(True)
        
        elif buttons:
            buttons[0].setChecked(True)

        main_layout.addWidget(selector_container)

    def _on_button_clicked(self, id: int):
        button = self._group.button(id)
        if not button:
            return
            
        text = button.text()
        button_number = len(self._group.buttons())
        
        if button_number > 0:
            tone = ((id + 1) / button_number) ** 0.5
            Utils.ui_sound("Toggle", tone)
            
        self.selection_changed.emit(id, text)

    def currentIndex(self) -> int:
        return self._group.checkedId()
    
    def setCurrentIndex(self, index: int):
        button = self._group.button(index)
        
        if button:
            button.setChecked(True)

    def currentText(self) -> str:
        btn = self._group.checkedButton()
        return btn.text() if btn else ""
        
    def setCurrentText(self, text: str):
        for button in self._group.buttons():
            if button.text() == text:
                button.setChecked(True)
                break

    def setValue(self, value):
        if isinstance(value, int):
            self.setCurrentIndex(value)
        
        elif isinstance(value, str):
            self.setCurrentText(value)

    def getValueAsText(self) -> str:
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

class BaseControlContainer(QWidget):
    def __init__(self, inner_layout_type=QVBoxLayout, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)

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
    selection_changed = pyqtSignal(int, str, object)

    def __init__(self, description: str, items, default_text: str = None, default_value: str = None):
        super().__init__()
        self.setFixedHeight(90)
        self.inner_layout.setContentsMargins(15, 10, 15, 15)

        self._keys = {}

        self.description_label = QLabel(description, self.container_background)
        self.description_label.setFont(Utils.NType(14))
        self.description_label.setStyleSheet(Styles.Other.label)
        self.inner_layout.addWidget(self.description_label)

        selector_container = QWidget(self.container_background)
        selector_container.setStyleSheet(Styles.Controls.SegmentedButton)
        
        selector_layout = QHBoxLayout(selector_container)
        selector_layout.setContentsMargins(0, 0, 0, 0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked[int].connect(self._on_button_clicked)

        if isinstance(items, dict):
            item_source = list(items.items())
        
        else:
            item_source = [(text, text) for text in items]

        for idx, (btn_text, data) in enumerate(item_source):
            btn = QPushButton(btn_text, parent=selector_container, objectName="segmentedButton")
            btn.setFont(Utils.NType(11))
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.setCursor(Qt.PointingHandCursor)
            
            selector_layout.addWidget(btn)
            self._group.addButton(btn, id=idx)
            self._keys[idx] = data
        
        if default_text:
            self.setCurrentText(default_text)
        
        elif default_value:
            self.setCurrentData(default_value)

        self.inner_layout.addWidget(selector_container)

    def _on_button_clicked(self, id: int):
        button = self._group.button(id)
        if not button:
            return
            
        text = button.text()
        key = self._keys.get(id)
        button_number = len(self._group.buttons())
        
        if button_number > 0:
            tone = ((id + 1) / button_number) ** 0.5
            Utils.ui_sound("Toggle", tone)
            
        self.selection_changed.emit(id, text, key)

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentText(self) -> str:
        btn = self._group.checkedButton()
        return btn.text() if btn else ""

    def currentData(self):
        idx = self._group.checkedId()
        return self._keys.get(idx)

    def setCurrentText(self, text: str):
        for button in self._group.buttons():
            if button.text() == text:
                button.setChecked(True)
                break

    def setCurrentData(self, key):
        for idx, k in self._keys.items():
            if str(k) == str(key):
                button = self._group.button(idx)
                
                if button:
                    button.setChecked(True)
                
                break
    
    def setValue(self, value):
        if isinstance(value, int):
            self.setCurrentIndex(value)
        
        elif isinstance(value, str):
            self.setCurrentText(value)
        
        else:
            self.setCurrentData(value)

class CheckboxWithLabel(BaseControlContainer):
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

    def stateChanged(self, func):
        self.checkbox.stateChanged.connect(func)

    def setValue(self, value: bool):
        if isinstance(value, bool):
            self.setChecked(value)

class TextboxWithLabel(BaseControlContainer):
    def __init__(self, description: str, min_value, max_value, default: str = None):
        super().__init__()
        self.setMaximumHeight(100)

        self.description_label = QLabel(description)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.description_label.setStyleSheet("color: #ddd; padding: 0px;")
        self.description_label.setFont(Utils.NType(14))
        self.inner_layout.addWidget(self.description_label)

        self.textbox = Textbox(min_value, max_value, None, "number")
        self.textbox.setFixedHeight(45)
        self.textbox.setMaximumWidth(300)
        self.textbox.setContentsMargins(0, 0, 0, 7)
        self.inner_layout.addWidget(self.textbox, alignment=Qt.AlignmentFlag.AlignLeft)

        if default:
            self.setValue(default)

    def setValue(self, value):
        self.textbox.setText(str(value))

    def getValueAsText(self) -> str:
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

    def getValueAsText(self) -> str:
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

        self.setFixedHeight(18)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        width = self.width()
        height = self.height()
        seg_width = width / self.segment_number

        painter.setPen(Qt.NoPen)

        radius = 10

        for i in range(self.segment_number):
            color = QColor("#ddd") if self.active[i] else QColor(Styles.Colors.glass_border)
            painter.setBrush(color)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            if i != self.segment_number - 1:
                rect = QRectF(i * seg_width, 0, seg_width + 1, height)
            
            else:
                rect = QRectF(i * seg_width, 0, seg_width, height)

            path = QPainterPath()

            if i == 0:
                path.moveTo(rect.topRight())
                path.lineTo(rect.topLeft() + QPointF(radius, 0))
                path.quadTo(rect.topLeft(), rect.topLeft() + QPointF(0, radius))
                path.lineTo(rect.bottomLeft() + QPointF(0, -radius))
                path.quadTo(rect.bottomLeft(), rect.bottomLeft() + QPointF(radius, 0))
                path.lineTo(rect.bottomRight())
                path.lineTo(rect.topRight())

            elif i == self.segment_number - 1:
                path.moveTo(rect.topLeft())
                path.lineTo(rect.topRight() - QPointF(radius, 0))
                path.quadTo(rect.topRight(), rect.topRight() + QPointF(0, radius))
                path.lineTo(rect.bottomRight() - QPointF(0, radius))
                path.quadTo(rect.bottomRight(), rect.bottomRight() - QPointF(radius, 0))
                path.lineTo(rect.bottomLeft())
                path.lineTo(rect.topLeft())

            else:
                path.addRect(rect)

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

class EffectPreviewWidget(QWidget):
    apply_requested = pyqtSignal(str, dict)

    def __init__(self, effect_name, config, glyph, parent=None):
        super().__init__(parent)
        self.effect_name = effect_name
        self.config = config
        self.controls = {}
        self.glyph = glyph

        self.setFixedWidth(500)
        self.setStyleSheet(Styles.Controls.EffectSetupper)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        self.live_preview_bar = ScheduledSegmentedBar(30, loop = True)
        layout.addWidget(self.live_preview_bar)

        self.configuration = GlyphEffects.EffectsConfig[self.effect_name]
        for element in self.configuration["settings"]:
            if element["type"] == "checkbox":
                widget = Checkbox(
                    element["title"],
                    element["default"]
                )

            if element["type"] == "slider":
                widget = SliderWithLabel(
                    element["title"],
                    element["min"],
                    element["max"],
                    element["default"]
                )

            if element["type"] == "selector":
                widget = SelectorWithLabel(
                    element["title"],
                    element["map"],
                    element["default"]
                )

            layout.addWidget(widget)
            self.controls[element["key"]] = widget

        self.apply_button = NothingButton("Apply")
        self.apply_button.clicked.connect(self.on_apply)

        layout.addWidget(self.apply_button)

        for widget in self.controls.values():
            if isinstance(widget, Checkbox):
                widget.stateChanged.connect(self.on_control_changed)
            
            elif isinstance(widget, SliderWithLabel):
                widget.slider.valueChanged.connect(self.on_control_changed)
            
            elif isinstance(widget, SelectorWithLabel):
                widget.selection_changed.connect(self.on_control_changed)
        
        self.on_control_changed()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.live_preview_bar.play()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.live_preview_bar.stop()
    
    def _generate_effect_track(self):
        settings = self.get_settings()
        glyph = {
            "start": 0,
            "track": "1",
            "duration": max(self.glyph["duration"], 3000),
            "brightness": self.glyph["brightness"]
        }

        self.live_preview_bar.set_schedule(
            GlyphEffects.effect_to_glyph(
                GlyphEffects.effectCallback(
                    self.effect_name,
                    settings,
                    glyph
                ),
                60,
                "PREVIEW"
            )
        )

    def on_control_changed(self, *args):
        self._generate_effect_track()
        #self.live_preview_bar.play()

    def get_settings(self):
        settings = {}
        for key, widget in self.controls.items():
            if isinstance(widget, QCheckBox):
                settings[key] = widget.isChecked()
            
            elif isinstance(widget, SliderWithLabel):
                settings[key] = widget.value()
            
            elif isinstance(widget, SelectorWithLabel):
                settings[key] = widget.currentData()
        
        settings["segmented"] = GlyphEffects.EffectsConfig[self.effect_name]["segmented"]
        return settings

    def on_apply(self):
        self.apply_button.setText("Applied")
        self.apply_button.setStyleSheet(Styles.Buttons.normal_button_with_border)
        current_settings = self.get_settings()

        self.apply_requested.emit(self.effect_name, current_settings)
    
    def mousePressEvent(self, event):
        event.accept()

class ValuePopup(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)

        self.padding = 10
        
        self.label = QLabel(self)
        self.label.setFont(Utils.NType(12))
        self.label.setStyleSheet("color: white; background: transparent;")
        self.label.move(self.padding, self.padding)

        self.setup_animations()

    def setup_animations(self):
        self.INTERPOLATION_FACTOR = 0.15
        self._target_pos = None
        self._target_size = None
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.fade_in_animation = Utils.Animations.make_animation(
            self.opacity_effect,
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], b"opacity", 350
        )
        
        self.fade_out_animation = Utils.Animations.make_animation(
            self.opacity_effect,
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], b"opacity", 350,
            finished = self.on_hide_finished
        )
        
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_position_and_size)
        self.update_timer.setInterval(FPS_60)

    def on_hide_finished(self):
        self.update_timer.stop()
        super().hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor(Styles.Colors.secondary_background)
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRect(0, 0, self.width(), self.height()), 8, 8)

        super().paintEvent(event)

    def _layout_for_text(self, text: str):
        self.label.setText(text)
        self.label.adjustSize()
        
        label_target_size = self.label.size()
        full_width = label_target_size.width() + self.padding * 2
        full_height = label_target_size.height() + self.padding * 2
        
        self._target_size = QSize(full_width, full_height)

    def _compute_top_left(self, pos: QPoint):
        w = self.width()

        desired_x = pos.x() - w // 2
        desired_y = pos.y() + 5

        return QPoint(desired_x, desired_y)

    def _update_position_and_size(self):
        current_pos = self.pos()
        current_size = self.size()
        
        delta_x = self._target_pos.x() - current_pos.x()
        delta_y = self._target_pos.y() - current_pos.y()
        delta_w = self._target_size.width() - current_size.width()
        delta_h = self._target_size.height() - current_size.height()
        
        if (
            abs(delta_x) < 0.5
            and abs(delta_y) < 0.5
            and abs(delta_w) < 0.5
            and abs(delta_h) < 0.5
        ):
            
            self.move(self._target_pos)
            self.resize(self._target_size)

        new_x = round(current_pos.x() + delta_x * self.INTERPOLATION_FACTOR)
        new_y = round(current_pos.y() + delta_y * self.INTERPOLATION_FACTOR)
        
        new_w = round(current_size.width() + delta_w * self.INTERPOLATION_FACTOR)
        new_h = round(current_size.height() + delta_h * self.INTERPOLATION_FACTOR)
        
        self.move(new_x, new_y)
        self.resize(new_w, new_h)

    def show_text(self, text: str, pos: QPoint):
        self.fade_out_animation.stop()
        
        if self.label.text() != text:
            self._layout_for_text(text)

        self._target_pos = self._compute_top_left(pos)

        if not self.isVisible():
            self.show()
            self.update_timer.start()
            self.fade_in_animation.start()
    
    def hide(self):
        if self.fade_out_animation.state() == QPropertyAnimation.Running:
            return
        
        self.fade_in_animation.stop()
        self.fade_out_animation.start()
    
    def cleanup(self):
        self.update_timer.stop()
        self.update_timer.timeout.disconnect(self._update_position_and_size)
        self.update_timer.deleteLater()

        self.fade_in_animation.stop()
        self.fade_out_animation.stop()
        self.fade_in_animation.deleteLater()
        self.fade_out_animation.deleteLater()

        self.setGraphicsEffect(None)

        self.label.deleteLater()

        super().hide()
        self.deleteLater()

class MiniWaveformPreview(QWidget):
    preview_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_data = None
        self.pixmap = None

        self.mouse_pressed = False
        self.playhead_position = 0.0

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(Styles.Controls.MiniWaveformPreview)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_audio_data(self, audio_data):
        self.audio_data = audio_data
        self._prepare_audio_data()
        self.update()
    
    def set_playhead_position(self, value):
        self.playhead_position = value
        self.update()
    
    def _prepare_audio_data(self):
        audio = self.audio_data

        if audio.size == 0:
            self._min_samples = np.array([])
            self._max_samples = np.array([])
            self._waveform_max = 1.0

            return

        total_samples = audio.shape[0]

        fade_in_samples = int(total_samples * 0.03)
        fade_out_samples = int(total_samples * 0.03)

        fade_in_samples = min(fade_in_samples, total_samples)
        fade_out_samples = min(fade_out_samples, total_samples - fade_in_samples)

        processed_audio = audio.copy()

        if fade_in_samples > 0:
            fade_in_mask = np.linspace(0.0, 1.0, fade_in_samples)
            start_slice = slice(0, fade_in_samples)

            if audio.ndim == 1:
                processed_audio[start_slice] *= fade_in_mask
            
            elif audio.ndim == 2:
                processed_audio[start_slice, :] *= fade_in_mask[:, np.newaxis]

        if fade_out_samples > 0:
            fade_out_mask = np.linspace(1.0, 0.0, fade_out_samples)
            end_start_index = total_samples - fade_out_samples
            end_slice = slice(end_start_index, total_samples)

            if audio.ndim == 1:
                processed_audio[end_slice] *= fade_out_mask
            
            elif audio.ndim == 2:
                processed_audio[end_slice, :] *= fade_out_mask[:, np.newaxis]

        audio = processed_audio

        if audio.ndim == 1:
            self._min_samples = audio
            self._max_samples = audio
        
        elif audio.ndim == 2:
            self._min_samples = np.min(audio, axis=1)
            self._max_samples = np.max(audio, axis=1)
        
        else:
            self._min_samples = np.array([])
            self._max_samples = np.array([])
            self._waveform_max = 1.0

            return

        dtype = self.audio_data.dtype
        scale = 32767.0 if np.issubdtype(dtype, np.integer) else 1.0

        max_abs_val = max(np.max(np.abs(self._min_samples)), np.max(np.abs(self._max_samples)))

        self._waveform_max = max_abs_val / scale
        if self._waveform_max == 0.0:
            self._waveform_max = 1.0

    def generate_pixmap(self):
        width = self.width() - 4
        height = self.height() - 10

        min_samples = self._min_samples
        max_samples = self._max_samples
        waveform_max = self._waveform_max

        if min_samples.size == 0:
            return None

        num_samples = len(min_samples)
        if num_samples == 0:
            return None

        samples_per_pixel_tile = num_samples / width
        step = max(1, int(np.ceil(samples_per_pixel_tile)))

        padded_length = ((num_samples + step - 1) // step) * step
        pad_amount = padded_length - num_samples

        padded_min = np.pad(min_samples, (0, pad_amount), mode = 'constant')
        padded_max = np.pad(max_samples, (0, pad_amount), mode = 'constant')

        reshaped_min = padded_min.reshape(-1, step)
        reshaped_max = padded_max.reshape(-1, step)

        min_vals = np.min(reshaped_min, axis=1)
        max_vals = np.max(reshaped_max, axis=1)

        max_vals_f = max_vals.astype(np.float32) / waveform_max
        min_vals_f = min_vals.astype(np.float32) / waveform_max

        y_center = height / 2.0

        amplitudes_top = y_center - max_vals_f * y_center
        amplitudes_bottom = y_center - min_vals_f * y_center

        sigma = CurrentSettings["waveform_smoothing"]
        
        if sigma and sigma > 0.0 and len(amplitudes_top) > 1:
            pad = int(np.ceil(sigma * 3.0))
            pad = min(pad, len(amplitudes_top) - 1)
        
            top_padded = np.pad(amplitudes_top, (pad, pad), mode = 'reflect')
            bottom_padded = np.pad(amplitudes_bottom, (pad, pad), mode = 'reflect')
        
            smooth_top_padded = Utils.gaussian_filter1d_np(top_padded, sigma=sigma)
            smooth_bottom_padded = Utils.gaussian_filter1d_np(bottom_padded, sigma=sigma)
        
            smooth_top = smooth_top_padded[pad:pad + len(amplitudes_top)]
            smooth_bottom = smooth_bottom_padded[pad:pad + len(amplitudes_bottom)]
        
        else:
            smooth_top = amplitudes_top
            smooth_bottom = amplitudes_bottom
        
        if len(smooth_top) == len(smooth_bottom):
            mask = smooth_top > smooth_bottom
            
            if np.any(mask):
                avg = (smooth_top[mask] + smooth_bottom[mask]) / 2.0
                smooth_top[mask] = avg
                smooth_bottom[mask] = avg

        if len(smooth_top) == 0 or len(smooth_bottom) == 0:
            return None

        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)

        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        bar_width = float(width) / len(smooth_top)

        path = QPainterPath()
        for i in range(len(smooth_top)):
            x = i * bar_width
            y = max(0.0, min(float(height), float(smooth_top[i])))
            
            if i == 0:
                path.moveTo(x, y)
            
            else:
                path.lineTo(x, y)

        for i in reversed(range(len(smooth_bottom))):
            x = i * bar_width
            y = max(0.0, min(float(height), float(smooth_bottom[i])))
            path.lineTo(x, y)

        path.closeSubpath()

        border_color = QColor(170, 170, 170, 255) 
        fill_color = QColor(255, 255, 255, 100)

        painter.setPen(QPen(border_color, 2.0)) 
        painter.setBrush(QBrush(fill_color))
        painter.drawPath(path)

        painter.end()

        return pixmap

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.pixmap:
            painter = QPainter(self)
            painter.drawPixmap(2, 5, self.pixmap)

            pen = QPen(QColor(255, 0, 0), 2.0)

            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            x = float(self.width() * self.playhead_position)
            painter.drawLine(QLineF(x, 0.0, x, float(self.height())))

    def mousePressEvent(self, event: QMouseEvent):
        if self.pixmap and event.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = True
            normalized_pos = max(0.0, min(1.0, event.x() / self.width()))
            self.set_playhead_position(normalized_pos)
            self.preview_clicked.emit(normalized_pos)
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        normalized_pos = max(0.0, min(1.0, event.x() / self.width()))
        self.set_playhead_position(normalized_pos)
        self.preview_clicked.emit(normalized_pos)
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.mouse_pressed = False
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)

        if self.isVisible():
            self.pixmap = self.generate_pixmap()
            self.update()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.pixmap = self.generate_pixmap()

class Textbox(QLineEdit):
    safeTextChanged = pyqtSignal(str)

    def __init__(
            self,
            min_number,
            max_number,
            max_length,
            input_type,
            default_text: str | None = None,
            placeholder: str | None = None,
            *args,
            **kwargs
        ):
        
        super().__init__(*args, **kwargs)

        self.input_type = input_type
        self.min_number = min_number
        self.max_number = max_number
        self.max_length = max_length
        self.default_text = default_text

        self._is_default_text_set = False
        self.animating = False
        self.is_key_pressed = False
        self.arrow_pressed = False
        self.arrow_direction = 0

        self.original_pos = QPoint()
        self.original_input_field_pos = QPoint()

        self.setPlaceholderText(placeholder or "")
        self.setFont(Utils.NType(14))
        self.setStyleSheet("""
            background-color: #222;
            color: #fff;
            padding: 8px 12px;
            border-radius: 14px;
            border: 2px solid #444;
        """)

        self.input_field_animation = QPropertyAnimation(self, b"pos")
        self.input_field_animation.setDuration(TEXTBOX_INPUT)
        self.input_field_animation.setEasingCurve(QEasingCurve.OutElastic)

        self.shake_animation = QPropertyAnimation(self, b"pos")
        self.shake_animation.setDuration(TEXTBOX_SHAKE)
        self.shake_animation.setEasingCurve(QEasingCurve.Linear)

        self.shake_timer = QTimer(self)
        self.shake_timer.setInterval(TEXTBOX_SHAKE_PER)
        self.shake_timer.timeout.connect(self._animate_to_random_shake_pos)

        self.glitch_timer = QTimer(self)
        self.glitch_timer.timeout.connect(self._glitch_step)
        self.glitch_steps_left = 0
        self.original_text = super().text()

        self.textChanged.connect(self.schedule_input_field_animation)
        self.textChanged.connect(self._emit_safe_text_changed)

    @staticmethod
    def _parse_time_to_seconds(text: str) -> int | None:
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

    @staticmethod
    def _seconds_to_time_text(seconds: int) -> str:
        s = int(seconds)
        m = s // 60
        sec = s % 60

        return f"{m}:{sec:02}"

    def _emit_safe_text_changed(self, text: str):
        if not self.animating and text:
            self.safeTextChanged.emit(text)

    def showEvent(self, event: QEvent):
        super().showEvent(event)
        
        if self.original_input_field_pos.isNull():
            self.original_input_field_pos = self.pos()
        
        if not self._is_default_text_set and self.default_text is not None:
            super().setText(self.default_text)
            self._is_default_text_set = True

    def schedule_input_field_animation(self):
        if self.original_input_field_pos.isNull():
            return
        
        Utils.ui_sound("Tick")
        
        if self.is_key_pressed:
            return
        
        if self.input_field_animation.state() == QAbstractAnimation.Running:
            self.input_field_animation.stop()
        
        self.move(self.original_input_field_pos + QPoint(-5, -5))
        self._run_input_field_animation()

    def _run_input_field_animation(self):
        self.input_field_animation.setStartValue(self.pos())
        self.input_field_animation.setEndValue(self.original_input_field_pos)
        self.input_field_animation.start()

    def _validate_new_text(self, new_text: str, new_char: str) -> bool:
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
            parsed = self._parse_time_to_seconds(normalized)

            if parsed is None:
                return False
            
            if parsed > self.max_number:
                return False
            
            if parsed < self.min_number:
                super().setText(self._seconds_to_time_text(self.min_number + 1))
                self.setCursorPosition(len(super().text()))
                return "handled"
            
            return True

        return True

    def keyPressEvent(self, event):
        key = event.key()
        cur_text = super().text()
        new_char = event.text()

        if CurrentSettings["textbox_animations"] and not self.arrow_pressed and cur_text:
            if key in (Qt.Key_Left, Qt.Key_Right):
                pos = self.cursorPosition()
                
                if key == Qt.Key_Left:
                    pos -= 1
                
                elif key == Qt.Key_Right:
                    pos += 1
                
                direction = -1 if key == Qt.Key_Left else 1
                tone = 0.85 + (pos / len(cur_text)) * 0.4
                
                print(f"{'Left' if direction == -1 else 'Right'} key | Tone {tone}")

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
        
        else:
            sel_start = self.selectionStart()
            sel_text = self.selectedText() if sel_start != -1 else ""
            sel_len = len(sel_text)
            insert_at = sel_start if sel_start != -1 else self.cursorPosition()
            
            if not new_char:
                return super().keyPressEvent(event)
            
            new_text = cur_text[:insert_at] + new_char + cur_text[insert_at + sel_len:]

            result = self._validate_new_text(new_text, new_char)
            if result is False:
                self.start_glitch()
                return
            
            if result == "handled":
                return

            super().keyPressEvent(event)

        if key not in (Qt.Key_Left, Qt.Key_Right):
            if self.is_key_pressed:
                return
            
            self.is_key_pressed = True
            
            if CurrentSettings["textbox_animations"]:
                self.shake_timer.start()
                self._animate_to_random_shake_pos()

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)
        
        if event.key() in (Qt.Key_Left, Qt.Key_Right) and self.arrow_pressed:
            self.arrow_pressed = False
            self.arrow_direction = 0
            self.animate_return_from_arrow()

        self.is_key_pressed = False
        self.shake_timer.stop()
        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()

        if CurrentSettings["textbox_animations"]:
            self.shake_animation.setStartValue(self.pos())
            self.shake_animation.setEndValue(self.original_input_field_pos)
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
            return self._parse_time_to_seconds(raw)
        
        if self.input_type == "number":
            try:
                return int(raw)
            
            except ValueError:
                return None
        
        return raw

    def setText(self, text: str | int):
        if self.input_type == ":time":
            super().setText(self._seconds_to_time_text(int(text)))
            return
        
        if self.input_type == "number":
            super().setText(str(text))
            return
        
        super().setText(str(text))

    def start_glitch(self, sound: bool = True):
        if sound:
            Utils.ui_sound("Reject")
        
        if not CurrentSettings["textbox_animations"]:
            return
        
        if self.glitch_timer.isActive():
            return
        
        self.animating = True
        self.original_pos = self.pos()
        self.original_text = super().text()
        self.glitch_steps_left = 7
        self.glitch_timer.start(24)

    def _glitch_step(self):
        if self.glitch_steps_left <= 0:
            self.move(self.original_pos)
            super().setText(self.original_text)
            
            self.glitch_timer.stop()
            self.animating = False
            
            return

        length = max(1, len(self.original_text or ""))
        glitch_text = ''.join(random.choices(string.ascii_letters + string.punctuation, k=length))
        
        super().setText(glitch_text)
        
        dx = random.randint(-2, 2)
        dy = random.randint(-2, 2)
        
        self.move(self.original_pos + QPoint(dx, dy))
        self.glitch_steps_left -= 1

    def animate_arrow_hold(self, offset: int):
        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(self.original_input_field_pos + QPoint(offset, 0))
        self.shake_animation.setDuration(120)
        self.shake_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.shake_animation.start()

    def animate_return_from_arrow(self):
        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(self.original_input_field_pos)
        self.shake_animation.setDuration(180)
        self.shake_animation.setEasingCurve(QEasingCurve.OutElastic)
        self.shake_animation.start()

    def _animate_to_random_shake_pos(self):
        shake_radius = 5
        dx = random.uniform(-shake_radius, shake_radius)
        dy = random.uniform(-shake_radius, shake_radius)
        target_pos = self.original_input_field_pos + QPoint(int(dx), int(dy))
        
        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()
        
        self.shake_animation.setStartValue(self.pos())
        self.shake_animation.setEndValue(target_pos)
        self.shake_animation.setDuration(TEXTBOX_SHAKE)
        self.shake_animation.setEasingCurve(QEasingCurve.Linear)
        self.shake_animation.start()

    def is_not_valid(self) -> bool:
        raw = super().text()
        
        if not raw:
            return False
        
        secs = self._parse_time_to_seconds(raw)
        return secs is not None and secs < self.min_number


class NavButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFont(Utils.NType(13))
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)

        self.active_style = f"""
            QPushButton {{
                background-color: {Styles.Colors.nothing_accent};
                color: {Styles.Colors.font_color};
                border: none;
                padding: 8px 15px;
                border-radius: 18px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {Styles.Colors.nothing_accent_hover};
            }}
        """
        self.inactive_style = f"""
            QPushButton {{
                background-color: transparent;
                color: {Styles.Colors.font_color};
                border: none;
                padding: 8px 15px;
                border-radius: 18px;
                text-align: left;
            }}
        """
        self.setActive(False)

    def setActive(self, is_active):
        self.setChecked(is_active)
        if is_active:
            self.setStyleSheet(self.active_style)
        else:
            self.setStyleSheet(self.inactive_style)

class FloatingWindow(QDialog):
    def __init__(
            self,
            title: str,
            bpm: int = None,
            player = None,
            max_tilt_angle = 12,

            animation_style = "bouncy",
            enable_tilt: bool = True,
            margin = 200,
            dialog = True,
            enable_transition_audio_effects: bool = True
        ):

        super().__init__()
        
        self.bpm = bpm
        self.player = player
        self.margin = margin
        self.enable_tilt = enable_tilt
        self.max_tilt_angle = max_tilt_angle

        self.animation_style = CurrentSettings["animation_style"] or animation_style

        self.is_ready = False
        self.is_closing = False
        self.was_cancelled = False
        
        self.enable_transition_audio_effects = enable_transition_audio_effects

        if dialog:
            self.setWindowFlags(self.windowFlags() | Qt.Dialog | Qt.FramelessWindowHint)
        
        else:
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.setup_layout(title)
        self.setup_timers()
        self.setup_animation_properties()

        self.update_bpm(self.bpm)
        
        QTimer.singleShot(0, self.start_open_animation)

    def update_bpm(self, bpm = None):
        if not CurrentSettings["bpm_animations"]:
            return
        
        if not bpm:
            return

        if bpm >= 200:
            self.bpm = int(bpm / 2)
        
        if bpm <= 80:
            self.bpm = int(bpm * 2)
        
        else:
            self.bpm = int(bpm)

        self.bpm_timer.setInterval(60000 // self.bpm)
        self.bpm_timer.start()

    def setup_timers(self):
        if not CurrentSettings["floating_window_animations"]:
            return

        if self.enable_tilt:
            self.tilt_animation_timer = QTimer(self)
            self.tilt_animation_timer.setInterval(FPS_60)
            self.tilt_animation_timer.timeout.connect(self.tilt_rotation_update)
            self.tilt_animation_timer.start()
        
        if not CurrentSettings["bpm_animations"]:
            return
        
        self.bpm_timer = QTimer(self)
        self.bpm_timer.setSingleShot(True)
        self.bpm_timer.timeout.connect(self.bpm_tick_animation)
        
        if self.bpm:
            self.bpm_timer.start(FPS_30)

    def setup_layout(self, title):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(self.margin, self.margin, self.margin, self.margin)
        main_layout.setSpacing(0)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(15)

        main_layout.addLayout(self.content_layout)

        if title:
            self.title_label = QLabel(title)
            self.title_label.setStyleSheet("color: #fff;")
            self.title_label.setFont(Utils.NType(15))

            self.content_layout.addWidget(self.title_label)
        
        self.adjustSize()

    def setup_animation_properties(self):
        self.current_tilt_x = 0.0
        self.current_tilt_y = 0.0
        self.target_tilt_x = 0.0
        self.target_tilt_y = 0.0
        self.open_tilt_x = 0.0
        self.open_tilt_y = 0.0
        self.close_tilt_x = 0.0
        self.disturbe_tilt_x = 0.0
        self.bpm_tilt_x = 0.0

        self.tilt_smoothing = float(CurrentSettings["window_hover_smoothing"])

        self.open_opacity = 1.0

        self.open_rotation = 0.0
        self.exit_rotation = 0.0
        self.disturbe_rotation = 0.0
        self.random_anim_rotation = 0.0

        self.entry_rotation_angle = 0
        self.current_rotation = 0.0
        self.entry_rotation_exit_angle = 0
        
        self.open_scale = 1.0
        self.exit_scale = 1.0
        self.bpm_scale = 1.0
        self.disturbe_scale = 1.0
        self.wobble_scale = 1.0

        self.bpm_wobble_start_size = 1.03
        self.background_size = QRect()
    
    def is_big(self):
        if self.width() - self.margin * 2 > 500 or self.height() - self.margin * 2 > 500:
            return True
        
        return False
    
    def set_bpm_start_size(self, start_coeff):
        self.bpm_wobble_start_size = start_coeff

    def tilt_rotation_update(self):
        if not self.isActiveWindow():
            return

        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)
        center_x = self.width() / 2
        center_y = self.height() / 2

        content_rect_global = QRect(self.mapToGlobal(self.content_layout.geometry().topLeft()), self.content_layout.geometry().size())

        if content_rect_global.contains(global_pos):
            x_norm = -(local_pos.x() - center_x) / center_x
            y_norm = (local_pos.y() - center_y) / center_y

            self.target_tilt_x = -y_norm * self.max_tilt_angle
            self.target_tilt_y = x_norm * self.max_tilt_angle

        combined_target_x = self.target_tilt_x + self.open_tilt_x + self.bpm_tilt_x + self.close_tilt_x + self.disturbe_tilt_x
        combined_target_y = self.target_tilt_y + self.open_tilt_y
        
        prev_x, prev_y = self.current_tilt_x, self.current_tilt_y
        self.current_tilt_x += (combined_target_x - self.current_tilt_x) * self.tilt_smoothing
        self.current_tilt_y += (combined_target_y - self.current_tilt_y) * self.tilt_smoothing

        if (
                abs(self.current_tilt_x - prev_x) > 1e-3
                or abs(self.current_tilt_y - prev_y) > 1e-3
            ):
            
            self.update()
    
    def make_animation(self, keyframes: list, property: bytes, duration: int, curve: QEasingCurve = QEasingCurve.OutCubic):
        anim = QPropertyAnimation(self, property)
        anim.setDuration(duration)
        anim.setKeyValues(keyframes)
        anim.setEasingCurve(curve)

        return anim

    def period_randomizer(self, *periods):
        period = random.choice(periods)
        return random.randint(*period)

    def center_window(self):
        window = QApplication.activeWindow()
        if window:
            window_center = window.geometry().center()
        
        else:
            window_center = QApplication.primaryScreen().geometry().center()
        
        final_rect = QRect(
            window_center.x() - self.width() // 2,
            window_center.y() - self.height() // 2,
            self.width(), self.height()
        )

        self.setGeometry(final_rect)

        return final_rect


    # Animations - Smooth Style
    def animation_open_smooth(self, final_rect, size):
        start_scale = get_scale(*size, 2.0, 1.1, 1200)

        anim_tilt_x = self.make_animation(
            [
                (0.0, 30),
                (1.0, 0)
            ], b"openTiltX", 800, QEasingCurve.OutExpo
        )

        anim_scale = self.make_animation(
            [
                (0.0, start_scale),
                (1.0, 1.0)
            ], b"openScale", 650, QEasingCurve.OutExpo
        )

        anim_opacity = self.make_animation(
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], b"windowOpacity", 500
        )

        def onValueChanged(value):
            self.open_opacity = value
        
        self.group_animate(
            [
                anim_tilt_x,
                anim_opacity,
                anim_scale
            ], valueChanged = onValueChanged
        )
    
    def animation_close_smooth(self, size):
        end_scale = get_scale(*size, 1.7)

        anim_tilt_x = self.make_animation(
            [
                (0.0, 0),
                (1.0, -30)
            ], b"closeTiltX", 800, QEasingCurve.OutExpo
        )

        anim_scale = self.make_animation(
            [
                (0.0, 1.0),
                (1.0, end_scale)
            ], b"exitScale", 800, QEasingCurve.OutExpo
        )

        anim_opacity = self.make_animation(
            [
                (0.0, self.windowOpacity()),
                (1.0, 0.0)
            ], b"windowOpacity", 400
        )

        self.group_animate(
            [
                anim_tilt_x,
                anim_scale,
                anim_opacity
            ], self._really_close
        )


    # Animations - Bouncy Style
    def animation_open_bouncy(self, final_rect, size):
        curve = QEasingCurve(QEasingCurve.OutElastic)
        curve.setPeriod(0.27)
        curve.setAmplitude(1.7)

        scale_curve = QEasingCurve(QEasingCurve.OutCubic)
        scale_curve.setAmplitude(2.0)
        scale_curve.setOvershoot(0.0)
        scale_curve.setPeriod(0.0)

        start_pos_y = self.period_randomizer((-170, -130), (130, 170))
        start_angle = get_rotation(*size)
        start_scale = get_scale(*size, base_scale = 2.0)

        optimal_tilt = get_optimal_tilt(*size)
        optimal_tilt = -optimal_tilt if random.random() < 0.5 else optimal_tilt

        if self.is_big():
            start_angle = self.period_randomizer((-20, -10), (10, 20))
            anim_geo_duration = 830
            anim_rotation_duration = 1170
        
        else:
            start_angle = self.period_randomizer((-30, -10), (15, 30))
            anim_geo_duration = 750
            anim_rotation_duration = 1050
        
        anim_position = self.make_animation(
            [
                (0.0, final_rect.translated(0, start_pos_y).topLeft()),
                (1.0, final_rect.topLeft())
            ], b"pos", anim_geo_duration, QEasingCurve.OutElastic
        )

        anim_scale = self.make_animation(
            [
                (0.0, start_scale),
                (1.0, 1.0)
            ], b"openScale", 1200, QEasingCurve.OutCubic
        )

        anim_tilt_x = self.make_animation(
            [
                (0.0, int(optimal_tilt)),
                (1.0, 0)
            ], b"openTiltX", 1000, QEasingCurve.OutElastic
        )

        anim_rotation = self.make_animation(
            [
                (0.0, start_angle),
                (1.0, 0)
            ], b"openRotation", anim_rotation_duration, curve
        )

        anim_opacity = self.make_animation(
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], b"windowOpacity", 500
        )

        def onValueChanged(value):
            self.open_opacity = value
        
        self.group_animate(
            [
                anim_position,
                anim_scale,
                anim_rotation,
                anim_opacity,
                anim_tilt_x
            ], valueChanged = onValueChanged
        )
    
    def animation_close_bouncy(self, size):
        self.target_tilt_y = random.randint(5, 15)

        anim_rotation = self.make_animation(
            [
                (0.0, 0),
                (1.0, get_rotation(*size, 11, 3))
            ], b"exitRotation", 700
        )

        anim_scale = self.make_animation(
            [
                (0.0, 1.0),
                (1.0, get_scale(*size, base_scale = 1.45))
            ], b"exitScale", 400, QEasingCurve.InOutCubic
        )

        anim_opacity = self.make_animation(
            [
                (0.0, self.windowOpacity()),
                (1.0, 0.0)
            ], b"windowOpacity", 400
        )

        self.group_animate(
            [
                anim_rotation,
                anim_scale,
                anim_opacity
            ], self._really_close
        )
    

    # Animations - Roll Style
    def animation_open_roll(self, final_rect, size):
        anim_tilt_x = self.make_animation(
            [
                (0.0, 200),
                (1.0, 0)
            ], b"openTiltX", 1000, QEasingCurve.OutExpo
        )

        anim_scale = self.make_animation(
            [
                (0.0, 0.1),
                (1.0, 1.0)
            ], b"openScale", 800, QEasingCurve.OutExpo
        )

        anim_opacity = self.make_animation(
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], b"windowOpacity", 500
        )

        def onValueChanged(value):
            self.open_opacity = value
        
        self.group_animate(
            [
                anim_tilt_x,
                anim_opacity,
                anim_scale
            ], valueChanged = onValueChanged
        )
    
    def animation_close_roll(self, size):
        anim_tilt_x = self.make_animation(
            [
                (0.0, 0),
                (1.0, 100)
            ], b"closeTiltX", 800, QEasingCurve.OutExpo
        )

        anim_scale = self.make_animation(
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], b"exitScale", 350, QEasingCurve.InCirc
        )

        anim_opacity = self.make_animation(
            [
                (0.0, self.windowOpacity()),
                (1.0, 0.0)
            ], b"windowOpacity", 700
        )

        self.group_animate(
            [
                anim_tilt_x,
                anim_opacity,
                anim_scale
            ], self._really_close
        )

    def start_open_animation(self):
        self.adjustSize()
        final_rect = self.center_window()
        self.is_ready = True
        self.open_sound()

        size = self.get_window_size()

        if not CurrentSettings["floating_window_animations"]:
            return

        {
            "bouncy": self.animation_open_bouncy,
            "smooth": self.animation_open_smooth,
            "roll": self.animation_open_roll
        }.get(self.animation_style)(final_rect, size)

    def player_pulse(self, duration = 0.4, pulse_peak_speed = 1.2):
        start_speed = self.player.speed
        duration_half = duration / 2

        self.player.set_speed(pulse_peak_speed, duration = duration_half)
        QTimer.singleShot(int(duration_half * 1000), lambda: self.player.set_speed(start_speed, duration = duration_half))
    
    def open_sound(self):
        if self.enable_transition_audio_effects:
            if self.player:
                if self.player.is_playing:
                    return self.player_pulse()

        Utils.ui_sound(
            {
                "bouncy": "BouncyPack/Open",
                "smooth": "SmoothPack/Open",
                "roll": "SmoothPack/Open"
            }.get(self.animation_style)
        )
    
    def close_sound(self):
        if self.enable_transition_audio_effects:
            if self.player:
                if self.player.is_playing:
                    return self.player_pulse(0.4, 0.5)

        Utils.ui_sound(
            {
                "bouncy": "BouncyPack/Close",
                "smooth": "SmoothPack/Close",
                "roll": "SmoothPack/Close"
            }.get(self.animation_style)
        )

    def group_animate(self, animations, finished = None, valueChanged = None, multiplier = 1.0):
        self.anim_group = QParallelAnimationGroup(self)

        if multiplier == 1.0:
            multiplier = float(CurrentSettings["animation_multiplier"])

        if multiplier != 1.0:
            for animation in animations:
                animation.setDuration(int(animation.duration() * multiplier))

        for animation in animations:
            if valueChanged:
                animation.valueChanged.connect(valueChanged)
            
            self.anim_group.addAnimation(animation)
        
        if finished:
            self.anim_group.finished.connect(finished)

        self.anim_group.start(QAbstractAnimation.DeleteWhenStopped)
    
    def random_rotate_anim(self):
        if not CurrentSettings["floating_window_animations"]:
            return
        
        self.anim_rotation = self.make_animation(
            [
                (0.0, 0),
                (0.5, self.period_randomizer((-6, -3), (3, 6))),
                (1.0, 0)
            ], b"randomAnimRotation", 350
        )
        
        self.anim_rotation.start()

    @pyqtProperty(float) # type: ignore
    def exitRotation(self):
        return self.exit_rotation

    @exitRotation.setter
    def exitRotation(self, value):
        self.exit_rotation = value
    
    @pyqtProperty(float) # type: ignore
    def openTiltX(self):
        return self.open_tilt_x

    @openTiltX.setter
    def openTiltX(self, value):
        self.open_tilt_x = value
    
    @pyqtProperty(float) # type: ignore
    def bpmTiltX(self):
        return self.bpm_tilt_x

    @bpmTiltX.setter
    def bpmTiltX(self, value):
        self.bpm_tilt_x = value
    
    @pyqtProperty(float) # type: ignore
    def disturbeTiltX(self):
        return self.disturbe_tilt_x

    @disturbeTiltX.setter
    def disturbeTiltX(self, value):
        self.disturbe_tilt_x = value

    @pyqtProperty(float) # type: ignore
    def openTiltY(self):
        return self.open_tilt_y

    @openTiltY.setter
    def openTiltY(self, value):
        self.open_tilt_y = value
    
    @pyqtProperty(float) # type: ignore
    def closeTiltX(self):
        return self.close_tilt_x

    @closeTiltX.setter
    def closeTiltX(self, value):
        self.close_tilt_x = value

    @pyqtProperty(float) # type: ignore
    def openRotation(self):
        return self.open_rotation

    @openRotation.setter
    def openRotation(self, value):
        self.open_rotation = value
    
    @pyqtProperty(float) # type: ignore
    def disturbeRotation(self):
        return self.disturbe_rotation

    @disturbeRotation.setter
    def disturbeRotation(self, value):
        self.disturbe_rotation = value
    
    @pyqtProperty(float) # type: ignore
    def randomAnimRotation(self):
        return self.random_anim_rotation

    @randomAnimRotation.setter
    def randomAnimRotation(self, value):
        self.random_anim_rotation = value

    @pyqtProperty(float) # type: ignore
    def exitScale(self):
        return self.exit_scale

    @exitScale.setter
    def exitScale(self, value):
        self.exit_scale = value
        self.update()
    
    @pyqtProperty(float) # type: ignore
    def openScale(self):
        return self.open_scale

    @openScale.setter
    def openScale(self, value):
        self.open_scale = value
        self.update()
    
    @pyqtProperty(float) # type: ignore
    def wobbleScale(self):
        return self.wobble_scale

    @wobbleScale.setter
    def wobbleScale(self, value):
        self.wobble_scale = value
        self.update()

    @pyqtProperty(float) # type: ignore
    def bpmScale(self):
        return self.bpm_scale

    @bpmScale.setter
    def bpmScale(self, value):
        self.bpm_scale = value
        self.update()

    @pyqtProperty(float) # type: ignore
    def disturbeScale(self):
        return self.disturbe_scale

    @disturbeScale.setter
    def disturbeScale(self, value):
        self.disturbe_scale = value
        self.update()
    
    @pyqtProperty(QRect) # type: ignore
    def backgroundSize(self):
        return self.background_size
    
    @backgroundSize.setter
    def backgroundSize(self, value):
        self.background_size = value
    
    def bpm_tick_animation(self):
        if not self.player.is_playing:
            return self.bpm_timer.start(FPS_30)
        
        audio_level = self.player.get_current_audio_level()

        if audio_level < 0.08:
            return self.bpm_timer.start(FPS_30)

        speed = self.player.speed or 0.01
        interval_ms = int(round(60000.0 / (self.bpm * speed)))

        self.bpm_scale_animation = self.make_animation(
            [
                (0.0, float(1.0)),
                (0.5, float(self.bpm_wobble_start_size + self.squish(audio_level))),
                (1.0, float(1.0))
            ],
            b"bpmScale",
            interval_ms
        )

        self.bpm_scale_animation.start(QAbstractAnimation.DeleteWhenStopped)
        self.bpm_timer.start(interval_ms)
    
    def squish(self, x, power = 1.2):
        return 0.05 * (x ** power)
    
    def wobble(self):
        if not CurrentSettings["floating_window_animations"]:
            return

        self.anim_scale = self.make_animation(
            [
                (0.0, 1.0),
                (0.5, 1.05),
                (1.0, 1.0)
            ], b"wobbleScale", 500
        )

        self.anim_scale.start()
    
    def animation_disturbe_bouncy(self):
        start_angle = random.choice([
            random.randint(-30, -15),
            random.randint(15, 30)
        ])

        anim_scale = self.make_animation(
            [
                (0.0, self.disturbe_scale),
                (0.5, min(self.disturbe_scale + 0.2, 1.5)),
                (1.0, 1.0)
            ], b"disturbeScale", 500
        )

        anim_rotation = self.make_animation(
            [
                (0.0, self.disturbe_rotation),
                (0.5, self.disturbe_rotation + start_angle if self.disturbe_rotation >= 0 else self.disturbe_rotation - start_angle),
                (1.0, 0)
            ], b"disturbeRotation", 1000, QEasingCurve.OutElastic
        )

        self.group_animate(
            [
                anim_scale,
                anim_rotation
            ]
        )

        self.anim_group.start(QAbstractAnimation.DeleteWhenStopped)

    def animation_disturbe_roll(self):
        anim_tilt_x = self.make_animation(
            [
                (0.0, self.disturbe_tilt_x),
                (0.5, min(self.disturbe_tilt_x + 45, 90) if self.disturbe_tilt_x >= 0 else max(self.disturbe_tilt_x - 45, -90)),
                (1.0, 0)
            ], b"disturbeTiltX", 1100, QEasingCurve.OutElastic
        )

        anim_scale = self.make_animation(
            [
                (0.0, self.disturbe_scale),
                (0.5, min(self.disturbe_scale + 0.1, 2.0)),
                (1.0, 1.0)
            ], b"disturbeScale", 1200, QEasingCurve.OutElastic
        )

        self.group_animate(
            [
                anim_tilt_x,
                anim_scale
            ]
        )

        self.anim_group.start(QAbstractAnimation.DeleteWhenStopped)
    
    def animation_disturbe_smooth(self):
        anim_scale = self.make_animation(
            [
                (0.0, self.disturbe_scale),
                (0.5, min(self.disturbe_scale + 0.2, 2.0)),
                (1.0, 1.0)
            ], b"disturbeScale", 600, QEasingCurve.OutExpo
        )

        anim_tilt_x = self.make_animation(
            [
                (0.0, 0),
                (0.5, 45),
                (1.0, 0)
            ], b"disturbeTiltX", 800, QEasingCurve.OutExpo
        )

        self.group_animate(
            [
                anim_scale,
                anim_tilt_x
            ]
        )
    
    def start_disturbe_animation(self):
        if not CurrentSettings["floating_window_animations"]:
            return
        
        {
            "bouncy": self.animation_disturbe_bouncy,
            "smooth": self.animation_disturbe_smooth,
            "roll": self.animation_disturbe_roll
        }.get(self.animation_style)()

    def get_window_size(self):
        geometry = self.content_layout.geometry()
        return geometry.width(), geometry.height()

    def start_exit_animation(self):
        if not CurrentSettings["floating_window_animations"]:
            return self._really_close()

        size = self.get_window_size()

        {
            "bouncy": self.animation_close_bouncy,
            "smooth": self.animation_close_smooth,
            "roll": self.animation_close_roll
        }.get(self.animation_style)(size)

    def paintEvent(self, event):
        painter = QPainter(self)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        content_rect = self.background_size or self.content_layout.geometry()
        painter.save()

        if CurrentSettings["floating_window_animations"]:
            transform = QTransform()
            center_point = content_rect.center()

            scale = self.exit_scale * self.bpm_scale * self.disturbe_scale * self.wobble_scale * self.open_scale
            rotation = self.open_rotation + self.exit_rotation + self.random_anim_rotation + self.disturbe_rotation

            transform.translate(center_point.x(), center_point.y())

            if self.enable_tilt:
                transform.rotate(self.current_tilt_y, Qt.YAxis)
                transform.rotate(self.current_tilt_x, Qt.XAxis)
            
            transform.rotate(rotation)
            transform.scale(scale, scale)
            transform.translate(-center_point.x(), -center_point.y())

            painter.setTransform(transform)

        bg_color = QColor(Styles.Colors.secondary_background)
        border_color = QColor(Styles.Colors.glass_border)
        pen = QPen(border_color, 1.5)
        
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(content_rect, 16, 16)

        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(content_rect, 16, 16)

        painter.restore()
        super().paintEvent(event)

    def _really_close(self):
        if CurrentSettings["floating_window_animations"]:
            if self.bpm:
                self.bpm_timer.stop()
        
            if self.enable_tilt:
                self.tilt_animation_timer.stop()
        
        if not self.was_cancelled:
            self.accept()
        
        else:
            self.reject()
    
    def on_ok(self):
        if self.is_closing:
            return

        self.is_closing = True
        self.close_sound()
        self.was_cancelled = False
        self.start_exit_animation()

    def on_cancel(self):
        if self.is_closing:
            return

        self.is_closing = True
        self.close_sound()
        self.was_cancelled = True
        self.start_exit_animation()
    
    def animate_resize(self, target_width, target_height):
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(500)
        anim.setStartValue(self.geometry())
        anim.setEndValue(QRect(self.x(), self.y(), target_width, target_height))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()

        self.anim = anim
    
    def adjustSize(self):
        if self.is_ready:
            size = self.sizeHint()
            self.animate_resize(size.width(), size.height())

        else:
            return super().adjustSize()

class DialogInputWindow(FloatingWindow):
    def __init__(self, title = "Input Dialog", placeholder = "Type something...", min_number = 0, max_number = 100, max_length = 100, input_type = "number", bpm = None, player = None):
        super().__init__(title, bpm, player)
        self.placeholder = placeholder
        self.result_text = None

        button_row = QHBoxLayout()
        self.ok_button = NothingButton("OK")
        self.cancel_button = ButtonWithOutline("Cancel")
        self.input_field = Textbox(min_number, max_number, max_length, input_type)
        
        self.input_field.setFont(Utils.NType(13))
        self.input_field.setPlaceholderText(self.placeholder)
        
        button_row.setSpacing(10)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)

        self.content_layout.addWidget(self.input_field)
        self.content_layout.addLayout(button_row)

        self.ok_button.setAutoDefault(False)
        self.ok_button.setDefault(False)

        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setDefault(False)

        self.ok_button.clicked.connect(self.on_ok)
        self.input_field.returnPressed.connect(self.on_ok)
        self.cancel_button.clicked.connect(self.on_cancel)
        self.ok_button.glitch_started.connect(self.start_disturbe_animation)

    def on_ok(self):
        text = self.input_field.text()
        
        if text is None:
            self.ok_button.start_glitch()
            return

        self.result_text = text
        super().on_ok()

    def get_text(self) -> str:
        return self.input_field.text()

class ExportDialogWindow(FloatingWindow):
    selection_changed = pyqtSignal(str)
    
    def __init__(self, title, composition, bpm = None, player = None):
        super().__init__(title, bpm, player)
        self.composition = composition
        self.original_model = composition.model

        self.number_model = code_to_number_model(composition.model)
        self.choices = PortVariants[composition.model] + [self.number_model]
        
        button_row = QHBoxLayout()
        self.combobox = Selector(self.choices, default_index = -1)
        self.ok_button = NothingButton("Tape it!")
        self.cancel_button = ButtonWithOutline("Later")
        self.all_button = ButtonWithOutline("Export to all models")
        
        self.ok_button.clicked.connect(self.export)
        self.all_button.clicked.connect(self.export_all)
        self.cancel_button.clicked.connect(self.on_cancel)

        button_row.setSpacing(10)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.all_button)
        button_row.addWidget(self.ok_button)

        self.content_layout.addWidget(self.combobox)
        self.content_layout.addLayout(button_row)
    
    def export(self):
        model = self.combobox.currentText()
        self.composition.export(number_model_to_code(model), open_folder = True)
    
    def export_all(self):
        if self.is_closing:
            return

        self.on_ok()
        self.composition.export_all()

class DialogWindow(FloatingWindow):
    def __init__(self, title):
        super().__init__(title)
        self.ok_button = NothingButton("Hell yeah")
        self.cancel_button = ButtonWithOutline("Nah")
        
        self.ok_button.clicked.connect(self.on_ok)
        self.cancel_button.clicked.connect(self.on_cancel)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)
        self.content_layout.addLayout(button_row)

class SegmentEditor(FloatingWindow):
    def __init__(self, title, bpm = None, player = None, segment_num = None, defaults = None):
        super().__init__(title, bpm, player)
        self.ok_button = NothingButton("Apply!")
        self.cancel_button = ButtonWithOutline("Nah")

        self.enable_all = ButtonWithOutlineSlim("Enable all")
        self.disable_all = ButtonWithOutlineSlim("Disable all")
        self.zebra_effect = ButtonWithOutlineSlim("Zebra")

        self.segmented_bar = SegmentedBar(segment_num, defaults)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        upper_button_row = QHBoxLayout()
        upper_button_row.setSpacing(10)

        for widget in [self.enable_all, self.disable_all, self.zebra_effect]:
            upper_button_row.addWidget(widget)
        
        for widget in [self.cancel_button, self.ok_button]:
            button_row.addWidget(widget)

        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.on_cancel)

        self.enable_all.clicked.connect(self.segmented_bar.enable_all)
        self.disable_all.clicked.connect(self.segmented_bar.disable_all)
        self.zebra_effect.clicked.connect(self.segmented_bar.zebra)
        
        self.content_layout.addWidget(self.segmented_bar)
        self.content_layout.addLayout(upper_button_row)
        self.content_layout.addLayout(button_row)

        self.segmented_bar.segment_changed.connect(self.wobble)

    def accept_callback(self):
        self.saved_segments = self.segments()
        super().on_ok()
    
    def segments(self):
        return self.segmented_bar.active

class ErrorWindow(FloatingWindow):
    def __init__(self, title, description, button_text = "Cool", bpm = None, player = None):
        super().__init__(title, bpm, player)
        self.ok_button = NothingButton(button_text)

        self.description_label = QLabel(description)
        self.description_label.setFont(Utils.NType(12))
        self.description_label.setStyleSheet(Styles.Other.second_font)
        self.description_label.setContentsMargins(0, 0, 0, 5)
        self.description_label.setWordWrap(True)

        self.ok_button.clicked.connect(self.on_ok)
        
        self.content_layout.addWidget(self.description_label)
        self.content_layout.addWidget(self.ok_button)

        self.adjustSize()

class About(FloatingWindow):
    def __init__(self, bpm = None, player = None):
        super().__init__(f"Cassette {open('version').read()} by chips047", bpm, player, 16)

        self.about_label = QLabel()
        text = f"The best open-source compositor. Currently in active development!\n\n`Inspirations and credits`\n- Most UI sounds from `R.E.P.O.` game by `semiwork`.\n- UI Open sound from `The Upturned` game by `Zeekers`."
        text = re.sub(r'`([^`]*)`', r'<span style="color:white;">\1</span>', text)
        text = text.replace("\n", "<br>")
        self.about_label.setTextFormat(Qt.RichText)
        self.about_label.setText(text)
        
        self.about_label.setFont(Utils.NType(12))
        self.about_label.setTextFormat(Qt.RichText)
        self.about_label.setMaximumWidth(500)
        self.about_label.setStyleSheet(Styles.Other.second_font)
        self.about_label.setWordWrap(True)

        self.image_pixmap = QPixmap("System/Media/Version.png").scaled(500, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label = QLabel()
        self.image_label.setPixmap(self.image_pixmap)

        self.ok_button = NothingButton("Five Stars?")
        self.ok_button.clicked.connect(self.on_ok)

        self.github_button = ButtonWithOutline("Check for updates on GitHub")
        self.github_button.clicked.connect(self.on_github)

        self.content_layout.addWidget(self.about_label)
        self.content_layout.addWidget(self.image_label)
        self.content_layout.addWidget(self.github_button)
        self.content_layout.addWidget(self.ok_button)

        self.adjustSize()
    
    def on_github(self):
        github = "https://www.github.com/Chipik0/Cassette/releases/latest"
        if random.random() < 0.95:
            webbrowser.open(github)
        
        else:
            fomx = Utils.get_fox_image()

            if fomx:
                webbrowser.open(fomx)

            else:
                webbrowser.open(github)

class Settings(FloatingWindow):
    def __init__(self):
        super().__init__("Settings", max_tilt_angle = 10)
        self.settings = QSettings("chips047", "Cassette")

        self.title_label.setFont(Utils.NType(30))
        self.nav_widget = QWidget()
        self.nav_widget.setFixedHeight(50)
        self.nav_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {Styles.Colors.third_background};
                border-radius: 23px;
            }}
        """)

        self.nav_layout = QHBoxLayout(self.nav_widget)
        self.nav_layout.setContentsMargins(5, 5, 5, 5)
        self.nav_layout.setSpacing(8)
        self.nav_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.content_layout.addWidget(self.nav_widget)

        self.stacked_widget = QStackedWidget()
        self.content_layout.addWidget(self.stacked_widget)

        self.ok_button = NothingButton("Apply!")
        self.cancel_button = ButtonWithOutline("What")
        
        self.button_row = QHBoxLayout()
        self.button_row.setSpacing(10)
        self.button_row.addWidget(self.cancel_button)
        self.button_row.addWidget(self.ok_button)
        self.content_layout.addLayout(self.button_row)
        
        self.nav_buttons = []
        self.pages = {}
        self.controls = {}

        self.ok_button.pressed.connect(self.apply_and_close)
        self.cancel_button.pressed.connect(self.on_cancel)
    
    def change_page(self, page_widget):
        self.stacked_widget.setCurrentWidget(page_widget)
        for button, widget in self.pages.values():
            button.setActive(widget == page_widget)

    def init_settings(self, setting_components):
        first_page_widget = None

        for page_name, components in setting_components.items():
            page_widget = QWidget()
            page_layout = QVBoxLayout(page_widget)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(15)
            page_layout.setAlignment(Qt.AlignTop)

            nav_btn = NavButton(page_name)
            nav_btn.clicked.connect(lambda _, w=page_widget: self.change_page(w))
            self.nav_layout.addWidget(nav_btn)
            self.nav_buttons.append(nav_btn)

            self.pages[page_name] = (nav_btn, page_widget)
            if first_page_widget is None:
                first_page_widget = page_widget

            for element_params in components:
                widget = None
                element_type = element_params["type"]
                saved_value = self.settings.value(element_params["key"])

                if element_type == "checkbox":
                    widget = CheckboxWithLabel(
                        element_params["title"],
                        element_params["description"],
                        saved_value.lower() == "true" if saved_value is not None
                        else element_params["default"]
                    )

                elif element_type == "textbox":
                    widget = TextboxWithLabel(
                        element_params["title"],
                        element_params["min"],
                        element_params["max"],
                        saved_value or element_params["default"]
                    )

                elif element_type == "slider":
                    widget = SliderWithLabel(
                        element_params["title"],
                        element_params["min"],
                        element_params["max"],
                        int(saved_value) or element_params["default"]
                    )

                elif element_type == "selector":
                    widget = SelectorWithLabel(
                        element_params["title"],
                        element_params["map"],
                        default_text = element_params["default"] if saved_value is None else None,
                        default_value = saved_value
                    )
                
                if widget:
                    self.controls[element_params["key"]] = widget
                    page_layout.addWidget(widget)

            self.stacked_widget.addWidget(page_widget)

        self.change_page(first_page_widget)

    def save_settings(self):
        for key, widget in self.controls.items():
            value = None

            if isinstance(widget, CheckboxWithLabel):
                value = widget.isChecked()
            
            elif isinstance(widget, SliderWithLabel):
                value = widget.value()
            
            elif isinstance(widget, SelectorWithLabel):
                value = widget.currentData()
            
            elif isinstance(widget, TextboxWithLabel):
                value = widget.getValueAsText()

            if value is not None:
                self.settings.setValue(key, value)
        
        self.settings.sync()
        load_settings()

    def apply_and_close(self):
        self.save_settings()
        super().on_ok()

class GlitchLabel(QWidget):
    def __init__(self, text="Cassette", parent=None):
        super().__init__(parent)
        self.text = text
        self._opacity = 1.0

        self.font = Utils.NType(25)
        self.setMinimumHeight(60)

        self.glitch_active = False
        self.glitch_start = 0.0
        self.glitch_duration = 0.0
        self.slice_params = []
        self.color_split = True

        self.noise_timer = QTimer(self)
        self.noise_timer.setInterval(300)
        self.noise_timer.timeout.connect(self._maybe_trigger_glitch)

        self.active_timer = QTimer(self)
        self.active_timer.setInterval(30)
        self.active_timer.timeout.connect(self.update)

    @pyqtProperty(float) # type: ignore
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, v: float):
        v = max(0.0, min(1.0, float(v)))
        if v != self._opacity:
            self._opacity = v
            self.update()

    def sizeHint(self):
        fm = QFontMetrics(self.font)
        w = fm.horizontalAdvance(self.text) + 20
        h = fm.height() + 20
        return QSize(w, h)

    def start_noise_loop(self):
        self.noise_timer.start()

    def trigger_glitch(self, duration_ms: int = 250):
        self.glitch_active = True
        self.glitch_start = time.time()
        self.glitch_duration = max(20, duration_ms) / 1000.0
        self._generate_slices()

        if not self.active_timer.isActive():
            self.active_timer.start()

        self.update()

    def _maybe_trigger_glitch(self):
        if random.random() < 0.5:
            self.font = random.choice([Utils.NDot(25), Utils.NType(25)])
            self.trigger_glitch(150)

    def _generate_slices(self):
        self.slice_params.clear()
        total_h = self.height()
        slices = random.randint(2, 6)

        for _ in range(slices):
            h = random.randint(max(6, total_h // 20), max(10, total_h // 6))
            y = random.randint(0, max(0, total_h - h))
            dx = random.randint(-18, 18)
            color_offset = (random.randint(-6, 6), random.randint(-6, 6))
            self.slice_params.append((y, h, dx, color_offset))

    def paintEvent(self, ev):
        painter = QPainter(self)

        if CurrentSettings["antialiasing"]:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
        
        painter.setFont(self.font)

        rect = self.rect()
        fm = QFontMetrics(self.font)
        text_w = fm.horizontalAdvance(self.text)
        text_h = fm.height()

        x = (rect.width() - text_w) / 2
        y_baseline = (rect.height() + text_h) / 2 - fm.descent()

        painter.setOpacity(self._opacity)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(int(x), int(y_baseline), self.text)

        if self.glitch_active:
            now = time.time()
            progress = min(1.0, (now - self.glitch_start) / max(1e-6, self.glitch_duration))

            global_dx = int(math.sin(now * 60.0) * 2.0 * (1.0 - progress))
            global_dy = int(math.cos(now * 50.0) * 1.0 * (1.0 - progress))

            if random.random() < 0.25:
                self._generate_slices()

            amp = 1.0 - progress
            for (sy, sh, sdx, color_off) in self.slice_params:
                cur_dx = int(sdx * amp) + global_dx
                cur_dy = int(global_dy * amp)

                painter.save()
                painter.setClipRect(0, sy, rect.width(), sh)

                if self.color_split:
                    painter.setOpacity(0.8 * amp)
                    painter.setPen(QColor(255, 50, 50))
                    painter.drawText(int(x + cur_dx + color_off[0]), int(y_baseline + cur_dy + color_off[1]), self.text)

                    painter.setOpacity(0.6 * amp)
                    painter.setPen(QColor(50, 255, 50))
                    painter.drawText(int(x + cur_dx - color_off[0]), int(y_baseline + cur_dy - color_off[1]), self.text)

                    painter.setOpacity(0.9 * amp)
                    painter.setPen(QColor(180, 200, 255))
                    painter.drawText(int(x + cur_dx), int(y_baseline + cur_dy), self.text)
                else:
                    painter.setOpacity(0.9 * amp)
                    painter.setPen(QColor(200, 200, 200))
                    painter.drawText(int(x + cur_dx), int(y_baseline + cur_dy), self.text)

                painter.restore()

            noise_alpha = int(100 * amp)
            if noise_alpha > 6:
                painter.save()
                painter.setOpacity(noise_alpha / 255.0)
                stripe_h = 2

                for yy in range(0, rect.height(), stripe_h * 3):
                    painter.fillRect(0, yy, rect.width(), stripe_h, QColor(0, 0, 0, noise_alpha))
                
                painter.restore()

            if progress >= 1.0:
                self.glitch_active = False
                self.slice_params.clear()
                self.active_timer.stop()

class ContextMenu(QMenu):
    def __init__(self, entries):
        super().__init__()
        self.setStyleSheet(Styles.Menus.RMB_element)

        self._style_menu(self)
        self._populate(self, entries)

    def _style_menu(self, menu: QMenu):
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        menu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)

    def _populate(self, menu: QMenu, entries):
        for label, handler in entries:
            if label == "-":
                menu.addSeparator()
                continue

            if isinstance(handler, list):
                sub = menu.addMenu(label)
                self._style_menu(sub)
                self._populate(sub, handler)
                continue

            if isinstance(handler, QWidget):
                wa = QWidgetAction(menu)
                wa.setDefaultWidget(handler)
                menu.addAction(wa)
                continue

            if callable(handler):
                act = QAction(label, menu)
                act.triggered.connect(handler)
                menu.addAction(act)
                continue

            act = QAction(label, menu)
            act.setEnabled(False)
            menu.addAction(act)

    def exec_and_cleanup(self, global_pos):
        try:
            self.exec(global_pos)
        
        finally:
            self.deleteLater()

class ADBTutorial(FloatingWindow):
    def __init__(self, bpm, playback_manager):
        super().__init__("Cassette Receiver Tutorial", bpm, playback_manager, 10, "official")
        self.playback_manager = playback_manager

        self.playback_manager.enable_midpass(center_hz = 500)

class Tutorial(FloatingWindow):
    def __init__(self, bpm, audiofile_path):
        self.playback_manager = Player.PlaybackManager()
        self.playback_manager.load_audio(audiofile_path)

        super().__init__(
            "Tutorial",
            bpm,
            self.playback_manager,
            10,
            "official",
            enable_transition_audio_effects = False
        )

        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        self.text_label.setFont(Utils.NType(12))
        self.text_label.setStyleSheet(Styles.Other.second_font)
        self.text_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.text_label.setMinimumWidth(400)

        self.next_button = NothingButton("Next?")
        self.next_button.clicked.connect(self.next_button_callback)

        self.content_layout.addWidget(self.text_label)
        self.content_layout.addWidget(self.next_button)

        self.set_bpm_start_size(1.02)

        if self.playback_manager.duration_ms > 10000:
            self.playback_manager.set_volume(0.5)
            self.playback_manager.enable_midpass(duration = 1.0)
            self.playback_manager.enable_bitcrush(6, 8, duration = 3.0)
            self.playback_manager.tape(start_speed = 0, end_speed = 0.9, duration = 3.0)

        self.stage = 0

        self.data = {
            0: {
                "label": "Welcome to Cassette",
                "text": "Explore this small tutorial to get started."
            },
            1: {
                "label": "Basics",
                "text": "`Space` to play / pause.\n`1, 2, 3, 4, 5, 6, 7, 8, 9, 0, Minus` to place a glyph. `Del` to delete it."
            },
            2: {
                "label": "Basics - Mouse",
                "text": "`Right Mouse Button` to open context menu. `Grab` the side of glyph to resize it. `Hold` to move it. `Press` on waveform to set playback position."
            },
            3: {
                "label": "Basics - Scroll",
                "text": "Use `Shift + Wheel` to scroll vertically. Use `Wheel` to scroll horizontally."
            },
            4: {
                "label": "Basics - Navigation",
                "text": "Click `Eject` to go back to the main menu."
            },
            5: {
                "label": "Effects - Mixing",
                "text": "You can combine effects! Place glyphs on top of each other with different effects."
            },
            6: {
                "label": "Shall we?",
                "text": "Now, try yourself in glyphtones creation."
            }
        }

        self.make_page()
    
    def make_page(self):
        page_data = self.data.get(self.stage)

        if not page_data:
            return

        colored_text = re.sub(r'`([^`]*)`', r'<span style="color:white;">\1</span>', page_data["text"])

        self.title_label.setText(page_data["label"])
        self.text_label.setText(colored_text)

        QTimer.singleShot(0, self.adjustSize)
    
    def next_button_callback(self):
        self.stage += 1
        self.random_rotate_anim()

        self.make_page()
        self.sound_effect_roll()

        if self.stage == 5:
            self.on_ok()
    
    def sound_effect_roll(self):
        if self.playback_manager.duration_ms < 10000:
            return

        if self.stage == 1:
            self.playback_manager.set_speed(0.95, duration = 1.0)
            self.playback_manager.disable_bitcrush(2.0)
            self.playback_manager.enable_midpass(700, duration = 2.0)
        
        elif self.stage == 2:
            self.playback_manager.set_speed(1.0, duration = 1.0)
            self.playback_manager.disable_midpass(2.0)
        
        elif self.stage == 3:
            self.set_bpm_start_size(1.04)
            self.playback_manager.set_volume(0.8, duration = 3.0)
        
        elif self.stage == 4:
            self.set_bpm_start_size(1.05)

        elif self.stage == 5:
            self.playback_manager.tape(end_speed = 0.0, duration = 3.0, cleanup_on_finish = True)

class ScheduledSegmentedBar(QWidget):
    segment_changed = pyqtSignal()
    def __init__(
            self,
            segment_number: int = 30,
            base_thickness: int = 20,
            curve: int = 0,
            loop: bool = False
        ):
        
        super().__init__()

        self.setFixedHeight(base_thickness)

        if curve:
            self.setFixedHeight(base_thickness + curve)

        self._main_timer = QTimer(self)
        self._main_timer.timeout.connect(self._tick)
        self._time0 = QElapsedTimer()

        self._end_timer = QTimer(self)
        self._end_timer.setSingleShot(True)
        self._end_timer.timeout.connect(self._on_schedule_end)

        self._schedule = []
        self.segment_number = segment_number
        self._running = False
        self._loop = loop
        self.curve = curve

        self.levels = [0.0] * self.segment_number
        self._blur_strength = 0.75

        self.segment_changed.connect(self.update)
    
    def _tick(self):
        if not self._running:
            return
        
        now = self._time0.elapsed() + self._start_offset
        new_levels = [0.0] * self.segment_number

        for item in self._schedule:
            start, dur, b1 = item["start"], item["duration"], item["brightness"]
            b2 = item.get("end_brightness", None)
            segs = item.get("segments", [i for i in range(self.segment_number)])
            
            if not (start <= now <= start + dur):
                continue
            
            value = b1 if b2 is None else b1 + (b2 - b1) * ((now - start) / dur)
            
            for idx in segs:
                if 0 <= idx < self.segment_number:
                    new_levels[idx] = max(new_levels[idx], value)

                    if idx > 0:
                        fade_value = value * (0.8 * self._blur_strength)
                        new_levels[idx - 1] = max(new_levels[idx - 1], fade_value)

                    if idx < self.segment_number - 1:
                        fade_value = value * (0.8 * self._blur_strength)
                        new_levels[idx + 1] = max(new_levels[idx + 1], fade_value)

                    if idx > 1:
                        fade_value = value * (0.4 * self._blur_strength)
                        new_levels[idx - 2] = max(new_levels[idx - 2], fade_value)

                    if idx < self.segment_number - 2:
                        fade_value = value * (0.4 * self._blur_strength)
                        new_levels[idx + 2] = max(new_levels[idx + 2], fade_value)
        
        if new_levels != self.levels:
            self.levels = new_levels
            self.segment_changed.emit()
    
    def _paint(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        max_h = self.height()

        if self.segment_number <= 0 or width <= 0 or max_h <= 0:
            return

        painter.setPen(Qt.NoPen)
        
        curve_amount = self.curve
        
        if curve_amount >= max_h - 2:
            curve_amount = max_h - 2
        
        if curve_amount < 0:
            curve_amount = 0
            
        bar_thickness = max_h - curve_amount
        if bar_thickness <= 0:
            return

        gradient = QLinearGradient(0, 0, width, 0)

        for i in range(self.segment_number):
            position = i / self.segment_number
            color = self._blend_color(QColor("#404040"), QColor("#ffffff"), self.levels[i])
            gradient.setColorAt(position, color)

            if i < self.segment_number - 1:
                mid_position = (i + 0.5) / self.segment_number
                mid_level = (self.levels[i] + self.levels[i + 1]) / 2.0
                mid_color = self._blend_color(QColor("#404040"), QColor("#ffffff"), mid_level)
                gradient.setColorAt(mid_position, mid_color)

        last_color = self._blend_color(QColor("#404040"), QColor("#ffffff"), self.levels[-1])
        gradient.setColorAt(1.0, last_color)

        painter.setBrush(gradient)
        path = QPainterPath()

        radius = min(10, bar_thickness / 2) 

        if not self.curve:
            rect = QRectF(0, 0, width, max_h)
            path.addRoundedRect(rect, radius, radius)
        
        else:
            path.moveTo(radius, curve_amount)

            path.quadTo(width / 2, 0, width - radius, curve_amount)
            path.quadTo(width, curve_amount + radius / 2, width, curve_amount + radius)
            path.lineTo(width, max_h - radius)

            path.quadTo(width, max_h, width - radius, max_h)
            path.quadTo(width / 2, max_h - curve_amount, radius, max_h)
            path.quadTo(0, max_h, 0, max_h - radius)
            path.lineTo(0, curve_amount + radius)

            path.quadTo(0, curve_amount + radius / 2, radius, curve_amount)
            path.closeSubpath()
            
        painter.drawPath(path)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        self._paint(painter)
    
    def _blend_color(self, off: QColor, on: QColor, level: float) -> QColor:
        t = max(0.0, min(1.0, level / 100.0))
        r = int(off.red() + (on.red() - off.red()) * t)
        g = int(off.green() + (on.green() - off.green()) * t)
        b = int(off.blue() + (on.blue() - off.blue()) * t)

        return QColor(r, g, b)

    def play(self, start_offset_ms: int = 0):
        self.stop(clear_levels = False)

        self._running = True
        self._start_offset = start_offset_ms
        self._time0.start()
        self._main_timer.start(10)

        self._schedule_end_timer()

    def stop(self, clear_levels: bool = True):
        self._main_timer.stop()
        self._end_timer.stop()
        self._running = False

        if clear_levels:
            self.levels = [0.0] * self.segment_number
            self.segment_changed.emit()

    def set_schedule(self, schedule):
        self._schedule = schedule or []
        if self._running:
            self._schedule_end_timer()

    def _compute_schedule_end_ms(self) -> int:
        if not self._schedule:
            return 0

        end_ms = 0

        for item in self._schedule:
            s = int(item.get("start", 0))
            d = int(item.get("duration", 0))
            end_ms = max(end_ms, s + d)
        
        return end_ms

    def _schedule_end_timer(self):
        end_ms = self._compute_schedule_end_ms()
        if end_ms <= 0:
            return

        elapsed = self._time0.elapsed() + getattr(self, "_start_offset", 0)
        remaining = end_ms - elapsed

        if remaining <= 0:
            self._on_schedule_end()
        
        else:
            self._end_timer.start(int(remaining))

    def _on_schedule_end(self):
        if self._loop:
            self.play(0)
            return

        self.stop(clear_levels=True)

class MultiBarWidget(QWidget):
    def __init__(self, bars_config: list):
        super().__init__()

        self._bars = []
        self._bars_config = bars_config or []

        self._offset_x = 0
        self._offset_y = 0

        for config in self._bars_config:
            _, _, w, h, _, thickness, segments, curve = self._unpack_config(config)
            
            bar = ScheduledSegmentedBar(
                segments,
                thickness,
                curve
            )
            
            bar.setParent(self)
            bar.setFixedWidth(w)
            bar.setFixedHeight(h)
            bar.hide()

            self._bars.append(bar)

        self._update_widget_size()
    
    def _unpack_config(self, config):
        return (
            config["x"],
            config["y"],
            
            config["width"],
            config.get(
                "height",
                config["base_thickness"] + config.get("curve", 0)
            ),
            
            config["rotation"],
            config["base_thickness"],
            config["segment_number"],
            
            config.get("curve", 0),
        )

    def _calculate_bounding_rect(self, x, y, width, height, rotation):
        cx, cy = width / 2.0, height / 2.0
        corners = [
            QPointF(-cx, -cy),
            QPointF(cx, -cy),
            QPointF(cx, cy),
            QPointF(-cx, cy)
        ]

        transform = QTransform()
        
        transform.translate(x, y)
        transform.rotate(rotation)

        transformed = [transform.map(c) for c in corners]
        xs = [p.x() for p in transformed]
        ys = [p.y() for p in transformed]

        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def _update_widget_size(self):
        rects = []
        for i, config in enumerate(self._bars_config):
            x, y, w, h, rotation, _, _, _ = self._unpack_config(config)
            rect = self._calculate_bounding_rect(x, y, w, h, rotation)
            rects.append(rect)

        min_x = min(r.left() for r in rects)
        max_x = max(r.right() for r in rects)
        min_y = min(r.top() for r in rects)
        max_y = max(r.bottom() for r in rects)

        total_width = int(max_x - min_x)
        total_height = int(max_y - min_y)

        self._offset_x = -min_x
        self._offset_y = -min_y

        self.setFixedSize(total_width, total_height)
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.save()
        painter.translate(self._offset_x, self._offset_y)

        for bar, config in zip(self._bars, self._bars_config):
            x, y, w, h, rotation, _, _, _ = self._unpack_config(config)

            painter.save()
            
            painter.translate(x, y)
            painter.rotate(rotation)
            painter.translate(-w / 2.0, -h / 2.0)

            bar._paint(painter)

            painter.restore()

        painter.restore()
    
    def set_bar_schedule(self, index: int, schedule: list):
        if 0 <= index < len(self._bars):
            self._bars[index].set_schedule(schedule)

    def play_all(self, start_offset_ms: int = 0):
        for bar in self._bars:
            bar.play(start_offset_ms)
            bar.segment_changed.connect(self.update)

    def stop_all(self, clear_levels: bool = True):
        for bar in self._bars:
            bar.stop(clear_levels)

class TestWindow(FloatingWindow):
    def __init__(self):
        super().__init__("Bruuh")

        bars_config = [
            {
                "x": 0,
                "y": 75,
                "width": 150,
                "rotation": -45,
                "segment_number": 20,
                "base_thickness": 15,
                "curve": 40,
                "loop": True
            },
            {
                "x": 215,
                "y": 165,
                "width": 150,
                "rotation": 90,
                "segment_number": 12,
                "base_thickness": 15,
                "curve": 40,
                "loop": True
            },
            {
                "x": 0,
                "y": 250,
                "width": 60,
                "rotation": 45,
                "segment_number": 5,
                "base_thickness": 15,
                "curve": 0,
                "loop": True
            }
        ]

        widget = MultiBarWidget(bars_config)

        # Устанавливаем schedules для каждого бара
        widget.set_bar_schedule(0, [
            {"start": 0, "duration": 2000, "brightness": 0, "end_brightness": 100, 
             "segments": list(range(30))}
        ])

        widget.set_bar_schedule(1, [
            {"start": 500, "duration": 2000, "brightness": 0, "end_brightness": 100, 
             "segments": list(range(25))}
        ])

        widget.set_bar_schedule(2, [
            {"start": 1000, "duration": 2000, "brightness": 0, "end_brightness": 100, 
             "segments": list(range(20))}
        ])
        
        self.content_layout.addWidget(widget)
        widget.play_all()