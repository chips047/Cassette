from __future__ import annotations

import numpy
import mimetypes

from PyQt6.QtCore import (
    Qt,
    QTimer
)

from PyQt6.QtGui import (
    QImage,
    QDropEvent,
    QDragEnterEvent,
    QGuiApplication
)

from PyQt6.QtWidgets import (
    QWidget,
    QFileDialog,
    QHBoxLayout
)

from System.Services  import Player
from System.Interface import Widgets

from System.Interface.Windows import FloatingWindowGPU

# Segment Editor

class SegmentEditor(FloatingWindowGPU):
    def __init__(
            self,
            title:          str,
            segment_number: int         | None = None,
            defaults:       list[int]   | None = None,
            default_levels: list[float] | None = None,
            parent:         QWidget     | None = None
        ) -> None:

        super().__init__(title, parent = parent)

        self.segmented_bar = Widgets.SegmentedBar(segment_number, defaults, default_levels)
        self.segmented_bar.setMinimumWidth(420)

        self.binary_checkbox = Widgets.Checkbox("Binary mode", default = False)
        self.binary_checkbox.toggled.connect(self.on_binary_mode_toggled)

        self.brush_slider = Widgets.SliderWithLabel("Segment brightness (%)", 5, 100, 100)
        self.brush_slider.valueChanged.connect(self.on_brush_brightness_changed)

        upper_button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "Enable all",  self.segmented_bar.enable_all),
                (Widgets.ButtonWithOutline, "Disable all", self.segmented_bar.disable_all),
                (Widgets.ButtonWithOutline, "Zebra",       self.segmented_bar.zebra),
                (Widgets.ButtonWithOutline, "Invert",      self.segmented_bar.invert)
            ],
            button_width = 96
        )

        lower_button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "Nah",   self.on_cancel),
                (Widgets.NothingButton,     "Apply", self.on_ok, False)
            ]
        )
        self.apply_button = lower_button_row.get_button("Apply")

        if self.apply_button is None:
            raise RuntimeError("Segment editor Apply button was not created")

        self.content_layout.addWidget(self.segmented_bar)
        self.content_layout.addWidget(self.binary_checkbox)
        self.content_layout.addWidget(self.brush_slider)
        self.content_layout.addLayout(upper_button_row)
        self.content_layout.addLayout(lower_button_row)

        self.segmented_bar.segment_changed.connect(self.wobble)

    def on_binary_mode_toggled(self, checked: bool) -> None:
        self.segmented_bar.set_binary_mode(checked)
        self.brush_slider.setVisible(not checked)
        QTimer.singleShot(0, self.adjustSize)

    def on_brush_brightness_changed(self, value: int) -> None:
        self.segmented_bar.set_brush_level(value / 100.0)

    def on_ok(self) -> None:
        if not any(self.segmented_bar.active):
            self.apply_button.start_glitch()
            self.play_disturb_animation()

            return

        super().on_ok()

    def segments(self) -> list[float]:
        return self.segmented_bar.levels

# Matrix Segment Editor

