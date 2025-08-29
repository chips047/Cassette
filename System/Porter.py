import random
from System import Utils

from pathlib import Path
from copy import deepcopy

from System import Exporter
from System import GlyphEffects

from System.Constants import *

# yes, this function is ai generated AND DONT EVEN TALK ABOUT THIS FUNCTION, IT MAKES ME RAGE AND TRIGGERS ME, DONT EVER FUCKING REMING ME ABOUT THIS SH*T F**K
def port_segments_func(old_segments, new_segments, active, dup_threshold_ratio=0.5):
    if not active:
        return []

    if old_segments <= 1:
        k_pos = 0.0
    else:
        k_pos = (new_segments - 1) / (old_segments - 1)

    rounded = [round(a * k_pos) for a in active]
    rounded = [max(0, min(new_segments - 1, r)) for r in rounded]

    dup_count = sum(1 for i in range(1, len(rounded)) if rounded[i] == rounded[i-1])

    if dup_count >= dup_threshold_ratio * len(active):
        uniq = []
        for r in rounded:
            if not uniq or r != uniq[-1]:
                uniq.append(r)
        
        mapped = [uniq[0]]
        for i in range(1, len(uniq)):
            gap = max(1, uniq[i] - uniq[i-1])
            mapped.append(mapped[-1] + gap)
    
    else:
        mapped = [rounded[0]]
        for i in range(1, len(active)):
            gap_old = active[i] - active[i-1]
            gap_new = max(1, round(gap_old * k_pos))
            mapped.append(mapped[-1] + gap_new)

    if mapped[-1] > new_segments - 1:
        overflow = mapped[-1] - (new_segments - 1)
        mapped = [max(0, m - overflow) for m in mapped]

    final = []
    for m in mapped:
        mm = max(0, min(new_segments - 1, m))
        if not final or mm != final[-1]:
            final.append(mm)

    return final

# ("1", "2", "3", "number of randomizes" "random")
# (["1", "5"], ["2", "3"], ["6", "7"], "number of randomizes" "random")

maps = {
    "PHONE2A": {
        "to": {
            "PHONE3A": {
                "1": ["1"],
                "2": ["2"],
                "3": ["3"],
                
                "segmented_effects": {
                    "1": ["1"]
                }
            },
            
            "PHONE2": {
                "segmented_effects": {
                    "1": ["4"]
                },
                
                "1": [["1", "2", "3"], ["1", "2"], ["4", "5", "6"], ["7", "8", "9"], ["4", "5", "7", "8"], ["4", "5", "6", "7", "8", "9"], ["5", "8"], 1, "random"],
                "2": [["4", "5", "6"], ["7", "8", "9"], ["4", "5", "7", "8"], ["4", "5", "6", "7", "8", "9"], ["5", "8"], 1, "random"],
                "3": ["10", "11", 1, "random"]
            },
            
            "PHONE1": {
                "segmented_effects": {
                    "1": ["4"]
                },
                
                "1": ["1", "2"],
                "2": [[("3", 1), ("3", 3)], ["3"], [("3", 2), ("3", 4)], 1, "random"],
                "3": [("4", "5", 1)]
            }
        }
    },
    "PHONE3A": {
        "to": {
            "PHONE2A": {
                "1": ["1"],
                "2": ["2"],
                "3": ["3"],
                
                "3.1": ["3"],
                "3.2": ["3"],
                "3.3": ["3"],
                "3.4": ["3"],
                "3.5": ["3"],
                
                "segmented_effects": {
                    "1": ["1"],
                    "2": ["1"],
                    "3": ["1"]
                }
            },
            
            "PHONE1": {
                "1": [["1", "2"], [("3", 1), ("3", 3)], [("3", 2), ("3", 4)], 1, "random"],
                "2": [[("3", 1), ("3", 3)], ["3"], [("3", 2), ("3", 4)], 1, "random"],
                "3": [["4"], ["5"], 1, "random"],

                "segmented_effects": {
                    "1": ["4"],
                    "2": ["4"],
                    "3": ["4"]
                }
            },
            
            "PHONE2": {
                "1": [["1", "2", "3"], ["1", "2"], ["4", "5", "7", "8"], ["4", "5", "6", "7", "8", "9"], ["5", "8"], 1, "random"],
                "2": [["1", "2", "3"], ["1", "2"], ["4", "5", "7", "8"], ["4", "5", "6", "7", "8", "9"], ["5", "8"], 1, "random"],
                "3": [["10"], ["11"], 1, "random"],

                "segmented_effects": {
                    "1": ["4"],
                    "2": ["4"],
                    "3": ["10"]
                }
            }
        }
    },
    "PHONE1": {
        "to": {
            "PHONE2": {
                "1": ["1", "2"],
                "2": ["3"],
                "3": ["4", "5", "6", "7", "8", "9"],
                "3.1": ["4"],
                "3.2": ["5", "6"],
                "3.3": ["7"],
                "3.4": ["8", "9"],
                "4": ["10"],
                "5": ["11"],
                
                "segmented_effects": {
                    "4": ["10"]
                }
            }
        }
    },
    "PHONE2": {
        "to": {
            "PHONE1": {
                "1": ["1"],
                "2": ["1"],
                "3": ["2"],
                "4": ("3", 1),
                "5": ("3", 2),
                "6": ("3", 2),
                "7": ("3", 3),
                "8": ("3", 4),
                "9": ("3", 4),
                "10": ["4"],
                "11": ["5"],
                
                "segmented_effects": {
                    "4": ["4"],
                    "10": ["4"]
                }
            }
        }
    }
}

