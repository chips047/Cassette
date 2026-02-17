import sys
import math

from enum import Enum

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from loguru import logger

class Easing:
    @staticmethod
    def linear(t):
        return t

    @staticmethod
    def smooth(t):
        return t * t * (3 - 2 * t)

    @staticmethod
    def bouncy(t):
        if t == 0: return 0.0
        if t == 1: return 1.0
        
        s = 0.27 / (2 * math.pi) * math.asin(1.0 / max(1.7, 1.0))
        
        return (1.7 * math.pow(2, -10 * t) * math.sin((t - s) * (2 * math.pi) / 0.27) + 1.0)
    
    @staticmethod
    def very_bouncy(t):
        if t == 0: return 0
        if t == 1: return 1

        p = 0.35
        s = p / 4

        return math.pow(2, -7 * t) * math.sin((t - s) * (2 * math.pi) / p) + 1
    
    @staticmethod
    def ease_out_cubic(t):
        t = max(0.0, min(1.0, t))
        return 1 - pow(1 - t, 3)

    @staticmethod
    def ease_in_expo(t):
        if t == 0: return 0.0
        return math.pow(2, 10 * (t - 1))

    @staticmethod
    def ease_out_expo(t):
        if t == 1: return 1.0
        return 1 - math.pow(2, -10 * t)

    @staticmethod
    def ease_in_out_expo(t):
        if t == 0: return 0.0
        if t == 1: return 1.0
        if t < 0.5:
            return math.pow(2, 20 * t - 10) / 2
        return (2 - math.pow(2, -20 * t + 10)) / 2

    @staticmethod
    def ease_in_circ(t):
        t = max(0.0, min(1.0, t))
        return 1 - math.sqrt(1 - math.pow(t, 2))
    
    @staticmethod
    def ease_out_quart(t):
        t = max(0.0, min(1.0, t))
        return 1 - (1 - t) ** 4
    
    @staticmethod
    def ease_in_quart(t):
        t = max(0.0, min(1.0, t))
        return t ** 4
    
    @staticmethod
    def ease_out_bounce(t):
        n1 = 7.5625
        d1 = 2.75
    
        if t < 1 / d1:
            return n1 * t * t
        
        elif t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        
        elif t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        
        else:
            t -= 2.625 / d1
            return n1 * t * t + 0.984375

class MixMode(Enum):
    ADD = 0
    MULTIPLY = 1
    NOMIX = 2

class AnimationInstance(QObject):
    updated = pyqtSignal()
    
    def __init__(self, parent, keyframes, duration_ms: int, easing_func, finished = None):
        super().__init__(parent)
        
        self.keyframes = sorted(keyframes, key=lambda k: k[0])
        
        self.duration = duration_ms
        self.easing = easing_func
        self.elapsed = 0
        
        self.finished_callback = finished
        
        self.is_finished = False

    def update(self, dt_ms):
        self.elapsed += dt_ms
        self.updated.emit()

        if self.elapsed >= self.duration:
            self.elapsed = self.duration
            self.is_finished = True
            
            if self.finished_callback:
                callback = self.finished_callback
                self.finished_callback = None
                QTimer.singleShot(0, callback)

    def get_value(self):
        if not self.keyframes:
            return 0

        t = self.elapsed / self.duration if self.duration > 0 else 1.0

        eased_t = self.easing(t)

        if eased_t <= self.keyframes[0][0]:
            k1, k2 = self.keyframes[0], self.keyframes[1]
        
        elif eased_t >= self.keyframes[-1][0]:
            k1, k2 = self.keyframes[-2], self.keyframes[-1]
        
        else:
            k1, k2 = self.keyframes[0], self.keyframes[1]
            
            for i in range(len(self.keyframes) - 1):
                if self.keyframes[i][0] <= eased_t <= self.keyframes[i + 1][0]:
                    k1 = self.keyframes[i]
                    k2 = self.keyframes[i + 1]
                    
                    break

        segment_duration = k2[0] - k1[0]
        
        if segment_duration == 0:
            return k2[1]

        local_t = (eased_t - k1[0]) / segment_duration

        return k1[1] + (k2[1] - k1[1]) * local_t

