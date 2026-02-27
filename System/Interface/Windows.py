import os
import math
import random
import traceback
import mimetypes
import webbrowser

import numpy as np

from loguru import logger

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from OpenGL.GL import *
from OpenGL.GL import shaders

from System.Common import Utils
from System.Common import Styles
from System.Common.Constants import *

from System.Components import Audio
from System.Components import Player
from System.Components import Encoder

from System.Interface import Inputs
from System.Interface import ThreeaD
from System.Interface import Basic
from System.Interface import Widgets

class FloatingWindowGPU(QOpenGLWidget):
    _shared_shader_program = None
    
    def __init__(
            self,
            title: str,
            parent = None,
            margin = None,
            dialog = True,
            stays_on_top = True,
            
            bpm: int = None,
            player = None,
            
            max_tilt_angle = 20,
            animation_style = None,
            enable_audioplayer_effects: bool = True,
            enable_advanced_beat_animations: bool = False,
            enable_tilt: bool = True,
            
            enable_open_animation = True,
            enable_close_animation = True,
            
            start_position: QPoint = None
        ):
        
        super().__init__(parent)

        self.bpm = bpm
        self.player = player
        self.enable_tilt = enable_tilt
        self.max_tilt_angle = max_tilt_angle
        
        self._result = None
        self._event_loop = None
        self.allow_exit = False

        self.animation_style = animation_style or CurrentSettings["animation_style"]

        self._drag_pos = None
        self.is_ready = False
        self.is_closing = False
        self.was_cancelled = False
        self.start_position = start_position
        
        self.enable_open_animation = enable_open_animation
        self.enable_close_animation = enable_close_animation
        self.enable_advanced_beat_animations = enable_advanced_beat_animations
        self.enable_transition_audio_effects = enable_audioplayer_effects

        self.margin_x = margin or 300
        self.margin_y = margin or 300
        
        self.prepare_fmt()
        self.apply_attributes(dialog, stays_on_top)
        self.setup_layout(title)
        self.setup_animation_properties()
        self.setup_timers()
        
        if self.enable_open_animation:
            QTimer.singleShot(0, self.start_open_animation)

    # Setup - - - - - - - - - - - - - - - - - - - - - - - -

    def prepare_fmt(self):
        fmt = QSurfaceFormat()
        fmt.setVersion(4, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions, False)
        
        if CurrentSettings.get("msaa"):
            fmt.setSamples(CurrentSettings["msaa"])
        
        self.setFormat(fmt)

    def apply_attributes(self, dialog, stays_on_top):
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

    @property
    def animations_enabled(self):
        return CurrentSettings.get("floating_window_animations", True)

    @property
    def bpm_animations_enabled(self):
        return self.animations_enabled and CurrentSettings.get("bpm_animations", True)

    def setup_timers(self):
        if self.animations_enabled and self.enable_tilt and self.tilt_smoothing > 0:
            self.tilt_animation_timer = QTimer(self, interval=FPS_60, timeout=self.tilt_rotation_update)
            self.tilt_animation_timer.start()

        if self.bpm_animations_enabled:
            if self.enable_advanced_beat_animations and self.player:
                self.player.beat_heavy.connect(self.beat_heavy_animation)
                self.player.beat_normal.connect(self.beat_normal_animation)
            
            else:
                self.bpm_timer = QTimer(
                    self,
                    singleShot = True,
                    timeout = self.bpm_tick_animation
                )
                
                if self.bpm:
                    self.bpm_timer.start(FPS_30)

    def setup_layout(self, title):
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

    def setup_animation_properties(self):
        # EE
        self.ee_exit_attempts = 0
        
        # Properties
        self.scale = 1.0
        self.rotation = QQuaternion()

        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self.rotation_z = 0.0
        
        self.current_tilt_x = 0.0
        self.current_tilt_y = 0.0
        
        self.target_tilt_x = 0.0
        self.target_tilt_y = 0.0
        
        self.opacity_content = 1.0
        self.opacity_background = 1.0
        
        self.x_offset = 0.0
        self.y_offset = 0.0
        self.z_offset = 0.0
        
        self.tilt_smoothing = float(CurrentSettings["window_hover_smoothing"])

        self.bpm_peak_scale = 1.03

        if not self.animations_enabled:
            logger.debug("Not creating the animator since the animations are disabled")
            
            return
        
        self.content_opacity_effect = QGraphicsOpacityEffect(self.content_widget)
        self.content_opacity_effect.setOpacity(0.0)
        self.content_widget.setGraphicsEffect(self.content_opacity_effect)

        self.animation_engine = ThreeaD.AnimationEngine(120)
        self.animation_engine.setParent(self)
        
        self.animation_engine.set_multiplier(float(CurrentSettings["animation_multiplier"]))
        
        properties = [
            ("rotation_x", 0.0, ThreeaD.MixMode.ADD),
            ("rotation_y", 0.0, ThreeaD.MixMode.ADD),
            ("rotation_z", 0.0, ThreeaD.MixMode.ADD),

            ("scale", 1.0, ThreeaD.MixMode.MULTIPLY),

            ("opacity_background", 1.0, ThreeaD.MixMode.MULTIPLY),
            ("opacity_content", 1.0, ThreeaD.MixMode.MULTIPLY),

            ("x_offset", 0.0, ThreeaD.MixMode.ADD),
            ("y_offset", 0.0, ThreeaD.MixMode.ADD),
            ("z_offset", 0.0, ThreeaD.MixMode.ADD),

            ("title_scale", 1.0, ThreeaD.MixMode.MULTIPLY),
            ("title_rotation", 0.0, ThreeaD.MixMode.ADD)
        ]

        for property in properties:
            self.animation_engine.add_property(*property)
        
        self.animation_engine.updated.connect(self.apply_animations)

    # Animations - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def apply_animations(self):
        self.scale = self.animation_engine.get_property_value("scale")
        
        self.rotation_x = self.animation_engine.get_property_value("rotation_x") + self.current_tilt_x
        self.rotation_y = self.animation_engine.get_property_value("rotation_y") + self.current_tilt_y
        self.rotation_z = self.animation_engine.get_property_value("rotation_z")

        self.rotation = QQuaternion.fromEulerAngles(self.rotation_x, self.rotation_y, self.rotation_z)
        
        self.x_offset = self.animation_engine.get_property_value("x_offset")
        self.y_offset = self.animation_engine.get_property_value("y_offset")
        self.z_offset = self.animation_engine.get_property_value("z_offset")
        
        self.opacity_content = self.animation_engine.get_property_value("opacity_content")
        self.opacity_background = self.animation_engine.get_property_value("opacity_background")
        
        self.content_opacity_effect.setOpacity(self.opacity_content)

        if self.title_label:
            self.title_label.scale = self.animation_engine.get_property_value("title_scale")
            self.title_label.rotation = self.animation_engine.get_property_value("title_rotation")
        
        self.update()

    def animation_title_punch(self, strength = 1.0):
        rotation_angle = self.period_randomizer((-40, -20), (20, 40))

        self.animation_engine.animate(
            "title_scale",
            [
                (0.0, 1.0),
                (0.5, 1.0 + 0.1 * strength),
                (1.0, 1.0)
            ], 500, ThreeaD.Easing.ease_out_cubic
        )

        self.animation_engine.animate(
            "title_rotation",
            [
                (0.0, 0.0),
                (0.5, rotation_angle),
                (1.0, 0.0)
            ], 700, ThreeaD.Easing.bouncy
        )

    def animation_title_scale(self, peak_scale = 1.2, duration = 100):
        if not self.animations_enabled or not self.animation_engine:
            return
        
        self.animation_engine.animate(
            "title_scale",
            [
                (0.0, 1.0),
                (0.5, peak_scale),
                (1.0, 1.0)
            ], duration, ThreeaD.Easing.ease_out_cubic, do_not_multiply_duration = True
        )

    def animate_resize(self, target_width, target_height):
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(500)
        
        anim.setStartValue(self.geometry())
        anim.setEndValue(
            QRect(
                self.x(),
                self.y(),
                target_width + self.margin_x,
                target_height + self.margin_y
            )
        )
        
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self.group_animate([anim], do_not_multiply_duration = True)

    def animation_open_classic(self, final_rect, size):
        self.animation_engine.animate(
            "y_offset",
            [
                (0.0, -0.2),
                (1.0, 0.0)
            ], 500, ThreeaD.Easing.bouncy
        )
        
        self.animation_engine.set_property_base_value("opacity_content", 1.0)
        self.animation_engine.set_property_base_value("opacity_background", 1.0)

    def animation_close_classic(self, size):
        self.animation_engine.animate(
            "y_offset",
            [
                (0.0, 0.0),
                (1.0, 0.1)
            ], 300, ThreeaD.Easing.ease_out_cubic
        )
        
        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 100
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 100, finished = self._really_close
        )

    def animation_open_smooth(self, final_rect, size):
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 30),
                (1.0, 0)
            ], 800, ThreeaD.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, self.maximum_scale()),
                (1.0, 1.0)
            ], 650, ThreeaD.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 250
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 200
        )

    def animation_close_smooth(self, size):
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 0),
                (1.0, -30)
            ], 500, ThreeaD.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, self.maximum_scale())
            ], 500, ThreeaD.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 300
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 500, finished = self._really_close
        )

    def animation_open_bouncy(self, final_rect, size):
        start_angle = self.period_randomizer((-55, -20), (20, 55))

        start_offset_x, start_offset_y = self.get_optimal_offset(*size)

        optimal_tilt = Utils.get_optimal_tilt(*size)
        optimal_tilt = -optimal_tilt if random.random() < 0.5 else optimal_tilt
        
        self.animation_engine.animate(
            "x_offset",
            [
                (0.0, start_offset_x),
                (1.0, 0.0)
            ], 950, ThreeaD.Easing.bouncy
        )

        self.animation_engine.animate(
            "y_offset",
            [
                (0.0, start_offset_y),
                (1.0, 0.0)
            ], 950, ThreeaD.Easing.bouncy
        )

        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, start_angle),
                (1.0, 0)
            ], 700, ThreeaD.Easing.very_bouncy
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 600, ThreeaD.Easing.ease_out_expo
        )
        
        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 800, ThreeaD.Easing.ease_out_expo
        )
    
    def animation_close_bouncy(self, size):
        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, self.maximum_scale())
            ], 400, ThreeaD.Easing.ease_out_cubic
        )
        
        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0.0),
                (1.0, Utils.get_rotation(*size, 11, 3))
            ], 500, ThreeaD.Easing.ease_out_cubic
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 200
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 450, finished = self._really_close
        )
    
    def animation_open_roll(self, final_rect, size):
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 150),
                (1.0, 0)
            ], 800, ThreeaD.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 600, ThreeaD.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 300
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 200
        )
    
    def animation_close_roll(self, size):
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 0),
                (1.0, 70)
            ], 800, ThreeaD.Easing.ease_out_expo
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 350, ThreeaD.Easing.ease_in_circ
        )

        self.animation_engine.animate(
            "opacity_content",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 400
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 700, finished = self._really_close
        )
    
    def animation_open_glitch(self, final_rect, size):
        self.animation_engine.set_property_base_value("opacity_content", 0.0)
        self.animation_engine.set_property_base_value("opacity_background", 0.0)
        
        actions = [
            (150, "scale", random.uniform(0.1, 0.4)),
            (270, "scale", random.uniform(0.7, 0.85)),
            (485, "scale", 1.0),
            
            (150, "opacity_content", random.uniform(0.2, 0.5)),
            (270, "opacity_content", random.uniform(0.5, 0.8)),
            (485, "opacity_content", 1.0),
            
            (150, "opacity_background", random.uniform(0.2, 0.5)),
            (270, "opacity_background", random.uniform(0.5, 0.8)),
            (485, "opacity_background", 1.0),
            
            (150, "rotation_z", random.randint(-30, 30)),
            (270, "rotation_z", random.randint(-10, 10)),
            (485, "rotation_z", 0.0)
        ]
        
        self.plan_timers(actions)
    
    def animation_close_glitch(self, size):
        actions = [
            (400, "scale", random.uniform(0.1, 0.4)),
            (570, "scale", 0.0),
            
            (400, "opacity_content", random.uniform(0.2, 0.5)),
            (570, "opacity_content", 0.0),
            
            (400, "opacity_background", random.uniform(0.2, 0.5)),
            (570, "opacity_background", 0.0),
            
            (400, "rotation_z", random.randint(-10, 10)),
            (570, "rotation_z", random.randint(-40, 40)),
        ]
        
        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 0.8)
            ], 210, ThreeaD.Easing.ease_out_cubic, do_not_multiply_duration = True
        )
        
        QTimer.singleShot(580, self._really_close)
        
        self.plan_timers(actions)

    def bpm_tick_animation(self):
        if not self.player.is_playing:
            return self.bpm_timer.start(FPS_30)
        
        audio_level = self.player.get_current_audio_level()

        if audio_level < 0.08:
            return self.bpm_timer.start(FPS_30)

        speed = self.player.speed or 0.01
        interval_ms = int(round(60000.0 / (self.bpm * speed)))
        QApplication.setCursorFlashTime(interval_ms)

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, self.bpm_peak_scale + self.squish(audio_level)),
                (1.0, 1.0)
            ],
            interval_ms, ThreeaD.Easing.ease_out_cubic, do_not_multiply_duration = True
        )

        self.bpm_timer.start(interval_ms)

    def beat_normal_animation(self, strength):
        if not self.animations_enabled or not self.animation_engine:
            return

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, self.bpm_peak_scale + strength * 0.06),
                (1.0, 1.0)
            ],
            400, ThreeaD.Easing.ease_out_cubic, do_not_multiply_duration = True
        )
    
    def beat_heavy_animation(self, strength):
        if not self.animations_enabled or not self.animation_engine:
            return

        self.animation_engine.animate(
            "y_offset",
            [
                (0.0, 0.0),
                (0.5, strength * random.choice([0.1, -0.1])),
                (1.0, 0.0)
            ],
            400, ThreeaD.Easing.ease_out_cubic, do_not_multiply_duration = True
        )

    def move_start_animation(self):
        if not CurrentSettings["floating_window_animations"]:
            return
        
        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 1.03)
            ], 250, ThreeaD.Easing.ease_out_cubic
        )

        self.animation_title_scale(1.15, 500)
    
    def move_end_animation(self):
        if not CurrentSettings["floating_window_animations"]:
            return
        
        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (1.0, 0.97)
            ], 400, ThreeaD.Easing.ease_out_cubic
        )

    def wobble(self):
        if not CurrentSettings["floating_window_animations"]:
            return

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, 1.05),
                (1.0, 1.0)
            ], 500, ThreeaD.Easing.ease_out_cubic
        )

    def animation_disturbe_bouncy(self):
        start_angle = random.choice([
            random.randint(-20, -10),
            random.randint(10, 20)
        ])

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, 1.3),
                (1.0, 1.0)
            ], 500, ThreeaD.Easing.ease_out_cubic
        )
        
        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0.0),
                (0.5, start_angle),
                (1.0, 0.0)
            ], 1000, ThreeaD.Easing.bouncy
        )

    def animation_disturbe_roll(self):
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 0.0),
                (0.5, 20),
                (1.0, 0.0)
            ], 1100, ThreeaD.Easing.bouncy
        )

        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, 1.1),
                (1.0, 1.0)
            ], 1200, ThreeaD.Easing.bouncy
        )
    
    def animation_disturbe_classic(self):
        angle = self.period_randomizer((-30, -15), (15, 30))
        
        self.animation_engine.animate(
            "scale",
            [
                (0.0, 1.0),
                (0.5, 1.05),
                (1.0, 1.0)
            ], 320
        )
        
        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0.0),
                (0.5, angle),
                (1.0, 0.0)
            ], 900, ThreeaD.Easing.very_bouncy
        )
    
    def animation_disturbe_glitch(self):
        actions = [
            (5, "scale", random.uniform(1.02, 1.1)),
            (80, "scale", 1.0),
            
            (5, "rotation_z", random.randint(-30, 30)),
            (80, "rotation_z", 0)
        ]
        
        self.plan_timers(actions)
    
    def animation_disturbe_smooth(self):
        self.animation_engine.animate(
            "rotation_x",
            [
                (0.0, 0.0),
                (0.5, 30),
                (1.0, 0.0)
            ], 600, ThreeaD.Easing.ease_out_expo
        )
    
    def animation_random_rotate(self):
        if not CurrentSettings["floating_window_animations"]:
            return
        
        self.animation_engine.animate(
            "rotation_z",
            [
                (0.0, 0),
                (0.5, self.period_randomizer((-6, -3), (3, 6))),
                (1.0, 0)
            ], 350, ThreeaD.Easing.ease_out_cubic
        )

    def start_exit_animation(self):
        if not self.enable_close_animation:
            return
        
        if not CurrentSettings["floating_window_animations"]:
            return self._really_close()

        size = self.get_window_size()

        {
            "bouncy": self.animation_close_bouncy,
            "smooth": self.animation_close_smooth,
            "roll": self.animation_close_roll,
            "glitch": self.animation_close_glitch,
            "classic": self.animation_close_classic
        }.get(self.animation_style)(size)
    
    def start_disturbe_animation(self):
        self.disturbe_sound()
        
        if not CurrentSettings["floating_window_animations"]:
            return
        
        {
            "bouncy": self.animation_disturbe_bouncy,
            "smooth": self.animation_disturbe_smooth,
            "roll": self.animation_disturbe_roll,
            "glitch": self.animation_disturbe_glitch,
            "classic": self.animation_disturbe_classic
        }.get(self.animation_style)()
    
    def start_open_animation(self):
        self.adjustSize()
        final_rect = self.center_window()
        self.is_ready = True
        self.open_sound()

        size = self.get_window_size()

        if not CurrentSettings["floating_window_animations"]:
            return

        {
            "bouncy": self.animation_open_bouncy,
            "smooth": self.animation_open_smooth,
            "roll": self.animation_open_roll,
            "glitch": self.animation_open_glitch,
            "classic": self.animation_open_classic
        }.get(self.animation_style)(final_rect, size)

    # Basic Physics - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def tilt_rotation_update(self):
        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)
        
        center_x = self.width() / 2
        center_y = self.height() / 2

        widget_rect = self.content_widget.rect()
        top_left_global = self.content_widget.mapToGlobal(widget_rect.topLeft())
        content_rect_global = QRect(top_left_global, widget_rect.size())

        if content_rect_global.contains(global_pos):
            x_norm = -(local_pos.x() - center_x) / center_x
            y_norm = (local_pos.y() - center_y) / center_y

            self.target_tilt_x = y_norm * self.max_tilt_angle
            self.target_tilt_y = -x_norm * self.max_tilt_angle
        
        self.current_tilt_x += (self.target_tilt_x - self.current_tilt_x) * self.tilt_smoothing
        self.current_tilt_y += (self.target_tilt_y - self.current_tilt_y) * self.tilt_smoothing
    
    # Render - - - - - - - - - - - - - - - - - - - - - - - -
    
    def initializeGL(self):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0, 0, 0, 0)

        if not self._shared_shader_program:
            vs = shaders.compileShader(FLOATING_WINDOW_VS, GL_VERTEX_SHADER)
            fs = shaders.compileShader(FLOATING_WINDOW_FS, GL_FRAGMENT_SHADER)
            self._shared_shader_program = shaders.compileProgram(vs, fs, validate = False)

        vertices = np.array(
            [
                1.0,   1.0, 0.0, 1.0, 1.0,
                1.0,  -1.0, 0.0, 1.0, 0.0,
                -1.0, -1.0, 0.0, 0.0, 0.0,
                -1.0,  1.0, 0.0, 0.0, 1.0 
            ], dtype = np.float32
        )

        indices = np.array([0, 1, 3, 1, 2, 3], dtype=np.uint32)

        self.VAO = glGenVertexArrays(1)
        glBindVertexArray(self.VAO)
        
        self.VBO = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.VBO)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        
        self.EBO = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.EBO)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 20, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 20, ctypes.c_void_p(12))
        glEnableVertexAttribArray(1)
        
        glBindVertexArray(0)
        
        self.location_size = glGetUniformLocation(self._shared_shader_program, "u_size")
        self.location_radius = glGetUniformLocation(self._shared_shader_program, "u_radius")
        self.location_border_px = glGetUniformLocation(self._shared_shader_program, "u_borderThicknessPixels")
        self.location_rect_color = glGetUniformLocation(self._shared_shader_program, "u_rectColor")
        self.location_border_color = glGetUniformLocation(self._shared_shader_program, "u_borderColor")
        self.location_rect_alpha = glGetUniformLocation(self._shared_shader_program, "u_rectAlpha")
        self.location_border_alpha = glGetUniformLocation(self._shared_shader_program, "u_borderAlpha")
        self.location_global_alpha = glGetUniformLocation(self._shared_shader_program, "u_globalAlpha")
    
        self.location_mvp = glGetUniformLocation(self._shared_shader_program, "u_curr_mvp")

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glUseProgram(self._shared_shader_program)

        glEnable(GL_BLEND)
        glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)

        content_rect = self.content_widget.geometry()
        cw, ch = float(content_rect.width()), float(content_rect.height())

        if cw < 1 or ch < 1: return

        mvp_final = self.calculate_matrix()

        glUniform2f(self.location_size, cw, ch)
        glUniform1f(self.location_radius, 16.0)
        glUniform1f(self.location_border_px, 2.0)
        glUniform4f(self.location_rect_color, 0.17, 0.17, 0.17, 1.0)
        glUniform4f(self.location_border_color, 0.25, 0.25, 0.25, 1.0)
        glUniform1f(self.location_rect_alpha, self.opacity_background)
        glUniform1f(self.location_border_alpha, self.opacity_background)
        glUniform1f(self.location_global_alpha, 1.0)
        
        glUniformMatrix4fv(self.location_mvp, 1, GL_FALSE, mvp_final.data())

        glBindVertexArray(self.VAO)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
    
    def calculate_matrix(self, scale = None, content_w = None, content_h = None):
        if not content_w:
            content_w = self.content_widget.width()
        
        if not content_h:
            content_h = self.content_widget.height()
        
        mvp = QMatrix4x4()
        
        fov = 45.0
        z_dist = 3.0
        aspect = self.width() / self.height()
    
        mvp.perspective(fov, aspect, 0.1, 100.0)
        mvp.translate(0.0, 0.0, -z_dist)
    
        visible_height_at_z = 2.0 * math.tan(math.radians(fov / 2.0)) * z_dist
        pixel_unit = visible_height_at_z / self.height()
    
        if self.animations_enabled:
            mvp.rotate(self.rotation)
            mvp.translate(self.x_offset, self.y_offset, self.z_offset)
            mvp.scale(self.scale)
        
        mvp.scale((content_w * pixel_unit) / 2.0, (content_h * pixel_unit) / 2.0)
        
        return mvp
    
    # Events - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def closeEvent(self, event):
        if self.allow_exit:
            super().closeEvent(event)
        
        else:
            self.ee_exit_attempts += 1
            
            if random.random() < 0.5:
                if self.ee_exit_attempts == 50:
                    Utils.ui_sound("CostOptimizer/WAYD")
                    
                    if self.title_label:
                        self.title_label.setText("What are you doing?")
                
                if self.ee_exit_attempts == 70:
                    Utils.ui_sound("CostOptimizer/HCYLWY")
                    
                    if self.title_label:
                        self.title_label.setText("???")
                
                if self.ee_exit_attempts > 70:
                    self.chaos_mode()
                
                if self.ee_exit_attempts == 100:
                    if self.title_label:
                        Utils.ui_sound("CostOptimizer/ONYD")

                        self.title_label.setText("Dividing by zero: 3")

                        QTimer.singleShot(1000, lambda: self.title_label.setText("Dividing by zero: 2"))
                        QTimer.singleShot(2000, lambda: self.title_label.setText("Dividing by zero: 1"))
                        QTimer.singleShot(2500, lambda: self.title_label.setText("LMAO"))
                        QTimer.singleShot(2100, lambda: Utils.ui_sound("NOK/Charging"))
                        QTimer.singleShot(3000, lambda: 1 / 0)
            
            event.ignore()
            self.start_disturbe_animation()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        
        if self.title_label:
            label_rect = self.title_label.geometry()
            local_pos = self.content_widget.mapFrom(self, event.pos())
            
            if label_rect.contains(local_pos):
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                self.move_start_animation()
                QTimer.singleShot(0, self.window().windowHandle().startSystemMove)

                event.accept()

        else:
            rect = self.content_widget.geometry()
            
            if rect.contains(event.pos()):
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                self.move_start_animation()
                QTimer.singleShot(0, self.window().windowHandle().startSystemMove)

                event.accept()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_pos:
            self.move_end_animation()
        
        self._drag_pos = None
    
    # Utils - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    def get_optimal_offset(self, width, height, limit = 500):
        scale_x = limit / max(width, limit)
        scale_y = limit / max(height, limit)

        start_offset_x = self.period_randomizer(
            (-0.35 * scale_x, -0.2 * scale_x), 
            (0.2 * scale_x, 0.35 * scale_x)
        )

        start_offset_y = self.period_randomizer(
            (-0.5 * scale_y, -0.2 * scale_y), 
            (0.2 * scale_y, 0.5 * scale_y)
        )

        return start_offset_x, start_offset_y
    
    def chaos_mode(self):
        widgets = self.content_widget.findChildren(QWidget)

        for widget in widgets:
            dx = random.randint(-10, 10)
            dy = random.randint(-10, 10)
            dw = random.randint(-10, 10)

            widget.move(widget.x() + dx, widget.y() + dy)
            widget.resize(widget.width() + dw, widget.height() + dw)
    
    def plan_timers(self, actions: list[tuple]):
        for delay, attr, value in actions:
            QTimer.singleShot(
                delay,
                lambda a = attr, v = value: self.animation_engine.set_property_base_value(a, v)
            )

    def on_ok(self):
        if self.is_closing:
            return

        self.is_closing = True
        self.was_cancelled = False
        
        self.close_sound()
        self.start_exit_animation()

    def on_cancel(self):
        if self.is_closing:
            return

        self.is_closing = True
        self.was_cancelled = True
        
        self.close_sound()
        self.start_exit_animation()

    def adjustSize(self):
        if self.is_ready:
            size = self.content_widget.sizeHint()
            
            self.animate_resize(
                size.width(),
                size.height()
            )

        else:
            return super().adjustSize()
    
    def update_bpm(self, bpm = None):
        if not bpm:
            return
        
        if bpm >= 200:
            self.bpm = int(bpm / 2)
        
        if bpm <= 80:
            self.bpm = int(bpm * 2)
        
        else:
            self.bpm = int(bpm)

        if self.bpm_animations_enabled and not self.enable_advanced_beat_animations:
            self.bpm_timer.setInterval(60000 // self.bpm)
            self.bpm_timer.start()
    
    def set_bpm_peak_size(self, start_coeff):
        self.bpm_peak_scale = start_coeff
    
    def make_animation(self, keyframes: list, property, duration: int, curve: QEasingCurve = QEasingCurve.OutCubic, finished = None):
        anim = QPropertyAnimation(self, property)
        anim.setDuration(duration)
        anim.setKeyValues(keyframes)
        anim.setEasingCurve(curve)
        
        if finished:
            anim.finished.connect(finished)

        return anim

    def period_randomizer(self, *periods):
        function = random.randint

        if isinstance(periods[0][0], float):
            function = random.uniform

        period = random.choice(periods)
        return function(*period)

    def center_window(self):
        if self.start_position:
            final_rect = QRect(
                self.start_position.x() - self.margin_x,
                self.start_position.y() - self.margin_y,
                self.width(),
                self.height()
            )
            
            self.setGeometry(final_rect)
            return final_rect
            
        window = QApplication.activeWindow()
        
        if window:
            window_center = window.geometry().center()
        
        else:
            window_center = QApplication.primaryScreen().geometry().center()
        
        final_rect = QRect(
            window_center.x() - self.width() // 2,
            window_center.y() - self.height() // 2,
            self.width(), self.height()
        )

        self.setGeometry(final_rect)

        return final_rect
    
    def player_pulse(self, duration = 0.4, pulse_peak_speed = 1.2):
        start_speed = self.player.speed
        duration_half = duration / 2

        self.player.set_speed(pulse_peak_speed, duration = duration_half)
        QTimer.singleShot(int(duration_half * 1000), lambda: self.player.set_speed(start_speed, duration = duration_half))
    
    def open_sound(self):
        if self.enable_transition_audio_effects:
            if self.player:
                if self.player.is_playing:
                    return self.player_pulse()

        Utils.ui_sound(
            {
                "bouncy": "BouncyPack/Open",
                "smooth": "SmoothPack/Open",
                "roll": "SmoothPack/Open",
                "glitch": "GlitchPack/Open",
                "classic": "ClassicPack/Open"
            }.get(self.animation_style)
        )
    
    def close_sound(self):
        if self.enable_transition_audio_effects:
            if self.player:
                if self.player.is_playing:
                    return self.player_pulse(0.4, 0.5)

        Utils.ui_sound(
            {
                "bouncy": "BouncyPack/Close",
                "smooth": "SmoothPack/Close",
                "roll": "SmoothPack/Close",
                "glitch": "GlitchPack/Close",
                "classic": "ClassicPack/Close"
            }.get(self.animation_style)
        )
    
    def disturbe_sound(self):
        if self.enable_transition_audio_effects:
            if self.player:
                if self.player.is_playing:
                    return self.player_pulse(0.4, 2.0)
        
        Utils.ui_sound(
            {
                "bouncy": "BouncyPack/Disturbe",
                "smooth": "SmoothPack/Disturbe",
                "roll": "SmoothPack/Disturbe",
                "glitch": f"GlitchPack/Disturbe{random.randint(1, 3)}",
                "classic": "ClassicPack/Disturbe"
            }.get(self.animation_style)
        )
    
    def squish(self, x, power = 1.2):
        return 0.05 * (x ** power)
    
    def pixels_to_normalized(self, width_px, height_px, viewport_width, viewport_height):
        norm_width = (width_px / viewport_width) * 2.0
        norm_height = (height_px / viewport_height) * 2.0
        
        return norm_width, norm_height
    
    def get_window_size(self):
        geometry = self.content_widget.geometry()
        return geometry.width(), geometry.height()
    
    def group_animate(self, animations, finished = None, valueChanged = None, multiplier = 1.0, do_not_multiply_duration = False):
        self.anim_group = QParallelAnimationGroup(self)

        if multiplier == 1.0 and not do_not_multiply_duration:
            multiplier = float(CurrentSettings["animation_multiplier"])
        
        else:
            multiplier = 1.0

        if multiplier != 1.0:
            for animation in animations:
                animation.setDuration(int(animation.duration() * multiplier))

        for animation in animations:
            if valueChanged:
                animation.valueChanged.connect(valueChanged)
            
            self.anim_group.addAnimation(animation)
        
        if finished:
            self.anim_group.finished.connect(finished)

        self.anim_group.start(QAbstractAnimation.DeleteWhenStopped)
    
    def maximum_scale(self):
        real_width = self.geometry().width()
        real_height = self.geometry().height()
        
        width = self.content_widget.width()
        height = self.content_widget.height()
        
        c1 = max(width, height)
        c2 = max(real_width, real_height)
        
        coeff = c1 / c2
        
        return 1.0 + (1.0 - coeff)

    def _really_close(self):
        if self.animations_enabled:
            self.animation_engine.clear()
            self.animation_engine.updated.disconnect()
            self.animation_engine = None
        
        if self.animations_enabled:
            if self.bpm_animations_enabled and not self.enable_advanced_beat_animations:
                self.bpm_timer.stop()
            
            if self.enable_tilt and self.tilt_smoothing > 0:
                self.tilt_animation_timer.stop()
        
        self.allow_exit = True
        self.close()
        
        if self._event_loop:
            self._event_loop.quit()
    
    def exec_(self):
        self.setWindowModality(Qt.ApplicationModal)
        
        self.show()
        self._event_loop = QEventLoop()
        self._event_loop.exec_()
        
        self.deleteLater()
        
        return not self.was_cancelled

    def accept(self):
        self._result = True
        self.on_ok()

    def reject(self):
        self._result = False
        self.on_cancel()
    
    def __del__(self):
        logger.warning("Floating Window has been removed from RAM")

class DialogInputWindow(FloatingWindowGPU):
    def __init__(
            self,
            title = "Input Dialog",
            placeholder = "Type something...",
            min_number = 0,
            max_number = 100,
            max_length = 100,
            input_type = "number",
            bpm = None,
            player = None
        ):

        super().__init__(
            title,
            bpm = bpm,
            player = player
        )

        self.input_field = Inputs.Textbox(min_number, max_number, max_length, input_type)
        self.input_field.setMinimumWidth(200)
        self.input_field.setPlaceholderText(placeholder)
        
        self.button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Cancel", self.on_cancel, False),
                (Basic.NothingButton, "OK", self.on_ok, False)
            ]
        )

        self.content_layout.addWidget(self.input_field)
        self.content_layout.addLayout(self.button_row)

        self.input_field.returnPressed.connect(self.on_ok)

    def on_ok(self):
        text = self.input_field.text()
        
        if not text:
            self.button_row.buttons["OK"].start_glitch()
            self.start_disturbe_animation()

            return

        super().on_ok()

    def get_text(self):
        return self.input_field.text()

