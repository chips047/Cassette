from __future__ import annotations

from System.Devices.Base import (
    DeviceConfig,
    generate_matrix_visualization_map
)

ROW_COUNTS = [
    7, 11, 15, 17, 19, 21, 21, 23, 23, 25, 25, 25, 25,
    25, 25, 25, 25, 23, 23, 21, 21, 19, 17, 15, 11, 7
]

PHONE3 = DeviceConfig(
    code_name          = "PHONE3",
    short_name         = "3",
    full_name          = "Phone (3)",
    hardware_codes     = ["A075"],
    composer_code_name = "Asteroids",
    matrix_rows        = ROW_COUNTS,
    visualization_map  = generate_matrix_visualization_map(ROW_COUNTS, (260, 260), 5.0)
)