import os
import math
import numpy
import random
import traceback
import mimetypes
import webbrowser

from loguru import logger
from collections.abc import Callable

from PyQt5.QtGui import (
    QIcon,
    QCursor,
    QPixmap,
    QMatrix4x4,
    QQuaternion,
    QWheelEvent,
    QResizeEvent,
    QSurfaceFormat
)

from PyQt5.QtCore import (
    Qt,
    QRect,
    QSize,
    QPoint,
    QTimer,
    QObject,
    QThread,
    QSettings,
    QEventLoop,
    pyqtSignal,
    QElapsedTimer
)

from PyQt5.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QFileDialog,
    QApplication,
    QOpenGLWidget,
    QStackedWidget,
    QGraphicsOpacityEffect
)

from OpenGL import GL
from OpenGL.GL import shaders

from System.Common import (
    Utils,
    Styles
)

from System.Common.Constants import (
    FPS_30,
    FPS_60,
    DEVICES,
    GLYPH_FS,
    GLYPH_VS,
    GITHUB_LINK,
    load_settings,
    VISUAL_EASINGS,
    NUMBER_TO_CODE,
    CURRENT_SETTINGS,
    FLOATING_WINDOW_FS,
    FLOATING_WINDOW_VS
)

from System.Services import (
    Audio,
    Player,
    Encoder
)

from System.Interface import (
    Basic,
    Inputs,
    Widgets
)

from System.Services import ProjectSaver
from System.Interface.Animation import LoomEngine

# Helpers

def build_column(
        title:   str,
        widgets: list[QWidget]
    ) -> QVBoxLayout:

    column = QVBoxLayout()
    column.addWidget(Basic.DescriptionLabel(title))

    for widget in widgets:
        column.addWidget(widget)

    column.addStretch()
    return column

def make_time_textbox() -> Inputs.Textbox:
    textbox = Inputs.Textbox(":time", max_length = 5)
    textbox.setStyleSheet(Styles.Controls.FloatingTextBox)
    textbox.setFixedHeight(40)
    textbox.setFixedWidth(70)
    
    return textbox

def make_fade_textbox(placeholder: str) -> Inputs.Textbox:
    textbox = Inputs.Textbox("number", 0, 5000, placeholder = placeholder)
    textbox.setStyleSheet(Styles.Controls.FloatingTextBox)
    textbox.setFixedHeight(40)
    
    return textbox

# Core Window

