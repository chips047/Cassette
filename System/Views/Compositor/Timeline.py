from __future__ import annotations

import copy
import numpy
import traceback

from loguru import logger

from PyQt6.QtGui import (
    QPen,
    QColor,
    QBrush,
    QImage,
    QPixmap,
    QPainter,
    QPolygonF,
    QMouseEvent,
    QPainterPath,
    QGuiApplication,
    QContextMenuEvent
)

from PyQt6.QtCore import (
    Qt,
    QObject,
    QTimer,
    QEvent,
    QPoint,
    QLineF,
    QRectF,
    QPointF,
    QRunnable,
    pyqtSignal,
    QThreadPool,
    QElapsedTimer
)

from PyQt6.QtWidgets import (
    QWidget,
    QGraphicsView,
    QGraphicsScene
)

from System.Accelerated import VisualFunctions

from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from . import (
    Actions,
    Controllers
)

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Services import (
    Player,
    GlyphEffects,
    ProjectSaver
)

from System.Interface import (
    Menu,
    Timing,
    Widgets,
    Windows
)

Utils.check_dynamic_library(VisualFunctions)

class Tooltip(Widgets.ValuePopup):
    def __init__(self, conductor: ScrollableContent) -> None:
        super().__init__(conductor)

        self.conductor       = conductor
        self.is_hide_planned = False

    def show_tooltip_at(
        self,
        text:        str,
        target_item: Widgets.GlyphItem | None = None,
        plan_hide:   bool                     = False
    ) -> None:
        
        self.is_hide_planned = plan_hide
        self.show_text(text, self.calculate_position(target_item), plan_hide)

    def calculate_position(
            self,
            target_item: Widgets.GlyphItem | None = None
        ) -> QPoint:
        
        viewport = self.conductor.viewport()

        if not target_item:
            selected    = self.conductor.scene.selectedItems()
            target_item = selected[0] if selected else None

        if not target_item:
            return self.conductor.mapToGlobal(viewport.rect().center())

        rect          = target_item.boundingRect()
        bottom_center = QPointF(rect.center().x(), rect.bottom())
        scene_pos     = target_item.mapToScene(bottom_center)
        view_pos      = self.conductor.mapFromScene(scene_pos)

        view_x = max(10, min(view_pos.x(), viewport.width() - 10))
        view_y = view_pos.y() + 10

        return viewport.mapToGlobal(QPoint(int(view_x), int(view_y)))

    def hide_tooltip(self) -> None:
        if not self.is_hide_planned:
            self.hide()

    def show_hover_tooltip(self, item: Widgets.GlyphItem) -> None:
        if (glyph := self.conductor.composition.get_glyph(item.glyph_id)) is None:
            return

        effect = glyph.get("effect")
        effect_name = f"Effect: {effect['name']}" if effect else "No effect"

        info = [
            f"Start: {glyph['start']} ms",
            f"Duration: {glyph['duration']} ms",
            f"Brightness: {glyph['brightness']}%",
            effect_name
        ]

        self.show_tooltip_at("\n".join(info), item)

class TileWorkerSignals(QObject):
    tile_ready = pyqtSignal(int, QImage)

class TileWorker(QRunnable):
    def __init__(
        self,
        view:       ScrollableContent,
        tile_index: int,
        generation: int,
        dpr:        float
    ) -> None:
        super().__init__()

        self.view       = view
        self.tile_index = tile_index
        self.generation = generation
        self.dpr        = dpr
        self.signals    = TileWorkerSignals()

        self.setAutoDelete(True)

    def run(self) -> None:
        image = self.view.compute_tile_image(self.tile_index, self.dpr)
        
        self.signals.tile_ready.emit(
            self.tile_index,
            image if image else QImage()
        )

