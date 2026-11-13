from __future__ import annotations

import math

from enum import Enum

from loguru import logger

from dataclasses import (
    field,
    dataclass
)

MASTER_TRACK_IDENTIFIER = "A"

# Modes

class MasterTrackMode(Enum):
    ALL_LIT      = "all_lit"
    MERGED_ZONES = "merged_zones"
    MIRROR_ZONES = "mirror_zones"
    MATRIX       = "matrix"

# Device Configuration

@dataclass
class DeviceConfig:
    code_name:             str
    short_name:            str
    full_name:             str
    hardware_codes:        list[str]
    composer_code_name:    str

    glyph_indexes:         list[list[int]] = field(default_factory = list)
    zone_indexes:          list[list[int]] = field(default_factory = list)
    segments_map:          dict[str, int]  = field(default_factory = dict)

    visualization_map:     dict            = field(default_factory = dict)
    port_variants:         list[str]       = field(default_factory = list)
    port_map:              dict            = field(default_factory = dict)

    matrix_rows:           list[int]       = field(default_factory = list)

    columns:               int             = field(init = False)
    base_tracks:           int             = field(init = False)
    custom_two_string:     str             = field(init = False)

    master_track_mode:     MasterTrackMode = field(init = False)
    master_track_segments: int | None      = field(init = False)

    legacy_tracks: dict[int, dict[str, list[str]]] = field(default_factory = dict)

    matrix_led_coordinates:    list[tuple[float, float]] = field(init = False, default_factory = list)
    matrix_led_to_row_segment: list[tuple[str, int]]     = field(init = False, default_factory = list)

    def __post_init__(self) -> None:
        if self.matrix_rows:
            self.glyph_indexes = make_ranges(*self.matrix_rows)
            total_matrix_leds  = sum(self.matrix_rows)
            self.zone_indexes  = [[index] for index in range(total_matrix_leds)]
            self.segments_map  = {
                str(row_index + 1): count
                for row_index, count in enumerate(self.matrix_rows)
            }

            self.build_matrix_geometry()

        self.columns               = sum(len(group) for group in self.glyph_indexes)
        self.base_tracks           = len(self.glyph_indexes)
        self.custom_two_string     = f"{self.columns}cols"
        self.master_track_mode     = self.compute_master_track_mode()
        self.master_track_segments = self.compute_master_track_segments()

        logger.info(f"\n\nModel {self.full_name}")
        logger.debug(f"Total columns (Glyphs + Segments): {self.columns}")
        logger.debug(f"Base Tracks: {self.base_tracks}")
        logger.debug(f"Hardware: {self.hardware_codes[0]}")
        logger.debug(f"Glyph Indexes: {self.glyph_indexes}")
        logger.debug(f"Zone Indexes: {self.zone_indexes}")
        logger.debug(f"Master Track Mode: {self.master_track_mode} ({self.master_track_segments} zones)")

    # Matrix Geometry

    def build_matrix_geometry(self) -> None:
        row_count       = len(self.matrix_rows)
        maximum_columns = max(self.matrix_rows)
        radius_x        = (maximum_columns - 1) / 2.0 if maximum_columns > 1 else 1.0
        radius_y        = (row_count - 1) / 2.0 if row_count > 1 else 1.0

        coordinates: list[tuple[float, float]] = []
        mapping:     list[tuple[str, int]]     = []

        for row_index, row_width in enumerate(self.matrix_rows):
            start_column = (maximum_columns - row_width) // 2
            row_track    = str(row_index + 1)
            y_normalized = (row_index - radius_y) / radius_y

            for segment_index in range(row_width):
                column_index = start_column + segment_index
                x_normalized = (column_index - radius_x) / radius_x

                coordinates.append((round(x_normalized, 4), round(y_normalized, 4)))
                mapping.append((row_track, segment_index))

        self.matrix_led_coordinates    = coordinates
        self.matrix_led_to_row_segment = mapping

    @property
    def is_matrix(self) -> bool:
        return bool(self.matrix_rows)

    def calculate_zone_offset(
            self,
            glyph_index: int
        ) -> int:

        if not self.segments_map:
            return 0

        offset = 0

        for position_string, segment_count in sorted(self.segments_map.items()):
            if glyph_index < int(position_string):
                continue

            offset += (segment_count - 1)

        return offset

    @property
    def total_tracks(self) -> int:
        return self.base_tracks

    @property
    def total_tracks_with_segments(self) -> int:
        return sum(
            self.segments_map.get(str(track_number), 1)
            for track_number in range(1, self.base_tracks + 1)
        )

    @property
    def track_names(self) -> list[str]:
        if self.master_track_mode is MasterTrackMode.MIRROR_ZONES:
            return [MASTER_TRACK_IDENTIFIER] + [str(index) for index in range(1, self.master_track_segments + 1)]

        return [MASTER_TRACK_IDENTIFIER] + [str(index) for index in range(1, self.base_tracks + 1)]

    def compute_master_track_mode(self) -> MasterTrackMode:
        if self.is_matrix:
            return MasterTrackMode.MATRIX

        if self.base_tracks == 1 and "1" in self.segments_map:
            return MasterTrackMode.MIRROR_ZONES

        all_base_tracks_segmented = all(
            str(index) in self.segments_map
            for index in range(1, self.base_tracks + 1)
        )

        if self.base_tracks > 1 and all_base_tracks_segmented:
            return MasterTrackMode.MERGED_ZONES

        return MasterTrackMode.ALL_LIT

    def compute_master_track_segments(self) -> int | None:
        if self.master_track_mode is MasterTrackMode.MATRIX:
            return self.columns

        if self.master_track_mode is MasterTrackMode.MIRROR_ZONES:
            return self.segments_map["1"]

        if self.master_track_mode is MasterTrackMode.MERGED_ZONES:
            return self.total_tracks_with_segments

        return None

    def is_master_track(self, track: str) -> bool:
        return track == MASTER_TRACK_IDENTIFIER

    def is_segment_track(self, track: str) -> bool:
        return (
            self.master_track_mode is MasterTrackMode.MIRROR_ZONES and
            not self.is_master_track(track)
        )

    def resolve_segment_track(self, track: str) -> tuple[str, int]:
        if not self.is_segment_track(track):
            raise ValueError(f"'{track}' is not a segment track for {self.full_name}")

        return "1", int(track) - 1

    def get_track_segment_count(self, track: str) -> int | None:
        if self.is_master_track(track):
            return self.master_track_segments

        if self.is_segment_track(track):
            if self.base_tracks == 1:
                return self.master_track_segments

            return None

        return self.segments_map.get(track)

    def can_edit_track_segments(self, track: str) -> bool:
        return bool(self.get_track_segment_count(track))

    def resolve_master_zone(self, zone_index: int) -> tuple[str, int]:
        if self.master_track_mode is MasterTrackMode.MIRROR_ZONES:
            return "1", zone_index

        if self.master_track_mode is not MasterTrackMode.MERGED_ZONES:
            raise ValueError(f"{self.full_name} has no zone-mapped master track (mode is {self.master_track_mode})")

        offset = 0

        for index in range(1, self.base_tracks + 1):
            track          = str(index)
            track_segments = self.segments_map[track]

            if zone_index < offset + track_segments:
                return track, zone_index - offset

            offset += track_segments

        raise IndexError(f"Master zone index {zone_index} is out of range for {self.full_name}")

    def resolve_master_track(self) -> list[tuple[str, int | None]]:
        if self.master_track_mode in (MasterTrackMode.ALL_LIT, MasterTrackMode.MATRIX):
            return [(str(index), None) for index in range(1, self.base_tracks + 1)]

        return [
            self.resolve_master_zone(zone_index)
            for zone_index in range(self.master_track_segments)
        ]

    def is_full_track_segments(
            self,
            track:    str,
            segments: list[int]
        ) -> bool:

        total = self.segments_map.get(track)

        if not total:
            return False

        return set(segments) == set(range(total))

    def expand_display_track(
            self,
            display_track: str,
            segments:      list[int] | None = None
        ) -> list[tuple[str, list[int] | None]]:

        if self.is_master_track(display_track):
            if self.master_track_mode in (MasterTrackMode.ALL_LIT, MasterTrackMode.MATRIX) and segments is None:
                return [(real_track, None) for real_track, _ in self.resolve_master_track()]

            if self.master_track_mode is MasterTrackMode.MATRIX and segments is not None:
                zones_by_real_track: dict[str, list[int]] = {}

                for led_index in segments:
                    if 0 <= led_index < len(self.matrix_led_to_row_segment):
                        real_track, real_zone = self.matrix_led_to_row_segment[led_index]
                        zones_by_real_track.setdefault(real_track, []).append(real_zone)

                return [
                    (
                        real_track,
                        None if self.is_full_track_segments(real_track, real_zones) else sorted(real_zones)
                    )
                    for real_track, real_zones in zones_by_real_track.items()
                ]

            active_segments = segments if segments is not None else range(self.master_track_segments)

            zones_by_real_track: dict[str, list[int]] = {}

            for virtual_zone in active_segments:
                real_track, real_zone = self.resolve_master_zone(virtual_zone)
                zones_by_real_track.setdefault(real_track, []).append(real_zone)

            return [
                (
                    real_track,
                    None if self.is_full_track_segments(real_track, real_zones) else sorted(real_zones)
                )
                for real_track, real_zones in zones_by_real_track.items()
            ]

        if self.is_segment_track(display_track):
            real_track, real_zone = self.resolve_segment_track(display_track)

            return [(real_track, [real_zone])]

        return [(display_track, segments)]

    def expand_display_track_with_levels(
            self,
            display_track:  str,
            segments:       list[int]   | None = None,
            segment_levels: list[float] | None = None
        ) -> list[tuple[str, list[int] | None, list[float] | None]]:

        if segment_levels is None or segments is None or len(segment_levels) != len(segments):
            return [
                (real_track, real_segments, None)
                for real_track, real_segments in self.expand_display_track(display_track, segments)
            ]

        level_by_virtual_zone = dict(zip(segments, segment_levels))

        if not self.is_master_track(display_track):
            if self.is_segment_track(display_track):
                real_track, real_zone = self.resolve_segment_track(display_track)
                level                 = level_by_virtual_zone.get(real_zone, 1.0)

                return [(real_track, [real_zone], [level])]

            return [(display_track, segments, segment_levels)]

        if self.master_track_mode is MasterTrackMode.MATRIX:
            zones_by_real_track: dict[str, list[tuple[int, float]]] = {}

            for led_index in segments:
                if 0 <= led_index < len(self.matrix_led_to_row_segment):
                    real_track, real_zone = self.matrix_led_to_row_segment[led_index]
                    level                 = level_by_virtual_zone.get(led_index, 1.0)
                    zones_by_real_track.setdefault(real_track, []).append((real_zone, level))

            result = []

            for real_track, pairs in zones_by_real_track.items():
                pairs.sort(key = lambda pair: pair[0])

                real_zones  = [pair[0] for pair in pairs]
                real_levels = [pair[1] for pair in pairs]

                if self.is_full_track_segments(real_track, real_zones) and all(level >= 0.999 for level in real_levels):
                    result.append((real_track, None, None))

                else:
                    result.append((real_track, real_zones, real_levels))

            return result

        zones_by_real_track = {}

        for virtual_zone in segments:
            real_track, real_zone = self.resolve_master_zone(virtual_zone)
            level                 = level_by_virtual_zone.get(virtual_zone, 1.0)
            zones_by_real_track.setdefault(real_track, []).append((real_zone, level))

        result = []

        for real_track, pairs in zones_by_real_track.items():
            pairs.sort(key = lambda pair: pair[0])

            real_zones  = [pair[0] for pair in pairs]
            real_levels = [pair[1] for pair in pairs]

            if self.is_full_track_segments(real_track, real_zones) and all(level >= 0.999 for level in real_levels):
                result.append((real_track, None, None))

            else:
                result.append((real_track, real_zones, real_levels))

        return result

    def get_master_array_indexes(self, active_segments: list[int] | None = None) -> list[int]:
        if self.master_track_mode is MasterTrackMode.ALL_LIT:
            indexes: list[int] = []

            for index in range(1, self.base_tracks + 1):
                indexes.extend(self.get_array_indexes(index, 0))

            return indexes

        if self.master_track_mode is MasterTrackMode.MATRIX:
            if active_segments is None:
                return list(range(self.columns))

            return [index for index in active_segments if 0 <= index < self.columns]

        if active_segments is None:
            active_segments = range(self.master_track_segments)

        return [
            self.get_array_indexes(int(real_track), real_zone + 1)[0]
            for real_track, real_zone in (
                self.resolve_master_zone(virtual_zone)
                for virtual_zone in active_segments
            )
        ]

    def get_display_array_indexes(
            self,
            display_track: str,
            segments:      list[int] | None = None
        ) -> list[int]:

        if self.is_master_track(display_track):
            return self.get_master_array_indexes(segments)

        if self.is_segment_track(display_track):
            real_track, real_zone = self.resolve_segment_track(display_track)

            return [self.get_array_indexes(int(real_track), real_zone + 1)[0]]

        real_track = int(display_track)

        if segments:
            return [self.get_array_indexes(real_track, segment + 1)[0] for segment in segments]

        return self.get_array_indexes(real_track, 0)

    def get_array_indexes(
            self,
            glyph_index: int,
            zone_index:  int
        ) -> list[int] | int:

        glyph_index -= 1
        zone_index  -= 1

        if zone_index == -1:
            return self.glyph_indexes[glyph_index]

        offset = self.calculate_zone_offset(glyph_index)

        return self.zone_indexes[glyph_index + zone_index + offset]

    def resolve_tracks(
            self,
            input_track:  str,
            total_tracks: int
        ) -> list[tuple[str, int | None]]:

        if self.is_master_track(input_track):
            return self.resolve_master_track()

        if total_tracks in self.legacy_tracks:
            mapping = self.legacy_tracks[total_tracks]

            if input_track in mapping:
                return [(track, None) for track in mapping[input_track]]

        if input_track in self.segments_map:
            count = self.segments_map[input_track]
            return [(input_track, index) for index in range(count)]

        return [(input_track, None)]

