import math

from PyQt5 import sip
from loguru import logger

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System import Styles

from System.Constants import *

class PlayheadItem(QGraphicsItem):
    def __init__(self, conductor, custom_height = None):
        super().__init__()
        self.conductor = conductor
        
        self.w = 2
        self.h = custom_height

    def boundingRect(self) -> QRectF:
        return QRectF(-self.w / 2, 0, self.w, self.h or self.conductor.height())

    def paint(self, painter: QPainter, option, widget):
        pen = QPen(QColor(255, 0, 0), 2.0)
        pen.setCosmetic(True)
        
        painter.setPen(pen)
        painter.drawLine(0, 0, 0, self.h or self.conductor.height())

class MarqueeItem(QGraphicsObject):
    def __init__(self, composition, player):
        super().__init__()
        
        self.composition = composition
        self.player = player

        self._bpm = 120.0
        self._is_closing = False

        self._start_pos = QPointF()
        self._target_pos = QPointF()
        self._current_pos = QPointF()

        self._marquee_pen = QPen(QColor(215, 20, 31, 200), 1, Qt.PenStyle.DashLine)
        
        self.setup_animations()
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.hide()
    
    def setup_animations(self):
        self._pulse_strength = 0.0

        self.bpm_animation_timer = QTimer(self)
        self.bpm_animation_timer.setSingleShot(True)
        self.bpm_animation_timer.timeout.connect(self.bpm_tick)
        
        self.bpm_pulse_animation = QPropertyAnimation(self, b"bpmPulseStrength", self)
        self.bpm_pulse_animation.setStartValue(1.0)
        self.bpm_pulse_animation.setEndValue(0.0)

        self.damper_timer = QTimer(self)
        self.damper_timer.setInterval(FPS_120)
        self.damper_timer.timeout.connect(self.animate)
    
    def set_bpm(self, bpm: float):
        if not CurrentSettings["bpm_animations"]:
            return
        
        self.bpm = float(bpm)
        self.bpm_animation_timer.start(FPS_30)

    @pyqtProperty(float) # type: ignore
    def bpmPulseStrength(self) -> float:
        return self._pulse_strength

    @bpmPulseStrength.setter
    def bpmPulseStrength(self, value: float):
        self._pulse_strength = value
        self.update()

    def boundingRect(self) -> QRectF:
        rect = QRectF(
            self._start_pos,
            self._current_pos
        ).normalized()
        
        if rect.isNull():
            return QRectF()
        
        return rect
    
    def _lerp(self, a: float, b: float, t: float) -> float:
        return a + (b - a) * t
    
    def _apply_alpha(self, color):
        alpha = color.alpha()
        alpha = int(alpha * (1.0 + self._pulse_strength))
        alpha = max(0, min(255, alpha))
        color.setAlpha(alpha)
        
        return color

    def bpm_tick(self):
        if not self.player.is_playing or not self.isVisible():
            return self.bpm_animation_timer.start(FPS_30)

        speed = self.player.speed or 0.01
        interval_ms = int(round(60000.0 / (self.bpm * speed)))

        self.bpm_pulse_animation.stop()
        self.bpm_pulse_animation.setDuration(interval_ms)
        self.bpm_pulse_animation.start()
        self.bpm_animation_timer.start(interval_ms)

    def paint(self, painter: QPainter, option, widget):
        rect_to_draw = QRectF(self._start_pos, self._current_pos).normalized()

        painter.setRenderHint(QPainter.Antialiasing)

        brush_color = QColor(255, 0, 0, 50)
        brush_color = self._apply_alpha(brush_color)

        brush = QBrush(brush_color)
        radius = min((rect_to_draw.width() + rect_to_draw.height()) / 12, 10)

        painter.setPen(self._marquee_pen)
        painter.setBrush(brush)
        painter.drawRoundedRect(rect_to_draw, radius, radius)

    def start_marquee(self, start_point):
        self._is_closing = False
        
        self._start_pos = start_point
        self._target_pos = start_point
        self._current_pos = start_point
        
        if not self.isVisible():
            self.show()
            self.damper_timer.start()
            
            if CurrentSettings["bpm_animations"]:
                self.bpm_tick()
    
    def animate(self):
        if not self.isVisible():
            return

        lerp_factor = (0.15 if CurrentSettings["marquee_smoothing"] else 0.5) if not self.player.is_playing else 1.0

        if lerp_factor >= 1.0:
            new_curr_pos = self._target_pos
        
        else:
            new_curr_x = self._lerp(self._current_pos.x(), self._target_pos.x(), lerp_factor)
            new_curr_y = self._lerp(self._current_pos.y(), self._target_pos.y(), lerp_factor)
            new_curr_pos = QPointF(new_curr_x, new_curr_y)

        if self._is_closing:
            if not CurrentSettings["marquee_hide_animation"]:
                return self._finish_and_hide()
            
            lerp_factor_damper = 0.15
            new_start_x = self._lerp(self._start_pos.x(), self._target_pos.x(), lerp_factor_damper)
            new_start_y = self._lerp(self._start_pos.y(), self._target_pos.y(), lerp_factor_damper)
            new_start_pos = QPointF(new_start_x, new_start_y)
        
        else:
            new_start_pos = self._start_pos

        dist_start = (new_start_pos - self._target_pos).manhattanLength()
        dist_curr = (new_curr_pos - self._target_pos).manhattanLength()

        if self._is_closing and dist_start < 1.0 and dist_curr < 1.0:
            return self._finish_and_hide()

        self.prepareGeometryChange()
        self._start_pos = new_start_pos
        self._current_pos = new_curr_pos
        self.update()

    def end_marquee(self):
        self._is_closing = True

    def _finish_and_hide(self):
        self._is_closing = False
        self.damper_timer.stop()
        
        if CurrentSettings["bpm_animations"]:
            self.bpm_pulse_animation.stop()
            self.bpm_animation_timer.stop()
        
        self.hide()

    def update_end_point(self, point: QPointF):
        self._target_pos = point
        modifiers = QApplication.keyboardModifiers()
        
        rect = QRectF(self._start_pos, self._current_pos).normalized()
        path = QPainterPath()
        path.addRect(rect)
        
        if modifiers & Qt.ControlModifier:
            selection_op = Qt.ItemSelectionOperation.AddToSelection
        
        else:
            selection_op = Qt.ItemSelectionOperation.ReplaceSelection

        self.scene().setSelectionArea(
            path,
            selection_op,
            Qt.ItemSelectionMode.IntersectsItemShape,
            QTransform()
        )

