import os
import json
import shutil
import random
import difflib
import mimetypes
import webbrowser

from loguru import logger

from PyQt6.QtCore import (
    Qt,
    QTimer,
    pyqtSignal,
    pyqtProperty,
    QPropertyAnimation
)

from PyQt6.QtGui import (
    QIcon,
    QBrush,
    QColor,
    QPainter,
    QDropEvent,
    QShowEvent,
    QPaintEvent,
    QResizeEvent,
    QDragEnterEvent,
    QDragLeaveEvent,
    QLinearGradient
)

from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QWidget,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QApplication
)

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Interface import (
    Widgets,
    Windows
)

from System.Services import (
    Player,
    ProjectSaver
)

# Search Helpers

def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())

def get_search_score(
        search_query:       str,
        project_identifier: str,
        title:              str,
        artist:             str,
        model:              str
    ) -> float:

    normalized_query = normalize_text(search_query)

    if not normalized_query:
        return 1.0

    normalized_title      = normalize_text(title)
    normalized_artist     = normalize_text(artist)
    normalized_model      = normalize_text(model)
    normalized_identifier = normalize_text(project_identifier)

    tokens = normalized_query.split()

    if normalized_query in normalized_title:
        return 1.0 + (len(normalized_query) / max(len(normalized_title), 1))

    all_fields = f"{normalized_title} {normalized_artist} {normalized_model} {normalized_identifier}"

    if all(token in all_fields for token in tokens):
        title_hits = sum(1 for token in tokens if token in normalized_title)
        return 0.8 + (0.2 * title_hits / len(tokens))

    title_ratio = difflib.SequenceMatcher(None, normalized_query, normalized_title).ratio()

    if title_ratio > 0.6:
        return title_ratio

    other_fields = f"{normalized_artist} {normalized_identifier} {normalized_model}"

    if normalized_query in other_fields:
        return 0.5

    return 0.0

# Project Discovery

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
            with open(json_path, "r", encoding = "utf-8") as file_handle:
                save_data = json.load(file_handle)

        except Exception:
            continue

        try:
            audio_data = save_data["audio"]
            model_code = save_data["model"]
            model_info = Constants.DEVICES[model_code]

            title  = audio_data["title"]
            artist = audio_data["artist"]

        except Exception:
            continue

        projects[project_name] = {
            "audio_path": audio_path,
            "save":       save_data,
            "title":      title,
            "artist":     artist,
            "model":      model_info.short_name,
            "progress":   save_data.get("progress", 0.0)
        }

    return projects

# Track Item Widget

class TrackItemWidget(QWidget):
    edit_clicked  = pyqtSignal(str)
    audio_clicked = pyqtSignal(str)

    def __init__(
            self,
            project_identifier: str,
            title:              str,
            artist:             str,
            subtitle:           str,
            main_menu:          QWidget | None = None
        ) -> None:

        super().__init__(main_menu)

        self.project_identifier = project_identifier
        self.main_menu          = main_menu

        self.setMinimumWidth(240)
        self.setFixedHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.background_frame = QFrame(self)
        self.background_frame.setStyleSheet(
            f"""
                QFrame {{
                    background-color: {Styles.Colors.SecondaryBackground};
                    border-radius: 24px;
                }}
            """
        )
        self.background_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.background_frame)

        content_layout = QVBoxLayout(self.background_frame)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(4)

        top_layout  = QHBoxLayout()
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setFont(Utils.NType(11.5))
        self.title_label.setStyleSheet(Styles.Other.Font)

        self.artist_label = QLabel(f"{artist}  {subtitle}")
        self.artist_label.setFont(Utils.NType(9))
        self.artist_label.setStyleSheet(Styles.Other.SecondFont)

        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.artist_label)
        info_layout.addStretch()

        top_layout.addLayout(info_layout)
        top_layout.addStretch()

        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 16, 0, 0)

        icons_layout = QHBoxLayout()
        icons_layout.setSpacing(4)

        icons_data = [
            ("Save.png",     self.on_export_clicked),
            ("Edit.png",     self.on_edit_clicked),
            ("Settings.png", self.on_audio_clicked),
            ("Delete.png",   self.on_delete_clicked)
        ]

        for icon_name, slot_handler in icons_data:
            button = Widgets.IconButtonSmall(
                QIcon(f"System/Assets/Icons/ProjectMenu/{icon_name}")
            )
            button.clicked.connect(slot_handler)
            icons_layout.addWidget(button)

        bottom_layout.addLayout(icons_layout)
        bottom_layout.addStretch()

        content_layout.addLayout(top_layout)
        content_layout.addLayout(bottom_layout)

    def update_information(
            self,
            title:    str,
            artist:   str,
            subtitle: str
        ) -> None:

        self.title_label.setText(title)
        self.artist_label.setText(f"{artist}  {subtitle}")

    def on_edit_clicked(self) -> None:
        self.edit_clicked.emit(self.project_identifier)

    def on_audio_clicked(self) -> None:
        self.audio_clicked.emit(self.project_identifier)

    def on_delete_clicked(self) -> None:
        dialog = Windows.DialogWindow("Remove?")

        if not dialog.exec():
            return

        shutil.rmtree(
            Utils.get_user_path(str(self.project_identifier), "Cassette/Songs"),
            ignore_errors = True
        )

        if self.main_menu:
            QTimer.singleShot(0, self.main_menu.refresh_tracks)

    def on_export_clicked(self) -> None:
        composition = ProjectSaver.MinimalComposition(self.project_identifier)
        Windows.ExportDialogWindow(composition).exec()

