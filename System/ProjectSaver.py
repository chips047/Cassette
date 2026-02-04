import os
import av
import copy
import json
import random
import shutil
import subprocess

from System import UI
from System import Porter
from System import ExporterImporter
from System import GlyphEffects
from System import RTVisualizer

from System.Constants import *
from System import Utils

import av

def get_metadata(file_path):
    container = av.open(file_path)
    
    title = None
    artist = "Unknown Artist"
    
    if container.metadata:
        title = container.metadata.get('title')
        artist = container.metadata.get('artist', "Unknown Artist")
    
    return title, artist

class SyncedDict(dict):
    def __init__(self, *args, sync_callback, composition, **kwargs):
        super().__init__(*args, **kwargs)
        self.composition = composition
        self._sync_callback = sync_callback
        self._glyph_id_to_track = {}
        
        self.visualizator_data = {}
        self._process_initial_data()
    
    def _process_initial_data(self):
        for glyph_id, glyph_data in self.items():
            track = glyph_data.get("track")
            
            if track:
                self._glyph_id_to_track[glyph_id] = track
        
        for glyph_id, glyph_data in self.items():
            self._process_glyph_effect(glyph_id, glyph_data)
            self._add_glyph_to_visualizator(glyph_id, glyph_data)
    
    def _process_glyph_effect(self, glyph_id, glyph_data):
        if "effect" in glyph_data and glyph_data["effect"]["name"] != "None":
            effect_glyph_data = GlyphEffects.effect_to_glyph(
                glyph_data, 
                self.composition.bpm, 
                self.composition.model
            )
            
            self.composition.cached_effects[str(glyph_id)] = effect_glyph_data
        
        else:
            self.composition.cached_effects.pop(str(glyph_id), None)
    
    def _add_glyph_to_visualizator(self, glyph_id, glyph_data):
        track = glyph_data["track"]
        
        if track not in self.visualizator_data:
            self.visualizator_data[track] = {}
        
        if "effect" not in glyph_data or glyph_data["effect"]["name"] == "None":
            self.visualizator_data[track][glyph_id] = glyph_data
        
        else:
            if str(glyph_id) in self.composition.cached_effects:
                effect_glyphs = self.composition.cached_effects[str(glyph_id)]
                
                #if isinstance(effect_glyphs, list):
                for idx, effect_glyph in enumerate(effect_glyphs):
                    effect_glyph_id = f"effect_{glyph_id}_{idx}"
                    self.visualizator_data[track][effect_glyph_id] = effect_glyph
                #
                #else:
                #    effect_glyph_id = f"effect_{glyph_id}"
                #    self.visualizator_data[track][effect_glyph_id] = effect_glyphs
    
    def _remove_glyph_from_visualizator(self, glyph_id):
        track = self._glyph_id_to_track.get(glyph_id)
        
        if track and track in self.visualizator_data:
            self.visualizator_data[track].pop(glyph_id, None)

            keys_to_remove = [
                k for k in self.visualizator_data[track].keys() 
                if str(k).startswith(f"effect_{glyph_id}")
            ]
            
            for k in keys_to_remove:
                self.visualizator_data[track].pop(k)

            if not self.visualizator_data[track]:
                self.visualizator_data.pop(track, None)
    
    def __setitem__(self, key, value):
        if key in self:
            self._remove_glyph_from_visualizator(key)
        
        self._process_glyph_effect(key, value)
        
        super().__setitem__(key, value)
        
        self._add_glyph_to_visualizator(key, value)
        
        track = value.get("track")
        if track:
            self._glyph_id_to_track[key] = track
        
        self._sync_callback(self)
        self.composition.save()
    
    def __delitem__(self, key):
        self.composition.cached_effects.pop(str(key), None)
        self._remove_glyph_from_visualizator(key)
        
        super().__delitem__(key)
        self._glyph_id_to_track.pop(key, None)
        
        self._sync_callback(self)
        self.composition.save()
    
    def delete_keys(self, keys):
        for key in keys:
            self.composition.cached_effects.pop(str(key), None)
            self._remove_glyph_from_visualizator(key)
                
            super().__delitem__(key)
            self._glyph_id_to_track.pop(key, None)
        
        self._sync_callback(self)
        self.composition.save()
    
    def update(self, *args, **kwargs):
        glyphs_to_update = args[0]
        glyphs_to_update.update(kwargs)
        
        for glyph_id, glyph_data in glyphs_to_update.items():
            if glyph_id in self:
                self._remove_glyph_from_visualizator(glyph_id)
            
            self._process_glyph_effect(glyph_id, glyph_data)
            super().__setitem__(glyph_id, glyph_data)
            self._add_glyph_to_visualizator(glyph_id, glyph_data)
            
            track = glyph_data.get("track")
            
            if track:
                self._glyph_id_to_track[glyph_id] = track
        
        self._sync_callback(self)
        self.composition.save()