class FloatingWindowGPU(QOpenGLWidget):
    shared_shader_program = None

    def __init__(
            self,
            title:                           str,
            parent:                          QWidget                | None = None,
            margin:                          int                    | None = None,
            dialog:                          bool                          = True,
            stays_on_top:                    bool                          = True,
            bpm:                             int                    | None = None,
            player:                          Player.PlaybackManager        = None,
            max_tilt_angle:                  int                           = 20,
            animation_style:                 str                    | None = None,
            enable_audioplayer_effects:      bool                          = True,
            enable_advanced_beat_animations: bool                          = False,
            enable_tilt:                     bool                          = True,
            enable_open_animation:           bool                          = True,
            enable_close_animation:          bool                          = True,
            start_position:                  QPoint                 | None = None
        ):

        super().__init__(parent)

        self.bpm                   = bpm
        self.player                = player
        self.enable_tilt           = enable_tilt
        self.max_tilt_angle        = max_tilt_angle

        self.result                = None
        self.event_loop            = None
        self.allow_exit            = False
        self.drag_pos              = None
        self.is_ready              = False
        self.is_closing            = False
        self.was_cancelled         = False
        self.start_position        = start_position

        self.animation_style       = animation_style or CURRENT_SETTINGS["animation_style"]

        self.enable_open_animation              = enable_open_animation
        self.enable_close_animation             = enable_close_animation
        self.enable_advanced_beat_animations    = enable_advanced_beat_animations
        self.enable_transition_audio_effects    = enable_audioplayer_effects

        self.margin_x = margin or 300
        self.margin_y = margin or 300

        self.tilt_animation_timer = None
        self.bpm_timer            = None
        self.anim_group           = None

        self.prepare_fmt()
        self.apply_attributes(dialog, stays_on_top)
        self.setup_layout(title)
        self.setup_animation_properties()
        self.setup_timers()

        if self.enable_open_animation:
            QTimer.singleShot(0, self.start_open_animation)

    # Setup

    def prepare_fmt(self) -> None:
        surface_format = QSurfaceFormat()
        
        surface_format.setVersion(4, 1)
        surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        surface_format.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions, False)

        if CURRENT_SETTINGS.get("msaa"):
            surface_format.setSamples(CURRENT_SETTINGS["msaa"])

        self.setFormat(surface_format)

    def apply_attributes(
            self,
            dialog:       bool,
            stays_on_top: bool
        ) -> None:

        flags = self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint

        if dialog:
            flags |= Qt.Dialog
        
        else:
            flags |= Qt.Tool

        if stays_on_top:
            flags |= Qt.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_PaintOnScreen, False)

    def setup_layout(self, title: str) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(self.margin_x, self.margin_y, self.margin_x, self.margin_y)
        main_layout.setSpacing(0)

        self.content_widget = QWidget(self)
        self.content_widget.setAttribute(Qt.WA_TranslucentBackground)

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(15)

        main_layout.addWidget(self.content_widget)

        if title:
            self.title_label = Basic.TitleLabel(title)
            self.content_layout.addWidget(self.title_label)
        
        else:
            self.title_label = None

        self.adjustSize()

    def setup_animation_properties(self) -> None:
        self.close_attempt_count = 0

        self.scale               = 1.0
        self.rotation            = QQuaternion()
        self.rotation_x          = 0.0
        self.rotation_y          = 0.0
        self.rotation_z          = 0.0
        self.current_tilt_x      = 0.0
        self.current_tilt_y      = 0.0
        self.target_tilt_x       = 0.0
        self.target_tilt_y       = 0.0
        self.opacity_content     = 1.0
        self.opacity_background  = 1.0
        self.x_offset            = 0.0
        self.y_offset            = 0.0
        self.z_offset            = 0.0
        self.tilt_smoothing      = float(CURRENT_SETTINGS["window_hover_smoothing"])
        self.bpm_peak_scale      = 1.03

        if not self.animations_enabled:
            logger.debug("Not creating the animator since the animations are disabled")
            return

        self.content_opacity_effect = QGraphicsOpacityEffect(self.content_widget)
        self.content_opacity_effect.setOpacity(0.0)
        self.content_widget.setGraphicsEffect(self.content_opacity_effect)

        self.animation_engine = LoomEngine.AnimationEngine("pyqt5", 120)
        self.animation_engine.set_multiplier(float(CURRENT_SETTINGS["animation_multiplier"]))

        properties = [
            ("rotation_x",          0.0,     LoomEngine.MixMode.ADD,      self.sync_rotation_x),
            ("rotation_y",          0.0,     LoomEngine.MixMode.ADD,      self.sync_rotation_y),
            ("rotation_z",          0.0,     LoomEngine.MixMode.ADD,      self.sync_rotation_z),
            ("scale",               1.0,     LoomEngine.MixMode.MULTIPLY, self.sync_scale),
            ("opacity_background",  1.0,     LoomEngine.MixMode.MULTIPLY, self.sync_opacity_background),
            ("opacity_content",     1.0,     LoomEngine.MixMode.MULTIPLY, self.sync_opacity_content),
            ("x_offset",            0.0,     LoomEngine.MixMode.ADD,      self.sync_x_offset),
            ("y_offset",            0.0,     LoomEngine.MixMode.ADD,      self.sync_y_offset),
            ("z_offset",            0.0,     LoomEngine.MixMode.ADD,      self.sync_z_offset),
            ("title_scale",         1.0,     LoomEngine.MixMode.MULTIPLY, self.sync_title_scale),
            ("title_rotation",      0.0,     LoomEngine.MixMode.ADD,      self.sync_title_rotation),
            ("geometry",            QRect(), LoomEngine.MixMode.NOMIX,    self.setGeometry)
        ]

        self.animation_engine.add_properties(properties)
        self.animation_engine.updated.connect(self.update)

    def sync_rotation_x(self, value: float) -> None:
        self.rotation_x = value

    def sync_rotation_y(self, value: float) -> None:
        self.rotation_y = value

    def sync_rotation_z(self, value: float) -> None:
        self.rotation_z = value
    
    def sync_scale(self, value: float) -> None:
        self.scale = value
    
    def sync_opacity_content(self, value: float) -> None:
        self.opacity_content = value
        self.content_opacity_effect.setOpacity(self.opacity_content)
    
    def sync_opacity_background(self, value: float) -> None:
        self.opacity_background = value
    
    def sync_x_offset(self, value: float) -> None:
        self.x_offset = value
    
    def sync_y_offset(self, value: float) -> None:
        self.y_offset = value
    
    def sync_z_offset(self, value: float) -> None:
        self.z_offset = value
    
    def sync_title_scale(self, value: float) -> None:
        if self.title_label:
            self.title_label.scale = value
    
    def sync_title_rotation(self, value: float) -> None:
        if self.title_label:
            self.title_label.rotation = value

    def setup_timers(self) -> None:
        if self.animations_enabled and self.enable_tilt and self.tilt_smoothing > 0:
            self.tilt_animation_timer = Basic.Timer(
                FPS_60,
                self.tilt_rotation_update,
                parent = self
            )

            self.tilt_animation_timer.start()

        if self.bpm_animations_enabled:
            if self.enable_advanced_beat_animations:
                self.player.beat_heavy.connect(self.beat_heavy_animation)
                self.player.beat_normal.connect(self.beat_normal_animation)
            
            else:
                self.bpm_timer = Basic.Timer(
                    FPS_30,
                    self.bpm_tick_animation,
                    single_shot = True,
                    parent = self
                )

                if self.bpm:
                    self.bpm_timer.start(FPS_30)

    # Properties

    @property
    def animations_enabled(self) -> bool:
        return CURRENT_SETTINGS.get("floating_window_animations", True)

    @property
    def bpm_animations_enabled(self) -> bool:
        return self.animations_enabled and CURRENT_SETTINGS.get("bpm_animations", True) and self.player is not None

    # Animations

    def animation_title_scale(
            self,
            peak_scale: float = 1.2,
            duration:   int   = 100
        ) -> None:

        if not self.animations_enabled or not self.animation_engine:
            return

        self.animation_engine.animate(
            "title_scale",
            [
                (0.0, 1.0),
                (0.5, peak_scale),
                (1.0, 1.0)
            ],
            duration,
            LoomEngine.Easing.ease_out_cubic,
            do_not_multiply_duration = True
        )

    def animate_resize(
            self,
            target_width:  int,
            target_height: int
        ) -> None:

        self.animation_engine.set_target_value(
            "geometry",
            QRect(
                self.x(), self.y(),
                target_width  + self.margin_x,
                target_height + self.margin_y
            ),
            500,
            LoomEngine.Easing.ease_out_cubic
        )

    def animation_open_classic(
            self,
            final_rect,
            size: tuple[int, int]
        ) -> None:
        
        self.animation_engine.animate(
            "y_offset",
            [
                (0.0, -0.2),
                (1.0, 0.0)
            ],
            500,
            LoomEngine.Easing.bouncy
        )

        self.animation_engine.set_property_base_value("opacity_content",    1.0)
        self.animation_engine.set_property_base_value("opacity_background",  1.0)

    def animation_close_classic(self, size: tuple[int, int]) -> None:
        self.animation_engine.animate(
            "y_offset",
            [
                (0.0, 0.0),
                (1.0, 0.1)
            ],
            300,
            LoomEngine.Easing.ease_out_cubic
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            100
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            100, finished = self.really_close
        )

    def animation_open_smooth(
            self,
            final_rect,
            size: tuple[int, int]
        ) -> None:
        
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 30),
                (1.0, 0)
            ],
            800,
            LoomEngine.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, self.maximum_scale()),
                (1.0, 1.0)
            ],
            650,
            LoomEngine.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            250
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            200
        )

    def animation_close_smooth(self, size: tuple[int, int]) -> None:
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 0),
                (1.0, -30)
            ],
            500,
            LoomEngine.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, self.maximum_scale())
            ],
            500,
            LoomEngine.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            300
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            500, finished = self.really_close
        )

    def animation_open_bouncy(
            self,
            final_rect,
            size: tuple[int, int]
        ) -> None:

        start_angle                    = self.period_randomizer((-75, -20), (20, 75))
        start_offset_x, start_offset_y = self.get_optimal_offset(*size)
        optimal_tilt                   = self.get_optimal_tilt(*size)
        optimal_tilt                   = -optimal_tilt if random.random() < 0.5 else optimal_tilt

        self.animation_engine.animate(
            "x_offset",
            [
                (0.0, start_offset_x),
                (1.0, 0.0)
            ],
            950, LoomEngine.Easing.bouncy
        )

        self.animation_engine.animate(
            "y_offset",
            [
                (0.0, start_offset_y),
                (1.0, 0.0)
            ],
            950, LoomEngine.Easing.bouncy
        )

        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, start_angle),
                (1.0, 0)
            ],
            700, LoomEngine.Easing.very_bouncy
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            600, LoomEngine.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            800, LoomEngine.Easing.ease_out_expo
        )

    def animation_close_bouncy(self, size: tuple[int, int]) -> None:
        end_angle = self.period_randomizer((-55, -20), (20, 55))

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, self.maximum_scale())
            ],
            400, LoomEngine.Easing.ease_out_cubic
        )

        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0.0),
                (1.0, end_angle)
            ],
            500, LoomEngine.Easing.ease_out_cubic
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            200
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            450, finished = self.really_close
        )

    def animation_open_roll(
            self,
            final_rect,
            size: tuple[int, int]
        ) -> None:
        
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 150),
                (1.0, 0)
            ],
            800, LoomEngine.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            600, LoomEngine.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            300
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            200
        )

    def animation_close_roll(self, size: tuple[int, int]) -> None:
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 0),
                (1.0, 70)
            ],
            800, LoomEngine.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            350, LoomEngine.Easing.ease_in_quad
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            400
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            700, finished = self.really_close
        )

    def animation_open_glitch(
            self,
            final_rect,
            size: tuple[int, int]
        ) -> None:
        
        self.animation_engine.set_property_base_value("opacity_content",    0.0)
        self.animation_engine.set_property_base_value("opacity_background", 0.0)

        actions = [
            (150, "scale",              random.uniform(0.1, 0.4)),
            (270, "scale",              random.uniform(0.7, 0.85)),
            (485, "scale",              1.0),
            (150, "opacity_content",    random.uniform(0.2, 0.5)),
            (270, "opacity_content",    random.uniform(0.5, 0.8)),
            (485, "opacity_content",    1.0),
            (150, "opacity_background", random.uniform(0.2, 0.5)),
            (270, "opacity_background", random.uniform(0.5, 0.8)),
            (485, "opacity_background", 1.0),
            (150, "rotation_z",         random.randint(-30, 30)),
            (270, "rotation_z",         random.randint(-10, 10)),
            (485, "rotation_z",         0.0)
        ]

        self.plan_timers(actions)

    def animation_close_glitch(self, size: tuple[int, int]) -> None:
        actions = [
            (400, "scale",              random.uniform(0.1, 0.4)),
            (570, "scale",              0.0),
            (400, "opacity_content",    random.uniform(0.2, 0.5)),
            (570, "opacity_content",    0.0),
            (400, "opacity_background", random.uniform(0.2, 0.5)),
            (570, "opacity_background", 0.0),
            (400, "rotation_z",         random.randint(-10, 10)),
            (570, "rotation_z",         random.randint(-40, 40)),
        ]

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 0.8)
            ],
            210,
            LoomEngine.Easing.ease_out_cubic,
            do_not_multiply_duration = True
        )

        QTimer.singleShot(580, self.really_close)
        self.plan_timers(actions)

    def bpm_tick_animation(self) -> None:
        if not self.player.is_playing:
            self.bpm_timer.start(FPS_30)
            return

        audio_level = self.player.get_current_audio_level()

        if audio_level < 0.08:
            self.bpm_timer.start(FPS_30)
            return

        speed       = self.player.speed or 0.01
        interval_ms = int(round(60000.0 / (self.bpm * speed)))

        QApplication.setCursorFlashTime(interval_ms)

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, self.bpm_peak_scale + self.squish(audio_level)),
                (1.0, 1.0)
            ],
            interval_ms,
            LoomEngine.Easing.ease_out_cubic,
            do_not_multiply_duration = True
        )

        self.bpm_timer.start(interval_ms)

    def beat_normal_animation(self, strength: float) -> None:
        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0.0),
                (0.5, strength * (5 if random.random() > 0.5 else -5)),
                (1.0, 0.0)
            ],
            1500,
            LoomEngine.Easing.bouncy
        )

    def beat_heavy_animation(self, strength: float) -> None:
        if not self.animations_enabled or not self.animation_engine:
            return

        self.animation_engine.animate(
            "y_offset",
            [
                (0.0, 0.0),
                (0.5, strength * random.choice([0.1, -0.1])),
                (1.0, 0.0)
            ],
            400,
            LoomEngine.Easing.ease_out_cubic,
            do_not_multiply_duration = True
        )

    def move_start_animation(self) -> None:
        if not CURRENT_SETTINGS["floating_window_animations"]:
            return

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 1.03)
            ],
            250,
            LoomEngine.Easing.ease_out_cubic
        )

        self.animation_title_scale(1.15, 500)

    def move_end_animation(self) -> None:
        if not CURRENT_SETTINGS["floating_window_animations"]:
            return

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 0.97)
            ],
            400,
            LoomEngine.Easing.ease_out_cubic
        )

    def wobble(self) -> None:
        if not CURRENT_SETTINGS["floating_window_animations"]:
            return

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, 1.05),
                (1.0, 1.0)
            ],
            500,
            LoomEngine.Easing.ease_out_cubic
        )

    def animation_disturbe_bouncy(self) -> None:
        start_angle = random.choice(
            [
                random.randint(-20, -10),
                random.randint(10, 20)
            ]
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, 1.3),
                (1.0, 1.0)
            ],
            500,
            LoomEngine.Easing.ease_out_cubic
        )

        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0.0),
                (0.5, start_angle),
                (1.0, 0.0)
            ],
            1000,
            LoomEngine.Easing.bouncy
        )

    def animation_disturbe_roll(self) -> None:
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 0.0),
                (0.5, 20),
                (1.0, 0.0)
            ],
            1100,
            LoomEngine.Easing.bouncy
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, 1.1),
                (1.0, 1.0)
            ],
            1200,
            LoomEngine.Easing.bouncy
        )

    def animation_disturbe_classic(self) -> None:
        angle = self.period_randomizer((-30, -15), (15, 30))

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, 1.05),
                (1.0, 1.0)
            ],
            320
        )

        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0.0),
                (0.5, angle),
                (1.0, 0.0)
            ],
            900,
            LoomEngine.Easing.very_bouncy
        )

    def animation_disturbe_glitch(self) -> None:
        actions = [
            (5,  "scale",      random.uniform(1.02, 1.1)),
            (80, "scale",      1.0),
            (5,  "rotation_z", random.randint(-30, 30)),
            (80, "rotation_z", 0)
        ]

        self.plan_timers(actions)

    def animation_disturbe_smooth(self) -> None:
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 0.0),
                (0.5, 30),
                (1.0, 0.0)
            ],
            600,
            LoomEngine.Easing.ease_out_expo
        )

    def animation_random_rotate(self) -> None:
        if not CURRENT_SETTINGS["floating_window_animations"]:
            return

        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0),
                (0.5, self.period_randomizer((-6, -3), (3, 6))),
                (1.0, 0)
            ],
            350,
            LoomEngine.Easing.ease_out_cubic
        )

    def start_exit_animation(self) -> None:
        if not self.enable_close_animation:
            return

        if not CURRENT_SETTINGS["floating_window_animations"]:
            self.really_close()
            return

        size = self.get_window_size()

        {
            "bouncy":  self.animation_close_bouncy,
            "smooth":  self.animation_close_smooth,
            "roll":    self.animation_close_roll,
            "glitch":  self.animation_close_glitch,
            "classic": self.animation_close_classic
        }.get(self.animation_style)(size)

    def start_disturbe_animation(self) -> None:
        self.disturbe_sound()

        if not CURRENT_SETTINGS["floating_window_animations"]:
            return

        {
            "bouncy":  self.animation_disturbe_bouncy,
            "smooth":  self.animation_disturbe_smooth,
            "roll":    self.animation_disturbe_roll,
            "glitch":  self.animation_disturbe_glitch,
            "classic": self.animation_disturbe_classic
        }.get(self.animation_style)()

    def start_open_animation(self) -> None:
        self.adjustSize()
        final_rect = self.center_window()
        self.is_ready = True
        self.open_sound()

        size = self.get_window_size()

        if not CURRENT_SETTINGS["floating_window_animations"]:
            return

        {
            "bouncy":  self.animation_open_bouncy,
            "smooth":  self.animation_open_smooth,
            "roll":    self.animation_open_roll,
            "glitch":  self.animation_open_glitch,
            "classic": self.animation_open_classic
        }.get(self.animation_style)(final_rect, size)

    # Physics

    def tilt_rotation_update(self) -> None:
        global_pos          = QCursor.pos()
        local_pos           = self.mapFromGlobal(global_pos)
        center_x            = self.width() / 2
        center_y            = self.height() / 2

        widget_rect         = self.content_widget.rect()
        top_left_global     = self.content_widget.mapToGlobal(widget_rect.topLeft())
        content_rect_global = QRect(top_left_global, widget_rect.size())

        if content_rect_global.contains(global_pos):
            x_norm = -(local_pos.x() - center_x) / center_x
            y_norm =  (local_pos.y() - center_y) / center_y

            self.target_tilt_x = y_norm * self.max_tilt_angle
            self.target_tilt_y = -x_norm * self.max_tilt_angle

        self.current_tilt_x += (self.target_tilt_x - self.current_tilt_x) * self.tilt_smoothing
        self.current_tilt_y += (self.target_tilt_y - self.current_tilt_y) * self.tilt_smoothing

    # Render

    def initializeGL(self) -> None:
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClearColor(0, 0, 0, 0)

        if not self.shared_shader_program:
            vertex_shader   = shaders.compileShader(FLOATING_WINDOW_VS, GL.GL_VERTEX_SHADER)
            fragment_shader = shaders.compileShader(FLOATING_WINDOW_FS, GL.GL_FRAGMENT_SHADER)
            
            self.__class__.shared_shader_program = shaders.compileProgram(
                vertex_shader,
                fragment_shader,
                validate = False
            )

        vertices = numpy.array(
            [
                1.0,  1.0, 0.0, 1.0, 1.0,
                1.0, -1.0, 0.0, 1.0, 0.0,
                -1.0, -1.0, 0.0, 0.0, 0.0,
                -1.0,  1.0, 0.0, 0.0, 1.0
            ], dtype = numpy.float32
        )

        indices = numpy.array([0, 1, 3, 1, 2, 3], dtype = numpy.uint32)

        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)
        self.ebo = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.vao)

        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STATIC_DRAW)

        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL.GL_STATIC_DRAW)

        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 20, GL.ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 20, GL.ctypes.c_void_p(12))
        GL.glEnableVertexAttribArray(1)

        GL.glBindVertexArray(0)

        self.location_size         = GL.glGetUniformLocation(self.shared_shader_program, "u_size")
        self.location_radius       = GL.glGetUniformLocation(self.shared_shader_program, "u_radius")
        self.location_border_px    = GL.glGetUniformLocation(self.shared_shader_program, "u_borderThicknessPixels")
        self.location_rect_color   = GL.glGetUniformLocation(self.shared_shader_program, "u_rectColor")
        self.location_border_color = GL.glGetUniformLocation(self.shared_shader_program, "u_borderColor")
        self.location_rect_alpha   = GL.glGetUniformLocation(self.shared_shader_program, "u_rectAlpha")
        self.location_border_alpha = GL.glGetUniformLocation(self.shared_shader_program, "u_borderAlpha")
        self.location_global_alpha = GL.glGetUniformLocation(self.shared_shader_program, "u_globalAlpha")
        self.location_mvp          = GL.glGetUniformLocation(self.shared_shader_program, "u_curr_mvp")

    def paintGL(self) -> None:
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glUseProgram(self.shared_shader_program)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)

        content_rect    = self.content_widget.geometry()
        content_width   = float(content_rect.width())
        content_height  = float(content_rect.height())

        if content_width < 1 or content_height < 1:
            return

        mvp_final = self.calculate_matrix()

        GL.glUniform2f(self.location_size,         content_width, content_height)
        GL.glUniform1f(self.location_radius,        16.0)
        GL.glUniform1f(self.location_border_px,     2.0)
        GL.glUniform4f(self.location_rect_color,    0.17, 0.17, 0.17, 1.0)
        GL.glUniform4f(self.location_border_color,  0.25, 0.25, 0.25, 1.0)
        GL.glUniform1f(self.location_rect_alpha,    self.opacity_background)
        GL.glUniform1f(self.location_border_alpha,  self.opacity_background)
        GL.glUniform1f(self.location_global_alpha,  1.0)

        GL.glUniformMatrix4fv(self.location_mvp, 1, GL.GL_FALSE, mvp_final.data())

        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)

    def calculate_matrix(
            self,
            content_w: float | None = None,
            content_h: float | None = None
        ) -> QMatrix4x4:
        
        content_w = content_w or self.content_widget.width()
        content_h = content_h or self.content_widget.height()

        mvp    = QMatrix4x4()
        fov    = 45.0
        z_dist = 3.0
        aspect = self.width() / self.height()

        mvp.perspective(fov, aspect, 0.1, 100.0)
        mvp.translate(0.0, 0.0, -z_dist)

        visible_height_at_z = 2.0 * math.tan(math.radians(fov / 2.0)) * z_dist
        pixel_unit          = visible_height_at_z / self.height()

        if self.animations_enabled:
            rotation = QQuaternion.fromEulerAngles(
                self.rotation_x + self.current_tilt_x,
                self.rotation_y + self.current_tilt_y,
                self.rotation_z
            )

            mvp.rotate(rotation)
            mvp.translate(self.x_offset, self.y_offset, self.z_offset)
            mvp.scale(self.scale)

        mvp.scale((content_w * pixel_unit) / 2.0, (content_h * pixel_unit) / 2.0)
        return mvp

    # Events

    def closeEvent(self, event) -> None:
        if self.allow_exit:
            super().closeEvent(event)
            return

        self.close_attempt_count += 1

        if random.random() < 0.5:
            if self.close_attempt_count == 50:
                Player.ui_player.play_sound("Packs/NOK/WAYD")

                if self.title_label:
                    self.title_label.setText("What are you doing?")

            if self.close_attempt_count == 70:
                Player.ui_player.play_sound("Packs/NOK/HCYLWY")

                if self.title_label:
                    self.title_label.setText("???")

            if self.close_attempt_count > 70:
                self.chaos_mode()

            if self.close_attempt_count == 100 and self.title_label:
                Player.ui_player.play_sound("Packs/NOK/ONYD")
                self.title_label.setText("Dividing by zero: 3")

                QTimer.singleShot(1000, lambda: self.title_label.setText("Dividing by zero: 2"))
                QTimer.singleShot(2000, lambda: self.title_label.setText("Dividing by zero: 1"))
                QTimer.singleShot(2100, lambda: Player.ui_player.play_sound("Packs/NOK/Charging"))
                QTimer.singleShot(2500, lambda: self.title_label.setText("LMAO"))
                QTimer.singleShot(3000, lambda: 1 / 0)

        event.ignore()
        self.start_disturbe_animation()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        if self.title_label:
            label_rect = self.title_label.geometry()
            local_pos  = self.content_widget.mapFrom(self, event.pos())

            if not label_rect.contains(local_pos):
                return
        
        else:
            if not self.content_widget.geometry().contains(event.pos()):
                return

        self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        self.move_start_animation()
        
        QTimer.singleShot(0, self.window().windowHandle().startSystemMove)
        
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self.drag_pos:
            self.move_end_animation()

        self.drag_pos = None

    # Utils

    def get_optimal_tilt(
            self,
            width,
            height
        ):
        
        coeff_w = 900 / width
        coeff_h = 900 / height

        tilt = int((coeff_h + coeff_w) * 7)

        return tilt

    def get_optimal_offset(
            self,
            width:  int,
            height: int,
            limit:  int = 500
        ) -> tuple[float, float]:
        
        scale_x = limit / max(width,  limit)
        scale_y = limit / max(height, limit)

        start_offset_x = self.period_randomizer(
            (-0.35 * scale_x, -0.2 * scale_x),
            ( 0.2  * scale_x,  0.35 * scale_x)
        )

        start_offset_y = self.period_randomizer(
            (-0.5 * scale_y, -0.2 * scale_y),
            ( 0.2 * scale_y,  0.5  * scale_y)
        )

        return start_offset_x, start_offset_y

    def chaos_mode(self) -> None:
        for widget in self.content_widget.findChildren(QWidget):
            delta_x    = random.randint(-10, 10)
            delta_y    = random.randint(-10, 10)
            delta_size = random.randint(-10, 10)

            widget.move(widget.x() + delta_x, widget.y() + delta_y)
            widget.resize(widget.width() + delta_size, widget.height() + delta_size)

    def plan_timers(self, actions: list[tuple]) -> None:
        for delay, attribute, value in actions:
            QTimer.singleShot(
                delay,
                lambda a = attribute, v = value: self.animation_engine.set_property_base_value(a, v)
            )

    def on_ok(self) -> None:
        if self.is_closing:
            return

        self.is_closing    = True
        self.was_cancelled = False

        self.close_sound()
        self.start_exit_animation()

    def on_cancel(self) -> None:
        if self.is_closing:
            return

        self.is_closing    = True
        self.was_cancelled = True

        self.close_sound()
        self.start_exit_animation()

    def adjustSize(self) -> None:
        if not self.is_ready:
            super().adjustSize()
            return

        size = self.content_widget.sizeHint()
        self.animate_resize(size.width(), size.height())

    def update_bpm(self, bpm: int | None = None) -> None:
        if not bpm:
            return

        if bpm >= 200:
            self.bpm = int(bpm / 2)

        elif bpm <= 80:
            self.bpm = int(bpm * 2)

        else:
            self.bpm = int(bpm)

        if self.bpm_animations_enabled and not self.enable_advanced_beat_animations:
            self.bpm_timer.setInterval(60000 // self.bpm)
            self.bpm_timer.start()

    def set_bpm_peak_size(self, coefficient: float) -> None:
        self.bpm_peak_scale = coefficient

    def period_randomizer(self, *periods) -> int | float:
        function = random.uniform if isinstance(periods[0][0], float) else random.randint
        return function(*random.choice(periods))

    def center_window(self) -> QRect:
        if self.start_position:
            final_rect = QRect(
                self.start_position.x() - self.margin_x,
                self.start_position.y() - self.margin_y,
                self.width(),
                self.height()
            )
            
            self.setGeometry(final_rect)
            
            return final_rect

        window        = QApplication.activeWindow()
        window_center = window.geometry().center() if window else QApplication.primaryScreen().geometry().center()

        final_rect = QRect(
            window_center.x() - self.width()  // 2,
            window_center.y() - self.height() // 2,
            self.width(), self.height()
        )
        
        self.setGeometry(final_rect)
        
        return final_rect

    def player_pulse(
            self,
            duration:         int   = 300,
            pulse_peak_speed: float = 1.2
        ) -> None:
        
        start_speed   = self.player.speed
        duration_half = int(duration / 2)

        self.player.set_speed(pulse_peak_speed, duration_half)
        
        QTimer.singleShot(
            duration_half,
            lambda: self.player.set_speed(start_speed, duration_half)
        )

    def open_sound(self) -> None:
        if self.enable_transition_audio_effects and self.player and self.player.is_playing:
            self.player_pulse()
            return

        Player.ui_player.play_sound({
            "bouncy":  "Packs/Bouncy/Open",
            "smooth":  "Packs/Smooth/Open",
            "roll":    "Packs/Smooth/Open",
            "glitch":  "Packs/Glitch/Open",
            "classic": "Packs/Classic/Open"
        }.get(self.animation_style))

    def close_sound(self) -> None:
        if self.enable_transition_audio_effects and self.player and self.player.is_playing:
            self.player_pulse(400, 0.5)
            return

        Player.ui_player.play_sound({
            "bouncy":  "Packs/Bouncy/Close",
            "smooth":  "Packs/Smooth/Close",
            "roll":    "Packs/Smooth/Close",
            "glitch":  "Packs/Glitch/Close",
            "classic": "Packs/Classic/Close"
        }.get(self.animation_style))

    def disturbe_sound(self) -> None:
        if self.enable_transition_audio_effects and self.player and self.player.is_playing:
            self.player_pulse(400, 2.0)
            return

        Player.ui_player.play_sound({
            "bouncy":  "Packs/Bouncy/Disturbe",
            "smooth":  "Packs/Smooth/Disturbe",
            "roll":    "Packs/Smooth/Disturbe",
            "glitch":  f"Packs/Glitch/Disturbe{random.randint(1, 3)}",
            "classic": "Packs/Classic/Disturbe"
        }.get(self.animation_style))

    def squish(self, x: float, power: float = 1.2) -> float:
        return 0.05 * (x ** power)

    def get_window_size(self) -> tuple[int, int]:
        geometry = self.content_widget.geometry()
        return geometry.width(), geometry.height()

    def maximum_scale(self) -> float:
        real_width   = self.geometry().width()
        real_height  = self.geometry().height()
        width        = self.content_widget.width()
        height       = self.content_widget.height()
        coefficient  = max(width, height) / max(real_width, real_height)
        
        return 1.0 + (1.0 - coefficient)

    def really_close(self) -> None:
        if self.animations_enabled:
            self.animation_engine.clear()
            self.animation_engine.updated.disconnect()
            self.animation_engine = None

            if self.bpm_animations_enabled and not self.enable_advanced_beat_animations and self.bpm_timer:
                self.bpm_timer.stop()

            if self.enable_tilt and self.tilt_smoothing > 0 and self.tilt_animation_timer:
                self.tilt_animation_timer.stop()

        self.allow_exit = True
        self.close()

        if self.event_loop:
            self.event_loop.quit()

    def exec_(self) -> bool:
        self.setWindowModality(Qt.ApplicationModal)
        self.show()

        self.event_loop = QEventLoop()
        self.event_loop.exec_()

        self.deleteLater()
        return not self.was_cancelled

    def accept(self) -> None:
        self.result = True
        self.on_ok()

    def reject(self) -> None:
        self.result = False
        self.on_cancel()

    def __del__(self) -> None:
        logger.warning("Floating Window has been removed from RAM")

# Simple Dialogs

class DialogInputWindow(FloatingWindowGPU):
    def __init__(
            self,
            title:       str                    = "Input Dialog",
            placeholder: str                    = "Type something...",
            min_number:  int                    = 0,
            max_number:  int                    = 100,
            max_length:  int                    = 100,
            input_type:  str                    = "number",
            bpm:         int | None             = None,
            player:      Player.PlaybackManager = None
        ):

        super().__init__(title, bpm = bpm, player = player)

        self.input_field = Inputs.Textbox(input_type, min_number, max_number, max_length)
        self.input_field.setMinimumWidth(200)
        self.input_field.setPlaceholderText(placeholder)

        self.button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Cancel", self.on_cancel, False),
                (Basic.NothingButton,     "OK",     self.on_ok,     False)
            ]
        )

        self.content_layout.addWidget(self.input_field)
        self.content_layout.addLayout(self.button_row)

        self.input_field.returnPressed.connect(self.on_ok)

    def on_ok(self) -> None:
        if not self.input_field.text():
            self.button_row.buttons["OK"].start_glitch()
            self.start_disturbe_animation()
            return

        super().on_ok()

    def get_text(self) -> str:
        return self.input_field.text()

