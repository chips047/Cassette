import math
import string
import random

import numpy as np

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System.Common import Utils
from System.Common import Styles

from System.Interface import ThreeaD
from System.Common.Constants import *

from loguru import logger

class ValuePopup(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)

        self.padding = 10
        
        self.original_text = ""
        self.display_text = ""
        self.font = Utils.NType(12)

        self.chars = string.ascii_uppercase + string.punctuation
        self.solved_indices = set()
        self.glitch_timer = QTimer(self)
        self.glitch_timer.setInterval(20)
        self.glitch_timer.timeout.connect(self.glitch_step)

        self.setup_animations()

    def setup_animations(self):
        self.animation_engine = ThreeaD.AnimationEngine()
        self.animation_engine.updated.connect(self._update_position_and_size)

        self.animation_engine.add_property("opacity", 1.0, ThreeaD.MixMode.NOMIX)
        
        self.animation_engine.add_property("position_x", 0.0, ThreeaD.MixMode.NOMIX)
        self.animation_engine.add_property("position_y", 0.0, ThreeaD.MixMode.NOMIX)

        self.animation_engine.add_property("width", 0.0, ThreeaD.MixMode.NOMIX)
        self.animation_engine.add_property("height", 0.0, ThreeaD.MixMode.NOMIX)

        self.manual_hide_timer = QTimer()
        self.manual_hide_timer.setSingleShot(True)
        self.manual_hide_timer.setInterval(1000)
        self.manual_hide_timer.timeout.connect(self.hide)

        self.target_width = 0
        self.target_height = 0
        
        self.opacity = 0
    
    def start_glitch_effect(self, text: str):
        self.original_text = text
        self.solved_indices.clear()
        self.glitch_timer.start()
    
    def glitch_step(self):
        res = []
        
        for i, char in enumerate(self.original_text):
            if i in self.solved_indices:
                res.append(char)
            
            elif char.isspace():
                res.append(char)
            
            else:
                if random.random() < 0.4:
                    self.solved_indices.add(i)
                    res.append(char)

                    continue
                
                res.append(random.choice(self.chars))
        
        self.display_text = "".join(res)
        self.update()

        if len(self.solved_indices) >= len(self.original_text.replace(" ", "")):
            self.display_text = self.original_text
            self.glitch_timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        alpha = int(self.opacity * 255)
        bg_color = QColor(Styles.Colors.secondary_background)
        bg_color.setAlpha(alpha)
        
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 8, 8)

        text_color = QColor(Qt.white)
        text_color.setAlpha(alpha)
        
        painter.setPen(text_color)
        painter.setFont(self.font)
        painter.translate(self.padding, self.padding)
        
        painter.drawText(
            self.rect(),
            Qt.AlignLeft, self.display_text
        )

    def _layout_for_text(self, text: str):
        self.original_text = text
        metrics = QFontMetrics(self.font)

        max_allowed_width = 700

        rect = metrics.boundingRect(
            0, 0, 
            max_allowed_width, 1000, 
            Qt.TextWordWrap, 
            text
        )

        self.target_width = rect.width() + self.padding * 2
        self.target_height = rect.height() + self.padding * 2

        self.animation_engine.set_target_value(
            "width",
            self.target_width, 500,
            ThreeaD.Easing.ease_out_cubic
        )

        self.animation_engine.set_target_value(
            "height",
            self.target_height, 500,
            ThreeaD.Easing.ease_out_cubic
        )

    def _compute_top_left(self, pos: QPoint):
        w = self.target_width

        desired_x = pos.x() - w // 2
        desired_y = pos.y() + 5

        return desired_x, desired_y

    def _update_position_and_size(self):
        x = int(self.animation_engine.get_property_value("position_x"))
        y = int(self.animation_engine.get_property_value("position_y"))

        w = int(self.animation_engine.get_property_value("width"))
        h = int(self.animation_engine.get_property_value("height"))

        self.opacity = self.animation_engine.get_property_value("opacity")

        self.setGeometry(x, y, w, h)
        self.update()

    def show_text(self, text: str, pos: QPoint, auto_hide: bool = False):
        if auto_hide:
            if self.manual_hide_timer.isActive():
                self.manual_hide_timer.stop()
            
            self.manual_hide_timer.start()

        self._layout_for_text(text)

        self.start_glitch_effect(text)

        x, y = self._compute_top_left(pos)

        self.animation_engine.set_target_value(
            "position_x",
            x, 350,
            ThreeaD.Easing.ease_out_cubic
        )

        self.animation_engine.set_target_value(
            "position_y",
            y, 350,
            ThreeaD.Easing.ease_out_cubic
        )

        if not self.isVisible():
            self.show()
    
    def fade_in(self):
        start_value = self.animation_engine.get_property_value("opacity")

        self.animation_engine.animate(
            "opacity",
            [
                (0.0, start_value),
                (1.0, 1.0)
            ], 300, ThreeaD.Easing.ease_out_cubic
        )
    
    def fade_out(self):
        start_value = self.animation_engine.get_property_value("opacity")

        self.animation_engine.animate(
            "opacity",
            [
                (0.0, start_value),
                (1.0, 0.0)
            ], 300, ThreeaD.Easing.ease_out_cubic, self.on_hide_finished
        )
    
    def on_hide_finished(self):
        self.animation_engine.pause()
        super().hide()

    def show(self):
        self.animation_engine.resume()
        self.fade_in()
        super().show()

    def hide(self):
        self.fade_out()

    def cleanup(self):
        self.animation_engine.clear()

        super().hide()
        self.deleteLater()

