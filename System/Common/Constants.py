from loguru import logger

from System.Common import Utils

from dataclasses import (
    field,
    dataclass
)

current_settings = Utils.SettingsController("chips047", "Cassette")

def load_settings() -> None:
    logger.debug(f"Loaded settings from chips047/Cassette")
    current_settings.load()

def get_default_value(parameters: dict[str, object]) -> int | str | bool | None:
    element_type = parameters.get("type", "")
    
    if element_type == "checkbox":
        return parameters.get("default", False)
    
    if element_type == "slider":
        return parameters.get("default", parameters.get("min", 0))
    
    if element_type.startswith("selector"):
        return parameters["map"][parameters["default"]]
    
    return None

def prepare_default_settings(setting_components: dict[str, list]) -> None:
    settings       = current_settings.instance
    existing_keys  = set(settings.allKeys())
    new_keys       = set()

    for components in setting_components.values():
        for parameters in components:
            key = parameters["key"]
            new_keys.add(key)

            if key in existing_keys:
                continue

            default_val = get_default_value(parameters)
            if default_val is not None:
                settings.setValue(key, default_val)

    for key in (existing_keys - new_keys):
        if key.startswith("_"):
            continue

        settings.remove(key)

    settings.sync()

    logger.success("Default settings prepared and synced.")

# Models and Related

@dataclass
class DeviceConfig:
    code_name:          str
    short_name:         str
    full_name:          str
    hardware_codes:     list[str]
    composer_code_name: str
    
    glyph_indexes:      list[list[int]]
    zone_indexes:       list[list[int]]
    segments_map:       dict[str, int]   = field(default_factory = dict)

    visualization_map:  dict             = field(default_factory = dict)
    port_variants:      list[str]        = field(default_factory = list)
    
    columns:            int              = field(init = False)
    base_tracks:        int              = field(init = False)
    custom2_str:        str              = field(init = False)

    # to support phone (1) 5 cols mode (for import function)
    legacy_tracks: dict[int, dict[str, list[str]]] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        self.columns     = sum(len(group) for group in self.glyph_indexes)
        self.base_tracks = len(self.glyph_indexes)
        self.custom2_str = f"{self.columns}cols"
        
        self.setup_offset_calc()

        logger.info(f"\n\nModel {self.full_name}")
        logger.debug(f"Total columns (Glyphs + Segments): {self.columns}")
        logger.debug(f"Base Tracks: {self.base_tracks}")
        logger.debug(f"Hardware: {self.hardware_codes[0]}")
        logger.debug(f"Glyph Indexes: {self.glyph_indexes}")
        logger.debug(f"Zone Indexes: {self.zone_indexes}")

    def setup_offset_calc(self) -> None:
        if not self.segments_map:
            self.zone_offset_calc = lambda g: 0
            return

        sorted_segments = sorted([(k, v) for k, v in self.segments_map.items()])
        
        def calc(g_idx: int) -> int:
            offset = 0
            
            for glyph_pos, val in sorted_segments:
                if g_idx < int(glyph_pos):
                    continue
                
                offset += (val - 1)
            
            return offset
        
        self.zone_offset_calc = calc

    @property
    def total_tracks(self) -> int:
        return self.base_tracks

    @property
    def total_tracks_with_segments(self) -> int:
        total = 0
        
        for i in range(1, self.base_tracks + 1):
            total += self.segments_map.get(str(i), 1)
        
        return total

    def get_array_indexes(
            self,
            glyph_index: int,
            zone_index:  int
        ) -> list | int:

        glyph_index -= 1
        zone_index  -= 1
        
        if zone_index == -1:
            return self.glyph_indexes[glyph_index]
        
        offset = self.zone_offset_calc(glyph_index)
        
        return self.zone_indexes[glyph_index + zone_index + offset]
    
    def resolve_tracks(
            self,
            input_track:  str,
            total_tracks: int
        ) -> list[tuple[str, int | None]]:
        
        if total_tracks in self.legacy_tracks:
            mapping = self.legacy_tracks[total_tracks]
            
            if input_track in mapping:
                return [(t, None) for t in mapping[input_track]]

        if input_track in self.segments_map:
            count = self.segments_map[input_track]
            return [(input_track, i) for i in range(count)]

        return [(input_track, None)]

def make_ranges(*args: int | list[int]) -> list[list[int]]:
    result = []
    current = 0

    for arg in args:
        if isinstance(arg, int):
            result.append(list(range(current, current + arg)))
            current += arg
        
        else:
            result.append(arg)
            current = max(arg) + 1 if arg else current
    
    return result

