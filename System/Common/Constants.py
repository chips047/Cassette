from __future__ import annotations

import json

from pathlib import Path
from loguru  import logger

from PyQt6.QtGui import QGuiApplication

from System.Common import Utils

from System.Devices import (
    DEVICES,
    PORT_MAPS,
    make_ranges,
    DeviceConfig,
    NUMBER_TO_CODE,
    MasterTrackMode,
    MASTER_TRACK_IDENTIFIER
)

# Settings Controller

current_settings = Utils.SettingsController("chips047", "Cassette")

def values_match(
        first:  object,
        second: object
    ) -> bool:

    if first == second:
        return True

    if first is None or second is None:
        return False

    try:
        if float(first) == float(second):
            return True

    except (ValueError, TypeError):
        pass

    return str(first).strip().lower() == str(second).strip().lower()

def get_default_value(parameters: dict[str, object]) -> int | float | str | bool | None:
    element_type = parameters.get("type", "")

    if element_type == "checkbox":
        return parameters.get("default", False)

    if element_type == "slider":
        return parameters.get("default", parameters.get("min", 0))

    if element_type.startswith("selector"):
        options_map = parameters.get("map", {})
        default_key = parameters.get("default")

        return options_map.get(default_key)

    return parameters.get("default")

def validate_and_repair_settings(setting_components: dict[str, list[dict[str, object]]]) -> None:
    settings       = current_settings.instance
    settings_repaired = False

    for components in setting_components.values():
        for parameters in components:
            key          = str(parameters["key"])
            element_type = str(parameters.get("type", ""))

            if key.startswith("_") and element_type not in ("tutorial_reset", "checkbox"):
                continue

            current_value = current_settings.get(key)
            default_value = get_default_value(parameters)

            if element_type == "checkbox":
                if not isinstance(current_value, bool):
                    fallback = bool(default_value)
                    current_settings.data[key] = fallback
                    settings.setValue(key, fallback)
                    settings_repaired = True

            elif element_type == "slider":
                min_value = int(parameters.get("min", 0))
                max_value = int(parameters.get("max", 100))

                if not isinstance(current_value, (int, float)):
                    fallback = int(default_value if default_value is not None else min_value)
                    current_settings.data[key] = fallback
                    settings.setValue(key, fallback)
                    settings_repaired = True

                elif current_value < min_value or current_value > max_value:
                    clamped_value              = max(min_value, min(max_value, int(current_value)))
                    current_settings.data[key] = clamped_value
                    settings.setValue(key, clamped_value)
                    settings_repaired          = True

            elif element_type.startswith("selector"):
                options_map   = parameters.get("map", {})
                matched_value = None

                for option_title, option_value in options_map.items():
                    if values_match(current_value, option_value) or values_match(current_value, option_title):
                        matched_value = option_value
                        break

                if matched_value is None:
                    current_settings.data[key] = default_value
                    settings.setValue(key, default_value)
                    settings_repaired = True

                elif current_value != matched_value:
                    current_settings.data[key] = matched_value
                    settings.setValue(key, matched_value)
                    settings_repaired          = True

            elif element_type == "delay_setup":
                if not isinstance(current_value, (int, float)) or current_value is None:
                    fallback                   = int(default_value if default_value is not None else 0)
                    current_settings.data[key] = fallback
                    settings.setValue(key, fallback)
                    settings_repaired          = True

            elif current_value is None and default_value is not None:
                current_settings.data[key] = default_value
                settings.setValue(key, default_value)
                settings_repaired          = True

    if settings_repaired:
        settings.sync()
        logger.warning("Repaired invalid or unaligned settings in chips047/Cassette")

def load_settings() -> None:
    current_settings.load()
    validate_and_repair_settings(SettingsDict())

    logger.debug("Loaded and verified settings from chips047/Cassette")

def prepare_default_settings(setting_components: dict[str, list]) -> None:
    settings      = current_settings.instance
    existing_keys = set(settings.allKeys())
    new_keys      = set()

    for components in setting_components.values():
        for parameters in components:
            key = parameters["key"]
            new_keys.add(key)

            if key in existing_keys:
                continue

            default_value = get_default_value(parameters)

            if default_value is not None:
                settings.setValue(key, default_value)

    for key in (existing_keys - new_keys):
        if key.startswith("_"):
            continue

        settings.remove(key)

    settings.sync()
    validate_and_repair_settings(setting_components)

    logger.success("Default settings prepared and synced.")

# Default Settings

STATUS_BAR_DEFAULT = f"Cassette {open(Utils.get_resource_path('version')).read()}"

DEFAULT_DURATION             = 100
DEFAULT_BRIGHTNESS           = 100

SPRING_STIFFNESS             = 0.04
FADE_OVERLAY_SIZE            = 60
SPRING_DAMPING_FACTOR        = 0.4
PINCH_ZOOM_SENSITIVITY       = 400.0
ANIMATION_TICK_INTERVAL      = 8
USER_SCROLL_IDLE_TIMEOUT     = 150
WHEEL_SCROLL_SENSITIVITY     = 1.0
INERTIA_DECELERATION_RATE    = 0.93
VISUAL_RESISTANCE_STRENGTH   = 600.0

EXIT_FADE_BASE_MS            = 3000
EXIT_EFFECTS_DELAY_MS        = 1700
EXIT_CLOSE_SOUND_DURATION_MS = 1500
NO_AUDIO_EXIT_DELAY_MS       = 1800
ENTRY_VERTICAL_OFFSET_PX     = 150

UNDERWATER_FREQUENCY_HZ      = 550.0
UNDERWATER_Q                 = 0.9
UNDERWATER_BLIP_MS           = 260

MIN_AUDIO_MS                 = 30000.0
LOOP_GUARD_MS                = 220.0
LOOP_WATCHDOG_MS             = 150

