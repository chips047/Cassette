from __future__ import annotations

import numpy

from PyQt6.QtCore import (
    Qt,
    QLineF,
    QRectF,
    QTimer,
    QPointF,
    pyqtSignal
)

from PyQt6.QtGui import (
    QPen,
    QBrush,
    QColor,
    QPixmap,
    QPainter,
    QPolygonF,
    QShowEvent,
    QPaintEvent,
    QMouseEvent,
    QResizeEvent,
    QPainterPath,
    QLinearGradient,
    QGuiApplication
)

from PyQt6.QtWidgets import (
    QWidget,
    QSizePolicy
)

from loguru import logger

from System.Common import (
    Dev,
    Utils,
    Styles,
    Constants
)

from System.Interface.Animation import LoomEngine

from System.Interface.Widgets import (
    WaveMode,
    PulseStatusWidget
)

# Waveform Geometry Helpers

def create_waveform_polygon_path(
        top_coordinates:    numpy.ndarray,
        bottom_coordinates: numpy.ndarray,
        width_px:           float,
        height_px:          float
    ) -> QPainterPath:

    sample_count = top_coordinates.size
    polygon      = QPolygonF()

    x_step_px = float(width_px) / float(sample_count)

    for index in range(sample_count):
        x_coordinate_px = index * x_step_px
        y_coordinate_px = float(numpy.clip(top_coordinates[index], 0.0, height_px))

        polygon.append(QPointF(x_coordinate_px, y_coordinate_px))

    for index in range(sample_count - 1, -1, -1):
        x_coordinate_px = index * x_step_px
        y_coordinate_px = float(numpy.clip(bottom_coordinates[index], 0.0, height_px))

        polygon.append(QPointF(x_coordinate_px, y_coordinate_px))

    path = QPainterPath()
    path.addPolygon(polygon)
    path.closeSubpath()

    return path

# Mini Waveform Preview

