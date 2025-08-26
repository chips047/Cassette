# add sebiai watermark

import os
import subprocess
import json
import csv
import re
import zlib
import math
import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from System import GlyphEffects
from System import Utils

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System.Constants import *

TIME_STEP_MS = 16.666

class NGlyphFile:
    def __init__(self, file_path: str):
        self.file_path: str = file_path
        self.format_version: int = 0
        self.raw_data: bytes = b''
        self.data: dict[str, ] = {}

        self.phone_model: PhoneModel = PhoneModel.PHONE1
        self.author: AuthorData | None = None
        self.custom1: Custom1Data | None = None
        self.watermark: Watermark | None = None
        self.legacy: bool = False

        with open(file_path, 'rb') as f:
            self.raw_data = f.read()
        
        self.data = json.loads(self.raw_data)
        self.format_version = int(self.data['VERSION'])
        self.phone_model = PhoneModel[str(self.data['PHONE_MODEL'])]

        author: list[str] = []
        author = list(self.data['AUTHOR'])
        self.author = AuthorData(author)
        
        custom1: list[str] = []
        custom1 = list(self.data['CUSTOM1'])
        self.custom1 = Custom1Data(custom1)
        
        if not self.data.get('WATERMARK'):
            return
        
        watermark: list[str] = []
        watermark = list(self.data['WATERMARK'])
        watermark_str = '\n'.join(watermark)

        salt_str: str = ""
        salt_str = str(self.data['SALT'])
        salt: bytes = b''
        salt = base64.b64decode(salt_str, validate=True)
        self.watermark = Watermark(watermark_str, salt)

        self.author.decrypt(self.watermark.to_key())

class AuthorData:
    class AuthorDataException(Exception):
        pass

    def __init__(self, data: list[str]):
        self.raw_data: bytes = b''
        self.data: list[list[int]] = []
        self.columns: int = 0
        self.columns_mode: ColsModder = ColsModder.FIFTEEN_ZONE

        self._parse_author_data(data)

        self.columns = len(self.data[0])
        for line in self.data:
            if len(line) != self.columns:
                raise AuthorData.AuthorDataException("AUTHOR data has different number of columns in some lines")
        
        self.columns_mode = N_COLUMNS_TO_COLS[self.columns]
    
    def _parse_author_data(self, data: list[str]):
        self.raw_data = ('\r\n'.join(data) + '\r\n').encode('utf-8')
        reader = csv.reader(data, delimiter=',', strict=True)
        self.data = [[int(e) for e in line if e.strip()] for line in list(reader) if ''.join(line).strip()]

    def decrypt(self, key: bytes) -> None:
        f = Fernet(key)
        author_len = self.data[0][0]
        compressed_token = bytes([e for line in self.data for e in line][1:author_len+1])
        
        data: list[str] = []
        data = zlib.decompress(f.decrypt(zlib.decompress(compressed_token))).decode('utf-8').splitlines()
        
        self._parse_author_data(data)
    
    def encrypt(self, key: bytes) -> None:
        f = Fernet(key)
        compressed_token = zlib.compress(f.encrypt(zlib.compress('\r\n'.join([f"{','.join([str(e) for e in line])}," for line in self.data]).encode('utf-8'), zlib.Z_BEST_COMPRESSION)), zlib.Z_BEST_COMPRESSION)
        encrypt_author_data: list[list[int]] = [[0 for n_column in range(self.columns)] for n_row in range(math.ceil((len(compressed_token) + 1) / self.columns))]
        encrypt_author_data[0][0] = len(compressed_token)
        
        for i, byte in enumerate(compressed_token, 1):
            encrypt_author_data[i // self.columns][i % self.columns] = byte
        
        self._parse_author_data([f"{','.join([str(e) for e in line])}," for line in encrypt_author_data])

class Custom1Data:
    class Custom1DataException(Exception):
        pass

    def __init__(self, data: list[str]):
        self.raw_data: bytes = b''
        self.data: list[list[int]] = []
        self.COLUMNS: int = 2

        self.raw_data = (','.join(data) + ',').encode('utf-8')
        reader = csv.reader(data, delimiter=',', strict=True)
        self.data = [[int(e) for e in line[0].split('-') if e.strip()] for line in list(reader) if line[0].strip()]

        for line in self.data:
            if len(line) != self.COLUMNS:
                raise Custom1Data.Custom1DataException("CUSTOM1 data has an invalid format")

class Watermark:
    class WatermarkException(Exception):
        pass

    def __init__(self, watermark: str, salt: bytes = os.urandom(16)) -> None:
        self.content = watermark.replace('\r\n', '\n').replace('\r', '\n')
        self.salt = salt

        if len(self.salt) != 16:
            raise Watermark.WatermarkException("The salt has to be 16 bytes long.")
    
    def to_key(self) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=480000
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.content.encode('utf-8')))
        return key