class GlyphItem(QGraphicsObject):
    def __init__(
        self,
        glyph_id,
        glyph_data,
        parent_view,
        composition,
        
        animate_spawn = True
    ):

        super().__init__()
        
        self.glyph_id = glyph_id
        self.parent_view = parent_view
        self.composition = composition
        self.glyph_controller = parent_view.glyph_controller

        self.duration_ms = glyph_data['duration']
        self.start_ms = glyph_data['start']
        self.track = glyph_data['track']
        
        self.setup_animation_properties()
        
        self.border_width = 2.5
        
        self.setFlags(
            QGraphicsItem.ItemIsSelectable | 
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCacheMode(QGraphicsItem.ItemCoordinateCache)
        self.setAcceptHoverEvents(True)
        
        self.resize_margin = 10
        self._interaction_mode = None
        self._is_being_closed = False
        
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(1000)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self._on_hover_timeout)
        
        self._fixed_y = self._calculate_y_pos()
        self._drag_start_pos = QPointF()
        self.dirty_rect = self.boundingRect()
        
        self.update_geometry()
        self.spawn_animation(animate_spawn)
    
    def _on_hover_timeout(self):
        self.glyph_controller.show_hover_tooltip(self)
    
    def hoverEnterEvent(self, event):
        if not self.glyph_controller._drag_session:
            self.hover_timer.start()
        
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.hover_timer.stop()
        self.glyph_controller.hide_tooltip()
        super().hoverLeaveEvent(event)
    
    def update_geometry(self, start_ms: int = None, duration_ms: int = None):
        self.prepareGeometryChange()

        if start_ms is not None:
            self.start_ms = start_ms
        
        if duration_ms is not None:
            self.duration_ms = max(10, duration_ms)

        new_x = self._ms_to_px(self.start_ms)
        self.setPos(new_x, self._fixed_y)

        self.update()
    
    # Animation Properties

    @pyqtProperty(float) # type: ignore
    def pulseOpacity(self):
        return self.pulse_opacity

    @pulseOpacity.setter
    def pulseOpacity(self, value):
        self.pulse_opacity = value
        self.update()
    
    @pyqtProperty(float) # type: ignore
    def clickTiltY(self):
        return self.click_tilt_y

    @clickTiltY.setter
    def clickTiltY(self, value):
        self.click_tilt_y = value
        self.update()
    
    @pyqtProperty(float) # type: ignore
    def clickTiltX(self):
        return self.click_tilt_x

    @clickTiltX.setter
    def clickTiltX(self, value):
        self.click_tilt_x = value
        self.update()
    
    @pyqtProperty(float) # type: ignore
    def spawnScale(self):
        return self.spawn_scale

    @spawnScale.setter
    def spawnScale(self, value):
        self.spawn_scale = value
        self.update()
    
    @pyqtProperty(float) # type: ignore
    def despawnScale(self):
        return self.despawn_scale
    
    @despawnScale.setter
    def despawnScale(self, value):
        self.despawn_scale = value
        self.update()
    
    def setup_animation_properties(self):
        self._anim_margin = 0.0
        self.is_animating = False
        
        self.pulse_opacity = 0.0
        
        self.click_tilt_y = 0.0
        self.click_tilt_x = 0.0
        self.tooltip_tilt_x = 0.0
        
        self.spawn_scale = 1.0
        self.despawn_scale = 1.0
        
        self.tooltip_visible = False
        
        self.spawn_scale_animation = self.make_animation(
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], b"spawnScale", 400, QEasingCurve.OutBack
        )
        
        self.pulse_animation = self.make_animation(
            [
                (0.0, 0.0),
                (0.5, 1.0),
                (1.0, 0.0)
            ], b"pulseOpacity", 1250, QEasingCurve.Linear, True
        )

        self.despawn_animation = self.make_animation(
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], b"despawnScale", 400, QEasingCurve.OutCubic
        )
        
        self.spawn_scale_animation.finished.connect(lambda: self.set_animating(False))
        self.despawn_animation.finished.connect(self.on_despawn_finished)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedChange:
            if not value:
                self.pulse_animation.stop()
                self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
                
                if self.is_animating:
                    self.set_animating(False)
            
            else:
                self.pulse_animation.start()
                self.setCacheMode(QGraphicsItem.NoCache)

        return super().itemChange(change, value)
    
    def setCacheMode(self, mode):
        logger.warning(f"Cache mode changed to {mode}")
        return super().setCacheMode(mode)
    
    def make_animation(self, keyframes: list, property: bytes, duration: int, curve: QEasingCurve = QEasingCurve.OutCubic, loop = False):
        anim = QPropertyAnimation(self, property)
        anim.setDuration(duration)
        anim.setKeyValues(keyframes)
        anim.setEasingCurve(curve)
        anim.setParent(self)
        
        if loop:
            anim.setLoopCount(-1)

        return anim

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

        self.anim_group.start()

    def _calculate_y_pos(self):
        top_margin = Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.box_spacing
        row_height = Styles.Metrics.Tracks.row_height + Styles.Metrics.Tracks.box_spacing
        
        track_top = top_margin + ((int(self.track) - 1) * row_height)
        offset_in_row = (Styles.Metrics.Tracks.row_height - Styles.Metrics.Tracks.box_height) / 2 
        
        return track_top + offset_in_row

    def _ms_to_px(self, ms):
        return ms * self.parent_view.px_per_sec / 1000.0

    def _px_to_ms(self, px):
        return px * 1000.0 / self.parent_view.px_per_sec

    def boundingRect(self):
        m = self._anim_margin + self.border_width
        return QRectF(-m, -m, self._ms_to_px(self.duration_ms) + 2*m, Styles.Metrics.Tracks.box_height + 2*m)

    def paint(self, painter: QPainter, option, widget = None):
        is_selected = option.state & QStyle.State_Selected
        height = Styles.Metrics.Tracks.box_height
        width_px = self._ms_to_px(self.duration_ms)

        center_x = width_px / 2
        center_y = height / 2

        scale_factor = self.spawn_scale * self.despawn_scale

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.save()

        painter.translate(center_x, center_y)

        if scale_factor != 1.0:
            painter.scale(scale_factor, scale_factor)

        if self.click_tilt_x != 0 or self.tooltip_tilt_x != 0 or self.click_tilt_y != 0:
            transform = QTransform()
            transform.rotate(self.click_tilt_y, Qt.Axis.YAxis)
            transform.rotate(self.click_tilt_x + self.tooltip_tilt_x, Qt.Axis.XAxis)
            painter.setTransform(transform * painter.transform())

        painter.translate(-center_x, -center_y)

        fill_brush = QBrush(QColor(255, 255, 255))

        if is_selected:
            color = QColor(int(255 * self.pulse_opacity), 0, 0)
        
        else:
            color = QColor("#000000")

        border_pen = QPen(color, self.border_width)
        border_pen.setCosmetic(True)
        border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        radius = 3 + max(0, min((width_px - 10) / 10 * 2.5, 2.5)) + max(0, min((width_px - 20) / 10 * 6, 6)) 

        painter.setPen(border_pen)
        painter.setBrush(fill_brush)

        painter.drawRoundedRect(
            QRectF(0, 0, width_px, height), 
            radius, radius
        )
        
        debug_mode = False
        if debug_mode:
            painter.save()

            rect = self.boundingRect()

            painter.setPen(QPen(QColor(255, 0, 0, 150), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            painter.setPen(QColor(0, 0, 255))
            painter.drawLine(-5, 0, 5, 0)
            painter.drawLine(0, -5, 0, 5)

            painter.restore()

        painter.restore()
    
    def set_animating(self, active: bool):
        if self._is_being_closed:
            return
        
        if self.is_animating == active:
            return

        self.prepareGeometryChange()
        self.is_animating = active

        self._anim_margin = 15.0 if active else 0.0
        self.update()
    
    def hoverMoveEvent(self, event):
        x = event.pos().x()
        visual_width = self._ms_to_px(self.duration_ms)
        
        hit_margin = self.resize_margin
        
        if -hit_margin < x < hit_margin:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        
        elif visual_width - hit_margin < x < visual_width + hit_margin:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        
        elif 0 <= x <= visual_width:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        
        if not self._interaction_mode:
            self.hover_timer.start()
        
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self.hover_timer.stop()
        
        if event.button() != Qt.MouseButton.LeftButton:
            event.accept()
            return

        self._drag_start_pos = event.scenePos()
        self._interaction_mode = None

        modifiers = event.modifiers()
        is_ctrl = (modifiers & Qt.ControlModifier)
        
        if is_ctrl:
            self.setSelected(not self.isSelected())
        
        else:
            if not self.isSelected():
                self.scene().clearSelection()
                self.setSelected(True)

        if not self.isSelected():
            return

        x = event.pos().x()
        visual_width = self._ms_to_px(self.duration_ms)
        
        if x < self.resize_margin:
            self._interaction_mode = 'resize_left'
        
        elif x > visual_width - self.resize_margin:
            self._interaction_mode = 'resize_right'
        
        else:
            self._interaction_mode = 'move'
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        self.glyph_controller.start_drag()
        
        self._animate_press(event)
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._interaction_mode:
            return super().mouseMoveEvent(event)
        
        self.parent_view.mouse_controller.auto_scroller.process_pos(event.screenPos())

        current_scene_pos = event.scenePos()
        delta_px = current_scene_pos.x() - self._drag_start_pos.x()
        delta_ms = self._px_to_ms(delta_px)

        self.glyph_controller.update_drag_state(
            delta_ms,
            self._interaction_mode,
            self
        )

    def mouseReleaseEvent(self, event):
        self.parent_view.mouse_controller.stop_auto_scroll_drag()

        self._interaction_mode = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.ungrabMouse()
        
        self.glyph_controller.end_drag()
        
        if not CurrentSettings["glyph_tilt_animation"]:
            return

    def _animate_press(self, event):
        self.pulse_animation.start()
        
        if not CurrentSettings["glyph_tilt_animation"]:
            return
        
        width_px = self._ms_to_px(self.duration_ms)
        height_px = Styles.Metrics.Tracks.box_height
        
        center_x = width_px / 2
        center_y = height_px / 2
        
        offset_x = event.pos().x() - center_x
        offset_y = event.pos().y() - center_y

        MAX_EDGE_LIFT_PX = 40.0 
        
        if center_x > 0:
            max_tilt_y = math.degrees(math.atan2(MAX_EDGE_LIFT_PX, center_x))
            max_tilt_y = min(max_tilt_y, 25.0)
        
        else:
            max_tilt_y = 0
    
        norm_x = max(-1.0, min(1.0, offset_x / center_x)) if center_x > 0 else 0
        norm_y = max(-1.0, min(1.0, offset_y / center_y)) if center_y > 0 else 0
        
        target_tilt_y = -norm_x * max_tilt_y 
        target_tilt_x = -norm_y * 25
    
        self.set_animating(True)
    
        self.group_animate(
            [
                self.make_animation([(0.0, self.click_tilt_y), (0.5, target_tilt_y), (1.0, 0.0)], b"clickTiltY", 700),
                self.make_animation([(0.0, self.click_tilt_x), (0.5, target_tilt_x), (1.0, 0.0)], b"clickTiltX", 700)
            ], lambda: self.set_animating(False)
        )
    
    def remove_glyph(self):
        self._is_being_closed = True
        
        if hasattr(self, "anim_group"):
            if not sip.isdeleted(self.anim_group):
                self.anim_group.stop()
                self.anim_group.clear()
                self.anim_group = None
        
        self.pulse_animation.stop()
        
        if CurrentSettings["glyph_spawn_animation"]:
            self.despawn_animation.start()
        
        else:
            self.on_despawn_finished()
    
    def on_despawn_finished(self):
        self.setGraphicsEffect(None)
        self.scene().removeItem(self)
        self.deleteLater()
    
    def spawn_animation(self, animate = True):
        should_animate = animate and CurrentSettings["glyph_spawn_animation"]

        if should_animate:
            self.set_animating(should_animate)
            self.spawn_scale_animation.start()