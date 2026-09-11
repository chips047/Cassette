import numpy

from OpenGL    import GL
from OpenGL.GL import shaders

from PyQt6.QtCore import (
    QObject,
    QElapsedTimer
)

from PyQt6.QtGui import QWheelEvent

from System.Common import (
    Dev,
    Utils,
    Constants
)

from System.Interface import Timing

from System.Interface.Animation import LoomEngine

from System.Interface.Windows import FloatingWindowGPU

# GlyphVisualizer

@Dev.track_ram
class GlyphVisualizer(FloatingWindowGPU):
    def __init__(
            self,
            parent: QObject | None,
            model:  str
        ) -> None:

        super().__init__(
            None,
            parent                  = parent,
            margin                  = 50,
            max_tilt_angle          = 9,
            stays_on_top            = True,
            enable_open_animation   = False,
            enable_close_animation  = False
        )

        self.parent                     = parent
        self.device                     = Constants.DEVICES[model]
        self.map_data                   = self.device.visualization_map
        self.map_width, self.map_height = self.map_data["size"]

        self.visual_scale               = 1.0
        self.target_scale               = 1.0
        self.scale_smoothing            = 0.15

        self.glyphs_gpu                 = []
        self.total_segments             = 0

        self.is_playing                 = False
        self.last_scrubbed_ms           = 0

        self.initialize_geometry()
        self.scale_in()
        self.sync_size_delayed()

    # Setup

    def setup_timers(self) -> None:
        super().setup_timers()

        self.resize_timer = Timing.Timer(
            200,
            self.sync_size_delayed,
            single_shot = True,
            parent      = self
        )

        self.timer = Timing.Timer(
            Constants.FPS_30,
            self.process_schedule,
            parent = self
        )

        self.elapsed = QElapsedTimer()

    def initialize_geometry(self) -> None:
        current_global_offset = 0

        for glyph_identifier, data in self.map_data["glyphs"].items():
            glyph = self.process_single_glyph(glyph_identifier, data, current_global_offset)
            self.glyphs_gpu.append(glyph)

            current_global_offset += glyph["segment_count"]

        self.total_segments = current_global_offset
        self.global_levels  = numpy.zeros(self.total_segments, dtype = numpy.float32)

    def initialize_shared_buffer(self) -> None:
        self.levels_texture = GL.glGenTextures(1)

        GL.glBindTexture(GL.GL_TEXTURE_1D, self.levels_texture)
        GL.glTexImage1D(GL.GL_TEXTURE_1D, 0, GL.GL_R32F, self.total_segments, 0, GL.GL_RED, GL.GL_FLOAT, None)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_WRAP_S,     GL.GL_CLAMP_TO_EDGE)

    def process_single_glyph(
            self,
            glyph_identifier: str,
            data:             dict,
            global_offset:    int
        ) -> dict:

        path                   = Utils.parse_svg_path_data(data["svg"])
        segment_count          = data.get("segments", 1)
        position_x, position_y = data["position"]
        points_per_segment     = 60

        total_length   = path.length()
        segment_length = total_length / segment_count

        all_vertices          = []
        starts                = []
        counts                = []
        current_buffer_offset = 0

        for segment_index in range(segment_count):
            start_distance = segment_index * segment_length
            end_distance   = (segment_index + 1) * segment_length

            points = []

            for point_index in range(points_per_segment):
                distance = start_distance + (point_index / (points_per_segment - 1)) * (end_distance - start_distance)
                progress = path.percentAtLength(distance)
                point    = path.pointAtPercent(progress)

                points.append(
                    [
                        point.x() + position_x - self.map_width / 2,
                        -(point.y() + position_y) + self.map_height / 2
                    ]
                )

            points           = numpy.array(points, dtype = numpy.float32)
            segment_vertices = self.calculate_segment_geometry(points, global_offset + segment_index)

            all_vertices.append(segment_vertices)
            vertices_count = len(segment_vertices) // 5

            starts.append(current_buffer_offset)
            counts.append(vertices_count)

            current_buffer_offset += vertices_count

        return {
            "id":                glyph_identifier,
            "vbo_data":          numpy.concatenate(all_vertices).astype(numpy.float32),
            "starts":            numpy.array(starts, dtype = numpy.int32),
            "counts":            numpy.array(counts, dtype = numpy.int32),
            "segment_count":     segment_count,
            "global_base_index": global_offset,
            "schedule":          []
        }

    def calculate_segment_geometry(
            self,
            points:       numpy.ndarray,
            global_index: int
        ) -> numpy.ndarray:

        differences = numpy.diff(points, axis = 0)
        tangents    = numpy.vstack([differences, differences[-1:]])
        normals     = numpy.stack([-tangents[:, 1], tangents[:, 0]], axis = 1)
        lengths     = numpy.linalg.norm(normals, axis = 1, keepdims = True)
        normals    /= numpy.where(lengths == 0, 1.0, lengths)

        index_float = float(global_index)
        result      = numpy.zeros((len(points) * 2, 5), dtype = numpy.float32)

        for point_index, (point, normal) in enumerate(zip(points, normals)):
            result[point_index * 2]     = [point[0], point[1],  normal[0],  normal[1], index_float]
            result[point_index * 2 + 1] = [point[0], point[1], -normal[0], -normal[1], index_float]

        return result.flatten()

    # Render

    def initializeGL(self) -> None:
        super().initializeGL()

        self.initialize_shared_buffer()

        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE)

        self.shader_program = shaders.compileProgram(
            shaders.compileShader(Constants.GLYPH_VERTEX_SHADER,   GL.GL_VERTEX_SHADER),
            shaders.compileShader(Constants.GLYPH_FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        )

        self.uniform_locations = {
            "mvp":        GL.glGetUniformLocation(self.shader_program, "mvp"),
            "thickness":  GL.glGetUniformLocation(self.shader_program, "uThickness"),
            "levels_tex": GL.glGetUniformLocation(self.shader_program, "uLevelsTex")
        }

        for glyph in self.glyphs_gpu:
            glyph["vao"] = GL.glGenVertexArrays(1)
            glyph["vbo"] = GL.glGenBuffers(1)

            GL.glBindVertexArray(glyph["vao"])
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, glyph["vbo"])
            GL.glBufferData(GL.GL_ARRAY_BUFFER, glyph["vbo_data"].nbytes, glyph["vbo_data"], GL.GL_STATIC_DRAW)

            stride = 20

            for attribute_index, size, offset in [(0, 2, 0), (1, 2, 8), (2, 1, 16)]:
                GL.glVertexAttribPointer(attribute_index, size, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(offset))
                GL.glEnableVertexAttribArray(attribute_index)

    def paintGL(self) -> None:
        super().paintGL()

        GL.glUseProgram(self.shader_program)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_1D, self.levels_texture)
        GL.glTexSubImage1D(GL.GL_TEXTURE_1D, 0, 0, self.total_segments, GL.GL_RED, GL.GL_FLOAT, self.global_levels)
        GL.glUniform1i(self.uniform_locations["levels_tex"], 0)

        mvp = self.calculate_matrix(2.0, 2.0)
        mvp.scale(self.visual_scale, self.visual_scale, 1.0)

        GL.glUniformMatrix4fv(self.uniform_locations["mvp"], 1, GL.GL_FALSE, mvp.data())
        GL.glUniform1f(self.uniform_locations["thickness"], float(self.map_data.get("thickness", 2.2)))

        for glyph in self.glyphs_gpu:
            GL.glBindVertexArray(glyph["vao"])
            GL.glMultiDrawArrays(GL.GL_TRIANGLE_STRIP, glyph["starts"], glyph["counts"], len(glyph["starts"]))

    # Animations

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

    # Schedule

    def set_schedule(self, schedule_dict: dict) -> None:
        resolved = {}

        for display_track, items in schedule_dict.items():
            for real_track, real_items in self.expand_display_track_items(display_track, items).items():
                resolved.setdefault(real_track, {}).update(real_items)

        for glyph in self.glyphs_gpu:
            glyph["schedule"] = list(resolved.get(glyph["id"], {}).values())

    def expand_display_track_items(
            self,
            display_track: str,
            items:         dict
        ) -> dict:

        if display_track != Constants.MASTER_TRACK_IDENTIFIER and not self.device.is_segment_track(display_track):
            return {display_track: items}

        expanded = {}

        for key, item in items.items():
            for real_track, real_segments in self.device.expand_display_track(display_track, item.get("segments")):
                item_copy = dict(item)

                if real_segments is None:
                    item_copy.pop("segments", None)

                else:
                    item_copy["segments"] = real_segments

                expanded.setdefault(real_track, {})[f"{key}:{real_track}"] = item_copy

        return expanded

    # Playback

    def play_all(self, ms_start: int = 0) -> None:
        self.is_playing        = True
        self.virtual_time      = ms_start
        self.last_process_time = 0

        self.elapsed.start()
        self.timer.start()

    def stop_all(self) -> None:
        self.is_playing = False

        self.timer.stop()
        self.virtual_time      = 0
        self.last_process_time = 0

        self.update()

    def update_levels_for_time(self, now_ms: float) -> None:
        self.global_levels.fill(0)

        for glyph in self.glyphs_gpu:
            base_index = glyph["global_base_index"]

            for item in glyph["schedule"]:
                if not (item["start"] <= now_ms <= item["start"] + item["duration"]):
                    continue

                brightness = self.get_item_brightness(item, now_ms)
                target     = self.get_target_slice(item, base_index, glyph["segment_count"])

                self.global_levels[target] = numpy.maximum(self.global_levels[target], brightness)

    def on_playhead_scrubbed(self, position_ms: float) -> None:
        if self.is_playing:
            return

        if abs(position_ms - self.last_scrubbed_ms) < 1:
            return

        self.last_scrubbed_ms = position_ms
        self.update_levels_for_time(position_ms)
        self.update()

    def on_visualizator_data_changed(self) -> None:
        if self.is_playing or not self.parent:
            return

        composition = getattr(self.parent, "composition", None)

        if not composition:
            return

        self.set_schedule(composition.glyphs.visualizator_data)
        self.update_levels_for_time(self.last_scrubbed_ms)
        self.update()

    def update_visual_scale(self) -> None:
        if abs(self.target_scale - self.visual_scale) > 0.001:
            self.visual_scale += (self.target_scale - self.visual_scale) * self.scale_smoothing
            self.update()

        else:
            self.visual_scale = self.target_scale

    def get_item_brightness(
            self,
            item:   dict,
            now_ms: float
        ) -> float:

        if "keyframes" in item:
            start_ms    = item["start"]
            duration_ms = item["duration"]
            progress    = (now_ms - start_ms) / duration_ms if duration_ms > 0 else 1.0

            easing_name = item.get("easing", "linear")
            easing_func = Constants.VISUAL_EASINGS.get(easing_name, Constants.VISUAL_EASINGS["linear"])

            return self.interpolate_keyframes(item["keyframes"], progress, easing_func)

        return float(item["brightness"])

    def get_target_slice(
            self,
            item:          dict,
            base_index:    int,
            segment_count: int
        ) -> slice | numpy.ndarray:

        if "segments" in item:
            return base_index + numpy.array(item["segments"])

        return slice(base_index, base_index + segment_count)

    def process_schedule(self) -> None:
        real_elapsed            = self.elapsed.elapsed()
        self.virtual_time      += (real_elapsed - self.last_process_time) * self.player.speed
        self.last_process_time  = real_elapsed

        now_ms = self.virtual_time
        self.global_levels.fill(0)

        for glyph in self.glyphs_gpu:
            base_index = glyph["global_base_index"]

            for item in glyph["schedule"]:
                if not (item["start"] <= now_ms <= item["start"] + item["duration"]):
                    continue

                brightness = self.get_item_brightness(item, now_ms)
                target     = self.get_target_slice(item, base_index, glyph["segment_count"])

                self.global_levels[target] = numpy.maximum(self.global_levels[target], brightness)

        self.update()

    def interpolate_keyframes(
            self,
            keyframes:       list[tuple[float, float]],
            progress:        float,
            easing_function: object
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

            return value_start + (value_end - value_start) * easing_function(local_progress)

        return float(keyframes[-1][1])

    # Events

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta             = 0.07 if event.angleDelta().y() > 0 else -0.07
        self.target_scale = numpy.clip(self.target_scale + delta, 0.3, 4.0)
        self.visual_scale = self.target_scale

        self.resize_timer.start()
        self.update()

    # Utilities

    def sync_size_delayed(self) -> None:
        new_width  = int(self.map_width * self.target_scale) + 80
        new_height = int(self.map_height * self.target_scale) + 80

        self.animate_resize(new_width, new_height)

    def exit(self, cleanup: bool = True) -> None:
        self.allow_exit = True
        self.stop_all()
        self.resize_timer.stop()
        self.scale_out(cleanup)