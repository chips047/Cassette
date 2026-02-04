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

    for _, components in setting_components.items():
        for element_params in components:
            element_type = element_params["type"]
            key = element_params["key"]
            new_keys.add(key)

            if not settings.contains(key):
                if element_type == "checkbox":
                    default_val = element_params.get("default", False)

                elif element_type == "slider":
                    default_val = element_params.get("default", element_params.get("min", 0))

                elif element_type.startswith("selector"):
                    default_val = element_params["map"][element_params["default"]]
                
                else:
                    default_val = None

                if default_val is not None:
                    settings.setValue(key, default_val)

    obsolete_keys = existing_keys - new_keys
    for key in obsolete_keys:
        if key in exceptions:
            continue
        
        if key != "new_user":
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

ModelVisualizerMaps = {
    "PHONE1": {
        "glyphs": {
            "1": {
                "svg": "M41.66,47.69 V58.08 C41.66,68.73 33.01,77.38 22.36,77.38 C11.71,77.38 3.06,68.73 3.06,58.08 V22.18 C3.06,11.53 11.71,2.88 22.36,2.88 C33.01,2.88 41.66,11.53 41.66,22.18",
                "position": (5, 0)
            },
            
            "2": {
                "svg": "M3.54,43.78 L37.25,3.61",
                "position": (130, 10)
            },

            "3": {
                "svg": "M158.48,37.83 C138.94,14.3 109.87,0.76 79.29,0.96 C55.43,0.96 34.12,9.45 18.5,23.15",
                "position": (10, 90)
            },
            
            "4": {
                "svg": "M18.5,23.15 C9.2,31.32 3.5,41.5 0.57,47.68 L0.57,125.8",
                "position": (10, 90)
            },
            
            "5": {
                "svg": "M0.57,125.8 V158.4 C19.95,191.2 49.11,205.12 79.94,205.12 C85.2,205.12 90.3,204.5 95.1,203.4",
                "position": (10, 90)
            },
            
            "6": {
                "svg": "M95.1,203.4 C123.5,197.2 146.8,183.5 159.31,167.23 V106.58",
                "position": (10, 90)
            },
            
            "7": {
                "svg": "M3.99,3.80 L3.99,45.68",
                "position": (90, 320),
                "segments": 8
            },
            
            "8": {
                "svg": "M3.99,3.11 L3.99,10.95",
                "position": (90, 373)
            }
        },
        
        "size": (180, 385),
        "thickness": 6
    },
    
    "PHONE3A": {
        "glyphs": {
            "1": {
                "svg": "M-5.69,72.38 C12.45,28.38 40.50,10.20 65.68,5.18",
                "position": (20, 10),
                "segments": 20
            },
            
            "2": {
                "svg": "M15.00,5.00 C32.00,40.00 32.00,75.00 15.00,110.00",
                "position": (210, 70),
                "segments": 11
            },
            
            "3": {
                "svg": "M2.91,7.12 L35.89,40.28",
                "position": (20, 178),
                "segments": 5
            }
        },
        
        "size": (250, 240),
        "thickness": 10
    },
    
    "PHONE2A": {
        "glyphs": {
            "1": {
                "svg": "M65.68,5.18 C40.50,10.20 12.45,28.38 -5.69,72.38",
                "position": (20, 20),
                "segments": 24
            },
            
            "2": {
                "svg": "M15.00,5.00 C15.00,40.00 15.00,75.00 15.00,110.00",
                "position": (225, 80)
            },
            
            "3": {
                "svg": "M2.91,7.12 C10.00,15.00 20.00,30.00 35.89,40.28",
                "position": (20, 192)
            }
        },
        
        "size": (255, 250),
        "thickness": 10
    },
    
    "PHONE2": {
        "glyphs": {
            "1": {
                "svg": "M4,47 V22 C4,10 13,4 23.5,4 C34,4 43,10 43,22",
                "position": (0, 0)
            },
            "2": {
                "svg": "M34.5,1.5 V19.5 C34.5,25.5 31,31 25,34 C19.5,37 13,36.5 8,33",
                "position": (9, 45)
            },
            "3": {
                "svg": "M37,3 L3,42",
                "position": (130, 10)
            },
            "4": {
                "svg": "M4,4 C38,1 71,15 94,40",
                "position": (75, 90)
            },
            "5": {
                "svg": "M49,-4.25 C31.5,3.25 16.5,15.75 4,32",
                "position": (0, 105)
            },
            "6": {
                "svg": "M3,3 V44",
                "position": (0, 150)
            },
            "7": {
                "svg": "M4,3 C30,30 65,42 95,39",
                "position": (3, 260)
            },
            "8": {
                "svg": "M3,32 C20.5,23.25 38,10.75 49.25,-4.25",
                "position": (117, 262)
            },
            "9": {
                "svg": "M3.5,4 V35",
                "position": (168, 195)
            },
            "10": {
                "svg": "M4,3 V43",
                "position": (90, 320)
            },
            "11": {
                "svg": "M3.99,3.11 L3.99,10.95",
                "position": (90, 371)
            }
        },
        
        "size": (177, 385),
        "thickness": 6
    }
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
TEXTBOX_SHAKE = 100
TEXTBOX_SHAKE_PER = 30
TEXTBOX_INPUT = 250

# Perfomance
TILE_SIZE = 1024

# Compositor Defaults
STATUS_BAR_DEFAULT = f"Cassette {open('version').read()}"

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

# Shaders
GLYPH_VS = """#version 330 core
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aNormal;
layout (location = 2) in float aSegIdx;

uniform mat4 mvp;
uniform float uThickness;

flat out float vSegIdx;

void main() {
    vec2 offsetPos = aPos + (aNormal * uThickness * 0.5);
    gl_Position = mvp * vec4(offsetPos, 0.0, 1.0);
    vSegIdx = aSegIdx;
}
"""

GLYPH_FS = """#version 330 core
flat in float vSegIdx;
out vec4 FragColor;
uniform vec3 uColorOn;
uniform vec3 uColorOff;
uniform float uLevels[128];
void main() {
    float level = uLevels[int(vSegIdx)] / 100.0;
    FragColor = vec4(mix(uColorOff, uColorOn, level), 1.0);
}
"""

FLOATING_WINDOW_VS = """#version 410 core
layout (location = 0) in vec3 position;
layout (location = 1) in vec2 texCoord;

uniform mat4 u_curr_mvp;

out vec2 UV;

void main() {
    gl_Position = u_curr_mvp * vec4(position, 1.0);
    UV = texCoord;
}
"""

FLOATING_WINDOW_FS = """#version 410 core
in vec2 UV;
out vec4 color;

uniform vec4 u_rectColor;
uniform vec4 u_borderColor;
uniform float u_rectAlpha;
uniform float u_borderAlpha;
uniform float u_globalAlpha;
uniform float u_borderThicknessPixels;
uniform float u_radius;
uniform vec2 u_size;

float roundedBoxSDF(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

void main() {
    vec2 halfSize = u_size * 0.5;
    float dist_center = roundedBoxSDF((UV - 0.5) * u_size, halfSize, u_radius);
    
    float smoothing = fwidth(dist_center);
    
    float mask = smoothstep(smoothing, -smoothing, dist_center);
    
    if (mask * u_globalAlpha < 0.001) discard;

    float innerMask = smoothstep(smoothing, -smoothing, dist_center + u_borderThicknessPixels);

    vec4 borderCol = vec4(u_borderColor.rgb, u_borderColor.a * u_borderAlpha);
    vec4 rectCol = vec4(u_rectColor.rgb, u_rectColor.a * u_rectAlpha);

    vec4 finalColor = mix(borderCol, rectCol, innerMask);
    
    color = vec4(finalColor.rgb, finalColor.a * mask * u_globalAlpha);
}
"""

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
    "Performance": [
        {
            "type": "checkbox",
            "title": "CPU Antialiasing",
            "key": "antialiasing",
            "description": "Antialiasing on CPU rendered components.",
            "default": True
        },
        {
            "type": "selector",
            "title": "OpenGL MSAA: Requires restart.",
            "key": "msaa",
            "map": {
                "No MSAA": 0,
                "2x": 2,
                "4x": 4,
                "8x": 8
            },
            "default": "4x"
        },
        {
            "type": "checkbox",
            "title": "Compositor GPU Rendering",
            "key": "gpu",
            "description": "Significantly improves smoothness. Beta feature. Requires restart.",
            "default": True
        },
        {
            "type": "selector",
            "title": "Waveform Tile Width",
            "key": "tile_width",
            "map": {
                "256": 256,
                "512": 512,
                "1024": 1024
            },
            "default": "512"
        }
    ],

    "Interface": [
        {
            "type": "selector",
            "title": "Animation Multiplier",
            "key": "animation_multiplier",
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
            "default": "1.0x"
        },
        {
            "type": "checkbox",
            "title": "Textbox Animations",
            "key": "textbox_animations",
            "description": "Enables textbox animations.",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Floating Window Animations",
            "key": "floating_window_animations",
            "description": "Enables popup background animations.",
            "default": True
        },
        {
            "type": "selector",
            "title": "Animation Style",
            "key": "animation_style",
            "map": {
                "Smooth": "smooth",
                "Bouncy": "bouncy",
                "Roll": "roll",
                "Glitch": "glitch"
            },
            "default": "Bouncy"
        },
        {
            "type": "selector",
            "title": "Window Hover Smoothing",
            "key": "window_hover_smoothing",
            "map": {
                "No Tilt": "0.0",
                "Slow": "0.07",
                "Normal": "0.2",
                "Very Fast": "0.8"
            },
            "default": "Normal"
        },
        {
            "type": "checkbox",
            "title": "Glyph 3D Tilt",
            "description": "Enables 3D tilt when resizing or moving a glyph.",
            "key": "glyph_tilt_animation",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Glyph Spawn Animation",
            "description": "Enables animations when spawning or despawning a glyph.",
            "key": "glyph_spawn_animation",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Marquee Smoothing",
            "description": "Makes the marquee selector smooth and fluid.",
            "key": "marquee_smoothing",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Marquee Hide Animation",
            "description": "Enables the marquee hide/damping animation.",
            "key": "marquee_hide_animation",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "BPM Animations",
            "description": "Enables beat - synced animations.",
            "key": "bpm_animations",
            "default": True
        }
    ],

    "User Experience": [
        {
            "type": "slider",
            "title": "Playhead Arrow Increment",
            "min": 1,
            "max": 10,
            "key": "arrow_increment",
            "default": 1
        },
        {
            "type": "slider",
            "title": "Zoom Step (on Wheel)",
            "min": 1,
            "max": 100,
            "key": "zoom_step",
            "default": 20
        },
        {
            "type": "selector",
            "title": "Horizontal Scroll Acceleration",
            "key": "scroll_acceleration",
            "map": {
                "Low": "0.1",
                "Normal": "0.2",
                "High": "0.4"
            },
            "default": "Normal"
        },
        {
            "type": "checkbox",
            "title": "Disable Sounds",
            "key": "disable_sounds",
            "description": "Disables all UI sounds.",
            "default": False
        },
        {
            "type": "checkbox",
            "title": "Sound Tone Effects",
            "description": "Enables dynamic tonal variation for UI sounds.",
            "key": "sound_tone_effects",
            "default": True
        },
        {
            "type": "selector",
            "title": "Waveform Smoothing",
            "key": "waveform_smoothing",
            "map": {
                "Accuracy": 0.5,
                "Balance": 1.7,
                "Smooth": 3
            },
            "default": "Balance"
        },
        {
            "type": "selector",
            "title": "Playhead Position",
            "key": "playhead_position",
            "map": {
                "Left": 0.25,
                "Center": 0.5,
                "Right": 0.75
            },
            "default": "Left"
        },
        {
            "type": "selector",
            "title": "Default Scaling",
            "key": "default_scaling",
            "map": {
                "Very small": 100,
                "Small": 200,
                "Medium": 300,
                "Big": 400,
                "Very big": 500
            },
            "default": "Very big"
        }
    ],

    "Devices": [
        {
            "type": "checkbox",
            "title": "Device Auto - Search",
            "key": "auto_search",
            "description": "Automatically searches for a connected Nothing Phone.",
            "default": True
        }
    ]
}