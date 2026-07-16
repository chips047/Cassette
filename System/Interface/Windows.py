import os
import re
import sys
import math
import numpy
import random
import platform
import traceback
import mimetypes
import webbrowser

from pathlib import Path
from loguru import logger
from collections.abc import Callable

from PyQt6.QtGui import (
    QIcon,
    QCursor,
    QPixmap,
    QDropEvent,
    QMatrix4x4,
    QQuaternion,
    QWheelEvent,
    QSurfaceFormat,
    QDragEnterEvent
)

from PyQt6.QtCore import (
    Qt,
    QRect,
    QSize,
    QPoint,
    QTimer,
    QEvent,
    QObject,
    QThread,
    QSettings,
    QEventLoop,
    pyqtSignal,
    QElapsedTimer
)

from PyQt6.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QFileDialog,
    QApplication,
    QStackedWidget,
    QGraphicsOpacityEffect
)

from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from OpenGL import GL
from OpenGL.GL import shaders

from System.Common import (
    Dev,
    Utils,
    Styles,
    Constants
)

from System.Services import (
    Audio,
    Player,
    Encoder
)

from System.Interface import (
    Timing,
    Labels,
    Widgets,
    Buttons,
    Sliders,
    Selectors,
    Textboxes,
    Checkboxes
)

from System.Services import ProjectSaver

from System.Interface.Animation import Lifecycle
from System.Interface.Animation import LoomEngine

from System.Interface.WindowAnimationStyles import (
    WindowAnimationStyle,
    play_sound_choice
)

# Helpers

def build_column(
        title:   str,
        widgets: list[QWidget]
    ) -> QVBoxLayout:

    column = QVBoxLayout()
    column.addWidget(Labels.DescriptionLabel(title))

    for widget in widgets:
        column.addWidget(widget)

    column.addStretch()
    return column

def make_time_textbox() -> Textboxes.Textbox:
    textbox = Textboxes.Textbox(":time", max_length = 5)
    textbox.setStyleSheet(Styles.Controls.FloatingTextBox)
    textbox.setFixedHeight(32)
    textbox.setFixedWidth(56)
    
    return textbox

def make_fade_textbox(placeholder: str) -> Textboxes.Textbox:
    textbox = Textboxes.Textbox("number", 0, 5000, placeholder = placeholder)
    textbox.setStyleSheet(Styles.Controls.FloatingTextBox)
    textbox.setFixedHeight(32)
    
    return textbox

