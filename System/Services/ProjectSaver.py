from __future__ import annotations

import os
import json
import copy
import numpy
import shutil
import random
import tempfile
import soundfile

from loguru import logger

from PyQt6.QtCore import QCoreApplication

from System.Common import (
    Utils,
    Constants
)

from System.Interface import (
    Timing,
    Windows
)

from System.Services import (
    Player,
    Porter,
    Encoder,
    GlyphEffects,
    RealTimeVisualizer
)

# Utility Functions

def is_valid_opus_file(file_path: str) -> bool:
    try:
        with open(file_path, "rb") as file_handle:
            header = file_handle.read(1024)

            return header.startswith(b"OggS") and b"OpusHead" in header

    except Exception:
        return False

def get_audio_duration_ms(file_path: str) -> int:
    command = [
        Constants.FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        file_path,
    ]

    result = Utils.run_hidden(command)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")

    data         = json.loads(result.stdout)
    duration_sec = float(data["format"]["duration"])

    return int(duration_sec * 1000)

def get_metadata(file_path: str) -> tuple[str | None, str]:
    command = [
        Constants.FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format_tags=title,artist,TITLE,ARTIST",
        "-of", "json",
        file_path
    ]

    try:
        result = Utils.run_hidden(command)

        if result.returncode != 0:
            return None, "Unknown Artist"

        data = json.loads(result.stdout)
        tags = data.get("format", {}).get("tags", {})

        title  = tags.get("title") or tags.get("TITLE")
        artist = tags.get("artist") or tags.get("ARTIST") or "Unknown Artist"

        return title, artist

    except Exception:
        logger.error("Unable to get metadata from the audio.")

        return None, "Unknown Artist"

# Synchronized Dictionary

class SyncedDict(dict):
    def __init__(
            self,
            *arguments:    object,
            sync_callback: object,
            composition:   Composition,
            **keywords:    object
        ) -> None:

        super().__init__(*arguments, **keywords)

        self.composition                   = composition
        self.sync_callback                 = sync_callback
        self.visualizator_changed_callback = None
        self.glyph_id_to_track             = {}
        self.visualizator_data             = {}
        self.is_batching                   = False
        self.pending_keys                  = set()
        self.needs_sync                    = False

        self.process_initial_data()

    def start_batching(self) -> None:
        self.is_batching = True
        self.pending_keys.clear()
        self.needs_sync  = False

    def mark_dirty(self, key: int) -> None:
        self.needs_sync = True

        if self.is_batching:
            self.pending_keys.add(key)

    def stop_batching(self) -> None:
        if not self.is_batching:
            return

        self.is_batching = False
        had_changes     = False

        if self.pending_keys:
            had_changes = True

            for key in list(self.pending_keys):
                if key not in self:
                    continue

                self.sync_item_logic(key, self[key], notify = False)

        self.pending_keys.clear()

        if had_changes and self.visualizator_changed_callback:
            self.visualizator_changed_callback()

        if self.needs_sync:
            self.finalize_sync()

        self.needs_sync = False

    def process_initial_data(self) -> None:
        for glyph_id, glyph_data in self.items():
            track                            = glyph_data["track"]
            self.glyph_id_to_track[glyph_id] = track

            self.process_glyph_effect(glyph_id, glyph_data)
            self.add_glyph_to_visualizator(glyph_id, glyph_data, notify = False)

        if self.visualizator_changed_callback:
            self.visualizator_changed_callback()

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
            glyph_data: dict,
            notify:     bool = True
        ) -> None:

        track  = glyph_data["track"]
        effect = glyph_data.get("effect")

        if track not in self.visualizator_data:
            self.visualizator_data[track] = {}

        if not effect or effect["name"] == "None":
            self.visualizator_data[track][glyph_id] = glyph_data

        else:
            if glyph_id not in self.composition.cached_effects:
                return

            for index, effect_glyph in enumerate(self.composition.cached_effects[glyph_id]):
                self.visualizator_data[track][f"effect_{glyph_id}_{index}"] = effect_glyph

        if notify and self.visualizator_changed_callback:
            self.visualizator_changed_callback()

    def remove_glyph_from_visualizator(
            self,
            glyph_id: int,
            notify:   bool = True
        ) -> None:

        track = self.glyph_id_to_track.get(glyph_id)

        if track is None:
            return

        track_data = self.visualizator_data.get(track)

        if not track_data:
            self.glyph_id_to_track.pop(glyph_id, None)

            return

        track_data.pop(glyph_id, None)

        prefix   = f"effect_{glyph_id}_"
        sub_keys = [key for key in track_data if str(key).startswith(prefix)]

        for key in sub_keys:
            track_data.pop(key, None)

        if not track_data:
            self.visualizator_data.pop(track, None)

        self.glyph_id_to_track.pop(glyph_id, None)

        if notify and self.visualizator_changed_callback:
            self.visualizator_changed_callback()

    def sync_item_logic(
            self,
            key:    int,
            value:  dict,
            notify: bool = True
        ) -> None:

        if key in self.glyph_id_to_track:
            self.remove_glyph_from_visualizator(key, notify = notify)

        self.process_glyph_effect(key, value)
        self.add_glyph_to_visualizator(key, value, notify = notify)

        self.glyph_id_to_track[key] = value["track"]

    def finalize_sync(self) -> None:
        self.sync_callback(self)
        self.composition.save(immediate = False)

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
            *arguments: object,
            **keywords:  object
        ) -> None:

        data = dict(*arguments, **keywords)

        if self.is_batching:
            for key, value in data.items():
                super().__setitem__(key, value)
                self.mark_dirty(key)

            return

        for key, value in data.items():
            super().__setitem__(key, value)
            self.sync_item_logic(key, value, notify = False)

        if self.visualizator_changed_callback:
            self.visualizator_changed_callback()

        self.mark_dirty(0)
        self.finalize_sync()
        self.needs_sync = False

    def delete_keys(self, keys: list[int]) -> None:
        for key in keys:
            if key not in self:
                continue

            self.composition.cached_effects.pop(key, None)
            self.remove_glyph_from_visualizator(key, notify = False)
            super().__delitem__(key)
            self.mark_dirty(key)

        if self.is_batching:
            return

        if self.visualizator_changed_callback:
            self.visualizator_changed_callback()

        self.finalize_sync()
        self.needs_sync = False

