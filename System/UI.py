import os
import random
import string
import numpy as np

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from . import Utils
from . import Styles
from . import Porter
from . import GlyphEffects

from .Constants import *

class GlitchyButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.glitch_timer = QTimer(self)
        self.glitch_timer.timeout.connect(self._glitch_step)
        self.glitch_steps_left = 0

        self.original_pos = None
        self.original_size = None
        
        self.original_button_text = super().text()
        
        self.setFont(Utils.NType(13))
        self.setFixedHeight(Styles.Metrics.element_height)

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
            self.setText(self.original_button_text)
            self.glitch_timer.stop()
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

class Selector(QWidget):
    selection_changed = pyqtSignal(int, str)

    def __init__(
        self,
        items,
        *,
        width: int = 300,
        parent=None,
    ):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setFixedWidth(width)
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
        self._group.buttonClicked[int].connect(self._on_button_clicked)

        for idx, text in enumerate(items):
            btn = QPushButton(text, objectName="segmentedButton", parent=selector_container)
            btn.setFont(Utils.NType(14))
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.setCursor(Qt.PointingHandCursor)
            selector_layout.addWidget(btn)
            self._group.addButton(btn, id=idx)

        if self._group.buttons():
            self._group.buttons()[0].setChecked(True)

        main_layout.addWidget(selector_container)

    def _on_button_clicked(self, id: int):
        text = self._group.button(id).text()
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
    selection_changed = pyqtSignal(int, str)
    
    def __init__(
        self,
        description: str,
        items,
        *,
        width: int = 300,
        parent=None,
    ):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setFixedWidth(width)
        self.setFixedHeight(90)

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
        self.description_label.setStyleSheet(Styles.Other.font)
        inner_layout.addWidget(self.description_label)
        self.setMaximumWidth(1000)

        selector_container = QWidget(self.container_background)
        selector_container.setStyleSheet(f"QWidget {{border-radius: 10px}}")
        selector_layout = QHBoxLayout(selector_container)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(5)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked[int].connect(self._on_button_clicked)

        for idx, text in enumerate(items):
            btn = QPushButton(text, objectName="segmentedButton", parent=selector_container)
            btn.setFont(Utils.NType(11))
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.setCursor(Qt.PointingHandCursor)
            selector_layout.addWidget(btn)
            self._group.addButton(btn, id=idx)

        if self._group.buttons():
            self._group.buttons()[0].setChecked(True)

        inner_layout.addWidget(selector_container)
        main_layout.addWidget(self.container_background)
    
    def _on_button_clicked(self, id: int):
        text = self._group.button(id).text()
        self.selection_changed.emit(id, text)

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentText(self) -> str:
        btn = self._group.checkedButton()
        return btn.text() if btn else ""
    
    def setCurrentText(self, text):
        for button in self._group.buttons():
            if button.text() == text:
                button.setChecked(True)
                continue
            
            button.setChecked(False)
    
    def setCurrentIndex(self, index):
        for i, button in enumerate(self._group.buttons()):
            if i == index:
                button.setChecked(True)
                continue
            
            button.setChecked(False)

class Checkbox(QCheckBox):
    def __init__(self, name, parent):
        super().__init__(name, parent)

        self.setFont(Utils.NType(13))
        self.setStyleSheet(Styles.Controls.Checkbox)

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
        self.description_label.setStyleSheet(f"color: {Styles.Colors.second_font_color}; padding: 0px;")
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