class MiniWaveformPreview(QWidget):
    preview_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._audio = None
        self._min_samples = np.array([])
        self._max_samples = np.array([])
        self._waveform_max = 1.0

        self.pixmap = None
        self.mouse_pressed = False
        self.playhead_position = 0.0

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(Styles.Controls.MiniWaveformPreview)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    
    def set_audio_data(self, audio: np.ndarray) -> None:
        self._audio = audio
        self._prepare_audio_data()
        self._regen_pixmap()
        self.update()

    def set_playhead_position(self, value: float) -> None:
        self.playhead_position = float(np.clip(value, 0.0, 1.0))
        self.update()

    def _prepare_audio_data(self) -> None:
        audio = self._audio
        if audio is None or audio.size == 0:
            self._min_samples = np.array([])
            self._max_samples = np.array([])
            self._waveform_max = 1.0
            return

        total_samples = audio.shape[0]

        fade_in = min(int(total_samples * 0.03), total_samples)
        fade_out = min(int(total_samples * 0.03), max(0, total_samples - fade_in))

        proc = audio.astype(np.float32, copy=True)

        if fade_in > 0:
            fade_in_mask = np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
            proc[:fade_in, :] *= fade_in_mask[:, None]

        if fade_out > 0:
            fade_out_mask = np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
            start = total_samples - fade_out
            proc[start:, :] *= fade_out_mask[:, None]

        self._min_samples = np.min(proc, axis=1)
        self._max_samples = np.max(proc, axis=1)

        scale = 1.0

        max_abs = max(np.max(np.abs(self._min_samples)), np.max(np.abs(self._max_samples)))
        self._waveform_max = max(max_abs / scale, 1e-6)

    def generate_pixmap(self):
        w = max(1, self.width() - 4)
        h = max(1, self.height() - 10)

        min_s = self._min_samples
        max_s = self._max_samples
        wm = self._waveform_max

        if min_s.size == 0 or len(min_s) == 0:
            return None

        num_samples = len(min_s)
        samples_per_pixel = max(1, int(np.ceil(num_samples / float(w))))
        pad_needed = (-num_samples) % samples_per_pixel
        
        if pad_needed:
            padded_min = np.pad(min_s, (0, pad_needed), mode='constant')
            padded_max = np.pad(max_s, (0, pad_needed), mode='constant')
        
        else:
            padded_min = min_s
            padded_max = max_s

        reshaped_min = padded_min.reshape(-1, samples_per_pixel)
        reshaped_max = padded_max.reshape(-1, samples_per_pixel)

        tile_min = np.min(reshaped_min, axis=1).astype(np.float32)
        tile_max = np.max(reshaped_max, axis=1).astype(np.float32)

        tile_max_f = tile_max / wm
        tile_min_f = tile_min / wm

        y_center = h / 2.0
        top = y_center - (tile_max_f * y_center)
        bottom = y_center - (tile_min_f * y_center)

        sigma = float(CurrentSettings.get("waveform_smoothing", 0.0))

        if sigma > 0.0 and top.size > 1:
            pad = int(np.ceil(sigma * 3.0))
            pad = min(pad, top.size - 1)
            
            top_p = np.pad(top, (pad, pad), mode='reflect')
            bottom_p = np.pad(bottom, (pad, pad), mode='reflect')
            
            top = Utils.gaussian_filter1d_np(top_p, sigma=sigma)[pad:pad + top.size]
            bottom = Utils.gaussian_filter1d_np(bottom_p, sigma=sigma)[pad:pad + bottom.size]

        if top.size == bottom.size:
            mask = top > bottom
            
            if np.any(mask):
                avg = (top[mask] + bottom[mask]) * 0.5
                top[mask] = avg
                bottom[mask] = avg

        if top.size == 0:
            return None

        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)

        if CurrentSettings.get("antialiasing"):
            painter.setRenderHint(QPainter.Antialiasing)

        bar_w = float(w) / float(top.size)

        path = QPainterPath()
        x0 = 0.0
        y0 = float(np.clip(top[0], 0.0, h))
        
        path.moveTo(x0, y0)
        
        for i in range(1, top.size):
            x = i * bar_w
            y = float(np.clip(top[i], 0.0, h))
            path.lineTo(x, y)
        
        for i in range(bottom.size - 1, -1, -1):
            x = i * bar_w
            y = float(np.clip(bottom[i], 0.0, h))
            path.lineTo(x, y)
        
        path.closeSubpath()
        
        border_color = QColor(170, 170, 170, 255)
        fill_color = QColor(255, 255, 255, 100)
        
        painter.setPen(QPen(border_color, 2.0))
        painter.setBrush(QBrush(fill_color))
        painter.drawPath(path)
        painter.end()

        return pixmap

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.pixmap:
            painter.drawPixmap(2, 5, self.pixmap)

            pen = QPen(QColor(255, 0, 0), 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            x = float(self.width()) * self.playhead_position
            painter.drawLine(QLineF(x, 0.0, x, float(self.height())))

        painter.end()

    def mousePressEvent(self, event):
        if self.pixmap and event.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = True
            norm = float(np.clip(event.x() / float(max(1, self.width())), 0.0, 1.0))
            self.set_playhead_position(norm)
            
            self.preview_clicked.emit(norm)
        
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        norm = float(np.clip(event.x() / float(max(1, self.width())), 0.0, 1.0))
        self.set_playhead_position(norm)
        self.preview_clicked.emit(norm)
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.mouse_pressed = False
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        
        if self.isVisible():
            self._regen_pixmap()
            self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._regen_pixmap()

    def _regen_pixmap(self) -> None:
        self.pixmap = self.generate_pixmap()

from typing import List, Dict, Iterable, Optional
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import QTimer, QElapsedTimer, Qt
from PyQt5.QtGui import QPainter, QColor, QLinearGradient

FPS_60 = 60


class ScheduledSegmentedBar(QWidget):
    def __init__(
        self,
        number_of_segments: int = 30,
        base_thickness: int = 20,
        loop: bool = False,
        fps: int = FPS_60,
    ) -> None:
        
        super().__init__()

        self.number_of_segments: int = max(1, number_of_segments)
        self._loop: bool = bool(loop)

        self._schedule: List[Dict] = []
        self.duration_ms: int = 0
        self.start_offset: int = 0
        self.levels: List[float] = [0.0] * self.number_of_segments

        self.setFixedHeight(base_thickness)
        self._color_off: QColor = QColor("#404040")
        self._color_on: QColor = QColor("#ffffff")

        interval_ms = int(1000 / max(1, fps))
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._tick)

        self.elapsed_timer = QElapsedTimer()

        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_schedule(self, schedule):
        self._schedule = schedule or []

        self.duration_ms = max(
            (item.get("start", 0) + item.get("duration", 0) for item in self._schedule),
            default=0,
        )

    def play(self, start_offset_ms = 0):
        self.start_offset = int(start_offset_ms)
        self.elapsed_timer.start()
        self.timer.start()

    def stop(self, clear_levels = True):
        self.timer.stop()

        if clear_levels:
            self.levels = [0.0] * self.number_of_segments
            self.update()

    def is_playing(self):
        return self.timer.isActive()

    def set_colors(self, off = None, on = None):
        if off is not None:
            self._color_off = off
        
        if on is not None:
            self._color_on = on
        
        self.update()

    def _blend_color(self, c0, c1, t):
        t = max(0.0, min(1.0, float(t)))
        
        r = int(c0.red() + (c1.red() - c0.red()) * t)
        g = int(c0.green() + (c1.green() - c0.green()) * t)
        b = int(c0.blue() + (c1.blue() - c0.blue()) * t)
        a = int(c0.alpha() + (c1.alpha() - c0.alpha()) * t)
        
        return QColor(r, g, b, a)

    def _active_indices(self, item):
        segs = item.get("segments")

        if segs is None:
            return range(self.number_of_segments)
        
        return (i for i in segs if 0 <= i < self.number_of_segments)

    def _tick(self):
        if not self._schedule or not self.timer.isActive():
            return

        now = int(self.elapsed_timer.elapsed()) + int(self.start_offset)

        if self.duration_ms and now >= self.duration_ms:
            if self._loop:
                self.elapsed_timer.restart()
                self.start_offset = 0
                return
            
            else:
                self.stop(clear_levels=True)
                return

        new_levels = [0.0] * self.number_of_segments

        for item in self._schedule:
            t_start = int(item.get("start", 0))
            dur = int(item.get("duration", 0))
            
            if dur <= 0:
                continue
            
            if not (t_start <= now <= t_start + dur):
                continue

            progress = (now - t_start) / dur
            b_start = float(item.get("brightness", 0.0))
            b_end = float(item.get("end_brightness", b_start))
            val = b_start + (b_end - b_start) * progress

            for i in self._active_indices(item):
                if 0 <= i < self.number_of_segments:
                    if val > new_levels[i]:
                        new_levels[i] = val

        if new_levels != self.levels:
            self.levels = new_levels
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        w = max(1, self.width())
        grad = QLinearGradient(0, 0, w, 0)

        denom = max(1, self.number_of_segments - 1)
        
        for i, level in enumerate(self.levels):
            t = max(0.0, min(level / 100.0, 1.0))
            pos = i / denom
            grad.setColorAt(pos, self._blend_color(self._color_off, self._color_on, t))

        painter.setBrush(grad)

        r = self.height() / 2
        painter.drawRoundedRect(self.rect(), r, r)

        painter.end()

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
        self.bpm = 120.0

        self.start_pos = QPointF()
        self.marquee_pen = QPen(
            QColor(215, 20, 31),
            1,
            Qt.PenStyle.DashLine
        )
        
        self.setup_animations()
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.hide()
    
    def setup_animations(self):
        self.bpm_animation_timer = QTimer(self)
        self.bpm_animation_timer.setSingleShot(True)
        self.bpm_animation_timer.timeout.connect(self.bpm_tick)

        self.animation_engine = ThreeaD.AnimationEngine()
        self.animation_engine.updated.connect(self.on_animation_updated)

        self.animation_engine.add_property("bpm_pulse", 0.0, ThreeaD.MixMode.ADD)

        self.animation_engine.add_property("mouse_x", 0.0, ThreeaD.MixMode.NOMIX)
        self.animation_engine.add_property("mouse_y", 0.0, ThreeaD.MixMode.NOMIX)
        
        self.animation_engine.add_property("brush_opacity", 1.0, ThreeaD.MixMode.NOMIX)
        self.animation_engine.add_property("pen_opacity", 1.0, ThreeaD.MixMode.NOMIX)

    def on_animation_updated(self):
        self.prepareGeometryChange() 
        self.update()

    def boundingRect(self):
        curr_x = self.animation_engine.get_property_value("mouse_x")
        curr_y = self.animation_engine.get_property_value("mouse_y")
        return QRectF(self.start_pos, QPointF(curr_x, curr_y)).normalized()
    
    def _apply_bpm_to_alpha(self, base_alpha, opacity):
        pulse = self.animation_engine.get_property_value("bpm_pulse")
        alpha = int(base_alpha * opacity * (1.0 + pulse))
        
        return max(0, min(255, alpha))

    def paint(self, painter: QPainter, option, widget):
        brush_alpha = self.animation_engine.get_property_value("brush_opacity")
        pen_alpha = self.animation_engine.get_property_value("pen_opacity")
        
        curr_x = self.animation_engine.get_property_value("mouse_x")
        curr_y = self.animation_engine.get_property_value("mouse_y")
        rect = QRectF(self.start_pos, QPointF(curr_x, curr_y)).normalized()

        painter.setRenderHint(QPainter.Antialiasing)

        b_color = QColor(255, 0, 0)
        b_color.setAlpha(self._apply_bpm_to_alpha(50, brush_alpha))
        
        p_color = QColor(self.marquee_pen.color())
        p_color.setAlpha(int(200 * pen_alpha))
        pen = QPen(self.marquee_pen)
        pen.setColor(p_color)

        radius = min((rect.width() + rect.height()) / 12, 10)

        painter.setPen(pen)
        painter.setBrush(QBrush(b_color))
        painter.drawRoundedRect(rect, radius, radius)

    def update_end_point(self, point: QPointF):
        self.animation_engine.set_target_value("mouse_x", point.x(), 150, ThreeaD.Easing.ease_out_cubic)
        self.animation_engine.set_target_value("mouse_y", point.y(), 150, ThreeaD.Easing.ease_out_cubic)

        rect = QRectF(self.start_pos, point).normalized()
        path = QPainterPath()
        path.addRect(rect)
        
        modifiers = QApplication.keyboardModifiers()

        selection_op = (
            Qt.ItemSelectionOperation.AddToSelection 
            if modifiers & Qt.ControlModifier 
            else Qt.ItemSelectionOperation.ReplaceSelection
        )

        self.scene().setSelectionArea(
            path,
            selection_op,
            Qt.ItemSelectionMode.IntersectsItemShape,
            QTransform()
        )

    def fade_in(self):
        self.animation_engine.resume()

        self.animation_engine.animate(
            "brush_opacity",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 300, ThreeaD.Easing.ease_out_cubic
        )

        self.animation_engine.animate(
            "pen_opacity",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 300, ThreeaD.Easing.ease_out_cubic
        )
    
    def fade_out(self):
        if not CurrentSettings["marquee_hide_animation"]:
            self.animation_engine.set_property_base_value("brush_opacity", 0.0)
            self.animation_engine.set_property_base_value("pen_opacity", 0.0)

            self._finish_and_hide()

            return

        self.animation_engine.animate(
            "brush_opacity",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 
            230, ThreeaD.Easing.ease_out_cubic,
        )

        QTimer.singleShot(70, self._animate_pen_out)
    
    def bpm_tick(self):
        if not self.player.is_playing or not self.isVisible() or self.player.get_current_audio_level() < 0.08:
            return self.bpm_animation_timer.start(FPS_30)

        speed = self.player.speed or 1.0
        interval_ms = int(round(60000.0 / (self.bpm * speed)))

        self.animation_engine.animate(
            "bpm_pulse",
            [
                (0.0, 0.5),
                (1.0, 0.0)
            ],
            interval_ms, ThreeaD.Easing.ease_out_cubic
        )

        self.bpm_animation_timer.start(interval_ms)

    def _animate_pen_out(self):
        self.animation_engine.animate(
            "pen_opacity",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            300, ThreeaD.Easing.ease_out_cubic, 
            self._finish_and_hide
        )

    def set_bpm(self, bpm):
        self.bpm = bpm

    def start_marquee(self, start_point):
        self.start_pos = start_point
        
        self.animation_engine.set_property_base_value("mouse_x", start_point.x())
        self.animation_engine.set_property_base_value("mouse_y", start_point.y())
        
        self.fade_in()
        self.show()
        
        if CurrentSettings["bpm_animations"]:
            self.bpm_tick()

    def end_marquee(self):
        self.fade_out()

    def _finish_and_hide(self):
        self.animation_engine.pause()
        self.bpm_animation_timer.stop()
        self.hide()

