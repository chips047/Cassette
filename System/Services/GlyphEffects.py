import random

from loguru import logger

from System.Common import Constants

# Data Extraction And Parsing

def parse_effect_arguments(
        configuration:     dict,
        settings_metadata: list[dict]
    ) -> dict:

    arguments = {}

    for metadata in settings_metadata:
        argument_name = metadata.get("key")
        if not argument_name:
            continue

        try:
            default_value            = metadata.get("default", 1)
            arguments[argument_name] = configuration.get(argument_name, default_value)

        except Exception as error:
            logger.error(f"Couldn't parse effect arguments: {error}. Effect: {configuration}, {settings_metadata}")

    return arguments

def extract_glyph_data(
        glyph: dict,
        model: str | None
    ) -> dict:

    start           = glyph["start"]
    duration        = glyph["duration"]
    end             = start + duration
    track           = glyph["track"]
    brightness      = glyph.get("brightness", 100)
    active_segments = glyph.get("segments")

    device = Constants.DEVICES.get(model) if model else None

    if not device:
        total_segments = 30

    else:
        total_segments = device.get_track_segment_count(track)

    return {
        "start":           start,
        "end":             end,
        "duration":        duration,
        "track":           track,
        "brightness":      brightness,
        "total_segments":  total_segments,
        "active_segments": active_segments
    }

def resolve_target_segments(glyph_data: dict) -> list[int]:
    if glyph_data["active_segments"]:
        return sorted(list(glyph_data["active_segments"]))

    return list(range(glyph_data["total_segments"]))

# Event Creation

def create_glyph_event(
        track:      str,
        start:      float,
        duration:   float,
        segments:   list[int] | None = None,
        brightness: int | None = None,
        keyframes:  list[tuple[float, int | float]] | None = None,
        easing:     str | None = None
    ) -> dict:

    event = {
        "start":    start,
        "duration": duration,
        "track":    track
    }

    if segments is not None:
        event["segments"] = segments

    if keyframes is not None:
        event["keyframes"] = keyframes

        if easing is not None:
            event["easing"] = easing

    elif brightness is not None:
        event["brightness"] = brightness

    return event

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

    if name != "Fade":
        return glyph

    brightness = glyph.get("brightness", 100)
    mode       = settings.get("mode", "fade_out")

    if "keyframes" in settings:
        glyph["effect"]["settings"]["keyframes"] = settings["keyframes"]
        return glyph

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
        bpm:   int | float,
        model: str | None = None
    ) -> list[dict]:

    if "effect" not in glyph:
        return []

    name          = glyph["effect"]["name"]
    configuration = glyph["effect"]["settings"]

    effect_information = EffectsConfig.get(name)
    if not effect_information:
        return []

    effect_function   = effect_information["function"]
    settings_metadata = effect_information["settings"]
    keyword_arguments = parse_effect_arguments(configuration, settings_metadata)

    return effect_function(
        glyph,
        model,
        bpm,
        **keyword_arguments
    )

# Simple Effects

def fade_effect(
        glyph:  dict,
        model:  str | None,
        bpm:    int | float,
        mode:   str,
        easing: str
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)

    if not target_segments:
        return []

    event = create_glyph_event(
        track     = glyph_data["track"],
        start     = glyph_data["start"],
        duration  = glyph_data["duration"],
        segments  = glyph_data["active_segments"],
        keyframes = glyph["effect"]["settings"]["keyframes"],
        easing    = easing
    )
    event["mode"] = mode

    return [event]