class ExportDialogWindow(FloatingWindowGPU):
    selectionChanged = pyqtSignal(str)
    
    def __init__(
            self,
            title,
            composition,
            bpm = None,
            player = None
        ):

        super().__init__(
            title,
            bpm = bpm,
            player = player
        )

        self.composition = composition

        original_model = code_to_number_model(composition.model)
        choices = PortVariants[composition.model] + [original_model]
        self.combobox = Inputs.Selector(choices, default_index = -1)

        button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Later", self.on_cancel),
                (Basic.ButtonWithOutline, "Export to every model", self.export_all),
                (Basic.NothingButton, "Tape it", self.export)
            ]
        )

        self.content_layout.addWidget(self.combobox)
        self.content_layout.addLayout(button_row)
    
    def export(self):
        model = self.combobox.currentText()

        self.composition.export(
            number_model_to_code(model),
            open_folder = True
        )
    
    def export_all(self):
        if self.is_closing:
            return

        self.on_ok()
        self.composition.export_all()

class DialogWindow(FloatingWindowGPU):
    def __init__(self, title):
        super().__init__(title)

        button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Nah", self.on_cancel),
                (Basic.NothingButton, "Hell yeah", self.on_ok)
            ]
        )

        self.content_layout.addLayout(button_row)

class SegmentEditor(FloatingWindowGPU):
    def __init__(
            self,
            title,
            segment_num = None,
            defaults = None,

            bpm = None,
            player = None,
        ):

        super().__init__(
            title,
            bpm = bpm,
            player = player
        )

        self.segmented_bar = Inputs.SegmentedBar(segment_num, defaults)

        upper_button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Enable all", self.segmented_bar.enable_all),
                (Basic.ButtonWithOutline, "Disable all", self.segmented_bar.disable_all),
                (Basic.ButtonWithOutline, "Zebra", self.segmented_bar.zebra)
            ]
        )

        lower_button_row = Basic.ButtonRow(
            [
                (Basic.ButtonWithOutline, "Nah", self.on_cancel),
                (Basic.NothingButton, "Apply", self.on_ok)
            ]
        )
        
        self.content_layout.addWidget(self.segmented_bar)
        self.content_layout.addLayout(upper_button_row)
        self.content_layout.addLayout(lower_button_row)

        self.segmented_bar.segment_changed.connect(self.wobble)

    def segments(self):
        return self.segmented_bar.active

