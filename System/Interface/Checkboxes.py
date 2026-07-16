from PyQt6.QtCore import (
    Qt,
    QSize,
    QEvent,
    QRectF,
    pyqtSignal
)

from PyQt6.QtGui import (
    QPen,
    QColor,
    QPainter,
    QHideEvent,
    QShowEvent,
    QEnterEvent,
    QPaintEvent,
    QPainterPath
)

from PyQt6.QtWidgets import (
    QLabel,
    QCheckBox,
    QHBoxLayout
)

from System.Common import (
    Dev,
    Utils,
    Styles
)

from System.Interface.Animation.LoomEngine import (
    Easing,
    ui_engine
)

from System.Services import Player
from System.Interface.Controls import BaseControlContainer

# Pixel Parsing

def pixel_size(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)

    digits = "".join(character for character in str(value) if character.isdigit() or character == ".")

    return float(digits) if digits else 0.0

# Checkbox

@Dev.track_ram
class Checkbox(QCheckBox):
    overflow_padding:       int   = 4
    resting_radius:         float = 4.0
    label_spacing:          int   = 6
    default_border:         str   = "#555555"
    indicator_visual_scale: float = 1.3

    def __init__(
            self,
            name:    str,
            default: bool = False
        ) -> None:

        super().__init__(name)

        self.setFont(Utils.NType(10))
        self.setChecked(default)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self.hovered = False

        self.indicator_scale = ui_engine.bind(
            owner      = self,
            name       = "indicatorScale",
            base_value = 1.0,
            on_change  = self.on_indicator_property_changed
        )

        self.indicator_radius = ui_engine.bind(
            owner      = self,
            name       = "indicatorRadius",
            base_value = self.resting_radius,
            on_change  = self.on_indicator_property_changed
        )

        self.destroyed.connect(lambda: ui_engine.unbind_owner(self))

    def on_indicator_property_changed(self, value: float) -> None:
        self.update()

    def nextCheckState(self) -> None:
        super().nextCheckState()

        tone = 1.0 if self.isChecked() else 0.82
        Player.ui_player.play_sound("Click/Checkbox", setting_key = "checkbox_sounds", speed = tone)

        self.indicator_scale.set_base(1.5)
        self.indicator_radius.set_base(0.0)

        self.indicator_scale.set_target(
            value           = 1.0,
            duration_ms     = 180,
            easing_function = Easing.ease_out_quad
        )

        self.indicator_radius.set_target(
            value           = self.resting_radius,
            duration_ms     = 180,
            easing_function = Easing.ease_out_quad
        )

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)

        self.hovered = True
        self.update()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)

        self.hovered = False
        self.update()

    def content_rect(self) -> QRectF:
        padding = self.overflow_padding

        return QRectF(self.rect().adjusted(padding, padding, -padding, -padding))

    def indicator_size(self) -> float:
        return pixel_size(Styles.Metrics.CheckboxSize)

    def border_width(self) -> float:
        return pixel_size(Styles.Metrics.GlassBorderThick)

    def sizeHint(self) -> QSize:
        metrics    = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self.text())
        size       = int(self.indicator_size())

        width  = size + self.label_spacing + text_width
        height = max(size, metrics.height())

        return QSize(width + self.overflow_padding * 2, height + self.overflow_padding * 2)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        ui_engine.acquire()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        ui_engine.release()

    def indicator_colors(self) -> tuple[QColor, QColor]:
        if self.isChecked():
            return QColor(Styles.Colors.NothingAccent), QColor(Styles.Colors.NothingAccent)

        if self.hovered:
            return QColor(Styles.Colors.EffectMenu.Hover), QColor(Styles.Colors.NothingAccentPressed)

        return QColor(Styles.Colors.EffectMenu.Hover), QColor(self.default_border)

    def layout_rects(self) -> tuple[QRectF, QRectF]:
        content_rect = self.content_rect()
        size         = self.indicator_size()

        indicator_rect = QRectF(
            content_rect.left(),
            content_rect.top() + (content_rect.height() - size) / 2,
            size,
            size
        )

        label_rect = QRectF(
            indicator_rect.right() + self.label_spacing,
            content_rect.top() - 1,
            content_rect.right() - indicator_rect.right() - self.label_spacing,
            content_rect.height()
        )

        return indicator_rect, label_rect

    def paintEvent(self, event: QPaintEvent) -> None:
        indicator_rect, label_rect = self.layout_rects()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(QColor(Styles.Colors.FontColor))
        painter.setFont(self.font())
        painter.drawText(label_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.text())

        background_color, border_color = self.indicator_colors()
        border_width                   = self.border_width()

        scale  = self.indicator_scale.value
        radius = self.indicator_radius.value
        center = indicator_rect.center()

        painter.save()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-center)

        stroked_rect = indicator_rect.adjusted(
            border_width / 2,
            border_width / 2,
            -border_width / 2,
            -border_width / 2
        )

        path = QPainterPath()
        path.addRoundedRect(stroked_rect, radius, radius)

        painter.setBrush(background_color)
        painter.setPen(QPen(border_color, border_width))
        painter.drawPath(path)

        painter.restore()

@Dev.track_ram
class CheckboxWithLabel(BaseControlContainer):
    stateChanged = pyqtSignal(bool)

    def __init__(
            self,
            title:       str,
            description: str,
            default:     bool = False
        ) -> None:

        super().__init__(inner_layout_type = QHBoxLayout)
 
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

    def setup_description(self, description: str) -> None:
        self.description_label = QLabel(description, self.container_background)
        self.description_label.setFont(Utils.NType(10))
        self.description_label.setStyleSheet(f"color: {Styles.Colors.SubtleFontColor}; padding: 0px; border: none;")
        self.inner_layout.addWidget(self.description_label, 1, Qt.AlignmentFlag.AlignVCenter)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)
        self.stateChanged.emit(checked)

    def setValue(self, value: bool) -> None:
        self.setChecked(value)