@Dev.track_ram
class MiniWaveformPreview(QWidget):
    preview_clicked = pyqtSignal(float)

    PLAYHEAD_UPDATE_INTERVAL_MS = 40

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.audio                     = None
        self.min_samples               = numpy.array([])
        self.max_samples               = numpy.array([])
        self.waveform_max              = 1.0
        self.pixmap                    = None
        self.mouse_pressed             = False
        self.playhead_position         = 0.0
        self.painted_playhead_position = 0.0
        self.pending_playhead_position = None

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(Styles.Controls.MiniWaveformPreview)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.cached_wave_pen                  = QPen(QColor(170, 170, 170, 255), 2.0)
        self.cached_wave_brush                = QBrush(QColor(255, 255, 255, 100))
        self.cached_playhead_pen              = QPen(QColor(255, 0, 0), 2.0)
        self.cached_gradient_fade_opaque      = QColor(0, 0, 0, 255)
        self.cached_gradient_fade_transparent = QColor(0, 0, 0, 0)

        self.playhead_update_timer = QTimer(self)
        self.playhead_update_timer.setInterval(self.PLAYHEAD_UPDATE_INTERVAL_MS)
        self.playhead_update_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.playhead_update_timer.timeout.connect(self.apply_pending_playhead_position)

    # Data

    def set_audio_data(self, audio: numpy.ndarray) -> None:
        self.audio = audio

        self.prepare_audio_data()
        self.regenerate_pixmap()
        self.update()

    def set_playhead_position(self, value: float) -> None:
        normalized_value = float(numpy.clip(value, 0.0, 1.0))
        width_px         = max(1, self.width())
        threshold        = 1.0 / float(width_px)

        if abs(normalized_value - self.playhead_position) < threshold:
            return

        self.playhead_position = normalized_value

        if not self.playhead_update_timer.isActive():
            self.apply_pending_playhead_position()
            self.playhead_update_timer.start()

            return

        self.pending_playhead_position = self.playhead_position

    def apply_pending_playhead_position(self) -> None:
        if self.pending_playhead_position is None and self.playhead_update_timer.isActive() and self.painted_playhead_position == self.playhead_position:
            self.playhead_update_timer.stop()

            return

        target_position                = self.pending_playhead_position if self.pending_playhead_position is not None else self.playhead_position
        self.pending_playhead_position = None

        self.repaint_playhead_region(target_position)

    def repaint_playhead_region(self, new_position: float) -> None:
        old_x_px = float(self.width()) * self.painted_playhead_position
        new_x_px = float(self.width()) * new_position

        self.painted_playhead_position = new_position

        half_pen_width_px   = self.cached_playhead_pen.widthF() / 2.0 + 1.0
        left_coordinate_px  = min(old_x_px, new_x_px) - half_pen_width_px
        right_coordinate_px = max(old_x_px, new_x_px) + half_pen_width_px

        dirty_rectangle = QRectF(left_coordinate_px, 0.0, right_coordinate_px - left_coordinate_px, float(self.height())).toAlignedRect()

        self.update(dirty_rectangle)

    def prepare_audio_data(self) -> None:
        audio = self.audio

        if audio is None or audio.size == 0:
            self.min_samples  = numpy.array([])
            self.max_samples  = numpy.array([])
            self.waveform_max = 1.0

            return

        if audio.ndim == 2:
            self.min_samples = numpy.min(audio, axis = 1).astype(numpy.float32)
            self.max_samples = numpy.max(audio, axis = 1).astype(numpy.float32)

        else:
            self.min_samples = audio.astype(numpy.float32)
            self.max_samples = audio.astype(numpy.float32)

        max_absolute      = max(numpy.max(numpy.abs(self.min_samples)), numpy.max(numpy.abs(self.max_samples)))
        self.waveform_max = max(max_absolute, 1e-6)

    # Rendering

    def generate_pixmap(self) -> QPixmap | None:
        width_px     = max(1, self.width() - 4)
        height_px    = max(1, self.height() - 10)
        min_samples  = self.min_samples
        max_samples  = self.max_samples
        waveform_max = self.waveform_max

        if min_samples.size == 0:
            return None

        sample_count      = len(min_samples)
        samples_per_pixel = max(1, int(numpy.ceil(sample_count / float(width_px))))
        padding_needed    = (-sample_count) % samples_per_pixel

        if padding_needed:
            padded_min = numpy.pad(min_samples, (0, padding_needed), mode = 'constant')
            padded_max = numpy.pad(max_samples, (0, padding_needed), mode = 'constant')

        else:
            padded_min = min_samples
            padded_max = max_samples

        tile_min = numpy.min(padded_min.reshape(-1, samples_per_pixel), axis = 1).astype(numpy.float32)
        tile_max = numpy.max(padded_max.reshape(-1, samples_per_pixel), axis = 1).astype(numpy.float32)

        center_y_px = height_px / 2.0
        top         = center_y_px - (tile_max / waveform_max * center_y_px)
        bottom      = center_y_px - (tile_min / waveform_max * center_y_px)

        smoothing_sigma = float(Constants.current_settings.get("waveform_smoothing", 0.0))

        if smoothing_sigma > 0.0 and top.size > 1:
            padding_amount = min(int(numpy.ceil(smoothing_sigma * 3.0)), top.size - 1)
            top            = Utils.gaussian_filter1d_np(numpy.pad(top,    (padding_amount, padding_amount), 'reflect'), smoothing_sigma)[padding_amount:padding_amount + top.size]
            bottom         = Utils.gaussian_filter1d_np(numpy.pad(bottom, (padding_amount, padding_amount), 'reflect'), smoothing_sigma)[padding_amount:padding_amount + bottom.size]

        if top.size == bottom.size:
            inverted_mask = top > bottom

            if numpy.any(inverted_mask):
                average_values        = (top[inverted_mask] + bottom[inverted_mask]) * 0.5
                top[inverted_mask]    = average_values
                bottom[inverted_mask] = average_values

        if top.size == 0:
            return None

        device_pixel_ratio = QGuiApplication.primaryScreen().devicePixelRatio()

        pixmap = QPixmap(int(width_px * device_pixel_ratio), int(height_px * device_pixel_ratio))
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)

        if Constants.current_settings.get("antialiasing"):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = create_waveform_polygon_path(top, bottom, width_px, height_px)

        painter.setPen(self.cached_wave_pen)
        painter.setBrush(self.cached_wave_brush)
        painter.drawPath(path)

        fade_width_px = width_px * 0.05

        gradient = QLinearGradient(0.0, 0.0, float(width_px), 0.0)
        gradient.setColorAt(0.0,                                 self.cached_gradient_fade_transparent)
        gradient.setColorAt(fade_width_px / width_px,            self.cached_gradient_fade_opaque)
        gradient.setColorAt(1.0 - fade_width_px / width_px,      self.cached_gradient_fade_opaque)
        gradient.setColorAt(1.0,                                 self.cached_gradient_fade_transparent)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(0, 0, width_px, height_px, QBrush(gradient))
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
        painter.setClipRect(event.rect())
        painter.drawPixmap(2, 5, self.pixmap)

        x_coordinate_px = float(self.width()) * self.painted_playhead_position

        painter.setPen(self.cached_playhead_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QLineF(x_coordinate_px, 0.0, x_coordinate_px, float(self.height())))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.pixmap or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)

            return

        self.mouse_pressed = True
        normalized_x       = float(numpy.clip(event.position().x() / float(max(1, self.width())), 0.0, 1.0))

        self.set_playhead_position(normalized_x)
        self.preview_clicked.emit(normalized_x)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.mouse_pressed:
            super().mouseMoveEvent(event)

            return

        normalized_x = float(numpy.clip(event.position().x() / float(max(1, self.width())), 0.0, 1.0))

        self.set_playhead_position(normalized_x)
        self.preview_clicked.emit(normalized_x)

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

