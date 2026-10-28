from __future__ import annotations

import time
import random
import numpy

from collections.abc import Callable

from OpenGL import GL
from OpenGL.GL import shaders

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QObject,
    pyqtSignal
)

from PyQt6.QtGui import (
    QColor,
    QImage,
    QPixmap,
    QPainter,
    QVector4D,
    QMatrix4x4,
    QSurfaceFormat
)

from PyQt6.QtWidgets import (
    QWidget,
    QMainWindow
)

from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from System.Common import Styles
from System.Services import (
    Player,
    Haptics
)
from System.Interface import Timing
from System.Interface.Animation import LoomEngine

# Shaders

SHATTER_VERTEX_SHADER = """
#version 410 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec2 in_uv;

out vec2 v_uv;

uniform mat4 u_mvp;

void main() {
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_position, 1.0);
}
"""

SHATTER_FRAGMENT_SHADER = """
#version 410 core
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_scene_tex;
uniform vec2      u_resolution;
uniform float     u_time;
uniform int       u_shatter_active;

uniform vec2      u_impact_pos;
uniform float     u_impact_count;
uniform float     u_concussion_flash;
uniform float     u_impact_seed;

float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

vec2 hash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(hash11(dot(i + vec2(0.0, 0.0), vec2(12.7, 31.1))),
            hash11(dot(i + vec2(1.0, 0.0), vec2(12.7, 31.1))), u.x),
        mix(hash11(dot(i + vec2(0.0, 1.0), vec2(12.7, 31.1))),
            hash11(dot(i + vec2(1.0, 1.0), vec2(12.7, 31.1))), u.x),
        u.y
    );
}

float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    mat2 rot = mat2(0.8, 0.6, -0.6, 0.8);
    for (int i = 0; i < 4; ++i) {
        v += a * noise(p);
        p = rot * p * 2.15 + vec2(1.2, 4.3);
        a *= 0.5;
    }
    return v;
}

void main() {
    vec2 frag_coord = v_uv * u_resolution;

    if (u_shatter_active == 0) {
        frag_color = texture(u_scene_tex, v_uv);
        return;
    }

    vec2 d_vec = frag_coord - u_impact_pos;
    float base_dist = length(d_vec);

    vec2 domain_warp = vec2(
        fbm(d_vec * 0.012 + vec2(u_impact_seed, 1.7)),
        fbm(d_vec * 0.012 + vec2(3.9, u_impact_seed * 0.8))
    ) - 0.5;

    vec2 warped_d = d_vec + domain_warp * (base_dist * 0.75 + 45.0);
    float dist = length(warped_d);
    float angle = atan(warped_d.y, warped_d.x);

    float angle_noise = fbm(vec2(angle * 4.0, dist * 0.04) + u_impact_seed);
    float jagged_angle = angle + (angle_noise - 0.5) * 0.85;

    float ring_jitter = hash11(floor(dist * 0.05) + u_impact_seed) * 0.6;
    float ring_id = floor(log2(max(dist, 6.0) / 7.0) * (2.6 + ring_jitter));

    float sector_rnd = hash11(ring_id * 17.3 + u_impact_seed);
    float sector_count = floor(8.0 + sector_rnd * 16.0);
    float sector_id = floor((jagged_angle + 3.14159) / (6.28318 / sector_count));

    vec2 shard_id = vec2(ring_id, sector_id) + vec2(u_impact_seed * 0.1);
    vec2 shard_rnd = hash22(shard_id);
    vec2 shard_rnd2 = hash22(shard_id + vec2(37.2, 19.4));

    float tilt_intensity = clamp(240.0 / (dist + 25.0), 0.0, 1.4);
    vec2 tilt_dir = (shard_rnd - 0.5) * 2.0;
    vec3 shard_normal = normalize(vec3(tilt_dir * tilt_intensity * 0.65, 1.0));

    vec2 shard_shift = (shard_rnd2 - 0.5) * clamp(180.0 / (dist + 30.0), 0.0, 1.0) * 14.0;

    float angle_cell = fract((jagged_angle + 3.14159) / (6.28318 / sector_count)) - 0.5;
    float dist_angular = abs(angle_cell) * (6.28318 / sector_count) * dist;
    float ring_cell = fract(log2(max(dist, 6.0) / 7.0) * (2.6 + ring_jitter)) - 0.5;
    float dist_radial = abs(ring_cell) * (22.0 + shard_rnd.x * 12.0);
    float dist_crack = min(dist_angular, dist_radial);

    float micro_spider = abs(fbm(warped_d * 0.08 + u_impact_seed) - 0.5);
    dist_crack = min(dist_crack, smoothstep(0.015, 0.0, micro_spider) * 8.0 + (1.0 - smoothstep(0.015, 0.0, micro_spider)) * dist_crack);

    vec2 refraction_offset = (shard_normal.xy * 38.0 + shard_shift) * clamp(260.0 / (dist + 35.0), 0.0, 1.0);
    float dispersion = 1.0 + clamp(180.0 / (dist + 15.0), 0.0, 1.0) * (0.045 + shard_rnd.y * 0.035);

    vec2 uv_r = v_uv + (refraction_offset * dispersion) / u_resolution;
    vec2 uv_g = v_uv + (refraction_offset) / u_resolution;
    vec2 uv_b = v_uv + (refraction_offset / dispersion) / u_resolution;

    float r_sample = texture(u_scene_tex, uv_r).r;
    float g_sample = texture(u_scene_tex, uv_g).g;
    float b_sample = texture(u_scene_tex, uv_b).b;
    vec3 scene_color = vec3(r_sample, g_sample, b_sample);

    vec3 light_dir = normalize(vec3(0.3, -0.7, 0.65));
    vec3 view_dir  = vec3(0.0, 0.0, 1.0);
    vec3 half_vec  = normalize(light_dir + view_dir);

    float spec = pow(max(dot(shard_normal, half_vec), 0.0), 28.0) * (0.4 + shard_rnd.x * 0.6);
    float crack_gleam = smoothstep(2.4, 0.2, dist_crack) * 2.2;
    float drop_shadow = smoothstep(0.0, 5.5, dist_crack);

    scene_color = scene_color * (0.55 + 0.45 * drop_shadow) + vec3(spec * 0.75) + vec3(crack_gleam);

    float frost_radius = 26.0 + u_impact_count * 5.0;
    float frost_noise = noise(warped_d * 0.6);
    float frost = smoothstep(frost_radius + 15.0, frost_radius - 8.0, dist) * step(0.35, frost_noise);
    scene_color = mix(scene_color, vec3(0.92, 0.95, 0.98), frost * 0.85);

    float dx = abs(frag_coord.x - u_impact_pos.x);
    float dy = abs(frag_coord.y - u_impact_pos.y);

    float col_cluster = floor(frag_coord.x / (1.0 + floor(hash11(floor(frag_coord.x * 0.2) + u_impact_seed) * 5.0)));
    float is_driver_col = step(0.978, hash11(col_cluster * 173.2 + u_impact_seed));
    float line_reach = step(dx, 340.0 + u_impact_count * 130.0);

    if (is_driver_col * line_reach > 0.5) {
        float col_type = hash11(col_cluster * 39.7);
        vec3 fault_color;
        if (col_type < 0.22) fault_color = vec3(0.1, 1.0, 0.25);
        else if (col_type < 0.44) fault_color = vec3(1.0, 0.02, 0.85);
        else if (col_type < 0.66) fault_color = vec3(0.0, 0.9, 1.0);
        else if (col_type < 0.82) fault_color = vec3(1.0, 0.92, 0.2);
        else if (col_type < 0.92) fault_color = vec3(1.0);
        else fault_color = vec3(0.0);

        float col_flicker = 0.85 + 0.15 * sin(u_time * 24.0 + col_cluster);
        scene_color = mix(scene_color, fault_color * col_flicker, 0.92);
    }

    float row_group = floor(frag_coord.y / (4.0 + floor(hash11(floor(frag_coord.y * 0.1) + u_impact_seed) * 8.0)));
    float is_row_glitch = step(0.972, hash11(row_group * 91.7 + floor(u_time * 16.0))) * step(dy, 220.0);
    if (is_row_glitch > 0.5) {
        float jitter_shift = (hash11(row_group + u_time) - 0.5) * 45.0;
        vec2 glitch_uv = vec2(v_uv.x + jitter_shift / u_resolution.x, v_uv.y);
        scene_color = texture(u_scene_tex, glitch_uv).rgb * 0.7;
    }

    float leak_noise = fbm(warped_d * 0.07 + u_impact_seed * 2.1) * 45.0;
    float leak_radius = 28.0 + u_impact_count * 16.0;
    float leak_dist = dist + leak_noise;

    float ink_bleed = smoothstep(leak_radius + 8.0, leak_radius - 2.0, leak_dist);
    vec3 rainbow_sheen = 0.5 + 0.5 * cos(leak_dist * 0.5 + vec3(0.0, 2.1, 4.2));
    float edge_stress = smoothstep(leak_radius + 18.0, leak_radius + 4.0, leak_dist) * (1.0 - ink_bleed);

    scene_color = mix(scene_color, rainbow_sheen, edge_stress * 0.85);
    scene_color = mix(scene_color, vec3(0.015, 0.02, 0.03), ink_bleed * 0.98);

    float hole_radius = 11.0 + u_impact_count * 4.0;
    float void_hole = smoothstep(hole_radius + 3.0, hole_radius, dist);
    scene_color = mix(scene_color, vec3(0.0), void_hole);

    if (u_concussion_flash > 0.001) {
        scene_color += vec3(0.95, 1.0, 0.90) * u_concussion_flash;
    }

    frag_color = vec4(scene_color, 1.0);
}
"""

