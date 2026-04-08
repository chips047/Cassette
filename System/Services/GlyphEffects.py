import random

from System.Common.Constants import DEVICES

from loguru import logger

# Data Extraction & Parsing

def parse_effect_arguments(
        config:        dict,
        settings_meta: dict
    ) -> dict:
    
    arguments = {}

    for meta in settings_meta:
        try:
            argument_name = meta.get("key")
            if not argument_name:
                continue

            value                    = config.get(meta["key"], 1)
            arguments[argument_name] = value
        
        except Exception as error:
            logger.error(f"Couldn't parse effect arguments: {error}. Effect: {config}, {settings_meta}")

    return arguments

def extract_glyph_data(
        glyph: dict,
        model: str
    ) -> dict:
    
    start              = glyph["start"]
    duration           = glyph["duration"]
    end                = start + duration
    
    track              = glyph["track"]
    brightness         = glyph["brightness"]
    
    total_segments     = None
    active_segments    = glyph.get("segments")

    model = DEVICES.get(model)

    if not model:
        total_segments = 30
    
    else:
        total_segments = model.segments_map.get(track)

    return {
        "start":              start,
        "end":                end,
        "duration":           duration,
        "track":              track,
        "brightness":         brightness,
        "total_segments":     total_segments,
        "active_segments":    active_segments
    }

# Effect Application

def apply_visual_effect(
        glyph:    dict,
        name:     str,
        settings: dict
    ) -> dict:

    if name == "None":
        glyph.pop("effect", None)
        return glyph

    glyph["effect"] = {
        "name":     name,
        "settings": settings
    }
    
    if name == "Fade":
        brightness = glyph["brightness"]
        mode       = settings.get("mode", "fade_out")

        if "keyframes" in settings:
            glyph["effect"]["settings"]["keyframes"] = settings["keyframes"]
        
        else:
            keyframes_map = {
                "custom":      [(0.0, brightness), (1.0, brightness)],
                "fade_out":    [(0.0, brightness), (1.0, 0)],
                "fade_in":     [(0.0, 0), (1.0, brightness)],
                "fade_in_out": [(0.0, 0), (0.5, brightness), (1.0, 0)]
            }
            
            glyph["effect"]["settings"]["keyframes"] = keyframes_map.get(mode, keyframes_map["fade_out"])

    return glyph

def effect_to_glyph(
        glyph: dict,
        bpm:   int,
        model: str | None = None
    ) -> list:

    if "effect" not in glyph:
        return []
    
    name   = glyph["effect"]["name"]
    config = glyph["effect"]["settings"]

    effect_info = EffectsConfig.get(name)

    if not effect_info:
        return []
    
    effect_function = effect_info["function"]
    settings_meta   = effect_info["settings"]
    kwargs          = parse_effect_arguments(config, settings_meta)
    
    result = effect_function(
        glyph,
        model,
        bpm,
        **kwargs
    )

    return result

# Simple Effects

def fade_effect(
        glyph:  dict,
        model:  str,
        bpm:    int,
        mode:   str,
        easing: str
    ) -> list:
    
    data = extract_glyph_data(glyph, model)

    out = {
        "start":     data["start"],
        "duration":  data["duration"],
        "track":     data["track"],
        "easing":    easing,
        "mode":      mode,
        "keyframes": glyph["effect"]["settings"]["keyframes"]
    }

    if data["active_segments"]:
        out["segments"] = data["active_segments"]

    return [out]

def strobe_effect(
        glyph:             dict,
        model:             str,
        bpm:               int,
        frequency:         int  = 1,
        first_brightness:  int  = 100,
        second_brightness: int  = 70,
        bpm_snap:          bool = False
    ) -> list:
    
    if bpm_snap:
        frequency = (bpm / 60) * bpm_snap

    data     = extract_glyph_data(glyph, model)
    interval = 1000 / frequency
    time     = data["start"]
    output   = []

    while time < data["end"]:
        time_off = min(time + interval / 2, data["end"])
        duration = time_off - time

        items = [
            {
                "start":      time,
                "duration":   duration,
                "track":      data["track"],
                "brightness": first_brightness
            },
            {
                "start":      time_off,
                "duration":   duration,
                "track":      data["track"],
                "brightness": second_brightness
            }
        ]

        if data["active_segments"]:
            for item in items:
                item["segments"] = data["active_segments"]

        output.extend(items)
        
        time += interval

    return output

