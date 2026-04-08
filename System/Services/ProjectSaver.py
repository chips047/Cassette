from __future__ import annotations

import os
import copy
import json
import random
import shutil
import ffmpeg

from loguru import (
    logger
)

from System.Common import (
    Utils
)

from System.Interface import (
    Windows
)

from System.Services import (
    Player,
    Porter,
    Encoder,
    GlyphEffects,
    RealTimeVisualizer
)

from System.Common.Constants import (
    DEVICES,
    FFMPEG_PATH,
    FFPROBE_PATH,
    NUMBER_TO_CODE,
    DEFAULT_DURATION,
    DEFAULT_BRIGHTNESS
)

# Utility Functions

def get_audio_duration_ms(file_path: str) -> int:
    probe        = ffmpeg.probe(file_path, cmd = FFPROBE_PATH)
    duration_sec = float(probe["format"]["duration"])
    
    return int(duration_sec * 1000)

def get_metadata(file_path: str) -> tuple[str | None, str]:
    try:
        probe = ffmpeg.probe(file_path, cmd = FFPROBE_PATH)

    except ffmpeg.Error:
        return None, "Unknown Artist"

    tags   = probe.get("format", {}).get("tags", {})
    title  = tags.get("title") or tags.get("TITLE")
    artist = tags.get("artist") or tags.get("ARTIST") or "Unknown Artist"

    return title, artist

class SyncedDict(dict):
    def __init__(
        self,
        *args:         object,
        sync_callback: object,
        composition:   Composition,
        **kwargs:      object
    ) -> None:
        
        super().__init__(*args, **kwargs)

        self.composition                        = composition
        self.sync_callback                      = sync_callback
        self.glyph_id_to_track:  dict[int, str] = {}
        self.visualizator_data:  dict           = {}
        self.is_batching:        bool           = False
        self.pending_keys:       set[int]       = set()
        self.needs_sync:         bool           = False

        self.process_initial_data()

    def start_batching(self) -> None:
        self.is_batching = True
        
        self.pending_keys.clear()
        
        self.needs_sync = False

    def mark_dirty(self, key: int) -> None:
        self.needs_sync = True

        if self.is_batching:
            self.pending_keys.add(key)

    def stop_batching(self) -> None:
        if not self.is_batching:
            return

        self.is_batching = False

        if self.pending_keys:
            for key in list(self.pending_keys):
                if key not in self:
                    continue

                self.sync_item_logic(key, self[key])

        self.pending_keys.clear()

        if self.needs_sync:
            self.finalize_sync()

        self.needs_sync = False

    def process_initial_data(self) -> None:
        for glyph_id, glyph_data in self.items():
            track = glyph_data["track"]
            
            self.glyph_id_to_track[glyph_id] = track
            
            self.process_glyph_effect(glyph_id, glyph_data)
            self.add_glyph_to_visualizator(glyph_id, glyph_data)

    def process_glyph_effect(
        self,
        glyph_id:   int,
        glyph_data: dict
    ) -> None:
        
        effect = glyph_data.get("effect")

        if not effect or effect["name"] == "None":
            self.composition.cached_effects.pop(glyph_id, None)
            return

        self.composition.cached_effects[glyph_id] = GlyphEffects.effect_to_glyph(
            glyph_data,
            self.composition.bpm,
            self.composition.model
        )

    def add_glyph_to_visualizator(
        self,
        glyph_id:   int,
        glyph_data: dict
    ) -> None:
        
        track  = glyph_data["track"]
        effect = glyph_data.get("effect")

        if track not in self.visualizator_data:
            self.visualizator_data[track] = {}

        if not effect or effect["name"] == "None":
            self.visualizator_data[track][glyph_id] = glyph_data
            return

        if glyph_id not in self.composition.cached_effects:
            return

        for index, effect_glyph in enumerate(self.composition.cached_effects[glyph_id]):
            self.visualizator_data[track][f"effect_{glyph_id}_{index}"] = effect_glyph

    def remove_glyph_from_visualizator(self, glyph_id: int) -> None:
        track = self.glyph_id_to_track.get(glyph_id)

        if track is None:
            return

        track_data = self.visualizator_data.get(track)

        if not track_data:
            self.glyph_id_to_track.pop(glyph_id, None)
            return

        track_data.pop(glyph_id, None)

        prefix = f"effect_{glyph_id}_"

        for key in list(track_data.keys()):
            if str(key).startswith(prefix):
                track_data.pop(key, None)

        if not track_data:
            self.visualizator_data.pop(track, None)

        self.glyph_id_to_track.pop(glyph_id, None)

    def sync_item_logic(
        self,
        key:   int,
        value: dict
    ) -> None:
        
        if key in self.glyph_id_to_track:
            self.remove_glyph_from_visualizator(key)

        self.process_glyph_effect(key, value)
        self.add_glyph_to_visualizator(key, value)

        track = value["track"]
        
        self.glyph_id_to_track[key] = track

    def finalize_sync(self) -> None:
        self.sync_callback(self)
        
        self.composition.save()

    def __setitem__(
        self,
        key:   int,
        value: dict
    ) -> None:
        
        super().__setitem__(key, value)

        self.mark_dirty(key)

        if self.is_batching:
            return

        self.sync_item_logic(key, value)
        self.finalize_sync()

        self.needs_sync = False

    def __delitem__(self, key: int) -> None:
        if key not in self:
            return

        self.composition.cached_effects.pop(key, None)
        
        self.remove_glyph_from_visualizator(key)

        super().__delitem__(key)

        self.mark_dirty(key)

        if self.is_batching:
            return

        self.finalize_sync()
        
        self.needs_sync = False

    def update(
        self,
        *args:   object,
        **kwargs: object
    ) -> None:
        
        data = dict(*args, **kwargs)

        if self.is_batching:
            for key, value in data.items():
                super().__setitem__(key, value)
                
                self.mark_dirty(key)

            return

        for key, value in data.items():
            super().__setitem__(key, value)
            
            self.sync_item_logic(key, value)

        self.mark_dirty(0)
        self.finalize_sync()

        self.needs_sync = False

    def delete_keys(self, keys: list[int]) -> None:
        for key in keys:
            if key not in self:
                continue

            self.composition.cached_effects.pop(key, None)
            
            self.remove_glyph_from_visualizator(key)

            super().__delitem__(key)

            self.mark_dirty(key)

        if self.is_batching:
            return

        self.finalize_sync()
        
        self.needs_sync = False

