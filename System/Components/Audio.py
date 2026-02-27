import av
import time
import aubio
import tempfile
import soundfile

import numpy as np

from loguru import logger

class NoAudioStreams(Exception):
    pass

class PermissionError(Exception):
    pass

class CorruptedFileError(Exception):
    pass

def ensure_wav(path):
    try:
        input_container = av.open(path)

        if input_container.format.name == 'wav' and path.lower().endswith(".wav"):
            logger.warning("Audio is WAV. Not converting.")

            input_container.close()
            return path

        logger.warning("Audio is not WAV. Starting conversion...")

        tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp_file.name
        tmp_file.close()

        if not input_container.streams.audio:
            raise NoAudioStreams()

        in_stream = input_container.streams.audio[0]
        output_container = av.open(tmp_path, mode='w', format='wav')

        out_stream = output_container.add_stream('pcm_s16le', rate=in_stream.rate)
        out_stream.layout = in_stream.layout

        resampler = av.AudioResampler(
            format = 's16', 
            layout = in_stream.layout, 
            rate = in_stream.rate
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

    except av.PermissionError:
        raise PermissionError("Permission error while accessing the file. Please check if the file is open in another application.")

    except av.InvalidDataError:
        raise CorruptedFileError("The audio file is corrupted or in an unsupported format.")
    
    except av.FileNotFoundError:
        raise FileNotFoundError("The specified audio file was not found.")

def analyze_bpm_and_beats(
        audio_path,
        hop_size = 512,
        win_s = 1024
    ):

    try:
        s = aubio.source(audio_path, 0, hop_size)
    
    except Exception:
        return 0, []

    samplerate = s.samplerate or 44100
    o = aubio.tempo("default", win_s, hop_size, samplerate)
    o.set_silence(-40)

    beats = []
    total_frames = 0
    
    count = 0

    while True:
        samples, read = s()
        total_frames += read
        
        if o(samples):
            beats.append(o.get_last_s())

        if read < hop_size:
            break
        
        count += 1
        if count % 150 == 0:
            time.sleep(0.0001) 

    bpm = 0

    if len(beats) >= 2:
        beats_array = np.array(beats, dtype=np.float32)
        intervals = np.diff(beats_array)
        intervals = intervals[(intervals > 0.08) & (intervals < 10.0)]
        
        if intervals.size > 0:
            bpm = round(float(np.median(60.0 / intervals)), 2)
    
    formatted_beats = [round(float(b), 3) for b in beats]
    
    return bpm, formatted_beats

def load_audio(path):
    try:
        data, fs = soundfile.read(path, dtype='float32')
        
        return data, fs

    except soundfile.LibsndfileError:
        raise CorruptedFileError("The audio file is corrupted or in an unsupported format.")