# BPM - based Effects

def bpm_effect(
        glyph:          dict,
        model:          str,
        bpm:            float,
        multiplier:     int,
        enable_fading:  bool
    ) -> list:
    
    data = extract_glyph_data(glyph, model)

    actual_bpm      = bpm * multiplier
    beat_interval   = 60000.0 / actual_bpm
    time            = data["start"]
    output          = []
    brightness      = data["brightness"]
    dim_brightness  = max(5, data["brightness"] * 0.2)
    tick            = 0

    while time < data["end"]:
        if enable_fading:
            if multiplier <= 1:
                brightness = data["brightness"]
            
            else:
                tick += 1
                
                if tick % multiplier == 1:
                    brightness = data["brightness"]
                
                else:
                    brightness = dim_brightness

        time_off = min(time + beat_interval / 2, data["end"])
        item     = {
            "start":     time,
            "duration":  time_off - time,
            "track":     data["track"],
            "keyframes": [(0.0, brightness), (1.0, 0)],
            "easing":    "linear"
        }

        if data["active_segments"]:
            item["segments"] = data["active_segments"]

        output.append(item)
        time += beat_interval

    return output

def sparkle_effect(
        glyph:      dict,
        model:      str,
        bpm:        int,
        multiplier: int,
        fade_out:   bool = True
    ) -> list:
    
    frequency = bpm * multiplier / 60
    data      = extract_glyph_data(glyph, model)
    interval  = 1000.0 / frequency
    time      = data["start"]
    output    = []

    while time < data["end"] - 1e-9:
        time_next = min(time + interval, data["end"])
        
        if data["active_segments"]:
            selected_segment = random.choice(data["active_segments"])
        else:
            selected_segment = random.randint(0, data["total_segments"] - 1)
        
        element = {
            "start":    time,
            "duration": time_next - time,
            "track":    data["track"],
            "segments": [selected_segment]
        }

        if fade_out:
            element["keyframes"] = [(0.0, data["brightness"]), (1.0, 0)]
            element["easing"]    = "linear"
        
        else:
            element["brightness"] = data["brightness"]
        
        output.append(element)
        time = time_next

    return output

# Segment - based Effects

def sidebeat_effect(
        glyph: dict,
        model: str,
        bpm:   int,
        part:  str
    ) -> list:
    
    data                  = extract_glyph_data(glyph, model)
    segment_list          = list(range(1, data["total_segments"] + 1))
    segments_in_one_part  = data["total_segments"] // 3
    time_per_segment      = data["duration"] / segments_in_one_part / 2

    left_part  = segment_list[0:segments_in_one_part]
    right_part = segment_list[-segments_in_one_part:]

    part_modes = {
        "left":  ([left_part], 1),
        "right": ([right_part], data["total_segments"]),
        "both":  ([left_part, right_part], [1, data["total_segments"]])
    }

    segments_to_animate, current_segments = part_modes[part]
    
    if not isinstance(current_segments, list):
        current_segments = [current_segments] * len(segments_to_animate)

    output = []

    for part_segments, base_segment in zip(segments_to_animate, current_segments):
        direction = 1 if base_segment == 1 else -1
    
        for i, _ in enumerate(part_segments):
            shrink = time_per_segment * i
    
            output.append(
                {
                    "start":      data["start"] + shrink,
                    "duration":   (data["end"] - data["start"]) - 2 * shrink,
                    "track":      data["track"],
                    "segments":   [(base_segment + i * direction) - 1],
                    "brightness": 100
                }
            )
    
    return output

def fill_effect(
        glyph: dict,
        model: str,
        bpm:   int,
        side:  int = 1
    ) -> list:
    
    data          = extract_glyph_data(glyph, model)
    segment_step  = data["duration"] / data["total_segments"]
    indices       = list(range(data["total_segments"]))[:: (1 if side == 1 else -1)]
    events        = []

    for output_index, i in enumerate(indices):
        start    = data["start"] + output_index * segment_step
        duration = data["end"] - start
        
        events.append(
            {
                "start":     start,
                "duration":  duration,
                "track":     data["track"],
                "segments":  [i],
                "keyframes": [(0.0, 0), (1.0, data["brightness"])],
                "easing":    "linear"
            }
        )
    
    return events

