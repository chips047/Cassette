from PyQt6.QtCore import (
    Qt,
    QTimer
)

from System.Common import Dev

# Timer

@Dev.track_ram
class Timer(QTimer):
    def __init__(
            self,
            interval:    int    = 1000,
            callback:    object = None,
            auto_start:  bool   = False,
            single_shot: bool   = False,
            parent:      QTimer = None
        ) -> None:

        super().__init__(parent)

        self.setInterval(interval)
        self.setSingleShot(single_shot)

        if interval < 15:
            self.setTimerType(Qt.TimerType.PreciseTimer)

        if callback:
            self.timeout.connect(callback)

        if auto_start:
            self.start()