BASELINE_SPEED               = 1.0
INTRO_RAMP_MS                = 2600
RELEASE_RAMP_MS              = 900

PAGE_PULSE_SPEED             = 0.8
PAGE_PULSE_DOWN_MS           = 120
PAGE_PULSE_UP_MS             = 160

PLAY_PAUSE_ACCEL_RAMP_MS     = 320
PLAY_PAUSE_HOLD_MS           = 1400
PLAY_PAUSE_STOP_RAMP_MS      = 400
PLAY_PAUSE_TEXT_HOLD_MS      = 1600

PLAY_PAUSE_GOOD_TEXT = (
    "Good.\n"
    "Let's put a glyph on the timeline next."
)

PLAY_PAUSE_QUICK_TEXT = (
    "Wow. You learn quick.\n"
    "Let's put a glyph on the timeline next."
)

COUNT_STAGE_TARGET      = 3
SPEED_STAGE_TARGET      = 3
SCROLL_TARGET_PX        = 1000.0
ZOOM_TARGET_MULTIPLIER  = 120
PLAYHEAD_MOVE_TARGET    = 3
PLAYHEAD_MOVE_GAP_MS    = 250
DRAG_PROGRESS_TARGET_MS = 750.0
RESUME_AUDIO_RAMP_MS    = 1400

FFMPEG_PATH  = Utils.get_ffmpeg_path("ffmpeg")
FFPROBE_PATH = Utils.get_ffmpeg_path("ffprobe")

FPS_60  = 16
FPS_120 = 8
FPS_30  = 33

GITHUB_LINK = "https://www.github.com/chips047/Cassette/releases/latest"

CROP_TOLERANCE_MS            = 100

EASE_PER_TICK                = 0.28
SNAP_THRESHOLD               = 0.003

POLL_INTERVAL_MS             = 20

EJECT_FADE_DURATION_MS       = 3000
INTERRUPTED_FADE_DURATION_MS = 1000

# Shader Programs

GLYPH_VERTEX_SHADER = """#version 330 core
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

GLYPH_FRAGMENT_SHADER = """#version 330 core

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

FLOATING_WINDOW_VERTEX_SHADER = """#version 410 core
layout (location = 0) in vec3 position;
layout (location = 1) in vec2 texCoord;

uniform mat4 u_curr_mvp;

out vec2 UV;

void main() {
    gl_Position = u_curr_mvp * vec4(position, 1.0);
    UV = texCoord;
}
"""

FLOATING_WINDOW_FRAGMENT_SHADER = """#version 410 core
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

CASSETTE_VERTEX_SHADER_SOURCE = """#version 330 core
layout (location = 0) in vec3 attribute_position;
layout (location = 1) in vec3 attribute_normal;
layout (location = 2) in vec2 attribute_texture_coordinate;
layout (location = 3) in vec4 attribute_tangent;

uniform mat4 projection_matrix;
uniform mat4 view_matrix;
uniform mat4 model_matrix;

out vec3 fragment_position;
out vec2 fragment_texture_coordinate;
out mat3 fragment_tangent_basis;

void main() {
    mat3 normal_matrix = mat3(transpose(inverse(model_matrix)));
    vec4 world_position = model_matrix * vec4(attribute_position, 1.0);

    fragment_position = vec3(world_position);
    fragment_texture_coordinate = attribute_texture_coordinate;

    vec3 normal_vector = normalize(normal_matrix * attribute_normal);
    vec3 tangent_vector = normalize(normal_matrix * attribute_tangent.xyz);
    tangent_vector = normalize(tangent_vector - dot(tangent_vector, normal_vector) * normal_vector);
    vec3 bitangent_vector = cross(normal_vector, tangent_vector) * attribute_tangent.w;

    fragment_tangent_basis = mat3(tangent_vector, bitangent_vector, normal_vector);

    gl_Position = projection_matrix * view_matrix * world_position;
}
"""

CASSETTE_FRAGMENT_SHADER_SOURCE = """#version 330 core
in vec3 fragment_position;
in vec2 fragment_texture_coordinate;
in mat3 fragment_tangent_basis;

uniform vec3 camera_position;
uniform vec3 accent_color;
uniform vec3 button_light_position;
uniform float global_alpha;

uniform sampler2D base_color_sampler;
uniform sampler2D normal_sampler;
uniform sampler2D metallic_roughness_sampler;
uniform sampler2D emissive_sampler;

uniform int has_base_color_texture;
uniform int has_normal_texture;
uniform int has_metallic_roughness_texture;
uniform int has_emissive_texture;

out vec4 output_color;

