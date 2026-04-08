import random

from loguru import logger

from System.Common.Constants import (
    DEVICES,
    PortMaps
)

from System.Services import GlyphEffects

# Segment Utilities

def calculate_position_ratio(old_segments_count: int, new_segments_count: int) -> float:
    if old_segments_count <= 1:
        return 0.0

    return (new_segments_count - 1) / (old_segments_count - 1)

def scale_active_segments(
        active_segments:   list,
        position_ratio:     float,
        new_segments_count: int
    ) -> list:

    rounded_values = [round(active_value * position_ratio) for active_value in active_segments]

    return [max(0, min(new_segments_count - 1, value)) for value in rounded_values]

def resolve_unique_segments(rounded_values: list) -> list:
    unique_values = []

    for value in rounded_values:
        if unique_values and value == unique_values[-1]:
            continue
        
        unique_values.append(value)

    mapped_segments = [unique_values[0]]

    for index in range(1, len(unique_values)):
        gap = max(1, unique_values[index] - unique_values[index - 1])
        mapped_segments.append(mapped_segments[-1] + gap)

    return mapped_segments

def resolve_gap_segments(active_segments: list, position_ratio:  float) -> list:
    mapped_segments = [round(active_segments[0] * position_ratio)]

    for index in range(1, len(active_segments)):
        gap_old_segments = active_segments[index] - active_segments[index - 1]
        gap_new_segments = max(1, round(gap_old_segments * position_ratio))
        mapped_segments.append(mapped_segments[-1] + gap_new_segments)

    return mapped_segments

def finalize_segments(mapped_segments: list, new_segments_count: int) -> list:
    overflow        = max(0, mapped_segments[-1] - (new_segments_count - 1))
    shifted_values  = [max(0, value - overflow) for value in mapped_segments]
    final_segments  = []

    for value in shifted_values:
        clamped_value = max(0, min(new_segments_count - 1, value))
        
        if not final_segments or clamped_value != final_segments[-1]:
            final_segments.append(clamped_value)

    return final_segments

def port_segments_function(
        old_segments_count:        int,
        new_segments_count:        int,
        active_segments:           list,
        duplicate_threshold_ratio: float = 0.5
    ) -> list:

    if not active_segments:
        return []

    position_ratio = calculate_position_ratio(old_segments_count, new_segments_count)
    rounded_values = scale_active_segments(active_segments, position_ratio, new_segments_count)
    
    duplicate_count = sum(1 for index in range(1, len(rounded_values)) if rounded_values[index] == rounded_values[index - 1])
    threshold       = duplicate_threshold_ratio * len(active_segments)

    if duplicate_count >= threshold:
        mapped_segments = resolve_unique_segments(rounded_values)

    if duplicate_count < threshold:
        mapped_segments = resolve_gap_segments(active_segments, position_ratio)

    return finalize_segments(mapped_segments, new_segments_count)

# Track Processing

def process_dictionary_track(
        track: dict
    ) -> dict:

    mode     = track.get("mode")
    variants = track.get("variants", [])

    if mode != "random" or not variants:
        return track

    chosen_variant = random.choice(variants)

    return chosen_variant

def get_target_track(
        port_from: str,
        port_to:   str,
        glyph:     dict
    ) -> list:

    glyph_track = glyph["track"]
    model_map   = PortMaps[port_from]["to"][port_to]
    track_data  = model_map[glyph_track]

    if "effect" in glyph:
        effect_name = glyph["effect"]["name"]
        
        if effect_name in GlyphEffects.get_segmented_effects():
            return model_map["effects"]["segments"][glyph_track]

    if "segments" in glyph:
        return model_map["effects"]["segments"][glyph_track]

    if isinstance(track_data, list):
        if track_data and isinstance(track_data[0], dict):
            return process_dictionary_track(random.choice(track_data))
        
        return track_data
    
    if isinstance(track_data, dict):
        return process_dictionary_track(track_data)

    return track_data

# Glyph Factory

def make_glyph(
        base_glyph:   dict,
        track_name:   str,
        segments:     list = None,
        copy_effects: bool = False
    ) -> dict:

    new_glyph          = base_glyph.copy()
    new_glyph["track"] = track_name

    if segments is None:
        new_glyph.pop("segments", None)

    if segments is not None:
        new_glyph["segments"] = list(segments)

    if copy_effects and "effects" in new_glyph:
        new_glyph["effects"] = [effect.copy() for effect in new_glyph["effects"]]

    return new_glyph

# Core Porting Logic

def convert_effect_to_ported_glyphs(
        effect:             dict,
        target_tracks:      list,
        composition_model:  str,
        port_to:            str,
        beats_per_minute:   float
    ) -> list:

    output_glyphs = []

    if "segments" in effect:
        segment_source      = DEVICES[composition_model].segments_map[effect["track"]]
        segment_destination = DEVICES[port_to].segments_map[target_tracks[0]]
        
        ported_segments = port_segments_function(segment_source, segment_destination, effect["segments"])

        effect_for_conversion             = effect.copy()
        effect_for_conversion["track"]    = target_tracks[0]
        effect_for_conversion["segments"] = ported_segments

        output_glyphs.extend(GlyphEffects.effect_to_glyph(effect_for_conversion, beats_per_minute, port_to))

    for track_item in target_tracks:
        if isinstance(track_item, tuple):
            track_name, segment = track_item
            effect_copy         = make_glyph(effect, track_name, segments = [segment], copy_effects = True)
        
        if not isinstance(track_item, tuple):
            effect_copy = make_glyph(effect, track_item, segments = None, copy_effects = True)

        output_glyphs.extend(GlyphEffects.effect_to_glyph(effect_copy, beats_per_minute, port_to))

    return output_glyphs

def convert_single_to_ported_glyphs(
        single:            dict,
        target_tracks:     list,
        composition_model: str,
        port_to:           str
    ) -> list:

    output_glyphs = []

    if "segments" not in single:
        for track_item in target_tracks:
            if isinstance(track_item, tuple):
                track_name, segment = track_item
                new_glyph           = make_glyph(single, track_name, segments = [segment])
            
            if not isinstance(track_item, tuple):
                new_glyph = make_glyph(single, track_item, segments = None)

            output_glyphs.append(new_glyph)
        
        return output_glyphs

    chosen_target       = target_tracks[0]
    port_segments_from  = DEVICES[composition_model].segments_map[single["track"]]
    port_segments_to    = DEVICES[port_to].segments_map[chosen_target]
    
    ported_segments     = port_segments_function(port_segments_from, port_segments_to, single["segments"])
    
    output_glyphs.append(make_glyph(single, chosen_target, segments = ported_segments))

    return output_glyphs

def port_glyphs(port_to: str, composition: object) -> list:
    singles, effects = composition.sorted_glyphs()
    ported_glyphs    = []

    for effect in effects:
        target_tracks = get_target_track(composition.model, port_to, effect)
        
        ported_glyphs.extend(
            convert_effect_to_ported_glyphs(
                effect, 
                target_tracks, 
                composition.model, 
                port_to, 
                composition.bpm
            )
        )

    for single in singles:
        target_tracks = get_target_track(composition.model, port_to, single)
        
        ported_glyphs.extend(
            convert_single_to_ported_glyphs(
                single, 
                target_tracks, 
                composition.model, 
                port_to
            )
        )

    return ported_glyphs