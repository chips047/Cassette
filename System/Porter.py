import json
import random
from loguru import logger
from System import Utils
from System import Exporter

from copy import deepcopy

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

maps = {
    "PHONE2A": {
        "to": {
            "PHONE3A": {
                "1": ["1"],
                "2": ["2"],
                "3": ["3"],

                "effects": {
                    "segments": {
                        "1": ["1"]
                    }
                }
            },
            
            "PHONE2": {
                "effects": {
                    "segments": {
                        "1": ["4"]
                    }
                },

                "1": {
                    "mode": "random",
                    "variants": [
                        ["1", "2", "3"],
                        ["4", "5", "6", "7", "8", "9"],
                        ["1", "2"],
                        ["3"]
                    ],
                    "randomize": 1
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        ["4", "5", "6"],
                        ["7", "8", "9"],
                        ["4", "5", "6", "7", "8", "9"],
                        ["5", "8"]
                    ],
                    "randomize": 1
                },

                "3": {
                    "mode": "random",
                    "variants": [
                        ["10"],
                        ["11"],
                        ["10", "11"]
                    ],
                    "randomize": 1
                }
            },
            
            "PHONE1": {
                "effects": {
                    "segments": {
                        "1": ["4"]
                    }
                },

                "1": {
                    "mode": "random",
                    "variants": [
                        ["1"],
                        ["2"],
                        ["1", "2"]
                    ],
                    "randomize": 1
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        [("3", 0), ("3", 2)],
                        [("3", 1), ("3", 3)],
                        ["3"],
                        ["3", "5"]
                    ],
                    "randomize": 1
                },
                
                "3": {
                    "mode": "random",
                    "variants": [
                        ["4"],
                        ["4", "5"]
                    ],
                    "randomize": 1
                }
            }
        }
    },
    "PHONE3A": {
        "to": {
            "PHONE2A": {
                "1": ["1"],
                "2": ["2"],
                "3": ["3"],
                
                "effects": {
                    "segments": {
                        "1": ["1"],
                        "2": ["1"],
                        "3": ["1"]
                    }
                },
            },
            
            "PHONE1": {
                "1": {
                    "mode": "random",
                    "variants": [
                        ["1", "2"],
                        [("3", 0), ("3", 2)],
                        [("3", 1), ("3", 3)]
                    ]
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        [("3", 0), ("3", 2)],
                        [("3", 1), ("3", 3)],
                        ["3"]
                    ]
                },

                "3": {
                    "mode": "random",
                    "variants": [
                        ["4"],
                        ["5"],
                        ["4", "5"]
                    ]
                },

                "effects": {
                    "segments": {
                        "1": ["4"],
                        "2": ["4"],
                        "3": ["4"]
                    }
                },
            },
            
            "PHONE2": {
                "1": {
                    "mode": "random",
                    "variants": [
                        ["1", "2", "3"],
                        ["1", "2"],
                        ["3"]
                    ],
                    "randomizes": 1
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        ["4", "5", "6", "7", "8", "9"],
                        ["5", "8"],
                        ["6", "9"],
                        ["4", "7"]
                    ],
                    "randomizes": 1
                },

                "3": {
                    "mode": "random",
                    "variants": [
                        ["10"],
                        ["11"],
                        ["10", "11"]
                    ],
                    "randomizes": 1
                },

                "effects": {
                    "segments": {
                        "1": ["4"],
                        "2": ["4"],
                        "3": ["10"]
                    }
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
                "4": ["10"],
                "5": ["11"],
                
                "effects": {
                    "segments": {
                        "4": ["10"]
                    }
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
                "4": [("3", 0)],
                "5": [("3", 1)],
                "6": [("3", 1)],
                "7": [("3", 2)],
                "8": [("3", 3)],
                "9": [("3", 3)],
                "10": ["4"],
                "11": ["5"],

                "effects": {
                    "segments": {
                        "4": ["4"],
                        "10": ["4"]
                    }
                }
            }
        }
    }
}