class Port:
    @staticmethod
    def unpack_labels(labels: str) -> list[list[str]]:
        return [line.split("\t") for line in labels.splitlines()]
    
    @staticmethod
    def randomize(tracks):
        randomizes = tracks[-2]
        variants = tracks[:-2]
        tracks = []

        for _ in range(randomizes):
            variant = random.choice(variants)

            if isinstance(variant, list):
                tracks.extend(variant)
                
            else:
                tracks.append(variant)
        
        return tracks

    @staticmethod
    def _process_tracks(tracks, glyph, port_from, port_to, composition, ported_labels, port_segments = True):
        original_track = glyph["track"]

        if "segments" in glyph and port_segments:
            port_track = maps[port_from]["to"][port_to]["segmented_effects"][original_track][0]
            port_from_segments = is_segmented(original_track, port_from)
            port_to_segments = is_segmented(port_track, port_to)
            ported_segments = port_segments_func(port_from_segments, port_to_segments, glyph["segments"])

            glyph["segments"] = ported_segments

        if "random" in tracks:
            tracks = Port.randomize(tracks)
        
        if "segments" in glyph and port_segments and "effect" in glyph:
            ported_labels.extend(
                GlyphEffects.effect_to_label(
                    glyph, 
                    glyph["effect"], 
                    port_to, 
                    composition.bpm, 
                    port_track
                )
            )
        
        elif "segments" in glyph and port_segments:
            for segment in glyph["segments"]:
                ported_labels.append(
                    GlyphEffects._format_entry(
                        glyph['start'] / 1000,
                        (glyph['start'] + glyph['duration']) / 1000,
                        f"{port_track}.{segment + 1}-{glyph['brightness']}-LIN"
                    )
                )
        
        elif "effect" in glyph:
            for track in tracks:
                if isinstance(track, list) and port_segments:
                    if isinstance(track[0], list):
                        glyph["segments"] = [track[0][-1]]
                
                if "segments" in glyph and not port_segments:
                    del glyph["segments"]

                if GlyphEffects.EffectsConfig[glyph["effect"]["name"]]["segmented"]: 
                    track = [maps[port_from]["to"][port_to]["segmented_effects"][original_track][0]] 
                
                print(f"LOOOL {track[0] if isinstance(track, tuple) else track}")

                ported_labels.extend(
                    GlyphEffects.effect_to_label(glyph, glyph["effect"], port_to, composition.bpm, track[0] if isinstance(track, tuple) or isinstance(track, list) else track)
                )
                print(ported_labels[-1])
        
        else:
            for track in tracks:
                if isinstance(track, tuple):
                    glyph["segments"] = [track[0][-1]]
                    track = track[0][0]

                ported_labels.append(
                    GlyphEffects._format_entry(
                        glyph['start'] / 1000,
                        (glyph['start'] + glyph['duration']) / 1000,
                        f"{track}-{glyph['brightness']}-LIN"
                    )
                )
    
    @staticmethod
    def port(port_from: str, port_to: str, composition, port_segments):
        only_singles, only_effects = composition.sorted_glyphs()
        singles = [deepcopy(g) for g in only_singles]
        effects = [deepcopy(g) for g in only_effects]

        ported_labels = []

        for glyph in singles:
            tracks = maps[port_from]["to"][port_to][glyph["track"]]
            Port._process_tracks(tracks, glyph, port_from, port_to, composition, ported_labels, port_segments)

        for glyph in effects:
            if glyph["effect"]["settings"]["segmented"]:
                tracks = maps[port_from]["to"][port_to]["segmented_effects"][glyph["track"]]
            
            else:
                tracks = maps[port_from]["to"][port_to][glyph["track"]]
            
            Port._process_tracks(tracks, glyph, port_from, port_to, composition, ported_labels, port_segments)

        return ported_labels, port_to

    @staticmethod
    def export_port(label_list, model: str, duration: float, song_id: int):
        labels = "\n".join(label_list)
        labels = (
            "0.000000\t0.000000\tLABEL_VERSION=1\n"
            f"0.000000\t0.000000\tPHONE_MODEL={model}\n"
            f"{labels}\n"
            f"{Exporter.f6(duration)}\t{Exporter.f6(duration)}\tEND"
        )

        cache_path = Path(Utils.get_cache_path("Labels.txt"))
        with cache_path.open("w+", encoding="utf-8") as f:
            f.write(labels)

        Exporter.compile_glyph_file(str(cache_path), Utils.get_cache_path(""))
        Exporter.nglyph_to_ogg(
            Utils.get_songs_path(f"{song_id}/cropped_song.ogg"),
            Utils.get_cache_path("Labels.cassette"),
            Utils.get_songs_path(str(song_id)),
            f"Ported_withCassette_{model}"
        )