def strobe_effect(
        glyph:             dict,
        model:             str | None,
        bpm:               int | float,
        frequency:         int | float = 1,
        duty_cycle:        int | float = 50,
        first_brightness:  int = 100,
        second_brightness: int = 0,
        bpm_snap:          int | float | bool = False
    ) -> list[dict]:

    if bpm_snap:
        frequency = (bpm / 60) * float(bpm_snap)

    glyph_data = extract_glyph_data(glyph, model)

    if frequency <= 0 or glyph_data["duration"] <= 0:
        return []

    duty_ratio   = max(0.05, min(0.95, float(duty_cycle) / 100.0))
    interval     = 1000.0 / frequency
    current_time = glyph_data["start"]
    output       = []

    while current_time < glyph_data["end"]:
        first_duration  = min(interval * duty_ratio, glyph_data["end"] - current_time)
        time_off        = current_time + first_duration
        second_duration = min(interval * (1.0 - duty_ratio), glyph_data["end"] - time_off)

        if first_duration > 0:
            output.append(
                create_glyph_event(
                    track      = glyph_data["track"],
                    start      = current_time,
                    duration   = first_duration,
                    segments   = glyph_data["active_segments"],
                    brightness = first_brightness
                )
            )

        if second_duration > 0:
            output.append(
                create_glyph_event(
                    track      = glyph_data["track"],
                    start      = time_off,
                    duration   = second_duration,
                    segments   = glyph_data["active_segments"],
                    brightness = second_brightness
                )
            )

        current_time += interval

    return output

# Tempo Effects

def bpm_effect(
        glyph:         dict,
        model:         str | None,
        bpm:           int | float,
        multiplier:    int | float,
        mode:          str = "Standard",
        decay_length:  int | float = 50,
        enable_fading: bool = True
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)
    if not target_segments or bpm <= 0 or multiplier <= 0 or glyph_data["duration"] <= 0:
        return []

    actual_bpm     = bpm * multiplier
    beat_interval  = 60000.0 / actual_bpm
    current_time   = glyph_data["start"]
    brightness     = glyph_data["brightness"]
    dim_brightness = max(5, int(brightness * 0.2))
    decay_ratio    = max(0.1, min(1.0, float(decay_length) / 100.0))
    tick_counter   = 0
    output         = []

    segment_count   = len(target_segments)
    center_position = (segment_count - 1) / 2.0
    max_distance    = max(1.0, center_position)

    while current_time < glyph_data["end"]:
        beat_end     = min(current_time + beat_interval, glyph_data["end"])
        sub_duration = beat_end - current_time

        if sub_duration <= 0:
            break

        current_brightness = brightness

        if enable_fading and multiplier > 1:
            tick_counter += 1

            if tick_counter % int(multiplier) != 1:
                current_brightness = dim_brightness

        if mode == "Standard":
            pulse_duration = min(sub_duration * decay_ratio, beat_interval * decay_ratio)
            output.append(
                create_glyph_event(
                    track     = glyph_data["track"],
                    start     = current_time,
                    duration  = pulse_duration,
                    segments  = glyph_data["active_segments"],
                    keyframes = [(0.0, current_brightness), (1.0, 0)],
                    easing    = "linear"
                )
            )

        elif mode == "Punch":
            punch_ratio    = min(0.45, decay_ratio * 0.6)
            punch_duration = min(sub_duration * punch_ratio, beat_interval * punch_ratio)
            hold_point     = min(0.18, 25.0 / max(1.0, punch_duration))

            output.append(
                create_glyph_event(
                    track     = glyph_data["track"],
                    start     = current_time,
                    duration  = punch_duration,
                    segments  = glyph_data["active_segments"],
                    keyframes = [
                        (0.0, current_brightness),
                        (hold_point, current_brightness),
                        (0.45, int(current_brightness * 0.15)),
                        (1.0, 0)
                    ],
                    easing    = "linear"
                )
            )

        elif mode == "Dispersion":
            for index, segment_index in enumerate(target_segments):
                distance_ratio   = abs(index - center_position) / max_distance
                segment_duration = max(15.0, sub_duration * decay_ratio * (0.25 + 0.75 * distance_ratio))
                hold_ratio       = max(0.08, 0.35 * distance_ratio)

                output.append(
                    create_glyph_event(
                        track     = glyph_data["track"],
                        start     = current_time,
                        duration  = segment_duration,
                        segments  = [segment_index],
                        keyframes = [
                            (0.0, current_brightness),
                            (hold_ratio, current_brightness),
                            (1.0, 0)
                        ],
                        easing    = "linear"
                    )
                )

        elif mode == "Pumping":
            active_duration = min(sub_duration * decay_ratio, beat_interval * decay_ratio)
            active_start    = current_time + (sub_duration - active_duration)

            output.append(
                create_glyph_event(
                    track     = glyph_data["track"],
                    start     = active_start,
                    duration  = active_duration,
                    segments  = glyph_data["active_segments"],
                    keyframes = [
                        (0.0, 0),
                        (0.6, int(current_brightness * 0.25)),
                        (1.0, current_brightness)
                    ],
                    easing    = "linear"
                )
            )

        elif mode == "Heartbeat":
            first_pulse_duration  = min(sub_duration * 0.35 * decay_ratio, beat_interval * 0.35 * decay_ratio)
            second_pulse_duration = min(sub_duration * 0.45 * decay_ratio, beat_interval * 0.45 * decay_ratio)
            second_pulse_start    = current_time + sub_duration * 0.4

            output.append(
                create_glyph_event(
                    track     = glyph_data["track"],
                    start     = current_time,
                    duration  = first_pulse_duration,
                    segments  = glyph_data["active_segments"],
                    keyframes = [(0.0, int(current_brightness * 0.6)), (1.0, 0)],
                    easing    = "linear"
                )
            )

            if second_pulse_start < glyph_data["end"]:
                output.append(
                    create_glyph_event(
                        track     = glyph_data["track"],
                        start     = second_pulse_start,
                        duration  = min(second_pulse_duration, glyph_data["end"] - second_pulse_start),
                        segments  = glyph_data["active_segments"],
                        keyframes = [(0.0, current_brightness), (1.0, 0)],
                        easing    = "linear"
                    )
                )

        current_time += beat_interval

    return output