# Visual Presentation Layer

class WindowAnimationOverlay(QOpenGLWidget):
    def __init__(
            self,
            animator: WindowAnimator,
            parent:   QWidget
        ) -> None:

        super().__init__(parent)

        self.animator       = animator
        self.shader_program = None
        self.quad_vao       = None
        self.quad_vbo       = None
        self.scene_texture  = None

        self.setup_surface_format()
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.hide()

    def setup_surface_format(self) -> None:
        surface_format = QSurfaceFormat()
        surface_format.setVersion(4, 1)
        surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        surface_format.setDepthBufferSize(24)
        surface_format.setAlphaBufferSize(8)
        surface_format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
        self.setFormat(surface_format)

    def initializeGL(self) -> None:
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)

        vertex_shader   = shaders.compileShader(SHATTER_VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        fragment_shader = shaders.compileShader(SHATTER_FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        self.shader_program = shaders.compileProgram(vertex_shader, fragment_shader)

        quad_vertices = numpy.array([
            0.0, 0.0, 0.0,  0.0, 0.0,
            1.0, 0.0, 0.0,  1.0, 0.0,
            1.0, 1.0, 0.0,  1.0, 1.0,
            0.0, 0.0, 0.0,  0.0, 0.0,
            1.0, 1.0, 0.0,  1.0, 1.0,
            0.0, 1.0, 0.0,  0.0, 1.0
        ], dtype = numpy.float32)

        self.quad_vao = GL.glGenVertexArrays(1)
        self.quad_vbo = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.quad_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.quad_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, quad_vertices.nbytes, quad_vertices, GL.GL_STATIC_DRAW)

        stride = 5 * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(0))

        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(12))

        GL.glBindVertexArray(0)

        self.scene_texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.scene_texture)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    def upload_scene_texture(self, pixmap: QPixmap) -> None:
        if pixmap is None or pixmap.isNull():
            return

        self.makeCurrent()
        image  = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        width  = image.width()
        height = image.height()

        pointer = image.bits()
        pointer.setsize(image.sizeInBytes())
        image_bytes = bytes(pointer)

        GL.glBindTexture(GL.GL_TEXTURE_2D, self.scene_texture)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D, 0, GL.GL_RGBA,
            width, height, 0,
            GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, image_bytes
        )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        self.doneCurrent()

    def paintGL(self) -> None:
        pixel_ratio     = self.devicePixelRatio()
        viewport_width  = max(1, int(self.width() * pixel_ratio))
        viewport_height = max(1, int(self.height() * pixel_ratio))

        GL.glViewport(0, 0, viewport_width, viewport_height)
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        if self.shader_program is None:
            return

        GL.glUseProgram(self.shader_program)

        width_pixels  = float(self.width())
        height_pixels = float(self.height())

        orthographic_matrix = QMatrix4x4()
        orthographic_matrix.ortho(0.0, 1.0, 1.0, 0.0, -1000.0, 1000.0)

        projection_matrix     = self.animator.calculate_projection_transform_matrix()
        model_view_projection = orthographic_matrix * projection_matrix

        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.shader_program, "u_mvp"), 1, GL.GL_FALSE, model_view_projection.data())
        GL.glUniform2f(GL.glGetUniformLocation(self.shader_program, "u_resolution"), width_pixels, height_pixels)
        GL.glUniform1f(GL.glGetUniformLocation(self.shader_program, "u_time"), float(time.time() % 1000.0))
        GL.glUniform1i(GL.glGetUniformLocation(self.shader_program, "u_shatter_active"), 1 if self.animator.glass_shatter_active else 0)

        GL.glUniform2f(GL.glGetUniformLocation(self.shader_program, "u_impact_pos"), self.animator.impact_point_x, self.animator.impact_point_y)
        GL.glUniform1f(GL.glGetUniformLocation(self.shader_program, "u_impact_count"), float(self.animator.impact_count))
        GL.glUniform1f(GL.glGetUniformLocation(self.shader_program, "u_concussion_flash"), self.animator.concussion_flash)
        GL.glUniform1f(GL.glGetUniformLocation(self.shader_program, "u_impact_seed"), self.animator.impact_seed)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.scene_texture)
        GL.glUniform1i(GL.glGetUniformLocation(self.shader_program, "u_scene_tex"), 0)

        GL.glBindVertexArray(self.quad_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)

