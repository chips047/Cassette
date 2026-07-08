import json
import random

from pathlib import Path

from PyQt6.QtCore import QTimer

from System.Services import Player

from System.Interface.Animation.LoomEngine import Easing

# Sound Mini Language

def play_sound_choice(
        source:      list[str] | str | None,
        setting_key: str | None = None,
        speed:       float      = 1.0
    ) -> None:

    if not source:
        return

    resolved = random.choice(source) if isinstance(source, list) and len(source) > 1 else source
    resolved = resolved[0] if isinstance(resolved, list) else resolved

    Player.ui_player.play_sound(
        resolved,
        setting_key = setting_key,
        speed       = speed
    )

# Value Resolution

class ValueResolver:
    def __init__(
            self,
            owner: object,
            size:  tuple[int, int]
        ) -> None:

        self.owner = owner
        self.size  = size

    def resolve(self, spec: object) -> object:
        if not isinstance(spec, dict):
            return spec

        if "period" in spec:
            return self.owner.period_randomizer(*[tuple(bound) for bound in spec["period"]])

        if "uniform" in spec:
            return random.uniform(*spec["uniform"])

        if "randint" in spec:
            return random.randint(*spec["randint"])

        if "choice" in spec:
            return random.choice(spec["choice"])

        if spec.get("maximum_scale"):
            return self.owner.maximum_scale()

        if spec.get("optimal_offset_x"):
            offset_x, _ = self.owner.get_optimal_offset(*self.size)
            return offset_x

        if spec.get("optimal_offset_y"):
            _, offset_y = self.owner.get_optimal_offset(*self.size)
            return offset_y

        raise ValueError(f"Unknown value spec: {spec}")

    def resolve_keyframes(self, keyframes: list[list]) -> list[tuple[float, object]]:
        return [(moment, self.resolve(value)) for moment, value in keyframes]

    def resolve_schedule(self, schedule: list[list]) -> list[tuple[int, object]]:
        return [(delay_ms, self.resolve(value)) for delay_ms, value in schedule]

# Window Animation Style

class WindowAnimationStyle:
    styles_directory = Path(__file__).parent / "Animation/Styles"
    cache: dict = {}

    def __init__(self, name: str) -> None:
        self.name = name
        self.data = self.load(name)

    @classmethod
    def load(cls, name: str) -> dict:
        if name in cls.cache:
            return cls.cache[name]

        path = cls.styles_directory / f"{name}.json"

        with path.open("r", encoding = "utf-8") as file:
            data = json.load(file)

        cls.cache[name] = data

        return data

    def sound_for(self, stage: str) -> list[str] | str | None:
        return self.data.get("sounds", {}).get(stage)

    def play(
            self,
            stage: str,
            owner: object,
            size:  tuple[int, int]
        ) -> None:

        stage_data = self.data.get(stage)

        if not stage_data:
            return

        resolver = ValueResolver(owner, size)

        for name, value in stage_data.get("bases", {}).items():
            owner.property_handles[name].set_base(resolver.resolve(value))

        for name, schedule in stage_data.get("schedules", {}).items():
            self.play_schedule(owner, name, resolver.resolve_schedule(schedule))

        for name, curve in stage_data.get("curves", {}).items():
            self.play_curve(owner, name, curve, resolver)

        after_ms = stage_data.get("close_after_ms")

        if after_ms is not None:
            QTimer.singleShot(after_ms, owner.really_close)

    def play_schedule(
            self,
            owner:    object,
            name:     str,
            schedule: list[tuple[int, object]]
        ) -> None:

        handle = owner.property_handles[name]

        for delay_ms, value in schedule:
            QTimer.singleShot(delay_ms, lambda value = value: handle.set_base(value))

    def play_curve(
            self,
            owner:    object,
            name:     str,
            curve:    dict,
            resolver: ValueResolver
        ) -> None:

        handle   = getattr(owner, name + "_property")
        easing   = getattr(Easing, curve.get("easing", "ease_out_cubic"))
        finished = getattr(owner, curve["finished"]) if "finished" in curve else None

        handle.play_curve(
            keyframes                   = resolver.resolve_keyframes(curve["keyframes"]),
            duration_ms                 = curve["duration_ms"],
            easing_function             = easing,
            delay_ms                    = curve.get("delay_ms", 0),
            multiply_duration_by_speed  = curve.get("multiply_duration_by_speed", True),
            finished                    = finished
        )