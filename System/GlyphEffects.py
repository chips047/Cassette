import random

from System.Constants import *

_example_glyph = {
    "start": 200,
    "duration": 2000,
    "track": "2",
    "brightness": 100,
    "effect": "KITTTYYY!"
}

def parse_effect_args(config: dict, settings_meta: dict) -> dict:
    args = {}

    for meta in settings_meta:
        try:
            arg_name = meta.get("key")
            if not arg_name:
                continue

            value = config.get(meta["key"], 1)
            args[arg_name] = value
        
        except Exception as e:
            print(f"ERROR FOUND - - - {str(e)}")

    return args

def effect_to_glyph(element, bpm = None, model = None):
    name = element["effect"]["name"]
    config = element["effect"]["settings"]

    if name == "None": return []

    effect_info = EffectsConfig[name]
    effect_fn = effect_info.get("function")
    settings_meta = effect_info.get("settings", {})
    kwargs = parse_effect_args(config, settings_meta)
    
    result = effect_fn(element, model, bpm = bpm, **kwargs)
    return result

def effectCallback(name, settings, element):
    if name == "None":
        if "effect" in element:
            del element["effect"]
            return element
    
    element["effect"] = {
        "name": name,
        "settings": settings
    }
    
    return element

def get_data(glyph: dict, model: str, segmented = False):
    start = glyph["start"]
    duration = glyph["duration"]
    end = start + duration

    n = glyph["track"]
    brightness = int(glyph["brightness"])
    segs = None
    turned_on_segs = glyph.get("segments")

    if model == "PREVIEW":
        segs = 30
    
    else:
        segs = ModelSegments[model].get(n)

    return n, segs, duration, start, end, brightness, turned_on_segs

def fade_template(glyph: dict, model: str, bpm: int, steps: list[tuple[int, int]]):
    n, segs, duration, start, end, brightness, turned_on_segs = get_data(glyph, model)

    result = []
    step_duration = duration // len(steps)
    current_start = start

    for b, eb in steps:
        item = {
            "start": current_start,
            "duration": step_duration,
            "track": n,
            "brightness": b if b != "auto" else brightness,
            "end_brightness": eb if eb != "auto" else brightness,
        }
        
        if turned_on_segs:
            item["segments"] = turned_on_segs
        
        result.append(item)
        current_start += step_duration

    return result

def fade_in(glyph: dict, model: str, bpm: int):
    return fade_template(glyph, model, bpm, [(0, "auto")])

def fade_out(glyph: dict, model: str, bpm: int):
    return fade_template(glyph, model, bpm, [("auto", 0)])

def fade_in_out(glyph: dict, model: str, bpm: int):
    return fade_template(glyph, model, bpm, [(0, "auto"), ("auto", 0)])

def sidebeat(glyph: dict, model: str, bpm: int, part: str):
    n, segs, duration, start, end, brightness, turned_on_segs = get_data(glyph, model, True)
    segment_list = list(range(1, segs + 1))
    segments_in_one_part = segs // 3
    time_per_segment = duration / segments_in_one_part / 2

    left_part = segment_list[0:segments_in_one_part]
    right_part = segment_list[-segments_in_one_part:]

    part_modes = {
        "left": ([left_part], 1),
        "right": ([right_part], segs),
        "both": ([left_part, right_part], [1, segs])
    }

    segments_to_animate, current_segments = part_modes[part]
    if not isinstance(current_segments, list):
        current_segments = [current_segments] * len(segments_to_animate)

    out = []

    for part, base_segment in zip(segments_to_animate, current_segments):
        direction = 1 if base_segment == 1 else -1
    
        for i, _ in enumerate(part):
            shrink = time_per_segment * i
    
            out.append({
                "start": start + shrink,
                "duration": (end - start) - 2 * shrink,
                "track": str(n),
                "segments": [(base_segment + i * direction) - 1],
                "brightness": 100
            })
    
    return out

#def volume(glyph: dict, model: str, bpm: int, audiosegment):