class FFmpeg:
    class FFmpegError(Exception):
        pass

    def __init__(self, ffmpeg_path: str, ffprobe_path: str):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.ffmpeg_base_command = [self.ffmpeg_path, '-v', 'error']
        self.ffprobe_base_command = [self.ffprobe_path, '-v', 'error', '-of', 'json']
    
    def write_metadata_to_audio_file(self, input_audio: str, output_file: str, metadata: dict[str, str]) -> None:
        ffmetadata_content = ';FFMETADATA1\n' + '\n'.join([f"{self._escape_ffmetadata(key)}={self._escape_ffmetadata(value)}" for key, value in metadata.items()]) + '\n'
        ffmpeg_command = self.ffmpeg_base_command + ['-i', input_audio, '-i', '-', '-y']
      
        for key in metadata.keys():
            ffmpeg_command += ['-metadata:s:a:0', f"{key}="]

        ffmpeg_command += [
            '-map_metadata', 
            '1', 
            '-c:a', 
            'copy',
            '-fflags', 
            '+bitexact', 
            '-flags:v', 
            '+bitexact', 
            '-flags:a', 
            '+bitexact',
            output_file
        ]

        result = subprocess.run(ffmpeg_command, input=ffmetadata_content.encode('utf-8'), capture_output=True, text=False) # This somehow fucks up on windows in text mode...
        if result.returncode != 0:
            raise FFmpeg.FFmpegError(f"Failed to write the metadata to the audio file: {result.stderr.decode('utf-8')}")
        
    def _escape_ffmetadata(self, content: str) -> str:
        return content.replace('\\', '\\\\').replace('=', '\\=').replace(';', '\\;').replace('#', '\\#').replace('\n', '\\\n')

class AudioFile:
    class AudioFileError(Exception):
        pass

    def __init__(self, audio_path: str, ffmpeg: FFmpeg):
        self.audio_path = audio_path
        
        ffprobe_command = ffmpeg.ffprobe_base_command + ['-show_streams', '-select_streams', 'a', audio_path]
        
        result = subprocess.run(
            ffprobe_command, 
            capture_output=True, 
            text=True, 
            encoding='utf-8'
        )
        if result.returncode != 0:
            raise AudioFile.AudioFileError(f"Failed to get the audio file metadata: {result.stderr}")
        
        self.metadata = json.loads(result.stdout)

        assert self.metadata['streams'][0]['codec_type'] == 'audio', "[Development Error] This file does not contain an audio stream. What happened here?"
    
    def get_tags(self) -> dict[str, str]:
        try:
            return self.metadata['streams'][0]['tags']
        
        except KeyError:
            return {}
    
    def get_audio_duration_ms(self) -> float:
        return float(self.metadata['streams'][0]['duration']) * 1000

def decode_base64(data: str) -> bytes:
    data_no_padding = data.rstrip('=')
    padding_length = (4 - (len(data_no_padding) % 4)) if (len(data_no_padding) % 4 != 0) else 0
    
    return base64.b64decode(data_no_padding + '=' * padding_length, validate=True)

