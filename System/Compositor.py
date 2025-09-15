import time
import random
import collections

import numpy as np

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System import Player as Player
from System import Styles
from System import ProjectSaver
from System import GlyphEffects

from System.Constants import *
from loguru import logger

from System import UI
from System import Utils

class DataManager(QObject):
    elements_changed = pyqtSignal()

    def __init__(self, conductor, composition):
        super().__init__()

        self.composition = composition
        self.conductor = conductor

        self.selected_element_ids = set()
        self.copied_elements = []
    
    def delete_selected_elements(self):
        if not self.selected_element_ids:
            return
        
        ids_to_delete = list(self.selected_element_ids)
        self.composition.delete_glyphs(ids_to_delete)

        logger.info(f"Deleted glyphs with ids: {ids_to_delete}")
        
        self.selected_element_ids.clear()
        self.elements_changed.emit()
    
    def copy_selected_elements(self):
        self.copied_elements = []

        for el_id in self.selected_element_ids:
            el = self.composition.get_glyph(el_id)

            logger.info(f"Copied: {el_id}")
            
            if el:
                self.copied_elements.append(el.copy())

    def paste_elements(self):
        if not self.copied_elements:
            return
        
        min_start = min(el['start'] for el in self.copied_elements)
        paste_start = self.conductor.playhead_x_position * self.conductor.ms_per_pixel
        offset = paste_start - min_start
    
        new_ids = []
        for el in self.copied_elements:
            new_ids.append(self.composition.copy_glyph(el, offset))
            logger.info(f"Pasting glyphs: {new_ids}")
        
        self.selected_element_ids = set(new_ids)
        self.elements_changed.emit()

class KeyboardController:
    def __init__(self, conductor, playback_manager, composition, glyph_manager):
        self.conductor = conductor
        self.playback_manager = playback_manager
        self.composition = composition
        self.glyph_manager = glyph_manager

        self.playhead_move_increment = CurrentSettings["arrow_increment"]

        logger.info("Keyboard Controller initialized")
    
    def _handle_copy_paste(self, event) -> bool:
        if event.matches(QKeySequence.Copy):
            self.glyph_manager.copy_selected_elements()
            event.accept()
            return True

        if event.matches(QKeySequence.Paste):
            self.glyph_manager.paste_elements()
            event.accept()

            return True

        return False

    def _handle_playhead_movement_and_playback(self, event, new_playhead_x):
        if event.key() == Qt.Key.Key_Space:
            self.playback_manager.toggle_playback(self.conductor.get_playhead_ms())
            return new_playhead_x

        if event.key() == Qt.Key.Key_Left:
            if not getattr(self.playback_manager, "_is_playing", False):
                new_playhead_x -= self.playhead_move_increment

        elif event.key() == Qt.Key.Key_Right:
            if not getattr(self.playback_manager, "_is_playing", False):
                new_playhead_x += self.playhead_move_increment

        return new_playhead_x

    def _handle_digit_shortcuts(self, event):
        txt = event.text()
        if not (txt.isdigit() or txt == '-'):
            return

        digit_char = txt
        target_track_index = -1

        if digit_char.isdigit():
            digit_val = int(digit_char)

            if 1 <= digit_val <= 9:
                target_track_index = digit_val - 1
            elif digit_val == 0:
                target_track_index = min(9, len(self.conductor.track_names))

        elif digit_char == '-':
            target_track_index = 10

        if not (0 <= target_track_index < len(self.conductor.track_names)):
            return

        el_x_start_px = self.conductor.playhead_x_position
        el_x_start = el_x_start_px * self.conductor.ms_per_pixel

        duration = self.composition.duration_ms

        if self.playback_manager.is_playing:
            el_x_start -= 120
        
        el_x_start = max(el_x_start, 0)

        max_ms = self.conductor.total_content_width * self.conductor.ms_per_pixel
        if el_x_start + duration > max_ms:
            duration = max(1, int(max_ms - el_x_start))

        if duration >= 1:
            track_name_to_use = self.conductor.track_names[target_track_index]

            id, _ = self.composition.new_glyph(
                track_name_to_use,
                int(el_x_start),
                duration
            )

            self.glyph_manager.selected_element_ids.clear()
            self.glyph_manager.selected_element_ids.add(id)
            self.glyph_manager.elements_changed.emit()
    
    def _finalize_playhead_update(self, new_playhead_x):
        self.conductor.playhead_x_position = max(0.0, min(new_playhead_x, self.conductor.total_content_width))
        self.conductor.update()
        self.conductor.ensure_playhead_visible()

    def process_key_event(self, event):
        new_playhead_x = self.conductor.playhead_x_position

        if self._handle_copy_paste(event):
            return

        new_playhead_x = self._handle_playhead_movement_and_playback(event, new_playhead_x)

        self._handle_digit_shortcuts(event)

        if event.key() != Qt.Key.Key_Space:
            self._finalize_playhead_update(new_playhead_x)

        event.accept()

class WheelController:
    def __init__(self, conductor):
        self.conductor = conductor

        self._scroll_velocity = 0
        self._scroll_target_velocity = 0

        # Timers
        self._scroll_timer = QTimer(conductor)
        self._scroll_timer.timeout.connect(self._update_smooth_scroll)
        self._scroll_timer.setInterval(FPS_120)

        logger.info("Mouse Wheel Controller initialized")
    
    def process_wheel_event(self, event):
        delta = event.angleDelta().y()

        if event.modifiers() & Qt.ControlModifier:
            self.conductor.scale_view(+10 if delta > 0 else -10)
            event.accept()

        elif event.modifiers() & Qt.ShiftModifier:
            scroll_area = self.conductor.parentWidget().parentWidget()

            if isinstance(scroll_area, QScrollArea):
                v_bar = scroll_area.verticalScrollBar()
                v_bar.setValue(v_bar.value() - delta)
            
            event.accept()

        else:
            self._scroll_target_velocity += -delta * 0.2

            if not self._scroll_timer.isActive():
                self._scroll_timer.start()

            event.accept()

    def _update_smooth_scroll(self):
        scroll_area = self.conductor.parentWidget().parentWidget()
        h_bar = scroll_area.horizontalScrollBar()

        self._scroll_velocity += (self._scroll_target_velocity - self._scroll_velocity) * 0.2
        h_bar.setValue(int(h_bar.value() + self._scroll_velocity))

        self._scroll_target_velocity *= 0.9

        if abs(self._scroll_velocity) < 0.1 and abs(self._scroll_target_velocity) < 0.1:
            self._scroll_timer.stop()
            self._scroll_velocity = 0
            self._scroll_target_velocity = 0

