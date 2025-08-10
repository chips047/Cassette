import librosa
import numpy as np

from PyQt5.QtCore import *

from System import Utils
from System.Constants import *

def snap_beats_to_onsets(bpm_times, onset_times, onset_strengths, should_interrupt=lambda: False):
    snapped = []
    onset_times = np.array(onset_times)
    onset_strengths = np.array(onset_strengths)

    for t in bpm_times:
        if should_interrupt():
            break

        mask = np.abs(onset_times - t) <= BEAT_MAX_DISTANCE
        candidates = onset_times[mask]
        candidates_strength = onset_strengths[mask]

        if len(candidates) == 0:
            continue

        max_idx = np.argmax(candidates_strength)
        best_time = candidates[max_idx]
        best_strength = candidates_strength[max_idx]

        if best_strength >= STRENGTH_THRESHOLD:
            snapped.append(best_time)

    return np.array(snapped)

def analyze_bpm_and_beat_grid(audio_path, sr=44100, hop_length=256, min_consistent_beats=7, tolerance=0.07, should_interrupt=lambda: False):
    if should_interrupt():
        return 0, 0, []

    y, sr = librosa.load(audio_path, sr=sr)
    if should_interrupt():
        return 0, 0, []

    duration = librosa.get_duration(y=y, sr=sr)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=hop_length)
    tempo *= 2
    beat_interval = 60.0 / tempo

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length, backtrack=True)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)
    onset_strengths = onset_env[onset_frames]

    if should_interrupt():
        return 0, 0, []

    if len(onset_times) < min_consistent_beats + 1:
        return 1, 0, []

    intervals = np.diff(onset_times)
    smoothed_intervals = Utils.medfilt_np(intervals, 5)
    target_interval = beat_interval
    mask = np.abs(smoothed_intervals - target_interval) < (target_interval * tolerance)

    count = 0
    start_idx = None
    for i, match in enumerate(mask):
        if should_interrupt():
            return 0, 0, []
        if match:
            count += 1
            if count >= min_consistent_beats:
                start_idx = i - count + 1
                break
        else:
            count = 0

    first_strong_beat_time = onset_times[start_idx] if start_idx is not None else onset_times[0]
    num_beats_back = int(first_strong_beat_time / beat_interval)
    pseudo_first_beat = first_strong_beat_time - num_beats_back * beat_interval

    bpm_grid = np.arange(pseudo_first_beat, duration, beat_interval)
    if should_interrupt():
        return 0, 0, []

    snapped_beats = snap_beats_to_onsets(bpm_grid, onset_times, onset_strengths, should_interrupt)

    return tempo / 2, pseudo_first_beat, list(snapped_beats)

class BPMWorker(QThread):
    bpm_ready = pyqtSignal(float, float, list)
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
    
    def run(self):
        def should_interrupt():
            return self.isInterruptionRequested()
    
        bpm, first_beat_offset_sec, snapped_times = analyze_bpm_and_beat_grid(
            self.file_path,
            should_interrupt=should_interrupt
        )
    
        if not self.isInterruptionRequested():
            self.bpm_ready.emit(bpm, first_beat_offset_sec, snapped_times)
    
    def stop_bpm_worker(self):
        if self.bpm_worker and self.bpm_worker.isRunning():
            self.bpm_worker.requestInterruption()
            self.bpm_worker.quit()
            self.bpm_worker.wait()