# Base Composition

class BaseComposition:
    def __init__(
            self,
            identifier: int,
            settings:   dict
        ) -> None:

        self.id    = identifier if identifier is not None else random.randint(10000000, 99999999)
        self.model = settings.get("model")

        self.audio_settings    = settings.get("audio", {})
        self.bpm               = self.audio_settings.get("bpm")
        self.start_ms          = self.audio_settings.get("start_ms")
        self.end_ms            = self.audio_settings.get("end_ms")
        self.fade_in_duration  = self.audio_settings.get("fade_in", 0)
        self.fade_out_duration = self.audio_settings.get("fade_out", 0)
        self.fade_in_type      = self.audio_settings.get("fade_in_type", "fade")
        self.fade_out_type     = self.audio_settings.get("fade_out_type", "fade")
        self.beats             = self.audio_settings.get("beats", [])

        self.glyphs = settings.get("glyphs", {})

        self.cropped_song_path = Utils.get_user_path(f"{self.id}/cropped_song.ogg", "Cassette/Songs")
        self.full_song_path    = Utils.get_user_path(f"{self.id}/full_song.ogg", "Cassette/Songs")

    def ensure_full_song_is_opus(self) -> None:
        if not os.path.exists(self.full_song_path):
            return

        if is_valid_opus_file(self.full_song_path):
            return

        logger.info(f"Converting non-Opus audio file to Opus: {self.full_song_path}")
        temporary_path = self.full_song_path.replace(".ogg", "_tmp.opus")

        command = [
            Constants.FFMPEG_PATH,
            "-y",
            "-v", "error",
            "-i", self.full_song_path,
            "-vn",
            "-c:a", "libopus",
            "-ar", "48000",
            temporary_path
        ]

        result = Utils.run_hidden(command)

        if result.returncode != 0:
            error_message = (result.stderr or "").strip()
            logger.critical(error_message)

            raise RuntimeError(error_message or "ffmpeg failed to convert full song to Opus")

        if os.path.exists(self.full_song_path):
            os.remove(self.full_song_path)

        os.rename(temporary_path, self.full_song_path)

    def needs_cropped_audio(self) -> bool:
        if not os.path.exists(self.full_song_path):
            return False

        full_duration_ms = get_audio_duration_ms(self.full_song_path)
        starts_at_zero   = self.start_ms <= Constants.CROP_TOLERANCE_MS
        ends_at_full     = abs(self.end_ms - full_duration_ms) <= Constants.CROP_TOLERANCE_MS
        has_no_effects   = (int(self.fade_in_duration or 0) == 0 and int(self.fade_out_duration or 0) == 0)

        return not (starts_at_zero and ends_at_full and has_no_effects)

    def get_playback_audio_path(self) -> str:
        has_full    = os.path.exists(self.full_song_path)
        has_cropped = os.path.exists(self.cropped_song_path)

        if not has_full and has_cropped:
            return self.cropped_song_path

        if has_full and has_cropped:
            if self.needs_cropped_audio():
                return self.cropped_song_path

            return self.full_song_path

        if has_full and not has_cropped:
            if self.needs_cropped_audio():
                self.prepare_cropped_audio(self.full_song_path)

                return self.cropped_song_path

            return self.full_song_path

        return self.full_song_path

    def apply_dsp_effects(
            self,
            data:          numpy.ndarray,
            sample_rate:   int,
            fade_in:       int,
            fade_out:      int,
            fade_in_type:  str,
            fade_out_type: str
        ) -> numpy.ndarray:

        processed_data = numpy.array(data, copy = True)
        total_samples  = len(processed_data)
        minimum_speed  = 0.05

        has_speed_intro = (fade_in_type == "speed" and fade_in > 0)
        has_speed_outro = (fade_out_type == "speed" and fade_out > 0)

        if has_speed_intro or has_speed_outro:
            output_intro_samples = int(sample_rate * (fade_in / 1000.0)) if has_speed_intro else 0
            source_intro_samples = int(output_intro_samples * (1.0 + minimum_speed) / 2.0) if has_speed_intro else 0

            output_outro_samples = int(sample_rate * (fade_out / 1000.0)) if has_speed_outro else 0
            source_outro_samples = int(output_outro_samples * (1.0 + minimum_speed) / 2.0) if has_speed_outro else 0

            if source_intro_samples + source_outro_samples >= total_samples:
                scale_ratio          = float(total_samples) / max(1.0, float(source_intro_samples + source_outro_samples))
                output_intro_samples = int(output_intro_samples * scale_ratio)
                source_intro_samples = int(source_intro_samples * scale_ratio)
                output_outro_samples = int(output_outro_samples * scale_ratio)
                source_outro_samples = int(source_outro_samples * scale_ratio)

            source_steady_samples = total_samples - source_intro_samples - source_outro_samples
            output_total_samples  = output_intro_samples + source_steady_samples + output_outro_samples

            source_indices = numpy.empty(output_total_samples, dtype = numpy.float64)

            if output_intro_samples > 0:
                time_range                  = numpy.arange(output_intro_samples, dtype = numpy.float64)
                time_fraction               = time_range / float(output_intro_samples)
                source_indices[:output_intro_samples] = output_intro_samples * (minimum_speed * time_fraction + ((1.0 - minimum_speed) / 2.0) * (time_fraction ** 2))

            steady_start_output = output_intro_samples
            steady_end_output   = output_intro_samples + source_steady_samples

            if source_steady_samples > 0:
                steady_range = numpy.arange(source_steady_samples, dtype = numpy.float64)
                source_indices[steady_start_output:steady_end_output] = source_intro_samples + steady_range

            if output_outro_samples > 0:
                time_range                 = numpy.arange(output_outro_samples, dtype = numpy.float64)
                time_fraction              = time_range / float(output_outro_samples)
                source_indices[steady_end_output:] = (source_intro_samples + source_steady_samples) + output_outro_samples * (time_fraction - ((1.0 - minimum_speed) / 2.0) * (time_fraction ** 2))

            source_positions = numpy.arange(total_samples, dtype = numpy.float64)
            resampled_audio  = numpy.empty((output_total_samples, processed_data.shape[1]), dtype = numpy.float32)

            for channel in range(processed_data.shape[1]):
                resampled_audio[:, channel] = numpy.interp(source_indices, source_positions, processed_data[:, channel])

            processed_data = resampled_audio
            total_samples  = len(processed_data)

        if fade_in_type == "fade" and fade_in > 0:
            fade_in_samples = min(total_samples, int(sample_rate * (fade_in / 1000.0)))
            ramp            = numpy.linspace(0.0, 1.0, fade_in_samples, dtype = numpy.float32)[:, None]
            processed_data[:fade_in_samples] *= ramp

        elif fade_in_type == "filter" and fade_in > 0:
            fade_in_samples = min(total_samples, int(sample_rate * (fade_in / 1000.0)))
            progress        = numpy.linspace(0.0, 1.0, fade_in_samples, dtype = numpy.float32)
            cutoff          = 300.0 + 11700.0 * (progress ** 2)
            alpha           = numpy.clip(2.0 * numpy.pi * cutoff / sample_rate, 0.001, 0.999).astype(numpy.float32)

            for channel in range(processed_data.shape[1]):
                filtered_sample = 0.0

                for sample_index in range(fade_in_samples):
                    filtered_sample += alpha[sample_index] * (processed_data[sample_index, channel] - filtered_sample)
                    processed_data[sample_index, channel] = filtered_sample

        if fade_out_type == "fade" and fade_out > 0:
            fade_out_samples = min(total_samples, int(sample_rate * (fade_out / 1000.0)))
            ramp             = numpy.linspace(1.0, 0.0, fade_out_samples, dtype = numpy.float32)[:, None]
            processed_data[-fade_out_samples:] *= ramp

        elif fade_out_type == "filter" and fade_out > 0:
            fade_out_samples = min(total_samples, int(sample_rate * (fade_out / 1000.0)))
            progress         = numpy.linspace(1.0, 0.0, fade_out_samples, dtype = numpy.float32)
            cutoff           = 300.0 + 11700.0 * (progress ** 2)
            alpha            = numpy.clip(2.0 * numpy.pi * cutoff / sample_rate, 0.001, 0.999).astype(numpy.float32)
            start_index      = total_samples - fade_out_samples

            for channel in range(processed_data.shape[1]):
                filtered_sample = float(processed_data[start_index, channel])

                for sample_index in range(fade_out_samples):
                    resolved_index   = start_index + sample_index
                    filtered_sample += alpha[sample_index] * (processed_data[resolved_index, channel] - filtered_sample)
                    processed_data[resolved_index, channel] = filtered_sample

        return processed_data

    def export_segment(
            self,
            input_path:    str,
            output_path:   str,
            start_ms:      int,
            end_ms:        int,
            fade_in:       int = 0,
            fade_out:      int = 0,
            fade_in_type:  str = "fade",
            fade_out_type: str = "fade"
        ) -> None:

        fade_in_duration  = int(fade_in or 0)
        fade_out_duration = int(fade_out or 0)

        is_pure_volume_fade = (fade_in_type == "fade" and fade_out_type == "fade")

        if is_pure_volume_fade:
            start_time   = start_ms / 1000.0
            end_time     = end_ms / 1000.0
            duration_sec = max(0.0, (end_ms - start_ms) / 1000.0)

            filters = [
                f"atrim=start={start_time}:end={end_time}",
                "asetpts=PTS-STARTPTS",
                "dynaudnorm"
            ]

            if fade_in_duration:
                fade_in_sec = fade_in_duration / 1000.0
                filters.append(f"afade=t=in:st=0:d={fade_in_sec}")

            if fade_out_duration:
                fade_out_sec = fade_out_duration / 1000.0
                fade_start   = max(0.0, duration_sec - fade_out_sec)
                filters.append(f"afade=t=out:st={fade_start}:d={fade_out_sec}")

            audio_filter = ",".join(filters)

            command = [
                Constants.FFMPEG_PATH,
                "-y",
                "-v", "error",
                "-i", input_path,
                "-vn",
                "-af", audio_filter,
                "-c:a", "libopus",
                "-ar", "48000",
                output_path
            ]

            result = Utils.run_hidden(command)

            if result.returncode != 0:
                error_message = (result.stderr or "").strip()
                logger.critical(error_message)

                raise RuntimeError(error_message or "ffmpeg failed")

            return

        temporary_wav      = tempfile.NamedTemporaryFile(suffix = ".wav", delete = False)
        temporary_wav_path = temporary_wav.name
        temporary_wav.close()

        duration_sec = max(0.0, (end_ms - start_ms) / 1000.0)

        extract_command = [
            Constants.FFMPEG_PATH,
            "-y",
            "-v", "error",
            "-ss", str(start_ms / 1000.0),
            "-t", str(duration_sec),
            "-i", input_path,
            "-vn",
            "-af", "dynaudnorm",
            "-c:a", "pcm_s16le",
            "-ar", "48000",
            temporary_wav_path
        ]

        result = Utils.run_hidden(extract_command)

        if result.returncode != 0:
            if os.path.exists(temporary_wav_path):
                os.remove(temporary_wav_path)

            error_message = (result.stderr or "").strip()
            raise RuntimeError(error_message or "ffmpeg failed extracting temporary WAV")

        audio_samples, sample_rate = soundfile.read(temporary_wav_path, dtype = "float32")

        if audio_samples.ndim == 1:
            audio_samples = numpy.column_stack((audio_samples, audio_samples))

        processed_samples = self.apply_dsp_effects(
            audio_samples,
            sample_rate,
            fade_in_duration,
            fade_out_duration,
            fade_in_type,
            fade_out_type
        )

        soundfile.write(temporary_wav_path, processed_samples, sample_rate)

        encode_command = [
            Constants.FFMPEG_PATH,
            "-y",
            "-v", "error",
            "-i", temporary_wav_path,
            "-vn",
            "-c:a", "libopus",
            "-ar", "48000",
            output_path
        ]

        result = Utils.run_hidden(encode_command)

        if os.path.exists(temporary_wav_path):
            os.remove(temporary_wav_path)

        if result.returncode != 0:
            error_message = (result.stderr or "").strip()
            raise RuntimeError(error_message or "ffmpeg failed encoding processed Opus")

    def sorted_glyphs(self) -> tuple[list[dict], list[dict]]:
        singles = []
        effects = []

        for glyph in self.glyphs.values():
            if "effect" in glyph:
                effects.append(copy.deepcopy(glyph))

                continue

            singles.append(copy.deepcopy(glyph))

        return singles, effects

    def prepare_cropped_audio(self, audio_path: str) -> None:
        temporary_path = self.cropped_song_path.replace(".ogg", ".opus")

        self.export_segment(
            audio_path,
            temporary_path,
            self.start_ms,
            self.end_ms,
            self.fade_in_duration,
            self.fade_out_duration,
            self.fade_in_type,
            self.fade_out_type
        )

        if os.path.exists(self.cropped_song_path):
            os.remove(self.cropped_song_path)

        os.rename(temporary_path, self.cropped_song_path)

    def save(self, immediate: bool = False) -> None:
        pass

    def export(
            self,
            watermark:        str        = "Cassette",
            model:            str | None = None,
            open_folder:      bool       = False,
            send_to_ringtone: bool       = False
        ) -> None:

        self.save(immediate = True)

        playback_audio_path = self.get_playback_audio_path()

        if model and model != self.model:
            ported_glyphs = Porter.port_glyphs(model, self)
            export_path   = Utils.get_user_path(f"{self.id}/Composed_{model}.ogg", "Cassette/Songs")

            Encoder.glyphs_to_ogg(
                playback_audio_path,
                export_path,
                ported_glyphs,
                model,
                watermark
            )

        else:
            singles, effects = self.sorted_glyphs()

            for effect in effects:
                singles.extend(GlyphEffects.effect_to_glyph(effect, self.bpm, self.model))

            export_path = Utils.get_user_path(f"{self.id}/Composed.ogg", "Cassette/Songs")

            Encoder.glyphs_to_ogg(
                playback_audio_path,
                export_path,
                singles,
                self.model,
                watermark
            )

        if send_to_ringtone:
            RealTimeVisualizer.rt_visualizer.push_ringtone(export_path)

        if open_folder:
            Utils.open_file(Utils.get_user_path(str(self.id), "Cassette/Songs"))
            Player.ui_player.play_sound("Controls/Export/Short")

    def export_all(
            self,
            watermark:        str  = "Cassette",
            send_to_ringtone: bool = False
        ) -> None:

        Player.ui_player.play_sound("Controls/Export/Long")

        self.export(
            watermark        = watermark,
            send_to_ringtone = send_to_ringtone
        )

        for model in Constants.DEVICES[self.model].port_variants:
            self.export(
                watermark        = watermark,
                model            = Constants.NUMBER_TO_CODE[model],
                send_to_ringtone = send_to_ringtone
            )

        Utils.open_file(Utils.get_user_path(str(self.id), "Cassette/Songs"))

