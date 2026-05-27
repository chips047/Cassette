import time
import json
import aubio
import numpy
import tempfile
import soundfile

from loguru import logger

from pathlib import Path

from System.Common import (
    Utils,
    Constants
)

class NoAudioStreams(Exception):
    pass

class PermissionError(Exception):
    pass

class CorruptedFileError(Exception):
    pass

def probe_audio(path: str) -> dict:
    cmd = [
        Constants.FFPROBE_PATH,
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        path
    ]

    try:
        logger.debug(f"Probing audio file: {path}")
        result = Utils.run_hidden(cmd)
    
    except FileNotFoundError:
        logger.error("FFprobe was not found. Please ensure it is included with the application.")
        raise FileNotFoundError("FFprobe was not found.")

    if result.returncode != 0:
        logger.error(f"FFprobe error: {result.stderr}")
        raise CorruptedFileError(
            "The audio file is corrupted or in an unsupported format."
        )

    try:
        logger.debug("Parsing FFprobe output")
        return json.loads(result.stdout)
    
    except json.JSONDecodeError:
        logger.error("Failed to parse FFprobe output. The audio file may be corrupted or in an unsupported format.")
        raise CorruptedFileError(
            "The audio file is corrupted or in an unsupported format."
        )

def ensure_wav(path: str) -> str:
    path_obj = Path(path)

    if not path_obj.exists():
        raise FileNotFoundError("The specified audio file was not found.")

    try:
        probe = probe_audio(path)
    
    except FileNotFoundError:
        raise
    
    except Exception:
        raise CorruptedFileError(
            "The audio file is corrupted or in an unsupported format."
        )

    audio_streams = [
        s for s in probe.get("streams", [])
        if s.get("codec_type") == "audio"
    ]

    if not audio_streams:
        raise NoAudioStreams()

    fmt = probe.get("format", {}).get("format_name", "").lower()

    if "wav" in fmt and path_obj.suffix.lower() == ".wav":
        logger.warning("Audio is WAV. Not converting.")
        return str(path_obj)

    logger.warning("Audio is not WAV. Starting conversion...")

    sample_rate = audio_streams[0].get("sample_rate", "44100")

    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    cmd = [
        Constants.FFMPEG_PATH,
        "-y",
        "-v", "error",
        "-i", path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        temp_path
    ]

    try:
        logger.debug(f"Converting audio to WAV: {path} -> {temp_path}")
        result = Utils.run_hidden(cmd)

        if result.returncode != 0:
            stderr = (result.stderr or "").lower()

            if "permission" in stderr or "access is denied" in stderr:
                raise PermissionError(
                    "Permission error while accessing the file. "
                    "Please check if the file is open in another application."
                )

            raise CorruptedFileError(
                "The audio file is corrupted or in an unsupported format."
            )

        return temp_path

    except FileNotFoundError:
        raise FileNotFoundError("FFmpeg was not found.")

def analyze_bpm_and_beats(
    audio_path:  str,
    hop_size:    int = 512,
    window_size: int = 1024
) -> tuple[float, list[float]]:
    
    try:
        source = aubio.source(audio_path, 0, hop_size)
    
    except Exception:
        return 0.0, []

    logger.debug(f"Analyzing BPM and beats for: {audio_path}")
    
    samplerate = source.samplerate or 44100
    detector   = aubio.tempo("default", window_size, hop_size, samplerate)
    detector.set_silence(-40)

    beats:        list[float] = []
    total_frames: int         = 0
    count:        int         = 0

    while True:
        samples, read = source()
        total_frames += read

        if detector(samples):
            beats.append(detector.get_last_s())

        if read < hop_size:
            break

        count += 1
        if count % 150 == 0:
            time.sleep(0.0001)

    bpm = 0.0

    if len(beats) >= 2:
        beats_array = numpy.array(beats, dtype=numpy.float32)
        intervals   = numpy.diff(beats_array)
        intervals   = intervals[(intervals > 0.08) & (intervals < 10.0)]

        if intervals.size > 0:
            bpm = round(float(numpy.median(60.0 / intervals)), 2)

    formatted_beats = [round(float(b), 3) for b in beats]

    logger.debug(f"Estimated BPM: {bpm}")

    return bpm, formatted_beats

def load_audio(path: str) -> tuple[numpy.ndarray, int]:
    try:
        data, sample_rate = soundfile.read(path, dtype="float32")
        logger.info(f"Loaded audio file: {path} (Sample Rate: {sample_rate}, Channels: {data.shape[1] if data.ndim > 1 else 1})")
        return data, sample_rate
    
    except soundfile.LibsndfileError:
        raise CorruptedFileError("The audio file is corrupted or in an unsupported format.")