def sparkle_effect(
        glyph:      dict,
        model:      str | None,
        bpm:        int | float,
        multiplier: int | float,
        density:    int = 1,
        fade_out:   bool = True
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)

    if not target_segments or bpm <= 0 or multiplier <= 0 or glyph_data["duration"] <= 0:
        return []

    frequency        = (bpm * multiplier) / 60.0
    interval         = 1000.0 / frequency
    current_time     = glyph_data["start"]
    sample_count     = max(1, min(density, len(target_segments)))
    keyframes_value  = [(0.0, glyph_data["brightness"]), (1.0, 0)] if fade_out else None
    brightness_value = None if fade_out else glyph_data["brightness"]
    easing_value     = "linear" if fade_out else None
    output           = []

    while current_time < glyph_data["end"] - 1e-9:
        next_time     = min(current_time + interval, glyph_data["end"])
        step_duration = next_time - current_time
        chosen_points = random.sample(target_segments, sample_count)

        output.append(
            create_glyph_event(
                track      = glyph_data["track"],
                start      = current_time,
                duration   = step_duration,
                segments   = sorted(chosen_points),
                brightness = brightness_value,
                keyframes  = keyframes_value,
                easing     = easing_value
            )
        )

        current_time = next_time

    return output

# Segment Effects

def sidebeat_effect(
        glyph: dict,
        model: str | None,
        bpm:   int | float,
        part:  str
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)
    total_count     = len(target_segments)

    if total_count == 0 or glyph_data["duration"] <= 0:
        return []

    if total_count < 3:
        return [
            create_glyph_event(
                track      = glyph_data["track"],
                start      = glyph_data["start"],
                duration   = glyph_data["duration"],
                segments   = target_segments,
                brightness = 100
            )
        ]

    segments_in_one_part = max(1, total_count // 3)
    time_per_segment     = glyph_data["duration"] / segments_in_one_part / 2.0

    left_part  = target_segments[:segments_in_one_part]
    right_part = list(reversed(target_segments[-segments_in_one_part:]))

    part_modes = {
        "left":  [left_part],
        "right": [right_part],
        "both":  [left_part, right_part]
    }

    segments_groups = part_modes.get(part, [left_part, right_part])
    output          = []

    for part_segments in segments_groups:
        for segment_step_index, segment_index in enumerate(part_segments):
            shrink_offset    = time_per_segment * segment_step_index
            segment_start    = glyph_data["start"] + shrink_offset
            segment_duration = glyph_data["duration"] - 2 * shrink_offset

            if segment_duration <= 0:
                continue

            output.append(
                create_glyph_event(
                    track      = glyph_data["track"],
                    start      = segment_start,
                    duration   = segment_duration,
                    segments   = [segment_index],
                    brightness = 100
                )
            )

    return output

def fill_effect(
        glyph:  dict,
        model:  str | None,
        bpm:    int | float,
        side:   int = 1,
        invert: bool = False
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)

    if not target_segments or glyph_data["duration"] <= 0:
        return []

    if side == 1:
        ordered_segments = target_segments

    else:
        ordered_segments = list(reversed(target_segments))

    segment_step = glyph_data["duration"] / len(ordered_segments)
    output       = []

    if invert:
        keyframes_value = [(0.0, glyph_data["brightness"]), (1.0, 0)]

    else:
        keyframes_value = [(0.0, 0), (1.0, glyph_data["brightness"])]

    for step_index, segment_index in enumerate(ordered_segments):
        step_start    = glyph_data["start"] + step_index * segment_step
        step_duration = glyph_data["end"] - step_start

        output.append(
            create_glyph_event(
                track     = glyph_data["track"],
                start     = step_start,
                duration  = step_duration,
                segments  = [segment_index],
                keyframes = keyframes_value,
                easing    = "linear"
            )
        )

    return output

def random_fill_effect(
        glyph:    dict,
        model:    str | None,
        bpm:      int | float,
        bpm_snap: int | float | bool = False,
        mode:     str = "Fill"
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)

    if not target_segments or glyph_data["duration"] <= 0:
        return []

    shuffled_segments = list(target_segments)
    random.shuffle(shuffled_segments)

    if bpm_snap:
        step_duration = 60000.0 / (bpm * float(bpm_snap))

    else:
        step_duration = glyph_data["duration"] / len(shuffled_segments)

    output = []

    for step_index, segment_index in enumerate(shuffled_segments):
        step_start = glyph_data["start"] + step_index * step_duration

        if step_start >= glyph_data["end"]:
            break

        if mode == "Fill":
            start_time          = step_start
            calculated_duration = glyph_data["end"] - step_start

        else:
            start_time          = glyph_data["start"]
            calculated_duration = step_start - glyph_data["start"]

        if calculated_duration <= 0:
            continue

        output.append(
            create_glyph_event(
                track      = glyph_data["track"],
                start      = start_time,
                duration   = calculated_duration,
                segments   = [segment_index],
                brightness = glyph_data["brightness"]
            )
        )

    return output

# Pattern Effects

def glitch_effect(
        glyph:                dict,
        model:                str | None,
        bpm:                  int | float,
        fps:                  float = 20.0,
        duty_cycle:           float = 0.7,
        min_brightness_ratio: float = 0.3,
        cluster_mode:         str = "Scattered",
        bpm_snap:             int | float | bool = False,
        enable_fade_out:      bool = False
    ) -> list[dict]:

    if bpm_snap:
        fps = (bpm / 60) * float(bpm_snap)

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)
    segment_count   = len(target_segments)

    if segment_count == 0 or fps <= 0 or glyph_data["duration"] <= 0:
        return []

    ratio_multiplier = min_brightness_ratio / 100.0
    frame_duration   = 1000.0 / fps
    current_time     = glyph_data["start"]
    min_brightness   = max(5, int(glyph_data["brightness"] * ratio_multiplier))
    count_to_sample  = max(1, min(segment_count, int(segment_count * duty_cycle)))
    output           = []

    while current_time < glyph_data["end"] - 1e-9:
        next_time     = min(current_time + frame_duration, glyph_data["end"])
        step_duration = next_time - current_time

        if cluster_mode == "Clustered":
            cluster_start = random.randint(0, max(0, segment_count - count_to_sample))
            chosen        = target_segments[cluster_start:cluster_start + count_to_sample]

        else:
            chosen = random.sample(target_segments, count_to_sample)

        if min_brightness >= glyph_data["brightness"]:
            current_brightness = glyph_data["brightness"]

        else:
            current_brightness = random.randint(min_brightness, glyph_data["brightness"])

        keyframes_value  = [(0.0, current_brightness), (1.0, 0)] if enable_fade_out else None
        brightness_value = None if enable_fade_out else current_brightness
        easing_value     = "linear" if enable_fade_out else None

        output.append(
            create_glyph_event(
                track      = glyph_data["track"],
                start      = current_time,
                duration   = step_duration,
                segments   = sorted(list(set(chosen))),
                brightness = brightness_value,
                keyframes  = keyframes_value,
                easing     = easing_value
            )
        )

        current_time = next_time

    return output

