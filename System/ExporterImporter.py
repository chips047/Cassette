import json
import zlib
import math
import base64
import subprocess

import shutil
from mutagen.oggopus import OggOpus
from System.Constants import *

TIME_STEP_MS = 16.666

def glyphs_to_ogg(path_to_audio: str, destination: str, glyphs: dict, model_code: str):
    model = get_model(model_code)
    columns_model = get_columns_model(model)
    audio_duration = get_audio_duration(path_to_audio)

    author_lines = math.ceil(float(audio_duration) * 1000 / TIME_STEP_MS)
    author_data = [[0 for _ in range(get_number_of_columns_from_columns_model(columns_model))] for _ in range(author_lines)]
    
    custom1_data = []
    parsed_glyphs = parse_glyphs(glyphs, columns_model)

    author_data, custom1_data = apply_glyphs_to_author(parsed_glyphs, author_data, custom1_data)
    nglyph_data = prepare_nglyph_data(model, author_data, custom1_data)
    
    author_compressed_base64, custom1_compressed_base64 = compress_and_encode_data(nglyph_data)
    
    columns_mode, custom2 = get_columns_mode_and_custom2(nglyph_data)
    
    metadata = prepare_metadata(author_compressed_base64, custom1_compressed_base64, columns_mode, custom2)

    run_ffmpeg(path_to_audio, destination, metadata)

def get_model(model_code: str):
    return PhoneModel[model_code]

def get_columns_model(model):
    return {
        PhoneModel.PHONE1: Cols.FIFTEEN_ZONE,
        PhoneModel.PHONE2: Cols.THIRTY_THREE_ZONE,
        PhoneModel.PHONE2A: Cols.TWENTY_SIX_ZONE,
        PhoneModel.PHONE3A: Cols.THIRTY_SIX_ZONE,
    }[model]

def parse_glyphs(glyphs, columns_model):
    parsed_glyphs = []
    for glyph in glyphs:
        custom_5col_id = get_custom_5col_id(int(glyph["track"]), columns_model)

        dict_glyph = {
            "rastered_start": get_nearest_divisable_by(round(glyph["start"]), TIME_STEP_MS),
            "rastered_end": get_nearest_divisable_by(round(glyph["start"] + glyph["duration"]), TIME_STEP_MS),
            "custom_5col_id": custom_5col_id,
            "brightness_from": glyph["brightness"] * 4095.0 / 100.0,
            "brightness_to": glyph["brightness"] * 4095.0 / 100.0,
        }

        dict_glyph["rastered_delta"] = dict_glyph["rastered_end"] - dict_glyph["rastered_start"]

        if "end_brightness" in glyph:
            dict_glyph["brightness_to"] = glyph["end_brightness"] * 4095.0 / 100.0

        if dict_glyph["rastered_delta"] == 0:
            dict_glyph["rastered_end"] += TIME_STEP_MS
            dict_glyph["rastered_delta"] = TIME_STEP_MS

        if "segments" in glyph:
            dict_glyph["array_indexes"] = [get_glyph_array_indexes(int(glyph["track"]), segment + 1, columns_model)[0] for segment in glyph["segments"]]
            parsed_glyphs.append(dict_glyph)
        
        else:
            dict_glyph["array_indexes"] = get_glyph_array_indexes(int(glyph["track"]), 0, columns_model)
            parsed_glyphs.append(dict_glyph)

    return parsed_glyphs

def apply_glyphs_to_author(parsed_glyphs, author_data, custom1_data):
    for parsed_glyph in parsed_glyphs:
        steps = list(
            range(
                round(parsed_glyph["rastered_start"] / TIME_STEP_MS),
                round(parsed_glyph["rastered_end"] / TIME_STEP_MS)
            )
        )

        start_i = 1 if parsed_glyph["brightness_from"] <= parsed_glyph["brightness_to"] else 0
        for i, row in enumerate(steps, start_i):
            brightness_start = parsed_glyph["brightness_from"]
            brightness_end = parsed_glyph["brightness_to"]

            step_count = len(steps)
            step_increment = (brightness_end - brightness_start) / step_count

            light_level = brightness_start + step_increment * i
            light_level = round(light_level)

            for index in parsed_glyph["array_indexes"]:
                author_data[row][index] = light_level

        custom1_data.append(f"{round(parsed_glyph['rastered_start'])}-{parsed_glyph['custom_5col_id']}")

    return author_data, custom1_data

def prepare_nglyph_data(model, author_data, custom1_data):
    nglyph_data = {
        'VERSION': 1,
        'PHONE_MODEL': model.name,
        "AUTHOR": [f"{','.join([str(e) for e in line])}," for line in author_data],
        "CUSTOM1": custom1_data
    }
    return nglyph_data

def get_audio_duration(path_to_audio: str):
    audio = OggOpus(path_to_audio)
    duration = audio.info.length
    
    return duration

def compress_and_encode_data(nglyph_data):
    author_raw_data = ('\r\n'.join(list(nglyph_data['AUTHOR'])) + '\r\n').encode('utf-8')
    custom1_raw_data = (','.join(list(nglyph_data['CUSTOM1'])) + ',').encode('utf-8')

    author_compressed = zlib.compress(author_raw_data, zlib.Z_BEST_COMPRESSION)
    custom1_compressed = zlib.compress(custom1_raw_data, zlib.Z_BEST_COMPRESSION)

    author_compressed_base64 = encode_base64(author_compressed)
    custom1_compressed_base64 = encode_base64(custom1_compressed)

    return author_compressed_base64, custom1_compressed_base64

