import time
import copy
import traceback

import numpy as np

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System import Player as Player
from System import Styles
from System import GlyphEffects
from System import ProjectSaver

from System.Constants import *
from loguru import logger

from System import UI
from System import Utils

from System.Interface import CompositorUI

class KeyboardController(QObject):
    def __init__(self, conductor, playback_manager):
        super().__init__()
        self.conductor = conductor
        self.playback_manager = playback_manager
        self.glyph_controller = conductor.glyph_controller
        self.move_increment = CurrentSettings["arrow_increment"]
        self.shortcuts = []
        
        self.destroyed.connect(self._release_shortcuts)
        self._setup_hotkeys()

    def _setup_hotkeys(self):
        def bind(key, action):
            shortcut = QShortcut(QKeySequence(key), self.conductor)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)

        bind(Qt.Key_Space, self._handle_playback_toggle)
        bind(Qt.Key_Left, lambda: self._handle_manual_scroll(-self.move_increment))
        bind(Qt.Key_Right, lambda: self._handle_manual_scroll(self.move_increment))
        
        bind(Qt.CTRL + Qt.Key_C, self.glyph_controller.copy_glyphs)
        bind(Qt.CTRL + Qt.Key_V, self.glyph_controller.paste_glyphs)
        bind(Qt.CTRL + Qt.Key_X, self.glyph_controller.cut_glyphs)
        
        bind(Qt.Key_Delete, self.glyph_controller.delete_glyphs)
        bind(Qt.Key_Backspace, self.glyph_controller.delete_glyphs)
        
        bind(Qt.Key_S, self.conductor.main_window_ref.playspeed_button.next_state)
        bind(Qt.Key_B, self._open_brightness_editor)
        bind(Qt.Key_D, self._open_duration_editor)

        for key, track_id in self.glyph_controller.track_map.items():
            bind(key, lambda t=track_id: self.glyph_controller.spawn_glyph_on_track(t))

    def _handle_playback_toggle(self):
        current_ms = self.conductor.get_playhead_ms()
        
        if current_ms >= self.playback_manager.duration_ms - 5:
            self.conductor.set_playhead_position_ms(0)
            current_ms = 0
        
        self.playback_manager.toggle_playback(current_ms)

    def _handle_manual_scroll(self, delta_px):
        if self.playback_manager.is_playing:
            return
        
        current_x = self.conductor.get_playhead_position_px()
        target_x = max(0, min(self.conductor.total_content_width, current_x + delta_px))
        self.conductor.set_playhead_position_px(target_x)

    def _open_brightness_editor(self):
        if self._ensure_selection():
            self.conductor.brightness_control_popup()

    def _open_duration_editor(self):
        if self._ensure_selection():
            self.conductor.duration_control_popup()

    def _ensure_selection(self):
        if not self.conductor.scene.selectedItems():
            self.glyph_controller._update_popup("No glyph selected!", plan_hide = True)
            return False
        
        return True
    
    def _release_shortcuts(self):
        for sc in self.shortcuts:
            sc.activated.disconnect()
            sc.deleteLater()
        
        self.shortcuts = []

class WheelController:
    def __init__(self, conductor):
        self.conductor = conductor

        self._scroll_velocity = 0
        self._scroll_target_velocity = 0
        
        self.zoom_step = CurrentSettings["zoom_step"]
        self.scroll_acceleration = CurrentSettings["scroll_acceleration"]

        self._scroll_timer = QTimer(conductor)
        self._scroll_timer.timeout.connect(self._update_smooth_scroll)
        self._scroll_timer.setInterval(FPS_120)
    
    def process_wheel_event(self, event):
        delta = event.angleDelta().y()
        modifiers = event.modifiers()

        if modifiers & Qt.ControlModifier:
            self.conductor.scale_view(+ self.zoom_step if delta > 0 else - self.zoom_step)

        elif modifiers & Qt.ShiftModifier:
            v_bar = self.conductor.verticalScrollBar()
            v_bar.setValue(v_bar.value() - delta)

        else:
            if self.conductor.playback_manager.is_playing:
                return event.accept()
            
            self._scroll_target_velocity += -delta * self.scroll_acceleration

            if not self._scroll_timer.isActive():
                self._scroll_timer.start()

        event.accept()

    def _update_smooth_scroll(self):
        h_bar = self.conductor.horizontalScrollBar()

        self._scroll_velocity += (self._scroll_target_velocity - self._scroll_velocity) * 0.2
        h_bar.setValue(int(h_bar.value() + self._scroll_velocity))

        self._scroll_target_velocity *= 0.9

        if abs(self._scroll_velocity) < 0.1 and abs(self._scroll_target_velocity) < 0.1:
            self._scroll_timer.stop()
            self._scroll_velocity = 0
            self._scroll_target_velocity = 0