def ripple_effect(
        glyph:         dict,
        model:         str | None,
        bpm:           int | float,
        tail:          int = 4,
        center_offset: int | float = 50.0
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)
    segment_count   = len(target_segments)

    if segment_count == 0 or glyph_data["duration"] <= 0:
        return []

    offset_ratio    = max(0.0, min(100.0, float(center_offset))) / 100.0
    center_position = int(round(offset_ratio * (segment_count - 1)))
    center_indices  = [center_position]

    actual_duration  = glyph_data["duration"]
    max_radius_glyph = max(center_position, (segment_count - 1) - center_position)
    max_total_radius = max_radius_glyph + tail

    if max_radius_glyph <= 0:
        full_duration = actual_duration

    else:
        full_duration = (max_total_radius / max_radius_glyph) * actual_duration

    full_duration = min(full_duration, actual_duration)

    if full_duration <= 1e-12:
        return []

    frame_duration = 20.0
    current_time   = glyph_data["start"]
    end_time       = glyph_data["start"] + full_duration
    output         = []

    while current_time < end_time - 1e-9:
        next_time     = min(current_time + frame_duration, end_time)
        step_interval = next_time - current_time
        elapsed_time  = current_time - glyph_data["start"]
        progress      = elapsed_time / full_duration
        radius        = int(progress * max_total_radius)

        for offset in range(max(0, radius - tail), radius):
            distance       = radius - offset
            decay          = 1.0 - (distance / max(1, tail))
            decayed_bright = max(0, int(glyph_data["brightness"] * decay))
            left_index     = center_indices[0] - offset
            right_index    = center_indices[-1] + offset
            tail_segments  = []

            if 0 <= left_index < segment_count:
                tail_segments.append(target_segments[left_index])

            if 0 <= right_index < segment_count and right_index != left_index:
                tail_segments.append(target_segments[right_index])

            for segment_item in tail_segments:
                output.append(
                    create_glyph_event(
                        track      = glyph_data["track"],
                        start      = current_time,
                        duration   = step_interval,
                        segments   = [segment_item],
                        brightness = decayed_bright
                    )
                )

        head_segments = []
        left_head     = center_indices[0] - radius
        right_head    = center_indices[-1] + radius

        if 0 <= left_head < segment_count:
            head_segments.append(target_segments[left_head])

        if 0 <= right_head < segment_count and right_head != left_head:
            head_segments.append(target_segments[right_head])

        if head_segments:
            output.append(
                create_glyph_event(
                    track      = glyph_data["track"],
                    start      = current_time,
                    duration   = step_interval,
                    segments   = head_segments,
                    brightness = glyph_data["brightness"]
                )
            )

        current_time = next_time

    return output

