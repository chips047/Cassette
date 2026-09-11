from loguru import logger

from collections.abc import Callable

from PyQt6.QtCore    import QPoint
from PyQt6.QtWidgets import QWidget

from System.Services  import Player
from System.Interface import Widgets

from System.Interface.Windows import FloatingWindowGPU

# Playground

class Playground(FloatingWindowGPU):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Playground", parent = parent)

        self.content_widget.setMinimumWidth(720)
        self.content_widget.setMinimumHeight(480)

        self.scroll_area = Widgets.ElasticScrollArea(self)
        self.content_layout.addWidget(self.scroll_area)

        self.setup_controls()
        self.bind_logic()
        self.adjustSize()

    # Layout

    def add_section(
            self,
            title:   str,
            widgets: list[QWidget]
        ) -> None:
        self.scroll_area.add_widget(Widgets.DescriptionLabel(title))

        for widget in widgets:
            self.scroll_area.add_widget(widget)

    def connect_change(
            self,
            control:  QWidget,
            callback: Callable[[], None]
        ) -> None:
        if isinstance(control, Widgets.CheckboxWithLabel):
            control.stateChanged.connect(lambda *unused_arguments: callback())
            return

        if isinstance(control, Widgets.SliderWithLabel):
            control.valueChanged.connect(lambda *unused_arguments: callback())
            return

        if isinstance(control, Widgets.SelectorWithLabel):
            control.selectionChanged.connect(lambda *unused_arguments: callback())
            return

        if isinstance(control, Widgets.Selector):
            control.selectionChanged.connect(lambda *unused_arguments: callback())
            return

    # Setup

    def setup_controls(self) -> None:
        animation_styles = ["bouncy", "smooth", "roll", "glitch", "classic"]
        default_index    = animation_styles.index(self.animation_style) if self.animation_style in animation_styles else 0

        self.margin_slider                        = Widgets.SliderWithLabel("Margin", 0, 600, self.margin_x)
        self.max_tilt_slider                      = Widgets.SliderWithLabel("Max Tilt Angle", 0, 45, self.max_tilt_angle)
        self.shake_frequency_slider               = Widgets.SliderWithLabel("Shake Frequency (ms)", 10, 200, self.shake_frequency_ms)
        self.shake_deviation_slider               = Widgets.SliderWithLabel("Shake Deviation", 0, 100, int(self.shake_deviation * 10))
        self.tilt_smoothing_slider                = Widgets.SliderWithLabel("Tilt Smoothing", 0, 100, int(self.tilt_smoothing * 100))
        self.bpm_peak_slider                      = Widgets.SliderWithLabel("BPM Peak", 100, 200, int(self.bpm_peak_scale * 100))

        self.start_position_enabled_checkbox      = Widgets.CheckboxWithLabel("Start Position", "Use custom spawn position", self.start_position is not None)
        self.start_position_x_slider              = Widgets.SliderWithLabel("Start X", 0, 4000, self.start_position.x() if self.start_position else 0)
        self.start_position_y_slider              = Widgets.SliderWithLabel("Start Y", 0, 4000, self.start_position.y() if self.start_position else 0)

        self.dialog_checkbox                      = Widgets.CheckboxWithLabel("Dialog", "Use dialog window flags", True)
        self.stays_on_top_checkbox                = Widgets.CheckboxWithLabel("Stays On Top", "Stay above other windows", True)
        self.enable_tilt_checkbox                 = Widgets.CheckboxWithLabel("Enable Tilt", "Mouse hover tilt", self.enable_tilt)
        self.enable_open_animation_checkbox       = Widgets.CheckboxWithLabel("Open Animation", "Animate on open", self.enable_open_animation)
        self.enable_close_animation_checkbox      = Widgets.CheckboxWithLabel("Close Animation", "Animate on close", self.enable_close_animation)
        self.enable_audio_effects_checkbox        = Widgets.CheckboxWithLabel("Transition Audio", "Use audio pulses on transitions", self.enable_transition_audio_effects)
        self.enable_advanced_beat_checkbox        = Widgets.CheckboxWithLabel("Advanced Beats", "Use heavy and normal beat hooks", self.enable_advanced_beat_animations)
        self.enable_shake_animation_checkbox      = Widgets.CheckboxWithLabel("Shake Animation", "Shake animation loop")
        self.style_selector                       = Widgets.Selector(animation_styles, default_index)
        self.apply_window_button                  = Widgets.ButtonWithOutlineSlim("Apply Window Settings")

        self.volume_slider                        = Widgets.SliderWithLabel("Volume", 0, 100, 100)
        self.player_speed_slider                  = Widgets.SliderWithLabel("Speed (%)", 10, 300, 100)

        self.bitcrush_mix_slider                  = Widgets.SliderWithLabel("BC Mix", 0, 100, 0)
        self.bitcrush_bits_slider                 = Widgets.SliderWithLabel("BC Bits", 1, 24, 16)
        self.bitcrush_downsample_slider           = Widgets.SliderWithLabel("Downsample", 1, 32, 1)

        self.pass_mix_slider                      = Widgets.SliderWithLabel("Filter Mix", 0, 100, 0)
        self.pass_freq_slider                     = Widgets.SliderWithLabel("Freq (Hz)", 100, 10000, 1000)
        self.pass_q_slider                        = Widgets.SliderWithLabel("Resonance", 1, 100, 10)
        self.pass_gain_slider                     = Widgets.SliderWithLabel("Gain", 0, 200, 100)

        self.eq_low_slider                        = Widgets.SliderWithLabel("EQ Low", 0, 200, 100)
        self.eq_mid_slider                        = Widgets.SliderWithLabel("EQ Mid", 0, 200, 100)
        self.eq_high_slider                       = Widgets.SliderWithLabel("EQ High", 0, 200, 100)

        self.background_noise_slider              = Widgets.SliderWithLabel("Background Noise", 0, 100, 0)
        self.reverb_mix_slider                    = Widgets.SliderWithLabel("Reverb Mix", 0, 100, 0)
        self.car_radio_checkbox                   = Widgets.CheckboxWithLabel("Car Radio", "Apply radio effect preset", False)

        self.delay_left_slider                    = Widgets.SliderWithLabel("Delay L (ms)", 0, 50, 0)
        self.delay_right_slider                   = Widgets.SliderWithLabel("Delay R (ms)", 0, 50, 0)

        self.radio_noise_intensity_slider         = Widgets.SliderWithLabel("Burst Intensity", 0, 100, 0)
        self.radio_noise_mix_slider               = Widgets.SliderWithLabel("Noise Mix", 0, 100, 30)
        self.radio_noise_color_selector           = Widgets.SelectorWithLabel("Noise Color", ["white", "pink", "brown"], default_text = "brown")
        self.radio_noise_attack_slider            = Widgets.SliderWithLabel("Attack (ms)", 0, 1000, 100)
        self.radio_noise_peak_slider              = Widgets.SliderWithLabel("Peak (ms)", 0, 1000, 180)
        self.radio_noise_release_slider           = Widgets.SliderWithLabel("Release (ms)", 0, 1000, 250)
        self.radio_noise_mute_slider              = Widgets.SliderWithLabel("Mute Audio", 0, 100, 45)
        self.radio_noise_permanent_checkbox       = Widgets.CheckboxWithLabel("Permanent", "Always active", False)
        self.radio_noise_random_duration_checkbox = Widgets.CheckboxWithLabel("Randomize", "Variable burst duration", True)

        self.tape_chew_intensity_slider           = Widgets.SliderWithLabel("Chew Intensity", 0, 100, 0)
        self.tape_chew_jitter_slider              = Widgets.SliderWithLabel("Jitter (ms)", 0, 500, 8)
        self.tape_chew_random_duration_checkbox   = Widgets.CheckboxWithLabel("Randomize", "Variable burst duration", True)

        self.echo_mix_slider                      = Widgets.SliderWithLabel("Echo Mix", 0, 100, 0)
        self.echo_delay_slider                    = Widgets.SliderWithLabel("Delay (ms)", 1, 2000, 180)
        self.echo_feedback_slider                 = Widgets.SliderWithLabel("Feedback", 0, 98, 25)
        self.echo_mode_selector                   = Widgets.SelectorWithLabel("Echo Mode", ["constant", "random"], default_text = "constant")
        self.echo_focus_selector                  = Widgets.SelectorWithLabel("Echo Focus", ["all", "voice", "bass"], default_text = "all")

        self.beat_threshold_slider                = Widgets.SliderWithLabel("Beat Sens.", 0, 100, 38)

        self.button_punch                         = Widgets.ButtonWithOutlineSlim("Title Punch")
        self.button_wobble                        = Widgets.ButtonWithOutlineSlim("Window Wobble")
        self.button_disturb                       = Widgets.ButtonWithOutlineSlim("Disturb FX")
        self.button_test_open                     = Widgets.ButtonWithOutlineSlim("Test Open")

        self.play_button                          = Widgets.ButtonWithOutlineSlim("Play")
        self.close_button                         = Widgets.ButtonWithOutline("Close")

        self.add_section(
            "Window",
            [
                self.margin_slider,
                self.max_tilt_slider,
                self.shake_frequency_slider,
                self.shake_deviation_slider,
                self.tilt_smoothing_slider,
                self.bpm_peak_slider,
                self.start_position_enabled_checkbox,
                self.start_position_x_slider,
                self.start_position_y_slider,
                self.dialog_checkbox,
                self.stays_on_top_checkbox,
                self.enable_tilt_checkbox,
                self.enable_open_animation_checkbox,
                self.enable_close_animation_checkbox,
                self.enable_audio_effects_checkbox,
                self.enable_advanced_beat_checkbox,
                self.enable_shake_animation_checkbox,
                self.style_selector,
                self.apply_window_button
            ]
        )

        self.add_section("Playback", [self.play_button])

        self.add_section(
            "Audio",
            [
                self.volume_slider,
                self.player_speed_slider
            ]
        )

        self.add_section(
            "Bitcrush",
            [
                self.bitcrush_mix_slider,
                self.bitcrush_bits_slider,
                self.bitcrush_downsample_slider
            ]
        )

        self.add_section(
            "Passes Filter",
            [
                self.pass_mix_slider,
                self.pass_freq_slider,
                self.pass_q_slider,
                self.pass_gain_slider
            ]
        )

        self.add_section(
            "Equalizer",
            [
                self.eq_low_slider,
                self.eq_mid_slider,
                self.eq_high_slider
            ]
        )

        self.add_section(
            "Presets & Effects",
            [
                self.reverb_mix_slider,
                self.background_noise_slider,
                self.car_radio_checkbox
            ]
        )

        self.add_section(
            "Stereo",
            [
                self.delay_left_slider,
                self.delay_right_slider
            ]
        )

        self.add_section(
            "Radio Noise",
            [
                self.radio_noise_intensity_slider,
                self.radio_noise_mix_slider,
                self.radio_noise_color_selector,
                self.radio_noise_attack_slider,
                self.radio_noise_peak_slider,
                self.radio_noise_release_slider,
                self.radio_noise_mute_slider,
                self.radio_noise_permanent_checkbox,
                self.radio_noise_random_duration_checkbox
            ]
        )

        self.add_section(
            "Tape Chew",
            [
                self.tape_chew_intensity_slider,
                self.tape_chew_jitter_slider,
                self.tape_chew_random_duration_checkbox
            ]
        )

        self.add_section(
            "Echo",
            [
                self.echo_mix_slider,
                self.echo_delay_slider,
                self.echo_feedback_slider,
                self.echo_mode_selector,
                self.echo_focus_selector
            ]
        )

        self.add_section("Detection", [self.beat_threshold_slider])

        self.add_section(
            "Animation Triggers",
            [
                self.button_punch,
                self.button_wobble,
                self.button_disturb,
                self.button_test_open,
                self.close_button
            ]
        )

    # Binding

    def bind_logic(self) -> None:
        self.volume_slider.valueChanged.connect(
            lambda value: Player.player.set_volume(value / 100)
        )

        self.player_speed_slider.valueChanged.connect(
            lambda value: Player.player.set_speed(value / 100, duration_ms = 3000)
        )

        for control in [self.bitcrush_mix_slider, self.bitcrush_bits_slider, self.bitcrush_downsample_slider]:
            self.connect_change(control, self.update_bitcrush)

        for control in [self.pass_mix_slider, self.pass_freq_slider, self.pass_q_slider, self.pass_gain_slider]:
            self.connect_change(control, self.update_passes)

        for control in [self.eq_low_slider, self.eq_mid_slider, self.eq_high_slider]:
            self.connect_change(control, self.update_eq)

        self.background_noise_slider.valueChanged.connect(
            lambda value: Player.player.set_background_noise(mix = value / 100)
        )

        self.reverb_mix_slider.valueChanged.connect(
            lambda value: Player.player.set_reverb(mix = value / 100)
        )

        self.car_radio_checkbox.stateChanged.connect(
            lambda active: Player.player.set_car_radio(active)
        )

        self.delay_left_slider.valueChanged.connect(self.update_delays)
        self.delay_right_slider.valueChanged.connect(self.update_delays)

        for control in [
            self.radio_noise_intensity_slider,
            self.radio_noise_mix_slider,
            self.radio_noise_color_selector,
            self.radio_noise_attack_slider,
            self.radio_noise_peak_slider,
            self.radio_noise_release_slider,
            self.radio_noise_mute_slider,
            self.radio_noise_permanent_checkbox,
            self.radio_noise_random_duration_checkbox
        ]:
            self.connect_change(control, self.update_radio_noise)

        for control in [
            self.tape_chew_intensity_slider,
            self.tape_chew_jitter_slider,
            self.tape_chew_random_duration_checkbox
        ]:
            self.connect_change(control, self.update_tape_chew)

        for control in [
            self.echo_mix_slider,
            self.echo_delay_slider,
            self.echo_feedback_slider,
            self.echo_mode_selector,
            self.echo_focus_selector
        ]:
            self.connect_change(control, self.update_echo)

        self.beat_threshold_slider.valueChanged.connect(
            lambda value: Player.player.onset_detector.set_threshold(value / 100)
        )

        self.style_selector.selectionChanged.connect(self.on_style_changed)
        self.apply_window_button.clicked.connect(self.apply_window_settings)

        self.button_punch.clicked.connect(lambda: self.pulse_title(peak_scale = 1.5))
        self.button_wobble.clicked.connect(self.wobble)
        self.button_disturb.clicked.connect(self.play_disturb_animation)
        self.button_test_open.clicked.connect(self.open_window)

        self.play_button.clicked.connect(Player.player.toggle_playback)
        self.close_button.clicked.connect(self.on_cancel)

    # Handlers

    def apply_window_settings(self) -> None:
        logger.debug("Setting window settings.")

        style = self.style_selector.current_text()

        if style:
            self.animation_style = style

        self.max_tilt_angle                  = self.max_tilt_slider.value()
        self.enable_tilt                     = self.enable_tilt_checkbox.isChecked()
        self.enable_open_animation           = self.enable_open_animation_checkbox.isChecked()
        self.enable_close_animation          = self.enable_close_animation_checkbox.isChecked()
        self.enable_advanced_beat_animations = self.enable_advanced_beat_checkbox.isChecked()
        self.enable_transition_audio_effects = self.enable_audio_effects_checkbox.isChecked()
        self.margin_x                        = self.margin_slider.value()
        self.margin_y                        = self.margin_slider.value()
        self.shake_frequency_ms              = self.shake_frequency_slider.value()
        self.shake_deviation                 = self.shake_deviation_slider.value() / 10
        self.tilt_smoothing                  = self.tilt_smoothing_slider.value() / 100
        self.bpm_peak_scale                  = self.bpm_peak_slider.value() / 100

        if self.start_position_enabled_checkbox.isChecked():
            self.start_position = QPoint(
                self.start_position_x_slider.value(),
                self.start_position_y_slider.value()
            )
        else:
            self.start_position = None

        if self.enable_shake_animation_checkbox.isChecked():
            self.start_shake()
        else:
            self.stop_shake()

        self.apply_attributes(
            self.dialog_checkbox.isChecked(),
            self.stays_on_top_checkbox.isChecked()
        )

        self.refresh_bpm_connections()
        self.adjustSize()

        if self.start_position:
            self.center_window()

    def refresh_bpm_connections(self) -> None:
        if not self.player:
            return

        try:
            Player.bpm_informer.beat_4.disconnect(self.bpm_tick_animation)
        except Exception:
            pass

        try:
            self.player.beat_heavy.disconnect(self.beat_heavy_animation)
            self.player.beat_normal.disconnect(self.beat_normal_animation)
        except Exception:
            pass

        if not self.bpm_animations_enabled:
            return

        if self.enable_advanced_beat_animations:
            self.player.beat_heavy.connect(self.beat_heavy_animation)
            self.player.beat_normal.connect(self.beat_normal_animation)
            return

        Player.bpm_informer.beat_4.connect(self.bpm_tick_animation)

    def on_style_changed(self, *unused_arguments: object) -> None:
        style = self.style_selector.current_data()

        if style:
            self.animation_style = style

    def update_radio_noise(self) -> None:
        Player.player.set_noise(
            intensity          = self.radio_noise_intensity_slider.value() / 100,
            mix                = self.radio_noise_mix_slider.value() / 100,
            permanent          = self.radio_noise_permanent_checkbox.isChecked(),
            color              = self.radio_noise_color_selector.current_data(),
            attack_ms          = self.radio_noise_attack_slider.value(),
            peak_ms            = self.radio_noise_peak_slider.value(),
            release_ms         = self.radio_noise_release_slider.value(),
            mute_audio         = self.radio_noise_mute_slider.value() / 100,
            randomize_duration = self.radio_noise_random_duration_checkbox.isChecked()
        )

    def update_tape_chew(self) -> None:
        Player.player.set_tape_chew(
            intensity          = self.tape_chew_intensity_slider.value() / 100,
            jitter_ms          = float(self.tape_chew_jitter_slider.value()),
            randomize_duration = self.tape_chew_random_duration_checkbox.isChecked()
        )

    def update_echo(self) -> None:
        Player.player.set_echo(
            mix      = self.echo_mix_slider.value() / 100,
            delay_ms = self.echo_delay_slider.value(),
            feedback = self.echo_feedback_slider.value() / 100,
            mode     = self.echo_mode_selector.current_data(),
            focus    = self.echo_focus_selector.current_data()
        )

    def update_passes(self) -> None:
        Player.player.set_passes(
            frequencies = [float(self.pass_freq_slider.value())],
            q           = self.pass_q_slider.value() / 10,
            mix         = self.pass_mix_slider.value() / 100,
            gain        = self.pass_gain_slider.value() / 100
        )

    def update_bitcrush(self) -> None:
        Player.player.set_bitcrush(
            bits       = self.bitcrush_bits_slider.value(),
            downsample = self.bitcrush_downsample_slider.value(),
            mix        = self.bitcrush_mix_slider.value() / 100
        )

    def update_delays(self) -> None:
        Player.player.set_channel_delay(
            left_to_ms  = self.delay_left_slider.value(),
            right_to_ms = self.delay_right_slider.value(),
            duration_ms = 1000
        )

    def update_eq(self) -> None:
        Player.player.set_eq(
            low  = self.eq_low_slider.value() / 100,
            mid  = self.eq_mid_slider.value() / 100,
            high = self.eq_high_slider.value() / 100
        )