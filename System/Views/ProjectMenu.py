from __future__ import annotations

import os
import json
import shutil
import random
import time
import difflib
import mimetypes
import webbrowser

from loguru import logger

from PyQt6.QtGui import (
    QIcon,
    QDropEvent,
    QHideEvent,
    QShowEvent,
    QFocusEvent,
    QMouseEvent,
    QResizeEvent,
    QDragMoveEvent,
    QDragEnterEvent,
    QDragLeaveEvent
)

from PyQt6.QtCore import (
    Qt,
    QSize,
    QEvent,
    QTimer,
    QObject,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QWidget,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
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

from System.Interface.Animation import WindowAnimator
from System.Interface.Widgets.ScrollArea import ElasticScrollArea

from System.Services import (
    Player,
    ProjectSaver
)

# Search Calculation

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
    edit_clicked    = pyqtSignal(str)
    audio_clicked   = pyqtSignal(str)
    project_deleted = pyqtSignal()

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

        self.setFixedHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.background_frame = QFrame(self)
        self.background_frame.setStyleSheet(Styles.Controls.TrackCard)
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
        self.title_label.setMinimumWidth(0)

        self.artist_label = QLabel(f"{artist}  {subtitle}")
        self.artist_label.setFont(Utils.NType(9))
        self.artist_label.setStyleSheet(Styles.Other.SecondFont)
        self.artist_label.setMinimumWidth(0)

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
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(slot_handler)
            icons_layout.addWidget(button)

        bottom_layout.addLayout(icons_layout)
        bottom_layout.addStretch()

        content_layout.addLayout(top_layout)
        content_layout.addLayout(bottom_layout)

    def sizeHint(self) -> QSize:
        return QSize(0, 120)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 120)

    # Information Update

    def update_information(
            self,
            title:    str,
            artist:   str,
            subtitle: str
        ) -> None:

        self.title_label.setText(title)
        self.artist_label.setText(f"{artist}  {subtitle}")

    # Action Handlers

    def on_edit_clicked(self) -> None:
        self.edit_clicked.emit(self.project_identifier)

    def on_audio_clicked(self) -> None:
        self.audio_clicked.emit(self.project_identifier)

    def on_delete_clicked(self) -> None:
        dialog = Windows.DialogWindow("Remove?")

        if not dialog.exec():
            return

        project_path = Utils.get_user_path(
            str(self.project_identifier),
            "Cassette/Songs"
        )
        shutil.rmtree(project_path, ignore_errors = True)

        if not self.main_menu:
            return

        if not os.path.exists(project_path):
            self.project_deleted.emit()

        QTimer.singleShot(0, self.main_menu.refresh_tracks)

    def on_export_clicked(self) -> None:
        composition = ProjectSaver.MinimalComposition(self.project_identifier)
        Windows.ExportDialogWindow(composition).exec()

# Main Menu Widget

