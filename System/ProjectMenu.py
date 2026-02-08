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

from loguru import logger

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
        
        else:
            logger.warning(f"Project '{project_name}' is missing audio or JSON file. Removing.")
            shutil.rmtree(project_path)
    
    return projects

class TrackItemWidget(QWidget):
    edit_clicked = pyqtSignal(str)
    
    def __init__(self, project_id, title, artist, duration, progress_text, parent=None, main_menu=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
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
        
        if dialog.exec_():
            shutil.rmtree(Utils.get_songs_path(str(self.project_id)), ignore_errors = True)
            QTimer.singleShot(0, self.main_menu.refresh_tracks)
    
    def on_export_clicked(self):
        composition = ProjectSaver.MinimalComposition(self.project_id)
        
        UI.ExportDialogWindow(
            "Export?",
            composition
        ).exec_()

class FadeScrollArea(QScrollArea):
    def __init__(self, fade_color=QColor("#000000"), fade_height=40, parent=None):
        super().__init__(parent)
        self.fade_color = fade_color if isinstance(fade_color, QColor) else QColor(fade_color)
        self.fade_height = fade_height
        
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.top_fade = FadeOverlay(self.fade_color, True, self)
        self.bottom_fade = FadeOverlay(self.fade_color, False, self)
        
        self.top_fade.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.bottom_fade.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.verticalScrollBar().valueChanged.connect(self.update_fade_visibility)
        self._animations = {}

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.viewport().width()
        
        self.top_fade.setGeometry(0, 0, w, self.fade_height)
        self.bottom_fade.setGeometry(0, self.height() - self.fade_height, w, self.fade_height)
        
        self.update_fade_visibility()

    def update_fade_visibility(self):
        val = self.verticalScrollBar().value()
        max_val = self.verticalScrollBar().maximum()
        
        self._animate_fade(self.top_fade, val > 0)
        self._animate_fade(self.bottom_fade, val < max_val)

    def _animate_fade(self, widget, show):
        target_opacity = 1.0 if show else 0.0
        current_opacity = widget._opacity

        if current_opacity == target_opacity:
            return

        if widget in self._animations:
            self._animations[widget].stop()

        animation = QPropertyAnimation(widget, b"opacity")
        animation.setDuration(175)
        animation.setStartValue(current_opacity)
        animation.setEndValue(target_opacity)
        
        if not show:
            animation.finished.connect(lambda: widget.hide())
        
        else:
            widget.show()
            
        animation.start()
        
        self._animations[widget] = animation

class FadeOverlay(QWidget):
    def __init__(self, color, is_top, parent=None):
        super().__init__(parent)
        self.color = color
        self.is_top = is_top
        self._opacity = 1.0
        
        self.setAttribute(Qt.WA_TranslucentBackground) 
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setOpacity(self._opacity) 
        
        grad = QLinearGradient(0, 0, 0, self.height())
        
        c_opaque = QColor(self.color)
        c_opaque.setAlpha(255)
        
        c_transparent = QColor(self.color)
        c_transparent.setAlpha(0)
        
        if self.is_top:
            grad.setColorAt(0, c_opaque)
            grad.setColorAt(1, c_transparent)
        
        else:
            grad.setColorAt(0, c_transparent)
            grad.setColorAt(1, c_opaque)
            
        painter.setBrush(QBrush(grad))
        painter.drawRect(self.rect())
    
    @pyqtProperty(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, opacity):
        self._opacity = opacity
        self.update()

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
                widget.deleteLater()

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
        file_path = None
    
        dialog = QFileDialog(
            self,
            "Open Audio File",
            "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.opus *.mp4 *.mkv *.mov);;All Files (*)"
        )
        
        dialog.setOptions(options)

        if dialog.exec_() == QFileDialog.Accepted:
            file_path = dialog.selectedFiles()[0]
        
        if not file_path:
            return
        
        QApplication.processEvents() # to fix center issues

        dialog = AudioSetupDialog(file_path)
        
        if not dialog.exec_():
            return
        
        settings = dialog.saved_settings
        
        composition = ProjectSaver.Composition(
            file_path,
            settings
        )
        
        self.composition_created.emit(composition)

    def go_to_glyphtones(self):
        webbrowser.open("https://glyphtones.firu.dev/")

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
        
        title_label = QLabel(Utils.get_time())
        title_label.setFont(Utils.NType(24))
        title_label.setStyleSheet("background-color: transparent; color: #ffffff;")
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

        bg_color = QColor(Styles.Colors.background) 
        self.scroll_area = FadeScrollArea(bg_color)
        
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
                border-radius: 30px;
            }
            QScrollBar:vertical {
                width: 0px; 
            }
        """)

        tracks_container.setStyleSheet("""
            QFrame {
                border-radius: 30px;
                background: transparent;
            }
        """)
        
        self.scroll_area.setWidget(tracks_container)
        container_layout.addWidget(self.scroll_area)
    
    def on_settings(self):
        settings_dialog = UI.Settings()
        settings_dialog.init_settings(SettingsDict)
        settings_dialog.exec_()
    
    def on_import(self):
        test = UI.ErrorWindow("Wait.", "This function is in development.", "I don't care")
        test.exec_()
    
    def on_about(self):
        dialog = UI.About()
        dialog.exec_()

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
            (version,            False, "on_about")
        ]

        accent_style = f"""
            QPushButton {{
                background-color: {Styles.Colors.nothing_accent};
                color: white;
                border: none;
                padding: 8px 15px;
                height: 30px;
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
                min-height: 30px;
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