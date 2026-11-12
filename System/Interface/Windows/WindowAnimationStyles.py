from __future__ import annotations

import json
import random

from pathlib import Path
from loguru  import logger

from PyQt6.QtCore import QTimer

from System.Services            import Player
from System.Interface.Animation import LoomEngine

# Sound Playback

def play_sound_choice(
        source:      list[str] | str | None,
        setting_key: str       | None = None,
        speed:       float            = 1.0
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

    def resolve(self, specification: object) -> object:
        if not isinstance(specification, dict):
            return specification

        if "period" in specification:
            return self.owner.period_randomizer(*[tuple(bound) for bound in specification["period"]])

        if "uniform" in specification:
            return random.uniform(*specification["uniform"])

        if "randint" in specification:
            return random.randint(*specification["randint"])

        if "choice" in specification:
            return random.choice(specification["choice"])

        if specification.get("maximum_scale"):
            return self.owner.maximum_scale()

        if specification.get("optimal_offset_x"):
            offset_x, _ = self.owner.get_optimal_offset(*self.size)
            return offset_x

        if specification.get("optimal_offset_y"):
            _, offset_y = self.owner.get_optimal_offset(*self.size)
            return offset_y

        raise ValueError(f"Unknown value specification: {specification}")

    def resolve_keyframes(self, keyframes: list[list]) -> list[tuple[float, object]]:
        return [(moment, self.resolve(value)) for moment, value in keyframes]

    def resolve_schedule(self, schedule: list[list]) -> list[tuple[int, object]]:
        return [(delay_ms, self.resolve(value)) for delay_ms, value in schedule]

# Window Animation Style

class WindowAnimationStyle:
    styles_directory = Path("System/Interface/Animation/Styles")
    cache            = {}

    def __init__(self, name: str) -> None:
        self.name = name
        self.data = self.load(name)

    @classmethod
    def load(cls, name: str) -> dict:
        if name == "disabled":
            return {
                "title": "Disabled",
                "sounds": {},
                "open": {},
                "close": {},
                "disturb": {}
            }

        if name in cls.cache:
            return cls.cache[name]

        path = cls.styles_directory / f"{name}.json"

        with path.open("r", encoding = "utf-8") as file:
            data = json.load(file)

        cls.cache[name] = data

        return data

    def play(
            self,
            stage: str,
            owner: object,
            size:  tuple[int, int]
        ) -> None:

        if self.name == "disabled":
            if stage == "close":
                owner.really_close()

            return

        stage_data = self.data.get(stage)

        if not stage_data:
            if stage == "close":
                owner.really_close()

            return

        resolver = ValueResolver(owner, size)

        for name, value in stage_data.get("bases", {}).items():
            handle = getattr(owner, name + "_property")
            handle.set_base(resolver.resolve(value))

        for name, schedule in stage_data.get("schedules", {}).items():
            self.play_schedule(owner, name, resolver.resolve_schedule(schedule))

        for name, curve in stage_data.get("curves", {}).items():
            self.play_curve(owner, name, curve, resolver)

        after_ms = stage_data.get("close_after_ms")

        if after_ms:
            QTimer.singleShot(after_ms, owner.really_close)

    @classmethod
    def get_available_styles(cls) -> dict[str, str]:
        styles: dict[str, str] = {}

        if not cls.styles_directory.is_dir():
            return styles

        for file_path in sorted(cls.styles_directory.glob("*.json")):
            style_identifier = file_path.stem

            try:
                data         = cls.load(style_identifier)
                display_name = data.get("title") or data.get("name") or style_identifier.capitalize()

                styles[display_name] = style_identifier

            except Exception as exception:
                logger.error(f"Failed to load animation style {file_path}: {exception}")

        return styles

    def sound_for(self, stage: str) -> list[str] | str | None:
        return self.data.get("sounds", {}).get(stage)

    def play_schedule(
            self,
            owner:    object,
            name:     str,
            schedule: list[tuple[int, object]]
        ) -> None:

        handle = getattr(owner, name + "_property")

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
        easing   = getattr(LoomEngine.Easing, curve.get("easing", "ease_out_cubic"))
        finished = getattr(owner, curve["finished"]) if "finished" in curve else None

        handle.play_curve(
            keyframes                  = resolver.resolve_keyframes(curve["keyframes"]),
            duration_ms                = curve["duration_ms"],
            easing_function            = easing,
            delay_ms                   = curve.get("delay_ms", 0),
            multiply_duration_by_speed = curve.get("multiply_duration_by_speed", True),
            finished                   = finished
        )