def encode_base64(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8').removesuffix('==').removesuffix('=')

def write_metadata_to_audio_file(audio_file: AudioFile, nglyph_file: NGlyphFile, output_path: str, title: str, ffmpeg: FFmpeg, auto_fix_audio: bool, file_title: str) -> None:
    required_n_lines = math.ceil(audio_file.get_audio_duration_ms() / TIME_STEP_MS)
    
    if required_n_lines > len(nglyph_file.author.data):
        if required_n_lines - 1 == len(nglyph_file.author.data):
            nglyph_file.author.data.append([0 for _ in range(nglyph_file.author.columns)])

    author_compressed = zlib.compress(nglyph_file.author.raw_data, zlib.Z_BEST_COMPRESSION)
    custom1_compressed = zlib.compress(nglyph_file.custom1.raw_data, zlib.Z_BEST_COMPRESSION)

    author_compressed_base64 = encode_base64(author_compressed)
    custom1_compressed_base64 = encode_base64(custom1_compressed)

    author_compressed_base64 = '\n'.join([author_compressed_base64[i:i+76] for i in range(0, len(author_compressed_base64), 76)]) + '\n'
    custom1_compressed_base64 = '\n'.join([custom1_compressed_base64[i:i+76] for i in range(0, len(custom1_compressed_base64), 76)]) + '\n'

    audio_file_ext_split = os.path.splitext(os.path.basename(audio_file.audio_path))
    new_audio_file_path = os.path.join(output_path, file_title + audio_file_ext_split[1])

    custom2 = STRING_TO_COLS.get(nglyph_file.author.columns_mode, None)

    metadata = {
        'TITLE': title,
        'ALBUM': f"Cassette 0.1",
        'AUTHOR': author_compressed_base64,
        'COMPOSER': f"v1-{DEVICE_CODENAME[nglyph_file.author.columns_mode]} Glyph Composer",
        'CUSTOM1': custom1_compressed_base64,
        'CUSTOM2': custom2,
    }
    
    if nglyph_file.watermark is not None:
        metadata['GLYPHER_WATERMARK'] = '\n' + nglyph_file.watermark.content

    ffmpeg.write_metadata_to_audio_file(audio_file.audio_path, new_audio_file_path, metadata)

def get_custom_5col_id(glyph_index: int, columns_model: Cols) -> int:
    glyph_index -= 1

    match columns_model:
        case Cols.FIVE_ZONE | Cols.FIFTEEN_ZONE:
            return PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index][0]
        
        case Cols.ELEVEN_ZONE | Cols.THIRTY_THREE_ZONE:
            return PHONE2_11COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index][0]
        
        case Cols.THREE_ZONE_2A | Cols.TWENTY_SIX_ZONE:
            return PHONE2A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index][0]
        
        case Cols.THREE_ZONE_3A | Cols.THIRTY_SIX_ZONE:
            return PHONE3A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index][0]
        
        case _:
            raise ValueError(f"[Programming Error] Missing columns model in switch case: '{columns_model}'. Please report this error to the developer.")

def get_nearest_divisable_by(number: float, divisor: float) -> float:
    return round(number / divisor) * divisor

def get_numer_of_columns_from_columns_model(columns_model: Cols) -> int:
    match columns_model:
        case Cols.FIVE_ZONE:
            return 5
        
        case Cols.FIFTEEN_ZONE:
            return 15
        
        case Cols.ELEVEN_ZONE | Cols.THIRTY_THREE_ZONE:
            return 33
        
        case Cols.THREE_ZONE_2A | Cols.TWENTY_SIX_ZONE:
            return 26
        
        case Cols.THREE_ZONE_3A | Cols.THIRTY_SIX_ZONE:
            return 36
        
        case _:
            raise ValueError(f"[Programming Error] Missing columns model in switch case: '{columns_model}'. Please report this error to the developer.")