class InteractionHandler:
    def __init__(self, conductor, playback_manager, composition, glyph_manager):
        self.conductor = conductor
        self.playback_manager = playback_manager
        self.composition = composition
        self.glyph_manager = glyph_manager

        # State
        self._mouse_pressed = False
        self.dragging_element_info = None
        self.updated_elements = {}
        self.active_popup = None
        self.is_marquee_selecting = False
        self.marquee_start_pos = None
        self.marquee_rect = QRectF()

        # Edge Scroll
        self._edge_scroll_timer = QTimer(conductor)
        self._edge_scroll_timer.timeout.connect(self._update_edge_scroll)
        self._edge_scroll_timer.setInterval(FPS_120)
        self._edge_scroll_velocity = 0
        self._edge_scroll_target_velocity = 0
        self._last_mouse_pos = None
        self._is_deceleration_mode = False
        self._accumulated_scroll = 0

        self._edge_sound_active = False
        self._rewind_sound_accumulator = 0.0
        self._edge_scroll_max_speed = 15.0
        self._rewind_min_hz = 12.0
        self._rewind_max_hz = 25.0

        self._tone_smoothed = 1.0           # текущее сглаженное значение тона
        self._tone_smoothing_alpha = 0.15   # 0..1 — больше = быстрее реагирует (0.15 = довольно плавно)
        self._tone_base = 0.8               # базовый тон
        self._tone_slope = 0.4              # коэффициент влияния нормализованной скорости
        self._tone_min = 0.6                # минимальный допустимый тон
        self._tone_max = 1.2                # максимальный допустимый тон
        self._tone_jitter = 0.02

        logger.info("Mouse Controller initialized")

    def process_mouse_press_event(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        self._mouse_pressed = True
        eid, clicked_element, edge = self.conductor.get_element_at(event.pos())
        is_ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if self.conductor.rect().contains(event.pos()):
            self.conductor.setFocus()

        if clicked_element:
            self._handle_element_press(eid, clicked_element, edge, event, is_ctrl)
            self.conductor.update()
            event.accept()
            return

        ruler_or_waveform_rect = QRectF(
            0, 0, self.conductor.width(),
            Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height
        )

        if ruler_or_waveform_rect.contains(event.pos()):
            self._handle_ruler_press(event)
            event.accept()
            return

        self._start_marquee(event, is_ctrl)
        self.conductor.update()
        self.conductor.tooltip_manager.clear_tooltip()
        event.accept()

    def process_mouse_release_event(self, event: QMouseEvent):
        self._mouse_pressed = False

        if self._edge_scroll_timer.isActive():
            self._is_deceleration_mode = True
            self._edge_scroll_target_velocity = 0

            if self._edge_sound_active:
                Utils.ui_sound('EndRewind')

                self._edge_sound_active = False
                self._rewind_sound_accumulator = 0.0

        if event.button() != Qt.MouseButton.LeftButton:
            event.accept()
            return

        if self.updated_elements:
            self.composition.update_bunch_of_glyphs(self.updated_elements)
            self.updated_elements = {}

        if self.dragging_element_info:
            self._finalize_drag()
        
        elif self.is_marquee_selecting:
            self._finalize_marquee()

        event.accept()

    def _check_edge_scroll(self, mouse_pos):
        if self._is_deceleration_mode:
            return
            
        scroll_area = self.conductor.parentWidget().parentWidget()
        if not isinstance(scroll_area, QScrollArea):
            return
        
        viewport = scroll_area.viewport()
        viewport_rect = viewport.rect()
        local_pos = viewport.mapFromGlobal(self.conductor.mapToGlobal(mouse_pos))
        
        edge_zone = 60
        max_speed = 15
        
        if local_pos.x() < edge_zone:
            distance_from_edge = edge_zone - local_pos.x()
            intensity = min(1.0, distance_from_edge / edge_zone)
            self._edge_scroll_target_velocity = -max_speed * (intensity ** 1.5)
            
        elif local_pos.x() > viewport_rect.width() - edge_zone:
            distance_from_edge = local_pos.x() - (viewport_rect.width() - edge_zone)
            intensity = min(1.0, distance_from_edge / edge_zone)
            self._edge_scroll_target_velocity = max_speed * (intensity ** 1.5)
            
        else:
            self._edge_scroll_target_velocity = 0
        
        if abs(self._edge_scroll_target_velocity) >= 1 and not self._edge_scroll_timer.isActive():
            self._edge_scroll_timer.start()

            if not self._edge_sound_active:
                self._edge_sound_active = True
                Utils.ui_sound('StartRewind')
                self._rewind_sound_accumulator = 0.0

    def _compute_tone_from_velocity(self, velocity):
        if self._edge_scroll_max_speed == 0:
            norm = 0.0
        else:
            norm = velocity / self._edge_scroll_max_speed
        
        target = self._tone_base + self._tone_slope * norm
        target = max(self._tone_min, min(self._tone_max, target))

        self._tone_smoothed += (target - self._tone_smoothed) * self._tone_smoothing_alpha

        jitter = random.uniform(-self._tone_jitter, self._tone_jitter)
        final = self._tone_smoothed + jitter

        final = max(self._tone_min, min(self._tone_max, final))

        if velocity < 0:
            final += 0.2

        return final

    def _update_edge_scroll(self):
        scroll_area = self.conductor.parentWidget().parentWidget()
        if not isinstance(scroll_area, QScrollArea):
            self._edge_scroll_timer.stop()
            return
        
        h_bar = scroll_area.horizontalScrollBar()
        
        if self._is_deceleration_mode:
            smoothing = 0.08
        else:
            smoothing = 0.15
            
        self._edge_scroll_velocity += (self._edge_scroll_target_velocity - self._edge_scroll_velocity) * smoothing
        dt = float(self._edge_scroll_timer.interval()) / 1000.0

        actual_scroll_delta = 0

        if abs(self._edge_scroll_velocity) >= 1:
            old_value = h_bar.value()
            new_value = old_value + self._edge_scroll_velocity

            h_bar.setValue(int(new_value))
            
            actual_scroll_delta = h_bar.value() - old_value
            
            if actual_scroll_delta != 0 and self._last_mouse_pos:
                adjusted_mouse_pos = QPoint(
                    self._last_mouse_pos.x() + actual_scroll_delta,
                    self._last_mouse_pos.y()
                )
                
                if self.dragging_element_info:
                    fake_event = QMouseEvent(
                        QEvent.MouseMove,
                        adjusted_mouse_pos,
                        Qt.NoButton,
                        Qt.LeftButton,
                        Qt.NoModifier
                    )

                    self._handle_drag_move(fake_event)
                    self._last_mouse_pos = adjusted_mouse_pos
                    
                elif self.is_marquee_selecting:
                    self._last_mouse_pos = QPoint(
                        self._last_mouse_pos.x() + actual_scroll_delta,
                        self._last_mouse_pos.y()
                    )

                    fake_event = QMouseEvent(
                        QEvent.MouseMove,
                        self._last_mouse_pos,
                        Qt.NoButton,
                        Qt.LeftButton,
                        Qt.NoModifier
                    )

                    self._update_marquee(fake_event)
                    self.conductor.update()
        
        if not CurrentSettings["disable_sounds"]:
            if abs(self._edge_scroll_velocity) >= 1 and self._edge_sound_active:
                norm = min(1.0, abs(self._edge_scroll_velocity) / max(1e-6, self._edge_scroll_max_speed))
                tone = self._compute_tone_from_velocity(self._edge_scroll_velocity)
    
                freq_hz = self._rewind_min_hz + (self._rewind_max_hz - self._rewind_min_hz) * norm
                interval = 1.0 / max(1e-6, freq_hz)
    
                self._rewind_sound_accumulator += dt
    
                if abs(actual_scroll_delta) > 0:
                    while self._rewind_sound_accumulator >= interval:
                        self._rewind_sound_accumulator -= interval
                        Utils.ui_sound('Rewind', tone)
            
            else:
                self._rewind_sound_accumulator = 0.0
        
        if abs(self._edge_scroll_velocity) < 1 and abs(self._edge_scroll_target_velocity) < 1:
            self._edge_scroll_timer.stop()
            self._edge_scroll_velocity = 0
            self._edge_scroll_target_velocity = 0
            self._is_deceleration_mode = False

            if self._edge_sound_active:
                Utils.ui_sound('EndRewind')
                self._edge_sound_active = False
                self._rewind_sound_accumulator = 0.0
    
    def _stop_edge_scroll(self):
        if self._edge_scroll_timer.isActive():
            self._edge_scroll_timer.stop()

        if self._edge_sound_active:
            self._edge_sound_active = False
            self._rewind_sound_accumulator = 0.0

        self._edge_scroll_velocity = 0
        self._edge_scroll_target_velocity = 0
        self._last_mouse_pos = None

    def _finalize_drag(self):
        if not self._is_deceleration_mode:
            self._stop_edge_scroll()
        
        self.conductor.setCursor(Qt.CursorShape.ArrowCursor)
        self.glyph_manager.elements_changed.emit()
        self.dragging_element_info = None
        self.updated_elements = {}
        self.conductor.update()

    def _finalize_marquee(self):
        if not self._is_deceleration_mode:
            self._stop_edge_scroll()
        
        self._accumulated_scroll = 0
        self.is_marquee_selecting = False
        self.marquee_rect = QRectF()
        self.glyph_manager.elements_changed.emit()
        self.conductor.update()

    def process_mouse_move_event(self, event: QMouseEvent):
        self._last_mouse_pos = event.pos()
        
        if self.dragging_element_info:
            self._handle_drag_move(event)
            self._check_edge_scroll(event.pos())
            event.accept()
            return

        if self.is_marquee_selecting:
            self._update_marquee(event)
            self._check_edge_scroll(event.pos())
            self.conductor.update()
            event.accept()
            return

        self._update_tooltip_and_cursor(event)
        event.accept()

    def _handle_element_press(self, eid, clicked_element, edge, event, is_ctrl):
        if edge in ('resize_left', 'resize_right'):
            if eid not in self.glyph_manager.selected_element_ids:
                self.glyph_manager.selected_element_ids.clear()
                self.glyph_manager.selected_element_ids.add(eid)

            self.dragging_element_info = {
                'element_id': eid,
                'mode': edge,
                'start_mouse_x': event.pos().x(),
                'original_start': clicked_element['start'],
                'original_duration': clicked_element['duration'],
                'selection_orig_state': {
                    sel_eid: self.composition.get_glyph(sel_eid).copy()
                    for sel_eid in self.glyph_manager.selected_element_ids
                }
            }
            
            return self.conductor.setCursor(Qt.CursorShape.SizeHorCursor)

        if edge == 'body':
            if is_ctrl:
                if eid in self.glyph_manager.selected_element_ids:
                    self.glyph_manager.selected_element_ids.remove(eid)
                else:
                    self.glyph_manager.selected_element_ids.add(eid)
            
            else:
                if eid not in self.glyph_manager.selected_element_ids:
                    self.glyph_manager.selected_element_ids.clear()
                    self.glyph_manager.selected_element_ids.add(eid)

            self.dragging_element_info = {
                'mode': 'move',
                'start_mouse_x': event.pos().x(),
                'selection_orig_state': {
                    sel_eid: self.composition.get_glyph(sel_eid).copy()
                    for sel_eid in self.glyph_manager.selected_element_ids
                }
            }

            self.conductor.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _handle_ruler_press(self, event: QMouseEvent):
        if not self.playback_manager.is_playing:
            new_x = max(0.0, min(float(event.x()), self.conductor.total_content_width))
            if self.conductor.playhead_x_position != new_x:
                self.conductor.playhead_x_position = new_x
                self.conductor.update()
                self.conductor.ensure_playhead_visible()

    def _start_marquee(self, event: QMouseEvent, is_ctrl):
        self.is_marquee_selecting = True
        self.marquee_start_pos = event.pos()
        self.marquee_rect = QRectF(self.marquee_start_pos, self.marquee_start_pos)
        self._accumulated_scroll = 0

        if not is_ctrl:
            self.glyph_manager.selected_element_ids.clear()

    def _handle_drag_move(self, event: QMouseEvent):
        info = self.dragging_element_info
        mode = info['mode']

        current_mouse_x = event.pos().x()
        delta_x = current_mouse_x - info['start_mouse_x']
        delta_ms = delta_x * self.conductor.ms_per_pixel

        if mode == 'move':
            self._update_move(delta_ms)
        
        elif mode in ('resize_left', 'resize_right'):
            self._update_resize(mode, delta_ms)

        QTimer.singleShot(0, self.conductor.update)

    def _update_move(self, delta_ms):
        selection_state = self.dragging_element_info['selection_orig_state']
        if not selection_state:
            return
        
        main_element_id = next(iter(selection_state))
        main_element = self.composition.get_glyph(main_element_id)

        for el_id, orig_state in selection_state.items():
            element = self.composition.get_glyph(el_id)
            if not element:
                continue

            min_start = 0
            max_start = self.conductor.total_content_width * self.conductor.ms_per_pixel - element['duration']
            new_start = orig_state['start'] + delta_ms
            new_start = max(min_start, min(new_start, max_start))

            element['start'] = new_start
            self.updated_elements[el_id] = element

        self._show_value_popup(main_element, f"{main_element['start']:.0f} ms")

    def _update_resize(self, mode, delta_ms):
        main_element_id = self.dragging_element_info.get('element_id')
        if main_element_id is None:
            return

        main_element = self.composition.get_glyph(main_element_id)
        orig_main = self.dragging_element_info['selection_orig_state'][main_element_id]

        if mode == 'resize_left':
            new_start = orig_main['start'] + delta_ms
            new_duration = orig_main['duration'] - delta_ms

            if new_duration < 1:
                new_duration = 1
                new_start = main_element['start'] + main_element['duration'] - 1

            new_start = max(new_start, 0)
            actual_delta_ms = new_start - orig_main['start']

            for el_id, orig_state in self.dragging_element_info['selection_orig_state'].items():
                element = self.composition.get_glyph(el_id)
                if element and orig_state['duration'] - actual_delta_ms >= 1:
                    element['start'] = orig_state['start'] + actual_delta_ms
                    element['duration'] = orig_state['duration'] - actual_delta_ms
                self.updated_elements[el_id] = element

            self._show_value_popup(main_element, f"{main_element['duration']:.0f} ms")

        elif mode == 'resize_right':
            new_duration = orig_main['duration'] + delta_ms
            if new_duration < 1:
                new_duration = 1

            actual_delta = new_duration - orig_main['duration']

            for el_id, orig_state in self.dragging_element_info['selection_orig_state'].items():
                element = self.composition.get_glyph(el_id)
                
                if element and orig_state['start'] + orig_state['duration'] + actual_delta <= self.conductor.total_content_width * self.conductor.ms_per_pixel:
                    element['duration'] = orig_state['duration'] + actual_delta
                self.updated_elements[el_id] = element

            self._show_value_popup(main_element, f"{main_element['duration']:.0f} ms")

    def _show_value_popup(self, element, text: str):
        rect = self.conductor.get_element_rect(element)
        pos = self.conductor.mapToGlobal(
            QPointF(rect.center().x(), rect.bottom()).toPoint()
        )

        if self.active_popup:
            return self.active_popup.show_text(text, pos)

        self.active_popup = UI.ValuePopup(text, pos, self.conductor.main_window_ref)
        self.active_popup.show()
        self.active_popup.destroyed.connect(self._on_popup_destroyed)

    def _on_popup_destroyed(self):
        self.active_popup = None

    def _update_marquee(self, event: QMouseEvent):
        adjusted_start = QPointF(
            self.marquee_start_pos.x() - self._accumulated_scroll,
            self.marquee_start_pos.y()
        )
        
        self.marquee_rect = QRectF(adjusted_start, event.pos()).normalized()
        
        current_selection = set()
        for id_, element in self.composition.all_glyphs().items():
            if self.marquee_rect.intersects(self.conductor.get_element_rect(element)):
                current_selection.add(id_)
        
        self.glyph_manager.selected_element_ids = current_selection

    def _update_tooltip_and_cursor(self, event: QMouseEvent):
        eid, hovered_element, edge = self.conductor.get_element_at(event.pos())

        if hovered_element:
            if self._mouse_pressed or self.is_marquee_selecting or self.playback_manager.is_playing:
                return

            info = (
                f"Start: {hovered_element.get('start', 0):.0f} ms\n"
                f"Duration: {hovered_element.get('duration', 0):.0f} ms\n"
                f"Brightness: {hovered_element.get('brightness', 0)}\n"
                f"Effect: {hovered_element.get('effect', {}).get('name')}"
            )
            global_pos = self.conductor.mapToGlobal(event.pos())
            self.conductor.tooltip_manager.request_tooltip(hovered_element, info)
        
        else:
            self.conductor.tooltip_manager.clear_tooltip()

        if edge in ('resize_left', 'resize_right'):
            self.conductor.setCursor(Qt.CursorShape.SizeHorCursor)
        
        elif edge == 'body':
            self.conductor.setCursor(Qt.CursorShape.OpenHandCursor)
        
        else:
            self.conductor.setCursor(Qt.CursorShape.ArrowCursor)

class ScrollableContent(QWidget):
    audio_state_changed = pyqtSignal()

    def __init__(self, parent, main_window_ref, composition: ProjectSaver.Composition):
        super().__init__(parent)
        
        self.composition = composition
        self.composition.syncer.error_occurred.connect(self.show_error_dialog)

        # References
        self.main_window_ref = main_window_ref
    
        # UI Configuration
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
    
        # Scaling & Time
        self.pixels_per_major_tick = CurrentSettings["default_scaling"]
        self.start_time_sec = 0
        self.ms_per_pixel = 1000.0 / self.pixels_per_major_tick
        
        # Playhead
        self.playhead_x_position = 0
        self.current_playback_speed_multiplier = 1.0
        self.playback_start_audio_ms = 0
    
        # Playback
        self.playback_timer = QTimer(self)
    
        # Track Management
        self.track_names = [f"{i + 1}" for i in range(composition.track_number)]
        self.total_content_width = 2000

        # Tooltip
        self.tooltip_manager = UI.AnimatedTooltipManager(main_window_ref)
    
        # Caching
        self._element_rects = []
        self.tile_width = CurrentSettings["tile_width"]
        self.waveform_tiles = {}
        self.glyph_paths = {}
        
        self._ruler_cache = None
        self._ruler_cache_rect = None

        self._beats_cache = None
        self._beats_cache_rect = None
        
        self._glyph_pixmaps = {}

        self._track_label_font = Utils.NType(15)
        self._ruler_font = Utils.NType(10)

        self._white_brush = QBrush(QColor(255, 255, 255))
        self._red_pen = QPen(QColor(Styles.Colors.nothing_accent), 1.5)
        self._gray_pen = QPen(QColor(Styles.Colors.glass_border), 1)

        accent = Styles.Colors.nothing_accent.lstrip("#")
        self._marquee_pen = QPen(QColor(f"#C8{accent}"), 1, Qt.PenStyle.DashLine)
        self._marquee_brush = QBrush(QColor(f"#32{accent}"))

        # Final init
        self.update_minimum_height()
        
        self.playback_manager = Player.PlaybackManager(self)
        self.playback_manager.playback_position_updated.connect(self._on_playback_position_updated)
        self.playback_manager.audio_loaded.connect(self._on_audio_loaded_from_manager)
        self.playback_manager.playback_state_changed.connect(self._on_playback_state_changed)

        self.wheel_controller    = WheelController(self)
        self.glyph_manager       = DataManager(self, self.composition)
        self.mouse_controller    = InteractionHandler(self, self.playback_manager, self.composition, self.glyph_manager)
        self.keyboard_controller = KeyboardController(self, self.playback_manager, self.composition, self.glyph_manager)

        # FPS
        self.last_time = time.time()
        self.frame_times = collections.deque(maxlen = 30)
        self.fps = 0.0

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.on_scale_plus)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.on_scale_minus)
        QShortcut(QKeySequence(Qt.Key_Delete), self).activated.connect(self.glyph_manager.delete_selected_elements)

        logger.info("Compositor is now running")
    
    def get_opacity_for_position(self, x_pos):
        widget_width = self.get_visible_rect().width()
        fade_margin = 100

        if x_pos > widget_width:
            return 0.0

        if x_pos > widget_width - fade_margin and x_pos < widget_width:
            t = (widget_width - x_pos) / fade_margin
            return t * t

        return 1.0
    
    def get_visible_rect(self):
        scroll_area_widget = self.parentWidget()
        viewport_widget = scroll_area_widget.parentWidget() if scroll_area_widget else None
        
        if viewport_widget and hasattr(viewport_widget, 'viewport'):
            visible_rect = viewport_widget.viewport().rect()
            scroll_x = viewport_widget.horizontalScrollBar().value()
            visible_rect = QRectF(scroll_x, 0, visible_rect.width(), self.height())
        
        else:
            visible_rect = QRectF(0, 0, self.width(), self.height())
        
        return visible_rect

    def get_element_rect(self, element):
        tracks_area_start_y = Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.box_spacing
        y_offset_for_this_track = 0
    
        track_index = int(element['track']) - 1
    
        if track_index < 0:
            track_index = 0
        
        elif track_index >= len(self.track_names):
            track_index = len(self.track_names) - 1
    
        for i in range(track_index):
            y_offset_for_this_track += Styles.Metrics.Tracks.row_height + Styles.Metrics.Tracks.box_spacing
    
        track_base_y = tracks_area_start_y + y_offset_for_this_track
        element_top_y = track_base_y + (Styles.Metrics.Tracks.row_height - Styles.Metrics.Tracks.box_height) / 2.0
        start_px = element['start'] / self.ms_per_pixel
        width = element['duration'] / self.ms_per_pixel
    
        return QRectF(start_px, element_top_y, width, Styles.Metrics.Tracks.box_height)
    
    def get_or_generate_glyph_pixmap(self, glyph_id, glyph_data, is_selected):
        cache_key = (glyph_id, is_selected, glyph_data['duration'], glyph_data['start'])

        if cache_key in self._glyph_pixmaps:
            return self._glyph_pixmaps[cache_key]

        rect = self.get_element_rect(glyph_data)
        pixmap = QPixmap(int(rect.width() + 2), int(rect.height() + 2))
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(1, 1, rect.width(), rect.height(), 10, 10) 

        fill_brush = QBrush(QColor(255, 255, 255))
        border_pen = QPen(Qt.GlobalColor.red, 1.5) if is_selected else QPen(QColor("#505050"), 1)
        
        painter.setPen(border_pen)
        painter.setBrush(fill_brush)
        painter.drawPath(path)
        
        painter.end()

        self._glyph_pixmaps[cache_key] = pixmap
        return pixmap
    
    def update_ruler_cache(self, visible_rect: QRectF):
        pixmap = QPixmap(int(visible_rect.width()), Styles.Metrics.Tracks.ruler_height)
        pixmap.fill(Qt.GlobalColor.transparent)

        p = QPainter(pixmap)
        CurrentSettings["antialiasing"] and p.setRenderHint(QPainter.Antialiasing)
        
        p.setFont(self._ruler_font)
        p.setPen(QPen(QColor(255, 255, 255), 0.5))

        start_second = int(max(0, visible_rect.left() // self.pixels_per_major_tick))
        end_second = int((visible_rect.right() // self.pixels_per_major_tick) + 2)

        for i in range(start_second, end_second + 1):
            x_pos = i * self.pixels_per_major_tick - visible_rect.left()
            p.drawLine(QPointF(x_pos, 0), QPointF(x_pos, 8))
            p.drawText(
                QPointF(x_pos + 5, Styles.Metrics.Tracks.ruler_height - 10),
                str(self.start_time_sec + i)
            )

        p.end()

        self._ruler_cache = pixmap
        self._ruler_cache_rect = QRectF(visible_rect)
    
    def update_beats_cache(self, visible_rect: QRectF):
        pixmap = QPixmap(int(visible_rect.width()), self.height())
        pixmap.fill(Qt.GlobalColor.transparent)

        p = QPainter(pixmap)

        CurrentSettings["antialiasing"] and p.setRenderHint(QPainter.Antialiasing)

        beat_times = self.composition.beats
        if beat_times:
            p.setPen(QPen(QColor(Styles.Colors.Waveline.beat_color), 1, Qt.PenStyle.DotLine))
            
            for beat_time_sec in beat_times:
                x_pos = beat_time_sec * self.pixels_per_major_tick - visible_rect.left()
                
                if 0 <= x_pos <= visible_rect.width():
                    p.drawLine(
                        QPointF(x_pos, 0),
                        QPointF(x_pos, Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.ruler_height)
                    )

        p.end()

        self._beats_cache = pixmap
        self._beats_cache_rect = QRectF(visible_rect)
    
    def _on_playback_state_changed(self, is_playing):
        if is_playing:
            self.composition.syncer.play(self.get_playhead_ms())
            
        else:
            self.composition.syncer.stop()

    def change_brightness(self, brightness):
        self.composition.set_brightness(brightness)
    
    def change_duration(self, duration):
        self.composition.set_duration(duration)

    def _on_playback_position_updated(self, new_playhead_ms):
        self.set_playhead_from_ms(new_playhead_ms)
        self.ensure_playhead_visible()

    def _on_audio_loaded_from_manager(self, audio_data, sampling_rate, duration_seconds):
        self.waveform_tiles = {}
        self.sampling_rate = sampling_rate
        self.total_content_width = duration_seconds * self.pixels_per_major_tick
        
        self.setMinimumWidth(int(self.total_content_width))
        
        self._glyph_pixmaps = {}
        self.update()
        
        self.audio_state_changed.emit()
        self.scale_view(0)

        self.global_waveform_max = np.max(np.abs(audio_data.astype(np.float32)))
        if self.global_waveform_max == 0 or np.isnan(self.global_waveform_max):
            self.global_waveform_max = 1.0

    def scale_view(self, delta):
        old_ms_per_pixel = self.ms_per_pixel
        playhead_ms = self.playhead_x_position * old_ms_per_pixel

        min_pixels_per_major_tick = 20.0
        visible_width = self.width()
        duration_seconds = 0

        if hasattr(self, "parentWidget"):
            scroll_area_widget = self.parentWidget()
            viewport_widget = scroll_area_widget.parentWidget() if scroll_area_widget else None
            
            if viewport_widget and hasattr(viewport_widget, 'viewport'):
                visible_width = viewport_widget.viewport().width()
            
            duration_seconds = len(self.playback_manager.audio_data) / self.sampling_rate
            if duration_seconds > 0:
                min_pixels_per_major_tick = max(
                    min_pixels_per_major_tick,
                    visible_width / duration_seconds
                )

        self.pixels_per_major_tick = max(min_pixels_per_major_tick, self.pixels_per_major_tick + delta)
        self.ms_per_pixel = 1000.0 / self.pixels_per_major_tick
        self.playhead_x_position = playhead_ms / self.ms_per_pixel

        if duration_seconds > 0:
            self.total_content_width = max(duration_seconds * self.pixels_per_major_tick, visible_width)
            self.setMinimumWidth(int(self.total_content_width))
            self.playhead_x_position = min(self.playhead_x_position, self.total_content_width)

        self.waveform_tiles = {}
        self._beats_cache = None
        self._ruler_cache = None
        
        if self.composition:
            self._glyph_pixmaps = {}
        
        self.update_minimum_height()
        self.update()

    def on_scale_plus(self):
        self.scale_view(+100)

    def on_scale_minus(self):
        self.scale_view(-100)

    def update_minimum_height(self):
        calculated_total_height = Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.box_spacing + len(self.track_names) * (Styles.Metrics.Tracks.row_height+ Styles.Metrics.Tracks.box_spacing)
        self.setMinimumHeight(int(calculated_total_height))

    def update_ms_per_pixel(self):
        if self.pixels_per_major_tick > 0:
            self.ms_per_pixel = 1000.0 / self.pixels_per_major_tick
        
        else:
            self.ms_per_pixel = 1000.0 / 100.0
    
    def generate_tile(self, tile_index):
        logger.warning(f"Tile {tile_index} created")

        if self.playback_manager.audio_data is None or len(self.playback_manager.audio_data) == 0:
            return None

        total_px_width = self.total_content_width
        samples_per_pixel_overall = len(self.playback_manager.audio_data) / float(total_px_width) if total_px_width > 0 else 1.0

        start_px = tile_index * self.tile_width
        start_sample = int(start_px * samples_per_pixel_overall)
        end_sample = int((start_px + self.tile_width) * samples_per_pixel_overall)

        start_sample = max(0, start_sample)
        end_sample = min(len(self.playback_manager.audio_data), end_sample)

        audio_chunk = self.playback_manager.audio_data[start_sample:end_sample]

        if audio_chunk.size == 0:
            return None

        if audio_chunk.ndim == 1:
            min_samples = audio_chunk
            max_samples = audio_chunk
        
        elif audio_chunk.ndim == 2:
            min_samples = np.min(audio_chunk, axis=1)
            max_samples = np.max(audio_chunk, axis=1)
        
        else:
            return None

        num_samples = len(min_samples)
        if num_samples == 0:
            return None

        samples_per_pixel_tile = num_samples / float(self.tile_width) if self.tile_width > 0 else float(num_samples)
        step = max(1, int(np.ceil(samples_per_pixel_tile)))

        padded_length = ((num_samples + step - 1) // step) * step
        pad_amount = padded_length - num_samples

        padded_min = np.pad(min_samples, (0, pad_amount), mode = 'constant')
        padded_max = np.pad(max_samples, (0, pad_amount), mode = 'constant')

        reshaped_min = padded_min.reshape(-1, step)
        reshaped_max = padded_max.reshape(-1, step)

        min_vals = np.min(reshaped_min, axis=1)
        max_vals = np.max(reshaped_max, axis=1)

        if not hasattr(self, "global_waveform_max"):
            dtype = self.playback_manager.audio_data.dtype
            scale = 32767.0 if np.issubdtype(dtype, np.integer) else 1.0
            self.global_waveform_max = np.max(np.abs(self.playback_manager.audio_data.astype(np.float32) / scale))
            if self.global_waveform_max == 0:
                self.global_waveform_max = 1.0

        dtype = self.playback_manager.audio_data.dtype
        
        if np.issubdtype(dtype, np.integer):
            scale = 32767.0
        
        else:
            scale = 1.0

        max_vals_f = (max_vals.astype(np.float32) / scale)
        min_vals_f = (min_vals.astype(np.float32) / scale)

        max_vals_f = max_vals.astype(np.float32) / self.global_waveform_max
        min_vals_f = min_vals.astype(np.float32) / self.global_waveform_max

        height = int(Styles.Metrics.Waveform.height)
        y_center = height / 2.0

        amplitudes_top = y_center - max_vals_f * y_center
        amplitudes_bottom = y_center - min_vals_f * y_center

        sigma = CurrentSettings["waveform_smoothing"]
        
        if sigma and sigma > 0.0 and len(amplitudes_top) > 1:
            pad = int(np.ceil(sigma * 3.0))
            pad = min(pad, len(amplitudes_top) - 1)
        
            top_padded = np.pad(amplitudes_top, (pad, pad), mode = 'reflect')
            bottom_padded = np.pad(amplitudes_bottom, (pad, pad), mode = 'reflect')
        
            smooth_top_padded = Utils.gaussian_filter1d_np(top_padded, sigma=sigma)
            smooth_bottom_padded = Utils.gaussian_filter1d_np(bottom_padded, sigma=sigma)
        
            smooth_top = smooth_top_padded[pad:pad + len(amplitudes_top)]
            smooth_bottom = smooth_bottom_padded[pad:pad + len(amplitudes_bottom)]
        
        else:
            smooth_top = amplitudes_top
            smooth_bottom = amplitudes_bottom
        
        if len(smooth_top) == len(smooth_bottom):
            mask = smooth_top > smooth_bottom
            if np.any(mask):
                avg = (smooth_top[mask] + smooth_bottom[mask]) / 2.0
                smooth_top[mask] = avg
                smooth_bottom[mask] = avg

        if len(smooth_top) == 0 or len(smooth_bottom) == 0:
            return None

        pixmap = QPixmap(self.tile_width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)

        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)

        bar_width = float(self.tile_width) / len(smooth_top)

        path = QPainterPath()
        for i in range(len(smooth_top)):
            x = i * bar_width
            y = max(0.0, min(float(height), float(smooth_top[i])))
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        for i in reversed(range(len(smooth_bottom))):
            x = i * bar_width
            y = max(0.0, min(float(height), float(smooth_bottom[i])))
            path.lineTo(x, y)

        path.closeSubpath()

        outline_color = QColor(255, 255, 255, 90)
        painter.setPen(QPen(outline_color, 2.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        fill_color = QColor(255, 255, 255, 90)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(QColor(255, 255, 255, 160), 0.7))
        painter.drawPath(path)

        painter.end()

        self.waveform_tiles[tile_index] = pixmap
        return pixmap
    
    def paintEvent(self, event):
        painter = QPainter(self)

        now = time.time()
        delta = now - self.last_time
        self.last_time = now

        if delta > 0:
            self.frame_times.append(1.0 / delta)
            self.fps = sum(self.frame_times) / len(self.frame_times)
        
        if self.playback_manager.is_playing:
            self.main_window_ref.top_status_label.setText(f"{STATUS_BAR_DEFAULT} - FPS {self.fps:.1f}")

        CurrentSettings["antialiasing"] and painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        visible_rect = self.get_visible_rect()
        current_y = Styles.Metrics.Tracks.ruler_height
        
        # Ruler
        if self._ruler_cache is None or self._ruler_cache_rect != visible_rect:
            self.update_ruler_cache(visible_rect)
        
        # Beats
        if self._beats_cache is None or self._beats_cache_rect != visible_rect:
            self.update_beats_cache(visible_rect)
        
        painter.drawPixmap(int(visible_rect.left()), 0, self._ruler_cache)
        painter.drawPixmap(int(visible_rect.left()), 0, self._beats_cache)

        # Waveform
        if self.playback_manager.audio_data is not None and len(self.playback_manager.audio_data) > 0:
            start_tile_index = int(visible_rect.left() // self.tile_width)
            end_tile_index = int(visible_rect.right() // self.tile_width)

            for i in range(start_tile_index, end_tile_index + 1):
                tile = self.waveform_tiles.get(i)
                
                if not tile:
                    tile = self.generate_tile(i)
                
                if tile:
                    draw_pos_x = i * self.tile_width
                    if draw_pos_x <= visible_rect.right() and draw_pos_x + self.tile_width >= visible_rect.left():
                        painter.drawPixmap(draw_pos_x, current_y, tile)

        current_y += Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.box_spacing

        # Track Names, Grid
        painter.setFont(self._track_label_font)

        for track_name in self.track_names:
            track_base_y = current_y
            track_content_top_y = track_base_y + (Styles.Metrics.Tracks.row_height - Styles.Metrics.Tracks.box_height) / 2.0
            track_content_bottom_y = track_content_top_y + Styles.Metrics.Tracks.box_height

            if track_content_bottom_y >= visible_rect.top() and track_base_y <= visible_rect.bottom():
                painter.setPen(QColor(Styles.Colors.Waveline.track_name_color))
                
                label_rect = QRectF(
                    Styles.Metrics.Tracks.box_spacing,
                    track_content_top_y,
                    Styles.Metrics.Tracks.label_width - 2 * Styles.Metrics.Tracks.box_spacing,
                    Styles.Metrics.Tracks.box_height,
                )
                
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, track_name)
                painter.setFont(self._track_label_font)

                painter.setPen(QPen(Qt.GlobalColor.darkGray, 0.5))
                start_second = int(max(0, visible_rect.left() // self.pixels_per_major_tick))
                end_second = int((visible_rect.right() // self.pixels_per_major_tick) + 2)

                for i in range(start_second, end_second + 1):
                    line_x = i * self.pixels_per_major_tick
                    
                    if visible_rect.left() <= line_x <= visible_rect.right():
                        if line_x > Styles.Metrics.Tracks.label_width:
                            painter.drawLine(
                                QPointF(line_x, track_content_top_y),
                                QPointF(line_x, track_content_bottom_y)
                            )

            current_y += Styles.Metrics.Tracks.row_height + Styles.Metrics.Tracks.box_spacing

        # Glyphs
        drawing_debug = 0
        for id, glyph in self.composition.all_glyphs().items():
            element_rect = self.get_element_rect(glyph)

            if not visible_rect.intersects(element_rect):
                continue
            
            is_selected = id in self.glyph_manager.selected_element_ids
            glyph_pixmap = self.get_or_generate_glyph_pixmap(id, glyph, is_selected)
            
            if glyph_pixmap:
                element_rect = self.get_element_rect(glyph)
                x_pos_in_viewport = element_rect.left() - visible_rect.left()
                painter.setOpacity(self.get_opacity_for_position(x_pos_in_viewport))
                painter.drawPixmap(element_rect.topLeft(), glyph_pixmap)
                drawing_debug += 1

        painter.setOpacity(1)

        # Selection
        if self.mouse_controller.is_marquee_selecting:
            painter.setPen(self._marquee_pen)
            painter.setBrush(self._marquee_brush)
            
            selection_radius = min(int((self.mouse_controller.marquee_rect.width() + self.mouse_controller.marquee_rect.height()) / 12), 10)
            painter.drawRoundedRect(self.mouse_controller.marquee_rect, selection_radius, selection_radius)

        # Playhead
        painter.setPen(QPen(Qt.GlobalColor.red, 2))
        painter.drawLine(
            int(self.playhead_x_position), 0,
            int(self.playhead_x_position), int(self.height())
        )

    def control_popup(self, title, label, key, min_val = 1, max_val = None):
        dialog = UI.DialogInputWindow(title, label, min_val, max_val, bpm = self.composition.bpm, player = self.playback_manager)
        if dialog.exec_() != QDialog.Accepted:
            return

        user_input = dialog.result_text
        updated_glyphs = {}

        for el_id in self.glyph_manager.selected_element_ids:
            el = self.composition.get_glyph(el_id)
            
            if el:
                el[key] = user_input
                updated_glyphs[el_id] = el
                
                self._glyph_pixmaps.pop(el_id, None)
        
        self.composition.update_bunch_of_glyphs(updated_glyphs)

    def brightness_control_popup(self):
        self.control_popup("Brightness", "Percent", "brightness", max_val = 100)

    def duration_control_popup(self):
        self.control_popup("Duration", "Duration (ms)", "duration", min_val = 1, max_val=10000)
        self.update()
    
    def keyPressEvent(self, event):
        return self.keyboard_controller.process_key_event(event)
    
    def wheelEvent(self, event):
        return self.wheel_controller.process_wheel_event(event)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_controller.process_mouse_press_event(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        return self.mouse_controller.process_mouse_move_event(event)

    def mouseReleaseEvent(self, event):
        return self.mouse_controller.process_mouse_release_event(event)
    
    def segment_control_popup(self):
        first_id = next(iter(self.glyph_manager.selected_element_ids))
        first_glyph = self.composition.get_glyph(first_id)

        popup = UI.SegmentEditor(
            "Segments",
            self.composition.bpm,
            self.playback_manager,
            get_segments(self.composition.model, first_glyph["track"]),
            first_glyph.get("segments"),
        )

        if popup.exec_() != QDialog.Accepted:
            return

        segments = popup.saved_segments
        turned_on = [i for i, s in enumerate(segments) if s]
        all_turned_on = all(segments)

        updated_glyphs = {}

        for element_id in self.glyph_manager.selected_element_ids:
            glyph = self.composition.get_glyph(element_id)
            if all_turned_on:
                glyph.pop("segments", None)
            
            else:
                glyph["segments"] = turned_on
            
            updated_glyphs[element_id] = glyph

        if not GlyphEffects.EffectsConfig.get(first_glyph.get("effect", {}).get("name"), {}).get("supports_segmentation", True):
            UI.ErrorWindow(
                "Effect has been reset",
                "Heads up: custom segmentation doesn't work with applied effect, so we reset the effect."
            ).exec_()

            for element_id in self.glyph_manager.selected_element_ids:
                glyph = self.composition.get_glyph(element_id)
                glyph.pop("effect", None)

        self.composition.update_bunch_of_glyphs(updated_glyphs)

    def contextMenuEvent(self, event: QContextMenuEvent):
        try:
            self.mouse_controller._mouse_pressed = False
            id, clicked_element, _ = self.get_element_at(event.pos())
            if not clicked_element:
                return

            Utils.ui_sound("MenuOpen")
            self.update()

            def on_apply_requested_factory(name, settings):
                for sel_id in self.glyph_manager.selected_element_ids:
                    element = self.composition.get_glyph(sel_id)
                    if element:
                        result = GlyphEffects.effectCallback(name, settings, element)
                        self.composition.replace_glyph(sel_id, result)
                    
                self.update()

            has_non_segmented = [
                not is_segmented(self.composition.get_glyph(sel_id)["track"], self.composition.model)
                for sel_id in self.glyph_manager.selected_element_ids
            ]
            
            has_segmented = [
                is_segmented(self.composition.get_glyph(sel_id)["track"], self.composition.model)
                for sel_id in self.glyph_manager.selected_element_ids
            ]

            if len(has_segmented) == 1 and all(has_segmented):
                can_show_segment_editor = True
            
            else:
                can_show_segment_editor = False

            has_segments = any(
                GlyphEffects.is_segment_edited(self.composition.get_glyph(sel_id))
                for sel_id in self.glyph_manager.selected_element_ids
            )

            if any(has_non_segmented):
                effects = GlyphEffects.only_non_segmented()
            
            elif has_segments:
                effects = GlyphEffects.only_segmentation_supported()
            
            else:
                effects = GlyphEffects.all()

            effect_entries = []
            for effect_name, config in effects.items():
                preview_widget = UI.EffectPreviewWidget(effect_name, config)
                preview_widget.apply_requested.connect(
                    lambda effect_name, settings: on_apply_requested_factory(effect_name, settings)
                )

                effect_entries.append((effect_name, [("preview_widget", preview_widget)]))

            entries = [
                ("Delete", self.glyph_manager.delete_selected_elements),
                ("Copy", self.glyph_manager.copy_selected_elements),
                ("Paste", self.glyph_manager.paste_elements),
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
            QMessageBox.critical(None, "Context menu failed to show.", f"Report this error to chips047: {str(e)}")
            return
    
    def show_error_dialog(self, title, message):
        error_dialog = UI.ErrorWindow(title, message, "Oh nah", self.composition.bpm, self.playback_manager)
        error_dialog.exec_()
    
    def get_element_at(self, pos):
        for id, element in reversed(self.composition.all_glyphs().items()):
            element_rect = self.get_element_rect(element)
            
            if element_rect.contains(pos):
                on_left_edge = abs(pos.x() - element_rect.left()) < GLYPH_RESIZE_SENSITIVITY
                on_right_edge = abs(pos.x() - element_rect.right()) < GLYPH_RESIZE_SENSITIVITY
                
                if on_left_edge:
                    return id, element, 'resize_left'
                
                if on_right_edge:
                    return id, element, 'resize_right'
                
                return id, element, 'body'
        
        return None, None, None

    def ensure_playhead_visible(self):
        scroll_widget = self.parentWidget()
        scroll_area = scroll_widget.parentWidget() if scroll_widget else None
        
        if isinstance(scroll_area, QScrollArea):
            h_bar = scroll_area.horizontalScrollBar(); vp_w = scroll_area.viewport().width()
            cur_scroll = h_bar.value()

            coeff = 0.5 if CurrentSettings["center_playhead"] else 0.15
            margin = vp_w * coeff
            
            if self.playhead_x_position < cur_scroll + margin:
                h_bar.setValue(max(0, int(self.playhead_x_position - margin)))
            
            elif self.playhead_x_position > cur_scroll + vp_w - margin:
                h_bar.setValue(min(h_bar.maximum(), int(self.playhead_x_position - vp_w + margin)))

    def get_playhead_ms(self):
        return self.playhead_x_position * self.ms_per_pixel

    def set_playhead_from_ms(self, time_ms):
        if self.ms_per_pixel > 0:
            self.playhead_x_position = time_ms / self.ms_per_pixel
            self.playhead_x_position = max(0, min(self.playhead_x_position, self.total_content_width))
            self.update() 
        
        else: 
            self.playhead_x_position = 0

    def scroll_to_normalized_position(self, normalized_pos):
        target_x_pixels = normalized_pos * self.total_content_width
        self.playhead_x_position = max(0.0, min(target_x_pixels, self.total_content_width))

        if self.playback_manager.is_playing:
            self.playback_manager.stop_playback()
            self.playback_manager.start_playback(self.get_playhead_ms())

        self.update()
        self.ensure_playhead_visible()

        if self.main_window_ref and hasattr(self.main_window_ref, 'scroll_area'):
            scroll_area = self.main_window_ref.scroll_area
            
            h_bar = scroll_area.horizontalScrollBar()
            vp_w = scroll_area.viewport().width()
            
            target_scroll_value = int(self.playhead_x_position - vp_w / 2)
            target_scroll_value = max(0, min(target_scroll_value, h_bar.maximum()))
            
            h_bar.setValue(target_scroll_value)

class CompositorWidget(QWidget):
    back_to_main_menu_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #1e1e1e;")

        self.overall_layout = QVBoxLayout(self)
        self.overall_layout.setContentsMargins(10, 10, 10, 10)
        self.overall_layout.setSpacing(10)

        self.top_control_bar_widget = QWidget()
        self.top_control_bar_layout = QHBoxLayout(self.top_control_bar_widget)
        self.top_control_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.top_control_bar_layout.setSpacing(10)
        
        self.eject_button = UI.Button("Eject")
        self.eject_button.clicked.connect(self.on_eject_button_clicked)

        self.top_control_bar_layout.addWidget(self.eject_button)

        self.mini_preview_widget = UI.MiniWaveformPreview()
        self.mini_preview_widget.setVisible(False)
        self.mini_preview_widget.preview_clicked.connect(self.on_mini_preview_clicked)
        self.top_control_bar_layout.addWidget(self.mini_preview_widget, 2)

        self.glyph_dur_control = UI.DraggableValueControl(Utils.Icons.Duration, "duration", 100, 5, 5000, 5, "ms")
        self.brightness_control = UI.DraggableValueControl(Utils.Icons.Brightness, "brightness", 100, 5, 100, 5, "%")
        self.playspeed_button = UI.CycleButton(Utils.Icons.Speed, "speed", [("1x", 1.0), ("0.5x", 0.5), ("0.2x", 0.2)])
        self.default_effect = UI.CycleButton(Utils.Icons.Effect, "effect", [("None", "None"), ("Fade out", "Fade out"), ("Fade in", "Fade in"), ("Fade in out", "Fade in + out")])
        
        self.top_control_bar_layout.addWidget(self.glyph_dur_control)
        self.top_control_bar_layout.addWidget(self.brightness_control)
        self.top_control_bar_layout.addWidget(self.playspeed_button)
        self.top_control_bar_layout.addWidget(self.default_effect)

        self.export_button = UI.NothingButton("Export")
        self.export_button.setEnabled(False)
        
        self.top_control_bar_layout.addWidget(self.export_button)

        self.overall_layout.addWidget(self.top_control_bar_widget)

        self.top_status_label = QLabel(STATUS_BAR_DEFAULT)
        self.top_status_label.setFont(Utils.NDot(14))
        self.top_status_label.setMinimumHeight(Styles.Metrics.element_height) 
        self.top_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.top_status_label.setStyleSheet(Styles.Other.status_bar)
        self.overall_layout.addWidget(self.top_status_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.export_button.clicked.connect(self.export_ringtone)
        self.playspeed_button.state_changed.connect(self.on_playspeed_changed)
        self.default_effect.state_changed.connect(self.on_default_effect_change)
    
    def on_eject_button_clicked(self):
        self.content_widget.composition.syncer.stop_scanning_loop()
        self.back_to_main_menu_requested.emit()

        if self.content_widget.playback_manager.is_playing:
            self.content_widget.playback_manager.play_tail_with_tape_stop()
    
    def cleanup(self):
        self.mini_preview_widget.audio_data = None
        self.mini_preview_widget.peaks = None
        self.content_widget.deleteLater()

        self.glyph_dur_control.current_value = 100
        self.brightness_control.current_value = 100
        self.default_effect.current_state_index = 0
        self.playspeed_button.current_state_index = 0
    
    def export_ringtone(self):
        dialog = UI.ExportDialogWindow("Export?", self.content_widget.composition, self.content_widget.composition.bpm, self.content_widget.playback_manager)
        if dialog.exec() == QDialog.Accepted:
            self.content_widget.composition.export()
            Utils.ui_sound("Export")

    def on_mini_preview_clicked(self, normalized_pos):
        self.content_widget.scroll_to_normalized_position(normalized_pos)

    def on_playspeed_changed(self, text_part, speed_value):
        self.content_widget.playback_manager.set_playback_speed_multiplier(speed_value)

    def on_default_effect_change(self, text_part, effect_value):
        self.content_widget.composition.set_default_effect(effect_value)

    def update_ui_on_audio_state_change(self):
        self.mini_preview_widget.setVisible(True)
        self.mini_preview_widget.set_audio_data(self.content_widget.playback_manager.audio_data, self.content_widget.sampling_rate)

        self.update_export_button_state()

    def update_export_button_state(self):
        elements_exist = len(self.content_widget.composition.glyphs) > 0
        self.export_button.setEnabled(elements_exist)

        self.content_widget.update()

    def initialize_compositor(self, audio_path, composition):
        self.content_widget = ScrollableContent(self.scroll_area, self, composition)
        self.overall_layout.addWidget(self.scroll_area, 1)

        self.content_widget.audio_state_changed.connect(self.update_ui_on_audio_state_change)
        self.content_widget.glyph_manager.elements_changed.connect(self.update_export_button_state)
        self.glyph_dur_control.valueChanged.connect(self.content_widget.change_duration)
        self.brightness_control.valueChanged.connect(self.content_widget.change_brightness)

        self.scroll_area.setWidget(self.content_widget)
                
        if self.content_widget.playback_manager.is_playing: 
            self.content_widget.playback_manager.stop_playback()
        
        self.content_widget.playback_manager.load_audio(audio_path)

        # Focus Fix
        for child in self.findChildren(QWidget):
            if child is not self.content_widget:
                child.setFocusPolicy(Qt.NoFocus)

        self.content_widget.setFocus()
    
    def closeEvent(self, event):
        if hasattr(self, "content_widget"):
            if self.content_widget.composition:
                self.content_widget.composition.syncer.exit_app()
                self.content_widget.composition.syncer.stop_scanning_loop()
        
        event.accept()