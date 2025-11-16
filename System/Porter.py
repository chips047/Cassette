import random

from loguru import logger
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
                        "1": ["7"]
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
                        ["3", "5"],
                        ["4", "6"],
                        ["3", "4", "5", "6"],
                        ["3", "4", "5", "6", "7"]
                    ],
                    "randomize": 1
                },
                
                "3": {
                    "mode": "random",
                    "variants": [
                        ["7"],
                        ["7", "8"]
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
                        ["3", "5"],
                        ["4", "6"]
                    ]
                },

                "2": {
                    "mode": "random",
                    "variants": [
                        ["3", "5"],
                        ["4", "6"],
                        ["3", "4", "5", "6"]
                    ]
                },

                "3": {
                    "mode": "random",
                    "variants": [
                        ["7"],
                        ["8"],
                        ["7", "8"]
                    ]
                },

                "effects": {
                    "segments": {
                        "1": ["7"],
                        "2": ["7"],
                        "3": ["7"]
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
                "3": ["4", "5"],
                "4": ["5", "6"],
                "5": ["7", "8"],
                "6": ["8", "9"],
                "7": ["10"],
                "8": ["11"],
                
                "effects": {
                    "segments": {
                        "7": ["10"]
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
                "4": ["3"],
                "5": ["4"],
                "6": ["4"],
                "7": ["5"],
                "8": ["6"],
                "9": ["6"],
                "10": ["7"],
                "11": ["8"],

                "effects": {
                    "segments": {
                        "4": ["7"],
                        "10": ["7"]
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
    
    def _make_glyph(base_glyph, track, segments=None, copy_effects=False):
        new = base_glyph.copy()
        new["track"] = track

        if segments is None:
            new.pop("segments", None)
        
        else:
            new["segments"] = list(segments)

        if copy_effects and "effects" in new:
            new["effects"] = [e.copy() for e in new["effects"]]

        return new

    def port_glyphs(port_to: str, composition):
        only_singles, only_effects = composition.sorted_glyphs()

        ported_glyphs = []

        singles = only_singles
        effects = only_effects

        for effect in effects:
            target_track = Port.get_target_track(composition.model, port_to, effect)
            logger.warning(f"RESULT TRACK: {target_track}")

            if "segments" in effect:
                seg_src = ModelSegments[composition.model][effect["track"]]
                seg_dst = ModelSegments[port_to][target_track[0]]
                ported_segments = port_segments_func(seg_src, seg_dst, effect["segments"])

                eff_for_conversion = effect.copy()
                eff_for_conversion["track"] = target_track[0]
                eff_for_conversion["segments"] = ported_segments

                list_of_glyphs = GlyphEffects.effect_to_glyph(eff_for_conversion, composition.bpm, port_to)
                ported_glyphs.extend(list_of_glyphs)
                logger.warning(f"Extending 1: {list_of_glyphs}")

            for track in target_track:
                eff_copy = Port._make_glyph(effect, track, segments=None, copy_effects=True)

                if isinstance(track, tuple):
                    tr, segment = track
                    eff_copy["track"] = tr
                    eff_copy["segments"] = [segment]

                logger.warning(f"Generating effect: {eff_copy['track']}, segments: {eff_copy.get('segments')}")
                list_of_glyphs = GlyphEffects.effect_to_glyph(eff_copy, composition.bpm, port_to)
                ported_glyphs.extend(list_of_glyphs)
                logger.warning(f"Extending 2: {list_of_glyphs}")

        for single in singles:
            target_track = Port.get_target_track(composition.model, port_to, single)
            logger.warning(f"RESULT TRACK: {target_track}")

            if "segments" not in single:
                for track in target_track:
                    if isinstance(track, tuple):
                        tr, segment = track
                        new_glyph = Port._make_glyph(single, tr, segments=[segment])

                    else:
                        new_glyph = Port._make_glyph(single, track, segments=None)

                    logger.warning(f"Adding a simple glyph: {new_glyph['track']}, segments: {new_glyph.get('segments')}")
                    ported_glyphs.append(new_glyph)
                    logger.warning(f"Extending 3: {new_glyph}")

            else:
                chosen_target = target_track[0]
                port_segments_from = ModelSegments[composition.model][single["track"]]
                port_segments_to = ModelSegments[port_to][chosen_target]
                ported_segments = port_segments_func(port_segments_from, port_segments_to, single["segments"])

                new_single = Port._make_glyph(single, chosen_target, segments=ported_segments)
                logger.warning(f"Adding a complex glyph: {new_single['track']}, segments: {new_single.get('segments')}")
                ported_glyphs.append(new_single)
                logger.warning(f"Extending 4: {new_single}")
        
        return ported_glyphs