def random_fill_effect(
        glyph:    dict,
        model:    str,
        bpm:      int,
        bpm_snap: bool = False,
        mode:     str  = "Fill"
    ) -> list:
    
    data = extract_glyph_data(glyph, model)
    
    if not data["total_segments"]:
        return []

    if data["active_segments"]:
        indices = data["active_segments"]
    
    else:
        indices = list(range(data["total_segments"]))
    
    random.shuffle(indices)

    if bpm_snap:
        step_duration = 60000.0 / (bpm * bpm_snap)
    
    else:
        step_duration = data["duration"] / data["total_segments"]

    output = []

    for i, segment_index in enumerate(indices):
        segment_start = data["start"] + i * step_duration
        
        if segment_start >= data["end"]:
            break
        
        segment_duration = data["end"] - segment_start

        if mode == "Fill":
            output.append(
                {
                    "start":      segment_start,
                    "duration":   segment_duration,
                    "track":      data["track"],
                    "segments":   [segment_index],
                    "brightness": data["brightness"]
                }
            )
        
        else:
            output.append(
                {
                    "start":      data["start"],
                    "duration":   segment_start - data["start"],
                    "track":      data["track"],
                    "segments":   [segment_index],
                    "brightness": data["brightness"]
                }
            )

    return output

# Pattern Effects

def glitch_effect(
        glyph:          dict,
        model:          str,
        bpm:            int,
        fps:            float = 20.0,
        duty_cycle:     float = 0.7,
        min_brightness_ratio:   float = 0.3,
        bpm_snap:       bool  = False,
        enable_fade_out: bool = False
    ) -> list:
    
    if bpm_snap:
        fps = (bpm / 60) * bpm_snap
    
    min_brightness_ratio      /= 100

    data               = extract_glyph_data(glyph, model)
    frame              = 1000.0 / fps
    time               = data["start"]
    
    min_brightness     = max(5, int(data["brightness"] * min_brightness_ratio))
    available_segments = glyph.get("segments", list(range(data["total_segments"])))
    count              = int(len(available_segments) * duty_cycle)
    output             = []

    while time < data["end"] - 1e-9:
        time_start = time
        time_end   = min(time + frame, data["end"])
        chosen     = random.sample(available_segments, count)
        
        if min_brightness >= data["brightness"]:
            brightness = data["brightness"]
        
        else:
            brightness = random.randint(min_brightness, data["brightness"])

        item = {
            "start":    time_start,
            "duration": time_end - time_start,
            "track":    data["track"],
            "segments": list(set(chosen))
        }

        if enable_fade_out:
            item["keyframes"] = [(0.0, brightness), (1.0, 0)]
            item["easing"]    = "linear"
        
        else:
            item["brightness"] = brightness

        output.append(item)
        time = time_end

    return output

