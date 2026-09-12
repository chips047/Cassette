from __future__ import annotations

import numpy

from PyQt6.QtGui import (
    QImage,
    QPixmap,
    QPainter,
    QPolygonF,
    QPainterPath,
    QGuiApplication
)

from PyQt6.QtCore import (
    Qt,
    QPointF,
    QObject,
    pyqtSignal,
    QThreadPool
)

from System.Accelerated import VisualFunctions

from System.Common import (
    Styles,
    Constants
)

from .TileWorker import TileWorker

from .. import Timeline

class WaveformController(QObject):
    tile_ready = pyqtSignal(int, QPixmap)

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor = conductor

        self.tile_width          = Constants.current_settings["tile_width"]
        self.waveform_tiles      = {}
        self.pending_tiles       = set()
        self.tile_generation_id  = 0
        self.global_waveform_max = 0.000001

    # Audio

    def prepare_audio(self) -> None:
        audio_data = self.conductor.playback_manager.data

        if audio_data is None or len(audio_data) == 0:
            self.global_waveform_max = 0.000001
            return

        maximum_sample           = float(numpy.max(numpy.abs(audio_data.astype(numpy.float32))))
        self.global_waveform_max = max(maximum_sample, 0.000001)

    # Tile Management

    def request_tile(self, tile_index: int) -> None:
        if tile_index in self.pending_tiles or tile_index in self.waveform_tiles:
            return

        self.pending_tiles.add(tile_index)

        device_pixel_ratio = QGuiApplication.primaryScreen().devicePixelRatio()
        generation         = self.tile_generation_id
        worker             = TileWorker(self, tile_index, generation, device_pixel_ratio)

        worker.signals.tile_ready.connect(
            lambda index, image, gen = generation:
            self.on_tile_ready(index, image, gen)
        )

        QThreadPool.globalInstance().start(worker)

    def on_tile_ready(
            self,
            tile_index: int,
            image:      QImage,
            generation: int
        ) -> None:

        self.pending_tiles.discard(tile_index)

        if generation != self.tile_generation_id:
            return

        if not image or image.isNull():
            return

        pixmap                          = QPixmap.fromImage(image)
        self.waveform_tiles[tile_index] = pixmap

        self.tile_ready.emit(tile_index, pixmap)
        self.conductor.viewport().update()

    def advance_generation_and_clear(self) -> None:
        self.tile_generation_id += 1
        self.clear()

    def get_tiles_snapshot(self) -> dict[int, QPixmap]:
        return dict(self.waveform_tiles)

    def compute_tile_image(
            self,
            tile_index:         int,
            device_pixel_ratio: float
        ) -> QImage | None:

        audio_data     = self.conductor.playback_manager.data
        total_px       = self.conductor.total_content_width
        samples_per_px = len(audio_data) / float(total_px)

        start_px     = tile_index * self.tile_width
        start_sample = int(start_px * samples_per_px)
        end_sample   = min(len(audio_data), int((start_px + self.tile_width) * samples_per_px))

        audio_chunk = audio_data[start_sample:end_sample]

        if audio_chunk.shape[0] == 0:
            return None

        height = float(Styles.Metrics.Waveform.Height)
        sigma  = float(Constants.current_settings["waveform_smoothing"])

        calculated_data = VisualFunctions.process_waveform_tile(
            audio_chunk.astype(numpy.float32),
            self.tile_width,
            samples_per_px,
            height,
            self.global_waveform_max,
            sigma
        )

        top_points    = calculated_data[:, 0]
        bottom_points = calculated_data[:, 1]
        points_count  = len(top_points)

        if points_count == 0:
            return None

        image = QImage(
            int(self.tile_width * device_pixel_ratio),
            int(height * device_pixel_ratio),
            QImage.Format.Format_ARGB32_Premultiplied
        )

        image.setDevicePixelRatio(device_pixel_ratio)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_width          = float(self.tile_width) / points_count
        x_positions        = (numpy.arange(points_count) * bar_width).astype(numpy.float32)
        y_top_positions    = numpy.clip(top_points.astype(numpy.float32),    0.0, float(height))
        y_bottom_positions = numpy.clip(bottom_points.astype(numpy.float32), 0.0, float(height))

        all_positions_x = numpy.concatenate([x_positions, x_positions[::-1]])
        all_positions_y = numpy.concatenate([y_top_positions, y_bottom_positions[::-1]])

        polygon_points = [
            QPointF(x, y)
            for x, y in zip(all_positions_x, all_positions_y)
        ]

        path = QPainterPath()
        path.addPolygon(QPolygonF(polygon_points))
        path.closeSubpath()

        painter.setPen(self.conductor.cached_waveform_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setBrush(self.conductor.cached_waveform_brush)
        painter.setPen(self.conductor.cached_waveform_pen2)
        painter.drawPath(path)

        painter.end()

        return image

    def clear(self) -> None:
        self.waveform_tiles.clear()
        self.pending_tiles.clear()