from __future__ import annotations

from PyQt6.QtGui  import QImage
from PyQt6.QtCore import QRunnable

from .TileWorkerSignals import TileWorkerSignals

class TileWorker(QRunnable):
    def __init__(
            self,
            controller,
            tile_index:         int,
            generation:         int,
            device_pixel_ratio: float
        ) -> None:

        super().__init__()

        self.controller         = controller
        self.tile_index         = tile_index
        self.generation         = generation
        self.device_pixel_ratio = device_pixel_ratio
        self.signals            = TileWorkerSignals()

        self.setAutoDelete(True)

    def run(self) -> None:
        image = self.controller.compute_tile_image(self.tile_index, self.device_pixel_ratio)

        self.signals.tile_ready.emit(
            self.tile_index,
            image if image else QImage()
        )