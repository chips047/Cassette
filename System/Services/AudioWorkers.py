import numpy
import traceback

from PyQt6.QtCore import (
    QObject,
    pyqtSignal
)

from System.Common import (
    Dev,
    Utils
)

from System.Services import Audio

# Audio Workers

@Dev.track_ram
class PrepareWorker(QObject):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str) -> None:
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

@Dev.track_ram
class LoadAudioWorker(QObject):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str) -> None:
        super().__init__()

        self.audio_path = file_path

    def run(self) -> None:
        try:
            data, sample_rate = Audio.load_audio(self.audio_path)
            audio_float       = data.astype("float32")

            if audio_float.ndim > 1:
                audio_float = numpy.mean(audio_float, axis = 1)

            samples_per_pixel = len(audio_float) / 1000
            step              = max(1, int(numpy.ceil(samples_per_pixel)))
            padded_length     = ((len(audio_float) + step - 1) // step) * step
            padded            = numpy.pad(audio_float, (0, padded_length - len(audio_float)), mode = "constant")
            reshaped          = padded.reshape(-1, step)
            waveform_data     = numpy.mean(numpy.abs(reshaped), axis = 1)
            waveform_data     = Utils.gaussian_filter1d_np(waveform_data, sigma = 2)

            self.finished.emit((data, sample_rate, waveform_data))

        except Audio.CorruptedFileError:
            self.error.emit("The audio file is corrupted or in an unsupported format.")

        except Exception:
            self.error.emit(traceback.format_exc())

@Dev.track_ram
class BPMWorker(QObject):
    finished = pyqtSignal(float, object)
    error    = pyqtSignal(str)

    def __init__(self, file_path: str) -> None:
        super().__init__()

        self.audio_path = file_path

    def run(self) -> None:
        try:
            bpm, peaks = Audio.analyze_bpm_and_beats(self.audio_path)
            self.finished.emit(bpm, peaks)

        except Exception:
            self.error.emit(traceback.format_exc())