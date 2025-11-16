import os
import copy
import json
import random
import shutil
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

class SyncedDict(dict):
    def __init__(self, *args, sync_callback, composition, **kwargs):
        super().__init__(*args, **kwargs)
        self.composition = composition
        self._sync_callback = sync_callback

    def __setitem__(self, key, value):
        if "effect" in value:
            if value["effect"]["name"] != "None":
                self.composition.cached_effects[str(key)] = GlyphEffects.effect_to_glyph(
                    value, self.composition.bpm, self.composition.model
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
                    self.composition.cached_effects[str(id)] = GlyphEffects.effect_to_glyph(glyph, self.composition.bpm, self.composition.model)

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
        self.sampling_rate = self.audio_settings.get("sampling_rate")
        self.start_ms = self.audio_settings.get("start_ms")
        self.end_ms = self.audio_settings.get("end_ms")
        self.fade_in_duration = self.audio_settings.get("fade_in", 0)
        self.fade_out_duration = self.audio_settings.get("fade_out", 0)
        self.beats = self.audio_settings.get("beats", [])

        self.glyphs = settings.get("glyphs", {})

        self.cropped_song_path = Utils.get_songs_path(f"{self.id}/cropped_song.ogg")
        self.full_song_path = Utils.get_songs_path(f"{self.id}/full_song.ogg")

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

    def prepare_cropped_audio(self, audio_path: str | None = None):
        print(f"loaded {audio_path}")
        full_song = AudioSegment.from_file(audio_path)
        audio = full_song[self.start_ms:self.end_ms]

        self.export_segment(
            audio,
            self.cropped_song_path,
            self.fade_in_duration,
            self.fade_out_duration
        )

    def export(self, model: str | None = None, open_folder: bool = False):
        if model != self.model and model:
            ported_glyphs = Porter.Port.port_glyphs(model, self)
            Exporter.glyphs_to_ogg(
                Utils.get_songs_path(f"{self.id}/cropped_song.ogg"),
                Utils.get_songs_path(f"{self.id}/Composed_{model}.ogg"),
                ported_glyphs,
                model
            )
        
        else:
            singles, effects = self.sorted_glyphs()
    
            for effect in effects:
                singles.extend(GlyphEffects.effect_to_glyph(effect, self.bpm, self.model))
            
            Exporter.glyphs_to_ogg(
                self.cropped_song_path,
                Utils.get_songs_path(f"{self.id}/Composed.ogg"),
                singles,
                self.model
            )
        
        if open_folder:
            Utils.open_file(os.path.abspath(Utils.get_songs_path(str(self.id))))
            Utils.ui_sound("Export")
    
    def export_all(self):
        Utils.ui_sound("ExportLong")

        self.export()
        for model in PortVariants[self.model]:
            print("model ", model)
            self.export(number_model_to_code(model))
        
        Utils.open_file(os.path.abspath(Utils.get_songs_path(str(self.id))))

class Composition(BaseComposition):
    def __init__(self, audiofile_path: str | None = None, settings: dict = {}, id: int | None = None):
        if id:
            settings = json.load(open(Utils.get_songs_path(f"{id}/Save.json"), "r", encoding="utf-8"))
        
        super().__init__(id, settings)

        self.version = open("version").read()
        self.save_version = settings.get("version", self.version)

        self.song_path = audiofile_path

        self.brightness = DEFAULT_BRIGHTNESS
        self.duration_ms = DEFAULT_DURATION
        self.default_effect = "None"
        self.track_number = ModelTracks[self.model]

        self.syncer = RTVisualizer.GlyphSyncer(self)

        self.glyphs = SyncedDict(settings.get("glyphs", {}), sync_callback=self.syncer.sync, composition=self)
        self.cached_effects = {}
        self.last_glyph_id = max(map(int, self.glyphs.keys())) if self.glyphs else 0

        if CurrentSettings["auto_search"]:
            self.syncer.start_scanning_loop()

        for gid, glyph in self.glyphs.items():
            if "effect" in glyph:
                self.cached_effects[gid] = GlyphEffects.effect_to_glyph(glyph, self.bpm, self.model)

        self.syncer.full_load(self.glyphs)
        os.makedirs(Utils.get_songs_path(str(self.id)), exist_ok=True)

        if audiofile_path:
            shutil.copyfile(audiofile_path, self.full_song_path)

        if not os.path.exists(self.cropped_song_path):
            self.prepare_cropped_audio(self.full_song_path)

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
            title, author = get_metadata(self.full_song_path)
            title = title or os.path.basename(self.song_path)
            author = author or "Unknown Artist"

            dict_data = {
                "audio": {
                    "title": title,
                    "artist": author,
                    "start_ms": self.start_ms,
                    "end_ms": self.end_ms,
                    "sampling_rate": self.sampling_rate,
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

        self.cropped_song_path = Utils.get_songs_path(f"{id}/cropped_song.ogg")
        self.full_song_path = Utils.get_songs_path(f"{id}/full_song.ogg")

        super().__init__(id, settings)

        if not os.path.exists(self.cropped_song_path):
            if not os.path.exists(self.full_song_path):
                error = UI.ErrorWindow("Corrupted!", "This save is corrupted.")
                error.exec_()
                return

            self.prepare_cropped_audio(self.full_song_path)