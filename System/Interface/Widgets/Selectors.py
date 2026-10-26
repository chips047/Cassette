from __future__ import annotations

import random

from PyQt6.QtCore import (
    Qt,
    QRectF,
    QEvent,
    QTimer,
    QObject,
    pyqtSignal
)

from PyQt6.QtGui import (
    QFont,
    QBrush,
    QColor,
    QPainter,
    QWheelEvent,
    QFontMetrics,
    QPainterPath
)

from PyQt6.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QSizePolicy,
    QButtonGroup
)

from System.Common import (
    Dev,
    Utils,
    Styles
)

from System.Services import (
    Player,
    Haptics
)

from System.Interface import Widgets

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine
)

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
            switch_sound:     str        = "Controls/Selector/Select"
        ) -> None:

        super().__init__()

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.pill_color        = QColor(pill_color) if pill_color else QColor(Styles.Colors.NothingAccent)
        self.hover_color       = self.resolve_hover_color(hover_color)
        self.hovered_button    = None
        self.has_indicator     = False
        self.switch_sound      = switch_sound
        self.wheel_accumulator = 0.0

        self.data_by_identifier: dict[int, object] = {}
        self.buttons:            list[QPushButton] = []

        self.setup_layout(items, button_font_size)
        self.setup_animation_handles()

        self.setStyleSheet(Styles.Controls.Selector)

        has_selection = False

        if default_value is not None:
            has_selection = self.select_data(default_value, animated = False)

        if not has_selection and default_text is not None:
            has_selection = self.select_text(default_text, animated = False)

        if not has_selection and self.group.buttons():
            first_button = self.group.buttons()[0]
            first_index  = self.group.id(first_button)
            self.select_index(first_index, animated = False, emit = False)

        QTimer.singleShot(0, self.animate_entrance)

    @staticmethod
    def values_match(
            first:  object,
            second: object
        ) -> bool:

        if first == second:
            return True

        if first is None or second is None:
            return False

        try:
            if float(first) == float(second):
                return True

        except (ValueError, TypeError):
            pass

        return str(first).strip().lower() == str(second).strip().lower()

    def resolve_hover_color(self, hover_color: object) -> QColor:
        if hover_color:
            return QColor(hover_color)

        return QColor(Styles.Colors.ThirdBackground)

    def setup_animation_handles(self) -> None:
        self.indicator_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "indicator",
            base_value = QRectF(),
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_indicator_changed
        )

        self.hover_rectangle_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "hover_rectangle",
            base_value = QRectF(),
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_hover_rectangle_changed
        )

        self.hover_opacity_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "hover_opacity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_hover_opacity_changed
        )

    def setup_layout(
            self,
            items:            list[str] | dict,
            button_font_size: int
        ) -> None:

        self.layout = QHBoxLayout(self)

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        self.group = QButtonGroup(self)

        self.group.buttonClicked.connect(self.on_button_clicked)
        self.group.setExclusive(True)

        source = items.items() if isinstance(items, dict) else ((identifier, identifier) for identifier in items)

        for index, (text, data) in enumerate(source):
            self.add_button(index, text, data, button_font_size)

    def add_button(
            self,
            index:            int,
            text:             str,
            data:             object,
            button_font_size: int
        ) -> None:

        button = QPushButton(text, self, objectName = "segmentedButton")

        button.setCheckable(True)
        button.setFont(Utils.NType(button_font_size))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        button.setMinimumHeight(30)

        button.setStyleSheet(Styles.Controls.SelectorButton)
        button.installEventFilter(self)

        self.layout.addWidget(button)
        self.group.addButton(button, index)

        self.data_by_identifier[index] = data
        self.buttons.append(button)

    # Layout and Sizing

    def update_button_widths(self) -> None:
        button_count = len(self.buttons)

        if button_count == 0:
            return

        total_spacing   = (button_count - 1) * self.layout.spacing()
        available_width = self.width() - total_spacing

        if available_width <= 0:
            return

        text_widths: list[int] = []

        for button in self.buttons:
            font_metrics = QFontMetrics(button.font())
            text_width   = font_metrics.horizontalAdvance(button.text())
            text_widths.append(text_width)

        total_text_width = sum(text_widths)
        remaining_space  = available_width - total_text_width

        if remaining_space > 0:
            extra_per_button = remaining_space // button_count
            remainder_pixels = remaining_space % button_count

            for index, button in enumerate(self.buttons):
                bonus_pixel  = 1 if index < remainder_pixels else 0
                target_width = text_widths[index] + extra_per_button + bonus_pixel
                button.setFixedWidth(int(target_width))

            return

        minimum_padding = 16

        for index, button in enumerate(self.buttons):
            button.setFixedWidth(text_widths[index] + minimum_padding)

    # Event Handlers

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
        self.hovered_button = watched
        target_rectangle    = QRectF(watched.geometry())

        if self.hover_opacity_handle.value == 0.0 or self.hover_rectangle_handle.value.isNull():
            self.hover_rectangle_handle.set_base(target_rectangle)

        self.hover_rectangle_handle.set_target(
            value           = target_rectangle,
            duration_ms     = 200,
            easing_function = LoomEngine.Easing.ease_out_quint
        )

        self.hover_opacity_handle.set_target(
            value           = 1.0,
            duration_ms     = 150,
            easing_function = LoomEngine.Easing.ease_in_out_sine
        )

        button_count = len(self.buttons)
        button_index = self.group.id(watched)
        tone         = 0.8 + (button_index / (button_count - 1)) * 0.4 if button_count > 1 else 1.0
        pan          = self.pan_ratio(button_index, button_count)

        Player.ui_player.play_sound(
            name        = "Controls/Selector/Hover",
            speed       = tone,
            pan         = pan,
            setting_key = "selector_sounds",
            volume      = 0.8
        )

    def handle_hover_leave(self) -> None:
        self.hovered_button = None

        self.hover_opacity_handle.set_target(
            value           = 0.0,
            duration_ms     = 150,
            easing_function = LoomEngine.Easing.ease_in_out_sine
        )

    def paintEvent(self, event: QEvent) -> None:
        super().paintEvent(event)

        painter = QPainter(self)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        self.draw_hover_pill(painter)
        self.draw_main_pill(painter)

    def showEvent(self, event: QEvent) -> None:
        super().showEvent(event)

        self.update_button_widths()
        self.layout.activate()

        QTimer.singleShot(0, self.animate_entrance)

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)

        self.update_button_widths()
        self.layout.activate()

        if self.hovered_button:
            self.hover_rectangle_handle.set_base(QRectF(self.hovered_button.geometry()))

        checked_identifier = self.group.checkedId()

        if checked_identifier == -1:
            return

        self.move_indicator(checked_identifier, animated = False)

    def wheelEvent(self, event: QWheelEvent) -> None:
        is_horizontal = event.angleDelta().x() != 0 or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if not is_horizontal:
            event.ignore()
            return

        delta = event.angleDelta().x() if event.angleDelta().x() != 0 else event.angleDelta().y()

        if delta == 0:
            event.ignore()
            return

        self.wheel_accumulator += delta
        threshold               = 1000.0

        if abs(self.wheel_accumulator) < threshold:
            event.accept()
            return

        steps                  = int(self.wheel_accumulator / threshold)
        self.wheel_accumulator = 0.0

        current_index = self.current_index()
        button_count  = len(self.buttons)

        if button_count <= 1:
            event.accept()
            return

        direction = 1 if steps > 0 else -1
        new_index = max(0, min(button_count - 1, current_index + direction))

        if new_index == current_index:
            event.accept()
            return

        button = self.group.button(new_index)

        if not button:
            event.accept()
            return

        self.on_button_clicked(button)
        event.accept()

    def on_button_clicked(self, button: QPushButton) -> None:
        count = len(self.group.buttons())
        index = self.group.id(button)

        multiplier = 1.75
        tone       = 1.0 + (index / (count - 1)) * (multiplier - 1.0) if count > 1 else 1.0
        pan        = self.pan_ratio(index, count)

        Player.ui_player.play_sound(
            name        = self.switch_sound,
            speed       = tone,
            pan         = pan,
            setting_key = "selector_sounds",
            volume      = 0.8
        )

        Haptics.ui_haptics.snap()

        self.select_index(index, animated = True, emit = True)

    # Indicator and Hover Animation

    def on_indicator_changed(self, rectangle: QRectF) -> None:
        self.update()

    def on_hover_opacity_changed(self, opacity: float) -> None:
        self.update()

    def on_hover_rectangle_changed(self, rectangle: QRectF) -> None:
        self.update()

    def animate_entrance(self) -> None:
        checked_button = self.group.checkedButton()

        if not checked_button:
            return

        index = self.group.id(checked_button)

        if index == -1:
            return

        target_rectangle   = QRectF(checked_button.geometry())
        start_rectangle    = QRectF(target_rectangle.translated(-self.width(), 0))
        self.has_indicator = True

        self.indicator_handle.set_base(start_rectangle)

        self.indicator_handle.set_target(
            value           = target_rectangle,
            duration_ms     = random.randint(200, 600),
            easing_function = LoomEngine.Easing.ease_out_quint
        )

    def move_indicator(
            self,
            index:    int,
            animated: bool = True
        ) -> None:

        button = self.group.button(index)

        if not button:
            return

        target_rectangle   = QRectF(button.geometry())
        self.has_indicator = True

        if not animated:
            self.indicator_handle.set_base(target_rectangle)
            return

        self.indicator_handle.set_target(
            value           = target_rectangle,
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_quint
        )

    # Drawing Methods

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

    # Selection and State

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
        ) -> bool:

        for button in self.group.buttons():
            if not self.values_match(button.text(), text):
                continue

            self.select_index(self.group.id(button), animated = animated, emit = emit)
            return True

        for index, data in self.data_by_identifier.items():
            if not self.values_match(data, text):
                continue

            self.select_index(index, animated = animated, emit = emit)
            return True

        return False

    def select_data(
            self,
            value:    object,
            animated: bool = True,
            emit:     bool = False
        ) -> bool:

        for index, data in self.data_by_identifier.items():
            if not self.values_match(data, value):
                continue

            self.select_index(index, animated = animated, emit = emit)
            return True

        for button in self.group.buttons():
            if not self.values_match(button.text(), value):
                continue

            self.select_index(self.group.id(button), animated = animated, emit = emit)
            return True

        return False

    def current_index(self) -> int:
        checked_identifier = self.group.checkedId()

        if checked_identifier != -1:
            return checked_identifier

        if self.buttons:
            return self.group.id(self.buttons[0])

        return -1

    def current_text(self) -> str:
        checked_button = self.group.checkedButton()

        if checked_button is not None:
            return checked_button.text()

        if self.buttons:
            return self.buttons[0].text()

        return ""

    def current_data(self) -> object:
        checked_identifier = self.group.checkedId()

        if checked_identifier in self.data_by_identifier:
            return self.data_by_identifier[checked_identifier]

        if self.buttons:
            first_button = self.buttons[0]
            first_index  = self.group.id(first_button)

            return self.data_by_identifier.get(first_index)

        return None

    # Helpers and Properties

    def setFont(self, font: QFont) -> None:
        for button in self.group.buttons():
            button.setFont(font)

        super().setFont(font)
        self.update_button_widths()

    def pan_ratio(
            self,
            index: int,
            count: int
        ) -> float:

        if count <= 1:
            return 0.0

        return (index / (count - 1)) * 2.0 - 1.0

