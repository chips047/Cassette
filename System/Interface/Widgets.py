from __future__ import annotations

import math
import bisect

import numpy as np

from PyQt6.QtCore import (
    Qt,
    QSize,
    QRect,
    QLineF,
    QPoint,
    QRectF,
    QTimer,
    QPointF,
    pyqtSignal,
    QEasingCurve,
    pyqtProperty,
    QElapsedTimer,
    QAbstractAnimation,
    QPropertyAnimation,
    QParallelAnimationGroup
)

from PyQt6.QtGui import (
    QPen,
    QBrush,
    QColor,
    QPixmap,
    QPainter,
    QShowEvent,
    QTransform,
    QPaintEvent,
    QMouseEvent,
    QWheelEvent,
    QFontMetrics,
    QPainterPath,
    QResizeEvent,
    QLinearGradient,
    QGuiApplication
)

from PyQt6.QtWidgets import (
    QWidget,
    QScrollArea,
    QVBoxLayout,
    QSizePolicy,
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent
)

from loguru import logger

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Interface import Basic
from System.Services import Player
from System.Interface.Animation import LoomEngine

class ValuePopup(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.padding       = 7
        self.text          = ""
        self.font          = Utils.NType(10)
        self.original_text = ""

        self.setup_animations()
        self.move(160, 160)
        self.resize(1, 1)

    # Setup

    def setup_animations(self) -> None:
        self.animation_engine = LoomEngine.AnimationEngine("PyQt6")

        self.animation_engine.add_properties(
            [
                ("opacity", 1.0,     LoomEngine.MixMode.NOMIX, self.on_opacity_updated),
                ("rect",    QRect(), LoomEngine.MixMode.NOMIX, self.on_geometry_updated)
            ]
        )

        self.manual_hide_timer = Basic.Timer(
            1000,
            self.hide,
            single_shot = True,
            parent      = self
        )

        self.final_hide_timer = Basic.Timer(
            300,
            self.on_hide_finished,
            single_shot = True,
            parent      = self
        )

        self.cached_background_color = QColor(Styles.Colors.SecondaryBackground)
        self.cached_text_color       = QColor(Qt.GlobalColor.white)

    # Painting

    def paintEvent(
        self,
        event: QPaintEvent
    ) -> None:
        
        painter = QPainter(self)
        
        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        alpha = int(self.animation_engine.get_property_value("opacity") * 255)

        background_color = QColor(self.cached_background_color)
        background_color.setAlpha(alpha)

        painter.setBrush(background_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 6.5, 6.5)

        text_color = QColor(self.cached_text_color)
        text_color.setAlpha(alpha)

        painter.setPen(text_color)
        painter.setFont(self.font)
        painter.translate(self.padding, self.padding)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft, self.text)

    # Helpers

    def layout_for_text(
        self,
        text: str
    ) -> tuple[int, int]:
        
        self.original_text = text
        metrics            = QFontMetrics(self.font)

        rect = metrics.boundingRect(0, 0, 700, 1000, Qt.TextFlag.TextWordWrap, text)

        width  = rect.width()  + self.padding * 2
        height = rect.height() + self.padding * 2

        return width, height

    def compute_top_left(
        self,
        position: QPoint,
        width: int
    ) -> tuple[int, int]:
        
        desired_x = position.x() - width // 2
        desired_y = position.y() + 5

        return desired_x, desired_y

    def on_geometry_updated(self, geometry: QRect) -> None:
        self.move(geometry.topLeft())
        self.resize(geometry.size())
        
        self.update()

    def on_opacity_updated(self, opacity: float) -> None:
        self.update()

    # API

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

        width, height = self.layout_for_text(text)
        x, y          = self.compute_top_left(position, width)

        self.text = text

        if self.parent():
            parent_pos = self.parent().mapFromGlobal(QPoint(x, y))
            x, y       = parent_pos.x(), parent_pos.y()

        self.animation_engine.set_target_value(
            "rect",
            QRect(x, y, width, height),
            300,
            LoomEngine.Easing.ease_out_cubic
        )

        self.show()

    def fade_in(self) -> None:
        self.animation_engine.set_target_value(
            "opacity",
            1.0,
            300,
            LoomEngine.Easing.ease_out_cubic
        )

    def fade_out(self) -> None:
        self.animation_engine.set_target_value(
            "opacity",
            0.0,
            300,
            LoomEngine.Easing.ease_out_cubic
        )

        self.final_hide_timer.start()

    def show(self) -> None:
        self.animation_engine.resume()
        self.fade_in()

        super().show()

    def hide(self) -> None:
        self.fade_out()

    def cleanup(self) -> None:
        self.animation_engine.clear()
        super().hide()

        self.deleteLater()

    # Callbacks

    def on_hide_finished(self) -> None:
        self.animation_engine.pause()
        super().hide()

