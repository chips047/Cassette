import time
import platform

from PyQt6.QtCore import QTimer
from PyQt6.QtGui  import QCloseEvent

from PyQt6.QtWidgets import (
    QWidget,
    QSizePolicy
)

from System.Common   import Constants
from System.Services import Player

from System.Interface import (
    Timing,
    Widgets
)

from System.Interface.Windows import FloatingWindowGPU

# Tutorial

class Tutorial(FloatingWindowGPU):
    def __init__(
            self,
            path:       str,
            conductor:  object | None = None,
            parent:     QWidget | None = None
        ) -> None:
        self.conductor  = conductor
        self.audio_path = path
        self.player     = Player.player

        super().__init__("Tutorial", parent = parent, enable_audioplayer_effects = False)

        self.stage                  = 0
        self.audio_enabled          = False
        self.audio_wind_down_sent   = False

        self.active_signal          = None
        self.active_signal_slot     = None
        self.play_pause_pause_slot  = None
        self.feedback_connections   = []
        self.loop_watchdog          = None

        self.progress_connections = []
        self.progress_steps       = {}
        self.progress_total       = 0.0

        self.progress_speed_current = 0.0
        self.progress_speed_target  = 0.0

        self.playhead_progress_last = None

        self.active_cancel_hint_signal = None
        self.active_cancel_hint_slot   = None

        self.driving_speed_until     = 0.0
        self.user_took_speed_control = False
        self.user_baseline_speed     = 1.0

        self.build_pages()
        self.initialize_ui()
        self.initialize_audio()
        self.setup_feedback_audio()
        self.set_bpm_peak_size(1.02)

        self.player.speed_changed.connect(self.on_external_speed_change)

        if self.conductor is not None:
            self.conductor.speed_control_used.connect(self.on_speed_control_used)
            self.conductor.destroyed.connect(self.on_conductor_destroyed)

        self.make_page()
        self.arm_current_stage()

    # Pages

    def build_pages(self) -> None:
        self.pages = [
            {
                "label":      "Welcome to Cassette",
                "text":       "Get ready. We'll learn everything hands - on.",
                "keep_focus": True
            },
            {
                "label": "Play / Pause",
                "text":  "Press `Space` to play the track.",
                "wait":  {"kind": "play_pause"}
            },
            {
                "label": "Placing a glyph",
                "text":  "Press `1, 2, 3, 4, 5, 6, 7, 8, 9, 0` or `Minus` to place a glyph on a track.",
                "wait":  {
                    "kind":  "progress",
                    "steps": [
                        {
                            "identifier": "spawn",
                            "get":        lambda tutorial: tutorial.conductor.glyph_controller.glyph_spawned,
                            "target":     5
                        }
                    ]
                }
            },
            {
                "label":       "Duration",
                "text":        "Press `D` to open the duration editor and set a new length.",
                "bpm_peak":    1.04,
                "wait":        {
                    "kind":            "signal",
                    "get":             lambda tutorial: tutorial.conductor.glyph_controller.glyph_property_changed,
                    "predicate":       lambda key: key == "duration",
                    "cancel_hint":     "Closed it without typing anything? Press `D` again and just type a number in.",
                    "cancel_hint_key": "duration"
                }
            },
            {
                "label":    "Brightness",
                "text":     "Press `B` for the brightness editor, or nudge it with `[` / `]`.",
                "bpm_peak": 1.04,
                "wait":     {
                    "kind":  "progress",
                    "steps": [
                        {
                            "identifier": "brightness",
                            "get":        lambda tutorial: tutorial.conductor.glyph_controller.glyph_property_changed,
                            "predicate":  lambda key: key == "brightness",
                            "target":     Constants.COUNT_STAGE_TARGET
                        }
                    ],
                    "cancel_hint":     "Closed the brightness editor empty - handed? No stress - type a number, or just tap `[` / `]` instead.",
                    "cancel_hint_key": "brightness"
                }
            },
            {
                "label":        "Speed",
                "text":         "Press `S` to cycle the playback speed, or use the `button` at the top of window.",
                "bpm_peak":     1.04,
                "resume_audio": True,
                "wait":         {"kind": "speed", "target": Constants.SPEED_STAGE_TARGET}
            },
            {
                "label":        "Resize or move",
                "text":         "`Grab` the side of a glyph to resize it, or `hold` its body to move it. Try both.",
                "bpm_peak":     1.05,
                "resume_audio": False,
                "wait":         {
                    "kind":  "progress",
                    "steps": [
                        {
                            "identifier":     "move",
                            "get":            lambda tutorial: tutorial.conductor.glyph_controller.glyph_moved_or_resized,
                            "predicate":      lambda mode: mode == "move",
                            "target":         1,
                            "live_get":       lambda tutorial: tutorial.conductor.glyph_controller.glyph_drag_progress,
                            "live_predicate": lambda mode, delta_ms: mode == "move",
                            "live_metric":    lambda mode, delta_ms: delta_ms,
                            "live_scale":     Constants.DRAG_PROGRESS_TARGET_MS
                        },
                        {
                            "identifier":     "resize",
                            "get":            lambda tutorial: tutorial.conductor.glyph_controller.glyph_moved_or_resized,
                            "predicate":      lambda mode: mode in ("resize_left", "resize_right"),
                            "target":         1,
                            "live_get":       lambda tutorial: tutorial.conductor.glyph_controller.glyph_drag_progress,
                            "live_predicate": lambda mode, delta_ms: mode in ("resize_left", "resize_right"),
                            "live_metric":    lambda mode, delta_ms: delta_ms,
                            "live_scale":     Constants.DRAG_PROGRESS_TARGET_MS
                        }
                    ]
                }
            },
            {
                "label": "Keyframes",
                "text":  "Keyframes - marker points that control brightness over time. Hold `Alt` to edit glyph keyframes. `Alt + Click` to create a brightness keyframe. `Alt + Drag` to move a keyframe. `Alt + Right Click` to delete a keyframe.",
                "wait":  {
                    "kind": "signal",
                    "get":  lambda tutorial: tutorial.conductor.glyph_controller.glyph_keyframe_edited
                }
            },
            {
                "label": "Deleting a glyph",
                "text":  "Select a glyph and press `Del` or `Backspace` to delete it.",
                "wait":  {
                    "kind":  "progress",
                    "steps": [
                        {
                            "identifier": "delete",
                            "get":        lambda tutorial: tutorial.conductor.glyph_controller.glyph_deleted,
                            "target":     5
                        }
                    ]
                }
            },
            {
                "label": "Zoom",
                "text":  f"Use `{'Cmd' if platform.system() == 'Darwin' else 'Ctrl'} + Plus / Minus`, or pinch on a trackpad, to zoom the timeline.",
                "wait":  {
                    "kind":  "progress",
                    "steps": [
                        {
                            "identifier": "zoom",
                            "get":        lambda tutorial: tutorial.conductor.zoom_changed,
                            "amount":     lambda magnitude: magnitude,
                            "target":     self.zoom_stage_target()
                        }
                    ]
                }
            },
            {
                "label": "Context menu",
                "text":  "Click the `Right Mouse Button` on a glyph to open the context menu. Use this menu to create beautiful effects.",
                "wait":  {
                    "kind": "signal",
                    "get":  lambda tutorial: tutorial.conductor.context_menu_opened
                }
            },
            {
                "label": "Playhead",
                "text":  "Press on the waveform to set the playback position.",
                "wait":  {
                    "kind":  "progress",
                    "steps": [
                        {
                            "identifier": "playhead",
                            "get":        lambda tutorial: tutorial.conductor.playhead.playhead_pressed,
                            "target":     Constants.PLAYHEAD_MOVE_TARGET
                        }
                    ]
                }
            },
            {
                "label": "Scrolling",
                "text":  "Use `Wheel` to scroll horizontally, `Shift + Wheel` to scroll vertically.",
                "wait":  {
                    "kind":  "progress",
                    "steps": [
                        {
                            "identifier": "scroll",
                            "get":        lambda tutorial: tutorial.conductor.content_scrolled,
                            "amount":     lambda magnitude: magnitude,
                            "target":     Constants.SCROLL_TARGET_PX
                        }
                    ]
                }
            },
            {
                "label":        "Visualizator",
                "text":         "Drag the visualizator with the `Left Mouse Button` to move it. Scroll `Wheel` over it to resize it.",
                "resume_audio": True,
                "keep_focus":   True
            },
            {
                "label":      "Navigation",
                "text":       "Click `Eject` to go back to the main menu whenever you like.",
                "keep_focus": True
            },
            {
                "label":      "Effects - Mixing",
                "text":       "You can combine effects. Place glyphs on top of each other with different effects. Double click to expand the glyph stack.",
                "keep_focus": True
            },
            {
                "label":      "Shall we?",
                "text":       "Now, try yourself in glyphtones creation.",
                "keep_focus": True
            }
        ]

        self.max_stage = len(self.pages)

    def zoom_stage_target(self) -> float:
        zoom_step = self.conductor.wheel_controller.zoom_step

        return zoom_step * Constants.ZOOM_TARGET_MULTIPLIER

    def playhead_progress_delta(self, normalized: float) -> float:
        last                        = self.playhead_progress_last
        self.playhead_progress_last = normalized

        if last is None:
            return 0.0

        return abs(normalized - last)

    def initialize_ui(self) -> None:
        self.text_label = Widgets.DescriptionLabel("Hello.")
        self.text_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.text_label.setMinimumWidth(320)

        self.progress_bar = Widgets.TutorialProgressBar()
        self.progress_bar.setVisible(False)

        self.next_button = Widgets.NothingButton("Next?")
        self.next_button.clicked.connect(self.next_button_callback)

        self.skip_button = Widgets.ConfirmButton("Skip tutorial", "Press again to confirm")
        self.skip_button.confirmed.connect(self.skip_tutorial)

        self.content_layout.addWidget(self.text_label)
        self.content_layout.addWidget(self.progress_bar)
        self.content_layout.addWidget(self.skip_button)
        self.content_layout.addWidget(self.next_button)

    def make_page(self) -> None:
        self.return_focus_to_tutorial()

        if not (0 <= self.stage < self.max_stage):
            return

        page = self.pages[self.stage]
        self.title_label.setText(page["label"])

        text = page["text"]

        if page.get("wait"):
            text = f"{text}\n\nDo it now to continue."

        self.text_label.setText(text)
        self.next_button.setVisible(not page.get("wait"))

        QTimer.singleShot(0, self.adjustSize)

        if not page.get("keep_focus"):
            QTimer.singleShot(1500, self.return_focus_to_main_window)

    # Focus

    def return_focus_to_main_window(self) -> None:
        window = self.conductor.window()

        window.activateWindow()
        window.raise_()

    def return_focus_to_tutorial(self) -> None:
        window = self.window()

        window.activateWindow()
        window.raise_()

    # Progression

    def next_button_callback(self) -> None:
        self.advance_stage()

    def advance_stage(self) -> None:
        self.disarm_current_stage()

        self.stage += 1
        self.animation_random_rotate()

        if self.stage >= self.max_stage:
            self.finish_tutorial()
            return

        self.make_page()
        self.arm_current_stage()

        resume_audio = self.pages[self.stage].get("resume_audio")

        if resume_audio is None:
            self.play_page_transition_pulse()
            return

        if resume_audio:
            self.resume_tutorial_audio()
            return

        self.stop_tutorial_audio()

    def finish_tutorial(self) -> None:
        self.stop_tutorial_audio()
        self.on_ok()

    def skip_tutorial(self) -> None:
        self.text_label.setText("Hm, good luck.")
        self.disarm_current_stage()
        self.finish_tutorial()

    def on_action_completed(self) -> None:
        self.advance_stage()

    # Waiting

    def current_page_wait(self) -> dict | None:
        if not (0 <= self.stage < self.max_stage):
            return None

        return self.pages[self.stage].get("wait")

    def arm_current_stage(self) -> None:
        if self.conductor is None:
            return

        wait = self.current_page_wait()

        if not wait:
            return

        self.arm_dialog_cancel_hint(wait)

        if wait["kind"] == "play_pause":
            self.arm_play_pause_stage()
            return

        if wait["kind"] == "speed":
            self.arm_speed_stage(wait)
            return

        if wait["kind"] == "progress":
            self.arm_progress_stage(wait["steps"])
            return

        signal    = wait["get"](self)
        predicate = wait.get("predicate")

        def slot(*arguments: object) -> None:
            if predicate and not predicate(*arguments):
                return

            self.on_action_completed()

        signal.connect(slot)

        self.active_signal      = signal
        self.active_signal_slot = slot

    def arm_progress_stage(self, steps: list) -> None:
        self.progress_steps = {
            step["identifier"]: {
                "current":   0.0,
                "target":    float(step.get("target", 1)),
                "live_last": None
            }
            for step in steps
        }

        self.progress_total = sum(entry["target"] for entry in self.progress_steps.values())

        self.progress_bar.set_total(self.progress_total)
        self.progress_bar.set_completed(0.0)
        self.progress_bar.setVisible(True)

        self.playhead_progress_last = None

        for step in steps:
            self.arm_progress_completion_signal(step)
            self.arm_progress_live_signal(step)

    def arm_progress_completion_signal(self, step: dict) -> None:
        signal     = step["get"](self)
        predicate  = step.get("predicate")
        identifier = step["identifier"]

        default_amount  = (lambda *arguments: 0.0) if step.get("live_get") else (lambda *arguments: 1.0)
        amount_function = step.get("amount", default_amount)

        def slot(
                *arguments:      object,
                predicate:       object | None   = predicate,
                amount_function: object          = amount_function,
                identifier:      str             = identifier
            ) -> None:
            if predicate and not predicate(*arguments):
                return

            entry            = self.progress_steps[identifier]
            entry["current"] = min(entry["target"], entry["current"] + amount_function(*arguments))

            self.update_progress_display()

            if all(step_entry["current"] >= step_entry["target"] for step_entry in self.progress_steps.values()):
                self.on_action_completed()

        signal.connect(slot)
        self.progress_connections.append((signal, slot))

    def arm_progress_live_signal(self, step: dict) -> None:
        live_get = step.get("live_get")

        if live_get is None:
            return

        signal         = live_get(self)
        live_predicate = step.get("live_predicate")
        live_function  = step["live_metric"]
        live_scale     = step.get("live_scale", 1.0)
        identifier     = step["identifier"]

        def slot(
                *arguments:     object,
                live_predicate: object | None   = live_predicate,
                live_function:  object          = live_function,
                live_scale:     float           = live_scale,
                identifier:     str             = identifier
            ) -> None:
            if live_predicate and not live_predicate(*arguments):
                return

            entry     = self.progress_steps[identifier]
            raw_value = live_function(*arguments)
            last      = entry["live_last"]

            entry["live_last"] = raw_value

            if last is None:
                return

            traveled         = abs(raw_value - last) / live_scale
            entry["current"] = min(entry["target"], entry["current"] + traveled)

            self.update_progress_display()

        signal.connect(slot)
        self.progress_connections.append((signal, slot))

    def update_progress_display(self) -> None:
        self.progress_bar.set_completed(sum(entry["current"] for entry in self.progress_steps.values()))

    def arm_speed_stage(self, wait: dict) -> None:
        self.progress_speed_current = 0.0
        self.progress_speed_target  = float(wait.get("target", Constants.SPEED_STAGE_TARGET))

        self.progress_bar.set_total(self.progress_speed_target)
        self.progress_bar.set_completed(0.0)
        self.progress_bar.setVisible(True)

    def arm_dialog_cancel_hint(self, wait: dict) -> None:
        hint = wait.get("cancel_hint")

        if not hint or self.conductor is None:
            return

        expected_key = wait.get("cancel_hint_key")

        def slot(key: str) -> None:
            if expected_key and key != expected_key:
                return

            if not (0 <= self.stage < self.max_stage):
                return

            self.return_focus_to_tutorial()

            QTimer.singleShot(0, self.adjustSize)
            QTimer.singleShot(1500, self.return_focus_to_main_window)

            base_text = self.pages[self.stage]["text"]
            self.text_label.setText(f"{base_text}\n\nDo it now to continue.\n\n{hint}")

        self.conductor.dialog_cancelled.connect(slot)

        self.active_cancel_hint_signal = self.conductor.dialog_cancelled
        self.active_cancel_hint_slot   = slot

    def disarm_current_stage(self) -> None:
        if self.active_signal is not None:
            self.safe_disconnect(self.active_signal, self.active_signal_slot)

        self.active_signal      = None
        self.active_signal_slot = None

        for signal, slot in self.progress_connections:
            self.safe_disconnect(signal, slot)

        self.progress_connections = []
        self.progress_steps       = {}
        self.progress_bar.setVisible(False)

        self.progress_speed_current = 0.0
        self.progress_speed_target  = 0.0

        if self.active_cancel_hint_signal is not None:
            self.safe_disconnect(self.active_cancel_hint_signal, self.active_cancel_hint_slot)

        self.active_cancel_hint_signal = None
        self.active_cancel_hint_slot   = None

        self.disarm_play_pause_watch()

    @staticmethod
    def safe_disconnect(
            signal: object,
            slot:   object
        ) -> None:
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass

    # Playback

    def arm_play_pause_stage(self) -> None:
        self.prepare_playback_for_pickup()

        def slot(started: bool) -> None:
            if not started:
                return

            self.safe_disconnect(self.player.playback_state_changed, slot)

            self.active_signal      = None
            self.active_signal_slot = None

            self.on_play_pause_started()

        self.player.playback_state_changed.connect(slot)

        self.active_signal      = self.player.playback_state_changed
        self.active_signal_slot = slot

    def prepare_playback_for_pickup(self) -> None:
        if not self.audio_enabled or not self.player.is_playing:
            return

        self.animate_speed(0.0, Constants.PLAY_PAUSE_STOP_RAMP_MS, on_finish = self.player.stop)

    def on_play_pause_started(self) -> None:
        self.return_focus_to_tutorial()
        self.text_label.setText(Constants.PLAY_PAUSE_GOOD_TEXT)

        if not self.audio_enabled:
            QTimer.singleShot(Constants.PLAY_PAUSE_TEXT_HOLD_MS, self.on_action_completed)
            return

        baseline = self.target_speed_baseline()

        def early_pause_slot(started: bool) -> None:
            if started:
                return

            self.disarm_play_pause_watch()

            self.text_label.setText(Constants.PLAY_PAUSE_QUICK_TEXT)
            self.animate_speed(baseline, Constants.PAGE_PULSE_UP_MS)

            QTimer.singleShot(Constants.PLAY_PAUSE_TEXT_HOLD_MS, self.on_action_completed)

        self.player.playback_state_changed.connect(early_pause_slot)
        self.play_pause_pause_slot = early_pause_slot

        def wind_down() -> None:
            if self.play_pause_pause_slot is not early_pause_slot:
                return

            self.disarm_play_pause_watch()
            self.animate_speed(0.0, Constants.PLAY_PAUSE_STOP_RAMP_MS, on_finish = self.finish_play_pause_stage)

        def hold_then_wind_down() -> None:
            if self.play_pause_pause_slot is not early_pause_slot:
                return

            QTimer.singleShot(Constants.PLAY_PAUSE_HOLD_MS, wind_down)

        self.animate_speed(baseline, Constants.PLAY_PAUSE_ACCEL_RAMP_MS, on_finish = hold_then_wind_down)

    def finish_play_pause_stage(self) -> None:
        self.player.stop()
        self.on_action_completed()

    def disarm_play_pause_watch(self) -> None:
        if self.play_pause_pause_slot is None:
            return

        self.safe_disconnect(self.player.playback_state_changed, self.play_pause_pause_slot)
        self.play_pause_pause_slot = None

    def on_external_speed_change(self, new_speed: float) -> None:
        if time.monotonic() < self.driving_speed_until:
            return

        self.user_took_speed_control = True
        self.user_baseline_speed     = new_speed

    def on_speed_control_used(self) -> None:
        wait = self.current_page_wait()

        if not wait or wait["kind"] != "speed":
            return

        self.progress_speed_current = min(self.progress_speed_target, self.progress_speed_current + 1.0)
        self.progress_bar.set_completed(self.progress_speed_current)

        if self.progress_speed_current >= self.progress_speed_target:
            self.on_action_completed()

    def target_speed_baseline(self) -> float:
        if self.user_took_speed_control:
            return self.user_baseline_speed

        return Constants.BASELINE_SPEED

    def animate_speed(
            self,
            value:       float,
            duration_ms: int           = 0,
            on_finish:   object | None = None,
            **keywords:  object
        ) -> None:
        guard_until              = time.monotonic() + (duration_ms / 1000.0) + 0.05
        self.driving_speed_until = max(self.driving_speed_until, guard_until)

        self.player.set_speed(value, duration_ms, on_finish = on_finish, **keywords)

    # Audio

    def initialize_audio(self) -> None:
        self.player.load_audio(self.audio_path)

        self.audio_enabled = self.player.duration_ms >= Constants.MIN_AUDIO_MS

        if not self.audio_enabled:
            return

        self.animate_speed(0.0)

        self.player.play()
        self.player.set_passes([Constants.UNDERWATER_FREQUENCY_HZ], q = Constants.UNDERWATER_Q, mix = 1.0)

        self.animate_speed(self.target_speed_baseline(), Constants.INTRO_RAMP_MS)
        self.player.set_passes([Constants.UNDERWATER_FREQUENCY_HZ], mix = 0.0, duration_ms = Constants.INTRO_RAMP_MS)

        self.loop_watchdog = Timing.Timer(Constants.LOOP_WATCHDOG_MS, self.check_audio_loop, parent = self)
        self.loop_watchdog.start()

    def check_audio_loop(self) -> None:
        if not self.player.is_playing:
            return

        remaining = self.player.duration_ms - self.player.get_position()

        if remaining > Constants.LOOP_GUARD_MS:
            return

        self.player.set_volume(0.0, 120)
        QTimer.singleShot(120, self.restart_loop)

    def restart_loop(self) -> None:
        self.player.play(0.0)
        self.player.set_volume(1.0, 220)

    def release_stage_effects(self) -> None:
        if not self.audio_enabled:
            return

        page = self.pages[self.stage] if 0 <= self.stage < self.max_stage else {}
        wait = page.get("wait")
        peak = page.get("bpm_peak")

        if peak:
            self.set_bpm_peak_size(peak)

        if wait and wait["kind"] == "play_pause":
            return

        baseline = self.target_speed_baseline()

        self.animate_speed(baseline, Constants.RELEASE_RAMP_MS)

        filter_mix = 0.35 if wait else 0.0

        self.player.set_passes(
            [Constants.UNDERWATER_FREQUENCY_HZ],
            q           = Constants.UNDERWATER_Q,
            mix         = filter_mix,
            duration_ms = Constants.RELEASE_RAMP_MS
        )

    def resume_tutorial_audio(self) -> None:
        if not self.audio_enabled:
            return

        page  = self.pages[self.stage] if 0 <= self.stage < self.max_stage else {}
        peak  = page.get("bpm_peak", 1.02)
        speed = self.target_speed_baseline()

        self.set_bpm_peak_size(peak)

        resume_position_ms = self.conductor.get_playhead_position_ms()

        self.animate_speed(0.0)
        self.player.play(resume_position_ms)

        self.player.set_volume(0.0)
        self.player.set_volume(1.0, Constants.RESUME_AUDIO_RAMP_MS)

        self.animate_speed(speed, Constants.RESUME_AUDIO_RAMP_MS)

        self.player.set_passes(
            [Constants.UNDERWATER_FREQUENCY_HZ],
            mix         = 0.0,
            duration_ms = Constants.RESUME_AUDIO_RAMP_MS
        )

    def stop_tutorial_audio(self) -> None:
        if not self.audio_enabled or self.audio_wind_down_sent:
            return

        self.audio_wind_down_sent = True

        baseline = self.target_speed_baseline()

        def finish_stop() -> None:
            self.player.stop()
            self.player.set_speed(baseline, 0)

        self.animate_speed(0.0, Constants.PLAY_PAUSE_STOP_RAMP_MS, on_finish = finish_stop)

    def play_page_transition_pulse(self) -> None:
        if not self.audio_enabled:
            return

        wait = self.current_page_wait()

        if wait and wait["kind"] == "play_pause":
            return

        baseline = self.target_speed_baseline()

        def pulse_up() -> None:
            self.animate_speed(baseline, Constants.PAGE_PULSE_UP_MS, on_finish = self.release_stage_effects)

        self.animate_speed(Constants.PAGE_PULSE_SPEED, Constants.PAGE_PULSE_DOWN_MS, on_finish = pulse_up)

    def setup_feedback_audio(self) -> None:
        if not self.audio_enabled:
            return

        glyph_controller = self.conductor.glyph_controller

        for signal in (
            glyph_controller.glyph_spawned,
            glyph_controller.glyph_deleted,
            glyph_controller.glyph_moved_or_resized
        ):
            signal.connect(self.underwater_blip)
            self.feedback_connections.append(signal)

    def disconnect_feedback_audio(self) -> None:
        for signal in self.feedback_connections:
            self.safe_disconnect(signal, self.underwater_blip)

        self.feedback_connections = []

    def underwater_blip(self, *arguments: object) -> None:
        if not self.audio_enabled:
            return

        self.player.set_passes(
            [Constants.UNDERWATER_FREQUENCY_HZ],
            q           = Constants.UNDERWATER_Q,
            mix         = 1.0,
            duration_ms = 0
        )

        self.player.set_passes(
            [Constants.UNDERWATER_FREQUENCY_HZ],
            q           = Constants.UNDERWATER_Q,
            mix         = 0.0,
            duration_ms = Constants.UNDERWATER_BLIP_MS
        )

    # Cleanup

    def on_conductor_destroyed(self, *arguments: object) -> None:
        self.teardown()
        self.close()

    def teardown(self) -> None:
        self.disarm_current_stage()
        self.disconnect_feedback_audio()
        self.safe_disconnect(self.player.speed_changed, self.on_external_speed_change)

        if self.conductor is not None:
            self.safe_disconnect(self.conductor.destroyed, self.on_conductor_destroyed)
            self.safe_disconnect(self.conductor.speed_control_used, self.on_speed_control_used)

        self.conductor = None

        if self.loop_watchdog is not None:
            self.loop_watchdog.stop()

        self.stop_tutorial_audio()

    def eject_close(self) -> None:
        self.text_label.setText("Oh well, see ya.")
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        Constants.current_settings.set_value("tutorial_shown", True)
        self.teardown()
        super().closeEvent(event)