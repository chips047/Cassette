import time
import aubio
import numpy
import ffmpeg
import tempfile
import soundfile

from loguru import logger

from System.Common.Constants import (
    FFMPEG_PATH,
    FFPROBE_PATH
)

class NoAudioStreams(Exception):
    pass

class PermissionError(Exception):
    pass

class CorruptedFileError(Exception):
    pass

def ensure_wav(path: str) -> str:
    try:
        probe = ffmpeg.probe(path, cmd=FFPROBE_PATH)
    
    except ffmpeg.Error:
        raise CorruptedFileError("The audio file is corrupted or in an unsupported format.")
    
    except FileNotFoundError:
        raise FileNotFoundError("The specified audio file was not found.")

    audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]

    if not audio_streams:
        raise NoAudioStreams()

    fmt = probe.get("format", {}).get("format_name", "")

    if "wav" in fmt and path.lower().endswith(".wav"):
        logger.warning("Audio is WAV. Not converting.")
        return path

    logger.warning("Audio is not WAV. Starting conversion...")

    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    try:
        (
            ffmpeg
            .input(path)
            .output(temp_path, acodec="pcm_s16le", ar=audio_streams[0].get("sample_rate", 44100))
            .overwrite_output()
            .run(cmd = FFMPEG_PATH, quiet = True)
        )
    
    except ffmpeg.Error as e:
        stderr = e.stderr.decode(errors="ignore") if e.stderr else ""
        
        if "permission" in stderr.lower():
            raise PermissionError("Permission error while accessing the file. Please check if the file is open in another application.")
        
        raise CorruptedFileError("The audio file is corrupted or in an unsupported format.")

    return temp_path

def analyze_bpm_and_beats(
    audio_path:  str,
    hop_size:    int = 512,
    window_size: int = 1024
) -> tuple[float, list[float]]:
    
    try:
        source = aubio.source(audio_path, 0, hop_size)
    
    except Exception:
        return 0.0, []

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

    return bpm, formatted_beats

def load_audio(path: str) -> tuple[numpy.ndarray, int]:
    try:
        data, sample_rate = soundfile.read(path, dtype="float32")
        return data, sample_rate
    
    except soundfile.LibsndfileError:
        raise CorruptedFileError("The audio file is corrupted or in an unsupported format.")