class ExportDialogWindow(FloatingWindowGPU):
    selectionChanged = pyqtSignal(str)

    def __init__(
            self,
            composition: ProjectSaver.Composition,
            bpm:         int | None             = None,
            player:      Player.PlaybackManager = None
        ):

        super().__init__(
            "Export?",
            bpm = bpm,
            player = player
        )

        self.composition = composition

        original_model = DEVICES[composition.model].short_name
        choices        = DEVICES[composition.model].port_variants + [original_model]

        self.combobox          = Inputs.Selector(choices, default_index = -1)
        self.watermark_textbox = Inputs.Textbox("text", max_length = 12, placeholder = "Dot Watermark")

        button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Later",                self.on_cancel),
                (Basic.ButtonWithOutline, "Export to every model", self.export_all),
                (Basic.NothingButton,     "Tape it",              self.export)
            ]
        )

        self.content_layout.addWidget(self.combobox)
        self.content_layout.addWidget(self.watermark_textbox)
        self.content_layout.addLayout(button_row)

    def export(self) -> None:
        model     = self.combobox.currentText()
        watermark = self.watermark_textbox.text() or "Cassette"

        self.composition.export(
            watermark,
            NUMBER_TO_CODE[model],
            open_folder = True
        )

    def export_all(self) -> None:
        if self.is_closing:
            return

        watermark = self.watermark_textbox.text() or "Cassette"
        self.on_ok()
        self.composition.export_all(watermark)