@Dev.track_ram
class FloatingWindowGPU(Lifecycle.LoomAnimationMixin, QOpenGLWidget):
    shared_shader_program = None

    def __init__(
            self,
            title:                           str,
            parent:                          QWidget                | None = None,
            margin:                          int                    | None = None,
            dialog:                          bool                          = True,
            stays_on_top:                    bool                          = True,
            max_tilt_angle:                  int                           = 20,
            animation_style:                 str                    | None = None,
            enable_audioplayer_effects:      bool                          = True,
            enable_advanced_beat_animations: bool                          = False,
            enable_tilt:                     bool                          = True,
            enable_open_animation:           bool                          = True,
            enable_close_animation:          bool                          = True,
            start_position:                  QPoint                 | None = None
        ):

        super().__init__(parent)

        self.player                = Player.player
        self.enable_tilt           = enable_tilt
        self.max_tilt_angle        = max_tilt_angle

        self.result                = None
        self.event_loop            = None
        self.allow_exit            = False
        self.drag_pos              = None
        self.is_ready              = False
        self.is_closing            = False
        self.was_cancelled         = False
        self.start_position        = start_position
        
        self.shake_frequency_ms    = 80
        self.shake_deviation       = 2.0

        self.animation_style       = animation_style or Constants.current_settings["animation_style"]

        self.enable_open_animation           = enable_open_animation
        self.enable_close_animation          = enable_close_animation
        self.enable_advanced_beat_animations = enable_advanced_beat_animations
        self.enable_transition_audio_effects = enable_audioplayer_effects

        self.target_margin = margin or 300
        self.margin_x      = self.target_margin
        self.margin_y      = self.target_margin

        self.anim_group = None

        self.prepare_fmt()
        self.apply_attributes(dialog, stays_on_top)
        self.setup_layout(title)
        self.setup_animation_properties()
        self.setup_timers()

    
    def showEvent(self, event) -> None:
        super().showEvent(event)

        if self.is_ready:
            return

        self.adjustSize()
        self.center_window()
        self.is_ready = True

        scale_restriction = self.maximum_scale()
        self.scale_property.set_max_value(scale_restriction)

        if self.enable_open_animation:
            self.open_window()

    # Setup

    def prepare_fmt(self) -> None:
        surface_format = QSurfaceFormat()
        
        surface_format.setVersion(4, 1)
        surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        surface_format.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions, False)
        surface_format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
        surface_format.setAlphaBufferSize(8)

        if Constants.current_settings.get("msaa"):
            surface_format.setSamples(Constants.current_settings["msaa"])

        self.setFormat(surface_format)

    def apply_attributes(
            self,
            dialog:       bool,
            stays_on_top: bool
        ) -> None:

        flags = self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint

        if dialog:
            flags |= Qt.WindowType.Dialog
        
        else:
            flags |= Qt.WindowType.Tool

        if stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_PaintOnScreen, False)

    def setup_layout(self, title: str) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(self.margin_x, self.margin_y, self.margin_x, self.margin_y)
        main_layout.setSpacing(0)

        self.content_widget = QWidget(self)
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(12)

        main_layout.addWidget(self.content_widget)

        if title:
            self.title_label = Labels.TitleLabel(title)
            self.content_layout.addWidget(self.title_label)
        
        else:
            self.title_label = None

        self.adjustSize()

    def setup_animation_properties(self) -> None:
        self.animations_active   = False

        self.current_tilt_x = 0.0
        self.current_tilt_y = 0.0

        self.target_tilt_x  = 0.0
        self.target_tilt_y  = 0.0

        self.tilt_smoothing       = float(Constants.current_settings["window_hover_smoothing"])
        self.bpm_peak_scale       = 1.03
        self.is_pulsing           = False
        self.pulse_original_speed = 1.0

        if not self.animations_enabled:
            logger.debug("Not creating animated properties: animations are disabled.")
            return

        self.content_opacity_effect = QGraphicsOpacityEffect(self.content_widget)
        self.content_opacity_effect.setOpacity(0.0)
        self.content_widget.setGraphicsEffect(self.content_opacity_effect)

        self.x_offset_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "xOffset",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD
        )

        self.y_offset_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "yOffset",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD
        )

        self.z_offset_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "zOffset",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD
        )

        self.rotation_x_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "rotationX",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD
        )

        self.rotation_y_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "rotationY",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD
        )

        self.rotation_z_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "rotationZ",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD
        )

        self.scale_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "scale",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.MULTIPLY,
            max_value  = self.maximum_scale()
        )

        self.opacity_background_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "opacityBackground",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.MULTIPLY
        )

        self.opacity_content_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "opacityContent",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.MULTIPLY,
            on_change  = self.on_opacity_content_changed
        )

        self.window_geometry_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "geometry",
            base_value = QRect(),
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.setGeometry
        )

        LoomEngine.ui_engine.updated.connect(self.update_tilt_smoothing)

        self.animations_active = True

    def on_opacity_content_changed(self, value: float) -> None:
        self.content_opacity_effect.setOpacity(value)
        self.update()

    def update_tilt_smoothing(self) -> None:
        if not self.animations_active:
            return

        if self.max_tilt_angle <= 0 or self.tilt_smoothing <= 0 or not self.enable_tilt:
            return

        local_pos          = self.mapFromGlobal(QCursor.pos())
        widget_rect        = self.content_widget.rect()
        content_rect_local = widget_rect.translated(self.content_widget.pos())

        if content_rect_local.contains(local_pos):
            center_x = self.width()  / 2
            center_y = self.height() / 2

            x_norm = -(local_pos.x() - center_x) / center_x
            y_norm =  (local_pos.y() - center_y) / center_y

            self.target_tilt_x = y_norm  * self.max_tilt_angle
            self.target_tilt_y = -x_norm * self.max_tilt_angle

        self.current_tilt_x += (self.target_tilt_x - self.current_tilt_x) * self.tilt_smoothing
        self.current_tilt_y += (self.target_tilt_y - self.current_tilt_y) * self.tilt_smoothing

        self.update()

    def setup_timers(self) -> None:
        self.shake_timer = Timing.Timer(
            self.shake_frequency_ms,
            self.apply_shake_step,
            parent = self
        )

        if self.bpm_animations_enabled:
            if self.enable_advanced_beat_animations:
                self.player.beat_heavy.connect(self.beat_heavy_animation)
                self.player.beat_normal.connect(self.beat_normal_animation)
            
            else:
                Player.bpm_informer.beat_4.connect(self.bpm_tick_animation)

    # Properties

    @property
    def animations_enabled(self) -> bool:
        return Constants.current_settings.get("floating_window_animations", True)

    @property
    def bpm_animations_enabled(self) -> bool:
        return self.animations_enabled and Constants.current_settings.get("bpm_animations", True) and self.player is not None

    # Animations

    def pulse_title(
            self,
            peak_scale:  float = 1.2,
            duration_ms: int   = 100
        ) -> None:

        if not self.animations_enabled or not self.title_label:
            return

        self.title_label.pulse_scale(peak_scale, duration_ms)

    def animate_resize(
            self,
            target_width:  int,
            target_height: int
        ) -> None:

        if not self.animations_active or not self.animations_enabled:
            self.resize(target_width + (self.margin_x * 2), target_height + (self.margin_y * 2))
            return

        self.window_geometry_property.set_target(
            value           = QRect(
                self.x(), self.y(),
                target_width  + (self.margin_x * 2),
                target_height + (self.margin_y * 2)
            ),
            duration_ms     = 500,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    def bpm_tick_animation(self) -> None:
        if not self.player.is_playing:
            return

        audio_level = self.player.get_current_audio_level()

        if audio_level < 0.08:
            return

        interval_ms = Player.bpm_informer.get_interval(4)

        QApplication.setCursorFlashTime(interval_ms)

        if Constants.current_settings.get("window_bpm_animation_style") == "pulse":
            keyframes = [
                (0.0, 1.0),
                (0.5, self.bpm_peak_scale + self.squish(audio_level)),
                (1.0, 1.0)
            ]

        else:
            keyframes = [
                (0.0, self.bpm_peak_scale + self.squish(audio_level)),
                (1.0, 1.0)
            ]

        self.scale_property.play_curve(
            keyframes                  = keyframes,
            duration_ms                = interval_ms,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def beat_normal_animation(self, strength: float) -> None:
        if not self.animations_active:
            return

        self.rotation_z_property.play_curve(
            keyframes       = [
                (0.0, 0.0),
                (0.5, strength * (5 if random.random() > 0.5 else -5)),
                (1.0, 0.0)
            ],
            duration_ms     = 1500,
            easing_function = LoomEngine.Easing.bouncy
        )

    def beat_heavy_animation(self, strength: float) -> None:
        if not self.animations_active:
            return

        self.y_offset_property.play_curve(
            keyframes                  = [
                (0.0, 0.0),
                (0.5, strength * random.choice([0.1, -0.1])),
                (1.0, 0.0)
            ],
            duration_ms                = 400,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def move_start_animation(self) -> None:
        if not self.animations_active or not self.animations_enabled:
            return

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 1.03)],
            duration_ms     = 250,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        self.pulse_title(1.15, 500)

    def move_end_animation(self) -> None:
        if not self.animations_active or not self.animations_enabled:
            return

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 0.97)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    def start_shake(self) -> None:
        if not self.animations_active:
            return

        self.shake_timer.start()

    def stop_shake(self) -> None:
        if not self.animations_active:
            return

        self.shake_timer.stop()

        self.rotation_x_property.set_target(0.0, duration_ms = 400, easing_function = LoomEngine.Easing.ease_out_cubic)
        self.rotation_y_property.set_target(0.0, duration_ms = 400, easing_function = LoomEngine.Easing.ease_out_cubic)

    def apply_shake_step(self) -> None:
        deviation = self.shake_deviation
        target_x  = random.uniform(-deviation, deviation)
        target_y  = random.uniform(-deviation, deviation)

        self.rotation_x_property.set_target(target_x, duration_ms = self.shake_frequency_ms, easing_function = LoomEngine.Easing.ease_out_cubic)
        self.rotation_y_property.set_target(target_y, duration_ms = self.shake_frequency_ms, easing_function = LoomEngine.Easing.ease_out_cubic)

    def wobble(self) -> None:
        if not self.animations_active or not self.animations_enabled:
            return

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.0), (0.5, 1.05), (1.0, 1.0)],
            duration_ms     = 500,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    def animation_random_rotate(self) -> None:
        if not self.animations_active or not self.animations_enabled:
            return

        self.rotation_z_property.play_curve(
            keyframes       = [
                (0.0, 0),
                (0.5, self.period_randomizer((-6, -3), (3, 6))),
                (1.0, 0)
            ],
            duration_ms     = 350,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    # Style Playback

    def current_style(self) -> WindowAnimationStyle:
        return WindowAnimationStyle(self.animation_style)

    def open_window(self) -> None:
        self.ensurePolished()

        if self.layout():
            self.layout().activate()

        super().adjustSize()
        self.center_window()

        self.is_ready = True

        self.play_stage_sound("open")

        if not self.animations_active or not self.animations_enabled:
            return

        self.current_style().play(
            stage = "open",
            owner = self,
            size  = self.get_window_size()
        )
    
    def get_window_size(self) -> tuple[int, int]:
        hint = self.content_widget.sizeHint()

        if hint.isValid() and not self.is_ready:
            return hint.width(), hint.height()

        geometry = self.content_widget.geometry()
        return geometry.width(), geometry.height()

    def request_close(self) -> None:
        if not self.enable_close_animation:
            return

        self.play_stage_sound("close")

        if not self.animations_active or not self.animations_enabled:
            self.really_close()
            return

        self.current_style().play(
            stage = "close",
            owner = self,
            size  = self.get_window_size()
        )

    def play_disturb_animation(self) -> None:
        self.play_stage_sound("disturb")

        if not self.animations_active or not self.animations_enabled:
            return

        self.current_style().play(
            stage = "disturb",
            owner = self,
            size  = self.get_window_size()
        )

    # Render

    def initializeGL(self) -> None:
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClearColor(0, 0, 0, 0)

        if not self.shared_shader_program:
            vertex_shader   = shaders.compileShader(Constants.FLOATING_WINDOW_VS, GL.GL_VERTEX_SHADER)
            fragment_shader = shaders.compileShader(Constants.FLOATING_WINDOW_FS, GL.GL_FRAGMENT_SHADER)
            
            self.__class__.shared_shader_program = shaders.compileProgram(
                vertex_shader,
                fragment_shader,
                validate = False
            )

        vertices = numpy.array(
            [
                1.0,  1.0, 0.0, 1.0, 1.0,
                1.0, -1.0, 0.0, 1.0, 0.0,
                -1.0, -1.0, 0.0, 0.0, 0.0,
                -1.0,  1.0, 0.0, 0.0, 1.0
            ], dtype = numpy.float32
        )

        indices = numpy.array([0, 1, 3, 1, 2, 3], dtype = numpy.uint32)

        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)
        self.ebo = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.vao)

        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STATIC_DRAW)

        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL.GL_STATIC_DRAW)

        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 20, GL.ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 20, GL.ctypes.c_void_p(12))
        GL.glEnableVertexAttribArray(1)

        GL.glBindVertexArray(0)

        self.location_size         = GL.glGetUniformLocation(self.shared_shader_program, "u_size")
        self.location_radius       = GL.glGetUniformLocation(self.shared_shader_program, "u_radius")
        self.location_border_px    = GL.glGetUniformLocation(self.shared_shader_program, "u_borderThicknessPixels")
        self.location_rect_color   = GL.glGetUniformLocation(self.shared_shader_program, "u_rectColor")
        self.location_border_color = GL.glGetUniformLocation(self.shared_shader_program, "u_borderColor")
        self.location_rect_alpha   = GL.glGetUniformLocation(self.shared_shader_program, "u_rectAlpha")
        self.location_border_alpha = GL.glGetUniformLocation(self.shared_shader_program, "u_borderAlpha")
        self.location_global_alpha = GL.glGetUniformLocation(self.shared_shader_program, "u_globalAlpha")
        self.location_mvp          = GL.glGetUniformLocation(self.shared_shader_program, "u_curr_mvp")

    def paintGL(self) -> None:
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glUseProgram(self.shared_shader_program)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)

        content_rect    = self.content_widget.geometry()
        content_width   = float(content_rect.width())
        content_height  = float(content_rect.height())

        if content_width < 1 or content_height < 1:
            return

        mvp_final = self.calculate_matrix()

        GL.glUniform2f(self.location_size,         content_width, content_height)
        GL.glUniform1f(self.location_radius,        16.0)
        GL.glUniform1f(self.location_border_px,     2.0)
        GL.glUniform4f(self.location_rect_color,    0.17, 0.17, 0.17, 1.0)
        GL.glUniform4f(self.location_border_color,  0.25, 0.25, 0.25, 1.0)
        GL.glUniform1f(self.location_rect_alpha,    self.opacity_background_property.value)
        GL.glUniform1f(self.location_border_alpha,  self.opacity_background_property.value)
        GL.glUniform1f(self.location_global_alpha,  1.0)

        GL.glUniformMatrix4fv(self.location_mvp, 1, GL.GL_FALSE, mvp_final.data())

        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)

    def calculate_matrix(
            self,
            content_w: float | None = None,
            content_h: float | None = None
        ) -> QMatrix4x4:
        
        content_w = content_w or self.content_widget.width()
        content_h = content_h or self.content_widget.height()

        mvp    = QMatrix4x4()
        fov    = 45.0
        z_dist = 3.0
        aspect = self.width() / self.height()

        mvp.perspective(fov, aspect, 0.1, 100.0)
        mvp.translate(0.0, 0.0, -z_dist)

        visible_height_at_z = 2.0 * math.tan(math.radians(fov / 2.0)) * z_dist
        pixel_unit          = visible_height_at_z / self.height()

        if self.animations_active:
            rotation = QQuaternion.fromEulerAngles(
                self.rotation_x_property.value + self.current_tilt_x,
                self.rotation_y_property.value + self.current_tilt_y,
                self.rotation_z_property.value
            )

            mvp.rotate(rotation)
            mvp.translate(self.x_offset_property.value, self.y_offset_property.value, self.z_offset_property.value)
            mvp.scale(self.scale_property.value)

        mvp.scale((content_w * pixel_unit) / 2.0, (content_h * pixel_unit) / 2.0)
        return mvp

    # Events

    
    def closeEvent(self, event) -> None:
        if self.allow_exit:
            super().closeEvent(event)
            return
    
        if self.is_closing:
            event.ignore()
            return
    
        self.is_closing    = True
        self.was_cancelled = True
    
        event.ignore()
        self.request_close()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.title_label:
            local_pos = self.content_widget.mapFrom(self, event.pos())
            if not self.title_label.geometry().contains(local_pos):
                return
        
        elif sys.platform != "linux" and not self.content_widget.geometry().contains(event.pos()):
            return

        if sys.platform == "linux":
            self.windowHandle().startSystemMove()
        
        self.drag_pos = event.globalPosition().toPoint() - self.pos()

        self.move_start_animation()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() == Qt.MouseButton.LeftButton and
            self.drag_pos is not None                    and
            sys.platform != "linux"
        ):
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self.drag_pos:
            self.move_end_animation()

        self.drag_pos = None

    # Utils

    def get_optimal_offset(
            self,
            width:  int,
            height: int,
            limit:  int = 500
        ) -> tuple[float, float]:
        
        scale_x = limit / max(width,  limit)
        scale_y = limit / max(height, limit)

        start_offset_x = self.period_randomizer(
            (-0.35 * scale_x, -0.2 * scale_x),
            ( 0.2  * scale_x,  0.35 * scale_x)
        )

        start_offset_y = self.period_randomizer(
            (-0.5 * scale_y, -0.2 * scale_y),
            ( 0.2 * scale_y,  0.5  * scale_y)
        )

        return start_offset_x, start_offset_y

    def chaos_mode(self) -> None:
        for widget in self.content_widget.findChildren(QWidget):
            delta_x    = random.randint(-10, 10)
            delta_y    = random.randint(-10, 10)
            delta_size = random.randint(-10, 10)

            widget.move(widget.x() + delta_x, widget.y() + delta_y)
            widget.resize(widget.width() + delta_size, widget.height() + delta_size)

    def on_ok(self) -> None:
        if self.is_closing:
            return

        self.is_closing    = True
        self.was_cancelled = False

        self.request_close()

    def on_cancel(self) -> None:
        if self.is_closing:
            return

        self.is_closing    = True
        self.was_cancelled = True

        self.request_close()

    def adjustSize(self) -> None:
        self.ensurePolished()

        if self.layout():
            self.layout().activate()

        content_size = self.content_widget.sizeHint()

        if self.is_ready:
            self.animate_resize(content_size.width(), content_size.height())
            return

        screen_geo       = QApplication.primaryScreen().availableGeometry()

        available_width  = screen_geo.width()
        available_height = screen_geo.height()

        content_width    = content_size.width()
        content_height   = content_size.height()

        max_margin_x     = (available_width  - 46 * 2 - content_width)  // 2
        max_margin_y     = (available_height - 46 * 2 - content_height) // 2
        margin_x         = min(max_margin_x, 300)
        margin_y         = min(max_margin_y, 300)

        self.margin_x    = min(margin_x, self.margin_x)
        self.margin_y    = min(margin_y, self.margin_y)

        self.layout().setContentsMargins(
            self.margin_x, 
            self.margin_y, 
            self.margin_x, 
            self.margin_y
        )

        final_width  = content_width  + (self.margin_x * 2)
        final_height = content_height + (self.margin_y * 2)

        self.resize(final_width, final_height)

    def set_bpm_peak_size(self, coefficient: float) -> None:
        self.bpm_peak_scale = coefficient

    def period_randomizer(self, *periods) -> int | float:
        function = random.uniform if isinstance(periods[0][0], float) else random.randint
        return function(*random.choice(periods))

    def center_window(self) -> QRect:
        if self.start_position:
            final_rect = QRect(
                self.start_position.x() - self.margin_x,
                self.start_position.y() - self.margin_y,
                self.width(),
                self.height()
            )
            
            self.setGeometry(final_rect)
            
            return final_rect

        window        = QApplication.activeWindow()
        window_center = window.geometry().center() if window else QApplication.primaryScreen().geometry().center()

        final_rect = QRect(
            window_center.x() - self.width()  // 2,
            window_center.y() - self.height() // 2,
            self.width(), self.height()
        )
        
        self.setGeometry(final_rect)
        
        return final_rect

    def player_pulse(
            self,
            duration:         int   = 300,
            pulse_peak_speed: float = 1.2
        ) -> None:

        if self.is_pulsing:
            return

        self.is_pulsing           = True
        self.pulse_original_speed = self.player.speed
        duration_half             = int(duration / 2)

        self.player.set_speed(pulse_peak_speed, duration_half)
        
        QTimer.singleShot(
            duration_half,
            lambda: self.player.set_speed(
                self.pulse_original_speed,
                duration_half,
                on_finish = self.finish_pulse
            )
        )

    def finish_pulse(self) -> None:
        self.is_pulsing = False

    def play_stage_sound(self, stage: str) -> None:
        pulse_speed_by_stage = {
            "open":    None,
            "close":   0.5,
            "disturb": 2.0
        }

        pulse_speed = pulse_speed_by_stage[stage]

        if self.enable_transition_audio_effects and self.player and self.player.is_playing:
            if pulse_speed is None:
                self.player_pulse()
            else:
                self.player_pulse(400, pulse_speed)

            return

        play_sound_choice(
            source      = self.current_style().sound_for(stage),
            setting_key = "floating_window_sounds"
        )

    def squish(self, x: float, power: float = 1.2) -> float:
        return 0.075 * (x ** power)

    def get_window_size(self) -> tuple[int, int]:
        geometry = self.content_widget.geometry()
        return geometry.width(), geometry.height()

    def maximum_scale(self) -> float:
        content_width  = self.content_widget.width()
        content_height = self.content_widget.height()

        if content_width <= 0 or content_height <= 0:
            return 1.0

        real_width  = self.geometry().width()
        real_height = self.geometry().height()

        screen_geo       = QApplication.primaryScreen().availableGeometry()
        available_width  = screen_geo.width()
        available_height = screen_geo.height()

        is_full_width  = real_width  >= (available_width  - 92)
        is_full_height = real_height >= (available_height - 92)

        tilt_angle_rad = math.radians(self.max_tilt_angle) if self.enable_tilt else 0.0
        cos_tilt       = math.cos(tilt_angle_rad)
        sin_tilt       = math.sin(tilt_angle_rad)

        bounding_width  = content_width * cos_tilt + content_height * sin_tilt
        bounding_height = content_width * sin_tilt + content_height * cos_tilt

        max_scale_x = float("inf") if is_full_width  else real_width  / bounding_width
        max_scale_y = float("inf") if is_full_height else real_height / bounding_height

        scale       = min(max_scale_x, max_scale_y)
        final_scale = scale - 0.1

        if final_scale == float("inf"):
            final_scale = 2.0

        logger.debug(f"Scale property was restricted to {final_scale}")

        return final_scale

    def really_close(self) -> None:
        if self.animations_active:
            LoomEngine.ui_engine.updated.disconnect(self.update_tilt_smoothing)
            
            self.shake_timer.stop()
            self.shake_timer = None

            self.animations_active = False

            if self.bpm_animations_enabled and not self.enable_advanced_beat_animations:
                Player.bpm_informer.beat_4.disconnect(self.bpm_tick_animation)
        
        LoomEngine.ui_engine.unbind_owner(self)

        self.allow_exit = True
        self.close()

        if self.event_loop:
            self.event_loop.quit()

    def exec(self) -> bool:
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.show()

        self.event_loop = QEventLoop()
        self.event_loop.exec()

        self.deleteLater()
        return not self.was_cancelled

    def accept(self) -> None:
        self.result = True
        self.on_ok()

    def reject(self) -> None:
        self.result = False
        self.on_cancel()

# Simple Dialogs

