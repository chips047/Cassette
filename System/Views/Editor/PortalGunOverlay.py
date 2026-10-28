from __future__ import annotations

import os
import json
import math
import numpy
import random
import struct

from OpenGL import GL
from OpenGL.GL import shaders

from PyQt6.QtCore import (
    Qt,
    QRect,
    QPointF,
    pyqtSignal
)

from PyQt6.QtGui import (
    QImage,
    QCursor,
    QVector3D,
    QMatrix4x4,
    QMouseEvent,
    QWheelEvent,
    QResizeEvent,
    QSurfaceFormat
)

from PyQt6.QtWidgets import QWidget
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from System.Common import (
    Dev,
    Utils,
    Constants
)

from System.Services import (
    Player,
    Haptics
)

from System.Interface import Timing

from System.Interface.Animation import (
    Lifecycle,
    LoomEngine,
    WindowAnimator
)

# Shader Sources

PORTAL_VERTEX_SHADER = """
#version 410 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec2 in_uv;

out vec2 v_uv;
out vec2 v_screen_uv;

uniform mat4 u_mvp;

void main() {
    v_uv = in_uv;
    vec4 clip_pos = u_mvp * vec4(in_position, 1.0);
    gl_Position = clip_pos;

    vec2 ndc = clip_pos.xy / clip_pos.w;
    v_screen_uv = ndc * 0.5 + 0.5;
}
"""

PORTAL_FRAGMENT_SHADER = """
#version 410 core
in vec2 v_uv;
in vec2 v_screen_uv;

out vec4 frag_color;

uniform float u_portal_phase;
uniform float u_alpha;
uniform int   u_portal_mode;

uniform vec2  u_portal_screen_pos;
uniform vec2  u_target_screen_pos;
uniform vec2  u_screen_size;
uniform float u_portal_radius_px;

uniform float u_suction_power;
uniform float u_spin_speed;
uniform float u_close_progress;
uniform float u_instability;

uniform sampler2D u_scene_tex;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(hash(i + vec2(0.0, 0.0)), hash(i + vec2(1.0, 0.0)), u.x),
        mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
        u.y
    );
}

float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    mat2 rot = mat2(0.8, 0.6, -0.6, 0.8);
    for (int i = 0; i < 4; ++i) {
        v += a * noise(p);
        p = rot * p * 2.1 + vec2(1.7, 9.2);
        a *= 0.5;
    }
    return v;
}

vec4 render_black_hole(vec2 p, float dist) {
    float collapse_pinch = pow(u_close_progress, 1.6);
    float r_event_horizon = max(0.001, (0.32 - collapse_pinch * 0.32) * (1.0 + u_instability * 0.45));
    float r_photon_sphere = r_event_horizon * 1.18;

    float deflection = (0.10 / max(0.001, (dist - r_event_horizon + 0.04))) * u_suction_power;
    float swirl_angle = atan(p.y, p.x) + ((1.2 * u_spin_speed) / (dist + 0.08)) - u_portal_phase * 3.4;

    vec2 swirled_p = vec2(cos(swirl_angle), sin(swirl_angle)) * max(0.0, dist - deflection * 0.14);

    vec2 pull_offset = (swirled_p * u_portal_radius_px) / u_screen_size;
    vec2 scene_coord = u_portal_screen_pos + pull_offset;
    scene_coord.y = 1.0 - scene_coord.y;

    float disp_amount = deflection * 0.04 * u_suction_power;
    float tex_r = texture(u_scene_tex, scene_coord * (1.0 + disp_amount)).r;
    float tex_g = texture(u_scene_tex, scene_coord).g;
    float tex_b = texture(u_scene_tex, scene_coord * (1.0 - disp_amount)).b;
    vec3 warped_scene = vec3(tex_r, tex_g, tex_b);

    float gas_noise = fbm(swirled_p * (4.5 + u_close_progress * 3.0) + vec2(u_portal_phase * 1.6, -u_portal_phase * 1.0));
    float doppler = clamp(0.55 + 1.25 * (-p.x * 0.75 - p.y * 0.25), 0.2, 2.2);

    vec3 hot_plasma = mix(vec3(0.95, 1.00, 0.50), vec3(1.0, 0.22, 0.1), u_instability);
    vec3 deep_green = mix(vec3(0.12, 0.85, 0.22), vec3(0.85, 0.12, 0.75), u_instability);
    vec3 dark_edge  = vec3(0.01, 0.04, 0.02);

    vec3 disk_color = mix(hot_plasma, deep_green, smoothstep(0.35, 0.70, dist + gas_noise * 0.2));
    disk_color = mix(disk_color, dark_edge, smoothstep(0.70, 0.98, dist));
    disk_color *= doppler * (1.0 + gas_noise * 1.4);

    float photon_ring = exp(-pow(abs(dist - r_photon_sphere) * (42.0 + u_close_progress * 50.0), 2.0)) * 3.8;
    disk_color += mix(vec3(0.85, 1.0, 0.75), vec3(1.0, 0.9, 0.4), u_instability) * photon_ring;

    vec3 composite = mix(warped_scene * 0.85, disk_color, smoothstep(0.25, 0.75, (gas_noise * 0.5 + (1.0 - dist) * 0.7) * u_suction_power));

    if (dist <= r_event_horizon) {
        float shadow_falloff = smoothstep(r_event_horizon, r_event_horizon - 0.04, dist);
        composite = mix(composite, vec3(0.0), shadow_falloff);
    }

    if (u_close_progress > 0.65 || u_instability > 0.6) {
        float snap_flash = exp(-dist * 18.0) * pow(max(u_close_progress, u_instability), 2.0) * 8.0;
        composite += vec3(0.7, 1.0, 0.5) * snap_flash;
    }

    float edge_alpha = smoothstep(1.0, 0.82, dist) * (1.0 - pow(u_close_progress, 3.0));
    return vec4(composite, edge_alpha);
}

vec4 render_white_hole(vec2 p, float dist) {
    float current_power = u_suction_power * (1.0 - u_close_progress);
    float expansion = pow(1.0 - dist, 1.8) * 0.45 * current_power;
    float burst_angle = atan(p.y, p.x) - ((1.0 * u_spin_speed) / (dist + 0.12)) + u_portal_phase * 4.2;

    vec2 ejected_p = vec2(cos(burst_angle), sin(burst_angle)) * (dist + expansion);

    vec2 target_offset = (ejected_p * u_portal_radius_px * 1.3) / u_screen_size;
    vec2 scene_coord = u_target_screen_pos + target_offset;
    scene_coord.y = 1.0 - scene_coord.y;

    float tex_r = texture(u_scene_tex, scene_coord * (1.0 + 0.03 * current_power)).r;
    float tex_g = texture(u_scene_tex, scene_coord).g;
    float tex_b = texture(u_scene_tex, scene_coord * (1.0 - 0.03 * current_power)).b;
    vec3 ejected_matter = vec3(tex_r, tex_g, tex_b);

    float radial_jets = fbm(vec2(atan(p.y, p.x) * 3.5 - u_portal_phase * 2.8, dist * 3.0 - u_portal_phase * 3.5));
    float shockwaves = sin(dist * 35.0 - u_portal_phase * 16.0) * 0.5 + 0.5;

    vec3 quasar_core   = vec3(1.00, 1.00, 0.95);
    vec3 emerald_burst = vec3(0.20, 1.00, 0.35);
    vec3 outer_corona  = vec3(0.04, 0.45, 0.15);

    vec3 plasma_color = mix(quasar_core, emerald_burst, smoothstep(0.05, 0.45, dist));
    plasma_color = mix(plasma_color, outer_corona, smoothstep(0.45, 0.95, dist));
    plasma_color += emerald_burst * radial_jets * 1.8 * current_power;
    plasma_color += quasar_core * shockwaves * (1.0 - dist) * 0.6 * current_power;

    float singularity_flash = exp(-dist * 8.0) * (2.5 * current_power + u_close_progress * 4.0);
    plasma_color += vec3(1.0) * singularity_flash;

    vec3 composite = mix(ejected_matter, plasma_color, smoothstep(0.2, 0.85, (radial_jets + (1.0 - dist) * 0.8) * current_power));

    float edge_alpha = smoothstep(1.0, 0.80, dist) * (1.0 - pow(u_close_progress, 3.0));
    return vec4(composite, edge_alpha);
}

vec4 render_single_portal(vec2 p, float dist) {
    float angle = atan(p.y, p.x);
    float swirl = angle + 3.2 * dist - u_portal_phase * 2.4;
    vec2 swirl_coord = vec2(cos(swirl), sin(swirl)) * dist;

    float plasma1 = fbm(swirl_coord * 3.6 + vec2(u_portal_phase * 0.35, -u_portal_phase * 0.25));
    float plasma2 = fbm(p * 4.2 - vec2(cos(u_portal_phase * 0.8), sin(u_portal_phase * 0.8)) * 0.4);
    float fluid = mix(plasma1, plasma2, 0.5);

    vec3 core_color   = vec3(0.88, 1.00, 0.45);
    vec3 bright_green = vec3(0.28, 0.96, 0.16);
    vec3 dark_green   = vec3(0.06, 0.44, 0.08);
    vec3 rim_black    = vec3(0.01, 0.12, 0.02);

    float rim = smoothstep(1.0, 0.78, dist);

    vec3 color = mix(core_color, bright_green, smoothstep(0.08, 0.55, dist + fluid * 0.28));
    color = mix(color, dark_green, smoothstep(0.48, 0.88, dist + fluid * 0.2));
    color = mix(color, rim_black, smoothstep(0.82, 1.0, dist));

    float filaments = pow(fluid, 2.8) * 2.0;
    color += bright_green * filaments * rim;

    float alpha = rim * (1.0 - pow(u_close_progress, 2.5));
    return vec4(color, alpha);
}

void main() {
    vec2 centered = (v_uv - 0.5) * 2.0;
    float dist = length(centered);

    if (dist > 1.0) {
        discard;
    }

    vec4 portal_output;

    if (u_portal_mode == 1) {
        portal_output = render_black_hole(centered, dist);
    } else if (u_portal_mode == 2) {
        portal_output = render_white_hole(centered, dist);
    } else {
        portal_output = render_single_portal(centered, dist);
    }

    frag_color = vec4(portal_output.rgb, portal_output.a * u_alpha);
}
"""

