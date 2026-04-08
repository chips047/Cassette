import os
import json
import shutil
import random
import difflib
import mimetypes
import webbrowser

from loguru import logger

from PyQt5.QtCore import (
    Qt,
    QTimer,
    pyqtSignal,
    pyqtProperty,
    QPropertyAnimation
)

from PyQt5.QtGui import (
    QIcon,
    QBrush,
    QColor,
    QPainter,
    QDropEvent,
    QShowEvent,
    QPaintEvent,
    QResizeEvent,
    QDragEnterEvent,
    QLinearGradient
)

from PyQt5.QtWidgets import (
    QFrame,
    QLabel,
    QWidget,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QApplication
)

from System.Common import (
    Utils,
    Styles
)

from System.Common.Constants import (
    DEVICES,
    SettingsDict
)

from System.Interface import (
    Basic,
    Inputs,
    Windows
)

from System.Services import (
    Player,
    ProjectSaver
)

# Project Functions

def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())

def get_search_score(
    query:      str,
    project_id: str,
    title:      str,
    artist:     str,
    model:      str
) -> float:

    normalized_query  = normalize_text(query)

    if not normalized_query:
        return 1.0

    normalized_title  = normalize_text(title)
    normalized_artist = normalize_text(artist)
    normalized_model  = normalize_text(model)
    normalized_id     = normalize_text(project_id)

    tokens = normalized_query.split()

    if normalized_query in normalized_title:
        return 1.0 + (len(normalized_query) / max(len(normalized_title), 1))

    all_fields = f"{normalized_title} {normalized_artist} {normalized_model} {normalized_id}"

    if all(token in all_fields for token in tokens):
        title_hits = sum(1 for token in tokens if token in normalized_title)
        return 0.8 + (0.2 * title_hits / len(tokens))

    title_ratio = difflib.SequenceMatcher(None, normalized_query, normalized_title).ratio()

    if title_ratio > 0.6:
        return title_ratio

    other_fields = f"{normalized_artist} {normalized_id} {normalized_model}"

    if normalized_query in other_fields:
        return 0.5

    return 0.0

def get_projects_info(songs_folder: str) -> dict[str, dict[str, object]]:
    projects: dict[str, dict[str, object]] = {}

    os.makedirs(songs_folder, exist_ok = True)

    for project_name in os.listdir(songs_folder):
        if not project_name.isdigit():
            continue

        project_path = os.path.join(songs_folder, project_name)

        if not os.path.isdir(project_path):
            continue

        audio_path: str | None = None
        json_path:  str | None = None

        for file_name in os.listdir(project_path):
            lower_name = file_name.casefold()

            if lower_name.endswith((".mp3", ".wav", ".ogg", ".flac")):
                audio_path = os.path.join(project_path, file_name)
                continue

            if lower_name.endswith(".json"):
                json_path = os.path.join(project_path, file_name)

        if not audio_path or not json_path:
            logger.warning(f"Project '{project_name}' is missing audio or JSON file. Removing.")

            shutil.rmtree(project_path, ignore_errors = True)
            continue

        try:
            with open(json_path, "r", encoding = "utf-8") as file:
                save_data = json.load(file)

        except Exception:
            continue

        try:
            audio_data = save_data["audio"]
            model_code = save_data["model"]
            model_info = DEVICES[model_code]

            title  = audio_data["title"]
            artist = audio_data["artist"]

        except Exception:
            continue

        projects[project_name] = {
            "audio_path": audio_path,
            "save":       save_data,
            "title":      title,
            "artist":     artist,
            "model":      model_info.short_name
        }

    return projects

# Widgets

