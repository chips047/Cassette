from __future__ import annotations

import os
import re

from PyQt6.QtCore import (
    Qt,
    QUrl,
    QTimer
)

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QSizePolicy
)

from PyQt6.QtMultimedia import (
    QAudioOutput,
    QMediaPlayer
)

from PyQt6.QtMultimediaWidgets import QVideoWidget

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Services import Player
from System.Interface import Widgets

from System.Interface.Windows.FloatingWindowGPU import FloatingWindowGPU

SETTING_PRANK_V1_SHOWN_KEY = "_prank_v1_shown"
SETTING_OG_USER_KEY        = "_is_og_user"

# Verification Helpers

def should_show_version_prank() -> bool:
    if Constants.current_settings.get(SETTING_PRANK_V1_SHOWN_KEY, False):
        return False

    version_file_path = Utils.get_resource_path("version")

    if not os.path.exists(version_file_path):
        return False

    with open(version_file_path, "r", encoding = "utf-8") as version_file:
        version_text = version_file.read().strip()

    version_numbers = [int(token) for token in re.findall(r"\d+", version_text)]

    if not version_numbers or version_numbers[0] < 1:
        return False

    is_og_user = Constants.current_settings.get(SETTING_OG_USER_KEY)

    if is_og_user is None:
        is_og_user = Constants.current_settings.get("_new_user") is False
        Constants.current_settings.set_value(SETTING_OG_USER_KEY, is_og_user)

    return bool(is_og_user)


def mark_version_prank_as_seen() -> None:
    Constants.current_settings.set_value(SETTING_PRANK_V1_SHOWN_KEY, True)


# Version Prank Window

class VersionPrankWindow(FloatingWindowGPU):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title                      = "Cassette v1.0",
            parent                     = parent,
            max_tilt_angle             = 12,
            enable_audioplayer_effects = False
        )

        self.current_stage         = 0
        self.video_playback_active = False

        self.setup_ui()
        self.setup_media_player()
        self.apply_stage_content(0)
        self.adjustSize()

    # Layout Setup

    def setup_ui(self) -> None:
        self.description_label = Widgets.DescriptionLabel("", 640)
        self.description_label.setMinimumWidth(560)

        self.footnote_label = Widgets.DescriptionLabel("* Just kidding.", 640)
        self.footnote_label.setVisible(False)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setFixedSize(560, 315)
        self.video_widget.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )
        self.video_widget.setVisible(False)

        self.action_button = Widgets.NothingButton("Next")
        self.action_button.setMinimumWidth(160)
        self.action_button.clicked.connect(self.handle_action_clicked)

        button_row_layout = QHBoxLayout()
        button_row_layout.addStretch()
        button_row_layout.addWidget(self.action_button)

        self.content_layout.addWidget(self.description_label)
        self.content_layout.addWidget(self.video_widget)
        self.content_layout.addWidget(self.footnote_label)
        self.content_layout.addLayout(button_row_layout)

    def setup_media_player(self) -> None:
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)

        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

    # Stage Transitions

    def apply_stage_content(self, stage_index: int) -> None:
        self.current_stage = stage_index

        if stage_index == 0:
            self.title_label.setText("Hello.")
            self.description_label.setText(
                "`Welcome to Cassette v1.0.`\n\n"
                "A major milestone in music and glyph synchronization. "
                "We have completely redesigned core systems, improved rendering performance, "
                "and introduced groundbreaking features.\n\n"
                "Take a quick look at what's new in this release."
            )
            self.footnote_label.setVisible(False)
            self.video_widget.setVisible(False)
            self.action_button.setText("Next")

        elif stage_index == 1:
            self.title_label.setText("Cassette AI*")
            self.description_label.setText(
                "`Meet Cassette AI*.`\n\n"
                "Harness the revolutionary next-generation neural matrix directly inside your timeline. "
                "Cassette AI autonomously predicts your glyph placements, dynamically synthesizes non-fungible "
                "polyphonic audio textures, optimizes composition synergies using multimodal neural reasoning, "
                "and transforms your creative workflow into an effortless prompt-driven cloud experience."
            )
            self.footnote_label.setVisible(True)
            self.video_widget.setVisible(False)
            self.action_button.setText("Next")

        elif stage_index == 2:
            self.title_label.setText("Telemetry")
            self.description_label.setText(
                "`We have added telemetry.`\n\n"
                "Warning: You can't disable it, because it helps me to continue the development.\n\n"
                "Every single mouse movement, key press, and session metric is securely relayed "
                "to our central processing cluster to guarantee peak ecosystem synergy."
            )
            self.footnote_label.setVisible(False)
            self.video_widget.setVisible(False)
            self.action_button.setText("Next")

        elif stage_index == 3:
            self.title_label.setText("The Future")
            self.description_label.setText("`Meet the new Cassette: clean AI experience.`")
            self.footnote_label.setVisible(False)
            self.video_widget.setVisible(True)
            self.action_button.setText("Play Video")

        elif stage_index == 4:
            self.title_label.setText("Just kidding.")
            self.description_label.setText(
                "`Just kidding. Let me tell you something:`\n\n"
                "Only OG users that used Cassette <1.0 version see this window.\n\n"
                "Thank you for being with me in this development journey."
            )
            self.footnote_label.setVisible(False)
            self.video_widget.setVisible(False)
            self.action_button.setText("Love you too <3")
            self.action_button.setEnabled(True)

        self.wobble()
        self.pulse_title(1.15, 200)

        QTimer.singleShot(0, self.adjustSize)

    # Action Handlers

    def handle_action_clicked(self) -> None:
        if self.current_stage in (0, 1):
            self.apply_stage_content(self.current_stage + 1)
            return

        if self.current_stage == 2:
            self.apply_stage_content(3)
            return

        if self.current_stage == 3:
            self.start_video_playback()
            return

        if self.current_stage == 4:
            mark_version_prank_as_seen()
            self.on_ok()

    # Video Playback

    def start_video_playback(self) -> None:
        if self.video_playback_active:
            return

        self.video_playback_active = True
        self.action_button.setEnabled(False)
        self.action_button.setText("Playing...")

        video_file_path = Utils.get_resource_path("System/Assets/Video/Rickroll.mp4")

        if os.path.exists(video_file_path):
            self.media_player.setSource(QUrl.fromLocalFile(video_file_path))
            self.media_player.play()

        else:
            Player.ui_player.play_sound(".vault/NOK/Gambling")

        QTimer.singleShot(5000, self.finish_video_playback)

    def finish_video_playback(self) -> None:
        self.media_player.stop()
        self.video_playback_active = False

        self.apply_stage_content(4)

    # Lifecycle Handlers

    def really_close(self) -> None:
        if self.media_player:
            self.media_player.stop()

        mark_version_prank_as_seen()
        super().really_close()