class LabelFile:
    _TIME_STEP_MS = 16.666
    _MAX_LIGHT_LEVEL = 4095
    _SUPPORTED_LABEL_VERSIONS = [1]
    _SUPPORTED_PHONE_MODELS = list(map(lambda x: x.name, PhoneModel))

    class LabelFileException(Exception):
        pass

    def __iter__(self):
        return iter(self.labels)
    
    def __getitem__(self, index: int) -> 'LabelFile.Label':
        return self.labels[index]
    
    def __str__(self) -> str:
        return f"LabelFile('{self.file}', {len(self.labels)} Labels: {self.labels[:3] + ['...'] if len(self.labels) > 3 else self.labels})"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def __init__(self, file_path: str) -> None:
        self.file: str = file_path
        self.labels: list[LabelFile.Label] = []
        self.contains_zone_labels: bool = False
        self.columns_model: Cols = Cols.FIVE_ZONE
        self.label_version: int = 0
        self.phone_model: PhoneModel = self._determine_phone_model(file_path)

        match self.phone_model:
            case PhoneModel.PHONE1:
                regex = re.compile(REGEX_PATTERN_LABEL_TEXT_PHONE1)
            
            case PhoneModel.PHONE2:
                regex = re.compile(REGEX_PATTERN_LABEL_TEXT_PHONE2)
            
            case PhoneModel.PHONE2A:
                regex = re.compile(REGEX_PATTERN_LABEL_TEXT_PHONE2A)
            
            case PhoneModel.PHONE3A:
                regex = re.compile(REGEX_PATTERN_LABEL_TEXT_PHONE3A)
            
            case _:
                raise ValueError(f"[Programming Error] Missing phone model in switch case: '{self.phone_model}'. Please report this error to the developer.")

        found_end_label: bool = False
        encountered_error: bool = False
        
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t', strict=True, skipinitialspace=True)
            
            for row in reader:
                if len(row) == 0 or row[0].strip() == "":
                    continue

                if len(row) != 3:
                    raise LabelFile.LabelFileException(f"Invalid Label file format in line {reader.line_num}. The file should contain 3 columns: 'Time Start', 'Time End' and 'Label Text'.")
                
                self.labels.append(LabelFile.Label.from_list(row, reader.line_num))

                if self.labels[-1].is_end_label:
                    found_end_label = True
                
                else:
                    if not self.labels[-1].is_version_label and not self.labels[-1].is_phone_model_label:
                        self.labels[-1].extract_text_values(regex)
        
        if not found_end_label:
            encountered_error = True

        if encountered_error:
            raise LabelFile.LabelFileException("Encountered errors while parsing the Label text values. Please resolve the errors above. Make sure that you used the right phone model.")
        
        if not all(self.labels[i].time_from_ms <= self.labels[i+1].time_from_ms for i in range(len(self.labels)-1)):
            self.labels.sort(key=lambda x: x.time_from_ms)

        self.label_version = self._get_label_version()
        self.contains_zone_labels = any(label.is_zone_label for label in self.labels)
        
        match self.phone_model:
            case PhoneModel.PHONE1:
                self.columns_model = Cols.FIFTEEN_ZONE if self.contains_zone_labels else Cols.FIVE_ZONE
            
            case PhoneModel.PHONE2:
                self.columns_model = Cols.THIRTY_THREE_ZONE if self.contains_zone_labels else Cols.ELEVEN_ZONE
            
            case PhoneModel.PHONE2A:
                self.columns_model = Cols.TWENTY_SIX_ZONE if self.contains_zone_labels else Cols.THREE_ZONE_2A
            
            case PhoneModel.PHONE3A:
                self.columns_model = Cols.THIRTY_SIX_ZONE if self.contains_zone_labels else Cols.THREE_ZONE_3A
            
            case _:
                raise ValueError(f"[Programming Error] Missing phone model in switch case: '{self.phone_model}'. Please report this error to the developer.")

    def _determine_phone_model(self, file_path: str) -> PhoneModel:
        phone_model: PhoneModel | None = None

        with open(file_path, newline='', encoding='utf-8') as f:
            
            for line in f:
                m = re.search(r'PHONE_MODEL=(\w+)', line)
                if m is not None:
                    phone_model_string: str = m.group(1)
                    phone_model = PhoneModel[phone_model_string]
        
        return phone_model

    def _get_label_version(self) -> int:        
        version_labels = [label for label in self.labels if label.is_version_label]

        label_version_match = re.match(LabelFile.Label._REGEX_PATTERN_LABEL_VERSION, version_labels[0].text)
        label_version = int(label_version_match.group(1))

        return label_version

    def get_nglyph_data(self) -> tuple[list[str], list[str]]:
        end_label: LabelFile.Label = next(label for label in self.labels if label.is_end_label)
        author_lines = math.ceil(end_label.time_to_ms / LabelFile._TIME_STEP_MS)

        author_data: list[list[int]] = [[0 for x in range(get_numer_of_columns_from_columns_model(self.columns_model))] for y in range(author_lines)]
        custom1_data: list[str] = []

        for label in self.labels:
            if label.is_end_label or label.is_version_label or label.is_phone_model_label:
                continue

            parsed_label = label.to_parsed_label(self.columns_model)

            overwrites: int = 0
            steps = list(range(round(parsed_label.rastered_time_from_ms/LabelFile._TIME_STEP_MS), round(parsed_label.rastered_time_to_ms/LabelFile._TIME_STEP_MS)))
            
            for i, row in enumerate(steps, 1 if parsed_label.absolute_light_level_from <= parsed_label.absolute_light_level_to else 0):
                match parsed_label.light_mode:
                    case "LIN":
                        light_level = round(parsed_label.absolute_light_level_from + ((parsed_label.absolute_light_level_to - parsed_label.absolute_light_level_from) / len(steps)) * i)
                
                for index in parsed_label.array_indexes:
                    if author_data[row][index] != 0:
                        overwrites += 1
                    
                    author_data[row][index] = light_level

            custom1_data.append(f"{round(label.time_from_ms)}-{parsed_label.custom_5col_id}")

        return ([f"{','.join([str(e) for e in line])}," for line in author_data], custom1_data)
    
    class Label:
        _TIME_FROM = 0
        _TIME_TO = 1
        _TEXT_CONTENT = 2
        _REGEX_PATTERN_LABEL_VERSION = r'^LABEL_VERSION=(\d+)$'
        _REGEX_PATTERN_LABEL_PHONE_MODEL = re.compile(r'^PHONE_MODEL=(\w+)$')

        def __str__(self) -> str:
            return f"Label(time_from: {self.time_from_ms}ms, time_to: {self.time_to_ms}ms, time_delta: {self.time_delta_ms}ms, text: '{self.text}', is_end_label: {self.is_end_label}, line_num:{self.line_num})"        
        
        def __repr__(self) -> str:
            return self.__str__()

        def __init__(self, time_from: float, time_to: float, text: str, line_num: int) -> None:
            self.time_from_ms: float = round(time_from * 1000, 3)
            self.time_to_ms: float = round(time_to * 1000, 3)
            self.time_delta_ms: float = round(self.time_to_ms - self.time_from_ms, 3)
            self.text: str = text.strip()
            self.is_end_label: bool = self.text == "END"
            self.is_version_label: bool = re.match(LabelFile.Label._REGEX_PATTERN_LABEL_VERSION, self.text) is not None
            self.is_phone_model_label: bool = re.match(LabelFile.Label._REGEX_PATTERN_LABEL_PHONE_MODEL, self.text) is not None
            self.line_num: int = line_num

            self.glyph_index: int = 0
            self.zone_index: int = 0
            self.relative_light_level_from: int = 0
            self.relative_light_level_to: int = 0
            self.light_mode: str = "LIN"
            self.is_zone_label: bool = False

        @staticmethod
        def from_list(list: list[str], line_num: int) -> 'LabelFile.Label':
            if len(list) != 3:
                raise ValueError("The list must contain 3 elements.")
            
            time_from = float(list[LabelFile.Label._TIME_FROM].replace(',', '.'))
            time_to = float(list[LabelFile.Label._TIME_TO].replace(',', '.'))
            text = list[LabelFile.Label._TEXT_CONTENT]

            return LabelFile.Label(time_from, time_to, text, line_num)
        
        def extract_text_values(self, regex: re.Pattern[str]) -> None:
            result = regex.match(self.text)

            glyph_index = int(result.group(1))
            zone_index = int(result.group(2)) if result.group(2) is not None else 0
            relative_light_level_from = int(result.group(3))
            relative_light_level_to = int(result.group(4)) if result.group(4) is not None else relative_light_level_from
            light_mode = result.group(5) if result.group(5) is not None else "LIN"

            self.glyph_index = glyph_index
            self.zone_index = zone_index
            self.relative_light_level_from = relative_light_level_from
            self.relative_light_level_to = relative_light_level_to
            self.light_mode = light_mode
            self.is_zone_label = zone_index != 0

        def to_parsed_label(self, columns_model: Cols) -> 'LabelFile.ParsedLabel':
            parsed_label = LabelFile.ParsedLabel()
            parsed_label.rastered_time_from_ms = get_nearest_divisable_by(self.time_from_ms, LabelFile._TIME_STEP_MS)
            parsed_label.rastered_time_to_ms = get_nearest_divisable_by(self.time_to_ms, LabelFile._TIME_STEP_MS)
            parsed_label.rastered_time_delta_ms = parsed_label.rastered_time_to_ms - parsed_label.rastered_time_from_ms

            if parsed_label.rastered_time_delta_ms == 0:
                parsed_label.rastered_time_to_ms += LabelFile._TIME_STEP_MS
                parsed_label.rastered_time_delta_ms = LabelFile._TIME_STEP_MS

            parsed_label.array_indexes = get_glyph_array_indexes(self.glyph_index, self.zone_index, columns_model)
            parsed_label.custom_5col_id = get_custom_5col_id(self.glyph_index, columns_model)

            parsed_label.absolute_light_level_from = round(self.relative_light_level_from * LabelFile._MAX_LIGHT_LEVEL / 100.0)
            parsed_label.absolute_light_level_to = round(self.relative_light_level_to * LabelFile._MAX_LIGHT_LEVEL / 100.0)
            
            parsed_label.light_mode = self.light_mode
            parsed_label.is_zone_label = self.is_zone_label

            return parsed_label
    
    class ParsedLabel:
        def __init__(self) -> None:
            self.rastered_time_from_ms: float = 0
            self.rastered_time_to_ms: float = 0
            self.rastered_time_delta_ms: float = 0
            self.array_indexes: list[int] = []
            self.custom_5col_id: int = 0
            self.absolute_light_level_from: int = 0
            self.absolute_light_level_to: int = 0
            self.light_mode: str = "LIN"
            self.is_zone_label: bool = False