class GlyphItem(QGraphicsObject):
    def __init__(
        self,
        glyph_id,
        glyph_data,
        conductor,
        
        animate_spawn = True
    ):

        super().__init__()
        
        self.hide()
        
        self.glyph_id = glyph_id
        self.conductor = conductor

        self.duration_ms = glyph_data['duration']
        self.start_ms = glyph_data['start']
        self.track = glyph_data['track']

        self.setup_animations()
        self.setup_flags()
        self.setup_timers()
        self.setup_keyframes()
        
        self.border_width = 2.5
        
        self.was_clicked = False
        self.resize_margin = 10
        self.interaction_mode = None
        self.drag_start_pos = QPointF()

        self.fixed_y = self.calculate_y_pos()
        self.dirty_rect = self.boundingRect()

        self.update_geometry()
        self.spawn_animation(animate_spawn)
        
        self.show()
    
    def setup_flags(self):
        self.setFlags(
            QGraphicsItem.ItemIsSelectable | 
            QGraphicsItem.ItemSendsGeometryChanges
        )

        self.setCacheMode(QGraphicsItem.ItemCoordinateCache)
        self.setAcceptHoverEvents(True)
    
    def setup_timers(self):
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(1000)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self._on_hover_timeout)

    def setup_keyframes(self):
        self.keyframe_line_padding = 12
        self.keyframe_line_width = 4

        self.fade_keyframe_enabled = False
        self.fade_keyframes = [(0.0, 0.0), (1.0, 0.0)]
        self._fade_dragging = False
        self._fade_dragged_idx = None

    def setup_animations(self):
        self.anim_margin = 0
        self.is_animating = False

        self.marquee_selection_scale = 1.0

        self.spawn_scale = 1.0
        self.despawn_scale = 1.0

        self.tilt_x = 0.0
        self.tilt_y = 0.0

        self.border_opacity = 0.0
    
    def calculate_y_pos(self):
        top_margin = Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.box_spacing
        row_height = Styles.Metrics.Tracks.row_height + Styles.Metrics.Tracks.box_spacing
        
        track_top = top_margin + ((int(self.track) - 1) * row_height)
        offset_in_row = (Styles.Metrics.Tracks.row_height - Styles.Metrics.Tracks.box_height) / 2 
        
        return track_top + offset_in_row

    def _ms_to_px(self, ms):
        return ms * self.conductor.px_per_sec / 1000.0

    def _px_to_ms(self, px):
        return px * 1000.0 / self.conductor.px_per_sec

    def boundingRect(self):
        m = self.anim_margin + self.border_width
        return QRectF(-m, -m, self._ms_to_px(self.duration_ms) + 2*m, Styles.Metrics.Tracks.box_height + 2*m)

    def paint(self, painter: QPainter, option, widget = None):
        scale = self.marquee_selection_scale * self.spawn_scale * self.despawn_scale
        rotation_x = self.tilt_x
        rotation_y = self.tilt_y
        border_opacity = self.border_opacity

        height = Styles.Metrics.Tracks.box_height
        width_px = self._ms_to_px(self.duration_ms)

        center_x = width_px / 2
        center_y = height / 2

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        painter.save()

        painter.translate(center_x, center_y)

        if scale != 1.0:
            painter.scale(scale, scale)

        if rotation_x != 0 or rotation_y != 0:
            transform = QTransform()
            transform.rotate(rotation_x, Qt.Axis.XAxis)
            transform.rotate(rotation_y, Qt.Axis.YAxis)

            painter.setTransform(transform * painter.transform())

        painter.translate(-center_x, -center_y)

        color = QColor(int(255 * border_opacity), 0, 0)

        fill_brush = QBrush(QColor(255, 255, 255))

        border_pen = QPen(color, self.border_width)
        border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        radius = 3 + max(0, min((width_px - 10) / 10 * 2.5, 2.5)) + max(0, min((width_px - 20) / 10 * 6, 6)) 

        painter.setPen(border_pen)
        painter.setBrush(fill_brush)

        painter.drawRoundedRect(
            QRectF(0, 0, width_px, height), 
            radius, radius
        )
        
        width_px -= 2 * self.keyframe_line_padding
        height -= 2 * self.border_width

        if self.fade_keyframe_enabled:
            fade_pen = QPen(color, self.keyframe_line_width)
            fade_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            fade_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            
            painter.setPen(fade_pen)

            fade_path = QPainterPath()
            
            for idx, (fx, fy) in enumerate(self.fade_keyframes):
                px = fx * width_px + self.keyframe_line_padding
                py = fy * height + self.border_width
                
                if idx == 0:
                    fade_path.moveTo(px, py)
                
                else:
                    fade_path.lineTo(px, py)
            
            painter.drawPath(fade_path)
            painter.setPen(Qt.NoPen)
            
            for fx, fy in self.fade_keyframes[1:-1]:
                px = fx * width_px + self.keyframe_line_padding
                py = fy * height
                
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPointF(px, py), 6, 6)

        debug_mode = False
        
        if debug_mode:
            rect = self.boundingRect()
            
            painter.setPen(QPen(QColor(255, 0, 0, 150), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            painter.drawRect(rect)
            
            painter.setPen(QColor(0, 0, 255))
            
            painter.drawLine(-5, 0, 5, 0)
            painter.drawLine(0, -5, 0, 5)

        painter.restore()
    
    # Animations - - - - - - - - - - - - -

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

    def set_animating(self, active: bool):
        if self.is_animating == active:
            return

        self.prepareGeometryChange()
        self.is_animating = active

        self.anim_margin = 15.0 if active else 0.0
        self.update()
    
    def fade_in_animation(self):
        self.fade_in = self.make_animation(
            [
                (0.0, self.border_opacity),
                (1.0, 1.0)
            ], b"borderOpacity", 400
        )

        self.fade_in.start()
    
    def fade_out_animation(self):
        self.fade_out = self.make_animation(
            [
                (0.0, self.border_opacity),
                (1.0, 0.0)
            ], b"borderOpacity", 400
        )

        self.fade_out.finished.connect(self.fade_out_callback)
        self.fade_out.start()

    def fade_out_callback(self):
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

        if self.is_animating:
            self.set_animating(False)

    def spawn_animation(self, animate = True):
        should_animate = animate and CurrentSettings["glyph_spawn_animation"]

        if not should_animate:
            return

        self.set_animating(should_animate)

        self.scale_animation = self.make_animation(
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], b"spawnScale", 400
        )

        self.scale_animation.start()
    
    def despawn_animation(self):
        self.scale_animation = self.make_animation(
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], b"despawnScale", 400
        )

        self.scale_animation.finished.connect(self.on_despawn_finished)
        self.scale_animation.start()
    
    def marquee_select_animation(self):
        self.set_animating(True)

        self.marquee_scale_animation = self.make_animation(
            [
                (0.0, self.marquee_selection_scale),
                (0.5, 1.05),
                (1.0, 1.0)
            ], b"marqueeSelectionScale", 500
        )

        self.marquee_scale_animation.finished.connect(lambda: self.set_animating(False))
        self.marquee_scale_animation.start()
    
    def press_animation(self, pos):
        if not CurrentSettings["glyph_tilt_animation"]:
            return
        
        width_px = self._ms_to_px(self.duration_ms)
        height_px = Styles.Metrics.Tracks.box_height
        
        center_x = width_px / 2
        center_y = height_px / 2
        
        offset_x = pos.x() - center_x
        offset_y = pos.y() - center_y

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
    
        tilt_x_animation = self.make_animation(
            [
                (0.0, self.tilt_x),
                (0.5, target_tilt_x),
                (1.0, 0.0)
            ], b"tiltX", 700
        )

        tilt_y_animation = self.make_animation(
            [
                (0.0, self.tilt_y),
                (0.5, target_tilt_y),
                (1.0, 0.0)
            ], b"tiltY", 700
        )

        self.group_animate(
            [
                tilt_x_animation,
                tilt_y_animation
            ], lambda: self.set_animating(False)
        )
    
    # Animation Properties

    @pyqtProperty(float) # type: ignore
    def borderOpacity(self):
        return self.border_opacity

    @borderOpacity.setter
    def borderOpacity(self, value):
        self.border_opacity = value
        self.update()
    
    @pyqtProperty(float) # type: ignore
    def tiltY(self):
        return self.tilt_y

    @tiltY.setter
    def tiltY(self, value):
        self.tilt_y = value
        self.update()
    
    @pyqtProperty(float) # type: ignore
    def tiltX(self):
        return self.tilt_x

    @tiltX.setter
    def tiltX(self, value):
        self.tilt_x = value
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
    
    @pyqtProperty(float) # type: ignore
    def marqueeSelectionScale(self):
        return self.marquee_selection_scale
    
    @marqueeSelectionScale.setter
    def marqueeSelectionScale(self, value):
        self.marquee_selection_scale = value
        self.update()
    
    # Events - - - - - - - - - - - -

    def hoverEnterEvent(self, event):
        if not self.conductor.glyph_controller._drag_session:
            self.hover_timer.start()
        
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.hover_timer.stop()
        self.conductor.tooltip.hide_tooltip()

        super().hoverLeaveEvent(event)

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
        
        if not self.interaction_mode:
            self.hover_timer.start()
        
        super().hoverMoveEvent(event)

    def itemChange(self, change, value):
        if not change == QGraphicsItem.ItemSelectedChange:
            return super().itemChange(change, value)
        
        if value:
            if not self.was_clicked:
                self.marquee_select_animation()
            
            self.was_clicked = False

            self.fade_in_animation()
            self.setCacheMode(QGraphicsItem.NoCache)

        else:
            self.fade_out_animation()
        
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.was_clicked = True

        self.hover_timer.stop()

        if self.fade_keyframe_enabled and (event.modifiers() & Qt.AltModifier):
            x = event.pos().x()
            y = event.pos().y()
            
            width_px = self._ms_to_px(self.duration_ms) - self.keyframe_line_padding * 2
            height = Styles.Metrics.Tracks.box_height
            
            min_dist = 12
            idx = None
            
            for i, (fx, fy) in enumerate(self.fade_keyframes[1:-1], 1):
                px = fx * width_px
                py = fy * height
                
                dist = math.hypot(x - px, y - py)
                
                if dist < min_dist:
                    min_dist = dist
                    idx = i
            
            if idx is not None:
                self._fade_dragging = True
                self._fade_dragged_idx = idx
                event.accept()
                return
            
            fx = min(max(x / width_px, 0.01), 0.99)
            fy = min(max(y / height, 0.0), 1.0)
            
            self.fade_keyframes.append((fx, fy))
            self.fade_keyframes = sorted(self.fade_keyframes, key=lambda p: p[0])
            
            self._fade_dragging = True
            self._fade_dragged_idx = self.fade_keyframes.index((fx, fy))
            
            self.update()
            event.accept()
            
            return

        self.drag_start_pos = event.scenePos()
        self.interaction_mode = None

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
            self.interaction_mode = 'resize_left'
        
        elif x > visual_width - self.resize_margin:
            self.interaction_mode = 'resize_right'
        
        else:
            self.interaction_mode = 'move'
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        self.conductor.glyph_controller.start_drag()
        self.press_animation(event.pos())
        event.accept()

    def mouseMoveEvent(self, event):
        if self.fade_keyframe_enabled and self._fade_dragging and self._fade_dragged_idx is not None:
            width_px = self._ms_to_px(self.duration_ms) - 2 * self.keyframe_line_padding
            height = Styles.Metrics.Tracks.box_height

            x = event.pos().x() - self.keyframe_line_padding
            x = min(max(x, 0), width_px)
            y = min(max(event.pos().y(), 0), height)

            desired_x = x / width_px
            idx = self._fade_dragged_idx
            
            left = self.fade_keyframes[idx - 1][0] + 0.01
            right = self.fade_keyframes[idx + 1][0] - 0.01
            
            fx = min(max(desired_x, left), right)
            fx = min(max(fx, 0.0), 1.0)
            fy = min(max(y / height, 0.0), 1.0)

            if 0 < idx < len(self.fade_keyframes) - 1:
                self.fade_keyframes[idx] = (fx, fy)
                self.update()
            
            event.accept()
            
            return

        if not self.interaction_mode:
            return super().mouseMoveEvent(event)
        
        self.conductor.mouse_controller.auto_scroller.process_pos(event.screenPos())

        current_scene_pos = event.scenePos()
        delta_px = current_scene_pos.x() - self.drag_start_pos.x()
        delta_ms = self._px_to_ms(delta_px)

        self.conductor.glyph_controller.update_drag_state(
            delta_ms,
            self.interaction_mode,
            self
        )

    def mouseReleaseEvent(self, event):
        if self.fade_keyframe_enabled and self._fade_dragging:
            self._fade_dragging = False
            self._fade_dragged_idx = None
            
            keyframes_str = ' '.join(f'{fx:.2f} {fy:.2f}' for fx, fy in self.fade_keyframes)
            event.accept()
            
            return

        self.conductor.mouse_controller.stop_auto_scroll_drag()

        self.interaction_mode = None
        
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.ungrabMouse()
        
        self.conductor.glyph_controller.end_drag()
        
        if not CurrentSettings["glyph_tilt_animation"]:
            return

    # API - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def update_geometry(self, start_ms: int = None, duration_ms: int = None):
        self.prepareGeometryChange()

        if start_ms is not None:
            self.start_ms = start_ms
        
        if duration_ms is not None:
            self.duration_ms = max(10, duration_ms)

        new_x = self._ms_to_px(self.start_ms)
        self.setPos(new_x, self.fixed_y)

        self.update()

    def remove_glyph(self):
        self.fade_out_animation()
        
        if CurrentSettings["glyph_spawn_animation"]:
            self.despawn_animation()
        
        else:
            self.on_despawn_finished()
    
    # Callbacks - - - - - - - - - - -

    def on_despawn_finished(self):
        self.scene().removeItem(self)
        self.deleteLater()
    
    def _on_hover_timeout(self):
        self.conductor.tooltip.show_hover_tooltip(self)

