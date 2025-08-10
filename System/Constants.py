from enum import Enum

PortVariants = {
    "PHONE1": [
        "2"
    ],
    "PHONE2": [
        "1"
    ],
    "PHONE2A": [
        "1",
        "2",
        "3a",
    ],
    "PHONE3A": [
        "1",
        "2",
        "2a"
    ]
}

def number_model_to_code(number: str):
    return {
        "1": "PHONE1",
        "2": "PHONE2",
        "2a": "PHONE2A",
        "3a": "PHONE3A"
    }.get(number)

def number_model_to_model(number: str):
    return {
        "1": "Phone (1)",
        "2": "Phone (2)",
        "2a": "Phone (2a)",
        "3a": "Phone (3a)"
    }.get(number)

def model_to_code(model: str):
    return {
        "Phone (1)": "PHONE1",
        "Phone (2)": "PHONE2",
        "Phone (2a)": "PHONE2A",
        "Phone (3a)": "PHONE3A"
    }.get(model)

def code_to_number_model(code: str):
    return {
        "PHONE1": "1",
        "PHONE2": "2",
        "PHONE2A": "2a",
        "PHONE3A": "3a"
    }.get(code)

def code_to_model(code: str):
    return {
        "PHONE1": "Phone (1)",
        "PHONE2": "Phone (2)",
        "PHONE2A": "Phone (2a)",
        "PHONE3A": "Phone (3a)"
    }.get(code)

# ANIMATIONS :))) (ms)
VALUE_POPUP_IN = 220

TOOLTIP_POPUP_IN = 600
TOOLTIP_TEXT_FADE_IN = 250

TEXTBOX_SHAKE = 100
TEXTBOX_SHAKE_PER = 30
TEXTBOX_INPUT = 250

DIALOG_POPUP_IN = 550
DIALOG_POPUP_OUT = 300
DIALOG_POPUP_FADEOUT = 100

# UI Sounds


# Perfomance
TILE_SIZE = 1024

# Compositor Defaults
DEFAULT_SCALING = 200.0

GLYPH_RESIZE_SENSITIVITY = 10
ARROW_KEY_INCREMENT = 1

STATUS_BAR_DEFAULT = f"Cassette - Preview ({open('version').read()})"

SAMPLING_RATE = 22050

# Qt Timer FPS
FPS_60 = 16
FPS_120 = 8
FPS_30 = 33

# BPM and Beat Detector
BEAT_MAX_DISTANCE = 0.1
STRENGTH_THRESHOLD = 0.07

# Models and Related
ModelSegments = {
    "PHONE1": {"4": 8},
    "PHONE2": {"4": 16, "10": 8},
    "PHONE2A": {"1": 24},
    "PHONE3A": {"1": 20, "2": 11, "3": 5},
}

ModelTracks = {
    "Phone (1)": 5,
    "Phone (2)": 11,
    "Phone (2a)": 3,
    "Phone (3a)": 3
}

# Columns (To export)
class PhoneModel(Enum):
    PHONE1 = 0
    PHONE2 = 1
    PHONE2A = 2
    PHONE3A = 3

class ColsModder(Enum):
    FIVE_ZONE = 0
    FIFTEEN_ZONE = 1
    ELEVEN_ZONE = 2
    THIRTY_THREE_ZONE = 3
    THREE_ZONE = 4
    TWENTY_SIX_ZONE = 5
    THIRTY_SIX_ZONE = 6

class Cols(Enum):
    FIVE_ZONE = 0
    FIFTEEN_ZONE = 1
    ELEVEN_ZONE = 2
    THIRTY_THREE_ZONE = 3
    THREE_ZONE_2A = 4
    TWENTY_SIX_ZONE = 5
    THREE_ZONE_3A = 6
    THIRTY_SIX_ZONE = 7

STRING_COLS_TO_PHONE_MODEL = {
    '5cols': PhoneModel.PHONE1,
    '33cols': PhoneModel.PHONE2,
    '26cols': PhoneModel.PHONE2A,
    '36cols': PhoneModel.PHONE3A,
}

STRING_TO_COLS: dict[ColsModder, str] = {
    ColsModder.FIVE_ZONE: '5cols',
    ColsModder.FIFTEEN_ZONE: '5cols',
    ColsModder.THIRTY_THREE_ZONE: '33cols',
    ColsModder.TWENTY_SIX_ZONE: '26cols',
    ColsModder.THIRTY_SIX_ZONE: '36cols',
}