def chase_effect(
        glyph:     dict,
        model:     str | None,
        bpm:       int | float,
        width:     int  = 3,
        direction: int  = 1,
        gap:       int  = 0,
        tail_fade: bool = False,
        invert:    bool = False
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)
    segment_count   = len(target_segments)

    if segment_count == 0 or glyph_data["duration"] <= 0:
        return []

    width_clamped   = max(1, width)
    gap_clamped     = max(0, gap)
    effective_width = width_clamped + (width_clamped - 1) * gap_clamped
    total_steps     = segment_count + effective_width - 1

    if total_steps <= 0:
        return []

    step_time    = glyph_data["duration"] / total_steps
    current_time = glyph_data["start"]
    output       = []

    for step_index in range(total_steps):
        segments_ordered = []

        for width_index in range(width_clamped):
            offset = width_index * (1 + gap_clamped)

            if direction == 1:
                target_index = step_index - offset

            else:
                target_index = (segment_count - 1) - (step_index - offset)

            if 0 <= target_index < segment_count:
                segments_ordered.append((target_segments[target_index], width_index))

        if not segments_ordered:
            current_time += step_time
            continue

        active_indices = [segment_index for segment_index, _ in segments_ordered]

        if invert:
            inverted_set = [seg for seg in target_segments if seg not in active_indices]

            if inverted_set:
                output.append(
                    create_glyph_event(
                        track      = glyph_data["track"],
                        start      = current_time,
                        duration   = step_time,
                        segments   = sorted(inverted_set),
                        brightness = glyph_data["brightness"]
                    )
                )

        elif tail_fade:
            for segment_index, width_index in segments_ordered:
                decay_factor = 1.0 - (width_index / width_clamped) * 0.85
                segment_brightness = max(5, int(glyph_data["brightness"] * decay_factor))

                output.append(
                    create_glyph_event(
                        track      = glyph_data["track"],
                        start      = current_time,
                        duration   = step_time,
                        segments   = [segment_index],
                        brightness = segment_brightness
                    )
                )

        else:
            output.append(
                create_glyph_event(
                    track      = glyph_data["track"],
                    start      = current_time,
                    duration   = step_time,
                    segments   = sorted(list(set(active_indices))),
                    brightness = glyph_data["brightness"]
                )
            )

        current_time += step_time
        if current_time > glyph_data["end"]:
            break

    return output

