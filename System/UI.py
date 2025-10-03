import re
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
            if not CurrentSettings["reduce_animations"]:
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

        selector_container = QWidget(self)
        selector_container.setStyleSheet(Styles.Controls.Selector2)
        selector_layout = QHBoxLayout(selector_container)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(5)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked.connect(self._on_button_clicked)

        for idx, text in enumerate(items):
            btn = QPushButton(text, objectName="segmentedButton", parent=selector_container)
            btn.setFont(Utils.NType(14))
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.setCursor(Qt.PointingHandCursor)
            selector_layout.addWidget(btn)
            self._group.addButton(btn, id=idx)

        if self._group.buttons():
            self._group.buttons()[default_index].setChecked(True)

        main_layout.addWidget(selector_container)

    def _on_button_clicked(self, button):
        text = button.text()
        self.selection_changed.emit(id, text)

    def currentIndex(self) -> int:
        return self._group.checkedId()
    
    def setCurrentIndex(self, index) -> int:
        for i, button in enumerate(self._group.buttons()):
            if i == index:
                button.setChecked(True)
                continue
            
            button.setChecked(False)

    def currentText(self) -> str:
        btn = self._group.checkedButton()
        return btn.text() if btn else ""

class SelectorWithLabel(QWidget):
    selection_changed = pyqtSignal(int, str, object)  # index, text, key

    def __init__(
        self,
        description: str,
        items,
        *,
        parent=None,
        default: int = None
    ):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setFixedHeight(90)

        self._keys = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)

        self.container_background = QWidget(self)
        self.container_background.setObjectName("backgroundContainer")
        self.container_background.setStyleSheet(Styles.Controls.Selector)

        inner_layout = QVBoxLayout(self.container_background)
        inner_layout.setContentsMargins(15, 10, 15, 15)
        inner_layout.setSpacing(10)

        self.description_label = QLabel(description, self.container_background)
        self.description_label.setFont(Utils.NType(14))
        self.description_label.setStyleSheet(Styles.Other.label)
        inner_layout.addWidget(self.description_label)

        selector_container = QWidget(self.container_background)
        selector_container.setStyleSheet(f"QWidget {{border-radius: 10px}}")
        selector_layout = QHBoxLayout(selector_container)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(5)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked[int].connect(self._on_button_clicked)

        if isinstance(items, dict):
            iterable = list(items.items())
            for idx, (key, text) in enumerate(iterable):
                btn = QPushButton(key, parent=selector_container, objectName="segmentedButton")
                btn.setFont(Utils.NType(11))
                btn.setCheckable(True)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                btn.setCursor(Qt.PointingHandCursor)
                selector_layout.addWidget(btn)
                self._group.addButton(btn, id=idx)
                self._keys[idx] = text
        
        else:
            for idx, text in enumerate(items):
                btn = QPushButton(text, parent=selector_container, objectName="segmentedButton")
                btn.setFont(Utils.NType(11))
                btn.setCheckable(True)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                btn.setCursor(Qt.PointingHandCursor)
                selector_layout.addWidget(btn)
                self._group.addButton(btn, id=idx)
                self._keys[idx] = text

        if default is not None and 0 <= default < len(self._group.buttons()):
            self._group.buttons()[default].setChecked(True)
        else:
            self._group.buttons()[0].setChecked(True)

        inner_layout.addWidget(selector_container)
        main_layout.addWidget(self.container_background)

    def _on_button_clicked(self, id: int):
        text = self._group.button(id).text()
        key = self._keys[id]
        button_number = len(self._group.buttons())
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

    def setCurrentText(self, text):
        for button in self._group.buttons():
            if button.text() == text:
                button.setChecked(True)
            else:
                button.setChecked(False)

    def setCurrentIndex(self, index):
        for i, button in enumerate(self._group.buttons()):
            button.setChecked(i == index)

    def setCurrentData(self, key):
        for idx, k in self._keys.items():
            print(f"Comparing {k} with {key}")
            if str(k) == str(key):
                self._group.button(idx).setChecked(True)
                break

class Checkbox(QCheckBox):
    def __init__(self, name, parent):
        super().__init__(name, parent)

        self.setFont(Utils.NType(13))
        self.setStyleSheet(Styles.Controls.Checkbox)
    
    def nextCheckState(self):
        super().nextCheckState()

        tone = 1.0 if self.isChecked() else 0.9
        Utils.ui_sound("Toggle", tone)

class CheckboxWithLabel(QWidget):
    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setMaximumHeight(75)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.title = title

        self.container_background = QWidget(self)
        self.container_background.setStyleSheet(Styles.Controls.SliderBackground)

        inner_layout = QHBoxLayout(self.container_background)
        inner_layout.setContentsMargins(15, 10, 15, 10)
        inner_layout.setSpacing(10)

        self.checkbox = Checkbox(self.title, self.container_background)
        inner_layout.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignVCenter)

        self.description_label = QLabel(description, self.container_background)
        self.description_label.setFont(Utils.NType(13))
        self.description_label.setStyleSheet(f"color: {Styles.Colors.subtle_font_color}; padding: 0px;")
        inner_layout.addWidget(self.description_label, 1, Qt.AlignmentFlag.AlignVCenter)

        main_layout.addWidget(self.container_background)

    def isChecked(self):
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool):
        self.checkbox.setChecked(checked)

    def stateChanged(self, func):
        self.checkbox.stateChanged.connect(func)