class MatrixSegmentEditor(FloatingWindowGPU):
    IMAGE_EXTENSIONS: tuple[str, ...] = (
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"
    )

    def __init__(
            self,
            title:          str,
            device:         object,
            defaults:       list[int]   | None = None,
            default_levels: list[float] | None = None,
            parent:         QWidget     | None = None
        ) -> None:

        super().__init__(title, parent = parent, max_tilt_angle = 12)

        self.device           = device
        self.image_luminances = None
        self.drag_loop_sound  = None

        self.setAcceptDrops(True)

        self.setup_ui(defaults, default_levels)
        self.adjustSize()

    # Setup

    def calculate_optimal_matrix_size(self) -> int:
        screen           = QGuiApplication.primaryScreen()
        screen_height_px = screen.availableGeometry().height() if screen else 900
        reserved_px      = 420

        return max(220, min(380, screen_height_px - reserved_px))

    def setup_ui(
            self,
            defaults:       list[int]   | None,
            default_levels: list[float] | None
        ) -> None:

        optimal_size    = self.calculate_optimal_matrix_size()
        self.matrix_bar = Widgets.MatrixSegmentBar(
            device          = self.device,
            defaults        = defaults,
            default_levels  = default_levels,
            preview_size_px = optimal_size
        )

        matrix_wrapper = QHBoxLayout()
        matrix_wrapper.setContentsMargins(0, 0, 0, 0)
        matrix_wrapper.addStretch()
        matrix_wrapper.addWidget(self.matrix_bar)
        matrix_wrapper.addStretch()

        self.warning_label = Widgets.DescriptionLabel(
            "`Heads up:` Selecting custom pixels or adding an image will limit available effects.",
            560
        )

        self.binary_checkbox = Widgets.Checkbox("Binary mode", default = False)
        self.binary_checkbox.toggled.connect(self.on_binary_mode_toggled)

        self.brush_slider = Widgets.SliderWithLabel("Pixel brightness (%)", 5, 100, 100)
        self.brush_slider.valueChanged.connect(self.on_brush_brightness_changed)

        self.bw_balance_slider = Widgets.SliderWithLabel(
            "B/W Balance",
            0,
            100,
            50
        )
        self.bw_balance_slider.setVisible(False)
        self.bw_balance_slider.valueChanged.connect(self.on_bw_balance_changed)

        upper_button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "Enable all",  self.matrix_bar.enable_all),
                (Widgets.ButtonWithOutline, "Disable all", self.matrix_bar.disable_all),
                (Widgets.ButtonWithOutline, "Zebra",       self.matrix_bar.zebra),
                (Widgets.ButtonWithOutline, "Invert",      self.matrix_bar.invert)
            ],
            button_width = 110
        )

        image_button = Widgets.ButtonWithOutline("Add Image (or drop onto window)")
        image_button.clicked.connect(self.ask_for_image)

        lower_button_row = Widgets.ButtonRow(
            [
                (Widgets.ButtonWithOutline, "Nah",   self.on_cancel),
                (Widgets.NothingButton,     "Apply", self.on_ok, False)
            ]
        )
        self.apply_button = lower_button_row.get_button("Apply")

        if self.apply_button is None:
            raise RuntimeError("Matrix segment editor Apply button was not created")

        self.content_layout.addLayout(matrix_wrapper)
        self.content_layout.addWidget(self.warning_label)
        self.content_layout.addWidget(self.binary_checkbox)
        self.content_layout.addWidget(self.brush_slider)
        self.content_layout.addWidget(self.bw_balance_slider)
        self.content_layout.addLayout(upper_button_row)
        self.content_layout.addWidget(image_button)
        self.content_layout.addLayout(lower_button_row)

        self.matrix_bar.segment_changed.connect(self.wobble)

    # Mode and Brush Handlers

    def on_binary_mode_toggled(self, checked: bool) -> None:
        self.matrix_bar.set_binary_mode(checked)
        self.brush_slider.setVisible(not checked)

        if self.image_luminances is not None:
            self.on_bw_balance_changed(self.bw_balance_slider.value())

        QTimer.singleShot(0, self.adjustSize)

    def on_brush_brightness_changed(self, value: int) -> None:
        self.matrix_bar.set_brush_level(value / 100.0)

    # Image Conversion

    def ask_for_image(self) -> None:
        dialog = QFileDialog(
            self,
            "Open Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*)"
        )
        dialog.setOptions(QFileDialog.Option.ReadOnly)

        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return

        selected_files = dialog.selectedFiles()

        if not selected_files:
            return

        image = QImage(selected_files[0])

        if image.isNull():
            Player.ui_player.play_sound("Alerts/Errors/MegaCritical")
            self.play_disturb_animation()

            return

        self.apply_image(image)

    def apply_image(self, image: QImage) -> None:
        square_side = min(image.width(), image.height())

        if square_side <= 0:
            return

        crop_x       = (image.width() - square_side) // 2
        crop_y       = (image.height() - square_side) // 2
        square_image = image.copy(crop_x, crop_y, square_side, square_side)

        matrix_side  = len(self.device.matrix_rows) if self.device.matrix_rows else 25
        sample_side  = matrix_side * 4
        scaled_image = square_image.scaled(
            sample_side,
            sample_side,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ).convertToFormat(QImage.Format.Format_RGBA8888)

        pointer = scaled_image.constBits()
        pointer.setsize(scaled_image.sizeInBytes())
        raw_array = numpy.frombuffer(bytes(pointer), dtype = numpy.uint8).reshape((sample_side, sample_side, 4)).astype(numpy.float32)

        alpha_channel  = raw_array[:, :, 3] / 255.0
        luminance_grid = (
            0.299 * raw_array[:, :, 0] +
            0.587 * raw_array[:, :, 1] +
            0.114 * raw_array[:, :, 2]
        ) * alpha_channel

        sampled_values = []
        radius_px      = max(1, sample_side // (matrix_side * 2))

        for normalized_x, normalized_y in self.device.matrix_led_coordinates:
            center_x = int(round(((normalized_x + 1.0) * 0.5) * (sample_side - 1)))
            center_y = int(round(((normalized_y + 1.0) * 0.5) * (sample_side - 1)))

            min_x = max(0, center_x - radius_px)
            max_x = min(sample_side, center_x + radius_px + 1)
            min_y = max(0, center_y - radius_px)
            max_y = min(sample_side, center_y + radius_px + 1)

            patch_mean = float(numpy.mean(luminance_grid[min_y:max_y, min_x:max_x]))
            sampled_values.append(patch_mean)

        sampled_array = numpy.array(sampled_values, dtype = numpy.float32)
        min_luminance = float(numpy.min(sampled_array))
        max_luminance = float(numpy.max(sampled_array))

        if (max_luminance - min_luminance) > 1e-3:
            normalized_array = (sampled_array - min_luminance) / (max_luminance - min_luminance)

        else:
            normalized_array = sampled_array / 255.0

        self.image_luminances = normalized_array
        auto_balance_percent  = self.compute_otsu_balance_percent(normalized_array)

        if not self.bw_balance_slider.isVisible():
            self.bw_balance_slider.setVisible(True)
            QTimer.singleShot(0, self.adjustSize)

        self.bw_balance_slider.setValue(auto_balance_percent, animated = False)

    @staticmethod
    def compute_otsu_balance_percent(normalized_values: numpy.ndarray) -> int:
        if normalized_values.size == 0:
            return 50

        histogram, _    = numpy.histogram(normalized_values, bins = 100, range = (0.0, 1.0))
        total_pixels    = float(normalized_values.size)
        bin_centers     = numpy.arange(100, dtype = numpy.float32)
        total_sum       = float(numpy.sum(bin_centers * histogram))

        background_weight = 0.0
        background_sum    = 0.0
        best_variance     = -1.0
        best_threshold    = 50

        for bin_index in range(100):
            background_weight += float(histogram[bin_index])

            if background_weight <= 0.0:
                continue

            foreground_weight = total_pixels - background_weight

            if foreground_weight <= 0.0:
                break

            background_sum += float(bin_index * histogram[bin_index])

            background_mean = background_sum / background_weight
            foreground_mean = (total_sum - background_sum) / foreground_weight

            variance = background_weight * foreground_weight * ((background_mean - foreground_mean) ** 2)

            if variance > best_variance:
                best_variance  = variance
                best_threshold = bin_index

        return max(10, min(90, best_threshold))

    def on_bw_balance_changed(self, balance_percent: int) -> None:
        if self.image_luminances is None:
            return

        if balance_percent <= 0:
            levels = [1.0] * len(self.image_luminances)

        elif balance_percent >= 100:
            levels = [0.0] * len(self.image_luminances)

        elif self.binary_checkbox.isChecked():
            threshold = balance_percent / 100.0
            levels    = [1.0 if float(value) >= threshold else 0.0 for value in self.image_luminances]

        else:
            balance_ratio = balance_percent / 100.0
            cutoff        = max(0.0, (balance_ratio - 0.35) * 1.15)
            gamma         = 2.0 ** ((balance_ratio - 0.5) * 2.4)
            levels        = []

            for raw_value in self.image_luminances:
                value = float(raw_value)

                if value <= cutoff or cutoff >= 0.999:
                    levels.append(0.0)

                    continue

                adjusted = ((value - cutoff) / (1.0 - cutoff)) ** gamma
                quantized = round(adjusted, 2)

                levels.append(quantized if quantized >= 0.04 else 0.0)

        self.matrix_bar.set_active_mask(levels)

    # Drag and Drop Events

    def is_image_file(self, file_path: str) -> bool:
        mime_type = mimetypes.guess_type(file_path)[0]

        if mime_type and mime_type.startswith("image/"):
            return True

        return file_path.lower().endswith(self.IMAGE_EXTENSIONS)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        Player.ui_player.play_sound(
            "Controls/DragDrop/Drop",
            speed       = 1.03,
            setting_key = "drag_drop_sounds"
        )

        if not self.drag_loop_sound:
            self.drag_loop_sound = Player.ui_player.play_sound(
                "Controls/DragDrop/Loop",
                loop        = True,
                setting_key = "drag_drop_sounds"
            )

        self.move_start_animation()
        self.start_shake()

        event.acceptProposedAction()

    def dragLeaveEvent(self, event: object) -> None:
        Player.ui_player.play_sound(
            "Controls/DragDrop/Drop",
            speed       = 0.94,
            setting_key = "drag_drop_sounds"
        )

        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        self.move_end_animation()
        self.stop_shake()

    def dropEvent(self, event: QDropEvent) -> None:
        Player.ui_player.play_sound(
            "Controls/DragDrop/Drop",
            speed       = 0.94,
            setting_key = "drag_drop_sounds"
        )

        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        self.move_end_animation()
        self.stop_shake()

        loaded_image = None

        for url in event.mimeData().urls():
            file_path = url.toLocalFile()

            if not file_path or not self.is_image_file(file_path):
                continue

            candidate = QImage(file_path)

            if not candidate.isNull():
                loaded_image = candidate

                break

        if loaded_image is None and event.mimeData().hasImage():
            candidate = QImage(event.mimeData().imageData())

            if not candidate.isNull():
                loaded_image = candidate

        if loaded_image is None:
            Player.ui_player.play_sound("Alerts/Errors/MegaCritical")
            self.play_disturb_animation()

            return

        self.apply_image(loaded_image)
        event.acceptProposedAction()

    # Lifecycle Handlers

    def really_close(self) -> None:
        if self.drag_loop_sound:
            self.drag_loop_sound.stop()
            self.drag_loop_sound = None

        super().really_close()

    def on_ok(self) -> None:
        if not any(self.matrix_bar.active):
            self.apply_button.start_glitch()
            self.play_disturb_animation()

            return

        super().on_ok()

    def segments(self) -> list[float]:
        return self.matrix_bar.levels