def zebra_effect(
        glyph:     dict,
        model:     str | None,
        bpm:       int | float,
        fps:       int | float = 1,
        on_count:  int = 1,
        off_count: int = 1,
        side:      int = 1,
        bpm_snap:  int | float | bool = False
    ) -> list[dict]:

    if bpm_snap:
        fps = (bpm / 60) * float(bpm_snap)

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)

    if not target_segments or fps <= 0 or glyph_data["duration"] <= 0:
        return []

    step_duration  = 1000.0 / fps
    total_steps    = max(1, int(glyph_data["duration"] / step_duration))
    pattern_length = on_count + off_count
    output         = []

    for step_index in range(total_steps):
        time_start    = glyph_data["start"] + step_index * step_duration
        time_end      = min(time_start + step_duration, glyph_data["end"])
        step_interval = time_end - time_start

        if step_interval <= 0:
            continue

        lit_segments = []

        for index, segment_index in enumerate(target_segments):
            shifted_index = (index - step_index * side) % pattern_length
            is_lit        = shifted_index < on_count

            if is_lit:
                lit_segments.append(segment_index)

        if lit_segments:
            output.append(
                create_glyph_event(
                    track      = glyph_data["track"],
                    start      = time_start,
                    duration   = step_interval,
                    segments   = lit_segments,
                    brightness = glyph_data["brightness"]
                )
            )

    return output