class SliderWithLabel(QWidget):
    def __init__(self, description: str, min_val: int, max_val: int, default_val: int, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setMaximumHeight(75)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint) 

        self.container_background = QWidget(self)
        self.container_background.setStyleSheet(Styles.Controls.SliderBackground)

        inner_layout = QVBoxLayout(self.container_background)
        inner_layout.setContentsMargins(15, 10, 15, 5)
        inner_layout.setSpacing(5)

        self.description_label = QLabel(description)
        self.description_label.setFont(Utils.NType(14))
        self.description_label.setStyleSheet("color: #ddd; padding: 0px;")
        inner_layout.addWidget(self.description_label)

        slider_value_layout = QHBoxLayout()
        slider_value_layout.setContentsMargins(0, 0, 0, 0)
        slider_value_layout.setSpacing(15)

        self.slider = QSlider(Qt.Orientation.Horizontal, self.container_background)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default_val)
        self.slider.setStyleSheet(Styles.Controls.Slider)

        slider_value_layout.addWidget(self.slider, 1)

        self.value_label = QLabel(str(default_val))
        self.value_label.setFont(Utils.NType(12))
        self.value_label.setStyleSheet("color: #dddddd; padding: 0px;")
        
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        slider_value_layout.addWidget(self.value_label, 0) 
        inner_layout.addLayout(slider_value_layout)
        main_layout.addWidget(self.container_background)

        self.slider.valueChanged.connect(self._update_value_label)

    def _update_value_label(self, value):
        self.value_label.setText(str(value))
        self.value_label.adjustSize()

        if self.slider.maximum() < 20:
            tone = (value - self.slider.minimum()) / (self.slider.maximum() - self.slider.minimum()) + 0.1
            Utils.ui_sound("Toggle2", tone)

    def value(self):
        return self.slider.value()

    def setValue(self, val):
        self.slider.setValue(val)

class _BaseControlWidget(QWidget):
    def __init__(self, icon=None, static_label_text=None, parent=None):
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
        font = Utils.NDot(13)
        self.value_label.setFont(font)
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
        Utils.ui_sound("Toggle", 1.0)
        self.segment_changed.emit()
    
    def disable_all(self):
        self.active = [False] * self.segment_number
        Utils.ui_sound("Toggle", 0.7)
        self.segment_changed.emit()
    
    def zebra(self):
        self.active = [i % 2 == 0 for i in range(self.segment_number)]
        Utils.ui_sound("Toggle3")
        self.segment_changed.emit()

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

    def show_state(self):
        display_text_part, value = self.states[self.current_state_index]
        self.value_label.setText(display_text_part)
        self.state_changed.emit(display_text_part, value)

    def reset(self):
        self.current_state_index = 0
        self.show_state()

    def get_current_value(self):
        return self.states[self.current_state_index][1]

class EffectPreviewWidget(QWidget):
    apply_requested = pyqtSignal(str, dict)

    def __init__(self, effect_name, config, parent=None):
        super().__init__(parent)
        self.effect_name = effect_name
        self.config = config
        self.controls = {}

        self.setFixedWidth(480)
        self.setStyleSheet(Styles.Controls.EffectSetupper)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        self.gif_label = QLabel(self)
        self.gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.movie = QMovie(config["gif"])
        self.movie.setScaledSize(QSize(460, 345))
        self.gif_label.setMovie(self.movie)
        self.movie.start()
        layout.addWidget(self.gif_label)

        self.configuration = GlyphEffects.EffectsConfig[self.effect_name]
        for i, element in enumerate(self.configuration["settings"].keys()):
            if element.startswith("checkbox"):
                widget = Checkbox(self.configuration["settings"][f"checkbox{i + 1}"]["title"], self)
                widget.setChecked(self.configuration["settings"][f"checkbox{i + 1}"]["default"])
                
                self.controls[element] = widget
                layout.addWidget(widget)

            if element.startswith("slider"):
                widget = SliderWithLabel(
                    description=self.configuration["settings"][f"slider{i + 1}"]["title"],
                    min_val=self.configuration["settings"][f"slider{i + 1}"]["min"],
                    max_val=self.configuration["settings"][f"slider{i + 1}"]["max"],
                    default_val=self.configuration["settings"][f"slider{i + 1}"]["max"]
                )

                self.controls[element] = widget
                layout.addWidget(widget)

            if element.startswith("selector"):
                widget = SelectorWithLabel(
                    self.configuration["settings"][f"selector{i + 1}"]["title"],
                    self.configuration["settings"][f"selector{i + 1}"]["choices"]
                )

                self.controls[element] = widget
                layout.addWidget(widget)

        layout.addStretch()

        self.apply_button = NothingButton("Apply")
        self.apply_button.clicked.connect(self.on_apply)

        layout.addWidget(self.apply_button)

    def get_settings(self):
        settings = {}
        for key, widget in self.controls.items():
            if isinstance(widget, QCheckBox):
                settings[key] = widget.isChecked()
            
            elif isinstance(widget, SliderWithLabel):
                settings[key] = widget.value()
            
            elif isinstance(widget, SelectorWithLabel):
                settings[key] = widget.currentText()
        
        settings["segmented"] = GlyphEffects.EffectsConfig[self.effect_name]["segmented"]
        return settings

    def on_apply(self):
        self.apply_button.setText("Applied")
        self.apply_button.setStyleSheet(Styles.Buttons.normal_button_with_border)
        current_settings = self.get_settings()

        self.apply_requested.emit(self.effect_name, current_settings)
    
    def mousePressEvent(self, event):
        event.accept()

