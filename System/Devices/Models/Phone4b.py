from __future__ import annotations

from System.Devices.Base import (
    make_ranges,
    DeviceConfig
)

PHONE4B = DeviceConfig(
    code_name          = "PHONE4B",
    short_name         = "4b",
    full_name          = "Phone (4b)",
    hardware_codes     = ["A009P"],
    composer_code_name = "SuperContra",
    glyph_indexes      = make_ranges(5),
    zone_indexes       = [[i] for i in range(5)],
    segments_map       = {"1": 5},
    visualization_map  = {
        "glyphs": {
            "1": {
                "svg":      "M4,3 V70",
                "position": (12, 0),
                "segments": 5
            }
        },
        "size":      (32, 70),
        "thickness": 14
    },
    port_variants      = ["2a", "3a", "4a"],
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

        "PHONE4A": {
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