class DialogInputWindow(FloatingWindowGPU):
    def __init__(
            self,
            title:       str                    = "Input Dialog",
            placeholder: str                    = "Type something...",
            min_number:  int                    = 0,
            max_number:  int                    = 100,
            max_length:  int                    = 100,
            input_type:  str                    = "number"
        ):

        super().__init__(title)

        self.close_attempt_count = 0

        self.input_field = Textboxes.Textbox(input_type, min_number, max_number, max_length)
        self.input_field.setMinimumWidth(160)
        self.input_field.setPlaceholderText(placeholder)

        self.button_row = Buttons.ButtonRow(
            [
                (Buttons.ButtonWithOutline, random.choice(Constants.NO_TEXTS), self.on_cancel),
                (Buttons.NothingButton,     random.choice(Constants.OK_TEXTS), self.on_ok)
            ]
        )

        self.button_row.get_button_by_number(1).block_glitch_sound()

        self.content_layout.addWidget(self.input_field)
        self.content_layout.addLayout(self.button_row)

        self.input_field.returnPressed.connect(self.on_ok)

    def on_ok(self) -> None:
        if not self.input_field.text():
            self.button_row.get_button_by_number(1).start_glitch()
            self.play_disturb_animation()

            self.process_ee()            

            return

        super().on_ok()
    
    def process_ee(self) -> None:
        self.close_attempt_count += 1

        if random.random() > 0.5:
            return
        
        if self.close_attempt_count == 50:
            Player.ui_player.play_sound("Packs/NOK/WAYD")

            if self.title_label:
                self.title_label.setText("What are you doing?")

        if self.close_attempt_count == 70:
            Player.ui_player.play_sound("Packs/NOK/HCYLWY")

            if self.title_label:
                self.title_label.setText("???")

        if self.close_attempt_count > 70:
            self.chaos_mode()

        if self.close_attempt_count == 100 and self.title_label:
            Player.ui_player.play_sound("Packs/NOK/ONYD")
            self.title_label.setText("Dividing by zero: 3")

            QTimer.singleShot(1000, lambda: self.title_label.setText("Dividing by zero: 2"))
            QTimer.singleShot(2000, lambda: self.title_label.setText("Dividing by zero: 1"))
            QTimer.singleShot(2100, lambda: Player.ui_player.play_sound("Packs/NOK/Charging"))
            QTimer.singleShot(2500, lambda: self.title_label.setText("LMAO"))
            QTimer.singleShot(3000, lambda: 1 / 0)

    def get_text(self) -> str:
        return self.input_field.text()

class ExportDialogWindow(FloatingWindowGPU):
    selectionChanged = pyqtSignal(str)

    def __init__(
            self,
            composition: ProjectSaver.Composition
        ):

        super().__init__("Export?")

        self.composition = composition

        original_model = Constants.DEVICES[composition.model].short_name
        choices        = Constants.DEVICES[composition.model].port_variants + [original_model]

        self.combobox          = Selectors.Selector(choices, default_index = len(choices) - 1)
        self.watermark_textbox = Textboxes.Textbox("text", max_length = 12, placeholder = "Dot Watermark")

        button_row = Buttons.ButtonRow(
            [
                (Buttons.ButtonWithOutline, random.choice(Constants.NO_TEXTS), self.on_cancel),
                (Buttons.ButtonWithOutline, "Export to every model",           self.export_all),
                (Buttons.NothingButton,     "Tape it",                         self.export)
            ]
        )

        self.content_layout.addWidget(self.combobox)
        self.content_layout.addWidget(self.watermark_textbox)
        self.content_layout.addLayout(button_row)

    def export(self) -> None:
        Player.ui_player.play_sound("App/ExportStart")

        model     = self.combobox.current_text()
        watermark = self.watermark_textbox.text() or "Cassette"

        self.composition.export(
            watermark,
            Constants.NUMBER_TO_CODE[model],
            open_folder = True
        )

    def export_all(self) -> None:
        if self.is_closing:
            return

        watermark = self.watermark_textbox.text() or "Cassette"
        self.on_ok()
        self.composition.export_all(watermark)

class DialogWindow(FloatingWindowGPU):
    def __init__(self, title: str):
        super().__init__(title)

        button_row = Buttons.ButtonRow(
            [
                (Buttons.ButtonWithOutline, random.choice(Constants.NO_TEXTS), self.on_cancel),
                (Buttons.NothingButton,     random.choice(Constants.OK_TEXTS), self.on_ok)
            ]
        )

        self.content_layout.addLayout(button_row)

class SegmentEditor(FloatingWindowGPU):
    def __init__(
            self,
            title:       str,
            segment_num: int | None  = None,
            defaults                 = None
        ):

        super().__init__(title)

        self.segmented_bar = Widgets.SegmentedBar(segment_num, defaults)

        upper_button_row = Buttons.ButtonRow(
            [
                (Buttons.ButtonWithOutline, "Enable all", self.segmented_bar.enable_all),
                (Buttons.ButtonWithOutline, "Disable all", self.segmented_bar.disable_all),
                (Buttons.ButtonWithOutline, "Zebra",       self.segmented_bar.zebra)
            ]
        )

        lower_button_row = Buttons.ButtonRow(
            [
                (Buttons.ButtonWithOutline, "Nah",   self.on_cancel),
                (Buttons.NothingButton,     "Apply", self.on_ok)
            ]
        )

        self.content_layout.addWidget(self.segmented_bar)
        self.content_layout.addLayout(upper_button_row)
        self.content_layout.addLayout(lower_button_row)

        self.segmented_bar.segment_changed.connect(self.wobble)

    def segments(self) -> list:
        return self.segmented_bar.active

class ErrorWindow(FloatingWindowGPU):
    def __init__(
            self,
            title:       str,
            description: str,
            button_text: str = "Cool"
        ):

        super().__init__(title)

        ok_button   = Buttons.NothingButton(button_text)
        copy_button = Buttons.ButtonWithOutline("Copy error details")

        self.description_label = Labels.DescriptionLabel(description, 600)

        self.content_layout.addWidget(self.description_label)
        self.content_layout.addWidget(copy_button)
        self.content_layout.addWidget(ok_button)

        ok_button.clicked.connect(self.on_ok)
        copy_button.clicked.connect(self.copy_error_details)

        self.content_widget.setMaximumSize(900, 800)

        self.title_label.start_glitch()
    
    def copy_error_details(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.description_label.text())

    def open_window(self) -> None:
        if random.random() > 0.995:
            self.adjustSize()
            self.center_window()
            self.is_ready = True

            Player.ui_player.play_sound("Packs/NOK/Death")

            self.title_label.start_glitch(0.01, 18)

            self.scale_property.play_curve(
                keyframes       = [(0.0, 1.5), (1.0, 1.0)],
                duration_ms     = 12000,
                easing_function = LoomEngine.Easing.ease_out_quart
            )

            self.opacity_content_property.set_base(1.0)

            self.opacity_background_property.play_curve(
                keyframes       = [(0.0, 0.0), (1.0, 1.0)],
                duration_ms     = 3000,
                easing_function = LoomEngine.Easing.linear
            )

        else:
            super().open_window()

# Fun Windows

class UpdateWindow(FloatingWindowGPU):
    def __init__(
            self,
            version:   str,
            changelog: str,
            url:       str = Constants.GITHUB_LINK
        ) -> None:

        super().__init__(f"Cassette {version}")

        changelog = re.sub(r'(?m)^### \*\*Cassette v\d+\.\d+\.\d+\*\*\s*\r?\n', '',      changelog)
        changelog = re.sub(r'(?m)^>\s*(.*?)\s*$',                               r'`\1`', changelog)
        changelog = re.sub(r'### \*\*(.*?)\*\*',                                r'`\1`', changelog)
        changelog = re.sub(r'\*\*(.*?)\*\*',                                    r'`\1`', changelog)
        changelog = re.sub(r'(?m)^-\s+',                                        '`•` ',  changelog)

        self.update_label = Labels.DescriptionLabel("`A new update on GitHub.`\n" + changelog, 700)

        scroll_area = Widgets.ElasticScrollArea(self)
        scroll_area.setFixedSize(700, 400)
        scroll_area.add_widget(self.update_label)

        self.close_button  = Buttons.NothingButton("Cool")
        self.github_button = Buttons.ButtonWithOutline("Check it out on GitHub")
        
        self.close_button.clicked.connect(self.on_ok)
        self.github_button.clicked.connect(lambda: webbrowser.open(url))

        self.content_layout.addWidget(scroll_area)
        self.content_layout.addWidget(self.github_button)
        self.content_layout.addWidget(self.close_button)

class About(FloatingWindowGPU):
    def __init__(self, more_info: bool = False):
        super().__init__(f"Cassette {open(Utils.get_resource_path('version')).read()} by chips047")

        if more_info:
            text = (
                f"System {sys.platform} {platform.machine()}"
                f"Python: {sys.version}"
            )
        
        else:
            text = (
                "The best open - source compositor. Currently in active development!\n\n"
                "`Inspirations and credits`\n"
                "- UI sounds from `R.E.P.O.` by `semiwork`.\n"
                "- Open sound from `The Upturned` by `Zeekers`.\n"
                "- Open sounds from `Simulacra` by `Kaigan Games`.\n"
                "- Sounds from `Pacific Drive` by `Ironwood Studios`.\n\n"
                "Made with care, way too much profiling, and a genuine love for smooth interfaces."
            )

        self.about_label = Labels.DescriptionLabel(text, 500)

        self.image_pixmap = QPixmap("System/Assets/Image/Version.png").scaled(
            500, 500,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self.image_label = QLabel()
        self.image_label.setPixmap(self.image_pixmap)

        ok_button     = Buttons.NothingButton("Five Stars?")
        github_button = Buttons.ButtonWithOutline("Check for updates on GitHub")

        ok_button.clicked.connect(self.on_ok)
        github_button.clicked.connect(self.on_github)

        self.content_layout.addWidget(self.about_label)
        self.content_layout.addWidget(self.image_label)
        self.content_layout.addWidget(github_button)
        self.content_layout.addWidget(ok_button)

    def on_github(self) -> None:
        github = Constants.GITHUB_LINK

        if random.random() < 0.95:
            webbrowser.open(github)
            return

        fox_image = Utils.get_fox_image()
        webbrowser.open(fox_image if fox_image else github)

class WalterWindow(FloatingWindowGPU):
    def __init__(self):
        super().__init__("walter.")

        self.path_open   = "System/Assets/Image/Walter"
        self.path_closed = "System/Assets/Image/WalterClosed"

        self.is_walter_closed = True

        self.walter        = QPixmap(self.path_open)
        self.walter_closed = QPixmap(self.path_closed)

        self.label = Labels.DescriptionLabel("Turn on the Waltuh, yes, click it.")
        self.image = Labels.Image(self.walter_closed)

        self.content_layout.addWidget(self.image)
        self.content_layout.addWidget(self.label)

        self.chaos_timer = Timing.Timer(20,   self.chaos_mode, parent = self)
        self.stop_timer  = Timing.Timer(8500, self.chaos_timer.stop, True, parent = self)

        self.image.clicked.connect(self.switch_walter)

    def switch_walter(self) -> None:
        self.is_walter_closed = not self.is_walter_closed

        current_pixmap = self.walter_closed if self.is_walter_closed else self.walter
        self.image.update_image(current_pixmap)

        if self.is_walter_closed:
            self.label.setText("Don't do that.")
            self.chaos_timer.stop()
            self.stop_timer.stop()
            
            return

        Player.ui_player.play_sound("Packs/NOK/HEVCharger", speed = 1.0, enable_tone_randomizer = False)
        self.label.setText("Such a good boy.")
        self.chaos_timer.start()
        self.stop_timer.start()

        if random.random() > 0.4:
            self.spam_errors()

    def spam_errors(self) -> None:
        for i in range(12):
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("walthu")
            msg.setText("waltuyh")
            msg.setInformativeText("the waltuh")
            msg.move(100 + i * 30, 100 + i * 30)
            msg.show()

        for i in range(12):
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("walthu")
            msg.setText("waltuyh")
            msg.setInformativeText("the waltuh")
            msg.move(1000 - i * 30, 1000 - i * 30)
            msg.show()

# Settings

class Settings(FloatingWindowGPU):
    def __init__(self) -> None:
        super().__init__("Settings", max_tilt_angle = 10)

        self.settings          = QSettings("chips047", "Cassette")
        self.pages             = {}
        self.controls          = {}
        self.max_scroll_width  = 0

        self.nav_widget        = self.setup_navigation()
        self.stacked_widget    = QStackedWidget()
        self.ok_button         = Buttons.NothingButton("Apply!")
        self.cancel_button     = Buttons.ButtonWithOutline("Cancel")

        self.stacked_widget.setStyleSheet("background: transparent;")
        self.title_label.setFont(Utils.NType(21))

        self.build_layout()
        self.connect_signals()

    # Setup

    def setup_navigation(self) -> QWidget:
        navigation_widget = QWidget()
        navigation_widget.setFixedHeight(40)
        navigation_widget.setStyleSheet(f"background: {Styles.Colors.ThirdBackground}; border-radius: 18px;")

        navigation_layout = QHBoxLayout(navigation_widget)

        navigation_layout.setContentsMargins(4, 4, 4, 4)
        navigation_layout.setSpacing(6)
        navigation_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.nav_layout = navigation_layout

        return navigation_widget

    def build_layout(self) -> None:
        button_row = QHBoxLayout()
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)

        self.content_layout.addWidget(self.nav_widget)
        self.content_layout.addWidget(self.stacked_widget)
        self.content_layout.addLayout(button_row)

    def connect_signals(self) -> None:
        self.ok_button.clicked.connect(self.apply_and_close)
        self.cancel_button.clicked.connect(self.on_cancel)

    # Pages

    def change_page(self, page_widget: QWidget) -> None:
        self.stacked_widget.setCurrentWidget(page_widget)

        for page_name, (button, widget) in self.pages.items():
            button.setActive(widget == page_widget)

    def init_settings(self, setting_components: dict) -> None:
        scroll_areas = []
        first_page   = None

        for page_name, components in setting_components.items():
            page_area = self.create_page(page_name, components, scroll_areas)

            if not first_page:
                first_page = page_area

        self.apply_uniform_width(scroll_areas)

        if first_page:
            self.change_page(first_page)

    def create_page(
            self,
            page_name:    str,
            components:   list,
            scroll_areas: list
        ) -> QWidget:

        page_area = Widgets.ElasticScrollArea(self)
        page_area.setFixedHeight(360)

        navigation_button = Buttons.NavButton(page_name)
        navigation_button.clicked.connect(lambda _, w = page_area: self.change_page(w))
        self.nav_layout.addWidget(navigation_button)

        self.pages[page_name] = (navigation_button, page_area)

        for component_config in components:
            widget = self.create_input_widget(component_config)

            if widget:
                page_area.add_widget(widget)
                self.controls[component_config["key"]] = widget

        self.stacked_widget.addWidget(page_area)
        scroll_areas.append(page_area)

        return page_area

    def apply_uniform_width(self, scroll_areas: list) -> None:
        for scroll_area in scroll_areas:
            required_width = scroll_area.get_required_width()

            if required_width > self.max_scroll_width:
                self.max_scroll_width = required_width

        for scroll_area in scroll_areas:
            scroll_area.setFixedWidth(self.max_scroll_width)

    # Widgets

    def create_input_widget(self, config: dict) -> QWidget | None:
        value     = self.settings.value(config["key"])
        type_name = config["type"]

        if type_name == "checkbox":
            return self.create_checkbox_widget(value, config)

        if type_name == "slider":
            return self.create_slider_widget(value, config)

        if type_name == "textbox":
            return self.create_textbox_widget(value, config)

        if type_name == "selector":
            return self.create_selector_widget(value, config)

        return None

    def create_checkbox_widget(self, value: str, config: dict) -> QWidget:
        state = str(value).lower() == "true" if value is not None else config["default"]

        return Checkboxes.CheckboxWithLabel(
            config["title"],
            config["description"],
            state
        )

    def create_slider_widget(self, value: str, config: dict) -> QWidget:
        slider_value = int(value or config["default"])

        return Sliders.SliderWithLabel(
            config["title"],
            config["min"],
            config["max"],
            slider_value
        )

    def create_textbox_widget(self, value: str, config: dict) -> QWidget:
        textbox_value = value or config["default"]

        return Textboxes.TextboxWithLabel(
            config["title"],
            config["min"],
            config["max"],
            textbox_value
        )

    def create_selector_widget(self, value: str, config: dict) -> QWidget:
        default_text  = config["default"] if value is None else None
        default_value = value
        
        return Selectors.SelectorWithLabel(
            config["title"],
            config["map"],
            default_text = default_text,
            default_value = default_value
        )

    # Actions

    def apply_and_close(self) -> None:
        for key, widget in self.controls.items():
            self.save_widget_value(key, widget)

        self.settings.sync()
        Constants.load_settings()
        
        self.on_ok()

    def save_widget_value(self, key: str, widget: QWidget) -> None:
        if isinstance(widget, Checkboxes.CheckboxWithLabel):
            self.settings.setValue(key, widget.isChecked())
        
        elif isinstance(widget, Sliders.SliderWithLabel):
            self.settings.setValue(key, widget.value())
        
        elif isinstance(widget, Selectors.SelectorWithLabel):
            self.settings.setValue(key, widget.current_data())
        
        elif isinstance(widget, Textboxes.TextboxWithLabel):
            self.settings.setValue(key, widget.getValue())

