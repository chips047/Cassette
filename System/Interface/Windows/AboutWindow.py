from __future__ import annotations

import os
import re
import sys
import json
import math
import time
import numpy
import shutil
import struct
import random
import zipfile
import tempfile
import platform
import subprocess
import webbrowser

from loguru import logger
from OpenGL import GL
from OpenGL.GL import shaders

from PyQt6.QtCore import (
    Qt,
    QUrl,
    QRect,
    QTimer,
    pyqtSignal
)

from PyQt6.QtGui import (
    QColor,
    QImage,
    QVector3D,
    QMatrix4x4,
    QMouseEvent,
    QPaintEvent,
    QTextDocument
)

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QApplication,
    QStackedLayout
)

from PyQt6.QtNetwork import (
    QNetworkReply,
    QNetworkRequest,
    QNetworkAccessManager
)

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Services import (
    Player,
    Haptics
)

from System.Interface import Widgets
from System.Interface.Animation import LoomEngine

from System.Interface.Windows import (
    ErrorWindow,
    FloatingWindowGPU
)

from System.Interface.Windows.FeedbackWindow import (
    FeedbackWindow,
    SETTING_FEEDBACK_RATING_KEY
)

# Animation Calibration Constants

CHECK_SWAY_FREQUENCY                 = 5.5
CHECK_SWAY_AMPLITUDE_YAW             = 8.0
CHECK_SWAY_AMPLITUDE_PITCH           = 2.5
CHECK_SWAY_AMPLITUDE_ROLL            = 1.5

FORWARD_DELAY_BUTTONS_OUT_MS         = 100
FORWARD_DELAY_TEXT_OUT_MS            = 265
FORWARD_DELAY_MODEL_PULSE_MS         = 400
FORWARD_DELAY_ACCELERATION_MS        = 700
FORWARD_DELAY_HIGH_SPEED_MS          = 1100
FORWARD_DELAY_IRIDESCENCE_MS         = 1100
FORWARD_DELAY_DECELERATION_MS        = 1690
FORWARD_DELAY_UPDATE_IN_MS           = 1670
FORWARD_DELAY_FINISH_SPIN_MS         = 2400

FORWARD_DURATION_BUTTONS_OUT_MS      = 120
FORWARD_DURATION_TEXT_OUT_MS         = 120
FORWARD_DURATION_TITLE_OUT_MS        = 120
FORWARD_DURATION_MODEL_PULSE_MS      = 200
FORWARD_DURATION_ACCELERATION_MS     = 400
FORWARD_DURATION_HIGH_SPEED_MS       = 590
FORWARD_DURATION_IRIDESCENCE_MS      = 450
FORWARD_DURATION_DECELERATION_MS     = 500
FORWARD_DURATION_SMEAR_OUT_MS        = 400
FORWARD_DURATION_TITLE_IN_MS         = 300
FORWARD_DURATION_INFO_IN_MS          = 350
FORWARD_DURATION_BUTTONS_IN_MS       = 350

FORWARD_TARGET_SCALE                 = 1.05
FORWARD_SPIN_STAGE_ONE_DEGREES       = 1080.0
FORWARD_SPIN_STAGE_TWO_DEGREES       = 2520.0
FORWARD_SPIN_FINAL_DEGREES           = 3600.0

REVERSE_DELAY_UPDATE_OUT_MS          = 100
REVERSE_DELAY_MODEL_SCALE_MS         = 300
REVERSE_DELAY_ACCELERATION_MS        = 500
REVERSE_DELAY_HIGH_SPEED_MS          = 900
REVERSE_DELAY_IRIDESCENCE_OUT_MS     = 700
REVERSE_DELAY_DECELERATION_MS        = 1200
REVERSE_DELAY_ABOUT_IN_MS            = 1600
REVERSE_DELAY_FINISH_SPIN_MS         = 1900

REVERSE_DELAY_BUTTONS_OUT_MS         = 100
REVERSE_DELAY_TEXT_OUT_MS            = 265

REVERSE_DURATION_BUTTONS_OUT_MS      = 120
REVERSE_DURATION_TEXT_OUT_MS         = 120
REVERSE_DURATION_TITLE_OUT_MS        = 120

REVERSE_DURATION_UPDATE_OUT_MS       = 120
REVERSE_DURATION_TITLE_OUT_MS        = 120
REVERSE_DURATION_MODEL_SCALE_MS      = 300
REVERSE_DURATION_ACCELERATION_MS     = 400
REVERSE_DURATION_HIGH_SPEED_MS       = 300
REVERSE_DURATION_IRIDESCENCE_MS      = 400
REVERSE_DURATION_DECELERATION_MS     = 780
REVERSE_DURATION_SMEAR_OUT_MS        = 480
REVERSE_DURATION_TITLE_IN_MS         = 300
REVERSE_DURATION_ABOUT_IN_MS         = 350
REVERSE_DURATION_BUTTONS_IN_MS       = 350

REVERSE_SPIN_STAGE_ONE_DEGREES       = 1080.0
REVERSE_SPIN_STAGE_TWO_DEGREES       = 1800.0
REVERSE_SPIN_FINAL_DEGREES           = 2880.0

FORWARD_DURATION_MODEL_SCALE_BACK_MS = 350

FORWARD_DELAY_ENABLE_BUTTONS_MS      = 2130
REVERSE_DELAY_ENABLE_BUTTONS_MS      = 2130

# Shader Sources

CASSETTE_VERTEX_SHADER_SOURCE = """#version 330 core
layout (location = 0) in vec3 attribute_position;
layout (location = 1) in vec3 attribute_normal;
layout (location = 2) in vec2 attribute_texture_coordinate;
layout (location = 3) in vec4 attribute_tangent;

uniform mat4 projection_matrix;
uniform mat4 view_matrix;
uniform mat4 model_matrix;
uniform float smear_intensity;
uniform float smear_phase;

out vec3 fragment_position;
out vec2 fragment_texture_coordinate;
out mat3 fragment_tangent_basis;

void main() {
    mat3 normal_matrix = mat3(transpose(inverse(model_matrix)));

    vec3 displaced_position = attribute_position;

    if (smear_intensity > 0.001) {
        float primary_wave = sin(displaced_position.y * 14.0 + smear_phase) * smear_intensity;
        float secondary_wave = cos(displaced_position.x * 10.0 - smear_phase * 1.6) * smear_intensity;

        displaced_position.x += primary_wave * 0.18;
        displaced_position.z += secondary_wave * 0.18;
        displaced_position.y += sin(displaced_position.z * 12.0 + smear_phase) * smear_intensity * 0.09;
    }

    vec4 world_position = model_matrix * vec4(displaced_position, 1.0);

    fragment_position = vec3(world_position);
    fragment_texture_coordinate = attribute_texture_coordinate;

    vec3 normal_vector = normalize(normal_matrix * attribute_normal);
    vec3 tangent_vector = normalize(normal_matrix * attribute_tangent.xyz);
    tangent_vector = normalize(tangent_vector - dot(tangent_vector, normal_vector) * normal_vector);
    vec3 bitangent_vector = cross(normal_vector, tangent_vector) * attribute_tangent.w;

    fragment_tangent_basis = mat3(tangent_vector, bitangent_vector, normal_vector);

    gl_Position = projection_matrix * view_matrix * world_position;
}
"""

CASSETTE_FRAGMENT_SHADER_SOURCE = """#version 330 core
in vec3 fragment_position;
in vec2 fragment_texture_coordinate;
in mat3 fragment_tangent_basis;

uniform vec3 camera_position;
uniform vec3 accent_color;
uniform vec3 button_light_position;
uniform float global_alpha;
uniform float iridescence_intensity;

uniform sampler2D base_color_sampler;
uniform sampler2D normal_sampler;
uniform sampler2D metallic_roughness_sampler;
uniform sampler2D emissive_sampler;

uniform int has_base_color_texture;
uniform int has_normal_texture;
uniform int has_metallic_roughness_texture;
uniform int has_emissive_texture;

out vec4 output_color;

void main() {
    vec4 base_sample = vec4(0.25, 0.25, 0.27, 1.0);

    if (has_base_color_texture == 1) {
        base_sample = texture(base_color_sampler, fragment_texture_coordinate);
    }

    if (base_sample.a < 0.1 || global_alpha < 0.001) {
        discard;
    }

    vec3 normal_vector = normalize(fragment_tangent_basis[2]);

    if (has_normal_texture == 1) {
        vec3 normal_map_sample = texture(normal_sampler, fragment_texture_coordinate).rgb * 2.0 - 1.0;
        normal_vector = normalize(fragment_tangent_basis * normal_map_sample);
    }

    float roughness_factor = 0.55;
    float metallic_factor = 0.15;

    if (has_metallic_roughness_texture == 1) {
        vec4 metallic_roughness_sample = texture(metallic_roughness_sampler, fragment_texture_coordinate);
        roughness_factor = clamp(metallic_roughness_sample.g, 0.04, 1.0);
        metallic_factor = clamp(metallic_roughness_sample.b, 0.0, 1.0);
    }

    vec3 emissive_color = vec3(0.0);

    if (has_emissive_texture == 1) {
        emissive_color = texture(emissive_sampler, fragment_texture_coordinate).rgb;
    }

    vec3 view_direction = normalize(camera_position - fragment_position);

    vec3 key_light_direction = normalize(vec3(0.7, 1.1, 1.4));
    vec3 fill_light_direction = normalize(vec3(-1.0, -0.4, 0.9));
    vec3 top_light_direction = normalize(vec3(0.0, 1.5, 0.2));

    float key_diffuse = max(dot(normal_vector, key_light_direction), 0.0);
    float fill_diffuse = max(dot(normal_vector, fill_light_direction), 0.0);
    float top_diffuse = max(dot(normal_vector, top_light_direction), 0.0);

    vec3 key_half_vector = normalize(key_light_direction + view_direction);
    float specular_power = mix(96.0, 4.0, roughness_factor);
    float specular_strength = pow(max(dot(normal_vector, key_half_vector), 0.0), specular_power);
    vec3 specular_tint = mix(vec3(0.04), base_sample.rgb, metallic_factor);
    vec3 specular_component = specular_tint * specular_strength * (1.2 - roughness_factor * 0.5);

    vec3 diffuse_albedo = base_sample.rgb * (1.0 - metallic_factor);
    vec3 button_light_vector = button_light_position - fragment_position;
    float button_light_distance = length(button_light_vector);
    vec3 button_light_direction = button_light_vector / max(button_light_distance, 0.0001);
    float button_light_diffuse = max(dot(normal_vector, button_light_direction), 0.0);
    float button_light_falloff = 1.0 - smoothstep(0.08, 1.15, button_light_distance);
    vec3 button_light_component = diffuse_albedo * accent_color
        * (0.12 + button_light_diffuse * 1.25)
        * pow(button_light_falloff, 1.6);

    vec3 ambient_component = diffuse_albedo * 0.52;
    vec3 diffuse_component = diffuse_albedo * (key_diffuse * 0.85 + fill_diffuse * 0.35 + top_diffuse * 0.25);

    vec3 resolved_rgb = (ambient_component + diffuse_component + specular_component + button_light_component + emissive_color * 1.6) * 0.78;

    if (iridescence_intensity > 0.001) {
        float fresnel_factor = 1.0 - clamp(dot(normal_vector, view_direction), 0.0, 1.0);
        vec3 rainbow_palette = 0.5 + 0.5 * cos(6.28318 * (vec3(0.0, 0.33, 0.67) + fresnel_factor * 2.2 + fragment_position.y * 0.4));
        vec3 rainbow_highlight = rainbow_palette * pow(fresnel_factor, 1.3) * 1.8;
        resolved_rgb = mix(resolved_rgb, resolved_rgb + rainbow_highlight, iridescence_intensity);
    }

    output_color = vec4(resolved_rgb, base_sample.a * global_alpha);
}
"""

