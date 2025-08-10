import random

from typing import List
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

    for key, meta in settings_meta.items():
        arg_name = meta.get("key")
        if not arg_name:
            continue

        value = config.get(key, 1)
        
        if "map" in meta:
            value = meta["map"].get(value, value)

        args[arg_name] = value

    return args

def reverse_effect_timeline(entries: List[str]) -> List[str]:
    parsed = [line.split('\t') for line in entries]
    times = [(float(start), float(end)) for start, end, _ in parsed]

    reversed_times = list(reversed(times))

    return [
        f"{t0:.6f}\t{t1:.6f}\t{label}"
        for (t0, t1), (_, _, label) in zip(reversed_times, parsed)
    ]

def glyphs_to_strings(glyphs: List[dict]) -> List[str]:
    lines = []
    for glyph in glyphs:
        t0 = _sec(glyph["start"])
        t1 = _sec(glyph["start"] + glyph["duration"])
        track = glyph.get("track")
        brightness = int(glyph.get("brightness", 100))
        
        if "end_brightness" in glyph:
            label = f"{track}-{brightness}-{glyph['end_brightness']}-LIN"
        
        else: label = f"{track}-{brightness}-LIN"

        lines.append(_format_entry(t0, t1, label))
    
    return lines

def effect_to_glyph(element, effect, model, bpm, port_track = None):
    name = effect["name"]
    config = effect["settings"]

    effect_info = EffectsConfig[name]
    effect_fn = effect_info.get("function")
    settings_meta = effect_info.get("settings", {})
    kwargs = parse_effect_args(config, settings_meta)
    
    result = effect_fn(element, model, bpm = bpm, **kwargs)
    return result

def effect_to_label(element, effect, model, bpm, port_track = None):
    name = effect["name"]
    config = effect["settings"]

    if name not in EffectsConfig:
        return []

    effect_info = EffectsConfig[name]
    effect_fn = effect_info.get("function")
    settings_meta = effect_info.get("settings", {})

    if not callable(effect_fn):
        return []

    kwargs = parse_effect_args(config, settings_meta)
    
    if port_track is not None:
        element["port_track"] = port_track
    
    result = glyphs_to_strings(effect_fn(element, model, bpm = bpm, **kwargs))

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

def _sec(ms: float | int) -> float:
    return float(ms) / 1000.0

def smart_number(value: str | int | float) -> int | float:
    try:
        return int(value)
    
    except ValueError:
        return float(value)

def get_data(glyph: dict, model: str, segmented = False):
    start = glyph["start"]
    duration = glyph["duration"]
    end = start + duration

    n = glyph["track"]
    brightness = int(glyph["brightness"])
    segs = None

    try:
        segs = ModelSegments[model][n]
    
    except KeyError as err:
        if segmented:
            if "port_track" in glyph:
                segs = ModelSegments[model][glyph["port_track"]]

    return n, segs, duration, start, end, brightness

def _format_entry(t0: float, t1: float, label: str) -> str:
    return f"{t0:.6f}\t{t1:.6f}\t{label}"

# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------

def fade_in(glyph: dict, model: str, bpm: int):
    n, segs, duration, start, end, brightness = get_data(glyph, model)
    return [{"start": start, "duration": duration, "track": n, "brightness": 0, "end_brightness": brightness}]

def fade_out(glyph: dict, model: str, bpm: int):
    n, segs, duration, start, end, brightness = get_data(glyph, model)
    return [{"start": start, "duration": duration, "track": n, "brightness": brightness, "end_brightness": 0}]

def fade_in_out(glyph: dict, model: str, bpm: int):
    n, segs, duration, start, end, brightness = get_data(glyph, model)

    mid = start + duration / 2

    return [
        {"start": start, "duration": int(duration / 2), "track": n, "brightness": 0, "end_brightness": brightness},
        {"start": mid, "duration": int(duration / 2), "track": n, "brightness": brightness, "end_brightness": 0}
    ]

def sidebeat(glyph: dict, model: str, bpm: int, part: str):
    n, segs, duration, start, end, _ = get_data(glyph, model, True)
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
                "track": f"{n}.{base_segment + i * direction}",
                "brightness": 100
            })
    
    return out

def glitch(glyph: dict, model: str, bpm: int, fps=20.0, duty_cycle=0.7, min_br_ratio=0.3, bpm_snap=False):
    if bpm_snap:
        fps = (bpm / 60) * bpm_snap
    min_br_ratio /= 100

    n, segs, duration, t, t_end, head_br = get_data(glyph, model, True)
    frame = 1000.0 / fps
    out = []

    min_br = max(5, int(head_br * min_br_ratio))

    while t < t_end - 1e-9:
        t0 = t
        t1 = min(t + frame, t_end)

        for seg_idx in range(1, segs + 1):
            if random.random() < duty_cycle:
                br = random.randint(min_br, head_br)
                out.append({
                    "start": t0,
                    "duration": t1 - t0,
                    "track": f"{n}.{seg_idx}",
                    "brightness": br
                })

        t = t1

    return out

