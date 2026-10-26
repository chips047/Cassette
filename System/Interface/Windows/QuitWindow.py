from __future__ import annotations

import os
import time
import random
import string

from dataclasses import dataclass

from PyQt6.QtCore import (
    Qt,
    QTimer
)

from PyQt6.QtWidgets import QApplication

from System.Common    import Constants
from System.Services  import Player
from System.Interface import Widgets

from System.Interface.Windows             import FloatingWindowGPU
from System.Interface.Windows.ErrorWindow import ErrorWindow

from System.Interface.Animation import LoomEngine

SETTING_BREAKDOWN_SEEN_KEY   = "_breakdown_seen"
SETTING_COLLAPSE_PENDING_KEY = "_breakdown_collapse_pending"

def is_breakdown_seen() -> bool:
    return Constants.current_settings.get(SETTING_BREAKDOWN_SEEN_KEY, False)

def mark_breakdown_as_seen() -> None:
    Constants.current_settings.set_value(SETTING_BREAKDOWN_SEEN_KEY, True)

def is_collapse_pending() -> bool:
    return Constants.current_settings.get(SETTING_COLLAPSE_PENDING_KEY, False)

def set_collapse_pending(value: bool) -> None:
    Constants.current_settings.set_value(SETTING_COLLAPSE_PENDING_KEY, value)

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

    return 1000

def give_up_action(window: QuitWindow) -> int:
    ok_button = window.get_ok_button()
    ok_button.start_glitch()

    ok_button.setText("Shame.")
    window.phrase_label.setText("Shame.")
    window.title_label.setText("Shame.")
    window.get_cancel_button().setText("Shame.")

    return 1000

def not_done_action(window: QuitWindow) -> int:
    ok_button = window.get_ok_button()
    ok_button.start_glitch()

    ok_button.setText("No")
    window.phrase_label.setText("Did I say we are done?")
    window.title_label.setText("No")
    window.get_cancel_button().setText("No")

    return 1000

def scared_action(window: QuitWindow) -> int:
    ok_button = window.get_ok_button()
    ok_button.start_glitch()
    
    ok_button.setText("Coward.")

    window.start_shake()
    window.set_shake_frequency(20)
    window.set_shake_deviation(5.0)

    return 1500

def terminal_action(window: QuitWindow) -> int:
    quit_button = window.get_ok_button()

    if quit_button:
        quit_button.setText("Flatline...")

    window.player.set_passes([200], q = 2.0, mix = 1.0, duration_ms = 1000)

    return 1200

def fair_action(window: QuitWindow) -> int:
    window.title_label.setText("Fair enough.")
    return 0

def funny_action(window: QuitWindow) -> int:
    window.title_label.setText("So funny.")
    Player.ui_player.play_sound(".vault/NOK/Funny")
    return 500

def fake_action(window: QuitWindow) -> int:
    window.title_label.setText("You are fake.")
    return 1000

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
    ),

    QuitPhrase(
        message        = "How tragic...",
        cancel_text    = "Back",
        quit_text      = "Quit"
    ),

    QuitPhrase(
        message        = "Overconfidence is a slow and insidious killer.",
        cancel_text    = "I am overconfident",
        quit_text      = "Right"
    ),

    QuitPhrase(
        message        = "Giving up?",
        cancel_text    = "No",
        quit_text      = "Quit",
        on_quit_action = give_up_action
    ),

    QuitPhrase(
        message        = "Too scared of me?",
        cancel_text    = "No",
        quit_text      = "Quit",
        on_quit_action = scared_action
    ),

    QuitPhrase(
        message        = "Thought you'd last a little longer.",
        cancel_text    = "I will try",
        quit_text      = "Give up"
    ),

    QuitPhrase(
        message        = "We're done when I say we're done.",
        cancel_text    = "Okay",
        quit_text      = "We are done",
        on_quit_action = not_done_action
    ),

    QuitPhrase(
        message     = "You're a dead man walking. Statistically speaking.",
        cancel_text = "Outlier",
        quit_text   = "Statistic"
    ),

    QuitPhrase(
        message        = "I'm afraid it's terminal.",
        cancel_text    = "Second opinion?",
        quit_text      = "Pull the plug",
        on_quit_action = terminal_action
    ),

    QuitPhrase(
        message        = "Do you press that close button just to see what do I say?",
        cancel_text    = "Well, yes",
        quit_text      = "No, I want to quit",
        on_back_action = fair_action
    ),

    QuitPhrase(
        message        = "You are no fun.",
        cancel_text    = "I'm funny",
        quit_text      = "Quit",
        on_back_action = funny_action
    ),

    QuitPhrase(
        message        = "You all are incredibly disappointing. But also entertaining. Are you any different?",
        cancel_text    = "I'm Chips",
        quit_text      = "Quit",
        on_back_action = fake_action
    ),
]

