from __future__ import annotations

import random

from dataclasses import dataclass

from PyQt6.QtCore import QTimer

from System.Interface           import Widgets
from System.Interface.Windows   import FloatingWindowGPU
from System.Interface.Animation import LoomEngine

@dataclass
class QuitPhrase:
    message:        str
    cancel_text:    str
    quit_text:      str
    on_back_action: object = None
    on_quit_action: object = None

def spare_action(window: QuitWindow) -> int:
    cancel_btn = window.get_cancel_button()
    cancel_btn.setText("Ha. Haha. Funny.")
    cancel_btn.start_glitch()

    return 3000

PHRASES = [
    QuitPhrase(
        message     = "Right behind you.",
        cancel_text = "Go to back",
        quit_text   = "Look back"
    ),

    QuitPhrase(
        message     = "Don't get comfortable.",
        cancel_text = "I won't",
        quit_text   = "I want"
    ),

    QuitPhrase(
        message     = "Might as well quit. The button's right there.",
        cancel_text = "No...",
        quit_text   = "Button"
    ),

    QuitPhrase(
        message        = "You're gonna give me a headache. Or, you would, if I could feel pain.",
        cancel_text    = "I spare you",
        quit_text      = "Quit",
        on_back_action = spare_action
    )
]

class QuitWindow(FloatingWindowGPU):
    def __init__(self) -> None:
        super().__init__("Quit?", enable_audioplayer_effects = False)

        self.phrase: QuitPhrase = random.choice(PHRASES)

        phrase_label = Widgets.DescriptionLabel(self.phrase.message)

        self.button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, self.phrase.cancel_text, self.on_back),
                (Widgets.NothingButton,     self.phrase.quit_text,   self.on_quit)
            ],
            button_width = 200
        )

        self.content_layout.addWidget(phrase_label)
        self.content_layout.addLayout(self.button_row)

        self.player.set_passes([1000], duration_ms = 2500)

    def get_cancel_button(self):
        return self.button_row.get_button(self.phrase.cancel_text)

    def on_quit(self) -> None:
        delay = 0

        if self.phrase.on_quit_action:
            delay = self.phrase.on_quit_action(self)

        if delay > 0:
            QTimer.singleShot(delay, self.on_ok)

        else:
            self.on_ok()

    def on_back(self) -> None:
        delay = 0
        
        if self.phrase.on_back_action:
            delay = self.phrase.on_back_action(self)

        if delay > 0:
            QTimer.singleShot(delay, self.on_cancel)

        else:
            self.on_cancel()

        self.player.set_passes(mix = 0.0, duration_ms = 1500)

    def open_window(self) -> None:
        self.play_stage_sound("open")

        if not self.animations_active or not self.animations_enabled:
            return

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.6), (1.0, 1.0)],
            duration_ms     = 1000,
            easing_function = LoomEngine.Easing.ease_out_quart
        )

        self.opacity_background_property.play_curve(
            keyframes       = [(0.0, 0.0), (1.0, 1.0)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.linear
        )

        self.opacity_content_property.play_curve(
            keyframes       = [(0.0, 0.0), (1.0, 1.0)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.linear
        )

    def request_close(self) -> None:
        if not self.enable_close_animation:
            return

        self.play_stage_sound("close")

        if not self.animations_active or not self.animations_enabled:
            self.really_close()
            return

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 1.6)],
            duration_ms     = 1000,
            easing_function = LoomEngine.Easing.ease_out_quart
        )

        self.opacity_background_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 0.0)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.linear,
            finished        = self.really_close
        )

        self.opacity_content_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 0.0)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.linear,
            finished        = self.really_close
        )