# Fade Overlay Widget

class FadeOverlay(QWidget):
    def __init__(
            self,
            color:             QColor,
            is_top_positioned: bool,
            parent:            QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.overlay_color     = color
        self.is_top_positioned = is_top_positioned
        self.opacity_value     = 1.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(self.opacity_value)

        gradient = QLinearGradient(0, 0, 0, self.height())

        opaque_color = QColor(self.overlay_color)
        opaque_color.setAlpha(255)

        transparent_color = QColor(self.overlay_color)
        transparent_color.setAlpha(0)

        if self.is_top_positioned:
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

# Fade Scroll Area

class FadeScrollArea(QScrollArea):
    def __init__(
            self,
            fade_color:  QColor         = QColor("#000000"),
            fade_height: int            = 40,
            parent:      QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.fade_color  = fade_color
        self.fade_height = fade_height
        self.animations  = {}

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.top_fade    = FadeOverlay(self.fade_color, True, self)
        self.bottom_fade = FadeOverlay(self.fade_color, False, self)

        self.top_fade.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.bottom_fade.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.verticalScrollBar().valueChanged.connect(self.update_fade_visibility)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        viewport_width = self.viewport().width()

        self.top_fade.setGeometry(0, 0, viewport_width, self.fade_height)
        self.bottom_fade.setGeometry(0, self.height() - self.fade_height, viewport_width, self.fade_height)

        self.update_fade_visibility()

    def update_fade_visibility(self, value: int = 0) -> None:
        scroll_value  = self.verticalScrollBar().value()
        maximum_value = self.verticalScrollBar().maximum()

        self.animate_fade(self.top_fade,    scroll_value > 0)
        self.animate_fade(self.bottom_fade, scroll_value < maximum_value)

    def animate_fade(
            self,
            widget:            FadeOverlay,
            should_be_visible: bool
        ) -> None:

        target_opacity  = 1.0 if should_be_visible else 0.0
        current_opacity = widget.opacity

        if current_opacity == target_opacity:
            return

        if widget in self.animations:
            self.animations[widget].stop()

        animation = QPropertyAnimation(widget, b"opacity")
        animation.setDuration(175)
        animation.setStartValue(current_opacity)
        animation.setEndValue(target_opacity)

        if should_be_visible:
            widget.show()

        else:
            animation.finished.connect(lambda target_widget = widget: target_widget.hide())

        animation.start()
        self.animations[widget] = animation

# Main Menu Widget

class MainMenu(QWidget):
    composition_created = pyqtSignal(object)
    edit_requested      = pyqtSignal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.projects_info:   dict[str, dict[str, object]] = {}
        self.track_widgets:   dict[str, TrackItemWidget]   = {}
        self.search_box:      Widgets.SearchTextbox | None = None
        self.drag_loop_sound: Player.UISound | None        = None

        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet(
            f"""
                #container {{
                    background-color: {Styles.Colors.Background};
                    border-radius: 32px;
                }}
            """
        )

        self.setAcceptDrops(True)
        self.setup_ui()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.container)

    def setup_ui(self) -> None:
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(12)

        card_style = f"""
            QFrame {{
                background-color: {Styles.Colors.SecondaryBackground};
                border-radius: 20px;
            }}
        """

        title_container = QFrame()
        title_container.setStyleSheet(card_style)

        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(20, 16, 20, 16)

        self.title_label = QLabel(Utils.get_some_title())
        self.title_label.setFont(Utils.NType(19))
        self.title_label.setStyleSheet("background-color: transparent; color: #ffffff;")

        title_layout.addWidget(self.title_label)
        container_layout.addWidget(title_container)

        button_container = QFrame()
        button_container.setStyleSheet(card_style)

        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(4, 4, 4, 4)
        button_layout.setSpacing(8)

        button_panel = self.create_button_panel()
        button_layout.addWidget(button_panel)

        self.search_box = Widgets.SearchTextbox()
        self.search_box.safeTextChanged.connect(self.apply_search_filter)

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
                    border-radius: 24px;
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
        self.tracks_grid_layout.setSpacing(12)
        self.tracks_grid_layout.setContentsMargins(0, 0, 0, 0)

        self.tracks_grid_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum
        )

        self.tracks_layout.addWidget(self.tracks_grid_widget, alignment = Qt.AlignmentFlag.AlignTop)

    def create_button_panel(self) -> QWidget:
        panel        = QWidget()
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(8)

        version_path = Utils.get_resource_path("version")
        version_text = "0.0.0"

        try:
            with open(version_path, "r", encoding = "utf-8") as file_handle:
                version_text = file_handle.read().strip()

        except OSError:
            pass

        buttons_configuration = [
            ("New composition",   True,  self.on_new_composition),
            ("Glyphtone Trimmer", False, self.on_glyphtone_editor),
            ("Import",            False, self.on_import),
            ("Go to glyphtones",  False, self.on_glyphtones),
            ("Settings",          False, self.on_settings),
            (version_text,        False, self.on_about)
        ]

        for text_label, is_accented, callback_handler in buttons_configuration:
            option_button = Widgets.OptionButton(
                text_label,
                is_accented,
                callback_handler
            )
            panel_layout.addWidget(option_button)

        panel.setStyleSheet("background-color: transparent;")
        
        return panel

    def get_visible_projects(self, search_text: str) -> list[tuple[str, dict[str, object]]]:
        projects = list(self.projects_info.items())

        if not search_text:
            return sorted(projects, key = lambda item: int(item[0]))

        ranked_projects = []

        for project_identifier, project_data in projects:
            score = get_search_score(
                search_text,
                project_identifier,
                str(project_data["title"]),
                str(project_data["artist"]),
                str(project_data["model"])
            )

            if score <= 0.0:
                continue

            ranked_projects.append((score, project_identifier, project_data))

        ranked_projects.sort(key = lambda item: (-item[0], int(item[1])))

        return [
            (project_identifier, project_data)
            for _, project_identifier, project_data in ranked_projects
        ]

    def refresh_tracks(self) -> None:
        songs_directory    = Utils.get_user_path("", "Cassette/Songs")
        self.projects_info = get_projects_info(songs_directory)

        for existing_identifier in list(self.track_widgets.keys()):
            if existing_identifier in self.projects_info:
                continue

            widget = self.track_widgets.pop(existing_identifier)
            widget.deleteLater()

        for project_identifier, project_data in self.projects_info.items():
            title_text    = str(project_data["title"])
            artist_text   = str(project_data["artist"])
            subtitle_text = f"- {project_data['model'] or ''} • {project_data.get('progress', 0.0)}%"

            if project_identifier in self.track_widgets:
                self.track_widgets[project_identifier].update_information(
                    title_text,
                    artist_text,
                    subtitle_text
                )
                continue

            track_item = TrackItemWidget(
                project_identifier,
                title_text,
                artist_text,
                subtitle_text,
                self
            )

            track_item.edit_clicked.connect(self.on_edit_project)
            track_item.audio_clicked.connect(self.on_audio_settings)

            self.track_widgets[project_identifier] = track_item

        search_query = self.search_box.text() if self.search_box else ""
        self.apply_search_filter(search_query)

    def apply_search_filter(self, search_text: str) -> None:
        for index in reversed(range(self.tracks_grid_layout.count())):
            layout_item = self.tracks_grid_layout.takeAt(index)
            grid_widget = layout_item.widget()

            if grid_widget:
                grid_widget.hide()

        visible_projects = self.get_visible_projects(search_text)

        for index, (project_identifier, _) in enumerate(visible_projects):
            row    = index // 2
            column = index % 2

            matched_widget = self.track_widgets.get(project_identifier)

            if matched_widget:
                self.tracks_grid_layout.addWidget(matched_widget, row, column)
                matched_widget.show()

    def process_new_composition(self, file_path: str) -> None:
        audio_dialog = Windows.AudioSetupDialog(file_path)

        if not audio_dialog.exec():
            return

        composition = ProjectSaver.Composition(
            file_path,
            audio_dialog.saved_settings
        )

        self.composition_created.emit(composition)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not self.drag_loop_sound:
            Player.ui_player.play_sound(
                "DragDrop/DragDrop",
                speed       = 1.1,
                setting_key = "drag_drop_sounds"
            )

            self.drag_loop_sound = Player.ui_player.play_sound(
                "DragDrop/Loop",
                loop        = True,
                setting_key = "drag_drop_sounds"
            )

        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        if self.drag_loop_sound:
            Player.ui_player.play_sound(
                "DragDrop/DragDrop",
                speed       = 0.9,
                setting_key = "drag_drop_sounds"
            )

            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        file_to_process = None

        for url in event.mimeData().urls():
            candidate_path = url.toLocalFile()
            mime_type      = mimetypes.guess_type(candidate_path)[0]

            if not mime_type:
                continue

            if mime_type.startswith("audio") or mime_type.startswith("video"):
                file_to_process = candidate_path
                break

        if not file_to_process:
            Player.ui_player.play_sound("Signals/Error/MegaCritical")
            self.title_label.setText(
                random.choice(
                    [
                        "Uhhm, no.",
                        "Huh?",
                        "How do I read that?",
                        "That's not music.",
                        "I only eat audio and video files.",
                        "Nice try, but no.",
                        "Wrong tape.",
                        "Maybe try a .wav?"
                    ]
                )
            )
            super().dropEvent(event)
            return

        Player.ui_player.play_sound(
            "DragDrop/DragDrop",
            speed       = 0.9,
            setting_key = "drag_drop_sounds"
        )

        self.process_new_composition(file_to_process)
        event.acceptProposedAction()

        super().dropEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh_tracks()

    def on_settings(self) -> None:
        settings_dialog = Windows.SettingsWindow()
        settings_dialog.initialize_settings(Constants.SettingsDict())
        settings_dialog.exec()

    def on_import(self) -> None:
        import_window = Windows.ImportWindow()

        if not import_window.exec():
            return

        composition = ProjectSaver.Composition(
            import_window.audio_path,
            import_window.saved_settings
        )

        self.composition_created.emit(composition)

    def on_about(self) -> None:
        modifiers = QApplication.keyboardModifiers()

        has_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        has_alt   = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        has_ctrl  = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

        if has_shift and has_ctrl:
            Windows.WalterWindow().exec()
            return

        if has_shift:
            Windows.ByteBeatWindow().exec()
            return

        if has_alt:
            Windows.AboutWindow(more_info = True).exec()
            return

        Windows.AboutWindow().exec()

    def on_glyphtones(self) -> None:
        webbrowser.open("https://glyphtones.firu.dev/")

    def on_edit_project(self, project_identifier: str) -> None:
        self.setEnabled(False)
        self.edit_requested.emit(project_identifier)

    def on_audio_settings(self, project_identifier: str) -> None:
        try:
            composition  = ProjectSaver.Composition(id = project_identifier)
            audio_window = Windows.ExistingAudioSetupDialog(composition)

            if not audio_window.exec():
                return

            composition.bpm = audio_window.get_bpm_value()

            if audio_window.snapped_times:
                composition.beats = audio_window.snapped_times

            trim_settings = audio_window.get_trim_settings()

            composition.trim_audio(
                int(trim_settings["start_ms"]),
                int(trim_settings["end_ms"]),
                int(trim_settings["fade_in"]),
                int(trim_settings["fade_out"])
            )

        except Exception as exception:
            Windows.ErrorWindow("Audio edit failed", str(exception)).exec()

    def ask_for_file(self) -> str | None:
        file_dialog = QFileDialog(
            self,
            "Open Audio File",
            "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.opus *.mp4 *.mkv *.mov);;All Files (*)"
        )

        file_dialog.setOptions(QFileDialog.Option.ReadOnly)

        if file_dialog.exec() != QFileDialog.DialogCode.Accepted:
            return None

        return file_dialog.selectedFiles()[0]

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

        Windows.GlyphtoneEditor(file_path).exec()