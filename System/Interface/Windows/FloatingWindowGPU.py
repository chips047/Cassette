import sys
import time
import math
import numpy
import random

from OpenGL    import GL
from OpenGL.GL import shaders

from loguru import logger

from PyQt6.QtCore import (
    Qt,
    QRect,
    QPoint,
    QTimer,
    QEventLoop
)

from PyQt6.QtGui import (
    QPen,
    QColor,
    QCursor,
    QPainter,
    QMatrix4x4,
    QShowEvent,
    QCloseEvent,
    QMouseEvent,
    QQuaternion,
    QSurfaceFormat
)

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QApplication,
    QGraphicsOpacityEffect
)

from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from System.Common import (
    Dev,
    Constants
)

from System.Services import Player

from System.Interface import (
    Timing,
    Widgets
)

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine
)

from .WindowAnimationStyles import (
    play_sound_choice,
    WindowAnimationStyle
)

# Floating Window GPU

@Dev.track_ram
class FloatingWindowGPU(Lifecycle.LoomAnimationMixin, QOpenGLWidget):
    shared_shader_program = None

    def __init__(
            self,
            title:                           str     | None,
            parent:                          QWidget | None = None,
            margin:                          int     | None = None,
            dialog:                          bool           = True,
            stays_on_top:                    bool           = True,
            max_tilt_angle:                  int            = 20,
            animation_style:                 str     | None = None,
            enable_audioplayer_effects:      bool           = True,
            enable_advanced_beat_animations: bool           = False,
            enable_tilt:                     bool           = True,
            enable_open_animation:           bool           = True,
            enable_close_animation:          bool           = True,
            start_position:                  QPoint  | None = None
        ) -> None:

        super().__init__(parent)

        self.player                          = Player.player
        self.enable_tilt                     = enable_tilt
        self.max_tilt_angle                  = max_tilt_angle

        self.result                          = None
        self.event_loop                      = None
        self.allow_exit                      = False
        self.drag_position                   = None
        self.is_ready                        = False
        self.is_closing                      = False
        self.was_cancelled                   = False
        self.start_position                  = start_position

        self.shake_frequency_ms              = 80
        self.shake_deviation                 = 2.0

        self.animation_style                 = animation_style or Constants.current_settings["animation_style"]

        self.enable_open_animation           = enable_open_animation
        self.enable_close_animation          = enable_close_animation
        self.enable_advanced_beat_animations = enable_advanced_beat_animations
        self.enable_transition_audio_effects = enable_audioplayer_effects

        self.enable_debug_mode               = Constants.current_settings.get("floating_window_debugging")
        self.debug_frame_times               = []
        self.debug_last_time                 = time.perf_counter()

        self.target_margin                   = margin or 300
        self.margin_x                        = self.target_margin
        self.margin_y                        = self.target_margin

        self.prepare_format()
        self.apply_attributes(dialog, stays_on_top)
        self.setup_layout(title)
        self.setup_animation_properties()
        self.setup_timers()

    # Setup

    def prepare_format(self) -> None:
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

    def setup_layout(self, title: str | None) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(self.margin_x, self.margin_y, self.margin_x, self.margin_y)
        main_layout.setSpacing(0)

        self.content_widget = QWidget(self)
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content_widget.setMinimumWidth(320)
        
        # Заставляем виджет контента НЕ расти выше, чем нужно его элементам:
        from PyQt6.QtWidgets import QSizePolicy
        self.content_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum
        )

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(12)
        # Ограничиваем layout минимально необходимым размером
        self.content_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        # ВАЖНО: AlignmentFlag.AlignCenter запрещает main_layout растягивать content_widget по высоте!
        main_layout.addWidget(self.content_widget, 0, Qt.AlignmentFlag.AlignCenter)

        if title:
            self.title_label = Widgets.TitleLabel(title)
            self.content_layout.addWidget(self.title_label)
        else:
            self.title_label = None

    def setup_animation_properties(self) -> None:
        self.animations_active    = False

        self.current_tilt_x       = 0.0
        self.current_tilt_y       = 0.0

        self.target_tilt_x        = 0.0
        self.target_tilt_y        = 0.0

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
        LoomEngine.ui_engine.updated.connect(self.update)

        self.animations_active = True

    def on_opacity_content_changed(self, value: float) -> None:
        self.content_opacity_effect.setOpacity(value)
        self.update()

    def update_tilt_smoothing(self) -> None:
        if not self.animations_active:
            return

        if self.max_tilt_angle <= 0 or self.tilt_smoothing <= 0 or not self.enable_tilt:
            return

        local_position          = self.mapFromGlobal(QCursor.pos())
        widget_rectangle        = self.content_widget.rect()
        content_rectangle_local = widget_rectangle.translated(self.content_widget.pos())

        if content_rectangle_local.contains(local_position):
            center_x = self.width() / 2
            center_y = self.height() / 2

            x_normalized = -(local_position.x() - center_x) / center_x
            y_normalized = (local_position.y() - center_y) / center_y

            self.target_tilt_x = y_normalized * self.max_tilt_angle
            self.target_tilt_y = -x_normalized * self.max_tilt_angle

        self.current_tilt_x += (self.target_tilt_x - self.current_tilt_x) * self.tilt_smoothing
        self.current_tilt_y += (self.target_tilt_y - self.current_tilt_y) * self.tilt_smoothing

    def setup_timers(self) -> None:
        self.shake_timer = Timing.Timer(
            self.shake_frequency_ms,
            self.apply_shake_step,
            parent = self
        )

        if not self.bpm_animations_enabled:
            return

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
                target_width + (self.margin_x * 2),
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
            vertex_shader   = shaders.compileShader(Constants.FLOATING_WINDOW_VERTEX_SHADER,   GL.GL_VERTEX_SHADER)
            fragment_shader = shaders.compileShader(Constants.FLOATING_WINDOW_FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)

            self.__class__.shared_shader_program = shaders.compileProgram(
                vertex_shader,
                fragment_shader,
                validate = False
            )

        vertices = numpy.array(
            [
                1.0, 1.0, 0.0, 1.0, 1.0,
                1.0, -1.0, 0.0, 1.0, 0.0,
                -1.0, -1.0, 0.0, 0.0, 0.0,
                -1.0, 1.0, 0.0, 0.0, 1.0
            ],
            dtype = numpy.float32
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

        content_rectangle = self.content_widget.geometry()
        content_width     = float(content_rectangle.width())
        content_height    = float(content_rectangle.height())

        if content_width < 1 or content_height < 1:
            return

        mvp_final        = self.calculate_matrix()
        background_alpha = self.opacity_background_property.value if self.animations_active else 1.0

        GL.glUniform2f(self.location_size, content_width, content_height)
        GL.glUniform1f(self.location_radius, 16.0)
        GL.glUniform1f(self.location_border_px, 2.0)
        GL.glUniform4f(self.location_rect_color, 0.17, 0.17, 0.17, 1.0)
        GL.glUniform4f(self.location_border_color, 0.25, 0.25, 0.25, 1.0)
        GL.glUniform1f(self.location_rect_alpha, background_alpha)
        GL.glUniform1f(self.location_border_alpha, background_alpha)
        GL.glUniform1f(self.location_global_alpha, 1.0)

        GL.glUniformMatrix4fv(self.location_mvp, 1, GL.GL_FALSE, mvp_final.data())

        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)

        if self.enable_debug_mode:
            self.draw_debug_overlay()

    def draw_debug_overlay(self) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        window_width  = self.width()
        window_height = self.height()

        painter.setPen(QPen(QColor(255, 50, 50, 200), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, window_width, window_height)

        painter.setPen(QColor(255, 50, 50, 255))

        font = painter.font()
        font.setPointSize(10)

        painter.setFont(font)
        painter.drawText(5, 15, f"Window (Total): {window_width}x{window_height} px")

        content_rectangle = self.content_widget.geometry()
        painter.setPen(QPen(QColor(50, 255, 50, 200), 2, Qt.PenStyle.DashLine))
        painter.drawRect(content_rectangle)

        painter.setPen(QColor(50, 255, 50, 255))
        painter.drawText(content_rectangle.x() + 5, content_rectangle.y() + 15, f"Content: {content_rectangle.width()}x{content_rectangle.height()} px")

        current_time         = time.perf_counter()
        delta_time           = current_time - self.debug_last_time
        self.debug_last_time = current_time

        if delta_time > 1.0:
            delta_time = 0.016

        if delta_time > 0:
            self.debug_frame_times.append(delta_time)

        if len(self.debug_frame_times) > 60:
            self.debug_frame_times.pop(0)

        if self.debug_frame_times:
            average_delta_time = sum(self.debug_frame_times) / len(self.debug_frame_times)
            frames_per_second  = 1.0 / average_delta_time if average_delta_time > 0 else 0.0

            stable_count = sum(1 for single_time in self.debug_frame_times if abs(single_time - average_delta_time) <= (average_delta_time * 0.15))
            stability    = (stable_count / len(self.debug_frame_times)) * 100.0

        else:
            frames_per_second = 0.0
            stability         = 100.0

        widgets_count = len(self.findChildren(QWidget))

        debug_info = [
            "--- DEBUG MODE ---",
            f"FPS: {frames_per_second:.1f}",
            f"Stability: {stability:.1f}%",
            f"Total Widgets: {widgets_count}",
            ""
        ]

        if self.animations_active:
            debug_info.extend(
                [
                    "--- PROPERTIES ---",
                    f"X Offset: {self.x_offset_property.value:.3f}",
                    f"Y Offset: {self.y_offset_property.value:.3f}",
                    f"Z Offset: {self.z_offset_property.value:.3f}",
                    f"Rotation X: {self.rotation_x_property.value:.3f}",
                    f"Rotation Y: {self.rotation_y_property.value:.3f}",
                    f"Rotation Z: {self.rotation_z_property.value:.3f}",
                    f"Scale: {self.scale_property.value:.3f}",
                    f"Target Tilt X, Y: {self.target_tilt_x:.2f}, {self.target_tilt_y:.2f}",
                    f"Current Tilt X, Y: {self.current_tilt_x:.2f}, {self.current_tilt_y:.2f}",
                    f"Bg Opacity: {self.opacity_background_property.value:.3f}",
                    f"Content Opacity: {self.opacity_content_property.value:.3f}",
                    "Disable Debug in Settings > Dev to hide this text."
                ]
            )
        
        else:
            debug_info.append("Animations: Inactive")

        text_position_x = 10
        text_position_y = 40

        for line_index, line in enumerate(debug_info):
            painter.setPen(QColor(0, 0, 0, 180))
            painter.drawText(text_position_x + 1, text_position_y + (line_index * 15) + 1, line)

            painter.setPen(QColor(255, 255, 50, 255))
            painter.drawText(text_position_x, text_position_y + (line_index * 15), line)

        painter.end()

    def calculate_matrix(
            self,
            content_width:  float | None = None,
            content_height: float | None = None
        ) -> QMatrix4x4:

        content_width  = content_width or self.content_widget.width()
        content_height = content_height or self.content_widget.height()

        mvp           = QMatrix4x4()
        field_of_view = 45.0
        z_distance    = 3.0
        aspect_ratio  = self.width() / self.height()

        mvp.perspective(field_of_view, aspect_ratio, 0.1, 100.0)
        mvp.translate(0.0, 0.0, -z_distance)

        visible_height_at_z = 2.0 * math.tan(math.radians(field_of_view / 2.0)) * z_distance
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

        mvp.scale((content_width * pixel_unit) / 2.0, (content_height * pixel_unit) / 2.0)

        return mvp

    # Events

    def showEvent(self, event: QShowEvent) -> None:
        if not self.is_ready:
            # Сначала рассчитываем идеальный размер и позицию, и только затем показываем окно
            self.adjustSize()

            if self.animations_active:
                scale_restriction = self.maximum_scale()
                self.scale_property.set_max_value(scale_restriction)

        super().showEvent(event)

        if not self.is_ready:
            if self.enable_open_animation:
                self.open_window()

            self.is_ready = True

    def closeEvent(self, event: QCloseEvent) -> None:
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.title_label:
            local_position = self.content_widget.mapFrom(self, event.pos())

            if not self.title_label.geometry().contains(local_position):
                return
        
        elif sys.platform != "linux" and not self.content_widget.geometry().contains(event.pos()):
            return

        if sys.platform == "linux":
            self.windowHandle().startSystemMove()

        self.drag_position = event.globalPosition().toPoint() - self.pos()

        self.move_start_animation()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            event.buttons() == Qt.MouseButton.LeftButton and
            self.drag_position is not None and
            sys.platform != "linux"
        ):
            
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.drag_position:
            self.move_end_animation()

        self.drag_position = None

    # Utilities

    def get_optimal_offset(
            self,
            width:  int,
            height: int,
            limit:  int = 500
        ) -> tuple[float, float]:

        scale_x = limit / max(width, limit)
        scale_y = limit / max(height, limit)

        start_offset_x = self.period_randomizer(
            (-0.35 * scale_x, -0.2 * scale_x),
            (0.2   * scale_x, 0.35 * scale_x)
        )

        start_offset_y = self.period_randomizer(
            (-0.5 * scale_y, -0.2 * scale_y),
            (0.2  * scale_y, 0.5  * scale_y)
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
        self.content_widget.ensurePolished()

        # Активируем оба layout, чтобы дочерние виджеты честно посчитали свои размеры
        if self.content_layout:
            self.content_layout.activate()
        if self.layout():
            self.layout().activate()

        # Принудительно сжимаем content_widget до минимально необходимого его детям размера
        self.content_widget.adjustSize()
        content_size = self.content_widget.sizeHint()

        if self.is_ready:
            self.animate_resize(content_size.width(), content_size.height())
            return

        screen_geometry  = QApplication.primaryScreen().availableGeometry()

        available_width  = screen_geometry.width()
        available_height = screen_geometry.height()

        content_width    = max(content_size.width(), self.content_widget.minimumWidth())
        content_height   = content_size.height()

        max_margin_x     = max(20, (available_width - 46 * 2 - content_width) // 2)
        max_margin_y     = max(20, (available_height - 46 * 2 - content_height) // 2)
        
        self.margin_x    = min(max_margin_x, self.target_margin)
        self.margin_y    = min(max_margin_y, self.target_margin)

        self.layout().setContentsMargins(
            self.margin_x,
            self.margin_y,
            self.margin_x,
            self.margin_y
        )

        final_width  = content_width + (self.margin_x * 2)
        final_height = content_height + (self.margin_y * 2)

        # Центрируем и устанавливаем итоговую геометрию с актуальными размерами
        self.center_window(final_width, final_height)

    def set_bpm_peak_size(self, coefficient: float) -> None:
        self.bpm_peak_scale = coefficient

    def period_randomizer(self, *periods: tuple) -> int | float:
        function = random.uniform if isinstance(periods[0][0], float) else random.randint

        return function(*random.choice(periods))

    def center_window(self, width: int | None = None, height: int | None = None) -> QRect:
        w = width if width is not None else self.width()
        h = height if height is not None else self.height()

        if self.start_position:
            final_rectangle = QRect(
                self.start_position.x() - self.margin_x,
                self.start_position.y() - self.margin_y,
                w,
                h
            )
            self.setGeometry(final_rectangle)
            return final_rectangle

        window        = QApplication.activeWindow()
        window_center = window.geometry().center() if window else QApplication.primaryScreen().geometry().center()

        final_rectangle = QRect(
            window_center.x() - w // 2,
            window_center.y() - h // 2,
            w,
            h
        )

        self.setGeometry(final_rectangle)
        return final_rectangle

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

    def squish(
            self,
            value: float,
            power: float = 1.2
        ) -> float:
        
        return 0.075 * (value ** power)

    def maximum_scale(self) -> float:
        content_width  = self.content_widget.width()
        content_height = self.content_widget.height()

        if content_width <= 0 or content_height <= 0:
            return 1.0

        real_width  = self.geometry().width()
        real_height = self.geometry().height()

        screen_geometry  = QApplication.primaryScreen().availableGeometry()
        available_width  = screen_geometry.width()
        available_height = screen_geometry.height()

        is_full_width  = real_width >= (available_width - 92)
        is_full_height = real_height >= (available_height - 92)

        tilt_angle_radians = math.radians(self.max_tilt_angle) if self.enable_tilt else 0.0
        cos_tilt           = math.cos(tilt_angle_radians)
        sin_tilt           = math.sin(tilt_angle_radians)

        bounding_width  = content_width * cos_tilt + content_height * sin_tilt
        bounding_height = content_width * sin_tilt + content_height * cos_tilt

        max_scale_x = float("inf") if is_full_width else real_width / bounding_width
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
            LoomEngine.ui_engine.updated.disconnect(self.update)

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