class BaseComposition:
    def __init__(self, id: int, settings: dict):
        self.id = id if id is not None else random.randint(10000000, 99999999)
        self.model = settings.get("model")
        self.audio_settings = settings.get("audio", {})

        self.bpm = self.audio_settings.get("bpm")
        self.start_ms = self.audio_settings.get("start_ms")
        self.end_ms = self.audio_settings.get("end_ms")
        self.fade_in_duration = self.audio_settings.get("fade_in", 0)
        self.fade_out_duration = self.audio_settings.get("fade_out", 0)
        self.beats = self.audio_settings.get("beats", [])

        self.glyphs = settings.get("glyphs", {})

        self.cropped_song_path = Utils.get_songs_path(f"{self.id}/cropped_song.ogg")
        self.full_song_path = Utils.get_songs_path(f"{self.id}/full_song.ogg")

    def export_segment(self, input_path, output_path, start_ms, end_ms, fade_in=0, fade_out=0):
        container = av.open(input_path)
        input_stream = container.streams.audio[0]

        start_time = start_ms / 1000.0
        end_time = end_ms / 1000.0
        seek_time = max(0, start_time - 2.0)

        container.seek(int(seek_time / input_stream.time_base), stream=input_stream)

        output_container = av.open(output_path, mode='w', format='opus')
        output_stream = output_container.add_stream('libopus', rate=48000)

        graph = av.filter.Graph()
        buffer = graph.add_abuffer(input_stream)

        trim = graph.add("atrim", f"start={start_time}:end={end_time}")
        reset_ts = graph.add("asetpts", "PTS-STARTPTS")
        norm = graph.add("dynaudnorm")

        buffer.link_to(trim)
        trim.link_to(reset_ts)
        reset_ts.link_to(norm)
        last_link = norm

        duration_sec = (end_ms - start_ms) / 1000

        if fade_in:
            f_in = graph.add("afade", f"type=in:start_time=0:duration={fade_in/1000}")
            last_link.link_to(f_in)
            last_link = f_in

        if fade_out:
            fade_start = max(0, duration_sec - fade_out/1000)
            f_out = graph.add("afade", f"type=out:start_time={fade_start}:duration={fade_out/1000}")
            last_link.link_to(f_out)
            last_link = f_out

        sink = graph.add("abuffersink")
        last_link.link_to(sink)
        graph.configure()

        filter_ended = False

        for frame in container.decode(audio=0):
            if filter_ended:
                break

            if frame.time is not None and frame.time < start_time - 2.0:
                continue
            
            if frame.time is not None and frame.time > end_time + 2.0:
                break
            
            try:
                graph.push(frame)
            
            except av.EOFError:
                filter_ended = True
                break
            
            while True:
                try:
                    filt_frame = graph.pull()
                    for packet in output_stream.encode(filt_frame):
                        output_container.mux(packet)
                
                except av.BlockingIOError:
                    break
                
                except av.EOFError:
                    filter_ended = True
                    break
        
        if not filter_ended:
            try:
                graph.push(None)
            
            except av.EOFError:
                pass
            
        while True:
            try:
                filt_frame = graph.pull()
                
                for packet in output_stream.encode(filt_frame):
                    output_container.mux(packet)
            
            except (av.BlockingIOError, av.EOFError):
                break
            
        for packet in output_stream.encode():
            output_container.mux(packet)

        container.close()
        output_container.close()

    def sorted_glyphs(self) -> tuple:
        singles, effects = [], []

        for glyph in self.glyphs.values():
            if "effect" in glyph:
                effects.append(copy.deepcopy(glyph))
            
            else:
                singles.append(copy.deepcopy(glyph))

        return singles, effects

    def prepare_cropped_audio(self, audio_path: str | None = None):
        tmp_path = self.cropped_song_path.replace(".ogg", ".opus")
        
        self.export_segment(
            audio_path,
            tmp_path,
            self.start_ms,
            self.end_ms,
            self.fade_in_duration,
            self.fade_out_duration
        )

        if os.path.exists(self.cropped_song_path):
            os.remove(self.cropped_song_path)
        
        os.rename(tmp_path, self.cropped_song_path)

    def export(self, model: str | None = None, open_folder: bool = False):
        if model != self.model and model:
            ported_glyphs = Porter.Port.port_glyphs(model, self)
            ExporterImporter.glyphs_to_ogg(
                Utils.get_songs_path(f"{self.id}/cropped_song.ogg"),
                Utils.get_songs_path(f"{self.id}/Composed_{model}.ogg"),
                ported_glyphs,
                model
            )
        
        else:
            singles, effects = self.sorted_glyphs()
    
            for effect in effects:
                singles.extend(GlyphEffects.effect_to_glyph(effect, self.bpm, self.model))
            
            ExporterImporter.glyphs_to_ogg(
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

        self.cached_effects = {}
        self.glyphs = SyncedDict(settings.get("glyphs", {}), sync_callback=self.syncer.sync, composition=self)
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
        return self.glyphs.get(glyph_id)

    def copy_glyph(self, glyph: dict, offset: int = 0, audio_ms: int | None = None):
        new_glyph = copy.deepcopy(glyph)

        start = glyph["start"] + offset
        duration = glyph["duration"]

        if audio_ms is not None:
            audio_ms = int(audio_ms)

            if start >= audio_ms:
                return None, None

            end = start + duration

            if end > audio_ms:
                duration = audio_ms - start

        if duration < 10:
            return None, None

        new_glyph["start"] = start
        new_glyph["duration"] = duration

        self.last_glyph_id += 1
        new_id = self.last_glyph_id
        self.glyphs[new_id] = new_glyph

        return new_id, new_glyph

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
    
    def delete_bunch_of_glyphs(self, keys):
        self.glyphs.delete_keys(keys)
    
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