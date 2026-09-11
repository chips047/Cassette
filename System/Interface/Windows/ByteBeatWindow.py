from PyQt6.QtGui     import QCloseEvent
from PyQt6.QtWidgets import QWidget

from System.Services  import Player
from System.Interface import Widgets

from System.Interface.Windows import FloatingWindowGPU

# ByteBeatWindow

class ByteBeatWindow(FloatingWindowGPU):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Hm.", parent = parent)

        self.bytebeat_player = Player.ByteBeatPlayer()
        self.bytebeat_player.play()

        self.textbox = Widgets.Textbox("text", placeholder = "Byte Beat?", max_length = 99999)
        self.textbox.setMinimumWidth(400)
        self.textbox.safeTextChanged.connect(self.on_textbox_changed)

        examples = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "1", lambda: self.example_callback("1")),
                (Widgets.ButtonWithOutline, "2", lambda: self.example_callback("2")),
                (Widgets.ButtonWithOutline, "3", lambda: self.example_callback("3")),
                (Widgets.ButtonWithOutline, "4", lambda: self.example_callback("4")),
                (Widgets.ButtonWithOutline, "5", lambda: self.example_callback("5"))
            ]
        )

        close_button = Widgets.ButtonWithOutline("Ok?")
        close_button.pressed.connect(self.on_ok)

        self.content_layout.addWidget(self.textbox)
        self.content_layout.addLayout(examples)
        self.content_layout.addWidget(close_button)

    def on_textbox_changed(self, text: str) -> None:
        self.bytebeat_player.set_formula(text)

    def example_callback(self, number: str) -> None:
        code_formulas = {
            "1": "(t * ((7 if t & 4096 else 16) + (1 if (1 & (t >> 14)) else 0) if t % 65536 < 59392 else t&7 or 16)) >> (3 & -t >> (2 if (t & 2048) else 10))",
            "2": "((t >> 10) & 42) * t",
            "3": "((t>>9^(t>>9)-1^1)%13*t&31)*(2+(t>>4))",
            "4": "t^t>>4^(t>>11+(t>>16)%3)%16*t^3*t",
            "5": "(lambda d,b,a,n,r: (((d if ((b//4)%16) in (0,3,6,10) else 0) % 64) + ((d*a[r]) % 64) + (((d*a[r])/1.33) % 64) + ((n if b%4==0 else 0) % 20) + ((n if b%32==16 else 0) % 44)))((0.127*(t*6)), int((t*6)/1578), [0,0,0,0,0,0,0,0,4,4,4.75,4.75,5.3,0,5.3,5.3,5.3,5.3,5.3,5.3,4.75,4.75,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,4,4.75,4.75,5.3,0,5.3,5.3,5.3,5.3,4.75,4.75,0,0,4,4,0,0,3.55,3.55,4,4,0,0], (0.127*(t*6))*random(), (int((t*6)/1578)//2)%64)"
        }

        formula = code_formulas.get(number)

        if formula:
            self.bytebeat_player.set_formula(formula)
            self.textbox.setText(formula)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.bytebeat_player.cleanup()
        super().closeEvent(event)