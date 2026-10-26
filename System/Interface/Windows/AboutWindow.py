from __future__ import annotations

import os
import sys
import json
import math
import time
import numpy
import struct
import random
import platform
import webbrowser

from OpenGL import GL
from OpenGL.GL import shaders

from PyQt6.QtCore import (
    Qt,
    QTimer,
    pyqtSignal
)

from PyQt6.QtGui import (
    QColor,
    QImage,
    QVector3D,
    QMatrix4x4,
    QMouseEvent,
    QPaintEvent
)

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QStackedLayout
)

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Interface import Widgets
from System.Interface.Animation import LoomEngine

from System.Services import Haptics

from System.Interface.Windows import (
    ErrorWindow,
    UpdateWindow,
    FloatingWindowGPU
)

from System.Interface.Windows.FeedbackWindow import (
    FeedbackWindow,
    SETTING_FEEDBACK_RATING_KEY
)

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

        self.window_reference       = window
        self.manual_yaw             = 0.0
        self.manual_pitch           = 0.0
        self.target_manual_yaw      = 0.0
        self.target_manual_pitch    = 0.0
        self.is_mouse_pressed       = False
        self.drag_start_position    = None
        self.haptic_accumulator     = 0.0

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
    def __init__(
            self,
            more_information: bool           = False,
            parent:           QWidget | None = None
        ) -> None:

        with open(Utils.get_resource_path("version"), "r", encoding = "utf-8") as version_file:
            version_text = version_file.read().strip()

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
        self.model_drag_duration_ms          = 0.0
        self.model_drag_started_at           = None
        self.model_rotation_easter_egg_shown = bool(Constants.current_settings.get("_about_model_rotated_seen", False))

        self.model_drag_timer = QTimer(self)
        self.model_drag_timer.setInterval(250)
        self.model_drag_timer.timeout.connect(self.check_model_rotation_easter_egg)

        self.model_location_projection           = -1
        self.model_location_view                 = -1
        self.model_location_model                = -1
        self.model_location_camera_position      = -1
        self.model_location_accent_color         = -1
        self.model_location_button_light         = -1
        self.model_location_global_alpha         = -1

        self.location_sampler_base_color         = -1
        self.location_sampler_normal             = -1
        self.location_sampler_metallic_roughness = -1
        self.location_sampler_emissive           = -1

        self.location_has_base_color             = -1
        self.location_has_normal                 = -1
        self.location_has_metallic_roughness     = -1
        self.location_has_emissive               = -1

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

        self.text_container = QWidget(self)
        self.text_container.setFixedWidth(500)
        self.text_container.setFixedHeight(maximum_height)

        self.text_layout = QStackedLayout(self.text_container)
        self.text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.text_layout.addWidget(self.about_label)
        self.text_layout.addWidget(self.credits_label)
        self.text_layout.setAlignment(self.about_label, Qt.AlignmentFlag.AlignTop)
        self.text_layout.setAlignment(self.credits_label, Qt.AlignmentFlag.AlignTop)

        cassette_path = Utils.get_resource_path("System/Assets/3D/Cassette.glb")
        self.load_model_data(cassette_path)

        self.cassette_canvas = CassetteCanvasWidget(self)
        self.cassette_canvas.model_dragged.connect(self.on_model_dragged)
        self.cassette_canvas.model_drag_ended.connect(self.on_model_drag_ended)

        self.content_layout.addWidget(self.text_container)
        self.content_layout.addWidget(self.cassette_canvas)

        self.button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "GitHub",        self.on_github),
                (Widgets.ButtonWithOutline, "Feedback",      self.on_feedback),
                (Widgets.ButtonWithOutline, "Check updates", self.on_check_updates),
                (Widgets.ButtonWithOutline, "Credits",       self.on_credits)
            ], button_width = 100
        )

        self.five_stars_button = Widgets.NothingButton("Five Stars?")
        saved_rating = Constants.current_settings.get(SETTING_FEEDBACK_RATING_KEY)
        rating_texts = Constants.CLOSE_BUTTON_RATING_TEXTS.get(saved_rating, []) if isinstance(saved_rating, int) else []

        if rating_texts:
            self.five_stars_button.setText(random.choice(rating_texts))

        self.five_stars_button.clicked.connect(self.on_ok)

        self.content_layout.addLayout(self.button_row)
        self.content_layout.addWidget(self.five_stars_button)

        self.setup_window_animations()

    def on_model_dragged(self) -> None:
        if self.model_rotation_easter_egg_shown or self.model_drag_started_at is not None:
            return

        self.model_drag_started_at = time.perf_counter()
        self.model_drag_timer.start()

    def on_model_drag_ended(self) -> None:
        if self.model_drag_started_at is None:
            return

        self.model_drag_duration_ms += (time.perf_counter() - self.model_drag_started_at) * 1000.0
        self.model_drag_started_at = None
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

        self.model_rotation_easter_egg_shown = True
        self.model_drag_timer.stop()
        self.cassette_canvas.is_mouse_pressed = False
        self.cassette_canvas.drag_start_position = None
        self.cassette_canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        Constants.current_settings.set_value("_about_model_rotated_seen", True)
        ErrorWindow(
            "Ahem...",
            "As I see, you like it very much.",
            parent = self
        ).exec()

    # Animation Setup

    def setup_window_animations(self) -> None:
        self.cassette_yaw_property = LoomEngine.ui_engine.bind(
            owner      = self,
            name       = "cassette_yaw",
            base_value = 0.0,
            mix_mode   = LoomEngine.MixMode.REPLACE,
            on_change  = self.on_model_yaw_changed
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

    def on_model_yaw_changed(self, value: object) -> None:
        self.model_yaw_offset = float(value)
        self.update()

    def on_about_opacity_changed(self, value: object) -> None:
        opacity_value = float(value)
        self.about_label.setProperty("paint_opacity", opacity_value)
        self.about_label.update()

    def on_credits_opacity_changed(self, value: object) -> None:
        opacity_value = float(value)
        self.credits_label.setProperty("paint_opacity", opacity_value)
        self.credits_label.update()

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
                    material_information            = parsed_json["materials"][material_index]
                    material_pbr_information        = material_information.get("pbrMetallicRoughness", {})

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

        vertex_shader   = shaders.compileShader(Constants.CASSETTE_VERTEX_SHADER_SOURCE,   GL.GL_VERTEX_SHADER)
        fragment_shader = shaders.compileShader(Constants.CASSETTE_FRAGMENT_SHADER_SOURCE, GL.GL_FRAGMENT_SHADER)

        self.cassette_shader_program = shaders.compileProgram(vertex_shader, fragment_shader)

        self.model_location_projection           = GL.glGetUniformLocation(self.cassette_shader_program, "projection_matrix")
        self.model_location_view                 = GL.glGetUniformLocation(self.cassette_shader_program, "view_matrix")
        self.model_location_model                = GL.glGetUniformLocation(self.cassette_shader_program, "model_matrix")
        self.model_location_camera_position      = GL.glGetUniformLocation(self.cassette_shader_program, "camera_position")
        self.model_location_accent_color         = GL.glGetUniformLocation(self.cassette_shader_program, "accent_color")
        self.model_location_button_light         = GL.glGetUniformLocation(self.cassette_shader_program, "button_light_position")
        self.model_location_global_alpha         = GL.glGetUniformLocation(self.cassette_shader_program, "global_alpha")

        self.location_sampler_base_color         = GL.glGetUniformLocation(self.cassette_shader_program, "base_color_sampler")
        self.location_sampler_normal             = GL.glGetUniformLocation(self.cassette_shader_program, "normal_sampler")
        self.location_sampler_metallic_roughness = GL.glGetUniformLocation(self.cassette_shader_program, "metallic_roughness_sampler")
        self.location_sampler_emissive           = GL.glGetUniformLocation(self.cassette_shader_program, "emissive_sampler")

        self.location_has_base_color             = GL.glGetUniformLocation(self.cassette_shader_program, "has_base_color_texture")
        self.location_has_normal                 = GL.glGetUniformLocation(self.cassette_shader_program, "has_normal_texture")
        self.location_has_metallic_roughness     = GL.glGetUniformLocation(self.cassette_shader_program, "has_metallic_roughness_texture")
        self.location_has_emissive               = GL.glGetUniformLocation(self.cassette_shader_program, "has_emissive_texture")

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
        model_scale           = target_model_width_px * units_per_pixel

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

        current_time_sec = float(time.perf_counter())
        idle_sway_y      = math.sin(current_time_sec * 1.2) * 2.0
        idle_sway_x      = math.cos(current_time_sec * 0.9) * 1.2

        smoothing_factor = 0.08

        if self.cassette_canvas.is_mouse_pressed:
            self.cassette_canvas.manual_yaw   += (self.cassette_canvas.target_manual_yaw - self.cassette_canvas.manual_yaw)     * smoothing_factor
            self.cassette_canvas.manual_pitch += (self.cassette_canvas.target_manual_pitch - self.cassette_canvas.manual_pitch) * smoothing_factor

        else:
            self.cassette_canvas.target_manual_yaw   *= 0.92
            self.cassette_canvas.target_manual_pitch *= 0.92
            self.cassette_canvas.manual_yaw          += (0.0 - self.cassette_canvas.manual_yaw)   * smoothing_factor
            self.cassette_canvas.manual_pitch        += (0.0 - self.cassette_canvas.manual_pitch) * smoothing_factor

        model_matrix = QMatrix4x4()
        model_matrix.translate(model_offset_x, model_offset_y, 0.0)
        model_matrix.rotate(-tilt_x * 1.2 + idle_sway_x + self.cassette_canvas.manual_pitch, 1.0, 0.0, 0.0)
        model_matrix.rotate(
            tilt_y * 1.2 + idle_sway_y + self.cassette_canvas.manual_yaw + self.model_yaw_offset,
            0.0, 1.0, 0.0
        )
        model_matrix.rotate(tilt_z * 1.2, 0.0, 0.0, 1.0)
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
        button = self.button_row.get_button_by_number(2)

        if button is not None:
            button.setEnabled(False)
            button.setText("Checking...")

        self.update_checker = Utils.UpdateChecker()
        self.update_checker.resource_loaded.connect(self.on_update_info_received)
        self.update_checker.error_occurred.connect(self.on_update_check_failed)
        self.update_checker.fetch_latest_release()

    # Update Handlers

    def on_update_info_received(
            self,
            resource_identifier: str,
            release_information: dict
        ) -> None:

        if resource_identifier != "release" or not isinstance(release_information, dict):
            return

        button = self.button_row.get_button_by_number(2)

        if button is not None:
            button.setEnabled(True)
            button.setText("Check updates")

        remote_tag = str(release_information.get("tag_name", ""))

        with open(Utils.get_resource_path("version"), "r", encoding = "utf-8") as version_file:
            local_version = version_file.read().strip()

        if Utils.is_newer_version(remote_tag, local_version):
            window = UpdateWindow(
                version             = remote_tag,
                changelog           = str(release_information.get("body", "")),
                url                 = str(release_information.get("html_url", Constants.GITHUB_LINK)),
                release_information = release_information,
                parent              = self.parent()
            )
            window.exec()
            return

        button.setText("Latest version")

    def on_update_check_failed(self, request_type: str) -> None:
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