class DialogWindow(FloatingWindowGPU):
    def __init__(self, title: str):
        super().__init__(title)

        button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Nah",       self.on_cancel),
                (Basic.NothingButton,     "Hell yeah", self.on_ok)
            ]
        )

        self.content_layout.addLayout(button_row)

class SegmentEditor(FloatingWindowGPU):
    def __init__(
            self,
            title:       str,
            segment_num: int | None  = None,
            defaults                 = None,
            bpm:         int | None  = None,
            player                   = None
        ):

        super().__init__(title, bpm = bpm, player = player)

        self.segmented_bar = Widgets.SegmentedBar(segment_num, defaults)

        upper_button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Enable all", self.segmented_bar.enable_all),
                (Basic.ButtonWithOutline, "Disable all", self.segmented_bar.disable_all),
                (Basic.ButtonWithOutline, "Zebra",       self.segmented_bar.zebra)
            ]
        )

        lower_button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Nah",   self.on_cancel),
                (Basic.NothingButton,     "Apply", self.on_ok)
            ]
        )

        self.content_layout.addWidget(self.segmented_bar)
        self.content_layout.addLayout(upper_button_row)
        self.content_layout.addLayout(lower_button_row)

        self.segmented_bar.segment_changed.connect(self.wobble)

    def segments(self) -> list:
        return self.segmented_bar.active

class ErrorWindow(FloatingWindowGPU):
    def __init__(
            self,
            title:       str,
            description: str,
            button_text: str = "Cool"
        ):
        super().__init__(title)

        ok_button         = Basic.NothingButton(button_text)
        description_label = Basic.DescriptionLabel(description)

        self.content_layout.addWidget(description_label)
        self.content_layout.addWidget(ok_button)

        ok_button.clicked.connect(self.on_ok)
        self.title_label.start_glitch()
    
    def start_open_animation(self):
        if random.random() > 0.995:
            self.adjustSize()
            self.center_window()
            self.is_ready = True

            Player.ui_player.play_sound("Packs/NOK/Death")

            self.title_label.start_glitch(0.01, 18)
            
            self.animation_engine.animate(
                "scale",
                [
                    (0.0, 1.5),
                    (1.0, 1.0)
                ], 12000, LoomEngine.Easing.ease_out_quart
            )

            self.animation_engine.set_property_base_value("opacity_content", 1.0)

            self.animation_engine.animate(
                "opacity_background",
                [
                    (0.0, 0.0),
                    (1.0, 1.0)
                ], 3000, LoomEngine.Easing.linear
            )
        
        else:
            super().start_open_animation()

# Fun Windows

class About(FloatingWindowGPU):
    def __init__(self):
        super().__init__(f"Cassette {open('version').read()} by chips047")

        text = (
            "The best open - source compositor. Currently in active development!\n\n"
            "`Inspirations and credits`\n"
            "- Most UI sounds from `R.E.P.O.` game by `semiwork`.\n"
            "- UI Open sound from `The Upturned` game by `Zeekers`."
        )

        self.about_label = Basic.DescriptionLabel(text, 500)

        self.image_pixmap = QPixmap("System/Assets/Image/Version.png").scaled(
            500, 500,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label = QLabel()
        self.image_label.setPixmap(self.image_pixmap)

        ok_button     = Basic.NothingButton("Five Stars?")
        github_button = Basic.ButtonWithOutline("Check for updates on GitHub")

        ok_button.clicked.connect(self.on_ok)
        github_button.clicked.connect(self.on_github)

        self.content_layout.addWidget(self.about_label)
        self.content_layout.addWidget(self.image_label)
        self.content_layout.addWidget(github_button)
        self.content_layout.addWidget(ok_button)

    def on_github(self) -> None:
        github = GITHUB_LINK

        if random.random() < 0.95:
            webbrowser.open(github)
            return

        fox_image = Utils.get_fox_image()
        webbrowser.open(fox_image if fox_image else github)

class WalterWindow(FloatingWindowGPU):
    def __init__(self):
        super().__init__("walter.")

        self.path_open   = "System/Assets/Image/Walter"
        self.path_closed = "System/Assets/Image/WalterClosed"

        self.is_walter_closed = True

        self.walter        = QPixmap(self.path_open)
        self.walter_closed = QPixmap(self.path_closed)

        self.label = Basic.DescriptionLabel("Turn on the Waltuh, yes, click it.")
        self.image = Basic.Image(self.walter_closed)

        self.content_layout.addWidget(self.image)
        self.content_layout.addWidget(self.label)

        self.chaos_timer = Basic.Timer(20,   self.chaos_mode, parent = self)
        self.stop_timer  = Basic.Timer(8500, self.chaos_timer.stop, True, parent = self)

        self.image.clicked.connect(self.switch_walter)

    def switch_walter(self) -> None:
        self.is_walter_closed = not self.is_walter_closed

        current_pixmap = self.walter_closed if self.is_walter_closed else self.walter
        self.image.update_image(current_pixmap)

        if self.is_walter_closed:
            self.label.setText("Don't do that.")
            self.chaos_timer.stop()
            self.stop_timer.stop()
            
            return

        Player.ui_player.play_sound("Packs/NOK/HEVCharger", speed = 1.0, enable_tone_randomizer = False)
        self.label.setText("Such a good boy.")
        self.chaos_timer.start()
        self.stop_timer.start()

        if random.random() > 0.4:
            self.spam_errors()

    def spam_errors(self) -> None:
        for i in range(12):
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("walthu")
            msg.setText("waltuyh")
            msg.setInformativeText("the waltuh")
            msg.move(100 + i * 30, 100 + i * 30)
            msg.show()

        for i in range(12):
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("walthu")
            msg.setText("waltuyh")
            msg.setInformativeText("the waltuh")
            msg.move(1000 - i * 30, 1000 - i * 30)
            msg.show()

# Settings

class Settings(FloatingWindowGPU):
    def __init__(self) -> None:
        super().__init__("Settings", max_tilt_angle = 10)

        self.settings          = QSettings("chips047", "Cassette")
        self.pages             = {}
        self.controls          = {}
        self.max_scroll_width  = 0

        self.nav_widget        = self.setup_navigation()
        self.stacked_widget    = QStackedWidget()
        self.ok_button         = Basic.NothingButton("Apply!")
        self.cancel_button     = Basic.ButtonWithOutline("Cancel")

        self.stacked_widget.setStyleSheet("background: transparent;")
        self.title_label.setFont(Utils.NType(21))

        self.build_layout()
        self.connect_signals()

    # Setup

    def setup_navigation(self) -> QWidget:
        navigation_widget = QWidget()
        navigation_widget.setFixedHeight(50)
        navigation_widget.setStyleSheet(f"background: {Styles.Colors.ThirdBackground}; border-radius: 23px;")

        navigation_layout = QHBoxLayout(navigation_widget)

        navigation_layout.setContentsMargins(5, 5, 5, 5)
        navigation_layout.setSpacing(8)
        navigation_layout.setAlignment(Qt.AlignLeft)

        self.nav_layout = navigation_layout

        return navigation_widget

    def build_layout(self) -> None:
        button_row = QHBoxLayout()
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)

        self.content_layout.addWidget(self.nav_widget)
        self.content_layout.addWidget(self.stacked_widget)
        self.content_layout.addLayout(button_row)

    def connect_signals(self) -> None:
        self.ok_button.pressed.connect(self.apply_and_close)
        self.cancel_button.pressed.connect(self.on_cancel)

    # Pages

    def change_page(self, page_widget: QWidget) -> None:
        self.stacked_widget.setCurrentWidget(page_widget)

        for page_name, (button, widget) in self.pages.items():
            button.setActive(widget == page_widget)

    def init_settings(self, setting_components: dict) -> None:
        scroll_areas = []
        first_page   = None

        for page_name, components in setting_components.items():
            page_area = self.create_page(page_name, components, scroll_areas)

            if not first_page:
                first_page = page_area

        self.apply_uniform_width(scroll_areas)

        if first_page:
            self.change_page(first_page)

    def create_page(
            self,
            page_name:    str,
            components:   list,
            scroll_areas: list
        ) -> QWidget:

        page_area = Widgets.ElasticScrollArea(self)
        page_area.setFixedHeight(450)

        navigation_button = Basic.NavButton(page_name)
        navigation_button.clicked.connect(lambda _, w = page_area: self.change_page(w))
        self.nav_layout.addWidget(navigation_button)

        self.pages[page_name] = (navigation_button, page_area)

        for component_config in components:
            widget = self.create_input_widget(component_config)

            if widget:
                page_area.add_widget(widget)
                self.controls[component_config["key"]] = widget

        self.stacked_widget.addWidget(page_area)
        scroll_areas.append(page_area)

        return page_area

    def apply_uniform_width(self, scroll_areas: list) -> None:
        for scroll_area in scroll_areas:
            required_width = scroll_area.get_required_width()

            if required_width > self.max_scroll_width:
                self.max_scroll_width = required_width

        for scroll_area in scroll_areas:
            scroll_area.setFixedWidth(self.max_scroll_width)

    # Widgets

    def create_input_widget(self, config: dict) -> QWidget | None:
        value     = self.settings.value(config["key"])
        type_name = config["type"]

        if type_name == "checkbox":
            return self.create_checkbox_widget(value, config)

        if type_name == "slider":
            return self.create_slider_widget(value, config)

        if type_name == "textbox":
            return self.create_textbox_widget(value, config)

        if type_name == "selector":
            return self.create_selector_widget(value, config)

        return None

    def create_checkbox_widget(self, value: str, config: dict) -> QWidget:
        state = str(value).lower() == "true" if value is not None else config["default"]

        return Inputs.CheckboxWithLabel(
            config["title"],
            config["description"],
            state
        )

    def create_slider_widget(self, value: str, config: dict) -> QWidget:
        slider_value = int(value or config["default"])

        return Inputs.SliderWithLabel(
            config["title"],
            config["min"],
            config["max"],
            slider_value
        )

    def create_textbox_widget(self, value: str, config: dict) -> QWidget:
        textbox_value = value or config["default"]

        return Inputs.TextboxWithLabel(
            config["title"],
            config["min"],
            config["max"],
            textbox_value
        )

    def create_selector_widget(self, value: str, config: dict) -> QWidget:
        default_text  = config["default"] if value is None else None
        default_value = value
        
        return Inputs.SelectorWithLabel(
            config["title"],
            config["map"],
            default_text = default_text,
            default_value = default_value
        )

    # Actions

    def apply_and_close(self) -> None:
        for key, widget in self.controls.items():
            self.save_widget_value(key, widget)

        self.settings.sync()

        load_settings()

        self.on_ok()

    def save_widget_value(self, key: str, widget: QWidget) -> None:
        if isinstance(widget, Inputs.CheckboxWithLabel):
            self.settings.setValue(key, widget.isChecked())
        
        elif isinstance(widget, Inputs.SliderWithLabel):
            self.settings.setValue(key, widget.value())
        
        elif isinstance(widget, Inputs.SelectorWithLabel):
            self.settings.setValue(key, widget.currentData())
        
        elif isinstance(widget, Inputs.TextboxWithLabel):
            self.settings.setValue(key, widget.getValue())

# Glyph Visualizer