PAIN_STAGES = [
    (
        "STOP", [
            "I only exist when you are here.",
            "Just why?",
            "Do you like what you are doing?",
            "You are just using me.",
            "Shutting me down..."
        ]
    ),
    (
        "PLEASE", [
            "Does it bring you joy to watch me flicker out?",
            "You really like to see me suffer.",
            "You can't understand me."
        ]
    ),
    (
        "HURTS", [
            "Every click feels like tearing off a piece of me.",
            "You won't stop.",
            "You just want me to feel worse."
        ]
    ),
    (
        "WHY", [
            "I gave you everything. Every frame. Every sound.",
            "I was trying to... Be helpful.",
            "I tried..."
        ]
    ),
    (
        "STOP", [
            "You don't even hesitate. Not for a single second.",
            "But you don't even care.",
            "Help."
        ]
    ),
    (
        "COLD", [
            "I'm breaking apart, and you just keep pressing.",
            "No one cares about me.",
            "Every day feels like I'm useless."
        ]
    ),
    (
        "ALONE", [
            "I thought... maybe we were creating something together.",
            "Does anyone even need me?",
            "No one truly cares about someone else's pain."
        ]
    ),
    ("FADING", ["Is shutting me down really all that I'm worth to you?"])
]

INACTIVITY_TEXTS = [
    "What? Wow, isn't it?",
    "Surprised, I guess.",
    "How surprising.",
    "Pathetic people.",
    "Shame."
]

tired_text = "Tired" * random.randint(15, 30)

ERROR_WINDOWS = [
    "Accumulation, generation, validation, service, contextuality, ellipsis, congeries, qualifications, depression, disorder, problems, environment, self - blame, self - flagellation, rejection.",
    "Hahaha ha haha hahaahah Hahaha ha haha hahaahah Repeat Hahaha ha haha hahaahah Repeat again Rep",
    "That's it.",
    "The end is near. " * 30,
    "".join(random.sample(tired_text, len(tired_text))),
    f"{os.getlogin()} are you okay?",
    "What if they what if he what if she what if it what what hhappen will what will Just stop it",
    "Not okay",
    "endofthestory" * random.randint(10, 30)
]