# Helpers

def make_ranges(*ranges: int | list[int]) -> list[list[int]]:
    result  = []
    current = 0

    for entry in ranges:
        if isinstance(entry, int):
            result.append(list(range(current, current + entry)))
            current += entry

        else:
            result.append(entry)
            current = max(entry) + 1 if entry else current

    return result

def generate_matrix_visualization_map(
        matrix_rows: list[int],
        view_size:   tuple[int, int] = (260, 260),
        thickness:   float           = 6.0
    ) -> dict:

    row_count       = len(matrix_rows)
    maximum_columns = max(matrix_rows)
    width_px        = view_size[0]
    height_px       = view_size[1]

    horizontal_step = (width_px - 40.0) / float(maximum_columns)
    vertical_step   = (height_px - 40.0) / float(row_count)

    center_x = width_px / 2.0
    center_y = height_px / 2.0

    glyphs_map: dict[str, dict[str, object]] = {}

    for row_index, row_width in enumerate(matrix_rows):
        row_track_identifier = str(row_index + 1)
        y_position           = center_y + (row_index - (row_count - 1) / 2.0) * vertical_step
        row_pixel_span       = (row_width - 1) * horizontal_step

        start_x = center_x - row_pixel_span / 2.0
        end_x   = center_x + row_pixel_span / 2.0

        if row_width == 1:
            end_x += 0.1

        svg_path = f"M{start_x:.2f},{y_position:.2f} L{end_x:.2f},{y_position:.2f}"

        glyphs_map[row_track_identifier] = {
            "svg":      svg_path,
            "position": (0, 0),
            "segments": row_width
        }

    return {
        "glyphs":    glyphs_map,
        "size":      view_size,
        "thickness": thickness
    }