class ScrollableContent(QGraphicsView):
    playhead_moved = pyqtSignal(float)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.configure_view()
        self.init_state(parent)
        self.setup_ui()

    def configure_view(self) -> None:
        if Constants.current_settings["gpu"]:
            self.gl_viewport = QOpenGLWidget()
            self.gl_viewport.frameSwapped.connect(self.on_frame_swapped)

            self.fps_timer   = QElapsedTimer()
            self.frame_count = 0
            
            self.fps_timer.start()

            self.setViewport(self.gl_viewport)
        
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontSavePainterState |
            QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
        )

        self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def init_state(self, parent: QWidget) -> None:
        self.playback_manager           = parent.playback_manager
        self.composition                = None

        self.px_per_sec                 = Constants.current_settings["default_scaling"]
        self.tile_width                 = Constants.current_settings["tile_width"]

        self.track_names                = []
        self.total_content_width        = 0
        self.waveform_tiles             = {}
        self.global_waveform_max        = 1e-6
        self.is_auto_scroll_active      = False

        self.pending_tiles              = set()
        self.tile_generation_id         = 0
        self.target_px_per_sec          = self.px_per_sec
        self.scale_anim_center_ms       = 0.0
        self.frozen_tiles               = {}
        self.frozen_px_per_sec          = self.px_per_sec
        self.frozen_fallback_tiles      = {}
        self.frozen_fallback_px_per_sec = self.px_per_sec
        self.tile_fade_alphas           = {}

        self.ruler_font                 = Utils.NType(10)
        self.track_label_font           = Utils.NType(12)
        
        self.cached_background_color    = QColor(0, 0, 0)
        self.cached_foreground_color    = QColor(31, 31, 31)
        self.cached_ruler_pen           = QPen(QColor(255, 255, 255), 0.5)
        self.cached_beat_pen            = QPen(QColor(Styles.Colors.Waveline.BeatColor), 1, Qt.PenStyle.DotLine)
        self.cached_track_name_color    = QColor(Styles.Colors.Waveline.TrackNameColor)
        self.cached_waveform_pen        = QPen(QColor(255, 255, 255, 90), 2.5)
        self.cached_waveform_brush      = QBrush(QColor(255, 255, 255, 90))
        self.cached_waveform_pen2       = QPen(QColor(255, 255, 255, 160), 0.7)
        
        self.cached_ruler_coordinates   = {}
        self.cached_track_grid_coords   = {}
        self.cached_beat_lines          = []

    def setup_ui(self) -> None:
        self.playhead_timer      = Timing.Timer(Constants.FPS_120, self.on_playback_position_updated)
        self.waveform_anim_timer = Timing.Timer(Constants.FPS_120, self.on_waveform_anim_tick)
        self.scroll_tick_timer   = Timing.Timer(Constants.FPS_120, self.on_scroll_tick)

        self.scale_anim_active   = False
        self.tile_fade_subframe  = 0

        self.tooltip        = Tooltip(self)
        self.playhead       = Widgets.PlayheadItem(self)
        self.marquee_item   = Widgets.MarqueeItem(self.playback_manager)
        self.playhead_hover = Widgets.PlayheadItem(self, Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height)

        for item in (self.playhead, self.playhead_hover, self.marquee_item):
            self.scene.addItem(item)

        self.playhead_hover.hide()

        self.setStyleSheet("border: none;")

    def on_frame_swapped(self) -> None:
        self.frame_count += 1
        elapsed = self.fps_timer.elapsed()

        if elapsed < 1000:
            return

        real_fps = self.frame_count / (elapsed / 1000.0)

        if self.window():
            self.window().setWindowTitle(f"Cassette | FPS: {real_fps:.2f}")

        self.frame_count = 0
        self.fps_timer.restart()

    # Playhead

    def get_playhead_position_px(self) -> float:
        return self.playhead.pos().x()
    
    def get_target_playhead_position_px(self) -> float:
        return self.playhead.target_x

    def set_playhead_position_px(
            self,
            x:       float,
            animate: bool = False
        ) -> None:

        target_x = max(0.0, min(x, self.total_content_width))
        self.playhead.set_target_x(target_x, animate)

    def get_playhead_position_ms(self) -> float:
        return (self.playhead.pos().x() / self.px_per_sec) * 1000.0

    def set_playhead_position_ms(
            self,
            ms:      float,
            animate: bool = False
        ) -> None:

        self.set_playhead_position_px((ms / 1000.0) * self.px_per_sec, animate)

    def scroll_to_playhead(self) -> None:
        if self.playback_manager.is_playing:
            return

        horizontal_bar = self.horizontalScrollBar()
        playhead_x     = self.get_target_playhead_position_px()
        viewport_width = self.viewport().width()

        target_scroll = int(playhead_x - viewport_width / 2)
        horizontal_bar.setValue(target_scroll)

    # Playback

    def on_playback_state_changed(self, is_playing: bool) -> None:
        if is_playing:
            self.start_playback()

            horizontal_bar = self.horizontalScrollBar()
            playhead_x     = self.get_playhead_position_px()
            viewport_width = self.viewport().width()

            if playhead_x < horizontal_bar.value() or playhead_x > (horizontal_bar.value() + viewport_width):
                self.is_auto_scroll_active = True
                self.sync_scroll_to_playhead()
            
            else:
                self.is_auto_scroll_active = False
        
        else:
            self.stop_playback()
            self.on_playback_position_updated()

    def on_playback_position_updated(self) -> None:
        pos_ms     = self.playback_manager.get_position()
        true_x_pos = (pos_ms / 1000.0) * self.px_per_sec
        
        self.set_playhead_position_px(true_x_pos)

        horizontal_bar = self.horizontalScrollBar()
        viewport_width = self.viewport().width()
        offset_ratio   = Constants.current_settings["playhead_position"]
        target_scroll  = round(true_x_pos - viewport_width * offset_ratio)

        if not self.is_auto_scroll_active:
            if true_x_pos < (horizontal_bar.value() + int(viewport_width * offset_ratio)):
                return
            
            self.is_auto_scroll_active = True

        horizontal_bar.setValue(target_scroll)

    def start_playback(self) -> None:
        self.playhead_timer.start()

        position = self.get_playhead_position_ms()
        self.glyph_visualizer.set_schedule(self.composition.glyphs.visualizator_data)
        self.glyph_visualizer.play_all(position)
        self.composition.syncer.play(position)

    def stop_playback(self) -> None:
        self.playhead_timer.stop()
        self.glyph_visualizer.stop_all()

        if self.composition:
            self.composition.syncer.stop()

    def sync_scroll_to_playhead(self) -> None:
        viewport_width = self.viewport().width()
        offset_ratio   = Constants.current_settings["playhead_position"]
        
        target_visual_offset = int(viewport_width * offset_ratio)
        target_scroll        = int(self.get_playhead_position_px()) - target_visual_offset

        self.horizontalScrollBar().setValue(target_scroll)

    # Lifecycle

    def load_composition(self, composition: ProjectSaver.Composition) -> None:
        self.prepare_audio()
        self.playback_manager.playback_state_changed.connect(self.on_playback_state_changed)

        self.composition = composition
        self.playback_manager.speed_changed.connect(self.composition.syncer.set_speed)
        self.composition.syncer.error_occurred.connect(self.show_error_dialog)

        self.track_names = [f"{i + 1}" for i in range(composition.track_number)]

        self.wheel_controller    = Controllers.WheelController(self)
        self.glyph_controller    = Controllers.GlyphController(self)
        self.mouse_controller    = Controllers.MouseController(self)
        self.keyboard_controller = Controllers.KeyboardController(self.parent(), self)

        self.horizontalScrollBar().valueChanged.connect(self.mouse_controller.force_mouse_update)

        self.glyph_visualizer = Windows.GlyphVisualizer(self, self.composition.model)

        self.glyph_controller.elements_changed.connect(self.parent().on_elements_changed)
        self.glyph_controller.create_glyph_items(self.composition.glyphs.keys(), True, False, False)

        self.marquee_item.set_bpm(self.composition.bpm)

        self.update_scene_rect()
        self.update()

        self.glyph_visualizer.show()

    def unload_composition(self) -> None:
        logger.warning("Unloading composition and clearing state")

        self.glyph_controller.clear_glyphs()

        if self.composition:
            self.composition.syncer.cleanup()
            self.composition.syncer.set_speed(1.0)
            self.composition.syncer.error_occurred.disconnect(self.show_error_dialog)
            self.composition = None

        self.playback_manager.playback_state_changed.disconnect()
        self.playback_manager.speed_changed.disconnect()

        logger.warning("Syncer stopped")

        self.scroll_tick_timer.stop()

        self.set_playhead_position_px(0)
        self.horizontalScrollBar().setValue(0)

        self.glyph_visualizer.exit()

        self.glyph_controller.elements_changed.disconnect()
        self.horizontalScrollBar().valueChanged.disconnect(self.mouse_controller.force_mouse_update)

        self.keyboard_controller.cleanup_shortcuts()

        self.glyph_controller      = None
        self.wheel_controller      = None
        self.mouse_controller      = None
        self.keyboard_controller   = None
        self.waveform_tiles        = {}
        self.pending_tiles         = set()
        self.frozen_tiles          = {}
        self.frozen_fallback_tiles = {}
        self.tile_fade_alphas      = {}

        logger.warning("Controllers and caches cleared")

    def init_composition(self, composition: ProjectSaver.Composition) -> None:
        self.composition = composition

    # Scroll & Scale

    def scroll_to_normalized_position(self, normalized_pos: float) -> None:
        if self.playback_manager.is_playing:
            self.playback_manager.toggle_playback()

        horizontal_bar = self.horizontalScrollBar()
        horizontal_bar.setValue(int(normalized_pos * self.total_content_width - self.width() / 2))

        self.set_playhead_position_px(normalized_pos * self.total_content_width)

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

    def scale_view(
            self,
            delta:        float = 0,
            force_update: bool  = False
        ) -> None:

        if not self.total_content_width:
            return

        viewport_width = self.viewport().width()
        current_scroll = self.horizontalScrollBar().value()

        duration_sec   = max(self.playback_manager.duration_ms / 1000.0, 0.001)
        fit_px_per_sec = viewport_width / duration_sec
        min_px_per_sec = max(fit_px_per_sec, 20.0)
        new_target     = max(min_px_per_sec, self.target_px_per_sec + delta)

        if self.target_px_per_sec == new_target and not force_update:
            return

        self.target_px_per_sec = new_target

        if not self.scale_anim_active:
            center_px = current_scroll + viewport_width / 2.0

            self.scale_anim_center_ms = (center_px / self.px_per_sec) * 1000.0
            self.frozen_tiles         = dict(self.waveform_tiles)
            self.frozen_px_per_sec    = self.px_per_sec

            self.tile_fade_subframe = 0
            self.tile_fade_alphas.clear()
            self.frozen_fallback_tiles.clear()

        self.scale_anim_active = True

        if not self.waveform_anim_timer.isActive():
            self.waveform_anim_timer.start()

    def on_waveform_anim_tick(self) -> None:
        if self.scale_anim_active:
            self.step_scale_animation()
            return

        self.tile_fade_subframe += 1

        if self.tile_fade_subframe < 2:
            return

        self.tile_fade_subframe = 0

        if self.step_tile_fade():
            self.waveform_anim_timer.stop()
            self.cached_beat_lines.clear()
            self.cached_ruler_coordinates.clear()
            self.cached_track_grid_coords.clear()

    def step_scale_animation(self) -> None:
        diff                = self.target_px_per_sec - self.px_per_sec
        current_playhead_ms = self.get_playhead_position_ms()

        if abs(diff) < 0.3:
            self.px_per_sec         = self.target_px_per_sec
            self.scale_anim_active  = False
            self.cached_beat_lines.clear()
            self.cached_ruler_coordinates.clear()
            self.cached_track_grid_coords.clear()
            self.finish_scale_change(current_playhead_ms)

            return

        self.px_per_sec += diff * 0.18
        self.cached_beat_lines.clear()
        self.cached_ruler_coordinates.clear()
        self.apply_intermediate_scale(current_playhead_ms)

    def apply_intermediate_scale(self, current_playhead_ms: float) -> None:
        self.update_scene_rect()
        self.update_scroll_to_center()
        self.set_playhead_position_ms(current_playhead_ms)

        if self.playback_manager.is_playing and self.is_auto_scroll_active:
            self.on_playback_position_updated()

        else:
            self.update_scroll_to_center()

            if not self.playback_manager.is_playing:
                self.set_playhead_position_ms(current_playhead_ms)

        if self.composition:
            self.glyph_controller.update_glyphs()

        self.viewport().update()

    def finish_scale_change(self, current_playhead_ms: float) -> None:
        self.tile_generation_id += 1

        self.tile_fade_subframe         = 0
        self.tile_fade_alphas.clear()
        self.frozen_fallback_tiles      = dict(self.frozen_tiles)
        self.frozen_fallback_px_per_sec = self.frozen_px_per_sec
        self.frozen_tiles.clear()

        self.waveform_tiles.clear()
        self.pending_tiles.clear()
        self.cached_beat_lines.clear()
        self.cached_ruler_coordinates.clear()
        self.cached_track_grid_coords.clear()

        self.update_scene_rect()
        self.update_scroll_to_center()
        self.set_playhead_position_ms(current_playhead_ms)

        if self.playback_manager.is_playing and self.is_auto_scroll_active:
            self.on_playback_position_updated()

        else:
            self.update_scroll_to_center()

            if not self.playback_manager.is_playing:
                self.set_playhead_position_ms(current_playhead_ms)

        if self.composition:
            self.glyph_controller.update_glyphs()

        self.viewport().update()

    def step_tile_fade(self) -> bool:
        if not self.tile_fade_alphas:
            self.frozen_fallback_tiles.clear()
            return True

        completed = [idx for idx, alpha in self.tile_fade_alphas.items() if alpha >= 1.0]

        for idx in completed:
            del self.tile_fade_alphas[idx]

        for idx in self.tile_fade_alphas:
            self.tile_fade_alphas[idx] = min(1.0, self.tile_fade_alphas[idx] + 0.09)

        self.viewport().update()
        return not self.tile_fade_alphas

    def update_scroll_to_center(self) -> None:
        viewport_width   = self.viewport().width()
        new_center_px    = (self.scale_anim_center_ms / 1000.0) * self.px_per_sec
        new_scroll_value = round(new_center_px - viewport_width / 2.0)

        self.horizontalScrollBar().setValue(new_scroll_value)

    def update_scene_rect(self) -> None:
        audio_duration_sec = self.playback_manager.duration_ms / 1000
        width              = audio_duration_sec * self.px_per_sec
        top_margin         = Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height
        row_height         = Styles.Metrics.Tracks.RowHeight + Styles.Metrics.Tracks.BoxSpacing
        
        total_height = max(
            top_margin + len(self.track_names) * row_height + 100,
            self.viewport().height(),
        )

        self.setSceneRect(0, 0, width, total_height)
        self.total_content_width = width

    # Audio

    def prepare_audio(self) -> None:
        self.update()
        self.global_waveform_max = float(
            max(
                numpy.max(numpy.abs(self.playback_manager.data.astype(numpy.float32))),
                1e-6
            )
        )

    def request_tile(self, tile_index: int) -> None:
        if tile_index in self.pending_tiles or tile_index in self.waveform_tiles:
            return

        self.pending_tiles.add(tile_index)

        dpr        = QGuiApplication.primaryScreen().devicePixelRatio()
        generation = self.tile_generation_id
        worker     = TileWorker(self, tile_index, generation, dpr)

        worker.signals.tile_ready.connect(
            lambda idx, img, gen = generation:
            self.on_tile_ready(idx, img, gen)
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
        
        if self.scale_anim_active:
            self.frozen_tiles.setdefault(tile_index, pixmap)

        if self.frozen_fallback_tiles:
            self.tile_fade_alphas[tile_index] = 0.0

            if not self.waveform_anim_timer.isActive():
                self.waveform_anim_timer.start()

        self.viewport().update()

    def compute_tile_image(self, tile_index: int, dpr: float) -> QImage | None:
        data           = self.playback_manager.data
        total_px       = self.total_content_width
        samples_per_px = len(data) / float(total_px)

        start_px     = tile_index * self.tile_width
        start_sample = int(start_px * samples_per_px)
        end_sample   = min(len(data), int((start_px + self.tile_width) * samples_per_px))

        chunk = data[start_sample:end_sample]

        if chunk.shape[0] == 0:
            return None
        
        height = float(Styles.Metrics.Waveform.Height)
        sigma  = float(Constants.current_settings["waveform_smoothing"])

        calculated_data = VisualFunctions.process_waveform_tile(
            chunk.astype(numpy.float32),
            self.tile_width,
            samples_per_px,
            height,
            self.global_waveform_max,
            sigma
        )
        
        top    = calculated_data[:, 0]
        bottom = calculated_data[:, 1]

        count = len(top)

        if count == 0:
            return None

        image = QImage(
            int(self.tile_width * dpr),
            int(height * dpr),
            QImage.Format.Format_ARGB32_Premultiplied
        )

        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_width          = float(self.tile_width) / count
        x_positions        = (numpy.arange(count) * bar_width).astype(numpy.float32)
        y_top_positions    = numpy.clip(top.astype(numpy.float32),    0.0, float(height))
        y_bottom_positions = numpy.clip(bottom.astype(numpy.float32), 0.0, float(height))

        all_x = numpy.concatenate([x_positions, x_positions[::-1]])
        all_y = numpy.concatenate([y_top_positions, y_bottom_positions[::-1]])

        points = [QPointF(x, y) for x, y in zip(all_x, all_y)]

        path = QPainterPath()
        path.addPolygon(QPolygonF(points))
        path.closeSubpath()

        painter.setPen(self.cached_waveform_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setBrush(self.cached_waveform_brush)
        painter.setPen(self.cached_waveform_pen2)
        painter.drawPath(path)

        painter.end()

        return image

    # Render

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self.cached_background_color)

        if Constants.current_settings["antialiasing"]:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.draw_waveform(painter, rect)
        self.draw_beat_lines(painter, rect)
        self.draw_ruler(painter, rect)
        self.draw_track_grid(painter, rect)

    def drawForeground(
            self,
            painter: QPainter,
            rect:    QRectF
        ) -> None:
        
        painter.resetTransform()

        radius    = 16
        view_rect = self.viewport().rect()

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        full = QPainterPath()
        full.addRect(QRectF(view_rect))

        rounded = QPainterPath()
        rounded.addRoundedRect(QRectF(view_rect), radius, radius)

        mask = full.subtracted(rounded)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.cached_foreground_color)
        painter.drawPath(mask)

    def draw_waveform(self, painter: QPainter, rect: QRectF) -> None:
        if self.playback_manager.data is None or len(self.playback_manager.data) == 0:
            return

        waveform_y = Styles.Metrics.Tracks.RulerHeight

        if self.scale_anim_active and self.frozen_tiles:
            scale_ratio = self.px_per_sec / self.frozen_px_per_sec

            for tile_index, pixmap in self.frozen_tiles.items():
                dst_x     = tile_index * self.tile_width * scale_ratio
                dst_width = self.tile_width * scale_ratio
                tile_h    = pixmap.height() / pixmap.devicePixelRatio()
                dst_rect  = QRectF(dst_x, waveform_y, dst_width, tile_h)

                if dst_rect.right() >= rect.left() and dst_rect.left() <= rect.right():
                    painter.drawPixmap(dst_rect, pixmap, QRectF(pixmap.rect()))

            return

        start_tile = int(rect.left() // self.tile_width)
        end_tile   = int(rect.right() // self.tile_width)

        if self.frozen_fallback_tiles:
            fallback_ratio = self.px_per_sec / self.frozen_fallback_px_per_sec

            for tile_index, pixmap in self.frozen_fallback_tiles.items():
                dst_x     = tile_index * self.tile_width * fallback_ratio
                dst_width = self.tile_width * fallback_ratio
                tile_h    = pixmap.height() / pixmap.devicePixelRatio()
                dst_rect  = QRectF(dst_x, waveform_y, dst_width, tile_h)

                if dst_rect.right() >= rect.left() and dst_rect.left() <= rect.right():
                    painter.drawPixmap(dst_rect, pixmap, QRectF(pixmap.rect()))

        for i in range(start_tile, end_tile + 1):
            tile = self.waveform_tiles.get(i)

            if tile is None:
                self.request_tile(i)
                continue

            draw_x = i * self.tile_width

            if draw_x > rect.right() or draw_x + self.tile_width < rect.left():
                continue

            alpha  = self.tile_fade_alphas.get(i, 1.0)
            tile_h = tile.height() / tile.devicePixelRatio()

            if alpha < 1.0:
                painter.setOpacity(alpha)
                painter.drawPixmap(draw_x, waveform_y, tile)
                painter.setOpacity(1.0)
            
            else:
                painter.fillRect(
                    QRectF(draw_x, waveform_y, self.tile_width, tile_h),
                    self.cached_background_color
                )

                painter.drawPixmap(draw_x, waveform_y, tile)

    def draw_ruler(self, painter: QPainter, rect: QRectF) -> None:
        painter.setFont(self.ruler_font)
        painter.setPen(self.cached_ruler_pen)

        start_second = int(rect.left() / self.px_per_sec)
        end_second   = int(rect.right() / self.px_per_sec)

        ruler_lines  = []
        ruler_height = Styles.Metrics.Tracks.RulerHeight

        for i in range(start_second, end_second + 1):
            x = i * self.px_per_sec
            ruler_lines.append(QLineF(x, 0, x, 8))
            painter.drawText(QPointF(x + 5, ruler_height - 10), str(i))

        if ruler_lines:
            painter.drawLines(ruler_lines)

    def draw_beat_lines(self, painter: QPainter, rect: QRectF) -> None:
        if not self.composition.beats:
            return

        painter.setPen(self.cached_beat_pen)

        line_height  = Styles.Metrics.Waveform.Height + Styles.Metrics.Tracks.RulerHeight
        rect_right   = rect.right()
        rect_left    = rect.left()
        beat_lines   = []

        for beat in self.composition.beats:
            x = beat * self.px_per_sec
    
            if x > rect_right:
                break
            
            if x >= rect_left:
                beat_lines.append(QLineF(x, 0, x, line_height))

        if beat_lines:
            painter.drawLines(beat_lines)

    def draw_track_grid(self, painter: QPainter, rect: QRectF) -> None:
        if rect.left() > Styles.Metrics.Tracks.BoxHeight:
            return

        painter.setFont(self.track_label_font)
        painter.setPen(self.cached_track_name_color)

        box_spacing     = Styles.Metrics.Tracks.BoxSpacing
        label_width     = Styles.Metrics.Tracks.LabelWidth
        row_height      = Styles.Metrics.Tracks.RowHeight
        box_height      = Styles.Metrics.Tracks.BoxHeight
        rect_top        = rect.top()
        rect_bottom     = rect.bottom()

        y = (
            Styles.Metrics.Tracks.RulerHeight +
            Styles.Metrics.Waveform.Height    +
            box_spacing
        )

        for track_name in self.track_names:
            top_y    = y + (row_height - box_height) / 2.0
            bottom_y = top_y + box_height

            if bottom_y >= rect_top and top_y <= rect_bottom:
                label_rect = QRectF(
                    box_spacing,
                    top_y,
                    label_width - 2 * box_spacing,
                    box_height
                )
                
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, track_name)

            y += row_height + box_spacing

    # Context menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            return

        try:
            scene_pos        = self.mapToScene(event.pos())
            item_under_mouse = self.scene.itemAt(scene_pos, self.transform())

            if not item_under_mouse:
                return

            if item_under_mouse not in self.glyph_controller.glyph_items.values():
                return

            if not item_under_mouse.isSelected():
                self.scene.clearSelection()
                item_under_mouse.setSelected(True)

            selected_ids   = self.glyph_controller.get_selected_glyph_ids()
            selected_items = self.glyph_controller.get_selected_glyph_items()
            clicked_glyph  = self.composition.get_glyph(item_under_mouse.glyph_id)

            if not clicked_glyph:
                return

            Player.ui_player.play_sound("Menu/Open", setting_key = "context_menu_sounds")
            self.update()

            effects, can_show_segments = self.resolve_effect_options(
                selected_ids,
                selected_items
            )

            effect_entries = [
                self.make_effect_entry(
                    effect_name,
                    config,
                    clicked_glyph,
                    selected_ids
                )
                for effect_name, config in effects.items()
            ]

            entries: list = [
                ("Delete",               self.glyph_controller.delete_selected_glyphs),
                ("Copy",                 self.glyph_controller.copy_glyphs),
                ("Paste",                self.glyph_controller.paste_glyphs),
                ("Cut",                  self.glyph_controller.cut_glyphs),
                ("-",                    None),
                ("Change Brightness...", lambda: QTimer.singleShot(0, self.brightness_control_popup)),
                ("Change Duration...",   lambda: QTimer.singleShot(0, self.duration_control_popup)),
                ("-",                    None),
                ("Effect",               effect_entries)
            ]

            if can_show_segments:
                entries.append(
                    (
                        "Segments...",
                        lambda: QTimer.singleShot(0, self.segment_control_popup)
                    )
                )

            self.menu = Menu.ContextMenu(entries, self)
            self.menu.exec(event.globalPos())
            self.menu.deleteLater()

        except Exception as error:
            logger.error(f"Context menu error: {error}")
            logger.error(traceback.format_exc())

            Windows.ErrorWindow(
                "Context Menu Error",
                "An unexpected error occurred while opening the context menu."
            ).exec()

    def resolve_effect_options(
        self,
        selected_ids:   list[int],
        selected_items: list[Widgets.GlyphItem]
    ) -> tuple[dict, bool]:

        if not selected_ids or not selected_items:
            return {}, False

        segments_map = Constants.DEVICES[self.composition.model].segments_map

        has_non_segmented = [
            not segments_map.get(self.composition.get_glyph(glyph_id)["track"], False)
            for glyph_id in selected_ids
        ]

        has_segmented = [
            segments_map.get(self.composition.get_glyph(glyph_id)["track"], False)
            for glyph_id in selected_ids
        ]

        has_custom_segments = any(
            GlyphEffects.is_segment_edited(self.composition.get_glyph(glyph_id))
            for glyph_id in selected_ids
        )

        same_track = all(
            item.track == selected_items[0].track
            for item in selected_items
        )

        can_show_segments = all(has_segmented) and same_track

        if any(has_non_segmented):
            effects = GlyphEffects.get_non_segmented_effects()

        elif has_custom_segments:
            effects = GlyphEffects.get_segmentation_supported_effects()

        else:
            effects = GlyphEffects.get_all_effects()

        return effects, can_show_segments

    def make_effect_entry(
        self,
        effect_name:   str,
        config:        dict,
        clicked_glyph: dict,
        selected_ids:  list[int]
    ) -> tuple[str, list]:

        preview: Menu.EffectPreviewWidget = Menu.EffectPreviewWidget(
            effect_name,
            config,
            clicked_glyph
        )

        preview.apply_requested.connect(
            lambda name, settings: self.apply_effect_to_selection(
                name,
                settings,
                selected_ids
            )
        )

        return (
            effect_name,
            [
                ("Preview", preview)
            ]
        )

    def apply_effect_to_selection(
        self,
        effect_name:  str,
        settings:     dict,
        selected_ids: list[int],
    ) -> None:
        
        before_state: dict[int, dict] = {}
        after_state:  dict[int, dict] = {}

        for gid in selected_ids:
            element = self.composition.get_glyph(gid)

            if not element:
                continue
            
            before_state[gid] = copy.deepcopy(element)
            after_state[gid]  = GlyphEffects.apply_visual_effect(element, effect_name, settings)

        if not after_state:
            return

        self.composition.update_bunch_of_glyphs(after_state)
        self.glyph_controller.push_action(
            Actions.ActionModify(
                self.glyph_controller,
                before_state,
                after_state
            )
        )
        
        self.glyph_controller.update_glyphs(selected_ids)

    # Popups

    def control_popup(
        self,
        title:   str,
        label:   str,
        key:     str,
        min_val: int        = 1,
        max_val: int | None = None,
    ) -> None:
        
        dialog = Windows.DialogInputWindow(
            title,
            label,
            min_val,
            max_val
        )

        if not dialog.exec():
            return

        self.glyph_controller.modify_selected_glyphs(key, dialog.get_text())

    def brightness_control_popup(self) -> None:
        self.control_popup("Brightness", "Percent", "brightness", max_val=100)

    def duration_control_popup(self) -> None:
        self.control_popup("Duration", "Duration (ms)", "duration", min_val=1, max_val=10000)

    def segment_control_popup(self) -> None:
        selected_ids = self.glyph_controller.get_selected_glyph_ids()
        orig_glyphs  = {gid: self.composition.get_glyph(gid) for gid in selected_ids}

        first_id     = selected_ids[0]
        first_glyph  = orig_glyphs[first_id]

        popup = Windows.SegmentEditor(
            "Segments",
            Constants.DEVICES[self.composition.model].segments_map[first_glyph["track"]],
            first_glyph.get("segments")
        )

        if not popup.exec():
            return

        segments      = popup.segments()
        turned_on     = [i for i, s in enumerate(segments) if s]
        all_turned_on = all(segments)

        before_state = {gid: copy.deepcopy(orig_glyphs[gid]) for gid in selected_ids}
        after_state: dict[int, dict] = {}

        for gid in selected_ids:
            new_glyph = copy.deepcopy(orig_glyphs[gid])
            
            if all_turned_on:
                new_glyph.pop("segments", None)
            
            else:
                new_glyph["segments"] = turned_on
            
            after_state[gid] = new_glyph

        effect_name   = first_glyph.get("effect", {}).get("name")
        effect_config = GlyphEffects.EffectsConfig.get(effect_name, {}) if effect_name else {}

        if effect_name and not effect_config.get("supports_segmentation", True):
            Windows.ErrorWindow(
                "Effect has been reset",
                "Heads up: custom segmentation doesn't work with applied effect, so we reset the effect."
            ).exec()

            for gid in selected_ids:
                after_state[gid].pop("effect", None)

        modified_before = {gid: before_state[gid] for gid in selected_ids if before_state[gid] != after_state[gid]}
        modified_after  = {gid: after_state[gid]  for gid in selected_ids if before_state[gid] != after_state[gid]}

        if not modified_after:
            return

        self.composition.update_bunch_of_glyphs(modified_after)
        self.glyph_controller.push_action(
            Actions.ActionModify(self.glyph_controller, modified_before, modified_after)
        )

    # Tutorial

    def check_tutorial(self) -> None:
        if Constants.current_settings.get("_tutorial_shown"):
            return

        self.tutorial_window = Windows.Tutorial(self.composition.full_song_path)

        Constants.current_settings.set_value("_tutorial_shown", True)

        QTimer.singleShot(0, self.tutorial_window.show)

        return True

    # Misc

    def show_error_dialog(
        self,
        title: str,
        message: str
    ) -> None:
        
        Windows.ErrorWindow(title, message, "Oh nah").exec()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self.update_scene_rect()

    # Events

    def wheelEvent(self, event: QEvent) -> None:
        self.wheel_controller.process_wheel_event(event)

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