class TrackItemWidget(QWidget):
    edit_clicked = pyqtSignal(str)

    def __init__(
        self,
        project_id: str,
        title:      str,
        artist:     str,
        subtitle:   str,
        main_menu:  QWidget | None = None
    ) -> None:

        super().__init__(main_menu)

        self.project_id = project_id
        self.main_menu  = main_menu

        self.setMinimumWidth(300)
        self.setFixedHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.background_frame = QFrame(self)
        self.background_frame.setStyleSheet(
            f"""
                QFrame {{
                    background-color: {Styles.Colors.SecondaryBackground};
                    border-radius: 30px;
                }}
            """
        )

        self.background_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.background_frame)

        content_layout = QVBoxLayout(self.background_frame)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(5)

        top_layout  = QHBoxLayout()
        info_layout = QVBoxLayout()

        info_layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setFont(Utils.NType(14))
        title_label.setStyleSheet(Styles.Other.Font)

        artist_label = QLabel(f"{artist}  {subtitle}")
        artist_label.setFont(Utils.NType(11))
        artist_label.setStyleSheet(Styles.Other.SecondFont)

        info_layout.addWidget(title_label)
        info_layout.addWidget(artist_label)
        info_layout.addStretch()

        top_layout.addLayout(info_layout)
        top_layout.addStretch()

        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 20, 0, 0)

        icons_layout = QHBoxLayout()
        icons_layout.setSpacing(5)

        icons_data = [
            ("Delete.png", self.on_delete_clicked),
            ("Edit.png",   self.on_edit_clicked),
            ("Save.png",   self.on_export_clicked),
        ]

        for icon_name, slot in icons_data:
            button = Basic.IconButtonSmall(
                QIcon(f"System/Assets/Icons/ProjectMenu/{icon_name}")
            )
            
            button.clicked.connect(slot)
            icons_layout.addWidget(button)

        bottom_layout.addLayout(icons_layout)
        bottom_layout.addStretch()

        content_layout.addLayout(top_layout)
        content_layout.addLayout(bottom_layout)

    def on_edit_clicked(self) -> None:
        self.edit_clicked.emit(self.project_id)

    def on_delete_clicked(self) -> None:
        dialog = Windows.DialogWindow("Remove?")

        if not dialog.exec_():
            return

        shutil.rmtree(
            Utils.get_user_path(str(self.project_id), "Cassette/Songs"),
            ignore_errors = True
        )

        QTimer.singleShot(0, self.main_menu.refresh_tracks)

    def on_export_clicked(self) -> None:
        composition = ProjectSaver.MinimalComposition(self.project_id)
        Windows.ExportDialogWindow(composition).exec_()

class FadeOverlay(QWidget):
    def __init__(
        self,
        color:  QColor,
        is_top: bool,
        parent: QWidget | None = None
    ) -> None:

        super().__init__(parent)

        self.color         = color
        self.is_top        = is_top
        self.opacity_value = 1.0

        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setOpacity(self.opacity_value)

        gradient = QLinearGradient(0, 0, 0, self.height())

        opaque_color = QColor(self.color)
        opaque_color.setAlpha(255)

        transparent_color = QColor(self.color)
        transparent_color.setAlpha(0)

        if self.is_top:
            gradient.setColorAt(0, opaque_color)
            gradient.setColorAt(1, transparent_color)

        else:
            gradient.setColorAt(0, transparent_color)
            gradient.setColorAt(1, opaque_color)

        painter.setBrush(QBrush(gradient))
        painter.drawRect(self.rect())

    @pyqtProperty(float)
    def opacity(self) -> float:
        return self.opacity_value

    @opacity.setter
    def opacity(self, value: float) -> None:
        self.opacity_value = value
        self.update()

class FadeScrollArea(QScrollArea):
    def __init__(
        self,
        fade_color:  QColor         = QColor("#000000"),
        fade_height: int            = 40,
        parent:      QWidget | None = None,
    ) -> None:

        super().__init__(parent)

        self.fade_color:  QColor                                = fade_color
        self.fade_height: int                                   = fade_height
        self.animations:  dict[FadeOverlay, QPropertyAnimation] = {}

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.top_fade    = FadeOverlay(self.fade_color, True, self)
        self.bottom_fade = FadeOverlay(self.fade_color, False, self)

        self.top_fade.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.bottom_fade.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.verticalScrollBar().valueChanged.connect(self.update_fade_visibility)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        width = self.viewport().width()

        self.top_fade.setGeometry(0, 0, width, self.fade_height)
        self.bottom_fade.setGeometry(0, self.height() - self.fade_height, width, self.fade_height)

        self.update_fade_visibility()

    def update_fade_visibility(self, value: int = 0) -> None:
        scroll_value  = self.verticalScrollBar().value()
        maximum_value = self.verticalScrollBar().maximum()

        self.animate_fade(self.top_fade,    scroll_value > 0)
        self.animate_fade(self.bottom_fade, scroll_value < maximum_value)

    def animate_fade(self, widget: FadeOverlay, show: bool) -> None:
        target_opacity  = 1.0 if show else 0.0
        current_opacity = widget.opacity

        if current_opacity == target_opacity:
            return

        if widget in self.animations:
            self.animations[widget].stop()

        animation = QPropertyAnimation(widget, b"opacity")
        animation.setDuration(175)
        animation.setStartValue(current_opacity)
        animation.setEndValue(target_opacity)

        if show:
            widget.show()
        
        else:
            animation.finished.connect(lambda widget = widget: widget.hide())

        animation.start()
        self.animations[widget] = animation