class BaseComposition:
    def __init__(
        self,
        id:       int,
        settings: dict
    ) -> None:
        
        self.id    = id if id is not None else random.randint(10000000, 99999999)
        self.model = settings.get("model")

        self.audio_settings    = settings.get("audio", {})
        self.bpm               = self.audio_settings.get("bpm")
        self.start_ms          = self.audio_settings.get("start_ms")
        self.end_ms            = self.audio_settings.get("end_ms")
        self.fade_in_duration  = self.audio_settings.get("fade_in", 0)
        self.fade_out_duration = self.audio_settings.get("fade_out", 0)
        self.beats             = self.audio_settings.get("beats", [])

        self.glyphs = settings.get("glyphs", {})

        self.cropped_song_path = Utils.get_user_path(f"{self.id}/cropped_song.ogg", "Cassette/Songs")
        self.full_song_path    = Utils.get_user_path(f"{self.id}/full_song.ogg", "Cassette/Songs")

    def needs_cropped_audio(self) -> bool:
        if not os.path.exists(self.full_song_path):
            return False
        
        full_duration_ms = get_audio_duration_ms(self.full_song_path)
        
        return not (self.start_ms == 0 and self.end_ms == full_duration_ms)

    def get_playback_audio_path(self) -> str:
        if self.needs_cropped_audio():
            return self.cropped_song_path
        
        return self.full_song_path

    def export_segment(
        self,
        input_path:  str,
        output_path: str,
        start_ms:    int,
        end_ms:      int,
        fade_in:     int = 0,
        fade_out:    int = 0
    ) -> None:
        
        start_time   = start_ms / 1000.0
        end_time     = end_ms / 1000.0
        duration_sec = (end_ms - start_ms) / 1000.0

        stream = ffmpeg.input(input_path)
        stream = ffmpeg.filter(stream, "atrim", start = start_time, end = end_time)
        stream = ffmpeg.filter(stream, "asetpts", expr = "PTS-STARTPTS")
        stream = ffmpeg.filter(stream, "dynaudnorm")

        if fade_in:
            stream = ffmpeg.filter(
                stream,
                "afade",
                type       = "in",
                start_time = 0,
                duration   = fade_in / 1000.0,
            )

        if fade_out:
            fade_start = max(0.0, duration_sec - fade_out / 1000.0)
            
            stream = ffmpeg.filter(
                stream,
                "afade",
                type       = "out",
                start_time = fade_start,
                duration   = fade_out / 1000.0,
            )

        try:
            (
                ffmpeg
                .output(stream, output_path, acodec = "libopus", ar = 48000)
                .overwrite_output()
                .run(
                    cmd            = FFMPEG_PATH,
                    capture_stdout = True,
                    capture_stderr = True
                )
            )

        except ffmpeg.Error as error:
            logger.critical(error.stderr.decode("utf-8", errors = "ignore"))

    def sorted_glyphs(self) -> tuple[list[dict], list[dict]]:
        singles: list[dict] = []
        effects: list[dict] = []

        for glyph in self.glyphs.values():
            if "effect" in glyph:
                effects.append(copy.deepcopy(glyph))
                continue

            singles.append(copy.deepcopy(glyph))

        return singles, effects

    def prepare_cropped_audio(self, audio_path: str) -> None:
        tmp_path = self.cropped_song_path.replace(".ogg", ".opus")

        self.export_segment(
            audio_path,
            tmp_path,
            self.start_ms,
            self.end_ms,
            self.fade_in_duration,
            self.fade_out_duration,
        )

        if os.path.exists(self.cropped_song_path):
            os.remove(self.cropped_song_path)

        os.rename(tmp_path, self.cropped_song_path)

    def export(
        self,
        watermark:   str        = "Cassette",
        model:       str | None = None,
        open_folder: bool       = False
    ) -> None:
        
        playback_audio_path = self.get_playback_audio_path()
        
        if model and model != self.model:
            ported_glyphs = Porter.port_glyphs(model, self)

            Encoder.glyphs_to_ogg(
                playback_audio_path,
                Utils.get_user_path(f"{self.id}/Composed_{model}.ogg","Cassette/Songs"),
                ported_glyphs,
                model,
                watermark
            )
        
        else:
            singles, effects = self.sorted_glyphs()

            for effect in effects:
                singles.extend(GlyphEffects.effect_to_glyph(effect, self.bpm, self.model))

            Encoder.glyphs_to_ogg(
                playback_audio_path,
                Utils.get_user_path(f"{self.id}/Composed.ogg", "Cassette/Songs"),
                singles,
                self.model,
                watermark,
            )

        if open_folder:
            Utils.open_file(Utils.get_user_path(str(self.id), "Cassette/Songs"))
            
            Player.ui_player.play_sound("App/Export")

    def export_all(self, watermark: str = "Cassette") -> None:
        Player.ui_player.play_sound("App/ExportLong")
        
        self.export(watermark)

        for model in DEVICES[self.model].port_variants:
            self.export(watermark, NUMBER_TO_CODE[model])

        Utils.open_file(Utils.get_user_path(str(self.id)), "Cassette/Songs")

