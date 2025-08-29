import aubio
import tempfile

import numpy as np
import multiprocessing as mp

from PyQt5.QtCore import *
from pydub import AudioSegment

from System import Utils
from System.Constants import *

def ensure_wav(path):
    if path.lower().endswith(".wav"):
        return path

    tmp_path = tempfile.mktemp(suffix=".wav")
    audio = AudioSegment.from_file(path)
    audio.export(tmp_path, format="wav", parameters=["-acodec", "pcm_s16le"])
    
    return tmp_path

def analyze_bpm_and_beat_grid(audio_path, hop_size=256, should_interrupt=lambda: False):
    if should_interrupt():
        return 0, 0, []

    wav_path = ensure_wav(audio_path)
    
    try:
        s = aubio.source(wav_path, 0, hop_size)
        samplerate = s.samplerate
    
    except Exception as e:
        print(f"Error opening audio file: {e}")
        return 0, 0, []

    onset_detector = aubio.onset("hfc", 1024, hop_size, samplerate)
    tempo_detector = aubio.tempo("default", 1024, hop_size, samplerate)

    onset_times, onset_strengths, tempo_estimates = [], [], []
    
    while True:
        if should_interrupt():
            return 0, 0, []

        samples, read = s()
        if read == 0:
            break

        if onset_detector(samples):
            onset_times.append(onset_detector.get_last_s())
            onset_strengths.append(onset_detector.get_last())

        if tempo_detector(samples):
            tempo_estimates.append(tempo_detector.get_bpm())

        if read < hop_size:
            break
            
    if not tempo_estimates or not onset_times:
        return 0, 0, []

    median_tempo_aubio = np.median(tempo_estimates)
    intervals = np.diff(onset_times)
    
    if len(intervals) == 0:
        return 0, 0, []

    hist, bins = np.histogram(intervals, bins=50)
    most_frequent_interval_idx = np.argmax(hist)
    most_frequent_interval = (bins[most_frequent_interval_idx] + bins[most_frequent_interval_idx+1]) / 2
    tempo_from_intervals = 60.0 / most_frequent_interval if most_frequent_interval > 0 else 0
    
    possible_tempos = [
        median_tempo_aubio,
        median_tempo_aubio * 0.5,
        median_tempo_aubio * 2,
        tempo_from_intervals,
        tempo_from_intervals * 0.5,
        tempo_from_intervals * 2
    ]
    
    def score_tempo(test_tempo):
        if test_tempo <= 0:
            return -1
        beat_interval = 60.0 / test_tempo
        score = np.sum(np.abs(intervals - beat_interval) < (beat_interval * 0.05))
        score += np.sum(np.abs(intervals - beat_interval * 2) < (beat_interval * 2 * 0.05))
        score += np.sum(np.abs(intervals - beat_interval / 2) < (beat_interval / 2 * 0.05))
        if 80 <= test_tempo <= 140:
            score *= 1.2
        
        return score
    
    valid_tempos = [t for t in possible_tempos if 60 <= t <= 180]
    best_tempo = max(valid_tempos, key=score_tempo, default=0)

    half_tempo = best_tempo / 2
    if 60 <= half_tempo <= 160 and score_tempo(half_tempo) > score_tempo(best_tempo) * 0.8:
        best_tempo = half_tempo

    scores = {
        best_tempo: score_tempo(best_tempo),
        best_tempo / 2: score_tempo(best_tempo / 2),
        best_tempo * 2: score_tempo(best_tempo * 2)
    }
    
    best_tempo = max(scores, key=lambda t: scores[t] if 60 <= t <= 160 else -1)

    if best_tempo == 0:
        return 0, 0, []

    strongest_onset_time = onset_times[np.argmax(onset_strengths)]
    beat_interval = 60.0 / best_tempo

    num_beats_back = int(strongest_onset_time / beat_interval)
    pseudo_first_beat = strongest_onset_time - num_beats_back * beat_interval
    
    if pseudo_first_beat < 0:
        pseudo_first_beat += beat_interval
    
    return best_tempo, pseudo_first_beat, list(onset_times)

def bpm_task(file_path, queue):
    bpm, first_beat, beats = analyze_bpm_and_beat_grid(file_path)
    queue.put((bpm, first_beat, beats))

def intro_generator(file_path, out_path, hop_s = 512):
    file_path = ensure_wav(file_path)
    
    source = aubio.source(file_path, 0, hop_s)
    samplerate = source.samplerate
    
    rms_list = []
    times = []

    total_frames = 0
    while True:
        samples, read = source()
        value = np.sqrt(np.mean(samples**2))
        rms_list.append(value)
        times.append(total_frames / float(samplerate))

        total_frames += read
        if read < hop_s:
            break

    rms_arr = np.array(rms_list)

    window_size = int(3 * samplerate / hop_s)
    energy_sum = np.convolve(rms_arr, np.ones(window_size), mode='valid')

    best_idx = np.argmax(energy_sum)
    start_time = times[best_idx]
    end_time = start_time + 3
    
    audio = AudioSegment.from_file(file_path)
    start_ms = int(start_time * 1000)
    end_ms = int(end_time * 1000)
    fragment = audio[start_ms:end_ms]
    fragment = fragment.fade_out(2000)
    
    fragment.export(out_path, format = "mp3")

class BPMWorkerProcess(QObject):
    bpm_ready = pyqtSignal(float, float, list)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.proc = None
        self.queue = mp.Queue()

    def start(self):
        if self.proc and self.proc.is_alive():
            return

        self.proc = mp.Process(target=bpm_task, args=(self.file_path, self.queue))
        self.proc.start()

        self.timer = QTimer()
        self.timer.timeout.connect(self._check_result)
        self.timer.start(100)

    def _check_result(self):
        if not self.queue.empty():
            bpm, first_beat, beats = self.queue.get()
            self.bpm_ready.emit(bpm, first_beat, beats)
            self.stop()

    def stop(self):
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()

        if self.proc and self.proc.is_alive():
            self.proc.terminate()
            self.proc.join()
        
        self.proc = None

def load_audio(path, sr = 44100, mono = True):
    audio = AudioSegment.from_file(path)

    if audio.frame_rate != sr:
        audio = audio.set_frame_rate(sr)

    if mono and audio.channels > 1:
        audio = audio.set_channels(1)

    samples = np.array(audio.get_array_of_samples())
    y = samples.astype(np.float32) / 32768.0  

    return y, sr