from __future__ import annotations

import math
import copy
import bisect

from PyQt6.QtCore import (
    Qt,
    QRectF,
    QTimer,
    QPointF,
    pyqtSignal
)

from PyQt6.QtGui import (
    QPen,
    QBrush,
    QColor,
    QPainter,
    QTransform,
    QPainterPath
)

from PyQt6.QtWidgets import (
    QWidget,
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem
)

from System.Common import (
    Dev,
    Utils,
    Styles,
    Constants
)

from System.Services import (
    Player,
    GlyphEffects
)

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine
)

@Dev.track_ram
class PlayheadItem(Lifecycle.LoomAnimationMixin, QGraphicsObject):
    playhead_pressed = pyqtSignal()

    def __init__(
            self,
            conductor,
            custom_height_px: float | None = None
        ) -> None:

        super().__init__()

        self.conductor               = conductor
        self.width_px                = 2.0
        self.height_px               = custom_height_px
        self.target_horizontal_px    = 0.0
        self.last_emitted_normalized = None

        self.cached_pen = QPen(QColor(255, 0, 0), 2.0)
        self.cached_pen.setCosmetic(True)

        self.horizontal_animation = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "playheadX",
            base_value = 0.0,
            on_change  = self.update_actual_position
        )

    # Geometry

    def boundingRect(self) -> QRectF:
        return QRectF(
            -self.width_px / 2,
            0,
            self.width_px,
            self.height_px or self.conductor.height()
        )

    # Painting

    def paint(
            self,
            painter: QPainter,
            option:  QStyleOptionGraphicsItem,
            widget:  QWidget | None = None
        ) -> None:

        painter.setPen(self.cached_pen)
        painter.drawLine(0, 0, 0, int(self.height_px or self.conductor.height()))

    # Api

    def set_target_x(
            self,
            target_x_px: float,
            animate:     bool = False
        ) -> None:

        self.target_horizontal_px = target_x_px
        self.playhead_pressed.emit()

        if animate and Constants.current_settings.get("playhead_animations", True):
            distance_px = abs(target_x_px - self.horizontal_animation.value)
            duration_ms = int(min(420, max(120, 120 + distance_px * 0.12)))

            self.horizontal_animation.set_target(
                value           = target_x_px,
                duration_ms     = duration_ms,
                easing_function = LoomEngine.Easing.ease_out_expo
            )

        else:
            self.horizontal_animation.stop_targeting()
            self.horizontal_animation.set_base(target_x_px)

    def update_actual_position(self, horizontal_px: float) -> None:
        self.setPos(horizontal_px, 0)

        if self.conductor.total_content_width <= 0:
            return

        normalized_position = horizontal_px / self.conductor.total_content_width
        width_px            = max(1, self.conductor.width())
        threshold           = 1.0 / float(width_px)

        if self.last_emitted_normalized is not None and abs(normalized_position - self.last_emitted_normalized) < threshold:
            return

        self.last_emitted_normalized = normalized_position

        self.conductor.playhead_moved_ms.emit(horizontal_px / self.conductor.px_per_sec * 1000.0)
        self.conductor.playhead_moved_normalized.emit(normalized_position)

    def destroy(self) -> None:
        LoomEngine.ui_engine.unbind_owner(self)

