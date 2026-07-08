from PyQt6.QtGui import (
    QIcon,
    QMouseEvent
)

from PyQt6.QtCore import (
    Qt,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QWidget,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout
)

from System.Common import (
    Dev,
    Utils,
    Styles
)

# Base Control Container

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

    def setup_layout(self, inner_layout_type: type) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.container_background = QFrame(self)
        self.container_background.setStyleSheet(Styles.Controls.SliderBackground)

        self.inner_layout = inner_layout_type(self.container_background)
        self.inner_layout.setContentsMargins(12, 8, 12, 8)
        self.inner_layout.setSpacing(8)

        main_layout.addWidget(self.container_background)

# Base Control Widget

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
            alignment = Qt.AlignmentFlag.AlignVCenter
        )

# Draggable Value Control

@Dev.track_ram
class DraggableValueControl(BaseControlWidget):
    valueChanged = pyqtSignal(int)

    def __init__(
            self,
            icon:              QIcon   | None = None,
            static_label_text: str     | None = None,
            initial_value:     int            = 100,
            minimum_value:     int            = 0,
            maximum_value:     int            = 200,
            step:              int            = 5,
            unit_suffix:       str            = "",
            parent:            QWidget | None = None
        ) -> None:

        super().__init__(icon, static_label_text, parent)

        self.initial_value = initial_value
        self.current_value = initial_value
        self.minimum_value = minimum_value
        self.maximum_value = maximum_value
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        self.dragging         = True
        self.drag_start_x     = event.pos().x()
        self.drag_start_value = self.current_value

        self.setCursor(Qt.CursorShape.SizeHorCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.dragging:
            return

        pixels_per_step = 10
        delta_x         = event.pos().x() - self.drag_start_x
        steps           = delta_x // pixels_per_step

        new_value = self.drag_start_value + steps * self.step
        new_value = int(round(new_value / self.step)) * self.step
        new_value = max(self.minimum_value, min(self.maximum_value, new_value))

        if new_value != self.current_value:
            self.current_value = new_value
            self.update_value_label()

            self.valueChanged.emit(self.current_value)

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
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

# Cycle Button

@Dev.track_ram
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
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

    def show_state(self, emit: bool = True) -> None:
        display_text, value = self.states[self.current_state_index]
        self.value_label.setText(display_text)

        if emit:
            self.state_changed.emit(display_text, value)

    def reset(self) -> None:
        self.current_state_index = 0
        self.show_state(False)

    def get_current_value(self) -> object:
        return self.states[self.current_state_index][1]