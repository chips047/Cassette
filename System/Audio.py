import aubio
import tempfile

import numpy as np

from PyQt5.QtCore import *
from loguru import logger
from pydub import AudioSegment

import math

def ensure_wav(path):
    if path.lower().endswith(".wav"):
        return path

    tmp_path = tempfile.mktemp(suffix=".wav")
    audio = AudioSegment.from_file(path)
    audio.export(tmp_path, format="wav", parameters=["-acodec", "pcm_s16le"])
    
    return tmp_path

def analyze_bpm_and_beats(
        audio_path: str,
        hop_size: int = 256,
        win_s = 1024
    ):

    try:
        audio_path = ensure_wav(audio_path)
        s = aubio.source(audio_path, 0, hop_size)
    
    except Exception as e:
        return 0, []

    samplerate = s.samplerate or 44100

    # Темпо-детектор
    o = aubio.tempo("default", win_s, hop_size, samplerate)
    o.set_silence(-40)

    beats = []
    total_frames = 0

    while True:
        samples, read = s()
        total_frames += read

        is_beat = o(samples)
        
        if is_beat:
            try:
                last_s = float(o.get_last_s())
            
            except Exception:
                last_s = float(total_frames) / float(samplerate)
            
            beats.append(round(last_s, 6))

        if read < hop_size:
            break

    duration = float(total_frames) / float(samplerate) if samplerate else 0.0
    bpm = None

    if len(beats) >= 2:
        intervals = np.diff(np.array(beats, dtype=float))

        intervals = intervals[(intervals > 0.08) & (intervals < 10.0)]
        
        if intervals.size > 0:
            instantaneous_bpms = 60.0 / intervals
            bpm_est = float(np.median(instantaneous_bpms))
            
            if math.isfinite(bpm_est) and bpm_est > 0:
                bpm = round(bpm_est, 2)
    
    else:
        if duration > 0 and len(beats) > 0:
            bpm_est = 60.0 * float(len(beats)) / duration
            
            if math.isfinite(bpm_est) and bpm_est > 0:
                bpm = round(bpm_est, 2)

    return bpm, beats

def load_audio(path, sr = 44100, mono = True):
    audio = AudioSegment.from_file(path)

    if audio.frame_rate != sr:
        audio = audio.set_frame_rate(sr)

    if mono and audio.channels > 1:
        audio = audio.set_channels(1)

    samples = np.array(audio.get_array_of_samples())
    y = samples.astype(np.float32) / 32768.0  

    return y, sr