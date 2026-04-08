from __future__ import annotations

import copy
import numpy
import traceback

from loguru import logger

from PyQt5.QtGui import (
    QPen,
    QColor,
    QBrush,
    QPixmap,
    QPainter,
    QPolygonF,
    QMouseEvent,
    QKeySequence,
    QPainterPath,
    QContextMenuEvent
)

from PyQt5.QtCore import (
    Qt,
    QTimer,
    QEvent,
    QPoint,
    QLineF,
    QRectF,
    QPointF,
    QSettings,
    pyqtSignal,
    QElapsedTimer
)

from PyQt5.QtWidgets import (
    QWidget,
    QShortcut,
    QOpenGLWidget,
    QGraphicsView,
    QGraphicsScene
)

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
    Basic,
    Widgets,
    Windows
)

class Tooltip(Widgets.ValuePopup):
    def __init__(self, conductor: ScrollableContent) -> None:
        super().__init__()

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

    def calculate_position(self, target_item: Widgets.GlyphItem | None = None) -> QPoint:
        viewport = self.conductor.viewport()

        if not target_item:
            selected    = self.conductor.scene.selectedItems()
            target_item = selected[0] if selected else None

        if not target_item:
            return self.conductor.mapToGlobal(viewport.rect().center())

        rect = target_item.boundingRect()
        bottom_center = QPointF(rect.center().x(), rect.bottom())
        scene_pos = target_item.mapToScene(bottom_center)
        view_pos = self.conductor.mapFromScene(scene_pos)

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
            effect_name,
        ]

        self.show_tooltip_at("\n".join(info), item)