def bpm_effect(glyph: dict, model: str, bpm: float, multiplier: int):
    n, _, _, start, end, brightness = get_data(glyph, model)

    actual_bpm = bpm * multiplier
    beat_interval = 60000.0 / actual_bpm
    t = start
    out = []

    while t < end:
        t_off = min(t + beat_interval / 2, end)
        out.append(fade_out({
            "start": t,
            "duration": t_off - t,
            "track": n,
            "brightness": brightness
        }, model, bpm)[0])
        t += beat_interval

    return out

def fill(glyph: dict, model: str, bpm: int, side=1):
    n, segs, duration, start, end, brightness = get_data(glyph, model, True)
    seg_step = duration / segs
    indices = range(segs) if side == 1 else reversed(range(segs))

    return [{
        "start": start + i * seg_step,
        "duration": end - (start + i * seg_step),
        "track": f"{n}.{i + 1}",
        "brightness": brightness
    } for i in indices]

def strobe(glyph: dict, model: str, bpm: int, frequency=1):
    n, _, _, start, end, brightness = get_data(glyph, model)
    interval = 1000.0 / frequency
    t = start
    out = []

    while t < end:
        t_off = min(t + interval / 2, end)
        out.append({
            "start": t,
            "duration": t_off - t,
            "track": n,
            "brightness": brightness
        })
        t += interval

    return out

def soft_or_pseudo_strobe(glyph: dict, model: str, bpm: int, frequency=1, first_brightness=100, second_brightness=70, bpm_snap=False):
    if bpm_snap:
        frequency = (bpm / 60) * bpm_snap

    n, _, _, start, end, _ = get_data(glyph, model)
    interval = 1000.0 / frequency
    t = start
    out = []

    while t < end:
        t_off = min(t + interval / 2, end)
        duration = t_off - t
        out.append({
            "start": t,
            "duration": duration,
            "track": n,
            "brightness": first_brightness
        })
        out.append({
            "start": t_off,
            "duration": duration,
            "track": n,
            "brightness": second_brightness
        })
        t += interval

    return out

def sweep(glyph: dict, model: str, bpm: int, side=1):
    n, segs, duration, start, _, brightness = get_data(glyph, model, True)
    order = list(range(segs, 0, -1)) + list(range(2, segs + 1))
    if side == -1:
        order = order[::-1]

    step = duration / len(order)

    return [{
        "start": start + i * step,
        "duration": step,
        "track": f"{n}.{seg}",
        "brightness": brightness
    } for i, seg in enumerate(order)]

def _tail_brightness(head_br: int, tail_pos: int, tail_len: int) -> int:
    if tail_pos == 0 or tail_len <= 1:
        return head_br

    min_br = max(5, int(head_br * 0.2))
    span = head_br - min_br
    return max(min_br, int(head_br - span * (tail_pos / (tail_len - 1))))

def boomerang(glyph: dict, model: str, bpm: int, jumps: int):
    n, segs, duration, t, t_end, br = get_data(glyph, model, True)
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
                    "track": f"{n}.{seg_idx}",
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
    n, segs, duration, start, _, br = get_data(glyph, model, True)
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
                    "track": f"{n}.{i + 1}",
                    "brightness": br
                })

    return out

def shocker(glyph: dict, model: str, bpm: int, frequency=5.0, fade_out=True, bpm_snap=False):
    if bpm_snap:
        frequency = (bpm / 60) * bpm_snap

    n, segs, duration, start, end, brightness = get_data(glyph, model, True)
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
                "track": f"{n}.{i}",
                "brightness": brightness
            }
            
            if fade_out:
                element["end_brightness"] = 0
            
            out.append(element)

        for i in odd_indices:
            element = {
                "start": t_half,
                "duration": t_next - t_half,
                "track": f"{n}.{i}",
                "brightness": brightness
            }
            
            if fade_out:
                element["end_brightness"] = 0
            
            out.append(element)

        t = t_next

    return out

def get_effect_config(model, track):
    is_segmented = ModelSegments.get(model_to_code(model), {}).get(track)
    non_segmented = {}
    
    if is_segmented:
        return EffectsConfig
    
    for name, value in EffectsConfig.items():
        if not value["segmented"]:
            non_segmented[name] = value
    
    return non_segmented