DEVICES: dict[str, DeviceConfig] = {
    "PHONE1": DeviceConfig(
        "PHONE1", "1", "Phone (1)", ["A063"], "Spacewar",
        glyph_indexes = [[0], [1], [4], [5], [2], [3], list(range(7, 15)), [6]],
        zone_indexes = [[0], [1], [4], [5], [2], [3], [14], [13], [12], [11], [10], [9], [8], [7], [6]],
        segments_map = {"7": 8},
        legacy_tracks = {
            5: {
                "1": ["1"],
                "2": ["2"],
                "3": ["3", "4", "5", "6"],
                "4": ["7"],
                "5": ["8"]
            }
        },

        visualization_map = {
            "glyphs": {
                "1": {
                    "svg": "M41.66,47.69 V58.08 C41.66,68.73 33.01,77.38 22.36,77.38 C11.71,77.38 3.06,68.73 3.06,58.08 V22.18 C3.06,11.53 11.71,2.88 22.36,2.88 C33.01,2.88 41.66,11.53 41.66,22.18",
                    "position": (5, 5)
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
                    "position": (89, 320),
                    "segments": 8
                },

                "8": {
                    "svg": "M3.99,3.11 L3.99,10.95",
                    "position": (89, 373)
                }
            },

            "size": (180, 385),
            "thickness": 6
        },

        port_variants = ["2"]
    ),

    "PHONE2": DeviceConfig(
        "PHONE2", "2", "Phone (2)", ["A065", "AIN065"], "Pong",
        glyph_indexes = [[0], [1], [2], list(range(3, 19)), [19], [20], [21], [22], [23], list(range(25, 33)), [24]],
        zone_indexes = [[i] for i in range(24)] + [[32], [31], [30], [29], [28], [27], [26], [25], [24]],
        segments_map = {"4": 16, "10": 8},

        visualization_map = {
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
                    "position": (80, 90)
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
                    "position": (120, 262)
                },
                "9": {
                    "svg": "M3.5,4 V35",
                    "position": (169, 195)
                },
                "10": {
                    "svg": "M4,3 V43",
                    "position": (86, 320),
                    "segments": 8
                },
                "11": {
                    "svg": "M3.99,3.11 L3.99,10.95",
                    "position": (86, 371)
                }
            },

            "size": (177, 385),
            "thickness": 6
        },

        port_variants = ["1"]
    ),

    "PHONE2A": DeviceConfig(
        "PHONE2A", "2a", "Phone (2a)", ["A142", "A142P"], "Pacman",
        glyph_indexes = make_ranges(24, 1, 1),
        zone_indexes = [[i] for i in range(26)],
        segments_map = {"1": 24},

        visualization_map = {
            "glyphs": {
                "1": {
                    "svg": "M-5.69,72.38 C12.45,28.38 40.50,10.20 65.68,5.18",
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

        port_variants = ["1", "2", "3a", "4a"]
    ),

    "PHONE3A": DeviceConfig(
        "PHONE3A", "3a", "Phone (3a)", ["A059", "A059P"], "Asteroids",
        glyph_indexes = make_ranges(20, 11, 5),
        zone_indexes = [[i] for i in range(36)],
        segments_map = {"1": 20, "2": 11, "3": 5},

        visualization_map = {
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
                    "svg": "M35.89,40.28 L2.91,7.12",
                    "position": (20, 178),
                    "segments": 5
                }
            },

            "size": (250, 240),
            "thickness": 10
        },

        port_variants = ["1", "2", "2a", "4a"]
    ),

    "PHONE4A": DeviceConfig(
        "PHONE4A", "4a", "Phone (4a)", ["A069"], "Frogger",
        glyph_indexes = make_ranges(7),
        zone_indexes = [[i] for i in range(7)],
        segments_map = {"1": 7},

        visualization_map = {
            "glyphs": {
                "1": {
                    "svg": "M4,3 V150",
                    "position": (12, 0),
                    "segments": 7
                }
            },
            "size": (32, 150),
            "thickness": 14
        },

        port_variants = ["2a", "3a"]
    ),

    "PHONE4B": DeviceConfig(
        "PHONE4B", "4b", "Phone (4b)", ["A009P"], "SuperContra",
        glyph_indexes = make_ranges(5),
        zone_indexes  = [[i] for i in range(5)],
        segments_map  = {"1": 5},

        visualization_map = {
            "glyphs": {
                "1": {
                    "svg": "M4,3 V70",
                    "position": (12, 0),
                    "segments": 5
                }
            },
            "size": (32, 70),
            "thickness": 14
        },

        port_variants = ["2a", "3a", "4a"]
    )
}