# Glyph Visualizer

@Dev.track_ram
class GlyphVisualizer(FloatingWindowGPU):
    def __init__(
            self,
            parent: QObject,
            model:  str
        ):

        super().__init__(
            None,
            margin                  = 50,
            max_tilt_angle          = 9,
            stays_on_top            = True,
            enable_open_animation   = False,
            enable_close_animation  = False
        )

        self.parent            = parent
        self.map_data          = Constants.DEVICES[model].visualization_map
        self.map_w, self.map_h = self.map_data["size"]

        self.visual_scale:    float = 1.0
        self.target_scale:    float = 1.0
        self.scale_smoothing: float = 0.15

        self.glyphs_gpu     = []
        self.total_segments = 0

        self.init_geometry()
        self.init_shared_buffer()

        self.scale_in()
        self.sync_size_delayed()

    def setup_timers(self) -> None:
        super().setup_timers()

        self.resize_timer = Timing.Timer(
            200,
            self.sync_size_delayed,
            single_shot = True,
            parent = self
        )

        self.timer = Timing.Timer(
            Constants.FPS_30,
            self.process_schedule,
            parent = self
        )

        self.elapsed = QElapsedTimer()

    def init_geometry(self) -> None:
        current_global_offset = 0

        for glyph_id, data in self.map_data["glyphs"].items():
            glyph = self.process_single_glyph(glyph_id, data, current_global_offset)
            self.glyphs_gpu.append(glyph)
            
            current_global_offset += glyph["segment_count"]

        self.total_segments = current_global_offset
        self.global_levels  = numpy.zeros(self.total_segments, dtype = numpy.float32)

    def init_shared_buffer(self) -> None:
        self.levels_tex = GL.glGenTextures(1)

        GL.glBindTexture(GL.GL_TEXTURE_1D, self.levels_tex)
        GL.glTexImage1D(GL.GL_TEXTURE_1D, 0, GL.GL_R32F, self.total_segments, 0, GL.GL_RED, GL.GL_FLOAT, None)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_WRAP_S,     GL.GL_CLAMP_TO_EDGE)

    def process_single_glyph(
            self,
            glyph_id:      str,
            data:          dict,
            global_offset: int
        ) -> dict:
        
        path               = Utils.parse_svg_path_data(data["svg"])
        segment_count      = data.get("segments", 1)
        position_x, position_y = data["position"]
        points_per_segment = 60

        total_length   = path.length()
        segment_length = total_length / segment_count

        all_vertices        = []
        starts, counts      = [], []
        current_vbo_offset  = 0

        for segment_index in range(segment_count):
            start_distance = segment_index       * segment_length
            end_distance   = (segment_index + 1) * segment_length

            points = []

            for i in range(points_per_segment):
                dist = start_distance + (i / (points_per_segment - 1)) * (end_distance - start_distance)
                t    = path.percentAtLength(dist)
                pt   = path.pointAtPercent(t)
                points.append(
                    [
                        pt.x() + position_x - self.map_w / 2,
                        -(pt.y() + position_y) + self.map_h / 2
                    ]
                )

            points       = numpy.array(points, dtype = numpy.float32)
            segment_verts = self.calculate_segment_geometry(points, global_offset + segment_index)

            all_vertices.append(segment_verts)
            num_verts = len(segment_verts) // 5

            starts.append(current_vbo_offset)
            counts.append(num_verts)

            current_vbo_offset += num_verts

        return {
            "id":              glyph_id,
            "vbo_data":        numpy.concatenate(all_vertices).astype(numpy.float32),
            "starts":          numpy.array(starts, dtype = numpy.int32),
            "counts":          numpy.array(counts, dtype = numpy.int32),
            "segment_count":   segment_count,
            "global_base_idx": global_offset,
            "schedule":        []
        }

    def calculate_segment_geometry(
            self,
            points:     numpy.ndarray,
            global_idx: int
        ) -> numpy.ndarray:
        
        differences = numpy.diff(points, axis = 0)
        tangents    = numpy.vstack([differences, differences[-1:]])
        normals     = numpy.stack([-tangents[:, 1], tangents[:, 0]], axis = 1)
        lengths     = numpy.linalg.norm(normals, axis = 1, keepdims = True)
        normals    /= numpy.where(lengths == 0, 1.0, lengths)

        index_float = float(global_idx)
        result      = numpy.zeros((len(points) * 2, 5), dtype = numpy.float32)

        for i, (point, normal) in enumerate(zip(points, normals)):
            result[i * 2]     = [point[0], point[1],  normal[0],  normal[1], index_float]
            result[i * 2 + 1] = [point[0], point[1], -normal[0], -normal[1], index_float]

        return result.flatten()

    def initializeGL(self) -> None:
        super().initializeGL()
        
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE)

        self.prog = shaders.compileProgram(
            shaders.compileShader(Constants.GLYPH_VS, GL.GL_VERTEX_SHADER),
            shaders.compileShader(Constants.GLYPH_FS, GL.GL_FRAGMENT_SHADER)
        )

        self.uniform_locations = {
            "mvp":        GL.glGetUniformLocation(self.prog, "mvp"),
            "thickness":  GL.glGetUniformLocation(self.prog, "uThickness"),
            "levels_tex": GL.glGetUniformLocation(self.prog, "uLevelsTex")
        }

        for glyph in self.glyphs_gpu:
            glyph["vao"], glyph["vbo"] = GL.glGenVertexArrays(1), GL.glGenBuffers(1)

            GL.glBindVertexArray(glyph["vao"])
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, glyph["vbo"])
            GL.glBufferData(GL.GL_ARRAY_BUFFER, glyph["vbo_data"].nbytes, glyph["vbo_data"], GL.GL_STATIC_DRAW)

            stride = 20

            for attribute_index, size, offset in [(0, 2, 0), (1, 2, 8), (2, 1, 16)]:
                GL.glVertexAttribPointer(attribute_index, size, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(offset))
                GL.glEnableVertexAttribArray(attribute_index)

    def paintGL(self) -> None:
        super().paintGL()
        
        GL.glUseProgram(self.prog)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_1D, self.levels_tex)
        GL.glTexSubImage1D(GL.GL_TEXTURE_1D, 0, 0, self.total_segments, GL.GL_RED, GL.GL_FLOAT, self.global_levels)
        GL.glUniform1i(self.uniform_locations["levels_tex"], 0)

        mvp = self.calculate_matrix(2.0, 2.0)
        mvp.scale(self.visual_scale, self.visual_scale, 1.0)

        GL.glUniformMatrix4fv(self.uniform_locations["mvp"], 1, GL.GL_FALSE, mvp.data())
        GL.glUniform1f(self.uniform_locations["thickness"], float(self.map_data.get("thickness", 2.2)))

        for glyph in self.glyphs_gpu:
            GL.glBindVertexArray(glyph["vao"])
            GL.glMultiDrawArrays(GL.GL_TRIANGLE_STRIP, glyph["starts"], glyph["counts"], len(glyph["starts"]))

    def scale_in(self) -> None:
        if not self.animations_active:
            return

        self.scale_property.play_curve(
            keyframes                  = [(0.0, 0.0), (1.0, 1.0)],
            duration_ms                = 1000,
            easing_function            = LoomEngine.Easing.ease_out_quart,
            multiply_duration_by_speed = False
        )

        self.scale_property.set_base(1.0)

    def scale_out(self, cleanup: bool) -> None:
        if not self.animations_active:
            if cleanup:
                self.really_close()

            return

        self.scale_property.play_curve(
            keyframes                  = [(0.0, 1.0), (1.0, 0.0)],
            duration_ms                = 500,
            easing_function            = LoomEngine.Easing.ease_in_quart,
            multiply_duration_by_speed = False,
            finished                   = self.really_close if cleanup else None
        )

    def set_schedule(self, schedule_dict: dict) -> None:
        for glyph in self.glyphs_gpu:
            glyph["schedule"] = list(schedule_dict.get(glyph["id"], {}).values())

    def play_all(self, ms_start: int = 0) -> None:
        self.virtual_time      = ms_start
        self.last_process_time = 0

        self.elapsed.start()
        self.timer.start()

    def stop_all(self) -> None:
        self.timer.stop()
        self.virtual_time      = 0
        self.last_process_time = 0
        self.global_levels.fill(0)

        self.update()

    def update_visual_scale(self) -> None:
        if abs(self.target_scale - self.visual_scale) > 0.001:
            self.visual_scale += (self.target_scale - self.visual_scale) * self.scale_smoothing
            self.update()
        
        else:
            self.visual_scale = self.target_scale

    def get_item_brightness(self, item: dict, now: float) -> float:
        if "keyframes" not in item:
            return item["brightness"]

        start    = item["start"]
        duration = item["duration"]
        progress = (now - start) / duration if duration > 0 else 1.0

        easing_name = item.get("easing", "linear")
        easing_func = Constants.VISUAL_EASINGS[easing_name]

        return self.interpolate_keyframes(item["keyframes"], progress, easing_func)

    def get_target_slice(
            self,
            item:          dict,
            base_index:    int,
            segment_count: int
        ):

        if "segments" in item:
            return base_index + numpy.array(item["segments"])

        return slice(base_index, base_index + segment_count)

    def process_schedule(self) -> None:
        real_elapsed            = self.elapsed.elapsed()
        self.virtual_time      += (real_elapsed - self.last_process_time) * self.player.speed
        self.last_process_time  = real_elapsed

        now = self.virtual_time
        self.global_levels.fill(0)

        for glyph in self.glyphs_gpu:
            base_index = glyph["global_base_idx"]

            for item in glyph["schedule"]:
                if not (item["start"] <= now <= item["start"] + item["duration"]):
                    continue

                brightness = self.get_item_brightness(item, now)
                target     = self.get_target_slice(item, base_index, glyph["segment_count"])

                self.global_levels[target] = numpy.maximum(self.global_levels[target], brightness)

        self.update()

    def interpolate_keyframes(
            self,
            keyframes:   list[tuple[float, float]],
            progress:    float,
            easing_func: Callable[[float], float]
        ) -> float:
        
        if not keyframes:
            return 0.0

        if progress <= keyframes[0][0]:
            return float(keyframes[0][1])

        if progress >= keyframes[-1][0]:
            return float(keyframes[-1][1])

        for (time_start, value_start), (time_end, value_end) in zip(keyframes, keyframes[1:]):
            if not (time_start <= progress <= time_end):
                continue

            segment_duration = time_end - time_start
            local_progress   = (progress - time_start) / segment_duration if segment_duration > 0 else 1.0

            return value_start + (value_end - value_start) * easing_func(local_progress)

        return float(keyframes[-1][1])

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta             = 0.07 if event.angleDelta().y() > 0 else -0.07
        self.target_scale = numpy.clip(self.target_scale + delta, 0.3, 4.0)
        self.visual_scale = self.target_scale

        self.resize_timer.start()
        self.update()

    def sync_size_delayed(self) -> None:
        new_w = int(self.map_w * self.target_scale) + 80
        new_h = int(self.map_h * self.target_scale) + 80
        
        self.animate_resize(new_w, new_h)

    def exit(self, cleanup: bool = True) -> None:
        self.allow_exit = True
        self.stop_all()
        self.resize_timer.stop()
        self.scale_out(cleanup)