class GlyphVisualizer(FloatingWindowGPU):
    def __init__(
            self,
            parent: QObject,
            model:  str,
            player: Player.PlaybackManager = None,
            bpm:    int | None             = None
        ):

        super().__init__(
            None,
            bpm                     = bpm,
            player                  = player,
            margin                  = 50,
            max_tilt_angle          = 9,
            enable_open_animation   = False,
            enable_close_animation  = False
        )

        self.parent            = parent
        self.map_data          = DEVICES[model].visualization_map
        self.map_w, self.map_h = self.map_data["size"]

        self.visual_scale:    float = 1.0
        self.target_scale:    float = 1.0
        self.scale_smoothing: float = 0.15

        self.glyphs_gpu     = []
        self.total_segments = 0

        self.init_geometry()
        self.init_shared_buffer()

        self.scale_in()
        self.sync_size_delayed()

    def setup_timers(self) -> None:
        super().setup_timers()

        self.resize_timer = Basic.Timer(
            200,
            self.sync_size_delayed,
            single_shot = True,
            parent = self
        )

        self.timer = Basic.Timer(
            FPS_60,
            self.process_schedule,
            parent = self
        )

        self.elapsed = QElapsedTimer()

    def init_geometry(self) -> None:
        current_global_offset = 0

        for glyph_id, data in self.map_data["glyphs"].items():
            glyph = self.process_single_glyph(glyph_id, data, current_global_offset)
            self.glyphs_gpu.append(glyph)
            
            current_global_offset += glyph["segment_count"]

        self.total_segments = current_global_offset
        self.global_levels  = numpy.zeros(self.total_segments, dtype = numpy.float32)

    def init_shared_buffer(self) -> None:
        self.levels_tex = GL.glGenTextures(1)

        GL.glBindTexture(GL.GL_TEXTURE_1D, self.levels_tex)
        GL.glTexImage1D(GL.GL_TEXTURE_1D, 0, GL.GL_R32F, self.total_segments, 0, GL.GL_RED, GL.GL_FLOAT, None)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_WRAP_S,     GL.GL_CLAMP_TO_EDGE)

    def process_single_glyph(
            self,
            glyph_id:      str,
            data:          dict,
            global_offset: int
        ) -> dict:
        
        path               = Utils.parse_svg_path_data(data["svg"])
        segment_count      = data.get("segments", 1)
        position_x, position_y = data["position"]
        points_per_segment = 60

        total_length   = path.length()
        segment_length = total_length / segment_count

        all_vertices        = []
        starts, counts      = [], []
        current_vbo_offset  = 0

        for segment_index in range(segment_count):
            start_distance = segment_index       * segment_length
            end_distance   = (segment_index + 1) * segment_length

            points = []

            for i in range(points_per_segment):
                dist = start_distance + (i / (points_per_segment - 1)) * (end_distance - start_distance)
                t    = path.percentAtLength(dist)
                pt   = path.pointAtPercent(t)
                points.append(
                    [
                        pt.x() + position_x - self.map_w / 2,
                        -(pt.y() + position_y) + self.map_h / 2
                    ]
                )

            points       = numpy.array(points, dtype = numpy.float32)
            segment_verts = self.calculate_segment_geometry(points, global_offset + segment_index)

            all_vertices.append(segment_verts)
            num_verts = len(segment_verts) // 5

            starts.append(current_vbo_offset)
            counts.append(num_verts)

            current_vbo_offset += num_verts

        return {
            "id":              glyph_id,
            "vbo_data":        numpy.concatenate(all_vertices).astype(numpy.float32),
            "starts":          numpy.array(starts, dtype = numpy.int32),
            "counts":          numpy.array(counts, dtype = numpy.int32),
            "segment_count":   segment_count,
            "global_base_idx": global_offset,
            "schedule":        []
        }

    def calculate_segment_geometry(
            self,
            points:     numpy.ndarray,
            global_idx: int
        ) -> numpy.ndarray:
        
        differences = numpy.diff(points, axis = 0)
        tangents    = numpy.vstack([differences, differences[-1:]])
        normals     = numpy.stack([-tangents[:, 1], tangents[:, 0]], axis = 1)
        lengths     = numpy.linalg.norm(normals, axis = 1, keepdims = True)
        normals    /= numpy.where(lengths == 0, 1.0, lengths)

        index_float = float(global_idx)
        result      = numpy.zeros((len(points) * 2, 5), dtype = numpy.float32)

        for i, (point, normal) in enumerate(zip(points, normals)):
            result[i * 2]     = [point[0], point[1],  normal[0],  normal[1], index_float]
            result[i * 2 + 1] = [point[0], point[1], -normal[0], -normal[1], index_float]

        return result.flatten()

    def initializeGL(self) -> None:
        super().initializeGL()
        
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE)

        self.prog = shaders.compileProgram(
            shaders.compileShader(GLYPH_VS, GL.GL_VERTEX_SHADER),
            shaders.compileShader(GLYPH_FS, GL.GL_FRAGMENT_SHADER)
        )

        self.uniform_locations = {
            "mvp":        GL.glGetUniformLocation(self.prog, "mvp"),
            "thickness":  GL.glGetUniformLocation(self.prog, "uThickness"),
            "levels_tex": GL.glGetUniformLocation(self.prog, "uLevelsTex")
        }

        for glyph in self.glyphs_gpu:
            glyph["vao"], glyph["vbo"] = GL.glGenVertexArrays(1), GL.glGenBuffers(1)

            GL.glBindVertexArray(glyph["vao"])
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, glyph["vbo"])
            GL.glBufferData(GL.GL_ARRAY_BUFFER, glyph["vbo_data"].nbytes, glyph["vbo_data"], GL.GL_STATIC_DRAW)

            stride = 20

            for attribute_index, size, offset in [(0, 2, 0), (1, 2, 8), (2, 1, 16)]:
                GL.glVertexAttribPointer(attribute_index, size, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.ctypes.c_void_p(offset))
                GL.glEnableVertexAttribArray(attribute_index)

    def paintGL(self) -> None:
        super().paintGL()
        
        GL.glUseProgram(self.prog)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_1D, self.levels_tex)
        GL.glTexSubImage1D(GL.GL_TEXTURE_1D, 0, 0, self.total_segments, GL.GL_RED, GL.GL_FLOAT, self.global_levels)
        GL.glUniform1i(self.uniform_locations["levels_tex"], 0)

        mvp = self.calculate_matrix(2.0, 2.0)
        mvp.scale(self.visual_scale, self.visual_scale, 1.0)

        GL.glUniformMatrix4fv(self.uniform_locations["mvp"], 1, GL.GL_FALSE, mvp.data())
        GL.glUniform1f(self.uniform_locations["thickness"], float(self.map_data.get("thickness", 2.2)))

        for glyph in self.glyphs_gpu:
            GL.glBindVertexArray(glyph["vao"])
            GL.glMultiDrawArrays(GL.GL_TRIANGLE_STRIP, glyph["starts"], glyph["counts"], len(glyph["starts"]))

    def scale_in(self) -> None:
        if not self.animations_enabled:
            return

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ],
            1000,
            LoomEngine.Easing.ease_out_quart,
            do_not_multiply_duration = True
        )

        self.animation_engine.set_property_base_value("opacity_background", 1.0)

    def scale_out(self, cleanup: bool) -> None:
        if not self.animations_enabled:
            if cleanup:
                self.really_close()
            
            return

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ],
            500,
            LoomEngine.Easing.ease_in_quart,
            self.really_close if cleanup else None,
            True
        )

    def set_schedule(self, schedule_dict: dict) -> None:
        for glyph in self.glyphs_gpu:
            glyph["schedule"] = list(schedule_dict.get(glyph["id"], {}).values())

    def play_all(self, ms_start: int = 0) -> None:
        self.virtual_time      = ms_start
        self.last_process_time = 0

        self.elapsed.start()
        self.timer.start()

    def stop_all(self) -> None:
        self.timer.stop()
        self.virtual_time      = 0
        self.last_process_time = 0
        self.global_levels.fill(0)

        self.update()

    def update_visual_scale(self) -> None:
        if abs(self.target_scale - self.visual_scale) > 0.001:
            self.visual_scale += (self.target_scale - self.visual_scale) * self.scale_smoothing
            self.update()
        
        else:
            self.visual_scale = self.target_scale

    def get_item_brightness(self, item: dict, now: float) -> float:
        if "keyframes" not in item:
            return item["brightness"]

        start    = item["start"]
        duration = item["duration"]
        progress = (now - start) / duration if duration > 0 else 1.0

        easing_name = item.get("easing", "linear")
        easing_func = VISUAL_EASINGS[easing_name]

        return self.interpolate_keyframes(item["keyframes"], progress, easing_func)

    def get_target_slice(
            self,
            item:          dict,
            base_index:    int,
            segment_count: int
        ):

        if "segments" in item:
            return base_index + numpy.array(item["segments"])

        return slice(base_index, base_index + segment_count)

    def process_schedule(self) -> None:
        real_elapsed            = self.elapsed.elapsed()
        self.virtual_time      += (real_elapsed - self.last_process_time) * self.player.speed
        self.last_process_time  = real_elapsed

        now = self.virtual_time
        self.global_levels.fill(0)

        for glyph in self.glyphs_gpu:
            base_index = glyph["global_base_idx"]

            for item in glyph["schedule"]:
                if not (item["start"] <= now <= item["start"] + item["duration"]):
                    continue

                brightness = self.get_item_brightness(item, now)
                target     = self.get_target_slice(item, base_index, glyph["segment_count"])

                self.global_levels[target] = numpy.maximum(self.global_levels[target], brightness)

        self.update()

    def interpolate_keyframes(
            self,
            keyframes:   list[tuple[float, float]],
            progress:    float,
            easing_func: Callable[[float], float]
        ) -> float:
        
        if not keyframes:
            return 0.0

        if progress <= keyframes[0][0]:
            return float(keyframes[0][1])

        if progress >= keyframes[-1][0]:
            return float(keyframes[-1][1])

        for (time_start, value_start), (time_end, value_end) in zip(keyframes, keyframes[1:]):
            if not (time_start <= progress <= time_end):
                continue

            segment_duration = time_end - time_start
            local_progress   = (progress - time_start) / segment_duration if segment_duration > 0 else 1.0

            return value_start + (value_end - value_start) * easing_func(local_progress)

        return float(keyframes[-1][1])

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta             = 0.07 if event.angleDelta().y() > 0 else -0.07
        self.target_scale = numpy.clip(self.target_scale + delta, 0.3, 4.0)
        self.visual_scale = self.target_scale

        self.resize_timer.start()
        self.update()

    def sync_size_delayed(self) -> None:
        new_w = int(self.map_w * self.target_scale) + 80
        new_h = int(self.map_h * self.target_scale) + 80
        
        self.animate_resize(new_w, new_h)

    def exit(self, cleanup: bool = True) -> None:
        self.stop_all()
        self.resize_timer.stop()
        self.scale_out(cleanup)

# Tutorial

class Tutorial(FloatingWindowGPU):
    def __init__(
            self,
            bpm:  int,
            path: str
        ):

        self.player = Player.PlaybackManager()
        self.player.load_audio(path)

        super().__init__(
            "Tutorial",
            bpm                        = bpm,
            player                     = self.player,
            enable_audioplayer_effects = False
        )

        self.stage = 0

        self.build_pages()
        self.initialize_ui()
        self.initialize_audio()
        self.set_bpm_peak_size(1.02)
        self.make_page()

    def build_pages(self) -> None:
        self.pages = [
            {
                "label": "Welcome to Cassette",
                "text": "Get ready."
            },
            {
                "label": "Basics",
                "text": (
                    "`Space` to play / pause.\n"
                    "`1, 2, 3, 4, 5, 6, 7, 8, 9, 0, Minus` to place a glyph. "
                    "`Del / Backspace` to delete it. `Ctrl + / -` or `Command + / -` to zoom. "
                    "`B`, `S`, `D` to quickly change the brightness, speed and duration."
                )
            },
            {
                "label": "Basics - Mouse",
                "text": (
                    "`Right Mouse Button` to open context menu. "
                    "`Grab` the side of glyph to resize it. `Hold` to move it. "
                    "`Press` on waveform to set playback position."
                )
            },
            {
                "label": "Basics - Scroll",
                "text": "Use `Shift + Wheel` to scroll vertically. Use `Wheel` to scroll horizontally."
            },
            {
                "label": "Basics - Visualizator",
                "text": (
                    "You can move the visualizator by dragging it with `Left Mouse Button`. "
                    "You also can resize by scrolling `Wheel` while hovering over it."
                )
            },
            {
                "label": "Basics - Navigation",
                "text": "Click `Eject` to go back to the main menu."
            },
            {
                "label": "Effects - Mixing",
                "text": "You can combine effects! Place glyphs on top of each other with different effects."
            },
            {
                "label": "Shall we?",
                "text": "Now, try yourself in glyphtones creation."
            }
        ]

        self.max_stage = len(self.pages)

    def initialize_ui(self) -> None:
        self.text_label = Basic.DescriptionLabel("Hello mazafaka белка")
        self.text_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.text_label.setMinimumWidth(400)

        self.next_button = Basic.NothingButton("Next?")
        self.next_button.clicked.connect(self.next_button_callback)

        self.content_layout.addWidget(self.text_label)
        self.content_layout.addWidget(self.next_button)

    def initialize_audio(self) -> None:
        self.is_audio_small = self.player.duration_ms < 30000

        if not self.is_audio_small:
            self.player.set_midpass()
            self.player.set_bitcrush(6, 8)
            self.player.set_speed(0)
            self.player.set_speed(0.8, 3000)

        def stage_one():
            self.player.set_speed(0.95, 1000)
            self.player.set_midpass(mix = 0.5, duration_ms = 1000)
            self.player.set_bitcrush(bits = 24, downsample = 1, duration_ms = 2000)

        def stage_two():
            self.player.set_speed(1.0, duration_ms = 1000)
            self.player.set_midpass(mix = 0.0, duration_ms = 1000)

        def stage_three():
            self.set_bpm_peak_size(1.04)

        def stage_four():
            self.set_bpm_peak_size(1.05)

        def stage_seven():
            self.player.set_speed(0.0, 4000, shutdown_on_finish = True)

        self.stage_effects = {
            1: stage_one,
            2: stage_two,
            3: stage_three,
            4: stage_four,
            7: stage_seven
        }

    def make_page(self) -> None:
        if not (0 <= self.stage < self.max_stage):
            return

        page = self.pages[self.stage]

        self.title_label.setText(page["label"])
        self.text_label.setText(page["text"])

        QTimer.singleShot(0, self.adjustSize)

    def next_button_callback(self) -> None:
        self.stage += 1
        self.animation_random_rotate()

        if self.stage >= self.max_stage:
            self.on_ok()
            return

        self.make_page()
        self.apply_stage_effects()

    def apply_stage_effects(self) -> None:
        if self.is_audio_small:
            return

        effect = self.stage_effects.get(self.stage)

        if effect:
            effect()