NUMBER_TO_CODE = {config.short_name: code for code, config in DEVICES.items()}

# Maps

PortMaps = {
    "PHONE2A": {
        "to": {
            "PHONE4A": {
                "1": ["1"],
                "2": ["1"],
                "3": ["1"],

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            },

            "PHONE4B": {
                "1": ["1"],
                "2": ["1"],
                "3": ["1"],

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            },

            "PHONE3A": {
                "1": ["1"],
                "2": ["2"],
                "3": ["3"],

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            },
            
            "PHONE2": {
                "effects": {
                    "segments": {
                        "1": ["4"]
                    }
                },

                "1": {
                    "mode": "random",
                    "variants": [
                        ["1", "2", "3"],
                        ["4", "5", "6", "7", "8", "9"],
                        ["1", "2"],
                        ["3"]
                    ],
                    "randomize": 1
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        ["4", "5", "6"],
                        ["7", "8", "9"],
                        ["4", "5", "6", "7", "8", "9"],
                        ["5", "8"]
                    ],
                    "randomize": 1
                },

                "3": {
                    "mode": "random",
                    "variants": [
                        ["10"],
                        ["11"],
                        ["10", "11"]
                    ],
                    "randomize": 1
                }
            },
            
            "PHONE1": {
                "effects": {
                    "segments": {
                        "1": ["7"]
                    }
                },

                "1": {
                    "mode": "random",
                    "variants": [
                        ["1"],
                        ["2"],
                        ["1", "2"]
                    ],
                    "randomize": 1
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        ["3", "5"],
                        ["4", "6"],
                        ["3", "4", "5", "6"],
                        ["3", "4", "5", "6", "7"]
                    ],
                    "randomize": 1
                },
                
                "3": {
                    "mode": "random",
                    "variants": [
                        ["7"],
                        ["7", "8"]
                    ],
                    "randomize": 1
                }
            }
        }
    },

    "PHONE3A": {
        "to": {
            "PHONE2A": {
                "1": ["1"],
                "2": ["2"],
                "3": ["3"],
                
                "effects": {
                    "segments": {
                        "1": ["1"],
                        "2": ["1"],
                        "3": ["1"]
                    }
                },
            },

            "PHONE4B": {
                "1": ["1"],
                "2": ["1"],
                "3": ["1"],

                "effects": {
                    "segments": {
                        "1": ["1"],
                        "2": ["1"],
                        "3": ["1"]
                    }
                },
            },
            
            "PHONE1": {
                "1": {
                    "mode": "random",
                    "variants": [
                        ["1", "2"],
                        ["3", "5"],
                        ["4", "6"]
                    ]
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        ["3", "5"],
                        ["4", "6"],
                        ["3", "4", "5", "6"]
                    ]
                },

                "3": {
                    "mode": "random",
                    "variants": [
                        ["7"],
                        ["8"],
                        ["7", "8"]
                    ]
                },

                "effects": {
                    "segments": {
                        "1": ["7"],
                        "2": ["7"],
                        "3": ["7"]
                    }
                },
            },
            
            "PHONE2": {
                "1": {
                    "mode": "random",
                    "variants": [
                        ["1", "2", "3"],
                        ["1", "2"],
                        ["3"]
                    ],
                    "randomizes": 1
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        ["4", "5", "6", "7", "8", "9"],
                        ["5", "8"],
                        ["6", "9"],
                        ["4", "7"]
                    ],
                    "randomizes": 1
                },

                "3": {
                    "mode": "random",
                    "variants": [
                        ["10"],
                        ["11"],
                        ["10", "11"]
                    ],
                    "randomizes": 1
                },

                "effects": {
                    "segments": {
                        "1": ["4"],
                        "2": ["4"],
                        "3": ["10"]
                    }
                }
            },

            "PHONE4A": {
                "1": ["1"],
                "2": ["1"],
                "3": ["1"],

                "effects": {
                    "segments": {
                        "1": ["1"],
                        "2": ["1"],
                        "3": ["1"]
                    }
                }
            },
        }
    },

    "PHONE4A": {
        "to": {
            "PHONE2A": {
                "1": {
                    "mode": "random",
                    "variants": [
                        ["1"],
                        ["2"],
                        ["3"],
                        ["1", "2"],
                        ["1", "3"],
                        ["2", "3"],
                        ["1", "2", "3"]
                    ],
                },

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            },

            "PHONE4B": {
                "1": "1",

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            },

            "PHONE3A": {
                "1": {
                    "mode": "random",
                    "variants": [
                        ["1"],
                        ["2"],
                        ["3"],
                        ["1", "2"],
                        ["1", "3"],
                        ["2", "3"],
                        ["1", "2", "3"]
                    ],
                },

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            }
        }
    },

    "PHONE4B": {
        "to": {
            "PHONE2A": {
                "1": {
                    "mode": "random",
                    "variants": [
                        ["1"],
                        ["2"],
                        ["3"],
                        ["1", "2"],
                        ["1", "3"],
                        ["2", "3"],
                        ["1", "2", "3"]
                    ],
                },

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            },

            "PHONE4A": {
                "1": "1",

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            },

            "PHONE3A": {
                "1": {
                    "mode": "random",
                    "variants": [
                        ["1"],
                        ["2"],
                        ["3"],
                        ["1", "2"],
                        ["1", "3"],
                        ["2", "3"],
                        ["1", "2", "3"]
                    ],
                },

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            }
        }
    },

    "PHONE1": {
        "to": {
            "PHONE2": {
                "1": ["1", "2"],
                "2": ["3"],
                "3": ["4", "5"],
                "4": ["5", "6"],
                "5": ["7", "8"],
                "6": ["8", "9"],
                "7": ["10"],
                "8": ["11"],
                
                "effects": {
                    "segments": {
                        "7": ["10"]
                    }
                }
            }
        }
    },

    "PHONE2": {
        "to": {
            "PHONE1": {
                "1": ["1"],
                "2": ["1"],
                "3": ["2"],
                "4": ["3"],
                "5": ["4"],
                "6": ["4"],
                "7": ["5"],
                "8": ["6"],
                "9": ["6"],
                "10": ["7"],
                "11": ["8"],    

                "effects": {
                    "segments": {
                        "4":  ["7"],
                        "10": ["7"]
                    }
                }
            }
        }
    }
}

