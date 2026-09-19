from __future__ import annotations

import json
import numpy
import traceback

from urllib.error import URLError

from urllib.request import (
    Request,
    urlopen
)

from PyQt6.QtGui import QImage

from PyQt6.QtCore import (
    QObject,
    QThread,
    QRunnable,
    pyqtSignal
)

from PyQt6.QtWidgets import QWidget

from System.Common import (
    Dev,
    Utils
)

from System.Services import Audio

# Tile Workers

class TileWorkerSignals(QObject):
    tile_ready = pyqtSignal(int, QImage)

class TileWorker(QRunnable):
    def __init__(
            self,
            controller,
            tile_index:         int,
            generation:         int,
            device_pixel_ratio: float
        ) -> None:

        super().__init__()

        self.controller         = controller
        self.tile_index         = tile_index
        self.generation         = generation
        self.device_pixel_ratio = device_pixel_ratio
        self.signals            = TileWorkerSignals()

        self.setAutoDelete(True)

    def run(self) -> None:
        image = self.controller.compute_tile_image(self.tile_index, self.device_pixel_ratio)

        self.signals.tile_ready.emit(
            self.tile_index,
            image if image else QImage()
        )

# Audio Workers

class BaseAudioWorker(QObject):
    error = pyqtSignal(str)

    def __init__(self, file_path: str) -> None:
        super().__init__()

        self.audio_path = file_path

@Dev.track_ram
class PrepareWorker(BaseAudioWorker):
    finished = pyqtSignal(str)

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

@Dev.track_ram
class LoadAudioWorker(BaseAudioWorker):
    finished = pyqtSignal(object)

    def run(self) -> None:
        try:
            data, sample_rate  = Audio.load_audio(self.audio_path)
            audio_float_data   = data.astype("float32")

            if audio_float_data.ndim > 1:
                audio_float_data = numpy.mean(audio_float_data, axis = 1)

            samples_per_pixel  = len(audio_float_data) / 1000
            step_size          = max(1, int(numpy.ceil(samples_per_pixel)))
            padded_length      = ((len(audio_float_data) + step_size - 1) // step_size) * step_size
            padding_difference = padded_length - len(audio_float_data)
            padded_audio       = numpy.pad(audio_float_data, (0, padding_difference), mode = "constant")
            reshaped_audio     = padded_audio.reshape(-1, step_size)
            waveform_data      = numpy.mean(numpy.abs(reshaped_audio), axis = 1)
            waveform_data      = Utils.gaussian_filter1d_np(waveform_data, sigma = 2)

            self.finished.emit((data, sample_rate, waveform_data))

        except Audio.CorruptedFileError:
            self.error.emit("The audio file is corrupted or in an unsupported format.")

        except Exception:
            self.error.emit(traceback.format_exc())

@Dev.track_ram
class BPMWorker(BaseAudioWorker):
    finished = pyqtSignal(float, object)

    def run(self) -> None:
        try:
            beats_per_minute, peaks = Audio.analyze_bpm_and_beats(self.audio_path)
            self.finished.emit(beats_per_minute, peaks)

        except Exception:
            self.error.emit(traceback.format_exc())

# Network Workers

class NetworkReportWorker(QThread):
    request_succeeded = pyqtSignal()
    request_failed    = pyqtSignal(str)

    def __init__(
            self,
            endpoint_url:       str,
            payload_dictionary: dict,
            timeout_seconds:    float          = 8.0,
            parent:             QWidget | None = None
        ) -> None:

        super().__init__(parent)

        self.endpoint_url        = endpoint_url
        self.payload_dictionary = payload_dictionary
        self.timeout_seconds     = timeout_seconds

    def run(self) -> None:
        try:
            encoded_payload = json.dumps(self.payload_dictionary, ensure_ascii = False).encode("utf-8")

            request_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }

            network_request = Request(
                self.endpoint_url,
                data    = encoded_payload,
                headers = request_headers,
                method  = "POST"
            )

            with urlopen(network_request, timeout = self.timeout_seconds) as network_response:
                response_code = network_response.getcode()

                if response_code != 200:
                    self.request_failed.emit(f"Server response code: {response_code}")
                    return

                self.request_succeeded.emit()

        except URLError:
            self.request_failed.emit("Network unreachable or blocked")

        except Exception as generic_exception:
            self.request_failed.emit(str(generic_exception))