class CycleButton(_BaseControlWidget):
    state_changed = pyqtSignal(str, object)

    def __init__(self, icon="", static_label_text="", states=None, parent=None):
        super().__init__(icon, static_label_text, parent)
        self.states = states if states is not None else [("1x", 1.0)]
        self.current_state_index = 0
        
        self.value_label.setContentsMargins(0, 0, 0, 5)
        self.update_button_state()
        self.setStyleSheet(Styles.Controls.CycleButton)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.cycle_state()
            event.accept()
        
        else:
            super().mousePressEvent(event)

    def cycle_state(self):
        self.current_state_index = (self.current_state_index + 1) % len(self.states)
        self.update_button_state()

    def update_button_state(self):
        display_text_part, value = self.states[self.current_state_index]
        self.value_label.setText(display_text_part)
        self.state_changed.emit(display_text_part, value)

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
                    default_val=self.configuration["settings"][f"slider{i + 1}"]["min"]
                )

                self.controls[element] = widget
                layout.addWidget(widget)

            if element.startswith("selector"):
                widget = SelectorWithLabel(
                    self.configuration["settings"][f"selector{i + 1}"]["title"],
                    self.configuration["settings"][f"selector{i + 1}"]["choices"],
                    width = 460
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

class ValuePopup(QWidget):
    def __init__(self, text: str, pos: QPoint, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)
        self.parent_ref = parent

        self.padding = 10
        self.label = QLabel(text, self)
        self.label.setFont(Utils.NType(12))
        self.label.setStyleSheet("color: white; background: transparent;")
        self.label.adjustSize()

        label_size = self.label.size()
        full_width = label_size.width() + self.padding * 2
        full_height = label_size.height() + self.padding * 2

        self.fixed_rect = QRect(0, 0, full_width, full_height)

        self.resize(full_width, full_height)
        self.label.move(self.padding, self.padding)
        self.move(pos - QPoint(self.width() // 2, self.height() // 2 - 34))

        self.anim_scale = QPropertyAnimation(self, b"geometry")
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.start_animation()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor(*Styles.hex_to_rgb(Styles.Colors.secondary_background))
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.fixed_rect, 8, 8)

        super().paintEvent(event)

    def start_animation(self):
        start_rect = self.geometry()
        scale_up = start_rect.adjusted(-4, -4, 4, 4)

        self.anim_scale.setDuration(VALUE_POPUP_IN)
        self.anim_scale.setStartValue(scale_up)
        self.anim_scale.setEndValue(start_rect)
        self.anim_scale.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_scale.start()

        QTimer.singleShot(800, self.deleteLater)

    def deleteLater(self):
        if hasattr(self.parent_ref, "active_popup"):
            if self.parent_ref.active_popup is self:
                self.parent_ref.active_popup = None
        
        super().deleteLater()

class AnimatedTooltip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._tooltip_visible = False

        self.label = QLabel(self)
        self.label.setStyleSheet("background: transparent; color: white;")
        self.label.setFont(Utils.NType(12))
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.label.setContentsMargins(10, 8, 10, 8)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.text_opacity = QGraphicsOpacityEffect(self.label)
        self.label.setGraphicsEffect(self.text_opacity)
        self.text_opacity.setOpacity(0.0)

        self.anim_size = QPropertyAnimation(self, b"size")
        self.anim_opacity = QPropertyAnimation(self.text_opacity, b"opacity")
        self._hiding = False
        
        self._target_size = 0

    def show_tooltip(self, text, pos):
        self._hiding = False

        self._tooltip_visible = True
        self.label.setText(text)
        self.label.adjustSize()

        margin = self.label.contentsMargins()
        label_size = self.label.size()
        final_size = QSize(
            label_size.width() + margin.left() + margin.right(),
            label_size.height() + margin.top() + margin.bottom()
        )

        self.setGeometry(QRect(pos, final_size))
        self.resize(0, 0)
        self.label.resize(final_size)
        self.text_opacity.setOpacity(0.0)
        self.show()

        self.anim_size.stop()
        self.anim_size.setDuration(TOOLTIP_POPUP_IN)
        self.anim_size.setStartValue(QSize(0, 0))
        self.anim_size.setEndValue(final_size)
        self.anim_size.setEasingCurve(QEasingCurve.OutBack)
        self.anim_size.start()
        
        self._target_size = final_size
        QTimer.singleShot(TOOLTIP_POPUP_IN, self._fade_in_text)

    def _fade_in_text(self):
        self.anim_opacity.stop()
        self.anim_opacity.setDuration(TOOLTIP_TEXT_FADE_IN)
        self.anim_opacity.setStartValue(0.0)
        self.anim_opacity.setEndValue(1.0)
        self.anim_opacity.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_opacity.start()
    
    def is_tooltip_visible(self):
        return self._tooltip_visible

    def hide_tooltip(self):
        self._hiding = True

        if not self._tooltip_visible:
            return
        
        self._tooltip_visible = False

        current_opacity = self.text_opacity.opacity()
        self.anim_opacity.stop()
        self.anim_opacity.setDuration(int(200 * current_opacity))
        self.anim_opacity.setStartValue(current_opacity)
        self.anim_opacity.setEndValue(0.0)
        self.anim_opacity.setEasingCurve(QEasingCurve.InCubic)
        self.anim_opacity.start()

        current_size = self.size()
        target_width = self._target_size.width() or 1
        remaining_ratio = current_size.width() / target_width
        duration = int(350 * remaining_ratio)

        def shrink_tooltip():
            self.anim_size.stop()
            self.anim_size.setDuration(duration)
            self.anim_size.setStartValue(current_size)
            self.anim_size.setEndValue(QSize(0, 0))
            self.anim_size.setEasingCurve(QEasingCurve.InBack)
            self.anim_size.start()
            self.anim_size.finished.connect(self._on_hide_finished)

        QTimer.singleShot(int(100 * current_opacity), shrink_tooltip)

    def _on_hide_finished(self):
        if self._hiding:
            self._tooltip_visible = False
            self.hide()

    def resizeEvent(self, event):
        margin = self.label.contentsMargins()
        self.label.setGeometry(
            margin.left(),
            margin.top(),
            self.width() - margin.left() - margin.right(),
            self.height() - margin.top() - margin.bottom()
        )
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)

        bg = QColor(*Styles.hex_to_rgb(Styles.Colors.secondary_background))
        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, Styles.Roundings.button, Styles.Roundings.button)

        border = QColor(*Styles.hex_to_rgb(Styles.Colors.glass_border))
        pen = QPen(border, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, Styles.Roundings.button, Styles.Roundings.button)