# Workers

class PrepareWorker(QObject):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.audio_path = file_path

    def run(self) -> None:
        try:
            cached_wav = Audio.ensure_wav(self.audio_path)
            self.finished.emit(cached_wav)

        except Audio.NoAudioStreams:
            self.error.emit("No audio streams found in the file.")

        except Audio.PermissionError:
            self.error.emit("Permission error while accessing the file. Please check if the file is open in another application.")

        except Audio.CorruptedFileError:
            self.error.emit("The audio file is corrupted or in an unsupported format.")

        except FileNotFoundError:
            self.error.emit("The specified audio file was not found. Maybe it was moved or deleted while the loader was running?")

        except Exception:
            self.error.emit(f"Conversion failed: {traceback.format_exc()}")

    def __del__(self) -> None:
        logger.debug("PrepareWorker has been removed")

class LoadAudioWorker(QObject):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()

        self.audio_path = file_path

    def run(self) -> None:
        try:
            data, sample_rate = Audio.load_audio(self.audio_path)
            audio_float       = data.astype('float32')

            if audio_float.ndim > 1:
                audio_float = numpy.mean(audio_float, axis = 1)

            samples_per_pixel = len(audio_float) / 1000
            step              = max(1, int(numpy.ceil(samples_per_pixel)))
            padded_len        = ((len(audio_float) + step - 1) // step) * step
            padded            = numpy.pad(audio_float, (0, padded_len - len(audio_float)), mode = "constant")
            reshaped          = padded.reshape(-1, step)
            waveform_data     = numpy.mean(numpy.abs(reshaped), axis = 1)
            waveform_data     = Utils.gaussian_filter1d_np(waveform_data, sigma = 2)

            self.finished.emit((data, sample_rate, waveform_data))

        except Audio.CorruptedFileError:
            self.error.emit("The audio file is corrupted or in an unsupported format.")

        except Exception:
            self.error.emit(traceback.format_exc())

    def __del__(self) -> None:
        logger.debug("LoadWorker has been removed")

class BPMWorker(QObject):
    finished = pyqtSignal(float, object)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.audio_path = file_path

    def run(self) -> None:
        try:
            bpm, peaks = Audio.analyze_bpm_and_beats(self.audio_path)
            self.finished.emit(bpm, peaks)

        except Exception:
            self.error.emit(traceback.format_exc())

    def __del__(self) -> None:
        logger.debug("BPMWorker has been removed")

# Audio Loading Base

class AudioLoadingDialog(FloatingWindowGPU):
    def run_loading_pipeline(self, file_path: str) -> None:
        self.cached_wav = None

        self.prepare_thread = QThread(self)
        self.prepare_worker = PrepareWorker(file_path)
        self.prepare_worker.moveToThread(self.prepare_thread)
        self.prepare_thread.started.connect(self.prepare_worker.run)

        self.prepare_worker.finished.connect(self.on_prepare_success)
        self.prepare_worker.error.connect(self.on_load_failed)

        self.prepare_worker.finished.connect(self.prepare_thread.quit)
        self.prepare_worker.finished.connect(self.prepare_worker.deleteLater)
        self.prepare_thread.finished.connect(self.prepare_thread.deleteLater)

        self.prepare_thread.start()

        self.load_thread  = None
        self.load_worker  = None

    def on_prepare_success(self, cached_wav_path: str) -> None:
        self.cached_wav  = cached_wav_path

        self.load_thread = QThread(self)
        self.load_worker = LoadAudioWorker(self.cached_wav)
        self.load_worker.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.load_worker.run)

        self.load_worker.finished.connect(self.on_load_finished)
        self.load_worker.error.connect(self.on_load_failed)

        self.load_worker.finished.connect(self.load_thread.quit)
        self.load_worker.finished.connect(self.load_worker.deleteLater)
        self.load_thread.finished.connect(self.load_thread.deleteLater)

        self.load_thread.start(QThread.LowPriority)

    def on_load_finished(self, result: tuple) -> None:
        pass

    def on_load_failed(self, message: str) -> None:
        window = ErrorWindow("Load Error", message)
        window.destroyed.connect(self.reject_callback)
        window.exec_()

    def cleanup_threads(self, threads: list) -> None:
        threads_to_wait = []

        for thread in threads:
            try:
                if not thread or not thread.isRunning():
                    continue

                threads_to_wait.append(thread)
                thread.quit()

            except Exception:
                pass

        if threads_to_wait:
            self.wait_and_cleanup(threads_to_wait)
        
        else:
            self.safe_delete_cache()

    def wait_and_cleanup(self, threads: list) -> None:
        for thread in threads:
            thread.wait(500)

        self.safe_delete_cache()

    def safe_delete_cache(self) -> None:
        if not self.cached_wav or self.cached_wav == self.audio_path:
            return

        try:
            if os.path.exists(self.cached_wav):
                os.unlink(self.cached_wav)
                logger.info(f"Cache deleted: {self.cached_wav}")

        except Exception as error:
            logger.warning(f"Could not delete cache yet, retrying... {error}")
            QTimer.singleShot(1000, self.safe_delete_cache)

class AudioEditorBase(AudioLoadingDialog):
    def setup_trim_section(self) -> None:
        self.trim_widget        = Widgets.TrimmingWaveformWidget()
        self.start_time_textbox = make_time_textbox()
        self.end_time_textbox   = make_time_textbox()
        self.fade_in_textbox    = make_fade_textbox("Fade in (ms)")
        self.fade_out_textbox   = make_fade_textbox("Fade out (ms)")

        self.play_icon  = QIcon("System/Assets/Icons/Audio/Play.png")
        self.pause_icon = QIcon("System/Assets/Icons/Audio/Pause.png")

        self.play_button = QPushButton()
        self.play_button.setStyleSheet("background-color: transparent; border: none;")
        self.play_button.setIcon(self.play_icon)
        self.play_button.setIconSize(QSize(45, 45))
        self.play_button.setFixedSize(45, 45)
        self.play_button.setEnabled(False)

        self.playback_timer = Basic.Timer(FPS_60, self.update_playback, parent = self)

        self.trim_widget.regionChanged.connect(self.update_textboxes)
        self.end_time_textbox.safeTextChanged.connect(self.edit_end_time)
        self.start_time_textbox.safeTextChanged.connect(self.edit_start_time)
        self.play_button.clicked.connect(self.toggle_playback)

    def build_playback_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        row.addWidget(self.start_time_textbox)
        row.addWidget(self.fade_in_textbox)
        row.addWidget(self.play_button)
        row.addWidget(self.fade_out_textbox)
        row.addWidget(self.end_time_textbox)

        return row

    # Load Pipeline

    def on_load_finished(self, result: tuple) -> None:
        try:
            data, sample_rate, waveform_data = result

            self.player.load_audio_from_data(data, sample_rate)
            self.trim_widget.set_data(data, sample_rate, waveform_data)

            self.end_time_textbox.max_number = self.trim_widget.duration
            self.end_time_textbox.setText(max(1, math.ceil(self.trim_widget.duration)))

            self.update_textboxes(self.trim_widget.start_time, self.trim_widget.end_time)

            self.play_button.setEnabled(True)
            self.on_audio_ready()

        except Exception:
            ErrorWindow("Load Error", traceback.format_exc()).exec_()

    def on_audio_ready(self) -> None:
        pass

    # Trim Textbox Sync

    def update_textboxes(self, start: float, end: float) -> None:
        self.start_time_textbox.blockSignals(True)
        self.end_time_textbox.blockSignals(True)

        self.start_time_textbox.setText(int(round(start)))
        self.end_time_textbox.setText(max(1, int(round(end))))

        self.start_time_textbox.blockSignals(False)
        self.end_time_textbox.blockSignals(False)

        self.start_time_textbox.max_number = int(round(end - 1))
        self.end_time_textbox.min_number   = int(round(start))

    def edit_start_time(self) -> None:
        start_seconds = self.start_time_textbox.text()

        if not start_seconds:
            return

        self.trim_widget.set_playback_position(start_seconds)
        self.trim_widget.start_time = start_seconds
        self.trim_widget.update()

        self.end_time_textbox.min_number = start_seconds

    def edit_end_time(self) -> None:
        end_seconds   = self.end_time_textbox.text()
        start_seconds = self.start_time_textbox.text()

        if end_seconds is None or start_seconds is None:
            return

        if start_seconds >= end_seconds:
            return

        self.trim_widget.set_playback_position(start_seconds)
        self.trim_widget.end_time = end_seconds
        self.trim_widget.update()

        self.start_time_textbox.max_number = end_seconds - 1

    # Playback

    def toggle_playback(self) -> None:
        if self.player.is_playing:
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time)
        else:
            self.play_selection()

    def play_selection(self) -> None:
        current_position = self.trim_widget.playback_position

        if not (self.trim_widget.start_time <= current_position < self.trim_widget.end_time):
            current_position = self.trim_widget.start_time
            self.trim_widget.set_playback_position(current_position)

        self.player.play(current_position * 1000)
        self.play_button.setIcon(self.pause_icon)
        self.trim_widget.set_is_playing(True)
        self.playback_timer.start()

    def stop_playback(self) -> None:
        self.player.stop()
        self.play_button.setIcon(self.play_icon)
        self.trim_widget.set_is_playing(False)
        self.playback_timer.stop()

    def update_playback(self) -> None:
        if not self.player.is_playing:
            self.trim_widget.set_playback_position(0)
            self.stop_playback()
            return

        current_position_ms = self.player.get_position()

        if current_position_ms > self.trim_widget.end_time * 1000:
            self.trim_widget.set_playback_position(self.trim_widget.start_time)
            self.toggle_playback()
            return

        self.trim_widget.set_playback_position(current_position_ms / 1000)

    # Settings

    def validate_trim(self) -> bool:
        if self.end_time_textbox.is_not_valid() or not self.end_time_textbox.text():
            self.end_time_textbox.start_glitch(False)
            return False

        if self.start_time_textbox.text() is None:
            self.start_time_textbox.start_glitch(False)
            return False

        return True

    def get_trim_settings(self) -> dict:
        return {
            "start_ms": self.trim_widget.start_time * 1000,
            "end_ms":   self.trim_widget.end_time   * 1000,
            "fade_in":  self.fade_in_textbox.text(),
            "fade_out": self.fade_out_textbox.text()
        }

    # Cleanup

    def get_threads(self) -> list:
        return [self.prepare_thread, self.load_thread]

    def cleanup_audio(self) -> None:
        self.playback_timer.stop()
        self.trim_widget.audio_data = None

        if self.player.is_playing:
            self.player.set_speed(0.0, 3000)

        self.cleanup_threads(self.get_threads())

        self.prepare_worker = self.load_worker  = None
        self.prepare_thread = self.load_thread  = None

    def reject_callback(self) -> None:
        self.cleanup_audio()
        super().on_cancel()