# Tutorial

class Tutorial(FloatingWindowGPU):
    def __init__(self, path: str):
        self.player = Player.PlaybackManager()
        self.player.load_audio(path)

        super().__init__("Tutorial", enable_audioplayer_effects = False)

        self.stage = 0

        self.build_pages()
        self.initialize_ui()
        self.initialize_audio()
        self.set_bpm_peak_size(1.02)
        self.make_page()

    def build_pages(self) -> None:
        self.pages = [
            {
                "label": "Welcome to Cassette",
                "text": "Get ready."
            },
            {
                "label": "Basics",
                "text": (
                    "`Space` to play / pause.\n"
                    "`1, 2, 3, 4, 5, 6, 7, 8, 9, 0, Minus` to place a glyph. "
                    "`Del / Backspace` to delete it. `Ctrl + / -` or `Command + / -` to zoom. "
                    "`B`, `S`, `D` to quickly change the brightness, speed and duration."
                    "`Alt + LMB` to edit keyframes."
                )
            },
            {
                "label": "Basics - Mouse",
                "text": (
                    "`Right Mouse Button` to open context menu. "
                    "`Grab` the side of glyph to resize it. `Hold` to move it. "
                    "`Press` on waveform to set playback position."
                )
            },
            {
                "label": "Basics - Scroll",
                "text": "Use `Shift + Wheel` to scroll vertically. Use `Wheel` to scroll horizontally."
            },
            {
                "label": "Basics - Visualizator",
                "text": (
                    "You can move the visualizator by dragging it with `Left Mouse Button`. "
                    "You also can resize by scrolling `Wheel` while hovering over it."
                )
            },
            {
                "label": "Basics - Navigation",
                "text": "Click `Eject` to go back to the main menu."
            },
            {
                "label": "Effects - Mixing",
                "text": "You can combine effects! Place glyphs on top of each other with different effects."
            },
            {
                "label": "Shall we?",
                "text": "Now, try yourself in glyphtones creation."
            }
        ]

        self.max_stage = len(self.pages)

    def initialize_ui(self) -> None:
        self.text_label = Labels.DescriptionLabel("Hello.")
        self.text_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.text_label.setMinimumWidth(320)

        self.next_button = Buttons.NothingButton("Next?")
        self.next_button.clicked.connect(self.next_button_callback)

        self.content_layout.addWidget(self.text_label)
        self.content_layout.addWidget(self.next_button)

    def initialize_audio(self) -> None:
        self.is_audio_small = self.player.duration_ms < 30000

        if not self.is_audio_small:
            self.player.play()
            self.player.set_passes([3000], duration_ms = 2000)
            self.player.set_speed(0.0)
            self.player.set_speed(0.8, 3000)

        def stage_one():
            self.player.set_speed(0.95, 1000)
            self.player.set_passes([1000], duration_ms = 1000)

        def stage_two():
            self.player.set_speed(1.0, duration_ms = 1000)
            self.player.set_passes([1000], mix = 0.0, duration_ms = 1000)

        def stage_three():
            self.set_bpm_peak_size(1.04)

        def stage_four():
            self.set_bpm_peak_size(1.05)

        def stage_seven():
            self.player.set_speed(0.0, 4000, shutdown_on_finish = True)

        self.stage_effects = {
            1: stage_one,
            2: stage_two,
            3: stage_three,
            4: stage_four,
            7: stage_seven
        }

    def make_page(self) -> None:
        if not (0 <= self.stage < self.max_stage):
            return

        page = self.pages[self.stage]

        self.title_label.setText(page["label"])
        self.text_label.setText(page["text"])

        QTimer.singleShot(0, self.adjustSize)

    def next_button_callback(self) -> None:
        self.stage += 1
        self.animation_random_rotate()

        if self.stage >= self.max_stage:
            self.on_ok()
            return

        self.make_page()
        self.apply_stage_effects()

    def apply_stage_effects(self) -> None:
        if self.is_audio_small:
            return

        effect = self.stage_effects.get(self.stage)

        if effect:
            effect()

# Workers

@Dev.track_ram
class PrepareWorker(QObject):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.audio_path = file_path

    def run(self) -> None:
        try:
            cached_wav = Audio.ensure_wav(self.audio_path)
            self.finished.emit(cached_wav)

        except Audio.NoAudioStreams:
            self.error.emit("No audio streams found in the file.")

        except Audio.PermissionError:
            self.error.emit("Permission error while accessing the file. Please check if the file is open in another application.")

        except Audio.CorruptedFileError:
            self.error.emit("The audio file is corrupted or in an unsupported format.")

        except FileNotFoundError:
            self.error.emit("The specified audio file was not found. Maybe it was moved or deleted while the loader was running?")

        except Exception:
            self.error.emit(f"Conversion failed: {traceback.format_exc()}")

@Dev.track_ram
class LoadAudioWorker(QObject):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()

        self.audio_path = file_path

    def run(self) -> None:
        try:
            data, sample_rate = Audio.load_audio(self.audio_path)
            audio_float       = data.astype('float32')

            if audio_float.ndim > 1:
                audio_float = numpy.mean(audio_float, axis = 1)

            samples_per_pixel = len(audio_float) / 1000
            step              = max(1, int(numpy.ceil(samples_per_pixel)))
            padded_len        = ((len(audio_float) + step - 1) // step) * step
            padded            = numpy.pad(audio_float, (0, padded_len - len(audio_float)), mode = "constant")
            reshaped          = padded.reshape(-1, step)
            waveform_data     = numpy.mean(numpy.abs(reshaped), axis = 1)
            waveform_data     = Utils.gaussian_filter1d_np(waveform_data, sigma = 2)

            self.finished.emit((data, sample_rate, waveform_data))

        except Audio.CorruptedFileError:
            self.error.emit("The audio file is corrupted or in an unsupported format.")

        except Exception:
            self.error.emit(traceback.format_exc())

@Dev.track_ram
class BPMWorker(QObject):
    finished = pyqtSignal(float, object)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.audio_path = file_path

    def run(self) -> None:
        try:
            bpm, peaks = Audio.analyze_bpm_and_beats(self.audio_path)
            self.finished.emit(bpm, peaks)

        except Exception:
            self.error.emit(traceback.format_exc())

# Audio Loading Base

class AudioLoadingDialog(FloatingWindowGPU):
    def run_loading_pipeline(self, file_path: str) -> None:
        self.cached_wav = None

        self.prepare_thread = QThread(self)
        self.prepare_worker = PrepareWorker(file_path)
        self.prepare_worker.moveToThread(self.prepare_thread)
        self.prepare_thread.started.connect(self.prepare_worker.run)

        self.prepare_worker.finished.connect(self.on_prepare_success)
        self.prepare_worker.error.connect(self.on_load_failed)

        self.prepare_worker.finished.connect(self.prepare_thread.quit)
        self.prepare_worker.finished.connect(self.prepare_worker.deleteLater)
        self.prepare_thread.finished.connect(self.prepare_thread.deleteLater)

        self.prepare_thread.start()

        self.load_thread  = None
        self.load_worker  = None

    def on_prepare_success(self, cached_wav_path: str) -> None:
        self.cached_wav  = cached_wav_path

        self.load_thread = QThread(self)
        self.load_worker = LoadAudioWorker(self.cached_wav)
        self.load_worker.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.load_worker.run)

        self.load_worker.finished.connect(self.on_load_finished)
        self.load_worker.error.connect(self.on_load_failed)

        self.load_worker.finished.connect(self.load_thread.quit)
        self.load_worker.finished.connect(self.load_worker.deleteLater)
        self.load_thread.finished.connect(self.load_thread.deleteLater)

        self.load_thread.start(QThread.Priority.LowPriority)

    def on_load_finished(self, result: tuple) -> None:
        pass

    def on_load_failed(self, message: str) -> None:
        window = ErrorWindow("Load Error", message)
        window.destroyed.connect(self.reject_callback)
        window.exec()

    def cleanup_threads(self, threads: list) -> None:
        threads_to_wait = []

        for thread in threads:
            try:
                if not thread or not thread.isRunning():
                    continue

                threads_to_wait.append(thread)
                thread.quit()

            except Exception:
                pass

        if threads_to_wait:
            self.wait_and_cleanup(threads_to_wait)
        
        else:
            self.safe_delete_cache()

    def wait_and_cleanup(self, threads: list) -> None:
        for thread in threads:
            thread.wait(500)

        self.safe_delete_cache()

    def safe_delete_cache(self) -> None:
        if not self.cached_wav:
            return

        cached_wav_normalized = str(Path(self.cached_wav).resolve())
        audio_path_normalized = str(Path(self.audio_path).resolve()) if self.audio_path else None

        if cached_wav_normalized == audio_path_normalized:
            return

        try:
            if os.path.exists(self.cached_wav):
                os.unlink(self.cached_wav)
                logger.info(f"Cache deleted: {self.cached_wav}")

        except Exception as error:
            logger.warning(f"Could not delete cache yet, retrying... {error}")
            QTimer.singleShot(1000, self.safe_delete_cache)

class AudioEditorBase(AudioLoadingDialog):
    def setup_trim_section(self) -> None:
        self.trim_widget        = Widgets.TrimmingWaveformWidget()
        self.start_time_textbox = make_time_textbox()
        self.end_time_textbox   = make_time_textbox()
        self.fade_in_textbox    = make_fade_textbox("Fade in (ms)")
        self.fade_out_textbox   = make_fade_textbox("Fade out (ms)")

        self.play_icon  = QIcon("System/Assets/Icons/Audio/Play.png")
        self.pause_icon = QIcon("System/Assets/Icons/Audio/Pause.png")

        self.play_button = QPushButton()
        self.play_button.setStyleSheet("background-color: transparent; border: none;")
        self.play_button.setIcon(self.play_icon)
        self.play_button.setIconSize(QSize(36, 36))
        self.play_button.setFixedSize(36, 36)
        self.play_button.setEnabled(False)

        self.playback_timer = Timing.Timer(Constants.FPS_60, self.update_playback, parent = self)

        self.trim_widget.regionChanged.connect(self.update_textboxes)
        self.end_time_textbox.safeTextChanged.connect(self.edit_end_time)
        self.start_time_textbox.safeTextChanged.connect(self.edit_start_time)
        self.play_button.clicked.connect(self.toggle_playback)

    def build_playback_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        row.addWidget(self.start_time_textbox)
        row.addWidget(self.fade_in_textbox)
        row.addWidget(self.play_button)
        row.addWidget(self.fade_out_textbox)
        row.addWidget(self.end_time_textbox)

        return row

    # Load Pipeline

    def on_load_finished(self, result: tuple) -> None:
        try:
            data, sample_rate, waveform_data = result

            self.player.load_audio_from_data(data, sample_rate)
            self.trim_widget.set_data(data, sample_rate, waveform_data)

            self.end_time_textbox.max_number = self.trim_widget.duration
            self.end_time_textbox.setText(max(1, math.ceil(self.trim_widget.duration)))

            self.update_textboxes(self.trim_widget.start_time, self.trim_widget.end_time)

            self.play_button.setEnabled(True)
            self.on_audio_ready()

        except Exception:
            ErrorWindow("Load Error", traceback.format_exc()).exec()

    def on_audio_ready(self) -> None:
        pass

    # Trim Textbox Sync

    def update_textboxes(self, start: float, end: float) -> None:
        self.start_time_textbox.blockSignals(True)
        self.end_time_textbox.blockSignals(True)

        self.start_time_textbox.setText(int(round(start)))
        self.end_time_textbox.setText(max(1, int(round(end))))

        self.start_time_textbox.blockSignals(False)
        self.end_time_textbox.blockSignals(False)

        self.start_time_textbox.max_number = int(round(end - 1))
        self.end_time_textbox.min_number   = int(round(start))

    def edit_start_time(self) -> None:
        start_seconds = self.start_time_textbox.text()

        if not start_seconds:
            return

        self.trim_widget.set_playback_position(start_seconds)
        self.trim_widget.start_time = start_seconds
        self.trim_widget.update()

        self.end_time_textbox.min_number = start_seconds

    def edit_end_time(self) -> None:
        end_seconds   = self.end_time_textbox.text()
        start_seconds = self.start_time_textbox.text()

        if end_seconds is None or start_seconds is None:
            return

        if start_seconds >= end_seconds:
            return

        self.trim_widget.set_playback_position(start_seconds)
        self.trim_widget.end_time = end_seconds
        self.trim_widget.update()

        self.start_time_textbox.max_number = end_seconds - 1

    # Playback

    def toggle_playback(self) -> None:
        if self.player.is_playing:
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time)
        else:
            self.play_selection()

    def play_selection(self) -> None:
        current_position = self.trim_widget.playback_position

        if not (self.trim_widget.start_time <= current_position < self.trim_widget.end_time):
            current_position = self.trim_widget.start_time
            self.trim_widget.set_playback_position(current_position)

        self.player.play(current_position * 1000)
        self.play_button.setIcon(self.pause_icon)
        self.trim_widget.set_is_playing(True)
        self.playback_timer.start()

    def stop_playback(self) -> None:
        self.player.stop()
        self.play_button.setIcon(self.play_icon)
        self.trim_widget.set_is_playing(False)
        self.playback_timer.stop()

    def update_playback(self) -> None:
        if not self.player.is_playing:
            self.trim_widget.set_playback_position(0)
            self.stop_playback()
            return

        current_position_ms = self.player.get_position()

        if current_position_ms > self.trim_widget.end_time * 1000:
            self.trim_widget.set_playback_position(self.trim_widget.start_time)
            self.toggle_playback()
            return

        self.trim_widget.set_playback_position(current_position_ms / 1000)

    # Settings

    def validate_trim(self) -> bool:
        if self.end_time_textbox.is_not_valid() or not self.end_time_textbox.text():
            self.end_time_textbox.start_glitch(False)
            return False

        if self.start_time_textbox.text() is None:
            self.start_time_textbox.start_glitch(False)
            return False

        return True

    def get_trim_settings(self) -> dict:
        return {
            "start_ms": self.trim_widget.start_time * 1000,
            "end_ms":   self.trim_widget.end_time   * 1000,
            "fade_in":  self.fade_in_textbox.text(),
            "fade_out": self.fade_out_textbox.text()
        }

    # Cleanup

    def get_threads(self) -> list:
        return [self.prepare_thread, self.load_thread]

    def cleanup_audio(self) -> None:
        self.playback_timer.stop()
        self.trim_widget.audio_data = None

        if self.player.is_playing:
            self.player.set_speed(0.0, 3000)

        self.cleanup_threads(self.get_threads())

        self.prepare_worker = self.load_worker  = None
        self.prepare_thread = self.load_thread  = None

    def reject_callback(self) -> None:
        self.cleanup_audio()
        super().on_cancel()

