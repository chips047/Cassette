import os
import json
import random
import shutil
import subprocess

import numpy as np
from pydub import AudioSegment

from System import UI
from System import Exporter
from System import GlyphEffects
from System import RTVisualizer

from System.Constants import *
from System import Utils

def get_metadata(file_path):
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    metadata = json.loads(result.stdout)
    
    tags = metadata.get("format", {}).get("tags", {})
    title = tags.get("title")
    artist = tags.get("artist", "Unknown Artist")
    
    return title, artist

def audiosegment_from_numpy(np_array, sample_rate):
    if np_array.ndim == 2:
        interleaved = (np_array.T * 32767).astype(np.int16).flatten()
        channels = np_array.shape[0]
    
    else:
        interleaved = (np_array * 32767).astype(np.int16)
        channels = 1

    return AudioSegment(
        interleaved.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=channels
    )

class SyncedDict(dict):
    def __init__(self, *args, sync_callback, composition, **kwargs):
        super().__init__(*args, **kwargs)
        self.composition = composition
        self._sync_callback = sync_callback

    def __setitem__(self, key, value):
        if "effect" in value:
            self.composition.cached_effects[str(key)] = GlyphEffects.effect_to_glyph(
                value, value["effect"], self.composition.model, self.composition.bpm
            )

        super().__setitem__(key, value)
        self._sync_callback(self)
        self.composition.save()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._sync_callback(self)
        self.composition.save()
    
    def delete_keys(self, keys):
        for key in keys:
            super().__delitem__(key)
        
        self._sync_callback(self)
        self.composition.save()

    def update(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            glyphs = args[0]

            for id, glyph in glyphs.items():
                if "effect" in glyph:
                    self.composition.cached_effects[str(id)] = GlyphEffects.effect_to_glyph(glyph, glyph["effect"], self.composition.model, self.composition.bpm)

            super().update(glyphs, *args[1:], **kwargs)
        
        else:
            super().update(*args, **kwargs)

        self._sync_callback(self)
        self.composition.save()

class Composition:
    def __init__(self, audiofile_path = None, settings = {}, id = None):
        self.id = id if id is not None else random.randint(10000000, 99999999)
        
        if id:
            settings = json.load(open(Utils.get_songs_path(f"{self.id}/Save.json"), "r", encoding="utf-8"))
            
        self.version = open("version").read()
        self.model = settings.get("model")
        self.track_number = ModelTracks.get(self.model)
        
        if "audio" not in settings:
            ... # Your composition was created with old Cassette version.
        
        self.audio_settings = settings["audio"]
        self.bpm = self.audio_settings["bpm"]
        self.beats = self.audio_settings["beats"] or []
        
        self.sampling_rate = self.audio_settings["sampling_rate"]
        
        self.audio_duration = self.audio_settings["duration"]
        self.fade_in_duration = self.audio_settings["fade_in"]
        self.fade_out_duration = self.audio_settings["fade_out"]

        self.start_sample = self.audio_settings["start_sample"]
        self.end_sample = self.audio_settings["end_sample"]
        self.audio_data = self.audio_settings.get("audio_data")
        self.audiofile_path = audiofile_path
        self.cropped_audiofile_path = Utils.get_songs_path(f"{self.id}/cropped_song.ogg")
        
        # Defaults
        self.brightness = 100
        self.duration_ms = 100
        self.default_effect = "None"
        
        # Syncer (Real Time Visualization)
        self.syncer = RTVisualizer.GlyphSyncer(self)
        
        # Glyph Management
        self.glyphs = SyncedDict(settings.get("glyphs", {}), sync_callback=self.syncer.sync, composition=self)
        self.cached_effects = {}
        self.last_glyph_id = max(map(int, self.glyphs.keys())) if self.glyphs else 0
        self.syncer.start_scanning_loop()
        
        for id, glyph in self.glyphs.items():
            if "effect" in glyph:
                self.cached_effects[id] = GlyphEffects.effect_to_glyph(glyph, glyph["effect"], self.model, self.bpm)

        # if settings != None, then its a new composition
        self.syncer.full_load(self.glyphs)

        if not os.path.exists(Utils.get_songs_path(f"{self.id}/cropped_song.ogg")):
            if settings != {}:
                self.prepare_cropped_audio(self.audiofile_path, settings)
            
            else:
                self.prepare_cropped_audio(self.audiofile_path)

    def prepare_cropped_audio(self, audio_path, settings = None):
        os.makedirs(Utils.get_songs_path(str(self.id)), exist_ok = True)
        
        if settings:
            shutil.copy(audio_path, Utils.get_songs_path(f"{self.id}/full_song.ogg"))
            segment = self.audio_data[self.start_sample:self.end_sample]
            
            audio = audiosegment_from_numpy(segment, self.sampling_rate)
            audio = audio.normalize()
            
            if self.fade_in_duration:
                audio = audio.fade_in(self.fade_in_duration)
            
            if self.fade_out_duration:
                audio = audio.fade_out(self.fade_out_duration)
            
            audio.export(Utils.get_songs_path(f"{self.id}/cropped_song.opus"), format='opus')
            os.rename(Utils.get_songs_path(f"{self.id}/cropped_song.opus"), Utils.get_songs_path(f"{self.id}/cropped_song.ogg"))
        
        else:
            full_song = AudioSegment.from_file(Utils.get_songs_path(f"{self.id}/full_song.ogg"))

            segment = full_song[self.start_sample:self.end_sample]
            segment = segment.normalize()
            
            if self.fade_in_duration:
                segment = segment.fade_in(self.fade_in_duration)
            
            if self.fade_out_duration:
                segment = segment.fade_out(self.fade_out_duration)
            
            segment.export(Utils.get_songs_path(f"{self.id}/cropped_song.opus"), format='opus')
                
            os.rename(Utils.get_songs_path(f"{self.id}/cropped_song.opus"), Utils.get_songs_path(f"{self.id}/cropped_song.ogg"))

    def export(self, out_path = None):
        Exporter.export_ringtone(out_path or Utils.get_songs_path(str(self.id)), self)
        Utils.open_file(os.path.abspath(Utils.get_songs_path(str(self.id))))

    def new_glyph(self, track, start, duration = None, brightness = None):
        self.last_glyph_id += 1
        glyph = {
            "track": track,
            "start": start,
            "duration": duration or self.duration_ms,
            "brightness": brightness or self.brightness
        }
        
        if self.default_effect != "None":
            glyph["effect"] = {
                "name": self.default_effect,
                "settings": {"segmented": False}
            }
        
        self.glyphs[self.last_glyph_id] = glyph
        return self.last_glyph_id, glyph

    def all_glyphs(self):
        return self.glyphs

    def get_glyph(self, glyph_id: int):
        return self.glyphs.get(glyph_id, "NOT FOUND")
    
    def copy_glyph(self, glyph: dict, offset: int = 0) -> int:
        new_glyph = glyph.copy()
        new_glyph["start"] = max(0, new_glyph["start"] + offset)

        self.last_glyph_id += 1
        new_id = self.last_glyph_id

        self.glyphs[new_id] = new_glyph
        return new_id
    
    def sorted_glyphs(self) -> tuple:
        glyphs = self.glyphs.values()

        only_singles_and_segments = []
        only_effects = []

        for glyph in glyphs:
            if "effect" in glyph:
                only_effects.append(glyph)

            else:
                only_singles_and_segments.append(glyph)

        return only_singles_and_segments, only_effects
    
    def save(self):
        save_path = Utils.get_songs_path(f"{self.id}/Save.json")
        os.makedirs(Utils.get_songs_path(str(self.id)), exist_ok=True)

        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            data["glyphs"] = self.glyphs
            
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        
        else:
            title, author = get_metadata(Utils.get_songs_path(f"{self.id}/full_song.ogg"))
            dict_data = {
                "audio": {
                    "title": title or self.audiofile_path.split("/")[-1],
                    "artist": author,
                    "start_sample": self.start_sample,
                    "end_sample": self.end_sample,
                    "sampling_rate": self.sampling_rate,
                    "duration": self.audio_duration,
                    "bpm": self.bpm,
                    "beats": self.beats,
                    "fade_in": self.fade_in_duration,
                    "fade_out": self.fade_out_duration
                },
                "progress": 0,
                "model": self.model,
                "version": self.version,
                "glyphs": self.glyphs
            }
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(dict_data, f, ensure_ascii=False, indent=4)
    
    def update_bunch_of_glyphs(self, data: dict):
        self.glyphs.update(data)
    
    def replace_glyph(self, id, data: dict):
        self.glyphs[id] = data
    
    def delete_glyph(self, id):
        del self.glyphs[id]
    
    def delete_glyphs(self, keys):
        self.glyphs.delete_keys(keys)
    
    def set_brightness(self, brightness):
        self.brightness = brightness
    
    def set_duration(self, duration):
        self.duration_ms = duration
    
    def set_default_effect(self, effect_name):
        self.default_effect = effect_name

class MinimalComposition:
    def __init__(self, id):
        self.id = id if id is not None else random.randint(10000000, 99999999)
        settings = json.load(open(Utils.get_songs_path(f"{self.id}/Save.json"), "r", encoding="utf-8"))
            
        self.model = settings.get("model")        
        self.audio_settings = settings["audio"]
        self.audio_duration = self.audio_settings["duration"]
        self.bpm = self.audio_settings["bpm"]
        self.audio_duration = self.audio_settings["duration"]

        self.glyphs = settings["glyphs"]

        self.cropped_audiofile_path = Utils.get_songs_path(f"{self.id}/cropped_song.ogg")
        
        if not os.path.exists(Utils.get_songs_path(f"{self.id}/cropped_song.ogg")):
            if not os.path.exists(Utils.get_songs_path(f"{self.id}/full_song.ogg")):
                error = UI.ErrorWindow("Corrupted!", "This save is corrupted.")
                return error.exec_()

            if settings != {}:
                self.prepare_cropped_audio(self.audiofile_path, settings)
            
            else:
                self.prepare_cropped_audio(self.audiofile_path)

    def sorted_glyphs(self) -> tuple:
        glyphs = self.glyphs.values()

        only_singles_and_segments = []
        only_effects = []

        for glyph in glyphs:
            if "effect" in glyph:
                only_effects.append(glyph)

            else:
                only_singles_and_segments.append(glyph)

        return only_singles_and_segments, only_effects

    def prepare_cropped_audio(self, settings = None):
        os.makedirs(Utils.get_songs_path(str(self.id)), exist_ok = True)
        
        if settings:
            segment = self.audio_data[self.start_sample:self.end_sample]
            
            audio = audiosegment_from_numpy(segment, self.sampling_rate)
            audio = audio.normalize()
            
            if self.fade_in_duration:
                audio = audio.fade_in(self.fade_in_duration)
            
            if self.fade_out_duration:
                audio = audio.fade_out(self.fade_out_duration)
            
            audio.export(Utils.get_songs_path(f"{self.id}/cropped_song.opus"), format='opus')
            os.rename(Utils.get_songs_path(f"{self.id}/cropped_song.opus"), Utils.get_songs_path(f"{self.id}/cropped_song.ogg"))
        
        else:
            full_song = AudioSegment.from_file(Utils.get_songs_path(f"{self.id}/full_song.ogg"))

            segment = full_song[self.start_sample:self.end_sample]
            segment = segment.normalize()
            
            if self.fade_in_duration:
                segment = segment.fade_in(self.fade_in_duration)
            
            if self.fade_out_duration:
                segment = segment.fade_out(self.fade_out_duration)
            
            segment.export(Utils.get_songs_path(f"{self.id}/cropped_song.opus"), format='opus')
            os.rename(Utils.get_songs_path(f"{self.id}/cropped_song.opus"), Utils.get_songs_path(f"{self.id}/cropped_song.ogg"))

    def export(self, out_path = None):
        Exporter.export_ringtone(out_path or Utils.get_songs_path(str(self.id)), self)
        Utils.open_file(os.path.abspath(Utils.get_songs_path(str(self.id))))