class AnimatedTooltipManager(QWidget):
    def __init__(self, parent, delay_ms: int = 1000):
        
        super().__init__(parent, Qt.ToolTip)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._margin = 30
        self._radius = 18
        
        self.label = QLabel(self)
        self.label.setStyleSheet("background: transparent; color: white;")
        self.label.setFont(Utils.NType(11))
        self.label.setAlignment(Qt.AlignVCenter)
        self.label.setContentsMargins(15, 0, 0, 0)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        
        self.anim_opacity = QPropertyAnimation(self._opacity_effect, b"opacity")
        self.anim_opacity.finished.connect(self._on_hide_finished)

        self._hiding = False
        self._bg_color = QColor(Styles.Colors.Floating.background)
        self._border_color = QColor(Styles.Colors.glass_border)

        self.delay_ms = delay_ms
        self.tooltip_delay_timer = QTimer(self)
        self.tooltip_delay_timer.setSingleShot(True)
        self.tooltip_delay_timer.timeout.connect(self._show_pending_tooltip)

        self._tooltip_pending_element = None
        self._tooltip_pending_text = None
        self._tooltip_current_element = None

    def request_tooltip(self, element, text: str):
        if (
                self._tooltip_pending_element != element or 
                self._tooltip_pending_text != text or
                not self.tooltip_delay_timer.isActive()
            ):

            print("Well")

            self.hide_tooltip()
            self.tooltip_delay_timer.stop()
            self._tooltip_pending_element = element
            self._tooltip_pending_text = text
            self.tooltip_delay_timer.start(self.delay_ms)

    def clear_tooltip(self):
        self._tooltip_pending_element = None
        self.tooltip_delay_timer.stop()
        if self.is_tooltip_visible():
            self.hide_tooltip()

    def is_tooltip_visible(self) -> bool:
        return self.isVisible() and self._opacity_effect.opacity() > 0

    def _show_pending_tooltip(self):
        if not self._tooltip_pending_element:
            return
        
        self._tooltip_current_element = self._tooltip_pending_element
        self.show_tooltip(self._tooltip_pending_text)

    def _calculate_position(self, tip_size: QSize) -> QPoint:
        parent_rect = self.parent().rect()

        x = parent_rect.right() - tip_size.width() - self._margin
        y = parent_rect.bottom() - tip_size.height() - self._margin
        
        return self.parent().mapToGlobal(QPoint(x, y))

    def show_tooltip(self, text: str):
        self._hiding = False
        self.anim_opacity.stop()

        self.label.setText(text)
        
        final_size = self.label.sizeHint().grownBy(QMargins(15, 15, 0, 15))
        pos = self._calculate_position(final_size)
        
        self.setGeometry(QRect(pos, final_size))

        if not CurrentSettings["reduce_animations"]:
            self._opacity_effect.setOpacity(0.0)
            self.show()

            self.anim_opacity.setDuration(300)
            self.anim_opacity.setStartValue(0.0)
            self.anim_opacity.setEndValue(1.0)
            self.anim_opacity.setEasingCurve(QEasingCurve.OutCubic)
            self.anim_opacity.start()
        
        else:
            self._opacity_effect.setOpacity(1.0)
            self.show()

    def hide_tooltip(self):
        if not self.is_tooltip_visible() or self._hiding:
            return
            
        self._hiding = True
        self.anim_opacity.stop()
        
        if not CurrentSettings["reduce_animations"]:
            self.anim_opacity.setDuration(300)
            self.anim_opacity.setStartValue(self._opacity_effect.opacity())
            self.anim_opacity.setEndValue(0.0)
            self.anim_opacity.setEasingCurve(QEasingCurve.InCubic)
            self.anim_opacity.start()
        
        else:
            self._on_hide_finished()

    def _on_hide_finished(self):
        if self._hiding:
            self._hiding = False
            self.hide()
            self._tooltip_current_element = None

    def resizeEvent(self, event):
        self.label.setGeometry(self.rect())
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)

        painter.setBrush(self._bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self._radius, self._radius)

        pen = QPen(self._border_color, 2)

        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, self._radius, self._radius)