class BPMEditorBase(AudioEditorBase):

    def setup_bpm_section(self) -> None:
        self.bpm_thread = None
        self.bpm_worker = None

        self.bpm_text              = ""
        self.bpm_number_string     = ""
        self.bpm_animation_target  = None
        self.bpm_animation_current = 120
        self.snapped_times         = None

        self.bpm_input = Inputs.Textbox("number", 1, 400, placeholder = "Counting BPM... 120")
        self.bpm_input.setMaximumWidth(220)
        self.bpm_input.setFixedHeight(Styles.Metrics.ElementHeight)
        self.bpm_input.setStyleSheet(Styles.Controls.FloatingTextBoxRound)

        self.bpm_animation_timer = Basic.Timer(
            FPS_30,
            self.animate_bpm_spinbox,
            auto_start = True,
            parent     = self
        )

        self.bpm_remove_timer = Basic.Timer(0, self.bpm_remove_step, parent = self)

        if self.animations_enabled:
            self.animation_engine.add_property(
                "bpm_textbox_width",
                self.bpm_input.width(),
                LoomEngine.MixMode.NOMIX,
                self.bpm_input.setFixedWidth
            )

        self.bpm_input.safeTextChanged.connect(self.on_bpm_changed)

    # BPM Pipeline

    def on_prepare_success(self, cached_wav_path: str) -> None:
        super().on_prepare_success(cached_wav_path)
        self.start_bpm_pipeline()

    def start_bpm_pipeline(self) -> None:
        self.bpm_thread = QThread(self)
        self.bpm_worker = BPMWorker(self.cached_wav)
        self.bpm_worker.moveToThread(self.bpm_thread)
        self.bpm_thread.started.connect(self.bpm_worker.run)

        self.bpm_worker.finished.connect(self.on_bpm_finished)
        self.bpm_worker.error.connect(lambda message: ErrorWindow("BPM error", message).exec_())

        self.bpm_worker.finished.connect(self.bpm_thread.quit)
        self.bpm_worker.finished.connect(self.bpm_worker.deleteLater)
        self.bpm_thread.finished.connect(self.bpm_thread.deleteLater)

        self.bpm_thread.start(QThread.LowPriority)

    def on_bpm_finished(self, bpm: float, peaks) -> None:
        try:
            self.bpm_ready(bpm, peaks)

        except Exception:
            ErrorWindow("BPM Error", traceback.format_exc()).exec_()

    def bpm_ready(self, bpm: float, snapped_times) -> None:
        self.snapped_times = snapped_times
        self.bpm_animation_timer.stop()

        if bpm:
            bpm_value              = round(bpm)
            self.bpm_text          = "Counting BPM "
            self.bpm_number_string = str(bpm_value)

            self.bpm_input.setPlaceholderText(f"{self.bpm_text}{self.bpm_number_string}")

            remove_interval = round(60000 / bpm / 8)
            self.bpm_remove_timer.start(remove_interval)
            return

        self.bpm_text          = "Counting BPM FAILURE"
        self.bpm_number_string = ""

        self.bpm_input.setPlaceholderText(self.bpm_text)
        self.bpm_remove_timer.start(100)

        if random.randint(1, 500) == 500:
            Player.ui_player.play_sound("Packs/NOK/Gambling")

    # BPM animations

    def get_perfect_bpm_width(self) -> int:
        text       = str(self.bpm_input.text() or self.bpm_input.placeholderText() or "BPM")
        metrics    = self.bpm_input.fontMetrics()
        text_width = metrics.horizontalAdvance(text)

        return round(text_width + 33)

    def shrink_bpm_input(self) -> None:
        if not self.animations_enabled:
            return

        self.animation_engine.set_target_value(
            "bpm_textbox_width",
            self.get_perfect_bpm_width(),
            300,
            LoomEngine.Easing.ease_out_cubic
        )

        QTimer.singleShot(300, self.on_bpm_animation_end)

    def on_bpm_animation_end(self) -> None:
        self.bpm_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def animate_bpm_spinbox(self) -> None:
        if not self.bpm_animation_target:
            self.bpm_animation_target = numpy.random.randint(60, 180)

        if self.bpm_animation_current == self.bpm_animation_target:
            self.bpm_animation_target = numpy.random.randint(60, 180)

        if self.bpm_animation_current < self.bpm_animation_target:
            self.bpm_animation_current += 1

        elif self.bpm_animation_current > self.bpm_animation_target:
            self.bpm_animation_current -= 1

        self.bpm_input.setPlaceholderText(f"Counting BPM {self.bpm_animation_current}")

    def bpm_remove_step(self) -> None:
        if self.bpm_text:
            self.bpm_text = self.bpm_text[1:]
            self.bpm_input.setPlaceholderText(f"{self.bpm_text}{self.bpm_number_string}")
            return

        self.bpm_remove_timer.stop()

        if self.bpm_number_string:
            self.bpm_input.setText(self.bpm_number_string)

        self.bpm_input.setPlaceholderText("BPM")
        self.shrink_bpm_input()

    def on_bpm_changed(self, value: str) -> None:
        if not value:
            return

        self.update_bpm(int(value))

    # Settings

    def get_bpm_value(self) -> int:
        return int(self.bpm_input.text() or 120)

    def get_bpm_settings(self) -> dict:
        return {
            "bpm":   self.get_bpm_value(),
            "beats": self.snapped_times
        }

    # Cleanup

    def get_threads(self) -> list:
        return [*super().get_threads(), self.bpm_thread]

    def cleanup_audio(self) -> None:
        self.bpm_animation_timer.stop()
        self.bpm_remove_timer.stop()

        super().cleanup_audio()

        self.bpm_worker = None
        self.bpm_thread = None

# Audio Setup Dialog

class AudioSetupDialog(BPMEditorBase):
    def __init__(
            self,
            audio_path: str
        ):

        self.player     = Player.player
        self.audio_path = audio_path
        self.filename   = audio_path.split("/")[-1]

        super().__init__(
            "Audio",
            player                     = self.player,
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.saved_settings = {}

        self.title_label.setText(self.filename)

        self.setup_audio_layout()
        self.run_loading_pipeline(audio_path)

        self.adjustSize()

    def setup_audio_layout(self) -> None:
        self.setup_trim_section()
        self.setup_bpm_section()

        self.beat_count = 0
        self.beat_timer = Basic.Timer(0, self.update_title_beat, parent = self)

        self.model_selector = Inputs.Selector(["1", "2", "2a", "3a", "4a"])
        self.cancel_button  = Basic.ButtonWithOutline("Cancel")
        self.ok_button      = Basic.NothingButton("Ok")

        self.ok_button.setMaximumWidth(70)
        self.cancel_button.setMaximumWidth(100)
        self.model_selector.setMinimumWidth(300)
        self.ok_button.setEnabled(False)

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(10)
        settings_layout.addWidget(self.bpm_input)
        settings_layout.addWidget(self.model_selector)
        settings_layout.addStretch()
        settings_layout.addWidget(self.cancel_button)
        settings_layout.addWidget(self.ok_button)

        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.reject_callback)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(self.build_playback_row())
        self.content_layout.addLayout(settings_layout)

    def on_audio_ready(self) -> None:
        self.ok_button.setEnabled(True)

    def toggle_playback(self) -> None:
        if self.player.is_playing:
            self.title_label.setText(self.filename)
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time)
        
        else:
            self.play_selection()

    def play_selection(self) -> None:
        super().play_selection()

        self.beat_count   = 0
        beat_interval     = int(60000 / self.get_bpm_value() / 4)

        self.beat_timer.stop()
        self.beat_timer.setInterval(beat_interval)
        self.beat_timer.start()

    def stop_playback(self) -> None:
        super().stop_playback()
        self.beat_timer.stop()
        self.beat_count = 0

    def update_title_beat(self) -> None:
        position_ms = f"{round(self.player.get_position() / 1000, 4):.3f}"
        self.title_label.setText(position_ms)

        audio_level = self.player.get_current_audio_level()

        if audio_level < 0.03:
            return

        self.beat_count += 1

        if self.beat_count % 4 == 0:
            self.animation_title_scale(peak_scale = 1.4, duration = 200)
        else:
            self.animation_title_scale(peak_scale = 1.1, duration = 120)

    # Settings

    def accept_callback(self) -> None:
        if not self.validate_trim():
            self.ok_button.start_glitch()
            return

        self.settings = self.get_settings()

        self.cleanup_audio()
        super().on_ok()

    def get_settings(self) -> dict:
        return {
            "audio": {**self.get_trim_settings(), **self.get_bpm_settings()},
            "model": NUMBER_TO_CODE[self.model_selector.currentText()]
        }

    def cleanup_audio(self) -> None:
        self.beat_timer.stop()
        super().cleanup_audio()

# Glyphtone Editor

class GlyphtoneEditor(AudioEditorBase):
    def __init__(self, audio_path: str):
        self.player    = Player.PlaybackManager()
        self.audio_path = audio_path

        super().__init__(
            "Glyphtone Editor",
            player                     = self.player,
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.saved_settings = {}
        self.folder_id      = None

        self.setup_ui()
        self.run_loading_pipeline(audio_path)

        self.adjustSize()

    def setup_ui(self) -> None:
        self.setup_trim_section()

        self.cancel_button = Basic.ButtonWithOutline("Cancel")
        self.ok_button     = Basic.NothingButton("Confirm")

        self.ok_button.setEnabled(False)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.cancel_button)
        bottom_layout.addWidget(self.ok_button)

        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.reject_callback)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(self.build_playback_row())
        self.content_layout.addLayout(bottom_layout)

    def on_audio_ready(self) -> None:
        self.ok_button.setEnabled(True)

    def accept_callback(self) -> None:
        if not self.validate_trim():
            self.ok_button.start_glitch()
            return

        trim = self.get_trim_settings()

        self.saved_settings = {
            **trim,
            "duration": self.trim_widget.end_time - self.trim_widget.start_time
        }

        if self.folder_id is None:
            self.folder_id = random.randint(0, 99999999)

        source        = self.audio_path
        output        = Utils.get_user_path(f"Editor/{self.folder_id}/Cropped.ogg", "Cassette/Songs")
        output_folder = Utils.get_user_path(f"Editor/{self.folder_id}", "Cassette/Songs")

        Encoder.trim_glyphs_ogg(
            source,
            output,
            int(self.saved_settings["start_ms"]),
            int(self.saved_settings["end_ms"]),
            self.fade_in_textbox.text()  or 0,
            self.fade_out_textbox.text() or 0
        )

        self.on_ok()
        Utils.open_file(output_folder)

# Import Window