# Defaults
STATUS_BAR_DEFAULT = f"Cassette {open(Utils.get_resource_path('version')).read()}"

DEFAULT_DURATION   = 100
DEFAULT_BRIGHTNESS = 100

SPRING_STIFFNESS           = 0.04
FADE_OVERLAY_SIZE          = 60
SPRING_DAMPING_FACTOR      = 0.4
ANIMATION_TICK_INTERVAL    = 8
USER_SCROLL_IDLE_TIMEOUT   = 150
WHEEL_SCROLL_SENSITIVITY   = 1.0
INERTIA_DECELERATION_RATE  = 0.93
VISUAL_RESISTANCE_STRENGTH = 600.0

# Paths
FFMPEG_PATH  = Utils.get_ffmpeg_path("ffmpeg")
FFPROBE_PATH = Utils.get_ffmpeg_path("ffprobe")

# Qt Timer Presets
FPS_60  = 16
FPS_120 = 8
FPS_30  = 33

GITHUB_LINK = "https://www.github.com/Chipik0/Cassette/releases/latest"

# Shaders
GLYPH_VS = """#version 330 core
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aNormal;
layout (location = 2) in float aGlobalIdx;

uniform mat4 mvp;
uniform float uThickness;

flat out float vGlobalIdx;

void main() {
    gl_Position = mvp * vec4(aPos + (aNormal * uThickness * 0.5), 0.0, 1.0);
    vGlobalIdx = aGlobalIdx;
}
"""

