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

from System.Interface.Windows.FeedbackWindow import FeedbackWindow

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

        about_label = Widgets.DescriptionLabel(text, 500)

        image_pixmap = QPixmap("System/Assets/Image/Version.png").scaled(
            500, 500,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        image_label = QLabel()
        image_label.setPixmap(image_pixmap)

        row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "GitHub",   self.on_github),
                (Widgets.ButtonWithOutline, "Feedback", self.on_feedback)
            ]
        )

        ok_button = Widgets.NothingButton("Five Stars?")
        ok_button.clicked.connect(self.on_ok)

        self.content_layout.addWidget(about_label)
        self.content_layout.addWidget(image_label)
        self.content_layout.addLayout(row)
        self.content_layout.addWidget(ok_button)
    
    def on_github(self) -> None:
        github_link = Constants.GITHUB_LINK

        if random.random() < 0.95:
            webbrowser.open(github_link)
            return

        fox_image = Utils.get_fox_image()
        webbrowser.open(fox_image if fox_image else github_link)

    def on_feedback(self) -> None:
        FeedbackWindow().exec()