class ScrollableContent(QGraphicsView):
    playhead_moved = pyqtSignal(float)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.configure_view()
        self.init_state(parent)
        self.setup_ui()
        self.setup_shortcuts()

    def configure_view(self) -> None:
        if Constants.CURRENT_SETTINGS["gpu"]:
            self.gl_viewport = QOpenGLWidget()
            self.gl_viewport.frameSwapped.connect(self.on_frame_swapped)

            self.fps_timer   = QElapsedTimer()
            self.frame_count = 0
            
            self.fps_timer.start()

            self.setViewport(self.gl_viewport)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def init_state(self, parent: QWidget) -> None:
        self.playback_manager: Player.PlaybackManager          = parent.playback_manager
        self.composition:      ProjectSaver.Composition | None = None

        self.px_per_sec: float = Constants.CURRENT_SETTINGS["default_scaling"]
        self.tile_width: int   = Constants.CURRENT_SETTINGS["tile_width"]

        self.track_names           = []
        self.total_content_width   = 0
        self.waveform_tiles        = {}
        self.global_waveform_max   = 1e-6
        self.is_auto_scroll_active = False

        self.ruler_font       = Utils.NType(10)
        self.track_label_font = Utils.NType(15)

    def setup_ui(self) -> None:
        self.playhead_timer = Basic.Timer(
            Constants.FPS_120,
            self.on_playback_position_updated
        )

        self.tooltip = Tooltip(self)
        self.playhead       = Widgets.PlayheadItem(self)
        self.marquee_item   = Widgets.MarqueeItem(self.playback_manager)
        self.playhead_hover = Widgets.PlayheadItem(self, Styles.Metrics.Tracks.RulerHeight + Styles.Metrics.Waveform.Height)

        for item in (self.playhead, self.playhead_hover, self.marquee_item):
            self.scene.addItem(item)

        self.playhead_hover.hide()

    def setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(lambda: self.scale_view(+100))
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(lambda: self.scale_view(-100))

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

    def set_playhead_position_px(self, x: float) -> None:
        self.playhead.setPos(min(x, self.total_content_width), 0)
        self.playhead_moved.emit(x / self.total_content_width)

    def get_playhead_position_ms(self) -> float:
        return (self.playhead.pos().x() / self.px_per_sec) * 1000.0

    def set_playhead_position_ms(self, ms: float) -> None:
        self.set_playhead_position_px((ms / 1000.0) * self.px_per_sec)

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
            self.stop_paddedlayback()
            self.on_playback_position_updated()

    def on_playback_position_updated(self) -> None:
        pos_ms     = self.playback_manager.get_position()
        true_x_pos = (pos_ms / 1000.0) * self.px_per_sec
        
        self.set_playhead_position_px(int(true_x_pos))

        horizontal_bar          = self.horizontalScrollBar()
        viewport_width = self.viewport().width()
        offset_ratio   = Constants.CURRENT_SETTINGS["playhead_position"]
        target_scroll  = int(true_x_pos) - int(viewport_width * offset_ratio)

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

    def stop_paddedlayback(self) -> None:
        self.playhead_timer.stop()
        self.glyph_visualizer.stop_all()

        if self.composition:
            self.composition.syncer.stop()

    def sync_scroll_to_playhead(self) -> None:
        viewport_width = self.viewport().width()
        offset_ratio   = Constants.CURRENT_SETTINGS["playhead_position"]
        
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

        self.glyph_visualizer = Windows.GlyphVisualizer(
            self,
            self.composition.model,
            self.playback_manager,
            self.composition.bpm
        )

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

        self.set_playhead_position_px(0)
        self.horizontalScrollBar().setValue(0)

        self.glyph_visualizer.exit()

        self.glyph_controller.elements_changed.disconnect()
        self.horizontalScrollBar().valueChanged.disconnect(self.mouse_controller.force_mouse_update)

        self.keyboard_controller.cleanup_shortcuts()

        self.glyph_controller    = None
        self.wheel_controller    = None
        self.mouse_controller    = None
        self.keyboard_controller = None
        self.waveform_tiles      = {}

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

    def scale_view(
            self,
            delta: float,
            force_update: bool = False
        ) -> None:
        
        viewport_width = self.viewport().width()
        current_scroll = self.horizontalScrollBar().value()

        center_px = current_scroll + viewport_width / 2
        center_ms = (center_px / self.px_per_sec) * 1000.0

        current_playhead_ms = self.get_playhead_position_ms()

        duration_sec = max(self.playback_manager.duration_ms / 1000.0, 0.001)
        
        fit_px_per_sec = viewport_width / duration_sec
        min_px_per_sec = max(fit_px_per_sec, 20.0)
        new_px_per_sec = max(min_px_per_sec, self.px_per_sec + delta)

        if self.px_per_sec == new_px_per_sec and not force_update:
            return

        self.px_per_sec = new_px_per_sec
        self.waveform_tiles.clear()

        self.update_scene_rect() 

        self.set_playhead_position_ms(current_playhead_ms)

        if self.composition:
            self.glyph_controller.update_glyphs()

        new_center_px = (center_ms / 1000.0) * self.px_per_sec
        new_scroll_value = int(new_center_px - viewport_width / 2)
        self.horizontalScrollBar().setValue(new_scroll_value)

        self.viewport().update()

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
        self.global_waveform_max = max(
            numpy.max(numpy.abs(self.playback_manager.data.astype(numpy.float32))),
            1e-6
        )

    def generate_tile(self, tile_index: int) -> QPixmap | None:
        data           = self.playback_manager.data
        total_px       = self.total_content_width
        samples_per_px = len(data) / float(total_px)

        start_px     = tile_index * self.tile_width
        start_sample = int(start_px * samples_per_px)
        end_sample   = min(len(data), int((start_px + self.tile_width) * samples_per_px))

        chunk = data[start_sample:end_sample]
        min_samples = numpy.min(chunk, axis=1)
        max_samples = numpy.max(chunk, axis=1)

        sample_count = len(min_samples)
        
        if sample_count == 0:
            return

        step     = max(1, int(numpy.ceil(sample_count / float(self.tile_width))) if self.tile_width > 0 else sample_count)
        indices  = numpy.arange(0, sample_count, step)
        min_vals = numpy.minimum.reduceat(min_samples, indices)
        max_vals = numpy.maximum.reduceat(max_samples, indices)

        max_f = max_vals.astype(numpy.float32) / self.global_waveform_max
        min_f = min_vals.astype(numpy.float32) / self.global_waveform_max

        height   = int(Styles.Metrics.Waveform.Height)
        center_y = height / 2.0
        top      = center_y - max_f * center_y
        bottom   = center_y - min_f * center_y

        sigma = Constants.CURRENT_SETTINGS["waveform_smoothing"]
        
        if sigma and sigma > 0.0 and len(top) > 1:
            padding_size   = min(int(numpy.ceil(sigma * 3.0)), len(top) - 1)
            top_padded     = numpy.pad(top, (padding_size, padding_size), "reflect")
            bottom_padded  = numpy.pad(bottom, (padding_size, padding_size), "reflect")
            top            = Utils.gaussian_filter1d_np(top_padded, sigma)[padding_size:padding_size + len(top)]
            bottom         = Utils.gaussian_filter1d_np(bottom_padded, sigma)[padding_size:padding_size + len(bottom)]

        if len(top) == len(bottom):
            mask = top > bottom
            
            if mask.any():
                avg          = (top + bottom) / 2.0
                top[mask]    = avg[mask]
                bottom[mask] = avg[mask]

        pixmap = QPixmap(self.tile_width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)

        if Constants.CURRENT_SETTINGS["antialiasing"]:
            painter.setRenderHint(QPainter.Antialiasing)

        count = len(top)
        
        if count == 0:
            painter.end()
            return None

        bar_width          = float(self.tile_width) / count
        x_positions        = (numpy.arange(count) * bar_width).astype(numpy.float32)
        y_top_positions    = numpy.clip(top.astype(numpy.float32),    0.0, float(height))
        y_bottom_positions = numpy.clip(bottom.astype(numpy.float32), 0.0, float(height))

        points  = [QPointF(float(x), float(y)) for x, y in zip(x_positions,        y_top_positions)]
        points += [QPointF(float(x), float(y)) for x, y in zip(x_positions[::-1], y_bottom_positions[::-1])]

        path = QPainterPath()
        path.addPolygon(QPolygonF(points))
        path.closeSubpath()

        painter.setPen(QPen(QColor(255, 255, 255, 90), 2.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setBrush(QBrush(QColor(255, 255, 255, 90)))
        painter.setPen(QPen(QColor(255, 255, 255, 160), 0.7))
        painter.drawPath(path)

        painter.end()
        
        self.waveform_tiles[tile_index] = pixmap

        return pixmap

    # Render

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(self.sceneRect(), QColor(0, 0, 0))

        if Constants.CURRENT_SETTINGS["antialiasing"]:
            painter.setRenderHint(QPainter.Antialiasing)

        self.draw_waveform(painter, rect)
        self.draw_beat_lines(painter, rect)
        self.draw_ruler(painter, rect)
        self.draw_track_grid(painter, rect)

    def draw_waveform(self, painter: QPainter, rect: QRectF) -> None:
        if self.playback_manager.data is None or len(self.playback_manager.data) == 0:
            return

        start_tile = int(rect.left() // self.tile_width)
        end_tile   = int(rect.right() // self.tile_width)

        for i in range(start_tile, end_tile + 1):
            tile = self.waveform_tiles.get(i) or self.generate_tile(i)

            if not tile:
                continue

            draw_x = i * self.tile_width
            
            if draw_x <= rect.right() and draw_x + self.tile_width >= rect.left():
                painter.drawPixmap(draw_x, Styles.Metrics.Tracks.RulerHeight, tile)

    def draw_ruler(self, painter: QPainter, rect: QRectF) -> None:
        painter.setFont(self.ruler_font)
        painter.setPen(QPen(QColor(255, 255, 255), 0.5))

        start_second = int(rect.left() / self.px_per_sec)
        end_second   = int(rect.right() / self.px_per_sec)

        for i in range(start_second, end_second + 1):
            x = i * self.px_per_sec
            painter.drawLine(QPointF(x, 0), QPointF(x, 8))
            painter.drawText(QPointF(x + 5, Styles.Metrics.Tracks.RulerHeight - 10), str(i))

    def draw_beat_lines(self, painter: QPainter, rect: QRectF) -> None:
        if not self.composition.beats:
            return

        painter.setPen(QPen(QColor(Styles.Colors.Waveline.BeatColor), 1, Qt.PenStyle.DotLine))

        line_height = Styles.Metrics.Waveform.Height + Styles.Metrics.Tracks.RulerHeight
        lines = [
            QLineF(QPointF(x, 0), QPointF(x, line_height))
            for beat in self.composition.beats
            if 0 <= (x := beat * self.px_per_sec) <= rect.x() + rect.width()
        ]

        if lines:
            painter.drawLines(lines)

    def draw_track_grid(self, painter: QPainter, rect: QRectF) -> None:
        if rect.left() > Styles.Metrics.Tracks.BoxHeight:
            return

        painter.setFont(self.track_label_font)
        painter.setPen(QColor(Styles.Colors.Waveline.TrackNameColor))

        y = (
            Styles.Metrics.Tracks.RulerHeight +
            Styles.Metrics.Waveform.Height +
            Styles.Metrics.Tracks.BoxSpacing
        )

        for track_name in self.track_names:
            top_y    = y + (Styles.Metrics.Tracks.RowHeight - Styles.Metrics.Tracks.BoxHeight) / 2.0
            bottom_y = top_y + Styles.Metrics.Tracks.BoxHeight

            if bottom_y >= rect.top() and top_y <= rect.bottom():
                label_rect = QRectF(
                    Styles.Metrics.Tracks.BoxSpacing,
                    top_y,
                    Styles.Metrics.Tracks.LabelWidth - 2 * Styles.Metrics.Tracks.BoxSpacing,
                    Styles.Metrics.Tracks.BoxHeight,
                )
                
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, track_name)

            y += Styles.Metrics.Tracks.RowHeight + Styles.Metrics.Tracks.BoxSpacing

    # Context menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if event.modifiers() & Qt.AltModifier:
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

            Player.ui_player.play_sound("App/Menu/MenuOpen")
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
                ("Delete", self.glyph_controller.delete_selected_glyphs),
                ("Copy",   self.glyph_controller.copy_glyphs),
                ("Paste",  self.glyph_controller.paste_glyphs),
                ("Cut",    self.glyph_controller.cut_glyphs),
                ("-",      None),
                ("Change Brightness...", lambda: QTimer.singleShot(0, self.brightness_control_popup)),
                ("Change Duration...",   lambda: QTimer.singleShot(0, self.duration_control_popup)),
                ("-",      None),
                ("Effect", effect_entries)
            ]

            if can_show_segments:
                entries.append(
                    (
                        "Segments...",
                        lambda: QTimer.singleShot(0, self.segment_control_popup)
                    )
                )

            self.menu = Menu.ContextMenu(entries, self)
            self.menu.exec_(event.globalPos())
            self.menu.deleteLater()

        except Exception as error:
            logger.error(f"Context menu error: {error}")
            logger.error(traceback.format_exc())

            Windows.ErrorWindow(
                "Context Menu Error",
                "An unexpected error occurred while opening the context menu."
            ).exec_()

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
            Actions.ActionModify(self.glyph_controller, before_state, after_state)
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
            max_val,
            bpm = self.composition.bpm,
            player = self.playback_manager,
        )

        if not dialog.exec_():
            return

        self.glyph_controller.modify_selected_glyphs(key, dialog.get_text())

    def brightness_control_popup(self) -> None:
        self.control_popup("Brightness", "Percent", "brightness", max_val=100)

    def duration_control_popup(self) -> None:
        self.control_popup("Duration", "Duration (ms)", "duration", min_val=1, max_val=10000)

    def segment_control_popup(self) -> None:
        selected_ids = self.glyph_controller.get_selected_glyph_ids()
        orig_glyphs  = {gid: self.composition.get_glyph(gid) for gid in selected_ids}

        first_id    = selected_ids[0]
        first_glyph = orig_glyphs[first_id]

        popup = Windows.SegmentEditor(
            "Segments",
            Constants.DEVICES[self.composition.model].segments_map[first_glyph["track"]],
            first_glyph.get("segments"),
            self.composition.bpm,
            self.playback_manager
        )

        if not popup.exec_():
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
                "Heads up: custom segmentation doesn't work with applied effect, so we reset the effect.",
            ).exec_()

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
        if Constants.CURRENT_SETTINGS.get("tutorial_shown"):
            return

        self.tutorial_window = Windows.Tutorial(
            self.composition.bpm,
            self.composition.full_song_path
        )

        settings = QSettings("chips047", "Cassette")
        settings.setValue("tutorial_shown", True)
        settings.sync()
        Constants.load_settings()

        QTimer.singleShot(0, self.tutorial_window.exec_)

    # Misc

    def show_error_dialog(
        self,
        title: str,
        message: str
    ) -> None:
        
        Windows.ErrorWindow(title, message, "Oh nah").exec_()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self.scale_view(0)
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