class GlyphController(QObject):
    elements_changed = pyqtSignal()
    
    def __init__(
            self,
            conductor,
            composition: ProjectSaver.Composition
        ):
        
        super().__init__()
        
        self.conductor = conductor
        self.composition = composition
        
        self.glyph_items: list[CompositorUI.GlyphItem] = []
        self.copied_data = []
        
        self._drag_session = {}
        self.updates = {}
        
        self._popup = UI.ValuePopup()
        
        self.manual_hide_timer = QTimer()
        self.manual_hide_timer.setSingleShot(True)
        self.manual_hide_timer.timeout.connect(self.hide_tooltip)
        
        self.track_map = {
            Qt.Key.Key_1: "1",
            Qt.Key.Key_2: "2",
            Qt.Key.Key_3: "3",
            Qt.Key.Key_4: "4",
            Qt.Key.Key_5: "5",
            Qt.Key.Key_6: "6",
            Qt.Key.Key_7: "7",
            Qt.Key.Key_8: "8",
            Qt.Key.Key_9: "9",
            Qt.Key.Key_0: "10",
            Qt.Key.Key_Minus: "11"
        }
    
    def cleanup_tooltip(self):
        if self._popup:
            self._popup.cleanup()
    
    def hide_tooltip(self):
        if self._drag_session:
            return
            
        if self._popup:
            self._popup.hide()
    
    def show_hover_tooltip(self, item):
        if self._drag_session:
            return

        glyph = self.composition.get_glyph(item.glyph_id)
        if not glyph:
            return

        effect = glyph.get("effect")
        effect_name = f"Effect: {effect['name']}" if effect else "No effect"

        info = (
            f"Start: {glyph.get('start')} ms\n"
            f"Duration: {glyph.get('duration')} ms\n"
            f"Brightness: {glyph.get('brightness')}\n"
            f"{effect_name}"
        )

        self._update_popup(info, item)
    
    def update_glyphs(self):
        for glyph in self.glyph_items:
            glyph.update_geometry()
    
    def clear_glyphs(self):
        for item in self.glyph_items:
            item.remove_glyph()
        
        self.glyph_items.clear()
        self.elements_changed.emit()

    def delete_glyphs(self):
        deleted_ids = []
        items = self.conductor.scene.selectedItems()
        
        if not items:
            return

        for item in items:
            if item not in self.glyph_items:
                continue
            
            deleted_ids.append(item.glyph_id)
            self.glyph_items.remove(item)
            item.remove_glyph()

        if deleted_ids:
            self.composition.delete_bunch_of_glyphs(deleted_ids)
        
        self.elements_changed.emit()

    def spawn_glyph_on_track(self, track_index):
        audio_duration = Player.player.duration_ms
        current_ms = self.conductor.get_playhead_ms()
        default_duration = self.composition.duration_ms

        remaining_time = max(0, audio_duration - current_ms)
        actual_duration = min(default_duration, remaining_time)

        if actual_duration <= 0:
            return

        if int(track_index) > self.composition.track_number:
            return

        new_id, new_data = self.composition.new_glyph(
            track_index,
            current_ms,
            actual_duration
        )

        self._create_glyph_item(new_id, new_data)
        self.elements_changed.emit()
        
        return True
    
    def copy_glyphs(self):
        self.copied_data = []
        selected = [item for item in self.conductor.scene.selectedItems() if isinstance(item, CompositorUI.GlyphItem)]

        for item in selected:
            glyph_data = self.composition.get_glyph(item.glyph_id)
            
            if not glyph_data:
                continue

            self.copied_data.append(
                copy.deepcopy(glyph_data)
            )
    
    def cut_glyphs(self):
        self.copy_glyphs()
        self.delete_glyphs()
    
    def paste_glyphs(self):
        if not self.copied_data:
            return

        current_ms = self.conductor.get_playhead_ms()
        copied_start_ms = min(data['start'] for data in self.copied_data)
        time_offset = int(current_ms - copied_start_ms)
        audio_ms = self.conductor.playback_manager.duration_ms
        
        self.conductor.scene.clearSelection()

        for glyph_data in self.copied_data:
            new_id, new_data = self.composition.copy_glyph(
                glyph_data,
                time_offset,
                audio_ms
            )

            if new_id is not None:
                self._create_glyph_item(new_id, new_data, reset_selection=False)

        self.elements_changed.emit()
    
    def _create_glyph_item(
        self,
        glyph_id: int,
        data: dict,
        reset_selection = True,
        set_selected = True,
        animate_spawn = True
    ) -> None:
    
        item = CompositorUI.GlyphItem(
            glyph_id,
            data,
            self.conductor,
            self.composition,
            animate_spawn
        )

        self.glyph_items.append(item)
        self.conductor.scene.addItem(item)

        if reset_selection:
            self.conductor.scene.clearSelection()
        
        item.setSelected(set_selected)
        item.update()
    
    def start_drag(self):
        self._drag_session = {}
        selected_items = self.conductor.scene.selectedItems()
        
        for item in selected_items:
            if item not in self.glyph_items:
                continue
            
            self._drag_session[item] = {
                'start': item.start_ms,
                'duration': item.duration_ms
            }

    def update_drag_state(self, delta_ms: float, mode: str, active_item_ref):
        popup_text = ""
        audio_duration_ms = self.conductor.playback_manager.duration_ms

        for item, initial_data in self._drag_session.items():
            initial_start = initial_data['start']
            initial_duration = initial_data['duration']

            if mode == 'move':
                new_start = initial_start + delta_ms
                new_start = max(0, new_start)
                new_start = min(new_start, audio_duration_ms - initial_duration)
                new_start = int(new_start)

                item.update_geometry(start_ms = new_start)
                
                if item == active_item_ref:
                    popup_text = f"{item.start_ms:.0f} ms"

            elif mode == 'resize_right':
                max_allowed_duration = audio_duration_ms - initial_start

                new_duration = initial_duration + delta_ms
                new_duration = max(10, new_duration)
                new_duration = min(new_duration, max_allowed_duration)
                new_duration = int(new_duration)
                
                item.update_geometry(duration_ms = new_duration)
                
                if item == active_item_ref:
                    popup_text = f"{item.duration_ms:.0f} ms"

            elif mode == 'resize_left':
                original_end = initial_start + initial_duration
                
                new_start = initial_start + delta_ms
                new_start = max(0, new_start)
                max_start = original_end - 10
                new_start = min(new_start, max_start)
                
                new_duration = original_end - new_start
                
                new_start = int(new_start)
                new_duration = int(new_duration)

                item.update_geometry(start_ms = new_start, duration_ms = new_duration)

                if item == active_item_ref:
                    popup_text = f"{item.duration_ms:.0f} ms"
        
        if popup_text:
            self._update_popup(popup_text, active_item_ref)

    def end_drag(self):
        updated_data_batch = {}
        
        for item in self._drag_session.keys():
            glyph_obj = self.composition.get_glyph(item.glyph_id)
            
            if glyph_obj:
                glyph_obj['start'] = item.start_ms
                glyph_obj['duration'] = item.duration_ms
                updated_data_batch[item.glyph_id] = glyph_obj

        if updated_data_batch:
            self.composition.update_bunch_of_glyphs(updated_data_batch)

        self._drag_session = {}
    
    def move_selection(self, delta_ms: float):
        selected_items: list[CompositorUI.GlyphItem] = [item for item in self.conductor.scene.selectedItems() if item in self.glyph_items]
        if not selected_items: return

        self.updates = {}
        
        for item in selected_items:
            new_start = max(0, item.start_ms + delta_ms)
            new_start = min(new_start, self.composition.duration_ms - item.duration_ms)
            
            self.updates[item.glyph_id] = {'start': int(new_start)}
            
            item.update_geometry(start_ms = new_start)
    
    def finish_edit_operation(self):
        self.composition.update_bunch_of_glyphs(self.updates)
    
    def resize_selection(self, delta_ms: float, from_left: bool = False):
        selected_items: list[CompositorUI.GlyphItem] = [item for item in self.conductor.scene.selectedItems() if item in self.glyph_items]
        if not selected_items: return

        self.updates = {}
        
        for item in selected_items:
            if from_left:
                new_start = item.start_ms + delta_ms
                new_start = max(0, new_start)
                new_start = min(new_start, item.start_ms + item.duration_ms - 10)
                
                effective_delta = new_start - item.start_ms
                new_duration = item.duration_ms - effective_delta
                
                self.updates[item.glyph_id] = {'start': int(new_start), 'duration': int(new_duration)}
                item.update_geometry(start_ms = new_start, duration_ms = new_duration)
            
            else:
                new_duration = max(10, item.duration_ms + delta_ms)
                self.updates[item.glyph_id] = {'duration': int(new_duration)}
                item.update_geometry(duration_ms = new_duration)
    
    def _update_popup(self, text, target_item = None, plan_hide = False):
        if not target_item and self.conductor.scene.selectedItems():
            target_item = self.conductor.scene.selectedItems()[0]
        
        global_pos = self._get_global_pos(target_item)
        self._popup.show_text(text, global_pos)
        
        if plan_hide:
            if self.manual_hide_timer.isActive():
                self.manual_hide_timer.stop()
            
            self.manual_hide_timer.start(1000)

    def _get_global_pos(self, target_item):
        if not target_item:
            return self.conductor.mapToGlobal(self.conductor.viewport().rect().center())
        
        rect = target_item.boundingRect()

        scene_pos = target_item.mapToScene(QPointF(rect.center().x(), rect.bottom()))
        view_pos = self.conductor.mapFromScene(scene_pos)

        viewport = self.conductor.viewport()

        vx = min(view_pos.x(), viewport.width())
        vx = max(0, vx)
        vy = view_pos.y()

        return viewport.mapToGlobal(QPoint(int(vx), int(vy)))

