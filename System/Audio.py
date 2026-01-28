import av
import math
import aubio
import soundfile
import tempfile

import numpy as np

from PyQt5.QtCore import *
from loguru import logger

class NoAudioStreams(Exception):
    pass

def ensure_wav(path):
    if path.lower().endswith(".wav"):
        return path

    tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp_file.name
    tmp_file.close()

    input_container = av.open(path)
        
    if not input_container.streams.audio:
        raise NoAudioStreams()

    in_stream = input_container.streams.audio[0]
    output_container = av.open(tmp_path, mode='w', format='wav')
    
    out_stream = output_container.add_stream('pcm_s16le', rate=in_stream.rate)
    out_stream.layout = in_stream.layout
    
    resampler = av.AudioResampler(
        format='s16', 
        layout=in_stream.layout, 
        rate=in_stream.rate
    )
    
    for packet in input_container.demux(in_stream):
        for frame in packet.decode():
            resampled_frames = resampler.resample(frame)
            
            for resampled_frame in resampled_frames:
                for out_packet in out_stream.encode(resampled_frame):
                    output_container.mux(out_packet)

    for out_packet in out_stream.encode():
        output_container.mux(out_packet)
    
    if input_container:
        input_container.close()
    
    if output_container:
        output_container.close()

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
    file_path = ensure_wav(path)
    data, fs = soundfile.read(file_path, dtype='float32')

    return data, fs