EffectsConfig = {
    "None": {
        "segmented": False,
        "gif": "System/Media/Effects/None.gif",
        "settings": {}
    },
    "Fade out": {
        "segmented": False,
        "gif": "System/Media/Effects/FadeOut.gif",
        "function": fade_out,
        "settings": {}
    },
    "Fade in": {
        "segmented": False,
        "gif": "System/Media/Effects/FadeIn.gif",
        "function": fade_in,
        "settings": {}
    },
    "Fade in + out": {
        "segmented": False,
        "gif": "System/Media/Effects/FadeInOut.gif",
        "function": fade_in_out,
        "settings": {}
    },
    "Fill": {
        "segmented": True,
        "gif": "System/Media/Effects/Fill.gif",
        "function": fill,
        "settings": {
            "selector1": {
                "title": "Side",
                "key": "side",
                "choices": ["To the left", "To the right"],
                "map": {"To the left": -1, "To the right": 1}
            }
        }
    },
    "Zebra": {
        "segmented": True,
        "gif": "System/Media/Effects/Zebra.gif",
        "function": zebra,
        "settings": {
            "selector1": {
                "title": "Snap to BPM",
                "key": "bpm_snap",
                "choices": ["Disabled", "BPM /2", "BPM", "BPM x2", "BPM x4"],
                "map": {
                    "Disabled": False,
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                }
            },
            "selector2": {
                "title": "Side",
                "key": "side",
                "choices": ["To the left", "To the right"],
                "map": {"To the left": -1, "To the right": 1}
            },
            "slider3": {
                "title": "Moves per second",
                "min": 1,
                "max": 20,
                "offset": 1,
                "key": "fps"
            },
            "slider4": {
                "title": "Lit segments in a row",
                "min": 1,
                "max": 5,
                "offset": 1,
                "key": "on_count"
            },
            "slider5": {
                "title": "Dark segments in a row",
                "min": 1,
                "max": 5,
                "offset": 1,
                "key": "off_count"
            }
        }
    },
    "Strobe": {
        "segmented": False,
        "gif": "System/Media/Effects/Strobe.gif",
        "function": strobe,
        "settings": {
            "slider1": {
                "title": "Strobes per second",
                "key": "frequency",
                "min": 1,
                "max": 15,
                "offset": 1
            }
        }
    },
    "Soft Strobe": {
        "segmented": False,
        "gif": "System/Media/Effects/SoftStrobe.gif",
        "function": soft_or_pseudo_strobe,
        "settings": {
            "selector1": {
                "title": "Snap to BPM",
                "key": "bpm_snap",
                "choices": ["Disabled", "BPM /2", "BPM", "BPM x2", "BPM x4"],
                "map": {
                    "Disabled": False,
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                }
            },
            "slider2": {
                "title": "Strobes per second",
                "key": "frequency",
                "min": 1,
                "max": 20,
                "offset": 1
            },
            "slider3": {
                "title": "First brightness",
                "key": "first_brightness",
                "min": 5,
                "max": 100,
                "offset": 1
            },
            "slider4": {
                "title": "Second brightness",
                "key": "second_brightness",
                "min": 5,
                "max": 100,
                "offset": 1
            }
        }
    },
    "Shocker": {
        "segmented": True,
        "gif": "System/Media/Effects/Shocker.gif",
        "function": shocker,
        "settings": {
            "selector1": {
                "title": "Snap to BPM",
                "key": "bpm_snap",
                "choices": ["Disabled", "BPM /2", "BPM", "BPM x2", "BPM x4"],
                "map": {
                    "Disabled": False,
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                }
            },
            "slider2": {
                "title": "Shocks per second",
                "key": "frequency",
                "min": 1,
                "max": 15,
                "offset": 1
            },
            "checkbox3": {
                "title": "Enable fade out",
                "key": "fade_out",
                "default": True
            }
        }
    },
    "Sweep": {
        "segmented": True,
        "gif": "System/Media/Effects/Sweep.gif",
        "function": sweep,
        "settings": {
            "selector1": {
                "title": "Side",
                "key": "side",
                "choices": ["To the left", "To the right"],
                "map": {"To the left": -1, "To the right": 1}
            }
        }
    },
    "Glitch": {
        "segmented": True,
        "gif": "System/Media/Effects/Glitch.gif",
        "function": glitch,
        "settings": {
            "selector1": {
                "title": "Snap to BPM",
                "key": "bpm_snap",
                "choices": ["Disabled", "BPM /2", "BPM", "BPM x2", "BPM x4"],
                "map": {
                    "Disabled": False,
                    "BPM /2": 0.5,
                    "BPM": 1,
                    "BPM x2": 2,
                    "BPM x4": 4
                }
            },
            "slider2": {
                "title": "Glitches per second",
                "key": "fps",
                "min": 1,
                "max": 30,
                "offset": 1
            },
            "slider3": {
                "title": "Minimal brightness",
                "key": "min_br_ratio",
                "min": 1,
                "max": 100,
                "offset": 1
            },
            "selector4": {
                "title": "Glitch fill level",
                "key": "duty_cycle",
                "choices": ["Less", "More"],
                "map": {"Less": 0.3, "More": 0.7}
            }
        }
    },
    "BPM": {
        "segmented": False,
        "gif": "System/Media/Effects/BPM.gif",
        "function": bpm_effect,
        "settings": {
            "selector1": {
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
            }
        }
    },
    "Sidebeat": {
        "segmented": True,
        "gif": "System/Media/Effects/Sidebeat.gif",
        "function": sidebeat,
        "settings": {
            "selector1": {
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
        }
    },
    "Boomerang": {
        "segmented": True,
        "gif": "System/Media/Effects/Boomerang.gif",
        "function": boomerang,
        "settings": {
            "slider1": {
                "title": "Jumps",
                "key": "jumps",
                "min": 4,
                "max": 12,
                "offset": 2
            }
        }
    }
}

def _preview(effect_fn, glyph=_example_glyph, model="PHONE2A"):
    print(effect_fn(glyph, model, 120))

if __name__ == "__main__":
    _preview(sidebeat)