# Composition

class Composition(BaseComposition):
    def __init__(
            self,
            audiofile_path: str  | None = None,
            settings:       dict | None = None,
            identifier:     int  | None  = None
        ) -> None:

        settings = settings or {}

        if identifier is not None:
            save_path = Utils.get_user_path(f"{identifier}/Save.json", "Cassette/Songs")

            with open(save_path, "r", encoding = "utf-8") as file_handle:
                settings = json.load(file_handle)

        super().__init__(identifier, settings)

        self.cached_save_data = copy.deepcopy(settings)
        self.progress         = float(self.cached_save_data.get("progress", 0.0))

        self.save_timer = Timing.Timer(
            interval    = 500,
            callback    = self.flush_save_to_disk,
            single_shot = True
        )

        application = QCoreApplication.instance()

        if application:
            application.aboutToQuit.connect(self.on_application_about_to_quit)

        self.syncer = RealTimeVisualizer.rt_visualizer

        path = Utils.get_resource_path("version")
        with open(path, "r", encoding = "utf-8") as file_handle:
            self.version = file_handle.read()

        self.song_path      = audiofile_path
        self.brightness     = Constants.DEFAULT_BRIGHTNESS
        self.duration_ms    = Constants.DEFAULT_DURATION
        self.track_number   = Constants.DEVICES[self.model].base_tracks
        self.track_names    = Constants.DEVICES[self.model].track_names
        self.save_version   = settings.get("version", self.version)
        self.default_effect = "none"

        self.syncer.set_composition(self)
        self.cached_effects = {}

        raw_glyphs = settings.get("glyphs", {})
        int_glyphs = {int(key): value for key, value in raw_glyphs.items()}

        self.glyphs = SyncedDict(
            int_glyphs,
            sync_callback = self.syncer.sync,
            composition   = self
        )

        self.last_glyph_id = max(self.glyphs.keys()) if self.glyphs else 0

        self.syncer.start_scanning_loop()
        self.syncer.full_load(self.glyphs)

        os.makedirs(Utils.get_user_path(str(self.id), "Cassette/Songs"), exist_ok = True)

        if audiofile_path:
            shutil.copyfile(audiofile_path, self.full_song_path)

        self.ensure_full_song_is_opus()

        if self.needs_cropped_audio():
            if not os.path.exists(self.cropped_song_path):
                self.prepare_cropped_audio(self.full_song_path)

        self.save(immediate = True)

    @property
    def batching_mode(self) -> bool:
        return self.glyphs.is_batching

    def on_application_about_to_quit(self) -> None:
        self.update_progress(immediate = True)

    def update_progress(self, immediate: bool = True) -> None:
        self.progress = self.calculate_completion_percentage()

        if immediate:
            self.save(immediate = True)

    def cleanup(self) -> None:
        application = QCoreApplication.instance()

        if application:
            try:
                application.aboutToQuit.disconnect(self.on_application_about_to_quit)

            except (TypeError, RuntimeError):
                pass

    def new_glyph(
            self,
            track:      str,
            start:      int,
            duration:   int | None = None,
            brightness: int | None = None
        ) -> tuple[int, dict]:

        self.last_glyph_id += 1

        glyph = {
            "track":      track,
            "start":      start,
            "duration":   duration or self.duration_ms,
            "brightness": brightness or self.brightness
        }

        if self.default_effect != "none":
            glyph = GlyphEffects.apply_visual_effect(
                glyph,
                "Fade",
                {
                    "mode":   self.default_effect,
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

    def save(self, immediate: bool = False) -> None:
        if immediate:
            if self.save_timer.isActive():
                self.save_timer.stop()

            self.flush_save_to_disk()

        else:
            self.save_timer.start()

    def calculate_completion_percentage(self) -> float:
        if not self.glyphs:
            return 0.0

        max_glyph_end_ms = max(
            glyph["start"] + glyph["duration"]
            for glyph in self.glyphs.values()
        )

        audio_duration_ms = float(self.end_ms or 0)

        if audio_duration_ms <= 0:
            if os.path.exists(self.full_song_path):
                audio_duration_ms = float(get_audio_duration_ms(self.full_song_path))

            elif os.path.exists(self.cropped_song_path):
                audio_duration_ms = float(get_audio_duration_ms(self.cropped_song_path))

        if audio_duration_ms <= 0:
            return 0.0

        ratio = (max_glyph_end_ms / audio_duration_ms) * 100.0

        return max(0.0, min(100.0, round(ratio, 1)))

    def flush_save_to_disk(self) -> None:
        save_path = Utils.get_user_path(f"{self.id}/Save.json", "Cassette/Songs")
        os.makedirs(Utils.get_user_path(str(self.id), "Cassette/Songs"), exist_ok = True)

        title = self.cached_save_data.get("audio", {}).get("title")

        if not title:
            title = os.path.basename(self.song_path or "") or "Unknown Track"

        artist = self.cached_save_data.get("audio", {}).get("artist") or "Unknown Artist"

        data = {
            **self.cached_save_data,
            "audio": {
                **self.cached_save_data.get("audio", {}),
                "title":         title,
                "artist":        artist,
                "start_ms":      self.start_ms,
                "end_ms":        self.end_ms,
                "bpm":           self.bpm,
                "beats":         self.beats,
                "fade_in":       self.fade_in_duration,
                "fade_out":      self.fade_out_duration,
                "fade_in_type":  self.fade_in_type,
                "fade_out_type": self.fade_out_type
            },
            "progress": self.progress,
            "model":    self.model,
            "version":  self.version,
            "glyphs":   dict(self.glyphs)
        }

        self.cached_save_data = data

        try:
            with open(save_path, "w", encoding = "utf-8") as file_handle:
                json.dump(data, file_handle, ensure_ascii = False, indent = 4)

        except Exception as error:
            logger.error(f"Save file writing failed: {error}")

    def update_bunch_of_glyphs(self, data: dict[int, dict]) -> None:
        self.glyphs.update(data)

    def delete_bunch_of_glyphs(self, keys: list[int]) -> None:
        self.glyphs.delete_keys(keys)

    def glyph_absolute_range(
            self,
            glyph:        dict,
            old_start_ms: int
        ) -> tuple[int, int]:

        absolute_start = glyph["start"] + old_start_ms
        absolute_end   = absolute_start + glyph["duration"]

        return absolute_start, absolute_end

    def count_glyphs_outside_range(
            self,
            start_ms: int,
            end_ms:   int
        ) -> int:

        old_start_ms = self.start_ms or 0
        count        = 0

        for glyph in self.glyphs.values():
            absolute_start, absolute_end = self.glyph_absolute_range(glyph, old_start_ms)

            if absolute_start < start_ms or absolute_end > end_ms:
                count += 1

        return count

    def trim_audio(
            self,
            start_ms:      int,
            end_ms:        int,
            fade_in:       int = 0,
            fade_out:      int = 0,
            fade_in_type:  str = "fade",
            fade_out_type: str = "fade"
        ) -> None:

        old_start_ms = self.start_ms or 0

        self.start_ms          = start_ms
        self.end_ms            = end_ms
        self.fade_in_duration  = fade_in
        self.fade_out_duration = fade_out
        self.fade_in_type      = fade_in_type
        self.fade_out_type     = fade_out_type

        kept_glyphs  = {}
        removed_keys = []

        self.glyphs.start_batching()

        for glyph_id, glyph in list(self.glyphs.items()):
            absolute_start, absolute_end = self.glyph_absolute_range(glyph, old_start_ms)

            if absolute_start < start_ms or absolute_end > end_ms:
                removed_keys.append(glyph_id)

                continue

            new_glyph          = copy.deepcopy(glyph)
            new_glyph["start"] = absolute_start - start_ms

            kept_glyphs[glyph_id] = new_glyph

        self.glyphs.delete_keys(removed_keys)
        self.glyphs.update(kept_glyphs)
        self.glyphs.stop_batching()

        self.prepare_cropped_audio(self.full_song_path)
        self.save(immediate = True)

    def replace_glyph(
            self,
            identifier: int,
            data:       dict
        ) -> None:

        self.glyphs[identifier] = data

    def delete_glyph(self, identifier: int) -> None:
        del self.glyphs[identifier]

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

# Minimal Composition

class MinimalComposition(BaseComposition):
    def __init__(self, identifier: int) -> None:
        save_path = Utils.get_user_path(f"{identifier}/Save.json", "Cassette/Songs")

        with open(save_path, "r", encoding = "utf-8") as file_handle:
            settings = json.load(file_handle)

        super().__init__(identifier, settings)

        if not os.path.exists(self.full_song_path):
            Windows.ErrorWindow("Corrupted!", "This save is corrupted.").exec()

            return

        self.ensure_full_song_is_opus()

        if self.needs_cropped_audio():
            if not os.path.exists(self.cropped_song_path):
                self.prepare_cropped_audio(self.full_song_path)