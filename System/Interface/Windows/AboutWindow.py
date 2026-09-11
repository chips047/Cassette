import sys
import random
import platform
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtGui  import QPixmap

from PyQt6.QtWidgets import (
    QLabel,
    QWidget
)

from System.Common import (
    Utils,
    Constants
)

from System.Interface import Widgets

from System.Interface.Windows import FloatingWindowGPU

# About Window

class AboutWindow(FloatingWindowGPU):
    def __init__(
            self,
            more_info: bool           = False,
            parent:    QWidget | None = None
        ) -> None:

        with open(Utils.get_resource_path("version"), "r", encoding = "utf-8") as version_file:
            version_text = version_file.read().strip()

        super().__init__(
            f"Cassette {version_text} by chips047",
            parent                     = parent,
            enable_audioplayer_effects = False
        )

        if more_info:
            text = (
                f"System {sys.platform} {platform.machine()}\n"
                f"Python: {sys.version}"
            )
        
        else:
            text = (
                "The best open - source compositor. Currently in active development!\n\n"
                "`Inspirations and credits`\n"
                "- UI sounds from `R.E.P.O.` by `semiwork`.\n"
                "- Open sound from `The Upturned` by `Zeekers`.\n"
                "- Open sounds from `Simulacra` by `Kaigan Games`.\n"
                "- Sounds from `Pacific Drive` by `Ironwood Studios`.\n\n"
                "Made with care, way too much profiling, and a genuine love for smooth interfaces."
            )

        self.about_label = Widgets.DescriptionLabel(text, 500)

        self.image_pixmap = QPixmap("System/Assets/Image/Version.png").scaled(
            500, 500,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self.image_label = QLabel()
        self.image_label.setPixmap(self.image_pixmap)

        ok_button     = Widgets.NothingButton("Five Stars?")
        github_button = Widgets.ButtonWithOutline("Check for updates on GitHub")

        ok_button.clicked.connect(self.on_ok)
        github_button.clicked.connect(self.on_github)

        for widget in (self.about_label, self.image_label, github_button, ok_button):
            self.content_layout.addWidget(widget)

    def on_github(self) -> None:
        github_link = Constants.GITHUB_LINK

        if random.random() < 0.95:
            webbrowser.open(github_link)
            return

        fox_image = Utils.get_fox_image()
        webbrowser.open(fox_image if fox_image else github_link)