DAMAGE_VERTEX_SHADER = """
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

DAMAGE_FRAGMENT_SHADER = """
#version 410 core
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_damage_tex;

void main() {
    vec4 damage_sample = texture(u_damage_tex, v_uv);
    if (damage_sample.a < 0.005) {
        discard;
    }
    frag_color = damage_sample;
}
"""

GUN_VERTEX_SHADER = """
#version 410 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec3 in_color;
layout(location = 3) in float in_emissive;

out vec3 v_normal;
out vec3 v_frag_pos;
out vec3 v_color;
out float v_emissive;

uniform mat4 u_mvp;
uniform mat4 u_model;

void main() {
    v_normal = mat3(transpose(inverse(u_model))) * in_normal;
    v_frag_pos = vec3(u_model * vec4(in_position, 1.0));
    v_color = in_color;
    v_emissive = in_emissive;

    gl_Position = u_mvp * vec4(in_position, 1.0);
}
"""

GUN_FRAGMENT_SHADER = """
#version 410 core
in vec3 v_normal;
in vec3 v_frag_pos;
in vec3 v_color;
in float v_emissive;

out vec4 frag_color;

uniform vec3  u_light_pos;
uniform vec3  u_view_pos;
uniform float u_bulb_glow;
uniform float u_alpha;

void main() {
    if (v_emissive > 0.5) {
        vec3 glow_color = vec3(0.28, 1.0, 0.18) * u_bulb_glow * 1.6;
        frag_color = vec4(glow_color, u_alpha);
        return;
    }

    vec3 normal = normalize(v_normal);
    vec3 light_dir = normalize(u_light_pos - v_frag_pos);
    float diff = max(dot(normal, light_dir), 0.0);

    vec3 view_dir = normalize(u_view_pos - v_frag_pos);
    vec3 reflect_dir = reflect(-light_dir, normal);
    float spec = pow(max(dot(view_dir, reflect_dir), 0.0), 16.0);

    vec3 ambient = 0.35 * v_color;
    vec3 diffuse = diff * v_color * 0.75;
    vec3 specular = spec * vec3(0.4);

    vec3 final_rgb = ambient + diffuse + specular;
    frag_color = vec4(final_rgb, u_alpha);
}
"""

BEAM_VERTEX_SHADER = """
#version 410 core
layout(location = 0) in vec3 in_position;

uniform mat4 u_mvp;

void main() {
    gl_Position = u_mvp * vec4(in_position, 1.0);
}
"""

BEAM_FRAGMENT_SHADER = """
#version 410 core
out vec4 frag_color;

uniform vec4 u_beam_color;

