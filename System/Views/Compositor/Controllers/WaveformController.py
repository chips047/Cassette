from __future__ import annotations

import numpy

from PyQt6.QtGui import (
    QPen,
    QBrush,
    QColor,
    QImage,
    QPixmap,
    QPainter,
    QPolygonF,
    QPainterPath,
    QGuiApplication
)

from PyQt6.QtCore import (
    Qt,
    QThread,
    QObject,
    QPointF,
    pyqtSignal,
    QThreadPool
)

from loguru import logger

from System.Accelerated import VisualFunctions

from System.Common import (
    Styles,
    Constants
)

from System.Services import Workers

from .. import Timeline

class WaveformController(QObject):
    tile_ready = pyqtSignal(int, QPixmap)

    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor           = conductor

        self.tile_width          = Constants.current_settings["tile_width"]
        self.waveform_tiles      = {}
        self.pending_tiles       = set()
        self.tile_generation_id  = 0
        self.global_waveform_max = 0.000001

        self.visible_start_tile  = 0
        self.visible_end_tile    = 0

        self.thread_pool         = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(max(1, min(4, QThread.idealThreadCount() // 2)))

    # Audio

    def prepare_audio(self) -> None:
        self.advance_generation_and_clear()
        self.thread_pool.waitForDone(150)

        audio_data = self.conductor.playback_manager.data

        if audio_data is None or len(audio_data) == 0:
            self.global_waveform_max = 0.000001
            return

        maximum_sample           = float(numpy.max(numpy.abs(audio_data.astype(numpy.float32))))
        self.global_waveform_max = max(maximum_sample, 0.000001)

    # Visibility and Culling

    def set_visible_range(
            self,
            start_tile_index: int,
            end_tile_index:   int
        ) -> None:

        self.visible_start_tile = start_tile_index
        self.visible_end_tile   = end_tile_index

    def is_tile_needed(
            self,
            tile_index: int,
            generation: int
        ) -> bool:

        if generation != self.tile_generation_id:
            return False

        if self.visible_end_tile <= 0:
            return True

        margin_tiles = 4

        return (self.visible_start_tile - margin_tiles) <= tile_index <= (self.visible_end_tile + margin_tiles)

    def discard_pending_tile(self, tile_index: int) -> None:
        self.pending_tiles.discard(tile_index)

    # Tile Management

    def request_tile(self, tile_index: int) -> None:
        if tile_index in self.pending_tiles or tile_index in self.waveform_tiles:
            return

        self.pending_tiles.add(tile_index)

        screen             = QGuiApplication.primaryScreen()
        device_pixel_ratio = screen.devicePixelRatio() if screen else 1.0
        generation         = self.tile_generation_id
        worker             = Workers.TileWorker(self, tile_index, generation, device_pixel_ratio)

        worker.signals.tile_ready.connect(
            lambda index, image, gen = generation:
            self.on_tile_ready(index, image, gen)
        )

        self.thread_pool.start(worker)

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

        is_currently_visible = (
            self.visible_end_tile <= 0 or
            self.visible_start_tile <= tile_index <= self.visible_end_tile
        )

        if is_currently_visible:
            self.conductor.viewport().update()

    def advance_generation_and_clear(self) -> None:
        self.tile_generation_id += 1
        self.clear()

    def get_tiles_snapshot(self) -> dict[int, QPixmap]:
        return dict(self.waveform_tiles)

    def compute_tile_image(
            self,
            tile_index:         int,
            generation:         int,
            device_pixel_ratio: float
        ) -> QImage | None:

        if generation != self.tile_generation_id:
            return None

        if self.conductor is None or self.conductor.playback_manager is None:
            return None

        audio_data = self.conductor.playback_manager.data

        if audio_data is None or len(audio_data) == 0:
            return None

        total_content_width = float(self.conductor.total_content_width)

        if total_content_width <= 0.0:
            return None

        total_samples  = len(audio_data)
        samples_per_px = total_samples / total_content_width

        if samples_per_px <= 0.0:
            return None

        start_px     = tile_index * self.tile_width
        start_sample = int(start_px * samples_per_px)

        if start_sample < 0 or start_sample >= total_samples:
            return None

        end_px       = start_px + self.tile_width
        end_sample   = min(total_samples, int(end_px * samples_per_px))

        if end_sample <= start_sample:
            return None

        audio_chunk = audio_data[start_sample:end_sample]

        if audio_chunk.shape[0] == 0:
            return None

        height       = float(Styles.Metrics.Waveform.Height)
        sigma        = 1.7 * (Constants.current_settings["waveform_smoothing_percent"] / 100.0)
        waveform_max = max(float(self.global_waveform_max), 0.000001)

        try:
            chunk_contiguous = numpy.ascontiguousarray(audio_chunk, dtype = numpy.float32)

            calculated_data = VisualFunctions.process_waveform_tile(
                chunk_contiguous,
                self.tile_width,
                samples_per_px,
                height,
                waveform_max,
                sigma
            )

        except Exception as error:
            logger.error(f"Waveform processing error: {error}")
            return None

        if calculated_data is None or len(calculated_data) == 0:
            return None

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

        waveform_pen   = QPen(QColor(255, 255, 255, 90), 2.5)
        waveform_brush = QBrush(QColor(255, 255, 255, 90))
        waveform_pen2  = QPen(QColor(255, 255, 255, 160), 0.7)

        painter.setPen(waveform_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setBrush(waveform_brush)
        painter.setPen(waveform_pen2)
        painter.drawPath(path)

        painter.end()

        return image

    def clear(self) -> None:
        self.waveform_tiles.clear()
        self.pending_tiles.clear()