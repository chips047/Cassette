import random

from PyQt6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath
)

from PyQt6.QtCore import (
    Qt,
    QRectF,
    QEvent,
    QTimer,
    QObject,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QPushButton,
    QButtonGroup
)

from System.Common import (
    Dev,
    Utils,
    Styles
)

from System.Services import Player

from System.Interface.Animation import Lifecycle

from System.Interface.Animation.LoomEngine import (
    Easing,
    MixMode,
    ui_engine
)

from System.Interface.Controls import BaseControlContainer

from loguru import logger

@Dev.track_ram
class SegmentedStrip(Lifecycle.LoomAnimationMixin, QWidget):
    selectionChanged = pyqtSignal(int, str, object)

    corner_radius: int = 12

    def __init__(
            self,
            items:            list[str] | dict,
            default_text:     str | None = None,
            default_value:    object     = None,
            pill_color:       object     = None,
            hover_color:      object     = None,
            button_font_size: int        = 10,
            button_style:     str        = "",
            stylesheet:       str        = ""
        ) -> None:

        super().__init__()

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.pill_color  = QColor(pill_color) if pill_color else QColor(Styles.Colors.NothingAccent)
        self.hover_color = self.resolve_hover_color(hover_color)

        self.has_indicator = False

        self.data_by_identifier: dict[int, object] = {}
        self.buttons:            list[QPushButton] = []

        self.setup_layout(items, button_font_size, button_style)
        self.setup_animation_handles()

        self.setStyleSheet(stylesheet if stylesheet else Styles.Controls.Selector)

        if default_text is not None:
            self.select_text(default_text, animated = False)
            return

        if default_value is not None:
            self.select_data(default_value, animated = False)
            return

        if not self.group.buttons():
            return

        self.group.buttons()[0].setChecked(True)
        QTimer.singleShot(0, self.animate_entrance)

    def resolve_hover_color(self, hover_color: object) -> QColor:
        if hover_color:
            return QColor(hover_color)

        fallback = getattr(Styles.Colors, "ThirdBackground", None)

        return QColor(fallback) if fallback else QColor(255, 255, 255, 20)

    def setup_animation_handles(self) -> None:
        self.indicator_handle = ui_engine.bind(
            owner      = self,
            name       = "indicator",
            base_value = QRectF(),
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_indicator_changed
        )

        self.hover_rectangle_handle = ui_engine.bind(
            owner      = self,
            name       = "hoverRectangle",
            base_value = QRectF(),
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_hover_rectangle_changed
        )

        self.hover_opacity_handle = ui_engine.bind(
            owner      = self,
            name       = "hoverOpacity",
            base_value = 0.0,
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_hover_opacity_changed
        )
    
    def on_indicator_changed(self, rectangle: QRectF) -> None:
        self.update()

    def on_hover_rectangle_changed(self, rectangle: QRectF) -> None:
        self.update()

    def on_hover_opacity_changed(self, opacity: float) -> None:
        self.update()

    def setup_layout(
            self,
            items:            list[str] | dict,
            button_font_size: int,
            button_style:     str
        ) -> None:

        self.layout = QHBoxLayout(self)

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        self.group = QButtonGroup(self)

        self.group.buttonClicked.connect(self.on_button_clicked)
        self.group.setExclusive(True)

        source = items.items() if isinstance(items, dict) else ((identifier, identifier) for identifier in items)

        for index, (text, data) in enumerate(source):
            self.add_button(index, text, data, button_font_size, button_style)

    def add_button(
            self,
            index:            int,
            text:             str,
            data:             object,
            button_font_size: int,
            button_style:     str
        ) -> None:

        button = QPushButton(text, self, objectName = "segmentedButton")

        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFont(Utils.NType(button_font_size))
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        button.setMinimumHeight(30)

        button.setStyleSheet(f"""
            QPushButton#segmentedButton {{
                {button_style}
            }}

            QPushButton#segmentedButton,
            QPushButton#segmentedButton:checked,
            QPushButton#segmentedButton:hover,
            QPushButton#segmentedButton:hover:checked {{
                background-color: transparent;
            }}
        """)

        button.installEventFilter(self)

        self.layout.addWidget(button)
        self.group.addButton(button, index)

        self.data_by_identifier[index] = data
        self.buttons.append(button)

    def eventFilter(
            self,
            watched: QObject,
            event:   QEvent
        ) -> bool:

        if not isinstance(watched, QPushButton):
            return super().eventFilter(watched, event)

        if event.type() == QEvent.Type.Enter:
            self.handle_hover_enter(watched)

        elif event.type() == QEvent.Type.Leave:
            self.handle_hover_leave()

        return super().eventFilter(watched, event)

    def handle_hover_enter(self, watched: QPushButton) -> None:
        target_rectangle = QRectF(watched.geometry())

        if self.hover_opacity_handle.value == 0.0 or self.hover_rectangle_handle.value.isNull():
            self.hover_rectangle_handle.set_base(target_rectangle)

        self.hover_rectangle_handle.set_target(
            value           = target_rectangle,
            duration_ms     = 200,
            easing_function = Easing.ease_out_quint
        )

        self.hover_opacity_handle.set_target(
            value           = 1.0,
            duration_ms     = 150,
            easing_function = Easing.ease_in_out_sine
        )

        button_count = len(self.buttons)
        button_index = self.group.id(watched)
        tone         = 0.8 + (button_index / (button_count - 1)) * 0.4 if button_count > 1 else 1.0

        Player.ui_player.play_sound(
            "Click/Selector/Hover",
            speed       = tone,
            setting_key = "selector_sounds"
        )

    def handle_hover_leave(self) -> None:
        self.hover_opacity_handle.set_target(
            value           = 0.0,
            duration_ms     = 150,
            easing_function = Easing.ease_in_out_sine
        )

    def paintEvent(self, event: QEvent) -> None:
        super().paintEvent(event)

        painter = QPainter(self)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        self.draw_hover_pill(painter)
        self.draw_main_pill(painter)

    def draw_hover_pill(self, painter: QPainter) -> None:
        opacity   = self.hover_opacity_handle.value
        rectangle = self.hover_rectangle_handle.value

        if opacity <= 0.0 or rectangle.isNull():
            return

        if rectangle.width() <= 0 or rectangle.height() <= 0:
            return

        painter.setOpacity(opacity)
        painter.setBrush(QBrush(self.hover_color))

        path = QPainterPath()

        path.addRoundedRect(rectangle, self.corner_radius, self.corner_radius)
        painter.drawPath(path)

    def draw_main_pill(self, painter: QPainter) -> None:
        rectangle = self.indicator_handle.value

        if not self.has_indicator or rectangle.isNull():
            return

        if rectangle.width() <= 0 or rectangle.height() <= 0:
            return

        painter.setOpacity(1.0)
        painter.setBrush(QBrush(self.pill_color))

        path = QPainterPath()

        path.addRoundedRect(rectangle, self.corner_radius, self.corner_radius)
        painter.drawPath(path)

    def showEvent(self, event: QEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.animate_entrance)

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)

        checked_identifier = self.group.checkedId()

        if checked_identifier == -1:
            return

        self.move_indicator(checked_identifier, animated = False)

    def on_button_clicked(self, button: QPushButton) -> None:
        count = len(self.group.buttons())
        index = self.group.id(button)

        multiplier = 1.75
        tone       = 1.0 + (index / (count - 1)) * (multiplier - 1.0) if count > 1 else 1.0

        Player.ui_player.play_sound(
            "Click/Selector/Confirm",
            speed       = tone,
            setting_key = "selector_sounds"
        )

        self.select_index(index, animated = True, emit = True)

    def animate_entrance(self) -> None:
        checked_button = self.group.checkedButton()

        if not checked_button:
            return

        index = self.group.id(checked_button)

        if index == -1:
            return

        target_rectangle = QRectF(checked_button.geometry())
        start_rectangle   = QRectF(target_rectangle.translated(-self.width(), 0))

        self.has_indicator = True
        self.indicator_handle.set_base(start_rectangle)

        self.indicator_handle.set_target(
            value           = target_rectangle,
            duration_ms     = random.randint(200, 500),
            easing_function = Easing.ease_out_quint
        )

    def move_indicator(
            self,
            index:    int,
            animated: bool = True
        ) -> None:

        button = self.group.button(index)

        if not button:
            return

        target_rectangle = QRectF(button.geometry())

        self.has_indicator = True

        if not animated:
            self.indicator_handle.set_base(target_rectangle)
            return

        self.indicator_handle.set_target(
            value           = target_rectangle,
            duration_ms     = 300,
            easing_function = Easing.ease_out_quint
        )

    def select_index(
            self,
            index:    int,
            animated: bool = True,
            emit:     bool = False
        ) -> None:

        count = len(self.buttons)

        if index < 0 and count > 0:
            index = count + index

        button = self.group.button(index)

        if not button:
            return

        button.setChecked(True)
        self.move_indicator(index, animated = animated)

        if not emit:
            return

        self.selectionChanged.emit(
            index,
            button.text(),
            self.data_by_identifier.get(index)
        )

    def select_text(
            self,
            text:     str,
            animated: bool = True,
            emit:     bool = False
        ) -> None:

        for button in self.group.buttons():
            if button.text() != text:
                continue

            self.select_index(self.group.id(button), animated = animated, emit = emit)
            return

    def select_data(
            self,
            value:    object,
            animated: bool = True,
            emit:     bool = False
        ) -> None:

        for index, data in self.data_by_identifier.items():
            if str(data) != str(value):
                continue

            self.select_index(index, animated = animated, emit = emit)
            return

    def current_index(self) -> int:
        return self.group.checkedId()

    def current_text(self) -> str:
        checked_button = self.group.checkedButton()

        if not checked_button:
            return ""

        return checked_button.text()

    def current_data(self) -> object:
        return self.data_by_identifier.get(self.group.checkedId())