class ValuePopup(QWidget):
    def __init__(self, text: str, pos: QPoint, parent=None):
        super().__init__(parent)
        self.parent_ref = parent

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)

        self.padding = 10
        self.label = QLabel("", self)
        self.label.setFont(Utils.NType(12))
        self.label.setStyleSheet("color: white; background: transparent;")
        self.label.move(self.padding, self.padding)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        # Animations
        self.move_anim = QPropertyAnimation(self, b"pos", self)
        self.move_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.size_anim = QPropertyAnimation(self, b"size", self)
        self.size_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._start_hide_animation)

        self._is_visible = False

        self.show_text(text, pos)

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
        label_size = self.label.size()

        full_width = label_size.width() + self.padding * 2
        full_height = label_size.height() + self.padding * 2
        target_size = QSize(full_width, full_height)

        if not self.isVisible():  
            self.resize(target_size)
        
        else:
            if not CurrentSettings["reduce_animations"]:
                self.size_anim.stop()
                self.size_anim.setDuration(200)
                self.size_anim.setStartValue(self.size())
                self.size_anim.setEndValue(QSize(full_width, self.height()))
                self.size_anim.start()
            
            else:
                self.setFixedSize(QSize(full_width, self.height()))

        self.label.move(self.padding, self.padding)

    def _compute_top_left(self, global_pos: QPoint):
        margin = 30
        w = self.width()
        h = self.height()

        parent_top_left = self.parent_ref.mapToGlobal(QPoint(0, 0))
        parent_rect = QRect(parent_top_left, self.parent_ref.size())

        desired_x = global_pos.x() - w // 2
        desired_y = global_pos.y() + 15

        min_x = parent_rect.left() + margin
        max_x = parent_rect.right() - w - margin

        if max_x < min_x:
            x = min_x
        else:
            x = max(min_x, min(desired_x, max_x))

        return QPoint(x, desired_y)

    def show_text(self, text: str, pos: QPoint):
        self._layout_for_text(text)
        target = self._compute_top_left(pos)

        if not self.isVisible():
            start_pos = QPoint(target.x() - 20, target.y())
        
        else:
            current_pos = self.pos()
            if current_pos == QPoint(0, 0):
                start_pos = QPoint(target.x() - 20, target.y())
            else:
                start_pos = current_pos

        if not CurrentSettings["reduce_animations"]:
            self.move_anim.stop()
            self.move_anim.setDuration(VALUE_POPUP_IN)
            self.move_anim.setStartValue(start_pos)
            self.move_anim.setEndValue(target)
            self.move_anim.start()
        
        else:
            self.move(target)

        self.opacity_anim.stop()
        self.opacity_effect.setOpacity(1.0)

        self.show()
        self.raise_()
        self._is_visible = True

        self.hide_timer.start(800)

    def _start_hide_animation(self):
        if not self._is_visible:
            return

        self._is_visible = False

        if not CurrentSettings["reduce_animations"]:
            start_op = self.opacity_effect.opacity()

            self.opacity_anim.stop()

            self.opacity_anim.setDuration(200)
            self.opacity_anim.setStartValue(start_op)
            self.opacity_anim.setEndValue(0.0)

            self.opacity_anim.finished.connect(self.deleteLater)
            self.opacity_anim.start()
        
        else:
            self.opacity_effect.setOpacity(0.0)
            self.deleteLater()

    def closeEvent(self, event):
        self.hide_timer.stop()
        self.move_anim.stop()
        self.opacity_anim.stop()

        super().closeEvent(event)