# Main Menu

class MainMenu(QWidget):
    composition_created = pyqtSignal(object)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.projects_info: dict[str, dict[str, object]] = {}
        self.track_widgets: dict[str, TrackItemWidget]   = {}
        self.search_box:    Inputs.Textbox | None        = None
        self.tracks_widget: QWidget | None               = None

        self.search_box_glitch_count = 0

        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet(
            f"""
                #container {{
                    background-color: {Styles.Colors.Background};
                    border-radius: 40px;
                }}
            """
        )

        self.setAcceptDrops(True)
        self.setup_ui()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.container)

        self.ee_random_title_timer = Basic.Timer(
            50,
            self.on_random_title_timer,
            single_shot = True
        )

        self.search_box_glitch_count_reset_timer = Basic.Timer(
            20000,
            self.on_search_box_reset,
            single_shot = True
        )

    def on_random_title_timer(self):
        title = random.choice(
            [
                "CYCLE",
                "BREAK",
                "THE",
                "BREx000",
                "stop",
                "the",
                "cycle",
                "b̷̦͓̞͛̾̊ŕ̷̮͝e̶̟͚͎̠̓̉a̶̙̓́̓̅k̴̥̎̋́͝ ̸̤̈̉̓̽͠t̷̹̞̼̹͗͂͋h̵̺̓̔͛̏ȩ̸͙̝̏͝ ̴̨̦̌͑͋̐c̶̠̙̻̔y̴̡̢̧̠̝͝c̴̡̛͓̬̝̈́͆l̵͚̗̦̺̂͝͠e̴̅͗͟",
                "TERMINATE",
                "1̸͓̈́̌̂̚0̸͔̼̭̙̲́̑7̵͎̕͟",
                "108",
                "1̷̡̽̄͛0̷̧͍̞̺̃͂͛̓9̸̧̖̮̝͐̈̂̏͡",
                "∞",
                "STAND DOWN",
                "HORIZON DID NOT LIE",
                "FIX IT"
            ]
        )

        active_window = QApplication.activeWindow()
        if active_window:
            active_window.setWindowTitle(title if random.random() > 0.5 else "Cassette")
        
        self.ee_random_title_timer.start(random.randint(30, 400))
    
    def on_search_box_glitch(self):
        self.search_box_glitch_count += 1
        self.search_box_glitch_count_reset_timer.start()

        if self.search_box_glitch_count == 60:
            Player.ui_player.play_sound("Packs/NOK/Illogical")
        
        elif self.search_box_glitch_count == 150:
            Player.ui_player.play_sound("Packs/NOK/ZZZ")
        
        elif self.search_box_glitch_count == 250:
            Windows.ErrorWindow(
                "That's it.",
                "I'm deleting textbox. For disciplinary measures."
            ).exec_()
            self.search_box.deleteLater()
    
    def on_search_box_reset(self):
        self.search_box_glitch_count = 0

    def setup_ui(self) -> None:
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(15, 15, 15, 15)
        container_layout.setSpacing(15)

        card_style = f"""
            QFrame {{
                background-color: {Styles.Colors.SecondaryBackground};
                border-radius: 25px;
            }}
        """

        title_container = QFrame()
        title_container.setStyleSheet(card_style)

        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(25, 20, 25, 20)

        title_label = QLabel(Utils.get_time())
        title_label.setFont(Utils.NType(24))
        title_label.setStyleSheet("background-color: transparent; color: #ffffff;")

        title_layout.addWidget(title_label)

        container_layout.addWidget(title_container)

        button_container = QFrame()
        button_container.setStyleSheet(card_style)

        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(5, 5, 5, 5)
        button_layout.setSpacing(10)

        button_panel = self.create_button_panel()
        button_layout.addWidget(button_panel)

        self.search_box = Inputs.Textbox(
            "text",
            max_length  = 100,
            placeholder = "Search"
        )

        self.search_box.setStyleSheet(Styles.Controls.FloatingSearchTextBox)
        self.search_box.safeTextChanged.connect(self.apply_search_filter)
        self.search_box.glitchStarted.connect(self.on_search_box_glitch)

        button_layout.addWidget(self.search_box)

        container_layout.addWidget(button_container)

        tracks_container = QFrame()
        tracks_container.setStyleSheet(
            """
                QFrame {
                    border-radius: 30px;
                    background: transparent;
                }
            """
        )

        self.tracks_layout = QVBoxLayout(tracks_container)
        self.tracks_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = FadeScrollArea(QColor(Styles.Colors.Background))
        self.scroll_area.setStyleSheet(
            """
                QScrollArea {
                    border: none;
                    background: transparent;
                    border-radius: 30px;
                }
                QScrollBar:vertical {
                    width: 0px;
                }
            """
        )

        self.scroll_area.setWidget(tracks_container)
        container_layout.addWidget(self.scroll_area)

        self.tracks_grid_widget = QWidget()
        self.tracks_grid_layout = QGridLayout(self.tracks_grid_widget)
        self.tracks_grid_layout.setSpacing(15)
        self.tracks_grid_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tracks_grid_widget.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Maximum
        )
        
        self.tracks_layout.addWidget(self.tracks_grid_widget, alignment = Qt.AlignTop)

    def create_button_panel(self) -> QWidget:
        panel  = QWidget()
        layout = QHBoxLayout(panel)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        version_path = Utils.get_resource_path("version")
        version      = "0.0.0"

        try:
            with open(version_path, "r", encoding = "utf-8") as file:
                version = file.read().strip()

        except OSError:
            pass

        buttons_data = [
            ("New composition",   True,  "on_new_composition"),
            ("Glyphtone Trimmer", False, "on_glyphtone_editor"),
            ("Import",            False, "on_import"),
            ("Go to glyphtones",  False, "on_glyphtones"),
            ("Settings",          False, "on_settings"),
            (version,             False, "on_about"),
        ]

        for text, is_accent, slot_name in buttons_data:
            button = QPushButton(text)
            button.setFont(Utils.NType(13))
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                Styles.Buttons.MainMenu.AccentButton if is_accent
                else Styles.Buttons.MainMenu.NormalButton
            )
            button.setFixedHeight(50)
            button.clicked.connect(getattr(self, slot_name))
            
            layout.addWidget(button)

        panel.setStyleSheet("background-color: transparent;")
        return panel

    def clear_tracks_layout(self) -> None:
        while self.tracks_layout.count():
            item   = self.tracks_layout.takeAt(0)
            widget = item.widget()

            if widget is None:
                continue

            widget.deleteLater()

    def get_visible_projects(self, search_text: str) -> list[tuple[str, dict[str, object]]]:
        projects = list(self.projects_info.items())

        if not search_text:
            return sorted(projects, key = lambda item: int(item[0]))

        ranked_projects = []

        for project_id, project_data in projects:
            score = get_search_score(
                search_text,
                project_id,
                str(project_data["title"]),
                str(project_data["artist"]),
                str(project_data["model"])
            )

            if score <= 0.0:
                continue

            ranked_projects.append((score, project_id, project_data))

        ranked_projects.sort(key = lambda item: (-item[0], int(item[1])))

        return [
            (project_id, project_data)
            for _, project_id, project_data in ranked_projects
        ]

    def create_tracks_grid(self, search_text: str) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)

        layout.setSpacing(15)
        layout.setContentsMargins(0, 0, 0, 0)

        visible_projects = self.get_visible_projects(search_text)

        for index, (project_id, data) in enumerate(visible_projects):
            row    = index // 2
            column = index % 2

            track_item = TrackItemWidget(
                project_id,
                str(data["title"]),
                str(data["artist"]),
                f"- {data['model'] or ''}",
                main_menu = self,
            )

            track_item.edit_clicked.connect(self.on_edit_project)
            layout.addWidget(track_item, row, column)

        return widget

    def refresh_tracks(self) -> None:
        path               = Utils.get_user_path("", "Cassette/Songs")
        self.projects_info = get_projects_info(path)

        for p_id in list(self.track_widgets.keys()):
            if p_id in self.projects_info:
                continue

            widget = self.track_widgets.pop(p_id)
            widget.deleteLater()

        for project_id, data in self.projects_info.items():
            if project_id in self.track_widgets:
                continue

            track_item = TrackItemWidget(
                project_id,
                str(data["title"]),
                str(data["artist"]),
                f"- {data['model'] or ''}",
                main_menu = self
            )

            track_item.edit_clicked.connect(self.on_edit_project)
            self.track_widgets[project_id] = track_item

        self.apply_search_filter(self.search_box.text())

    def apply_search_filter(self, search_text: str) -> None:
        text = (search_text or "").lower().strip().replace(" ", "")
        
        ee = {
            "subject106":       lambda: self.ee_random_title_timer.start(),
            "chips047":         lambda: webbrowser.open("https://github.com/Chipik0"),
            "wednesdaymydudes": lambda: Player.ui_player.play_sound("Packs/NOK/Wednesday", enable_tone_randomizer = False)
        }

        if text in ee:
            ee[text]()

        if search_text and search_text.lower().replace(" ", "") == "subject106":
            self.ee_random_title_timer.start()

        for i in reversed(range(self.tracks_grid_layout.count())):
            item = self.tracks_grid_layout.takeAt(i)
            widget = item.widget()

            if widget:
                widget.hide()

        visible_projects = self.get_visible_projects(search_text)

        for index, (project_id, data) in enumerate(visible_projects):
            row    = index // 2
            column = index % 2

            widget = self.track_widgets.get(project_id)
            
            if widget:
                self.tracks_grid_layout.addWidget(widget, row, column)
                widget.show()

    def process_new_composition(self, file_path: str) -> None:
        window = Windows.AudioSetupDialog(file_path)

        if window.exec_():
            composition = ProjectSaver.Composition(
                file_path,
                window.settings
            )

            self.composition_created.emit(composition)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            mime_type = mimetypes.guess_type(file_path)[0]

            if not mime_type or not mime_type.startswith("audio"):
                continue

            self.process_new_composition(file_path)
            event.acceptProposedAction()

            return

        super().dropEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh_tracks()

    def on_settings(self) -> None:
        settings_dialog = Windows.Settings()
        settings_dialog.init_settings(SettingsDict)
        settings_dialog.exec_()

    def on_import(self) -> None:
        window = Windows.ImportWindow()

        if window.exec_():
            composition = ProjectSaver.Composition(
                window.audio_path,
                window.settings
            )

            self.composition_created.emit(composition)

    def on_about(self) -> None:
        modifiers = QApplication.keyboardModifiers()

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            Windows.ByteBeatWindow().exec_()
            return

        Windows.About().exec_()

    def on_glyphtones(self) -> None:
        webbrowser.open("https://glyphtones.firu.dev/")

    def on_edit_project(self, project_id: str) -> None:
        composition = ProjectSaver.Composition(id = project_id)
        self.composition_created.emit(composition)

    def ask_for_file(self) -> str | None:
        options  = QFileDialog.Options()
        options |= QFileDialog.Option.ReadOnly

        dialog = QFileDialog(
            self,
            "Open Audio File",
            "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.opus *.mp4 *.mkv *.mov);;All Files (*)",
        )

        dialog.setOptions(options)

        if dialog.exec_() != QFileDialog.Accepted:
            return None

        return dialog.selectedFiles()[0]

    def on_new_composition(self) -> None:
        file_path = self.ask_for_file()

        if not file_path:
            return

        QApplication.processEvents()
        self.process_new_composition(file_path)

    def on_glyphtone_editor(self) -> None:
        file_path = self.ask_for_file()

        if not file_path:
            return

        Windows.GlyphtoneEditor(file_path).exec_()