class Port:
    def randomize(variants):
        return random.choice(variants)
    
    def process_dict_track(glyph, track):
        logger.info(f"Track is a dict: {track}")
        mode = track.get("mode")

        if mode == "random":
            variants = track.get("variants")

            target_track = Port.randomize(variants)
        
        return target_track

    def get_target_track(port_from, port_to, glyph):
        from_track = glyph["track"]
        model_map = maps[port_from]["to"][port_to]

        track = model_map[from_track]

        if "effect" in glyph:
            logger.warning(f'Effect is segmented. {glyph["effect"]["settings"]["segmented"]}')

            if glyph["effect"]["settings"]["segmented"]:
                return model_map["effects"]["segments"][from_track]
        
        if "segments" in glyph:
            return model_map["effects"]["segments"][from_track]

        if isinstance(track, list):
            if isinstance(track[0], dict):
                logger.info(f"Track is a list of dicts: {track}. Randomizing the variant...")
                target_track = Port.process_dict_track(glyph, random.choice(track))

            else:
                logger.info(f"Track is a list: {track}")
                target_track = track
            
        elif isinstance(track, dict):
            logger.info(f"Track is a dict: {track}, fetching needed track")
            target_track = Port.process_dict_track(glyph, track)

        return target_track

    def port_glyphs(port_to: str, composition):
        only_singles, only_effects = composition.sorted_glyphs()

        ported_glyphs = []

        singles = [deepcopy(g) for g in only_singles]
        effects = [deepcopy(g) for g in only_effects]

        # model to model -> dict ["track"] -> x
        # if x is list -> list of tracks to add
        # if x is tuple -> ("track", segment)

        # if x is dict -> 
        # if mode in dict: mode: random / effect
        # mode: random. variants: list of lists of tracks. randomizes: number of randomizations.
        # mode: effect. track: track to apply effect to. trigger_effect: replace if glyph["effect"] == trigger_effect. to_effect: effect to apply.

        for effect in effects:
            target_track = Port.get_target_track(composition.model, port_to, effect)
            logger.warning(f"RESULT TRACK: {target_track}")

            if "segments" in effect:
                port_segments_from = ModelSegments[composition.model][effect["track"]]
                port_segments_to = ModelSegments[port_to][target_track[0]]
                ported_segments = port_segments_func(port_segments_from, port_segments_to, effect["segments"])

                effect["track"] = target_track[0]
                effect["segments"] = ported_segments

                list_of_glyphs = GlyphEffects.effect_to_glyph(effect, port_to, composition.bpm)
                ported_glyphs.extend(list_of_glyphs)
                logger.error(f"Extending 1: {list_of_glyphs}")
            
            for track in target_track:
                if isinstance(track, tuple):
                    track, segment = track
                    effect["segments"] = [segment]
                
                effect["track"] = track
                logger.warning(f"Generating effect: {effect['track']}, segments: {effect.get('segments')}")

                list_of_glyphs = GlyphEffects.effect_to_glyph(effect, port_to, composition.bpm)
                ported_glyphs.extend(list_of_glyphs)
                logger.error(f"Extending 2: {list_of_glyphs}")

        for single in singles:
            target_track = Port.get_target_track(composition.model, port_to, single)
            logger.warning(f"RESULT TRACK: {target_track}")

            if "segments" not in single:
                for track in target_track:
                    if isinstance(track, tuple):
                        print(track)
                        track, segment = track
                        single["segments"] = [segment]
                    
                    print(track)
                    single["track"] = track

                    logger.warning(f"Adding a simple glyph: {single['track']}, segments: {single.get('segments')}")
                    ported_glyphs.append(single)
                    logger.error(f"Extending 3: {single}")
            
            else:
                target_track = Port.get_target_track(composition.model, port_to, single)
                logger.warning(f"RESULT TRACK: {target_track}")

                port_segments_from = ModelSegments[composition.model][single["track"]]
                port_segments_to = ModelSegments[port_to][target_track[0]]
                ported_segments = port_segments_func(port_segments_from, port_segments_to, single["segments"])

                single["track"] = target_track[0]
                single["segments"] = ported_segments

                logger.warning(f"Adding a complex glyph: {single['track']}, segments: {single.get('segments')}")
                ported_glyphs.append(single)
                logger.error(f"Extending 4: {single}")

        with open("data.json", "w", encoding="utf-8") as f:
            json.dump({"list": ported_glyphs}, f, ensure_ascii=False, indent=4)
        
        return ported_glyphs
    
    def export_port(port_from: str, port_to: str, composition):
        ported_glyphs = Port.port_glyphs(port_from, port_to, composition)
        Exporter.glyphs_to_ogg()