from PyQt6.QtWidgets import QWidget

from System.Interface import Widgets

from System.Interface.Windows import DialogWindow

# Trim Warning Dialog

class TrimWarningDialog(DialogWindow):
    def __init__(
            self,
            glyph_count: int,
            parent:      QWidget | None = None
        ) -> None:
        
        super().__init__("Heads up", parent = parent)

        glyph_word  = "glyph" if glyph_count == 1 else "glyphs"
        description = (
            f"This will permanently delete {glyph_count} {glyph_word} "
            f"that fall outside the new selection. This cannot be undone."
        )

        self.description_label = Widgets.DescriptionLabel(description, 600)
        self.content_layout.insertWidget(1, self.description_label)

        self.title_label.start_glitch()
        
        self.adjustSize()