# Primitive Mesh Batch

class PrimitiveMeshBatch:
    def __init__(
            self,
            vertex_buffer_data:            numpy.ndarray,
            texture_base_color_id:         int = 0,
            texture_normal_id:             int = 0,
            texture_metallic_roughness_id: int = 0,
            texture_emissive_id:           int = 0
        ) -> None:

        self.vertex_buffer_data            = vertex_buffer_data
        self.texture_base_color_id         = texture_base_color_id
        self.texture_normal_id             = texture_normal_id
        self.texture_metallic_roughness_id = texture_metallic_roughness_id
        self.texture_emissive_id           = texture_emissive_id

        self.vertex_count                  = len(vertex_buffer_data) // 12
        self.vertex_array_object           = None
        self.vertex_buffer_object          = None

    def allocate_gl(self) -> None:
        self.vertex_array_object  = GL.glGenVertexArrays(1)
        self.vertex_buffer_object = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.vertex_array_object)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vertex_buffer_object)
        GL.glBufferData(
            GL.GL_ARRAY_BUFFER,
            self.vertex_buffer_data.nbytes,
            self.vertex_buffer_data,
            GL.GL_STATIC_DRAW
        )

        stride_bytes = 12 * 4

        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(
            0,
            3,
            GL.GL_FLOAT,
            GL.GL_FALSE,
            stride_bytes,
            GL.ctypes.c_void_p(0)
        )

        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(
            1,
            3,
            GL.GL_FLOAT,
            GL.GL_FALSE,
            stride_bytes,
            GL.ctypes.c_void_p(12)
        )

        GL.glEnableVertexAttribArray(2)
        GL.glVertexAttribPointer(
            2,
            2,
            GL.GL_FLOAT,
            GL.GL_FALSE,
            stride_bytes,
            GL.ctypes.c_void_p(24)
        )

        GL.glEnableVertexAttribArray(3)
        GL.glVertexAttribPointer(
            3,
            4,
            GL.GL_FLOAT,
            GL.GL_FALSE,
            stride_bytes,
            GL.ctypes.c_void_p(32)
        )

        GL.glBindVertexArray(0)

    def draw(self) -> None:
        if self.vertex_array_object is None or self.vertex_count == 0:
            return

        GL.glBindVertexArray(self.vertex_array_object)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, self.vertex_count)
        GL.glBindVertexArray(0)

    def cleanup(self) -> None:
        if self.vertex_buffer_object is not None:
            GL.glDeleteBuffers(1, [self.vertex_buffer_object])
            self.vertex_buffer_object = None

        if self.vertex_array_object is not None:
            GL.glDeleteVertexArrays(1, [self.vertex_array_object])
            self.vertex_array_object = None

# Model Canvas Widget

class CassetteCanvasWidget(QWidget):
    model_dragged    = pyqtSignal()
    model_drag_ended = pyqtSignal()

    def __init__(self, window: QWidget | None = None) -> None:
        super().__init__(window)

        self.window_reference    = window
        self.manual_yaw          = 0.0
        self.manual_pitch        = 0.0
        self.target_manual_yaw   = 0.0
        self.target_manual_pitch = 0.0
        self.is_mouse_pressed    = False
        self.drag_start_position = None
        self.haptic_accumulator  = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedSize(500, 330)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)

            return

        self.is_mouse_pressed    = True
        self.drag_start_position = event.pos()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (self.is_mouse_pressed and self.drag_start_position is not None):
            super().mouseMoveEvent(event)

            return

        delta_x = float(event.pos().x() - self.drag_start_position.x())
        delta_y = float(event.pos().y() - self.drag_start_position.y())

        self.drag_start_position = event.pos()

        sensitivity               = 0.14
        self.target_manual_yaw   += delta_x * sensitivity
        self.target_manual_pitch += delta_y * sensitivity
        self.target_manual_pitch  = max(-40.0, min(40.0, self.target_manual_pitch))

        drag_distance            = math.hypot(delta_x, delta_y)
        self.haptic_accumulator += drag_distance
        haptic_threshold_px      = 22.0

        if self.haptic_accumulator >= haptic_threshold_px:
            self.haptic_accumulator %= haptic_threshold_px
            Haptics.ui_haptics.step()

        if delta_x != 0.0 or delta_y != 0.0:
            self.model_dragged.emit()

        if self.window_reference is not None:
            self.window_reference.update()

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)

            return

        self.is_mouse_pressed = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.model_drag_ended.emit()
        event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        pass

# About Window