def get_glyph_array_indexes(glyph_index: int, zone_index: int, columns_model: Cols) -> list[int]:
    glyph_index -= 1
    zone_index -= 1

    offset: int = 0

    match columns_model:
        case Cols.FIVE_ZONE:
            return PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index]
        
        case Cols.FIFTEEN_ZONE:
            offset += 3 if glyph_index > 2 else 0
            offset += 7 if glyph_index > 3 else 0

            if zone_index == -1:
                return PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_15COL[glyph_index]
            
            else:
                return PHONE1_15COL_GLYPH_ZONE_INDEX_TO_ARRAY_INDEXES_15COL[glyph_index + zone_index + offset]
        
        case Cols.ELEVEN_ZONE:
            return PHONE2_11COL_GLYPH_INDEX_TO_ARRAY_INDEXES_33COL[glyph_index]
        
        case Cols.THIRTY_THREE_ZONE:
            offset += 15 if glyph_index > 3 else 0
            offset += 7 if glyph_index > 9 else 0

            if zone_index == -1:
                return PHONE2_11COL_GLYPH_INDEX_TO_ARRAY_INDEXES_33COL[glyph_index]
            
            else:
                return PHONE2_33_COL_GLYPH_ZONE_INDEX_TO_ARRAY_INDEXES_33COL[glyph_index + zone_index + offset]
        
        case Cols.THREE_ZONE_2A:
            return PHONE2A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_26COL[glyph_index]
        
        case Cols.TWENTY_SIX_ZONE:
            offset += 23 if glyph_index > 0 else 0

            if zone_index == -1:
                return PHONE2A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_26COL[glyph_index]
            
            else:
                return PHONE2A_26COL_GLYPH_INDEX_TO_ARRAY_INDEXES_26COL[glyph_index + zone_index + offset]
        
        case Cols.THREE_ZONE_3A:
            return PHONE3A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_36COL[glyph_index]
        
        case Cols.THIRTY_SIX_ZONE:
            offset += 19 if glyph_index > 0 else 0
            offset += 10 if glyph_index > 1 else 0

            if zone_index == -1:
                return PHONE3A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_36COL[glyph_index]
            
            else:
                return PHONE3A_36COL_GLYPH_INDEX_TO_ARRAY_INDEXES_36COL[glyph_index + zone_index + offset]
        
        case _:
            raise ValueError(f"[Programming Error] Missing columns model in switch case: '{columns_model}'. Please report this error to the developer.")

