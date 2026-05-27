import json
import math
import zlib
import base64
import shutil

from loguru import logger

from mutagen.oggopus import OggOpus

from System.Common import (
    Utils,
    Constants
)

from System.Services import GlyphEffects

TIME_STEP_MS = 16.666  # 60 FPS

def glyphs_to_ogg(
        path_to_audio: str,
        destination:   str,
        glyphs:        dict,
        model_code:    str,
        watermark:     str = "Cassette"
    ) -> None:

    device = Constants.DEVICES.get(model_code)

    if not device:
        raise ValueError(f"Unsupported device model: {model_code}")

    audio_duration = get_audio_duration(path_to_audio) * 1000
    author_lines   = math.ceil(float(audio_duration) / TIME_STEP_MS)
    author_data    = [[0 for _ in range(device.columns)] for _ in range(author_lines)]

    parsed_glyphs = parse_glyphs(glyphs, device)
    author_data   = apply_glyphs_to_author(parsed_glyphs, author_data)
    custom1_data  = generate_point_list(audio_duration, watermark)[0]
    nglyph_data   = prepare_nglyph_data(device, author_data, custom1_data)

    author_base64, custom1_base64 = compress_and_encode_data(nglyph_data)

    metadata = prepare_metadata(device, author_base64, custom1_base64)

    run_ffmpeg(path_to_audio, destination, metadata)

def is_bngc_file(data: dict) -> bool:
    first_track_glyphs = next(iter(data.values()))

    if not first_track_glyphs or not isinstance(first_track_glyphs, list):
        return False

    return "startTimeMilis" in first_track_glyphs[0]

def is_labels_file(data: str) -> bool:
    return "PHONE_MODEL=" in data and "\t" in data

def convert_to_glyphs(
        path:     str,
        start_ms: int,
        end_ms:   int
    ) -> tuple[str | None, dict[int, dict] | None]:

    file = open(path).read()

    if "\t" in file:
        return labels_to_glyphs(file, start_ms, end_ms)

    file = json.loads(file)

    if is_bngc_file(file):
        return bngc_to_glyphs(file, start_ms, end_ms)

    logger.error(f"{path}: Unknown format")

    raise UnknownFileFormatError(f"Unknown file format for: {path}")

def get_audio_duration(path_to_audio: str) -> float:
    audio = OggOpus(path_to_audio)
    return audio.info.length

def parse_glyphs(glyphs: dict, device: Constants.DeviceConfig) -> list[dict]:
    parsed = []

    for glyph in glyphs:
        start         = round(glyph["start"])
        duration      = round(glyph["duration"])
        rounded_start = get_nearest_divisable_by(start, TIME_STEP_MS)
        rounded_end   = get_nearest_divisable_by(start + duration, TIME_STEP_MS)

        if rounded_end <= rounded_start:
            rounded_end = rounded_start + TIME_STEP_MS

        track_index = int(glyph["track"])
        segments    = glyph.get("segments")

        if segments:
            indices = [device.get_array_indexes(track_index, segment + 1)[0] for segment in segments]

        else:
            indices = device.get_array_indexes(track_index, 0)

        item: dict = {
            "rastered_start": rounded_start,
            "rastered_end":   rounded_end,
            "array_indexes":  indices,
        }

        if "keyframes" in glyph:
            item["keyframes"] = glyph["keyframes"]
            item["easing"]    = glyph["easing"]

        else:
            item["brightness"] = glyph["brightness"]

        parsed.append(item)

    return parsed

def get_nearest_divisable_by(number: float, divisor: float) -> float:
    return round(number / divisor) * divisor

def is_glyph_within_time_range(
        start_ms:    int,
        duration_ms: int,
        range_start: int | None,
        range_end:   int | None
    ) -> bool:

    glyph_end = start_ms + duration_ms

    if range_start is not None and start_ms < range_start:
        return False

    if range_end is not None and glyph_end > range_end:
        return False

    return True

