from __future__ import annotations

from loguru import logger

from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from PyQt6.QtGui import (
    QPen,
    QBrush,
    QColor,
    QImage,
    QPixmap,
    QPainter,
    QMouseEvent,
    QPainterPath,
    QContextMenuEvent,
    QNativeGestureEvent
)

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QLineF,
    QRectF,
    QTimer,
    QPointF,
    pyqtSignal,
    QElapsedTimer
)

from PyQt6.QtWidgets import (
    QWidget,
    QGestureEvent,
    QGraphicsView,
    QPinchGesture,
    QGraphicsScene
)

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Services import ProjectSaver

from System.Interface import (
    Timing,
    Widgets,
    Windows
)

from . import Controllers

class ScrollableContent(QGraphicsView):
    playhead_moved_ms         = pyqtSignal(float)
    playhead_moved_normalized = pyqtSignal(float)
    zoom_changed              = pyqtSignal(float)
    content_scrolled          = pyqtSignal(float)
    context_menu_opened       = pyqtSignal()
    dialog_cancelled          = pyqtSignal(str)
    speed_control_used        = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.configure_view()
        self.init_state(parent)
        self.setup_ui()
        self.init_controllers(parent)

    # Setup

    def configure_view(self) -> None:
        if Constants.current_settings["gpu"]:
            self.gl_viewport = QOpenGLWidget()
            self.gl_viewport.frameSwapped.connect(self.on_frame_swapped)

            self.fps_timer   = QElapsedTimer()
            self.frame_count = 0

            self.fps_timer.start()

            self.setViewport(self.gl_viewport)

        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontSavePainterState |
            QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
        )

        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.viewport().grabGesture(Qt.GestureType.PinchGesture)

    def init_state(self, parent: QWidget) -> None:
        self.playback_manager              = parent.playback_manager
        self.composition                   = None
        self.track_names                   = []
        self.total_content_width           = 0.0

        self.tutorial_window               = None
        self.glyph_visualizer              = None

        self.ruler_font                    = Utils.NType(10)
        self.track_label_font              = Utils.NType(12)

        self.cached_background_color       = QColor(0, 0, 0)
        self.cached_foreground_color       = QColor(31, 31, 31)
        self.cached_ruler_pen              = QPen(QColor(255, 255, 255), 0.5)
        self.cached_beat_pen               = QPen(QColor(Styles.Colors.Waveline.BeatColor), 1, Qt.PenStyle.DotLine)
        self.cached_waveform_pen           = QPen(QColor(255, 255, 255, 90), 2.5)
        self.cached_waveform_brush         = QBrush(QColor(255, 255, 255, 90))
        self.cached_waveform_pen2          = QPen(QColor(255, 255, 255, 160), 0.7)

        self.cached_track_name_color       = QColor(Styles.Colors.Waveline.TrackNameColor)
        self.cached_track_name_white_color = QColor(255, 255, 255)
        self.cached_track_name_black_color = QColor(0, 0, 0)
        self.cached_track_name_white_pen   = QPen(self.cached_track_name_white_color)
        self.cached_track_name_black_pen   = QPen(self.cached_track_name_black_color)

        self.cached_beat_lines             = []
        self.cached_track_grid_image       = None
        self.cached_foreground_mask        = None
        self.cached_foreground_size        = None

    def setup_ui(self) -> None:
        self.scroll_tick_timer = Timing.Timer(Constants.FPS_120, self.on_scroll_tick, fps_managed = True)

        self.tooltip        = Widgets.Tooltip(self)
        self.playhead       = Widgets.PlayheadItem(self)
        self.marquee_item   = Widgets.MarqueeItem(self.playback_manager)
        self.playhead_hover = Widgets.PlayheadItem(self, Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height)

        for item in (self.playhead, self.playhead_hover, self.marquee_item):
            self.scene.addItem(item)

        self.playhead_hover.hide()

        self.setStyleSheet("border: none;")

    def init_controllers(self, parent: QWidget) -> None:
        self.playback_controller     = Controllers.PlaybackController(self)
        self.scale_controller        = Controllers.ScaleController(self)
        self.waveform_controller     = Controllers.WaveformController(self)
        self.context_menu_controller = Controllers.ContextMenuController(self)

        self.playback_controller.playhead_moved_ms.connect(self.playhead_moved_ms.emit)
        self.playback_controller.playhead_moved_normalized.connect(self.playhead_moved_normalized.emit)
        self.scale_controller.zoom_changed.connect(self.zoom_changed.emit)

        self.context_menu_controller.context_menu_opened.connect(self.context_menu_opened.emit)
        self.context_menu_controller.dialog_cancelled.connect(self.dialog_cancelled.emit)

        self.wheel_controller    = None
        self.glyph_controller    = None
        self.mouse_controller    = None
        self.keyboard_controller = None

    # Properties

    @property
    def playhead_timer(self) -> object:
        return self.playback_controller.playhead_timer

    @property
    def px_per_sec(self) -> float:
        return self.scale_controller.px_per_sec

    @px_per_sec.setter
    def px_per_sec(self, value: float) -> None:
        self.scale_controller.px_per_sec = value

    @property
    def target_px_per_sec(self) -> float:
        return self.scale_controller.target_px_per_sec

    @target_px_per_sec.setter
    def target_px_per_sec(self, value: float) -> None:
        self.scale_controller.target_px_per_sec = value

    @property
    def scale_anim_active(self) -> bool:
        return self.scale_controller.scale_anim_active

    @scale_anim_active.setter
    def scale_anim_active(self, value: bool) -> None:
        self.scale_controller.scale_anim_active = value

    @property
    def waveform_tiles(self) -> dict[int, QPixmap]:
        return self.waveform_controller.waveform_tiles

    @property
    def pending_tiles(self) -> set[int]:
        return self.waveform_controller.pending_tiles

    @property
    def tile_width(self) -> int:
        return self.waveform_controller.tile_width

    # Lifecycle

    def load_composition(self, composition: ProjectSaver.Composition) -> None:
        self.waveform_controller.prepare_audio()
        self.playback_controller.attach_playback_signals()

        self.composition = composition
        self.playback_manager.speed_changed.connect(self.composition.syncer.set_speed)
        self.composition.syncer.error_occurred.connect(self.show_error_dialog)

        self.track_names = composition.track_names

        self.wheel_controller    = Controllers.WheelController(self)
        self.glyph_controller    = Controllers.GlyphController(self)
        self.mouse_controller    = Controllers.MouseController(self)
        self.keyboard_controller = Controllers.KeyboardController(self.parent(), self)

        self.horizontalScrollBar().valueChanged.connect(self.mouse_controller.force_mouse_update)

        self.glyph_visualizer = Windows.GlyphVisualizer(self, self.composition.model)

        self.glyph_controller.elements_changed.connect(self.parent().on_elements_changed)

        self.update_scene_rect()
        self.glyph_controller.create_glyph_items(self.composition.glyphs.keys(), True, False, False)

        self.update()
        QTimer.singleShot(0, self.finalize_scene_layout)

        self.glyph_visualizer.show()

        self.playhead_moved_ms.connect(self.glyph_visualizer.on_playhead_scrubbed)
        self.composition.glyphs.visualizator_changed_callback = self.glyph_visualizer.on_visualizator_data_changed

    def unload_composition(self) -> None:
        logger.warning("Unloading composition and clearing state")

        self.playback_controller.cleanup()
        self.scale_controller.cleanup()
        self.waveform_controller.clear()

        if self.glyph_controller:
            self.glyph_controller.clear_glyphs()

        syncer = self.composition.syncer if self.composition else None

        if self.composition:
            self.composition.syncer.cleanup()
            self.composition.syncer.set_speed(1.0)
            self.composition.syncer.error_occurred.disconnect(self.show_error_dialog)
            self.composition = None

        if syncer is not None:
            self.playback_manager.speed_changed.disconnect(syncer.set_speed)

        logger.warning("Syncer stopped")

        if self.glyph_visualizer:
            self.glyph_visualizer.exit()
            self.glyph_visualizer = None

        if self.glyph_controller:
            self.glyph_controller.elements_changed.disconnect()

        if self.mouse_controller:
            self.horizontalScrollBar().valueChanged.disconnect(self.mouse_controller.force_mouse_update)

        if self.keyboard_controller:
            self.keyboard_controller.cleanup_shortcuts()

        self.glyph_controller    = None
        self.wheel_controller    = None
        self.mouse_controller    = None
        self.keyboard_controller = None
        self.track_names         = []

        logger.warning("Controllers and caches cleared")

    def check_tutorial(self) -> bool:
        if not Constants.current_settings.get("tutorial_shown", Constants.current_settings.get("_tutorial_shown")):
            return False

        self.tutorial_window = Windows.Tutorial(self.composition.get_playback_audio_path(), self)

        QTimer.singleShot(0, self.tutorial_window.show)

        return True

    def show_error_dialog(
            self,
            title:   str,
            message: str
        ) -> None:
        Windows.ErrorWindow(title, message, "Oh nah").exec()

    # Geometry

    def update_scene_rect(self) -> None:
        audio_duration_sec = self.playback_manager.duration_ms / 1000.0
        viewport_width     = self.viewport().width()

        if audio_duration_sec > 0:
            min_px_per_sec = max(viewport_width / audio_duration_sec, 20.0)

            if self.px_per_sec < min_px_per_sec:
                self.px_per_sec        = min_px_per_sec
                self.target_px_per_sec = min_px_per_sec

        width      = audio_duration_sec * self.px_per_sec
        top_margin = Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height
        row_height = Styles.Metrics.Tracks.RowHeight + Styles.Metrics.Tracks.BoxSpacing

        total_height = max(
            top_margin + len(self.track_names) * row_height + 100,
            self.viewport().height()
        )

        self.setSceneRect(0, 0, width, total_height)
        self.total_content_width     = width
        self.cached_track_grid_image = None
        self.cached_foreground_mask  = None
        self.cached_foreground_size  = None

    def finalize_scene_layout(self) -> None:
        self.update_scene_rect()
        self.viewport().update()

    # Painting

    def on_frame_swapped(self) -> None:
        self.frame_count += 1
        elapsed_ms       = self.fps_timer.elapsed()

        if elapsed_ms < 1000:
            return

        real_fps = self.frame_count / (elapsed_ms / 1000.0)

        if self.window():
            self.window().setWindowTitle(f"Cassette | FPS: {real_fps:.2f}")

        self.frame_count = 0
        self.fps_timer.restart()

    def drawBackground(
            self,
            painter:   QPainter,
            rectangle: QRectF
        ) -> None:
        painter.fillRect(rectangle, self.cached_background_color)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.draw_waveform(painter, rectangle)
        self.draw_beat_lines(painter, rectangle)
        self.draw_ruler(painter, rectangle)

    def draw_waveform(
            self,
            painter:   QPainter,
            rectangle: QRectF
        ) -> None:
        if self.playback_manager.data is None or len(self.playback_manager.data) == 0:
            return

        waveform_y = Styles.Metrics.Tracks.RulerHeight
        tile_width = self.tile_width

        if self.scale_anim_active and self.scale_controller.frozen_tiles:
            scale_ratio = self.px_per_sec / self.scale_controller.frozen_px_per_sec
            self.draw_scaled_tiles(painter, self.scale_controller.frozen_tiles, scale_ratio, tile_width, waveform_y, rectangle)
            return

        start_tile = int(rectangle.left() // tile_width)
        end_tile   = int(rectangle.right() // tile_width)

        if self.scale_controller.frozen_fallback_tiles:
            fallback_ratio = self.px_per_sec / self.scale_controller.frozen_fallback_px_per_sec
            self.draw_scaled_tiles(painter, self.scale_controller.frozen_fallback_tiles, fallback_ratio, tile_width, waveform_y, rectangle)

        for index in range(start_tile, end_tile + 1):
            tile = self.waveform_tiles.get(index)

            if tile is None:
                self.waveform_controller.request_tile(index)
                continue

            draw_x = index * tile_width

            if draw_x > rectangle.right() or draw_x + tile_width < rectangle.left():
                continue

            alpha       = self.scale_controller.tile_fade_alphas.get(index, 1.0)
            tile_height = tile.height() / tile.devicePixelRatio()

            if alpha < 1.0:
                painter.setOpacity(alpha)
                painter.drawPixmap(draw_x, waveform_y, tile)
                painter.setOpacity(1.0)

            else:
                painter.fillRect(
                    QRectF(draw_x, waveform_y, tile_width, tile_height),
                    self.cached_background_color
                )

                painter.drawPixmap(draw_x, waveform_y, tile)

    def draw_scaled_tiles(
            self,
            painter:       QPainter,
            tiles:         dict[int, QPixmap],
            scale_ratio:   float,
            tile_width:    float,
            waveform_y:    float,
            visible_range: QRectF
        ) -> None:
        for tile_index, pixmap in tiles.items():
            destination_x     = tile_index * tile_width * scale_ratio
            destination_width = tile_width * scale_ratio
            tile_height       = pixmap.height() / pixmap.devicePixelRatio()
            destination_rect  = QRectF(destination_x, waveform_y, destination_width, tile_height)

            if destination_rect.right() >= visible_range.left() and destination_rect.left() <= visible_range.right():
                painter.drawPixmap(destination_rect, pixmap, QRectF(pixmap.rect()))

    def draw_ruler(
            self,
            painter:   QPainter,
            rectangle: QRectF
        ) -> None:
        painter.setFont(self.ruler_font)
        painter.setPen(self.cached_ruler_pen)

        start_second = int(rectangle.left() / self.px_per_sec)
        end_second   = int(rectangle.right() / self.px_per_sec)

        ruler_lines  = []
        ruler_height = Styles.Metrics.Tracks.RulerHeight

        for second in range(start_second, end_second + 1):
            x = second * self.px_per_sec
            ruler_lines.append(QLineF(x, 0, x, 8))
            painter.drawText(QPointF(x + 5, ruler_height - 10), str(second))

        if ruler_lines:
            painter.drawLines(ruler_lines)

    def draw_beat_lines(
            self,
            painter:   QPainter,
            rectangle: QRectF
        ) -> None:
        if not self.composition.beats:
            return

        painter.setPen(self.cached_beat_pen)

        line_height     = Styles.Metrics.Waveform.Height + Styles.Metrics.Tracks.RulerHeight
        rectangle_right = rectangle.right()
        rectangle_left  = rectangle.left()
        beat_lines      = []

        for beat in self.composition.beats:
            x = beat * self.px_per_sec

            if x > rectangle_right:
                break

            if x >= rectangle_left:
                beat_lines.append(QLineF(x, 0, x, line_height))

        if beat_lines:
            painter.drawLines(beat_lines)

    def draw_track_grid(
            self,
            painter:   QPainter,
            rectangle: QRectF = None
        ) -> None:
        if not self.track_names:
            return

        box_spacing = Styles.Metrics.Tracks.BoxSpacing
        row_height  = Styles.Metrics.Tracks.RowHeight
        box_height  = Styles.Metrics.Tracks.BoxHeight
        label_width = Styles.Metrics.Tracks.LabelWidth

        start_y    = Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height + box_spacing
        row_stride = row_height + box_spacing
        offset_y   = (row_height - box_height) / 2.0
        label_w    = label_width - 2 * box_spacing

        viewport_rect = self.viewport().rect()
        viewport_h    = viewport_rect.height()

        visible_scene_top    = self.mapToScene(0, 0).y()
        visible_scene_bottom = self.mapToScene(0, viewport_h).y()

        start_idx = max(0, int((visible_scene_top - start_y - offset_y - box_height) // row_stride))
        end_idx   = min(len(self.track_names), int((visible_scene_bottom - start_y - offset_y) // row_stride) + 2)

        if start_idx >= end_idx:
            return

        scene_x = self.mapToScene(int(box_spacing), 0).x()

        painter.save()
        painter.resetTransform()

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setFont(self.track_label_font)

        ignored_items = {
            item for item in (
                getattr(self, 'playhead', None),
                getattr(self, 'playhead_hover', None),
                getattr(self, 'marquee_item', None)
            ) if item is not None
        }

        for i in range(start_idx, end_idx):
            top_y          = start_y + i * row_stride + offset_y
            viewport_top_y = self.mapFromScene(0, int(top_y)).y()

            if viewport_top_y + box_height < 0 or viewport_top_y > viewport_h:
                continue

            label_viewport_rect = QRectF(box_spacing, float(viewport_top_y), label_w, box_height)
            label_scene_rect    = QRectF(scene_x, top_y, label_w, box_height)

            is_over_glyph = False

            for item in self.scene.items(label_scene_rect):
                if item not in ignored_items and item.isVisible() and item.opacity() > 0:
                    is_over_glyph = True
                    break

            if is_over_glyph:
                painter.setPen(self.cached_track_name_black_pen)

            else:
                painter.setPen(self.cached_track_name_white_pen)

            painter.drawText(label_viewport_rect, Qt.AlignmentFlag.AlignCenter, self.track_names[i])

        painter.restore()

    def prepare_track_grid_cache(self) -> None:
        pass

    def drawForeground(
            self,
            painter:   QPainter,
            rectangle: QRectF
        ) -> None:
        painter.resetTransform()

        self.draw_track_grid(painter, rectangle)

        self.prepare_foreground_mask()

        if not self.cached_foreground_mask:
            return

        painter.drawPixmap(0, 0, self.cached_foreground_mask)

    def prepare_foreground_mask(self) -> None:
        view_rect = self.viewport().rect()

        if view_rect.isEmpty():
            self.cached_foreground_mask = None
            self.cached_foreground_size = None
            return

        size = (view_rect.width(), view_rect.height())

        if self.cached_foreground_mask is not None and self.cached_foreground_size == size:
            return

        radius = 16
        image  = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        full = QPainterPath()
        full.addRect(QRectF(0.0, 0.0, float(size[0]), float(size[1])))

        rounded = QPainterPath()
        rounded.addRoundedRect(QRectF(0.0, 0.0, float(size[0]), float(size[1])), radius, radius)

        mask = full.subtracted(rounded)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.cached_foreground_color)
        painter.drawPath(mask)
        painter.end()

        self.cached_foreground_mask = QPixmap.fromImage(image)
        self.cached_foreground_size = size

    # Playhead Delegation

    def get_audio_delay_ms(self) -> float:
        return self.playback_controller.get_audio_delay_ms()

    def get_playhead_position_px(self) -> float:
        return self.playback_controller.get_playhead_position_px()

    def get_target_playhead_position_px(self) -> float:
        return self.playback_controller.get_target_playhead_position_px()

    def set_playhead_position_px(
            self,
            position_px: float,
            animate:     bool = False
        ) -> None:
        self.playback_controller.set_playhead_position_px(position_px, animate)

    def get_playhead_position_ms(self) -> float:
        return self.playback_controller.get_playhead_position_ms()

    def set_playhead_position_ms(
            self,
            position_ms: float,
            animate:     bool = False
        ) -> None:
        self.playback_controller.set_playhead_position_ms(position_ms, animate)

    def scroll_to_playhead(self) -> None:
        self.playback_controller.scroll_to_playhead()

    def scroll_to_normalized_position(self, normalized_position: float) -> None:
        self.playback_controller.scroll_to_normalized_position(normalized_position)

    def sync_scroll_to_playhead(self) -> None:
        self.playback_controller.sync_scroll_to_playhead()

    # Scaling Delegation

    def scale_view(
            self,
            delta:        float = 0.0,
            force_update: bool  = False
        ) -> None:
        self.scale_controller.scale_view(delta, force_update)

    # Scrolling

    def start_scroll_tick(self) -> None:
        if not self.scroll_tick_timer.isActive():
            self.scroll_tick_timer.start()

    def on_scroll_tick(self) -> None:
        if not self.wheel_controller or not self.mouse_controller:
            self.scroll_tick_timer.stop()
            return

        wheel_idle = self.wheel_controller.tick()
        drag_idle  = self.mouse_controller.auto_scroller.tick()

        if wheel_idle and drag_idle:
            self.scroll_tick_timer.stop()

    # Context Menu Delegation

    def brightness_control_popup(self) -> None:
        self.context_menu_controller.brightness_control_popup()

    def duration_control_popup(self) -> None:
        self.context_menu_controller.duration_control_popup()

    def segment_control_popup(self) -> None:
        self.context_menu_controller.segment_control_popup()

    # Event Handlers

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.context_menu_controller.handle_context_menu(event)

    def wheelEvent(self, event: QEvent) -> None:
        self.wheel_controller.process_wheel_event(event)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.NativeGesture:
            gesture_event: QNativeGestureEvent = event

            if gesture_event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self.wheel_controller.process_pinch_event(gesture_event.value())
                return True

        return super().event(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Gesture:
            gesture_event: QGestureEvent = event
            pinch_gesture: QPinchGesture = gesture_event.gesture(Qt.GestureType.PinchGesture)

            if pinch_gesture and pinch_gesture.changeFlags() & QPinchGesture.ChangeFlag.ScaleFactorChanged:
                self.wheel_controller.process_pinch_event(pinch_gesture.scaleFactor() - 1.0)

            return True

        return super().viewportEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.mouse_controller.process_mouse_press_event(event)
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.mouse_controller.process_mouse_move_event(event)
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.mouse_controller.process_mouse_release_event(event)
        return super().mouseReleaseEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.mouse_controller.process_mouse_leave_event(event)
        return super().leaveEvent(event)

    def showEvent(self, event: QEvent) -> None:
        super().showEvent(event)
        self.update_scene_rect()
        self.viewport().update()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self.update_scene_rect()
        self.viewport().update()