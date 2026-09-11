from __future__ import annotations

from PyQt6.QtCore import (
    Qt,
    QRect
)

from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPaintEvent
)

from PyQt6.QtWidgets import (
    QWidget,
    QSizePolicy
)

from System.Common import (
    Styles,
    Constants
)

from System.Interface import Timing

class TutorialProgressBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.total           = 1.0
        self.completed       = 0.0
        self.displayed_ratio = 0.0

        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.ease_timer = Timing.Timer(
            Constants.FPS_60,
            self.ease_towards_target,
            parent = self
        )

    # Api

    def set_total(self, total: float) -> None:
        self.total           = max(1.0, total)
        self.completed       = 0.0
        self.displayed_ratio = 0.0

        self.ease_timer.stop()
        self.update()

    def set_completed(self, completed: float) -> None:
        self.completed = max(0.0, min(self.total, completed))

        if not self.ease_timer.isActive():
            self.ease_timer.start()

    # Animation

    def ease_towards_target(self) -> None:
        target_ratio = self.completed / self.total
        delta_ratio  = target_ratio - self.displayed_ratio

        if abs(delta_ratio) < Constants.SNAP_THRESHOLD:
            self.displayed_ratio = target_ratio
            self.ease_timer.stop()

        else:
            self.displayed_ratio += delta_ratio * Constants.EASE_PER_TICK

        self.update()

    # Events

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_rectangle = self.rect()
        radius_px       = track_rectangle.height() / 2.0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(Styles.Colors.GlassBorder))
        painter.drawRoundedRect(track_rectangle, radius_px, radius_px)

        fill_width_px = track_rectangle.width() * self.displayed_ratio

        if fill_width_px > 0.0:
            fill_rectangle = QRect(track_rectangle.x(), track_rectangle.y(), int(round(fill_width_px)), track_rectangle.height())

            painter.setBrush(QColor(Styles.Colors.NothingAccent))
            painter.drawRoundedRect(fill_rectangle, radius_px, radius_px)

        painter.end()