class AutoScroller:
    def __init__(self, conductor):
        self.conductor = conductor
        
        self.scroll_margin = 100
        self.max_speed = 30.0
        self.damping = 0.90
        self.acceleration_curve = 2.0
        
        # State
        self.velocity = 0.0
        self.is_dragging = False
        self.position = float(self.conductor.horizontalScrollBar().value())
        
        self.timer = QTimer(conductor)
        self.timer.setInterval(FPS_120)
        self.timer.timeout.connect(self._update)

    def process_pos(self, global_pos):
        if self.conductor.playback_manager.is_playing:
            return
        
        self.position = float(self.conductor.horizontalScrollBar().value())
        view_pos = self.conductor.mapFromGlobal(global_pos)
        viewport_w = self.conductor.viewport().width()
        target_velocity = 0.0
        
        # Left Edge
        if view_pos.x() < self.scroll_margin:
            ratio = (self.scroll_margin - view_pos.x()) / self.scroll_margin
            ratio = max(0.0, min(1.0, ratio))
            target_velocity = -self.max_speed * (ratio ** self.acceleration_curve)
            
        # Right Edge
        elif view_pos.x() > viewport_w - self.scroll_margin:
            dist_from_right = view_pos.x() - (viewport_w - self.scroll_margin)
            ratio = dist_from_right / self.scroll_margin
            ratio = max(0.0, min(1.0, ratio))
            target_velocity = self.max_speed * (ratio ** self.acceleration_curve)
            
        self.velocity = target_velocity
        self.is_dragging = True
        
        if abs(self.velocity) > 0.1 and not self.timer.isActive():
            self.timer.start()

    def stop_drag(self):
        self.is_dragging = False

    def _update(self):
        if self.conductor.playback_manager.is_playing:
            return
        
        h_bar = self.conductor.horizontalScrollBar()
        self.position += self.velocity
        self.position = max(h_bar.minimum(), min(h_bar.maximum(), self.position))
        h_bar.setValue(int(self.position))
    
        if self.is_dragging:
            if self.velocity == 0:
                self.timer.stop()
        
        else:
            self.velocity *= self.damping
            if abs(self.velocity) < 0.5:
                self.velocity = 0
                self.timer.stop()

