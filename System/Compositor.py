import numpy as np

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System import Player
from System import Styles
from System import ProjectSaver
from System import GlyphEffects

from System.Constants import *

from System import UI
from System import Utils

class ScrollableContent(QWidget):
    audio_state_changed = pyqtSignal()
    elements_changed = pyqtSignal()

    def __init__(self, parent, top_status_label, main_window_ref, composition: ProjectSaver.Composition):
        super().__init__(parent)
        
        self.composition = composition
        
        # References
        self.top_status_label = top_status_label
        self.main_window_ref = main_window_ref
    
        # UI Configuration
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
    
        # Scaling & Time
        self.pixels_per_major_tick = DEFAULT_SCALING
        self.start_time_sec = 0
        self.ms_per_pixel = 1000.0 / self.pixels_per_major_tick
        
        # Playhead
        self.playhead_x_position = 0
        self.playhead_move_increment = ARROW_KEY_INCREMENT
        self.current_playback_speed_multiplier = 1.0
        self.playback_start_audio_ms = 0

        # Scroll
        self._scroll_velocity = 0
        self._scroll_target_velocity = 0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.timeout.connect(self._update_smooth_scroll)
        self._scroll_timer.setInterval(FPS_120)
    
        # Playback
        self.playback_timer = QTimer(self)
        self.audio_data = None
    
        # Track Management
        self.track_names = ["1"]
        self.total_content_width = 2000
    
        # Element Management
        self.selected_element_ids = set()
        self.updated_elements = {}
    
        # Selection & Interaction
        self.dragging_element_info = None
        self.is_marquee_selecting = False
        self.marquee_start_pos = QPointF()
        self.marquee_rect = QRectF()
    
        # Shortcuts
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.on_scale_plus)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.on_scale_minus)
        QShortcut(QKeySequence(Qt.Key_Delete), self).activated.connect(self.delete_selected_elements)

        # Tooltip
        self._tooltip_last_global_pos = None
        self._tooltip_current_element = None
        self._tooltip_pending_element = None
        self._tooltip_pending_pos = None
    
        self.animated_tooltip = UI.AnimatedTooltip(self)
        self.tooltip_delay_timer = QTimer(self)
        self.tooltip_delay_timer.setSingleShot(True)
        self.tooltip_delay_timer.timeout.connect(self.show_delayed_tooltip)
    
        # Caching
        self._elements_cache_dirty = True
        self._element_rects = []
        self._elements_pixmap = None
        self._elements_pixmap_rect = None
        self.tile_width = TILE_SIZE
        self.waveform_tiles = {}
    
        # Other state
        self.active_popup = None
        self._mouse_pressed = False

        # Final init
        self.update_minimum_height()
        
        self.playback_manager = Player.PlaybackManager(self)
        self.playback_manager.playback_position_updated.connect(self._on_playback_position_updated)
        self.playback_manager.audio_loaded.connect(self._on_audio_loaded_from_manager)
        self.playback_manager.status_message_requested.connect(self.set_status_message)
        self.playback_manager.playback_state_changed.connect(self._on_playback_state_changed)
    
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
        self.audio_data = audio_data
        self.sampling_rate = sampling_rate
        self.total_content_width = duration_seconds * self.pixels_per_major_tick
        
        self.setMinimumWidth(int(self.total_content_width))
        
        self.update_element_rects_cache()
        self.mark_elements_cache_dirty()
        self.update()
        
        self.audio_state_changed.emit()
        self.scale_view(0)

    def show_delayed_tooltip(self):
        if self._tooltip_pending_element:
            if (self.animated_tooltip.is_tooltip_visible() and
                self._tooltip_pending_element == self._tooltip_current_element):
                return
            
            self._tooltip_current_element = self._tooltip_pending_element
            self.animated_tooltip.show_tooltip(
                self._tooltip_pending_text,
                self._tooltip_pending_pos
            )

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

    def update_element_rects_cache(self):
        self._element_rects = [self.get_element_rect(el) for id, el in self.composition.glyphs.items()]
        self.mark_elements_cache_dirty()

    def mark_elements_cache_dirty(self):
        self._elements_cache_dirty = True
        self._elements_pixmap_rect = None

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

    def set_status_message(self, message, timeout=0):
        if self.top_status_label:
            self.top_status_label.setText(message)
            
            if timeout > 0:
                QTimer.singleShot(timeout, lambda: self.clear_status_message_if_matches(message))

    def clear_status_message_if_matches(self, original_message):
        if self.top_status_label and self.top_status_label.text() == original_message:
            self.top_status_label.setText(STATUS_BAR_DEFAULT)

    def scale_view(self, delta):
        old_ms_per_pixel = self.ms_per_pixel
        playhead_ms = self.playhead_x_position * old_ms_per_pixel

        min_pixels_per_major_tick = 20.0
        visible_width = self.width()
        duration_seconds = 0

        if self.audio_data is not None and hasattr(self, "parentWidget"):
            scroll_area_widget = self.parentWidget()
            viewport_widget = scroll_area_widget.parentWidget() if scroll_area_widget else None
            if viewport_widget and hasattr(viewport_widget, 'viewport'):
                visible_width = viewport_widget.viewport().width()
            duration_seconds = len(self.audio_data) / self.sampling_rate
            if duration_seconds > 0:
                min_pixels_per_major_tick = max(
                    min_pixels_per_major_tick,
                    visible_width / duration_seconds
                )

        self.pixels_per_major_tick = max(min_pixels_per_major_tick, self.pixels_per_major_tick + delta)
        self.ms_per_pixel = 1000.0 / self.pixels_per_major_tick
        self.playhead_x_position = playhead_ms / self.ms_per_pixel

        if self.audio_data is not None and duration_seconds > 0:
            self.total_content_width = max(duration_seconds * self.pixels_per_major_tick, visible_width)
            self.setMinimumWidth(int(self.total_content_width))
            self.playhead_x_position = min(self.playhead_x_position, self.total_content_width)

        self.waveform_tiles = {}
        if self.composition:
            self.update_element_rects_cache()
            self.mark_elements_cache_dirty()
        
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
        if self.audio_data is None or len(self.audio_data) == 0:
            return None
    
        total_px_width = self.total_content_width
        samples_per_pixel_overall = len(self.audio_data) / float(total_px_width)
    
        start_px = tile_index * self.tile_width
        start_sample = int(start_px * samples_per_pixel_overall)
        end_sample = int((start_px + self.tile_width) * samples_per_pixel_overall)
    
        start_sample = max(0, start_sample)
        end_sample = min(len(self.audio_data), end_sample)
        audio_chunk = self.audio_data[start_sample:end_sample]
        
        audio_chunk = audio_chunk - np.mean(audio_chunk)
        audio_chunk = audio_chunk / np.max(np.abs(audio_chunk))
    
        if audio_chunk.size == 0:
            return None
    
        height = int(Styles.Metrics.Waveform.height)
        y_center = height / 2.0
    
        num_samples = len(audio_chunk)
        samples_per_pixel_tile = num_samples / float(self.tile_width)
    
        step = max(1, int(np.ceil(samples_per_pixel_tile)))
        padded_length = ((len(audio_chunk) + step - 1) // step) * step
        padded = np.pad(audio_chunk, (0, padded_length - len(audio_chunk)), mode='constant')
        reshaped = padded.reshape(-1, step)
        min_vals = np.min(reshaped, axis=1)
        max_vals = np.max(reshaped, axis=1)
    
        amplitudes_top = y_center - max_vals * y_center
        amplitudes_bottom = y_center - min_vals * y_center
    
        smooth_top = Utils.gaussian_filter1d_np(amplitudes_top, sigma=2)
        smooth_bottom = Utils.gaussian_filter1d_np(amplitudes_bottom, sigma=2)
    
        pixmap = QPixmap(self.tile_width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
    
        bar_width = self.tile_width / len(smooth_top)
    
        path = QPainterPath()
        for i in range(len(smooth_top)):
            x = i * bar_width
            y = max(0, min(height, smooth_top[i]))
            
            if i == 0:
                path.moveTo(x, y)
            
            else:
                path.lineTo(x, y)
    
        for i in reversed(range(len(smooth_bottom))):
            x = i * bar_width
            y = max(0, min(height, smooth_bottom[i]))
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
        
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        
        current_y = 0
        font = painter.font()
        painter.setPen(Qt.GlobalColor.white)
        
        ruler_font = QFont(font); ruler_font.setPointSize(8); painter.setFont(ruler_font)
        num_seconds_to_display_on_ruler = int(self.total_content_width / self.pixels_per_major_tick) + 2

        beat_times = self.composition.beats
        if beat_times:
            painter.setPen(QPen(QColor(Styles.Colors.Waveline.beat_color), 1, Qt.PenStyle.DotLine))
            for beat_time_sec in beat_times:
                x_pos = beat_time_sec * self.pixels_per_major_tick
                if x_pos > self.width():
                    break
                painter.drawLine(
                    QPointF(x_pos, current_y),
                    QPointF(x_pos, current_y + Styles.Metrics.Waveform.height + Styles.Metrics.Tracks.ruler_height)
                )

        for i in range(num_seconds_to_display_on_ruler):
            x_pos = i * self.pixels_per_major_tick
            
            if x_pos > self.width() + self.pixels_per_major_tick : 
                break
            
            time_label = str(self.start_time_sec + i)
            painter.drawText(QPointF(x_pos + 5, current_y + Styles.Metrics.Tracks.ruler_height - 10), time_label)
            painter.drawLine(QPointF(x_pos, current_y + Styles.Metrics.Tracks.ruler_height - 8), QPointF(x_pos, current_y + Styles.Metrics.Tracks.ruler_height))
            pixels_per_minor_tick = self.pixels_per_major_tick / 10.0
            
            for j in range(1, 10):
                minor_x_pos = x_pos + j * pixels_per_minor_tick
                
                if minor_x_pos < self.total_content_width + pixels_per_minor_tick:
                    painter.drawLine(QPointF(minor_x_pos, current_y + Styles.Metrics.Tracks.ruler_height - 4), QPointF(minor_x_pos, current_y + Styles.Metrics.Tracks.ruler_height))
        
        current_y += Styles.Metrics.Tracks.ruler_height; painter.setFont(font)
        waveform_top_y = current_y
        
        if self.audio_data is not None and len(self.audio_data) > 0:
            scroll_area_widget = self.parentWidget()
            viewport_widget = scroll_area_widget.parentWidget() if scroll_area_widget else None
            visible_rect = viewport_widget.viewport().rect() if viewport_widget and hasattr(viewport_widget, 'viewport') else self.rect()
            scroll_x = viewport_widget.horizontalScrollBar().value() if viewport_widget and hasattr(viewport_widget, 'horizontalScrollBar') else 0
            
            start_tile_index = int(scroll_x / self.tile_width)
            end_tile_index = int((scroll_x + visible_rect.width()) / self.tile_width)

            for i in range(start_tile_index, end_tile_index + 1):
                tile = self.waveform_tiles.get(i)
                if not tile:
                    tile = self.generate_tile(i)

                if tile:
                    draw_pos_x = i * self.tile_width
                    painter.drawPixmap(draw_pos_x, waveform_top_y, tile)
        
        current_y += Styles.Metrics.Waveform.height
        current_y += Styles.Metrics.Tracks.box_spacing

        track_label_font = QFont(font); track_label_font.setPointSize(9); track_label_font.setBold(True)
        white_brush = QBrush(QColor(255, 255, 255))
        red_pen = QPen(Qt.GlobalColor.red, 1.5)
        gray_pen = QPen(QColor("#505050"), 1)
        
        for track_name in self.track_names:
            track_base_y = current_y
            track_content_top_y = track_base_y + (Styles.Metrics.Tracks.row_height- Styles.Metrics.Tracks.box_height) / 2.0
            track_content_bottom_y = track_content_top_y + Styles.Metrics.Tracks.box_height

            painter.setFont(Utils.NDot(14)); painter.setPen(QColor(Styles.Colors.Waveline.track_name_color))
            label_rect = QRectF(Styles.Metrics.Tracks.box_spacing, track_content_top_y, Styles.Metrics.Tracks.label_width - 2 * Styles.Metrics.Tracks.box_spacing, Styles.Metrics.Tracks.box_height)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, track_name)
            painter.setFont(font)

            painter.setPen(QPen(Qt.GlobalColor.darkGray, 0.5)) 
            
            for i in range(num_seconds_to_display_on_ruler): 
                line_x = i * self.pixels_per_major_tick
                
                if line_x > Styles.Metrics.Tracks.label_width and line_x <= self.total_content_width + self.pixels_per_major_tick:
                    if line_x < self.width() + self.pixels_per_major_tick:
                        painter.drawLine(QPointF(line_x, track_content_top_y), QPointF(line_x, track_content_bottom_y))
            
            current_y += Styles.Metrics.Tracks.row_height
            current_y += Styles.Metrics.Tracks.box_spacing
        
        scroll_area_widget = self.parentWidget()
        viewport_widget = scroll_area_widget.parentWidget() if scroll_area_widget else None
        
        if viewport_widget and hasattr(viewport_widget, 'viewport'):
            visible_rect = viewport_widget.viewport().rect()
            scroll_x = viewport_widget.horizontalScrollBar().value()
            visible_rect = QRectF(scroll_x, 0, visible_rect.width(), self.height())
        
        else:
            visible_rect = QRectF(0, 0, self.width(), self.height())
        
        painter.setClipRect(visible_rect)
        
        if (self._elements_pixmap is None or self._elements_cache_dirty or
            self._elements_pixmap_rect is None or self._elements_pixmap_rect != visible_rect):
            self.update_elements_pixmap(visible_rect)
        
        if self._elements_pixmap:
            painter.drawPixmap(int(visible_rect.left()), int(visible_rect.top()), self._elements_pixmap)
        
        painter.setClipping(False)
        
        for id, glyph in self.composition.glyphs.items():
            element_rect = self.get_element_rect(glyph)
            
            if not element_rect.intersects(visible_rect):
                continue
            
            path = QPainterPath(); path.addRoundedRect(element_rect, 10, 10)
            
            if id in self.selected_element_ids:
                painter.fillPath(path, white_brush)
                painter.setPen(red_pen)
            
            else:
                painter.fillPath(path, white_brush)
                painter.setPen(gray_pen)
            
            painter.drawPath(path)
        
        painter.setFont(font)
        
        if self.is_marquee_selecting:
            painter.setPen(QPen(QColor(*Styles.hex_to_rgb(Styles.Colors.nothing_accent) + (200,)), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(*Styles.hex_to_rgb(Styles.Colors.nothing_accent) + (50,))))
            painter.drawRoundedRect(self.marquee_rect, Styles.Roundings.selection, Styles.Roundings.selection)

        painter.setPen(QPen(Qt.GlobalColor.red, 2))
        painter.drawLine(int(self.playhead_x_position), 0, int(self.playhead_x_position), int(self.height()))

    def copy_selected_elements(self):
        self._copied_elements = []
        for el_id in self.selected_element_ids:
            el = self.composition.get_glyph(el_id)
            if el:
                self._copied_elements.append(el.copy())

    def paste_elements(self):
        if not hasattr(self, '_copied_elements') or not self._copied_elements:
            return
        
        min_start = min(el['start'] for el in self._copied_elements)
        paste_start = self.playhead_x_position * self.ms_per_pixel
        offset = paste_start - min_start
    
        new_ids = []
        for el in self._copied_elements:
            new_el = el.copy()
            new_el['start'] = max(0, new_el['start'] + offset)
            id, _ = self.composition.new_glyph(str(new_el['track']), new_el['start'], new_el['duration'])
            self.composition.replace_glyph(id, new_el)
            new_ids.append(id)
        
        self.selected_element_ids = set(new_ids)
        self.update_element_rects_cache()
        self.elements_changed.emit()
        self.mark_elements_cache_dirty()
        self.update()
        
        self.composition.save()
    
    def control_popup(self, title, label, key, min_val=1, max_val=None):
        dialog = UI.DialogInputWindow(title, label, min_val, max_val) if max_val else UI.DialogInputWindow(title, label, min_val)
        if dialog.exec_() != QDialog.Accepted:
            return

        user_input = dialog.get_text()
        updated_glyphs = {}

        for el_id in self.selected_element_ids:
            el = self.composition.get_glyph(el_id)
            if el:
                el[key] = user_input
                updated_glyphs[el_id] = el

        self.composition.glyphs.update(updated_glyphs)

    def brightness_control_popup(self):
        self.control_popup("Brightness", "Percent", "brightness")

    def duration_control_popup(self):
        self.control_popup("Duration", "Duration (ms)", "duration", min_val=1, max_val=10000)
        
        self.update_element_rects_cache(),
        self.mark_elements_cache_dirty(),
        self.update(),
        self.elements_changed.emit()

    def wheelEvent(self, event):
        scroll_area = self.parentWidget().parentWidget()
        if not isinstance(scroll_area, QScrollArea):
            return super().wheelEvent(event)

        if event.modifiers() & Qt.ControlModifier:
            self.scale_view(+100 if event.angleDelta().y() > 0 else -100)
        else:
            delta = event.angleDelta().y()
            self._scroll_target_velocity += -delta * 0.2
            
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()

    def _update_smooth_scroll(self):
        scroll_area = self.parentWidget().parentWidget()
        h_bar = scroll_area.horizontalScrollBar()

        self._scroll_velocity += (self._scroll_target_velocity - self._scroll_velocity) * 0.2
        h_bar.setValue(int(h_bar.value() + self._scroll_velocity))

        self._scroll_target_velocity *= 0.9

        if abs(self._scroll_velocity) < 0.1 and abs(self._scroll_target_velocity) < 0.1:
            self._scroll_timer.stop()
            self._scroll_velocity = 0
            self._scroll_target_velocity = 0

    def keyPressEvent(self, event: QKeyEvent):
        consumed = False
        new_playhead_x = self.playhead_x_position
        
        if event.matches(QKeySequence.Copy):
            self.copy_selected_elements()
            event.accept()
            return
        
        elif event.matches(QKeySequence.Paste):
            self.paste_elements()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Space:
            self.playback_manager.toggle_playback(self.get_playhead_ms())
            consumed = True

        elif event.key() == Qt.Key.Key_Left:
            new_playhead_x -= self.playhead_move_increment
            consumed = True

        elif event.key() == Qt.Key.Key_Right:
            new_playhead_x += self.playhead_move_increment
            consumed = True

        elif event.text().isdigit() or event.text() == '-':
            digit_char = event.text()
            target_track_index = -1

            if digit_char.isdigit():
                digit_val = int(digit_char)
                
                if 1 <= digit_val <= 9:
                    target_track_index = digit_val - 1
                
                elif digit_val == 0:
                    target_track_index = min(9, len(self.track_names))
            
            elif digit_char == '-':
                target_track_index = 11 # 11th track

            if 0 <= target_track_index < len(self.track_names):
                el_x_start_px = self.playhead_x_position
                el_x_start = el_x_start_px * self.ms_per_pixel

                duration = self.composition.duration_ms
                
                if self.playback_manager.is_playing:
                    el_x_start -= 120

                if el_x_start + duration > self.total_content_width * self.ms_per_pixel:
                    duration = max(1, self.total_content_width * self.ms_per_pixel - el_x_start)

                if duration >= 1:
                    track_name_to_use = self.track_names[target_track_index]
    
                    id, _ = self.composition.new_glyph(
                        track_name_to_use,
                        el_x_start,
                        duration
                    )

                    self.selected_element_ids.clear()
                    self.selected_element_ids.add(id) 
                    self.elements_changed.emit()
                    self.composition.save()
                    
                    self.update_element_rects_cache()
                    self.mark_elements_cache_dirty()
                
                consumed = True

        if consumed and event.key() != Qt.Key.Key_Space :
            self.playhead_x_position = max(0.0, min(new_playhead_x, self.total_content_width))

            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                if self.playback_manager.is_playing:
                    self.playback_manager.stop_playback()

            self.update()
            self.ensure_playhead_visible()

        if consumed:
            event.accept()
        else:
            super().keyPressEvent(event)
        
    def mousePressEvent(self, event: QMouseEvent):
        self._mouse_pressed = True
        if self._mouse_pressed:
            self.tooltip_delay_timer.stop()
            self.animated_tooltip.hide_tooltip()
            self._tooltip_pending_element = None
            self._tooltip_current_element = None

        if self.rect().contains(event.pos()):
            self.setFocus()

        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        id, clicked_element, edge = self.get_element_at(event.pos())
        is_ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier

        if clicked_element:
            if edge in ('resize_left', 'resize_right'):
                if id not in self.selected_element_ids:
                    self.selected_element_ids.clear()
                    self.selected_element_ids.add(id)

                self.dragging_element_info = {
                    'element_id': id,
                    'mode': edge,
                    'start_mouse_x': event.pos().x(),
                    'original_start': clicked_element['start'],
                    'original_duration': clicked_element['duration'],
                    'selection_orig_state': {eid: self.composition.get_glyph(eid).copy() for eid in self.selected_element_ids}
                }
                
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            
            elif edge == 'body':
                if is_ctrl_pressed:
                    if id in self.selected_element_ids:
                        self.selected_element_ids.remove(id)

                    else:
                        self.selected_element_ids.add(id)
                
                elif id not in self.selected_element_ids:
                    self.selected_element_ids.clear()
                    self.selected_element_ids.add(id)

                self.dragging_element_info = {
                    'mode': 'move',
                    'start_mouse_x': event.pos().x(),
                    'selection_orig_state': {eid: self.composition.get_glyph(eid).copy() for eid in self.selected_element_ids}
                }
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            
            self.update()
            return event.accept()

        ruler_or_waveform_area_rect = QRectF(0, 0, self.width(), Styles.Metrics.Tracks.ruler_height + Styles.Metrics.Waveform.height)
        
        if ruler_or_waveform_area_rect.contains(event.pos()):
            if not self.playback_manager.is_playing:
                new_playhead_x = max(0.0, min(float(event.x()), self.total_content_width))
                if self.playhead_x_position != new_playhead_x:
                    self.playhead_x_position = new_playhead_x
                    self.update()
                    self.ensure_playhead_visible()
            
            event.accept()
            return
        
        self.is_marquee_selecting = True
        self.marquee_start_pos = event.pos()
        self.marquee_rect = QRectF(self.marquee_start_pos, self.marquee_start_pos)
        
        if not is_ctrl_pressed:
            self.selected_element_ids.clear()
        
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.dragging_element_info:
            mode = self.dragging_element_info['mode']
            
            delta_x = event.pos().x() - self.dragging_element_info['start_mouse_x']
            delta_ms = delta_x * self.ms_per_pixel
            
            if mode == 'move':
                main_element_id = list(self.dragging_element_info['selection_orig_state'].keys())[0]
                main_element = self.composition.get_glyph(main_element_id)
                
                for el_id, orig_state in self.dragging_element_info['selection_orig_state'].items():
                    element = self.composition.get_glyph(el_id)

                    if element:
                        new_start = orig_state['start'] + delta_ms
                        new_start = max(Styles.Metrics.Tracks.label_width * self.ms_per_pixel, min(new_start, self.total_content_width * self.ms_per_pixel - element['duration']))
                        element['start'] = new_start
                        
                        self.updated_elements[el_id] = element

                if self.active_popup and self.active_popup.isVisible():
                    self.active_popup.deleteLater()
                
                pos = self.mapToGlobal(QPointF(self.get_element_rect(main_element).center().x(), self.get_element_rect(main_element).bottom()).toPoint())
                popup = UI.ValuePopup(f"{main_element['start']:.0f} ms", pos, parent=self)
                popup.show()
                self.active_popup = popup
            
            elif mode in ('resize_left', 'resize_right'):
                main_element_id = self.dragging_element_info['element_id']
                main_element = self.composition.get_glyph(main_element_id)
                orig_main_state = self.dragging_element_info['selection_orig_state'][main_element_id]

                if mode == 'resize_left':
                    new_start = orig_main_state['start'] + delta_ms
                    new_duration = orig_main_state['duration'] - delta_ms
                    
                    if new_duration < 1:
                        new_duration = 1
                        new_start = main_element['start'] + main_element['duration'] - 1

                    actual_delta_ms = new_start - orig_main_state['start']
                    
                    for el_id, orig_state in self.dragging_element_info['selection_orig_state'].items():
                        element = self.composition.get_glyph(el_id)
                        
                        if element and orig_state['duration'] - actual_delta_ms >= 1:
                            element['start'] = orig_state['start'] + actual_delta_ms
                            element['duration'] = orig_state['duration'] - actual_delta_ms
                        
                        self.updated_elements[el_id] = element

                elif mode == 'resize_right':
                    new_duration = orig_main_state['duration'] + delta_ms

                    if new_duration < 1:
                        new_duration = 1

                    actual_delta_duration = new_duration - orig_main_state['duration']

                    for el_id, orig_state in self.dragging_element_info['selection_orig_state'].items():
                        element = self.composition.get_glyph(el_id)
                        
                        if element and orig_state['start'] + orig_state['duration'] + actual_delta_duration <= self.total_content_width * self.ms_per_pixel:
                            element['duration'] = orig_state['duration'] + actual_delta_duration
                        
                        self.updated_elements[el_id] = element
                
                if self.active_popup and self.active_popup.isVisible():
                    self.active_popup.deleteLater()
                
                pos = self.mapToGlobal(QPointF(self.get_element_rect(main_element).center().x(), self.get_element_rect(main_element).bottom()).toPoint())
                popup = UI.ValuePopup(f"{main_element['duration']:.0f} ms", pos, parent=self)
                popup.show()
                
                self.active_popup = popup
            
            QTimer.singleShot(0, self.update)
        
        elif self.is_marquee_selecting:
            self.marquee_rect = QRectF(self.marquee_start_pos, event.pos()).normalized()
            
            current_selection = set()
            for id, element in self.composition.glyphs.items():
                if self.marquee_rect.intersects(self.get_element_rect(element)):
                    current_selection.add(id)

            self.selected_element_ids = current_selection
            self.update()

        else:
            id, hovered_element, edge = self.get_element_at(event.pos())
            if hovered_element:
                if self._mouse_pressed:
                    return
                
                info = (
                    f"Start: {hovered_element.get('start', 0):.0f} ms\n"
                    f"Duration: {hovered_element.get('duration', 0):.0f} ms\n"
                    f"Brightness: {hovered_element.get('brightness', 0)}\n"
                    f"Effect: {hovered_element.get('effect', {}).get('name')}"
                )
                
                global_pos = self.mapToGlobal(event.pos())
                rounded_pos = QPoint(global_pos.x() // 5, global_pos.y() // 5)

                if (self._tooltip_pending_element != hovered_element or
                    self._tooltip_last_global_pos != rounded_pos or
                    not self.tooltip_delay_timer.isActive()):

                    self.tooltip_delay_timer.stop()
                    self._tooltip_pending_element = hovered_element
                    self._tooltip_pending_pos = global_pos + QPoint(10, 10)
                    self._tooltip_pending_text = info
                    self._tooltip_last_global_pos = rounded_pos
                    self.tooltip_delay_timer.start(1000)

            else:
                self._tooltip_pending_element = None
                self._tooltip_last_global_pos = None
                self._tooltip_current_element = None
                self.tooltip_delay_timer.stop()
                if self.animated_tooltip.is_tooltip_visible():
                    self.animated_tooltip.hide_tooltip()
            
            if edge in ('resize_left', 'resize_right'):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            
            elif edge == 'body':
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._mouse_pressed = False
        
        if event.button() == Qt.MouseButton.LeftButton:
            if self.updated_elements != {}:
                self.composition.glyphs.update(self.updated_elements)
                self.updated_elements = {}
            
            if self.dragging_element_info:
                self.setCursor(Qt.CursorShape.ArrowCursor)

                self.composition.save()
                self.update_element_rects_cache()
                self.mark_elements_cache_dirty()
                self.elements_changed.emit()
                
                self.dragging_element_info = None
                
                self.update()
                event.accept()
            
            elif self.is_marquee_selecting:
                self.is_marquee_selecting = False
                self.marquee_rect = QRectF()
                self.elements_changed.emit()
                self.update()
                event.accept()
            
            else:
                super().mouseReleaseEvent(event)
        
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent):
        try:
            id, clicked_element, _ = self.get_element_at(event.pos()) 
            if not clicked_element:
                return

            Utils.ui_sound("MenuOpen")
            self.update()

            self.context_menu = QMenu(self)
            self.context_menu.setStyleSheet(Styles.Menus.RMB_element) 
            self.context_menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.context_menu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.context_menu.setWindowFlags(self.context_menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint) 
            
            delete_action = QAction("Delete", self)
            delete_action.triggered.connect(self.delete_selected_elements)
            self.context_menu.addAction(delete_action)

            copy_action = QAction("Copy", self)
            copy_action.triggered.connect(self.copy_selected_elements)
            self.context_menu.addAction(copy_action)

            paste_action = QAction("Paste", self)
            paste_action.triggered.connect(self.paste_elements)
            self.context_menu.addAction(paste_action)

            self.context_menu.addSeparator()
            
            change_brightness_action = QAction("Change Brightness...", self)
            change_brightness_action.triggered.connect(self.brightness_control_popup)
            self.context_menu.addAction(change_brightness_action)

            change_duration_action = QAction("Change Duration...", self)
            change_duration_action.triggered.connect(
                self.duration_control_popup
            )
            self.context_menu.addAction(change_duration_action)

            self.context_menu.addSeparator()

            effect_submenu = self.context_menu.addMenu("Effect")
            effect_submenu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            effect_submenu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            effect_submenu.setWindowFlags(effect_submenu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint) 

            has_non_segmented = any(
                not ModelSegments.get(model_to_code(self.composition.model), {}).get(self.composition.get_glyph(sel_id)["track"])
                for sel_id in self.selected_element_ids
            )

            if has_non_segmented:
                effects = {
                    name: config for name, config in GlyphEffects.EffectsConfig.items()
                    if not config.get("segmented", False)
                }
            
            else:
                effects = GlyphEffects.EffectsConfig

            for effect_name, config in effects.items():
                single_effect_menu = effect_submenu.addMenu(effect_name)
                single_effect_menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                single_effect_menu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
                single_effect_menu.setWindowFlags(single_effect_menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint) 
                preview_widget = UI.EffectPreviewWidget(effect_name, config)

                def on_apply_requested(name, settings, element = clicked_element):
                    for sel_id in self.selected_element_ids:
                        element = self.composition.get_glyph(sel_id)
                        
                        if element:
                            result = GlyphEffects.effectCallback(name, settings, element)
                            self.composition.replace_glyph(sel_id, result)
                    
                    self.composition.save()
                    self.elements_changed.emit()
                    self.update()
                
                preview_widget.apply_requested.connect(on_apply_requested)

                widget_action = QWidgetAction(single_effect_menu)
                widget_action.setDefaultWidget(preview_widget)

                single_effect_menu.addAction(widget_action)

            self.context_menu.addSeparator()

            self.context_menu.aboutToHide.connect(lambda: Utils.ui_sound("MenuClose"))
            self.context_menu.exec(event.globalPos())
            self.context_menu.deleteLater()
            self.context_menu = None
        
        except Exception as e:
            QMessageBox.critical(None, "Context menu failed to show.", f"Report this error to chips047: {str(e)}")
            return
    
    def get_element_at(self, pos):
        for id, element in reversed(self.composition.glyphs.items()):
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

    def delete_selected_elements(self):
        if not self.selected_element_ids:
            return
        
        ids_to_delete = list(self.selected_element_ids)
        for id in ids_to_delete:
            self.composition.delete_glyph(id)
        
        self.selected_element_ids.clear()
        self.update_element_rects_cache()
        self.elements_changed.emit()
        self.mark_elements_cache_dirty()
        self.update()

    def ensure_playhead_visible(self):
        scroll_widget = self.parentWidget()
        scroll_area = scroll_widget.parentWidget() if scroll_widget else None
        
        if isinstance(scroll_area, QScrollArea):
            h_bar = scroll_area.horizontalScrollBar(); vp_w = scroll_area.viewport().width()
            cur_scroll = h_bar.value(); margin = vp_w * 0.15
            
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
        if self.audio_data is None: return

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

    def update_elements_pixmap(self, visible_rect):
        w, h = int(visible_rect.width()), int(visible_rect.height())
        if w <= 0 or h <= 0:
            self._elements_pixmap = None
            self._elements_pixmap_rect = None
            return
        
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)
        cache_painter = QPainter(pixmap)
        cache_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        white_brush = QBrush(QColor(*Styles.hex_to_rgb(Styles.Colors.element_background)))
        red_pen = QPen(QColor(*Styles.hex_to_rgb(Styles.Colors.nothing_accent)), 2)
        gray_pen = QPen(QColor("#505050"), 1)
        
        for idx, (id, element) in enumerate(self.composition.glyphs.items()):
            element_rect = self._element_rects[idx] if idx < len(self._element_rects) else self.get_element_rect(element)
            if not element_rect.intersects(visible_rect):
                continue
            
            local_rect = QRectF(element_rect)
            local_rect.moveLeft(local_rect.left() - visible_rect.left())
            path = QPainterPath(); path.addRoundedRect(local_rect, 10, 10)
            
            if id in self.selected_element_ids:
                cache_painter.fillPath(path, white_brush)
                cache_painter.setPen(red_pen)
            
            else:
                cache_painter.fillPath(path, white_brush)
                cache_painter.setPen(gray_pen)
            
            cache_painter.drawPath(path)
        
        cache_painter.end()
        self._elements_pixmap = pixmap
        self._elements_pixmap_rect = QRectF(visible_rect)
        self._elements_cache_dirty = False

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

        self.top_status_label = QLabel("Cassette - Preview (0.1)")
        self.top_status_label.setFont(Utils.NDot(14))
        self.top_status_label.setMinimumHeight(Styles.Metrics.element_height) 
        self.top_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.top_status_label.setStyleSheet(Styles.Other.status_bar)
        self.overall_layout.addWidget(self.top_status_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: #1e1e1e; border-radius: 10px; }
            QScrollBar:horizontal {border: 1px solid #4A4A4A; background: #323232; height: 10px; margin: 0px; border-radius: 7px}
            QScrollBar::handle:horizontal {background: #787878; min-width:  25px; border-radius: 7px}
            QScrollBar:vertical {border: 1px solid #4A4A4A; background: #323232; width: 10px; margin: 0px; border-radius: 7px}
            QScrollBar::handle:vertical {background: #787878; min-height: 25px; border-radius: 7px;}
        """)
        
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content_widget = ScrollableContent(self.scroll_area, self.top_status_label, self, None)
        self.scroll_area.setWidget(self.content_widget)
        self.overall_layout.addWidget(self.scroll_area, 1)

        self.export_button.clicked.connect(self.export_ringtone)
        self.content_widget.audio_state_changed.connect(self.update_ui_on_audio_state_change)
        self.content_widget.elements_changed.connect(self.update_export_button_state)
        self.glyph_dur_control.valueChanged.connect(self.content_widget.change_duration)
        self.brightness_control.valueChanged.connect(self.content_widget.change_brightness)
        self.playspeed_button.state_changed.connect(self.on_playspeed_changed)
        self.default_effect.state_changed.connect(self.on_default_effect_change)
    
    def on_eject_button_clicked(self):
        self.back_to_main_menu_requested.emit()
    
    def export_ringtone(self):
        dialog = UI.ExportDialogWindow("Export?", self.content_widget.composition)
        if dialog.exec_() == QDialog.Accepted:
            self.content_widget.composition.export()
            Utils.ui_sound("Export")

    def on_mini_preview_clicked(self, normalized_pos):
        self.content_widget.scroll_to_normalized_position(normalized_pos)

    def on_playspeed_changed(self, text_part, speed_value):
        if self.content_widget:
            self.content_widget.playback_manager.set_playback_speed_multiplier(speed_value)
        
        if self.top_status_label:
            self.content_widget.set_status_message(f"Playback speed is now {text_part}", 2000)

    def on_default_effect_change(self, text_part, effect_value):
        self.content_widget.composition.set_default_effect(effect_value)

    def update_ui_on_audio_state_change(self):
        audio_loaded = self.content_widget.audio_data is not None
        self.mini_preview_widget.setVisible(audio_loaded)
        
        if audio_loaded:
            self.mini_preview_widget.set_audio_data(self.content_widget.audio_data, self.content_widget.sampling_rate)
        else:
            self.mini_preview_widget.set_audio_data(None, 0)
        
        self.content_widget.composition.save()
        self.update_export_button_state()

    def update_export_button_state(self):
        audio_loaded = self.content_widget.audio_data is not None
        elements_exist = len(self.content_widget.composition.glyphs) > 0
        self.export_button.setEnabled(audio_loaded and elements_exist)

    def initialize_compositor(self, audio_path, composition):
        self.content_widget.track_names = [f"{i + 1}" for i in range(composition.track_number)]
        self.content_widget.composition = composition
                
        if self.content_widget.playback_manager.is_playing: 
            self.content_widget.playback_manager.stop_playback()
                
        self.content_widget.playback_manager.load_audio(audio_path)
        Utils.ui_sound("Load")
        QTimer.singleShot(0, lambda: self.content_widget.scale_view(0))