# Window Animator

class WindowAnimator(QObject):
    transformed = pyqtSignal()

    active_animators: dict[QWidget, WindowAnimator] = {}

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)

        self.target_window         = window
        self.target_content_widget = window.centralWidget()
        self.captured_pixmap       = None
        self.static_frame_pixmap   = None
        self.is_visual_animating   = False
        self.focal_length          = 1100.0

        self.glass_shatter_active  = False
        self.concussion_flash      = 0.0
        self.impact_count          = 0
        self.impact_point_x        = 0.0
        self.impact_point_y        = 0.0
        self.impact_seed           = 42.0

        self.collapse_duration_ms       = 5000.0
        self.collapse_start_time_sec    = 0.0
        self.collapse_finished_callback = None
        self.collapse_timer             = None

        self.background_color = QColor(Styles.Colors.Background)

        self.overlay = WindowAnimationOverlay(self, self.target_window)

        self.setup_animation_handles()
        self.setup_idle_watchdog()
        self.setup_flash_timer()

        self.target_window.installEventFilter(self)

        WindowAnimator.active_animators[window] = self

    # Setup

    def setup_animation_handles(self) -> None:
        self.rotation_x_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "window_rotation_x",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD,
            on_change  = self.handle_visual_property_changed
        )

        self.rotation_y_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "window_rotation_y",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD,
            on_change  = self.handle_visual_property_changed
        )

        self.rotation_z_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "window_rotation_z",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD,
            on_change  = self.handle_visual_property_changed
        )

        self.scale_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "window_scale",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.MULTIPLY,
            on_change  = self.handle_visual_property_changed
        )

        self.offset_x_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "window_offset_x",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD,
            on_change  = self.handle_visual_property_changed
        )

        self.offset_y_handle = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "window_offset_y",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.ADD,
            on_change  = self.handle_visual_property_changed
        )

        self.collapse_timer = Timing.Timer(
            interval    = 45,
            callback    = self.process_corrupt_collapse_step,
            single_shot = False,
            parent      = self
        )

    def setup_idle_watchdog(self) -> None:
        self.idle_watchdog_timer = Timing.Timer(
            interval    = 80,
            callback    = self.evaluate_animation_idle_state,
            single_shot = True,
            parent      = self
        )

    def setup_flash_timer(self) -> None:
        self.flash_decay_timer = Timing.Timer(
            interval    = 25,
            callback    = self.process_flash_decay_step,
            single_shot = False,
            parent      = self
        )

    # Event Filtering

    def eventFilter(
            self,
            watched: QObject,
            event:   QEvent
        ) -> bool:

        if event.type() == QEvent.Type.Resize:
            self.overlay.setGeometry(self.target_window.rect())

        return super().eventFilter(watched, event)

    # Matrix Projection

    def calculate_projection_transform_matrix(self) -> QMatrix4x4:
        scale_ratio = max(0.60, min(1.35, float(self.scale_handle.value)))

        rotation_x = max(-35.0, min(35.0, float(self.rotation_x_handle.value)))
        rotation_y = max(-35.0, min(35.0, float(self.rotation_y_handle.value)))
        rotation_z = max(-30.0, min(30.0, float(self.rotation_z_handle.value)))

        matrix = QMatrix4x4()
        matrix.translate(0.5, 0.5, 0.0)
        matrix.setRow(3, QVector4D(0.0, 0.0, -1.0 / self.focal_length, 1.0))

        matrix.rotate(rotation_x, 1.0, 0.0, 0.0)
        matrix.rotate(rotation_y, 0.0, 1.0, 0.0)
        matrix.rotate(rotation_z, 0.0, 0.0, 1.0)

        matrix.scale(scale_ratio, scale_ratio, 1.0)
        matrix.translate(-0.5, -0.5, 0.0)

        return matrix

    # Presentation Management

    def capture_content_buffer(self) -> None:
        if self.target_content_widget is None:
            self.target_content_widget = self.target_window.centralWidget()

        if self.target_content_widget is None:
            return

        self.static_frame_pixmap = self.target_content_widget.grab()
        self.captured_pixmap     = QPixmap(self.static_frame_pixmap)

        self.overlay.upload_scene_texture(self.captured_pixmap)

    def activate_visual_transformation(self) -> None:
        if self.is_visual_animating:
            return

        self.capture_content_buffer()

        self.overlay.setGeometry(self.target_window.rect())
        self.overlay.show()
        self.overlay.raise_()

        LoomEngine.ui_engine.acquire()

        self.is_visual_animating = True

    def finish_visual_transformation(self) -> None:
        if not self.is_visual_animating:
            return

        if self.glass_shatter_active:
            return

        if self.collapse_timer is not None and self.collapse_timer.isActive():
            return

        self.is_visual_animating = False

        self.overlay.hide()

        self.captured_pixmap     = None
        self.static_frame_pixmap = None

        LoomEngine.ui_engine.release()

    def is_transform_busy(self) -> bool:
        return (
            abs(self.rotation_x_handle.value) > 0.05       or
            abs(self.rotation_y_handle.value) > 0.05       or
            abs(self.rotation_z_handle.value) > 0.05       or
            abs(self.scale_handle.value - 1.0) > 0.005     or
            abs(self.offset_x_handle.value) > 0.5          or
            abs(self.offset_y_handle.value) > 0.5          or
            self.glass_shatter_active                      or
            (self.collapse_timer is not None and self.collapse_timer.isActive())
        )

    def evaluate_animation_idle_state(self) -> None:
        if not self.is_visual_animating:
            return

        if self.is_transform_busy():
            self.idle_watchdog_timer.start(80)

            return

        self.finish_visual_transformation()

    # Callbacks

    def handle_visual_property_changed(self, value: float) -> None:
        if self.is_transform_busy():
            if not self.is_visual_animating:
                self.activate_visual_transformation()

            self.overlay.update()
            self.idle_watchdog_timer.start(80)

        elif self.is_visual_animating:
            if not self.idle_watchdog_timer.isActive():
                self.idle_watchdog_timer.start(80)

        self.transformed.emit()

    def reset(
            self,
            duration_ms: int = 250
        ) -> None:

        self.rotation_x_handle.set_target(0.0, duration_ms, LoomEngine.Easing.ease_out_cubic)
        self.rotation_y_handle.set_target(0.0, duration_ms, LoomEngine.Easing.ease_out_cubic)
        self.rotation_z_handle.set_target(0.0, duration_ms, LoomEngine.Easing.ease_out_cubic)

        self.scale_handle.set_target(1.0, duration_ms, LoomEngine.Easing.ease_out_cubic)

        self.offset_x_handle.set_target(0.0, duration_ms, LoomEngine.Easing.ease_out_cubic)
        self.offset_y_handle.set_target(0.0, duration_ms, LoomEngine.Easing.ease_out_cubic)

        self.idle_watchdog_timer.start(duration_ms + 40)

    # Glass Shatter

    def trigger_glass_shatter(
            self,
            impact_point_x: float,
            impact_point_y: float
        ) -> None:

        if not self.is_visual_animating:
            self.activate_visual_transformation()

        self.glass_shatter_active = True
        self.impact_count        += 1
        self.concussion_flash     = 1.0
        self.impact_point_x       = impact_point_x
        self.impact_point_y       = impact_point_y
        self.impact_seed          = float(random.uniform(1.0, 999.0))

        Player.ui_player.play_sound(f".vault/NOK/Glass{random.randint(1, 3)}")
        Player.ui_player.play_sound("Alerts/Errors/MegaCritical", volume = 0.4)

        Haptics.ui_haptics.snap()

        self.scale_handle.play_curve(
            keyframes       = [(0.0, 1.0), (0.07, 1.12), (1.0, 1.0)],
            duration_ms     = 380,
            easing_function = LoomEngine.Easing.bouncy
        )

        jitter_angle = float(random.choice([-14.0, 14.0]))
        self.rotation_z_handle.play_curve(
            keyframes       = [(0.0, jitter_angle), (1.0, 0.0)],
            duration_ms     = 600,
            easing_function = LoomEngine.Easing.very_bouncy
        )

        self.offset_y_handle.play_curve(
            keyframes       = [(0.0, 22.0), (1.0, 0.0)],
            duration_ms     = 360,
            easing_function = LoomEngine.Easing.bouncy
        )

        if not self.flash_decay_timer.isActive():
            self.flash_decay_timer.start()

        self.overlay.update()

    def process_flash_decay_step(self) -> None:
        if self.concussion_flash <= 0.0:
            self.flash_decay_timer.stop()

            return

        self.concussion_flash = max(0.0, self.concussion_flash - 0.08)
        self.overlay.update()

    # Corrupt Glitch Collapse

    def start_corrupt_collapse(
            self,
            duration_ms: int = 5000,
            on_finished: Callable[[], object] | None = None
        ) -> None:

        if duration_ms <= 0:
            raise ValueError("Collapse duration must be greater than zero")

        if self.captured_pixmap is None:
            self.activate_visual_transformation()

        self.collapse_duration_ms       = float(duration_ms)
        self.collapse_start_time_sec    = time.perf_counter()
        self.collapse_finished_callback = on_finished

        if self.collapse_timer is None:
            self.collapse_timer = Timing.Timer(
                interval    = 45,
                callback    = self.process_corrupt_collapse_step,
                single_shot = False,
                parent      = self
            )

        self.collapse_timer.start()

    def process_corrupt_collapse_step(self) -> None:
        if self.captured_pixmap is None or self.captured_pixmap.isNull():
            self.stop_corrupt_collapse()

            return

        elapsed_time_ms = (time.perf_counter() - self.collapse_start_time_sec) * 1000.0
        progress_ratio  = max(0.0, min(1.0, elapsed_time_ms / self.collapse_duration_ms))
        eased_progress  = progress_ratio ** 1.7

        current_chunk_size = max(2, int(round(20.0 - (18.0 * eased_progress))))
        next_interval_ms   = max(12, int(round(45.0 - (33.0 * eased_progress))))

        if self.collapse_timer is not None:
            self.collapse_timer.setInterval(next_interval_ms)

        pixmap_width  = self.captured_pixmap.width()
        pixmap_height = self.captured_pixmap.height()

        painter = QPainter(self.captured_pixmap)

        slices_per_tick = int(25 + (650 * eased_progress))
        darkness_alpha  = int(round(255.0 * eased_progress))

        for slice_index in range(slices_per_tick):
            source_x = random.randint(0, max(0, pixmap_width - current_chunk_size))
            source_y = random.randint(0, max(0, pixmap_height - current_chunk_size))

            target_x = random.randint(0, max(0, pixmap_width - current_chunk_size))
            target_y = random.randint(0, max(0, pixmap_height - current_chunk_size))

            copied_fragment = self.captured_pixmap.copy(
                source_x,
                source_y,
                current_chunk_size,
                current_chunk_size
            )

            painter.drawPixmap(target_x, target_y, copied_fragment)

            if darkness_alpha > 0:
                painter.fillRect(
                    target_x,
                    target_y,
                    current_chunk_size,
                    current_chunk_size,
                    QColor(0, 0, 0, darkness_alpha)
                )

                if random.random() < (darkness_alpha / 255.0):
                    painter.fillRect(
                        target_x,
                        target_y,
                        current_chunk_size,
                        current_chunk_size,
                        QColor(0, 0, 0, 255)
                    )

        dot_spacing = 18
        dot_radius  = max(1, int(round((dot_spacing * 0.85) * eased_progress)))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, darkness_alpha))

        for dot_y in range(-dot_spacing // 2, pixmap_height + dot_spacing // 2, dot_spacing):
            for dot_x in range(-dot_spacing // 2, pixmap_width + dot_spacing // 2, dot_spacing):
                painter.drawEllipse(
                    dot_x - dot_radius,
                    dot_y - dot_radius,
                    dot_radius * 2,
                    dot_radius * 2
                )

        if progress_ratio >= 1.0:
            painter.fillRect(self.captured_pixmap.rect(), QColor(0, 0, 0, 255))

        painter.end()

        self.overlay.upload_scene_texture(self.captured_pixmap)
        self.overlay.update()

        if progress_ratio >= 1.0:
            self.stop_corrupt_collapse()

    def stop_corrupt_collapse(self) -> None:
        if self.collapse_timer is not None:
            self.collapse_timer.stop()
            self.collapse_timer.deleteLater()
            self.collapse_timer = None

        if self.collapse_finished_callback is not None:
            callback = self.collapse_finished_callback
            self.collapse_finished_callback = None
            callback()

    # Static Registry

    @classmethod
    def get(
            cls,
            window: QWidget | None = None
        ) -> WindowAnimator | None:

        if window is not None and window in cls.active_animators:
            return cls.active_animators[window]

        if not cls.active_animators:
            return None

        return next(iter(cls.active_animators.values()))