@Dev.track_ram
class Selector(QWidget):
    selectionChanged = pyqtSignal(int, str)

    def __init__(
            self,
            items:         list[str] | dict,
            default_index: int = 0,
            switch_sound:  str = "Controls/Selector/Select"
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
            switch_sound     = switch_sound
        )

        self.strip.selectionChanged.connect(self.on_selection_changed)
        self.strip.setFixedHeight(40)

        self.layout.addWidget(self.strip)

        if not items:
            return

        self.set_current_index(default_index)

    # Event Handlers

    def on_selection_changed(
            self,
            index: int,
            text:  str,
            data:  object
        ) -> None:

        self.selectionChanged.emit(index, text)

    # State Access and Helpers

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

    def setFont(self, font: QFont) -> None:
        self.strip.setFont(font)
        super().setFont(font)

@Dev.track_ram
class SelectorWithLabel(Widgets.BaseControlContainer):
    selectionChanged = pyqtSignal(int, str, object)

    def __init__(
            self,
            description:   str,
            items:         list[str] | dict,
            default_text:  str | None = None,
            default_value: object     = None,
            switch_sound:  str        = "Controls/Selector/Select"
        ) -> None:

        super().__init__()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.inner_layout.setContentsMargins(12, 8, 12, 12)

        self.setup_label(description)
        self.setup_strip(items, default_text, default_value, switch_sound)

    def setup_label(self, description: str) -> None:
        self.label = QLabel(description, self.container_background)

        self.label.setFont(Utils.NType(11))
        self.label.setStyleSheet(Styles.Other.Label)

        self.inner_layout.addWidget(self.label)

    def setup_strip(
            self,
            items:         list[str] | dict,
            default_text:  str       | None,
            default_value: object    | None,
            switch_sound:  str
        ) -> None:

        self.strip = SegmentedStrip(
            items         = items,
            default_text  = default_text,
            default_value = default_value,
            switch_sound  = switch_sound
        )

        self.strip.selectionChanged.connect(self.selectionChanged.emit)
        self.inner_layout.addWidget(self.strip)

    # State Access and Helpers

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

    def setFont(self, font: QFont) -> None:
        self.strip.setFont(font)
        super().setFont(font)