class InteractionHandler:
    def __init__(self, conductor, playback_manager, composition):
        self.conductor = conductor
        self.playback_manager = playback_manager
        self.composition = composition
        
        # Marquee
        self.is_marquee_selecting = False

        # Auto Scroll
        self.auto_scroller = AutoScroller(conductor)

    def stop_auto_scroll_drag(self):
        self.auto_scroller.stop_drag()

    def start_marquee(self, event):
        start_point = self.conductor.mapToScene(event.pos())
        self.conductor.marquee_item.start_marquee(start_point)
        self.is_marquee_selecting = True
    
    def end_marquee(self, event):
        if self.is_marquee_selecting:
            self.conductor.marquee_item.end_marquee()
            self.is_marquee_selecting = False
            
            self.stop_auto_scroll_drag()
    
    def marquee_tick(self, event):
        if self.is_marquee_selecting:
            current_point = self.conductor.mapToScene(event.pos())
            self.conductor.marquee_item.update_end_point(current_point)
            
            self.auto_scroller.process_pos(event.globalPos())

    def _handle_ruler_press(self, event: QMouseEvent):
        if self.playback_manager.is_playing:
            return
        
        new_x = self.conductor.mapToScene(event.pos()).x()

        if self.conductor.get_playhead_position_px() != new_x:
            self.conductor.set_playhead_position_px(new_x)

    def _handle_ruler_hover(self, event):
        y = event.y()
        
        playhead_hover = self.conductor.playhead_hover
        waveform_end = Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.ruler_height
        
        if waveform_end > y > 0:
            if not playhead_hover.isVisible():
                playhead_hover.show()
            
            scene_x = self.conductor.mapToScene(event.pos())
            
            playhead_hover.setPos(scene_x.x(), 0)
        
        else:
            if playhead_hover.isVisible():
                playhead_hover.hide()
    
    def _force_mouse_update(self):
        global_pos = QCursor.pos()
        local_pos = self.conductor.viewport().mapFromGlobal(global_pos)

        fake_event = QMouseEvent(
            QEvent.MouseMove,
            local_pos,
            global_pos,
            Qt.NoButton,
            QApplication.mouseButtons(),
            QApplication.keyboardModifiers()
        )

        self.process_mouse_move_event(fake_event)

    def process_mouse_press_event(self, event: QMouseEvent):
        ruler_or_waveform_rect = QRectF(
            0, 0, self.conductor.width(),
            Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height
        )

        if ruler_or_waveform_rect.contains(event.pos()):
            self._handle_ruler_press(event)
            event.accept()
            
            return

        scene_pos = self.conductor.mapToScene(event.pos())
        item_at_pos = self.conductor.scene.itemAt(scene_pos, self.conductor.transform())

        if item_at_pos:
            return event.ignore()
        
        modifiers = event.modifiers()
        if not (modifiers & Qt.ControlModifier):
            self.conductor.scene.clearSelection()

        self.start_marquee(event)
        event.accept()

    def process_mouse_move_event(self, event: QMouseEvent):
        self.marquee_tick(event)
        self._handle_ruler_hover(event)
    
    def process_mouse_release_event(self, event: QMouseEvent):
        self.end_marquee(event)
    
    def process_mouse_leave_event(self, event: QMouseEvent):
        playhead_hover = self.conductor.playhead_hover
        playhead_hover.hide()

