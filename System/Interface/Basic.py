import re
import random
import string

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System.Common import Utils
from System.Common import Styles

from loguru import logger

class GlitchyButton(QPushButton):
    glitch_started = pyqtSignal()
    def __init__(self, title, enable_glitch_sound = True):
        super().__init__(title)

        self.glitch_timer = QTimer(self)
        self.glitch_timer.timeout.connect(self._glitch_step)
        self.glitch_steps_left = 0

        self.original_pos = None
        self.original_size = None
        self.enable_glitch_sound = enable_glitch_sound
        
        self.original_button_text = super().text()
        
        self.setFont(Utils.NType(13))
        self.setFixedHeight(50)
        
        self.installEventFilter(self)
    
    def random_ass_text(self, length):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k = length))

    def eventFilter(self, obj, event):
        if obj == self and event.type() == QEvent.MouseButtonPress:
            if not self.isEnabled():
                self.start_glitch()
                return True
        
        return super().eventFilter(obj, event)

    def start_glitch(self):
        if self.enable_glitch_sound:
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
    def __init__(self, title, enable_glitch_sound = True):
        super().__init__(title, enable_glitch_sound)
        self.setStyleSheet(Styles.Buttons.nothing_styled_button)

class Button(GlitchyButton):
    def __init__(self, title, enable_glitch_sound = True):
        super().__init__(title, enable_glitch_sound)
        self.setStyleSheet(Styles.Buttons.normal_button)

class ButtonWithOutline(GlitchyButton):
    def __init__(self, title, enable_glitch_sound = True):
        super().__init__(title, enable_glitch_sound)
        self.setStyleSheet(Styles.Buttons.normal_button_with_border)

class ButtonWithOutlineSlim(GlitchyButton):
    def __init__(self, title, enable_glitch_sound = True):
        super().__init__(title, enable_glitch_sound)
        self.setStyleSheet(Styles.Buttons.normal_button_with_border_slim)

        self.setFixedHeight(35)

class ButtonRow(QHBoxLayout):
    def __init__(self, buttons, spacing = 10):
        super().__init__()

        self.setSpacing(spacing)
        self.buttons = {}

        for item in buttons:
            if len(item) == 4:
                class_name, text, callback, glitch = item
            
            else:
                class_name, text, callback = item
                glitch = True
            
            btn = class_name(text, enable_glitch_sound = glitch)
            
            btn.clicked.connect(callback)
            
            self.addWidget(btn)
            self.buttons[text] = btn

    def get_button(self, text):
        return self.buttons.get(text)

class TitleLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)

        self._scale = 1.0
        self._rotation = 0.0
        
        self.setContentsMargins(0, 0, 0, 5)
        
        self.setFont(Utils.NType(15))
        self.setStyleSheet(Styles.Other.font)

        self.original_text = text
        self.display_text = list(text)
        
        self.chars = string.ascii_uppercase
        self.solved_indices = set()

        self.glitch_timer = QTimer(self)
        self.glitch_timer.setInterval(25)
        self.glitch_timer.timeout.connect(self.text_glitch_step)

    def start_glitch(self):
        self.solved_indices.clear()
        self.glitch_timer.start()

    def text_glitch_step(self):
        new_text = []
        
        for i, char in enumerate(self.original_text):
            if i in self.solved_indices:
                new_text.append(char)
            
            elif char == " ":
                new_text.append(" ")
            
            else:
                if random.random() < 0.4:
                    self.solved_indices.add(i)
                    new_text.append(char)
                
                else:
                    new_text.append(random.choice(self.chars))

        self.setText("".join(new_text))

        if len(self.solved_indices) >= len(self.original_text.replace(" ", "")):
            self.setText(self.original_text)
            self.glitch_timer.stop()

    @pyqtProperty(float)
    def scale(self): return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = value
        self.update()

    @pyqtProperty(float)
    def rotation(self): return self._rotation

    @rotation.setter
    def rotation(self, value):
        self._rotation = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = self.contentsRect()
        alignment = self.alignment()

        cx = rect.width() / 2.0
        cy = rect.height() / 2.0

        if alignment & Qt.AlignmentFlag.AlignLeft:
            px = 0.0
        
        elif alignment & Qt.AlignmentFlag.AlignRight:
            px = float(rect.width())
        
        else:
            px = cx

        transform = QTransform()
        
        transform.translate(px, cy)
        transform.scale(self._scale, self._scale)
        transform.translate(-px, -cy)

        transform.translate(cx, cy)
        transform.rotate(self._rotation)
        transform.translate(-cx, -cy)

        painter.setTransform(transform)

        painter.setPen(self.palette().windowText().color())
        painter.setFont(self.font())
        
        text_flags = alignment | (Qt.TextFlag.TextWordWrap if self.wordWrap() else 0)
        painter.drawText(rect, text_flags, self.text())

        painter.end()

class DescriptionLabel(QLabel):
    def __init__(self, text, maximum_width = None):
        text = re.sub(r'`([^`]*)`', r'<span style="color:white;">\1</span>', text)
        text = text.replace("\n", "<br>")

        super().__init__(text)

        self.setFont(Utils.NType(12))
        self.setStyleSheet(Styles.Other.second_font)

        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)

        if maximum_width:
            self.setMaximumWidth(maximum_width)

class Image(QLabel):
    clicked = pyqtSignal()

    def __init__(self, pixmap):
        super().__init__()
        
        self.setCursor(Qt.PointingHandCursor)
        self.update_image(pixmap)

    def update_image(self, pixmap):
        self.setPixmap(pixmap)

    def mousePressEvent(self, event):
        self.clicked.emit()