def fade_to(glyph: dict, model: str, bpm: int, fade_to_brightness = 100):
    n, segs, duration, start, end, brightness, turned_on_segs = get_data(glyph, model, True)
    
    item = {"start": start, "duration": duration, "brightness": brightness, "end_brightness": fade_to_brightness, "track": n}
    if turned_on_segs:
        item["segments"] = turned_on_segs
    
    return [item]

def glitch(glyph: dict, model: str, bpm: int, fps = 20.0, duty_cycle = 0.7, min_br_ratio = 0.3, bpm_snap=False, enable_fadeout = False):
    if bpm_snap:
        fps = (bpm / 60) * bpm_snap
    
    min_br_ratio /= 100

    n, segs, duration, t, t_end, head_br, turned_on_segs = get_data(glyph, model, True)
    frame = 1000.0 / fps
    out = []

    min_br = max(5, int(head_br * min_br_ratio))
    available_segments = glyph.get("segments", list(range(segs)))
    count = int(len(available_segments) * duty_cycle)

    while t < t_end - 1e-9:
        t0 = t
        t1 = min(t + frame, t_end)

        chosen = random.sample(available_segments, count)
        br = random.randint(min_br, head_br)

        item = {
            "start": t0,
            "duration": t1 - t0,
            "track": str(n),
            "segments": list(set(chosen)),
            "brightness": br
        }

        if enable_fadeout:
            item["end_brightness"] = 0

        out.append(item)
        t = t1

    return out