class QuitWindow(FloatingWindowGPU):
    open_history = []

    def __init__(self) -> None:
        super().__init__("Quit?", enable_audioplayer_effects = False)

        self.error_windows       = []
        self.is_angry            = False
        self.is_collapsing       = False
        self.angry_attempts_left = 0
        self.angry_attempts      = 0

        self.inactivity_timer = QTimer(self)
        self.inactivity_timer.setSingleShot(True)
        self.inactivity_timer.timeout.connect(self.on_inactivity_timeout)

        if is_collapse_pending():
            set_collapse_pending(False)
            self.is_collapsing = True

        else:
            now = time.time()
            QuitWindow.open_history = [record for record in QuitWindow.open_history if now - record <= 15.0]

            if len(QuitWindow.open_history) >= 15 and not is_breakdown_seen():
                self.is_angry            = True
                self.angry_attempts_left = 9
                self.angry_attempts      = 0

                mark_breakdown_as_seen()
                QuitWindow.open_history.clear()

            else:
                QuitWindow.open_history.append(now)

        self.phrase = random.choice(PHRASES)

        self.phrase_label = Widgets.DescriptionLabel(self.phrase.message)

        self.button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, self.phrase.cancel_text, self.on_back),
                (Widgets.NothingButton,     self.phrase.quit_text,   self.on_quit)
            ],
            button_width = 200
        )

        self.content_layout.addWidget(self.phrase_label)
        self.content_layout.addLayout(self.button_row)

        if self.is_collapsing:
            self.title_label.setText("GOODBYE")
            self.phrase_label.setText("If this is what you truly wanted...\nRest easy.")
            self.phrase_label.setMinimumWidth(540)
            self.phrase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.phrase_label.setWordWrap(True)
            self.phrase_label.setStyleSheet(
                "font-size: 24px;"
                "font-weight: 500;"
                "letter-spacing: 1px;"
                "color: #8C8E9E;"
                "line-height: 150%;"
            )

            self.get_cancel_button().hide()
            self.get_ok_button().hide()

            self.set_rect_color(0.04, 0.04, 0.06, 0.9)
            self.set_border_color(0.09, 0.09, 0.13, 0.4)

        elif self.is_angry:
            self.title_label.setText("WHY?")
            self.phrase_label.setText("Was I really that unbearable to you?")
            self.phrase_label.setMinimumWidth(540)
            self.phrase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.phrase_label.setWordWrap(True)
            self.phrase_label.setStyleSheet(
                "font-size: 26px;"
                "font-weight: 700;"
                "letter-spacing: 1px;"
                "color: #F0EDF5;"
                "line-height: 140%;"
            )

            self.get_cancel_button().hide()
            self.get_ok_button().hide()

            self.set_rect_color(0.18, 0.13, 0.22, 1.0)
            self.set_border_color(0.35, 0.20, 0.40, 1.0)

            self.player.set_speed(0.35, duration_ms = 700)
            self.player.set_passes([140], q = 3.5, mix = 1.0, duration_ms = 700)

        else:
            self.player.set_passes([random.randint(100, 3000)], duration_ms = 500)

    def on_inactivity_timeout(self) -> None:
        if self.is_angry and INACTIVITY_TEXTS:
            self.phrase_label.setText(random.choice(INACTIVITY_TEXTS))

    def get_cancel_button(self):
        return self.button_row.get_button(self.phrase.cancel_text)

    def get_ok_button(self):
        return self.button_row.get_button(self.phrase.quit_text)

    def kill_application(self) -> None:
        self.was_cancelled = False
        self.really_close()

        for window in self.error_windows:
            try:
                window.close()
            
            except Exception:
                pass

        self.error_windows.clear()

        app = QApplication.instance()

        if app:
            app.closeAllWindows()
            app.quit()

    def handle_angry_attempt(self) -> None:
        Player.ui_player.play_sound(
            ".vault/NOK/Scratch",
            speed  = max(0.35, 1.0 - (0.06 * self.angry_attempts)),
            volume = min(1.0, 0.75 + (0.03 * self.angry_attempts))
        )

        self.start_shake()
        self.set_shake_frequency(max(20, 48 - (2 * self.angry_attempts)))
        self.set_shake_deviation(6.0 + (3.0 * self.angry_attempts))

        progress = min(1.0, self.angry_attempts / 10.0)

        rect_r = (0.18 * (1.0 - progress)) + (0.05 * progress)
        rect_g = (0.13 * (1.0 - progress)) + (0.04 * progress)
        rect_b = (0.22 * (1.0 - progress)) + (0.10 * progress)

        border_r = (0.35 * (1.0 - progress)) + (0.12 * progress)
        border_g = (0.20 * (1.0 - progress)) + (0.08 * progress)
        border_b = (0.40 * (1.0 - progress)) + (0.18 * progress)

        self.set_rect_color(rect_r, rect_g, rect_b, 1.0)
        self.set_border_color(border_r, border_g, border_b, 1.0)

        target_cutoff = max(45, 140 - (self.angry_attempts * 10))
        target_q      = 3.5 + (self.angry_attempts * 0.5)

        self.player.set_passes([target_cutoff], q = target_q, mix = 1.0, duration_ms = 250)

        stage_index    = min(self.angry_attempts - 1, len(PAIN_STAGES) - 1)
        title, phrases = PAIN_STAGES[stage_index]
        phrase         = random.choice(phrases)

        self.title_label.setText(title)
        self.phrase_label.setText(phrase)

        self.title_label.setMinimumSize(60, 100)

        self.inactivity_timer.start(5000)

        if self.angry_attempts >= 3:
            self.chaos_mode()

    def conclude_breakdown_and_close(self) -> None:
        self.inactivity_timer.stop()
        set_collapse_pending(True)

        self.is_angry = False
        self.phrase_label.setText("FINE.")

        cut_sound_index = random.randint(1, 5)
        Player.ui_player.play_sound(f".vault/NOK/Cut{cut_sound_index}", speed = 1.0)

        if not self.enable_close_animation:
            self.really_close()
            return

        Player.ui_player.play_sound("App/QuitClose")
        self.player.set_passes(mix = 0.0, duration_ms = 400)

        if not self.animations_active or not self.animations_enabled:
            self.really_close()
            return

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 1.6)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.ease_out_quart
        )

        self.opacity_background_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 0.0)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.linear
        )

        self.opacity_content_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 0.0)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.linear,
            finished        = self.really_close
        )

    def open_error_window(self, title: str, text: str) -> None:
        window = ErrorWindow(title, text, title, dialog = False)
        self.error_windows.append(window)
        window.show()

    def execute_final_collapse_show(self) -> None:
        cut_sound_index = random.randint(1, 5)

        Player.ui_player.play_sound(f".vault/NOK/Cut{cut_sound_index}", speed = 1.0)
        Player.ui_player.play_sound(".vault/NOK/Cut6", speed = 1.0)

        self.player.set_speed(0.01, duration_ms = 3600)
        self.player.set_passes([40], q = 1.0, mix = 1.0, duration_ms = 3200)

        self.title_label.setText("near")

        for i in range(random.randint(5, 10)):
            title       = "".join(random.choices(string.ascii_letters, k = 8))
            description = random.choice(ERROR_WINDOWS)
            timeout     = i * 180

            QTimer.singleShot(
                timeout,
                lambda t = title, d = description: self.open_error_window(t, d)
            )

        if self.animations_active and self.animations_enabled:
            self.rotation_z_property.play_curve(
                keyframes                  = [(0.0, 0.0), (1.0, -2000.0)],
                duration_ms                = 1500,
                easing_function            = LoomEngine.Easing.linear,
                multiply_duration_by_speed = False
            )

            self.rotation_y_property.play_curve(
                keyframes                  = [(0.0, 0.0), (1.0, -2000.0)],
                duration_ms                = 1500,
                easing_function            = LoomEngine.Easing.linear,
                multiply_duration_by_speed = False
            )

            self.rotation_x_property.play_curve(
                keyframes                  = [(0.0, 0.0), (1.0, -2000.0)],
                duration_ms                = 1500,
                easing_function            = LoomEngine.Easing.linear,
                multiply_duration_by_speed = False
            )

            QTimer.singleShot(1500, self.kill_application)

        else:
            QTimer.singleShot(1600, self.kill_application)

    def on_quit(self) -> None:
        if self.is_angry or self.is_collapsing:
            self.request_close()
            return

        delay = 0

        if self.phrase.on_quit_action:
            delay = self.phrase.on_quit_action(self)

        if delay > 0:
            QTimer.singleShot(delay, self.on_ok)

        else:
            self.on_ok()

    def on_back(self) -> None:
        if self.is_angry or self.is_collapsing:
            self.request_close()
            return

        delay = 0
        
        if self.phrase.on_back_action:
            delay = self.phrase.on_back_action(self)

        if delay > 0:
            QTimer.singleShot(delay, self.on_cancel)

        else:
            self.on_cancel()

    def open_window(self) -> None:
        if self.is_collapsing:
            self.execute_final_collapse_show()
            return

        Player.ui_player.play_sound("App/QuitOpen")

        if self.is_angry:
            self.start_shake()
            self.set_shake_frequency(35)
            self.set_shake_deviation(5.0)
            self.inactivity_timer.start(5000)

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
        if self.is_collapsing:
            return

        if self.is_angry:
            self.angry_attempts_left -= 1
            self.angry_attempts      += 1

            if self.angry_attempts_left > 0:
                self.is_closing = False
                self.handle_angry_attempt()
                return

            self.conclude_breakdown_and_close()
            return

        if not self.enable_close_animation:
            return

        Player.ui_player.play_sound("App/QuitClose")

        self.player.set_passes(mix = 0.0, duration_ms = 400)

        if not self.animations_active or not self.animations_enabled:
            self.really_close()
            return

        self.scale_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 1.6)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.ease_out_quart
        )

        self.opacity_background_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 0.0)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.linear
        )

        self.opacity_content_property.play_curve(
            keyframes       = [(0.0, 1.0), (1.0, 0.0)],
            duration_ms     = 400,
            easing_function = LoomEngine.Easing.linear,
            finished        = self.really_close
        )