class MiniWaveformPreview(QWidget):
    preview_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_data = None
        self.peaks = []
        self.setFixedHeight(Styles.Metrics.element_height)
        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_audio_data(self, audio_data):
        self.audio_data = audio_data
        self.generate_peaks()
        self.update()

    def generate_peaks(self):
        if self.audio_data is None or len(self.audio_data) == 0 or self.width() <=0:
            self.peaks = []
            return
        
        self.audio_data = self.audio_data - np.mean(self.audio_data)
        self.audio_data = self.audio_data / np.max(np.abs(self.audio_data))

        num_peaks = self.width()

        if len(self.audio_data) == 0:
            self.peaks = []
            return

        samples_per_peak = max(1, len(self.audio_data) // num_peaks)
        temp_peaks = []
        
        for i in range(0, len(self.audio_data), samples_per_peak):
            chunk = self.audio_data[i:i + samples_per_peak]
            if len(chunk) > 0:
                temp_peaks.append((np.min(chunk), np.max(chunk)))
            
            elif i == 0: 
                temp_peaks.append((0,0))
            
        self.peaks = temp_peaks

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        if not self.peaks:
            painter.setPen(Qt.GlobalColor.darkGray)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Mini Preview")
            return

        rect_height = self.height()
        center_y = rect_height / 2.0

        path_upper = QPainterPath()

        current_width = self.width()
        if current_width <= 0 or not self.peaks:
            return

        bar_width = current_width / len(self.peaks) if len(self.peaks) > 0 else 1.0

        for i, (_, max_val) in enumerate(self.peaks):
            x_pos = i * bar_width
            scaled_max = center_y - (max_val * center_y) 
            scaled_max = max(0, min(scaled_max, rect_height))
            if i == 0:
                path_upper.moveTo(x_pos, scaled_max)
            else:
                path_upper.lineTo(x_pos, scaled_max)

        for i in range(len(self.peaks) - 1, -1, -1):
            min_val, _ = self.peaks[i]
            x_pos = i * bar_width
            scaled_min = center_y - (min_val * center_y) 
            scaled_min = max(0, min(scaled_min, rect_height))
            
            if i == len(self.peaks) -1: 
                path_upper.lineTo(x_pos, scaled_min)
            
            else:
                path_upper.lineTo(x_pos, scaled_min)

        if self.peaks:
            path_upper.closeSubpath()
            painter.fillPath(path_upper, QBrush(QColor(*Styles.hex_to_rgb(Styles.Colors.nothing_accent) + (100,)))) 
            painter.setPen(QPen(QColor(*Styles.hex_to_rgb(Styles.Colors.nothing_accent)), 0.5)) 
            painter.drawPath(path_upper)

    def mousePressEvent(self, event: QMouseEvent):
        if self.peaks and event.button() == Qt.MouseButton.LeftButton:
            normalized_pos = max(0.0, min(1.0, event.x() / self.width()))
            self.preview_clicked.emit(normalized_pos)
        
        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.generate_peaks()
        self.update()

class AnimatedLineEdit(QLineEdit):
    safeTextChanged = pyqtSignal(str)
    
    def __init__(self, min_number, max_number, max_length, input_type, default_text = None, placeholder = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_pos = QPoint()

        self.input_type = input_type
        self.max_number = max_number
        self.min_number = min_number
        self.max_length = max_length
        
        self.default_text = default_text
        self._is_default_text_set = False
        self.animating = False
        
        self.setPlaceholderText(placeholder)

        self.textChanged.connect(self.schedule_input_field_animation)
        self.original_input_field_pos = QPoint() 

        self.input_field_animation = QPropertyAnimation(self, b"pos")
        self.input_field_animation.setDuration(TEXTBOX_INPUT)
        self.input_field_animation.setEasingCurve(QEasingCurve.OutElastic)

        self.shake_timer = QTimer(self)
        self.shake_timer.setInterval(TEXTBOX_SHAKE_PER)
        self.shake_timer.timeout.connect(self._animate_to_random_shake_pos)
        
        self.is_key_pressed = False
        self.shake_animation = QPropertyAnimation(self, b"pos")
        self.shake_animation.setDuration(TEXTBOX_SHAKE)
        self.shake_animation.setEasingCurve(QEasingCurve.Linear)
        
        self.glitch_timer = QTimer(self)
        self.glitch_timer.timeout.connect(self._glitch_step)
        self.glitch_steps_left = 0
        self.original_text = super().text()
        
        self.textChanged.connect(self._emit_safe_text_changed)
        
        self.arrow_pressed = False
        self.arrow_direction = 0
        
        self.setFont(Utils.NType(14))
        self.setStyleSheet("""
            background-color: #222;
            color: #fff;
            padding: 8px 12px;
            border-radius: 14px;
            border: 2px solid #444;
        """)
    
    def _emit_safe_text_changed(self, text):
        if self.animating:
            return

        if not text:
            return
        
        self.safeTextChanged.emit(text)
    
    def showEvent(self, event: QEvent):
        super().showEvent(event)

        if self.original_input_field_pos.isNull():
            self.original_input_field_pos = self.pos()

        if not self._is_default_text_set and self.default_text is not None:
            super().setText()(self.default_text)
            self._is_default_text_set = True
    
    def is_not_valid(self):
        if super().text():
            secs = self.time_text_to_seconds()

            if secs:
                if secs < self.min_number:
                    return True

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

    def _parse_time_string(self, text):
        try:
            if ':' not in text:
                return int(text)

            if text.startswith(':'):
                parts = ['0', text[1:]]
            
            else:
                parts = text.split(':')

            if len(parts) != 2:
                return None

            minutes = int(parts[0]) if parts[0] else 0
            seconds = int(parts[1]) if parts[1] else 0

            if not (0 <= seconds < 60):
                return None

            return minutes * 60 + seconds

        except:
            return None

    def schedule_input_field_animation(self):
        if self.original_input_field_pos.isNull():
            return

        Utils.ui_sound("Tick")

        if self.is_key_pressed:
            return

        if self.input_field_animation.state() == QAbstractAnimation.Running:
            self.input_field_animation.stop()

        start_animation_pos = self.original_input_field_pos + QPoint(-5, -5)
        self.move(start_animation_pos) 
        
        self._run_input_field_animation()
    
    def showEvent(self, event: QEvent):
        super().showEvent(event)
        self.original_input_field_pos = self.pos()
    
    def _run_input_field_animation(self):
        self.input_field_animation.setStartValue(self.pos())
        self.input_field_animation.setEndValue(self.original_input_field_pos)
        self.input_field_animation.start()

    def keyPressEvent(self, event):
        key = event.key()
        
        text = super().text()
        new_char = event.text()
        
        if not CurrentSettings["reduce_animations"]:
            if not self.arrow_pressed and super().text():
                if key == Qt.Key_Left:
                    Utils.ui_sound("TickLeft")

                    self.arrow_pressed = True
                    self.arrow_direction = -1
                    self.animate_arrow_hold(-6)

                    return super().keyPressEvent(event)

                elif key == Qt.Key_Right:
                    Utils.ui_sound("TickRight")

                    self.arrow_pressed = True
                    self.arrow_direction = 1
                    self.animate_arrow_hold(6)

                    return super().keyPressEvent(event)

        allowed_keys = (
            Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left,
            Qt.Key_Right, Qt.Key_Home, Qt.Key_End,
            Qt.Key_Shift, Qt.Key_Return, Qt.Key_Enter,
            
        )

        if key not in allowed_keys:
            if self.input_type == "number":
                if not new_char.isdigit():
                    self.start_glitch()
                    return
                
                if text == "0" and new_char.isdigit():
                    self.start_glitch()
                    return
                
                if not (text + new_char).isdigit():
                    self.start_glitch()
                    return

                number = int(text + new_char)
                if number > self.max_number or number < self.min_number:
                    self.start_glitch()
                    return

            elif self.input_type == "text":
                if len(text) >= self.max_length:
                    self.start_glitch()
                    return

            elif self.input_type == ":time":
                if not new_char.isdigit() and new_char != ":":
                    self.start_glitch()
                    return

                if len(text) >= self.max_length:
                    self.start_glitch()
                    return

                new_text = text + new_char

                if new_text.count(":") > 1:
                    self.start_glitch()
                    return

                stripped = new_text.strip(":")
                if stripped.isdigit() and len(stripped) < 2:
                    super().keyPressEvent(event)
                    return

                normalized = f"0{new_text}" if new_text.startswith(":") else new_text
                parsed = self._parse_time_string(normalized)

                if parsed is None:
                    self.start_glitch()
                    return

                if parsed > self.max_number:
                    self.start_glitch()
                    return

                if parsed < self.min_number:
                    super().setText(self.seconds_to_time_text(self.min_number + 1))
                    self.setCursorPosition(len(super().text()))
                    
                    return

        super().keyPressEvent(event)

        if key not in (Qt.Key_Left, Qt.Key_Right):
            if self.is_key_pressed:
                return
            
            self.is_key_pressed = True

            if not CurrentSettings["reduce_animations"]:
                self.shake_timer.start()
                self._animate_to_random_shake_pos()
    
    def seconds_to_time_text(self, seconds: int) -> str:
        seconds = int(seconds)
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02}"
    
    def text(self):
        if self.animating:
            return None
        
        if not super().text():
            return None
        
        if self.input_type == ":time":
            return self.time_text_to_seconds()
        
        if self.input_type == "number":
            return int(super().text())
        
        return super().text()
    
    def time_text_to_seconds(self) -> int | None:
        text = super().text()
        
        try:
            if ':' not in text:
                return int(text)

            if text.startswith(':'):
                parts = ['0', text[1:]]
            
            else:
                parts = text.split(':')

            if len(parts) != 2:
                return None

            minutes = int(parts[0]) if parts[0] else 0
            seconds = int(parts[1]) if parts[1] else 0

            if not (0 <= seconds < 60):
                return None

            return minutes * 60 + seconds
        
        except:
            return None
    
    def setText(self, text: str | int):
        if self.input_type == ":time":
            return super().setText(self.seconds_to_time_text(text))
        
        if self.input_type == "number":
            return super().setText(str(text))
        
        super().setText(text)

    def start_glitch(self, sound = True):
        if sound:
            Utils.ui_sound("Reject")

        if not CurrentSettings["reduce_animations"]:
            self.animating = True

            if self.glitch_timer.isActive():
                return

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

        length = max(1, len(self.original_text))
        glitch_text = ''.join(random.choices(string.ascii_letters + string.punctuation, k=length))
        super().setText(glitch_text)

        dx = random.randint(-2, 2)
        dy = random.randint(-2, 2)
        self.move(self.original_pos + QPoint(dx, dy))

        self.glitch_steps_left -= 1

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)

        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            if self.arrow_pressed:
                self.arrow_pressed = False
                self.arrow_direction = 0
                self.animate_return_from_arrow()

        self.is_key_pressed = False
        self.shake_timer.stop()

        if self.shake_animation.state() == QPropertyAnimation.Running:
            self.shake_animation.stop()

        if not CurrentSettings["reduce_animations"]:
            self.shake_animation.setStartValue(self.pos())
            self.shake_animation.setEndValue(self.original_input_field_pos)
            self.shake_animation.setDuration(TEXTBOX_INPUT)
            self.shake_animation.setEasingCurve(QEasingCurve.OutQuad)
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
    MARGIN = 200
    
    def __init__(self, title: str, bpm: int = None, player = None, max_tilt_angle = 12, animate_func = "normal"):
        super().__init__()
        self.bpm = bpm
        self.player = player
        self.max_tilt_angle = max_tilt_angle

        self.is_ready = False
        self.is_closing = False
        self.was_cancelled = False

        self.setWindowFlags(self.windowFlags() | Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.setup_layout(title)
        self.setup_timers()
        self.setup_mouse_racking()
        self.setup_animation_properties()

        self.update_bpm(self.bpm)
        
        if animate_func == "official":
            animate_func = self.start_official_animation
        
        else:
            animate_func = self.start_normal_animation

        QTimer.singleShot(0, animate_func)

    def update_bpm(self, bpm = None):
        if not bpm:
            return

        if bpm >= 200:
            self.bpm = int(bpm / 2)
        
        if bpm <= 80:
            self.bpm = int(bpm * 2)
        
        else:
            self.bpm = int(bpm)

        self.bpm_timer.setInterval(60000 // self.bpm)

    def poll_mouse_position(self):
        global_pos = QCursor.pos()
        content_rect_global = QRect(self.mapToGlobal(self.content_layout.geometry().topLeft()), self.content_layout.geometry().size())

        if content_rect_global.contains(global_pos):
            local_pos = self.mapFromGlobal(global_pos)
            self.calculate_target_tilt(local_pos)
    
    def setup_timers(self):
        self.mouse_poll_timer = QTimer(self)
        self.mouse_poll_timer.setInterval(FPS_30)
        self.mouse_poll_timer.timeout.connect(self.poll_mouse_position)

        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(FPS_60)
        self.animation_timer.timeout.connect(self.update_smooth)

        self.bpm_timer = QTimer(self)
        self.bpm_timer.timeout.connect(self.bpm_tick_animation)

        if not CurrentSettings["reduce_animations"]:
            self.animation_timer.start()
            self.mouse_poll_timer.start()

            if self.bpm:
                self.bpm_timer.start()

    def setup_layout(self, title):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
        main_layout.setSpacing(0)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(15)

        main_layout.addLayout(self.content_layout)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #fff;")
        self.title_label.setFont(Utils.NType(15))

        self.content_layout.addWidget(self.title_label)
        self.adjustSize()

    def is_big(self):
        if self.width() - self.MARGIN * 2 > 500 or self.height() - self.MARGIN * 2 > 500:
            return True
        
        return False

    def setup_mouse_racking(self):
        self.current_tilt_x = 0.0
        self.current_tilt_y = 0.0
        self.target_tilt_x = 0.0
        self.target_tilt_y = 0.0
        self.tilt_smoothing = 0.2

    def setup_animation_properties(self):
        self.open_opacity = 1.0

        self.open_rotation = 0.0
        self.exit_rotation = 0.0
        self.disturbe_rotation = 0.0
        self.random_anim_rotation = 0.0

        self.entry_rotation_angle = 0
        self.current_rotation = 0.0
        
        self.open_scale = 1.0
        self.exit_scale = 1.0
        self.bpm_scale = 1.0
        self.disturbe_scale = 1.0
        self.wobble_scale = 1.0

        self.entry_rotation_exit_angle = 0

        self.bpm_wobble_start_size = 1.03
    
    def set_bpm_start_size(self, start_coeff):
        self.bpm_wobble_start_size = start_coeff

    def calculate_target_tilt(self, mouse_pos):
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        x_norm = -(mouse_pos.x() - center_x) / center_x
        y_norm = (mouse_pos.y() - center_y) / center_y

        self.target_tilt_x = -y_norm * self.max_tilt_angle
        self.target_tilt_y = x_norm * self.max_tilt_angle

    def update_smooth(self):
        self.current_tilt_x += (self.target_tilt_x - self.current_tilt_x) * self.tilt_smoothing
        self.current_tilt_y += (self.target_tilt_y - self.current_tilt_y) * self.tilt_smoothing
        
        if (
            abs(self.current_tilt_x - self.target_tilt_x) > 0.01 or 
            abs(self.current_tilt_y - self.target_tilt_y) > 0.01
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

        self.setGeometry(final_rect.translated(0, +20))

        return final_rect

    def start_normal_animation(self):
        self.adjustSize()
        final_rect = self.center_window()
        self.is_ready = True
        self.open_sound()

        if CurrentSettings["reduce_animations"]:
            return

        curve = QEasingCurve(QEasingCurve.OutElastic)
        curve.setPeriod(0.27)
        curve.setAmplitude(1.7)
        size = self.get_window_size()

        start_pos_y = self.period_randomizer((-250, -130), (130, 250))
        start_angle = get_rotation(*size)
        start_scale = get_scale(*size, base_scale = 1.6)

        if self.is_big():
            start_angle = self.period_randomizer((-20, -10), (10, 20))
            anim_geo_duration = 830
            anim_rotation_duration = 1070
        
        else:
            start_angle = self.period_randomizer((-30, -10), (15, 30))
            anim_geo_duration = 750
            anim_rotation_duration = 950
        
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
            ], b"openScale", 1200
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
                anim_opacity
            ], valueChanged = onValueChanged
        )

    def player_pulse(self, duration = 0.4, pulse_peak_speed = 1.2):
        start_speed = self.player.speed
        duration_half = duration / 2

        self.player.set_speed(pulse_peak_speed, duration = duration_half)
        QTimer.singleShot(int(duration_half * 1000), lambda: self.player.set_speed(start_speed, duration = duration_half))
    
    def open_sound(self):
        if self.player:
            if self.player.is_playing:
                return self.player_pulse()

        Utils.ui_sound(f"Open{random.randint(1, 2)}", 1.0)

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
        self.anim_rotation = self.make_animation(
            [
                (0.0, 0),
                (0.5, self.period_randomizer((-6, -3), (3, 6))),
                (1.0, 0)
            ], b"randomAnimRotation", 350
        )

        self.anim_rotation.start()
    
    def start_official_animation(self):
        self.adjustSize()
        self.center_window()
        self.is_ready = True

        if CurrentSettings["reduce_animations"]:
            return Utils.ui_sound(f"Open1", 1.0)

        curve = QEasingCurve(QEasingCurve.OutElastic)
        curve.setPeriod(0.27)
        curve.setAmplitude(1.7)
        size = self.get_window_size()
        
        start_angle = get_rotation(*size)

        anim_opacity = self.make_animation(
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], b"windowOpacity", 500
        )

        anim_scale = self.make_animation(
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], b"openScale", 1400
        )

        anim_rotation = self.make_animation(
            [
                (0.0, start_angle),
                (1.0, 0)
            ], b"openRotation", 1000, curve
        )

        self.group_animate(
            [
                anim_opacity,
                anim_scale,
                anim_rotation
            ]
        )

    @pyqtProperty(float) # type: ignore
    def exitRotation(self):
        return self.exit_rotation

    @exitRotation.setter
    def exitRotation(self, value):
        self.exit_rotation = value
    
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
    
    def bpm_tick_animation(self):
        if not self.player.is_playing:
            return

        audio_level = self.player.get_current_audio_level()

        if audio_level < 0.05:
            return

        player_speed = self.player.speed
        beat_interval_ms = int(60000 / self.bpm / (player_speed or 0.01))

        if player_speed != 1.0:
            self.bpm_timer.setInterval(beat_interval_ms)
            
        else:
            interval = int(60000 // self.bpm)
            if self.bpm_timer.interval() != interval:
                self.bpm_timer.setInterval(interval)
        
        self.anim_scale = self.make_animation(
            [
                (0.0, float(1.0)),
                (0.5, float(self.bpm_wobble_start_size + self.squish(audio_level))),
                (1.0, float(1.0))
            ],
            b"bpmScale",
            beat_interval_ms
        )

        self.anim_scale.start()
    
    def squish(self, x, power = 1.2):
        return 0.05 * (x ** power)
    
    def wobble(self):
        if CurrentSettings["reduce_animations"]:
            return

        self.anim_scale = self.make_animation(
            [
                (0.0, 1.0),
                (0.5, 1.05),
                (1.0, 1.0)
            ], b"wobbleScale", 500
        )

        self.anim_scale.start()

    def disturbeAnim(self):
        if CurrentSettings["reduce_animations"]:
            return

        start_angle = random.choice([
            random.randint(-30, -15),
            random.randint(15, 30)
        ])

        pos = self.pos()
        x, y = pos.x(), pos.y()

        anim_scale = self.make_animation(
            [
                (0.0, 1.0),
                (0.5, 1.2),
                (1.0, 1.0)
            ], b"disturbeScale", 400
        )

        anim_position = self.make_animation(
            [
                (0.0, pos),
                (0.5, QPoint(x - 15, y - 15)),
                (1.0, pos)
            ], b"pos", 500, QEasingCurve.OutElastic
        )

        anim_rotation = self.make_animation(
            [
                (0.0, self.entry_rotation_angle),
                (0.5, start_angle),
                (1.0, 0)
            ], b"disturbeRotation", 700, QEasingCurve.OutElastic
        )

        self.group_animate(
            [
                anim_scale,
                anim_position,
                anim_rotation
            ]
        )

        self.anim_group.start(QAbstractAnimation.DeleteWhenStopped)

    def get_window_size(self):
        geometry = self.content_layout.geometry()
        return geometry.width(), geometry.height()

    def start_exit_animation(self):
        if CurrentSettings["reduce_animations"]:
            return self._really_close()

        self.target_tilt_y = random.randint(5, 15)
        size = self.get_window_size()

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
            ], b"exitScale", 400
        )

        anim_opacity = self.make_animation(
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], b"windowOpacity", 400
        )

        self.group_animate(
            [
                anim_rotation,
                anim_scale,
                anim_opacity
            ], self._really_close, self._label_animator
        )

    def _label_animator(self, value):
        self.title_label.setText(str(value)[:5])

    def paintEvent(self, event):
        painter = QPainter(self)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        content_rect = self.content_layout.geometry()
        painter.save()

        if not CurrentSettings["reduce_animations"]:
            transform = QTransform()
            center_point = content_rect.center()

            transform.translate(center_point.x(), center_point.y())

            transform.rotate(self.current_tilt_y, Qt.YAxis)
            transform.rotate(self.current_tilt_x, Qt.XAxis)
            transform.rotate(self.open_rotation + self.exit_rotation + self.random_anim_rotation + self.disturbe_rotation)

            scale = self.exit_scale * self.bpm_scale * self.disturbe_scale * self.wobble_scale * self.open_scale
            transform.scale(scale, scale)
            transform.translate(-center_point.x(), -center_point.y())

            painter.setTransform(transform)

        bg_color = QColor(Styles.Colors.secondary_background)
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(content_rect, 16, 16)

        border_color = QColor(Styles.Colors.glass_border)
        pen = QPen(border_color, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(content_rect, 16, 16)

        painter.restore()
        super().paintEvent(event)

    def _really_close(self):
        self.bpm_timer.stop()
        self.mouse_poll_timer.stop()
        self.animation_timer.stop()
        
        if not self.was_cancelled:
            self.accept()
        
        else:
            self.reject()
    
    def on_ok(self):
        if self.is_closing:
            return

        self.is_closing = True
        Utils.ui_sound("PopupClose")
        self.was_cancelled = False
        self.start_exit_animation()

    def on_cancel(self):
        if self.is_closing:
            return

        self.is_closing = True
        Utils.ui_sound("PopupClose")
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
        self.input_field = AnimatedLineEdit(min_number, max_number, max_length, input_type)
        
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
        self.ok_button.glitch_started.connect(self.disturbeAnim)

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
        super().__init__(f"Cassette {open('version').read()} by chips047", bpm, player)

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
        super().__init__("Settings", max_tilt_angle = 5)
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

            for element_key, params in components.items():
                widget = None
                
                if element_key.startswith("checkbox"):
                    widget = CheckboxWithLabel(params["title"], params["description"], self)
                
                elif element_key.startswith("slider"):
                    widget = SliderWithLabel(
                        description=params["title"],
                        min_val=params["min"],
                        max_val=params["max"],
                        default_val=params["min"]
                    )
                
                elif element_key.startswith("selector"):
                    widget = SelectorWithLabel(
                        params["title"],
                        params["map"]
                    )
                
                if widget:
                    self.controls[params["key"]] = widget
                    self.load_setting(params["key"], widget, params)
                    page_layout.addWidget(widget)

            self.stacked_widget.addWidget(page_widget)

        self.change_page(first_page_widget)

    def load_setting(self, key, widget, params):
        if self.settings.contains(key):
            saved_value = self.settings.value(key)
            
            if isinstance(widget, CheckboxWithLabel):
                widget.setChecked(saved_value.lower() == "true")
            
            elif isinstance(widget, SliderWithLabel):
                widget.setValue(int(saved_value))
            
            elif isinstance(widget, SelectorWithLabel):
                print(f"Loading setting for {key}: {saved_value} (type: {type(saved_value)})")
                widget.setCurrentData(saved_value)
        
        else:
            if isinstance(widget, CheckboxWithLabel):
                widget.setChecked(params.get("default", False))
            
            elif isinstance(widget, SliderWithLabel):
                widget.setValue(params.get("default", 0))
            
            elif isinstance(widget, SelectorWithLabel):
                default_index = params.get("default", 0)
                widget.setCurrentIndex(default_index)

    def save_settings(self):
        for key, widget in self.controls.items():
            value = None
            if isinstance(widget, CheckboxWithLabel):
                value = widget.isChecked()
            
            elif isinstance(widget, SliderWithLabel):
                value = widget.value()
            
            elif isinstance(widget, SelectorWithLabel):
                value = widget.currentData()
                print(f"Saving setting for {key}: {value} (type: {type(value)})")

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

    @pyqtProperty(float)
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
        self.playback_manager = Player.Player()
        self.playback_manager.load_audio(audiofile_path)

        super().__init__("Tutorial", bpm, self.playback_manager, 10, "official")

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
                "label": "Welcome to compositor",
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