GLYPH_FS = """#version 330 core

flat in float vGlobalIdx;
out vec4 FragColor;

uniform sampler1D uLevelsTex;

void main() {
    int idx = int(vGlobalIdx + 0.5);
    float level = texelFetch(uLevelsTex, idx, 0).r / 100.0;

    vec3 offColor = vec3(0.2, 0.2, 0.2);
    vec3 onColor  = vec3(1.0, 1.0, 1.0);
    
    vec3 color = mix(offColor, onColor, level);
    FragColor = vec4(color, 1.0);
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
                "Smooth":   "smooth",
                "Bouncy":   "bouncy",
                "Roll":     "roll",
                "Glitch":   "glitch",
                "Classic":  "classic",
                "Electric": "electric"
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
            "title": "Playhead Animations",
            "description": "Enables animations on the playhead.",
            "key": "playhead_animations",
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
        },
        {
            "type": "selector",
            "title": "Window BPM Animation Style",
            "key": "window_bpm_animation_style",
            "map": {
                "Pulse": "pulse",
                "Punch": "punch"
            },
            "default": "Pulse"
        }
    ],

    "Audio": [
        {
            "type": "checkbox",
            "title": "Disable Sounds",
            "key": "disable_sounds",
            "description": "Disables all UI sounds.",
            "default": False
        },
        {
            "type": "slider",
            "title": "Sound Effect Volume",
            "key": "sound_effect_volume",
            "min": 0,
            "max": 100,
            "default": 100
        },
        {
            "type": "checkbox",
            "title": "Sound Tone Effects",
            "description": "Enables dynamic tonal variation for UI sounds.",
            "key": "sound_tone_effects",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Glyph Deletion Sound",
            "description": "Enables a sound effect when a glyph is deleted.",
            "key": "glyph_deletion_sound",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Playhead Sound Effects",
            "description": "Enables sound effects on playhead actions.",
            "key": "playhead_sounds",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Glyph Spawn Sound",
            "description": "Enables a sound effect when a glyph is spawned.",
            "key": "glyph_spawn_sound",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Startup Sound",
            "description": "Enables a sound effect on application startup.",
            "key": "startup_sound",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Floating Window Sound Effects",
            "description": "Enables sound effects on floating window actions.",
            "key": "floating_window_sounds",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Drag & Drop Sound Effects",
            "description": "Enables sound effects when dragging and dropping files.",
            "key": "drag_drop_sounds",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Glyph Duplication Sound",
            "description": "Enables a sound effect when a glyph is duplicated.",
            "key": "glyph_duplication_sound",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Rewind Sound Effect",
            "description": "Enables a sound effect when auto scrolling.",
            "key": "rewind_sound",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Context Menu Sound Effects",
            "description": "Enables sound effects on context menu actions.",
            "key": "context_menu_sounds",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Timeline Jump Sound Effect",
            "description": "Enables a sound effect when jumping to the start or end of a timeline.",
            "key": "timeline_jump_sounds",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Textbox Sound Effects",
            "description": "Enables sound effects on textbox actions.",
            "key": "textbox_sounds",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Shutdown Sound",
            "description": "Enables a sound effect on application shutdown.",
            "key": "shutdown_sound",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Brightness Adjustment Sound",
            "description": "Enables a sound effect when adjusting brightness.",
            "key": "brightness_adjustment_sound",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Glyph Stack Sounds",
            "description": "Enables sound effects when stacking or unstacking glyphs.",
            "key": "glyph_stack_sounds",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Checkbox Sounds",
            "description": "Enables sound effects when toggling checkboxes.",
            "key": "checkbox_sounds",
            "default": True
        },
        {
            "type": "checkbox",
            "title": "Selector Sounds",
            "description": "Enables sound effects when changing selector values.",
            "key": "selector_sounds",
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
            "title": "Mouse Click Behavior",
            "key": "mouse_click_behavior",
            "map": {
                "Normal": "normal",
                "Fast (On Press)": "fast"
            },
            "default": "Normal"
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
        },
        {
            "type": "selector",
            "title": "Menu Scroll Sensitivity",
            "key": "wheel_scroll_sensitivity",
            "map": {
                "Low":    "0.5",
                "Normal": "1.0",
                "High":   "1.5"
            },
            "default": "Normal"
        },
        {
            "type": "selector",
            "title": "Menu Scroll Inertia",
            "key": "inertia_deceleration_rate",
            "map": {
                "Low": 0.85,
                "Normal": 0.93,
                "High": 0.97
            },
            "default": "Normal"
        }
    ]
}

DOT_FONT = {
    'A': [[0,1,0], [1,0,1], [1,1,1], [1,0,1], [1,0,1]],
    'B': [[1,1,0], [1,0,1], [1,1,0], [1,0,1], [1,1,0]],
    'C': [[0,1,1], [1,0,0], [1,0,0], [1,0,0], [0,1,1]],
    'D': [[1,1,0], [1,0,1], [1,0,1], [1,0,1], [1,1,0]],
    'E': [[1,1,1], [1,0,0], [1,1,0], [1,0,0], [1,1,1]],
    'F': [[1,1,1], [1,0,0], [1,1,0], [1,0,0], [1,0,0]],
    'G': [[0,1,1], [1,0,0], [1,0,1], [1,0,1], [0,1,1]],
    'H': [[1,0,1], [1,0,1], [1,1,1], [1,0,1], [1,0,1]],
    'I': [[1,1,1], [0,1,0], [0,1,0], [0,1,0], [1,1,1]],
    'J': [[0,0,1], [0,0,1], [0,0,1], [1,0,1], [0,1,0]],
    'K': [[1,0,1], [1,0,1], [1,1,0], [1,0,1], [1,0,1]],
    'L': [[1,0,0], [1,0,0], [1,0,0], [1,0,0], [1,1,1]],
    'M': [[1,0,1], [1,1,1], [1,0,1], [1,0,1], [1,0,1]],
    'N': [[1,1,0], [1,0,1], [1,0,1], [1,0,1], [1,0,1]],
    'O': [[0,1,0], [1,0,1], [1,0,1], [1,0,1], [0,1,0]],
    'P': [[1,1,0], [1,0,1], [1,1,0], [1,0,0], [1,0,0]],
    'Q': [[0,1,0], [1,0,1], [1,0,1], [1,1,1], [0,1,1]],
    'R': [[1,1,0], [1,0,1], [1,1,0], [1,0,1], [1,0,1]],
    'S': [[0,1,1], [1,0,0], [0,1,0], [0,0,1], [1,1,0]],
    'T': [[1,1,1], [0,1,0], [0,1,0], [0,1,0], [0,1,0]],
    'U': [[1,0,1], [1,0,1], [1,0,1], [1,0,1], [1,1,1]],
    'V': [[1,0,1], [1,0,1], [1,0,1], [0,1,0], [0,1,0]],
    'W': [[1,0,1], [1,0,1], [1,0,1], [1,1,1], [1,0,1]],
    'X': [[1,0,1], [1,0,1], [0,1,0], [1,0,1], [1,0,1]],
    'Y': [[1,0,1], [1,0,1], [0,1,0], [0,1,0], [0,1,0]],
    'Z': [[1,1,1], [0,0,1], [0,1,0], [1,0,0], [1,1,1]],

    'a': [[0,0,0], [0,1,1], [1,0,1], [1,1,1], [0,1,1]],
    'b': [[0,0,0], [1,0,0], [1,1,0], [1,0,1], [1,1,0]],
    'c': [[0,0,0], [0,1,1], [1,0,0], [1,0,0], [0,1,1]],
    'd': [[0,0,0], [0,0,1], [0,1,1], [1,0,1], [0,1,1]],
    'e': [[0,0,0], [0,1,0], [1,1,1], [1,0,0], [0,1,1]],
    'f': [[0,0,0], [0,1,1], [0,1,0], [0,1,1], [0,1,0]],
    'g': [[0,1,1], [1,0,1], [0,1,1], [0,0,1], [1,1,0]],
    'h': [[0,0,0], [1,0,0], [1,1,0], [1,0,1], [1,0,1]],
    'l': [[0], [1], [1], [1], [1]],
    'i': [[1], [0], [1], [1], [1]],
    'k': [[0,0,0], [1,0,1], [1,1,0], [1,0,1], [1,0,1]],
    'm': [[0,0,0,0,0], [1,1,1,1,1], [1,0,1,0,1], [1,0,1,0,1], [1,0,1,0,1]],
    'n': [[0,0,0], [1,1,0], [1,0,1], [1,0,1], [1,0,1]],
    'o': [[0,0,0], [0,1,0], [1,0,1], [1,0,1], [0,1,0]],
    'p': [[0,0,0], [1,1,0], [1,0,1], [1,1,0], [1,0,0]],
    'r': [[0,0,0], [1,1,0], [1,0,1], [1,0,0], [1,0,0]],
    's': [[0,0,0], [0,1,1], [0,1,0], [0,0,1], [1,1,1]],
    'q': [[0,0,0], [0,1,1], [1,0,1], [0,1,1], [0,0,1]],
    't': [[0,0,0], [0,1,0], [1,1,1], [0,1,0], [0,1,1]],
    'u': [[0,0,0], [1,0,1], [1,0,1], [1,0,1], [0,1,1]],
    'v': [[0,0,0], [1,0,1], [1,0,1], [1,0,1], [0,1,0]],
    'w': [[0,0,0,0,0], [1,0,1,0,1], [1,0,1,0,1], [1,1,1,1,1], [1,0,1,0,1]],
    'x': [[0,0,0], [1,0,1], [0,1,0], [1,0,1], [1,0,1]],
    'y': [[0,0,0], [1,0,1], [1,1,1], [0,0,1], [1,1,0]],
    'z': [[0,0,0], [1,1,1], [0,1,0], [1,0,0], [1,1,1]],
    'j': [[0,1], [0,0], [0,1], [0,1], [1,0]],

    'А': [[0,1,0], [1,0,1], [1,1,1], [1,0,1], [1,0,1]],
    'Б': [[1,1,1], [1,0,0], [1,1,0], [1,0,1], [1,1,0]],
    'В': [[1,1,0], [1,0,1], [1,1,0], [1,0,1], [1,1,0]],
    'Г': [[1,1,1], [1,0,0], [1,0,0], [1,0,0], [1,0,0]],
    'Д': [[0,1,1], [0,1,0], [0,1,0], [1,1,1], [1,0,1]],
    'Е': [[1,1,1], [1,0,0], [1,1,0], [1,0,0], [1,1,1]],
    'Ё': [[0,1,0], [1,1,1], [1,0,0], [1,1,0], [1,1,1]],
    'Ж': [[1,0,1], [1,0,1], [0,1,0], [1,0,1], [1,0,1]],
    'З': [[1,1,0], [0,0,1], [0,1,0], [0,0,1], [1,1,0]],
    'И': [[1,0,1], [1,0,1], [1,1,1], [1,0,1], [1,0,1]],
    'Й': [[1,1,1], [1,0,1], [1,1,1], [1,0,1], [1,0,1]],
    'К': [[1,0,1], [1,0,1], [1,1,0], [1,0,1], [1,0,1]],
    'Л': [[0,1,1], [1,0,1], [1,0,1], [1,0,1], [1,0,1]],
    'М': [[1,0,1], [1,1,1], [1,0,1], [1,0,1], [1,0,1]],
    'Н': [[1,0,1], [1,0,1], [1,1,1], [1,0,1], [1,0,1]],
    'О': [[0,1,0], [1,0,1], [1,0,1], [1,0,1], [0,1,0]],
    'П': [[1,1,1], [1,0,1], [1,0,1], [1,0,1], [1,0,1]],
    'Р': [[1,1,0], [1,0,1], [1,1,0], [1,0,0], [1,0,0]],
    'С': [[0,1,1], [1,0,0], [1,0,0], [1,0,0], [0,1,1]],
    'Т': [[1,1,1], [0,1,0], [0,1,0], [0,1,0], [0,1,0]],
    'У': [[1,0,1], [1,0,1], [0,1,1], [0,0,1], [0,1,1]],
    'Ф': [[0,1,0], [1,1,1], [1,1,1], [0,1,0], [0,1,0]],
    'Х': [[1,0,1], [1,0,1], [0,1,0], [1,0,1], [1,0,1]],
    'Ц': [[1,0,1], [1,0,1], [1,0,1], [1,1,1], [0,0,1]],
    'Ч': [[1,0,1], [1,0,1], [0,1,1], [0,0,1], [0,0,1]],
    'Ш': [[1,0,1], [1,0,1], [1,0,1], [1,0,1], [1,1,1]],
    'Щ': [[1,0,1,0,0], [1,0,1,0,0], [1,0,1,0,0], [1,1,1,0,0], [0,0,0,1,1]],
    'Ъ': [[1,1,0], [0,1,0], [1,1,0], [1,0,1], [1,1,0]],
    'Ы': [[1,0,1], [1,0,1], [1,1,1], [1,0,1], [1,1,1]],
    'Ь': [[1,0,0], [1,0,0], [1,1,0], [1,0,1], [1,1,0]],
    'Э': [[1,1,0], [0,0,1], [0,1,1], [0,0,1], [1,1,0]],
    'Ю': [[1,1,1], [1,0,1], [1,1,1], [1,0,1], [1,1,1]],
    'Я': [[0,1,1], [1,0,1], [0,1,1], [1,0,1], [1,0,1]],

    'а': [[0,0,0], [0,1,1], [1,0,1], [1,1,1], [0,1,1]],
    'б': [[1,1,0], [1,0,0], [1,1,0], [1,0,1], [1,1,0]],
    'в': [[0,0,0], [1,1,0], [1,1,1], [1,0,1], [1,1,1]],
    'г': [[0,0,0], [1,1,1], [1,0,0], [1,0,0], [1,0,0]],
    'д': [[0,1,0], [0,1,0], [1,1,1], [1,0,1], [1,0,1]],
    'е': [[0,0,0], [0,1,0], [1,1,1], [1,0,0], [0,1,1]],
    'ё': [[0,1,0], [0,0,0], [1,1,1], [1,0,0], [1,1,1]],
    'ж': [[0,0,0], [1,0,1], [0,1,0], [1,0,1], [1,0,1]],
    'з': [[0,0,0], [1,1,1], [0,1,1], [0,0,1], [1,1,1]],
    'и': [[0,0,0], [1,0,1], [1,0,1], [1,0,1], [1,1,1]],
    'й': [[1,0,1], [0,0,0], [1,0,1], [1,0,1], [1,1,1]],
    'к': [[0,0,0], [1,0,1], [1,1,0], [1,0,1], [1,0,1]],
    'л': [[0,0,0], [0,1,1], [1,0,1], [1,0,1], [1,0,1]],
    'м': [[0,0,0,0,0], [1,1,1,1,1], [1,0,1,0,1], [1,0,1,0,1], [1,0,1,0,1]],
    'н': [[0,0,0], [1,0,1], [1,1,1], [1,0,1], [1,0,1]],
    'о': [[0,0,0], [0,1,0], [1,0,1], [1,0,1], [0,1,0]],
    'п': [[0,0,0], [1,1,1], [1,0,1], [1,0,1], [1,0,1]],
    'р': [[0,0,0], [1,1,0], [1,0,1], [1,1,0], [1,0,0]],
    'с': [[0,0,0], [0,1,1], [1,0,0], [1,0,0], [0,1,1]],
    'т': [[0,0,0,0,0], [1,1,1,1,1], [0,0,1,0,0], [0,0,1,0,0], [0,0,1,0,0]],
    'у': [[0,0,0], [1,0,1], [1,1,1], [0,0,1], [1,1,0]],
    'ф': [[0,1,0], [1,1,1], [1,1,1], [0,1,0], [0,1,0]],
    'х': [[0,0,0], [1,0,1], [0,1,0], [1,0,1], [1,0,1]],
    'ц': [[0,0,0], [1,0,1], [1,0,1], [1,1,1], [0,0,1]],
    'ч': [[0,0,0], [1,0,1], [0,1,1], [0,0,1], [0,0,1]],
    'ш': [[0,0,0], [1,0,1], [1,0,1], [1,0,1], [1,1,1]],
    'щ': [[0,0,0,0,0], [1,0,1,0,0], [1,0,1,0,0], [1,1,1,0,0], [0,0,0,1,1]],
    'ъ': [[0,1,0], [0,1,0], [1,1,0], [1,0,1], [1,1,0]],
    'ы': [[0,0,0], [1,0,1], [1,1,1], [1,0,1], [1,1,1]],
    'ь': [[0,0,0], [1,0,0], [1,1,0], [1,0,1], [1,1,0]],
    'э': [[0,0,0], [1,1,0], [0,1,1], [0,0,1], [1,1,0]],
    'ю': [[0,0,0,0,0], [1,0,1,1,0], [1,0,1,0,1], [1,0,1,0,1], [1,0,1,1,0]],
    'я': [[0,0,0], [0,1,1], [1,0,1], [0,1,1], [1,0,1]],

    '1': [[0,1,0], [1,1,0], [0,1,0], [0,1,0], [1,1,1]],
    '2': [[1,1,1], [0,0,1], [1,1,1], [1,0,0], [1,1,1]],
    '3': [[1,1,1], [0,0,1], [0,1,1], [0,0,1], [1,1,1]],
    '4': [[1,0,1], [1,0,1], [1,1,1], [0,0,1], [0,0,1]],
    '5': [[1,1,1], [1,0,0], [1,1,1], [0,0,1], [1,1,1]],
    '6': [[1,1,1], [1,0,0], [1,1,1], [1,0,1], [1,1,1]],
    '7': [[1,1,1], [0,0,1], [0,1,0], [0,1,0], [0,1,0]],
    '8': [[1,1,1], [1,0,1], [1,1,1], [1,0,1], [1,1,1]],
    '9': [[1,1,1], [1,0,1], [1,1,1], [0,0,1], [1,1,1]],
    '0': [[1,1,1], [1,0,1], [1,0,1], [1,0,1], [1,1,1]],
    
    ',': [[0,0,0], [0,0,0], [0,0,0], [1,0,0], [0,1,0]],
    '?': [[1,1,1], [0,0,1], [0,1,1], [0,0,0], [0,1,0]],
    '-': [[0,0,0], [0,0,0], [1,1,1], [0,0,0], [0,0,0]],
    '+': [[0,0,0], [0,1,0], [1,1,1], [0,1,0], [0,0,0]],
    '.': [[0], [0], [0], [0], [1]],
    '!': [[1], [1], [1], [0], [1]],
    ':': [[0], [1], [0], [1], [0]],
    ' ': [[0], [0], [0], [0], [0]]
}

VISUAL_EASINGS = {
    "linear":         lambda t: t,
    "ease_in":        lambda t: t * t,
    "ease_out":       lambda t: 1 - (1 - t) ** 2,
    "ease_in_out":    lambda t: 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2,
    "ease_out_cubic": lambda t: 1 - (1 - t) ** 3
}

OK_TEXTS = [
    "Ok",
    "Yeah",
    "YEAH",
    "Hell yeah",
    "Yep",
    "Sure",
    "Cool",
    "Right",
    "You bet"
]

NO_TEXTS = [
    "Nah",
    "Later",
    "Nope",
    "Pass",
    "Not now",
    "No thanks"
]