void main() {
    vec4 base_sample = vec4(0.25, 0.25, 0.27, 1.0);

    if (has_base_color_texture == 1) {
        base_sample = texture(base_color_sampler, fragment_texture_coordinate);
    }

    if (base_sample.a < 0.1 || global_alpha < 0.001) {
        discard;
    }

    vec3 normal_vector = normalize(fragment_tangent_basis[2]);

    if (has_normal_texture == 1) {
        vec3 normal_map_sample = texture(normal_sampler, fragment_texture_coordinate).rgb * 2.0 - 1.0;
        normal_vector = normalize(fragment_tangent_basis * normal_map_sample);
    }

    float roughness_factor = 0.55;
    float metallic_factor = 0.15;

    if (has_metallic_roughness_texture == 1) {
        vec4 metallic_roughness_sample = texture(metallic_roughness_sampler, fragment_texture_coordinate);
        roughness_factor = clamp(metallic_roughness_sample.g, 0.04, 1.0);
        metallic_factor = clamp(metallic_roughness_sample.b, 0.0, 1.0);
    }

    vec3 emissive_color = vec3(0.0);

    if (has_emissive_texture == 1) {
        emissive_color = texture(emissive_sampler, fragment_texture_coordinate).rgb;
    }

    vec3 view_direction = normalize(camera_position - fragment_position);

    vec3 key_light_direction = normalize(vec3(0.7, 1.1, 1.4));
    vec3 fill_light_direction = normalize(vec3(-1.0, -0.4, 0.9));
    vec3 top_light_direction = normalize(vec3(0.0, 1.5, 0.2));

    float key_diffuse = max(dot(normal_vector, key_light_direction), 0.0);
    float fill_diffuse = max(dot(normal_vector, fill_light_direction), 0.0);
    float top_diffuse = max(dot(normal_vector, top_light_direction), 0.0);

    vec3 key_half_vector = normalize(key_light_direction + view_direction);
    float specular_power = mix(96.0, 4.0, roughness_factor);
    float specular_strength = pow(max(dot(normal_vector, key_half_vector), 0.0), specular_power);
    vec3 specular_tint = mix(vec3(0.04), base_sample.rgb, metallic_factor);
    vec3 specular_component = specular_tint * specular_strength * (1.2 - roughness_factor * 0.5);

    vec3 diffuse_albedo = base_sample.rgb * (1.0 - metallic_factor);
    vec3 button_light_vector = button_light_position - fragment_position;
    float button_light_distance = length(button_light_vector);
    vec3 button_light_direction = button_light_vector / max(button_light_distance, 0.0001);
    float button_light_diffuse = max(dot(normal_vector, button_light_direction), 0.0);
    float button_light_falloff = 1.0 - smoothstep(0.08, 1.15, button_light_distance);
    vec3 button_light_component = diffuse_albedo * accent_color
        * (0.12 + button_light_diffuse * 1.25)
        * pow(button_light_falloff, 1.6);

    vec3 ambient_component = diffuse_albedo * 0.52;
    vec3 diffuse_component = diffuse_albedo * (key_diffuse * 0.85 + fill_diffuse * 0.35 + top_diffuse * 0.25);

    vec3 resolved_rgb = (ambient_component + diffuse_component + specular_component + button_light_component + emissive_color * 1.6) * 0.78;

    output_color = vec4(resolved_rgb, base_sample.a * global_alpha);
}
"""

# Settings Schema

class SettingsDictionaryMeta(type):
    def __getitem__(cls, item: str) -> list:
        return cls()[item]

    def items(cls) -> object:
        return cls().items()

    def values(cls) -> object:
        return cls().values()

    def keys(cls) -> object:
        return cls().keys()

    def get(
            cls,
            key:     str,
            default: object = None
        ) -> object:

        return cls().get(key, default)

    def __iter__(cls) -> object:
        return iter(cls())

class SettingsDict(dict, metaclass = SettingsDictionaryMeta):
    candidate_refresh_rates = [30, 60, 75, 90, 120, 144, 165, 240, 360, 480]

    def __init__(self) -> None:
        super().__init__(self.build())

    @staticmethod
    def get_maximum_screen_refresh_rate() -> int:
        application = QGuiApplication.instance()

        if not application:
            return 60

        screens = application.screens()

        if not screens and application.primaryScreen():
            screens = [application.primaryScreen()]

        refresh_rates = [
            round(screen.refreshRate())
            for screen in screens
            if screen and screen.refreshRate() > 0
        ]

        if not refresh_rates:
            return 60

        return max(refresh_rates)

    @classmethod
    def get_frames_per_second_options(cls) -> tuple[dict[str, int], str]:
        application = QGuiApplication.instance()

        if not application:
            frames_per_second_map = {str(rate): rate for rate in cls.candidate_refresh_rates}
            return frames_per_second_map, "60"

        maximum_rate = cls.get_maximum_screen_refresh_rate()
        valid_rates  = [rate for rate in cls.candidate_refresh_rates if rate <= maximum_rate]

        if maximum_rate > 30 and maximum_rate not in valid_rates:
            valid_rates.append(maximum_rate)
            valid_rates.sort()

        if not valid_rates:
            valid_rates = [30, 60]

        frames_per_second_map = {str(rate): rate for rate in valid_rates}
        default_selection     = str(maximum_rate) if str(maximum_rate) in frames_per_second_map else "60"

        return frames_per_second_map, default_selection

    @staticmethod
    def get_animation_styles() -> tuple[dict[str, str], str]:
        styles_map: dict[str, str] = {}

        from System.Interface.Windows.WindowAnimationStyles import WindowAnimationStyle
        styles_map = WindowAnimationStyle.get_available_styles()

        if not styles_map:
            candidate_paths = [
                Path(__file__).parent.parent / "Interface" / "Animation" / "Styles",
                Path(__file__).parent / "Animation" / "Styles",
                Path(Utils.get_resource_path("Animation/Styles"))
            ]

            for styles_directory in candidate_paths:
                if not styles_directory.is_dir():
                    continue

                for file_path in sorted(styles_directory.glob("*.json")):
                    try:
                        with file_path.open("r", encoding = "utf-8") as file:
                            data = json.load(file)

                        display_name             = data.get("title") or data.get("name") or file_path.stem.capitalize()
                        styles_map[display_name] = file_path.stem

                    except Exception:
                        continue

                if styles_map:
                    break

        if not styles_map:
            styles_map = {
                "Smooth":   "smooth",
                "Bouncy":   "bouncy",
                "Roll":     "roll",
                "Glitch":   "glitch",
                "Classic":  "classic",
                "Electric": "electric"
            }

        default_style = "Bouncy" if "Bouncy" in styles_map else next(iter(styles_map.keys()))

        return styles_map, default_style

    @classmethod
    def build(cls) -> dict[str, list]:
        frames_per_second_map, default_frames_per_second = cls.get_frames_per_second_options()
        styles_map, default_style                        = cls.get_animation_styles()

        return {
            "Performance": [
                {
                    "type":    "selector",
                    "title":   "OpenGL MSAA: Requires restart.",
                    "key":     "msaa",
                    "map": {
                        "No MSAA": 0,
                        "2x":      2,
                        "4x":      4,
                        "8x":      8
                    },
                    "default": "4x"
                },
                {
                    "type":        "checkbox",
                    "title":       "CPU Antialiasing",
                    "key":         "antialiasing",
                    "description": "Antialiasing on CPU rendered components.",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Compositor GPU Rendering",
                    "key":         "gpu",
                    "description": "Significantly improves smoothness. Requires restart.",
                    "default":     True
                },
                {
                    "type":    "selector",
                    "title":   "Waveform Tile Width",
                    "key":     "tile_width",
                    "map": {
                        "256":  256,
                        "512":  512,
                        "1024": 1024
                    },
                    "default": "512"
                },
                {
                    "type":        "checkbox",
                    "title":       "Rounded Glyph Corners",
                    "description": "Draws glyphs with rounded corners. Disabling may slightly improve rendering performance.",
                    "key":         "glyph_rounded_corners",
                    "default":     True
                }
            ],

            "Scrolling and Zoom": [
                {
                    "type":    "selector",
                    "title":   "Trackpad Scroll Mode",
                    "key":     "trackpad_scroll_mode",
                    "map": {
                        "Classic":     "classic",
                        "Directional": "directional"
                    },
                    "default": "Classic"
                },
                {
                    "type":    "slider",
                    "title":   "Zoom Step (on Wheel)",
                    "min":     1,
                    "max":     100,
                    "key":     "zoom_step",
                    "default": 20
                },
                {
                    "type":    "selector",
                    "title":   "Horizontal Scroll Acceleration",
                    "key":     "scroll_acceleration",
                    "map": {
                        "Low":       0.1,
                        "Normal":    0.3,
                        "High":      0.5,
                        "Very High": 0.8
                    },
                    "default": "Normal"
                },
                {
                    "type":        "checkbox",
                    "title":       "Scroll Smoothing",
                    "key":         "scroll_smoothing",
                    "description": "Makes scrolling more fluid.",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Scroll Inertia",
                    "key":         "scroll_inertia",
                    "description": "Keeps scrolling naturally after a swipe.",
                    "default":     True
                },
                {
                    "type":    "selector",
                    "title":   "Menu Scroll Sensitivity",
                    "key":     "wheel_scroll_sensitivity",
                    "map": {
                        "Low":    0.125,
                        "Normal": 0.175,
                        "High":   0.200
                    },
                    "default": "Normal"
                },
                {
                    "type":    "selector",
                    "title":   "Menu Scroll Inertia",
                    "key":     "inertia_deceleration_rate",
                    "map": {
                        "Low":    0.85,
                        "Normal": 0.93,
                        "High":   0.97
                    },
                    "default": "Normal"
                },
                {
                    "type":    "slider",
                    "title":   "Spring Stiffness",
                    "min":     1,
                    "max":     10,
                    "key":     "scroll_spring_stiffness",
                    "default": 1
                },
                {
                    "type":    "slider",
                    "title":   "Spring Damping",
                    "min":     10,
                    "max":     90,
                    "key":     "scroll_spring_damping",
                    "default": 15
                },
                {
                    "type":    "selector",
                    "title":   "Overscroll Resistance",
                    "key":     "overscroll_resistance",
                    "map": {
                        "Soft":   1200,
                        "Normal": 600,
                        "Rigid":  300
                    },
                    "default": "Soft"
                }
            ],

            "Interface": [
                {
                    "type":    "selector",
                    "title":   "Animation Style",
                    "key":     "animation_style",
                    "map":     styles_map,
                    "default": default_style
                },
                {
                    "type":    "selector",
                    "title":   "Animation Multiplier",
                    "key":     "animation_multiplier",
                    "map": {
                        "0.75x": 0.75,
                        "1.0x":  1.0,
                        "1.15x": 1.15,
                        "1.25x": 1.25,
                        "1.5x":  1.5,
                        "3.0x":  3.0,
                        "5.0x":  5.0,
                        "10.0x": 10.0,
                        "20.0x": 20.0
                    },
                    "default": "1.0x"
                },
                {
                    "type":    "selector",
                    "title":   "Target FPS",
                    "key":     "target_fps",
                    "map":     frames_per_second_map,
                    "default": default_frames_per_second
                },
                {
                    "type":        "checkbox",
                    "title":       "Floating Window Animations",
                    "key":         "floating_window_animations",
                    "description": "Enables popup background animations.",
                    "default":     True
                },
                {
                    "type":    "selector",
                    "title":   "Window Hover Smoothing",
                    "key":     "window_hover_smoothing",
                    "map": {
                        "No Tilt":   0.0,
                        "Slow":      0.07,
                        "Normal":    0.2,
                        "Very Fast": 0.8
                    },
                    "default": "Normal"
                },
                {
                    "type":        "checkbox",
                    "title":       "BPM Animations",
                    "description": "Enables beat - synced animations.",
                    "key":         "bpm_animations",
                    "default":     True
                },
                {
                    "type":    "selector",
                    "title":   "Window BPM Animation Style",
                    "key":     "window_bpm_animation_style",
                    "map": {
                        "Pulse": "pulse",
                        "Punch": "punch"
                    },
                    "default": "Pulse"
                },
                {
                    "type":        "checkbox",
                    "title":       "Glyph 3D Tilt",
                    "description": "Enables 3D tilt when resizing or moving a glyph.",
                    "key":         "glyph_tilt_animation",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Glyph Spawn Animation",
                    "description": "Enables animations when spawning or despawning a glyph.",
                    "key":         "glyph_spawn_animation",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Playhead Animations",
                    "description": "Enables animations on the playhead.",
                    "key":         "playhead_animations",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Marquee Hide Animation",
                    "description": "Enables the marquee hiding / damping animation.",
                    "key":         "marquee_hide_animation",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Textbox Animations",
                    "key":         "textbox_animations",
                    "description": "Enables textbox animations.",
                    "default":     True
                }
            ],

            "Audio": [
                {
                    "type":        "delay_setup",
                    "description": "Audio Latency.\nPress Space to the beat.",
                    "key":         "audio_delay_ms",
                    "default":     0
                },
                {
                    "type":    "selector",
                    "title":   "Audio Blocksize",
                    "key":     "audio_blocksize",
                    "map": {
                        "32":   32,
                        "64":   64,
                        "128":  128,
                        "256":  256,
                        "512":  512,
                        "1024": 1024,
                        "2048": 2048,
                        "4096": 4096
                    },
                    "default": "128"
                },
                {
                    "type":        "checkbox",
                    "title":       "Disable Sounds",
                    "key":         "disable_sounds",
                    "description": "Disables all UI sounds.",
                    "default":     False
                },
                {
                    "type":    "slider",
                    "title":   "Sound Effect Volume",
                    "key":     "sound_effect_volume",
                    "min":     0,
                    "max":     100,
                    "default": 100
                },
                {
                    "type":        "checkbox",
                    "title":       "Sound Tone Effects",
                    "description": "Enables dynamic tonal variation for UI sounds.",
                    "key":         "sound_tone_effects",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Startup Sound",
                    "description": "Enables a sound effect on application startup.",
                    "key":         "startup_sound",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Shutdown Sound",
                    "description": "Enables a sound effect on application shutdown.",
                    "key":         "shutdown_sound",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Glyph Spawn Sound",
                    "description": "Enables a sound effect when a glyph is spawned.",
                    "key":         "glyph_spawn_sound",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Other Glyph Sounds",
                    "description": "Enables nudging and moving sounds.",
                    "key":         "other_glyph_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Glyph Deletion Sound",
                    "description": "Enables a sound effect when a glyph is deleted.",
                    "key":         "glyph_deletion_sound",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Glyph Duplication Sound",
                    "description": "Enables a sound effect when a glyph is duplicated.",
                    "key":         "glyph_duplication_sound",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Glyph Stack Sounds",
                    "description": "Enables sound effects when stacking or unstacking glyphs.",
                    "key":         "glyph_stack_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Brightness Adjustment Sound",
                    "description": "Enables a sound effect when adjusting brightness.",
                    "key":         "brightness_adjustment_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Playhead Sounds",
                    "description": "Enables sound effects on playhead actions.",
                    "key":         "playhead_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Timeline Jump Sound",
                    "description": "Enables a sound effect when jumping to the start or end of a timeline.",
                    "key":         "timeline_jump_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Rewind Sounds",
                    "description": "Enables a sound effect when auto scrolling.",
                    "key":         "rewind_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Checkbox Sounds",
                    "description": "Enables sound effects when toggling checkboxes.",
                    "key":         "checkbox_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Selector Sounds",
                    "description": "Enables sound effects when changing selector values.",
                    "key":         "selector_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Textbox Sounds",
                    "description": "Enables sound effects on textbox actions.",
                    "key":         "textbox_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Context Menu Sounds",
                    "description": "Enables sound effects on context menu actions.",
                    "key":         "context_menu_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Floating Window Sounds",
                    "description": "Enables sound effects on floating window actions.",
                    "key":         "floating_window_sounds",
                    "default":     True
                },
                {
                    "type":        "checkbox",
                    "title":       "Drag & Drop Sounds",
                    "description": "Enables sound effects when dragging and dropping files.",
                    "key":         "drag_drop_sounds",
                    "default":     True
                }
            ],

            "User Experience": [
                {
                    "type":        "tutorial_reset",
                    "description": f"Interactive Tutorial.\n{'Show again on the next project load.' if current_settings['_tutorial_shown'] else 'You haven\'t seen the tutorial yet.'}",
                    "key":         "_tutorial_shown",
                    "button_text": "Reset",
                    "default":     False
                },
                {
                    "type":        "checkbox",
                    "title":       "Enable Quit Dialog",
                    "description": "Enables confirmation dialog before closing.",
                    "default":     True,
                    "key":         "quit_dialog"
                },
                {
                    "type":    "selector",
                    "title":   "Mouse Click Behavior",
                    "key":     "mouse_click_behavior",
                    "map": {
                        "Normal":          "normal",
                        "Fast (On Press)": "fast"
                    },
                    "default": "Normal"
                },
                {
                    "type":    "selector",
                    "title":   "Playhead Position",
                    "key":     "playhead_position",
                    "map": {
                        "Left":   0.25,
                        "Center": 0.5,
                        "Right":  0.75
                    },
                    "default": "Left"
                },
                {
                    "type":    "slider",
                    "title":   "Playhead Arrow Increment",
                    "min":     1,
                    "max":     10,
                    "key":     "arrow_increment",
                    "default": 1
                },
                {
                    "type":    "selector",
                    "title":   "Default Scaling",
                    "key":     "default_scaling",
                    "map": {
                        "Very Small": 100,
                        "Small":      200,
                        "Medium":     300,
                        "Big":        400,
                        "Very Big":   500
                    },
                    "default": "Very Big"
                },
                {
                    "type":    "selector",
                    "title":   "Waveform Smoothing",
                    "key":     "waveform_smoothing",
                    "map": {
                        "Accuracy":   0.5,
                        "Balance":    1.7,
                        "Smoothness": 3.0
                    },
                    "default": "Balance"
                },
                {
                    "type":    "slider",
                    "title":   "Brightness Step",
                    "min":     1,
                    "max":     25,
                    "key":     "brightness_step",
                    "default": 5
                },
                {
                    "type":    "slider",
                    "title":   "Glyph Resize Handle Width",
                    "min":     1,
                    "max":     25,
                    "key":     "glyph_resize_handle_width",
                    "default": 10
                },
                {
                    "type":    "selector",
                    "title":   "Playback Stop Mode",
                    "key":     "playback_stop_mode",
                    "map": {
                        "Pause":  "pause",
                        "Return": "return"
                    },
                    "default": "Pause"
                }
            ],

            "Dev": [
                {
                    "type":        "checkbox",
                    "title":       "FloatingWindow Debugging",
                    "description": "Enables debugging for the FloatingWindow class. Slows down the app.",
                    "key":         "floating_window_debugging",
                    "default":     False
                }
            ]
        }

# Dot Matrix Font

DOT_FONT = {
    'A': [[0,1,0],     [1,0,1],     [1,1,1],     [1,0,1],     [1,0,1]    ],
    'B': [[1,1,0],     [1,0,1],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'C': [[0,1,1],     [1,0,0],     [1,0,0],     [1,0,0],     [0,1,1]    ],
    'D': [[1,1,0],     [1,0,1],     [1,0,1],     [1,0,1],     [1,1,0]    ],
    'E': [[1,1,1],     [1,0,0],     [1,1,0],     [1,0,0],     [1,1,1]    ],
    'F': [[1,1,1],     [1,0,0],     [1,1,0],     [1,0,0],     [1,0,0]    ],
    'G': [[0,1,1],     [1,0,0],     [1,0,1],     [1,0,1],     [0,1,1]    ],
    'H': [[1,0,1],     [1,0,1],     [1,1,1],     [1,0,1],     [1,0,1]    ],
    'I': [[1,1,1],     [0,1,0],     [0,1,0],     [0,1,0],     [1,1,1]    ],
    'J': [[0,0,1],     [0,0,1],     [0,0,1],     [1,0,1],     [0,1,0]    ],
    'K': [[1,0,1],     [1,0,1],     [1,1,0],     [1,0,1],     [1,0,1]    ],
    'L': [[1,0,0],     [1,0,0],     [1,0,0],     [1,0,0],     [1,1,1]    ],
    'M': [[1,0,1],     [1,1,1],     [1,0,1],     [1,0,1],     [1,0,1]    ],
    'N': [[1,1,0],     [1,0,1],     [1,0,1],     [1,0,1],     [1,0,1]    ],
    'O': [[0,1,0],     [1,0,1],     [1,0,1],     [1,0,1],     [0,1,0]    ],
    'P': [[1,1,0],     [1,0,1],     [1,1,0],     [1,0,0],     [1,0,0]    ],
    'Q': [[0,1,0],     [1,0,1],     [1,0,1],     [1,1,1],     [0,1,1]    ],
    'R': [[1,1,0],     [1,0,1],     [1,1,0],     [1,0,1],     [1,0,1]    ],
    'S': [[0,1,1],     [1,0,0],     [0,1,0],     [0,0,1],     [1,1,0]    ],
    'T': [[1,1,1],     [0,1,0],     [0,1,0],     [0,1,0],     [0,1,0]    ],
    'U': [[1,0,1],     [1,0,1],     [1,0,1],     [1,0,1],     [1,1,1]    ],
    'V': [[1,0,1],     [1,0,1],     [1,0,1],     [0,1,0],     [0,1,0]    ],
    'W': [[1,0,1],     [1,0,1],     [1,0,1],     [1,1,1],     [1,0,1]    ],
    'X': [[1,0,1],     [1,0,1],     [0,1,0],     [1,0,1],     [1,0,1]    ],
    'Y': [[1,0,1],     [1,0,1],     [0,1,0],     [0,1,0],     [0,1,0]    ],
    'Z': [[1,1,1],     [0,0,1],     [0,1,0],     [1,0,0],     [1,1,1]    ],

    'a': [[0,0,0],     [0,1,1],     [1,0,1],     [1,1,1],     [0,1,1]    ],
    'b': [[0,0,0],     [1,0,0],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'c': [[0,0,0],     [0,1,1],     [1,0,0],     [1,0,0],     [0,1,1]    ],
    'd': [[0,0,0],     [0,0,1],     [0,1,1],     [1,0,1],     [0,1,1]    ],
    'e': [[0,0,0],     [0,1,0],     [1,1,1],     [1,0,0],     [0,1,1]    ],
    'f': [[0,0,0],     [0,1,1],     [0,1,0],     [0,1,1],     [0,1,0]    ],
    'g': [[0,1,1],     [1,0,1],     [0,1,1],     [0,0,1],     [1,1,0]    ],
    'h': [[0,0,0],     [1,0,0],     [1,1,0],     [1,0,1],     [1,0,1]    ],
    'l': [[0],         [1],         [1],         [1],         [1]        ],
    'i': [[1],         [0],         [1],         [1],         [1]        ],
    'k': [[0,0,0],     [1,0,1],     [1,1,0],     [1,0,1],     [1,0,1]    ],
    'm': [[0,0,0,0,0], [1,1,1,1,1], [1,0,1,0,1], [1,0,1,0,1], [1,0,1,0,1]],
    'n': [[0,0,0],     [1,1,0],     [1,0,1],     [1,0,1],     [1,0,1]    ],
    'o': [[0,0,0],     [0,1,0],     [1,0,1],     [1,0,1],     [0,1,0]    ],
    'p': [[0,0,0],     [1,1,0],     [1,0,1],     [1,1,0],     [1,0,0]    ],
    'r': [[0,0,0],     [1,1,0],     [1,0,1],     [1,0,0],     [1,0,0]    ],
    's': [[0,0,0],     [0,1,1],     [0,1,0],     [0,0,1],     [1,1,1]    ],
    'q': [[0,0,0],     [0,1,1],     [1,0,1],     [0,1,1],     [0,0,1]    ],
    't': [[0,0,0],     [0,1,0],     [1,1,1],     [0,1,0],     [0,1,1]    ],
    'u': [[0,0,0],     [1,0,1],     [1,0,1],     [1,0,1],     [0,1,1]    ],
    'v': [[0,0,0],     [1,0,1],     [1,0,1],     [1,0,1],     [0,1,0]    ],
    'w': [[0,0,0,0,0], [1,0,1,0,1], [1,0,1,0,1], [1,1,1,1,1], [1,0,1,0,1]],
    'x': [[0,0,0],     [1,0,1],     [0,1,0],     [1,0,1],     [1,0,1]    ],
    'y': [[0,0,0],     [1,0,1],     [1,1,1],     [0,0,1],     [1,1,0]    ],
    'z': [[0,0,0],     [1,1,1],     [0,1,0],     [1,0,0],     [1,1,1]    ],
    'j': [[0,1],       [0,0],       [0,1],       [0,1],       [1,0]      ],

    'А': [[0,1,0],     [1,0,1],     [1,1,1],     [1,0,1],     [1,0,1]    ],
    'Б': [[1,1,1],     [1,0,0],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'В': [[1,1,0],     [1,0,1],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'Г': [[1,1,1],     [1,0,0],     [1,0,0],     [1,0,0],     [1,0,0]    ],
    'Д': [[0,1,1],     [0,1,0],     [0,1,0],     [1,1,1],     [1,0,1]    ],
    'Е': [[1,1,1],     [1,0,0],     [1,1,0],     [1,0,0],     [1,1,1]    ],
    'Ё': [[0,1,0],     [1,1,1],     [1,0,0],     [1,1,0],     [1,1,1]    ],
    'Ж': [[1,0,1],     [1,0,1],     [0,1,0],     [1,0,1],     [1,0,1]    ],
    'З': [[1,1,0],     [0,0,1],     [0,1,0],     [0,0,1],     [1,1,0]    ],
    'И': [[1,0,1],     [1,0,1],     [1,1,1],     [1,0,1],     [1,0,1]    ],
    'Й': [[1,1,1],     [1,0,1],     [1,1,1],     [1,0,1],     [1,0,1]    ],
    'К': [[1,0,1],     [1,0,1],     [1,1,0],     [1,0,1],     [1,0,1]    ],
    'Л': [[0,1,1],     [1,0,1],     [1,0,1],     [1,0,1],     [1,0,1]    ],
    'М': [[1,0,1],     [1,1,1],     [1,0,1],     [1,0,1],     [1,0,1]    ],
    'Н': [[1,0,1],     [1,0,1],     [1,1,1],     [1,0,1],     [1,0,1]    ],
    'О': [[0,1,0],     [1,0,1],     [1,0,1],     [1,0,1],     [0,1,0]    ],
    'П': [[1,1,1],     [1,0,1],     [1,0,1],     [1,0,1],     [1,0,1]    ],
    'Р': [[1,1,0],     [1,0,1],     [1,1,0],     [1,0,0],     [1,0,0]    ],
    'С': [[0,1,1],     [1,0,0],     [1,0,0],     [1,0,0],     [0,1,1]    ],
    'Т': [[1,1,1],     [0,1,0],     [0,1,0],     [0,1,0],     [0,1,0]    ],
    'У': [[1,0,1],     [1,0,1],     [0,1,1],     [0,0,1],     [0,1,1]    ],
    'Ф': [[0,1,0],     [1,1,1],     [1,1,1],     [0,1,0],     [0,1,0]    ],
    'Х': [[1,0,1],     [1,0,1],     [0,1,0],     [1,0,1],     [1,0,1]    ],
    'Ц': [[1,0,1],     [1,0,1],     [1,0,1],     [1,1,1],     [0,0,1]    ],
    'Ч': [[1,0,1],     [1,0,1],     [0,1,1],     [0,0,1],     [0,0,1]    ],
    'Ш': [[1,0,1],     [1,0,1],     [1,0,1],     [1,0,1],     [1,1,1]    ],
    'Щ': [[1,0,1,0,0], [1,0,1,0,0], [1,0,1,0,0], [1,1,1,0,0], [0,0,0,1,1]],
    'Ъ': [[1,1,0],     [0,1,0],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'Ы': [[1,0,1],     [1,0,1],     [1,1,1],     [1,0,1],     [1,1,1]    ],
    'Ь': [[1,0,0],     [1,0,0],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'Э': [[1,1,0],     [0,0,1],     [0,1,1],     [0,0,1],     [1,1,0]    ],
    'Ю': [[1,1,1],     [1,0,1],     [1,1,1],     [1,0,1],     [1,1,1]    ],
    'Я': [[0,1,1],     [1,0,1],     [0,1,1],     [1,0,1],     [1,0,1]    ],

    'а': [[0,0,0],     [0,1,1],     [1,0,1],     [1,1,1],     [0,1,1]    ],
    'б': [[1,1,0],     [1,0,0],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'в': [[0,0,0],     [1,1,0],     [1,1,1],     [1,0,1],     [1,1,1]    ],
    'г': [[0,0,0],     [1,1,1],     [1,0,0],     [1,0,0],     [1,0,0]    ],
    'д': [[0,1,0],     [0,1,0],     [1,1,1],     [1,0,1],     [1,0,1]    ],
    'е': [[0,0,0],     [0,1,0],     [1,1,1],     [1,0,0],     [0,1,1]    ],
    'ё': [[0,1,0],     [0,0,0],     [1,1,1],     [1,0,0],     [1,1,1]    ],
    'ж': [[0,0,0],     [1,0,1],     [0,1,0],     [1,0,1],     [1,0,1]    ],
    'з': [[0,0,0],     [1,1,1],     [0,1,1],     [0,0,1],     [1,1,1]    ],
    'и': [[0,0,0],     [1,0,1],     [1,0,1],     [1,0,1],     [1,1,1]    ],
    'й': [[1,0,1],     [0,0,0],     [1,0,1],     [1,0,1],     [1,1,1]    ],
    'к': [[0,0,0],     [1,0,1],     [1,1,0],     [1,0,1],     [1,0,1]    ],
    'л': [[0,0,0],     [0,1,1],     [1,0,1],     [1,0,1],     [1,0,1]    ],
    'м': [[0,0,0,0,0], [1,1,1,1,1], [1,0,1,0,1], [1,0,1,0,1], [1,0,1,0,1]],
    'н': [[0,0,0],     [1,0,1],     [1,1,1],     [1,0,1],     [1,0,1]    ],
    'о': [[0,0,0],     [0,1,0],     [1,0,1],     [1,0,1],     [0,1,0]    ],
    'п': [[0,0,0],     [1,1,1],     [1,0,1],     [1,0,1],     [1,0,1]    ],
    'р': [[0,0,0],     [1,1,0],     [1,0,1],     [1,1,0],     [1,0,0]    ],
    'с': [[0,0,0],     [0,1,1],     [1,0,0],     [1,0,0],     [0,1,1]    ],
    'т': [[0,0,0,0,0], [1,1,1,1,1], [0,0,1,0,0], [0,0,1,0,0], [0,0,1,0,0]],
    'у': [[0,0,0],     [1,0,1],     [1,1,1],     [0,0,1],     [1,1,0]    ],
    'ф': [[0,1,0],     [1,1,1],     [1,1,1],     [0,1,0],     [0,1,0]    ],
    'х': [[0,0,0],     [1,0,1],     [0,1,0],     [1,0,1],     [1,0,1]    ],
    'ц': [[0,0,0],     [1,0,1],     [1,0,1],     [1,1,1],     [0,0,1]    ],
    'ч': [[0,0,0],     [1,0,1],     [0,1,1],     [0,0,1],     [0,0,1]    ],
    'ш': [[0,0,0],     [1,0,1],     [1,0,1],     [1,0,1],     [1,1,1]    ],
    'щ': [[0,0,0,0,0], [1,0,1,0,0], [1,0,1,0,0], [1,1,1,0,0], [0,0,0,1,1]],
    'ъ': [[0,1,0],     [0,1,0],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'ы': [[0,0,0],     [1,0,1],     [1,1,1],     [1,0,1],     [1,1,1]    ],
    'ь': [[0,0,0],     [1,0,0],     [1,1,0],     [1,0,1],     [1,1,0]    ],
    'э': [[0,0,0],     [1,1,0],     [0,1,1],     [0,0,1],     [1,1,0]    ],
    'ю': [[0,0,0,0,0], [1,0,1,1,0], [1,0,1,0,1], [1,0,1,0,1], [1,0,1,1,0]],
    'я': [[0,0,0],     [0,1,1],     [1,0,1],     [0,1,1],     [1,0,1]    ],

    '1': [[0,1,0],     [1,1,0],     [0,1,0],     [0,1,0],     [1,1,1]    ],
    '2': [[1,1,1],     [0,0,1],     [1,1,1],     [1,0,0],     [1,1,1]    ],
    '3': [[1,1,1],     [0,0,1],     [0,1,1],     [0,0,1],     [1,1,1]    ],
    '4': [[1,0,1],     [1,0,1],     [1,1,1],     [0,0,1],     [0,0,1]    ],
    '5': [[1,1,1],     [1,0,0],     [1,1,1],     [0,0,1],     [1,1,1]    ],
    '6': [[1,1,1],     [1,0,0],     [1,1,1],     [1,0,1],     [1,1,1]    ],
    '7': [[1,1,1],     [0,0,1],     [0,1,0],     [0,1,0],     [0,1,0]    ],
    '8': [[1,1,1],     [1,0,1],     [1,1,1],     [1,0,1],     [1,1,1]    ],
    '9': [[1,1,1],     [1,0,1],     [1,1,1],     [0,0,1],     [1,1,1]    ],
    '0': [[1,1,1],     [1,0,1],     [1,0,1],     [1,0,1],     [1,1,1]    ],

    ',': [[0,0,0],     [0,0,0],     [0,0,0],     [1,0,0],     [0,1,0]    ],
    '?': [[1,1,1],     [0,0,1],     [0,1,1],     [0,0,0],     [0,1,0]    ],
    '-': [[0,0,0],     [0,0,0],     [1,1,1],     [0,0,0],     [0,0,0]    ],
    '+': [[0,0,0],     [0,1,0],     [1,1,1],     [0,1,0],     [0,0,0]    ],
    '.': [[0],         [0],         [0],         [0],         [1]        ],
    '!': [[1],         [1],         [1],         [0],         [1]        ],
    ':': [[0],         [1],         [0],         [1],         [0]        ],
    ' ': [[0],         [0],         [0],         [0],         [0]        ]
}

# Visual Easings

VISUAL_EASINGS = {
    "linear":         lambda time: time,
    "ease_in":        lambda time: time * time,
    "ease_out":       lambda time: 1 - (1 - time) ** 2,
    "ease_in_out":    lambda time: 2 * time * time if time < 0.5 else 1 - (-2 * time + 2) ** 2 / 2,
    "ease_out_cubic": lambda time: 1 - (1 - time) ** 3
}

# Interface Responses

OK_TEXTS = [
    "Ok",
    "Yeah",
    "YEAH",
    "Yep",
    "Sure",
    "Cool",
    "Right",
    "You bet",
    "Hell yeah"
]

NO_TEXTS = [
    "Nah",
    "Later",
    "Nope",
    "Pass",
    "Not now",
    "No thanks"
]

CLOSE_BUTTON_RATING_TEXTS = {
    1: [
        "Why do you keep me.",
        "You don't like Cassette :(",
        "I remember that one star..."
    ],

    2: [
        "Meh.",
        "I'm sad.",
        "One day you rated me... 2 stars..."
    ],
    
    3: [
        "3",
        "Close",
        "3 stars"
    ],

    4: [
        "Good app.",
        "Cassette is cool.",
        "You gave me 4 stars!!! :)"
    ],

    5: [
        "Peak app.",
        "#cassette",
        "I luv it!!!"
    ]
}