class PropertyNode(QObject):
    updated = pyqtSignal()
    
    def __init__(self, parent, base_value: float, mode: MixMode, damper: bool = False, lerp_factor: float = 0.1):
        super().__init__(parent)
        
        self.mode = mode
        self.animations = []
        self.damper_enabled = damper
        self.lerp_factor = lerp_factor
        self.base_value = base_value
        self._cached_value = base_value
        self._target_value = base_value

        self._is_targeting = False
        self._t_start_val = base_value
        self._t_end_val = base_value
        self._t_duration = 0
        self._t_elapsed = 0
        self._t_easing = Easing.linear

    def set_target(self, value: float, duration: int, easing_func):
        self._t_start_val = self._cached_value 
        self._t_end_val = value
        self._t_duration = duration
        self._t_elapsed = 0
        self._t_easing = easing_func
        self._is_targeting = True
        
        if self.mode == MixMode.NOMIX:
            self.animations.clear()

    def update(self, dt_ms):
        still_running = []
        
        for anim in self.animations:
            anim.update(dt_ms)
            
            if anim.is_finished:
                final_val = anim.get_value()
                
                if self.mode == MixMode.MULTIPLY: self.base_value *= final_val
                elif self.mode == MixMode.ADD: self.base_value += final_val
                elif self.mode == MixMode.NOMIX: self.base_value = final_val

                continue
            
            still_running.append(anim)
        
        self.animations = still_running

        target = self.base_value
        
        if self._is_targeting:
            self._t_elapsed += dt_ms
            progress = min(1.0, self._t_elapsed / self._t_duration) if self._t_duration > 0 else 1.0
            
            eased_progress = self._t_easing(progress)
            target = self._t_start_val + (self._t_end_val - self._t_start_val) * eased_progress
            
            if progress >= 1.0:
                self._is_targeting = False
                self.base_value = self._t_end_val
        
        if self.mode != MixMode.NOMIX:
            for anim in self.animations:
                val = anim.get_value()
                if self.mode == MixMode.MULTIPLY: target *= val
                elif self.mode == MixMode.ADD: target += val
        
        else:
            if self.animations:
                target = self.animations[-1].get_value()

        self._target_value = target

        if self.damper_enabled:
            actual_lerp = min(1.0, self.lerp_factor * (dt_ms / 16.0)) 
            self._cached_value += (self._target_value - self._cached_value) * actual_lerp
        
        else:
            self._cached_value = self._target_value

        if abs(self._cached_value - self._target_value) > 0.0001 or self.animations or self._is_targeting:
            self.updated.emit()

    def add_animation(self, anim: AnimationInstance):
        if self.mode == MixMode.NOMIX:
            self.animations.clear()
        
        self.animations.append(anim)

    def value(self):
        return self._cached_value
    
    def clear_animations(self):
        self.animations.clear()
        self._cached_value = self.base_value
        
        self.updated.emit()

class AnimationEngine(QObject):
    updated = pyqtSignal()

    def __init__(self, fps = 120):
        super().__init__()
        self.properties: dict[str, PropertyNode] = {}
        
        self.timer = QTimer(self)
        self.timer.setInterval(1000 // fps)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()
        self.last_time = 0
        
        self.duration_multiplier = 1.0

    def set_multiplier(self, value = 1.0):
        self.duration_multiplier = value

    def set_fps(self, fps):
        self.timer.setInterval(1000 // fps)
        self.timer.stop()
        self.timer.start()

    def set_property_base_value(self, name, value):
        self.properties[name].base_value = value
    
    def set_target_value(self, name: str, value: float, duration: int = 500, easing = Easing.smooth):
        if name not in self.properties:
            return logger.error(f"Property {name} not found.")
        
        final_duration = duration * self.duration_multiplier
        self.properties[name].set_target(value, final_duration, easing)

    def add_property(self, name: str, base_value: float, mode: MixMode, on_update = None, damper_enabled = False, lerp_factor: float = 0.1):
        node = PropertyNode(self, base_value, mode, damper_enabled, lerp_factor)
        
        if on_update:
            node.updated.connect(on_update)
        
        self.properties[name] = node
    
    def get_property_value(self, name):
        if not self.properties.get(name):
            return logger.error(f"Property {name} not found in ThreeaD Engine.")
        
        return self.properties[name].value()

    def animate(self, name: str, keyframes: list, duration: int, easing: Easing = Easing.linear, finished = None, do_not_multiply_duration = False):
        if name not in self.properties:
            return logger.error(f"Property {name} not found in ThreeaD Engine.")

        anim = AnimationInstance(self, keyframes, duration if do_not_multiply_duration else duration * self.duration_multiplier, easing, finished)
        self.properties[name].add_animation(anim)

    def _tick(self):
        current_time = self.elapsed_timer.elapsed()
        dt = current_time - self.last_time
        self.last_time = current_time

        if dt > 100: 
            dt = 16 
        
        for prop in list(self.properties.values()):
            prop.update(dt)
        
        self.updated.emit()
    
    def pause(self):
        self.timer.stop()
    
    def resume(self):
        self.timer.start()

    def clear(self):
        self.timer.timeout.disconnect()
        self.timer.stop()
        
        for prop in self.properties.values():
            prop.deleteLater()
        
        self.properties.clear()