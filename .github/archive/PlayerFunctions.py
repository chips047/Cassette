import math
import numpy

#pythran export resample_block(float32[:, :], float64, float64, float64[:], int)
#pythran export apply_biquad_block(float32[:, :], float64, float64, float64, float64, float64, float64[:, :])
#pythran export apply_bitcrush_block(float32[:, :], float64, int, int)
#pythran export calculate_lowshelf_coefficients(float64, float64, float64)
#pythran export calculate_peaking_coefficients(float64, float64, float64, float64)
#pythran export calculate_highshelf_coefficients(float64, float64, float64)
#pythran export calculate_bandpass_coefficients(float64, float64, float64)
#pythran export apply_eq_triple(float32[:, :], float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64, float64[:, :], float64[:, :], float64[:, :])
#pythran export apply_reverb_block(float32[:, :], float32[:, :], float32[:, :], float64)
#pythran export mix_audio_blocks(float32[:, :], float32[:, :], float64)
#pythran export apply_noise_mix(float32[:, :], float64)
#pythran export generate_colored_noise(int, int, str)
#pythran export apply_glitch_noise_block(float32[:, :], int, int, str)
#pythran export process_ui_sound_fast(float32[:,:], float64, float64, int, bool)
#pythran export process_ui_sound_interp(float32[:,:], float64, float64, float64, int, bool)

# Resampling

def resample_block(
        data:     numpy.ndarray,
        position: float,
        speed:    float,
        delays:   numpy.ndarray,
        frames:   int
    ) -> numpy.ndarray:

    total_samples = data.shape[0]
    channels      = data.shape[1]

    if frames <= 0 or total_samples <= 0:
        return numpy.zeros((max(frames, 0), channels), dtype = numpy.float32)

    result    = numpy.zeros((frames, channels), dtype = numpy.float32)
    max_index = total_samples - 1

    for frame_index in range(frames):
        base_position = position + frame_index * speed

        for channel_index in range(channels):
            delayed_position = base_position - delays[channel_index]
            integer_index    = int(delayed_position)

            if integer_index < 0:
                continue

            if integer_index >= max_index:
                result[frame_index, channel_index] = data[max_index, channel_index]
                continue

            fraction = delayed_position - integer_index
            sample_0 = data[integer_index,     channel_index]
            sample_1 = data[integer_index + 1, channel_index]

            result[frame_index, channel_index] = sample_0 + fraction * (sample_1 - sample_0)

    return result

# Processing

def apply_biquad_block(
        block:  numpy.ndarray,
        b0:     float,
        b1:     float,
        b2:     float,
        a1:     float,
        a2:     float,
        states: numpy.ndarray
    ) -> numpy.ndarray:

    frames   = block.shape[0]
    channels = block.shape[1]

    if frames <= 0 or channels <= 0:
        return block.astype(numpy.float32)

    result = numpy.empty((frames, channels), dtype = numpy.float32)

    for channel_index in range(channels):
        x1 = states[channel_index, 0]
        x2 = states[channel_index, 1]
        y1 = states[channel_index, 2]
        y2 = states[channel_index, 3]

        for frame_index in range(frames):
            x0 = float(block[frame_index, channel_index])
            y0 = (b0 * x0) + (b1 * x1) + (b2 * x2) - (a1 * y1) - (a2 * y2)

            result[frame_index, channel_index] = y0

            x2 = x1
            x1 = x0
            y2 = y1
            y1 = y0

        states[channel_index, 0] = x1
        states[channel_index, 1] = x2
        states[channel_index, 2] = y1
        states[channel_index, 3] = y2

    return result

