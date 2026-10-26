from __future__ import annotations

from System.Devices.Base import (
    make_ranges,
    DeviceConfig
)

PHONE4A = DeviceConfig(
    code_name          = "PHONE4A",
    short_name         = "4a",
    full_name          = "Phone (4a)",
    hardware_codes     = ["A069"],
    composer_code_name = "Frogger",
    glyph_indexes      = make_ranges(7),
    zone_indexes       = [[i] for i in range(7)],
    segments_map       = {"1": 7},
    visualization_map  = {
        "glyphs": {
            "1": {
                "svg":      "M4,3 V150",
                "position": (12, 0),
                "segments": 7
            }
        },
        "size":      (32, 150),
        "thickness": 14
    },
    port_variants      = ["2a", "3a"],
    port_map           = {
        "PHONE2A": {
            "1": {
                "mode":     "random",
                "variants": [
                    ["1"],
                    ["2"],
                    ["3"],
                    ["1", "2"],
                    ["1", "3"],
                    ["2", "3"],
                    ["1", "2", "3"]
                ]
            },

            "effects": {
                "segments": {
                    "1": ["1"]
                }
            }
        },

        "PHONE4B": {
            "1": ["1"],

            "effects": {
                "segments": {
                    "1": ["1"]
                }
            }
        },

        "PHONE3A": {
            "1": {
                "mode":     "random",
                "variants": [
                    ["1"],
                    ["2"],
                    ["3"],
                    ["1", "2"],
                    ["1", "3"],
                    ["2", "3"],
                    ["1", "2", "3"]
                ]
            },

            "effects": {
                "segments": {
                    "1": ["1"]
                }
            }
        }
    }
)