def apply_glyphs_to_author(
        parsed_glyphs: list[dict],
        author_data:   list[list[int]]
    ) -> list[list[int]]:

    for glyph in parsed_glyphs:
        start_row = round(glyph["rastered_start"] / TIME_STEP_MS)
        end_row   = round(glyph["rastered_end"]   / TIME_STEP_MS)
        rows      = list(range(start_row, end_row))

        if not rows:
            continue

        for index, row_index in enumerate(rows):
            if not (0 <= row_index < len(author_data)):
                continue

            brightness_percent = get_glyph_brightness(glyph, index, len(rows))
            light_level        = max(0, min(4095, round((brightness_percent / 100.0) * 4095.0)))

            for led_index in glyph["array_indexes"]:
                author_data[row_index][led_index] = light_level

    return author_data

def get_glyph_brightness(
        parsed_glyph: dict,
        step_index:   int,
        total_steps:  int
    ) -> float:

    if "keyframes" not in parsed_glyph:
        return parsed_glyph["brightness"]

    keyframes   = parsed_glyph["keyframes"]
    easing_func = Constants.VISUAL_EASINGS[parsed_glyph["easing"]]
    progress    = step_index / (total_steps - 1) if total_steps > 1 else 1.0

    if progress <= keyframes[0][0]:
        return keyframes[0][1]

    if progress >= keyframes[-1][0]:
        return keyframes[-1][1]

    for keyframe_index in range(len(keyframes) - 1):
        (time_1, brightness_1), (time_2, brightness_2) = keyframes[keyframe_index], keyframes[keyframe_index + 1]

        if not (time_1 <= progress <= time_2):
            continue

        duration = time_2 - time_1
        local_t  = (progress - time_1) / duration if duration > 0 else 1.0

        return brightness_1 + (brightness_2 - brightness_1) * easing_func(local_t)

    return 100.0

def generate_point_list(
        duration_ms: float,
        text:        str,
        view_width:  int = 24
    ) -> tuple[list[str], list[list[int]]]:

    matrix           = get_text_matrix(text, view_width)
    actual_width     = len(matrix[0])
    ms_per_column    = duration_ms / (actual_width - 1) if actual_width > 1 else 0
    points_list      = []

    for column in range(actual_width):
        start_ms = int(column * ms_per_column)

        for row in range(5):
            if matrix[row][column] == 1:
                points_list.append(f"{start_ms}-{row}")

    return points_list, matrix

def get_text_matrix(text: str, min_width: int = 24) -> list[list[int]]:
    font          = Constants.DOT_FONT
    matrix_height = 5
    raw_matrix    = [[] for _ in range(matrix_height)]

    for char in text:
        char_data = font.get(char) or font.get(char.upper(), font[" "])

        for row_index in range(matrix_height):
            raw_matrix[row_index].extend(char_data[row_index])
            raw_matrix[row_index].append(0)

    current_width = len(raw_matrix[0])
    final_width   = max(current_width, min_width)
    pad_left      = (final_width - current_width) // 2
    pad_right     = final_width - current_width - pad_left

    return [
        [0] * pad_left + raw_matrix[row] + [0] * pad_right
        for row in range(matrix_height)
    ]

def prepare_nglyph_data(
        device:       Constants.DeviceConfig,
        author_data:  list[list[int]],
        custom1_data: list[str]
    ) -> dict:

    return {
        "VERSION":     1,
        "PHONE_MODEL": device.code_name,
        "AUTHOR":      [f"{','.join(str(e) for e in line)}," for line in author_data],
        "CUSTOM1":     custom1_data,
    }

def compress_and_encode_data(nglyph_data: dict) -> tuple[str, str]:
    author_raw  = ("\r\n".join(nglyph_data["AUTHOR"]) + "\r\n").encode("utf-8")
    custom1_raw = (",".join(nglyph_data["CUSTOM1"])   + ",").encode("utf-8")

    author_compressed  = zlib.compress(author_raw,  zlib.Z_BEST_COMPRESSION)
    custom1_compressed = zlib.compress(custom1_raw, zlib.Z_BEST_COMPRESSION)

    return encode_base64(author_compressed), encode_base64(custom1_compressed)

def encode_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8").removesuffix("==").removesuffix("=")

def decode_base64_padded(data: str) -> bytes:
    remainder = len(data) % 4

    if remainder:
        data += "=" * (4 - remainder)

    return base64.b64decode(data)

def decode_author_data(author_b64: str) -> list[list[int]]:
    author_raw   = zlib.decompress(decode_base64_padded(author_b64))
    author_lines = author_raw.decode("utf-8").splitlines()
    author_data  = [
        [int(v) for v in line.rstrip(",").split(",") if v]
        for line in author_lines
        if line.strip()
    ]

    return author_data