@Dev.track_ram
class MarqueeItem(Lifecycle.LoomAnimationMixin, QGraphicsObject):
    def __init__(self, player: Player.PlaybackManager) -> None:
        super().__init__()

        self.player                 = player
        self.start_position         = QPointF()
        self.cached_brush_color     = QColor(255, 0, 0)
        self.cached_brush           = QBrush(self.cached_brush_color)
        self.cached_pen             = QPen(QColor(215, 20, 31), 1, Qt.PenStyle.DashLine)
        self.cached_pen_color       = QColor(self.cached_pen.color())

        self.setup_animations()
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.hide()

    # Setup

    def setup_animations(self) -> None:
        Player.bpm_informer.beat_4.connect(self.bpm_tick)

        self.bpm_pulse_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "bpmPulse",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD,
            on_change  = self.on_animation_updated
        )

        self.mouse_point_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "mousePoint",
            base_value = QPointF(),
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_animation_updated
        )

        self.start_position_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "startPosition",
            base_value = QPointF(),
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_animation_updated
        )

        self.brush_opacity_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "brushOpacity",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_animation_updated
        )

        self.pen_opacity_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "penOpacity",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_animation_updated
        )

    # Geometry

    def boundingRect(self) -> QRectF:
        return QRectF(
            self.start_position_handle.value,
            self.mouse_point_handle.value
        ).normalized()

    # Painting

    def apply_bpm_to_alpha(
            self,
            base_alpha: int,
            opacity:    float
        ) -> int:

        pulse_value = self.bpm_pulse_handle.value

        return int(base_alpha * opacity * (1.0 + pulse_value))

    def paint(
            self,
            painter: QPainter,
            option:  QStyleOptionGraphicsItem,
            widget:  QWidget | None = None
        ) -> None:

        brush_alpha = self.brush_opacity_handle.value
        pen_alpha   = self.pen_opacity_handle.value
        start_point = self.start_position_handle.value
        mouse_point = self.mouse_point_handle.value

        rectangle = QRectF(start_point, mouse_point).normalized()
        radius_px = min((rectangle.width() + rectangle.height()) / 12, 10)

        self.cached_brush_color.setAlpha(self.apply_bpm_to_alpha(50, brush_alpha))
        self.cached_brush = QBrush(self.cached_brush_color)

        self.cached_pen_color.setAlpha(int(200 * pen_alpha))
        self.cached_pen.setColor(self.cached_pen_color)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.cached_pen)
        painter.setBrush(self.cached_brush)
        painter.drawRoundedRect(rectangle, radius_px, radius_px)

    # Animations

    def fade_in(self) -> None:
        self.brush_opacity_handle.play_curve(
            keyframes       = [(0.0, self.brush_opacity_handle.value), (1.0, 1.0)],
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        self.pen_opacity_handle.play_curve(
            keyframes       = [(0.0, self.pen_opacity_handle.value), (1.0, 1.0)],
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    def fade_out(self) -> None:
        if not Constants.current_settings["marquee_hide_animation"]:
            self.brush_opacity_handle.set_base(0.0)
            self.pen_opacity_handle.set_base(0.0)
            self.finish_and_hide()

            return

        self.brush_opacity_handle.play_curve(
            keyframes       = [(0.0, self.brush_opacity_handle.value), (1.0, 0.0)],
            duration_ms     = 230,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        QTimer.singleShot(70, self.animate_pen_out)

    def animate_pen_out(self) -> None:
        self.pen_opacity_handle.play_curve(
            keyframes       = [(0.0, self.pen_opacity_handle.value), (1.0, 0.0)],
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic,
            finished        = self.finish_and_hide
        )

    def finish_and_hide(self) -> None:
        self.hide()

    # Api

    def start_marquee(self, start_point: QPointF) -> None:
        if self.isVisible():
            current_start = self.start_position_handle.value

            self.start_position_handle.play_curve(
                keyframes       = [(0.0, current_start), (1.0, start_point)],
                duration_ms     = 150,
                easing_function = LoomEngine.Easing.ease_out_cubic
            )

        else:
            self.mouse_point_handle.set_base(start_point)
            self.start_position_handle.set_base(start_point)

        self.fade_in()
        self.show()

    def end_marquee(self) -> None:
        self.fade_out()

    def update_end_point(
            self,
            point:   QPointF,
            animate: bool = True
        ) -> None:

        if animate:
            self.mouse_point_handle.set_target(
                value           = point,
                duration_ms     = 150,
                easing_function = LoomEngine.Easing.ease_out_cubic
            )

        else:
            self.mouse_point_handle.set_base(point)
            self.on_animation_updated()

        path = QPainterPath()
        path.addRect(QRectF(self.start_position_handle.value, point).normalized())

        modifiers = QApplication.keyboardModifiers()

        selection_operation = (
            Qt.ItemSelectionOperation.AddToSelection
            if modifiers & Qt.KeyboardModifier.ControlModifier
            else Qt.ItemSelectionOperation.ReplaceSelection
        )

        self.scene().setSelectionArea(
            path,
            selection_operation,
            Qt.ItemSelectionMode.IntersectsItemShape,
            QTransform()
        )

    # Callbacks

    def on_animation_updated(self, *arguments: object) -> None:
        self.prepareGeometryChange()
        self.update()

    def bpm_tick(self) -> None:
        if not self.player.is_playing:
            return

        if not self.isVisible():
            return

        if self.player.get_current_audio_level() < 0.08:
            return

        interval_ms = Player.bpm_informer.get_interval(4)

        self.bpm_pulse_handle.play_curve(
            keyframes                  = [(0.0, 0.5), (1.0, 0.0)],
            duration_ms                = interval_ms,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

class GlyphItem(Lifecycle.LoomAnimationMixin, QGraphicsObject):
    STACK_LABEL_FONT  = Utils.NType(9)
    STACK_LABEL_COLOR = QColor(0, 0, 0)

    def __init__(
            self,
            glyph_id:      int,
            conductor:     object,
            animate_spawn: bool = True
        ) -> None:

        super().__init__()

        self.hide()

        self.glyph_id  = glyph_id
        self.conductor = conductor

        self.was_clicked             = False
        self.border_width_px         = 2
        self.keyframe_line_padding   = 12
        self.keyframe_line_width_px  = 4
        self.resize_margin_px        = 10
        self.is_despawning           = False
        self.is_moving_horizontally  = False
        self.is_resizing_width       = False
        self.interaction_mode        = None
        self.current_width_px        = 0.0
        self.drag_start_position     = QPointF()

        self.cached_width_px         = -1.0
        self.cached_radius_px        = 0.0
        self.cached_border_pen       = QPen()
        self.cached_stack_label      = ""
        self.cached_stack_colors     = []

        self.cached_fade_pen         = QPen()
        self.cached_fade_brush       = QBrush()
        self.cached_border_color     = QColor(255, 0, 0, 255)
        self.cached_stack_color_pool = [QColor(220, 220, 220), QColor(220, 220, 220), QColor(220, 220, 220)]

        self.cached_border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.cached_border_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.cached_border_pen.setWidthF(self.border_width_px)

        self.cached_fade_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.cached_fade_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.cached_fade_pen.setWidthF(self.keyframe_line_width_px)

        self.setup_animations()
        self.setup_flags()
        self.setup_keyframes()

        self.fixed_y_px = self.calculate_y_pos()

        self.update_geometry()
        self.spawn_animation(animate_spawn)

        self.show()

    # Properties

    @property
    def data(self) -> dict | None:
        return self.conductor.composition.get_glyph(self.glyph_id)

    @property
    def duration_ms(self) -> int:
        data = self.data

        if data:
            return data["duration"]

        if self.despawn_duration_ms is not None:
            return self.despawn_duration_ms

        return 0

    @property
    def start_ms(self) -> int:
        data = self.data

        if data:
            return data["start"]

        if self.despawn_start_ms is not None:
            return self.despawn_start_ms

        return 0

    @property
    def track(self) -> str:
        data = self.data

        if data:
            return data["track"]

        return ""

    @property
    def visual_width_px(self) -> float:
        if self.current_width_px > 0.0:
            return self.current_width_px

        return self.ms_to_px(self.duration_ms)

    @property
    def keyframes(self) -> list[tuple[float, int]] | None:
        data = self.data

        if not data:
            return None

        if "effect" in data and data["effect"].get("name") == "Fade":
            effect_settings = data["effect"].get("settings", {})

            if "keyframes" in effect_settings and effect_settings["keyframes"] is not None:
                return [
                    (round(float(time_fraction), 2), int(round(float(brightness_value))))
                    for time_fraction, brightness_value in effect_settings["keyframes"]
                ]

        if "keyframes" in data and data["keyframes"] is not None:
            return [
                (round(float(time_fraction), 2), int(round(float(brightness_value))))
                for time_fraction, brightness_value in data["keyframes"]
            ]

        return None

    # Setup

    def setup_flags(self) -> None:
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.setCacheMode(QGraphicsItem.CacheMode.ItemCoordinateCache)
        self.setAcceptHoverEvents(True)

    def setup_keyframes(self) -> None:
        self.pending_fade_keyframes = copy.deepcopy(self.keyframes) or []
        self.fade_initial_keyframes = copy.deepcopy(self.pending_fade_keyframes)
        self.fade_is_dragging       = False
        self.fade_dragged_index     = None

    def setup_animations(self) -> None:
        self.animation_margin_px = 0.0
        self.is_animating        = False
        self.stack_depth         = 0

        self.despawn_duration_ms = None
        self.despawn_start_ms    = None

        self.scale_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "scale",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.MULTIPLY,
            on_change  = self.on_visual_property_changed
        )

        self.tilt_x_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "tiltX",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_visual_property_changed
        )

        self.tilt_y_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "tiltY",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_visual_property_changed
        )

        self.border_opacity_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "borderOpacity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_border_opacity_changed
        )

        self.stack_y_offset_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "stackYOffset",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_stack_y_offset_changed
        )

        self.position_x_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "positionX",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_position_x_changed
        )

        self.width_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "widthPx",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_width_changed
        )

    # Geometry And Metrics

    def calculate_y_pos(self) -> float:
        top_margin_px = (
            Styles.Metrics.Tracks.RulerHeight +
            Styles.Metrics.Waveform.Height    +
            Styles.Metrics.Tracks.BoxSpacing
        )

        row_height_px = Styles.Metrics.Tracks.RowHeight + Styles.Metrics.Tracks.BoxSpacing
        device        = Constants.DEVICES[self.conductor.composition.model]
        track_row     = device.track_names.index(str(self.track))
        track_top_px  = top_margin_px + (track_row * row_height_px)
        offset_px     = (Styles.Metrics.Tracks.RowHeight - Styles.Metrics.Tracks.BoxHeight) / 2

        return track_top_px + offset_px

    def ms_to_px(self, ms: float) -> float:
        return ms * self.conductor.px_per_sec / 1000.0

    def px_to_ms(self, px: float) -> float:
        return px * 1000.0 / self.conductor.px_per_sec

    def boundingRect(self) -> QRectF:
        margin_px = self.animation_margin_px + self.border_width_px
        width_px  = self.visual_width_px

        return QRectF(
            -margin_px,
            -margin_px,
            width_px + 2 * margin_px,
            Styles.Metrics.Tracks.BoxHeight + 2 * margin_px
        )

    # Painting

    def paint(
            self,
            painter: QPainter,
            option:  QStyleOptionGraphicsItem,
            widget:  QWidget | None = None
        ) -> None:

        width_px  = self.visual_width_px
        height_px = Styles.Metrics.Tracks.BoxHeight

        has_transforms = (
            self.scale_handle.value  != 1.0 or
            self.tilt_x_handle.value != 0   or
            self.tilt_y_handle.value != 0
        )

        if has_transforms:
            painter.save()
            self.apply_paint_transforms(painter, width_px, height_px)

        self.draw_base_shape(painter, width_px, height_px)

        if self.pending_fade_keyframes and width_px > 30:
            self.draw_fade_keyframes(painter, width_px, height_px)

        if has_transforms:
            painter.restore()

    def apply_paint_transforms(
            self,
            painter:   QPainter,
            width_px:  float,
            height_px: float
        ) -> None:

        center_x_px = width_px  / 2
        center_y_px = height_px / 2
        scale_value = self.scale_handle.value

        painter.translate(center_x_px, center_y_px)

        if scale_value != 1.0:
            painter.scale(scale_value, scale_value)

        tilt_x = self.tilt_x_handle.value
        tilt_y = self.tilt_y_handle.value

        if tilt_x != 0 or tilt_y != 0:
            transform = QTransform()
            transform.rotate(tilt_x, Qt.Axis.XAxis)
            transform.rotate(tilt_y, Qt.Axis.YAxis)

            painter.setTransform(transform * painter.transform())

        painter.translate(-center_x_px, -center_y_px)

    def update_radius(self, width_px: float) -> None:
        if width_px == self.cached_width_px:
            return

        self.cached_width_px  = width_px
        self.cached_radius_px = (
            2.4
            + max(0.0, min((width_px - 10) * 0.2, 2.0))
            + max(0.0, min((width_px - 20) * 0.48, 4.8))
        )

    def update_border_pen(self) -> None:
        opacity     = max(0.0, min(1.0, self.border_opacity_handle.value))
        red_channel = int(255 * opacity)

        self.cached_border_color.setRed(red_channel)
        self.cached_border_pen.setColor(self.cached_border_color)

    def update_stack_cache(self) -> None:
        depth = min(self.stack_depth, 3)

        for index in range(depth):
            alpha_channel = max(30, 90 - (index + 1) * 25)
            self.cached_stack_color_pool[index].setAlpha(alpha_channel)

        self.cached_stack_colors = self.cached_stack_color_pool[:depth]
        self.cached_stack_label  = f"+{self.stack_depth}"

    def draw_base_shape(
            self,
            painter:   QPainter,
            width_px:  float,
            height_px: float
        ) -> None:

        has_stack = self.stack_depth > 0 and abs(self.stack_y_offset_handle.value) < 1.0

        self.update_radius(width_px)
        self.update_border_pen()

        radius_px = self.cached_radius_px
        base_rect = QRectF(0, 0, width_px, height_px)

        pen = QPen(self.cached_border_pen)

        if not self.isSelected() and width_px < 15.0:
            standard_width_px = self.cached_border_pen.widthF()
            minimum_limit_px  = 3.0
            factor            = max(0.0, min(1.0, (width_px - minimum_limit_px) / (15.0 - minimum_limit_px)))
            new_width_px      = standard_width_px * factor

            if new_width_px <= 0.05:
                pen.setStyle(Qt.PenStyle.NoPen)

            else:
                pen.setWidthF(new_width_px)

        use_rounded_corners = width_px >= 15.0 and radius_px > 0.0 and Constants.current_settings.get("glyph_rounded_corners")

        def draw_shape(target_rectangle: QRectF) -> None:
            if use_rounded_corners:
                painter.drawRoundedRect(target_rectangle, radius_px, radius_px)

            else:
                painter.drawRect(target_rectangle)

        if has_stack:
            painter.setPen(Qt.PenStyle.NoPen)

            for step_index, color in enumerate(reversed(self.cached_stack_colors), start = 1):
                offset_x_px = step_index * 3.0
                offset_y_px = step_index * 4.0

                painter.setBrush(color)

                draw_shape(
                    QRectF(
                        offset_x_px,
                        offset_y_px,
                        max(0.0, width_px - offset_x_px),
                        max(0.0, height_px - offset_y_px)
                    )
                )

        painter.setPen(pen)
        painter.setBrush(Qt.GlobalColor.white)

        draw_shape(base_rect)

        if has_stack and width_px > 24:
            painter.setFont(self.STACK_LABEL_FONT)
            painter.setPen(self.STACK_LABEL_COLOR)

            painter.drawText(
                QRectF(0, 0, 30, 42),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignCenter,
                self.cached_stack_label
            )

    def draw_fade_keyframes(
            self,
            painter:   QPainter,
            width_px:  float,
            height_px: float
        ) -> None:

        inner_width_px  = width_px - 2 * self.keyframe_line_padding
        inner_height_px = height_px - 2 * self.border_width_px

        self.cached_fade_pen.setColor(self.cached_border_color)
        painter.setPen(self.cached_fade_pen)

        fade_path = QPainterPath()

        for index, (time_fraction, brightness_value) in enumerate(self.pending_fade_keyframes):
            point_x_px = time_fraction * inner_width_px + self.keyframe_line_padding
            point_y_px = (1.0 - brightness_value / 100.0) * inner_height_px + self.border_width_px

            if index == 0:
                fade_path.moveTo(point_x_px, point_y_px)

            else:
                fade_path.lineTo(point_x_px, point_y_px)

        painter.drawPath(fade_path)

        painter.setPen(Qt.PenStyle.NoPen)
        self.cached_fade_brush.setColor(self.cached_border_color)
        painter.setBrush(self.cached_fade_brush)

        dot_radius_px = 3.0

        for time_fraction, brightness_value in self.pending_fade_keyframes[1:-1]:
            corner_x_px = time_fraction * inner_width_px + self.keyframe_line_padding
            corner_y_px = (1.0 - brightness_value / 100.0) * inner_height_px + self.border_width_px

            painter.drawEllipse(QPointF(corner_x_px, corner_y_px), dot_radius_px, dot_radius_px)

    # Animations

    def set_animating(self, active: bool) -> None:
        if self.is_animating == active:
            return

        self.prepareGeometryChange()

        self.is_animating        = active
        self.animation_margin_px = 15.0 if active else 0.0

        self.update()

    def fade_in_animation(self) -> None:
        self.border_opacity_handle.play_curve(
            keyframes                  = [(0.0, self.border_opacity_handle.value), (1.0, 1.0)],
            duration_ms                = 400,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def fade_out_animation(self) -> None:
        self.border_opacity_handle.play_curve(
            keyframes                  = [(0.0, self.border_opacity_handle.value), (1.0, 0.0)],
            duration_ms                = 400,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False,
            finished                   = self.fade_out_callback
        )

    def spawn_animation(self, animate: bool = True) -> None:
        if not animate:
            return

        if not Constants.current_settings["glyph_spawn_animation"]:
            return

        self.set_animating(True)

        self.scale_handle.play_curve(
            keyframes                  = [(0.0, 0.0), (1.0, 1.0)],
            duration_ms                = 400,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            snap_to_start              = True,
            finished                   = lambda: self.set_animating(False)
        )

    def prepare_for_despawn(self) -> None:
        data = self.data

        if not data:
            return

        self.despawn_duration_ms = data["duration"]
        self.despawn_start_ms    = data["start"]

    def despawn_animation(self) -> None:
        self.prepare_for_despawn()
        self.set_animating(True)

        self.scale_handle.play_curve(
            keyframes                  = [(0.0, 1.0), (1.0, 0.0)],
            duration_ms                = 300,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            finished                   = self.on_despawn_finished
        )

    def marquee_select_animation(self) -> None:
        self.set_animating(True)

        self.scale_handle.play_curve(
            keyframes = [
                (0.0, 1.000),
                (0.5, 1.075),
                (1.0, 1.000)
            ],
            duration_ms                 = 500,
            easing_function             = LoomEngine.Easing.ease_out_cubic,
            finished                    = lambda: self.set_animating(False)
        )

    def press_animation(self, position: QPointF) -> None:
        if not Constants.current_settings["glyph_tilt_animation"]:
            return

        target_tilt_x, target_tilt_y = self.calculate_target_tilt(position)

        self.set_animating(True)

        self.tilt_x_handle.play_curve(
            keyframes = [
                (0.0, self.tilt_x_handle.value),
                (0.5, target_tilt_x),
                (1.0, 0.0)
            ],
            duration_ms     = 700,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        self.tilt_y_handle.play_curve(
            keyframes = [
                (0.0, self.tilt_y_handle.value),
                (0.5, target_tilt_y),
                (1.0, 0.0)
            ],
            duration_ms     = 700,
            easing_function = LoomEngine.Easing.ease_out_cubic,
            finished        = lambda: self.set_animating(False)
        )

    def animate_horizontal_move(self, target_x_px: float) -> None:
        current_x_px = self.pos().x()

        if abs(current_x_px - target_x_px) < 0.5:
            self.stop_horizontal_move()
            self.setPos(target_x_px, self.fixed_y_px + self.stack_y_offset_handle.value)
            return

        self.is_moving_horizontally = True

        self.position_x_handle.play_curve(
            keyframes                  = [
                (0.0, current_x_px),
                (1.0, target_x_px)
            ],
            duration_ms                = 220,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False,
            finished                   = self.on_horizontal_move_finished
        )

    def animate_width_resize(self, target_width_px: float) -> None:
        current_width_px = self.visual_width_px

        if abs(current_width_px - target_width_px) < 0.5:
            self.stop_width_animation()
            self.current_width_px = target_width_px
            self.prepareGeometryChange()
            self.update()
            return

        self.is_resizing_width = True

        self.width_handle.play_curve(
            keyframes                  = [
                (0.0, current_width_px),
                (1.0, target_width_px)
            ],
            duration_ms                = 220,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False,
            finished                   = self.on_width_animation_finished
        )

    def stop_horizontal_move(self) -> None:
        self.is_moving_horizontally = False

        try:
            self.position_x_handle.stop_targeting()

        except Exception:
            pass

    def stop_width_animation(self) -> None:
        self.is_resizing_width = False

        try:
            self.width_handle.stop_targeting()

        except Exception:
            pass

    def capture_current_visual_state(self) -> None:
        was_animating = self.is_moving_horizontally or self.is_resizing_width

        if not was_animating:
            return

        self.stop_horizontal_move()
        self.stop_width_animation()

        current_start_ms    = max(0, int(round(self.px_to_ms(self.pos().x()))))
        current_duration_ms = max(10, int(round(self.px_to_ms(self.visual_width_px))))

        glyph_data = self.data

        if glyph_data is not None:
            glyph_data["start"]    = current_start_ms
            glyph_data["duration"] = current_duration_ms

        self.setPos(self.ms_to_px(current_start_ms), self.fixed_y_px + self.stack_y_offset_handle.value)
        self.current_width_px = self.ms_to_px(current_duration_ms)

        self.conductor.composition.glyphs.mark_dirty(self.glyph_id)
        self.prepareGeometryChange()
        self.update()

        self.conductor.glyph_controller.elements_changed.emit()
        self.conductor.glyph_controller.refresh_all_occlusion()

    # Callbacks

    def on_visual_property_changed(self, value: object) -> None:
        self.update()

    def on_border_opacity_changed(self, value: float) -> None:
        self.update_border_pen()
        self.update()

    def on_stack_y_offset_changed(self, value: float) -> None:
        self.setPos(self.pos().x(), self.fixed_y_px + value)
        self.update()

    def on_position_x_changed(self, value: float) -> None:
        self.setPos(value, self.fixed_y_px + self.stack_y_offset_handle.value)
        self.update()

    def on_width_changed(self, value: float) -> None:
        self.prepareGeometryChange()
        self.current_width_px = value
        self.update()

    def on_horizontal_move_finished(self) -> None:
        self.is_moving_horizontally = False

    def on_width_animation_finished(self) -> None:
        self.is_resizing_width = False

    def fade_out_callback(self) -> None:
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

        if self.is_animating:
            self.set_animating(False)

    def on_despawn_finished(self) -> None:
        self.stop_horizontal_move()
        self.stop_width_animation()

        if self.scene():
            self.scene().removeItem(self)

        self.deleteLater()

    # Events

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        if not self.conductor.glyph_controller.drag_session:
            self.conductor.glyph_controller.set_hovered_item(self)

        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.conductor.glyph_controller.clear_hovered_item()
        self.conductor.tooltip.hide_tooltip()

        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        x_coordinate_px = event.pos().x()
        visual_width_px = self.visual_width_px
        margin_px       = self.resize_margin_px

        if -margin_px < x_coordinate_px < margin_px or visual_width_px - margin_px < x_coordinate_px < visual_width_px + margin_px:
            self.setCursor(Qt.CursorShape.SizeHorCursor)

        elif 0 <= x_coordinate_px <= visual_width_px:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if not self.interaction_mode:
            self.conductor.glyph_controller.set_hovered_item(self)

        super().hoverMoveEvent(event)

    def itemChange(
            self,
            change: QGraphicsItem.GraphicsItemChange,
            value:  object
        ) -> object:

        if change != QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            return super().itemChange(change, value)

        if value:
            if not self.was_clicked:
                self.marquee_select_animation()

            self.was_clicked = False
            self.fade_in_animation()
            self.setCacheMode(QGraphicsItem.CacheMode.NoCache)

        else:
            self.fade_out_animation()

        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.is_despawning:
            return

        controller = self.conductor.glyph_controller

        if controller.expanded_stack and self.glyph_id in controller.expanded_stack:
            controller.collapse_stack()
            event.accept()

            return

        if len(controller.get_overlapping_group(self.glyph_id)) > 1:
            controller.expand_stack(self.glyph_id)
            event.accept()

            return

        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.is_despawning:
            return

        self.capture_current_visual_state()

        controller = self.conductor.glyph_controller

        if controller.expanded_stack and self.glyph_id not in controller.expanded_stack:
            controller.collapse_stack()

        self.was_clicked = True
        self.conductor.glyph_controller.clear_hovered_item()

        super().mousePressEvent(event)

        alt_pressed = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)

        if alt_pressed and event.button() == Qt.MouseButton.LeftButton and not self.keyframes:
            controller.glyph_keyframe_edited.emit()
            self.apply_default_fade_effect(event)

            return

        if not self.keyframes:
            self.standard_press(event)

            return

        if event.button() == Qt.MouseButton.RightButton and alt_pressed:
            self.handle_fade_delete(event)

            return

        if alt_pressed:
            controller.glyph_keyframe_edited.emit()
            self.handle_fade_press(event)

            return

        self.standard_press(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.is_despawning:
            return

        if self.keyframes and self.fade_is_dragging and self.fade_dragged_index is not None:
            self.handle_fade_move(event)

            return

        if not self.interaction_mode:
            super().mouseMoveEvent(event)

            return

        self.conductor.mouse_controller.auto_scroller.process_position(event.screenPos())

        delta_px = event.scenePos().x() - self.drag_start_position.x()

        self.conductor.glyph_controller.update_drag_state(
            self.px_to_ms(delta_px),
            self.interaction_mode,
            self
        )

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.is_despawning:
            return

        if self.keyframes and self.fade_is_dragging:
            self.fade_is_dragging   = False
            self.fade_dragged_index = None

            formatted_keyframes = [
                (round(float(time_fraction), 2), int(round(float(brightness_value))))
                for time_fraction, brightness_value in self.pending_fade_keyframes
            ]

            self.conductor.glyph_controller.commit_fade_keyframes(
                self.glyph_id,
                self.fade_initial_keyframes,
                formatted_keyframes
            )

            self.fade_initial_keyframes = copy.deepcopy(formatted_keyframes)
            event.accept()

            return

        self.conductor.glyph_controller.end_drag()
        self.conductor.mouse_controller.stop_auto_scroll_drag()
        self.interaction_mode = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseReleaseEvent(event)

    # Helpers

    def set_is_occluded(self, state: bool) -> None:
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, state)

    def standard_press(self, event: QGraphicsSceneMouseEvent) -> None:
        self.drag_start_position = event.scenePos()
        self.interaction_mode    = None

        self.press_animation(event.pos())

        if not self.isSelected():
            return

        self.determine_interaction_mode(event.pos().x())
        self.conductor.glyph_controller.start_drag()

        event.accept()

    def apply_default_fade_effect(self, event: QGraphicsSceneMouseEvent) -> None:
        from System.Views.Compositor import Actions

        current_glyph = self.data

        if current_glyph is None:
            return

        original_glyph = copy.deepcopy(current_glyph)

        faded_glyph = GlyphEffects.apply_visual_effect(
            copy.deepcopy(current_glyph),
            "Fade",
            {"easing": "linear"}
        )

        self.conductor.composition.replace_glyph(self.glyph_id, faded_glyph)
        self.conductor.glyph_controller.push_action(
            Actions.ActionModify(
                self.conductor.glyph_controller,
                {self.glyph_id: original_glyph},
                {self.glyph_id: faded_glyph}
            )
        )

        self.pending_fade_keyframes = self.keyframes
        self.update_geometry()
        self.update()

        self.handle_fade_press(event)

    def determine_interaction_mode(self, x_position_px: float) -> None:
        visual_width_px = self.visual_width_px

        if x_position_px < self.resize_margin_px:
            self.interaction_mode = "resize_left"

        elif x_position_px > visual_width_px - self.resize_margin_px:
            self.interaction_mode = "resize_right"

        else:
            self.interaction_mode = "move"
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def handle_fade_press(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self.fade_is_dragging:
            self.fade_initial_keyframes = [
                (round(float(time_fraction), 2), int(round(float(brightness_value))))
                for time_fraction, brightness_value in self.pending_fade_keyframes
            ]

        width_px        = self.visual_width_px - self.keyframe_line_padding * 2
        height_px       = Styles.Metrics.Tracks.BoxHeight
        position        = event.pos()
        click_radius_px = 8.0

        for index, (time_fraction, brightness_value) in enumerate(self.pending_fade_keyframes):
            point_x_px = time_fraction * width_px + self.keyframe_line_padding
            point_y_px = (1.0 - brightness_value / 100.0) * (height_px - 2 * self.border_width_px) + self.border_width_px

            if math.hypot(position.x() - point_x_px, position.y() - point_y_px) < click_radius_px:
                self.fade_is_dragging   = True
                self.fade_dragged_index = index

                self.update()
                event.accept()

                return

        fraction_x = round(max(0.0, min(1.0, (position.x() - self.keyframe_line_padding) / width_px)), 2)
        fraction_y = int(round((1.0 - max(0.0, min(1.0, position.y() / height_px))) * 100.0))
        new_point  = (fraction_x, fraction_y)

        insert_position = bisect.bisect_left([point[0] for point in self.pending_fade_keyframes], fraction_x)

        self.pending_fade_keyframes.insert(insert_position, new_point)

        self.fade_is_dragging   = True
        self.fade_dragged_index = insert_position

        self.update()
        event.accept()

    def handle_fade_delete(self, event: QGraphicsSceneMouseEvent) -> None:
        width_px        = self.visual_width_px - self.keyframe_line_padding * 2
        height_px       = Styles.Metrics.Tracks.BoxHeight
        position        = event.pos()
        click_radius_px = 8.0
        last_index      = len(self.pending_fade_keyframes) - 1

        for index, (time_fraction, brightness_value) in enumerate(self.pending_fade_keyframes):
            if index == 0 or index == last_index:
                continue

            point_x_px = time_fraction * width_px + self.keyframe_line_padding
            point_y_px = (1.0 - brightness_value / 100.0) * (height_px - 2 * self.border_width_px) + self.border_width_px

            if math.hypot(position.x() - point_x_px, position.y() - point_y_px) >= click_radius_px:
                continue

            old_keyframes = [
                (round(float(time_part), 2), int(round(float(brightness_part))))
                for time_part, brightness_part in self.pending_fade_keyframes
            ]

            del self.pending_fade_keyframes[index]

            new_keyframes = [
                (round(float(time_part), 2), int(round(float(brightness_part))))
                for time_part, brightness_part in self.pending_fade_keyframes
            ]

            self.conductor.glyph_controller.commit_fade_keyframes(
                self.glyph_id,
                old_keyframes,
                new_keyframes
            )

            self.fade_initial_keyframes = copy.deepcopy(new_keyframes)

            self.update()
            event.accept()

            return

    def handle_fade_move(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self.fade_is_dragging:
            return

        if self.fade_dragged_index is None:
            return

        width_px        = self.visual_width_px - 2 * self.keyframe_line_padding
        height_px       = Styles.Metrics.Tracks.BoxHeight
        inner_height_px = height_px - 2 * self.border_width_px
        index           = self.fade_dragged_index

        new_fraction_x = round(max(0.0, min(1.0, (event.pos().x() - self.keyframe_line_padding) / width_px)), 2)
        new_fraction_y = int(round((1.0 - max(0.0, min(1.0, (event.pos().y() - self.border_width_px) / inner_height_px))) * 100.0))

        keyframes = self.pending_fade_keyframes

        if index == 0:
            keyframes[index] = (0.0, new_fraction_y)

        elif index == len(keyframes) - 1:
            keyframes[index] = (1.0, new_fraction_y)

        else:
            clamped_fraction_x = max(
                keyframes[index - 1][0] + 0.01,
                min(keyframes[index + 1][0] - 0.01, new_fraction_x)
            )

            clamped_fraction_x = round(clamped_fraction_x, 2)
            keyframes[index]   = (clamped_fraction_x, new_fraction_y)

        self.update()
        event.accept()

    def calculate_target_tilt(self, position: QPointF) -> tuple[float, float]:
        width_px    = self.visual_width_px
        height_px   = Styles.Metrics.Tracks.BoxHeight
        center_x_px = width_px  / 2
        center_y_px = height_px / 2
        offset_x_px = position.x() - center_x_px
        offset_y_px = position.y() - center_y_px

        maximum_edge_lift_px = 40.0

        max_tilt_y   = min(math.degrees(math.atan2(maximum_edge_lift_px, center_x_px)), 25.0) if center_x_px > 0 else 0.0
        normalized_x = max(-1.0, min(1.0, offset_x_px / center_x_px)) if center_x_px > 0 else 0.0
        normalized_y = max(-1.0, min(1.0, offset_y_px / center_y_px)) if center_y_px > 0 else 0.0

        return (-normalized_y * 25, -normalized_x * max_tilt_y)

    # Api

    def update_geometry(self, animate_movement: bool = False) -> None:
        self.prepareGeometryChange()

        if not self.data and self.despawn_duration_ms is None:
            return

        self.pending_fade_keyframes = copy.deepcopy(self.keyframes) or []
        self.fade_initial_keyframes = copy.deepcopy(self.pending_fade_keyframes)
        self.fixed_y_px             = self.calculate_y_pos()

        target_x_px     = self.ms_to_px(self.start_ms)
        target_width_px = self.ms_to_px(self.duration_ms)
        target_y_px     = self.fixed_y_px + self.stack_y_offset_handle.value

        if animate_movement:
            self.animate_horizontal_move(target_x_px)
            self.animate_width_resize(target_width_px)

        else:
            self.stop_horizontal_move()
            self.stop_width_animation()
            self.setPos(target_x_px, target_y_px)
            self.current_width_px = target_width_px

        self.update()

    def remove_glyph(self, animate: bool = True) -> None:
        self.prepare_for_despawn()
        self.is_despawning = True

        if Constants.current_settings["glyph_spawn_animation"] and animate:
            self.despawn_animation()

        else:
            self.on_despawn_finished()

    def set_stack_depth(self, depth: int) -> None:
        if self.stack_depth == depth:
            return

        self.stack_depth = depth
        self.update_stack_cache()
        self.update()