void main() {
    frag_color = u_beam_color;
}
"""

# Portal Instance Record

class PortalInstance:
    def __init__(
            self,
            position:    QVector3D,
            normal:      QVector3D,
            time_offset: float = 0.0
        ) -> None:

        self.position         = position
        self.normal           = normal
        self.scale            = 0.0
        self.alpha            = 1.0
        self.time_offset      = time_offset
        self.opening_progress = 0.0
        self.is_closing       = False
        self.closing_progress = 0.0
        self.mode             = 0
        self.suction_power    = 0.0
        self.spin_speed       = 0.20
        self.spin_phase       = time_offset
        self.instability      = 0.0

# Portal Gun Overlay Widget

@Dev.track_ram
class PortalGunOverlay(Lifecycle.LoomAnimationMixin, QOpenGLWidget):
    dismiss_requested = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.gun_position_x               = 0.0
        self.gun_position_y               = -200.0
        self.gun_velocity_x               = 0.0
        self.gun_velocity_y               = 0.0
        self.recoil_offset_x              = 0.0
        self.recoil_offset_y              = 0.0

        self.gun_rotation_x               = 0.0
        self.gun_rotation_y               = 0.0
        self.gun_rotation_z               = 0.0

        self.angular_velocity_x           = 0.0
        self.angular_velocity_y           = 0.0
        self.angular_velocity_z           = 0.0

        self.gun_is_falling               = True
        self.gun_is_equipped              = False
        self.gun_is_resting               = False

        self.drop_played                  = False

        self.portals: list[PortalInstance]         = []
        self.closing_portal: PortalInstance | None = None
        self.portal_time                           = 0.0
        self.is_capturing_scene                    = False

        self.merger_in_progress                    = False
        self.merger_progress                       = 0.0
        self.merger_primary_portal: PortalInstance | None = None
        self.merger_start_position                 = QVector3D()
        self.merger_impact_position                = QVector3D()
        self.merger_center_x                       = 0.0
        self.merger_center_y                       = 0.0

        self.clean_scene_array: numpy.ndarray | None      = None
        self.damage_array: numpy.ndarray | None           = None
        self.has_damage                            = False
        self.transfer_step_accumulator             = 0

        self.projectile_active            = False
        self.projectile_start             = QPointF()
        self.projectile_end               = QPointF()
        self.projectile_progress          = 0.0
        self.projectile_hits_glass        = False

        self.muzzle_flash_alpha           = 0.0
        self.bulb_glow_pulse              = 1.0

        self.gun_mesh_vertex_array_object  = None
        self.gun_mesh_vertex_buffer_object = None
        self.gun_vertex_count             = 0

        self.quad_vertex_array_object     = None
        self.quad_vertex_buffer_object    = None

        self.beam_vertex_array_object     = None
        self.beam_vertex_buffer_object    = None

        self.portal_shader                = None
        self.damage_shader                = None
        self.gun_shader                   = None
        self.beam_shader                  = None

        self.scene_texture_id             = None
        self.damage_texture_id            = None

        self.setup_surface_format()
        self.setup_widget_properties()
        self.setup_simulation_timer()

    # Setup Methods

    def setup_surface_format(self) -> None:
        surface_format = QSurfaceFormat()
        surface_format.setVersion(4, 1)
        surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        surface_format.setDepthBufferSize(24)
        surface_format.setAlphaBufferSize(8)
        surface_format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)

        self.setFormat(surface_format)

    def setup_widget_properties(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        parent_rect = self.parentWidget().rect() if self.parentWidget() else QRect(0, 0, 1000, 640)
        self.setGeometry(parent_rect)
        self.show()
        self.raise_()

    def setup_simulation_timer(self) -> None:
        self.timer = Timing.Timer(
            interval    = Constants.FPS_60,
            callback    = self.advance_simulation_step,
            parent      = self,
            fps_managed = True,
            auto_start  = True
        )

    # OpenGL Initialization

    def initializeGL(self) -> None:
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)

        portal_vertex_shader   = shaders.compileShader(PORTAL_VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        portal_fragment_shader = shaders.compileShader(PORTAL_FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        self.portal_shader     = shaders.compileProgram(portal_vertex_shader, portal_fragment_shader)

        damage_vertex_shader   = shaders.compileShader(DAMAGE_VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        damage_fragment_shader = shaders.compileShader(DAMAGE_FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        self.damage_shader     = shaders.compileProgram(damage_vertex_shader, damage_fragment_shader)

        gun_vertex_shader      = shaders.compileShader(GUN_VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        gun_fragment_shader    = shaders.compileShader(GUN_FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        self.gun_shader        = shaders.compileProgram(gun_vertex_shader, gun_fragment_shader)

        beam_vertex_shader     = shaders.compileShader(BEAM_VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        beam_fragment_shader   = shaders.compileShader(BEAM_FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        self.beam_shader       = shaders.compileProgram(beam_vertex_shader, beam_fragment_shader)

        self.scene_texture_id  = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.scene_texture_id)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        self.damage_texture_id = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.damage_texture_id)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        self.build_portal_quad()
        self.build_beam_buffers()
        self.load_gun_geometry()

    # Geometry Buffers

    def build_portal_quad(self) -> None:
        vertices = numpy.array([
            -1.0, -1.0, 0.0,  0.0, 0.0,
             1.0, -1.0, 0.0,  1.0, 0.0,
             1.0,  1.0, 0.0,  1.0, 1.0,
            -1.0, -1.0, 0.0,  0.0, 0.0,
             1.0,  1.0, 0.0,  1.0, 1.0,
            -1.0,  1.0, 0.0,  0.0, 1.0
        ], dtype = numpy.float32)

        self.quad_vertex_array_object  = GL.glGenVertexArrays(1)
        self.quad_vertex_buffer_object = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.quad_vertex_array_object)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.quad_vertex_buffer_object)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STATIC_DRAW)

        stride = 5 * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(0))

        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(12))

        GL.glBindVertexArray(0)

    def build_beam_buffers(self) -> None:
        self.beam_vertex_array_object  = GL.glGenVertexArrays(1)
        self.beam_vertex_buffer_object = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.beam_vertex_array_object)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.beam_vertex_buffer_object)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 6 * 3 * 4, None, GL.GL_DYNAMIC_DRAW)

        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 3 * 4, GL.ctypes.c_void_p(0))

        GL.glBindVertexArray(0)

    def setup_gun_mesh_buffers(self, vertex_data: numpy.ndarray) -> None:
        flat_data = vertex_data.flatten()
        self.gun_vertex_count = len(vertex_data)

        self.gun_mesh_vertex_array_object  = GL.glGenVertexArrays(1)
        self.gun_mesh_vertex_buffer_object = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.gun_mesh_vertex_array_object)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.gun_mesh_vertex_buffer_object)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, flat_data.nbytes, flat_data, GL.GL_STATIC_DRAW)

        stride = 10 * 4

        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(0))

        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(12))

        GL.glEnableVertexAttribArray(2)
        GL.glVertexAttribPointer(2, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(24))

        GL.glEnableVertexAttribArray(3)
        GL.glVertexAttribPointer(3, 1, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(36))

        GL.glBindVertexArray(0)

    # Model Loader

    def load_gun_geometry(self) -> None:
        model_path = Utils.get_resource_path("System/Assets/3D/PortalGun.glb")

        with open(model_path, "rb") as file_handle:
            file_bytes = file_handle.read()

        json_length   = struct.unpack("<I", file_bytes[12:16])[0]
        parsed_json   = json.loads(file_bytes[20:20 + json_length].decode("utf-8"))

        binary_offset = 20 + json_length + 8
        binary_data   = file_bytes[binary_offset:]

        component_types = {
            5120: numpy.int8,
            5121: numpy.uint8,
            5122: numpy.int16,
            5123: numpy.uint16,
            5125: numpy.uint32,
            5126: numpy.float32
        }

        type_dimensions = {
            "SCALAR": 1,
            "VEC2":   2,
            "VEC3":   3,
            "VEC4":   4
        }

        def read_accessor(accessor_index: int) -> numpy.ndarray:
            accessor_dictionary    = parsed_json["accessors"][accessor_index]
            buffer_view_dictionary = parsed_json["bufferViews"][accessor_dictionary["bufferView"]]
            offset                 = buffer_view_dictionary.get("byteOffset", 0) + accessor_dictionary.get("byteOffset", 0)
            component_type         = component_types[accessor_dictionary["componentType"]]
            dimensions             = type_dimensions[accessor_dictionary["type"]]
            count                  = accessor_dictionary["count"]
            stride                 = buffer_view_dictionary.get("byteStride", 0)
            element_size           = dimensions * numpy.dtype(component_type).itemsize

            if stride == 0 or stride == element_size:
                data_slice = numpy.frombuffer(
                    binary_data,
                    dtype  = component_type,
                    count  = count * dimensions,
                    offset = offset
                )

                if dimensions > 1:
                    data_slice = data_slice.reshape((count, dimensions))

                return data_slice

            result = numpy.empty((count, dimensions), dtype = component_type)

            for step_index in range(count):
                start_byte = offset + step_index * stride
                result[step_index] = numpy.frombuffer(binary_data[start_byte : start_byte + element_size], dtype = component_type)

            return result

        combined_vertices: list[numpy.ndarray] = []

        for mesh in parsed_json.get("meshes", []):
            for primitive in mesh.get("primitives", []):
                attributes = primitive.get("attributes", {})

                if "POSITION" not in attributes:
                    continue

                positions = read_accessor(attributes["POSITION"]).astype(numpy.float32)
                normals   = None

                if "NORMAL" in attributes:
                    normals = read_accessor(attributes["NORMAL"]).astype(numpy.float32)

                if "indices" in primitive:
                    indices   = read_accessor(primitive["indices"]).astype(numpy.int64).flatten()
                    positions = positions[indices]

                    if normals is not None:
                        normals = normals[indices]

                if normals is None:
                    triangle_count = len(positions) // 3
                    triangles      = positions[: triangle_count * 3].reshape(-1, 3, 3)
                    edge_one       = triangles[:, 1] - triangles[:, 0]
                    edge_two       = triangles[:, 2] - triangles[:, 0]
                    face_normals   = numpy.cross(edge_one, edge_two)
                    lengths        = numpy.linalg.norm(face_normals, axis = 1, keepdims = True)
                    lengths[lengths == 0] = 1.0
                    face_normals   = face_normals / lengths
                    normals        = numpy.repeat(face_normals, 3, axis = 0)

                material_index = primitive.get("material", 0)
                materials_list = parsed_json.get("materials", [])
                material_dict  = materials_list[material_index] if material_index < len(materials_list) else {}
                material_name  = str(material_dict.get("name", "")).lower()

                physically_based_rendering_information = material_dict.get("pbrMetallicRoughness", {})
                base_color                             = physically_based_rendering_information.get("baseColorFactor", [0.86, 0.86, 0.88, 1.0])[:3]

                is_glow = (
                    "fluid" in material_name or
                    "liquid" in material_name or
                    "green" in material_name or
                    "bulb" in material_name or
                    "glass" in material_name
                )

                if is_glow or (base_color[1] > 0.65 and base_color[0] < 0.4):
                    color_rgb     = [0.25, 0.98, 0.18]
                    emissive_flag = 1.0

                else:
                    color_rgb     = [base_color[0], base_color[1], base_color[2]]
                    emissive_flag = 0.0

                vertex_count = len(positions)
                interleaved  = numpy.empty((vertex_count, 10), dtype = numpy.float32)

                interleaved[:, 0:3] = positions
                interleaved[:, 3:6] = normals
                interleaved[:, 6:9] = color_rgb
                interleaved[:, 9]   = emissive_flag

                combined_vertices.append(interleaved)

        all_data = numpy.concatenate(combined_vertices, axis = 0)

        positions_only = all_data[:, 0:3]
        min_bounds     = numpy.min(positions_only, axis = 0)
        max_bounds     = numpy.max(positions_only, axis = 0)
        center         = (min_bounds + max_bounds) / 2.0
        span_size      = float(numpy.max(max_bounds - min_bounds))

        if span_size <= 0.0:
            span_size = 1.0

        all_data[:, 0:3] = (all_data[:, 0:3] - center) / span_size

        extents = max_bounds - min_bounds

        if extents[2] > extents[0] and extents[2] > extents[1]:
            temporary_position_x = numpy.copy(all_data[:, 0])
            all_data[:, 0]       = all_data[:, 2]
            all_data[:, 2]       = -temporary_position_x

            temporary_normal_x   = numpy.copy(all_data[:, 3])
            all_data[:, 3]       = all_data[:, 5]
            all_data[:, 5]       = -temporary_normal_x

        all_data[:, 0] = -all_data[:, 0]
        all_data[:, 2] = -all_data[:, 2]
        all_data[:, 3] = -all_data[:, 3]
        all_data[:, 5] = -all_data[:, 5]

        self.setup_gun_mesh_buffers(all_data)

    # Scene Capture

    def capture_underlying_scene(self) -> None:
        if self.is_capturing_scene:
            return

        parent = self.parentWidget()

        if parent is None:
            return

        width_px  = self.width()
        height_px = self.height()

        if width_px <= 0 or height_px <= 0:
            return

        self.is_capturing_scene = True

        try:
            was_visible = self.isVisible()

            if was_visible:
                self.setVisible(False)

            pixmap = parent.grab()

            if was_visible:
                self.setVisible(True)

            image     = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            pointer   = image.bits()
            pointer.setsize(image.sizeInBytes())
            raw_bytes = bytes(pointer)

            self.clean_scene_array = numpy.frombuffer(raw_bytes, dtype = numpy.uint8).reshape((height_px, width_px, 4)).copy()

            if self.damage_array is None or self.damage_array.shape != (height_px, width_px, 4):
                self.damage_array = numpy.zeros((height_px, width_px, 4), dtype = numpy.uint8)

            GL.glBindTexture(GL.GL_TEXTURE_2D, self.scene_texture_id)
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D, 0, GL.GL_RGBA,
                width_px, height_px, 0,
                GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, raw_bytes
            )
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

            GL.glBindTexture(GL.GL_TEXTURE_2D, self.damage_texture_id)
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D, 0, GL.GL_RGBA,
                width_px, height_px, 0,
                GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, self.damage_array.tobytes()
            )
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        finally:
            self.is_capturing_scene = False

    def update_damage_texture_region(
            self,
            minimum_x: int,
            minimum_y: int,
            maximum_x: int,
            maximum_y: int
        ) -> None:

        if self.damage_array is None:
            return

        sub_array = self.damage_array[minimum_y : maximum_y, minimum_x : maximum_x].copy()
        sub_bytes = sub_array.tobytes()

        GL.glBindTexture(GL.GL_TEXTURE_2D, self.damage_texture_id)
        GL.glTexSubImage2D(
            GL.GL_TEXTURE_2D, 0,
            minimum_x, minimum_y,
            maximum_x - minimum_x, maximum_y - minimum_y,
            GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, sub_bytes
        )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    # Matter Transfer Engine

    def process_matter_transfer(self) -> None:
        if self.damage_array is None or self.clean_scene_array is None or len(self.portals) < 2:
            return

        portal_source = self.portals[0]
        portal_target = self.portals[1]

        if portal_source.suction_power < 0.15 or portal_source.scale < 0.20:
            return

        height_px, width_px, _ = self.damage_array.shape

        source_center_x = int(portal_source.position.x())
        source_center_y = int(portal_source.position.y())

        target_center_x = int(portal_target.position.x())
        target_center_y = int(portal_target.position.y())

        carve_radius_px = int(95.0 * portal_source.scale * portal_source.suction_power)

        if carve_radius_px < 6:
            return

        source_min_x = max(0, source_center_x - carve_radius_px)
        source_max_x = min(width_px, source_center_x + carve_radius_px)
        source_min_y = max(0, source_center_y - carve_radius_px)
        source_max_y = min(height_px, source_center_y + carve_radius_px)

        if source_max_x <= source_min_x or source_max_y <= source_min_y:
            return

        grid_y, grid_x = numpy.ogrid[
            source_min_y - source_center_y : source_max_y - source_center_y,
            source_min_x - source_center_x : source_max_x - source_center_x
        ]

        distance_squared = grid_x * grid_x + grid_y * grid_y
        radius_squared   = float(carve_radius_px * carve_radius_px)
        inside_mask      = distance_squared <= radius_squared

        if not numpy.any(inside_mask):
            return

        source_damage_slice = self.damage_array[source_min_y : source_max_y, source_min_x : source_max_x]
        source_clean_slice  = self.clean_scene_array[source_min_y : source_max_y, source_min_x : source_max_x]

        stolen_matter_sample = source_clean_slice[inside_mask].copy()

        normalized_dist = numpy.sqrt(distance_squared[inside_mask]) / float(carve_radius_px)
        void_alpha      = numpy.clip((1.0 - normalized_dist * 0.95) * 255.0, 0, 255).astype(numpy.uint8)

        source_damage_slice[inside_mask, 0] = numpy.clip(source_damage_slice[inside_mask, 0] * 0.92 + 2, 0, 255).astype(numpy.uint8)
        source_damage_slice[inside_mask, 1] = numpy.clip(source_damage_slice[inside_mask, 1] * 0.92 + 8, 0, 255).astype(numpy.uint8)
        source_damage_slice[inside_mask, 2] = numpy.clip(source_damage_slice[inside_mask, 2] * 0.92 + 3, 0, 255).astype(numpy.uint8)
        source_damage_slice[inside_mask, 3] = numpy.maximum(source_damage_slice[inside_mask, 3], void_alpha)

        event_horizon_core = distance_squared <= (radius_squared * 0.22)
        source_damage_slice[event_horizon_core, 0:3] = 0
        source_damage_slice[event_horizon_core, 3]   = 255

        self.update_damage_texture_region(source_min_x, source_min_y, source_max_x, source_max_y)

        target_min_x = max(0, target_center_x - carve_radius_px)
        target_max_x = min(width_px, target_center_x + carve_radius_px)
        target_min_y = max(0, target_center_y - carve_radius_px)
        target_max_y = min(height_px, target_center_y + carve_radius_px)

        if target_max_x <= target_min_x or target_max_y <= target_min_y:
            self.has_damage = True
            return

        target_damage_slice = self.damage_array[target_min_y : target_max_y, target_min_x : target_max_x]

        target_grid_y, target_grid_x = numpy.ogrid[
            target_min_y - target_center_y : target_max_y - target_center_y,
            target_min_x - target_center_x : target_max_x - target_center_x
        ]

        target_dist_sq = target_grid_x * target_grid_x + target_grid_y * target_grid_y
        target_mask    = target_dist_sq <= radius_squared

        matching_elements = min(len(stolen_matter_sample), numpy.count_nonzero(target_mask))

        if matching_elements > 0:
            target_indices = numpy.where(target_mask)
            sub_target_y   = target_indices[0][:matching_elements]
            sub_target_x   = target_indices[1][:matching_elements]

            eject_portion  = stolen_matter_sample[:matching_elements]
            deposit_rate   = 0.08

            for channel in range(3):
                target_damage_slice[sub_target_y, sub_target_x, channel] = numpy.clip(
                    target_damage_slice[sub_target_y, sub_target_x, channel] * (1.0 - deposit_rate) +
                    eject_portion[:, channel] * deposit_rate,
                    0, 255
                ).astype(numpy.uint8)

            target_damage_slice[sub_target_y, sub_target_x, 1] = numpy.clip(
                target_damage_slice[sub_target_y, sub_target_x, 1] + 3, 0, 255
            ).astype(numpy.uint8)

            target_damage_slice[sub_target_y, sub_target_x, 3] = numpy.maximum(
                target_damage_slice[sub_target_y, sub_target_x, 3],
                220
            )

            self.update_damage_texture_region(target_min_x, target_min_y, target_max_x, target_max_y)

        self.has_damage = True

    # Physics Simulation

    def spawn_falling_gun(self) -> None:
        window_width = float(self.width())
        target_x     = window_width - 150.0

        self.gun_position_x     = target_x
        self.gun_position_y     = -120.0
        self.gun_velocity_x     = float(random.uniform(-2.2, -1.2))
        self.gun_velocity_y     = float(random.uniform(2.5, 4.5))

        self.gun_rotation_x     = float(random.uniform(0.0, 360.0))
        self.gun_rotation_y     = float(random.uniform(0.0, 360.0))
        self.gun_rotation_z     = float(random.uniform(0.0, 360.0))

        self.angular_velocity_x = float(random.uniform(-12.0, 12.0))
        self.angular_velocity_y = float(random.uniform(-12.0, 12.0))
        self.angular_velocity_z = float(random.uniform(-14.0, 14.0))

        self.gun_is_falling     = True
        self.gun_is_resting     = False
        self.gun_is_equipped    = False

    def advance_simulation_step(self) -> None:
        self.portal_time    += 0.016
        self.bulb_glow_pulse = 0.85 + 0.35 * math.sin(self.portal_time * 6.0)

        if self.gun_is_falling:
            self.process_gun_fall_physics()

        elif self.gun_is_equipped:
            self.process_equipped_physics()

        if self.merger_in_progress:
            self.advance_merger_simulation_step()

        else:
            for portal in self.portals:
                portal.opening_progress = min(1.0, portal.opening_progress + 0.016)
                progress_eased         = portal.opening_progress * portal.opening_progress * (3.0 - 2.0 * portal.opening_progress)
                portal.scale           = progress_eased

                target_suction_power   = 1.0 if len(self.portals) >= 2 else 0.20
                portal.suction_power  += (target_suction_power - portal.suction_power) * 0.012

                target_spin_speed      = 0.65
                portal.spin_speed     += (target_spin_speed - portal.spin_speed) * 0.018
                portal.spin_phase     += 0.016 * portal.spin_speed

            self.transfer_step_accumulator += 1

            if self.transfer_step_accumulator >= 3:
                self.transfer_step_accumulator = 0
                self.process_matter_transfer()

        if self.closing_portal is not None:
            self.closing_portal.closing_progress += 0.035
            progress_factor = self.closing_portal.closing_progress
            self.closing_portal.scale = max(0.0, 1.0 - progress_factor ** 2.2)
            self.closing_portal.suction_power = max(0.0, self.closing_portal.suction_power - 0.04)
            self.closing_portal.spin_phase += 0.016 * (self.closing_portal.spin_speed * (1.0 + progress_factor * 2.0))

            if self.closing_portal.closing_progress >= 1.0:
                self.closing_portal = None

        if len(self.portals) == 2:
            self.portals[0].mode = 1
            self.portals[1].mode = 2

        elif len(self.portals) == 1:
            self.portals[0].mode = 0

        if self.projectile_active:
            self.projectile_progress += 0.22

            if self.projectile_progress >= 1.0:
                self.projectile_active = False
                self.on_projectile_impact()

        if self.muzzle_flash_alpha > 0.0:
            self.muzzle_flash_alpha = max(0.0, self.muzzle_flash_alpha - 0.14)

        self.update()

    def advance_merger_simulation_step(self) -> None:
        self.merger_progress += 0.019

        if self.merger_primary_portal is None:
            self.merger_in_progress = False
            return

        convergence_factor = 1.0 - math.pow(self.merger_progress, 1.6)
        spiral_angle       = self.merger_progress * 22.0

        offset_x = (self.merger_impact_position.x() - self.merger_center_x) * convergence_factor
        offset_y = (self.merger_impact_position.y() - self.merger_center_y) * convergence_factor

        rotated_x = offset_x * math.cos(spiral_angle) - offset_y * math.sin(spiral_angle)
        rotated_y = offset_x * math.sin(spiral_angle) + offset_y * math.cos(spiral_angle)

        self.merger_primary_portal.position = QVector3D(
            self.merger_center_x + rotated_x,
            self.merger_center_y + rotated_y,
            0.0
        )

        self.merger_primary_portal.scale        = min(1.85, 1.0 + self.merger_progress * 0.9)
        self.merger_primary_portal.suction_power = min(1.9, 1.0 + self.merger_progress * 1.2)
        self.merger_primary_portal.spin_speed    = 0.65 + self.merger_progress * 2.8
        self.merger_primary_portal.spin_phase   += 0.016 * self.merger_primary_portal.spin_speed
        self.merger_primary_portal.instability   = self.merger_progress

        shake_amplitude = self.merger_progress * 14.0
        self.recoil_offset_x = float(random.uniform(-shake_amplitude, shake_amplitude))
        self.recoil_offset_y = float(random.uniform(-shake_amplitude, shake_amplitude))

        animator = WindowAnimator.WindowAnimator.get(self.window())

        if animator is not None and self.merger_progress > 0.25:
            animator.offset_x_handle.set_target(
                float(random.uniform(-shake_amplitude * 0.4, shake_amplitude * 0.4)),
                20,
                LoomEngine.Easing.ease_out_cubic
            )
            animator.offset_y_handle.set_target(
                float(random.uniform(-shake_amplitude * 0.4, shake_amplitude * 0.4)),
                20,
                LoomEngine.Easing.ease_out_cubic
            )

        if self.merger_progress >= 1.0:
            self.detonate_portal_collision()

    def detonate_portal_collision(self) -> None:
        self.merger_in_progress = False
        detonation_x = self.merger_center_x
        detonation_y = self.merger_center_y

        self.portals.clear()
        self.closing_portal = None

        if self.damage_array is not None:
            height_px, width_px, _ = self.damage_array.shape
            crater_radius_px       = 240

            min_x = max(0, int(detonation_x) - crater_radius_px)
            max_x = min(width_px, int(detonation_x) + crater_radius_px)
            min_y = max(0, int(detonation_y) - crater_radius_px)
            max_y = min(height_px, int(detonation_y) + crater_radius_px)

            if max_x > min_x and max_y > min_y:
                grid_y, grid_x = numpy.ogrid[
                    min_y - int(detonation_y) : max_y - int(detonation_y),
                    min_x - int(detonation_x) : max_x - int(detonation_x)
                ]

                distance_sq  = grid_x * grid_x + grid_y * grid_y
                radius_sq    = float(crater_radius_px * crater_radius_px)
                inside_blast = distance_sq <= radius_sq

                damage_slice = self.damage_array[min_y : max_y, min_x : max_x]
                normalized_r = numpy.sqrt(distance_sq[inside_blast]) / float(crater_radius_px)

                burn_alpha   = numpy.clip((1.0 - normalized_r * 0.85) * 255.0, 0, 255).astype(numpy.uint8)

                damage_slice[inside_blast, 0] = numpy.clip(damage_slice[inside_blast, 0] * 0.5 + 2, 0, 255).astype(numpy.uint8)
                damage_slice[inside_blast, 1] = numpy.clip(damage_slice[inside_blast, 1] * 0.5 + 8, 0, 255).astype(numpy.uint8)
                damage_slice[inside_blast, 2] = numpy.clip(damage_slice[inside_blast, 2] * 0.5 + 3, 0, 255).astype(numpy.uint8)
                damage_slice[inside_blast, 3] = numpy.maximum(damage_slice[inside_blast, 3], burn_alpha)

                singularity_void = distance_sq <= (radius_sq * 0.28)
                damage_slice[singularity_void, 0:3] = 0
                damage_slice[singularity_void, 3]   = 255

                self.update_damage_texture_region(min_x, min_y, max_x, max_y)
                self.has_damage = True

        animator = WindowAnimator.WindowAnimator.get(self.window())

        if animator is not None:
            animator.trigger_glass_shatter(detonation_x, detonation_y)

        Player.ui_player.play_sound(".vault/NOK/Glass1")
        Player.ui_player.play_sound("Alerts/Errors/MegaCritical", volume = 1.0)
        Haptics.ui_haptics.snap()

        self.recoil_offset_x = float(random.choice([-100.0, 100.0]))
        self.recoil_offset_y = 75.0
        self.gun_velocity_y += 18.0

    def process_gun_fall_physics(self) -> None:
        gravity = 1.03
        self.gun_velocity_y += gravity

        self.gun_position_x += self.gun_velocity_x
        self.gun_position_y += self.gun_velocity_y

        self.gun_rotation_x += self.angular_velocity_x
        self.gun_rotation_y += self.angular_velocity_y
        self.gun_rotation_z += self.angular_velocity_z

        floor_level_px = float(self.height()) - 85.0

        if self.gun_position_y >= floor_level_px:
            self.gun_position_y = floor_level_px

            if abs(self.gun_velocity_y) > 2.0:
                self.gun_velocity_y     = -self.gun_velocity_y * 0.40
                self.gun_velocity_x    *= 0.60

                self.angular_velocity_x = -self.angular_velocity_x * float(random.uniform(0.3, 0.6))
                self.angular_velocity_y = -self.angular_velocity_y * float(random.uniform(0.3, 0.6))
                self.angular_velocity_z = -self.angular_velocity_z * float(random.uniform(0.3, 0.6))

                if not self.drop_played:
                    Player.ui_player.play_sound(".vault/NOK/GunDrop")
                    self.drop_played = True

                Haptics.ui_haptics.step()

            else:
                self.gun_velocity_y     = 0.0
                self.gun_velocity_x     = 0.0
                self.angular_velocity_x = 0.0
                self.angular_velocity_y = 0.0
                self.angular_velocity_z = 0.0
                self.gun_is_falling     = False
                self.gun_is_resting     = True

    def process_equipped_physics(self) -> None:
        cursor_position   = self.mapFromGlobal(QCursor.pos())
        current_cursor_x  = float(cursor_position.x())
        current_cursor_y  = float(cursor_position.y())

        target_position_x = current_cursor_x + self.recoil_offset_x
        target_position_y = current_cursor_y + self.recoil_offset_y

        cursor_distance_x = target_position_x - self.gun_position_x
        cursor_distance_y = target_position_y - self.gun_position_y

        spring_linear_stiffness = 0.28
        linear_damping          = 0.76

        self.gun_velocity_x = (self.gun_velocity_x + cursor_distance_x * spring_linear_stiffness) * linear_damping
        self.gun_velocity_y = (self.gun_velocity_y + cursor_distance_y * spring_linear_stiffness) * linear_damping

        self.gun_position_x += self.gun_velocity_x
        self.gun_position_y += self.gun_velocity_y

        recoil_damping_factor = 0.82
        self.recoil_offset_x *= recoil_damping_factor
        self.recoil_offset_y *= recoil_damping_factor

        angular_damping = 0.86
        self.angular_velocity_x *= angular_damping
        self.angular_velocity_y *= angular_damping
        self.angular_velocity_z *= angular_damping

        self.gun_rotation_x += self.angular_velocity_x
        self.gun_rotation_y += self.angular_velocity_y
        self.gun_rotation_z += self.angular_velocity_z

    # Weapon Actions

    def fire_portal_gun(self) -> None:
        self.muzzle_flash_alpha = 1.0

        Haptics.ui_haptics.snap()

        rotation_matrix = QMatrix4x4()
        rotation_matrix.rotate(self.gun_rotation_z, 0.0, 0.0, 1.0)
        rotation_matrix.rotate(self.gun_rotation_x, 1.0, 0.0, 0.0)
        rotation_matrix.rotate(self.gun_rotation_y, 0.0, 1.0, 0.0)

        forward_direction_3d = rotation_matrix.map(QVector3D(1.0, 0.0, 0.0))
        forward_direction_3d.normalize()

        barrel_offset_px = 65.0
        muzzle_offset    = rotation_matrix.map(QVector3D(barrel_offset_px, 0.0, 0.0))
        muzzle_x         = self.gun_position_x + muzzle_offset.x()
        muzzle_y         = self.gun_position_y + muzzle_offset.y()

        forward_direction_2d_x = forward_direction_3d.x()
        forward_direction_2d_y = forward_direction_3d.y()
        forward_length_2d      = math.hypot(forward_direction_2d_x, forward_direction_2d_y)

        if forward_length_2d > 0.001:
            normalized_recoil_direction_x = forward_direction_2d_x / forward_length_2d
            normalized_recoil_direction_y = forward_direction_2d_y / forward_length_2d

        else:
            normalized_recoil_direction_x = 1.0
            normalized_recoil_direction_y = 0.0

        recoil_kick_distance = 45.0
        self.recoil_offset_x -= normalized_recoil_direction_x * recoil_kick_distance
        self.recoil_offset_y -= normalized_recoil_direction_y * recoil_kick_distance

        self.gun_position_x -= normalized_recoil_direction_x * 20.0
        self.gun_position_y -= normalized_recoil_direction_y * 20.0

        if forward_direction_3d.z() > 0.28:
            self.projectile_hits_glass = True
            impact_x = muzzle_x + forward_direction_3d.x() * 100.0
            impact_y = muzzle_y + forward_direction_3d.y() * 100.0

        elif forward_direction_3d.z() < -0.22:
            self.projectile_hits_glass = False
            depth_distance = 240.0
            impact_x       = muzzle_x + forward_direction_3d.x() * depth_distance
            impact_y       = muzzle_y + forward_direction_3d.y() * depth_distance
            impact_x       = max(70.0, min(float(self.width()) - 70.0, impact_x))
            impact_y       = max(70.0, min(float(self.height()) - 70.0, impact_y))

        else:
            self.projectile_hits_glass = False
            impact_x, impact_y = self.raycast_window_bounds(
                muzzle_x,
                muzzle_y,
                forward_direction_3d.x(),
                forward_direction_3d.y()
            )

        self.projectile_active   = True
        self.projectile_start    = QPointF(muzzle_x, muzzle_y)
        self.projectile_end      = QPointF(impact_x, impact_y)
        self.projectile_progress = 0.0

    def find_colliding_portal(
            self,
            target_x: float,
            target_y: float
        ) -> PortalInstance | None:

        for portal in self.portals:
            distance = math.hypot(target_x - portal.position.x(), target_y - portal.position.y())
            threshold_radius = 210.0 * max(0.2, portal.scale)

            if distance <= threshold_radius:
                return portal

        return None

    def trigger_portal_merger(
            self,
            primary_portal:   PortalInstance,
            impact_point_x:   float,
            impact_point_y:   float
        ) -> None:

        self.merger_in_progress          = True
        self.merger_progress             = 0.0
        self.merger_primary_portal       = primary_portal
        self.merger_start_position       = QVector3D(primary_portal.position)
        self.merger_impact_position      = QVector3D(impact_point_x, impact_point_y, 0.0)

        self.merger_center_x             = (primary_portal.position.x() + impact_point_x) * 0.5
        self.merger_center_y             = (primary_portal.position.y() + impact_point_y) * 0.5

        primary_portal.mode              = 1
        primary_portal.suction_power     = 1.4

        Player.ui_player.play_sound("Alerts/Errors/MegaCritical", volume = 0.7)
        Haptics.ui_haptics.snap()

    def on_projectile_impact(self) -> None:
        impact_x = self.projectile_end.x()
        impact_y = self.projectile_end.y()

        if self.projectile_hits_glass:
            animator = WindowAnimator.WindowAnimator.get(self.window())

            if animator is not None:
                animator.trigger_glass_shatter(impact_x, impact_y)

            return

        colliding_portal = self.find_colliding_portal(impact_x, impact_y)

        if colliding_portal is not None:
            self.trigger_portal_merger(colliding_portal, impact_x, impact_y)
            return

        self.open_portal_at(impact_x, impact_y)

    def open_portal_at(
            self,
            position_x: float,
            position_y: float
        ) -> None:

        width_px  = float(self.width())
        height_px = float(self.height())

        distance_left   = position_x
        distance_right  = width_px - position_x
        distance_top    = position_y
        distance_bottom = height_px - position_y

        minimum_distance = min(distance_left, distance_right, distance_top, distance_bottom)

        normal = QVector3D(0.0, 0.0, 1.0)

        if minimum_distance < 180.0:
            if minimum_distance == distance_left:
                normal = QVector3D(0.85, 0.0, 0.45)

            elif minimum_distance == distance_right:
                normal = QVector3D(-0.85, 0.0, 0.45)

            elif minimum_distance == distance_top:
                normal = QVector3D(0.0, 0.85, 0.45)

            else:
                normal = QVector3D(0.0, -0.85, 0.45)

        normal.normalize()

        if len(self.portals) >= 2:
            displaced_portal                  = self.portals.pop(0)
            displaced_portal.is_closing       = True
            displaced_portal.closing_progress = 0.0
            self.closing_portal               = displaced_portal

        new_portal = PortalInstance(
            position    = QVector3D(position_x, position_y, 0.0),
            normal      = normal,
            time_offset = float(random.uniform(0.0, 50.0))
        )

        self.portals.append(new_portal)

        if self.clean_scene_array is None:
            self.capture_underlying_scene()

        Player.ui_player.play_sound(".vault/NOK/Portal", tone_spread = 0.2)

    # Collision Raycasting

    def raycast_window_bounds(
            self,
            origin_x:    float,
            origin_y:    float,
            direction_x: float,
            direction_y: float
        ) -> tuple[float, float]:

        width_px  = float(self.width())
        height_px = float(self.height())

        length = math.hypot(direction_x, direction_y)

        if length <= 0.001:
            return origin_x + 100.0, origin_y

        normalized_direction_x = direction_x / length
        normalized_direction_y = direction_y / length

        intersections: list[float] = []

        if normalized_direction_x > 0.001:
            intersections.append((width_px - origin_x) / normalized_direction_x)

        elif normalized_direction_x < -0.001:
            intersections.append(-origin_x / normalized_direction_x)

        if normalized_direction_y > 0.001:
            intersections.append((height_px - origin_y) / normalized_direction_y)

        elif normalized_direction_y < -0.001:
            intersections.append(-origin_y / normalized_direction_y)

        positive_intersections = [intersection for intersection in intersections if intersection > 0.0]

        if not positive_intersections:
            return origin_x + normalized_direction_x * 200.0, origin_y + normalized_direction_y * 200.0

        minimum_intersection_distance = min(positive_intersections)

        return origin_x + normalized_direction_x * minimum_intersection_distance, origin_y + normalized_direction_y * minimum_intersection_distance

    # OpenGL Painting

    def paintGL(self) -> None:
        pixel_ratio = self.devicePixelRatio()
        viewport_w  = max(1, int(self.width() * pixel_ratio))
        viewport_h  = max(1, int(self.height() * pixel_ratio))

        GL.glViewport(0, 0, viewport_w, viewport_h)
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        width_px  = float(self.width())
        height_px = float(self.height())

        if width_px <= 0.0 or height_px <= 0.0:
            return

        projection = QMatrix4x4()
        projection.ortho(0.0, width_px, height_px, 0.0, -1000.0, 1000.0)

        if self.has_damage and self.damage_texture_id is not None:
            GL.glDisable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
            self.render_damage_layer(projection)

        if self.portals or self.closing_portal is not None:
            GL.glDisable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)

            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self.scene_texture_id)

            if self.closing_portal is not None and self.closing_portal.scale > 0.0001:
                self.render_portal(projection, self.closing_portal, self.closing_portal)

            for index, portal in enumerate(self.portals):
                if portal.scale > 0.0001:
                    target_portal = self.portals[1 - index] if len(self.portals) > 1 else portal
                    self.render_portal(projection, portal, target_portal)

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        self.render_portal_gun(projection)

        if self.projectile_active or self.muzzle_flash_alpha > 0.0:
            GL.glDisable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE)
            self.render_projectile_beam(projection)

    def render_damage_layer(self, projection_matrix: QMatrix4x4) -> None:
        if self.damage_shader is None or self.quad_vertex_array_object is None:
            return

        GL.glUseProgram(self.damage_shader)

        width_px  = float(self.width())
        height_px = float(self.height())

        model_matrix = QMatrix4x4()
        model_matrix.translate(width_px * 0.5, height_px * 0.5, 0.0)
        model_matrix.scale(width_px * 0.5, height_px * 0.5, 1.0)

        model_view_projection_matrix = projection_matrix * model_matrix

        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.damage_shader, "u_mvp"), 1, GL.GL_FALSE, model_view_projection_matrix.data())

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.damage_texture_id)
        GL.glUniform1i(GL.glGetUniformLocation(self.damage_shader, "u_damage_tex"), 0)

        GL.glBindVertexArray(self.quad_vertex_array_object)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)

    def render_portal(
            self,
            projection_matrix: QMatrix4x4,
            portal:            PortalInstance,
            target_portal:     PortalInstance
        ) -> None:

        GL.glUseProgram(self.portal_shader)

        model_matrix = QMatrix4x4()
        model_matrix.translate(portal.position)

        base_normal   = QVector3D(0.0, 0.0, 1.0)
        rotation_axis = QVector3D.crossProduct(base_normal, portal.normal)
        dot_product   = QVector3D.dotProduct(base_normal, portal.normal)

        if rotation_axis.length() > 0.001:
            angle_degrees = math.degrees(math.acos(max(-1.0, min(1.0, dot_product))))
            model_matrix.rotate(angle_degrees, rotation_axis)

        portal_radius_px = 250.0 * portal.scale
        model_matrix.scale(portal_radius_px, portal_radius_px, 1.0)

        model_view_projection_matrix = projection_matrix * model_matrix

        width_px  = float(self.width())
        height_px = float(self.height())

        portal_norm_x = portal.position.x() / max(1.0, width_px)
        portal_norm_y = portal.position.y() / max(1.0, height_px)

        target_norm_x = target_portal.position.x() / max(1.0, width_px)
        target_norm_y = target_portal.position.y() / max(1.0, height_px)

        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.portal_shader, "u_mvp"), 1, GL.GL_FALSE, model_view_projection_matrix.data())
        GL.glUniform1f(GL.glGetUniformLocation(self.portal_shader, "u_portal_phase"), portal.spin_phase)
        GL.glUniform1f(GL.glGetUniformLocation(self.portal_shader, "u_alpha"), portal.alpha * portal.scale)
        GL.glUniform1i(GL.glGetUniformLocation(self.portal_shader, "u_portal_mode"), portal.mode)

        GL.glUniform2f(GL.glGetUniformLocation(self.portal_shader, "u_screen_size"), width_px, height_px)
        GL.glUniform2f(GL.glGetUniformLocation(self.portal_shader, "u_portal_screen_pos"), portal_norm_x, portal_norm_y)
        GL.glUniform2f(GL.glGetUniformLocation(self.portal_shader, "u_target_screen_pos"), target_norm_x, target_norm_y)
        GL.glUniform1f(GL.glGetUniformLocation(self.portal_shader, "u_portal_radius_px"), portal_radius_px)

        GL.glUniform1f(GL.glGetUniformLocation(self.portal_shader, "u_suction_power"), portal.suction_power)
        GL.glUniform1f(GL.glGetUniformLocation(self.portal_shader, "u_spin_speed"), portal.spin_speed)
        GL.glUniform1f(GL.glGetUniformLocation(self.portal_shader, "u_close_progress"), portal.closing_progress)
        GL.glUniform1f(GL.glGetUniformLocation(self.portal_shader, "u_instability"), portal.instability)

        GL.glUniform1i(GL.glGetUniformLocation(self.portal_shader, "u_scene_tex"), 0)

        GL.glBindVertexArray(self.quad_vertex_array_object)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)

    def render_portal_gun(self, projection_matrix: QMatrix4x4) -> None:
        if self.gun_mesh_vertex_array_object is None or self.gun_vertex_count == 0:
            return

        GL.glUseProgram(self.gun_shader)

        model_matrix = QMatrix4x4()
        model_matrix.translate(self.gun_position_x, self.gun_position_y, 0.0)

        model_matrix.rotate(self.gun_rotation_z, 0.0, 0.0, 1.0)
        model_matrix.rotate(self.gun_rotation_x, 1.0, 0.0, 0.0)
        model_matrix.rotate(self.gun_rotation_y, 0.0, 1.0, 0.0)

        gun_scale = 130.0
        model_matrix.scale(gun_scale, gun_scale, gun_scale)

        model_view_projection_matrix = projection_matrix * model_matrix

        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.gun_shader, "u_mvp"), 1, GL.GL_FALSE, model_view_projection_matrix.data())
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.gun_shader, "u_model"), 1, GL.GL_FALSE, model_matrix.data())

        GL.glUniform3f(GL.glGetUniformLocation(self.gun_shader, "u_light_pos"), self.gun_position_x - 60.0, self.gun_position_y - 200.0, 300.0)
        GL.glUniform3f(GL.glGetUniformLocation(self.gun_shader, "u_view_pos"), self.gun_position_x, self.gun_position_y, 500.0)
        GL.glUniform1f(GL.glGetUniformLocation(self.gun_shader, "u_bulb_glow"), self.bulb_glow_pulse)
        GL.glUniform1f(GL.glGetUniformLocation(self.gun_shader, "u_alpha"), 1.0)

        GL.glBindVertexArray(self.gun_mesh_vertex_array_object)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, self.gun_vertex_count)
        GL.glBindVertexArray(0)

    def render_projectile_beam(self, projection_matrix: QMatrix4x4) -> None:
        if not self.projectile_active:
            return

        GL.glUseProgram(self.beam_shader)

        start_x = self.projectile_start.x()
        start_y = self.projectile_start.y()
        end_x   = self.projectile_end.x()
        end_y   = self.projectile_end.y()

        current_head_x = start_x + (end_x - start_x) * min(1.0, self.projectile_progress * 1.5)
        current_head_y = start_y + (end_y - start_y) * min(1.0, self.projectile_progress * 1.5)

        current_tail_x = start_x + (end_x - start_x) * max(0.0, self.projectile_progress * 1.5 - 0.45)
        current_tail_y = start_y + (end_y - start_y) * max(0.0, self.projectile_progress * 1.5 - 0.45)

        delta_x = current_head_x - current_tail_x
        delta_y = current_head_y - current_tail_y
        length  = math.hypot(delta_x, delta_y)

        if length <= 0.001:
            return

        beam_thickness = 4.0

        normal_x = (-delta_y / length) * beam_thickness
        normal_y = (delta_x / length) * beam_thickness

        beam_vertices = numpy.array([
            current_tail_x + normal_x, current_tail_y + normal_y, 0.0,
            current_head_x + normal_x, current_head_y + normal_y, 0.0,
            current_head_x - normal_x, current_head_y - normal_y, 0.0,

            current_tail_x + normal_x, current_tail_y + normal_y, 0.0,
            current_head_x - normal_x, current_head_y - normal_y, 0.0,
            current_tail_x - normal_x, current_tail_y - normal_y, 0.0
        ], dtype = numpy.float32)

        GL.glBindVertexArray(self.beam_vertex_array_object)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.beam_vertex_buffer_object)
        GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, beam_vertices.nbytes, beam_vertices)

        model_view_projection_uniform_location = GL.glGetUniformLocation(self.beam_shader, "u_mvp")
        color_uniform_location                 = GL.glGetUniformLocation(self.beam_shader, "u_beam_color")

        GL.glUniformMatrix4fv(model_view_projection_uniform_location, 1, GL.GL_FALSE, projection_matrix.data())
        GL.glUniform4f(color_uniform_location, 0.35, 1.0, 0.22, 0.95)

        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)

    # Input Handling

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.gun_is_equipped:
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()

        if delta == 0:
            delta = event.angleDelta().x()

        if delta == 0:
            return

        steps     = delta / 120.0
        modifiers = event.modifiers()

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            self.angular_velocity_x += steps * 6.5

        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            self.angular_velocity_y += steps * 7.0

        else:
            self.angular_velocity_z += steps * 9.0

        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            click_point     = event.position()
            distance_to_gun = math.hypot(click_point.x() - self.gun_position_x, click_point.y() - self.gun_position_y)

            if distance_to_gun < 180.0 or self.gun_is_resting:
                self.gun_is_equipped = True
                self.gun_is_resting  = False
                self.gun_is_falling  = False

                Player.ui_player.play_sound("Alerts/Clicks/Toggle1", speed = 1.3)
                Haptics.ui_haptics.snap()
                event.accept()
                return

        if event.button() == Qt.MouseButton.LeftButton and self.gun_is_equipped:
            self.fire_portal_gun()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton and self.gun_is_equipped:
            self.gun_is_equipped    = False
            self.gun_is_falling     = True
            self.gun_velocity_x     = 0.0
            self.gun_velocity_y     = 1.0
            self.angular_velocity_z = self.angular_velocity_z * 0.5
            event.accept()
            return

        super().mouseReleaseEvent(event)

    # Window Events

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        if self.is_capturing_scene:
            return

        pixel_ratio = self.devicePixelRatio()
        GL.glViewport(0, 0, int(self.width() * pixel_ratio), int(self.height() * pixel_ratio))
        self.capture_underlying_scene()