def apply_bitcrush_block(
        block:      numpy.ndarray,
        mix:        float,
        bits:       int,
        downsample: int
    ) -> numpy.ndarray:

    if mix <= 0.0:
        return block.astype(numpy.float32)

    frames   = block.shape[0]
    channels = block.shape[1]

    if frames <= 0 or channels <= 0:
        return block.astype(numpy.float32)

    if bits < 1:
        bits = 1
    
    elif bits > 24:
        bits = 24

    if downsample < 1:
        downsample = 1

    levels  = float((1 << bits) - 1)
    inverse = 1.0 / levels
    crushed = numpy.empty_like(block)

    if downsample == 1:
        for frame_index in range(frames):
            for channel_index in range(channels):
                sample = float(block[frame_index, channel_index])
                value  = round((sample + 1.0) * 0.5 * levels) * inverse

                crushed[frame_index, channel_index] = (value * 2.0) - 1.0

    else:
        for hold_index in range(0, frames, downsample):
            hold_limit = min(hold_index + downsample, frames)

            for current_frame in range(hold_index, hold_limit):
                for channel_index in range(channels):
                    sample = float(block[hold_index, channel_index])
                    value  = round((sample + 1.0) * 0.5 * levels) * inverse

                    crushed[current_frame, channel_index] = (value * 2.0) - 1.0

    if mix >= 1.0:
        return crushed

    return (block * (1.0 - mix)) + (crushed * mix)

# Coefficients

def calculate_bandpass_coefficients(
        center_hz:   float,
        q:           float,
        sample_rate: float
    ) -> tuple[float, float, float, float, float, float]:

    if sample_rate <= 0.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0

    omega  = 2.0 * math.pi * (center_hz / sample_rate)
    sine   = math.sin(omega)
    cosine = math.cos(omega)
    alpha  = sine / (2.0 * q)

    b0 =  alpha
    b1 =  0.0
    b2 = -alpha
    a0 =  1.0 + alpha
    a1 = -2.0 * cosine
    a2 =  1.0 - alpha

    if a0 == 0.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0

    inverse_a0 = 1.0 / a0

    return (
        b0 * inverse_a0,
        b1 * inverse_a0,
        b2 * inverse_a0,
        a1 * inverse_a0,
        a2 * inverse_a0,
        inverse_a0
    )

def calculate_peaking_coefficients(
        center_hz:   float,
        gain:        float,
        q:           float,
        sample_rate: float
    ) -> tuple[float, float, float, float, float, float]:

    if sample_rate <= 0.0 or q <= 0.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0

    if gain <= 0.0:
        gain = 0.001

    omega  = 2.0 * math.pi * (center_hz / sample_rate)
    sine   = math.sin(omega)
    cosine = math.cos(omega)
    alpha  = sine / (2.0 * q)

    b0 =  1.0 + alpha * gain
    b1 = -2.0 * cosine
    b2 =  1.0 - alpha * gain
    a0 =  1.0 + alpha / gain
    a1 = -2.0 * cosine
    a2 =  1.0 - alpha / gain

    if a0 == 0.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0

    inverse_a0 = 1.0 / a0

    return (
        b0 * inverse_a0,
        b1 * inverse_a0,
        b2 * inverse_a0,
        a1 * inverse_a0,
        a2 * inverse_a0,
        inverse_a0
    )

def calculate_lowshelf_coefficients(
        center_hz:   float,
        gain:        float,
        sample_rate: float
    ) -> tuple[float, float, float, float, float, float]:

    if sample_rate <= 0.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0

    if gain <= 0.0:
        gain = 0.001

    omega     = 2.0 * math.pi * (center_hz / sample_rate)
    sine      = math.sin(omega)
    cosine    = math.cos(omega)
    amplitude = math.sqrt(gain)
    beta      = math.sqrt(amplitude) / 0.707

    b0 =  amplitude * ((amplitude + 1.0) - (amplitude - 1.0) * cosine + beta * sine)
    b1 =  2.0 * amplitude * ((amplitude - 1.0) - (amplitude + 1.0) * cosine)
    b2 =  amplitude * ((amplitude + 1.0) - (amplitude - 1.0) * cosine - beta * sine)
    a0 =  (amplitude + 1.0) + (amplitude - 1.0) * cosine + beta * sine
    a1 = -2.0 * ((amplitude - 1.0) + (amplitude + 1.0) * cosine)
    a2 =  (amplitude + 1.0) + (amplitude - 1.0) * cosine - beta * sine

    if a0 == 0.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0

    inverse_a0 = 1.0 / a0

    return (
        b0 * inverse_a0,
        b1 * inverse_a0,
        b2 * inverse_a0,
        a1 * inverse_a0,
        a2 * inverse_a0,
        inverse_a0
    )