class MiniWaveformPreview(QWidget):
    preview_clicked = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.audio             = None
        self.min_samples       = np.array([])
        self.max_samples       = np.array([])
        self.waveform_max      = 1.0
        self.pixmap            = None
        self.mouse_pressed     = False
        self.playhead_position = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(Styles.Controls.MiniWaveformPreview)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.cached_wave_pen                  = QPen(QColor(170, 170, 170, 255), 2.0)
        self.cached_wave_brush                = QBrush(QColor(255, 255, 255, 100))
        self.cached_playhead_pen              = QPen(QColor(255, 0, 0), 2.0)
        self.cached_loading_color             = QColor("#888")
        self.cached_gradient_fade_transparent = QColor(0, 0, 0, 0)
        self.cached_gradient_fade_opaque      = QColor(0, 0, 0, 255)

    # Data

    def set_audio_data(self, audio: np.ndarray) -> None:
        self.audio = audio

        self.prepare_audio_data()
        self.regenerate_pixmap()
        self.update()

    def set_playhead_position(self, value: float) -> None:
        self.playhead_position = float(np.clip(value, 0.0, 1.0))
        self.update()

    def prepare_audio_data(self) -> None:
        audio = self.audio

        if audio is None or audio.size == 0:
            self.min_samples  = np.array([])
            self.max_samples  = np.array([])
            self.waveform_max = 1.0

            return

        self.min_samples = np.min(audio, axis=1).astype(np.float32)
        self.max_samples = np.max(audio, axis=1).astype(np.float32)

        max_absolute      = max(np.max(np.abs(self.min_samples)), np.max(np.abs(self.max_samples)))
        self.waveform_max = max(max_absolute, 1e-6)

    # Rendering

    def generate_pixmap(self) -> QPixmap | None:
        width        = max(1, self.width()  - 4)
        height       = max(1, self.height() - 10)
        waveform_max = self.waveform_max
        min_samples  = self.min_samples
        max_samples  = self.max_samples

        if min_samples.size == 0:
            return None

        num_samples       = len(min_samples)
        samples_per_pixel = max(1, int(np.ceil(num_samples / float(width))))
        pad_needed        = (-num_samples) % samples_per_pixel

        if pad_needed:
            padded_min = np.pad(min_samples, (0, pad_needed), mode = 'constant')
            padded_max = np.pad(max_samples, (0, pad_needed), mode = 'constant')

        else:
            padded_min = min_samples
            padded_max = max_samples

        tile_min = np.min(padded_min.reshape(-1, samples_per_pixel), axis=1).astype(np.float32)
        tile_max = np.max(padded_max.reshape(-1, samples_per_pixel), axis=1).astype(np.float32)

        y_center = height / 2.0
        top      = y_center - (tile_max / waveform_max * y_center)
        bottom   = y_center - (tile_min / waveform_max * y_center)

        sigma = float(Constants.current_settings.get("waveform_smoothing", 0.0))

        if sigma > 0.0 and top.size > 1:
            pad    = min(int(np.ceil(sigma * 3.0)), top.size - 1)
            top    = Utils.gaussian_filter1d_np(np.pad(top,    (pad, pad), 'reflect'), sigma)[pad:pad + top.size]
            bottom = Utils.gaussian_filter1d_np(np.pad(bottom, (pad, pad), 'reflect'), sigma)[pad:pad + bottom.size]

        if top.size == bottom.size:
            mask = top > bottom

            if np.any(mask):
                average      = (top[mask] + bottom[mask]) * 0.5
                top[mask]    = average
                bottom[mask] = average

        if top.size == 0:
            return None
        
        dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        
        pixmap = QPixmap(int(width * dpr), int(height * dpr))
        pixmap.setDevicePixelRatio(dpr)

        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)

        if Constants.current_settings.get("antialiasing"):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_width = float(width) / float(top.size)
        path      = QPainterPath()

        path.moveTo(0.0, float(np.clip(top[0], 0.0, height)))

        for i in range(1, top.size):
            path.lineTo(i * bar_width, float(np.clip(top[i], 0.0, height)))

        for i in range(bottom.size - 1, -1, -1):
            path.lineTo(i * bar_width, float(np.clip(bottom[i], 0.0, height)))

        path.closeSubpath()

        painter.setPen(self.cached_wave_pen)
        painter.setBrush(self.cached_wave_brush)
        painter.drawPath(path)

        fade_width = width * 0.05

        gradient = QLinearGradient(0.0, 0.0, float(width), 0.0)
        gradient.setColorAt(0.0,                          self.cached_gradient_fade_transparent)
        gradient.setColorAt(fade_width / width,           self.cached_gradient_fade_opaque)
        gradient.setColorAt(1.0 - fade_width / width,     self.cached_gradient_fade_opaque)
        gradient.setColorAt(1.0,                          self.cached_gradient_fade_transparent)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(0, 0, width, height, QBrush(gradient))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        painter.end()

        return pixmap

    def regenerate_pixmap(self) -> None:
        self.pixmap = self.generate_pixmap()

    # Events

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self.pixmap:
            return

        painter = QPainter(self)

        painter.drawPixmap(2, 5, self.pixmap)

        x = float(self.width()) * self.playhead_position

        painter.setPen(self.cached_playhead_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QLineF(x, 0.0, x, float(self.height())))

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.pixmap or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        self.mouse_pressed = True
        normalized         = float(np.clip(event.position().x() / float(max(1, self.width())), 0.0, 1.0))

        self.set_playhead_position(normalized)
        self.preview_clicked.emit(normalized)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.mouse_pressed:
            super().mouseMoveEvent(event)
            return

        normalized = float(np.clip(event.position().x() / float(max(1, self.width())), 0.0, 1.0))

        self.set_playhead_position(normalized)
        self.preview_clicked.emit(normalized)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.mouse_pressed = False
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        if self.isVisible():
            self.regenerate_pixmap()
            self.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.regenerate_pixmap()

class BaseSegmentedBar(QWidget):
    RADIUS = 10.0

    def __init__(
        self,
        number_of_segments: int,
        base_thickness:     int
    ) -> None:

        super().__init__()

        self.amount_of_segments = max(1, number_of_segments)
        self.cached_paths       = []

        self.setFixedHeight(base_thickness)

    # Path Building

    def update_paths(self) -> None:
        amount = self.amount_of_segments
        width  = self.width() / amount
        height = float(self.height())
        last   = amount - 1

        self.cached_paths = [
            self.build_segment_path(
                i,
                width,
                height,
                last
            )
            for i in range(amount)
        ]

    def build_segment_path(
        self,
        index:         int,
        segment_width: float,
        height:        float,
        last_index:    int
    ) -> QPainterPath:

        width  = segment_width if index == last_index else segment_width + 1
        rect   = QRectF(index * segment_width, 0, width, height)
        radius = self.RADIUS
        path   = QPainterPath()

        if index == 0:
            path.moveTo(rect.topRight())
            path.lineTo(rect.topLeft() + QPointF(radius, 0))
            path.quadTo(rect.topLeft(), rect.topLeft() + QPointF(0, radius))
            path.lineTo(rect.bottomLeft() + QPointF(0, -radius))
            path.quadTo(rect.bottomLeft(), rect.bottomLeft() + QPointF(radius, 0))
            path.lineTo(rect.bottomRight())
            
            path.closeSubpath()
            return path

        if index == last_index:
            path.moveTo(rect.topLeft())
            path.lineTo(rect.topRight() - QPointF(radius, 0))
            path.quadTo(rect.topRight(), rect.topRight() + QPointF(0, radius))
            path.lineTo(rect.bottomRight() - QPointF(0, radius))
            path.quadTo(rect.bottomRight(), rect.bottomRight() - QPointF(radius, 0))
            path.lineTo(rect.bottomLeft())
            
            path.closeSubpath()
            return path

        path.addRect(rect)

        return path

    # Helpers

    def blend_color(
        self,
        color0: QColor,
        color1: QColor,
        t:      float
    ) -> QColor:
        
        t = max(0.0, min(1.0, float(t)))
        
        return QColor(
            int(color0.red()   + (color1.red()   - color0.red())   * t),
            int(color0.green() + (color1.green() - color0.green()) * t),
            int(color0.blue()  + (color1.blue()  - color0.blue())  * t),
            int(color0.alpha() + (color1.alpha() - color0.alpha()) * t),
        )

    # Events

    def paintEvent(self, event: QPaintEvent) -> None:
        if len(self.cached_paths) != self.amount_of_segments:
            self.update_paths()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        for i, path in enumerate(self.cached_paths):
            painter.setBrush(self.segment_color(i))
            painter.drawPath(path)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update_paths()

class ScheduledSegmentedBar(BaseSegmentedBar):
    def __init__(
        self,
        number_of_segments: int  = 30,
        base_thickness:     int  = 20,
        loop:               bool = False
    ) -> None:

        super().__init__(number_of_segments, base_thickness)

        self.loop         = bool(loop)
        self.schedule     = []
        self.duration_ms  = 0
        self.start_offset = 0
        self.levels       = [0.0] * self.amount_of_segments
        self.color_off    = QColor("#404040")
        self.color_on     = QColor("#ffffff")

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet("background-color: transparent;")

        self.elapsed_timer = QElapsedTimer()

        self.timer = Basic.Timer(
            Constants.FPS_60,
            self.tick,
            parent = self
        )

    # Override

    def segment_color(self, index: int) -> QColor:
        t = max(0.0, min(self.levels[index] / 100.0, 1.0))

        return self.blend_color(
            self.color_off,
            self.color_on,
            t
        )

    # API

    def set_schedule(self, schedule: list) -> None:
        self.schedule    = schedule or []
        self.duration_ms = max(
            (
                item["start"] + item["duration"]
                for item in self.schedule
            ),
            default = 0
        )

    def play(self, start_offset_ms: int = 0) -> None:
        self.start_offset = int(start_offset_ms)
        
        self.elapsed_timer.start()
        self.timer.start()

    def stop(self,clear_levels: bool = True) -> None:
        self.timer.stop()
        
        if clear_levels:
            self.levels = [0.0] * self.amount_of_segments
            self.update()

    def is_playing(self) -> bool:
        return self.timer.isActive()

    def set_colors(
        self,
        off: QColor | None = None,
        on:  QColor | None = None
    ) -> None:
        
        if off:
            self.color_off = off
        
        if on:
            self.color_on = on
        
        self.update()

    # Helpers

    def active_indices(self, item: dict) -> range:
        segments = item.get("segments")
        
        if not segments:
            return range(self.amount_of_segments)
        
        return (i for i in segments if 0 <= i < self.amount_of_segments)

    def eval_keyframes(
        self,
        keyframes:       list,
        progress:        float,
        easing_function: callable
    ) -> float:
        
        if progress <= keyframes[0][0]:
            return float(keyframes[0][1])
        
        if progress >= keyframes[-1][0]:
            return float(keyframes[-1][1])

        for (t0, v0), (t1, v1) in zip(keyframes, keyframes[1:]):
            if not (t0 <= progress <= t1):
                continue
            
            segment = t1 - t0
            local_t = (progress - t0) / segment if segment else 1.0
            
            return v0 + (v1 - v0) * easing_function(local_t)

        return float(keyframes[-1][1])

    # Tick

    def tick(self) -> None:
        if not self.timer.isActive():
            return
        
        now = int(self.elapsed_timer.elapsed()) + int(self.start_offset)

        if self.duration_ms and now >= self.duration_ms:
            if self.loop:
                self.elapsed_timer.restart()
                self.start_offset = 0
            
            else:
                self.stop()
            
            return
        
        new_levels = [0.0] * self.amount_of_segments

        for item in self.schedule:
            time_start = int(item["start"])
            duration   = int(item["duration"])

            if duration <= 0:
                continue
            
            if not (time_start <= now <= time_start + duration):
                continue
            
            progress        = (now - time_start) / duration
            keyframes       = item.get("keyframes")
            easing_function = Constants.VISUAL_EASINGS[item.get("easing", "linear")]

            value = (
                self.eval_keyframes(keyframes, progress, easing_function)
                if keyframes
                else float(item["brightness"])
            )

            for i in self.active_indices(item):
                if value < new_levels[i]:
                    continue

                new_levels[i] = value

        if new_levels != self.levels:
            self.levels = new_levels
            self.update()