class MainMenu(QWidget):
    composition_created = pyqtSignal(object)
    edit_requested      = pyqtSignal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.projects_info:          dict[str, dict[str, object]] = {}
        self.track_widgets:          dict[str, TrackItemWidget]   = {}
        self.search_box:             Widgets.SearchTextbox | None = None
        self.drag_loop_sound:        Player.UISound | None        = None
        self.version_button:         Widgets.OptionButton | None  = None
        self.cached_update_info:     dict[str, object] | None     = None
        self.current_column_count:   int                          = 2
        self.project_deletion_times: list[float]                  = []

        self.minimum_column_width_px: int                         = 340
        self.grid_spacing_px:         int                         = 12

        self.window_animator = WindowAnimator.WindowAnimator.get()

        self.container = QFrame(self)
        self.container.setStyleSheet(Styles.Controls.TitleCard)

        self.setAcceptDrops(True)
        self.setup_ui()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.container)

    # UI Setup

    def setup_ui(self) -> None:
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(12)

        title_container = QFrame()
        title_container.setStyleSheet(Styles.Controls.ContainerCard)

        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(20, 16, 20, 16)

        self.title_label = QLabel(Utils.get_some_title())
        self.title_label.setFont(Utils.NType(19))
        self.title_label.setStyleSheet("background-color: transparent; color: #ffffff;")

        title_layout.addWidget(self.title_label)
        container_layout.addWidget(title_container)

        button_container = QFrame()
        button_container.setStyleSheet(Styles.Controls.ContainerCard)

        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(4, 4, 4, 4)
        button_layout.setSpacing(8)

        button_panel = self.create_button_panel()
        button_layout.addWidget(button_panel)

        self.search_box = Widgets.SearchTextbox()
        self.search_box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.search_box.installEventFilter(self)
        self.search_box.safeTextChanged.connect(self.apply_search_filter)

        button_layout.addWidget(self.search_box)
        container_layout.addWidget(button_container)

        self.scroll_area = ElasticScrollArea(self, Styles.Colors.Background)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.tracks_grid_widget = QWidget()
        self.tracks_grid_layout = QGridLayout(self.tracks_grid_widget)
        self.tracks_grid_layout.setSpacing(self.grid_spacing_px)
        self.tracks_grid_layout.setContentsMargins(0, 0, 0, 0)

        self.apply_column_stretches(self.current_column_count)

        self.tracks_grid_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum
        )

        self.scroll_area.add_widget(self.tracks_grid_widget)
        container_layout.addWidget(self.scroll_area)

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
            option_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            if callback_handler == self.on_about:
                self.version_button = option_button

            panel_layout.addWidget(option_button)

        panel.setStyleSheet(Styles.Other.Transparent)

        return panel

    # Update State

    def set_available_update(
            self,
            release_information: dict[str, object]
        ) -> None:

        self.cached_update_info = release_information

        if self.version_button is not None:
            self.version_button.setText("Update available")

    # Grid Dimension Management

    def calculate_optimal_column_count(self) -> int:
        viewport_width = self.scroll_area.viewport().width()

        if viewport_width <= 0:
            viewport_width = self.width() - 24

        calculated_columns = viewport_width // self.minimum_column_width_px

        return max(2, min(5, calculated_columns))

    def apply_column_stretches(self, column_count: int) -> None:
        for column_index in range(10):
            self.tracks_grid_layout.setColumnStretch(column_index, 0)

        for column_index in range(column_count):
            self.tracks_grid_layout.setColumnStretch(column_index, 1)

    # Search & Grid Layout

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
            for score, project_identifier, project_data in ranked_projects
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
            subtitle_text = f"- {project_data['model'] or ''} - {project_data.get('progress', 0.0)}%"

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
            track_item.project_deleted.connect(self.on_project_deleted)

            self.track_widgets[project_identifier] = track_item

        search_query = self.search_box.text() if self.search_box else ""
        self.apply_search_filter(search_query)

    def on_project_deleted(self) -> None:
        current_time = time.monotonic()
        self.project_deletion_times = [
            deletion_time
            for deletion_time in self.project_deletion_times
            if current_time - deletion_time <= 30.0
        ]
        self.project_deletion_times.append(current_time)

        if len(self.project_deletion_times) < 5 or not self.search_box:
            return

        self.search_box.setPlaceholderText("Creative crisis, I guess.")
        self.search_box.random_quote_enabled = False

    def apply_search_filter(self, search_text: str) -> None:
        for index in reversed(range(self.tracks_grid_layout.count())):
            layout_item = self.tracks_grid_layout.takeAt(index)
            grid_widget = layout_item.widget()

            if not grid_widget:
                continue

            grid_widget.hide()

        visible_projects = self.get_visible_projects(search_text)

        self.current_column_count = self.calculate_optimal_column_count()
        self.apply_column_stretches(self.current_column_count)

        for index, (project_identifier, _) in enumerate(visible_projects):
            row_index    = index // self.current_column_count
            column_index = index % self.current_column_count

            matched_widget = self.track_widgets.get(project_identifier)

            if not matched_widget:
                continue

            self.tracks_grid_layout.addWidget(matched_widget, row_index, column_index)
            matched_widget.show()

        self.scroll_area.raw_scroll_position = 0.0
        self.scroll_area.velocity_speed      = 0.0
        self.scroll_area.apply_content_position()
        self.scroll_area.update_canvas_geometry()

    def reset_search(self) -> None:
        if not self.search_box:
            return

        self.search_box.clear()

    # Focus Management

    def refocus_search_box(self) -> None:
        if not self.isVisible():
            return

        if not self.search_box:
            return

        if not self.search_box.isVisible():
            return

        active_modal_widget = QApplication.activeModalWidget()

        if active_modal_widget is not None:
            return

        active_window = QApplication.activeWindow()

        if active_window is not None and active_window is not self.window():
            return

        if not self.search_box.hasFocus():
            self.search_box.setFocus()

    # Events & Filtering

    def eventFilter(
            self,
            watched_object: QObject,
            event:          QEvent
        ) -> bool:

        if watched_object is not self.search_box:
            return super().eventFilter(watched_object, event)

        if event.type() == QEvent.Type.FocusIn and not self.isVisible():
            self.search_box.clearFocus()

            return True

        if event.type() == QEvent.Type.FocusOut:
            if not self.isVisible():
                return super().eventFilter(watched_object, event)

            focus_event = event

            if isinstance(focus_event, QFocusEvent):
                should_ignore_reason = focus_event.reason() in (
                    Qt.FocusReason.ActiveWindowFocusReason,
                    Qt.FocusReason.PopupFocusReason
                )

                if not should_ignore_reason and self.window().isActiveWindow():
                    QTimer.singleShot(0, self.refocus_search_box)

        return super().eventFilter(watched_object, event)

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)

        if not self.search_box:
            return

        self.search_box.clearFocus()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)

        if not self.isVisible():
            return

        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.refocus_search_box()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)

        if not self.isVisible():
            return

        self.refocus_search_box()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        new_column_count = self.calculate_optimal_column_count()

        if new_column_count == self.current_column_count:
            return

        search_query = self.search_box.text() if self.search_box else ""
        self.apply_search_filter(search_query)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reset_search()
        self.refresh_tracks()
        self.refocus_search_box()

    # Drag & Drop Events

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not self.drag_loop_sound:
            Player.ui_player.play_sound(
                "Controls/DragDrop/Drop",
                speed       = 1.1,
                setting_key = "drag_drop_sounds"
            )

            self.drag_loop_sound = Player.ui_player.play_sound(
                "Controls/DragDrop/Loop",
                loop        = True,
                setting_key = "drag_drop_sounds"
            )

        self.window_animator.scale_handle.set_target(0.97, 200)

        event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        if self.drag_loop_sound:
            Player.ui_player.play_sound(
                "Controls/DragDrop/Drop",
                speed       = 0.9,
                setting_key = "drag_drop_sounds"
            )

            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        self.window_animator.scale_handle.set_target(1.0, 200)

        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        self.window_animator.scale_handle.set_target(1.0, 160)

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
            Player.ui_player.play_sound("Alerts/Errors/MegaCritical")
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
            "Controls/DragDrop/Drop",
            speed       = 0.9,
            setting_key = "drag_drop_sounds"
        )

        self.process_new_composition(file_to_process)
        event.acceptProposedAction()

        super().dropEvent(event)

    # Actions & Dialogs

    # Actions & Dialogs

    def process_new_composition(
            self,
            file_path: str
        ) -> None:

        Player.player.emergency_stop(600)

        audio_dialog = Windows.AudioSetupDialog(file_path)

        if not audio_dialog.exec():
            return

        composition = ProjectSaver.Composition(
            file_path,
            audio_dialog.saved_settings
        )

        self.composition_created.emit(composition)


    def on_import(self) -> None:
        Player.player.emergency_stop(600)

        import_window = Windows.ImportWindow()

        if not import_window.exec():
            return

        composition = ProjectSaver.Composition(
            import_window.audio_path,
            import_window.saved_settings
        )

        self.composition_created.emit(composition)


    def on_edit_project(
            self,
            project_identifier: str
        ) -> None:

        Player.player.emergency_stop(600)

        self.setEnabled(False)
        self.edit_requested.emit(project_identifier)


    def on_audio_settings(
            self,
            project_identifier: str
        ) -> None:

        Player.player.emergency_stop(600)

        try:
            composition  = ProjectSaver.Composition(identifier = int(project_identifier))
            audio_window = Windows.ExistingAudioSetupDialog(composition)

            if not audio_window.exec():
                return

            self.refresh_tracks()

        except Exception as exception:
            Windows.ErrorWindow("Audio edit failed", str(exception)).exec()


    def on_glyphtone_editor(self) -> None:
        file_path = self.ask_for_file()

        if not file_path:
            return

        Player.player.emergency_stop(600)
        Windows.GlyphtoneEditor(file_path).exec()

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

        elif has_shift:
            Windows.ByteBeatWindow().exec()

            return

        elif has_alt:
            Windows.AboutWindow(more_information = True).exec()

            return

        Windows.AboutWindow(cached_update_information = self.cached_update_info).exec()

    def on_glyphtones(self) -> None:
        webbrowser.open("https://glyphtones.firu.dev/")

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