from __future__ import annotations

from PyQt6.QtCore import (
    Qt,
    QRect,
    QPoint,
    QPointF
)

from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPaintEvent,
    QFontMetrics
)

from PyQt6.QtWidgets import QWidget

from System.Common import (
    Dev,
    Utils,
    Styles,
    Constants
)

from System.Interface import Timing

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine
)

@Dev.track_ram
class ValuePopup(Lifecycle.LoomAnimationMixin, QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.padding_px = 7
        self.text       = ""
        self.font       = Utils.NType(10)

        self.setup_animations()
        self.move(160, 160)
        self.resize(1, 1)

    # Setup

    def setup_animations(self) -> None:
        self.opacity_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "opacity",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_opacity_updated
        )

        self.rectangle_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "rect",
            base_value = QRect(),
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_geometry_updated
        )

        self.manual_hide_timer = Timing.Timer(
            1000,
            self.hide,
            single_shot = True,
            parent      = self
        )

        self.final_hide_timer = Timing.Timer(
            300,
            self.on_hide_finished,
            single_shot = True,
            parent      = self
        )

        self.cached_background_color = QColor(Styles.Colors.SecondaryBackground)
        self.cached_text_color       = QColor(Qt.GlobalColor.white)

    # Painting

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        alpha_channel = int(self.opacity_handle.value * 255)

        background_color = QColor(self.cached_background_color)
        background_color.setAlpha(alpha_channel)

        painter.setBrush(background_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 6.5, 6.5)

        text_color = QColor(self.cached_text_color)
        text_color.setAlpha(alpha_channel)

        painter.setPen(text_color)
        painter.setFont(self.font)
        painter.translate(self.padding_px, self.padding_px)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft, self.text)

    # Helpers

    def layout_for_text(self, text: str) -> tuple[int, int]:
        metrics        = QFontMetrics(self.font)
        text_rectangle = metrics.boundingRect(0, 0, 700, 1000, Qt.TextFlag.TextWordWrap, text)

        width_px  = text_rectangle.width()  + self.padding_px * 2
        height_px = text_rectangle.height() + self.padding_px * 2

        return width_px, height_px

    def compute_top_left(
            self,
            position: QPoint,
            width_px: int
        ) -> tuple[int, int]:

        desired_x_px = position.x() - width_px // 2
        desired_y_px = position.y() + 5

        return desired_x_px, desired_y_px

    # Callbacks

    def on_geometry_updated(self, geometry: QRect) -> None:
        self.move(geometry.topLeft())
        self.resize(geometry.size())
        self.update()

    def on_opacity_updated(self, opacity: float) -> None:
        self.update()

    def on_hide_finished(self) -> None:
        super().hide()

    # Api

    def show_text(
            self,
            text:      str,
            position:  QPoint,
            auto_hide: bool = False
        ) -> None:

        if auto_hide:
            self.final_hide_timer.stop()
            self.manual_hide_timer.stop()
            self.manual_hide_timer.start()

        width_px, height_px = self.layout_for_text(text)
        x_px, y_px          = self.compute_top_left(position, width_px)

        self.text = text

        if self.parent():
            parent_position = self.parent().mapFromGlobal(QPoint(x_px, y_px))
            x_px            = parent_position.x()
            y_px            = parent_position.y()

        self.rectangle_handle.set_target(
            value           = QRect(x_px, y_px, width_px, height_px),
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        self.show()

    def fade_in(self) -> None:
        self.opacity_handle.set_target(
            value           = 1.0,
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    def fade_out(self) -> None:
        self.opacity_handle.set_target(
            value           = 0.0,
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        self.final_hide_timer.start()

    def show(self) -> None:
        self.fade_in()
        super().show()

    def hide(self) -> None:
        self.fade_out()

    def cleanup(self) -> None:
        super().hide()
        self.deleteLater()

class Tooltip(ValuePopup):
    def __init__(self, conductor) -> None:
        super().__init__(conductor)

        self.conductor       = conductor
        self.is_hide_planned = False

    # Helpers

    def calculate_position(self, target_item = None) -> QPoint:
        viewport = self.conductor.viewport()

        if not target_item:
            selected_items = self.conductor.scene.selectedItems()
            target_item    = selected_items[0] if selected_items else None

        if not target_item:
            return self.conductor.mapToGlobal(viewport.rect().center())

        bounding_box   = target_item.boundingRect()
        bottom_center  = QPointF(bounding_box.center().x(), bounding_box.bottom())
        scene_position = target_item.mapToScene(bottom_center)
        view_position  = self.conductor.mapFromScene(scene_position)

        view_x_px = max(10, min(view_position.x(), viewport.width() - 10))
        view_y_px = view_position.y() + 10

        return viewport.mapToGlobal(QPoint(int(view_x_px), int(view_y_px)))

    # Api

    def show_tooltip_at(
            self,
            text:        str,
            target_item  = None,
            plan_hide:   bool = False
        ) -> None:

        self.is_hide_planned = plan_hide
        self.show_text(text, self.calculate_position(target_item), plan_hide)

    def hide_tooltip(self) -> None:
        if not self.is_hide_planned:
            self.hide()

    def show_hover_tooltip(self, item) -> None:
        glyph = self.conductor.composition.get_glyph(item.glyph_id)

        if glyph is None:
            return

        effect_name = f"Effect: {glyph['effect']['name']}" if "effect" in glyph else "No effect"
        brightness  = glyph["brightness"] if "brightness" in glyph else 0

        information = [
            f"Start: {glyph['start']} ms",
            f"Duration: {glyph['duration']} ms",
            f"Brightness: {brightness}%",
            effect_name
        ]

        self.show_tooltip_at("\n".join(information), item)