def shocker_effect(
        glyph:     dict,
        model:     str | None,
        bpm:       int | float,
        frequency: float = 5.0,
        fade_out:  bool = True,
        bpm_snap:  int | float | bool = False
    ) -> list[dict]:

    if bpm_snap:
        frequency = (bpm / 60) * float(bpm_snap)

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)

    if not target_segments or frequency <= 0 or glyph_data["duration"] <= 0:
        return []

    interval     = 1000.0 / frequency
    current_time = glyph_data["start"]
    output       = []

    even_segments = [segment for index, segment in enumerate(target_segments) if index % 2 == 0]
    odd_segments  = [segment for index, segment in enumerate(target_segments) if index % 2 == 1]

    if not odd_segments:
        odd_segments = even_segments

    while current_time < glyph_data["end"]:
        time_half     = min(current_time + interval / 2.0, glyph_data["end"])
        time_next     = min(current_time + interval, glyph_data["end"])
        first_period  = time_half - current_time
        second_period = time_next - time_half

        keyframes_value  = [(0.0, glyph_data["brightness"]), (1.0, 0)] if fade_out else None
        brightness_value = None if fade_out else glyph_data["brightness"]
        easing_value     = "linear" if fade_out else None

        if first_period > 0 and even_segments:
            output.append(
                create_glyph_event(
                    track      = glyph_data["track"],
                    start      = current_time,
                    duration   = first_period,
                    segments   = even_segments,
                    brightness = brightness_value,
                    keyframes  = keyframes_value,
                    easing     = easing_value
                )
            )

        if second_period > 0 and odd_segments:
            output.append(
                create_glyph_event(
                    track      = glyph_data["track"],
                    start      = time_half,
                    duration   = second_period,
                    segments   = odd_segments,
                    brightness = brightness_value,
                    keyframes  = keyframes_value,
                    easing     = easing_value
                )
            )

        current_time = time_next

    return output

# Motion Effects

def calculate_tail_brightness(
        head_brightness: int,
        tail_position:   int,
        tail_length:     int
    ) -> int:

    if tail_position == 0 or tail_length <= 1:
        return head_brightness

    min_brightness = max(5, int(head_brightness * 0.05))
    span           = head_brightness - min_brightness
    decay_factor   = tail_position / (tail_length - 1)

    return max(min_brightness, int(head_brightness - span * decay_factor))

def boomerang_effect(
        glyph: dict,
        model: str | None,
        bpm:   int | float,
        jumps: int
    ) -> list[dict]:

    glyph_data      = extract_glyph_data(glyph, model)
    target_segments = resolve_target_segments(glyph_data)
    segment_count   = len(target_segments)

    if segment_count == 0 or glyph_data["duration"] <= 0:
        return []

    actual_jumps  = jumps + 2
    growth_range  = segment_count - 1
    steps_to_grow = max(1, actual_jumps - 1)
    tail_step     = max(1, round(growth_range / steps_to_grow))

    output       = []
    tail_length  = 1
    direction    = -1
    virtual_head = segment_count - 1
    current_time = glyph_data["start"]

    while current_time < glyph_data["end"] - 1e-9:
        step_time = glyph_data["duration"] / (actual_jumps * (segment_count + tail_length))
        next_time = current_time + step_time

        segments_to_light = [
            (virtual_head + position if direction == -1 else virtual_head - position, position)
            for position in range(tail_length)
        ]

        for segment_position, tail_position in segments_to_light:
            if 0 <= segment_position < segment_count:
                calculated_brightness = calculate_tail_brightness(
                    glyph_data["brightness"],
                    tail_position,
                    tail_length
                )

                output.append(
                    create_glyph_event(
                        track      = glyph_data["track"],
                        start      = current_time,
                        duration   = step_time,
                        segments   = [target_segments[segment_position]],
                        brightness = calculated_brightness
                    )
                )

        virtual_head += direction

        is_left_turn  = direction == -1 and (virtual_head + tail_length - 1 < 0)
        is_right_turn = direction == 1 and (virtual_head - tail_length + 1 >= segment_count)

        if is_left_turn or is_right_turn:
            remaining_time = glyph_data["end"] - next_time
            estimated_step = step_time * (segment_count + tail_length + tail_step)

            if remaining_time > estimated_step:
                tail_length  = min(tail_length + tail_step, segment_count)
                direction   *= -1
                virtual_head = (segment_count - 1) if direction == -1 else 0

        current_time = next_time

    return output

