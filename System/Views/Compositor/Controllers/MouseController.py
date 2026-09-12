from __future__ import annotations

from PyQt6.QtGui import (
    QCursor,
    QMouseEvent
)

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QRectF,
    QPointF
)

from PyQt6.QtWidgets import QApplication

from System.Common   import Styles
from System.Services import Player

from .AutoScroller import AutoScroller

from .. import Timeline

class MouseController:
    def __init__(self, conductor: Timeline.ScrollableContent) -> None:
        self.conductor            = conductor
        self.is_marquee_selecting = False
        self.auto_scroller        = AutoScroller(conductor)
        self.playback_manager     = conductor.playback_manager

    # MarqueeSelection

    def start_marquee(self, event: QMouseEvent) -> None:
        self.conductor.marquee_item.start_marquee(self.conductor.mapToScene(event.pos()))
        self.is_marquee_selecting = True

    def end_marquee(self, event: QMouseEvent) -> None:
        if not self.is_marquee_selecting:
            return

        self.conductor.marquee_item.end_marquee()
        self.is_marquee_selecting = False
        self.stop_auto_scroll_drag()

    def marquee_tick(self, event: QMouseEvent) -> None:
        if not self.is_marquee_selecting:
            return

        self.conductor.marquee_item.update_end_point(
            self.conductor.mapToScene(event.pos()),
            animate = False
        )

        self.auto_scroller.process_position(self.conductor.viewport().mapToGlobal(event.pos()))

    def stop_auto_scroll_drag(self) -> None:
        self.auto_scroller.stop_drag()

    # RulerInteractions

    def handle_ruler_press(self, event: QMouseEvent) -> None:
        if self.playback_manager.is_playing:
            return

        new_position_x = self.conductor.mapToScene(event.pos()).x()

        if self.conductor.get_playhead_position_px() != new_position_x:
            self.conductor.set_playhead_position_px(new_position_x, True)

    def handle_ruler_hover(self, event: QMouseEvent) -> None:
        position_y     = event.position().y()
        playhead_hover = self.conductor.playhead_hover
        waveform_end   = Styles.Metrics.Waveform.Height + Styles.Metrics.Tracks.RulerHeight

        if waveform_end > position_y > 0:
            if not playhead_hover.isVisible():
                playhead_hover.show()

            playhead_hover.setPos(self.conductor.mapToScene(event.pos()).x(), 0)

        elif playhead_hover.isVisible():
            playhead_hover.hide()

    # SyntheticEvents

    def force_mouse_update(self) -> None:
        glyph_controller   = self.conductor.glyph_controller
        is_dragging_glyphs = bool(glyph_controller and glyph_controller.drag_session)

        if (
            not self.is_marquee_selecting and
            not is_dragging_glyphs and
            not self.conductor.playhead_hover.isVisible()
        ):
            return

        global_position = QCursor.pos()
        local_position  = self.conductor.viewport().mapFromGlobal(global_position)

        synthetic_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(local_position),
            QPointF(global_position),
            Qt.MouseButton.NoButton,
            QApplication.mouseButtons(),
            QApplication.keyboardModifiers()
        )

        self.process_mouse_move_event(synthetic_event)

    # EventDispatching

    def process_mouse_press_event(self, event: QMouseEvent) -> None:
        ruler_area = QRectF(
            0,
            0,
            self.conductor.width(),
            Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height,
        )

        if ruler_area.contains(event.position()):
            self.handle_ruler_press(event)
            event.accept()

            return

        if self.conductor.itemAt(event.pos()):
            event.ignore()

            return

        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.conductor.scene.clearSelection()

        self.start_marquee(event)
        event.accept()

    def process_mouse_move_event(self, event: QMouseEvent) -> None:
        self.marquee_tick(event)
        self.handle_ruler_hover(event)

    def process_mouse_release_event(self, event: QMouseEvent) -> None:
        self.end_marquee(event)

    def process_mouse_leave_event(self, event: QMouseEvent) -> None:
        self.conductor.playhead_hover.hide()