class AboutWindow(FloatingWindowGPU):
    download_progress_updated = pyqtSignal(float, float)

    def __init__(
            self,
            more_information:          bool                      = False,
            cached_update_information: dict[str, object] | None  = None,
            parent:                    QWidget | None            = None
        ) -> None:

        with open(Utils.get_resource_path("version"), "r", encoding = "utf-8") as version_file:
            version_text = version_file.read().strip()

        self.local_version             = version_text
        self.cached_update_information = cached_update_information

        super().__init__(
            f"Cassette {version_text}",
            parent                     = parent,
            enable_audioplayer_effects = False
        )

        self.content_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)

        self.update_checker                  = None
        self.model_batches                   = []
        self.model_texture_ids               = []
        self.pending_image_bytes             = []
        self.texture_source_indices          = []
        self.cassette_shader_program         = None
        self.model_yaw_offset                = 0.0
        self.is_showing_credits              = False
        self.is_showing_update_view          = False
        self.model_drag_duration_ms          = 0.0
        self.model_drag_started_at           = None
        self.model_rotation_easter_egg_shown = bool(Constants.current_settings.get("_about_model_rotated_seen", False))

        self.is_checking_updates             = False
        self.checking_started_at             = 0.0

        self.pending_remote_tag              = ""
        self.pending_release_information     = None
        self.pending_changelog_text          = ""
        self.pending_release_url             = Constants.GITHUB_LINK

        self.download_target_url             = ""
        self.download_file_path              = ""
        self.temporary_file                  = None
        self.download_reply                  = None
        self.total_bytes                     = 0
        self.received_bytes                  = 0
        self.is_downloading                  = False
        self.is_ready_to_install             = False

        self.network_manager                 = QNetworkAccessManager(self)

        self.model_drag_timer = QTimer(self)
        self.model_drag_timer.setInterval(250)
        self.model_drag_timer.timeout.connect(self.check_model_rotation_easter_egg)

        self.model_location_projection            = -1
        self.model_location_view                  = -1
        self.model_location_model                 = -1
        self.model_location_camera_position       = -1
        self.model_location_accent_color          = -1
        self.model_location_button_light          = -1
        self.model_location_global_alpha          = -1
        self.model_location_smear_intensity       = -1
        self.model_location_smear_phase           = -1
        self.model_location_iridescence_intensity = -1

        self.location_sampler_base_color          = -1
        self.location_sampler_normal              = -1
        self.location_sampler_metallic_roughness  = -1
        self.location_sampler_emissive            = -1

        self.location_has_base_color              = -1
        self.location_has_normal                  = -1
        self.location_has_metallic_roughness      = -1
        self.location_has_emissive                = -1

        if more_information:
            self.about_text = (
                f"System {sys.platform} {platform.machine()}\n"
                f"Python: {sys.version}"
            )

        else:
            with open(Utils.get_resource_path("System/Assets/About.txt"), "r", encoding = "utf-8") as about_file:
                self.about_text = about_file.read()

        with open(Utils.get_resource_path("System/Assets/Credits.txt"), "r", encoding = "utf-8") as credits_file:
            self.credits_text = credits_file.read()

        self.setup_user_interface()
        self.setup_window_animations()

        cassette_path = Utils.get_resource_path("System/Assets/3D/Cassette.glb")
        self.load_model_data(cassette_path)

    # Setup User Interface

    def setup_user_interface(self) -> None:
        self.about_label = Widgets.DescriptionLabel(self.about_text, 500)
        self.about_label.setProperty("paint_opacity", 1.0)
        self.about_label.setAlignment(Qt.AlignmentFlag.AlignTop | (self.about_label.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask))

        self.credits_label = Widgets.DescriptionLabel(self.credits_text, 500)
        self.credits_label.setProperty("paint_opacity", 0.0)
        self.credits_label.setAlignment(Qt.AlignmentFlag.AlignTop | (self.credits_label.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask))

        label_font_metrics = self.about_label.fontMetrics()
        about_bounds       = label_font_metrics.boundingRect(0, 0, 500, 10000, int(Qt.TextFlag.TextWordWrap), self.about_text)
        credits_bounds     = label_font_metrics.boundingRect(0, 0, 500, 10000, int(Qt.TextFlag.TextWordWrap), self.credits_text)
        maximum_height     = max(about_bounds.height(), credits_bounds.height(), self.about_label.sizeHint().height(), self.credits_label.sizeHint().height())

        self.text_container_height = maximum_height

        self.text_view_widget = QWidget()
        self.text_view_widget.setFixedWidth(500)
        self.text_view_widget.setFixedHeight(maximum_height)

        self.text_view_layout = QStackedLayout(self.text_view_widget)
        self.text_view_layout.setContentsMargins(0, 0, 0, 0)
        self.text_view_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.text_view_layout.addWidget(self.about_label)
        self.text_view_layout.addWidget(self.credits_label)
        self.text_view_layout.setAlignment(self.about_label, Qt.AlignmentFlag.AlignTop)
        self.text_view_layout.setAlignment(self.credits_label, Qt.AlignmentFlag.AlignTop)

        self.update_content_widget = QWidget()
        self.update_content_widget.setFixedWidth(500)
        self.update_content_widget.setFixedHeight(maximum_height)
        self.update_content_widget.setVisible(False)

        self.update_content_layout = QVBoxLayout(self.update_content_widget)
        self.update_content_layout.setContentsMargins(0, 0, 0, 0)
        self.update_content_layout.setSpacing(0)

        self.update_label = Widgets.DescriptionLabel("", 500)
        self.update_label.setAlignment(Qt.AlignmentFlag.AlignTop | (self.update_label.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask))

        self.update_scroll_area = Widgets.ElasticScrollArea(self)
        self.update_scroll_area.setFixedWidth(500)
        self.update_scroll_area.setFixedHeight(maximum_height)
        self.update_scroll_area.add_widget(self.update_label)

        self.update_content_layout.addWidget(self.update_scroll_area)

        self.text_stack_wrapper = QWidget(self)
        self.text_stack_wrapper.setFixedWidth(500)
        self.text_stack_wrapper.setFixedHeight(maximum_height)

        self.text_view_widget.setParent(self.text_stack_wrapper)
        self.update_content_widget.setParent(self.text_stack_wrapper)

        self.text_view_widget.setGeometry(0, 0, 500, maximum_height)
        self.update_content_widget.setGeometry(0, 0, 500, maximum_height)

        self.cassette_canvas = CassetteCanvasWidget(self)
        self.cassette_canvas.model_dragged.connect(self.on_model_dragged)
        self.cassette_canvas.model_drag_ended.connect(self.on_model_drag_ended)

        self.status_label = Widgets.DescriptionLabel("", 500)
        self.status_label.setVisible(False)

        self.pulse_status_widget = Widgets.PulseStatusWidget(self)
        self.pulse_status_widget.setFixedHeight(60)
        self.pulse_status_widget.setVisible(False)

        self.about_buttons_widget = QWidget()
        self.about_buttons_widget.setFixedWidth(500)

        about_buttons_layout = QVBoxLayout(self.about_buttons_widget)
        about_buttons_layout.setContentsMargins(0, 0, 0, 0)
        about_buttons_layout.setSpacing(12)

        self.button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "GitHub",        self.on_github),
                (Widgets.ButtonWithOutline, "Feedback",      self.on_feedback),
                (Widgets.ButtonWithOutline, "Check updates", self.on_check_updates),
                (Widgets.ButtonWithOutline, "Credits",       self.on_credits)
            ],
            button_width = 100
        )

        if self.cached_update_information is not None:
            update_button = self.button_row.get_button_by_number(2)

            if update_button is not None:
                update_button.setText("Update available")

        self.five_stars_button = Widgets.NothingButton("Five Stars?")
        saved_rating           = Constants.current_settings.get(SETTING_FEEDBACK_RATING_KEY)
        rating_texts           = Constants.CLOSE_BUTTON_RATING_TEXTS.get(saved_rating, []) if isinstance(saved_rating, int) else []

        if rating_texts:
            self.five_stars_button.setText(random.choice(rating_texts))

        self.five_stars_button.clicked.connect(self.on_ok)

        about_buttons_layout.addLayout(self.button_row)
        about_buttons_layout.addWidget(self.five_stars_button)

        self.update_buttons_widget = QWidget()
        self.update_buttons_widget.setFixedWidth(500)
        self.update_buttons_widget.setVisible(False)

        update_buttons_layout = QVBoxLayout(self.update_buttons_widget)
        update_buttons_layout.setContentsMargins(0, 0, 0, 0)
        update_buttons_layout.setSpacing(12)

        update_top_buttons_layout = QHBoxLayout()
        update_top_buttons_layout.setContentsMargins(0, 0, 0, 0)
        update_top_buttons_layout.setSpacing(12)

        self.update_github_button = Widgets.ButtonWithOutline("View on GitHub")
        self.update_cancel_button = Widgets.ButtonWithOutline("Later")
        self.update_action_button = Widgets.NothingButton("Update now")

        self.update_github_button.clicked.connect(self.open_github_release)
        self.update_cancel_button.clicked.connect(self.handle_cancel_clicked)
        self.update_action_button.clicked.connect(self.handle_action_clicked)

        update_top_buttons_layout.addWidget(self.update_github_button)
        update_top_buttons_layout.addWidget(self.update_cancel_button)

        update_buttons_layout.addLayout(update_top_buttons_layout)
        update_buttons_layout.addWidget(self.update_action_button)

        buttons_container_height = self.about_buttons_widget.sizeHint().height()

        self.buttons_stack_wrapper = QWidget(self)
        self.buttons_stack_wrapper.setFixedWidth(500)
        self.buttons_stack_wrapper.setFixedHeight(buttons_container_height)

        self.about_buttons_widget.setParent(self.buttons_stack_wrapper)
        self.update_buttons_widget.setParent(self.buttons_stack_wrapper)

        self.about_buttons_widget.setGeometry(0, 0, 500, buttons_container_height)
        self.update_buttons_widget.setGeometry(0, 0, 500, buttons_container_height)

        self.download_progress_updated.connect(self.update_progress_display)

        self.content_layout.addWidget(self.text_stack_wrapper)
        self.content_layout.addWidget(self.cassette_canvas)
        self.content_layout.addWidget(self.status_label)
        self.content_layout.addWidget(self.pulse_status_widget)
        self.content_layout.addWidget(self.buttons_stack_wrapper)

    # Animation Setup

    def setup_window_animations(self) -> None:
        self.cassette_yaw_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "cassette_yaw",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_model_yaw_changed
        )

        self.check_sway_intensity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "check_sway_intensity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE
        )

        self.about_opacity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "about_opacity",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_about_opacity_changed
        )

        self.credits_opacity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "credits_opacity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_credits_opacity_changed
        )

        self.about_buttons_opacity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "about_buttons_opacity",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_about_buttons_opacity_changed
        )

        self.about_buttons_offset_y_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "about_buttons_offset_y",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_about_buttons_offset_y_changed
        )

        self.about_text_opacity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "about_text_opacity",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_about_text_opacity_changed
        )

        self.about_text_offset_y_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "about_text_offset_y",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_about_text_offset_y_changed
        )

        self.title_opacity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "title_opacity",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_title_opacity_changed
        )

        self.title_offset_y_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "title_offset_y",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_title_offset_y_changed
        )

        self.update_info_opacity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "update_info_opacity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_update_info_opacity_changed
        )

        self.update_info_offset_y_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "update_info_offset_y",
            base_value = 30.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_update_info_offset_y_changed
        )

        self.update_buttons_opacity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "update_buttons_opacity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_update_buttons_opacity_changed
        )

        self.update_buttons_offset_y_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "update_buttons_offset_y",
            base_value = 30.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_update_buttons_offset_y_changed
        )

        self.model_scale_multiplier_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "model_scale_multiplier",
            base_value = 1.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_model_scale_multiplier_changed
        )

        self.model_spin_yaw_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "model_spin_yaw",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_model_spin_yaw_changed
        )

        self.model_smear_intensity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "model_smear_intensity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_model_smear_intensity_changed
        )

        self.model_iridescence_intensity_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "model_iridescence_intensity",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_model_iridescence_intensity_changed
        )

    def on_model_yaw_changed(self, value: object) -> None:
        self.model_yaw_offset = float(value)
        self.update()

    def on_about_opacity_changed(self, value: object) -> None:
        self.about_label.setProperty("paint_opacity", float(value))
        self.about_label.update()

    def on_credits_opacity_changed(self, value: object) -> None:
        self.credits_label.setProperty("paint_opacity", float(value))
        self.credits_label.update()

    @staticmethod
    def set_hierarchy_paint_opacity(
            target_widget: QWidget,
            opacity_value: float
        ) -> None:

        target_widget.setProperty("paint_opacity", opacity_value)
        target_widget.update()

        for child_widget in target_widget.findChildren(QWidget):
            child_widget.setProperty("paint_opacity", opacity_value)
            child_widget.update()

    def on_about_buttons_opacity_changed(self, value: object) -> None:
        self.set_hierarchy_paint_opacity(self.about_buttons_widget, float(value))

    def on_about_buttons_offset_y_changed(self, value: object) -> None:
        self.about_buttons_widget.move(0, int(float(value)))

    def on_about_text_opacity_changed(self, value: object) -> None:
        opacity_factor = float(value)

        about_target   = (0.0 if self.is_showing_credits else 1.0) * opacity_factor
        credits_target = (1.0 if self.is_showing_credits else 0.0) * opacity_factor

        self.about_label.setProperty("paint_opacity", about_target)
        self.about_label.update()

        self.credits_label.setProperty("paint_opacity", credits_target)
        self.credits_label.update()

    def on_about_text_offset_y_changed(self, value: object) -> None:
        self.text_view_widget.move(0, int(float(value)))

    def on_title_opacity_changed(self, value: object) -> None:
        self.set_hierarchy_paint_opacity(self.title_label, float(value))

    def on_title_offset_y_changed(self, value: object) -> None:
        offset_value = int(float(value))
        self.title_label.setContentsMargins(0, max(0, offset_value), 0, max(0, -offset_value))

    def on_update_info_opacity_changed(self, value: object) -> None:
        self.set_hierarchy_paint_opacity(self.update_content_widget, float(value))

    def on_update_info_offset_y_changed(self, value: object) -> None:
        self.update_content_widget.move(0, int(float(value)))

    def on_update_buttons_opacity_changed(self, value: object) -> None:
        self.set_hierarchy_paint_opacity(self.update_buttons_widget, float(value))

    def on_update_buttons_offset_y_changed(self, value: object) -> None:
        self.update_buttons_widget.move(0, int(float(value)))

    def on_model_scale_multiplier_changed(self, value: object) -> None:
        self.update()

    def on_model_spin_yaw_changed(self, value: object) -> None:
        self.update()

    def on_model_smear_intensity_changed(self, value: object) -> None:
        self.update()

    def on_model_iridescence_intensity_changed(self, value: object) -> None:
        self.update()

    def enable_update_buttons(self) -> None:
        self.update_buttons_widget.setEnabled(True)

    def enable_about_buttons(self) -> None:
        self.about_buttons_widget.setEnabled(True)

    # Model Loader

    def load_model_data(self, file_path: str) -> None:
        if not os.path.exists(file_path):
            self.model_batches = [PrimitiveMeshBatch(self.create_fallback_mesh())]

            return

        try:
            with open(file_path, "rb") as file_handle:
                file_bytes = file_handle.read()

        except OSError:
            self.model_batches = [PrimitiveMeshBatch(self.create_fallback_mesh())]

            return

        if len(file_bytes) < 20:
            self.model_batches = [PrimitiveMeshBatch(self.create_fallback_mesh())]

            return

        magic_bytes, version, total_length = struct.unpack("<4sII", file_bytes[0:12])

        if magic_bytes != b"glTF" or version != 2:
            self.model_batches = [PrimitiveMeshBatch(self.create_fallback_mesh())]

            return

        chunk_zero_length, chunk_zero_type = struct.unpack("<II", file_bytes[12:20])
        chunk_zero_data                    = file_bytes[20 : 20 + chunk_zero_length]

        try:
            parsed_json = json.loads(chunk_zero_data.decode("utf-8"))

        except Exception:
            self.model_batches = [PrimitiveMeshBatch(self.create_fallback_mesh())]

            return

        chunk_one_offset = 20 + chunk_zero_length
        binary_buffer    = b""

        if chunk_one_offset + 8 <= len(file_bytes):
            chunk_one_length, chunk_one_type = struct.unpack("<II", file_bytes[chunk_one_offset : chunk_one_offset + 8])
            binary_buffer                    = file_bytes[chunk_one_offset + 8 : chunk_one_offset + 8 + chunk_one_length]

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
            "VEC4":   4,
            "MAT4":   16
        }

        def read_accessor_data(accessor_index: int) -> numpy.ndarray:
            accessor_dictionary = parsed_json["accessors"][accessor_index]
            buffer_view_index   = accessor_dictionary["bufferView"]
            buffer_view         = parsed_json["bufferViews"][buffer_view_index]
            buffer_offset       = buffer_view.get("byteOffset", 0) + accessor_dictionary.get("byteOffset", 0)
            component_code      = accessor_dictionary["componentType"]
            component_type      = component_types.get(component_code, numpy.float32)
            type_string         = accessor_dictionary["type"]
            dimension_count     = type_dimensions.get(type_string, 1)
            element_count       = accessor_dictionary["count"]
            byte_stride         = buffer_view.get("byteStride", 0)
            element_byte_size   = dimension_count * numpy.dtype(component_type).itemsize

            if byte_stride == 0 or byte_stride == element_byte_size:
                data_array = numpy.frombuffer(
                    binary_buffer,
                    dtype  = component_type,
                    count  = element_count * dimension_count,
                    offset = buffer_offset
                )

                if dimension_count > 1:
                    data_array = data_array.reshape((element_count, dimension_count))

                return data_array

            data_array = numpy.empty((element_count, dimension_count), dtype = component_type)

            for element_index in range(element_count):
                start_offset              = buffer_offset + element_index * byte_stride
                data_array[element_index] = numpy.frombuffer(
                    binary_buffer[start_offset : start_offset + element_byte_size],
                    dtype = component_type
                )

            return data_array

        image_raw_bytes_list: list[bytes] = []

        for image_information in parsed_json.get("images", []):
            if "bufferView" in image_information:
                image_view_index   = image_information["bufferView"]
                image_buffer_view  = parsed_json["bufferViews"][image_view_index]
                image_start_offset = image_buffer_view.get("byteOffset", 0)
                image_byte_length  = image_buffer_view["byteLength"]
                image_raw_bytes_list.append(binary_buffer[image_start_offset : image_start_offset + image_byte_length])

            else:
                image_raw_bytes_list.append(b"")

        self.pending_image_bytes    = image_raw_bytes_list
        self.texture_source_indices = [
            texture_definition.get("source", -1)
            for texture_definition in parsed_json.get("textures", [])
        ]

        primitive_records    = []
        all_vertex_positions = []

        for mesh in parsed_json.get("meshes", []):
            for primitive in mesh.get("primitives", []):
                attributes = primitive.get("attributes", {})

                if "POSITION" not in attributes:
                    continue

                position_array = read_accessor_data(attributes["POSITION"]).astype(numpy.float32)
                normal_array   = None

                if "NORMAL" in attributes:
                    normal_array = read_accessor_data(attributes["NORMAL"]).astype(numpy.float32)

                texture_coordinate_array = None

                if "TEXCOORD_0" in attributes:
                    texture_coordinate_array = read_accessor_data(attributes["TEXCOORD_0"]).astype(numpy.float32)

                tangent_array = None

                if "TANGENT" in attributes:
                    tangent_array = read_accessor_data(attributes["TANGENT"]).astype(numpy.float32)

                if "indices" in primitive:
                    index_array    = read_accessor_data(primitive["indices"]).astype(numpy.int64).flatten()
                    position_array = position_array[index_array]

                    if normal_array is not None:
                        normal_array = normal_array[index_array]

                    if texture_coordinate_array is not None:
                        texture_coordinate_array = texture_coordinate_array[index_array]

                    if tangent_array is not None:
                        tangent_array = tangent_array[index_array]

                if texture_coordinate_array is None:
                    texture_coordinate_array = numpy.zeros((len(position_array), 2), dtype = numpy.float32)

                if normal_array is None:
                    triangle_count         = len(position_array) // 3
                    triangles              = position_array[: triangle_count * 3].reshape(-1, 3, 3)
                    edge_one               = triangles[:, 1] - triangles[:, 0]
                    edge_two               = triangles[:, 2] - triangles[:, 0]
                    face_normals           = numpy.cross(edge_one, edge_two)
                    lengths                = numpy.linalg.norm(face_normals, axis = 1, keepdims = True)
                    lengths[lengths == 0]  = 1.0
                    face_normals           = face_normals / lengths
                    normal_array           = numpy.repeat(face_normals, 3, axis = 0)

                if tangent_array is None:
                    tangent_array       = numpy.zeros((len(position_array), 4), dtype = numpy.float32)
                    tangent_array[:, 0] = 1.0
                    tangent_array[:, 3] = 1.0

                material_index      = primitive.get("material", -1)
                texture_pointer_map = {
                    "base_color":         -1,
                    "normal":             -1,
                    "metallic_roughness": -1,
                    "emissive":           -1
                }

                if 0 <= material_index < len(parsed_json.get("materials", [])):
                    material_information     = parsed_json["materials"][material_index]
                    material_pbr_information = material_information.get("pbrMetallicRoughness", {})

                    if "baseColorTexture" in material_pbr_information:
                        texture_pointer_map["base_color"] = material_pbr_information["baseColorTexture"].get("index", -1)

                    if "normalTexture" in material_information:
                        texture_pointer_map["normal"] = material_information["normalTexture"].get("index", -1)

                    if "metallicRoughnessTexture" in material_pbr_information:
                        texture_pointer_map["metallic_roughness"] = material_pbr_information["metallicRoughnessTexture"].get("index", -1)

                    if "emissiveTexture" in material_information:
                        texture_pointer_map["emissive"] = material_information["emissiveTexture"].get("index", -1)

                primitive_records.append({
                    "positions":           position_array,
                    "normals":             normal_array,
                    "texture_coordinates": texture_coordinate_array,
                    "tangents":            tangent_array,
                    "textures":            texture_pointer_map
                })

                all_vertex_positions.append(position_array)

        if not primitive_records:
            self.model_batches = [PrimitiveMeshBatch(self.create_fallback_mesh())]

            return

        concatenated_positions = numpy.concatenate(all_vertex_positions, axis = 0)
        minimum_bounds         = numpy.min(concatenated_positions, axis = 0)
        maximum_bounds         = numpy.max(concatenated_positions, axis = 0)
        center_point           = (minimum_bounds + maximum_bounds) / 2.0
        span_size              = float(numpy.max(maximum_bounds - minimum_bounds))

        if span_size <= 0.0:
            span_size = 1.0

        batches = []

        for record in primitive_records:
            normalized_positions = (record["positions"] - center_point) / span_size
            normals              = record["normals"]
            texture_coordinates  = record["texture_coordinates"]
            tangents             = record["tangents"]

            total_vertices = len(normalized_positions)
            interleaved    = numpy.empty((total_vertices, 12), dtype = numpy.float32)

            interleaved[:, 0:3]  = normalized_positions
            interleaved[:, 3:6]  = normals
            interleaved[:, 6:8]  = texture_coordinates
            interleaved[:, 8:12] = tangents

            batch = PrimitiveMeshBatch(
                vertex_buffer_data            = interleaved.flatten(),
                texture_base_color_id         = record["textures"]["base_color"],
                texture_normal_id             = record["textures"]["normal"],
                texture_metallic_roughness_id = record["textures"]["metallic_roughness"],
                texture_emissive_id           = record["textures"]["emissive"]
            )
            batches.append(batch)

        self.model_batches = batches

    # Fallback Mesh Generator

    def create_fallback_mesh(self) -> numpy.ndarray:
        half_width  = 0.50
        half_height = 0.32
        half_depth  = 0.06

        quads = [
            ([0.0, 0.0, 1.0],  [(-half_width, -half_height,  half_depth), ( half_width, -half_height,  half_depth), ( half_width,  half_height,  half_depth), (-half_width,  half_height,  half_depth)]),
            ([0.0, 0.0, -1.0], [( half_width, -half_height, -half_depth), (-half_width, -half_height, -half_depth), (-half_width,  half_height, -half_depth), ( half_width,  half_height, -half_depth)]),
            ([-1.0, 0.0, 0.0], [(-half_width, -half_height, -half_depth), (-half_width, -half_height,  half_depth), (-half_width,  half_height,  half_depth), (-half_width,  half_height, -half_depth)]),
            ([1.0, 0.0, 0.0],  [( half_width, -half_height,  half_depth), ( half_width, -half_height, -half_depth), ( half_width,  half_height, -half_depth), ( half_width,  half_height,  half_depth)]),
            ([0.0, 1.0, 0.0],  [(-half_width,  half_height,  half_depth), ( half_width,  half_height,  half_depth), ( half_width,  half_height, -half_depth), (-half_width,  half_height, -half_depth)]),
            ([0.0, -1.0, 0.0], [(-half_width, -half_height, -half_depth), ( half_width, -half_height, -half_depth), ( half_width, -half_height,  half_depth), (-half_width, -half_height,  half_depth)])
        ]

        vertices = []

        for normal_direction, corners in quads:
            triangle_vertices = [
                (corners[0], [0.0, 1.0]),
                (corners[1], [1.0, 1.0]),
                (corners[2], [1.0, 0.0]),
                (corners[0], [0.0, 1.0]),
                (corners[2], [1.0, 0.0]),
                (corners[3], [0.0, 0.0])
            ]

            for position, uv_coordinates in triangle_vertices:
                vertices.extend([*position, *normal_direction, *uv_coordinates, 1.0, 0.0, 0.0, 1.0])

        return numpy.array(vertices, dtype = numpy.float32)

    # Texture Management

    def upload_parsed_textures(self) -> None:
        raw_images             = self.pending_image_bytes
        texture_source_indices = self.texture_source_indices
        uploaded_texture_ids   = []

        for image_bytes in raw_images:
            if not image_bytes:
                uploaded_texture_ids.append(0)

                continue

            image   = QImage()
            success = image.loadFromData(image_bytes)

            if not success:
                uploaded_texture_ids.append(0)

                continue

            image_rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
            raw_bits   = image_rgba.constBits()
            raw_bits.setsize(image_rgba.sizeInBytes())

            gl_texture_id = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, gl_texture_id)
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D,
                0,
                GL.GL_RGBA,
                image_rgba.width(),
                image_rgba.height(),
                0,
                GL.GL_RGBA,
                GL.GL_UNSIGNED_BYTE,
                bytes(raw_bits)
            )
            GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_REPEAT)

            uploaded_texture_ids.append(gl_texture_id)

        self.model_texture_ids = uploaded_texture_ids

        def resolve_texture_id(texture_index: int) -> int:
            if not (0 <= texture_index < len(texture_source_indices)):
                return 0

            source_index = texture_source_indices[texture_index]

            if not (0 <= source_index < len(uploaded_texture_ids)):
                return 0

            return uploaded_texture_ids[source_index]

        for batch in self.model_batches:
            batch.texture_base_color_id         = resolve_texture_id(batch.texture_base_color_id)
            batch.texture_normal_id             = resolve_texture_id(batch.texture_normal_id)
            batch.texture_metallic_roughness_id = resolve_texture_id(batch.texture_metallic_roughness_id)
            batch.texture_emissive_id           = resolve_texture_id(batch.texture_emissive_id)

    def apply_batch_texture(
            self,
            texture_unit:         int,
            texture_id:           int,
            has_texture_location: int
        ) -> None:

        if texture_id <= 0:
            GL.glUniform1i(has_texture_location, 0)

            return

        GL.glActiveTexture(texture_unit)
        GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
        GL.glUniform1i(has_texture_location, 1)

    # OpenGL Lifecycle

    def initializeGL(self) -> None:
        super().initializeGL()

        vertex_shader   = shaders.compileShader(CASSETTE_VERTEX_SHADER_SOURCE,   GL.GL_VERTEX_SHADER)
        fragment_shader = shaders.compileShader(CASSETTE_FRAGMENT_SHADER_SOURCE, GL.GL_FRAGMENT_SHADER)

        self.cassette_shader_program = shaders.compileProgram(vertex_shader, fragment_shader)

        self.model_location_projection            = GL.glGetUniformLocation(self.cassette_shader_program, "projection_matrix")
        self.model_location_view                  = GL.glGetUniformLocation(self.cassette_shader_program, "view_matrix")
        self.model_location_model                 = GL.glGetUniformLocation(self.cassette_shader_program, "model_matrix")
        self.model_location_camera_position       = GL.glGetUniformLocation(self.cassette_shader_program, "camera_position")
        self.model_location_accent_color          = GL.glGetUniformLocation(self.cassette_shader_program, "accent_color")
        self.model_location_button_light          = GL.glGetUniformLocation(self.cassette_shader_program, "button_light_position")
        self.model_location_global_alpha          = GL.glGetUniformLocation(self.cassette_shader_program, "global_alpha")
        self.model_location_smear_intensity       = GL.glGetUniformLocation(self.cassette_shader_program, "smear_intensity")
        self.model_location_smear_phase           = GL.glGetUniformLocation(self.cassette_shader_program, "smear_phase")
        self.model_location_iridescence_intensity = GL.glGetUniformLocation(self.cassette_shader_program, "iridescence_intensity")

        self.location_sampler_base_color          = GL.glGetUniformLocation(self.cassette_shader_program, "base_color_sampler")
        self.location_sampler_normal              = GL.glGetUniformLocation(self.cassette_shader_program, "normal_sampler")
        self.location_sampler_metallic_roughness  = GL.glGetUniformLocation(self.cassette_shader_program, "metallic_roughness_sampler")
        self.location_sampler_emissive            = GL.glGetUniformLocation(self.cassette_shader_program, "emissive_sampler")

        self.location_has_base_color              = GL.glGetUniformLocation(self.cassette_shader_program, "has_base_color_texture")
        self.location_has_normal                  = GL.glGetUniformLocation(self.cassette_shader_program, "has_normal_texture")
        self.location_has_metallic_roughness      = GL.glGetUniformLocation(self.cassette_shader_program, "has_metallic_roughness_texture")
        self.location_has_emissive                = GL.glGetUniformLocation(self.cassette_shader_program, "has_emissive_texture")

        self.upload_parsed_textures()

        for batch in self.model_batches:
            batch.allocate_gl()

    def paintGL(self) -> None:
        super().paintGL()

        if not self.model_batches or self.cassette_shader_program is None:
            return

        background_alpha = float(self.opacity_background_property.value) if self.animations_active else 1.0

        if background_alpha <= 0.001:
            return

        current_time_sec = float(time.perf_counter())

        pixel_ratio      = self.devicePixelRatio()
        window_width_px  = max(1, int(self.width() * pixel_ratio))
        window_height_px = max(1, int(self.height() * pixel_ratio))

        canvas_geometry = self.cassette_canvas.geometry()
        canvas_center   = self.content_widget.mapTo(self, canvas_geometry.center())

        field_of_view_y   = 32.0
        camera_distance_z = 2.05

        visible_height_units = 2.0 * math.tan(math.radians(field_of_view_y / 2.0)) * camera_distance_z
        units_per_pixel      = visible_height_units / float(max(1, self.height()))

        pixel_offset_x = float(canvas_center.x()) - float(self.width()) / 2.0
        pixel_offset_y = float(canvas_center.y()) - float(self.height()) / 2.0

        model_offset_x = pixel_offset_x * units_per_pixel
        model_offset_y = -pixel_offset_y * units_per_pixel

        target_model_width_px = float(canvas_geometry.width())
        base_model_scale      = target_model_width_px * units_per_pixel
        scale_multiplier      = float(self.model_scale_multiplier_property.value)
        model_scale           = base_model_scale * scale_multiplier

        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)
        GL.glViewport(0, 0, window_width_px, window_height_px)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        GL.glUseProgram(self.cassette_shader_program)

        aspect_ratio = float(window_width_px) / float(window_height_px)

        projection_matrix = QMatrix4x4()
        projection_matrix.perspective(field_of_view_y, aspect_ratio, 0.1, 50.0)

        view_matrix     = QMatrix4x4()
        camera_position = QVector3D(0.0, 0.0, camera_distance_z)
        view_matrix.lookAt(camera_position, QVector3D(0.0, 0.0, 0.0), QVector3D(0.0, 1.0, 0.0))

        tilt_x = 0.0
        tilt_y = 0.0
        tilt_z = 0.0

        if self.animations_active:
            tilt_x = -float(self.rotation_x_property.value + self.current_tilt_x)
            tilt_y = float(self.rotation_y_property.value + self.current_tilt_y)
            tilt_z = float(self.rotation_z_property.value)

        idle_sway_y = math.sin(current_time_sec * 1.2) * 2.0
        idle_sway_x = math.cos(current_time_sec * 0.9) * 1.2

        smoothing_factor = 0.08

        if self.cassette_canvas.is_mouse_pressed:
            self.cassette_canvas.manual_yaw   += (self.cassette_canvas.target_manual_yaw - self.cassette_canvas.manual_yaw)     * smoothing_factor
            self.cassette_canvas.manual_pitch += (self.cassette_canvas.target_manual_pitch - self.cassette_canvas.manual_pitch) * smoothing_factor

        else:
            self.cassette_canvas.target_manual_yaw   *= 0.92
            self.cassette_canvas.target_manual_pitch *= 0.92
            self.cassette_canvas.manual_yaw          += (0.0 - self.cassette_canvas.manual_yaw)   * smoothing_factor
            self.cassette_canvas.manual_pitch        += (0.0 - self.cassette_canvas.manual_pitch) * smoothing_factor

        sway_yaw   = 0.0
        sway_pitch = 0.0
        sway_roll  = 0.0

        sway_intensity = float(self.check_sway_intensity_property.value)

        if self.is_checking_updates or sway_intensity > 0.001:
            checking_elapsed_sec = current_time_sec - self.checking_started_at
            sway_yaw             = math.sin(checking_elapsed_sec * CHECK_SWAY_FREQUENCY) * CHECK_SWAY_AMPLITUDE_YAW * sway_intensity
            sway_pitch           = math.sin(checking_elapsed_sec * CHECK_SWAY_FREQUENCY * 0.7) * CHECK_SWAY_AMPLITUDE_PITCH * sway_intensity
            sway_roll            = math.sin(checking_elapsed_sec * CHECK_SWAY_FREQUENCY * 0.5) * CHECK_SWAY_AMPLITUDE_ROLL * sway_intensity
            self.update()

        spin_yaw_angle = float(self.model_spin_yaw_property.value)
        smear_phase    = spin_yaw_angle * 0.02

        model_matrix = QMatrix4x4()
        model_matrix.translate(model_offset_x, model_offset_y, 0.0)
        model_matrix.rotate(
            -tilt_x * 1.4 + idle_sway_x + self.cassette_canvas.manual_pitch + sway_pitch,
            1.0, 0.0, 0.0
        )
        model_matrix.rotate(
            tilt_y * 1.4 + idle_sway_y + self.cassette_canvas.manual_yaw + self.model_yaw_offset + spin_yaw_angle + sway_yaw,
            0.0, 1.0, 0.0
        )
        model_matrix.rotate(tilt_z * 1.2 + sway_roll, 0.0, 0.0, 1.0)
        model_matrix.rotate(180.0, 0.0, 0.0, 1.0)
        model_matrix.scale(model_scale, model_scale, model_scale)

        accent_color_value = QColor(Styles.Colors.NothingAccent)

        GL.glUniformMatrix4fv(self.model_location_projection, 1, GL.GL_FALSE, projection_matrix.data())
        GL.glUniformMatrix4fv(self.model_location_view, 1, GL.GL_FALSE, view_matrix.data())
        GL.glUniformMatrix4fv(self.model_location_model, 1, GL.GL_FALSE, model_matrix.data())
        GL.glUniform3f(self.model_location_camera_position, camera_position.x(), camera_position.y(), camera_position.z())
        GL.glUniform3f(
            self.model_location_accent_color,
            accent_color_value.redF(),
            accent_color_value.greenF(),
            accent_color_value.blueF()
        )
        GL.glUniform3f(
            self.model_location_button_light,
            model_offset_x,
            model_offset_y - model_scale * 0.62,
            model_scale * 0.28
        )
        GL.glUniform1f(self.model_location_global_alpha, background_alpha)
        GL.glUniform1f(self.model_location_smear_intensity, float(self.model_smear_intensity_property.value))
        GL.glUniform1f(self.model_location_smear_phase, smear_phase)
        GL.glUniform1f(self.model_location_iridescence_intensity, float(self.model_iridescence_intensity_property.value))

        GL.glUniform1i(self.location_sampler_base_color, 0)
        GL.glUniform1i(self.location_sampler_normal, 1)
        GL.glUniform1i(self.location_sampler_metallic_roughness, 2)
        GL.glUniform1i(self.location_sampler_emissive, 3)

        for batch in self.model_batches:
            self.apply_batch_texture(GL.GL_TEXTURE0, batch.texture_base_color_id, self.location_has_base_color)
            self.apply_batch_texture(GL.GL_TEXTURE1, batch.texture_normal_id, self.location_has_normal)
            self.apply_batch_texture(GL.GL_TEXTURE2, batch.texture_metallic_roughness_id, self.location_has_metallic_roughness)
            self.apply_batch_texture(GL.GL_TEXTURE3, batch.texture_emissive_id, self.location_has_emissive)

            batch.draw()

        GL.glDisable(GL.GL_DEPTH_TEST)

    def really_close(self) -> None:
        if self.is_downloading:
            self.cancel_download()

        self.makeCurrent()

        for batch in self.model_batches:
            batch.cleanup()

        for texture_id in self.model_texture_ids:
            if texture_id > 0:
                GL.glDeleteTextures(1, [texture_id])

        self.model_texture_ids.clear()
        self.model_batches.clear()

        if self.cassette_shader_program is not None:
            GL.glDeleteProgram(self.cassette_shader_program)
            self.cassette_shader_program = None

        self.doneCurrent()
        super().really_close()

    # User Actions

    def on_credits(self) -> None:
        if self.is_closing:
            return

        self.is_showing_credits = not self.is_showing_credits

        credits_button = self.button_row.get_button_by_number(3)

        if credits_button is not None:
            credits_button.setText("About" if self.is_showing_credits else "Credits")

        target_yaw     = 180.0 if self.is_showing_credits else 0.0
        target_about   = 0.0 if self.is_showing_credits else 1.0
        target_credits = 1.0 if self.is_showing_credits else 0.0

        self.cassette_yaw_property.set_target(
            value           = target_yaw,
            duration_ms     = 700,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        self.about_opacity_property.set_target(
            value           = target_about,
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

        self.credits_opacity_property.set_target(
            value           = target_credits,
            duration_ms     = 300,
            easing_function = LoomEngine.Easing.ease_out_cubic
        )

    def on_github(self) -> None:
        github_link = Constants.GITHUB_LINK

        if random.random() < 0.95:
            webbrowser.open(github_link)

            return

        fox_image = Utils.get_fox_image()
        webbrowser.open(fox_image if fox_image else github_link)

    def on_feedback(self) -> None:
        FeedbackWindow(parent = self).exec()

    def on_check_updates(self) -> None:
        if self.cached_update_information is not None:
            self.on_update_info_received("release", self.cached_update_information)

            return

        button = self.button_row.get_button_by_number(2)

        if button is not None:
            button.setEnabled(False)
            button.setText("Checking...")

        self.is_checking_updates = True
        self.checking_started_at = time.perf_counter()
        self.check_sway_intensity_property.set_base(0.0)
        self.check_sway_intensity_property.set_target(
            value           = 1.0,
            duration_ms     = 1200,
            easing_function = LoomEngine.Easing.smooth
        )
        self.update()

        self.update_checker = Utils.UpdateChecker()
        self.update_checker.resource_loaded.connect(self.on_update_info_received)
        self.update_checker.error_occurred.connect(self.on_update_check_failed)
        self.update_checker.fetch_latest_release()

    def on_model_dragged(self) -> None:
        if self.model_rotation_easter_egg_shown or self.model_drag_started_at is not None:
            return

        self.model_drag_started_at = time.perf_counter()
        self.model_drag_timer.start()

    def on_model_drag_ended(self) -> None:
        if self.model_drag_started_at is None:
            return

        self.model_drag_duration_ms += (time.perf_counter() - self.model_drag_started_at) * 1000.0
        self.model_drag_started_at   = None
        self.model_drag_timer.stop()
        self.check_model_rotation_easter_egg()

    def check_model_rotation_easter_egg(self) -> None:
        if self.model_rotation_easter_egg_shown:
            return

        elapsed_ms = self.model_drag_duration_ms

        if self.model_drag_started_at is not None:
            elapsed_ms += (time.perf_counter() - self.model_drag_started_at) * 1000.0

        if elapsed_ms < 10000:
            return

        self.model_rotation_easter_egg_shown    = True
        self.model_drag_timer.stop()
        self.cassette_canvas.is_mouse_pressed    = False
        self.cassette_canvas.drag_start_position = None
        self.cassette_canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        Constants.current_settings.set_value("_about_model_rotated_seen", True)

        ErrorWindow(
            "Ahem...",
            "As I see, you like it very much.",
            parent = self
        ).exec()

    # Update Checker Handlers

    def on_update_info_received(
            self,
            resource_identifier: str,
            release_information: dict[str, object]
        ) -> None:

        self.check_sway_intensity_property.set_target(
            value           = 0.0,
            duration_ms     = 1200,
            easing_function = LoomEngine.Easing.smooth
        )

        update_button = self.button_row.get_button_by_number(2)

        if resource_identifier != "release" or not isinstance(release_information, dict):
            self.is_checking_updates = False
            self.update()

            if update_button is not None:
                update_button.setEnabled(True)
                update_button.setText("Check updates")

            return

        remote_tag = str(release_information.get("tag_name", ""))

        if not Utils.is_newer_version(remote_tag, self.local_version):
            self.is_checking_updates = False
            self.update()

            if update_button is not None:
                update_button.setEnabled(True)
                update_button.setText("Latest version")

            return

        self.about_buttons_widget.setEnabled(False)
        self.update_buttons_widget.setEnabled(False)

        self.cached_update_information   = release_information
        self.is_checking_updates         = False
        self.is_showing_update_view      = True
        self.pending_remote_tag          = remote_tag
        self.pending_release_information = release_information
        self.pending_changelog_text      = str(release_information.get("body", ""))
        self.pending_release_url         = str(release_information.get("html_url", Constants.GITHUB_LINK))

        self.prepare_update_view()
        self.resolve_target_asset()

        Player.ui_player.play_sound("Alerts/UpdateFound")

        QTimer.singleShot(FORWARD_DELAY_BUTTONS_OUT_MS,    self.forward_step_animate_buttons_out)
        QTimer.singleShot(FORWARD_DELAY_TEXT_OUT_MS,       self.forward_step_animate_text_and_title_out)
        QTimer.singleShot(FORWARD_DELAY_MODEL_PULSE_MS,    self.forward_step_animate_model_pulse)
        QTimer.singleShot(FORWARD_DELAY_ACCELERATION_MS,   self.forward_step_animate_model_acceleration)
        QTimer.singleShot(FORWARD_DELAY_HIGH_SPEED_MS,     self.forward_step_animate_high_speed_spin)
        QTimer.singleShot(FORWARD_DELAY_IRIDESCENCE_MS,    self.forward_step_animate_iridescence_in)
        QTimer.singleShot(FORWARD_DELAY_DECELERATION_MS,   self.forward_step_animate_model_deceleration)
        QTimer.singleShot(FORWARD_DELAY_UPDATE_IN_MS,      self.forward_step_animate_update_interface_in)
        QTimer.singleShot(FORWARD_DELAY_ENABLE_BUTTONS_MS, self.enable_update_buttons)
        QTimer.singleShot(FORWARD_DELAY_FINISH_SPIN_MS,    self.forward_step_finish_model_spin)

    def on_update_check_failed(self, request_type: str) -> None:
        self.check_sway_intensity_property.set_target(
            value           = 0.0,
            duration_ms     = 1200,
            easing_function = LoomEngine.Easing.smooth
        )

        self.is_checking_updates = False
        self.update()

        button = self.button_row.get_button_by_number(2)

        if button is not None:
            button.setEnabled(True)
            button.setText("Check updates")
            button.start_glitch()

        ErrorWindow(
            "Check Failed",
            "Unable to fetch the latest release from GitHub. Please check your network connection.",
            "I hate my Wi - Fi"
        ).exec()

    # Forward Transition Sequence

    def prepare_update_view(self) -> None:
        self.update_action_button.setEnabled(True)
        self.update_cancel_button.setText("Later")

        formatted_changelog = self.format_changelog_text(self.pending_changelog_text)

        if formatted_changelog:
            content_text = f"`A new version is available.`\n\n{formatted_changelog}"

        else:
            content_text = "`A new version is available.`"

        self.update_label.setText(content_text)
        self.update_scroll_area.layout_manager.setAlignment(self.update_label, Qt.AlignmentFlag.AlignTop)

        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(self.update_label.font())
        document.setTextWidth(500.0)
        document.setHtml(self.update_label.text())

        measured_height       = int(document.size().height()) + 20
        optimal_scroll_height = min(self.text_container_height, max(60, measured_height))

        self.update_scroll_area.setFixedHeight(optimal_scroll_height)
        self.update_content_widget.setFixedHeight(optimal_scroll_height)
        self.text_stack_wrapper.setFixedHeight(optimal_scroll_height)

        self.update_scroll_area.raw_scroll_position = 0.0
        self.update_scroll_area.apply_content_position()
        self.update_scroll_area.update_canvas_geometry()

    def forward_step_animate_buttons_out(self) -> None:
        self.about_buttons_opacity_property.set_target(
            value                      = 0.0,
            duration_ms                = FORWARD_DURATION_BUTTONS_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.about_buttons_offset_y_property.set_target(
            value                      = 40.0,
            duration_ms                = FORWARD_DURATION_BUTTONS_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )

    def forward_step_animate_text_and_title_out(self) -> None:
        self.about_text_opacity_property.set_target(
            value                      = 0.0,
            duration_ms                = FORWARD_DURATION_TEXT_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.about_text_offset_y_property.set_target(
            value                      = 40.0,
            duration_ms                = FORWARD_DURATION_TEXT_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.title_opacity_property.set_target(
            value                      = 0.0,
            duration_ms                = FORWARD_DURATION_TITLE_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.title_offset_y_property.set_target(
            value                      = 40.0,
            duration_ms                = FORWARD_DURATION_TITLE_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )

    def forward_step_animate_model_pulse(self) -> None:
        self.model_scale_multiplier_property.set_target(
            value                      = FORWARD_TARGET_SCALE,
            duration_ms                = FORWARD_DURATION_MODEL_PULSE_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def forward_step_animate_model_acceleration(self) -> None:
        self.model_spin_yaw_property.set_base(0.0)
        self.model_spin_yaw_property.set_target(
            value                      = FORWARD_SPIN_STAGE_ONE_DEGREES,
            duration_ms                = FORWARD_DURATION_ACCELERATION_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.model_smear_intensity_property.set_target(
            value                      = 1.0,
            duration_ms                = FORWARD_DURATION_ACCELERATION_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )

    def forward_step_animate_high_speed_spin(self) -> None:
        self.model_spin_yaw_property.set_target(
            value                      = FORWARD_SPIN_STAGE_TWO_DEGREES,
            duration_ms                = FORWARD_DURATION_HIGH_SPEED_MS,
            easing_function            = LoomEngine.Easing.linear,
            multiply_duration_by_speed = False
        )

    def forward_step_animate_iridescence_in(self) -> None:
        self.model_iridescence_intensity_property.set_target(
            value                      = 1.0,
            duration_ms                = FORWARD_DURATION_IRIDESCENCE_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def forward_step_animate_model_deceleration(self) -> None:
        self.model_spin_yaw_property.set_target(
            value                      = FORWARD_SPIN_FINAL_DEGREES,
            duration_ms                = FORWARD_DURATION_DECELERATION_MS,
            easing_function            = LoomEngine.Easing.ease_out_expo,
            multiply_duration_by_speed = False
        )
        self.model_smear_intensity_property.set_target(
            value                      = 0.0,
            duration_ms                = FORWARD_DURATION_SMEAR_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def forward_step_animate_update_interface_in(self) -> None:
        self.text_view_widget.setVisible(False)
        self.about_buttons_widget.setVisible(False)

        self.update_content_widget.setVisible(True)
        self.update_buttons_widget.setVisible(True)

        self.title_label.setText(f"Cassette {self.pending_remote_tag}")

        self.model_scale_multiplier_property.set_target(
            value                      = 1.0,
            duration_ms                = FORWARD_DURATION_MODEL_SCALE_BACK_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

        self.title_offset_y_property.set_base(-30.0)
        self.title_opacity_property.set_target(
            value                      = 1.0,
            duration_ms                = FORWARD_DURATION_TITLE_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )
        self.title_offset_y_property.set_target(
            value                      = 0.0,
            duration_ms                = FORWARD_DURATION_TITLE_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

        self.update_info_offset_y_property.set_base(-30.0)
        self.update_info_opacity_property.set_target(
            value                      = 1.0,
            duration_ms                = FORWARD_DURATION_INFO_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )
        self.update_info_offset_y_property.set_target(
            value                      = 0.0,
            duration_ms                = FORWARD_DURATION_INFO_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

        self.update_buttons_offset_y_property.set_base(30.0)
        self.update_buttons_opacity_property.set_target(
            value                      = 1.0,
            duration_ms                = FORWARD_DURATION_BUTTONS_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )
        self.update_buttons_offset_y_property.set_target(
            value                      = 0.0,
            duration_ms                = FORWARD_DURATION_BUTTONS_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def forward_step_finish_model_spin(self) -> None:
        self.model_spin_yaw_property.set_base(0.0)
        self.update()

    # Reverse Transition Sequence

    def start_reverse_transition_to_about(self) -> None:
        if self.is_downloading:
            self.cancel_download()

        self.update_buttons_widget.setEnabled(False)
        self.about_buttons_widget.setEnabled(False)

        self.status_label.setVisible(False)
        self.pulse_status_widget.setVisible(False)

        Player.ui_player.play_sound("Alerts/UpdateFound")

        QTimer.singleShot(REVERSE_DELAY_BUTTONS_OUT_MS,      self.reverse_step_animate_buttons_out)
        QTimer.singleShot(REVERSE_DELAY_TEXT_OUT_MS,         self.reverse_step_animate_text_and_title_out)
        QTimer.singleShot(REVERSE_DELAY_MODEL_SCALE_MS,      self.reverse_step_animate_model_scale_back)
        QTimer.singleShot(REVERSE_DELAY_ACCELERATION_MS,     self.reverse_step_animate_model_acceleration)
        QTimer.singleShot(REVERSE_DELAY_HIGH_SPEED_MS,       self.reverse_step_animate_high_speed_spin)
        QTimer.singleShot(REVERSE_DELAY_IRIDESCENCE_OUT_MS,  self.reverse_step_animate_iridescence_out)
        QTimer.singleShot(REVERSE_DELAY_DECELERATION_MS,     self.reverse_step_animate_model_deceleration)
        QTimer.singleShot(REVERSE_DELAY_ABOUT_IN_MS,         self.reverse_step_animate_about_interface_in)
        QTimer.singleShot(REVERSE_DELAY_ENABLE_BUTTONS_MS,   self.enable_about_buttons)
        QTimer.singleShot(REVERSE_DELAY_FINISH_SPIN_MS,      self.reverse_step_finish_model_spin)

    def reverse_step_animate_buttons_out(self) -> None:
        self.update_buttons_opacity_property.set_target(
            value                      = 0.0,
            duration_ms                = REVERSE_DURATION_BUTTONS_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.update_buttons_offset_y_property.set_target(
            value                      = 40.0,
            duration_ms                = REVERSE_DURATION_BUTTONS_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )

    def reverse_step_animate_text_and_title_out(self) -> None:
        self.update_info_opacity_property.set_target(
            value                      = 0.0,
            duration_ms                = REVERSE_DURATION_TEXT_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.update_info_offset_y_property.set_target(
            value                      = 40.0,
            duration_ms                = REVERSE_DURATION_TEXT_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.title_opacity_property.set_target(
            value                      = 0.0,
            duration_ms                = REVERSE_DURATION_TITLE_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.title_offset_y_property.set_target(
            value                      = 40.0,
            duration_ms                = REVERSE_DURATION_TITLE_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )

    def reverse_step_animate_model_scale_back(self) -> None:
        self.model_scale_multiplier_property.set_target(
            value                      = 1.0,
            duration_ms                = REVERSE_DURATION_MODEL_SCALE_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def reverse_step_animate_model_acceleration(self) -> None:
        self.model_spin_yaw_property.set_base(0.0)
        self.model_spin_yaw_property.set_target(
            value                      = REVERSE_SPIN_STAGE_ONE_DEGREES,
            duration_ms                = REVERSE_DURATION_ACCELERATION_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )
        self.model_smear_intensity_property.set_target(
            value                      = 1.0,
            duration_ms                = REVERSE_DURATION_ACCELERATION_MS,
            easing_function            = LoomEngine.Easing.ease_in_quad,
            multiply_duration_by_speed = False
        )

    def reverse_step_animate_high_speed_spin(self) -> None:
        self.model_spin_yaw_property.set_target(
            value                      = REVERSE_SPIN_STAGE_TWO_DEGREES,
            duration_ms                = REVERSE_DURATION_HIGH_SPEED_MS,
            easing_function            = LoomEngine.Easing.linear,
            multiply_duration_by_speed = False
        )

    def reverse_step_animate_iridescence_out(self) -> None:
        self.model_iridescence_intensity_property.set_target(
            value                      = 0.0,
            duration_ms                = REVERSE_DURATION_IRIDESCENCE_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def reverse_step_animate_model_deceleration(self) -> None:
        self.model_spin_yaw_property.set_target(
            value                      = REVERSE_SPIN_FINAL_DEGREES,
            duration_ms                = REVERSE_DURATION_DECELERATION_MS,
            easing_function            = LoomEngine.Easing.ease_out_expo,
            multiply_duration_by_speed = False
        )
        self.model_smear_intensity_property.set_target(
            value                      = 0.0,
            duration_ms                = REVERSE_DURATION_SMEAR_OUT_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def reverse_step_animate_about_interface_in(self) -> None:
        self.update_content_widget.setVisible(False)
        self.update_buttons_widget.setVisible(False)

        self.text_stack_wrapper.setFixedHeight(self.text_container_height)
        self.text_view_widget.setFixedHeight(self.text_container_height)
        self.text_view_widget.setVisible(True)
        self.about_buttons_widget.setVisible(True)

        self.title_label.setText(f"Cassette {self.local_version}")

        check_updates_button = self.button_row.get_button_by_number(2)

        if check_updates_button is not None:
            check_updates_button.setEnabled(True)

            if self.cached_update_information is not None:
                check_updates_button.setText("Update available")

            else:
                check_updates_button.setText("Check updates")

        self.title_offset_y_property.set_base(-30.0)
        self.title_opacity_property.set_target(
            value                      = 1.0,
            duration_ms                = REVERSE_DURATION_TITLE_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )
        self.title_offset_y_property.set_target(
            value                      = 0.0,
            duration_ms                = REVERSE_DURATION_TITLE_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

        self.about_text_offset_y_property.set_base(-30.0)
        self.about_text_opacity_property.set_target(
            value                      = 1.0,
            duration_ms                = REVERSE_DURATION_ABOUT_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )
        self.about_text_offset_y_property.set_target(
            value                      = 0.0,
            duration_ms                = REVERSE_DURATION_ABOUT_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

        self.about_buttons_offset_y_property.set_base(30.0)
        self.about_buttons_opacity_property.set_target(
            value                      = 1.0,
            duration_ms                = REVERSE_DURATION_BUTTONS_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )
        self.about_buttons_offset_y_property.set_target(
            value                      = 0.0,
            duration_ms                = REVERSE_DURATION_BUTTONS_IN_MS,
            easing_function            = LoomEngine.Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def reverse_step_finish_model_spin(self) -> None:
        self.model_spin_yaw_property.set_base(0.0)
        self.is_showing_update_view = False
        self.update()

    # Asset Resolution

    def resolve_target_asset(self) -> None:
        if not self.pending_release_information:
            return

        assets_list = self.pending_release_information.get("assets", [])

        if not isinstance(assets_list, list):
            return

        compatible_asset = self.find_compatible_asset(assets_list)

        if not compatible_asset:
            logger.warning("No compatible asset found for current platform and architecture.")
            self.update_action_button.setEnabled(False)

            return

        self.download_target_url = str(compatible_asset.get("browser_download_url", ""))
        download_size_bytes      = int(compatible_asset.get("size", 0))

        if download_size_bytes > 0:
            size_in_megabytes = download_size_bytes / (1024.0 * 1024.0)
            self.update_action_button.setText(f"Update now ({size_in_megabytes:.1f} MB)")

    @staticmethod
    def get_platform_asset_filename() -> str:
        platform_name = sys.platform
        machine_name  = platform.machine().lower()
        is_arm        = "arm" in machine_name or "aarch64" in machine_name

        if platform_name == "win32":
            architecture = "arm64" if is_arm else "x64"

            return f"cassette-windows-{architecture}.zip"

        elif platform_name == "darwin":
            architecture = "silicon" if is_arm else "intel"

            return f"cassette-macos-{architecture}.zip"

        architecture = "arm64" if is_arm else "x64"

        return f"cassette-linux-{architecture}.zip"

    def find_compatible_asset(
            self,
            assets: list[dict[str, object]]
        ) -> dict[str, object] | None:

        target_name = self.get_platform_asset_filename()

        for asset in assets:
            asset_filename = str(asset.get("name", "")).lower()

            if asset_filename == target_name:
                return asset

        return None

    # Safety And Verification

    def has_sufficient_disk_space(self) -> bool:
        temporary_directory   = tempfile.gettempdir()
        executable_path       = sys.executable
        application_directory = os.path.dirname(executable_path)

        try:
            temporary_space_bytes   = shutil.disk_usage(temporary_directory).free
            application_space_bytes = shutil.disk_usage(application_directory).free
            one_gigabyte            = 1024 * 1024 * 1024

            if temporary_space_bytes < one_gigabyte:
                return False

            if application_space_bytes < one_gigabyte:
                return False

            return True

        except OSError:
            return False

    def is_safe_application_path(self, target_path: str) -> bool:
        if not target_path:
            return False

        normalized_path = os.path.abspath(target_path)

        if not os.path.isabs(normalized_path):
            return False

        dangerous_directories = {
            "/",
            "/bin",
            "/sbin",
            "/usr",
            "/usr/bin",
            "/usr/local",
            "/etc",
            "/var",
            "/tmp",
            "/home",
            "/root",
            "/Applications"
        }

        if sys.platform == "win32":
            dangerous_directories.update(
                {
                    "c:\\",
                    "c:\\windows",
                    "c:\\program files",
                    "c:\\program files (x86)"
                }
            )

        if normalized_path.lower() in {directory.lower() for directory in dangerous_directories}:
            return False

        user_home_directory = os.path.abspath(os.path.expanduser("~"))

        if normalized_path.lower() == user_home_directory.lower():
            return False

        return True

    def is_directory_writable(self, target_directory: str) -> bool:
        if not os.path.exists(target_directory):
            return False

        return os.access(target_directory, os.W_OK)

    def verify_downloaded_package(self) -> bool:
        if not self.download_file_path:
            return False

        if not os.path.exists(self.download_file_path):
            return False

        if not zipfile.is_zipfile(self.download_file_path):
            return False

        try:
            with zipfile.ZipFile(self.download_file_path, "r") as archive:
                if archive.testzip() is not None:
                    return False

            return True

        except (zipfile.BadZipFile, OSError):
            return False

    def clean_up_temporary_file(self) -> None:
        if not self.download_file_path:
            return

        if not os.path.exists(self.download_file_path):
            return

        try:
            os.remove(self.download_file_path)

        except OSError:
            pass

    # Network Operations

    def start_download(self) -> None:
        if not self.download_target_url:
            self.open_github_release()

            return

        self.is_downloading = True

        self.update_action_button.setEnabled(False)
        self.update_cancel_button.setText("Cancel")

        self.status_label.setText("Connecting to server...")
        self.status_label.setVisible(True)

        self.pulse_status_widget.setVisible(True)
        self.pulse_status_widget.resume_heartbeat()
        self.pulse_status_widget.transition_to_white(duration_ms = 200)
        self.pulse_status_widget.unflatten(duration_ms = 400)
        self.pulse_status_widget.set_mode(Widgets.WaveMode.PULSE)
        self.pulse_status_widget.set_beats_per_minute(60.0, duration_ms = 0)

        self.adjustSize()

        target_file_name        = self.download_target_url.split("/")[-1]
        temporary_directory     = tempfile.gettempdir()
        self.download_file_path = os.path.join(temporary_directory, target_file_name)

        try:
            self.temporary_file = open(self.download_file_path, "wb")

        except OSError as exception:
            logger.error(f"Failed to create temporary update file: {exception}")
            self.handle_download_failure("Failed to create temporary file.")

            return

        request = QNetworkRequest(QUrl(self.download_target_url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy
        )
        request.setRawHeader(b"User-Agent", b"Cassette-Updater")

        self.download_reply = self.network_manager.get(request)
        self.download_reply.downloadProgress.connect(self.handle_download_progress)
        self.download_reply.readyRead.connect(self.handle_data_received)
        self.download_reply.finished.connect(self.handle_download_finished)

    def handle_data_received(self) -> None:
        if not self.download_reply or not self.temporary_file:
            return

        chunk_data = self.download_reply.readAll()

        if chunk_data.isEmpty():
            return

        self.temporary_file.write(chunk_data.data())

    def handle_download_progress(
            self,
            received_bytes: int,
            total_bytes:    int
        ) -> None:

        if total_bytes <= 0:
            return

        self.received_bytes = received_bytes
        self.total_bytes    = total_bytes

        self.download_progress_updated.emit(float(received_bytes), float(total_bytes))

    def update_progress_display(
            self,
            received_bytes: float,
            total_bytes:    float
        ) -> None:

        received_megabytes = received_bytes / (1024.0 * 1024.0)
        total_megabytes    = total_bytes / (1024.0 * 1024.0)
        progress_fraction  = min(1.0, max(0.0, received_bytes / total_bytes))
        progress_percent   = progress_fraction * 100.0

        self.status_label.setText(
            f"Downloading: {received_megabytes:.1f} MB / {total_megabytes:.1f} MB ({progress_percent:.0f}%)"
        )

        current_bpm = 60.0 + (progress_fraction * 90.0)
        self.pulse_status_widget.set_beats_per_minute(current_bpm, duration_ms = 180)

    def handle_download_finished(self) -> None:
        if not self.is_downloading:
            return

        if self.temporary_file:
            self.temporary_file.close()
            self.temporary_file = None

        if not self.download_reply:
            return

        network_error = self.download_reply.error()
        self.download_reply.deleteLater()
        self.download_reply = None

        if network_error == QNetworkReply.NetworkError.OperationCanceledError:
            self.clean_up_temporary_file()

            return

        if network_error != QNetworkReply.NetworkError.NoError:
            self.handle_download_failure("Connection lost during download.")

            return

        if not self.verify_downloaded_package():
            self.handle_download_failure("The downloaded package is corrupted.")

            return

        self.is_downloading      = False
        self.is_ready_to_install = True

        self.status_label.setText("Update package downloaded and verified. Click restart to apply.")
        self.update_action_button.setText("Restart now")
        self.update_action_button.setEnabled(True)
        self.update_cancel_button.setText("Later")

        self.pulse_status_widget.transition_to_sine(150)
        self.pulse_status_widget.set_loading_speed_ratio(0.5, 0)
        self.pulse_status_widget.set_amplitude(4.0, 0)

        QTimer.singleShot(150, lambda: self.pulse_status_widget.set_amplitude(0.0, 500))

        Player.ui_player.play_sound("Alerts/UpdateReady")

    def handle_download_failure(self, error_message: str) -> None:
        self.is_downloading = False

        self.clean_up_temporary_file()

        self.status_label.setText(f"Download failed: {error_message}")
        self.update_action_button.setText("Retry")
        self.update_action_button.setEnabled(True)
        self.update_cancel_button.setText("Close")

        self.pulse_status_widget.transition_to_red(duration_ms = 250)
        self.pulse_status_widget.flatten(duration_ms = 400)
        self.pulse_status_widget.simulate_cardiac_arrest()

        Player.ui_player.play_sound("Alerts/Transmit/Fail")

    def handle_insufficient_disk_space(self) -> None:
        self.status_label.setText("Update blocked: Less than 1 GB of free disk space available.")
        self.status_label.setVisible(True)
        self.update_action_button.setEnabled(False)

        self.pulse_status_widget.setVisible(True)
        self.pulse_status_widget.transition_to_red(duration_ms = 250)
        self.pulse_status_widget.flatten(duration_ms = 400)
        self.pulse_status_widget.simulate_cardiac_arrest()

        Player.ui_player.play_sound("Alerts/Transmit/Fail")

        ErrorWindow(
            "Insufficient Disk Space",
            "At least 1 GB of free disk space is required on both the temporary and installation drives to update.\nAutomatic update has been canceled.",
            "Go delete ya files"
        ).exec()

    def handle_permission_denied(self) -> None:
        self.status_label.setText("Update blocked: No write permission in the application directory.")
        self.status_label.setVisible(True)
        self.update_action_button.setEnabled(False)

        self.pulse_status_widget.setVisible(True)
        self.pulse_status_widget.transition_to_red(duration_ms = 250)
        self.pulse_status_widget.flatten(duration_ms = 400)
        self.pulse_status_widget.simulate_cardiac_arrest()

        Player.ui_player.play_sound("Alerts/Transmit/Fail")

        ErrorWindow(
            "Write Permission Denied",
            "Cassette cannot write to its installation folder.\nPlease run as administrator or download and install the update manually.",
            "Ow"
        ).exec()

    def cancel_download(self) -> None:
        if self.download_reply:
            try:
                self.download_reply.finished.disconnect(self.handle_download_finished)
                self.download_reply.readyRead.disconnect(self.handle_data_received)
                self.download_reply.downloadProgress.disconnect(self.handle_download_progress)

            except (TypeError, RuntimeError):
                pass

            self.download_reply.abort()
            self.download_reply.deleteLater()
            self.download_reply = None

        if self.temporary_file:
            self.temporary_file.close()
            self.temporary_file = None

        self.clean_up_temporary_file()

        self.is_downloading = False
        self.update_action_button.setEnabled(True)
        self.update_cancel_button.setText("Later")

    # Installation And Restart

    def apply_update_and_restart(self) -> None:
        if not getattr(sys, "frozen", False):
            logger.warning("Running from Python source code. Binary replacement skipped.")
            self.on_ok()

            return

        if not self.verify_downloaded_package():
            self.handle_download_failure("The downloaded package is corrupted.")

            return

        executable_path       = sys.executable
        process_identifier    = os.getpid()
        temporary_folder      = tempfile.gettempdir()
        application_directory = os.path.dirname(executable_path)

        if not self.is_safe_application_path(application_directory):
            logger.critical("Unsafe application directory detected. Update aborted to prevent system damage.")
            self.handle_download_failure("Refused to update: Unsafe target directory.")

            return

        if sys.platform == "win32":
            script_path    = os.path.join(temporary_folder, "cassette_updater.bat")
            script_content = f"""@echo off
chcp 65001 > nul
:wait_process
tasklist /fi "PID eq {process_identifier}" | find ":" > nul
if errorlevel 1 (
    timeout /t 1 /nobreak > nul
    goto wait_process
)
if not exist "{application_directory}" goto cleanup
tar -xf "{self.download_file_path}" -C "{application_directory}" || powershell -Command "Expand-Archive -Force -Path '{self.download_file_path}' -DestinationPath '{application_directory}'"
start "" "{executable_path}"
:cleanup
del "{self.download_file_path}"
del "%~f0"
"""
            with open(script_path, "w", encoding = "utf-8") as script_file:
                script_file.write(script_content)

            subprocess.Popen(
                ["cmd.exe", "/c", script_path],
                creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )

        elif sys.platform == "darwin":
            bundle_directory = os.path.abspath(os.path.join(application_directory, "../../.."))
            parent_directory = os.path.dirname(bundle_directory)

            if not bundle_directory.endswith(".app") or not self.is_safe_application_path(bundle_directory):
                logger.critical("Unsafe bundle directory on macOS. Aborting update.")
                self.handle_download_failure("Refused to update: Unsafe bundle directory.")

                return

            script_path    = os.path.join(temporary_folder, "cassette_updater.sh")
            script_content = f"""#!/bin/sh
while kill -0 {process_identifier} 2>/dev/null; do
    sleep 0.5
done
if [ -d "{bundle_directory}" ] && [ "{bundle_directory}" != "/" ] && [ "{bundle_directory}" != "/Applications" ]; then
    rm -rf "{bundle_directory}"
fi
unzip -o "{self.download_file_path}" -d "{parent_directory}"
xattr -cr "{bundle_directory}"
open "{bundle_directory}"
rm -f "{self.download_file_path}"
rm -f "$0"
"""
            with open(script_path, "w", encoding = "utf-8") as script_file:
                script_file.write(script_content)

            os.chmod(script_path, 0o755)
            subprocess.Popen(["/bin/sh", script_path], start_new_session = True)

        else:
            if not self.is_safe_application_path(application_directory):
                logger.critical("Unsafe Linux directory. Aborting update.")
                self.handle_download_failure("Refused to update: Unsafe target directory.")

                return

            script_path    = os.path.join(temporary_folder, "cassette_updater.sh")
            script_content = f"""#!/bin/sh
while kill -0 {process_identifier} 2>/dev/null; do
    sleep 0.5
done
if [ -d "{application_directory}" ] && [ "{application_directory}" != "/" ] && [ "{application_directory}" != "$HOME" ]; then
    unzip -o "{self.download_file_path}" -d "{application_directory}"
    chmod +x "{executable_path}"
    "{executable_path}" &
fi
rm -f "{self.download_file_path}"
rm -f "$0"
"""
            with open(script_path, "w", encoding = "utf-8") as script_file:
                script_file.write(script_content)

            os.chmod(script_path, 0o755)
            subprocess.Popen(["/bin/sh", script_path], start_new_session = True)

        application = QApplication.instance()

        if application:
            application.quit()

        sys.exit(0)

    # Event Handlers

    def handle_action_clicked(self) -> None:
        if self.is_ready_to_install:
            self.apply_update_and_restart()

            return

        if not self.has_sufficient_disk_space():
            self.handle_insufficient_disk_space()

            return

        executable_path       = sys.executable
        application_directory = os.path.dirname(executable_path)

        if getattr(sys, "frozen", False):
            if not self.is_safe_application_path(application_directory):
                self.handle_download_failure("Refused to update: Unsafe target directory.")

                return

            if not self.is_directory_writable(application_directory):
                self.handle_permission_denied()

                return

        self.start_download()

    def handle_cancel_clicked(self) -> None:
        if self.is_showing_update_view:
            self.start_reverse_transition_to_about()

            return

        if self.is_downloading:
            self.cancel_download()

        self.on_cancel()

    def open_github_release(self) -> None:
        webbrowser.open(self.pending_release_url)

    # Text Formatting

    @staticmethod
    def format_changelog_text(changelog: str) -> str:
        changelog = re.sub(r"(?m)^### \*\*Cassette v\d+\.\d+\.\d+\*\*\s*\r?\n", "",      changelog)
        changelog = re.sub(r"(?m)^>\s*(.*?)\s*$",                               r"`\1`", changelog)
        changelog = re.sub(r"### \*\*(.*?)\*\*",                                r"`\1`", changelog)
        changelog = re.sub(r"\*\*(.*?)\*\*",                                    r"`\1`", changelog)
        changelog = re.sub(r"(?m)^-\s+",                                        "`•` ",  changelog)
        changelog = changelog.strip()

        return changelog