import sys
import ctypes
import ctypes.util

from enum import Enum

# Enumerations

class HapticType(Enum):
    GENERIC   = 0
    ALIGNMENT = 1
    LEVEL     = 2


class HapticPerformanceTime(Enum):
    DEFAULT        = 0
    NOW            = 1
    DRAW_COMPLETED = 2

# Controller Engine

class MacHapticController:
    is_supported:     bool
    performer:        int    | None
    perform_function: object | None
    selector:         int    | None

    def __init__(self) -> None:
        self.is_supported     = sys.platform == "darwin"
        self.performer        = None
        self.perform_function = None
        self.selector         = None

        if not self.is_supported:
            return

        self.setup_bridge()

    # Bridge Setup

    def setup_bridge(self) -> None:
        objective_c_path = ctypes.util.find_library("objc")

        if not objective_c_path:
            self.is_supported = False
            return

        application_kit_path = ctypes.util.find_library("AppKit")

        if not application_kit_path:
            self.is_supported = False
            return

        objective_c = ctypes.cdll.LoadLibrary(objective_c_path)
        ctypes.cdll.LoadLibrary(application_kit_path)

        objective_c.objc_getClass.restype  = ctypes.c_void_p
        objective_c.objc_getClass.argtypes = [ctypes.c_char_p]

        objective_c.sel_registerName.restype  = ctypes.c_void_p
        objective_c.sel_registerName.argtypes = [ctypes.c_char_p]

        manager_class = objective_c.objc_getClass(b"NSHapticFeedbackManager")
        if not manager_class:
            self.is_supported = False
            return

        message_send_address = ctypes.cast(objective_c.objc_msgSend, ctypes.c_void_p).value

        if not message_send_address:
            self.is_supported = False
            return

        get_performer_function = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p
        )(message_send_address)

        default_performer_selector = objective_c.sel_registerName(b"defaultPerformer")
        if not default_performer_selector:
            self.is_supported = False
            return

        self.performer = get_performer_function(manager_class, default_performer_selector)
        if not self.performer:
            self.is_supported = False
            return

        self.selector = objective_c.sel_registerName(b"performFeedbackPattern:performanceTime:")

        if not self.selector:
            self.is_supported = False
            return

        self.perform_function = ctypes.CFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_ulong
        )(message_send_address)

    # Feedback Execution

    def trigger(
        self,
        feedback_type:    HapticType            = HapticType.ALIGNMENT,
        performance_time: HapticPerformanceTime = HapticPerformanceTime.NOW
    ) -> None:
        
        if not self.is_supported:
            return

        if not self.performer:
            return

        if not self.perform_function:
            return

        if not self.selector:
            return

        pattern_identifier = feedback_type.value
        time_identifier    = performance_time.value

        self.perform_function(
            self.performer,
            self.selector,
            pattern_identifier,
            time_identifier
        )

    # Convenience Triggers

    def click(self) -> None:
        self.trigger(HapticType.GENERIC)
        print("CLICK")

    def snap(self) -> None:
        self.trigger(HapticType.ALIGNMENT)
        print("SNAP")

    def step(self) -> None:
        self.trigger(HapticType.LEVEL)
        print("STEP")

ui_haptics = MacHapticController()