# Configuration And Utilities

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
        "supports_segmentation": True,
        "function":              fill_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Side",
                "key":     "side",
                "map":     {"To the left": -1, "To the right": 1},
                "default": "To the left"
            },
            {
                "type":    "checkbox",
                "title":   "Invert (Dark Fill)",
                "key":     "invert",
                "default": False
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
                    "Disabled": False,
                    "BPM x0.5": 0.5,
                    "BPM x1":   1,
                    "BPM x2":   2,
                    "BPM x4":   4
                },
                "default": "Disabled"
            }
        ]
    },

    "Zebra": {
        "segmented":             True,
        "supports_segmentation": True,
        "function":              zebra_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Snap to BPM",
                "key":     "bpm_snap",
                "map": {
                    "Disabled": False,
                    "BPM x0.5": 0.5,
                    "BPM x1":   1,
                    "BPM x2":   2,
                    "BPM x4":   4
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
                "type":    "slider",
                "title":   "Density",
                "key":     "density",
                "min":     1,
                "max":     5,
                "offset":  1,
                "default": 1
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
                    "Disabled": False,
                    "BPM x0.5": 0.5,
                    "BPM x1":   1,
                    "BPM x2":   2,
                    "BPM x4":   4
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
                "title":   "Duty Cycle (%)",
                "key":     "duty_cycle",
                "min":     5,
                "max":     95,
                "offset":  5,
                "default": 50
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
        "supports_segmentation": True,
        "function":              shocker_effect,
        "settings": [
            {
                "type":    "selector",
                "title":   "Snap to BPM",
                "key":     "bpm_snap",
                "map": {
                    "Disabled": False,
                    "BPM x0.5": 0.5,
                    "BPM x1":   1,
                    "BPM x2":   2,
                    "BPM x4":   4
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
                    "Disabled": False,
                    "BPM x0.5": 0.5,
                    "BPM x1":   1,
                    "BPM x2":   2,
                    "BPM x4":   4
                },
                "default": "Disabled"
            },
            {
                "type":    "selector",
                "title":   "Cluster Mode",
                "key":     "cluster_mode",
                "map": {
                    "Scattered": "Scattered",
                    "Clustered": "Clustered"
                },
                "default": "Scattered"
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
                "title":   "Mode",
                "key":     "mode",
                "map": {
                    "Standard":   "Standard",
                    "Punch":      "Punch",
                    "Dispersion": "Dispersion",
                    "Pumping":    "Pumping",
                    "Heartbeat":  "Heartbeat"
                },
                "default": "Standard"
            },
            {
                "type":    "slider",
                "title":   "Decay Length (%)",
                "key":     "decay_length",
                "min":     10,
                "max":     100,
                "offset":  5,
                "default": 50
            },
            {
                "type":    "selector",
                "title":   "Multiplier",
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
        "supports_segmentation": True,
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
        "supports_segmentation": True,
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
        "supports_segmentation": True,
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
            },
            {
                "type":    "checkbox",
                "title":   "Tail Gradient Fade",
                "key":     "tail_fade",
                "default": False
            },
            {
                "type":    "checkbox",
                "title":   "Invert (Dark Wave)",
                "key":     "invert",
                "default": False
            }
        ]
    },

    "Ripple": {
        "segmented":             True,
        "supports_segmentation": True,
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
            },
            {
                "type":    "slider",
                "title":   "Center Offset (%)",
                "key":     "center_offset",
                "min":     0,
                "max":     100,
                "offset":  5,
                "default": 50
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
        name: configuration for name, configuration in EffectsConfig.items()
        if not configuration.get("segmented", False)
    }

def get_segmented_effects() -> dict:
    return {
        name: configuration for name, configuration in EffectsConfig.items()
        if configuration.get("segmented", False)
    }

def get_segmentation_supported_effects() -> dict:
    return {
        name: configuration for name, configuration in EffectsConfig.items()
        if configuration.get("supports_segmentation", False)
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
        track:      str = "1",
        brightness: int = 100,
        duration:   int = 100,
        start:      int = 0,
        effect:     dict | None = None
    ) -> dict:

    glyph_dictionary = {
        "track":      track,
        "brightness": brightness,
        "duration":   duration,
        "start":      start
    }

    if effect:
        glyph_dictionary["effect"] = effect

    return glyph_dictionary