N_COLUMNS_TO_COLS = {
    5: ColsModder.FIVE_ZONE,
    15: ColsModder.FIFTEEN_ZONE,
    33: ColsModder.THIRTY_THREE_ZONE,
    26: ColsModder.TWENTY_SIX_ZONE,
    36: ColsModder.THIRTY_SIX_ZONE,
}

DEVICE_CODENAME = {
    ColsModder.FIVE_ZONE: 'Spacewar',
    ColsModder.FIFTEEN_ZONE: 'Spacewar',
    ColsModder.THIRTY_THREE_ZONE: 'Pong',
    ColsModder.TWENTY_SIX_ZONE: 'Pacman',
    ColsModder.THIRTY_SIX_ZONE: 'Asteroids',
}

# Regex
REGEX_PATTERN_LABEL_TEXT_PHONE1 = r'^([1-5])(?:\.((?:(?<![1-24-5]\.)[1-4])|(?:(?<![1-35]\.)[1-8])))?-(\d{1,2}|100)(?:-(\d{1,2}|100))?(?:-(EXP|LIN|LOG))?$'
REGEX_PATTERN_LABEL_TEXT_PHONE2 = r'^([1-9]|1[0-1])(?:\.((?:(?<![0-35-9]\.)[1-9]|1[0-6])|(?:(?<![1-9]\.)[1-8])))?-(\d{1,2}|100)(?:-(\d{1,2}|100))?(?:-(EXP|LIN|LOG))?$'
REGEX_PATTERN_LABEL_TEXT_PHONE2A = r'^([1-3])(?:(?<![23])\.([1-9]|1\d|2[0-4]))?-(\d{1,2}|100)(?:-(\d{1,2}|100))?(?:-(EXP|LIN|LOG))?$'
REGEX_PATTERN_LABEL_TEXT_PHONE3A = r'^([1-3])(?:\.((?:(?<=1\.)(?:[1-9]|1\d|20))|(?:(?<=2\.)(?:[1-9]|1[0-1]))|(?:(?<=3\.)[1-5])))?-(\d{1,2}|100)(?:-(\d{1,2}|100))?(?:-(EXP|LIN|LOG))?$'

# Column Lists
PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL = [[i] for i in range(5)]
PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_15COL = [[0], [1], list(range(2, 6)), list(range(7, 15)), [6]]
PHONE1_15COL_GLYPH_ZONE_INDEX_TO_ARRAY_INDEXES_15COL = [[0], [1], [4], [5], [2], [3], [14], [13], [12], [11], [10], [9], [8], [7], [6]]
PHONE2_11COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL = [[0], [0], [1], [2], [2], [2], [2], [2], [2], [3], [4]]
PHONE2_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_11COL = [list(range(0, 2)), [2], list(range(3, 9)), [9], [10]]
PHONE2_11COL_GLYPH_INDEX_TO_ARRAY_INDEXES_33COL = [[0], [1], [2], list(range(3, 19)), [19], [20], [21], [22], [23], list(range(25, 33)), [24]]
PHONE2_33_COL_GLYPH_ZONE_INDEX_TO_ARRAY_INDEXES_33COL = [[i] for i in range(24)] + [[32], [31], [30], [29], [28], [27], [26], [25], [24]]
PHONE2A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL = [[i] for i in range(3)]
PHONE2A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_26COL = [list(range(0, 24)), [24], [25]]
PHONE2A_26COL_GLYPH_INDEX_TO_ARRAY_INDEXES_26COL = [[23 - i] for i in range(24)] + [[24], [25]]
PHONE3A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL = [[i] for i in range(3)]
PHONE3A_3COL_GLYPH_INDEX_TO_ARRAY_INDEXES_36COL = [list(range(0, 20)), list(range(20, 31)), list(range(31, 36))]
PHONE3A_36COL_GLYPH_INDEX_TO_ARRAY_INDEXES_36COL = [[i] for i in range(36)]

models = {
    "Phone (1)": "PHONE1",
    "Phone (2)": "PHONE2",
    "Phone (2a)": "PHONE2A",
    "Phone (3a)": "PHONE3A"
}

ModelCodes = {
    "A063": "Phone (1)",
    "A065": "Phone (2)",
    "AIN065": "Phone (2)",
    "A142": "Phone (2a)",
    "A142P": "Phone (2a)",
    "A059": "Phone (3a)",
    "A059P": "Phone (3a)"
}