class TrimmingWaveformWidget(QWidget):
    regionChanged = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0
        self.peaks = []
        self.is_loading = True
        self.waveform_pixmap = None
        self._is_playing = False

        self.start_time = 0.0
        self.end_time = 0.0
        
        self.waveform_amplitudes = []

        self.dragging_handle = None
        self._playback_position = 0.0

        self.setMinimumHeight(80)
        self.setFixedWidth(690)

    def _generate_pixmap(self):
        width = self.width()
        height = self.height()
        y_center = height * 0.5

        amplitudes = self.waveform_amplitudes
        count = len(amplitudes)

        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(Styles.Colors.Floating.background))

        painter = QPainter(pixmap)

        if CurrentSettings["antialiasing"]:
            painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()

        x_step = width / count

        clamp_min = 0
        clamp_max = height

        for i, amp in enumerate(amplitudes):
            x = i * x_step
            y = y_center - amp * y_center
            y = max(clamp_min, min(clamp_max, y))

            if i == 0:
                path.moveTo(x, y)
            
            else:
                path.lineTo(x, y)

        for i in range(count - 1, -1, -1):
            amp = amplitudes[i]
            x = i * x_step
            y = y_center + amp * y_center
            y = max(clamp_min, min(clamp_max, y))

            path.lineTo(x, y)

        path.closeSubpath()

        color = QColor(Styles.Colors.Waveform.main_color)

        painter.setPen(QPen(color, 2.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(255, 255, 255, 160), 0.7))
        painter.drawPath(path)

        painter.end()

        self.waveform_pixmap = pixmap
    
    def set_data(self, audio_data, sampling_rate, waveform_amplitudes):
        self.audio_data = audio_data
        self.waveform_amplitudes = waveform_amplitudes
        
        self.duration = len(audio_data) / sampling_rate if sampling_rate > 0 else 0
        self.end_time = self.duration
        self.is_loading = False

        self._generate_pixmap()
        self.update()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        # Loading Text
        if self.is_loading:
            painter.setPen(QColor("#888"))
            painter.setFont(Utils.NType(15))
            painter.drawText(self.rect(), Qt.AlignLeft, "Loading the audio...")
            
            return

        # Pixmap Drawing
        if self.waveform_pixmap:
            painter.drawPixmap(0, 0, self.waveform_pixmap)

        start_x = (self.start_time / self.duration) * self.width() if self.duration > 0 else 0
        end_x = (self.end_time / self.duration) * self.width() if self.duration > 0 else 0

        start_x = max(0, min(self.width(), start_x))
        end_x = max(0, min(self.width(), end_x))

        # Region Highlight
        painter.setBrush(QColor(255, 255, 255, 30))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            QRectF(
                QPointF(start_x, 0),
                QPointF(end_x, self.height())
            ),
            
            10, 10
        )

        # Handles
        painter.setPen(QPen(QColor(Styles.Colors.nothing_accent), 2))
        
        painter.drawLine(
            int(start_x), 10,
            int(start_x), self.height() - 10
        )
        
        painter.drawLine(
            int(end_x), 10,
            int(end_x), self.height() - 10
        )

        # Playhead
        width = 2
        playhead_x = (self._playback_position / self.duration) * self.width() if self.duration > 0 else 0
        
        color = QColor(Styles.Colors.nothing_accent)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        
        painter.drawRect(
            QRectF(
                playhead_x - width / 2, 0,
                width, self.height()
            )
        )

    def mousePressEvent(self, event):
        x = event.pos().x()
        
        start_x = (self.start_time / self.duration) * self.width() if self.duration > 0 else 0
        end_x = (self.end_time / self.duration) * self.width() if self.duration > 0 else 0

        if abs(x - start_x) < 10:
            self.dragging_handle = 'start'
        
        elif abs(x - end_x) < 10:
            self.dragging_handle = 'end'
        
        else:
            self.dragging_handle = None
            
            if self.is_loading:
                return
            
            if self._is_playing:
                return
            
            time_pos = (x / self.width()) * self.duration
            self.set_playback_position(time_pos)

            logger.info(f"Placed playback on {time_pos}")

    def mouseMoveEvent(self, event):
        if not self.dragging_handle:
            return
        
        x = event.pos().x()
        x = max(0, min(self.width(), x))
        
        time = (x / self.width()) * self.duration if self.duration > 0 else 0
        time = max(0, min(self.duration, time))

        if self.dragging_handle == 'start':
            self.start_time = min(time, self.end_time - 0.1)
            
            if not self._is_playing:
                self.set_playback_position(self.start_time)

        elif self.dragging_handle == 'end':
            self.end_time = max(time, self.start_time + 0.1)
            self.end_time = min(self.end_time, self.duration if self.duration > 0 else self.end_time)
            
            if self._playback_position > self.end_time:
                self.set_playback_position(self.end_time)

        self.regionChanged.emit(self.start_time, self.end_time)
        self.update()

    def mouseReleaseEvent(self, event):
        self.dragging_handle = None

    def set_times(self, start, end):
        duration = self.duration
        start = max(0.0, start)
        end = min(duration if duration > 0 else end, end)
        
        if end <= start + 0.01:
            end = start + 0.01
            
            if duration > 0 and end > duration:
                start = max(0.0, duration - 0.01)
                end = duration

        self.start_time = start
        self.end_time = end
        
        self.update()

    def set_playback_position(self, pos):
        self._playback_position = max(0, min(self.duration, pos))
        self.update()

    def set_is_playing(self, is_playing):
        self._is_playing = is_playing