from enum import Enum
from PyQt5.QtCore import *

from System import Utils

CurrentSettings = {}

def load_settings():
    qsettings_cache = QSettings("chips047", "Cassette")

    CurrentSettings.clear()
    CurrentSettings.update(
        {
            k: Utils.auto_cast(qsettings_cache.value(k)) for k in qsettings_cache.allKeys()
        }
    )

def prepare_default_settings(setting_components):
    settings = QSettings("chips047", "Cassette")
    existing_keys = set(settings.allKeys())
    new_keys = set()
    exceptions = ["tutorial_shown"]

    for page_name, components in setting_components.items():
        for element_key, params in components.items():
            key = params["key"]
            new_keys.add(key)

            if not settings.contains(key):
                if element_key.startswith("checkbox"):
                    default_val = params.get("default", False)
                
                elif element_key.startswith("slider"):
                    default_val = params.get("default", params.get("min", 0))
                
                elif element_key.startswith("selector"):
                    default_index = params.get("default", 0)
                    options = list(params.get("map", {}).values())
                    default_val = options[default_index] if 0 <= default_index < len(options) else None
                
                else:
                    default_val = None

                if default_val is not None:
                    settings.setValue(key, default_val)

    obsolete_keys = existing_keys - new_keys
    for key in obsolete_keys:
        if key in exceptions:
            continue
        
        settings.remove(key)

    settings.sync()

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

def code_to_number_model(code: str):
    return {
        "PHONE1": "1",
        "PHONE2": "2",
        "PHONE2A": "2a",
        "PHONE3A": "3a"
    }.get(code)

def is_segmented(track, model):
    segments = {
        "PHONE1": {"7": 8},
        "PHONE2": {"4": 16, "10": 8},
        "PHONE2A": {"1": 24},
        "PHONE3A": {"1": 20, "2": 11, "3": 5}
    }

    return segments.get(model, {}).get(str(track), False)

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

# Perfomance
TILE_SIZE = 1024

# Compositor Defaults
DEFAULT_SCALING = 200.0

GLYPH_RESIZE_SENSITIVITY = 10
ARROW_KEY_INCREMENT = 1

STATUS_BAR_DEFAULT = f"Cassette {open('version').read()}"

SAMPLING_RATE = 22050

# Qt Timer FPS
FPS_60 = 16
FPS_120 = 8
FPS_30 = 33

# Models and Related
ModelSegments = {
    "PHONE1": {"7": 8},
    "PHONE2": {"4": 16, "10": 8},
    "PHONE2A": {"1": 24},
    "PHONE3A": {"1": 20, "2": 11, "3": 5},
}

def get_segments(model, track):
    return ModelSegments.get(model, {}).get(track)

ModelTracks = {
    "PHONE1": 8,
    "PHONE2": 11,
    "PHONE2A": 3,
    "PHONE3A": 3
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

# Column Lists
PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_5COL = [[i] for i in range(8)]
PHONE1_5COL_GLYPH_INDEX_TO_ARRAY_INDEXES_15COL = [[0], [1], [4], [5], [2], [3], list(range(7, 15)), [6]]
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

ModelCodes = {
    "A063": "Phone (1)",
    "A065": "Phone (2)",
    "AIN065": "Phone (2)",
    "A142": "Phone (2a)",
    "A142P": "Phone (2a)",
    "A059": "Phone (3a)",
    "A059P": "Phone (3a)"
}

DEFAULT_DURATION = 100
DEFAULT_BRIGHTNESS = 100

SettingsDict = {
    "Visuals and Performance": {
        "checkbox1": {
            "title": "Reduce Animations",
            "key": "reduce_animations",
            "description": "Reduce all these cool animations :(",
            "default": False
        },
        "checkbox2": {
            "title": "Antialiasing",
            "key": "antialiasing",
            "description": "Strongly affects performance on weak computers.",
            "default": True
        },
        "selector3": {
            "title": "Waveform Tile Width",
            "key": "tile_width",
            "choices": ["512", "1024", "2048"],
            "map": {
                "512": 512,
                "1024": 1024,
                "2048": 2048
            },
            "default": 1
        },
        "selector4": {
            "title": "Waveform Smoothing",
            "key": "waveform_smoothing",
            "choices": ["Accuracy", "Balance", "Smooth"],
            "map": {
                "Accuracy": 0.5,
                "Balance": 1.7,
                "Smooth": 3
            },
            "default": 1
        },
        "checkbox5": {
            "title": "Center Playhead",
            "description": "Move the playhead to the center.",
            "key": "center_playhead",
            "default": False
        },
        "selector6": {
            "title": "Default Scaling (ms / px)",
            "key": "default_scaling",
            "choices": ["100", "200", "300", "400", "500"],
            "map": {
                "100": 100,
                "200": 200,
                "300": 300,
                "400": 400,
                "500": 500
            },
            "default": 1
        }
    },

    "Connectivity & Devices": {
        "checkbox1": {
            "title": "Device Auto - Search",
            "key": "auto_search",
            "description": "Automatically searches for a connected Nothing Phone.",
            "default": True
        },
#        "checkbox2": {
#            "title": "Instant Device Export",
#            "key": "device_export",
#            "description": "Exported ringtones will be copied to your Nothing Phone.",
#            "default": True
#        }
    },

    "User Experience": {
        "checkbox1": {
            "title": "Disable sounds",
            "key": "disable_sounds",
            "description": "All UI sounds will be disabled :(",
            "default": False
        },
        "slider2": {
            "title": "Playhead Arrow Move Increment",
            "min": 1,
            "max": 10,
            "key": "arrow_increment",
            "default": 1
        },
        "selector3": {
            "title": "Animation Multiplier",
            "key": "animation_multiplier",
            "choices": ["0.75x", "1.0x", "1.15x", "1.25x", "1.5x", "3.0x", "5.0x", "10.0x", "20.0x"],
            "map": {
                "0.75x": "0.75",
                "1.0x": "1.0",
                "1.15x": "1.15",
                "1.25x": "1.25",
                "1.5x": "1.5",
                "3.0x": "3.0",
                "5.0x": "5.0",
                "10.0x": "10.0",
                "20.0x": "20.0"
            },
            "default": 1
        }
    }
}