class BPMEditorBase(AudioEditorBase):
    def setup_bpm_section(self) -> None:
        self.bpm_thread = None
        self.bpm_worker = None

        self.bpm_text              = ""
        self.bpm_number_string     = ""
        self.bpm_animation_target  = None
        self.bpm_animation_current = 120
        self.snapped_times         = None

        self.bpm_input = Textboxes.Textbox("number", 1, 400, placeholder = "Counting BPM... 120")
        self.bpm_input.setMaximumWidth(176)
        self.bpm_input.setFixedHeight(Styles.Metrics.ElementHeight)
        self.bpm_input.setStyleSheet(Styles.Controls.FloatingTextBoxRound)

        self.bpm_animation_timer = Timing.Timer(
            Constants.FPS_30,
            self.animate_bpm_spinbox,
            auto_start = True,
            parent     = self
        )

        self.bpm_remove_timer = Timing.Timer(
            0,
            self.bpm_remove_step,
            parent = self
        )

        if self.animations_active:
            self.bpm_textbox_width = LoomEngine.ui_engine.bind(
                owner      = self,
                name       = "bpmTextboxWidth",
                base_value = self.bpm_input.width(),
                mix_mode   = LoomEngine.MixMode.REPLACE,
                on_change  = self.bpm_input.setFixedWidth
            )

        self.bpm_input.safeTextChanged.connect(self.on_bpm_changed)

    # BPM Pipeline

    def on_prepare_success(self, cached_wav_path: str) -> None:
        super().on_prepare_success(cached_wav_path)
        self.start_bpm_pipeline()

    def start_bpm_pipeline(self) -> None:
        self.bpm_thread = QThread(self)
        self.bpm_worker = BPMWorker(self.cached_wav)
        self.bpm_worker.moveToThread(self.bpm_thread)
        self.bpm_thread.started.connect(self.bpm_worker.run)

        self.bpm_worker.finished.connect(self.on_bpm_finished)
        self.bpm_worker.error.connect(lambda message: ErrorWindow("BPM error", message).exec())

        self.bpm_worker.finished.connect(self.bpm_thread.quit)
        self.bpm_worker.finished.connect(self.bpm_worker.deleteLater)
        self.bpm_thread.finished.connect(self.bpm_thread.deleteLater)

        self.bpm_thread.start(QThread.Priority.LowPriority)

    def on_bpm_finished(self, bpm: float, peaks) -> None:
        try:
            self.bpm_ready(bpm, peaks)

        except Exception:
            ErrorWindow("BPM Error", traceback.format_exc()).exec()

    def bpm_ready(self, bpm: float, snapped_times) -> None:
        self.snapped_times = snapped_times
        self.bpm_animation_timer.stop()

        if bpm:
            bpm_value              = round(bpm)
            self.bpm_text          = "Counting BPM "
            self.bpm_number_string = str(bpm_value)

            self.bpm_input.setPlaceholderText(f"{self.bpm_text}{self.bpm_number_string}")

            remove_interval = round(60000 / bpm / 8)
            self.bpm_remove_timer.start(remove_interval)
            return

        self.bpm_text          = "Counting BPM FAILURE"
        self.bpm_number_string = ""

        self.bpm_input.setPlaceholderText(self.bpm_text)
        self.bpm_remove_timer.start(100)

        if random.randint(1, 500) == 500:
            Player.ui_player.play_sound("Packs/NOK/Gambling")

    # BPM animations

    def get_perfect_bpm_width(self) -> int:
        text       = str(self.bpm_input.text() or self.bpm_input.placeholderText() or "BPM")
        metrics    = self.bpm_input.fontMetrics()
        text_width = metrics.horizontalAdvance(text)

        return round(text_width + 33)

    def shrink_bpm_input(self) -> None:
        if not self.animations_active:
            return

        self.bpm_textbox_width.set_target(
            value           = self.get_perfect_bpm_width(),
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        QTimer.singleShot(290, self.on_bpm_animation_end)

    def on_bpm_animation_end(self) -> None:
        self.bpm_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def animate_bpm_spinbox(self) -> None:
        if not self.bpm_animation_target:
            self.bpm_animation_target = numpy.random.randint(60, 180)

        if self.bpm_animation_current == self.bpm_animation_target:
            self.bpm_animation_target = numpy.random.randint(60, 180)

        if self.bpm_animation_current < self.bpm_animation_target:
            self.bpm_animation_current += 1

        elif self.bpm_animation_current > self.bpm_animation_target:
            self.bpm_animation_current -= 1

        self.bpm_input.setPlaceholderText(f"Counting BPM {self.bpm_animation_current}")

    def finalize_bpm_placeholder(self) -> None:
        if self.bpm_number_string:
            self.bpm_input.setText(self.bpm_number_string)

        self.bpm_input.setPlaceholderText("BPM")

    def bpm_remove_step(self) -> None:
        if self.bpm_text:
            self.bpm_text = self.bpm_text[1:]
            self.bpm_input.setPlaceholderText(f"{self.bpm_text}{self.bpm_number_string}")
            
            return

        self.bpm_remove_timer.stop()

        self.finalize_bpm_placeholder()
        self.shrink_bpm_input()

    def on_bpm_changed(self, value: int) -> None:
        if not value or int(value) < 1:
            return

        Player.bpm_informer.set_bpm(int(value))

    # Settings

    def get_bpm_value(self) -> int:
        return int(self.bpm_input.text() or 120)

    def get_bpm_settings(self) -> dict:
        return {
            "bpm":   self.get_bpm_value(),
            "beats": self.snapped_times
        }

    # Cleanup

    def get_threads(self) -> list:
        return [*super().get_threads(), self.bpm_thread]

    def cleanup_audio(self) -> None:
        self.bpm_animation_timer.stop()
        self.bpm_remove_timer.stop()

        super().cleanup_audio()

        self.bpm_worker = None
        self.bpm_thread = None

# Audio Setup Dialog

class AudioSetupDialog(BPMEditorBase):
    def __init__(self, audio_path: str):
        self.audio_path = audio_path
        self.filename   = audio_path.split("/")[-1]

        super().__init__(
            "Audio",
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.saved_settings = {}

        self.title_label.setText(self.filename)

        self.setup_audio_layout()
        self.run_loading_pipeline(audio_path)

        self.adjustSize()

    def setup_audio_layout(self) -> None:
        self.setup_trim_section()
        self.setup_bpm_section()

        self.beat_counter = 0

        self.model_selector = Selectors.Selector(["1", "2", "2a", "3a", "4a", "4b"])
        self.cancel_button  = Buttons.ButtonWithOutline("Cancel")
        self.ok_button      = Buttons.NothingButton("Ok")

        self.ok_button.setMaximumWidth(56)
        self.cancel_button.setMaximumWidth(80)
        self.model_selector.setMinimumWidth(240)
        self.ok_button.setEnabled(False)

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(8)
        settings_layout.addWidget(self.bpm_input)
        settings_layout.addWidget(self.model_selector)
        settings_layout.addStretch()
        settings_layout.addWidget(self.cancel_button)
        settings_layout.addWidget(self.ok_button)

        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.reject_callback)

        Player.bpm_informer.beat_16.connect(self.update_title_beat)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(self.build_playback_row())
        self.content_layout.addLayout(settings_layout)

    def on_audio_ready(self) -> None:
        self.ok_button.setEnabled(True)

    def toggle_playback(self) -> None:
        if self.player.is_playing:
            self.title_label.setText(self.filename)
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time)
        
        else:
            self.play_selection()

    def stop_playback(self) -> None:
        super().stop_playback()
        self.beat_counter = 0

    def update_title_beat(self) -> None:
        if not self.player.is_playing:
            return

        current_position_seconds = self.player.get_position() / 1000
        self.title_label.setText(f"{current_position_seconds:.3f}")

        audio_level = self.player.get_current_audio_level()
        
        if audio_level < 0.03:
            return

        self.beat_counter = (self.beat_counter + 1) % 4

        if self.beat_counter == 0:
            self.pulse_title(peak_scale = 1.4, duration_ms = 200)

        else:
            self.pulse_title(peak_scale = 1.1, duration_ms = 120)

    # Settings

    def really_close(self) -> None:
        Player.bpm_informer.beat_16.disconnect(self.update_title_beat)
        super().really_close()

    def accept_callback(self) -> None:
        if not self.validate_trim():
            self.ok_button.start_glitch()
            return

        self.settings = self.get_settings()

        self.cleanup_audio()
        super().on_ok()

    def get_settings(self) -> dict:
        return {
            "audio": {**self.get_trim_settings(), **self.get_bpm_settings()},
            "model": Constants.NUMBER_TO_CODE[self.model_selector.current_text()]
        }

# Glyphtone Editor

class GlyphtoneEditor(AudioEditorBase):
    def __init__(self, audio_path: str):
        self.audio_path = audio_path

        super().__init__(
            "Glyphtone Editor",
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.saved_settings = {}
        self.folder_id      = None

        self.setup_ui()
        self.run_loading_pipeline(audio_path)

        self.adjustSize()

    def setup_ui(self) -> None:
        self.setup_trim_section()

        self.cancel_button = Buttons.ButtonWithOutline("Cancel")
        self.ok_button     = Buttons.NothingButton("Confirm")

        self.ok_button.setEnabled(False)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.cancel_button)
        bottom_layout.addWidget(self.ok_button)

        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.reject_callback)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(self.build_playback_row())
        self.content_layout.addLayout(bottom_layout)

    def on_audio_ready(self) -> None:
        self.ok_button.setEnabled(True)

    def accept_callback(self) -> None:
        if not self.validate_trim():
            self.ok_button.start_glitch()
            return

        trim = self.get_trim_settings()

        self.saved_settings = {
            **trim,
            "duration": self.trim_widget.end_time - self.trim_widget.start_time
        }

        if self.folder_id is None:
            self.folder_id = random.randint(0, 99999999)

        source        = self.audio_path
        output        = Utils.get_user_path(f"Editor/{self.folder_id}/Cropped.ogg", "Cassette/Songs")
        output_folder = Utils.get_user_path(f"Editor/{self.folder_id}", "Cassette/Songs")

        Encoder.trim_glyphs_ogg(
            source,
            output,
            int(self.saved_settings["start_ms"]),
            int(self.saved_settings["end_ms"]),
            self.fade_in_textbox.text()  or 0,
            self.fade_out_textbox.text() or 0
        )

        self.on_ok()
        Utils.open_file(output_folder)

# Import Window