@Dev.track_ram
class Selector(QWidget):
    selectionChanged = pyqtSignal(int, str)

    def __init__(
            self,
            items:         list[str],
            default_index: int = 0
        ) -> None:

        super().__init__()

        self.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout = QVBoxLayout(self)

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.strip = SegmentedStrip(
            items            = items,
            pill_color       = Styles.Colors.NothingAccent,
            button_font_size = 12,
            button_style     = "background: transparent;"
        )

        self.strip.selectionChanged.connect(self.on_selection_changed)
        self.strip.setFixedHeight(40)

        self.layout.addWidget(self.strip)

        if not items:
            return

        self.set_current_index(default_index)

    def on_selection_changed(
            self,
            index: int,
            text:  str,
            data:  object
        ) -> None:

        self.selectionChanged.emit(index, text)

    def current_index(self) -> int:
        return self.strip.current_index()

    def set_current_index(self, index: int) -> None:
        self.strip.select_index(index, animated = False, emit = False)

    def current_text(self) -> str:
        return self.strip.current_text()

    def set_current_text(self, text: str) -> None:
        self.strip.select_text(text, animated = False, emit = False)

    def set_value(self, value: int | str) -> None:
        if isinstance(value, int):
            self.set_current_index(value)
            return

        self.set_current_text(str(value))

    def get_value_as_text(self) -> str:
        return self.current_text()