def ripple_effect(
        glyph:            dict,
        model:            str,
        bpm:              int,
        tail:             int  = 4
    ) -> list:
    
    data = extract_glyph_data(glyph, model)
    
    if data["total_segments"] is None or data["total_segments"] <= 0 or (data["end"] - data["start"]) <= 0:
        return []

    center_indices = []
    
    if data["total_segments"] % 2 == 1:
        center_indices.append(data["total_segments"] // 2)
    
    else:
        center_indices.append(data["total_segments"] // 2 - 1)
        center_indices.append(data["total_segments"] // 2)

    actual_duration   = data["end"] - data["start"]
    max_radius_glyph  = max(center_indices[-1], data["total_segments"] - 1 - center_indices[0])
    max_total_radius  = max_radius_glyph + tail

    if max_radius_glyph <= 0:
        full_duration = actual_duration
    
    else:
        full_duration = (max_total_radius / max_radius_glyph) * actual_duration

    full_duration = min(full_duration, actual_duration)

    if full_duration <= 1e-12:
        return []

    frame    = 20
    time     = data["start"]
    output   = []
    end_time = data["start"] + full_duration

    while time < end_time - 1e-9:
        time_next = min(time + frame, end_time)
        elapsed   = time - data["start"]
        progress  = elapsed / full_duration
        radius    = int(progress * max_total_radius)

        for r in range(max(0, radius - tail), radius):
            distance       = radius - r
            decay          = 1.0 - (distance / max(1, tail))
            brightness_now = max(0, int(data["brightness"] * decay))
            left           = center_indices[0] - r
            right          = center_indices[-1] + r
            indices        = []
            
            if 0 <= left < data["total_segments"]:
                indices.append(left)
            
            if 0 <= right < data["total_segments"] and right != left:
                indices.append(right)

            for i in indices:
                output.append(
                    {
                        "start":      time,
                        "duration":   time_next - time,
                        "track":      data["track"],
                        "segments":   [i],
                        "brightness": brightness_now
                    }
                )

        head_segments = []
        left          = center_indices[0] - radius
        right         = center_indices[-1] + radius

        if 0 <= left < data["total_segments"]:
            head_segments.append(left)
        
        if 0 <= right < data["total_segments"] and right != left:
            head_segments.append(right)

        if head_segments:
            output.append(
                {
                    "start":      time,
                    "duration":   time_next - time,
                    "track":      data["track"],
                    "segments":   head_segments,
                    "brightness": data["brightness"]
                }
            )

        time = time_next

    return output


def chase_effect(
        glyph:     dict,
        model:     str,
        bpm:       int,
        width:     int = 3,
        direction: int = 1,
        gap:       int = 0
    ) -> list:
    
    data = extract_glyph_data(glyph, model)
    
    if not data["total_segments"]:
        return []

    width           = max(1, width)
    gap             = max(0, gap)
    effective_width = width + (width - 1) * gap
    total_steps     = data["total_segments"] + effective_width - 1
    
    if total_steps <= 0:
        return []
    
    step_time = data["duration"] / total_steps
    output    = []
    time      = data["start"]

    for step in range(total_steps):
        segments_to_light = []
        
        for i in range(width):
            offset = i * (1 + gap)
            
            if direction == 1:
                index = step - offset
            
            else:
                index = (data["total_segments"] - 1) - (step - offset)
            
            if 0 <= index < data["total_segments"]:
                segments_to_light.append(index)

        if segments_to_light:
            output.append(
                {
                    "start":      time,
                    "duration":   step_time,
                    "track":      data["track"],
                    "segments":   sorted(list(set(segments_to_light))),
                    "brightness": data["brightness"]
                }
            )

        time += step_time
        
        if time > data["end"]:
            break

    return output

def zebra_effect(
        glyph:     dict,
        model:     str,
        bpm:       int,
        fps:       int  = 1,
        on_count:  int  = 1,
        off_count: int  = 1,
        side:      int  = 1,
        bpm_snap:  bool = False
    ) -> list:
    
    data = extract_glyph_data(glyph, model)
    
    if bpm_snap:
        fps = (bpm / 60) * bpm_snap

    step_duration = 1000.0 / fps
    total_steps   = max(1, int(data["duration"] / step_duration))
    pattern_len   = on_count + off_count
    output        = []

    for step in range(total_steps):
        time_start = data["start"] + step * step_duration
        time_end   = min(time_start + step_duration, data["start"] + data["duration"])

        for i in range(data["total_segments"]):
            shifted_index = (i - step * side) % pattern_len
            
            if shifted_index < on_count:
                output.append(
                    {
                        "start":      time_start,
                        "duration":   time_end - time_start,
                        "track":      data["track"],
                        "segments":   [i],
                        "brightness": data["brightness"]
                    }
                )

    return output


def shocker_effect(
        glyph:     dict,
        model:     str,
        bpm:       int,
        frequency: float = 5.0,
        fade_out:  bool  = True,
        bpm_snap:  bool  = False
    ) -> list:
    
    if bpm_snap:
        frequency = (bpm / 60) * bpm_snap

    data     = extract_glyph_data(glyph, model)
    interval = 1000.0 / frequency
    time     = data["start"]
    output   = []

    even_indices = [i + 1 for i in range(data["total_segments"]) if (i + 1) % 2 == 0]
    odd_indices  = [i + 1 for i in range(data["total_segments"]) if (i + 1) % 2 == 1]

    while time < data["end"]:
        time_half = min(time + interval / 2, data["end"])
        time_next = min(time + interval, data["end"])

        for i in even_indices:
            element = {
                "start":    time,
                "duration": time_half - time,
                "track":    data["track"],
                "segments": [i - 1]
            }
            
            if fade_out:
                element["keyframes"] = [(0.0, data["brightness"]), (1.0, 0)]
                element["easing"]    = "linear"
            
            else:
                element["brightness"] = data["brightness"]
            
            output.append(element)

        for i in odd_indices:
            element = {
                "start":    time_half,
                "duration": time_next - time_half,
                "track":    data["track"],
                "segments": [i - 1]
            }
            
            if fade_out:
                element["keyframes"] = [(0.0, data["brightness"]), (1.0, 0)]
                element["easing"]    = "linear"
            
            else:
                element["brightness"] = data["brightness"]
            
            output.append(element)

        time = time_next

    return output

# Advanced motion effects

def calculate_tail_brightness(
        head_brightness: int,
        tail_position:   int,
        tail_length:     int
    ) -> int:
    
    if tail_position == 0 or tail_length <= 1:
        return head_brightness

    min_brightness = max(5, int(head_brightness * 0.05))
    span           = head_brightness - min_brightness

    return max(min_brightness, int(head_brightness - span * (tail_position / (tail_length - 1))))

def boomerang_effect(
        glyph: dict,
        model: str,
        bpm:   int,
        jumps: int
    ) -> list:
    
    data          = extract_glyph_data(glyph, model)
    jumps        += 2
    growth_range  = data["total_segments"] - 1
    steps_to_grow = jumps - 1 if jumps > 1 else 1
    tail_step     = max(1, round(growth_range / steps_to_grow))

    output       = []
    tail_length  = 1
    direction    = -1
    virtual_head = data["total_segments"]
    time         = data["start"]

    def get_step(current_tail: int) -> float:
        return data["duration"] / (jumps * (data["total_segments"] + current_tail))

    while time < data["end"] - 1e-9:
        step      = get_step(tail_length)
        time_next = time + step

        segments_to_light = [
            (virtual_head + i if direction == -1 else virtual_head - i, i)
            for i in range(tail_length)
        ]

        for segment_index, tail_position in segments_to_light:
            if 1 <= segment_index <= data["total_segments"]:
                brightness = calculate_tail_brightness(data["brightness"], tail_position, tail_length)
                
                output.append(
                    {
                        "start":      time,
                        "duration":   step,
                        "track":      data["track"],
                        "segments":   [segment_index - 1],
                        "brightness": brightness
                    }
                )

        virtual_head += direction

        if (
            (direction == -1 and virtual_head + tail_length - 1 < 1) or
            (direction == 1 and virtual_head - tail_length + 1 > data["total_segments"])
        ):
            
            remaining = (data["end"] - time_next)
            new_step  = step * (data["total_segments"] + tail_length + tail_step)
            
            if remaining > new_step:
                tail_length  = min(tail_length + tail_step, data["total_segments"])
                direction   *= -1
                virtual_head = data["total_segments"] if direction == -1 else 1

        time = time_next

    return output

# Configuration & Utilities

EffectsConfig = {
    "None": {
        "segmented":             False,
        "supports_segmentation": True,
        "settings":              []
    },

    "Fade": {
        "segmented":             False,
        "supports_segmentation": True,
        "function":              fade_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Mode",
                "key":     "mode",
                "map": {
                    "Fade In":     "fade_in",
                    "Fade Out":    "fade_out",
                    "Fade In Out": "fade_in_out"
                },
                "default": "Fade Out"
            },
            {
                "type":    "selector",
                "title":   "Easing",
                "key":     "easing",
                "map": {
                    "Linear":         "linear",
                    "Ease In":        "ease_in",
                    "Ease Out":       "ease_out",
                    "Ease In Out":    "ease_in_out",
                    "Ease Out Cubic": "ease_out_cubic"
                },
                "default": "Linear"
            }
        ]
    },

    "Fill": {
        "segmented":             True,
        "supports_segmentation": False,
        "function":              fill_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Side",
                "key":     "side",
                "map":     {"To the left": -1, "To the right": 1},
                "default": "To the left"
            }
        ]
    },

    "Random Fill": {
        "segmented":             True,
        "supports_segmentation": True,
        "function":              random_fill_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Mode",
                "key":     "mode",
                "map":     {"Fill": "Fill", "Clear": "Clear"},
                "default": "Fill"
            },
            {
                "type":    "selector",
                "title":   "Snap to BPM",
                "key":     "bpm_snap",
                "map": {
                    "Disabled":  False,
                    "BPM x0.5":  0.5,
                    "BPM x1":    1,
                    "BPM x2":    2,
                    "BPM x4":    4
                },
                "default": "Disabled"
            }
        ]
    },

    "Zebra": {
        "segmented":             True,
        "supports_segmentation": False,
        "function":              zebra_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Snap to BPM",
                "key":     "bpm_snap",
                "map": {
                    "Disabled":  False,
                    "BPM x0.5":  0.5,
                    "BPM x1":    1,
                    "BPM x2":    2,
                    "BPM x4":    4
                },
                "default": "Disabled"
            },
            {
                "type":    "selector",
                "title":   "Side",
                "key":     "side",
                "map":     {"To the left": -1, "To the right": 1},
                "default": "To the left"
            },
            {
                "type":    "slider",
                "title":   "Moves per second",
                "min":     1,
                "max":     20,
                "offset":  1,
                "key":     "fps",
                "default": 5
            },
            {
                "type":    "slider",
                "title":   "Lit segments in a row",
                "min":     1,
                "max":     5,
                "offset":  1,
                "key":     "on_count",
                "default": 3
            },
            {
                "type":    "slider",
                "title":   "Dark segments in a row",
                "min":     1,
                "max":     5,
                "offset":  1,
                "key":     "off_count",
                "default": 1
            }
        ]
    },

    "Sparkle": {
        "segmented":             True,
        "supports_segmentation": True,
        "function":              sparkle_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "BPM",
                "key":     "multiplier",
                "map": {
                    "BPM x0.5": 0.5,
                    "BPM x1":   1,
                    "BPM x2":   2,
                    "BPM x4":   4
                },
                "default": "BPM x1"
            },
            {
                "type":    "checkbox",
                "title":   "Enable fade out",
                "key":     "fade_out",
                "default": True
            }
        ]
    },

    "Strobe": {
        "segmented":             False,
        "supports_segmentation": True,
        "function":              strobe_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Snap to BPM",
                "key":     "bpm_snap",
                "map": {
                    "Disabled":  False,
                    "BPM x0.5":  0.5,
                    "BPM x1":    1,
                    "BPM x2":    2,
                    "BPM x4":    4
                },
                "default": "Disabled"
            },
            {
                "type":    "slider",
                "title":   "Strobes per second",
                "key":     "frequency",
                "min":     1,
                "max":     20,
                "default": 5
            },
            {
                "type":    "slider",
                "title":   "First brightness",
                "key":     "first_brightness",
                "min":     0,
                "max":     100,
                "default": 100
            },
            {
                "type":    "slider",
                "title":   "Second brightness",
                "key":     "second_brightness",
                "min":     0,
                "max":     100,
                "default": 0
            }
        ]
    },

    "Shocker": {
        "segmented":             True,
        "supports_segmentation": False,
        "function":              shocker_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Snap to BPM",
                "key":     "bpm_snap",
                "map": {
                    "Disabled":  False,
                    "BPM x0.5":  0.5,
                    "BPM x1":    1,
                    "BPM x2":    2,
                    "BPM x4":    4
                },
                "default": "Disabled"
            },
            {
                "type":    "slider",
                "title":   "Shocks per second",
                "key":     "frequency",
                "min":     1,
                "max":     15,
                "default": 3
            },
            {
                "type":    "checkbox",
                "title":   "Enable fade out",
                "key":     "fade_out",
                "default": True
            }
        ]
    },

    "Glitch": {
        "segmented":             True,
        "supports_segmentation": True,
        "function":              glitch_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Snap to BPM",
                "key":     "bpm_snap",
                "map": {
                    "Disabled":  False,
                    "BPM x0.5":  0.5,
                    "BPM x1":    1,
                    "BPM x2":    2,
                    "BPM x4":    4
                },
                "default": "Disabled"
            },
            {
                "type":    "slider",
                "title":   "Glitches per second",
                "key":     "fps",
                "min":     1,
                "max":     30,
                "default": 10
            },
            {
                "type":    "slider",
                "title":   "Minimal brightness",
                "key":     "min_brightness_ratio",
                "min":     1,
                "max":     100,
                "default": 30
            },
            {
                "type":    "selector",
                "title":   "Glitch fill level",
                "key":     "duty_cycle",
                "map":     {"Less": 0.3, "More": 0.7},
                "default": "More"
            },
            {
                "type":    "checkbox",
                "title":   "Enable Fade out",
                "key":     "enable_fade_out",
                "default": True
            }
        ]
    },

    "BPM": {
        "segmented":             False,
        "supports_segmentation": True,
        "function":              bpm_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "BPM",
                "key":     "multiplier",
                "map": {
                    "BPM x0.5": 0.5,
                    "BPM x1":   1,
                    "BPM x2":   2,
                    "BPM x4":   4
                },
                "default": "BPM x1"
            },
            {
                "type":    "checkbox",
                "title":   "Enable fading on sub - beats",
                "key":     "enable_fading",
                "default": True
            }
        ]
    },

    "Sidebeat": {
        "segmented":             True,
        "supports_segmentation": False,
        "function":              sidebeat_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Side",
                "key":     "part",
                "map": {
                    "Left":  "left",
                    "Both":  "both",
                    "Right": "right"
                },
                "default": "Both"
            }
        ]
    },

    "Boomerang": {
        "segmented":             True,
        "supports_segmentation": False,
        "function":              boomerang_effect,
        "settings": [
            {
                "type":    "slider",
                "title":   "Jumps",
                "key":     "jumps",
                "min":     4,
                "max":     12,
                "default": 4
            }
        ]
    },

    "Chase": {
        "segmented":             True,
        "supports_segmentation": False,
        "function":              chase_effect,
        "settings": [
            {
                "type":    "slider",
                "title":   "Width",
                "key":     "width",
                "min":     1,
                "max":     10,
                "offset":  1,
                "default": 3
            },
            {
                "type":    "slider",
                "title":   "Gap",
                "key":     "gap",
                "min":     0,
                "max":     5,
                "offset":  1,
                "default": 0
            },
            {
                "type":    "selector",
                "title":   "Direction",
                "key":     "direction",
                "map":     {"To the left": -1, "To the right": 1},
                "default": "To the left"
            }
        ]
    },

    "Ripple": {
        "segmented":             True,
        "supports_segmentation": False,
        "function":              ripple_effect,
        "settings": [
            {
                "type":    "slider",
                "title":   "Tail",
                "key":     "tail",
                "min":     1,
                "max":     10,
                "offset":  1,
                "default": 5
            }
        ]
    }
}

# Helper Functions

def is_segment_edited(glyph: dict) -> bool:
    return "segments" in glyph

def get_all_effects() -> dict:
    return EffectsConfig

def get_non_segmented_effects() -> dict:
    return {
        name: config for name, config in EffectsConfig.items()
        if not config.get("segmented", False)
    }

def get_segmented_effects() -> dict:
    return {
        name: config for name, config in EffectsConfig.items()
        if config.get("segmented", False)
    }

def get_segmentation_supported_effects() -> dict:
    return {
        name: config for name, config in EffectsConfig.items()
        if config.get("supports_segmentation", False)
    }

def generate_effect_dict(
        name:     str,
        settings: dict | None = None
    ) -> dict:
    
    return {
        "name":     name,
        "settings": settings or {}
    }

def generate_glyph_dict(
        track:      str  = "1",
        brightness: int  = 100,
        duration:   int  = 100,
        start:      int  = 0,
        effect:     dict = None
    ) -> dict:
    
    glyph_dict = {
        "track":      track,
        "brightness": brightness,
        "duration":   duration,
        "start":      start
    }

    if effect:
        glyph_dict["effect"] = effect
    
    return glyph_dict