class SegmentedBar(BaseSegmentedBar):
    segment_changed = pyqtSignal()

    def __init__(
        self,
        amount_of_zones: int,
        defaults:        list[int] = None
    ) -> None:

        super().__init__(amount_of_zones, 18)

        numbers            = defaults if defaults else list(range(amount_of_zones))
        self.active        = [i in numbers for i in range(amount_of_zones)]
        self.is_pressed    = False
        self.hovered_index = None
        self.last_index    = None
        self.drag_target   = None

        self.cached_active_color = QColor(Styles.Colors.FontColor)
        self.cached_hover_color  = QColor(Styles.Colors.GlassBorder).lighter(130)
        self.cached_border_color = QColor(Styles.Colors.GlassBorder)

    # Override

    def segment_color(self, index: int) -> QColor:
        if self.active[index]:
            return self.cached_active_color

        if self.hovered_index == index:
            return self.cached_hover_color

        return self.cached_border_color

    # Events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.is_pressed = True
        index           = self.get_index(event.pos().x())

        if not (0 <= index < self.amount_of_segments):
            return

        new_state          = not self.active[index]
        self.active[index] = new_state
        self.drag_target   = new_state
        self.last_index    = index

        self.play_toggle_sound(index)
        self.segment_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.is_pressed  = False
        self.last_index  = None
        self.drag_target = None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.amount_of_segments <= 0:
            return

        index = self.get_index(event.pos().x())

        if self.is_pressed and self.drag_target is not None and self.last_index is not None:
            self.handle_drag(index)
        
        else:
            self.handle_hover(index)

    # Helpers

    def get_index(self, x_position: int) -> int:
        segment_width = self.width() / self.amount_of_segments
        return max(0, min(self.amount_of_segments - 1, int(x_position / segment_width)))

    def handle_drag(self, index: int) -> None:
        if index == self.last_index:
            return

        start, end = sorted((self.last_index, index))
        changed    = False

        for i in range(start, end + 1):
            if self.active[i] == self.drag_target:
                continue
            
            self.active[i] = self.drag_target
            self.play_toggle_sound(i, alt=True)
            
            changed = True

        if changed:
            self.segment_changed.emit()
            self.update()

        self.last_index = index

    def handle_hover(
        self,
        index: int
    ) -> None:
        
        if self.hovered_index == index:
            return
        
        self.hovered_index = index
        self.update()

    def play_toggle_sound(
        self,
        index: int,
        alt:   bool = False
    ) -> None:
        
        tone  = index / self.amount_of_segments + 0.5
        tone += 0.05 if self.active[index] else 0.0
        
        Player.ui_player.play_sound("Click/Toggle3" if alt else "Click/Toggle", speed = tone)

    # API

    def enable_all(self) -> None:
        self.active = [True] * self.amount_of_segments
        self.segment_changed.emit()
        
        Player.ui_player.play_sound("Click/Toggle", speed=1.0, enable_tone_randomizer=False)

    def disable_all(self) -> None:
        self.active = [False] * self.amount_of_segments
        self.segment_changed.emit()
        
        Player.ui_player.play_sound("Click/Toggle", speed=0.7, enable_tone_randomizer=False)

    def zebra(self) -> None:
        self.active = [i % 2 == 0 for i in range(self.amount_of_segments)]
        self.segment_changed.emit()
        
        Player.ui_player.play_sound("Click/Toggle3")

class PlayheadItem(QGraphicsObject):
    def __init__(
        self,
        conductor,
        custom_height: float | None = None
    ) -> None:
        
        super().__init__()

        self.conductor = conductor
        self.width     = 2.0
        self.height    = custom_height
        self.target_x  = 0.0

        self.cached_pen = QPen(QColor(255, 0, 0), 2.0)
        self.cached_pen.setCosmetic(True)

        self.lerp_timer = Basic.Timer(
            Constants.FPS_120,
            self.lerp_step,
            parent = self
        )

    # Graphics Item

    def boundingRect(self) -> QRectF:
        return QRectF(
            -self.width / 2,
            0,
            self.width,
            self.height or self.conductor.height()
        )

    def paint(
        self,
        painter: QPainter,
        option:  QStyleOptionGraphicsItem,
        widget:  QWidget = None
    ) -> None:
        
        painter.setPen(self.cached_pen)
        painter.drawLine(0, 0, 0, self.height or self.conductor.height())

    # Logic

    def set_target_x(
            self,
            x:       float,
            animate: bool = False
        ) -> None:
        
        self.target_x = x

        if animate and Constants.current_settings.get("playhead_animations", True):
            if not self.lerp_timer.isActive():
                self.lerp_timer.start()

            return
            
        self.lerp_timer.stop()
        self.update_actual_position(x)

    def lerp_step(self) -> None:
        current_x = self.x()
        target_x  = self.target_x
        
        lerp_factor = 0.22
        new_x       = current_x + (target_x - current_x) * lerp_factor
        
        if abs(target_x - new_x) < 0.1:
            new_x = target_x
            self.lerp_timer.stop()

            logger.debug(f"Playhead reached target: {new_x:.2f} | Timer stopped")
        
        self.update_actual_position(new_x)

    def update_actual_position(
            self,
            x: float
        ) -> None:
        
        self.setPos(x, 0)
        
        if self.conductor.total_content_width > 0:
            self.conductor.playhead_moved.emit(x / self.conductor.total_content_width)

