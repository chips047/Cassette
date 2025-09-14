import os
import json
import shutil
import random
import webbrowser

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from System import UI
from System import Utils
from System import Styles
from System import ProjectSaver

from System.Constants import *
from System.AudioSetupper import AudioSetupDialog

def get_projects_info(songs_folder):
    projects = {}
    
    os.makedirs(songs_folder, exist_ok=True)

    for project_name in os.listdir(songs_folder):
        project_path = os.path.join(songs_folder, project_name)
        if not os.path.isdir(project_path):
            continue

        audio_path = None
        json_file = None

        for file in os.listdir(project_path):
            if file.lower().endswith(('.mp3', '.wav', '.ogg', '.flac')):
                audio_path = os.path.join(project_path, file)
            
            elif file.lower().endswith('.json'):
                json_file = os.path.join(project_path, file)

        if audio_path and json_file:
            with open(json_file, 'r', encoding='utf-8') as f:
                try:
                    save_data = json.load(f)
                
                except Exception as e:
                    save_data = None

            try:
                projects[project_name] = {
                    "audio_path": audio_path,
                    "save": save_data,
                    "title": save_data["audio"]["title"],
                    "artist": save_data["audio"]["artist"],
                    "model": code_to_number_model(save_data["model"]),
                }
            
            except Exception:
                pass

    return projects

class TrackItemWidget(QWidget):
    edit_clicked = pyqtSignal(str)
    
    def __init__(self, project_id, title, artist, duration, progress_text, parent=None, main_menu=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        self.setFixedHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.project_id = project_id
        self.main_menu = main_menu

        bg_color = Styles.Colors.secondary_background

        self.bg_frame = QFrame(self)
        self.bg_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 30px;
            }}
        """)
        self.bg_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.bg_frame)

        content_layout = QVBoxLayout(self.bg_frame)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(5)

        top_layout = QHBoxLayout()
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setFont(Utils.NType(14))
        title_label.setStyleSheet(Styles.Other.font)

        artist_duration_label = QLabel(f"{artist}  {duration}")
        artist_duration_label.setFont(Utils.NType(11))
        artist_duration_label.setStyleSheet(Styles.Other.second_font)

        info_layout.addWidget(title_label)
        info_layout.addWidget(artist_duration_label)
        info_layout.addStretch()

        top_layout.addLayout(info_layout)
        top_layout.addStretch()

        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 20, 0, 0)
        
        icons_layout = QHBoxLayout()
        icons_layout.setSpacing(5)
        
        btn_delete = QPushButton(QIcon("System/Icons/Delete.png"), "")
        btn_edit = QPushButton(QIcon("System/Icons/Edit.png"), "")
        btn_export = QPushButton(QIcon("System/Icons/Save.png"), "")

        for btn in [btn_delete, btn_edit, btn_export]:
            btn.setFixedHeight(35)
            btn.setFixedWidth(66)
            btn.setIconSize(QSize(28, 28))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { background-color: #3a3a3a; border-radius: 14px; }
                QPushButton:hover { background-color: #4a4a4a; }
            """)
            icons_layout.addWidget(btn)
        
        btn_edit.clicked.connect(self.on_edit_clicked)
        btn_delete.clicked.connect(self.on_delete_clicked)
        btn_export.clicked.connect(self.on_export_clicked)

        bottom_layout.addLayout(icons_layout)
        bottom_layout.addStretch()

        content_layout.addLayout(top_layout)
        content_layout.addLayout(bottom_layout)
    
    def on_edit_clicked(self):
        self.edit_clicked.emit(self.project_id)
    
    def on_delete_clicked(self):
        dialog = UI.DialogWindow("Remove?")
        if dialog.exec_() == QDialog.Accepted:
            shutil.rmtree(Utils.get_songs_path(str(self.project_id)), ignore_errors = True)
            self.main_menu.refresh_tracks()
    
    def on_export_clicked(self):
        composition = ProjectSaver.MinimalComposition(self.project_id)
        
        dialog = UI.ExportDialogWindow("Export?", composition)
        if dialog.exec_() == QDialog.Accepted:
            composition.export()
            Utils.ui_sound("Export")

