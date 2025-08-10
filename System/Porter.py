import random
from System import Utils

from copy import deepcopy

from System import Exporter
from System import GlyphEffects

def gen_map(glyph_number_1, glyph_number_2, glyph_count_1, glyph_count_2):
    factor = glyph_count_2 / glyph_count_1
    result = {}
    
    for i in range(1, glyph_count_1):
        key = f"{glyph_number_1}.{i}"
        val = round(i * factor)
        result[key] = f"{glyph_number_2}.{val}"
    
    return result

maps = {
    "PHONE2A": {
        "to": {
            "PHONE3A": {
                "1": "1",
                "2": "2",
                "3": "3",
                
                **gen_map(1, 1, 24, 20),
                
                "segmented_effects": {
                    "1": "1"
                }
            },
            
            "PHONE2": {
                **gen_map(1, 4, 24, 16),
                
                "segmented_effects": {
                    "1": "4"
                },
                
                "1": [(["1", "2", "3"], ["1", "2"], ["4", "5", "6"], ["7", "8", "9"], ["4", "5", "7", "8"], ["4", "5", "6", "7", "8", "9"], ["5", "8"])],
                "2": [(["4", "5", "6"], ["7", "8", "9"], ["4", "5", "7", "8"], ["4", "5", "6", "7", "8", "9"], ["5", "8"])],
                "3": [("10", "11", 1)]
            },
            
            "PHONE1": {
                **gen_map(1, 4, 24, 8),
                
                "segmented_effects": {
                    "1": "4"
                },
                
                "1": ["1", "2"],
                "2": [(["3.1", "3.3"], ["3"], ["3.2", "3.4"])],
                "3": [("4", "5", 1)]
            }
        }
    },
    "PHONE3A": {
        "to": {
            "PHONE2A": {
                "1": "1",
                "2": "2",
                "3": "3",
                
                **gen_map(1, 1, 20, 24),
                **gen_map(2, 1, 11, 24),
                
                "3.1": "3",
                "3.2": "3",
                "3.3": "3",
                "3.4": "3",
                "3.5": "3",
                
                "segmented_effects": {
                    "1": "1",
                    "2": "1",
                    "3": "1"
                }
            },
            
            "PHONE1": {
                "1": [(["1", "2"], ["3.1", "3.3"], ["3.2", "3.4"])],
                "2": [(["3.1", "3.3"], ["3"], ["3.2", "3.4"])],
                "3": [("4", "5", 1)],
                
                **gen_map(1, 4, 20, 8),
                **gen_map(2, 4, 11, 8),
                **gen_map(3, 4, 5, 8),
                
                "segmented_effects": {
                    "1": "4",
                    "2": "4",
                    "3": "4"
                }
            },
            
            "PHONE2": {
                "1": [(["1", "2", "3"], ["1", "2"], ["4", "5", "6"], ["7", "8", "9"], ["4", "5", "7", "8"], ["4", "5", "6", "7", "8", "9"], ["5", "8"])],
                "2": [(["1", "2", "3"], ["1", "2"], ["4", "5", "6"], ["7", "8", "9"], ["4", "5", "7", "8"], ["4", "5", "6", "7", "8", "9"], ["5", "8"])],
                "3": [("10", "11", 1)],
                
                **gen_map(1, 4, 20, 16),
                **gen_map(2, 4, 11, 16),
                **gen_map(3, 10, 5, 8),
                
                "segmented_effects": {
                    "1": "4",
                    "2": "4",
                    "3": "10"
                }
            }
        }
    },
    "PHONE1": {
        "to": {
            "PHONE2": {
                "1": ["1", "2"],
                "2": "3",
                "3": ["4", "5", "6", "7", "8", "9"],
                "3.1": "4",
                "3.2": ["5", "6"],
                "3.3": "7",
                "3.4": ["8", "9"],
                
                **gen_map(4, 10, 8, 8),
                
                "5": "11",
                
                "segmented_effects": {
                    "4": "10"
                }
            }
        }
    },
    "PHONE2": {
        "to": {
            "PHONE1": {
                "1": "1",
                "2": "1",
                "3": "2",
                "4": "3.1",
                "5": "3.2",
                "6": "3.2",
                "7": "3.3",
                "8": "3.4",
                "9": "3.4",
                
                **gen_map(4, 4, 16, 8),
                **gen_map(10, 4, 8, 8),
                
                "11": "5",
                
                "segmented_effects": {
                    "4": "4",
                    "10": "4"
                }
            }
        }
    }
}