class MiniWaveformPreview(QWidget):
    preview_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_data = None
        self.sampling_rate = None
        self.peaks = []
        self.setFixedHeight(Styles.Metrics.element_height)
        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_audio_data(self, audio_data, sampling_rate):
        self.audio_data = audio_data
        self.sampling_rate = sampling_rate
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

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
            border-radius: 8px;
            border: 1px solid #444;
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
        
        if key == Qt.Key_Left:
            if not self.arrow_pressed:
                Utils.ui_sound("TickLeft")
                
                self.arrow_pressed = True
                self.arrow_direction = -1
                self.animate_arrow_hold(-6)
            
            return super().keyPressEvent(event)

        elif key == Qt.Key_Right:
            if not self.arrow_pressed:
                Utils.ui_sound("TickRight")
                
                self.arrow_pressed = True
                self.arrow_direction = 1
                self.animate_arrow_hold(6)
            
            return super().keyPressEvent(event)

        text = super().text()
        new_char = event.text()

        allowed_keys = (
            Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left,
            Qt.Key_Right, Qt.Key_Home, Qt.Key_End,
            Qt.Key_Shift
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
        self.animating = True
        
        if sound:
            Utils.ui_sound("Reject")
        
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
                background-color: {Styles.Colors.nothing_accent_second};
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

class Settings(QDialog):
    MARGIN = 20
    def __init__(self):
        super().__init__()
        self.content_width = 1200
        self.content_height = 700

        self.settings = QSettings("beatlink", "Cassette")

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedSize(self.content_width + self.MARGIN * 2, self.content_height + self.MARGIN * 2)
        Utils.ui_sound("PopupOpen")

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.overall_layout = QVBoxLayout(self)
        self.overall_layout.setContentsMargins(self.MARGIN + 20, self.MARGIN + 20, self.MARGIN + 20, self.MARGIN + 20)
        self.overall_layout.setSpacing(15)

        self.title_label = QLabel("Settings")
        self.title_label.setFont(Utils.NType(30))
        self.title_label.setStyleSheet(f"color: {Styles.Colors.font_color};")
        self.title_label.setAlignment(Qt.AlignLeft)
        self.overall_layout.addWidget(self.title_label)

        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(20)

        self.nav_widget = QWidget()
        self.nav_widget.setFixedWidth(250)
        self.nav_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {Styles.Colors.third_background};
                border-radius: 12px;
            }}
        """)
        self.nav_layout = QVBoxLayout(self.nav_widget)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(8)
        self.nav_layout.setAlignment(Qt.AlignTop)
        self.content_layout.addWidget(self.nav_widget)

        self.stacked_widget = QStackedWidget()
        self.content_layout.addWidget(self.stacked_widget)
        
        self.overall_layout.addLayout(self.content_layout)

        self.ok_button = NothingButton("Apply")
        self.cancel_button = ButtonWithOutline("Back")
        
        self.button_row = QHBoxLayout()
        self.button_row.setSpacing(10)
        self.button_row.addWidget(self.cancel_button)
        self.button_row.addWidget(self.ok_button)
        self.overall_layout.addLayout(self.button_row)
        
        self.nav_buttons = []
        self.pages = {}
        self.controls = {}

        self.ok_button.pressed.connect(self.apply_and_close)
        self.cancel_button.pressed.connect(self.reject)

        self.setMouseTracking(True)
        self.max_tilt_angle = 2
        self.mouse_origin = None
        self.is_mouse_inside = False

        self.tilt_timer = QTimer(self)
        self.tilt_timer.setInterval(16)
        self.tilt_timer.timeout.connect(self.update)
        self.tilt_timer.start()
        
        QTimer.singleShot(0, self.start_entry_animation)
    
    def change_page(self, page_widget):
        self.stacked_widget.setCurrentWidget(page_widget)
        for button, widget in self.pages.values():
            button.setActive(widget == page_widget)

    def init_settings(self, setting_components, initial_page=""):
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
                        default_val=params["default"]
                    )
                
                elif element_key.startswith("selector"):
                    widget = SelectorWithLabel(
                        params["title"],
                        params["choices"],
                        width=460
                    )
                
                if widget:
                    self.controls[element_key] = widget
                    self.load_setting(element_key, widget, params)
                    page_layout.addWidget(widget)

            self.stacked_widget.addWidget(page_widget)

        target_page = self.pages.get(initial_page)
        
        if target_page:
            self.change_page(target_page[1])
        elif first_page_widget:
            self.change_page(first_page_widget)

    def load_setting(self, key, widget, params):
        if self.settings.contains(key):
            saved_value = self.settings.value(key)
            
            if isinstance(widget, CheckboxWithLabel):
                widget.setChecked(bool(saved_value))
            
            elif isinstance(widget, SliderWithLabel):
                widget.setValue(int(saved_value))
            
            elif isinstance(widget, SelectorWithLabel):
                widget.setCurrentText(str(saved_value))
        
        else:
            if isinstance(widget, CheckboxWithLabel):
                widget.setChecked(params.get("default", False))
            
            elif isinstance(widget, SliderWithLabel):
                widget.setValue(params.get("default", 0))
            
            elif isinstance(widget, SelectorWithLabel):
                default_index = params.get("default", 0)
                if isinstance(default_index, int) and len(params["choices"]) > default_index:
                    widget.setCurrentIndex(default_index)

    def save_settings(self):
        for key, widget in self.controls.items():
            value = None
            if isinstance(widget, CheckboxWithLabel):
                value = widget.isChecked()
            elif isinstance(widget, SliderWithLabel):
                value = widget.value()
            elif isinstance(widget, SelectorWithLabel):
                value = widget.currentText()

            if value is not None:
                self.settings.setValue(key, value)
        
        self.settings.sync()

    def apply_and_close(self):
        Utils.ui_sound("Setup/StartSetup1")
        self.save_settings()
        self.start_exit_animation()
    
    def reject(self):
        Utils.ui_sound("PopupClose")
        self.start_exit_animation()

    def _really_close(self):
        super().done(self.result())

    def eventFilter(self, watched_object, event):
        if event.type() == QEvent.MouseMove:
            new_pos = watched_object.mapTo(self, event.pos())
            self.mouse_origin = new_pos
            self.update()
        return super().eventFilter(watched_object, event)

    def start_entry_animation(self):
        desktop = QApplication.desktop()
        if desktop:
            screen_center = desktop.screen().rect().center()
            final_rect = QRect(screen_center.x() - self.width() // 2, screen_center.y() - self.height() // 2, self.width(), self.height())
            self.setGeometry(final_rect.translated(0, +20))
            self.anim = QPropertyAnimation(self, b"geometry")
            self.anim.setDuration(DIALOG_POPUP_IN)
            self.anim.setStartValue(final_rect.translated(0, +20))
            self.anim.setEndValue(final_rect)
            self.anim.setEasingCurve(QEasingCurve.OutElastic)
            self.anim.start(QAbstractAnimation.DeleteWhenStopped)

    def start_exit_animation(self):
        start_rect = self.geometry()
        end_rect = start_rect.translated(0, -25)
        anim_move = QPropertyAnimation(self, b"geometry")
        anim_move.setDuration(DIALOG_POPUP_OUT)
        anim_move.setStartValue(start_rect)
        anim_move.setEndValue(end_rect)
        anim_move.setEasingCurve(QEasingCurve.OutExpo)
        anim_opacity = QPropertyAnimation(self.opacity_effect, b"opacity")
        anim_opacity.setDuration(DIALOG_POPUP_FADEOUT)
        anim_opacity.setStartValue(1.0)
        anim_opacity.setEndValue(0.0)
        anim_opacity.setEasingCurve(QEasingCurve.InCubic)
        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(anim_move)
        self.anim_group.addAnimation(anim_opacity)
        self.anim_group.finished.connect(self._really_close)
        self.anim_group.start(QAbstractAnimation.DeleteWhenStopped)

    def enterEvent(self, event):
        self.is_mouse_inside = True
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self.mouse_origin = event.pos()
        self.update()
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        content_rect = QRect(self.MARGIN, self.MARGIN, self.content_width, self.content_height)
        
        if self.is_mouse_inside and self.mouse_origin:
            mouse_pos_in_content = self.mouse_origin - content_rect.topLeft()
            x_norm = max(-1.0, min(1.0, (mouse_pos_in_content.x() / self.content_width) * 2 - 1))
            y_norm = max(-1.0, min(1.0, (mouse_pos_in_content.y() / self.content_height) * 2 - 1))
            x_norm = max(-0.98, min(0.98, x_norm))
            y_norm = max(-0.98, min(0.98, y_norm))
            
            angle_x = -y_norm * self.max_tilt_angle
            angle_y = -x_norm * self.max_tilt_angle
            
            transform = QTransform()
            transform.translate(content_rect.center().x(), content_rect.center().y())
            transform.rotate(angle_y, Qt.YAxis)
            transform.rotate(angle_x, Qt.XAxis)
            transform.translate(-content_rect.center().x(), -content_rect.center().y())
            
            painter.setTransform(transform)
        
        bg_color = QColor(*Styles.hex_to_rgb(Styles.Colors.secondary_background))
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(content_rect, 16, 16)
        
        border = QColor(*Styles.hex_to_rgb(Styles.Colors.glass_border))
        pen = QPen(border, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(content_rect, 16, 16)
        
        super().paintEvent(event)

class FloatingWindow(QDialog):
    MARGIN = 70
    
    def __init__(self, title: str, width: int, height: int):
        super().__init__()
        self.content_width = width
        self.content_height = height

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setFixedSize(self.content_width + self.MARGIN * 2, self.content_height + self.MARGIN * 2)

        self.setupLayout(title)
        self.setupMouseTracking()
        self.setupAnimationProperties()
        
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(FPS_60)
        self.animation_timer.timeout.connect(self.updateSmooth)
        self.animation_timer.start()
        
        self.was_cancelled = False
        
        QTimer.singleShot(0, self.start_entry_animation)

    def setupLayout(self, title):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(
            self.MARGIN + 20, self.MARGIN + 20, 
            self.MARGIN + 20, self.MARGIN + 20
        )
        self.layout.setSpacing(15)

        self.title_label = QLabel(title)
        self.title_label.setFont(Utils.NType(15))
        self.title_label.setStyleSheet("color: #fff;")
        self.layout.addWidget(self.title_label)
        
        self._apply_mouse_tracking_and_filter(self)

    def setupMouseTracking(self):
        self.setMouseTracking(True)
        self.max_tilt_angle = 25
        
        self.current_tilt_x = 0.0
        self.current_tilt_y = 0.0
        self.target_tilt_x = 0.0
        self.target_tilt_y = 0.0
        self.tilt_smoothing = 0.1

    def setupAnimationProperties(self):
        self.entry_rotation_angle = 0
        self.current_rotation = 0.0
        self.target_rotation = 0.0
        self.rotation_smoothing = 0.2
        
        self.exit_scale = 1.0

    def eventFilter(self, watched_object, event):
        if event.type() == QEvent.MouseMove:
            pos_in_window = watched_object.mapTo(self, event.pos())
            self.calculateTargetTilt(pos_in_window)
        
        return super().eventFilter(watched_object, event)

    def _apply_mouse_tracking_and_filter(self, widget):
        widget.setMouseTracking(True)
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.installEventFilter(self)
            child.setMouseTracking(True)

    def calculateTargetTilt(self, mouse_pos):
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        x_norm = -(mouse_pos.x() - center_x) / center_x
        y_norm = (mouse_pos.y() - center_y) / center_y

        self.target_tilt_x = -y_norm * self.max_tilt_angle
        self.target_tilt_y = x_norm * self.max_tilt_angle

    def updateSmooth(self):
        self.current_tilt_x += (self.target_tilt_x - self.current_tilt_x) * self.tilt_smoothing
        self.current_tilt_y += (self.target_tilt_y - self.current_tilt_y) * self.tilt_smoothing
        self.current_rotation += (self.target_rotation - self.current_rotation) * self.rotation_smoothing
        
        if (
            abs(self.current_tilt_x - self.target_tilt_x) > 0.01 or 
            abs(self.current_tilt_y - self.target_tilt_y) > 0.01 or
            abs(self.current_rotation - self.target_rotation) > 0.01
        ):
            self.update()

    def start_entry_animation(self):
        screen_center = QApplication.primaryScreen().geometry().center()
        final_rect = QRect(
            screen_center.x() - self.width() // 2,
            screen_center.y() - self.height() // 2,
            self.width(), self.height()
        )

        self.setGeometry(final_rect.translated(0, +20))

        anim_geo = QPropertyAnimation(self, b"geometry")
        anim_geo.setDuration(800)
        anim_geo.setStartValue(final_rect.translated(0, -200))
        anim_geo.setEndValue(final_rect)
        anim_geo.setEasingCurve(QEasingCurve.OutElastic)
        
        anim_opacity = QPropertyAnimation(self, b"windowOpacity")
        anim_opacity.setDuration(350)
        anim_opacity.setStartValue(0)
        anim_opacity.setEndValue(1)
        anim_opacity.setEasingCurve(QEasingCurve.OutExpo)

        self.rotation_anim = QPropertyAnimation(self, b"entryRotation")
        self.rotation_anim.setDuration(1200)
        start_angle = random.randint(-65, -15) if random.random() < 0.5 else random.randint(15, 65)
        self.rotation_anim.setStartValue(start_angle)
        self.rotation_anim.setEndValue(0)
        self.rotation_anim.setEasingCurve(QEasingCurve.OutElastic)

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(anim_geo)
        self.anim_group.addAnimation(anim_opacity)
        self.anim_group.addAnimation(self.rotation_anim)
        
        self.animation_timer.start()
        self.anim_group.start(QAbstractAnimation.DeleteWhenStopped)
        
        Utils.ui_sound("Error1")

    def getEntryRotation(self):
        return self.entry_rotation_angle

    def setEntryRotation(self, value):
        self.entry_rotation_angle = value
        self.target_rotation = value

    entryRotation = pyqtProperty(float, fget = getEntryRotation, fset = setEntryRotation)
    
    def getExitScale(self):
        return self.exit_scale

    def setExitScale(self, value):
        self.exit_scale = value
        self.update()

    exitScale = pyqtProperty(float, fget = getExitScale, fset = setExitScale)

    def start_exit_animation(self):
        self.target_tilt_y = random.randint(10, 30)
        self.target_rotation = random.randint(-15, 15)

        anim_scale = QPropertyAnimation(self, b"exitScale")
        anim_scale.setDuration(450)
        anim_scale.setStartValue(1.0)
        anim_scale.setEndValue(1.5)
        anim_scale.setEasingCurve(QEasingCurve.OutCubic)

        anim_opacity = QPropertyAnimation(self, b"windowOpacity")
        anim_opacity.setDuration(270)
        anim_opacity.setStartValue(1.0)
        anim_opacity.setEndValue(0.0)
        anim_opacity.setEasingCurve(QEasingCurve.OutCubic)

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(anim_scale)
        self.anim_group.addAnimation(anim_opacity)
        self.anim_group.finished.connect(self._really_close)
        self.anim_group.start(QAbstractAnimation.DeleteWhenStopped)
    
    def event(self, event):
        if event.type() == QEvent.ChildAdded:
            child = event.child()
            if isinstance(child, QWidget):
                self._apply_mouse_tracking_and_filter(child)
        
        return super().event(event)

    def mouseMoveEvent(self, event):
        self.calculateTargetTilt(event.pos())
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        content_rect = QRect(self.MARGIN, self.MARGIN, self.content_width, self.content_height)
        
        transform = QTransform()
        center_point = content_rect.center()
        transform.translate(center_point.x(), center_point.y())
        
        transform.rotate(self.current_tilt_y, Qt.YAxis)
        transform.rotate(self.current_tilt_x, Qt.XAxis)
        transform.rotate(self.current_rotation)
        
        transform.scale(self.exit_scale, self.exit_scale)
        
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

        painter.save()
        painter.resetTransform()
        super().paintEvent(event)
        painter.restore()

    def _really_close(self):
        self.animation_timer.stop()
        
        if not self.was_cancelled:
            self.accept()
        
        else:
            self.reject()

class DialogInputWindow(FloatingWindow):
    def __init__(self, title="Input Dialog", placeholder = "Type something...", min_number = 0, max_number = 100, max_length = 100, input_type = "number"):
        super().__init__(title, 400, 180)
        self.placeholder = placeholder
        self.result_text = None

        self.input_field = AnimatedLineEdit(min_number, max_number, max_length, input_type)
        self.input_field.setFont(Utils.NType(13))
        self.input_field.setPlaceholderText(self.placeholder)
        self.layout.insertWidget(1, self.input_field)
        
        self.ok_button = NothingButton("OK")
        self.ok_button.setFixedSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)

        self.cancel_button = ButtonWithOutline("Cancel")
        self.cancel_button.setFixedSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)
        self.layout.addLayout(button_row)

        self.ok_button.clicked.connect(self.on_ok)
        self.cancel_button.clicked.connect(self.on_cancel)

    def on_ok(self):
        Utils.ui_sound("PopupClose")
        text = self.input_field.text()
        
        if text is None:
            self.ok_button.start_glitch()
            return

        self.result_text = text
        self.start_exit_animation()

    def on_cancel(self):
        Utils.ui_sound("PopupClose")
        self.result_text = None
        self.was_cancelled = True
        self.start_exit_animation()

    def get_text(self) -> str:
        return self.input_field.text()

class ExportDialogWindow(FloatingWindow):
    selection_changed = pyqtSignal(str)
    
    def __init__(self, title, composition):
        super().__init__(title, 400, 250)
        self.composition = composition
        self.original_model = model_to_code(composition.model)
        
        self._was_cancelled = False
        
        self.ok_button = NothingButton("Tape it!")
        self.ok_button.setFixedSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)

        self.cancel_button = ButtonWithOutline("Later")
        self.cancel_button.setFixedSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
        
        self.ok_button.clicked.connect(self.on_ok)
        self.cancel_button.clicked.connect(self.on_cancel)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)
        self.layout.addLayout(button_row)
        
        self.number_model = code_to_number_model(composition.model)
        self.choices = PortVariants[model_to_code(composition.model)]
        self.combobox = SelectorWithLabel("Tap a model to port the song to it.", self.choices)
        self.combobox.selection_changed.connect(self.request_port)
        
        self.layout.insertWidget(1, self.combobox)
    
    def request_port(self, index, text):
        code_model = number_model_to_code(text)
        
        ported, ported_to = Porter.Port.port(self.original_model, code_model, self.composition)
        Porter.Port.export_port(ported, ported_to, self.composition.duration_ms, self.composition.id)
        
        Utils.open_file(os.path.abspath(Utils.get_songs_path(str(self.composition.id))))
        Utils.ui_sound("Export")

    def on_ok(self):
        Utils.ui_sound("PopupClose")
        self.was_cancelled = False
        self.start_exit_animation()

    def on_cancel(self):
        Utils.ui_sound("PopupClose")
        self.was_cancelled = True
        self.start_exit_animation()

class DialogWindow(FloatingWindow):
    def __init__(self, title):
        super().__init__(title, 400, 130)
        self.ok_button = NothingButton("Hell yeah")
        self.ok_button.setFixedSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)

        self.cancel_button = ButtonWithOutline("Nah")
        self.cancel_button.setFixedSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
        
        self.ok_button.clicked.connect(self.on_ok)
        self.cancel_button.clicked.connect(self.on_cancel)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)
        self.layout.addLayout(button_row)

    def on_ok(self):
        Utils.ui_sound("PopupClose")
        self.was_cancelled = False
        self.start_exit_animation()

    def on_cancel(self):
        Utils.ui_sound("PopupClose")
        self.was_cancelled = True
        self.start_exit_animation()