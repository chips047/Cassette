import os
import copy
import json
import random
import subprocess

import numpy as np
from pydub import AudioSegment

from System import UI
from System import Porter
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
            print(value["effect"]["name"])
            if value["effect"]["name"] != "None":
                self.composition.cached_effects[str(key)] = GlyphEffects.effect_to_glyph(
                    value, self.composition.model, self.composition.bpm
                )
            
            else:
                self.composition.cached_effects.pop(str(key), None)

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
                    self.composition.cached_effects[str(id)] = GlyphEffects.effect_to_glyph(glyph, self.composition.model, self.composition.bpm)

            super().update(glyphs, *args[1:], **kwargs)
        
        else:
            super().update(*args, **kwargs)

        self._sync_callback(self)
        self.composition.save()

class BaseComposition:
    def __init__(self, id: int, settings: dict):
        self.id = id if id is not None else random.randint(10000000, 99999999)
        self.model = settings.get("model")
        self.audio_settings = settings.get("audio", {})

        self.bpm = self.audio_settings.get("bpm")
        self.audio_duration = self.audio_settings.get("duration")
        self.sampling_rate = self.audio_settings.get("sampling_rate")
        self.start_sample = self.audio_settings.get("start_sample")
        self.end_sample = self.audio_settings.get("end_sample")
        self.fade_in_duration = self.audio_settings.get("fade_in", 0)
        self.fade_out_duration = self.audio_settings.get("fade_out", 0)
        self.beats = self.audio_settings.get("beats", [])

        self.glyphs = settings.get("glyphs", {})

        self.cropped_audiofile_path = Utils.get_songs_path(f"{self.id}/cropped_song.ogg")
        self.full_audiofile_path = Utils.get_songs_path(f"{self.id}/full_song.ogg")

    def export_segment(self, segment, path, fade_in = 0, fade_out = 0):
        segment = segment.normalize()

        if fade_in:
            segment = segment.fade_in(fade_in)

        if fade_out:
            segment = segment.fade_out(fade_out)

        tmp = path.replace(".ogg", ".opus")
        segment.export(tmp, format="opus")

        os.replace(tmp, path)

    def sorted_glyphs(self) -> tuple:
        singles, effects = [], []

        for glyph in self.glyphs.values():
            if "effect" in glyph:
                effects.append(copy.deepcopy(glyph))
            
            else:
                singles.append(copy.deepcopy(glyph))

        return singles, effects

    def prepare_cropped_audio(self, audio_path: str | None = None, audio_data = None):
        os.makedirs(Utils.get_songs_path(str(self.id)), exist_ok=True)

        if audio_data is not None:
            segment = audio_data[self.start_sample:self.end_sample]
            audio = audiosegment_from_numpy(segment, self.sampling_rate)
        
        else:
            full_song = AudioSegment.from_file(audio_path or self.full_audiofile_path)
            audio = full_song[self.start_sample:self.end_sample]

        self.export_segment(
            audio,
            self.cropped_audiofile_path,
            self.fade_in_duration,
            self.fade_out_duration
        )

    def export(self, out_path: str | None = None):
        singles, effects = self.sorted_glyphs()
        temp_glyphs = singles

        for effect in effects:
            temp_glyphs.extend(GlyphEffects.effect_to_glyph(effect, self.model, self.bpm))

        print(temp_glyphs)

        Exporter.glyphs_to_ogg(self.cropped_audiofile_path, out_path or Utils.get_songs_path(f"{self.id}/Composed.ogg"), temp_glyphs, self.model)
        Utils.open_file(os.path.abspath(Utils.get_songs_path(str(self.id))))
    
    def export_port(self, port_to: str):
        ported_glyphs = Porter.Port.port_glyphs(port_to, self)
        Exporter.glyphs_to_ogg(Utils.get_songs_path(f"{self.id}/cropped_song.ogg"), Utils.get_songs_path(f"{self.id}/Composed_{port_to}.ogg"), ported_glyphs, port_to)

        Utils.ui_sound("Export")

class Composition(BaseComposition):
    def __init__(self, audiofile_path: str | None = None, settings: dict = {}, id: int | None = None):
        if id:
            settings = json.load(open(Utils.get_songs_path(f"{id}/Save.json"), "r", encoding="utf-8"))
        
        super().__init__(id, settings)

        self.version = open("version").read()
        self.track_number = ModelTracks.get(self.model)
        self.audiofile_path = audiofile_path
        self.audio_data = self.audio_settings.get("audio_data")

        self.brightness = 100
        self.duration_ms = 100
        self.default_effect = "None"

        self.syncer = RTVisualizer.GlyphSyncer(self)

        self.glyphs = SyncedDict(settings.get("glyphs", {}), sync_callback=self.syncer.sync, composition=self)
        self.cached_effects = {}
        self.last_glyph_id = max(map(int, self.glyphs.keys())) if self.glyphs else 0
        self.syncer.start_scanning_loop()

        for gid, glyph in self.glyphs.items():
            if "effect" in glyph:
                self.cached_effects[gid] = GlyphEffects.effect_to_glyph(glyph, self.model, self.bpm)

        self.syncer.full_load(self.glyphs)

        if not os.path.exists(self.cropped_audiofile_path):
            if settings:
                self.prepare_cropped_audio(self.audiofile_path, self.audio_data)
            
            else:
                self.prepare_cropped_audio(self.audiofile_path)

    def new_glyph(self, track, start, duration=None, brightness=None):
        self.last_glyph_id += 1
        glyph = {
            "track": track,
            "start": start,
            "duration": duration or self.duration_ms,
            "brightness": brightness or self.brightness
        }

        if self.default_effect != "None":
            glyph["effect"] = {"name": self.default_effect, "settings": {"segmented": False}}

        self.glyphs[self.last_glyph_id] = glyph
        return self.last_glyph_id, glyph

    def get_glyph(self, glyph_id: int):
        return self.glyphs.get(glyph_id, "NOT FOUND")

    def copy_glyph(self, glyph: dict, offset: int = 0) -> int:
        new_glyph = glyph.copy()
        new_glyph["start"] = max(0, new_glyph["start"] + offset)

        self.last_glyph_id += 1
        new_id = self.last_glyph_id

        self.glyphs[new_id] = new_glyph
        return new_id

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
            title, author = get_metadata(self.full_audiofile_path)
            title = title or os.path.basename(self.audiofile_path)
            author = author or "Unknown Artist"

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

            dict_data["audio"].update({"title": title, "artist": author})

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
    
    def all_glyphs(self):
        return self.glyphs

class MinimalComposition(BaseComposition):
    def __init__(self, id: int):
        settings = json.load(open(Utils.get_songs_path(f"{id}/Save.json"), "r", encoding="utf-8"))
        super().__init__(id, settings)

        if not os.path.exists(self.cropped_audiofile_path):
            if not os.path.exists(self.full_audiofile_path):
                error = UI.ErrorWindow("Corrupted!", "This save is corrupted.")
                error.exec_()
                return

            self.prepare_cropped_audio(self.full_audiofile_path, settings.get("audio_data") if settings else None)