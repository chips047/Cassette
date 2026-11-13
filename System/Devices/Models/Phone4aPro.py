from __future__ import annotations

from System.Devices.Base import (
    DeviceConfig,
    generate_matrix_visualization_map
)

ROW_COUNTS = [
    5, 9, 11, 11, 13, 13, 13, 13, 13, 11, 11, 9, 5
]

PHONE4APRO = DeviceConfig(
    code_name          = "PHONE4APRO",
    short_name         = "4ap",
    full_name          = "Phone (4a) Pro",
    hardware_codes     = ["A142PRO", "A069PRO"],
    composer_code_name = "FroggerPro",
    matrix_rows        = ROW_COUNTS,
    visualization_map  = generate_matrix_visualization_map(ROW_COUNTS, (260, 260), 8.0)
)