class ImportWindow(BPMEditorBase):
    def __init__(self):
        self.audio_path = None
        self.save_path  = None
        self.cached_wav = None

        self.prepare_thread   = None
        self.load_thread      = None
        
        self.drag_loop_sound  = None

        super().__init__(
            "Import",
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.setAcceptDrops(True)

        self.setup_import_ui()
        self.adjustSize()
    
    def ask_for_file(
            self,
            types: list[str],
            type_name: str
        ):
        
        options = QFileDialog.Option.ReadOnly

        file_path = None
    
        dialog = QFileDialog(
            self,
            "Open Audio File",
            "",
            f"{type_name} ({' '.join(types)});;All Files (*)"
        )
        
        dialog.setOptions(options)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            file_path = dialog.selectedFiles()[0]
        
        return file_path
    
    def ask_for_audio(self):
        file_path = self.ask_for_file(
            [
                "*.wav", "*.mp3", "*.ogg",
                "*.flac", "*.opus", "*.mp4",
                "*.mkv", "*.mov"
            ],
            "Audiofile"
        )

        if not file_path:
            return
        
        self.audio_path = file_path
        self.audio_path_button.setText(file_path.split("/")[-1])

        self.run_loading_pipeline(file_path)
    
    def ask_for_savefile(self):
        file_path = self.ask_for_file(
            ["*.json", "*.txt"],
            "BNGC Save File or Labels File"
        )

        if not file_path:
            return
        
        self.save_path = file_path
        self.save_path_button.setText(file_path.split("/")[-1])

        self.refresh_import_button()

    def setup_import_ui(self) -> None:
        self.setup_trim_section()
        self.setup_bpm_section()

        self.audio_path_button = Buttons.ButtonWithOutlineSlim("Audiofile")
        self.save_path_button  = Buttons.ButtonWithOutlineSlim("Savefile")

        for button in [self.audio_path_button, self.save_path_button]:
            button.setMinimumWidth(240)
            button.block_glitch_sound()

        self.cancel_button = Buttons.ButtonWithOutline("Later, gator")
        self.import_button = Buttons.NothingButton("Import!")

        self.import_button.setEnabled(False)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(self.audio_path_button)
        path_row.addWidget(self.save_path_button)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addWidget(self.bpm_input)
        bottom_row.addStretch()
        bottom_row.addWidget(self.cancel_button)
        bottom_row.addWidget(self.import_button)

        playback_row = self.build_playback_row()

        self.import_button.clicked.connect(self.on_import_callback)
        self.cancel_button.clicked.connect(self.reject_callback)

        self.audio_path_button.pressed.connect(self.ask_for_audio)
        self.save_path_button.pressed.connect(self.ask_for_savefile)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(path_row)
        self.content_layout.addLayout(playback_row)
        self.content_layout.addLayout(bottom_row)

    # Drag and Drop

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        Player.ui_player.play_sound(
            "DragDrop/DragDrop",
            speed       = 1.03,
            setting_key = "drag_drop_sounds"
        )

        if not self.drag_loop_sound:
            self.drag_loop_sound = Player.ui_player.play_sound(
                "DragDrop/Loop",
                loop        = True,
                setting_key = "drag_drop_sounds"
            )

        self.move_start_animation()
        self.start_shake()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: object) -> None:
        Player.ui_player.play_sound(
            "DragDrop/DragDrop",
            speed       = 0.94,
            setting_key = "drag_drop_sounds"
        )

        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        self.move_end_animation()
        self.stop_shake()

    def dropEvent(self, event: QDropEvent) -> None:
        Player.ui_player.play_sound(
            "DragDrop/DragDrop",
            speed       = 0.94,
            setting_key = "drag_drop_sounds"
        )

        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        found_valid_file = False

        for url in event.mimeData().urls():
            file_path      = url.toLocalFile()
            mime_type, _   = mimetypes.guess_type(file_path)

            if not mime_type:
                continue

            is_audio_video = "audio" in mime_type or "video" in mime_type
            is_save_file   = mime_type in ["text/plain", "application/json"]

            if is_audio_video:
                self.audio_path = file_path
                self.audio_path_button.setText(file_path.split("/")[-1])

                self.run_loading_pipeline(file_path)
                found_valid_file = True

            elif is_save_file:
                self.save_path = file_path
                self.save_path_button.setText(file_path.split("/")[-1])

                self.refresh_import_button()
                found_valid_file = True

        if not found_valid_file:
            Player.ui_player.play_sound("Signals/Error/MegaCritical")
            self.title_label.setText(
                random.choice(
                    [
                        "Uhhm, no.",
                        "Huh?",
                        "How do I read that?",
                        "That's not music or video.",
                        "I only eat audio and video files.",
                        "Nice try, but no.",
                        "Wrong tape.",
                        "Unsupported format.",
                        "Maybe try a .wav or .mp4?"
                    ]
                )
            )

        else:
            self.title_label.setText("Import")

        self.move_end_animation()
        self.stop_shake()
        self.refresh_import_button()
    
    def on_audio_ready(self):
        self.refresh_import_button()

    def refresh_import_button(self) -> None:
        self.import_button.setEnabled(
            self.audio_path is not None and
            self.save_path is not None
        )

    # Import

    def on_import_callback(self) -> None:
        if not self.validate_trim():
            self.import_button.start_glitch()
            return

        try:
            model, glyphs = Encoder.convert_to_glyphs(
                self.save_path,
                int(self.trim_widget.start_time * 1000),
                int(self.trim_widget.end_time   * 1000)
            )

        except Encoder.ZeroGlyphsError:
            ErrorWindow("No glyphs?", "The save file doesn't contain any valid glyphs. File may be corrupted.").exec()
            return

        except Encoder.LabelsNoModelError:
            ErrorWindow("Woops.", "Unable to determine the model from the save file. File may be corrupted.").exec()
            return

        except Encoder.UnknownFileFormatError:
            ErrorWindow("Woops.", "Unknown file format. Make sure you are importing a valid save file.").exec()
            return

        bpm_settings = self.get_bpm_settings()

        self.settings = {
            "model": model,
            "audio": {
                "bpm":      bpm_settings["bpm"],
                "beats":    bpm_settings["beats"],
                "start_ms": self.trim_widget.start_time * 1000,
                "end_ms":   self.trim_widget.end_time   * 1000,
                "fade_in":  self.fade_in_textbox.text(),
                "fade_out": self.fade_out_textbox.text(),
            },
            "glyphs": glyphs
        }

        self.cleanup_audio()
        self.on_ok()

# Playground