def ripple(glyph: dict, model: str, bpm: int, tail=4, clip_to_duration=True):
    n, segs, duration, start, end, br, turned_on_segs = get_data(glyph, model, True)
    if segs is None or segs <= 0 or (end - start) <= 0:
        return []

    center_indices = []
    if segs % 2 == 1:
        center_indices.append(segs // 2)
    else:
        center_indices.append(segs // 2 - 1)
        center_indices.append(segs // 2)

    actual_duration = end - start
    max_radius_glyph = max(center_indices[-1], segs - 1 - center_indices[0])

    max_total_radius = max_radius_glyph + tail

    if max_radius_glyph <= 0:
        full_duration = actual_duration
    else:
        full_duration = (max_total_radius / max_radius_glyph) * actual_duration

    full_duration = min(full_duration, actual_duration)

    if full_duration <= 1e-12:
        return []

    frame = 20
    t = start
    out = []

    end_time = start + full_duration

    while t < end_time - 1e-9:
        t1 = min(t + frame, end_time)
        elapsed = t - start

        progress = elapsed / full_duration
        radius = int(progress * max_total_radius)

        active_segs = set()

        for r in range(radius + 1):
            left = center_indices[0] - r
            right = center_indices[-1] + r

            if 0 <= left < segs:
                active_segs.add(left)
            if 0 <= right < segs:
                active_segs.add(right)

        for r in range(max(0, radius - tail), radius):
            dist = radius - r
            decay = 1.0 - (dist / max(1, tail))
            br_now = max(0, int(br * decay))

            left = center_indices[0] - r
            right = center_indices[-1] + r

            inds = []
            if 0 <= left < segs:
                inds.append(left)
            if 0 <= right < segs and right != left:
                inds.append(right)

            for i in inds:
                out.append({
                    "start": t,
                    "duration": t1 - t,
                    "track": str(n),
                    "segments": [i],
                    "brightness": br_now
                })

        head_segs = []
        left = center_indices[0] - radius
        right = center_indices[-1] + radius

        if 0 <= left < segs:
            head_segs.append(left)
        
        if 0 <= right < segs and right != left:
            head_segs.append(right)

        if head_segs:
            out.append({
                "start": t,
                "duration": t1 - t,
                "track": str(n),
                "segments": head_segs,
                "brightness": br
            })

        t = t1

    return out


def bpm_effect(glyph: dict, model: str, bpm: float, multiplier: int, enable_fading: bool):
    n, segs, duration, start, end, br, turned_on_segs = get_data(glyph, model)

    actual_bpm = bpm * multiplier
    beat_interval = 60000.0 / actual_bpm
    t = start
    out = []

    brightness = br
    dim_brightness = max(5, br * 0.2)
    tick = 0

    while t < end:
        if enable_fading:
            if multiplier <= 1:
                brightness = br
            
            else:
                tick += 1
                
                if tick % multiplier == 1:
                    brightness = br
                else:
                    brightness = dim_brightness

        t_off = min(t + beat_interval / 2, end)
        glyph = {
            "start": t,
            "duration": t_off - t,
            "track": n,
            "brightness": brightness,
            "end_brightness": 0
        }

        if turned_on_segs:
            glyph["segments"] = turned_on_segs

        out.append(glyph)
        
        t += beat_interval

    return out

def fill(glyph: dict, model: str, bpm: int, side=1):
    n, segs, duration, start, end, brightness, _ = get_data(glyph, model, True)

    seg_step = duration / segs
    indices = list(range(segs))[:: (1 if side == 1 else -1)]

    events = []
    for out_idx, i in enumerate(indices):
        s = start + out_idx * seg_step
        dur = end - s
        events.append({
            "start": s,
            "duration": dur,
            "track": str(n),
            "segments": [i],
            "brightness": 0,
            "end_brightness": brightness
        })
    return events

def chase(glyph: dict, model: str, bpm: int, width = 2, direction = 1):
    n, segs, duration, start, end, br, turned_on_segs = get_data(glyph, model, True)
    if not segs:
        return []

    width = max(1, width)

    total_steps = segs + width - 1
    if total_steps <= 0:
        return []
        
    step_t = duration / total_steps

    out = []
    t = start

    for step in range(total_steps):
        segs_to_light = []
        for i in range(width):
            if direction == 1:
                idx = step - i
            
            else:
                idx = (segs - 1) - (step - i)
            
            if 0 <= idx < segs:
                segs_to_light.append(idx)

        if segs_to_light:
            out.append({
                "start": t,
                "duration": step_t,
                "track": str(n),
                "segments": sorted(list(set(segs_to_light))),
                "brightness": br
            })

        t += step_t
        if t > end:
            break

    return out

def strobe(glyph: dict, model: str, bpm: int, frequency = 1):
    n, segs, duration, start, end, brightness, turned_on_segs = get_data(glyph, model)
    interval = 1000.0 / frequency
    t = start
    out = []

    while t < end:
        t_off = min(t + interval / 2, end)
        item = {
            "start": t,
            "duration": t_off - t,
            "track": n,
            "brightness": brightness
        }

        if turned_on_segs:
            item["segments"] = turned_on_segs

        out.append(item)
        t += interval

    return out

def soft_or_pseudo_strobe(glyph: dict, model: str, bpm: int, frequency = 1, first_brightness = 100, second_brightness = 70, bpm_snap = False):
    if bpm_snap:
        frequency = (bpm / 60) * bpm_snap

    n, _, _, start, end, _, turned_on_segs = get_data(glyph, model)
    interval = 1000.0 / frequency
    t = start
    out = []

    while t < end:
        t_off = min(t + interval / 2, end)
        duration = t_off - t

        items = [
            {
                "start": t,
                "duration": duration,
                "track": n,
                "brightness": first_brightness
            },
            {
                "start": t_off,
                "duration": duration,
                "track": n,
                "brightness": second_brightness
            }
        ]

        if turned_on_segs:
            for item in items:
                item["segments"] = turned_on_segs

        for item in items:
            out.append(item)
        
        t += interval

    return out

def sweep(glyph: dict, model: str, bpm: int, side=1):
    n, segs, duration, start, _, brightness, turned_on_segs = get_data(glyph, model, True)

    if side == 1:
        order = list(range(segs, 0, -1)) + list(range(2, segs + 1))
    else:
        order = list(range(1, segs + 1)) + list(range(segs - 1, 0, -1))

    step = duration / len(order) if len(order) else 0

    events = []
    for out_idx, seg in enumerate(order):
        s = start + out_idx * step
        events.append({
            "start": s,
            "duration": step,
            "track": str(n),
            "segments": [seg - 1],
            "brightness": brightness
        })
    
    return events

def _tail_brightness(head_br: int, tail_pos: int, tail_len: int) -> int:
    if tail_pos == 0 or tail_len <= 1:
        return head_br

    min_br = max(5, int(head_br * 0.05))
    span = head_br - min_br

    return max(min_br, int(head_br - span * (tail_pos / (tail_len - 1))))

def boomerang(glyph: dict, model: str, bpm: int, jumps: int):
    n, segs, duration, t, t_end, br, turned_on_segs = get_data(glyph, model, True)
    jumps += 2
    growth_range = segs - 1
    steps_to_grow = jumps - 1 if jumps > 1 else 1
    TAIL_STEP = max(1, round(growth_range / steps_to_grow))

    avg_tail_len = sum(min(1 + i * TAIL_STEP, segs) for i in range(jumps)) / jumps
    STEP = duration / (jumps * (segs + avg_tail_len))

    out = []
    tail_len = 1
    direction = -1
    virtual_head = segs

    def get_step(curr_tail: int) -> float:
        return duration / (jumps * (segs + curr_tail))

    while t < t_end - 1e-9:
        STEP = get_step(tail_len)
        t_next = t + STEP

        segs_to_light = [
            (virtual_head + i if direction == -1 else virtual_head - i, i)
            for i in range(tail_len)
        ]

        for seg_idx, tail_pos in segs_to_light:
            if 1 <= seg_idx <= segs:
                b = _tail_brightness(br, tail_pos, tail_len)
                out.append({
                    "start": t,
                    "duration": STEP,
                    "track": str(n),
                    "segments": [seg_idx - 1],
                    "brightness": b
                })

        virtual_head += direction

        if ((direction == -1 and virtual_head + tail_len - 1 < 1) or
            (direction == 1 and virtual_head - tail_len + 1 > segs)):
            if (t_end - t_next) > STEP * (segs + tail_len + TAIL_STEP):
                tail_len = min(tail_len + TAIL_STEP, segs)
                direction *= -1
                virtual_head = segs if direction == -1 else 1

        t = t_next

    return out

def zebra(glyph: dict, model: str, bpm: int, fps=1, on_count=1, off_count=1, side=1, bpm_snap=False):
    n, segs, duration, start, _, br, turned_on_segs = get_data(glyph, model, True)
    if bpm_snap:
        fps = (bpm / 60) * bpm_snap

    step_duration = 1000.0 / fps
    total_steps = max(1, int(duration / step_duration))
    pattern_len = on_count + off_count

    out = []
    for step in range(total_steps):
        t0 = start + step * step_duration
        t1 = min(t0 + step_duration, start + duration)

        for i in range(segs):
            shifted_index = (i - step * side) % pattern_len
            if shifted_index < on_count:
                out.append({
                    "start": t0,
                    "duration": t1 - t0,
                    "track": str(n),
                    "segments": [i],
                    "brightness": br
                })

    return out

def shocker(glyph: dict, model: str, bpm: int, frequency=5.0, fade_out=True, bpm_snap=False):
    if bpm_snap:
        frequency = (bpm / 60) * bpm_snap

    n, segs, duration, start, end, brightness, turned_on_segs = get_data(glyph, model, True)
    interval = 1000.0 / frequency
    t = start
    out = []

    even_indices = [i + 1 for i in range(segs) if (i + 1) % 2 == 0]
    odd_indices = [i + 1 for i in range(segs) if (i + 1) % 2 == 1]

    while t < end:
        t_half = min(t + interval / 2, end)
        t_next = min(t + interval, end)

        for i in even_indices:
            element = {
                "start": t,
                "duration": t_half - t,
                "track": str(n),
                "segments": [i - 1],
                "brightness": brightness
            }
            
            if fade_out:
                element["end_brightness"] = 0
            
            out.append(element)

        for i in odd_indices:
            element = {
                "start": t_half,
                "duration": t_next - t_half,
                "track": str(n),
                "segments": [i - 1],
                "brightness": brightness
            }
            
            if fade_out:
                element["end_brightness"] = 0
            
            out.append(element)

        t = t_next

    return out

EffectsConfig = {
    "None": {
        "segmented": False,
        "supports_segmentation": True,
        "settings": []
    },
    "Fade out": {
        "segmented": False,
        "supports_segmentation": True,
        "function": fade_out,
        "settings": []
    },
    "Fade in": {
        "segmented": False,
        "supports_segmentation": True,
        "function": fade_in,
        "settings": []
    },
    "Fade in + out": {
        "segmented": False,
        "supports_segmentation": True,
        "function": fade_in_out,
        "settings": []
    },
    "Fade to": {
        "segmented": False,
        "supports_segmentation": True,
        "function": fade_to,
        "settings": [
            {
                "type": "slider",
                "title": "Fade to",
                "min": 1,
                "max": 100,
                "key": "fade_to_brightness",
                "default": 50
            }
        ]
    },
    "Fill": {
        "segmented": True,
        "supports_segmentation": False,
        "function": fill,
        "settings": [
            {
                "type": "selector",
                "title": "Side",
                "key": "side",
                "choices": ["To the left", "To the right"],
                "map": {"To the left": -1, "To the right": 1},
                "default": "To the left"
            }
        ]
    },
    "Zebra": {
        "segmented": True,
        "supports_segmentation": False,
        "function": zebra,
        "settings": [
            {
                "type": "selector",
                "title": "Snap to BPM",
                "key": "bpm_snap",
                "choices": ["Disabled", "BPM /2", "BPM", "BPM x2", "BPM x4"],
                "map": {
                    "Disabled": False,
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                },
                "default": "Disabled"
            },
            {
                "type": "selector",
                "title": "Side",
                "key": "side",
                "choices": ["To the left", "To the right"],
                "map": {"To the left": -1, "To the right": 1},
                "default": "To the left"
            },
            {
                "type": "slider",
                "title": "Moves per second",
                "min": 1,
                "max": 20,
                "offset": 1,
                "key": "fps",
                "default": 5
            },
            {
                "type": "slider",
                "title": "Lit segments in a row",
                "min": 1,
                "max": 5,
                "offset": 1,
                "key": "on_count",
                "default": 3
            },
            {
                "type": "slider",
                "title": "Dark segments in a row",
                "min": 1,
                "max": 5,
                "offset": 1,
                "key": "off_count",
                "default": 1
            }
        ]
    },
    "Strobe": {
        "segmented": False,
        "supports_segmentation": True,
        "function": strobe,
        "settings": [
            {
                "type": "slider",
                "title": "Strobes per second",
                "key": "frequency",
                "min": 1,
                "max": 15,
                "default": 5
            }
        ]
    },
    "Soft Strobe": {
        "segmented": False,
        "supports_segmentation": True,
        "function": soft_or_pseudo_strobe,
        "settings": [
            {
                "type": "selector",
                "title": "Snap to BPM",
                "key": "bpm_snap",
                "choices": ["Disabled", "BPM /2", "BPM", "BPM x2", "BPM x4"],
                "map": {
                    "Disabled": False,
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                },
                "default": "Disabled"
            },
            {
                "type": "slider",
                "title": "Strobes per second",
                "key": "frequency",
                "min": 1,
                "max": 20,
                "default": 5
            },
            {
                "type": "slider",
                "title": "First brightness",
                "key": "first_brightness",
                "min": 5,
                "max": 100,
                "default": 100
            },
            {
                "type": "slider",
                "title": "Second brightness",
                "key": "second_brightness",
                "min": 5,
                "max": 100,
                "default": 80
            }
        ]
    },
    "Shocker": {
        "segmented": True,
        "supports_segmentation": False,
        "function": shocker,
        "settings": [
            {
                "type": "selector",
                "title": "Snap to BPM",
                "key": "bpm_snap",
                "choices": ["Disabled", "BPM /2", "BPM", "BPM x2", "BPM x4"],
                "map": {
                    "Disabled": False,
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                },
                "default": "Disabled"
            },
            {
                "type": "slider",
                "title": "Shocks per second",
                "key": "frequency",
                "min": 1,
                "max": 15,
                "default": 3
            },
            {
                "type": "checkbox",
                "title": "Enable fade out",
                "key": "fade_out",
                "default": True
            }
        ]
    },
    "Sweep": {
        "segmented": True,
        "supports_segmentation": False,
        "function": sweep,
        "settings": [
            {
                "type": "selector",
                "title": "Side",
                "key": "side",
                "choices": ["To the left", "To the right"],
                "map": {"To the left": -1, "To the right": 1},
                "default": "To the left"
            }
        ]
    },
    "Glitch": {
        "segmented": True,
        "supports_segmentation": True,
        "function": glitch,
        "settings": [
            {
                "type": "selector",
                "title": "Snap to BPM",
                "key": "bpm_snap",
                "map": {
                    "Disabled": False,
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                },
                "default": "Disabled"
            },
            {
                "type": "slider",
                "title": "Glitches per second",
                "key": "fps",
                "min": 1,
                "max": 30,
                "default": 10
            },
            {
                "type": "slider",
                "title": "Minimal brightness",
                "key": "min_br_ratio",
                "min": 1,
                "max": 100,
                "default": 30
            },
            {
                "type": "selector",
                "title": "Glitch fill level",
                "key": "duty_cycle",
                "choices": ["Less", "More"],
                "map": {"Less": 0.3, "More": 0.7},
                "default": "More"
            },
            {
                "type": "checkbox",
                "title": "Enable Fade out",
                "key": "enable_fadeout",
                "default": True
            }
        ]
    },
    "BPM": {
        "segmented": False,
        "supports_segmentation": True,
        "function": bpm_effect,
        "settings": [
            {
                "type": "selector",
                "title": "Select BPM",
                "key": "multiplier",
                "choices": ["BPM /2", "BPM", "BPM x2", "BPM x4"],
                "map": {
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                },
                "default": "BPM"
            },
            {
                "type": "checkbox",
                "title": "Enable fading on sub - beats",
                "key": "enable_fading",
                "default": True
            }
        ]
    },
    "Sidebeat": {
        "segmented": True,
        "supports_segmentation": False,
        "function": sidebeat,
        "settings": [
            {
                "type": "selector",
                "title": "Side",
                "key": "part",
                "choices": ["Left", "Both", "Right"],
                "map": {
                    "Left": "left",
                    "Both": "both",
                    "Right": "right"
                },
                "default": "Both"
            }
        ]
    },
    "Boomerang": {
        "segmented": True,
        "supports_segmentation": False,
        "function": boomerang,
        "settings": [
            {
                "type": "slider",
                "title": "Jumps",
                "key": "jumps",
                "min": 4,
                "max": 12,
                "default": 4
            }
        ]
    },

    "Chase": {
        "segmented": True,
        "supports_segmentation": False,
        "function": chase,
        "settings": [
            {
                "type": "slider",
                "title": "Width",
                "key": "width",
                "min": 1,
                "max": 10,
                "offset": 1,
                "default": 3
            },
            {
                "type": "selector",
                "title": "Direction",
                "key": "direction",
                "choices": ["To the left", "To the right"],
                "map": {"To the left": -1, "To the right": 1},
                "default": "To the left"
            }
        ]
    },

    "Ripple": {
        "segmented": True,
        "supports_segmentation": False,
        "function": ripple,
        "settings": [
            {
                "type": "slider",
                "title": "Tail",
                "key": "tail",
                "min": 1,
                "max": 10,
                "offset": 1,
                "default": 5
            }
        ]
    }
}

def is_segment_edited(glyph):
    return "segments" in glyph

def all():
    return EffectsConfig

def only_non_segmented():
    return {
        name: config for name, config in EffectsConfig.items()
        if not config.get("segmented", False)
    }

def only_segmentation_supported():
    return {
        name: config for name, config in EffectsConfig.items()
        if config.get("supports_segmentation", False)
    }

def _preview(effect_fn, glyph=_example_glyph, model="PHONE2A"):
    print(effect_fn(glyph, model, 120))

if __name__ == "__main__":
    _preview(sidebeat)