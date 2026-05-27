import numpy
import math

#pythran export process_waveform_tile(float32[:,:], int, float, float, float, float)

def process_waveform_tile(
        chunk:          numpy.ndarray,
        tile_width:     int,
        samples_per_px: float,
        height:         float,
        global_max:     float,
        sigma:          float
    ) -> numpy.ndarray:

    sample_count = chunk.shape[0]
    
    if sample_count == 0:
        return numpy.zeros((0, 2), dtype = numpy.float32)

    res_top    = numpy.zeros(tile_width, dtype = numpy.float32)
    res_bottom = numpy.zeros(tile_width, dtype = numpy.float32)

    center_y = height / 2.0
    inv_max  = 1.0 / (global_max if global_max > 1e-6 else 1e-6)

    for i in range(tile_width):
        start_idx = int(i * samples_per_px)
        end_idx   = int((i + 1) * samples_per_px)
        
        if start_idx >= sample_count:
            res_top[i]    = center_y
            res_bottom[i] = center_y
            continue
            
        if end_idx > sample_count:
            end_idx = sample_count

        pixel_chunk = chunk[start_idx:end_idx]
        
        if pixel_chunk.size > 0:
            current_max = numpy.max(pixel_chunk)
            current_min = numpy.min(pixel_chunk)
        
        else:
            current_max = 0.0
            current_min = 0.0

        res_top[i]    = center_y - (current_max * inv_max * center_y)
        res_bottom[i] = center_y - (current_min * inv_max * center_y)

    if sigma > 0.1:
        res_top    = apply_simple_smooth(res_top,    sigma)
        res_bottom = apply_simple_smooth(res_bottom, sigma)

    for i in range(tile_width):
        if res_top[i] > res_bottom[i]:
            avg = (res_top[i] + res_bottom[i]) / 2.0
            res_top[i]    = avg
            res_bottom[i] = avg

    result = numpy.zeros((tile_width, 2), dtype = numpy.float32)
    
    for i in range(tile_width):
        result[i, 0] = res_top[i]
        result[i, 1] = res_bottom[i]

    return result

def apply_simple_smooth(data: numpy.ndarray, sigma: float) -> numpy.ndarray:
    size   = data.shape[0]
    result = data.copy()
    radius = int(sigma * 2)
    if radius < 1: return result

    # Simple box blur is extremely fast in Pythran and looks similar for waveforms
    for i in range(radius, size - radius):
        val = 0.0
        for j in range(i - radius, i + radius + 1):
            val += data[j]
        result[i] = val / (2.0 * radius + 1.0)
    return result