# Trimming Waveform Widget

@Dev.track_ram
class TrimmingWaveformWidget(QWidget):
    regionChanged = pyqtSignal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.duration_sec        = 0.0
        self.is_loading          = True
        self.is_transitioning    = False
        self.waveform_pixmap     = None
        self.is_playing          = False
        self.playback_position   = 0.0
        self.start_time_sec      = 0.0
        self.end_time_sec        = 0.0
        self.waveform_amplitudes = []
        self.dragging_handle     = None

        self.setMinimumHeight(80)
        self.setFixedWidth(690)

        wave_color = QColor(Styles.Colors.Waveform.MainColor)

        self.cached_wave_pen     = QPen(wave_color, 2.5)
        self.cached_accent_pen   = QPen(QColor(Styles.Colors.NothingAccent), 2)
        self.cached_wave_brush   = QBrush(wave_color)
        self.cached_trim_brush   = QBrush(QColor(255, 255, 255, 30))
        self.cached_accent_brush = QBrush(QColor(Styles.Colors.NothingAccent))

        self.pulse_status_widget = PulseStatusWidget(self)
        self.pulse_status_widget.set_mode(WaveMode.PULSE)
        self.pulse_status_widget.setGeometry(0, 0, 690, 80)
        self.pulse_status_widget.show()

        self.waveform_opacity_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "waveformOpacity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = lambda value: self.update()
        )

    def start_loading(self) -> None:
        self.is_loading          = True
        self.is_transitioning    = False
        self.waveform_pixmap     = None
        self.waveform_amplitudes = []

        self.waveform_opacity_handle.set_base(0.0)

        self.pulse_status_widget.transition_to_white(0)
        self.pulse_status_widget.unflatten(0)
        self.pulse_status_widget.fade_in(0)
        self.pulse_status_widget.setGeometry(self.rect())
        self.pulse_status_widget.show()

        self.update()

    def show_error(self) -> None:
        self.is_loading       = True
        self.is_transitioning = False

        self.waveform_opacity_handle.set_target(
            value                      = 0.0,
            duration_ms                = 200,
            easing_function            = LoomEngine.Easing.smooth,
            multiply_duration_by_speed = False
        )

        self.pulse_status_widget.setGeometry(self.rect())
        self.pulse_status_widget.show()
        self.pulse_status_widget.fade_in(100)
        self.pulse_status_widget.flatten(duration_ms = 400)
        self.pulse_status_widget.transition_to_red(duration_ms = 400)

        self.update()

    def set_data(
            self,
            audio_data:          numpy.ndarray,
            sampling_rate:       int,
            waveform_amplitudes: list[float]
        ) -> None:

        self.waveform_amplitudes = waveform_amplitudes
        self.duration_sec        = len(audio_data) / sampling_rate if sampling_rate > 0 else 0.0
        self.end_time_sec        = self.duration_sec
        self.is_transitioning    = True

        self.generate_pixmap()

        self.pulse_status_widget.set_amplitude(5)
        self.pulse_status_widget.transition_to_sine(1200, LoomEngine.Easing.ease_out_cubic)

        QTimer.singleShot(300, self.begin_waveform_fade)

    def begin_waveform_fade(self) -> None:
        if not self.is_transitioning:
            return

        self.pulse_status_widget.fade_out(duration_ms = 400)

        self.waveform_opacity_handle.set_target(
            value                      = 1.0,
            duration_ms                = 250,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

        QTimer.singleShot(400, self.complete_waveform_fade)

    def complete_waveform_fade(self) -> None:
        self.is_loading       = False
        self.is_transitioning = False

        self.pulse_status_widget.hide()
        self.update()

    def set_times(
            self,
            start_sec: float,
            end_sec:   float
        ) -> None:

        start_sec = max(0.0, start_sec)
        end_sec   = min(self.duration_sec if self.duration_sec > 0 else end_sec, end_sec)

        if end_sec <= start_sec + 0.01:
            end_sec = start_sec + 0.01

            if self.duration_sec > 0 and end_sec > self.duration_sec:
                start_sec = max(0.0, self.duration_sec - 0.01)
                end_sec   = self.duration_sec

        self.start_time_sec = start_sec
        self.end_time_sec   = end_sec

        self.update()

    def set_start_time(self, start_sec: float) -> None:
        self.set_times(start_sec, self.end_time_sec)

    def set_end_time(self, end_sec: float) -> None:
        self.set_times(self.start_time_sec, end_sec)

    def set_playback_position(self, position_sec: float) -> None:
        self.playback_position = max(0.0, min(self.duration_sec, position_sec))
        self.update()

    def set_is_playing(self, is_playing: bool) -> None:
        self.is_playing = is_playing

    def generate_pixmap(self) -> None:
        width_px        = self.width()
        height_px       = self.height()
        center_y_px     = height_px * 0.5
        amplitude_array = numpy.array(self.waveform_amplitudes, dtype = numpy.float32)

        if amplitude_array.size == 0:
            return

        pixmap = QPixmap(width_px, height_px)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        top_coordinates    = center_y_px - amplitude_array * center_y_px
        bottom_coordinates = center_y_px + amplitude_array * center_y_px

        path = create_waveform_polygon_path(top_coordinates, bottom_coordinates, width_px, height_px)

        painter.setPen(self.cached_wave_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setBrush(self.cached_wave_brush)
        painter.setPen(QPen(QColor(255, 255, 255, 160), 0.7))
        painter.drawPath(path)
        painter.end()

        self.waveform_pixmap = pixmap

    def paintEvent(self, event: QPaintEvent) -> None:
        opacity = float(self.waveform_opacity_handle.value)

        if opacity <= 0.0:
            return

        super().paintEvent(event)

        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setOpacity(opacity)

        if self.waveform_pixmap:
            painter.drawPixmap(0, 0, self.waveform_pixmap)

        width_px = self.width()

        start_x_px = (self.start_time_sec / self.duration_sec) * width_px if self.duration_sec > 0 else 0.0
        end_x_px   = (self.end_time_sec   / self.duration_sec) * width_px if self.duration_sec > 0 else 0.0

        painter.setBrush(self.cached_trim_brush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(QPointF(start_x_px, 0), QPointF(end_x_px, self.height())),
            10,
            10
        )

        painter.setPen(self.cached_accent_pen)
        painter.drawLine(int(start_x_px), 10, int(start_x_px), self.height() - 10)
        painter.drawLine(int(end_x_px),   10, int(end_x_px),   self.height() - 10)

        playhead_x_px = (self.playback_position / self.duration_sec) * width_px if self.duration_sec > 0 else 0.0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.cached_accent_brush)
        painter.drawRect(QRectF(playhead_x_px - 1.0, 0, 2.0, self.height()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.is_loading or self.is_transitioning:
            return

        click_x_px = event.position().x()
        start_x_px = (self.start_time_sec / self.duration_sec) * self.width() if self.duration_sec > 0 else 0.0
        end_x_px   = (self.end_time_sec   / self.duration_sec) * self.width() if self.duration_sec > 0 else 0.0

        if abs(click_x_px - start_x_px) < 10:
            self.dragging_handle = 'start'

        elif abs(click_x_px - end_x_px) < 10:
            self.dragging_handle = 'end'

        else:
            self.dragging_handle = None

            if not self.is_playing:
                time_position_sec = (click_x_px / self.width()) * self.duration_sec

                self.set_playback_position(time_position_sec)
                logger.info(f"Placed playback on {time_position_sec}")

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.is_loading or self.is_transitioning or not self.dragging_handle:
            return

        clamped_x_px      = max(0, min(self.width(), event.position().x()))
        time_position_sec = max(0.0, min(self.duration_sec, (clamped_x_px / self.width()) * self.duration_sec if self.duration_sec > 0 else 0.0))

        if self.dragging_handle == 'start':
            self.start_time_sec = min(time_position_sec, self.end_time_sec - 0.1)

            if not self.is_playing:
                self.set_playback_position(self.start_time_sec)

        elif self.dragging_handle == 'end':
            self.end_time_sec = min(max(time_position_sec, self.start_time_sec + 0.1), self.duration_sec or time_position_sec)

            if self.playback_position > self.end_time_sec:
                self.set_playback_position(self.end_time_sec)

        self.regionChanged.emit(self.start_time_sec, self.end_time_sec)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.dragging_handle = None

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.pulse_status_widget.setGeometry(self.rect())