class ErrorWindow(FloatingWindowGPU):
    def __init__(self, title, description, button_text = "Cool", bpm = None, player = None):
        super().__init__(title, bpm = bpm, player = player)

        ok_button = Basic.NothingButton(button_text)
        description_label = Basic.DescriptionLabel(description)

        self.content_layout.addWidget(description_label)
        self.content_layout.addWidget(ok_button)

        ok_button.clicked.connect(self.on_ok)

        self.title_label.start_glitch()

class About(FloatingWindowGPU):
    def __init__(self):
        super().__init__(f"Cassette {open('version').read()} by chips047")

        text = f"The best open - source compositor. Currently in active development!\n\n`Inspirations and credits`\n- Most UI sounds from `R.E.P.O.` game by `semiwork`.\n- UI Open sound from `The Upturned` game by `Zeekers`."
        
        self.about_label = Basic.DescriptionLabel(text, 500)

        self.image_pixmap = QPixmap("System/Assets/Image/Version.png").scaled(
            500, 500,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label = QLabel()
        self.image_label.setPixmap(self.image_pixmap)

        ok_button = Basic.NothingButton("Five Stars?")
        ok_button.clicked.connect(self.on_ok)

        github_button = Basic.ButtonWithOutline("Check for updates on GitHub")
        github_button.clicked.connect(self.on_github)

        self.content_layout.addWidget(self.about_label)
        self.content_layout.addWidget(self.image_label)

        self.content_layout.addWidget(github_button)
        self.content_layout.addWidget(ok_button)
    
    def on_github(self):
        github = GITHUB_LINK
        # fomx

        if random.random() < 0.95:
            webbrowser.open(github)
        
        else:
            fomx = Utils.get_fox_image()

            if fomx:
                webbrowser.open(fomx)

            else:
                webbrowser.open(github)

class Settings(FloatingWindowGPU):
    def __init__(self):
        super().__init__("Settings", max_tilt_angle = 10)
        self.settings = QSettings("chips047", "Cassette")

        self.title_label.setFont(Utils.NType(30))
        self.nav_widget = QWidget()
        self.nav_widget.setFixedHeight(50)
        self.nav_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {Styles.Colors.third_background};
                border-radius: 23px;
            }}
        """)

        self.nav_layout = QHBoxLayout(self.nav_widget)
        self.nav_layout.setContentsMargins(5, 5, 5, 5)
        self.nav_layout.setSpacing(8)
        self.nav_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.content_layout.addWidget(self.nav_widget)

        self.stacked_widget = QStackedWidget()
        self.content_layout.addWidget(self.stacked_widget)

        self.ok_button = Basic.NothingButton("Apply!")
        self.cancel_button = Basic.ButtonWithOutline("What")
        
        self.button_row = QHBoxLayout()
        self.button_row.setSpacing(10)
        self.button_row.addWidget(self.cancel_button)
        self.button_row.addWidget(self.ok_button)
        self.content_layout.addLayout(self.button_row)
        
        self.nav_buttons = []
        self.pages = {}
        self.controls = {}

        self.ok_button.pressed.connect(self.apply_and_close)
        self.cancel_button.pressed.connect(self.on_cancel)
    
    def change_page(self, page_widget):
        self.stacked_widget.setCurrentWidget(page_widget)
        for button, widget in self.pages.values():
            button.setActive(widget == page_widget)

    def init_settings(self, setting_components):
        first_page_widget = None

        for page_name, components in setting_components.items():
            page_widget = QWidget()
            page_layout = QVBoxLayout(page_widget)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(15)
            page_layout.setAlignment(Qt.AlignTop)

            nav_btn = Inputs.NavButton(page_name)
            nav_btn.clicked.connect(lambda _, w=page_widget: self.change_page(w))
            self.nav_layout.addWidget(nav_btn)
            self.nav_buttons.append(nav_btn)

            self.pages[page_name] = (nav_btn, page_widget)
            if first_page_widget is None:
                first_page_widget = page_widget

            for element_params in components:
                widget = None
                element_type = element_params["type"]
                saved_value = self.settings.value(element_params["key"])

                if element_type == "checkbox":
                    widget = Inputs.CheckboxWithLabel(
                        element_params["title"],
                        element_params["description"],
                        str(saved_value).lower() == "true" if saved_value is not None
                        else element_params["default"]
                    )

                elif element_type == "textbox":
                    widget = Inputs.TextboxWithLabel(
                        element_params["title"],
                        element_params["min"],
                        element_params["max"],
                        saved_value or element_params["default"]
                    )

                elif element_type == "slider":
                    widget = Inputs.SliderWithLabel(
                        element_params["title"],
                        element_params["min"],
                        element_params["max"],
                        int(saved_value) or element_params["default"]
                    )

                elif element_type == "selector":
                    widget = Inputs.SelectorWithLabel(
                        element_params["title"],
                        element_params["map"],
                        default_text = element_params["default"] if saved_value is None else None,
                        default_value = saved_value
                    )
                
                if widget:
                    self.controls[element_params["key"]] = widget
                    page_layout.addWidget(widget)

            self.stacked_widget.addWidget(page_widget)

        self.change_page(first_page_widget)

    def save_settings(self):
        for key, widget in self.controls.items():
            value = None

            if isinstance(widget, Inputs.CheckboxWithLabel):
                value = widget.isChecked()
            
            elif isinstance(widget, Inputs.SliderWithLabel):
                value = widget.value()
            
            elif isinstance(widget, Inputs.SelectorWithLabel):
                value = widget.currentData()
            
            elif isinstance(widget, Inputs.TextboxWithLabel):
                value = widget.getValue()

            if value is not None:
                self.settings.setValue(key, value)
        
        self.settings.sync()
        load_settings()

    def apply_and_close(self):
        super().on_ok()
        self.save_settings()

class GlyphVisualizer(FloatingWindowGPU):
    def __init__(
            self,
            parent,
            model: str,
            player = None,
            bpm = None
        ):

        super().__init__(
            None,
            bpm = bpm,
            player = player,
            
            margin = 50,
            max_tilt_angle = 9,

            enable_open_animation = False,
            enable_close_animation = False
        )
        
        self.parent = parent
        self.map_data = ModelVisualizerMaps[model]
        self.map_w, self.map_h = self.map_data["size"]
        
        self.visual_scale: float = 1.0
        self.target_scale: float = 1.0
        self.scale_smoothing: float = 0.15
        
        self.glyphs_gpu = []
        self.total_segments = 0
        
        self._setup_timers()
        self._init_geometry()
        self._init_shared_buffer()
        
        self.scale_in()
        self._sync_size_delayed()

    def scale_in(self):
        if not self.animations_enabled:
            return
        
        self.animation_engine.animate(
            "scale",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 1000, 
            
            ThreeaD.Easing.ease_out_quart,
            do_not_multiply_duration = True
        )

        self.animation_engine.animate(
            "opacity_background",
            [
                (0.0, 0.0),
                (1.0, 1.0)
            ], 175, 
            do_not_multiply_duration = True
        )
    
    def scale_out(self, cleanup: bool):
        if not self.animations_enabled:
            
            if cleanup:
                self._really_close
            
            return

        self.animation_engine.animate(
            "scale", [
                (0.0, 1.0),
                (1.0, 0.0)
            ], 500, 
            
            ThreeaD.Easing.ease_in_quart, 
            self._really_close if cleanup else None, True
        )
    
    def set_schedule(self, schedule_dict):
        for g in self.glyphs_gpu:
            g["schedule"] = list(schedule_dict.get(g["id"], {}).values())

    def play_all(self, ms_start: int = 0) -> None:
        self.virtual_time = ms_start
        self.last_process_time = 0

        self.elapsed.start()
        self.timer.start()

    def stop_all(self):
        self.timer.stop()
        self.virtual_time = 0
        self.last_process_time = 0
        self.global_levels.fill(0)
        self.update()

    def _setup_timers(self):
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(200)
        self.resize_timer.timeout.connect(self._sync_size_delayed)

        self.timer = QTimer(self)
        self.timer.setInterval(FPS_60)
        self.timer.timeout.connect(self._process_schedule)
        self.elapsed = QElapsedTimer()

    def _init_geometry(self):
        current_global_offset = 0
        
        for gid, data in self.map_data["glyphs"].items():
            glyph = self._process_single_glyph(gid, data, current_global_offset)
            self.glyphs_gpu.append(glyph)
            current_global_offset += glyph["num_segs"]
        
        self.total_segments = current_global_offset
        self.global_levels = np.zeros(self.total_segments, dtype=np.float32)

    def _init_shared_buffer(self) -> None:
        self.levels_tex = glGenTextures(1)
        
        glBindTexture(GL_TEXTURE_1D, self.levels_tex)
        glTexImage1D(GL_TEXTURE_1D, 0, GL_R32F, self.total_segments, 0, GL_RED, GL_FLOAT, None)
        glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)

    def _process_single_glyph(self, gid: str, data: dict, global_offset: int):
        path = Utils.parse_svg_path_data(data["svg"])
        num_segs = data.get("segments", 1)
        px, py = data["position"]
        pts_per_seg = 60

        total_length = path.length()
        seg_length = total_length / num_segs
        
        all_verts, starts, counts = [], [], []
        cur_vbo_offset = 0

        for s in range(num_segs):
            seg_start_dist = s * seg_length
            seg_end_dist = (s + 1) * seg_length
            
            points = []
            
            for i in range(pts_per_seg):
                dist = seg_start_dist + (i / (pts_per_seg - 1)) * (seg_end_dist - seg_start_dist)
                t = path.percentAtLength(dist)
                pt = path.pointAtPercent(t)
                points.append([pt.x() + px - self.map_w/2, -(pt.y() + py) + self.map_h/2])
            
            points = np.array(points, dtype=np.float32)
            seg_verts = self._calculate_segment_geometry(points, global_offset + s)
            
            all_verts.append(seg_verts)
            num_verts = len(seg_verts) // 5
            
            starts.append(cur_vbo_offset)
            counts.append(num_verts)
            
            cur_vbo_offset += num_verts

        return {
            "id": gid,
            "vbo_data": np.concatenate(all_verts).astype(np.float32),
            "starts": np.array(starts, dtype=np.int32),
            "counts": np.array(counts, dtype=np.int32),
            "num_segs": num_segs,
            "global_base_idx": global_offset,
            "schedule": []
        }

    def _calculate_segment_geometry(self, points: np.ndarray, global_idx: int) -> np.ndarray:
        diffs = np.diff(points, axis=0)
        tangents = np.vstack([diffs, diffs[-1:]])
        norms = np.stack([-tangents[:, 1], tangents[:, 0]], axis=1)
        lengths = np.linalg.norm(norms, axis=1, keepdims=True)
        norms /= np.where(lengths == 0, 1.0, lengths)
        
        idx_f = float(global_idx)
        res = np.zeros((len(points) * 2, 5), dtype=np.float32)
        
        for i, (p, n) in enumerate(zip(points, norms)):
            res[i * 2] = [p[0], p[1], n[0], n[1], idx_f]
            res[i * 2 + 1] = [p[0], p[1], -n[0], -n[1], idx_f]
        
        return res.flatten()

    def initializeGL(self) -> None:
        super().initializeGL()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        
        self.prog = shaders.compileProgram(
            shaders.compileShader(GLYPH_VS, GL_VERTEX_SHADER),
            shaders.compileShader(GLYPH_FS, GL_FRAGMENT_SHADER)
        )

        self.locs = {
            "mvp": glGetUniformLocation(self.prog, "mvp"),
            "thickness": glGetUniformLocation(self.prog, "uThickness"),
            "levels_tex": glGetUniformLocation(self.prog, "uLevelsTex")
        }

        for g in self.glyphs_gpu:
            g["vao"], g["vbo"] = glGenVertexArrays(1), glGenBuffers(1)
            glBindVertexArray(g["vao"])
            glBindBuffer(GL_ARRAY_BUFFER, g["vbo"])
            glBufferData(GL_ARRAY_BUFFER, g["vbo_data"].nbytes, g["vbo_data"], GL_STATIC_DRAW)
            
            stride = 20
            
            for i, size, offset in [(0, 2, 0), (1, 2, 8), (2, 1, 16)]:
                glVertexAttribPointer(i, size, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(offset))
                glEnableVertexAttribArray(i)

    def paintGL(self) -> None:
        super().paintGL()
        glUseProgram(self.prog)
        
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_1D, self.levels_tex)
        glTexSubImage1D(GL_TEXTURE_1D, 0, 0, self.total_segments, GL_RED, GL_FLOAT, self.global_levels)
        glUniform1i(self.locs["levels_tex"], 0)

        mvp = self.calculate_matrix(self.scale, 2.0, 2.0)
        mvp.scale(self.visual_scale, self.visual_scale, 1.0)
        
        glUniformMatrix4fv(self.locs["mvp"], 1, GL_FALSE, mvp.data())
        glUniform1f(self.locs["thickness"], float(self.map_data.get("thickness", 2.2)))

        for g in self.glyphs_gpu:
            glBindVertexArray(g["vao"])
            glMultiDrawArrays(GL_TRIANGLE_STRIP, g["starts"], g["counts"], len(g["starts"]))
    
    def _update_visual_scale(self) -> None:
        if abs(self.target_scale - self.visual_scale) > 0.001:
            self.visual_scale += (self.target_scale - self.visual_scale) * self.scale_smoothing
            self.update()
        
        else:
            self.visual_scale = self.target_scale

    def _process_schedule(self) -> None:
        real_elapsed = self.elapsed.elapsed()
        self.virtual_time += (real_elapsed - self.last_process_time) * self.player.speed
        self.last_process_time = real_elapsed

        now = self.virtual_time
        self.global_levels.fill(0)

        for g in self.glyphs_gpu:
            base = g["global_base_idx"]

            for item in g["schedule"]:
                start, dur = item["start"], item["duration"]

                if not (start <= now <= start + dur):
                    continue
                
                prog = (now - start) / dur
                b_start = item["brightness"]
                bright = b_start + (item.get("end_brightness", b_start) - b_start) * prog

                if "segments" in item:
                    target = base + np.array(item["segments"])
                
                else:
                    target = slice(base, base + g["num_segs"])

                self.global_levels[target] = np.maximum(self.global_levels[target], bright)

        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = 0.07 if event.angleDelta().y() > 0 else -0.07
        self.target_scale = np.clip(self.target_scale + delta, 0.3, 4.0)
        
        self.visual_scale = self.target_scale 
        
        self.resize_timer.start()
        self.update()

    def _sync_size_delayed(self) -> None:
        new_w = int(self.map_w * self.target_scale) + 80
        new_h = int(self.map_h * self.target_scale) + 80
        self.animate_resize(new_w, new_h)

    def _sync_size_delayed(self):
        self.animate_resize(int(self.map_w * self.target_scale) + 80, int(self.map_h * self.target_scale) + 80)

    def exit(self, cleanup: bool = True) -> None:
        self.stop_all()
        self.resize_timer.stop()
        self.scale_out(cleanup)

class TestWindow(FloatingWindowGPU):
    def __init__(self):
        super().__init__("Import")
        self.setAcceptDrops(True)
        
        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        
        self.audio_path = None
        self.save_path = None
        
        self.audio_path_button = Basic.ButtonWithOutlineSlim("Audiofile", False)
        self.save_path_button = Basic.ButtonWithOutlineSlim("Savefile", False)
        
        self.cancel_button = Basic.ButtonWithOutline("Later, gator")
        self.import_button = Basic.NothingButton("Import!")
        
        self.import_button.clicked.connect(self.on_import_callback)
        
        self.content_layout.addWidget(self.audio_path_button)
        self.content_layout.addWidget(self.save_path_button)
        
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.import_button)
        
        self.content_layout.addLayout(button_row)
    
    def dragEnterEvent(self, event):
        for url in event.mimeData().urls():
            file = url.toLocalFile()
            mime, encoding = mimetypes.guess_type(file)
            
            if "audio" in mime:
                self.audio_path_button.setText(file.split("/")[-1])
                self.audio_path = file
            
            if mime in ["text/plain", "application/json"]:
                self.save_path_button.setText(file.split("/")[-1])
                self.save_path = file

        super().dragEnterEvent(event)
    
    def calculate_last_glyph_end(self, glyphs):
        return max(x["start"] + x["duration"] for x in glyphs)
    
    def on_import_callback(self):
        if not self.audio_path:
            self.audio_path_button.start_glitch()
            self.import_button.start_glitch()
            
            return

        if not self.save_path:
            self.audio_path_button.start_glitch()
            self.import_button.start_glitch()
            
            return
        
        audio = AudioSegment.from_file(self.audio_path)
        
        duration_ms = audio.duration_seconds * 1000
        converted_glyphs = Encoder.convert_to_glyphs(self.save_path)
        max_ms_glyphs = self.calculate_last_glyph_end(converted_glyphs)
        
        print(converted_glyphs)
        print(max_ms_glyphs)
        print(duration_ms)
        
        if max_ms_glyphs > duration_ms:
            return ErrorWindow(
                "Woops.",
                "Audio doesn't match with the save file."
            ).exec_()

class Tutorial(FloatingWindowGPU):
    def __init__(self, bpm, path):
        self.player = Player.PlaybackManager()
        self.player.load_audio(path)

        super().__init__(
            "Tutorial",
            bpm = bpm,
            player = self.player,
            enable_audioplayer_effects = False
        )

        self.stage = 0

        self.build_pages()
        self.initialize_ui()
        self.initalize_audio()
        self.set_bpm_peak_size(1.02)

        self.make_page()

    def build_pages(self):
        self.pages = [
            {"label": "Welcome to Cassette", "text": "Get ready."},
            {
                "label": "Basics",
                "text": "`Space` to play / pause.\n`1, 2, 3, 4, 5, 6, 7, 8, 9, 0, Minus` to place a glyph. `Del / Backspace` to delete it. `Ctrl + / -` or `Command + / -` to zoom. `B`, `S`, `D` to quickly change the brightness, speed and duration."
            },
            {
                "label": "Basics - Mouse",
                "text": "`Right Mouse Button` to open context menu. `Grab` the side of glyph to resize it. `Hold` to move it. `Press` on waveform to set playback position."
            },
            {
                "label": "Basics - Scroll",
                "text": "Use `Shift + Wheel` to scroll vertically. Use `Wheel` to scroll horizontally."
            },
            {
                "label": "Basics - Visualizator",
                "text": "You can move the visualizator by dragging it with `Left Mouse Button`. You also can resize by scrolling `Wheel` while hovering over it."
            },
            {"label": "Basics - Navigation", "text": "Click `Eject` to go back to the main menu."},
            {"label": "Effects - Mixing", "text": "You can combine effects! Place glyphs on top of each other with different effects."},
            {"label": "Shall we?", "text": "Now, try yourself in glyphtones creation."}
        ]

        self.max_stage = len(self.pages)

    def initialize_ui(self):
        self.text_label = Basic.DescriptionLabel()
        self.text_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.text_label.setMinimumWidth(400)

        self.next_button = Basic.NothingButton("Next?")
        self.next_button.clicked.connect(self.next_button_callback)

        self.content_layout.addWidget(self.text_label)
        self.content_layout.addWidget(self.next_button)

    def initialize_audio(self):
        self.is_audio_small = self.player.duration_ms < 30000
        
        if not self.is_audio_small:
            self.player.enable_midpass(duration=1.0)
            self.player.enable_bitcrush(6, 8, duration=3.0)
            self.player.tape(start_speed=0, end_speed=0.9, duration=3.0)

        def s1():
            self.player.set_speed(0.95, duration=1.0)
            self.player.disable_bitcrush(2.0)
            self.player.enable_midpass(700, duration=2.0)

        def s2():
            self.player.set_speed(1.0, duration=1.0)
            self.player.disable_midpass(2.0)

        def s3():
            self.set_bpm_peak_size(1.04)

        def s4():
            self.set_bpm_peak_size(1.05)

        def s7():
            self.player.tape(end_speed=0.0, duration=3.0, cleanup_on_finish=True)

        self._stage_effects = {
            1: s1,
            2: s2,
            3: s3,
            4: s4,
            7: s7
        }

    def make_page(self):
        if not (0 <= self.stage < self.max_stage):
            return

        page = self.pages[self.stage]

        self.title_label.setText(page["label"])
        self.text_label.setText(page["text"])

        QTimer.singleShot(0, self.adjustSize)

    def next_button_callback(self):
        self.stage += 1
        self.animation_random_rotate()

        if self.stage >= self.max_stage:
            self.on_ok()
            return

        self.make_page()
        self._apply_stage_effects()

    def _apply_stage_effects(self):
        if self.is_audio_small:
            return
        
        effect = self._stage_effects.get(self.stage)
        
        if effect:
            effect()

class PrepareWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            cached_wav = Audio.ensure_wav(self.file_path)
            self.finished.emit(cached_wav)
        
        except Audio.NoAudioStreams:
            self.error.emit("No audio streams found in the file.")

        except Audio.PermissionError:
            self.error.emit("Permission error while accessing the file. Please check if the file is open in another application.")

        except Audio.CorruptedFileError:
            self.error.emit("The audio file is corrupted or in an unsupported format.")

        except FileNotFoundError:
            self.error.emit("The specified audio file was not found. Maybe it was moved or deleted while the loader was running?")

        except Exception as e:
            self.error.emit(f"Conversion failed: {traceback.format_exc()}")
    
    def __del__(self):
        logger.debug("PrepareWorker has been removed")

class LoadAudioWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            data, fs = Audio.load_audio(self.file_path)
            audio_calc = data.astype('float32')

            if audio_calc.ndim > 1:
                audio_calc = np.mean(audio_calc, axis=1)

            samples_per_pixel = len(audio_calc) / 1000
            step = max(1, int(np.ceil(samples_per_pixel)))

            padded_len = ((len(audio_calc) + step - 1) // step) * step
            padded = np.pad(audio_calc, (0, padded_len - len(audio_calc)), mode="constant")
            reshaped = padded.reshape(-1, step)

            waveform_data = np.mean(np.abs(reshaped), axis=1)
            waveform_data = Utils.gaussian_filter1d_np(waveform_data, sigma=2)

            self.finished.emit((data, fs, waveform_data))
        
        except Audio.CorruptedFileError:
            self.error.emit("The audio file is corrupted or in an unsupported format.")

        except Exception:
            self.error.emit(traceback.format_exc())
    
    def __del__(self):
        logger.debug("LoadWorker has been removed")

class BPMWorker(QObject):
    finished = pyqtSignal(float, object)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            bpm, peaks = Audio.analyze_bpm_and_beats(self.file_path)
            self.finished.emit(bpm, peaks)
        
        except Exception:
            self.error.emit(traceback.format_exc())
    
    def __del__(self):
        logger.debug("BPMWorker has been removed")

class AudioSetupDialog(FloatingWindowGPU):
    def __init__(self, file_path):
        self.player = Player.player
        
        super().__init__(
            "Audio",
            player = self.player,
            max_tilt_angle = 14,
            enable_audioplayer_effects = False
        )
        
        self.file_path = file_path
        self.filename = self.file_path.split("/")[-1]
        
        self.title_label.setText(self.filename)
        
        self.settings = {}
        self.snapped_times = None
        self.cached_wav = None

        self.setStyleSheet(Styles.Controls.AudioSetupper)
        
        self.setup_audio_layout()
        self.setup_animations()
        self.run_tasks(file_path)

        self.adjustSize()
    
    def run_tasks(self, audiofile):
        self.cached_wav = None

        self.prepare_thread = QThread(self)
        self.prepare_worker = PrepareWorker(audiofile)
        self.prepare_worker.moveToThread(self.prepare_thread)
        self.prepare_thread.started.connect(self.prepare_worker.run)

        self.prepare_worker.finished.connect(self._on_prepare_success)
        self.prepare_worker.error.connect(lambda msg: ErrorWindow("Conversion Error", msg).exec_())

        self.prepare_worker.finished.connect(self.prepare_thread.quit)
        self.prepare_worker.finished.connect(self.prepare_worker.deleteLater)
        self.prepare_thread.finished.connect(self.prepare_thread.deleteLater)

        self.prepare_thread.start()

        self.load_thread = None
        self.load_worker = None
        self.bpm_thread = None
        self.bpm_worker = None

    def _on_prepare_success(self, cached_wav_path):
        self.cached_wav = cached_wav_path

        self.load_thread = QThread(self)
        self.load_worker = LoadAudioWorker(self.cached_wav)
        self.load_worker.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.load_worker.run)

        self.load_worker.finished.connect(self._on_load_finished)
        self.load_worker.error.connect(lambda msg: ErrorWindow("Load Error", msg).exec_())

        self.load_worker.finished.connect(self.load_thread.quit)
        self.load_worker.finished.connect(self.load_worker.deleteLater)
        self.load_thread.finished.connect(self.load_thread.deleteLater)

        self.load_thread.start(QThread.LowPriority)

        self.bpm_thread = QThread(self)
        self.bpm_worker = BPMWorker(self.cached_wav)
        self.bpm_worker.moveToThread(self.bpm_thread)
        self.bpm_thread.started.connect(self.bpm_worker.run)

        self.bpm_worker.finished.connect(self._on_bpm_finished)
        self.bpm_worker.error.connect(lambda msg: ErrorWindow("BPM error", msg).exec_())

        self.bpm_worker.finished.connect(self.bpm_thread.quit)
        self.bpm_worker.finished.connect(self.bpm_worker.deleteLater)
        self.bpm_thread.finished.connect(self.bpm_thread.deleteLater)

        self.bpm_thread.start(QThread.LowPriority)

    def _on_load_finished(self, result):
        try:
            data, fs, waveform_data = result
            self.player.load_audio_from_data(data, fs)
            self.on_audio_loaded(data, fs, waveform_data)
        
        except Exception:
            ErrorWindow("Load Error", traceback.format_exc()).exec_()

    def _on_bpm_finished(self, bpm, peaks):
        try:
            self.on_bpm_ready(bpm, peaks)

        except Exception:
            ErrorWindow("BPM Error", traceback.format_exc()).exec_()
    
    def setup_animations(self):
        self._bpm_anim_target = None
        self._bpm_anim_current = 120
        self._bpm_text = ""
        self._bpm_number_str = ""
        
        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self.update_playback)
        
        self.bpm_remove_timer = QTimer(self)
        self.bpm_remove_timer.timeout.connect(self._bpm_remove_step)
        
        self.bpm_anim_timer = QTimer(self)
        self.bpm_anim_timer.timeout.connect(self.animate_bpm_spinbox)
        self.bpm_anim_timer.start(FPS_30)

        self.player.beat_normal.connect(self.update_title)
    
    def setup_audio_layout(self):
        playback_layout = QHBoxLayout()
        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(10)

        self.trim_widget = Widgets.TrimmingWaveformWidget()

        self.start_time_label = Inputs.Textbox(0, 0, 5, ":time")
        self.end_time_label = Inputs.Textbox(0, 0, 5, ":time")
        
        self.fade_in_textbox = Inputs.Textbox(0, 5000, None, "number", None, "Fade in (Ms)")
        self.fade_out_textbox = Inputs.Textbox(0, 5000, None, "number", None, "Fade out (Ms)")
        
        self.bpm_input = Inputs.Textbox(1, 400, None, "number", None, "Counting BPM... 120")        
        
        self.bpm_input.setMaximumWidth(220)
        self.bpm_input.setFixedHeight(Styles.Metrics.element_height)
        self.bpm_input.setStyleSheet(Styles.Controls.FloatingTextBoxRound)

        for textbox in [self.start_time_label, self.end_time_label]:
            textbox.setFixedWidth(70)

        for textbox in [self.fade_in_textbox, self.fade_out_textbox, self.start_time_label, self.end_time_label]:
            textbox.setStyleSheet(Styles.Controls.FloatingTextBox)
            textbox.setFixedHeight(40)
        
        self.play_button = QPushButton()
        self.play_button.setObjectName("play_button")
        
        self.play_icon = QIcon(QIcon("System/Assets/Icons/Audio/Play.png"))
        self.pause_icon = QIcon(QIcon("System/Assets/Icons/Audio/Pause.png"))
        
        self.play_button.setIcon(self.play_icon)
        self.play_button.setIconSize(QSize(45, 45))

        playback_layout.addWidget(self.start_time_label)
        playback_layout.addWidget(self.fade_in_textbox)
        playback_layout.addWidget(self.play_button)
        playback_layout.addWidget(self.fade_out_textbox)
        playback_layout.addWidget(self.end_time_label)
        
        # Settings Layout
        self.model_selector = Inputs.Selector(["1", "2", "2a", "3a"])

        self.cancel_button = Basic.ButtonWithOutline("Cancel")
        self.ok_button = Basic.NothingButton("Ok")
        
        self.ok_button.setMaximumWidth(70)
        self.play_button.setFixedSize(45, 45)
        self.cancel_button.setMaximumWidth(100)
        self.model_selector.setMinimumWidth(300)
        
        self.play_button.setEnabled(False)
        self.ok_button.setEnabled(False)

        settings_layout.addWidget(self.bpm_input)
        settings_layout.addWidget(self.model_selector)
        settings_layout.addStretch()
        settings_layout.addWidget(self.cancel_button)
        settings_layout.addWidget(self.ok_button)

        # Connecting
        self.start_time_label.safeTextChanged.connect(self.edit_start_time)
        self.end_time_label.safeTextChanged.connect(self.edit_end_time)
        self.play_button.clicked.connect(self.toggle_playback)
        self.ok_button.clicked.connect(self.accept_callback)
        self.cancel_button.clicked.connect(self.reject_callback)
        self.trim_widget.regionChanged.connect(self.update_texboxes)
        self.bpm_input.safeTextChanged.connect(self.on_bpm_changed)

        # Content Layout Adding
        self.content_layout.addWidget(self.trim_widget)
        self.content_layout.addLayout(playback_layout)
        self.content_layout.addLayout(settings_layout)
    
    def on_audio_loaded(self, audio_data, sampling_rate, waveform_data):
        logger.info("Audio loaded.")
        
        self.trim_widget.set_data(audio_data, sampling_rate, waveform_data)
        
        self.end_time_label.max_number = self.trim_widget.duration
        self.end_time_label.setText(max(1, math.ceil(self.trim_widget.duration)))

        self.update_texboxes(self.trim_widget.start_time, self.trim_widget.end_time)

        self.play_button.setEnabled(True)
        self.ok_button.setEnabled(True)
    
    def on_bpm_ready(self, bpm, snapped_times):
        logger.info(f"BPM found: {bpm}")
        self.snapped_times = snapped_times
        
        self.bpm_anim_timer.stop()
        
        if bpm:
            bpm_val = round(bpm)
            self._bpm_text = "Counting BPM "
            self._bpm_number_str = str(bpm_val)
            
            self.bpm_input.setPlaceholderText(f"{self._bpm_text}{self._bpm_number_str}")

            remove_interval = round(60000 / bpm / 8)
            self.bpm_remove_timer.start(remove_interval)
            
            return

        self._bpm_text = "Counting BPM FAILURE"
        self._bpm_number_str = ""

        self.bpm_input.setPlaceholderText(self._bpm_text)
        self.bpm_remove_timer.start(100)

        if random.randint(1, 500) == 500:
            Utils.ui_sound("Gambling")

    def get_perfect_width(self):
        text = str(self.bpm_input.text() or self.bpm_input.placeholderText() or "BPM")
        
        metrics = self.bpm_input.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        padding = 33
        
        return round(text_width + padding)
    
    def shrink_bpm_input(self):
        logger.info("Shrinking BPM section...")
        
        self.bpm_shrink_animation = QPropertyAnimation(self.bpm_input, b"maximumWidth")
        self.bpm_shrink_animation.setDuration(300)
        self.bpm_shrink_animation.setStartValue(self.bpm_input.width())
        self.bpm_shrink_animation.setEndValue(self.get_perfect_width())
        self.bpm_shrink_animation.setEasingCurve(QEasingCurve.OutCubic)

        self.bpm_shrink_animation.finished.connect(self.on_bpm_animation_end)
        
        self.bpm_shrink_animation.start()

    def update_texboxes(self, start, end):
        self.start_time_label.blockSignals(True)
        self.end_time_label.blockSignals(True)
        
        self.start_time_label.setText(int(round(start)))
        self.end_time_label.setText(max(1, int(round(end))))
        
        self.start_time_label.blockSignals(False)
        self.end_time_label.blockSignals(False)

        self.start_time_label.max_number = int(round(end - 1))
        self.end_time_label.min_number = int(round(start))

    def edit_start_time(self):
        start_s = self.start_time_label.text()
        
        if not start_s:
            return
        
        self.trim_widget.set_playback_position(start_s)

        self.trim_widget.start_time = start_s
        self.trim_widget.update()

        self.end_time_label.min_number = self.start_time_label.text()

    def edit_end_time(self):
        end_s = self.end_time_label.text()
        start_s = self.start_time_label.text()
        
        if end_s is None or start_s is None:
            return

        if start_s >= end_s:
            return

        self.trim_widget.set_playback_position(start_s)

        self.trim_widget.end_time = end_s
        self.trim_widget.update()

        self.start_time_label.max_number = end_s - 1

    def update_title(self):
        position_ms = f"{round(self.player.get_position_ms() / 1000, 4):.3f}"
        self.title_label.setText(position_ms)

        self.animation_title_scale()

    def animate_bpm_spinbox(self):
        if not self._bpm_anim_target:
            self._bpm_anim_target = np.random.randint(60, 180)

        if self._bpm_anim_current == self._bpm_anim_target:
            self._bpm_anim_target = np.random.randint(60, 180)

        if self._bpm_anim_current < self._bpm_anim_target:
            self._bpm_anim_current += 1
        
        elif self._bpm_anim_current > self._bpm_anim_target:
            self._bpm_anim_current -= 1

        self.bpm_input.setPlaceholderText(f"Counting BPM {self._bpm_anim_current}")

    def _bpm_remove_step(self):
        if self._bpm_text:
            self._bpm_text = self._bpm_text[1:]
            self.bpm_input.setPlaceholderText(f"{self._bpm_text}{self._bpm_number_str}")
            return
        
        self.bpm_remove_timer.stop()
        
        if self._bpm_number_str:
            self.bpm_input.setText(self._bpm_number_str)
        
        self.bpm_input.setPlaceholderText("BPM")
        self.shrink_bpm_input()
    
    def on_bpm_changed(self, value):
        if not value:
            return

        value = int(value)
        self.update_bpm(value)

    def on_bpm_animation_end(self):
        self.bpm_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def toggle_playback(self):
        if self.player.is_playing:
            self.title_label.setText(self.filename)
            
            self.stop_playback()
            self.trim_widget.set_playback_position(self.trim_widget.start_time)

        else:
            self.play_selection()

    def play_selection(self):
        current_playback_sec = self.trim_widget._playback_position
        
        if not (self.trim_widget.start_time <= current_playback_sec < self.trim_widget.end_time):
            current_playback_sec = self.trim_widget.start_time
            self.trim_widget.set_playback_position(current_playback_sec)
        
        self.player.play(current_playback_sec * 1000)

        self.play_button.setIcon(self.pause_icon)
        self.trim_widget.set_is_playing(True)
        self.playback_timer.start(FPS_120)

    def stop_playback(self):
        self.player.stop()

        self.play_button.setIcon(self.play_icon)
        self.trim_widget.set_is_playing(False)
        self.playback_timer.stop()

    def update_playback(self):
        if self.player.is_playing:
            current_pos_ms = self.player.get_position_ms()
            
            if current_pos_ms > self.trim_widget.end_time * 1000:
                self.trim_widget.set_playback_position(self.trim_widget.start_time)
                self.toggle_playback()
                
                return

            self.trim_widget.set_playback_position(current_pos_ms / 1000)

        else:
            self.trim_widget.set_playback_position(0)
            self.stop_playback()

    def accept_callback(self):
        is_not_valid = self.end_time_label.is_not_valid()
        
        if is_not_valid or not self.end_time_label.text():
            self.end_time_label.start_glitch(False)
            self.ok_button.start_glitch()
            
            return
        
        if self.start_time_label.text() is None:
            self.start_time_label.start_glitch(False)
            self.ok_button.start_glitch()
            
            return
        
        self.saved_settings = self.get_settings()

        self.cleanup()
        super().on_ok()
    
    def reject_callback(self):
        self.cleanup(True)
        super().on_cancel()

    def get_settings(self):
        return {
            "audio": {
                "start_ms": self.trim_widget.start_time * 1000,
                "end_ms": self.trim_widget.end_time * 1000,
                
                "audio_data": self.player.data,
                
                "fade_in": self.fade_in_textbox.text(),
                "fade_out": self.fade_out_textbox.text(),
                "duration": self.trim_widget.end_time - self.trim_widget.start_time,
                
                "bpm": self.bpm_input.text() or 120,
                "beats": self.snapped_times
            },
            
            "model": number_model_to_code(self.model_selector.currentText()),
        }
    
    def cleanup(self, cancelled=False):
        self.playback_timer.stop()
        self.bpm_anim_timer.stop()
        self.bpm_remove_timer.stop()
        self.trim_widget.audio_data = None

        if self.player.is_playing:
            self.player.tape(duration = 1.0 if not cancelled else 3.0, end_speed = 0.0)

        threads_to_wait = []
        
        for thread in [self.prepare_thread, self.load_thread, self.bpm_thread]:
            try:
                if not thread:
                    continue

                if not thread.isRunning():
                    continue

                threads_to_wait.append(thread)
                thread.quit()
            
            except:
                pass

        if not threads_to_wait:
            self._safe_delete_cache()
        
        else:
            self._wait_and_cleanup(threads_to_wait)

        self.prepare_worker = self.load_worker = self.bpm_worker = None
        self.prepare_thread = self.load_thread = self.bpm_thread = None

    def _wait_and_cleanup(self, threads):
        for t in threads:
            t.wait(500)
        
        self._safe_delete_cache()

    def _safe_delete_cache(self):
        if not self.cached_wav or self.cached_wav == self.file_path:
            return

        try:
            if os.path.exists(self.cached_wav):
                os.unlink(self.cached_wav)
                logger.info(f"Cache deleted: {self.cached_wav}")
        
        except Exception as e:
            logger.warning(f"Could not delete cache yet, retrying... {e}")
            QTimer.singleShot(1000, self._safe_delete_cache)


# UNOPTIMIZED CODE - PLANNED:


class Playground(FloatingWindowGPU):
    def __init__(self):
        super().__init__("GPU Engine Master Tuner")
        
        self.content_widget.setMinimumWidth(1400)

        self.main_row = QHBoxLayout()
        self.main_row.setSpacing(20)
        self.content_layout.addLayout(self.main_row)

        self._setup_audio_col()
        self._setup_filter_col()
        self._setup_style_col()
        self._setup_engine_props()

        self._bind_logic()

        self.adjustSize()

    def _setup_audio_col(self):
        col = QVBoxLayout()
        col.addWidget(Basic.DescriptionLabel("Audio"))
        
        self.volume_slider = Inputs.SliderWithLabel("Volume", 0, 100, 100)
        self.player_speed_slider = Inputs.SliderWithLabel("Speed (%)", 10, 300, 100)
        self.bc_mix_slider = Inputs.SliderWithLabel("BC Mix", 0, 100, 0)
        self.bc_bits_slider = Inputs.SliderWithLabel("BC Bits", 1, 24, 16)
        self.bc_down_slider = Inputs.SliderWithLabel("Downsample", 1, 32, 1)

        for w in [self.volume_slider, self.player_speed_slider, self.bc_mix_slider, self.bc_bits_slider, self.bc_down_slider]:
            col.addWidget(w)
        
        col.addStretch()
        self.main_row.addLayout(col)

    def _setup_filter_col(self):
        col = QVBoxLayout()
        col.addWidget(Basic.DescriptionLabel("Stereo"))
        
        self.mid_mix_slider = Inputs.SliderWithLabel("Filt Mix", 0, 100, 0)
        self.mid_freq_slider = Inputs.SliderWithLabel("Freq (Hz)", 100, 10000, 1000)
        self.mid_q_slider = Inputs.SliderWithLabel("Resonance", 1, 100, 10)
        self.delay_l_slider = Inputs.SliderWithLabel("Delay L (ms)", 0, 50, 0)
        self.delay_r_slider = Inputs.SliderWithLabel("Delay R (ms)", 0, 50, 0)
        self.beat_threshold_slider = Inputs.SliderWithLabel("Beat Sens.", 0, 100, 38)

        for w in [self.mid_mix_slider, self.mid_freq_slider, self.mid_q_slider, self.delay_l_slider, self.delay_r_slider, self.beat_threshold_slider]:
            col.addWidget(w)
        
        col.addStretch()
        self.main_row.addLayout(col)

    def _setup_style_col(self):
        col = QVBoxLayout()
        col.addWidget(Basic.DescriptionLabel("Animations"))
        
        anim_styles = ["bouncy", "smooth", "roll", "glitch", "classic"]
        default_idx = anim_styles.index(self.animation_style) if self.animation_style in anim_styles else 0
        self.style_selector = Inputs.Selector(anim_styles, default_idx)
        self.style_selector.setMinimumWidth(400)
        col.addWidget(self.style_selector)

        col.addWidget(Basic.DescriptionLabel("Animation Triggers"))
        self.btn_punch = Basic.ButtonWithOutlineSlim("Title Punch")
        self.btn_wobble = Basic.ButtonWithOutlineSlim("Window Wobble")
        self.btn_disturbe = Basic.ButtonWithOutlineSlim("Disturbe FX")
        self.btn_test_open = Basic.ButtonWithOutlineSlim("Test Open")
        
        for btn in [self.btn_punch, self.btn_wobble, self.btn_disturbe, self.btn_test_open]:
            col.addWidget(btn)
        
        col.addStretch()
        self.main_row.addLayout(col)

    def _setup_engine_props(self):
        col = QVBoxLayout()
        col.addWidget(Basic.DescriptionLabel("Engine"))
        
        self.props_config = {
            "rotation_x": (-90, 90, 0, 1),
            "rotation_y": (-90, 90, 0, 1),
            "rotation_z": (-180, 180, 0, 1),
            "scale": (0, 200, 100, 100),
            "opacity_background": (0, 100, 100, 100),
            "opacity_content": (0, 100, 100, 100),
            "x_offset": (-200, 200, 0, 100),
            "y_offset": (-200, 200, 0, 100),
            "z_offset": (-200, 200, 0, 100),
            "title_scale": (0, 200, 100, 100),
            "title_rotation": (-180, 180, 0, 1)
        }

        self.prop_sliders = {}
        for prop, (min_v, max_v, def_v, div) in self.props_config.items():
            slider = Inputs.SliderWithLabel(prop, min_v, max_v, def_v)
            slider.setMinimumWidth(350)
            self.prop_sliders[prop] = (slider, div)
            col.addWidget(slider)
            slider.slider.valueChanged.connect(
                lambda v, p=prop, d=div: self._update_engine_prop(p, v, d)
            )

        col.addStretch()
        self.main_row.addLayout(col)

    def _update_engine_prop(self, prop_name, value, divider):
        final_val = value / divider
        self.animation_engine.set_property_base_value(prop_name, final_val)
        self.update()

    def _bind_logic(self):
        self.volume_slider.slider.valueChanged.connect(lambda v: Player.player.set_volume(v/100))
        self.player_speed_slider.slider.valueChanged.connect(lambda v: Player.player.set_speed(v/100, duration=0.1))
        
        for s in [self.bc_mix_slider, self.bc_bits_slider, self.bc_down_slider]:
            s.slider.valueChanged.connect(self.update_bitcrush)
        
        for s in [self.mid_mix_slider, self.mid_freq_slider, self.mid_q_slider]:
            s.slider.valueChanged.connect(self.update_filter)

        self.delay_l_slider.slider.valueChanged.connect(self.update_delays)
        self.delay_r_slider.slider.valueChanged.connect(self.update_delays)
        self.beat_threshold_slider.slider.valueChanged.connect(
            lambda v: Player.player.onset_detector.set_threshold(v/100) if hasattr(Player.player, 'onset_detector') else None
        )

        self.style_selector.selectionChanged.connect(self._on_style_changed)
        self.btn_punch.clicked.connect(lambda: self.animation_title_punch(strength=1.5))
        self.btn_wobble.clicked.connect(self.wobble)
        self.btn_disturbe.clicked.connect(self.start_disturbe_animation)
        self.btn_test_open.clicked.connect(self.start_open_animation)

    def _on_style_changed(self, index, name):
        self.animation_style = name

    def update_bitcrush(self):
        mix = self.bc_mix_slider.slider.value() / 100
        if mix > 0:
            Player.player.enable_bitcrush(
                bits=self.bc_bits_slider.slider.value(),
                downsample=self.bc_down_slider.slider.value(),
                mix=mix
            )
        else:
            Player.player.disable_bitcrush(duration=0.1)

    def update_filter(self):
        mix = self.mid_mix_slider.slider.value() / 100
        if mix > 0:
            Player.player.enable_midpass(
                center_hz=self.mid_freq_slider.slider.value(),
                q=self.mid_q_slider.slider.value() / 10,
                mix=mix
            )
        else:
            Player.player.disable_midpass(duration=0.1)

    def update_delays(self):
        Player.player.smooth_channel_delay(
            left_to_ms=self.delay_l_slider.slider.value(),
            right_to_ms=self.delay_r_slider.slider.value(),
            duration=0.2
        )

class WalterWindow(FloatingWindowGPU):
    def __init__(self):
        super().__init__("walter.")

        self.path_open = "System/Assets/Image/Walter"
        self.path_closed = "System/Assets/Image/WalterClosed"
        
        self.is_walter_closed = True

        self.walter = QPixmap(self.path_open)
        self.walter_closed = QPixmap(self.path_closed)
        
        self.label = Basic.DescriptionLabel("Turn on the Waltuh, yes, click it.")
        self.image = Basic.Image(self.walter_closed)

        self.content_layout.addWidget(self.image)
        self.content_layout.addWidget(self.label)

        self.chaos_timer = QTimer(self)
        self.chaos_timer.setInterval(20)
        self.chaos_timer.timeout.connect(self.chaos_mode)

        self.stop_timer = QTimer(self)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.setInterval(8500)
        self.stop_timer.timeout.connect(self.chaos_timer.stop)

        self.image.clicked.connect(self.switch_walter)
    
    def switch_walter(self):
        self.is_walter_closed = not self.is_walter_closed
        
        current_pixmap = self.walter_closed if self.is_walter_closed else self.walter
        self.image.update_image(current_pixmap)

        if not self.is_walter_closed:
            Utils.ui_sound("NOK/HEVCharger", tone = 1.0)
            self.label.setText("Such a good boy.")

            self.chaos_timer.start()
            self.stop_timer.start()

            if random.random() > 0.4:
                self.spam_errors()
        
        else:
            self.label.setText("Don't do that.")
            self.chaos_timer.stop()
            self.stop_timer.stop()
    
    def spam_errors(self):
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