class Port:
    def unpack_labels(labels):
        labels = labels.split("\n")
        labels = [(label.split("\t")) for label in labels]
        
        return labels
    
    def port(port_from, port_to, composition):
        only_singles, only_effects, _ = composition.sorted_glyphs()
        singles = [deepcopy(g) for g in only_singles]
        effects = [deepcopy(g) for g in only_effects]
        
        ported_labels = []
        
        for glyph in singles:
            tracks = maps[port_from]["to"][port_to][glyph["track"]]
            
            if isinstance(tracks, list):
                if any(isinstance(x, tuple) for x in tracks):
                    if isinstance(tracks[0][-1], int):
                        tracks = [random.choice(tracks[0][:-1]) for i in range(tracks[0][-1])]
                        tracks = list(set(tracks))
                    
                    else:
                        tracks = random.choice(tracks[0])

                for element in tracks:
                    ported_labels.append(f"{(glyph['start'] / 1000):.6f}\t{((glyph['start'] + glyph['duration']) / 1000):.6f}\t{element}-{glyph['brightness']}-LIN")
                
                continue
            
            glyph["track"] = tracks
            ported_labels.append(f"{(glyph['start'] / 1000):.6f}\t{((glyph['start'] + glyph['duration']) / 1000):.6f}\t{glyph['track']}-{glyph['brightness']}-LIN")
        
        for glyph in effects:
            if glyph["effect"]["settings"]["segmented"]:
                tracks = maps[port_from]["to"][port_to]["segmented_effects"][glyph["track"]]
            
            else:
                tracks = maps[port_from]["to"][port_to][str(int(glyph["track"]))]
            
            if isinstance(tracks, list):
                if any(isinstance(x, tuple) for x in tracks):
                    if isinstance(tracks[0][-1], int):
                        tracks = [random.choice(tracks[0][:-1]) for i in range(tracks[0][-1])]
                        tracks = list(set(tracks))
                    
                    else:
                        tracks = random.choice(tracks[0])
                
                for element in tracks:
                    glyph["track"] = element
                    ported_labels.extend(GlyphEffects.effect_to_label(glyph, glyph["effect"], port_to, composition.bpm, tracks))
                
                continue
            
            glyph["track"] = tracks
            ported_labels.extend(GlyphEffects.effect_to_label(glyph, glyph["effect"], port_to, composition.bpm, tracks))
        
        return ported_labels, port_to
    
    def export_port(label_list, model, duration, id):
        labels = "\n".join(label_list)
        labels = f"0.000000\t0.000000\tLABEL_VERSION=1\n0.000000\t0.000000\tPHONE_MODEL={model}\n{labels}\n{Exporter.f6(duration)}\t{Exporter.f6(duration)}\tEND"
    
        labels_file = open(Utils.get_cache_path("Labels.txt"), "w+")
        labels_file.write(labels)
        labels_file.close()
        
        Exporter.compile_glyph_file(Utils.get_cache_path("Labels.txt"), Utils.get_cache_path(""))
        Exporter.nglyph_to_ogg(Utils.get_songs_path(f"{id}/cropped_song.ogg"), Utils.get_cache_path("Labels.cassette"), Utils.get_songs_path(str(id)), f"Ported_withCassette_{model}")