def get_columns_mode_and_custom2(nglyph_data):
    columns = len([x for x in nglyph_data['AUTHOR'][0].split(',') if x])
    columns_mode = N_COLUMNS_TO_COLS[columns]
    custom2 = STRING_TO_COLS.get(columns_mode, None)
    
    return columns_mode, custom2

def prepare_metadata(author_base64, custom1_base64, columns_mode, custom2):
    return {
        "TITLE": "Made with Cassette",
        "ALBUM": "Made with Cassette",
        "AUTHOR": author_base64,
        "COMPOSER": f"v1-{DEVICE_CODENAME[columns_mode]} Glyph Composer",
        "CUSTOM1": custom1_base64,
        "CUSTOM2": custom2
    }

def run_ffmpeg(path_to_audio, destination, metadata):
    if path_to_audio != destination:
        shutil.copy2(path_to_audio, destination)
    
    audio = OggOpus(destination)
    
    for key, value in metadata.items():
        audio[key] = str(value)
    
    audio.save()

def encode_base64(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8').removesuffix('==').removesuffix('=')

def get_custom_5col_id(glyph_index: int, columns_model: Cols) -> int:
    glyph_index -= 1

    return {
        Cols.FIFTEEN_ZONE: PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL,
        Cols.THIRTY_THREE_ZONE: PHONE2_11COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL,
        Cols.TWENTY_SIX_ZONE: PHONE2A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL,
        Cols.THIRTY_SIX_ZONE: PHONE3A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL,
    }[columns_model][glyph_index][0]

def get_nearest_divisable_by(number: float, divisor: float) -> float:
    return round(number / divisor) * divisor

def get_number_of_columns_from_columns_model(columns_model: Cols) -> int:
    return {
        Cols.FIFTEEN_ZONE: 15,
        Cols.THIRTY_THREE_ZONE: 33,
        Cols.TWENTY_SIX_ZONE: 26,
        Cols.THIRTY_SIX_ZONE: 36
    }[columns_model]

def get_glyph_array_indexes(glyph_index: int, zone_index: int, columns_model: Cols) -> list[int]:
    glyph_index -= 1
    zone_index -= 1

    offset: int = 0

    match columns_model:
        case Cols.FIFTEEN_ZONE:
            if zone_index == -1:
                return PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_15COL[glyph_index]
            
            else:
                return PHONE1_15COL_GLYPH_ZONE_INDEX_TO_ARRAY_INDEXES_15COL[glyph_index + zone_index]
        
        case Cols.THIRTY_THREE_ZONE:
            offset += 15 if glyph_index > 3 else 0
            offset += 7 if glyph_index > 9 else 0

            if zone_index == -1:
                return PHONE2_11COL_GLYPH_INDEX_TO_ARRAY_INDEXES_33COL[glyph_index]
            
            else:
                return PHONE2_33_COL_GLYPH_ZONE_INDEX_TO_ARRAY_INDEXES_33COL[glyph_index + zone_index + offset]
        
        case Cols.TWENTY_SIX_ZONE:
            offset += 23 if glyph_index > 0 else 0

            if zone_index == -1:
                return PHONE2A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_26COL[glyph_index]
            
            else:
                return PHONE2A_26COL_GLYPH_INDEX_TO_ARRAY_INDEXES_26COL[glyph_index + zone_index + offset]
        
        case Cols.THIRTY_SIX_ZONE:
            offset += 19 if glyph_index > 0 else 0
            offset += 10 if glyph_index > 1 else 0

            if zone_index == -1:
                return PHONE3A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_36COL[glyph_index]
            
            else:
                return PHONE3A_36COL_GLYPH_INDEX_TO_ARRAY_INDEXES_36COL[glyph_index + zone_index + offset]

def labels_to_glyphs(data):
    labels = [l for l in data.split("\n") if l.strip()]
    grouped_glyphs = {}

    for line in labels:
        parts_tab = line.split("\t")

        if len(parts_tab) < 3:
            continue

        start_ms = int(float(parts_tab[0]) * 1000)
        end_ms = int(float(parts_tab[1]) * 1000)
        duration_ms = end_ms - start_ms
        label = parts_tab[2]

        parts_label = label.split("-")
        track_full = parts_label[0]
        brightness = parts_label[1]
        end_brightness = parts_label[2] if len(parts_label) == 4 else None

        if "." in track_full:
            track_id, segment_str = track_full.split(".")
            current_segment = int(segment_str) - 1
            has_segment = True

        else:
            track_id = track_full
            current_segment = None
            has_segment = False

        group_key = (start_ms, duration_ms, track_id, brightness, end_brightness, has_segment)

        if group_key in grouped_glyphs:
            if has_segment:
                grouped_glyphs[group_key]["segments"].append(current_segment)

        else:
            new_glyph = {
                "start": start_ms,
                "duration": duration_ms,
                "track": track_id,
                "brightness": brightness,
            }

            if end_brightness:
                new_glyph["end_brightness"] = end_brightness

            if has_segment:
                new_glyph["segments"] = [current_segment]

            grouped_glyphs[group_key] = new_glyph

    glyphs = list(grouped_glyphs.values())
    
    return glyphs

def convert_to_glyphs(path):
    file = open(path).read()
    
    if "\t" in file:
        return labels_to_glyphs(file)

    else:
        print("unknown")