import re
import webbrowser

from PyQt6.QtWidgets import QWidget

from System.Common    import Constants
from System.Interface import Widgets

from System.Interface.Windows import FloatingWindowGPU

# Update Window

class UpdateWindow(FloatingWindowGPU):
    def __init__(
            self,
            version:   str,
            changelog: str,
            url:       str            = Constants.GITHUB_LINK,
            parent:    QWidget | None = None
        ) -> None:
        
        super().__init__(f"Cassette {version}", parent = parent)

        changelog = re.sub(r"(?m)^### \*\*Cassette v\d+\.\d+\.\d+\*\*\s*\r?\n", "",      changelog)
        changelog = re.sub(r"(?m)^>\s*(.*?)\s*$",                               r"`\1`", changelog)
        changelog = re.sub(r"### \*\*(.*?)\*\*",                                r"`\1`", changelog)
        changelog = re.sub(r"\*\*(.*?)\*\*",                                    r"`\1`", changelog)
        changelog = re.sub(r"(?m)^-\s+",                                        "`•` ",  changelog)

        self.update_label = Widgets.DescriptionLabel("`A new update on GitHub.`\n" + changelog, 700)

        scroll_area = Widgets.ElasticScrollArea(self)
        scroll_area.setFixedSize(700, 400)
        scroll_area.add_widget(self.update_label)

        self.close_button  = Widgets.NothingButton("Cool")
        self.github_button = Widgets.ButtonWithOutline("Check it out on GitHub")

        self.close_button.clicked.connect(self.on_ok)
        self.github_button.clicked.connect(lambda: webbrowser.open(url))

        self.content_layout.addWidget(scroll_area)
        self.content_layout.addWidget(self.github_button)
        self.content_layout.addWidget(self.close_button)