class MainMenu(QWidget):
    composition_created = pyqtSignal(object)

    def __init__(self, parent):
        super().__init__(parent)

        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet(f"""
            #container {{
                background-color: {Styles.Colors.background};
                border-radius: 40px;
            }}
        """)
        
        self.setup_ui()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.container)
    
    def refresh_tracks(self):
        while self.tracks_layout.count():
            item = self.tracks_layout.takeAt(0)
            widget = item.widget()
            
            if widget is not None:
                widget.setParent(None)

        self.tracks_widget = self.create_tracks_grid()
        self.tracks_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.tracks_layout.addWidget(self.tracks_widget, alignment=Qt.AlignTop)
    
    def on_edit_project(self, project_id):
        composition = ProjectSaver.Composition(
            id = project_id
        )
            
        self.composition_created.emit(composition)

    def on_new_composition(self):
        options = QFileDialog.Options()
        options |= QFileDialog.Option.ReadOnly
                    
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Open Audio File", "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.mp4);;All Files (*)", 
            options = options
        )
        
        if not file_path:
            return
        
        QApplication.processEvents() # to fix center issues

        dialog = AudioSetupDialog(file_path)
        if dialog.exec_() == QDialog.Accepted:
            Utils.ui_sound("MenuClose")
            settings = dialog.saved_settings
            
            composition = ProjectSaver.Composition(
                file_path,
                settings
            )
            
            self.composition_created.emit(composition)
    
    def go_to_glyphtones(self):
        webbrowser.open("https://glyphtones.firu.dev/")
    
    def go_to_github(self):
        github = "https://www.github.com/Chipik0/Cassette/releases/latest"
        if random.random() < 0.95:
            webbrowser.open(github) # lol
        
        else:
            fomx = Utils.get_fox_image()
            fomx = fomx # what
            fox = fomx
            foox = fox
            foks = foox

            if foks:
                webbrowser.open(foks)
            
            else:
                webbrowser.open(github)
    
    def center_on_parent(self):
        self.move(0, 0)

    def setup_ui(self):
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(15, 15, 15, 15)
        container_layout.setSpacing(15)

        card_style = f"""
            QFrame {{
                background-color: {Styles.Colors.secondary_background};
                border-radius: 25px;
            }}
        """

        title_container = QFrame()
        title_container.setStyleSheet(card_style)
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(25, 20, 25, 20)
        
        title_label = QLabel(
            Utils.get_time()
        )
        title_label.setFont(Utils.NType(24))
        title_label.setStyleSheet("background-color: transparent; color: #ffffff")
        title_layout.addWidget(title_label)
        
        container_layout.addWidget(title_container)

        button_container = QFrame()
        button_container.setStyleSheet(card_style)
        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(5, 5, 5, 5)
        
        button_panel = self.create_button_panel()
        button_layout.addWidget(button_panel)
        
        container_layout.addWidget(button_container)

        tracks_container = QFrame()
        self.tracks_layout = QVBoxLayout(tracks_container)
        self.tracks_layout.setContentsMargins(0, 0, 0, 0)

        tracks_widget = self.create_tracks_grid()
        tracks_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.tracks_layout.addWidget(tracks_widget, alignment=Qt.AlignTop)

        scroll_area = QScrollArea()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
                border-radius: 30px;
            }
            QScrollArea > QWidget > QWidget {
                border-radius: 30px;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #2b2b2b;
                width: 8px;
                margin: 0px 0px 0px 0px;
                border-radius: 30px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                min-height: 20px;
                border-radius: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        tracks_container.setStyleSheet("""
            QFrame {
                border-radius: 30px;
                background: transparent;
            }
        """)
        
        scroll_area.setWidget(tracks_container)
        container_layout.addWidget(scroll_area)

    def on_settings(self):
        settings_dialog = UI.Settings()
        settings_dialog.init_settings(SettingsDict)
        settings_dialog.exec_()
    
    def on_import(self):
        UI.ErrorWindow(
            "Lmao!", 
            "This feature is in development process."
        ).exec_()
    
    def on_about(self):
        UI.ErrorWindow(
            "Oh, hello.",
            f"The best compositor that is still in development.\n\n- Developed entirely by chips047\n- Version: {open('version').read()}\n- UI is inspired by R.E.P.O. game"
        ).exec_()

    def create_button_panel(self):
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        version = open("version").read()

        buttons_data = [
            ("New composition",  True,  "on_new_composition"),
            ("Import",           False, "on_import"),
            ("Go to glyphtones", False, "go_to_glyphtones"),
            ("Settings",         False, "on_settings"),
            ("About",            False, "on_about"),
            (version,            False, "go_to_github"),
        ]

        accent_style = f"""
            QPushButton {{
                background-color: {Styles.Colors.nothing_accent};
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 20px;
            }}
            QPushButton:hover {{
                background-color: {Styles.Colors.nothing_accent_hover};
            }}
        """

        default_style = """
            QPushButton {
                background-color: #333;
                color: #ccc;
                border: none;
                padding: 8px 15px;
                border-radius: 20px;
            }
            QPushButton:hover {
                background-color: #444;
            }
        """

        for text, is_accent, slot_name in buttons_data:
            btn = QPushButton(text)
            btn.setFont(Utils.NType(13))
            btn.setCursor(Qt.PointingHandCursor)

            btn.setStyleSheet(accent_style if is_accent else default_style)

            if hasattr(self, slot_name):
                btn.clicked.connect(getattr(self, slot_name))

            layout.addWidget(btn)
        
        panel.setStyleSheet("background-color: transparent;")
        return panel

    def create_tracks_grid(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setSpacing(15)
        layout.setContentsMargins(0, 0, 0, 0)
        
        tracks_data = get_projects_info(Utils.get_songs_path(""))
        tracks_data = [
            (project_id, data["title"], data["artist"], "- " + data["model"], f"{data['save']['progress']}% done.")
            for project_id, data in tracks_data.items()
        ]
        
        num_columns = 2
        for i, data in enumerate(tracks_data):
            row = i // num_columns
            col = i % num_columns
            track_item = TrackItemWidget(*data, main_menu = self)
            track_item.edit_clicked.connect(self.on_edit_project)
            layout.addWidget(track_item, row, col)
        
        return widget
    
    def showEvent(self, event):
        self.refresh_tracks()
        super().showEvent(event)