class Composition(BaseComposition):
    def __init__(
        self,
        audiofile_path: str  | None = None,
        settings:       dict | None = None,
        id:             int  | None = None
    ) -> None:
        
        settings = settings or {}

        if id is not None:
            save_path = Utils.get_user_path(f"{id}/Save.json", "Cassette/Songs")

            with open(save_path, "r", encoding = "utf-8") as file:
                settings = json.load(file)

        super().__init__(id, settings)

        self.syncer = RealTimeVisualizer.rt_visualizer
        
        with open("version", "r", encoding = "utf-8") as file:
            self.version = file.read()

        self.song_path      = audiofile_path
        self.brightness     = DEFAULT_BRIGHTNESS
        self.duration_ms    = DEFAULT_DURATION
        self.track_number   = DEVICES[self.model].base_tracks
        self.save_version   = settings.get("version", self.version)
        self.default_effect = "none"

        self.syncer.set_composition(self)

        self.cached_effects: dict[int, list] = {}

        raw_glyphs: dict = settings.get("glyphs", {})
        int_glyphs: dict[int, dict] = {int(key): value for key, value in raw_glyphs.items()}

        self.glyphs = SyncedDict(
            int_glyphs,
            sync_callback = self.syncer.sync,
            composition   = self,
        )

        self.last_glyph_id = max(self.glyphs.keys()) if self.glyphs else 0

        self.syncer.start_scanning_loop()
        self.syncer.full_load(self.glyphs)

        os.makedirs(Utils.get_user_path(str(self.id), "Cassette/Songs"), exist_ok = True)

        if audiofile_path:
            shutil.copyfile(audiofile_path, self.full_song_path)

        if self.needs_cropped_audio():
            if not os.path.exists(self.cropped_song_path):
                self.prepare_cropped_audio(self.full_song_path)
        
        self.save()

    @property
    def batching_mode(self) -> bool:
        return self.glyphs.is_batching

    def new_glyph(
        self,
        track:      str,
        start:      int,
        duration:   int | None = None,
        brightness: int | None = None
    ) -> tuple[int, dict]:
        
        self.last_glyph_id += 1

        glyph: dict = {
            "track":      track,
            "start":      start,
            "duration":   duration or self.duration_ms,
            "brightness": brightness or self.brightness,
        }

        if self.default_effect != "none":
            glyph = GlyphEffects.apply_visual_effect(
                glyph,
                "Fade",
                {
                    "mode": self.default_effect,
                    "easing": "linear"
                }
            )

        self.glyphs[self.last_glyph_id] = glyph
        
        return self.last_glyph_id, glyph

    def get_glyph(self, glyph_id: int) -> dict | None:
        return self.glyphs.get(glyph_id)

    def copy_glyph(
        self,
        glyph:    dict,
        offset:   int        = 0,
        audio_ms: int | None = None
    ) -> tuple[int, dict] | tuple[None, None]:
        
        new_glyph = copy.deepcopy(glyph)
        start     = glyph["start"] + offset
        duration  = glyph["duration"]

        if audio_ms is not None:
            audio_ms = int(audio_ms)

            if start >= audio_ms:
                return None, None

            end = start + duration

            if end > audio_ms:
                duration = audio_ms - start

        if duration < 10:
            return None, None

        new_glyph["start"]    = start
        new_glyph["duration"] = duration

        self.last_glyph_id += 1
        
        self.glyphs[self.last_glyph_id] = new_glyph

        return self.last_glyph_id, new_glyph

    def save(self) -> None:
        save_path = Utils.get_user_path(f"{self.id}/Save.json", "Cassette/Songs")
        
        os.makedirs(Utils.get_user_path(str(self.id), "Cassette/Songs"), exist_ok = True)

        if os.path.exists(save_path):
            with open(save_path, "r", encoding = "utf-8") as file:
                data = json.load(file)

            data["glyphs"] = dict(self.glyphs)

            with open(save_path, "w", encoding = "utf-8") as file:
                json.dump(data, file, ensure_ascii = False, indent = 4)

            return

        title, author = get_metadata(self.full_song_path)
        
        title  = title or os.path.basename(self.song_path)
        author = author or "Unknown Artist"

        data = {
            "audio": {
                "title":    title,
                "artist":   author,
                "start_ms": self.start_ms,
                "end_ms":   self.end_ms,
                "bpm":      self.bpm,
                "beats":    self.beats,
                "fade_in":  self.fade_in_duration,
                "fade_out": self.fade_out_duration,
            },
            "progress": 0,
            "model":    self.model,
            "version":  self.version,
            "glyphs":   dict(self.glyphs)
        }

        with open(save_path, "w", encoding = "utf-8") as file:
            json.dump(data, file, ensure_ascii = False, indent = 4)

    def update_bunch_of_glyphs(self, data: dict[int, dict]) -> None:
        self.glyphs.update(data)

    def delete_bunch_of_glyphs(self, keys: list[int]) -> None:
        self.glyphs.delete_keys(keys)

    def replace_glyph(
        self,
        id:   int,
        data: dict
    ) -> None:
        
        self.glyphs[id] = data

    def delete_glyph(self, id: int) -> None:
        del self.glyphs[id]

    def delete_glyphs(self, keys: list[int]) -> None:
        self.glyphs.delete_keys(keys)

    def set_brightness(self, brightness: int) -> None:
        self.brightness = brightness

    def set_duration(self, duration: int) -> None:
        self.duration_ms = duration

    def set_default_effect(self, effect_name: str) -> None:
        self.default_effect = effect_name

    def all_glyphs(self) -> dict[int, dict]:
        return self.glyphs

    def start_batching(self) -> None:
        if self.batching_mode:
            return

        self.glyphs.start_batching()

    def stop_batching(self) -> None:
        if not self.batching_mode:
            return

        self.glyphs.stop_batching()

class MinimalComposition(BaseComposition):
    def __init__(self, id: int) -> None:
        save_path = Utils.get_user_path(f"{id}/Save.json", "Cassette/Songs")

        with open(save_path, "r", encoding = "utf-8") as file:
            settings = json.load(file)

        super().__init__(id, settings)

        if not os.path.exists(self.full_song_path):
            Windows.ErrorWindow("Corrupted!", "This save is corrupted.").exec_()
            return

        if self.needs_cropped_audio():
            if not os.path.exists(self.cropped_song_path):
                self.prepare_cropped_audio(self.full_song_path)