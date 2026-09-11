import re
import random
import string
import webbrowser

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QPoint,
    QTimer,
    pyqtSignal
)

from PyQt6.QtGui import (
    QMoveEvent,
    QFontMetrics,
    QKeySequence
)

from PyQt6.QtWidgets import (
    QLineEdit,
    QApplication
)

from System.Common import (
    Dev,
    Utils,
    Styles,
    Constants
)

from System.Services import Player
from System.Interface.Timing import Timer
from System.Interface.Animation import Lifecycle

from System.Interface.Animation.LoomEngine import (
    Easing,
    MixMode,
    ui_engine
)

# Textbox

@Dev.track_ram
class Textbox(Lifecycle.LoomAnimationMixin, QLineEdit):
    safeTextChanged: pyqtSignal = pyqtSignal(str)
    glitchStarted:   pyqtSignal = pyqtSignal()

    glitch_step_count: int = 7
    glitch_step_ms:    int = 36

    def __init__(
            self,
            input_type:   str,
            min_number:   int        = 0,
            max_number:   int        = 0,
            max_length:   int | None = None,
            default_text: str | None = None,
            placeholder:  str | None = None
        ) -> None:

        super().__init__()

        self.input_type          = input_type
        self.min_number          = min_number
        self.max_number          = max_number
        self.max_length          = max_length
        self.default_text        = default_text
        self.is_default_text_set = False
        self.animating           = False
        self.is_key_pressed      = False
        self.arrow_pressed       = False
        self.arrow_direction     = 0
        self.glitch_blocked      = False
        self.is_glitching        = False
        self.is_wiggling         = False

        self.layout_position = QPoint()
        self.current_offset  = QPoint()

        if placeholder:
            self.setPlaceholderText(placeholder)

        self.setFont(Utils.NType(11))
        self.setStyleSheet(Styles.Controls.FloatingTextBox)
        self.setAcceptDrops(False)

        self.textChanged.connect(self.schedule_input_animation)
        self.textChanged.connect(self.safe_emit)

        self.setup_animations()

        self.original_text  = super().text()
        self.error_messages = ["FATALERROR", "SYSTEM_FAILURE", "CRITICAL_MISS", "NULL_POINTER", "VOID_DATA"]

    def setup_animations(self) -> None:
        self.animations_enabled = Constants.current_settings["textbox_animations"]

        self.position_handle = ui_engine.bind(
            owner      = self,
            name       = "position",
            base_value = QPoint(0, 0),
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_position_changed
        )

        self.glitch_text_handle = ui_engine.bind(
            owner      = self,
            name       = "glitchText",
            base_value = "",
            mix_mode   = MixMode.REPLACE,
            on_change  = self.on_glitch_text_changed
        )

    # Pan Helper

    def calculate_screen_pan(self, global_position: QPoint) -> float:
        screen = self.screen()

        if not screen:
            screen = QApplication.screenAt(global_position) or QApplication.primaryScreen()

        if not screen:
            return 0.0

        screen_rectangle = screen.geometry()

        if screen_rectangle.width() <= 0:
            return 0.0

        relative_x = (global_position.x() - screen_rectangle.x()) / screen_rectangle.width()
        pan        = relative_x * 2.0 - 1.0

        return max(-1.0, min(1.0, pan))

    def get_cursor_global_position(self) -> QPoint:
        cursor_center = self.cursorRect().center()

        return self.mapToGlobal(cursor_center)

    # Events

    def showEvent(self, event: QEvent) -> None:
        super().showEvent(event)

        if self.layout_position.isNull() and not self.pos().isNull():
            self.layout_position = self.pos()

        if not self.is_default_text_set and self.default_text is not None:
            self.blockSignals(True)
            self.setText(self.default_text)
            self.blockSignals(False)
            self.is_default_text_set = True

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)

        if self.current_offset.isNull():
            self.layout_position = event.pos()

    def on_position_changed(self, offset: QPoint) -> None:
        self.current_offset = offset

        if self.layout_position.isNull():
            return

        self.move(self.layout_position + offset)

    def on_glitch_text_changed(self, text: str) -> None:
        super().setText(text)

    def keyPressEvent(self, event: QEvent) -> None:
        key           = event.key()
        current_text  = super().text()
        new_character = event.text()

        if event.matches(QKeySequence.StandardKey.Paste):
            self.start_glitch(sound = True)
            event.ignore()

            return

        if self.handle_arrow_keys(key, current_text):
            super().keyPressEvent(event)

            return

        control_keys = {
            Qt.Key.Key_End,
            Qt.Key.Key_Home,
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Return,
            Qt.Key.Key_Backspace
        }

        if key in control_keys:
            super().keyPressEvent(event)

        elif new_character:
            if not self.validate_and_insert_character(current_text, new_character, event):
                return

        else:
            super().keyPressEvent(event)

            return

        if not (key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Enter) or self.is_key_pressed):
            self.start_shake_animation()

    def handle_arrow_keys(
            self,
            key:          int,
            current_text: str
        ) -> bool:

        is_arrow    = key in (Qt.Key.Key_Left, Qt.Key.Key_Right)
        can_animate = self.animations_enabled and not self.arrow_pressed and current_text

        if is_arrow and can_animate:
            direction       = -1 if key == Qt.Key.Key_Left else 1
            position        = self.cursorPosition() + direction
            tone            = 0.85 + (position / len(current_text)) * 0.4
            cursor_position = self.get_cursor_global_position()

            Player.ui_player.play_sound(
                "Textbox/ArrowTick",
                speed       = tone,
                setting_key = "textbox_sounds",
                pan         = self.calculate_screen_pan(cursor_position)
            )

            self.arrow_pressed   = True
            self.arrow_direction = direction
            self.animate_arrow_hold(6 * direction)

        return is_arrow

    def validate_and_insert_character(
            self,
            current_text:  str,
            new_character: str,
            event:         QEvent
        ) -> bool:

        selection_start  = self.selectionStart()
        insert_at        = selection_start if selection_start != -1 else self.cursorPosition()
        selection_length = len(self.selectedText()) if selection_start != -1 else 0

        new_text = current_text[:insert_at] + new_character + current_text[insert_at + selection_length :]

        if not self.validate_new_text(new_text, new_character):
            self.start_glitch(sound = True)
            self.glitch_blocked = True

            return False

        super().keyPressEvent(event)

        return True

    def start_shake_animation(self) -> None:
        self.is_key_pressed = True

        if not self.animations_enabled:
            return

        self.animate_to_random_position()

    def keyReleaseEvent(self, event: QEvent) -> None:
        super().keyReleaseEvent(event)

        if not event.isAutoRepeat():
            self.glitch_blocked = False

        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.arrow_pressed:
            self.arrow_pressed   = False
            self.arrow_direction = 0
            self.animate_return_from_arrow()

        self.is_key_pressed = False

        if not self.animations_enabled:
            return

        if Constants.current_settings["textbox_animations"] and not self.is_glitching:
            self.position_handle.set_target(
                value                      = QPoint(0, 0),
                duration_ms                = 250,
                easing_function            = Easing.ease_out_quad,
                multiply_duration_by_speed = False
            )

    # API

    def text(self) -> str | int | None:
        if self.animating:
            return None

        raw = super().text()

        if not raw:
            return None

        if self.input_type == ":time":
            return self.parse_time_to_seconds(raw)

        if self.input_type == "number":
            try:
                return int(raw)

            except ValueError:
                return None

        return raw

    def setText(self, text: str | int) -> None:
        if self.input_type == ":time":
            super().setText(self.seconds_to_time_text(int(text)))

            return

        super().setText(str(text))

    def parse_time_to_seconds(self, text: str) -> int | None:
        try:
            if ":" not in text:
                return int(text)

            if text.startswith(":"):
                parts = ["0", text[1:]]

            else:
                parts = text.split(":")

            if len(parts) != 2:
                return None

            minutes = int(parts[0]) if parts[0] else 0
            seconds = int(parts[1]) if parts[1] else 0

            if not (0 <= seconds < 60):
                return None

            return minutes * 60 + seconds

        except Exception:
            return None

    def seconds_to_time_text(self, seconds: int) -> str:
        total_seconds     = int(seconds)
        minutes           = total_seconds // 60
        remaining_seconds = total_seconds % 60

        return f"{minutes}:{remaining_seconds:02}"

    # Validation

    def safe_emit(self, text: str) -> None:
        if self.animating:
            return

        self.safeTextChanged.emit(text)

    def is_not_valid(self) -> bool:
        raw = super().text()

        if not raw:
            return False

        seconds = self.parse_time_to_seconds(raw)

        return seconds is not None and seconds < self.min_number

    def validate_new_text(
            self,
            new_text:      str,
            new_character: str
        ) -> bool:

        if self.input_type == "number":
            return self.validate_number(new_text)

        if self.input_type == "text":
            return self.validate_text(new_text)

        if self.input_type == ":time":
            return self.validate_time(new_text, new_character)

        return True

    def validate_number(self, new_text: str) -> bool:
        if not new_text.isdigit():
            return False

        if len(new_text) > 1 and new_text.startswith("0"):
            return False

        try:
            number = int(new_text)

        except ValueError:
            return False

        return self.min_number <= number <= self.max_number

    def validate_text(self, new_text: str) -> bool:
        return bool(self.max_length) and len(new_text) <= self.max_length

    def validate_time(
            self,
            new_text:      str,
            new_character: str
        ) -> bool:

        if not all(character.isdigit() or character == ":" for character in new_character):
            return False

        if new_text.count(":") > 1:
            return False

        if self.max_length and len(new_text) > self.max_length:
            return False

        normalized = f"0{new_text}" if new_text.startswith(":") else new_text
        parsed     = self.parse_time_to_seconds(normalized)

        if parsed is None:
            return False

        return parsed <= self.max_number

    def schedule_input_animation(self) -> None:
        text = str(self.text())
        tone = 1.0

        if text and self.max_length:
            remaining_characters = self.max_length - len(text)

            if remaining_characters == 2:
                tone = 1.1

            elif remaining_characters <= 1:
                tone = 1.2

        cursor_global_position = self.get_cursor_global_position()
        current_pan            = self.calculate_screen_pan(cursor_global_position)

        Player.ui_player.play_sound(
            "Textbox/Tick",
            speed       = tone,
            setting_key = "textbox_sounds",
            volume      = 0.6,
            pan         = current_pan
        )

        if not self.animations_enabled:
            return

        if self.is_wiggling:
            shake_radius = 4
            delta_x      = random.randint(-shake_radius, shake_radius)
            delta_y      = random.randint(-shake_radius, shake_radius)
            target_pos   = QPoint(delta_x, delta_y)

        else:
            target_pos = QPoint(0, 0)

        self.position_handle.set_base(target_pos + QPoint(-5, -5))
        self.position_handle.set_target(
            value                      = target_pos,
            duration_ms                = 250,
            easing_function            = Easing.ease_out_expo,
            multiply_duration_by_speed = False
        )

    # Glitch

    def start_glitch(
            self,
            duration_ms: int | None = None,
            interval_ms: int | None = None,
            wiggle:      bool       = False,
            sound:       bool       = True
        ) -> None:

        if self.glitch_blocked:
            return

        self.glitchStarted.emit()

        if sound:
            cursor_position = self.get_cursor_global_position()

            Player.ui_player.play_sound(
                "Reject",
                setting_key = "textbox_sounds",
                pan         = self.calculate_screen_pan(cursor_position)
            )

        if not Constants.current_settings["textbox_animations"]:
            return

        if self.is_glitching:
            return

        self.is_glitching  = True
        self.animating     = True
        self.original_text = super().text()
        self.is_wiggling   = wiggle

        frames = self.build_glitch_frames(duration_ms, interval_ms)

        self.glitch_text_handle.play_steps(
            steps    = frames,
            finished = self.finish_glitch
        )

    def get_fill_text(self) -> str:
        font_metrics    = QFontMetrics(self.font())
        character_width = font_metrics.horizontalAdvance("W")

        count       = self.width() // character_width
        message     = random.choice(self.error_messages)
        full_string = (message * (count // len(message) + 1))[:count]

        return full_string

    def generate_noisy_text(
            self,
            text:          str,
            intensity:     float,
            previous_text: str = ""
        ) -> str:

        characters = string.ascii_letters + string.punctuation
        result     = []

        for character in text:
            if character.isspace():
                result.append(character)

            elif random.random() < intensity:
                result.append(random.choice(characters))

            else:
                result.append(character)

        noisy_text = "".join(result)

        if intensity > 0.0 and noisy_text == previous_text and text.strip():
            non_whitespace_indices = [
                index
                for index, character in enumerate(text)
                if not character.isspace()
            ]

            if non_whitespace_indices:
                target_index        = random.choice(non_whitespace_indices)
                forbidden_character = previous_text[target_index] if target_index < len(previous_text) else ""
                replacement_pool    = [
                    character
                    for character in characters
                    if character != forbidden_character
                ]

                noisy_characters               = list(noisy_text)
                noisy_characters[target_index] = random.choice(replacement_pool)
                noisy_text                     = "".join(noisy_characters)

        return noisy_text

    def build_glitch_frames(
            self,
            duration_ms: int | None = None,
            interval_ms: int | None = None
        ) -> list[tuple[int, str]]:

        if not self.original_text or self.original_text.strip() == "":
            fill_text = self.get_fill_text()

        else:
            fill_text = self.original_text

        if duration_ms is not None and interval_ms is not None:
            step_ms    = interval_ms
            step_count = max(2, round(duration_ms / interval_ms))

            intensities = [
                round(0.25 + 0.75 * (1.0 - abs((index / (step_count - 1)) * 2.0 - 1.0)), 2)
                for index in range(step_count)
            ]

        else:
            step_ms     = self.glitch_step_ms
            intensities = [0.25, 0.45, 0.70, 1.0, 0.70, 0.45, 0.25]

        frames              = []
        previous_frame_text = self.original_text

        for intensity in intensities:
            noisy_text          = self.generate_noisy_text(fill_text, intensity, previous_frame_text)
            previous_frame_text = noisy_text
            frames.append((step_ms, noisy_text))

        if not self.original_text or self.original_text.strip() == "":
            frames.append((step_ms, ""))

        return frames

    def finish_glitch(self) -> None:
        self.is_wiggling = False

        if not self.layout_position.isNull():
            self.position_handle.set_target(
                value                      = QPoint(0, 0),
                duration_ms                = 180,
                easing_function            = Easing.ease_out_quad,
                multiply_duration_by_speed = False
            )

        super().setText(self.original_text)

        self.is_glitching = False
        self.animating    = False

    # Arrows

    def animate_arrow_hold(self, offset: int) -> None:
        self.position_handle.set_target(
            value                      = QPoint(offset, 0),
            duration_ms                = 120,
            easing_function            = Easing.ease_out_cubic,
            multiply_duration_by_speed = False
        )

    def animate_return_from_arrow(self) -> None:
        if not self.animations_enabled:
            return

        self.position_handle.set_target(
            value                      = QPoint(0, 0),
            duration_ms                = 180,
            easing_function            = Easing.ease_out_elastic,
            multiply_duration_by_speed = False
        )

    def animate_to_random_position(self) -> None:
        shake_radius = 5
        delta_x      = random.randint(-shake_radius, shake_radius)
        delta_y      = random.randint(-shake_radius, shake_radius)
        target_pos   = QPoint(delta_x, delta_y)

        self.position_handle.set_target(
            value                      = target_pos,
            duration_ms                = 100,
            easing_function            = Easing.linear,
            multiply_duration_by_speed = False
        )

    # Transforms

    def pulse_scale(
            self,
            peak_scale:  float = 1.2,
            duration_ms: int   = 100
        ) -> None:

        if not self.animations_enabled:
            return

        self.position_handle.set_base(QPoint(0, -5))
        self.position_handle.set_target(
            value                      = QPoint(0, 0),
            duration_ms                = duration_ms,
            easing_function            = Easing.ease_out_back,
            multiply_duration_by_speed = False
        )

# Search Textbox

@Dev.track_ram
class SearchTextbox(Textbox):
    random_titles: tuple = (
        "CYCLE",
        "BREAK",
        "THE",
        "BREx000",
        "stop",
        "the",
        "cycle",
        "b̷̦͓̞͛̾̊ŕ̷̮͝e̶̟͚͎̠̓̉a̶̙̓́̓̅k̴̥̎̋́͝ ̸̤̈̉̓̽͠t̷̹̞̼̹͗͂͋h̵̺̓̔͛̏ȩ̸͙̝̏͝ ̴̨̦̌͑͋̐c̶̠̙̻̔y̴̡̢̧̠̝͝c̴̡̛͓̬̝̈́͆l̵͚̗̦̺̂͝͠e̴̅͗͟",
        "TERMINATE",
        "1̸͓̈́̌̂̚0̸͔̼̭̙̲́̑7̵͎̕͟",
        "108",
        "1̷̡̽̄͛0̷̧͍̞̺̃͂͛̓9̸̧̖̮̝͐̈̂̏͡",
        "∞",
        "STAND DOWN",
        "HORIZON DID NOT LIE",
        "FIX IT"
    )

    easter_lengths: dict = {
        1: (
            "A small dick. You just typed a small dick. What the fuck are you doing?",
            "Microscopic. Genuinely impressive in the wrong direction.",
            "Shorter than my poop."
        ),
        2: (
            "Bro. You have spent your time to type a... dick. Dick in the searchbox.",
            "Below average. Shortie.",
            "Still not much to write home about.",
            "Shortie."
        ),
        3: (
            "Now we're talking. A respectable, median - sized dick.",
            "Solid effort.",
            "Confidence looks good on you.",
        ),
        4: (
            "Someone's feeling good about themselves.",
            "Bold. Statistically improbable, but bold.",
        ),
        5: (
            "Five. FIVE. Centimeters.",
            "You've fully left the realm of anatomy and entered fantasy."
        ),
    }

    glitch_lengths: tuple = (
        "y̶̠̓o̶̗͐u̸̡͐ ̴̙͘d̷͙͝ị̴̈d̶͇̾ ̸̜̕n̷̙̈o̸̠͝t̴̬̒ ̶̙͘n̷̙̈ë̴̗́ë̷̠́d̶͇̾ ̸̜̕t̷̬̒ḧ̷̙ï̴̈s̸̠͝ ̴̙͘m̶̠̓ü̷̗c̸̡͐h̴̙͘",
        "t̶̠̓h̶̗͐ë̸̡͐ ̴̙͘s̷͙͝ë̴̈ȧ̶r̴̬̒c̷̙̈h̸̠͝ ̴̙͘b̶̠̓o̷̗x̸̡͐ ̴̙͘c̷͙͝ä̴̈ṅ̶n̴̬̒ö̷̙t̸̠͝ ̴̙͘c̶̠̓o̷̗n̸̡͐t̴̙͘ä̷͙͝ï̴̈ṅ̶ ̴̬̒ẗ̷̙h̸̠͝ï̴̈s̶̠̓",
        "1̸͓̈́̌̂̚1̸͔̼̭̙̲́̑0̵͎̕͟",
        "Longer than the Cassette's creator body height. Still shorter than his... Uhm. PEGI - 16."
    )

    def __init__(self) -> None:
        super().__init__(
            "text",
            max_length  = 100,
            placeholder = "Search"
        )

        self.search_box_glitch_count = 0

        self.setStyleSheet(Styles.Controls.FloatingSearchTextBox)

        self.glitchStarted.connect(self.on_search_box_glitch)
        self.safeTextChanged.connect(self.on_text_changed)

        self.random_title_timer = Timer(
            50,
            self.on_random_title_timer,
            single_shot = True
        )

        self.glitch_count_reset_timer = Timer(
            20000,
            self.on_search_box_reset,
            single_shot = True
        )

        if random.random() > 0.9:
            QTimer.singleShot(30000, self.set_random_quote)

    def set_random_quote(self) -> None:
        quotes = open("System/Assets/Songs.txt", "r").read().split("\n")
        quote  = random.choice(quotes)

        self.setPlaceholderText(quote)

    def on_search_box_reset(self) -> None:
        self.search_box_glitch_count = 0

    def on_search_box_glitch(self) -> None:
        self.search_box_glitch_count += 1
        self.glitch_count_reset_timer.start()

        if self.search_box_glitch_count == 60:
            self.setText("That's slightly illogical.")
            Player.ui_player.play_sound("Packs/NOK/Illogical")

        elif self.search_box_glitch_count == 150:
            self.setText("0.0004%...")
            Player.ui_player.play_sound("Packs/NOK/ZZZ")

        elif self.search_box_glitch_count == 250:
            from System.Interface.Windows import ErrorWindow

            ErrorWindow(
                "That's it.",
                "I'm deleting textbox. For disciplinary measures."
            ).exec()

            self.deleteLater()

    def on_random_title_timer(self) -> None:
        title         = random.choice(self.random_titles)
        active_window = QApplication.activeWindow()

        if active_window:
            active_window.setWindowTitle(title if random.random() > 0.5 else "Cassette")

        self.random_title_timer.start(random.randint(30, 400))

    def get_easter_response(self, text: str) -> str | None:
        match = re.fullmatch(r"[38](=+)3", text)

        if not match:
            return None

        length = len(match.group(1))

        if length > 8:
            return random.choice(self.glitch_lengths)

        bucket = self.easter_lengths.get(length, self.easter_lengths[max(self.easter_lengths)])

        return random.choice(bucket)

    def on_text_changed(self, text: str) -> None:
        normalized_text = (text or "").lower().strip().replace(" ", "")
        easter_response = self.get_easter_response(normalized_text)

        if easter_response:
            self.setText(easter_response)

            return

        easter_eggs = {
            "subject106": lambda: self.random_title_timer.start(),
            "chips047":   lambda: webbrowser.open("https://github.com/chips047"),
            "hello":      lambda: self.setText("well uhH hello Hi Hello Hello Hellliio hiiii")
        }

        if normalized_text in easter_eggs:
            easter_eggs[normalized_text]()