def prepare_metadata(
        device:         Constants.DeviceConfig,
        author_base64:  str,
        custom1_base64: str
    ) -> dict:

    return {
        "TITLE":    "Made with Cassette",
        "ALBUM":    "Made with Cassette",
        "AUTHOR":   author_base64,
        "COMPOSER": f"v1-{device.composer_code_name} Glyph Composer",
        "CUSTOM1":  custom1_base64,
        "CUSTOM2":  device.custom2_str,
    }

def run_ffmpeg(
        path_to_audio: str,
        destination:   str,
        metadata:      dict
    ) -> None:

    if path_to_audio != destination:
        shutil.copy2(path_to_audio, destination)

    audio = OggOpus(destination)

    for key, value in metadata.items():
        audio[key] = str(value)

    audio.save()

def is_increasing(values: list[int]) -> bool:
    return all(left <= right for left, right in zip(values, values[1:]))

def is_decreasing(values: list[int]) -> bool:
    return all(left >= right for left, right in zip(values, values[1:]))

def is_peak_shape(values: list[int]) -> bool:
    if len(values) < 3:
        return False

    peak_index = values.index(max(values))

    if peak_index == 0 or peak_index == len(values) - 1:
        return False

    return is_increasing(values[: peak_index + 1]) and is_decreasing(values[peak_index:])

def detect_easing(data: list[int]) -> str:
    if len(data) < 3:
        return "linear"

    deltas = [current - previous for previous, current in zip(data, data[1:])]
    deltas = [delta for delta in deltas if delta != 0]

    if not deltas:
        return "linear"

    abs_deltas = [abs(delta) for delta in deltas]
    increasing = is_increasing(abs_deltas)
    decreasing = is_decreasing(abs_deltas)

    if increasing and not decreasing:
        return "ease_in"

    if decreasing and not increasing:
        return "ease_out"

    if len(abs_deltas) > 2 and is_peak_shape(abs_deltas):
        return "ease_in_out"

    return "linear"

def resolve_fade_info(effect_data: list[int]) -> tuple[str | None, str, bool]:
    if len(effect_data) <= 1:
        return None, "linear", False

    if len(set(effect_data)) == 1:
        return None, "linear", False

    if is_increasing(effect_data):
        return "fade_in", detect_easing(effect_data), False

    if is_decreasing(effect_data):
        return "fade_out", detect_easing(effect_data), False

    if not is_peak_shape(effect_data):
        return None, "linear", True

    peak_index  = effect_data.index(max(effect_data))
    easing_type = "smooth" if effect_data[peak_index] == effect_data[peak_index - 1] else "sharp"

    return "fade_in_out", easing_type, False

def build_audio_fade_filters(
        duration_s:   float,
        fade_in_ms:   float = 120.0,
        fade_out_ms:  float = 120.0
    ) -> tuple[str | None, str | None]:

    if duration_s <= 0:
        return None, None

    fade_in_s  = min(max(0.0, fade_in_ms  / 1000.0), duration_s)
    fade_out_s = min(max(0.0, fade_out_ms / 1000.0), duration_s)

    filters = []

    if fade_in_s > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in_s}")

    if fade_out_s > 0:
        fade_out_start = max(0.0, duration_s - fade_out_s)
        filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out_s}")

    return ",".join(filters) if filters else None, ("libopus" if filters else None)

def finalize_glyphs(grouped_dict: dict, config: object) -> dict:
    segments_map = config.segments_map

    for glyph in grouped_dict.values():
        if "segments" not in glyph:
            continue

        maximum_segments = segments_map.get(glyph["track"], 0)

        if len(glyph["segments"]) == maximum_segments and maximum_segments > 0:
            del glyph["segments"]

        else:
            glyph["segments"].sort()

    sorted_list = sorted(grouped_dict.values(), key = lambda x: x["start"])

    return {index: glyph for index, glyph in enumerate(sorted_list)}