def calculate_highshelf_coefficients(
        center_hz:   float,
        gain:        float,
        sample_rate: float
    ) -> tuple[float, float, float, float, float, float]:

    if sample_rate <= 0.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0

    if gain <= 0.0:
        gain = 0.001

    omega     = 2.0 * math.pi * (center_hz / sample_rate)
    sine      = math.sin(omega)
    cosine    = math.cos(omega)
    amplitude = math.sqrt(gain)
    beta      = math.sqrt(amplitude) / 0.707

    b0 =  amplitude * ((amplitude + 1.0) + (amplitude - 1.0) * cosine + beta * sine)
    b1 = -2.0 * amplitude * ((amplitude - 1.0) + (amplitude + 1.0) * cosine)
    b2 =  amplitude * ((amplitude + 1.0) + (amplitude - 1.0) * cosine - beta * sine)
    a0 =  (amplitude + 1.0) - (amplitude - 1.0) * cosine + beta * sine
    a1 =  2.0 * ((amplitude - 1.0) - (amplitude + 1.0) * cosine)
    a2 =  (amplitude + 1.0) - (amplitude - 1.0) * cosine - beta * sine

    if a0 == 0.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0

    inverse_a0 = 1.0 / a0

    return (
        b0 * inverse_a0,
        b1 * inverse_a0,
        b2 * inverse_a0,
        a1 * inverse_a0,
        a2 * inverse_a0,
        inverse_a0
    )

# EQ Processing

def apply_eq_triple(
        block:          numpy.ndarray,
        eq_low:         float,
        eq_mid:         float,
        eq_high:        float,
        low_b0:         float,
        low_b1:         float,
        low_b2:         float,
        low_a1:         float,
        low_a2:         float,
        mid_b0:         float,
        mid_b1:         float,
        mid_b2:         float,
        mid_a1:         float,
        mid_a2:         float,
        high_b0:        float,
        high_b1:        float,
        high_b2:        float,
        high_a1:        float,
        high_a2:        float,
        eq_low_states:  numpy.ndarray,
        eq_mid_states:  numpy.ndarray,
        eq_high_states: numpy.ndarray
    ) -> numpy.ndarray:

    if (abs(eq_low - 1.0) < 0.01 and 
        abs(eq_mid - 1.0) < 0.01 and 
        abs(eq_high - 1.0) < 0.01):
        return block

    result = block.copy()

    if abs(eq_low - 1.0) >= 0.01:
        result = apply_biquad_block(
            result,
            low_b0, low_b1, low_b2,
            low_a1, low_a2,
            eq_low_states
        )

    if abs(eq_mid - 1.0) >= 0.01:
        result = apply_biquad_block(
            result,
            mid_b0, mid_b1, mid_b2,
            mid_a1, mid_a2,
            eq_mid_states
        )

    if abs(eq_high - 1.0) >= 0.01:
        result = apply_biquad_block(
            result,
            high_b0, high_b1, high_b2,
            high_a1, high_a2,
            eq_high_states
        )

    return result

# Reverb

def apply_reverb_block(
        block:         numpy.ndarray,
        tap_one:       numpy.ndarray,
        tap_two:       numpy.ndarray,
        reverb_mix:    float
    ) -> numpy.ndarray:

    reverb_signal = (tap_one * 0.6) + (tap_two * 0.3)
    return (block * (1.0 - reverb_mix)) + (reverb_signal * reverb_mix)