#def get_custom_5col_id(glyph_index: int, columns_model: Cols) -> int:
#    glyph_index -= 1
#
#    match columns_model:
#        case Cols.FIVE_ZONE | Cols.FIFTEEN_ZONE:
#            return PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index][0]
#        
#        case Cols.ELEVEN_ZONE | Cols.THIRTY_THREE_ZONE:
#            return PHONE2_11COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index][0]
#        
#        case Cols.THREE_ZONE_2A | Cols.TWENTY_SIX_ZONE:
#            return PHONE2A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index][0]
#        
#        case Cols.THREE_ZONE_3A | Cols.THIRTY_SIX_ZONE:
#            return PHONE3A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL[glyph_index][0]
#        
#        case _:
#            raise ValueError(f"[Programming Error] Missing columns model in switch case: '{columns_model}'. Please report this error to the developer.")

def compile_glyph_file(label_file_path: str, output_directory: str) -> str:
    label_file_path = os.path.abspath(label_file_path)
    output_directory = os.path.abspath(output_directory)

    label_file = LabelFile(label_file_path)

    nglyph_data = {
        'VERSION': 1,
        'PHONE_MODEL': label_file.phone_model.name,
    }

    nglyph_data['AUTHOR'], nglyph_data['CUSTOM1'] = label_file.get_nglyph_data()

    base_filename = os.path.splitext(os.path.basename(label_file_path))[0]
    nglyph_file_path = os.path.join(output_directory, base_filename + ".cassette")

    with open(nglyph_file_path, 'w', newline='\r\n', encoding='utf-8') as f:
        json.dump(nglyph_data, f, indent=4)

    return nglyph_file_path