def bngc_to_glyphs(
        json_data:   dict[str, list[dict[str, object]]],
        start_ms:    int | None = None,
        end_ms:      int | None = None
    ) -> tuple[str, dict[int, dict[str, object]]]:

    total_tracks = len(json_data)

    target_config, model_name = next(
        (
            (config, name) for name, config in Constants.DEVICES.items()
            if config.total_tracks_with_segments == total_tracks or total_tracks in config.legacy_tracks
        ),
        (None, "UNKNOWN")
    )

    if not target_config:
        raise LabelsNoModelError(f"No device matches track count: {total_tracks}")

    grouped_glyphs = {}

    for track_index_str, glyph_list in json_data.items():
        track_id_in   = str(int(track_index_str) + 1)
        target_tracks = target_config.resolve_tracks(track_id_in, total_tracks)

        for item in glyph_list:
            start_ms_item = int(round(item["startTimeMilis"]))
            duration_ms   = int(round(item["durationMilis"]))
            brightness    = int(round(item["startingBrightness"] / 40.95))

            if not is_glyph_within_time_range(start_ms_item, duration_ms, start_ms, end_ms):
                continue

            shifted_start_ms = start_ms_item - start_ms if start_ms and start_ms > 0 else start_ms_item

            fade_type, easing_type, is_complex = resolve_fade_info(item.get("effectData", []))

            for track_id, segment_index in target_tracks:
                time_key = (shifted_start_ms // 10, duration_ms // 10, track_id, brightness, fade_type)

                if time_key in grouped_glyphs:
                    existing = grouped_glyphs[time_key]

                    if segment_index is not None and segment_index not in existing.get("segments", []):
                        existing.setdefault("segments", []).append(segment_index)

                    continue

                new_glyph = {
                    "start":      shifted_start_ms,
                    "duration":   duration_ms,
                    "track":      track_id,
                    "brightness": brightness
                }

                if fade_type:
                    new_glyph = GlyphEffects.apply_visual_effect(
                        new_glyph,
                        "Fade",
                        {
                            "mode":   fade_type,
                            "easing": easing_type
                        }
                    )

                if segment_index is not None:
                    new_glyph["segments"] = [segment_index]

                if is_complex:
                    new_glyph["effect_type"] = "complex"

                grouped_glyphs[time_key] = new_glyph

    return model_name, finalize_glyphs(grouped_glyphs, target_config)

def labels_to_glyphs(
        data:     str,
        start_ms: int | None = None,
        end_ms:   int | None = None
    ) -> tuple[str, dict[int, dict]]:

    model_name = next(
        (
            line.split("PHONE_MODEL=")[-1].strip()
            for line in data.splitlines() if "PHONE_MODEL=" in line
        ), None
    )

    config = Constants.DEVICES.get(model_name)

    if not config:
        raise LabelsNoModelError(f"Unknown model: {model_name}")

    raw_lines = [
        line.strip() for line in data.splitlines()
        if line.strip() and not any(x in line for x in ["PHONE_MODEL", "LABEL_VERSION", "END"])
    ]

    unique_tracks_in_file = len(
        {
            line.split("\t")[2].split("-")[0].split(".")[0]
            for line in raw_lines if "\t" in line
        }
    )

    legacy_track_map = config.legacy_tracks.get(unique_tracks_in_file, {})
    segments_map     = config.segments_map
    grouped_glyphs   = {}

    for line in raw_lines:
        parts_tab = line.split("\t")

        if len(parts_tab) < 3:
            continue

        try:
            start_ms_item = int(float(parts_tab[0]) * 1000)
            duration_ms   = int(float(parts_tab[1]) * 1000) - start_ms_item

            label_parts = parts_tab[2].strip().split("-")
            track_part  = label_parts[0]
            brightness  = int(label_parts[1])
            end_bright  = int(label_parts[2]) if len(label_parts) >= 3 else None

            track_id_in    = track_part.split(".")[0]
            manual_segment = int(track_part.split(".")[1]) - 1 if "." in track_part else None

            if not is_glyph_within_time_range(start_ms_item, duration_ms, start_ms, end_ms):
                continue

            shifted_start_ms = start_ms_item - start_ms if start_ms and start_ms > 0 else start_ms_item

            legacy_mapping = legacy_track_map.get(track_id_in)

            if legacy_mapping and manual_segment is not None:
                resolved_single = legacy_mapping[0] if len(legacy_mapping) == 1 else None

                if resolved_single and segments_map.get(resolved_single, 1) > 1:
                    target_tracks = [(resolved_single, manual_segment)]

                else:
                    if manual_segment >= len(legacy_mapping):
                        continue

                    target_tracks = [(legacy_mapping[manual_segment], None)]

            else:
                target_tracks = config.resolve_tracks(track_id_in, unique_tracks_in_file)

            for track_id, automatic_segment in target_tracks:
                time_key = (shifted_start_ms // 10, duration_ms // 10, track_id, brightness, end_bright)

                if time_key in grouped_glyphs:
                    existing = grouped_glyphs[time_key]

                    if automatic_segment is not None and automatic_segment not in existing.get("segments", []):
                        existing.setdefault("segments", []).append(automatic_segment)

                    continue

                glyph = {
                    "start":      shifted_start_ms,
                    "duration":   duration_ms,
                    "track":      track_id,
                    "brightness": brightness
                }

                if end_bright:
                    glyph = GlyphEffects.apply_visual_effect(
                        glyph,
                        "Fade",
                        {
                            "keyframes": [(0, brightness), (1, end_bright)],
                            "easing":    "linear"
                        }
                    )

                final_segment = automatic_segment

                if final_segment is None and manual_segment is not None and segments_map.get(str(track_id), 1) > 1:
                    final_segment = manual_segment

                if final_segment is not None:
                    glyph["segments"] = [final_segment]

                grouped_glyphs[time_key] = glyph

        except Exception:
            continue

    return model_name, finalize_glyphs(grouped_glyphs, config)

def trim_glyphs_ogg(
        path:         str,
        output:       str,
        start_ms:     int,
        end_ms:       int,
        fade_in_ms:   int = 0,
        fade_out_ms:  int = 0
    ) -> None:

    source_audio    = OggOpus(path)

    author_b64  = source_audio.get("AUTHOR",  [None])[0]
    custom1_b64 = source_audio.get("CUSTOM1", [None])[0]

    if not author_b64:
        raise ValueError(f"No AUTHOR glyph data found in: {path}")

    author_data  = decode_author_data(author_b64)

    start_frame  = round(start_ms / TIME_STEP_MS)
    end_frame    = round(end_ms   / TIME_STEP_MS)
    trimmed_data = author_data[start_frame:end_frame]

    author_lines_new = [f"{','.join(str(e) for e in line)}," for line in trimmed_data]
    author_raw_new   = ("\r\n".join(author_lines_new) + "\r\n").encode("utf-8")
    author_b64_new   = encode_base64(zlib.compress(author_raw_new, zlib.Z_BEST_COMPRESSION))

    custom1_b64_new = custom1_b64

    if custom1_b64:
        custom1_raw     = zlib.decompress(decode_base64_padded(custom1_b64))
        original_points = [p for p in custom1_raw.decode("utf-8").rstrip(",").split(",") if p]
        shifted_points  = []

        for point in original_points:
            time_str, row_str = point.split("-")
            point_ms          = int(time_str)

            if not (start_ms <= point_ms <= end_ms):
                continue

            shifted_points.append(f"{round(point_ms - start_ms)}-{row_str}")

        custom1_raw_new = (",".join(shifted_points) + ",").encode("utf-8")
        custom1_b64_new = encode_base64(zlib.compress(custom1_raw_new, zlib.Z_BEST_COMPRESSION))

    clip_duration_s = max(0.0, (end_ms - start_ms) / 1000.0)
    
    fade_filters, audio_codec = build_audio_fade_filters(
        clip_duration_s,
        fade_in_ms,
        fade_out_ms
    )

    cmd = [
        Constants.FFMPEG_PATH,
        "-y",
        "-v", "error",
        "-ss", str(start_ms / 1000.0),
        "-t", str(clip_duration_s),
        "-i", path,
        "-vn",
        "-map_metadata", "0"
    ]

    if fade_filters:
        cmd += ["-af", fade_filters, "-c:a", audio_codec or "libopus"]
    
    else:
        cmd += ["-c:a", "copy"]

    cmd.append(output)

    Utils.run_hidden(cmd)

    trimmed_audio = OggOpus(output)
    trimmed_audio["AUTHOR"] = author_b64_new
    trimmed_audio["CUSTOM1"] = custom1_b64_new
    trimmed_audio.save()

class LabelsNoModelError(Exception):
    pass

class ZeroGlyphsError(Exception):
    pass

class UnknownFileFormatError(Exception):
    pass