# Mixing

def mix_audio_blocks(
        block_a: numpy.ndarray,
        block_b: numpy.ndarray,
        mix:     float
    ) -> numpy.ndarray:

    return (block_a * (1.0 - mix)) + (block_b * mix)

def apply_noise_mix(
        block:     numpy.ndarray,
        noise_mix: float
    ) -> numpy.ndarray:

    if noise_mix <= 0.0:
        return block

    noise = numpy.random.normal(0.0, 0.15, block.shape).astype(numpy.float32)
    return (block * (1.0 - noise_mix)) + (noise * noise_mix)

# Noise Generation

def generate_colored_noise(
        frames:      int,
        channels:    int,
        noise_color: str
    ) -> numpy.ndarray:

    if frames <= 0 or channels <= 0:
        return numpy.zeros((max(frames, 0), max(channels, 0)), dtype = numpy.float32)

    white = numpy.random.normal(0.0, 1.0, (frames, channels)).astype(numpy.float32)

    if noise_color == "white":
        noise = white

    elif noise_color == "brown":
        noise = numpy.cumsum(white, axis = 0)

    else:
        noise = white.copy()

        for channel_index in range(channels):
            state = 0.0

            for frame_index in range(frames):
                state = (state * 0.94) + (noise[frame_index, channel_index] * 0.06)
                noise[frame_index, channel_index] = state

    noise -= numpy.mean(noise, axis = 0, keepdims = True)

    peak = float(numpy.max(numpy.abs(noise)))
    if peak < 1e-6:
        return numpy.zeros((frames, channels), dtype = numpy.float32)

    return (noise / peak).astype(numpy.float32) * 0.20

def apply_glitch_noise_block(
        block:       numpy.ndarray,
        frames:      int,
        channels:    int,
        noise_color: str
    ) -> numpy.ndarray:

    noise = generate_colored_noise(frames, channels, noise_color)
    noise_mix = 0.6
    return (block * (1.0 - noise_mix)) + (noise * noise_mix)

# UI Engine

def process_ui_sound_fast(data, position, volume, frames, loop):
    data_len    = data.shape[0]
    channels    = data.shape[1]
    out_block   = numpy.zeros((frames, channels), dtype = numpy.float32)
    active      = True
    current_pos = position
    volume_f    = float(volume)

    start_idx = int(current_pos)
    end_idx   = start_idx + frames

    if end_idx <= data_len:
        for i in range(frames):
            for c in range(channels):
                out_block[i, c] = data[start_idx + i, c] * volume_f
        current_pos += frames

    else:
        available = data_len - start_idx
        if available > 0:
            for i in range(available):
                for c in range(channels):
                    out_block[i, c] = data[start_idx + i, c] * volume_f
        
        current_pos += frames
        
        if not loop:
            active = False
        
        else:
            current_pos = float(current_pos % data_len)

    return out_block, float(current_pos), active

def process_ui_sound_interp(data, position, speed, volume, frames, loop):
    data_len    = data.shape[0]
    channels    = data.shape[1]
    out_block   = numpy.zeros((frames, channels), dtype = numpy.float32)
    active      = True
    current_pos = position
    volume_f    = float(volume)
    speed_f     = float(speed)

    for i in range(frames):
        idx1 = int(current_pos)
        idx2 = idx1 + 1
        
        if idx1 >= data_len - 1:
            if loop:
                current_pos = current_pos % data_len
                idx1 = int(current_pos)
                idx2 = idx1 + 1
            
            else:
                active = False
                break
        
        frac = current_pos - idx1
        
        for c in range(channels):
            v1 = data[idx1, c]
            
            if idx2 < data_len:
                v2 = data[idx2, c]
            else:
                v2 = 0.0

            out_block[i, c] = (v1 + (v2 - v1) * frac) * volume_f
            
        current_pos += speed_f

    return out_block, float(current_pos), active