class Playground(FloatingWindowGPU):
    def __init__(self) -> None:
        super().__init__(
            "GPU Engine Master Tuner",
            dialog                         = True,
            stays_on_top                   = True,
            max_tilt_angle                 = 20,
            animation_style                = Constants.current_settings["animation_style"],
            enable_audioplayer_effects     = True,
            enable_advanced_beat_animations = False,
            enable_tilt                    = True,
            enable_open_animation          = True,
            enable_close_animation         = True
        )

        self.content_widget.setMinimumWidth(720)
        self.content_widget.setMinimumHeight(480)

        self.scroll_area = Widgets.ElasticScrollArea(self)
        self.content_layout.addWidget(self.scroll_area)

        self.setup_controls()
        self.bind_logic()
        self.adjustSize()

    # Helpers

    def add_section(
            self,
            title:   str,
            widgets: list[QWidget]
        ) -> None:

        self.scroll_area.add_widget(Labels.DescriptionLabel(title))

        for widget in widgets:
            self.scroll_area.add_widget(widget)

    def connect_change(
            self,
            control:  QWidget,
            callback: Callable[[], None]
        ) -> None:

        if isinstance(control, Checkboxes.CheckboxWithLabel):
            control.stateChanged.connect(lambda *_: callback())
            return

        if isinstance(control, Sliders.SliderWithLabel):
            control.valueChanged.connect(lambda *_: callback())
            return

        if isinstance(control, Selectors.SelectorWithLabel):
            control.selectionChanged.connect(lambda *_: callback())
            return

        if isinstance(control, Selectors.Selector):
            control.selectionChanged.connect(lambda *_: callback())
            return

    # Setup

    def setup_controls(self) -> None:
        animation_styles = ["bouncy", "smooth", "roll", "glitch", "classic"]
        default_index    = animation_styles.index(self.animation_style) if self.animation_style in animation_styles else 0

        self.margin_slider                   = Sliders.SliderWithLabel("Margin", 0, 600, self.margin_x)
        self.max_tilt_slider                 = Sliders.SliderWithLabel("Max Tilt Angle", 0, 45, self.max_tilt_angle)
        self.shake_frequency_slider          = Sliders.SliderWithLabel("Shake Frequency (ms)", 10, 200, self.shake_frequency_ms)
        self.shake_deviation_slider          = Sliders.SliderWithLabel("Shake Deviation", 0, 100, int(self.shake_deviation * 10))
        self.tilt_smoothing_slider           = Sliders.SliderWithLabel("Tilt Smoothing", 0, 100, int(self.tilt_smoothing * 100))
        self.bpm_peak_slider                 = Sliders.SliderWithLabel("BPM Peak", 100, 200, int(self.bpm_peak_scale * 100))

        self.start_position_enabled_check     = Checkboxes.CheckboxWithLabel("Start Position", "Use custom spawn position", self.start_position is not None)
        self.start_position_x_slider          = Sliders.SliderWithLabel("Start X", 0, 4000, self.start_position.x() if self.start_position else 0)
        self.start_position_y_slider          = Sliders.SliderWithLabel("Start Y", 0, 4000, self.start_position.y() if self.start_position else 0)

        self.dialog_check                     = Checkboxes.CheckboxWithLabel("Dialog", "Use dialog window flags", True)
        self.stays_on_top_check               = Checkboxes.CheckboxWithLabel("Stays On Top", "Stay above other windows", True)
        self.show_fps_check                   = Checkboxes.CheckboxWithLabel("Show FPS", "Display frame rate in the title", self.show_fps)
        self.enable_tilt_check                = Checkboxes.CheckboxWithLabel("Enable Tilt", "Mouse hover tilt", self.enable_tilt)
        self.enable_open_animation_check      = Checkboxes.CheckboxWithLabel("Open Animation", "Animate on open", self.enable_open_animation)
        self.enable_close_animation_check     = Checkboxes.CheckboxWithLabel("Close Animation", "Animate on close", self.enable_close_animation)
        self.enable_audio_effects_check       = Checkboxes.CheckboxWithLabel("Transition Audio", "Use audio pulses on transitions", self.enable_transition_audio_effects)
        self.enable_advanced_beat_check       = Checkboxes.CheckboxWithLabel("Advanced Beats", "Use heavy and normal beat hooks", self.enable_advanced_beat_animations)
        self.enable_shake_animation_check     = Checkboxes.CheckboxWithLabel("Shake Animation", "Shake animation loop")
        self.style_selector                   = Selectors.Selector(animation_styles, default_index)
        self.apply_window_button              = Buttons.ButtonWithOutlineSlim("Apply Window Settings")

        self.volume_slider                    = Sliders.SliderWithLabel("Volume", 0, 100, 100)
        self.player_speed_slider              = Sliders.SliderWithLabel("Speed (%)", 10, 300, 100)

        self.bitcrush_mix_slider              = Sliders.SliderWithLabel("BC Mix", 0, 100, 0)
        self.bitcrush_bits_slider             = Sliders.SliderWithLabel("BC Bits", 1, 24, 16)
        self.bitcrush_downsample_slider       = Sliders.SliderWithLabel("Downsample", 1, 32, 1)

        self.pass_mix_slider                  = Sliders.SliderWithLabel("Filter Mix", 0, 100, 0)
        self.pass_freq_slider                 = Sliders.SliderWithLabel("Freq (Hz)", 100, 10000, 1000)
        self.pass_q_slider                    = Sliders.SliderWithLabel("Resonance", 1, 100, 10)
        self.pass_gain_slider                 = Sliders.SliderWithLabel("Gain", 0, 200, 100)

        self.eq_low_slider                    = Sliders.SliderWithLabel("EQ Low", 0, 200, 100)
        self.eq_mid_slider                    = Sliders.SliderWithLabel("EQ Mid", 0, 200, 100)
        self.eq_high_slider                   = Sliders.SliderWithLabel("EQ High", 0, 200, 100)

        self.background_noise_slider          = Sliders.SliderWithLabel("Background Noise", 0, 100, 0)
        self.reverb_mix_slider                = Sliders.SliderWithLabel("Reverb Mix", 0, 100, 0)
        self.car_radio_checkbox               = Checkboxes.CheckboxWithLabel("Car Radio", "Apply radio effect preset", False)

        self.delay_left_slider                = Sliders.SliderWithLabel("Delay L (ms)", 0, 50, 0)
        self.delay_right_slider               = Sliders.SliderWithLabel("Delay R (ms)", 0, 50, 0)

        self.radio_noise_intensity_slider     = Sliders.SliderWithLabel("Burst Intensity", 0, 100, 0)
        self.radio_noise_mix_slider           = Sliders.SliderWithLabel("Noise Mix", 0, 100, 30)
        self.radio_noise_color_selector       = Selectors.SelectorWithLabel("Noise Color", ["white", "pink", "brown"], default_text = "brown")
        self.radio_noise_attack_slider        = Sliders.SliderWithLabel("Attack (ms)", 0, 1000, 100)
        self.radio_noise_peak_slider          = Sliders.SliderWithLabel("Peak (ms)", 0, 1000, 180)
        self.radio_noise_release_slider       = Sliders.SliderWithLabel("Release (ms)", 0, 1000, 250)
        self.radio_noise_mute_slider          = Sliders.SliderWithLabel("Mute Audio", 0, 100, 45)
        self.radio_noise_permanent_check      = Checkboxes.CheckboxWithLabel("Permanent", "Always active", False)
        self.radio_noise_random_dur_check     = Checkboxes.CheckboxWithLabel("Randomize", "Variable burst duration", True)

        self.tape_chew_intensity_slider       = Sliders.SliderWithLabel("Chew Intensity", 0, 100, 0)
        self.tape_chew_jitter_slider          = Sliders.SliderWithLabel("Jitter (ms)", 0, 500, 8)
        self.tape_chew_random_dur_check       = Checkboxes.CheckboxWithLabel("Randomize", "Variable burst duration", True)

        self.echo_mix_slider                  = Sliders.SliderWithLabel("Echo Mix", 0, 100, 0)
        self.echo_delay_slider                = Sliders.SliderWithLabel("Delay (ms)", 1, 2000, 180)
        self.echo_feedback_slider             = Sliders.SliderWithLabel("Feedback", 0, 98, 25)
        self.echo_mode_selector               = Selectors.SelectorWithLabel("Echo Mode", ["constant", "random"], default_text = "constant")
        self.echo_focus_selector              = Selectors.SelectorWithLabel("Echo Focus", ["all", "voice", "bass"], default_text = "all")

        self.beat_threshold_slider            = Sliders.SliderWithLabel("Beat Sens.", 0, 100, 38)

        self.button_punch                     = Buttons.ButtonWithOutlineSlim("Title Punch")
        self.button_wobble                    = Buttons.ButtonWithOutlineSlim("Window Wobble")
        self.button_disturbe                  = Buttons.ButtonWithOutlineSlim("Disturbe FX")
        self.button_test_open                 = Buttons.ButtonWithOutlineSlim("Test Open")

        self.play_button                      = Buttons.ButtonWithOutlineSlim("Play")
        self.close_button                     = Buttons.ButtonWithOutline("Close")

        self.add_section(
            "Window",
            [
                self.margin_slider,
                self.max_tilt_slider,
                self.shake_frequency_slider,
                self.shake_deviation_slider,
                self.tilt_smoothing_slider,
                self.bpm_peak_slider,
                self.start_position_enabled_check,
                self.start_position_x_slider,
                self.start_position_y_slider,
                self.dialog_check,
                self.stays_on_top_check,
                self.show_fps_check,
                self.enable_tilt_check,
                self.enable_open_animation_check,
                self.enable_close_animation_check,
                self.enable_audio_effects_check,
                self.enable_advanced_beat_check,
                self.enable_shake_animation_check,
                self.style_selector,
                self.apply_window_button
            ]
        )

        self.add_section("Playback", [self.play_button])

        self.add_section(
            "Audio",
            [
                self.volume_slider,
                self.player_speed_slider
            ]
        )

        self.add_section(
            "Bitcrush",
            [
                self.bitcrush_mix_slider,
                self.bitcrush_bits_slider,
                self.bitcrush_downsample_slider
            ]
        )

        self.add_section(
            "Passes Filter",
            [
                self.pass_mix_slider,
                self.pass_freq_slider,
                self.pass_q_slider,
                self.pass_gain_slider
            ]
        )

        self.add_section(
            "Equalizer",
            [
                self.eq_low_slider,
                self.eq_mid_slider,
                self.eq_high_slider
            ]
        )

        self.add_section(
            "Presets & Effects",
            [
                self.reverb_mix_slider,
                self.background_noise_slider,
                self.car_radio_checkbox
            ]
        )

        self.add_section(
            "Stereo",
            [
                self.delay_left_slider,
                self.delay_right_slider
            ]
        )

        self.add_section(
            "Radio Noise",
            [
                self.radio_noise_intensity_slider,
                self.radio_noise_mix_slider,
                self.radio_noise_color_selector,
                self.radio_noise_attack_slider,
                self.radio_noise_peak_slider,
                self.radio_noise_release_slider,
                self.radio_noise_mute_slider,
                self.radio_noise_permanent_check,
                self.radio_noise_random_dur_check
            ]
        )

        self.add_section(
            "Tape Chew",
            [
                self.tape_chew_intensity_slider,
                self.tape_chew_jitter_slider,
                self.tape_chew_random_dur_check
            ]
        )

        self.add_section(
            "Echo",
            [
                self.echo_mix_slider,
                self.echo_delay_slider,
                self.echo_feedback_slider,
                self.echo_mode_selector,
                self.echo_focus_selector
            ]
        )

        self.add_section("Detection", [self.beat_threshold_slider])

        self.add_section(
            "Animation Triggers",
            [
                self.button_punch,
                self.button_wobble,
                self.button_disturbe,
                self.button_test_open,
                self.close_button
            ]
        )

    # Binding

    def bind_logic(self) -> None:
        self.volume_slider.valueChanged.connect(
            lambda value: Player.player.set_volume(value / 100)
        )

        self.player_speed_slider.valueChanged.connect(
            lambda value: Player.player.set_speed(value / 100, duration_ms = 3000)
        )

        for control in [self.bitcrush_mix_slider, self.bitcrush_bits_slider, self.bitcrush_downsample_slider]:
            self.connect_change(control, self.update_bitcrush)

        for control in [self.pass_mix_slider, self.pass_freq_slider, self.pass_q_slider, self.pass_gain_slider]:
            self.connect_change(control, self.update_passes)

        for control in [self.eq_low_slider, self.eq_mid_slider, self.eq_high_slider]:
            self.connect_change(control, self.update_eq)

        self.background_noise_slider.valueChanged.connect(
            lambda value: Player.player.set_background_noise(mix = value / 100)
        )

        self.reverb_mix_slider.valueChanged.connect(
            lambda value: Player.player.set_reverb(mix = value / 100)
        )

        self.car_radio_checkbox.stateChanged.connect(
            lambda active: Player.player.set_car_radio(active)
        )

        self.delay_left_slider.valueChanged.connect(self.update_delays)
        self.delay_right_slider.valueChanged.connect(self.update_delays)

        for control in [
            self.radio_noise_intensity_slider,
            self.radio_noise_mix_slider,
            self.radio_noise_color_selector,
            self.radio_noise_attack_slider,
            self.radio_noise_peak_slider,
            self.radio_noise_release_slider,
            self.radio_noise_mute_slider,
            self.radio_noise_permanent_check,
            self.radio_noise_random_dur_check
        ]:
            self.connect_change(control, self.update_radio_noise)

        for control in [
            self.tape_chew_intensity_slider,
            self.tape_chew_jitter_slider,
            self.tape_chew_random_dur_check
        ]:
            self.connect_change(control, self.update_tape_chew)

        for control in [
            self.echo_mix_slider,
            self.echo_delay_slider,
            self.echo_feedback_slider,
            self.echo_mode_selector,
            self.echo_focus_selector
        ]:
            self.connect_change(control, self.update_echo)

        self.beat_threshold_slider.valueChanged.connect(
            lambda value: Player.player.onset_detector.set_threshold(value / 100)
        )

        self.style_selector.selectionChanged.connect(self.on_style_changed)

        self.apply_window_button.clicked.connect(self.apply_window_settings)

        self.button_punch.clicked.connect(lambda: self.pulse_title(peak_scale = 1.5))
        self.button_wobble.clicked.connect(self.wobble)
        self.button_disturbe.clicked.connect(self.play_disturb_animation)
        self.button_test_open.clicked.connect(self.open_window)

        self.play_button.clicked.connect(Player.player.toggle_playback)
        self.close_button.clicked.connect(self.on_cancel)

    def apply_window_settings(self) -> None:
        logger.debug("Setting window settings.")

        style = self.style_selector.current_text()

        if style:
            self.animation_style = style

        self.max_tilt_angle                  = self.max_tilt_slider.value()
        self.enable_tilt                     = self.enable_tilt_check.isChecked()
        self.enable_open_animation           = self.enable_open_animation_check.isChecked()
        self.enable_close_animation          = self.enable_close_animation_check.isChecked()
        self.enable_advanced_beat_animations = self.enable_advanced_beat_check.isChecked()
        self.enable_transition_audio_effects = self.enable_audio_effects_check.isChecked()
        self.margin_x                        = self.margin_slider.value()
        self.margin_y                        = self.margin_slider.value()
        self.shake_frequency_ms              = self.shake_frequency_slider.value()
        self.shake_deviation                 = self.shake_deviation_slider.value() / 10
        self.tilt_smoothing                  = self.tilt_smoothing_slider.value() / 100
        self.bpm_peak_scale                  = self.bpm_peak_slider.value() / 100
        self.show_fps                        = self.show_fps_check.isChecked()

        if self.start_position_enabled_check.isChecked():
            self.start_position = QPoint(
                self.start_position_x_slider.value(),
                self.start_position_y_slider.value()
            )

        else:
            self.start_position = None

        if self.enable_shake_animation_check.isChecked():
            self.start_shake()
        
        else:
            self.stop_shake()

        self.apply_attributes(
            self.dialog_check.isChecked(),
            self.stays_on_top_check.isChecked()
        )

        self.refresh_fps_connection()
        self.refresh_bpm_connections()

        self.adjustSize()

        if self.start_position:
            self.center_window()

    def refresh_fps_connection(self) -> None:
        try:
            self.frameSwapped.disconnect(self.on_frame_swapped)
        
        except Exception:
            pass

        if not self.show_fps:
            return

        self.frame_count = 0
        self.fps_timer.start()
        self.frameSwapped.connect(self.on_frame_swapped)

    def refresh_bpm_connections(self) -> None:
        if not self.player:
            return

        try:
            Player.bpm_informer.beat_4.disconnect(self.bpm_tick_animation)
        
        except Exception:
            pass

        try:
            self.player.beat_heavy.disconnect(self.beat_heavy_animation)
            self.player.beat_normal.disconnect(self.beat_normal_animation)
        
        except Exception:
            pass

        if not self.bpm_animations_enabled:
            return

        if self.enable_advanced_beat_animations:
            self.player.beat_heavy.connect(self.beat_heavy_animation)
            self.player.beat_normal.connect(self.beat_normal_animation)
            return

        Player.bpm_informer.beat_4.connect(self.bpm_tick_animation)

    def on_style_changed(self, *_: object) -> None:
        style = self.style_selector.current_data()

        if style:
            self.animation_style = style
    
    def update_radio_noise(self) -> None:
        Player.player.set_noise(
            intensity          = self.radio_noise_intensity_slider.value() / 100,
            mix                = self.radio_noise_mix_slider.value()       / 100,
            permanent          = self.radio_noise_permanent_check.isChecked(),
            color              = self.radio_noise_color_selector.current_data(),
            attack_ms          = self.radio_noise_attack_slider.value(),
            peak_ms            = self.radio_noise_peak_slider.value(),
            release_ms         = self.radio_noise_release_slider.value(),
            mute_audio         = self.radio_noise_mute_slider.value()      / 100,
            randomize_duration = self.radio_noise_random_dur_check.isChecked()
        )

    def update_tape_chew(self) -> None:
        Player.player.set_tape_chew(
            intensity          = self.tape_chew_intensity_slider.value() / 100,
            jitter_ms          = float(self.tape_chew_jitter_slider.value()),
            randomize_duration = self.tape_chew_random_dur_check.isChecked()
        )

    def update_echo(self) -> None:
        Player.player.set_echo(
            mix      = self.echo_mix_slider.value()   / 100,
            delay_ms = self.echo_delay_slider.value(),
            feedback = self.echo_feedback_slider.value() / 100,
            mode     = self.echo_mode_selector.current_data(),
            focus    = self.echo_focus_selector.current_data()
        )

    def update_passes(self) -> None:
        Player.player.set_passes(
            frequencies = [float(self.pass_freq_slider.value())],
            q           = self.pass_q_slider.value()    / 10,
            mix         = self.pass_mix_slider.value()  / 100,
            gain        = self.pass_gain_slider.value() / 100
        )

    def update_bitcrush(self) -> None:
        Player.player.set_bitcrush(
            bits       = self.bitcrush_bits_slider.value(),
            downsample = self.bitcrush_downsample_slider.value(),
            mix        = self.bitcrush_mix_slider.value() / 100
        )

    def update_delays(self) -> None:
        Player.player.set_channel_delay(
            left_to_ms  = self.delay_left_slider.value(),
            right_to_ms = self.delay_right_slider.value(),
            duration_ms = 1000
        )

    def update_eq(self) -> None:
        Player.player.set_eq(low = self.eq_low_slider.value() / 100, mid = self.eq_mid_slider.value() / 100, high = self.eq_high_slider.value() / 100)

class ByteBeatWindow(FloatingWindowGPU):
    def __init__(self):
        super().__init__("Hm.")

        self.bytebeat_player = Player.ByteBeatPlayer()
        self.bytebeat_player.play()

        self.textbox = Textboxes.Textbox("text", placeholder = "Byte Beat?", max_length = 99999)
        self.textbox.setMinimumWidth(400)
        self.textbox.safeTextChanged.connect(self.on_textbox_changed)

        examples = Buttons.ButtonRow(
            [
                (Buttons.ButtonWithOutline, "1", lambda: self.example_callback("1")),
                (Buttons.ButtonWithOutline, "2", lambda: self.example_callback("2")),
                (Buttons.ButtonWithOutline, "3", lambda: self.example_callback("3")),
                (Buttons.ButtonWithOutline, "4", lambda: self.example_callback("4")),
                (Buttons.ButtonWithOutline, "5", lambda: self.example_callback("5"))
            ]
        )

        close_button = Buttons.ButtonWithOutline("Ok?")
        close_button.pressed.connect(self.on_ok)

        self.content_layout.addWidget(self.textbox)
        self.content_layout.addLayout(examples)
        self.content_layout.addWidget(close_button)
    
    def on_textbox_changed(self, text):
        self.bytebeat_player.set_formula(text)
    
    def example_callback(self, number):
        code = {
            "1": "(t * ((7 if t & 4096 else 16) + (1 if (1 & (t >> 14)) else 0) if t % 65536 < 59392 else t&7 or 16)) >> (3 & -t >> (2 if (t & 2048) else 10))",
            "2": "((t >> 10) & 42) * t",
            "3": "((t>>9^(t>>9)-1^1)%13*t&31)*(2+(t>>4))",
            "4": "t^t>>4^(t>>11+(t>>16)%3)%16*t^3*t",
            "5": "(lambda d,b,a,n,r: (((d if ((b//4)%16) in (0,3,6,10) else 0) % 64) + ((d*a[r]) % 64) + (((d*a[r])/1.33) % 64) + ((n if b%4==0 else 0) % 20) + ((n if b%32==16 else 0) % 44)))((0.127*(t*6)), int((t*6)/1578), [0,0,0,0,0,0,0,0,4,4,4.75,4.75,5.3,0,5.3,5.3,5.3,5.3,5.3,5.3,4.75,4.75,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,4,4.75,4.75,5.3,0,5.3,5.3,5.3,5.3,4.75,4.75,0,0,4,4,0,0,3.55,3.55,4,4,0,0], (0.127*(t*6))*random(), (int((t*6)/1578)//2)%64)"
        }.get(number)

        self.bytebeat_player.set_formula(code)
        self.textbox.setText(code)
    
    def closeEvent(self, event):
        self.bytebeat_player.cleanup()
        super().closeEvent(event)