class ImportWindow(BPMEditorBase):
    def __init__(self):
        self.player     = Player.player
        self.audio_path = None
        self.save_path  = None
        self.cached_wav = None

        self.prepare_thread = None
        self.load_thread    = None

        super().__init__(
            "Import",
            player                     = self.player,
            max_tilt_angle             = 14,
            enable_audioplayer_effects = False
        )

        self.setAcceptDrops(True)

        self.setup_import_ui()
        self.adjustSize()
    
    def ask_for_file(
            self,
            types: list[str],
            type_name: str
        ):
        
        options   = QFileDialog.Options()
        options  |= QFileDialog.Option.ReadOnly

        file_path = None
    
        dialog = QFileDialog(
            self,
            "Open Audio File",
            "",
            f"{type_name} ({' '.join(types)});;All Files (*)"
        )
        
        dialog.setOptions(options)

        if dialog.exec_() == QFileDialog.Accepted:
            file_path = dialog.selectedFiles()[0]
        
        return file_path
    
    def ask_for_audio(self):
        file_path = self.ask_for_file(
            [
                "*.wav", "*.mp3", "*.ogg",
                "*.flac", "*.opus", "*.mp4",
                "*.mkv", "*.mov"
            ],
            "Audiofile"
        )

        if not file_path:
            return
        
        self.audio_path = file_path
        self.audio_path_button.setText(file_path.split("/")[-1])

        self.run_loading_pipeline(file_path)
    
    def ask_for_savefile(self):
        file_path = self.ask_for_file(
            ["*.json", "*.txt"],
            "BNGC Save File or Labels File"
        )

        if not file_path:
            return
        
        self.save_path = file_path
        self.save_path_button.setText(file_path.split("/")[-1])

        self.refresh_import_button()

    def setup_import_ui(self) -> None:
        self.setup_trim_section()
        self.setup_bpm_section()

        self.audio_path_button = Basic.ButtonWithOutlineSlim("Audiofile", False)
        self.save_path_button  = Basic.ButtonWithOutlineSlim("Savefile",  False)

        self.audio_path_button.setMinimumWidth(300)
        self.save_path_button.setMinimumWidth(300)

        self.cancel_button = Basic.ButtonWithOutline("Later, gator")
        self.import_button = Basic.NothingButton("Import!")

        self.import_button.setEnabled(False)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        path_row.addWidget(self.audio_path_button)
        path_row.addWidget(self.save_path_button)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.addWidget(self.bpm_input)
        bottom_row.addStretch()
        bottom_row.addWidget(self.cancel_button)
        bottom_row.addWidget(self.import_button)

        playback_row = self.build_playback_row()

        self.import_button.clicked.connect(self.on_import_callback)
        self.cancel_button.clicked.connect(self.reject_callback)

        self.audio_path_button.pressed.connect(self.ask_for_audio)
        self.save_path_button.pressed.connect(self.ask_for_savefile)

        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(path_row)
        self.content_layout.addLayout(playback_row)
        self.content_layout.addLayout(bottom_row)

    # Drag and Drop

    def dragEnterEvent(self, event) -> None:
        Player.ui_player.play_sound("App/DragDrop", speed = 1.03)
        self.move_start_animation()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        Player.ui_player.play_sound("App/DragDrop", speed = 0.94)
        self.move_end_animation()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            file_path    = url.toLocalFile()
            mime_type, _ = mimetypes.guess_type(file_path)

            if not mime_type:
                continue

            if "audio" in mime_type:
                self.audio_path = file_path
                self.audio_path_button.setText(file_path.split("/")[-1])

                self.run_loading_pipeline(file_path)

            elif mime_type in ["text/plain", "application/json"]:
                self.save_path = file_path
                self.save_path_button.setText(file_path.split("/")[-1])

                self.refresh_import_button()

        self.move_end_animation()
        self.refresh_import_button()
    
    def on_audio_ready(self):
        self.refresh_import_button()

    def refresh_import_button(self) -> None:
        self.import_button.setEnabled(
            self.audio_path is not None and
            self.save_path is not None
        )

    # Import

    def on_import_callback(self) -> None:
        if not self.validate_trim():
            self.import_button.start_glitch()
            return

        try:
            model, glyphs = Encoder.convert_to_glyphs(
                self.save_path,
                int(self.trim_widget.start_time * 1000),
                int(self.trim_widget.end_time   * 1000)
            )

        except Encoder.ZeroGlyphsError:
            ErrorWindow("No glyphs?", "The save file doesn't contain any valid glyphs. File may be corrupted.").exec_()
            return

        except Encoder.LabelsNoModelError:
            ErrorWindow("Woops.", "Unable to determine the model from the save file. File may be corrupted.").exec_()
            return

        except Encoder.UnknownFileFormatError:
            ErrorWindow("Woops.", "Unknown file format. Make sure you are importing a valid save file.").exec_()
            return

        bpm_settings = self.get_bpm_settings()

        self.settings = {
            "model": model,
            "audio": {
                "bpm":      bpm_settings["bpm"],
                "beats":    bpm_settings["beats"],
                "start_ms": self.trim_widget.start_time * 1000,
                "end_ms":   self.trim_widget.end_time   * 1000,
                "fade_in":  self.fade_in_textbox.text(),
                "fade_out": self.fade_out_textbox.text(),
            },
            "glyphs": glyphs
        }

        self.cleanup_audio()
        self.on_ok()

# Playground

class Playground(FloatingWindowGPU):
    def __init__(self):
        super().__init__("GPU Engine Master Tuner")

        self.content_widget.setMinimumWidth(1400)

        self.main_row = QHBoxLayout()
        self.main_row.setSpacing(20)
        self.content_layout.addLayout(self.main_row)

        self.setup_audio_column()
        self.setup_filter_column()
        self.setup_style_column()
        self.setup_engine_properties()

        self.bind_logic()
        self.adjustSize()

    def setup_audio_column(self) -> None:
        self.volume_slider           = Inputs.SliderWithLabel("Volume",     0,  100, 100)
        self.player_speed_slider     = Inputs.SliderWithLabel("Speed (%)", 10,  300, 100)
        self.bitcrush_mix_slider     = Inputs.SliderWithLabel("BC Mix",     0,  100,   0)
        self.bitcrush_bits_slider    = Inputs.SliderWithLabel("BC Bits",    1,   24,  16)
        self.bitcrush_down_slider    = Inputs.SliderWithLabel("Downsample", 1,   32,   1)

        self.main_row.addLayout(
            build_column(
                "Audio",
                [
                    self.volume_slider,
                    self.player_speed_slider,
                    self.bitcrush_mix_slider,
                    self.bitcrush_bits_slider,
                    self.bitcrush_down_slider
                ]
            )
        )

    def setup_filter_column(self) -> None:
        self.midpass_mix_slider     = Inputs.SliderWithLabel("Filt Mix",      0,     100,    0)
        self.midpass_freq_slider    = Inputs.SliderWithLabel("Freq (Hz)",    100,  10000, 1000)
        self.midpass_q_slider       = Inputs.SliderWithLabel("Resonance",     1,     100,   10)
        self.delay_left_slider      = Inputs.SliderWithLabel("Delay L (ms)",  0,      50,    0)
        self.delay_right_slider     = Inputs.SliderWithLabel("Delay R (ms)",  0,      50,    0)
        self.beat_threshold_slider  = Inputs.SliderWithLabel("Beat Sens.",    0,     100,   38)

        self.main_row.addLayout(
            build_column(
                "Stereo",
                [
                    self.midpass_mix_slider,
                    self.midpass_freq_slider,
                    self.midpass_q_slider,
                    self.delay_left_slider,
                    self.delay_right_slider,
                    self.beat_threshold_slider
                ]
            )
        )

    def setup_style_column(self) -> None:
        animation_styles = ["bouncy", "smooth", "roll", "glitch", "classic"]
        default_index    = animation_styles.index(self.animation_style) if self.animation_style in animation_styles else 0

        self.style_selector = Inputs.Selector(animation_styles, default_index)
        self.style_selector.setMinimumWidth(400)

        self.button_punch     = Basic.ButtonWithOutlineSlim("Title Punch")
        self.button_wobble    = Basic.ButtonWithOutlineSlim("Window Wobble")
        self.button_disturbe  = Basic.ButtonWithOutlineSlim("Disturbe FX")
        self.button_test_open = Basic.ButtonWithOutlineSlim("Test Open")

        column = QVBoxLayout()
        
        column.addWidget(Basic.DescriptionLabel("Animations"))
        column.addWidget(self.style_selector)
        column.addWidget(Basic.DescriptionLabel("Animation Triggers"))

        for button in [self.button_punch, self.button_wobble, self.button_disturbe, self.button_test_open]:
            column.addWidget(button)

        column.addStretch()
        self.main_row.addLayout(column)

    def setup_engine_properties(self) -> None:
        properties_config = {
            "rotation_x":         (-90,  90,  0,   1),
            "rotation_y":         (-90,  90,  0,   1),
            "rotation_z":         (-180, 180, 0,   1),
            "scale":              (0,    200, 100, 100),
            "opacity_background": (0,    100, 100, 100),
            "opacity_content":    (0,    100, 100, 100),
            "x_offset":           (-200, 200, 0,   100),
            "y_offset":           (-200, 200, 0,   100),
            "z_offset":           (-200, 200, 0,   100),
            "title_scale":        (0,    200, 100, 100),
            "title_rotation":     (-180, 180, 0,   1)
        }

        self.property_sliders = {}

        column = QVBoxLayout()
        column.addWidget(Basic.DescriptionLabel("Engine"))

        for prop_name, (min_value, max_value, default_value, divider) in properties_config.items():
            slider = Inputs.SliderWithLabel(
                prop_name,
                min_value,
                max_value,
                default_value
            )

            slider.setMinimumWidth(350)

            self.property_sliders[prop_name] = (slider, divider)

            column.addWidget(slider)

            slider.slider.valueChanged.connect(
                lambda value, name = prop_name, div = divider:
                self.update_engine_property(name, value, div)
            )

        column.addStretch()
        self.main_row.addLayout(column)

    def update_engine_property(
            self,
            property_name: str,
            value:         int,
            divider:       int
        ) -> None:
        
        self.animation_engine.set_property_base_value(property_name, value / divider)
        self.update()

    def bind_logic(self) -> None:
        self.volume_slider.slider.valueChanged.connect(
            lambda value: Player.player.set_volume(value / 100)
        )
        
        self.player_speed_slider.slider.valueChanged.connect(
            lambda value: Player.player.set_speed(value / 100, duration_ms = 3000)
        )

        for slider in [self.bitcrush_mix_slider, self.bitcrush_bits_slider, self.bitcrush_down_slider]:
            slider.slider.valueChanged.connect(self.update_bitcrush)

        for slider in [self.midpass_mix_slider, self.midpass_freq_slider, self.midpass_q_slider]:
            slider.slider.valueChanged.connect(self.update_midpass)

        self.delay_left_slider.slider.valueChanged.connect(self.update_delays)
        self.delay_right_slider.slider.valueChanged.connect(self.update_delays)

        self.beat_threshold_slider.slider.valueChanged.connect(
            lambda value: Player.player.onset_detector.set_threshold(value / 100)
        )

        self.style_selector.selectionChanged.connect(self.on_style_changed)
        self.button_punch.clicked.connect(lambda: self.animation_title_punch(strength = 1.5))
        self.button_wobble.clicked.connect(self.wobble)
        self.button_disturbe.clicked.connect(self.start_disturbe_animation)
        self.button_test_open.clicked.connect(self.start_open_animation)

    def on_style_changed(self, index: int, name: str) -> None:
        self.animation_style = name

    def update_bitcrush(self) -> None:
        Player.player.set_bitcrush(
            bits       = self.bitcrush_bits_slider.slider.value(),
            downsample = self.bitcrush_down_slider.slider.value(),
            mix        = self.bitcrush_mix_slider.slider.value() / 100
        )

    def update_midpass(self) -> None:
        Player.player.set_midpass(
            center_hz = self.midpass_freq_slider.slider.value(),
            q         = self.midpass_q_slider.slider.value() / 10,
            mix       = self.midpass_mix_slider.slider.value() / 100
        )

    def update_delays(self) -> None:
        Player.player.set_channel_delay(
            left_to_ms  = self.delay_left_slider.slider.value(),
            right_to_ms = self.delay_right_slider.slider.value(),
            duration_ms = 1000
        )

class ByteBeatWindow(FloatingWindowGPU):
    def __init__(self):
        super().__init__("Hm.")

        self.bytebeat_player = Player.ByteBeatPlayer()
        self.bytebeat_player.play()

        self.textbox = Inputs.Textbox("text", placeholder = "Byte Beat?", max_length = 99999)
        self.textbox.setMinimumWidth(500)
        self.textbox.safeTextChanged.connect(self.on_textbox_changed)

        examples = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "1", lambda: self.example_callback("1")),
                (Basic.ButtonWithOutline, "2", lambda: self.example_callback("2")),
                (Basic.ButtonWithOutline, "3", lambda: self.example_callback("3")),
                (Basic.ButtonWithOutline, "4", lambda: self.example_callback("4")),
                (Basic.ButtonWithOutline, "5", lambda: self.example_callback("5"))
            ]
        )

        close_button = Basic.ButtonWithOutline("Ok?")
        close_button.pressed.connect(self.on_ok)

        self.content_layout.addWidget(self.textbox)
        self.content_layout.addLayout(examples)
        self.content_layout.addWidget(close_button)
    
    def on_textbox_changed(self, text):
        self.bytebeat_player.set_formula(text)
    
    def example_callback(self, number):
        code = {
            "1": "(t * ((7 if t & 4096 else 16) + (1 if (1 & (t >> 14)) else 0) if t % 65536 < 59392 else t&7 or 16)) >> (3 & -t >> (2 if (t & 2048) else 10))",
            "2": "((t >> 10) & 42) * t",
            "3": "((t>>9^(t>>9)-1^1)%13*t&31)*(2+(t>>4))",
            "4": "t^t>>4^(t>>11+(t>>16)%3)%16*t^3*t",
            "5": "(lambda d,b,a,n,r: (((d if ((b//4)%16) in (0,3,6,10) else 0) % 64) + ((d*a[r]) % 64) + (((d*a[r])/1.33) % 64) + ((n if b%4==0 else 0) % 20) + ((n if b%32==16 else 0) % 44)))((0.127*(t*6)), int((t*6)/1578), [0,0,0,0,0,0,0,0,4,4,4.75,4.75,5.3,0,5.3,5.3,5.3,5.3,5.3,5.3,4.75,4.75,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,4,4.75,4.75,5.3,0,5.3,5.3,5.3,5.3,4.75,4.75,0,0,4,4,0,0,3.55,3.55,4,4,0,0], (0.127*(t*6))*random(), (int((t*6)/1578)//2)%64)"
        }.get(number)

        self.bytebeat_player.set_formula(code)
        self.textbox.setText(code)
    
    def closeEvent(self, event):
        self.bytebeat_player.cleanup()
        super().closeEvent(event)