@Dev.track_ram
class SelectorWithLabel(BaseControlContainer):
    selectionChanged = pyqtSignal(int, str, object)

    def __init__(
            self,
            description:   str,
            items:         list[str] | dict,
            default_text:  str | None = None,
            default_value: object     = None
        ) -> None:

        super().__init__()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.inner_layout.setContentsMargins(12, 8, 12, 12)

        self.setup_label(description)
        self.setup_strip(items, default_text, default_value)

    def setup_label(self, description: str) -> None:
        self.label = QLabel(description, self.container_background)

        self.label.setFont(Utils.NType(11))
        self.label.setStyleSheet(Styles.Other.Label)

        self.inner_layout.addWidget(self.label)

    def setup_strip(
            self,
            items:         list[str] | dict,
            default_text:  str       | None,
            default_value: object    | None
        ) -> None:

        self.strip = SegmentedStrip(
            items         = items,
            default_text  = default_text,
            default_value = default_value
        )

        self.strip.selectionChanged.connect(self.selectionChanged.emit)
        self.inner_layout.addWidget(self.strip)

    def current_index(self) -> int:
        return self.strip.current_index()

    def current_text(self) -> str:
        return self.strip.current_text()

    def current_data(self) -> object:
        return self.strip.current_data()

    def set_current_text(self, text: str) -> None:
        self.strip.select_text(text, animated = False, emit = False)

    def set_current_data(self, key: object) -> None:
        self.strip.select_data(key, animated = False, emit = False)