from __future__ import annotations

from System.Devices.Base import DeviceConfig

from System.Devices.Models.Phone1     import PHONE1
from System.Devices.Models.Phone2     import PHONE2
from System.Devices.Models.Phone3     import PHONE3
from System.Devices.Models.Phone2a    import PHONE2A
from System.Devices.Models.Phone3a    import PHONE3A
from System.Devices.Models.Phone4a    import PHONE4A
from System.Devices.Models.Phone4b    import PHONE4B
from System.Devices.Models.Phone4aPro import PHONE4APRO

DEVICES: dict[str, DeviceConfig] = {
    "PHONE1":     PHONE1,
    "PHONE2":     PHONE2,
    "PHONE3":     PHONE3,
    "PHONE2A":    PHONE2A,
    "PHONE3A":    PHONE3A,
    "PHONE4A":    PHONE4A,
    "PHONE4B":    PHONE4B,
    "PHONE4APRO": PHONE4APRO
}

NUMBER_TO_CODE: dict[str, str] = {
    configuration.short_name: code_name
    for code_name, configuration in DEVICES.items()
}

PORT_MAPS: dict[str, dict[str, dict[str, object]]] = {
    code_name: {"to": configuration.port_map}
    for code_name, configuration in DEVICES.items()
    if configuration.port_map
}