def nglyph_to_ogg(audio_path, nglyph_path, output_dir, file_title):
    ffmpeg = FFmpeg("ffmpeg", "ffprobe")

    audio_file = AudioFile(audio_path, ffmpeg)
    nglyph_file = NGlyphFile(nglyph_path)

    write_metadata_to_audio_file(audio_file, nglyph_file, output_dir, "Test", ffmpeg, False, file_title)

def f6(x):
    x = float(x)
    return "{:.6f}".format(x)

def smart_number(s):
    try:
        return int(s)
    
    except ValueError:
        return float(s)

def export_ringtone(out_path, composition):
    model = composition.model
    labels = []
    only_singles_and_segments, only_effects, only_segments_with_effects = composition.sorted_glyphs()
    
    if not model:
        return QMessageBox.critical(None, "Failed to export the ringtone", f"Model {model} is not found.")
    
    labels.extend(GlyphEffects.glyphs_to_strings(only_singles_and_segments))

    for glyph in only_effects:
        labels.extend(GlyphEffects.effect_to_label(glyph, glyph["effect"], model, composition.bpm))
    
    labels = "\n".join(labels)
    labels = f"0.000000\t0.000000\tLABEL_VERSION=1\n0.000000\t0.000000\tPHONE_MODEL={model}\n{labels}\n{f6(composition.audio_duration)}\t{f6(composition.audio_duration)}\tEND"
    
    try:
        labels_file = open(Utils.get_cache_path("Labels.txt"), "w+")
        labels_file.write(labels)
        labels_file.close()
    
    except Exception as e: return QMessageBox.critical(None, "Failed to export the ringtone", f"Something went wrong while writing the Label file. Report this error to chips047: {str(e)}")
    
    compile_glyph_file(Utils.get_cache_path("Labels.txt"), Utils.get_cache_path(""))
    
    try: nglyph_to_ogg(f"{out_path}/cropped_song.ogg", Utils.get_cache_path("Labels.cassette"), out_path, "Composed_withCassette")
    except Exception as e: QMessageBox.critical(None, "Failed to export the ringtone", f"Failed to write the metadata. Report this error to chips047: {str(e)}")