class ScrollableContent(QGraphicsView):
    def __init__(self, parent):
        super().__init__(parent)
        
        # References
        self.main_window_ref = parent
        self.composition = None
        
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        if CurrentSettings["gpu"]:
            self._gl_viewport = QOpenGLWidget()
            self._gl_viewport.frameSwapped.connect(self._on_frame_swapped)
            
            self._fps_timer = QElapsedTimer()
            self._fps_timer.start()
            self._frame_count = 0

            self.setViewport(self._gl_viewport)

        # UI Configuration
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        
        self.setStyleSheet("border: none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self._is_auto_scroll_active = False

        # Scaling & Time
        self.px_per_sec = CurrentSettings["default_scaling"]
    
        # Track Management
        self.track_names = []
        self.total_content_width = 0
    
        # Caching
        self.tile_width = CurrentSettings["tile_width"]
        self.waveform_tiles = {}

        self._track_label_font = Utils.NType(15)
        self._ruler_font = Utils.NType(10)

        self.playback_manager = parent.playback_manager

        self.playhead_timer = QTimer(self)
        self.playhead_timer.setInterval(FPS_120)
        self.playhead_timer.timeout.connect(self._on_playback_position_updated)
        
        self.playhead = CompositorUI.PlayheadItem(self)
        self.playhead_hover = CompositorUI.PlayheadItem(
            self,
            Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height
        )
        
        self.scene.addItem(self.playhead)
        self.scene.addItem(self.playhead_hover)
        
        self.playhead_hover.hide()
        
        self.marquee_item = CompositorUI.MarqueeItem(self.composition, self.playback_manager)
        self.scene.addItem(self.marquee_item)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.on_scale_plus)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.on_scale_minus)
    
    def _on_frame_swapped(self):
        self._frame_count += 1
        elapsed = self._fps_timer.elapsed()
        
        if elapsed >= 1000:
            real_fps = self._frame_count / (elapsed / 1000.0)
            
            if self.window():
                self.window().setWindowTitle(f"Cassette | FPS: {real_fps:.2f}")
            
            self._frame_count = 0
            self._fps_timer.restart()
    
    def get_playhead_position_px(self):
        return self.playhead.pos().x()
    
    def set_playhead_position_px(self, x):
        self.playhead.setPos(min(x, self.total_content_width), 0)
        self.main_window_ref.mini_preview_widget.set_playhead_position(x / self.total_content_width) 
    
    def get_playhead_position_ms(self):
        x_pos = self.playhead.pos().x()
        pos_ms = (x_pos / self.px_per_sec) * 1000.0
        
        return pos_ms
    
    def set_playhead_position_ms(self, ms):
        x_pos = (ms / 1000.0) * self.px_per_sec
        self.set_playhead_position_px(x_pos)
    
    def _on_playback_state_changed(self, is_playing):
        if is_playing:
            self._start_playback()

            h_bar = self.horizontalScrollBar()
            playhead_x = self.get_playhead_position_px()
            viewport_width = self.viewport().width()

            if playhead_x < h_bar.value() or playhead_x > (h_bar.value() + viewport_width):
                self._is_auto_scroll_active = True
                self._sync_scroll_to_playhead()
            
            else:
                self._is_auto_scroll_active = False
        
        else:
            self._stop_playback()
            self._on_playback_position_updated()

    def _on_playback_position_updated(self):
        pos_ms = self.playback_manager.get_position_ms()
        true_x_pos = (pos_ms / 1000.0) * self.px_per_sec
        self.set_playhead_position_px(int(true_x_pos))

        h_bar = self.horizontalScrollBar()
        viewport_width = self.viewport().width()

        offset_ratio = CurrentSettings["playhead_position"]
        target_visual_offset = int(viewport_width * offset_ratio)
        target_scroll = int(true_x_pos) - target_visual_offset

        if not self._is_auto_scroll_active:
            if true_x_pos < (h_bar.value() + target_visual_offset):
                return
            
            self._is_auto_scroll_active = True

        if self._is_auto_scroll_active:
            h_bar.setValue(target_scroll)

    def _sync_scroll_to_playhead(self):
        viewport_width = self.viewport().width()
        target_visual_offset = int(viewport_width * 0.2)
        target_scroll = int(self.get_playhead_position_px()) - target_visual_offset
        
        self.horizontalScrollBar().setValue(target_scroll)

    def scroll_to_normalized_position(self, normalized_pos):
        if self.playback_manager.is_playing:
            self.playback_manager.toggle_playback()

        h_bar = self.horizontalScrollBar()
        h_bar.setValue(int(normalized_pos * self.total_content_width - self.width() / 2))
        
        self.set_playhead_position_px(normalized_pos * self.total_content_width)
    
    def load_composition(self, composition):
        self.prepare_audio()
        self.playback_manager.playback_state_changed.connect(self._on_playback_state_changed)

        self.composition = composition
        self.composition.syncer.error_occurred.connect(self.show_error_dialog)

        self.track_names = [f"{i + 1}" for i in range(composition.track_number)]

        self.wheel_controller    = WheelController(self)
        self.glyph_controller    = GlyphController(self, self.composition)
        self.mouse_controller    = InteractionHandler(self, self.playback_manager, self.composition)
        self.keyboard_controller = KeyboardController(self, self.playback_manager)
        
        self.horizontalScrollBar().valueChanged.connect(self.mouse_controller._force_mouse_update)
        
        self.glyph_visualizer = UI.GlyphVisualizer(
            self.composition.model,
            self.playback_manager,
            self.composition.bpm
        )
        self.glyph_visualizer.setParent(None)
        
        self.glyph_controller.elements_changed.connect(self.main_window_ref.on_elements_changed)
        
        for id, glyph in self.composition.glyphs.items():
            self.glyph_controller._create_glyph_item(id, glyph, True, False, False)
        
        self.marquee_item.set_bpm(self.composition.bpm)
        
        self.update_scene_rect()
        self.update()
        
        self.glyph_visualizer.show()
    
    def unload_composition(self):
        logger.warning("Unloading composition and clearing state")
        
        self.glyph_controller.clear_glyphs()

        if self.composition:
            self.composition.syncer.stop_scanning_loop()
            self.composition.syncer.error_occurred.disconnect(self.show_error_dialog)
            self.composition = None
        
        self.playback_manager.playback_state_changed.disconnect()
        
        logger.warning("Syncer stoppped")
        
        self.set_playhead_position_px(0)
        self.horizontalScrollBar().setValue(0)

        self.glyph_controller.cleanup_tooltip()
        self.glyph_visualizer.exit()
        
        self.glyph_controller.elements_changed.disconnect()
        self.horizontalScrollBar().valueChanged.disconnect(self.mouse_controller._force_mouse_update)
        
        # Clean up keyboard shortcuts before removing the controller reference
        if self.keyboard_controller:
            try:
                self.keyboard_controller.cleanup_shortcuts()
            except Exception:
                pass

        self.glyph_controller = None
        self.wheel_controller = None
        self.mouse_controller = None
        self.keyboard_controller = None
        
        self.waveform_tiles = {}
        
        logger.warning("Controllers cleared")
        logger.warning("Caches and state cleared")
    
    def _draw_waveform(self, painter, rect):
        if self.playback_manager.data is not None and len(self.playback_manager.data) > 0:
            start_tile_index = int(rect.left() // self.tile_width)
            end_tile_index = int(rect.right() // self.tile_width)

            for i in range(start_tile_index, end_tile_index + 1):
                tile = self.waveform_tiles.get(i)
                
                if not tile:
                    tile = self.generate_tile(i)
                
                if tile:
                    draw_pos_x = i * self.tile_width
                    if draw_pos_x <= rect.right() and draw_pos_x + self.tile_width >= rect.left():
                        painter.drawPixmap(draw_pos_x, Styles.Metrics.Tracks.ruler_height, tile)
    
    def _draw_ruler(self, painter, rect):
        painter.setFont(self._ruler_font)
        painter.setPen(QPen(QColor(255, 255, 255), 0.5))

        start_second = int(rect.left() / self.px_per_sec)
        end_second   = int(rect.right() / self.px_per_sec)

        for i in range(start_second, end_second + 1):
            x_pos = i * self.px_per_sec
            painter.drawLine(
                QPointF(x_pos, 0),
                QPointF(x_pos, 8)
            )
            
            painter.drawText(
                QPointF(x_pos + 5, Styles.Metrics.Tracks.ruler_height - 10),
                str(i)
            )
    
    def _draw_beat_lines(self, painter, rect):
        beat_times = self.composition.beats
        if not beat_times:
            return
        
        painter.setPen(
            QPen(
                QColor(Styles.Colors.Waveline.beat_color),
                1,
                Qt.PenStyle.DotLine
            )
        )
            
        lines = []
        line_height = Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.ruler_height
    
        for beat_time_sec in beat_times:
            x_pos = beat_time_sec * self.px_per_sec

            if 0 <= x_pos <= rect.x() + rect.width():
                lines.append(
                    QLineF(
                        QPointF(x_pos, 0), 
                        QPointF(x_pos, line_height)
                    )
                )

        if lines:
            painter.drawLines(lines)
    
    def _draw_track_grid(self, painter, rect):
        if rect.left() > Styles.Metrics.Tracks.box_height:
            return
        
        painter.setFont(self._track_label_font)
        painter.setPen(
            QColor(Styles.Colors.Waveline.track_name_color)
        )
        
        y = Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.box_spacing

        for track_name in self.track_names:
            track_content_top_y = y + (Styles.Metrics.Tracks.row_height - Styles.Metrics.Tracks.box_height) / 2.0
            track_content_bottom_y = track_content_top_y + Styles.Metrics.Tracks.box_height

            if track_content_bottom_y < rect.top() or track_content_top_y > rect.bottom():
                continue
            
            label_rect = QRectF(
                Styles.Metrics.Tracks.box_spacing,
                track_content_top_y,
                Styles.Metrics.Tracks.label_width - 2 * Styles.Metrics.Tracks.box_spacing,
                Styles.Metrics.Tracks.box_height,
            )
                
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, track_name)
            y += Styles.Metrics.Tracks.row_height + Styles.Metrics.Tracks.box_spacing
    
    def drawBackground(self, painter, rect):
        painter.fillRect(self.sceneRect(), QColor(0, 0, 0))
        
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        self._draw_waveform(painter, rect)
        self._draw_beat_lines(painter, rect)
        self._draw_ruler(painter, rect)
        self._draw_track_grid(painter, rect)
    
    def init_composition(self, composition):
        self.composition = composition

    def _stop_playback(self):
        self.playhead_timer.stop()
        self.glyph_visualizer.stop_all()
        
        if self.composition:
            self.composition.syncer.stop()
    
    def _start_playback(self):
        self.playhead_timer.start()
        
        position = self.get_playhead_ms()
        
        self.glyph_visualizer.set_schedule(self.composition.glyphs.visualizator_data)
        self.glyph_visualizer.play_all(position)
        
        self.composition.syncer.play(position)

    def change_brightness(self, brightness):
        self.composition.set_brightness(brightness)
    
    def change_duration(self, duration):
        self.composition.set_duration(duration)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scale_view(0)
        self.update_scene_rect()

    def update_scene_rect(self):
        audio_duration_sec = self.playback_manager.duration_ms / 1000
        width = audio_duration_sec * self.px_per_sec

        top_margin = Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height
        row_height = Styles.Metrics.Tracks.row_height + Styles.Metrics.Tracks.box_spacing
        
        total_height = top_margin + (len(self.track_names) * row_height) + 100 
        total_height = max(total_height, self.viewport().height())

        self.setSceneRect(0, 0, width, total_height)
        self.total_content_width = width

    def prepare_audio(self):
        self.update()

        self.global_waveform_max = np.max(
            np.abs(
                self.playback_manager.data.astype(np.float32)
            )
        )

    def scale_view(self, delta, force_update=False):
        current_ms = self.get_playhead_position_ms()

        duration_sec = max(self.playback_manager.duration_ms / 1000.0, 0.001)
        fit_px_per_sec = self.viewport().width() / duration_sec

        min_px_per_sec = max(fit_px_per_sec, 20.0)
        new_px_per_sec = max(min_px_per_sec, self.px_per_sec + delta)

        if self.px_per_sec == new_px_per_sec and not force_update:
            return

        self.px_per_sec = new_px_per_sec
        self.waveform_tiles.clear()
        
        self.glyph_controller.update_glyphs()

        self.set_playhead_position_ms(current_ms)
        self.update_scene_rect()
        self.update()

    def on_scale_plus(self):
        self.scale_view(+100)

    def on_scale_minus(self):
        self.scale_view(-100)
    
    def generate_tile(self, tile_index):
        logger.warning(f"Tile {tile_index} is being created...")
        start = time.time()

        data = self.playback_manager.data
        total_px = self.total_content_width
        spp_overall = len(data) / float(total_px)

        start_px = tile_index * self.tile_width
        start_sample = int(start_px * spp_overall)
        end_sample = min(len(data), int((start_px + self.tile_width) * spp_overall))

        chunk = data[start_sample:end_sample]
        min_s = np.min(chunk, axis=1)
        max_s = np.max(chunk, axis=1)

        n = len(min_s)
        if n == 0:
            return None

        step = int(np.ceil(n / float(self.tile_width))) if self.tile_width > 0 else n
        step = max(1, step)

        idx = np.arange(0, n, step)
        min_vals = np.minimum.reduceat(min_s, idx)
        max_vals = np.maximum.reduceat(max_s, idx)

        max_f = max_vals.astype(np.float32) / self.global_waveform_max
        min_f = min_vals.astype(np.float32) / self.global_waveform_max

        height = int(Styles.Metrics.Waveform.height)
        yc = height / 2.0

        top = yc - max_f * yc
        bottom = yc - min_f * yc

        sigma = CurrentSettings["waveform_smoothing"]
        if sigma and sigma > 0.0 and len(top) > 1:
            pad_sz = min(int(np.ceil(sigma * 3.0)), len(top) - 1)
            top_p = np.pad(top, (pad_sz, pad_sz), mode='reflect')
            bottom_p = np.pad(bottom, (pad_sz, pad_sz), mode='reflect')
            top = Utils.gaussian_filter1d_np(top_p, sigma=sigma)[pad_sz:pad_sz + len(top)]
            bottom = Utils.gaussian_filter1d_np(bottom_p, sigma=sigma)[pad_sz:pad_sz + len(bottom)]

        if len(top) == len(bottom):
            mask = top > bottom
            if mask.any():
                avg = (top + bottom) / 2.0
                top[mask] = avg[mask]
                bottom[mask] = avg[mask]

        pixmap = QPixmap(self.tile_width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        if CurrentSettings["antialiasing"]:
            painter.setRenderHint(QPainter.Antialiasing)

        count = len(top)
        if count == 0:
            painter.end()
            return None

        bar_w = float(self.tile_width) / count
        xs = (np.arange(count) * bar_w).astype(np.float32)
        ys_top = np.clip(top.astype(np.float32), 0.0, float(height))
        ys_bottom = np.clip(bottom.astype(np.float32), 0.0, float(height))

        pts = []

        for x, y in zip(xs, ys_top):
            pts.append(QPointF(float(x), float(y)))
        
        for x, y in zip(xs[::-1], ys_bottom[::-1]):
            pts.append(QPointF(float(x), float(y)))

        poly = QPolygonF(pts)
        path = QPainterPath()
        path.addPolygon(poly)
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

    def control_popup(self, title, label, key, min_val = 1, max_val = None):
        dialog = UI.DialogInputWindow(title, label, min_val, max_val, bpm = self.composition.bpm, player = self.playback_manager)
        if not dialog.exec_():
            return

        user_input = dialog.result_text
        updated = {}
        
        selected_items = self.scene.selectedItems()
        
        for item in selected_items:
            element_id = item.glyph_id
            glyph = self.composition.get_glyph(element_id)
            glyph_copy = copy.deepcopy(glyph)
            
            glyph_copy[key] = user_input
            updated[element_id] = glyph_copy
            
            item.update_geometry(duration_ms = glyph_copy["duration"])
        
        self.composition.update_bunch_of_glyphs(updated)

    def brightness_control_popup(self):
        self.control_popup("Brightness", "Percent", "brightness", max_val = 100)

    def duration_control_popup(self):
        self.control_popup("Duration", "Duration (ms)", "duration", min_val = 1, max_val = 10000)
    
    def wheelEvent(self, event):
        self.wheel_controller.process_wheel_event(event)
        
    def mousePressEvent(self, event):
        self.mouse_controller.process_mouse_press_event(event)
        super().mousePressEvent(event)
    
    def segment_control_popup(self):
        selected_items = self.scene.selectedItems()

        first_item = selected_items[0]
        first_id = first_item.glyph_id
        first_glyph = self.composition.get_glyph(first_id)

        popup = UI.SegmentEditor(
            "Segments",
            self.composition.bpm,
            self.playback_manager,
            get_segments(self.composition.model, first_glyph["track"]),
            first_glyph.get("segments"),
        )

        if not popup.exec_():
            return

        segments = popup.saved_segments
        turned_on = [i for i, s in enumerate(segments) if s]
        all_turned_on = all(segments)

        updated_glyphs = {}

        for item in selected_items:
            element_id = item.glyph_id
            glyph = self.composition.get_glyph(element_id)
            
            if all_turned_on:
                glyph.pop("segments", None)
            
            else:
                glyph["segments"] = turned_on
            
            updated_glyphs[element_id] = glyph

        effect_name = first_glyph.get("effect", {}).get("name")
        effect_config = GlyphEffects.EffectsConfig.get(effect_name, {})
        
        if not effect_name:
            return self.composition.update_bunch_of_glyphs(updated_glyphs)
        
        if not effect_config["supports_segmentation"]:
            UI.ErrorWindow(
                "Effect has been reset",
                "Heads up: custom segmentation doesn't work with applied effect, so we reset the effect."
            ).exec_()

            for item in selected_items:
                element_id = item.glyph_id
                
                if element_id in updated_glyphs:
                    updated_glyphs[element_id].pop("effect", None)
                
                else:
                    glyph = self.composition.get_glyph(element_id)
                    glyph.pop("effect", None)
                    updated_glyphs[element_id] = glyph

        self.composition.update_bunch_of_glyphs(updated_glyphs)

    def contextMenuEvent(self, event: QContextMenuEvent):
        try:
            view_pos = event.pos()
            scene_pos = self.mapToScene(view_pos)
            item_under_mouse = self.scene.itemAt(scene_pos, self.transform())
            
            if not item_under_mouse:
                return

            if item_under_mouse not in self.glyph_controller.glyph_items:
                return
            
            if not item_under_mouse.isSelected():
                self.scene.clearSelection()
                item_under_mouse.setSelected(True)

            selected_items = self.scene.selectedItems()

            if not selected_items:
                return

            selected_element_ids = [item.glyph_id for item in selected_items]
            
            target_id = item_under_mouse.glyph_id
            clicked_element = self.composition.get_glyph(target_id)

            Utils.ui_sound("MenuOpen")
            self.update()

            def on_apply_requested_factory(name, settings):
                for sel_id in selected_element_ids:
                    element = self.composition.get_glyph(sel_id)
                    if element:
                        result = GlyphEffects.effectCallback(name, settings, element)
                        self.composition.replace_glyph(sel_id, result)

            has_non_segmented = [
                not is_segmented(self.composition.get_glyph(sel_id)["track"], self.composition.model)
                for sel_id in selected_element_ids
            ]
            
            has_segmented = [
                is_segmented(self.composition.get_glyph(sel_id)["track"], self.composition.model)
                for sel_id in selected_element_ids
            ]
            
            can_show_segment_editor = (len(has_segmented) == 1 and all(has_segmented))

            has_segments = any(
                GlyphEffects.is_segment_edited(self.composition.get_glyph(sel_id))
                for sel_id in selected_element_ids
            )

            if any(has_non_segmented):
                effects = GlyphEffects.only_non_segmented()
            
            elif has_segments:
                effects = GlyphEffects.only_segmentation_supported()
            
            else:
                effects = GlyphEffects.all()

            effect_entries = []
            for effect_name, config in effects.items():
                preview_widget = UI.EffectPreviewWidget(effect_name, config, clicked_element)
                preview_widget.apply_requested.connect(
                    lambda name = effect_name, s =
                    config: on_apply_requested_factory(name, s)
                )
                
                effect_entries.append((effect_name, [("preview_widget", preview_widget)]))

            entries = [
                ("Delete", self.glyph_controller.delete_glyphs),
                ("Copy", lambda: self.glyph_controller.copy_glyphs), 
                ("Paste", self.glyph_controller.paste_glyphs),
                ("Cut", self.glyph_controller.cut_glyphs),
                ("-", None),
                ("Change Brightness...", lambda: QTimer.singleShot(0, self.brightness_control_popup)),
                ("Change Duration...", lambda: QTimer.singleShot(0, self.duration_control_popup)),
                ("-", None),
                ("Effect", effect_entries)
            ]

            if can_show_segment_editor:
                entries.append(("Segments...", lambda: QTimer.singleShot(0, self.segment_control_popup)))

            menu = UI.ContextMenu(entries)
            menu.aboutToHide.connect(lambda: Utils.ui_sound("MenuClose"))
            
            menu.exec_and_cleanup(event.globalPos())

        except Exception as e:
            logger.error(f"Context menu error: {e}")
            logger.error(traceback.format_exc())
            
            UI.ErrorWindow(
                "Context Menu Error",
                "An unexpected error occurred while opening the context menu."
            ).exec_()

    def show_error_dialog(self, title, message):
        error_dialog = UI.ErrorWindow(title, message, "Oh nah", self.composition.bpm, self.playback_manager)
        error_dialog.exec_()

    def get_playhead_ms(self):
        return self.playhead.pos().x() / self.px_per_sec * 1000

    def _tutorial_shown_callback(self):
        settings = QSettings("chips047", "Cassette")
        settings.setValue("tutorial_shown", True)
        settings.sync()
        load_settings()

    def check_tutorial(self):
        if not CurrentSettings.get("tutorial_shown"):
            if not self.composition.full_song_path:
                return

            self.tutorial_window = UI.Tutorial(
                self.composition.bpm,
                self.composition.full_song_path
            )
            
            self._tutorial_shown_callback()
            QTimer.singleShot(0, self.tutorial_window.exec_)
    
    def mouseMoveEvent(self, event):
        self.mouse_controller.process_mouse_move_event(event)
        return super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self.mouse_controller.process_mouse_release_event(event)
        return super().mouseReleaseEvent(event)
    
    def leaveEvent(self, event):
        self.mouse_controller.process_mouse_leave_event(event)
        return super().leaveEvent(event)

class CompositorWidget(QWidget):
    back_to_main_menu_requested = pyqtSignal()
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet("background-color: #1e1e1e;")
        
        self.playback_manager = Player.player

        # UI Initialization
        self.overall_layout = QVBoxLayout(self)
        self.overall_layout.setContentsMargins(10, 10, 10, 10)
        self.overall_layout.setSpacing(10)

        self.top_control_bar_widget = QWidget()
        self.top_control_bar_layout = QHBoxLayout(self.top_control_bar_widget)
        self.top_control_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.top_control_bar_layout.setSpacing(10)
        
        self.eject_button =        UI.Button("Eject")
        self.export_button =       UI.NothingButton("Export")
        self.top_status_label =    QLabel(STATUS_BAR_DEFAULT)
        self.mini_preview_widget = UI.MiniWaveformPreview()
        self.glyph_dur_control =   UI.DraggableValueControl(QIcon("System/Icons/Duration.png"), "duration", 100, 5, 5000, 5, "ms")
        self.brightness_control =  UI.DraggableValueControl(QIcon("System/Icons/Brightness.png"), "brightness", 100, 5, 100, 5, "%")
        self.playspeed_button =    UI.CycleButton(QIcon("System/Icons/Speed.png"), "speed", [("1x", 1.0), ("0.5x", 0.5), ("0.2x", 0.2)])
        self.default_effect =      UI.CycleButton(QIcon("System/Icons/Effect.png"), "effect", [("None", "None"), ("Fade out", "Fade out"), ("Fade in", "Fade in"), ("Fade in out", "Fade in + out")])
        
        # Other Settings
        self.top_status_label.setFont(Utils.NDot(14))
        self.top_status_label.setMinimumHeight(Styles.Metrics.element_height)
        self.top_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.top_status_label.setStyleSheet(Styles.Other.status_bar)

        # Connections
        self.export_button.clicked.connect(self.export_ringtone)
        self.eject_button.clicked.connect(self.unload_composition)
        self.playspeed_button.state_changed.connect(self.on_playspeed_changed)
        self.default_effect.state_changed.connect(self.on_default_effect_change)
        self.mini_preview_widget.preview_clicked.connect(self.on_mini_preview_clicked)

        # Layout Setup
        self.top_control_bar_layout.addWidget(self.eject_button)
        self.top_control_bar_layout.addWidget(self.mini_preview_widget, 1)
        self.top_control_bar_layout.addWidget(self.glyph_dur_control)
        self.top_control_bar_layout.addWidget(self.brightness_control)
        self.top_control_bar_layout.addWidget(self.playspeed_button)
        self.top_control_bar_layout.addWidget(self.default_effect)
        self.top_control_bar_layout.addWidget(self.export_button)

        self.overall_layout.addWidget(self.top_control_bar_widget)
        self.overall_layout.addWidget(self.top_status_label)
        
        # Core Components, pre - init
        self.content_widget = ScrollableContent(self)

        self.overall_layout.addWidget(self.content_widget)

        # Focus Fix
        for child in self.findChildren(QWidget):
            if child is not self.content_widget:
                child.setFocusPolicy(Qt.NoFocus)

        self.content_widget.setFocusPolicy(Qt.StrongFocus)
        self.glyph_dur_control.valueChanged.connect(self.set_default_glyph_duration)
        self.brightness_control.valueChanged.connect(self.set_default_brightness)
    
    def set_default_glyph_duration(self, duration_ms):
        self.content_widget.composition.set_duration(duration_ms)
    
    def set_default_brightness(self, brightness):
        self.content_widget.composition.set_brightness(brightness)
    
    def unload_composition(self):
        logger.warning("Unloading composition from compositor widget and clearing state")
        
        self.back_to_main_menu_requested.emit()
        if self.playback_manager.is_playing:
            logger.warning("Stopping playback manager, taping")
            self.content_widget.playhead_timer.stop()
            self.playback_manager.tape(end_speed = 0.0, duration = 1.5)

        logger.warning("Stopping syncer")
        self.content_widget.composition.syncer.stop()

        self.mini_preview_widget.audio_data = None

        self.default_effect.reset()
        self.playspeed_button.reset()
        self.glyph_dur_control.reset()
        self.brightness_control.reset()
    
    def load_composition(self, composition):
        self.playback_manager.cleanup()
        self.playback_manager.load_audio(composition.cropped_song_path)
        self.content_widget.load_composition(composition)

        self.mini_preview_widget.set_audio_data(self.playback_manager.data)
        
        self.on_elements_changed()
        self.window().activateWindow()

    def export_ringtone(self):
        UI.ExportDialogWindow(
            "Export?",
            self.content_widget.composition,
            self.content_widget.composition.bpm,
            self.playback_manager
        ).exec_()

    def on_mini_preview_clicked(self, normalized_pos):
        self.content_widget.scroll_to_normalized_position(normalized_pos)

    def on_playspeed_changed(self, text_part, speed_value):
        self.playback_manager.set_speed(speed_value, duration = 2.0, steps = 200)

    def on_default_effect_change(self, text_part, effect_value):
        self.content_widget.composition.set_default_effect(effect_value)
    
    def on_elements_changed(self):
        items = self.content_widget.glyph_controller.glyph_items
        self.export_button.setEnabled(len(items) > 0)