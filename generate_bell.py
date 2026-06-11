import wave
import struct
import math
import os

def generate_sample_bell():
    sound_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'sounds')
    os.makedirs(sound_dir, exist_ok=True)
    filepath = os.path.join(sound_dir, 'bell_sample.wav')
    
    sample_rate = 44100.0
    duration = 2.0  # seconds
    frequency = 587.33  # D5 note (a nice high bell tone)

    with wave.open(filepath, 'w') as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(int(sample_rate))
        
        num_samples = int(sample_rate * duration)
        for i in range(num_samples):
            t = float(i) / sample_rate
            # Decays exponentially to sound like a bell ring
            decay = math.exp(-2.0 * t)
            
            # Simple additive synthesis for bell timbre:
            # Fundamental + overtone + high bell tinkle
            val = (
                0.5 * math.sin(2.0 * math.pi * frequency * t) +
                0.25 * math.sin(2.0 * math.pi * frequency * 2.0 * t) +
                0.15 * math.sin(2.0 * math.pi * frequency * 3.0 * t) +
                0.1 * math.sin(2.0 * math.pi * frequency * 4.2 * t)
            )
            
            # Apply decay and scale to 16-bit signed int range
            val = val * decay
            int_val = int(val * 32767)
            # Clip values to prevent overflow/distortion
            int_val = max(-32768, min(32767, int_val))
            
            data = struct.pack('<h', int_val)
            wav.writeframesraw(data)
            
    print(f"Generated sample bell sound at: {filepath}")

if __name__ == '__main__':
    generate_sample_bell()