class MarqueeItem(QGraphicsObject):
    def __init__(
        self,
        player: Player.PlaybackManager
    ) -> None:
        
        super().__init__()

        self.player         = player
        self.bpm            = 120.0
        self.start_position = QPointF()

        self.cached_brush_color = QColor(255, 0, 0)
        self.cached_brush       = QBrush(self.cached_brush_color)

        self.cached_pen         = QPen(
            QColor(215, 20, 31), 1,
            Qt.PenStyle.DashLine
        )
        self.cached_pen_color   = QColor(self.cached_pen.color())

        self.setup_animations()
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)

        self.hide()

    # Setup

    def setup_animations(self) -> None:
        Player.bpm_informer.beat_4.connect(self.bpm_tick)

        self.animation_engine = LoomEngine.AnimationEngine("PyQt6")
        self.animation_engine.updated.connect(self.on_animation_updated)

        self.animation_engine.add_properties(
            [
                ("bpm_pulse",     0.0,       LoomEngine.MixMode.ADD),
                ("mouse_point",   QPointF(), LoomEngine.MixMode.NOMIX),
                ("mouse_y",       0.0,       LoomEngine.MixMode.NOMIX),
                ("brush_opacity", 1.0,       LoomEngine.MixMode.NOMIX),
                ("pen_opacity",   1.0,       LoomEngine.MixMode.NOMIX)
            ]
        )
    
    # Geometry

    def boundingRect(self) -> QRectF:
        mouse_point = self.animation_engine.get_property_value("mouse_point")
        
        return QRectF(
            self.start_position,
            mouse_point
        ).normalized()

    # Painting

    def apply_bpm_to_alpha(
        self,
        base_alpha: int,
        opacity:    float
    ) -> int:
        
        pulse = self.animation_engine.get_property_value("bpm_pulse")
        alpha = int(base_alpha * opacity * (1.0 + pulse))
        
        return alpha

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget = None
    ) -> None:
        
        brush_alpha = self.animation_engine.get_property_value("brush_opacity")
        pen_alpha   = self.animation_engine.get_property_value("pen_opacity")
        mouse_point = self.animation_engine.get_property_value("mouse_point")

        rect   = QRectF(self.start_position, mouse_point).normalized()
        radius = min((rect.width() + rect.height()) / 12, 10)

        self.cached_brush_color.setAlpha(self.apply_bpm_to_alpha(50, brush_alpha))
        self.cached_brush = QBrush(self.cached_brush_color)
        
        self.cached_pen_color.setAlpha(int(200 * pen_alpha))
        self.cached_pen.setColor(self.cached_pen_color)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(self.cached_pen)
        painter.setBrush(self.cached_brush)

        painter.drawRoundedRect(rect, radius, radius)

    # Animations

    def fade_in(self) -> None:
        self.animation_engine.resume()

        self.animation_engine.animate(
            "brush_opacity",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            300,
            LoomEngine.Easing.ease_out_cubic
        )

        self.animation_engine.animate(
            "pen_opacity", [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            300,
            LoomEngine.Easing.ease_out_cubic
        )

    def fade_out(self) -> None:
        if not Constants.current_settings["marquee_hide_animation"]:
            self.animation_engine.set_property_base_value("brush_opacity", 0.0)
            self.animation_engine.set_property_base_value("pen_opacity",   0.0)
            
            self.finish_and_hide()
            
            return

        self.animation_engine.animate("brush_opacity", [(0.0, 1.0), (1.0, 0.0)], 230, LoomEngine.Easing.ease_out_cubic)
        QTimer.singleShot(70, self.animate_pen_out)

    def animate_pen_out(self) -> None:
        self.animation_engine.animate(
            "pen_opacity",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            300,
            LoomEngine.Easing.ease_out_cubic,
            self.finish_and_hide
        )

    def finish_and_hide(self) -> None:
        self.animation_engine.pause()
        self.hide()

    # API

    def set_bpm(self, bpm: float) -> None:
        self.bpm = bpm

    def start_marquee(self, start_point: QPointF) -> None:
        self.start_position = start_point
        
        self.animation_engine.set_property_base_value("mouse_point", start_point)
        
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
            self.animation_engine.set_target_value(
                "mouse_point",
                point,
                150,
                LoomEngine.Easing.ease_out_cubic
            )
        
        else:
            self.animation_engine.set_property_base_value("mouse_point", point)
            self.on_animation_updated()

        path = QPainterPath()
        path.addRect(QRectF(self.start_position, point).normalized())

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

    def on_animation_updated(self) -> None:
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

        self.animation_engine.animate(
            "bpm_pulse",
            [
                (0.0, 0.5),
                (1.0, 0.0)
            ],
            interval_ms,
            LoomEngine.Easing.ease_out_cubic
        )

class GlyphItem(QGraphicsObject):
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

        self.fixed_y             = self.calculate_y_pos()
        self.was_clicked         = False
        self.border_width        = 2
        self.is_despawning       = False
        self.resize_margin       = 10
        self.interaction_mode    = None
        self.drag_start_position = QPointF()

        self.cached_width        = -1.0
        self.cached_radius       = 0.0
        self.cached_border_pen   = QPen()
        self.cached_stack_label  = ""
        self.cached_stack_colors = []

        self.cached_fade_pen         = QPen()
        self.cached_fade_brush       = QBrush()
        self.cached_border_color     = QColor(255, 0, 0, 255)
        self.cached_stack_color_pool = [QColor(220, 220, 220), QColor(220, 220, 220), QColor(220, 220, 220)]

        self.cached_border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.cached_border_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.cached_border_pen.setWidthF(self.border_width)
        
        self.cached_fade_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.cached_fade_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.cached_fade_pen.setWidthF(self.keyframe_line_width if hasattr(self, 'keyframe_line_width') else 4)

        self.setup_animations()
        self.setup_flags()
        self.setup_timers()
        self.setup_keyframes()
        
        self.cached_fade_pen.setWidthF(self.keyframe_line_width)

        self.dirty_rect = self.boundingRect()

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
            return data['duration']
        
        if self.despawn_duration_ms is not None:
            return self.despawn_duration_ms
        
        return 0

    @property
    def start_ms(self) -> int:
        data = self.data
        
        if data:
            return data['start']
        
        if self.despawn_start_ms is not None:
            return self.despawn_start_ms
        
        return 0

    @property
    def track(self) -> int:
        data = self.data
        
        if data:
            return data['track']

    @property
    def keyframes(self) -> list | None:
        data = self.data
        
        if not data:
            return None
        
        if data.get("effect", {}).get("name") == "Fade":
            return data.get("effect", {}).get("settings", {}).get("keyframes")
        
        return None

    # Setup

    def setup_flags(self) -> None:
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        
        self.setCacheMode(QGraphicsItem.CacheMode.ItemCoordinateCache)
        self.setAcceptHoverEvents(True)

    def setup_timers(self) -> None:
        self.hover_timer = Basic.Timer(
            1000,
            self.on_hover_timeout,
            single_shot = True,
            parent = self
        )

    def setup_keyframes(self) -> None:
        self.keyframe_line_padding  = 12
        self.keyframe_line_width    = 4
        self.pending_fade_keyframes = self.keyframes

        self.fade_dragging          = False
        self.fade_dragged_index     = None

    def setup_animations(self) -> None:
        self.animation_margin              = 0.0
        self.is_animating                  = False

        self.marquee_selection_scale       = 1.0
        self.spawn_scale                   = 1.0
        self.despawn_scale                 = 1.0

        self.tilt_x                        = 0.0
        self.tilt_y                        = 0.0

        self.border_opacity                = 0.0

        self.stack_y_offset                = 0.0
        self.stack_depth                   = 0

        self.despawn_duration_ms           = None
        self.despawn_start_ms              = None

    # Geometry & Metrics

    def calculate_y_pos(self) -> float:
        top_margin = (
            Styles.Metrics.Tracks.RulerHeight +
            Styles.Metrics.Waveform.Height    +
            Styles.Metrics.Tracks.BoxSpacing
        )

        row_height = Styles.Metrics.Tracks.RowHeight + Styles.Metrics.Tracks.BoxSpacing
        track_top  = top_margin + ((int(self.track) - 1) * row_height)
        offset     = (Styles.Metrics.Tracks.RowHeight - Styles.Metrics.Tracks.BoxHeight) / 2

        return track_top + offset

    def ms_to_px(self, ms: float) -> float:
        return ms * self.conductor.px_per_sec / 1000.0

    def px_to_ms(self, px: float) -> float:
        return px * 1000.0 / self.conductor.px_per_sec

    def boundingRect(self) -> QRectF:
        margin = self.animation_margin + self.border_width

        if self.is_despawning:
            duration = self.despawn_duration_ms
        
        else:
            duration = self.duration_ms

        return QRectF(
            -margin,
            -margin,
            self.ms_to_px(duration) + 2 * margin,
            Styles.Metrics.Tracks.BoxHeight + 2 * margin
        )

    # Painting

    def paint(
        self,
        painter: QPainter,
        option:  QStyleOptionGraphicsItem,
        widget:  QWidget = None
    ) -> None:
        width_px     = self.ms_to_px(self.duration_ms)
        height       = Styles.Metrics.Tracks.BoxHeight

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.save()

        self.apply_paint_transforms(painter, width_px, height)
        self.draw_base_shape(painter, width_px, height)

        if self.pending_fade_keyframes and width_px > 30:
            self.draw_fade_keyframes(painter, width_px, height)

        painter.restore()

    def apply_paint_transforms(
        self,
        painter:      QPainter,
        width_px:     float,
        height:       float
    ) -> None:
        
        scale    = self.marquee_selection_scale * self.spawn_scale * self.despawn_scale
        center_x = width_px / 2
        center_y = height       / 2

        painter.translate(center_x, center_y)

        if scale != 1.0:
            painter.scale(scale, scale)

        if self.tilt_x != 0 or self.tilt_y != 0:
            transform = QTransform()
            transform.rotate(self.tilt_x, Qt.Axis.XAxis)
            transform.rotate(self.tilt_y, Qt.Axis.YAxis)
            
            painter.setTransform(transform * painter.transform())

        painter.translate(-center_x, -center_y)
    
    def update_radius(self, width: float) -> None:
        if width == self.cached_width:
            return

        self.cached_width  = width
        self.cached_radius = (
            2.4
            + max(0.0, min((width - 10) * 0.2, 2.0))
            + max(0.0, min((width - 20) * 0.48, 4.8))
        )

    def update_border_pen(self) -> None:
        opacity = max(0.0, min(1.0, self.border_opacity))
        r = int(255 * opacity)
        
        self.cached_border_color.setRed(r)
        self.cached_border_pen.setColor(self.cached_border_color)

    def update_stack_cache(self) -> None:
        depth = min(self.stack_depth, 3)
        
        for i in range(depth):
            alpha = max(30, 90 - (i + 1) * 25)
            self.cached_stack_color_pool[i].setAlpha(alpha)
        
        self.cached_stack_colors = self.cached_stack_color_pool[:depth]
        self.cached_stack_label  = f"+{self.stack_depth}"

    def draw_base_shape(
            self,
            painter: QPainter,
            width:   float,
            height:  float
        ) -> None:
        
        has_stack = self.stack_depth > 0 and abs(self.stack_y_offset) < 1.0

        self.update_radius(width)
        self.update_border_pen()
        radius    = self.cached_radius
        base_rect = QRectF(0, 0, width, height)

        if has_stack:
            painter.setPen(Qt.PenStyle.NoPen)
            
            for step, color in enumerate(reversed(self.cached_stack_colors), start = 1):
                ox, oy = step * 3.0, step * 4.0
                
                painter.setBrush(color)
                painter.drawRoundedRect(
                    QRectF(ox, oy, max(0.0, width - ox), max(0.0, height - oy)),
                    radius, radius
                )

        painter.setPen(self.cached_border_pen)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawRoundedRect(base_rect, radius, radius)

        if has_stack and width > 24:
            painter.setFont(self.STACK_LABEL_FONT)
            painter.setPen(self.STACK_LABEL_COLOR)

            painter.drawText(
                QRectF(0, 0, 30, 42),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignCenter,
                self.cached_stack_label
            )

    def draw_fade_keyframes(
        self,
        painter:      QPainter,
        width_px:     float,
        height:       float
    ) -> None:
        
        self.cached_fade_pen.setColor(self.cached_border_color)

        inner_width  = width_px - 2 * self.keyframe_line_padding
        inner_height = height       - 2 * self.border_width

        self.cached_fade_pen.setColor(self.cached_border_color)
        painter.setPen(self.cached_fade_pen)

        fade_path = QPainterPath()

        for index, (fraction_x, fraction_y) in enumerate(self.pending_fade_keyframes):
            pixel_x = fraction_x * inner_width + self.keyframe_line_padding
            pixel_y = (1.0 - fraction_y / 100.0) * inner_height + self.border_width

            if index == 0:
                fade_path.moveTo(pixel_x, pixel_y)
            
            else:
                fade_path.lineTo(pixel_x, pixel_y)

        painter.drawPath(fade_path)

        painter.setPen(Qt.PenStyle.NoPen)
        self.cached_fade_brush.setColor(self.cached_border_color)
        painter.setBrush(self.cached_fade_brush)

        for fraction_x, fraction_y in self.pending_fade_keyframes[1:-1]:
            pixel_x = fraction_x * inner_width + self.keyframe_line_padding
            pixel_y = (1.0 - fraction_y / 100.0) * inner_height
            
            painter.drawEllipse(QPointF(pixel_x, pixel_y), 6, 6)

    # Animations

    def make_animation(
        self,
        keyframes: list,
        property:  bytes,
        duration:  int,
        curve:     QEasingCurve = QEasingCurve.Type.OutCubic,
        loop:      bool         = False
    ) -> QPropertyAnimation:

        animation = QPropertyAnimation(self, property)
        animation.setDuration(duration)
        animation.setKeyValues(keyframes)
        animation.setEasingCurve(curve)
        animation.setParent(self)

        if loop:
            animation.setLoopCount(-1)

        return animation

    def group_animate(
        self,
        animations:    list[QPropertyAnimation],
        finished:      callable | None = None,
        value_changed: callable | None = None,
        multiplier:    float           = 1.0
    ) -> None:

        self.animation_group = QParallelAnimationGroup(self)

        if multiplier == 1.0:
            multiplier = float(Constants.current_settings["animation_multiplier"])

        for animation in animations:
            if multiplier != 1.0:
                animation.setDuration(int(animation.duration() * multiplier))
            
            if value_changed:
                animation.valueChanged.connect(value_changed)
            
            self.animation_group.addAnimation(animation)

        if finished:
            self.animation_group.finished.connect(finished)

        self.animation_group.start()

    def set_animating(self, active: bool) -> None:
        if self.is_animating == active:
            return
        
        self.prepareGeometryChange()
        
        self.is_animating    = active
        self.animation_margin = 15.0 if active else 0.0
        
        self.update()

    def fade_in_animation(self) -> None:
        self.fade_in = self.make_animation(
            [
                (0.0, self.border_opacity),
                (1.0, 1.0)
            ],
            b"borderOpacity",
            400
        )
        
        self.fade_in.start()

    def fade_out_animation(self) -> None:
        self.fade_out = self.make_animation(
            [
                (0.0, self.border_opacity),
                (1.0, 0.0)
            ],
            b"borderOpacity",
            400
        )
        
        self.fade_out.finished.connect(self.fade_out_callback)
        self.fade_out.start()

    def spawn_animation(self, animate: bool = True) -> None:
        if not animate:
            return
        
        if not Constants.current_settings["glyph_spawn_animation"]:
            return
        
        self.set_animating(True)
        
        self.scale_animation = self.make_animation(
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            b"spawnScale",
            400
        )
        
        self.scale_animation.start()

    def prepare_for_despawn(self) -> None:
        data = self.data
        
        if not data:
            return
        
        self.despawn_duration_ms = data['duration']
        self.despawn_start_ms    = data['start']

    def despawn_animation(self) -> None:
        self.prepare_for_despawn()

        for child in self.children():
            if not isinstance(child, QAbstractAnimation):
                continue

            child.stop()

        self.set_animating(True)
        
        self.scale_animation = self.make_animation(
            [
                (0.0, self.spawn_scale),
                (1.0, 0.0)
            ],
            b"spawnScale",
            300
        )
        
        self.scale_animation.finished.connect(self.on_despawn_finished)
        self.scale_animation.start()

    def marquee_select_animation(self) -> None:
        self.set_animating(True)
        
        self.marquee_scale_animation = self.make_animation(
            [
                (0.0, self.marquee_selection_scale),
                (0.5, 1.05),
                (1.0, 1.0)
            ],
            b"marqueeSelectionScale",
            500
        )
        
        self.marquee_scale_animation.finished.connect(lambda: self.set_animating(False))
        self.marquee_scale_animation.start()

    def press_animation(self, position: QPointF) -> None:
        if not Constants.current_settings["glyph_tilt_animation"]:
            return

        target_tilt_x, target_tilt_y = self.calculate_target_tilt(position)
        
        self.set_animating(True)

        tilt_x_animation = self.make_animation(
            [
                (0.0, self.tilt_x),
                (0.5, target_tilt_x),
                (1.0, 0.0)
            ],
            b"tiltX",
            700
        )
        
        tilt_y_animation = self.make_animation(
            [
                (0.0, self.tilt_y),
                (0.5, target_tilt_y),
                (1.0, 0.0)
            ],
            b"tiltY",
            700
        )

        self.group_animate(
            [
                tilt_x_animation,
                tilt_y_animation
            ],
            lambda: self.set_animating(False)
        )

    # Animation Properties

    @pyqtProperty(float)
    def borderOpacity(self) -> float:
        return self.border_opacity

    @borderOpacity.setter
    def borderOpacity(self, value: float) -> None:
        self.border_opacity = value
        self.update_border_pen()
        self.update()

    @pyqtProperty(float)
    def tiltY(self) -> float:
        return self.tilt_y

    @tiltY.setter
    def tiltY(self, value: float) -> None:
        self.tilt_y = value
        self.update()

    @pyqtProperty(float)
    def tiltX(self) -> float:
        return self.tilt_x

    @tiltX.setter
    def tiltX(self, value: float) -> None:
        self.tilt_x = value
        self.update()

    @pyqtProperty(float)
    def spawnScale(self) -> float:
        return self.spawn_scale

    @spawnScale.setter
    def spawnScale(self, value: float) -> None:
        self.spawn_scale = value
        self.update()

    @pyqtProperty(float)
    def despawnScale(self) -> float:
        return self.despawn_scale

    @despawnScale.setter
    def despawnScale(self, value: float) -> None:
        self.despawn_scale = value
        self.update()

    @pyqtProperty(float)
    def marqueeSelectionScale(self) -> float:
        return self.marquee_selection_scale

    @marqueeSelectionScale.setter
    def marqueeSelectionScale(self, value: float) -> None:
        self.marquee_selection_scale = value
        self.update()

    @pyqtProperty(float)
    def stackYOffset(self) -> float:
        return self.stack_y_offset
    
    @stackYOffset.setter
    def stackYOffset(self, value: float) -> None:
        self.stack_y_offset = value
        self.setPos(self.pos().x(), self.fixed_y + value)

        self.update()

    # Events

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        if not self.conductor.glyph_controller.drag_session:
            self.hover_timer.start()
        
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.hover_timer.stop()
        self.conductor.tooltip.hide_tooltip()
        
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        x            = event.pos().x()
        visual_width = self.ms_to_px(self.duration_ms)
        hit_margin   = self.resize_margin

        if -hit_margin < x < hit_margin or visual_width - hit_margin < x < visual_width + hit_margin:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        
        elif 0 <= x <= visual_width:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if not self.interaction_mode:
            self.hover_timer.start()

        super().hoverMoveEvent(event)

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value:  any
    ) -> any:
        
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

        controller = self.conductor.glyph_controller

        if controller.expanded_stack and self.glyph_id not in controller.expanded_stack:
            controller.collapse_stack()
        
        self.was_clicked = True
        self.hover_timer.stop()

        super().mousePressEvent(event)

        if not self.keyframes:
            self.standard_press(event)
            return

        if event.button() == Qt.MouseButton.RightButton and event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self.handle_fade_delete(event)
            return

        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self.handle_fade_press(event)
            return

        self.standard_press(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.is_despawning:
            return
        
        if self.keyframes and self.fade_dragging and self.fade_dragged_index is not None:
            self.handle_fade_move(event)
            return

        if not self.interaction_mode:
            return super().mouseMoveEvent(event)

        self.conductor.mouse_controller.auto_scroller.process_pos(event.screenPos())

        delta_px = event.scenePos().x() - self.drag_start_position.x()
        
        self.conductor.glyph_controller.update_drag_state(
            self.px_to_ms(delta_px),
            self.interaction_mode,
            self
        )

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.is_despawning:
            return

        if self.keyframes and self.fade_dragging:
            self.fade_dragging      = False
            self.fade_dragged_index = None
            
            formatted = [
                (round(time, 2), int(brightness))
                for time, brightness in self.pending_fade_keyframes
            ]

            self.conductor.glyph_controller.commit_fade_keyframes(
                self.glyph_id,
                formatted
            )
            
            event.accept()
            return

        self.conductor.glyph_controller.end_drag()
        self.conductor.mouse_controller.stop_auto_scroll_drag()
        
        self.interaction_mode = None
        
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    # Event Helpers

    def standard_press(self, event: QGraphicsSceneMouseEvent) -> None:
        self.drag_start_position   = event.scenePos()
        self.interaction_mode = None
        
        self.press_animation(event.pos())

        if not self.isSelected():
            return

        self.determine_interaction_mode(event.pos().x())
        self.conductor.glyph_controller.start_drag()
        
        event.accept()

    def determine_interaction_mode(self, x_position: float) -> None:
        visual_width = self.ms_to_px(self.duration_ms)

        if x_position < self.resize_margin:
            self.interaction_mode = 'resize_left'
        
        elif x_position > visual_width - self.resize_margin:
            self.interaction_mode = 'resize_right'
        
        else:
            self.interaction_mode = 'move'
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def handle_fade_press(self, event: QGraphicsSceneMouseEvent) -> None:
        width_px     = self.ms_to_px(self.duration_ms) - self.keyframe_line_padding * 2
        height       = Styles.Metrics.Tracks.BoxHeight
        position     = event.pos()
        click_radius = 8.0

        for index, (fraction_x, fraction_y) in enumerate(self.pending_fade_keyframes):
            pixel_x = fraction_x * width_px + self.keyframe_line_padding
            pixel_y = (1.0 - fraction_y / 100.0) * (height - 2 * self.border_width) + self.border_width

            if math.hypot(position.x() - pixel_x, position.y() - pixel_y) < click_radius:
                self.fade_dragging      = True
                self.fade_dragged_index = index
                
                self.update()
                event.accept()
                return

        fraction_x = max(0.0, min(1.0, (position.x() - self.keyframe_line_padding) / width_px))
        fraction_y = (1.0 - max(0.0, min(1.0, position.y() / height))) * 100.0
        new_point  = (fraction_x, fraction_y)

        insert_position = bisect.bisect_left([point[0] for point in self.pending_fade_keyframes], fraction_x)
        
        self.pending_fade_keyframes.insert(insert_position, new_point)

        self.fade_dragging      = True
        self.fade_dragged_index = insert_position

        self.update()
        event.accept()

    def handle_fade_delete(self, event: QGraphicsSceneMouseEvent) -> None:
        width_px = self.ms_to_px(self.duration_ms) - self.keyframe_line_padding * 2
        height       = Styles.Metrics.Tracks.BoxHeight
        position     = event.pos()
        click_radius = 8.0
        last_index   = len(self.pending_fade_keyframes) - 1

        for index, (fraction_x, fraction_y) in enumerate(self.pending_fade_keyframes):
            if index == 0 or index == last_index:
                continue

            pixel_x = fraction_x * width_px + self.keyframe_line_padding
            pixel_y = (1.0 - fraction_y / 100.0) * (height - 2 * self.border_width) + self.border_width

            if math.hypot(position.x() - pixel_x, position.y() - pixel_y) >= click_radius:
                continue

            del self.pending_fade_keyframes[index]
            
            rounded = [(round(t, 2), round(v, 2)) for t, v in self.pending_fade_keyframes]

            self.conductor.glyph_controller.commit_fade_keyframes(
                self.glyph_id,
                rounded
            )
            
            self.update()
            event.accept()
            
            return

    def handle_fade_move(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self.fade_dragging:
            return
        
        if self.fade_dragged_index is None:
            return

        width_px = self.ms_to_px(self.duration_ms) - 2 * self.keyframe_line_padding
        height       = Styles.Metrics.Tracks.BoxHeight
        inner_height = height - 2 * self.border_width
        index        = self.fade_dragged_index

        new_fraction_x = max(0.0, min(1.0, (event.pos().x() - self.keyframe_line_padding) / width_px))
        new_fraction_y = (1.0 - max(0.0, min(1.0, (event.pos().y() - self.border_width) / inner_height))) * 100.0

        keyframes = self.pending_fade_keyframes

        if index == 0:
            keyframes[index] = (0.0, new_fraction_y)

        elif index == len(keyframes) - 1:
            keyframes[index] = (1.0, new_fraction_y)

        else:
            clamped_fraction_x = max(
                keyframes[index - 1][0] + 0.001,
                min(keyframes[index + 1][0] - 0.001, new_fraction_x)
            )
            
            keyframes[index] = (clamped_fraction_x, new_fraction_y)

        self.update()
        event.accept()

    def calculate_target_tilt(self, position: QPointF) -> tuple[float, float]:
        width_px      = self.ms_to_px(self.duration_ms)
        height_px     = Styles.Metrics.Tracks.BoxHeight
        center_x      = width_px  / 2
        center_y      = height_px / 2
        offset_x      = position.x() - center_x
        offset_y      = position.y() - center_y

        MAX_EDGE_LIFT_px = 40.0

        max_tilt_y = min(math.degrees(math.atan2(MAX_EDGE_LIFT_px, center_x)), 25.0) if center_x > 0 else 0.0
        norm_x     = max(-1.0, min(1.0, offset_x / center_x)) if center_x > 0 else 0.0
        norm_y     = max(-1.0, min(1.0, offset_y / center_y)) if center_y > 0 else 0.0

        return (-norm_y * 25, -norm_x * max_tilt_y)

    # API

    def update_geometry(self) -> None:
        self.prepareGeometryChange()

        if not self.data and self.despawn_duration_ms is None:
            return

        self.pending_fade_keyframes = self.keyframes
        self.fixed_y                = self.calculate_y_pos()

        self.setPos(self.ms_to_px(self.start_ms), self.fixed_y + self.stack_y_offset)
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

    # Callbacks

    def fade_out_callback(self) -> None:
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        
        if self.is_animating:
            self.set_animating(False)

    def on_despawn_finished(self) -> None:
        if self.scene():
            self.scene().removeItem(self)

        self.deleteLater()

    def on_hover_timeout(self) -> None:
        self.conductor.tooltip.show_hover_tooltip(self)

class TrimmingWaveformWidget(QWidget):
    regionChanged = pyqtSignal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.duration            = 0.0
        self.peaks               = []
        self.is_loading          = True
        self.waveform_pixmap     = None
        self.is_playing          = False
        self.playback_position   = 0.0
        self.start_time          = 0.0
        self.end_time            = 0.0
        self.waveform_amplitudes = []
        self.dragging_handle     = None

        self.setMinimumHeight(80)
        self.setFixedWidth(690)

        wave_color = QColor(Styles.Colors.Waveform.MainColor)
        
        self.cached_wave_pen      = QPen(wave_color, 2.5)
        self.cached_accent_pen    = QPen(QColor(Styles.Colors.NothingAccent), 2)
        self.cached_wave_brush    = QBrush(wave_color)
        self.cached_trim_brush    = QBrush(QColor(255, 255, 255, 30))
        self.cached_accent_brush  = QBrush(QColor(Styles.Colors.NothingAccent))
        self.cached_loading_color = QColor("#888")

    # Data

    def set_data(
        self,
        audio_data:          np.ndarray,
        sampling_rate:       int,
        waveform_amplitudes: list
    ) -> None:
        
        self.audio_data          = audio_data
        self.waveform_amplitudes = waveform_amplitudes
        self.duration            = len(audio_data) / sampling_rate if sampling_rate > 0 else 0
        self.end_time            = self.duration
        self.is_loading          = False

        self.generate_pixmap()
        self.update()

    def set_times(
        self,
        start: float,
        end:   float
    ) -> None:
        
        start = max(0.0, start)
        end   = min(self.duration if self.duration > 0 else end, end)

        if end <= start + 0.01:
            end = start + 0.01
            
            if self.duration > 0 and end > self.duration:
                start = max(0.0, self.duration - 0.01)
                end   = self.duration

        self.start_time = start
        self.end_time   = end
        
        self.update()
    
    def set_start_time(self, start: float) -> None:
        self.set_times(start, self.end_time)
    
    def set_end_time(self, end: float) -> None:
        self.set_times(self.start_time, end)

    def set_playback_position(
        self,
        position: float
    ) -> None:
        
        self.playback_position = max(0.0, min(self.duration, position))
        self.update()

    def set_is_playing(self, is_playing: bool) -> None:
        self.is_playing = is_playing

    # Rendering

    def generate_pixmap(self) -> None:
        width      = self.width()
        height     = self.height()
        y_center   = height * 0.5
        amplitudes = self.waveform_amplitudes
        count      = len(amplitudes)

        pixmap  = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        x_step    = width / count
        clamp_max = height
        path      = QPainterPath()

        for i, amplitude in enumerate(amplitudes):
            x = i * x_step
            y = max(0, min(clamp_max, y_center - amplitude * y_center))
            
            if i == 0:
                path.moveTo(x, y)
            
            else:
                path.lineTo(x, y)

        for i in range(count - 1, -1, -1):
            x = i * x_step
            y = max(0, min(clamp_max, y_center + amplitudes[i] * y_center))
            
            path.lineTo(x, y)

        path.closeSubpath()

        painter.setPen(self.cached_wave_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setBrush(self.cached_wave_brush)
        painter.setPen(QPen(QColor(255, 255, 255, 160), 0.7))
        painter.drawPath(path)

        painter.end()
        
        self.waveform_pixmap = pixmap

    # Painting

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.is_loading:
            painter.setPen(self.cached_loading_color)
            painter.setFont(Utils.NType(15))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft, "Loading the audio...")
            
            return

        if self.waveform_pixmap:
            painter.drawPixmap(0, 0, self.waveform_pixmap)

        width = self.width()

        def to_x(time: float) -> float:
            return (time / self.duration) * width

        start_x = to_x(self.start_time)
        end_x   = to_x(self.end_time)

        painter.setBrush(self.cached_trim_brush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(QPointF(start_x, 0), QPointF(end_x, self.height())),
            10,
            10
        )

        painter.setPen(self.cached_accent_pen)
        painter.drawLine(int(start_x), 10, int(start_x), self.height() - 10)
        painter.drawLine(int(end_x),   10, int(end_x),   self.height() - 10)

        playhead_x = to_x(self.playback_position)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.cached_accent_brush)
        painter.drawRect(QRectF(playhead_x - 1.0, 0, 2.0, self.height()))

    # Events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        x       = event.pos().x()
        start_x = (self.start_time / self.duration) * self.width() if self.duration > 0 else 0
        end_x   = (self.end_time   / self.duration) * self.width() if self.duration > 0 else 0

        if abs(x - start_x) < 10:
            self.dragging_handle = 'start'
        
        elif abs(x - end_x) < 10:
            self.dragging_handle = 'end'
        
        else:
            self.dragging_handle = None
            
            if not self.is_loading and not self.is_playing:
                time_position = (x / self.width()) * self.duration
                
                self.set_playback_position(time_position)
                logger.info(f"Placed playback on {time_position}")

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.dragging_handle:
            return

        x    = max(0, min(self.width(), event.pos().x()))
        time = max(0.0, min(self.duration, (x / self.width()) * self.duration if self.duration > 0 else 0))

        if self.dragging_handle == 'start':
            self.start_time = min(time, self.end_time - 0.1)
            
            if not self.is_playing:
                self.set_playback_position(self.start_time)

        elif self.dragging_handle == 'end':
            self.end_time = min(max(time, self.start_time + 0.1), self.duration or time)
            
            if self.playback_position > self.end_time:
                self.set_playback_position(self.end_time)

        self.regionChanged.emit(self.start_time, self.end_time)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.dragging_handle = None

class ContentCanvas(QWidget):
    def __init__(
            self,
            parent: QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.layout_manager = QVBoxLayout(self)
        self.layout_manager.setContentsMargins(0, 0, 0, 0)
        self.layout_manager.setSpacing(12)
        self.layout_manager.setSizeConstraint(QVBoxLayout.SetMinimumSize)

    def sizeHint(self) -> QSize:
        size_hint = self.layout_manager.sizeHint()
        return QSize(size_hint.width(), size_hint.height())

class ElasticScrollArea(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.raw_scroll_position   = 0.0
        self.velocity_speed        = 0.0
        self.scrolling_is_active   = False

        self.setStyleSheet("background: transparent;")

        self.setup_canvas()
        self.setup_timers()
        self.viewport().installEventFilter(self)

    # Setup

    def setup_canvas(self) -> None:
        self.canvas          = QWidget(self.viewport())
        self.layout_manager  = QVBoxLayout(self.canvas)

        self.layout_manager.setContentsMargins(0, 8, 0, 8)
        self.layout_manager.setSpacing(12)
        self.layout_manager.setAlignment(Qt.AlignmentFlag.AlignTop)

    def setup_timers(self) -> None:
        self.idle_timer = Basic.Timer(
            Constants.USER_SCROLL_IDLE_TIMEOUT,
            self.handle_scroll_finished,
            single_shot = True,
            parent = self
        )

        self.animation_timer = Basic.Timer(
            Constants.ANIMATION_TICK_INTERVAL,
            self.process_animation_tick,
            parent = self
        )

    # Widget Management

    def add_widget(self, widget: QWidget) -> None:
        self.layout_manager.addWidget(widget)

    def get_required_width(self) -> int:
        maximum_width = 0

        for index in range(self.layout_manager.count()):
            item   = self.layout_manager.itemAt(index)
            widget = item.widget() if item else None

            if not widget:
                continue

            hint = widget.sizeHint()

            if hint.width() > maximum_width:
                maximum_width = hint.width()

        return max(maximum_width, 400)

    # Events

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update_canvas_geometry()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta      = event.angleDelta().y()
        limit      = self.calculate_maximum_scroll()
        resistance = self.calculate_resistance(limit)

        self.velocity_speed     -= (delta * Constants.current_settings.get("wheel_scroll_sensitivity") / 8.0) * resistance
        self.scrolling_is_active = True

        self.idle_timer.start(Constants.USER_SCROLL_IDLE_TIMEOUT)

        if not self.animation_timer.isActive():
            self.animation_timer.start()

        event.accept()
    
    def hideEvent(self, event):
        self.animation_timer.stop()
        super().hideEvent(event)

    # Animation

    def process_animation_tick(self) -> None:
        limit                     = self.calculate_maximum_scroll()
        self.raw_scroll_position += self.velocity_speed

        overshoot = self.calculate_overshoot(limit)

        self.update_velocity(overshoot)
        self.apply_content_position()

        should_stop = (
            abs(self.velocity_speed) < 0.01 and
            abs(overshoot) < 0.1 and
            not self.scrolling_is_active
        )

        if should_stop:
            self.raw_scroll_position = max(0.0, min(limit, self.raw_scroll_position))
            self.apply_content_position()
            self.animation_timer.stop()

    # Calculation

    def update_canvas_geometry(self) -> None:
        viewport_width = self.viewport().width()
        canvas_height  = self.layout_manager.sizeHint().height()

        self.canvas.resize(viewport_width, canvas_height)

    def calculate_maximum_scroll(self) -> float:
        maximum_scroll = max(0, self.canvas.height() - self.viewport().height())
        return float(maximum_scroll)

    def handle_scroll_finished(self) -> None:
        self.scrolling_is_active = False

    def apply_content_position(self) -> None:
        limit = self.calculate_maximum_scroll()
        raw   = self.raw_scroll_position
        y     = -self.calculate_position(raw, limit)
        
        self.canvas.move(0, int(y))

    def calculate_resistance(self, limit: float) -> float:
        if self.raw_scroll_position >= 0 and self.raw_scroll_position <= limit:
            return 1.0

        if self.raw_scroll_position < 0:
            excess = abs(self.raw_scroll_position)
        
        else:
            excess = self.raw_scroll_position - limit

        resistance = max(0.05, 1.0 / (1.0 + excess / (Constants.VISUAL_RESISTANCE_STRENGTH * 0.5))) * 0.3
        
        return resistance

    def calculate_overshoot(self, limit: float) -> float:
        if self.raw_scroll_position < 0.0:
            return self.raw_scroll_position

        if self.raw_scroll_position > limit:
            return self.raw_scroll_position - limit

        return 0.0

    def update_velocity(self, overshoot: float) -> None:
        if overshoot == 0.0:
            self.velocity_speed *= Constants.current_settings.get("inertia_deceleration_factor", Constants.INERTIA_DECELERATION_RATE)
            return

        if self.scrolling_is_active:
            self.velocity_speed *= 0.8
        
        else:
            spring_force  = -overshoot           * Constants.SPRING_STIFFNESS
            damping_force = -self.velocity_speed * Constants.SPRING_DAMPING_FACTOR

            self.velocity_speed += spring_force + damping_force

    def calculate_position(self, raw: float, limit: float) -> float:
        if raw < 0.0:
            return raw / (1.0 + abs(raw) / Constants.VISUAL_RESISTANCE_STRENGTH)

        if raw > limit:
            excess = raw - limit
            return limit + (excess / (1.0 + excess / Constants.VISUAL_RESISTANCE_STRENGTH))

        return raw