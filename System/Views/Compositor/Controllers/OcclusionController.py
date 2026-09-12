from __future__ import annotations

from PyQt6.QtCore import QObject

from System.Interface import Widgets

class OcclusionController(QObject):
    def __init__(self) -> None:
        super().__init__()

        self.track_intervals: dict[str, list[tuple[float, float]]] = {}
        self.occluded_glyphs: set[int]                             = set()

    # State

    def clear(self) -> None:
        self.track_intervals.clear()
        self.occluded_glyphs.clear()

    def reveal_glyphs(self, glyph_items: list[Widgets.GlyphItem]) -> None:
        for item in glyph_items:
            glyph_id = item.glyph_id

            self.occluded_glyphs.discard(glyph_id)
            item.set_is_occluded(False)

    # Occlusion Calculation

    def update_track_occlusion(
            self,
            track_id:       str,
            glyph_items:    list[Widgets.GlyphItem],
            expanded_stack: frozenset[int] | None = None
        ) -> None:

        if not glyph_items:
            self.track_intervals[track_id] = []
            return

        sorted_items = sorted(
            glyph_items,
            key     = lambda item: (item.zValue(), item.glyph_id),
            reverse = True
        )

        merged_intervals: list[tuple[float, float]] = []

        for item in sorted_items:
            glyph_id = item.glyph_id

            if expanded_stack and glyph_id in expanded_stack:
                self.occluded_glyphs.discard(glyph_id)
                item.set_is_occluded(False)
                continue

            start_ms = float(item.start_ms)
            end_ms   = start_ms + float(item.duration_ms)

            if self.is_interval_covered(start_ms, end_ms, merged_intervals):
                self.occluded_glyphs.add(glyph_id)
                item.set_is_occluded(True)
                continue

            self.occluded_glyphs.discard(glyph_id)
            item.set_is_occluded(False)

            self.insert_and_merge(merged_intervals, start_ms, end_ms)

        self.track_intervals[track_id] = merged_intervals

    def is_interval_covered(
            self,
            start_ms:  float,
            end_ms:    float,
            intervals: list[tuple[float, float]]
        ) -> bool:

        for interval_start, interval_end in intervals:
            if interval_start <= start_ms and interval_end >= end_ms:
                return True

            if interval_start > start_ms:
                break

        return False

    def insert_and_merge(
            self,
            intervals: list[tuple[float, float]],
            start_ms:  float,
            end_ms:    float
        ) -> None:

        index           = 0
        intervals_count = len(intervals)

        while index < intervals_count and intervals[index][1] < start_ms:
            index += 1

        current_start = start_ms
        current_end   = end_ms

        while index < intervals_count and intervals[index][0] <= current_end:
            current_start = min(current_start, intervals[index][0])
            current_end   = max(current_end, intervals[index][1])

            intervals.pop(index)
            intervals_count -= 1

        intervals.insert(index, (current_start, current_end))