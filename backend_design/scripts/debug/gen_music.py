"""
Generate realistic instrumental music WAV files for the vehicle media player.

This script creates 10 tracks with:
- Multiple harmonic layers (melody + chords + bass + percussion)
- Musical chord progressions (I-V-vi-IV etc.)
- ADSR envelopes for natural instrument timbre
- Stereo output at 44100 Hz
- ~30 seconds per track

Run: python backend_design/scripts/gen_music.py
"""
import math
import os
import random
import struct
import wave

# ============================================================
# Audio constants
# ============================================================
SAMPLE_RATE = 44100
DURATION_SEC = 30  # seconds per track
BITS_PER_SAMPLE = 16
MAX_AMPLITUDE = 32767

# ============================================================
# Note frequency table (A4 = 440 Hz)
# ============================================================
NOTE_FREQS = {}
_BASE_NOTES = {
    "C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4,
    "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2,
}
for octave in range(1, 7):
    for name, semitone in _BASE_NOTES.items():
        midi = 12 * (octave + 1) + semitone  # MIDI note number
        NOTE_FREQS[f"{name}{octave}"] = 440.0 * (2 ** ((midi - 69) / 12.0))


# ============================================================
# Chord progressions (10 different moods)
# ============================================================
# Each progression: list of (root_note, chord_type) tuples
# chord_type: 'maj', 'min', '7', 'm7'
CHORD_PROGRESSIONS = [
    # Track 1: Pop/Upbeat - I-V-vi-IV in C
    [("C3", "maj"), ("G3", "maj"), ("A3", "min"), ("F3", "maj")],
    # Track 2: Jazz - ii-V-I-vi in D
    [("D3", "min"), ("G3", "7"), ("C3", "maj"), ("A3", "min")],
    # Track 3: Ballad - I-vi-IV-V in G
    [("G3", "maj"), ("E3", "min"), ("C3", "maj"), ("D3", "maj")],
    # Track 4: Rock - I-bVII-IV-I in A
    [("A3", "maj"), ("G3", "maj"), ("D3", "maj"), ("A3", "maj")],
    # Track 5: Classical - I-IV-V-I in F
    [("F3", "maj"), ("B3", "maj"), ("C3", "maj"), ("F3", "maj")],
    # Track 6: Blues - I-IV-I-V-IV-I in E
    [("E3", "7"), ("A3", "7"), ("E3", "7"), ("B3", "7"), ("A3", "7"), ("E3", "7")],
    # Track 7: Folk - I-IV-vi-V in D
    [("D3", "maj"), ("G3", "maj"), ("B3", "min"), ("A3", "maj")],
    # Track 8: Ambient - vi-IV-I-V in C
    [("A3", "min"), ("F3", "maj"), ("C3", "maj"), ("G3", "maj")],
    # Track 9: R&B - i-iv-v-VII in Am
    [("A3", "min"), ("D3", "min"), ("E3", "min"), ("G3", "maj")],
    # Track 10: Epic - I-VI-III-VII in C
    [("C3", "maj"), ("A3", "maj"), ("E3", "maj"), ("G3", "maj")],
]

# Scale patterns for melody generation
SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11, 12],
    "minor": [0, 2, 3, 5, 7, 8, 10, 12],
    "pentatonic": [0, 2, 4, 7, 9, 12],
}

# Tempos (BPM) for each track
TEMPOS = [120, 100, 80, 140, 90, 110, 130, 70, 105, 160]

# Track names
TRACK_NAMES = [
    "爱错 - 王力宏",
    "晴天 - 周杰伦",
    "起风了 - 买辣椒也用券",
    "夜曲 - 周杰伦",
    "稻香 - 周杰伦",
    "光年之外 - 邓紫棋",
    "说好不哭 - 周杰伦",
    "圈圈叉叉 - 蔡依林",
    "告白气球 - 周杰伦",
    "年少有为 - 李荣浩",
]


def get_chord_notes(root_note: str, chord_type: str) -> list[str]:
    """Get the notes in a chord given root note and chord type."""
    # Find the octave and note name
    note_name = root_note[:-1]
    octave = int(root_note[-1])

    intervals = {
        "maj": [0, 4, 7],
        "min": [0, 3, 7],
        "7": [0, 4, 7, 10],
        "m7": [0, 3, 7, 10],
    }

    base_semitone = _BASE_NOTES.get(note_name, 0)
    notes = []
    for interval in intervals.get(chord_type, [0, 4, 7]):
        total_semitone = base_semitone + interval
        extra_octave = 0
        while total_semitone > 2:
            total_semitone -= 12
            extra_octave += 1
        while total_semitone < -9:
            total_semitone += 12
            extra_octave -= 1

        # Find the note name
        for name, semi in _BASE_NOTES.items():
            if semi == total_semitone:
                notes.append(f"{name}{octave + extra_octave}")
                break

    return notes


def adsr_envelope(t: float, duration: float, attack: float = 0.01,
                  decay: float = 0.1, sustain_level: float = 0.7,
                  release: float = 0.05) -> float:
    """ADSR envelope for natural instrument sound."""
    if t < attack:
        return t / attack
    elif t < attack + decay:
        return 1.0 - (1.0 - sustain_level) * ((t - attack) / decay)
    elif t < duration - release:
        return sustain_level
    else:
        return max(0.0, sustain_level * (duration - t) / release)


def generate_tone(freq: float, duration: float, sample_rate: int = SAMPLE_RATE,
                  wave_type: str = "sine", harmonics: int = 3) -> list[float]:
    """Generate a tone with harmonics for richer sound."""
    n_samples = int(sample_rate * duration)
    samples = []

    for i in range(n_samples):
        t = i / sample_rate
        env = adsr_envelope(t, duration)

        value = 0.0
        if wave_type == "sine":
            # Add harmonics for a richer sound (like a piano/guitar)
            for h in range(1, harmonics + 1):
                amplitude = 1.0 / (h * h)  # harmonics decay quickly
                value += amplitude * math.sin(2 * math.pi * freq * h * t)
        elif wave_type == "triangle":
            value = (2 / math.pi) * math.asin(math.sin(2 * math.pi * freq * t))
        elif wave_type == "saw":
            value = 2 * (t * freq - math.floor(0.5 + t * freq))

        samples.append(value * env)

    return samples


def generate_drum_hit(duration: float, sample_rate: int = SAMPLE_RATE,
                      freq: float = 80.0) -> list[float]:
    """Generate a drum-like percussion hit."""
    n_samples = int(sample_rate * duration)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        env = math.exp(-t * 30)  # fast decay
        # Low-frequency sine + noise for a kick drum
        tone = 0.6 * math.sin(2 * math.pi * freq * t)
        noise = 0.4 * (random.random() * 2 - 1)
        samples.append((tone + noise) * env)
    return samples


def generate_hihat(duration: float, sample_rate: int = SAMPLE_RATE) -> list[float]:
    """Generate a hi-hat-like sound (high-frequency noise)."""
    n_samples = int(sample_rate * duration)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        env = math.exp(-t * 50)
        noise = (random.random() * 2 - 1)
        # High-pass filter simulation
        samples.append(noise * env * 0.3)
    return samples


def generate_track(track_idx: int) -> list[float]:
    """Generate a complete music track with multiple layers."""
    progression = CHORD_PROGRESSIONS[track_idx]
    tempo = TEMPOS[track_idx]
    scale_type = "major" if any(ct == "maj" for _, ct in progression[:1]) else "minor"
    if track_idx in (5, 8):  # Blues and R&B use minor/pentatonic
        scale_type = "pentatonic"

    beat_duration = 60.0 / tempo  # seconds per beat
    bars_per_chord = 2  # each chord lasts 2 bars
    beats_per_bar = 4
    chord_duration = beat_duration * beats_per_bar * bars_per_chord
    total_duration = chord_duration * len(progression)

    # Loop the progression to fill DURATION_SEC
    num_loops = max(1, int(DURATION_SEC / total_duration) + 1)
    total_samples = int(SAMPLE_RATE * min(DURATION_SEC, total_duration * num_loops))

    # Initialize stereo output
    output = [0.0] * total_samples

    for loop in range(num_loops):
        for chord_idx, (root_note, chord_type) in enumerate(progression):
            chord_start = (loop * len(progression) + chord_idx) * chord_duration
            if chord_start >= DURATION_SEC:
                break

            chord_notes = get_chord_notes(root_note, chord_type)

            # 1. Chord pad (harmony background)
            for note in chord_notes:
                freq = NOTE_FREQS.get(note, 220.0)
                tone = generate_tone(freq, chord_duration * 0.95, harmonics=2)
                start_idx = int(chord_start * SAMPLE_RATE)
                for i, s in enumerate(tone):
                    idx = start_idx + i
                    if idx < total_samples:
                        output[idx] += s * 0.08  # low volume for pad

            # 2. Bass line (root note one octave lower)
            bass_note = root_note
            bass_freq = NOTE_FREQS.get(bass_note, 110.0) / 2  # one octave down
            for beat in range(beats_per_bar * bars_per_chord):
                beat_start = chord_start + beat * beat_duration
                bass_tone = generate_tone(bass_freq, beat_duration * 0.8, harmonics=1)
                start_idx = int(beat_start * SAMPLE_RATE)
                for i, s in enumerate(bass_tone):
                    idx = start_idx + i
                    if idx < total_samples:
                        output[idx] += s * 0.15

            # 3. Melody (random notes from the scale)
            melody_root_freq = NOTE_FREQS.get(root_note, 261.63)
            # Use the root note's MIDI to build the scale
            base_midi = 69 + 12 * math.log2(melody_root_freq / 440.0)
            scale_intervals = SCALES.get(scale_type, SCALES["major"])

            notes_per_chord = beats_per_bar * 2  # 8th notes
            note_duration = chord_duration / notes_per_chord
            random.seed(track_idx * 100 + chord_idx + loop * 10)

            for n in range(notes_per_chord):
                note_start = chord_start + n * note_duration
                if note_start >= DURATION_SEC:
                    break

                # Pick a scale note (with some randomness but偏向 melody)
                scale_idx = random.choice([0, 2, 4, 4, 6, 7])  # favor consonant notes
                semitone_offset = scale_intervals[scale_idx % len(scale_intervals)]
                if scale_idx >= len(scale_intervals):
                    semitone_offset += 12
                note_freq = 440.0 * (2 ** ((base_midi + semitone_offset - 69) / 12.0))

                # Skip some notes for rhythm
                if random.random() < 0.2:
                    continue

                melody_tone = generate_tone(note_freq, note_duration * 0.9, harmonics=4)
                start_idx = int(note_start * SAMPLE_RATE)
                for i, s in enumerate(melody_tone):
                    idx = start_idx + i
                    if idx < total_samples:
                        output[idx] += s * 0.12

            # 4. Drums (kick on beats 1 and 3, hi-hat on off-beats)
            for beat in range(beats_per_bar * bars_per_chord):
                beat_start = chord_start + beat * beat_duration

                # Kick drum on beats 1 and 3
                if beat % 2 == 0:
                    kick = generate_drum_hit(beat_duration * 0.3, freq=60)
                    start_idx = int(beat_start * SAMPLE_RATE)
                    for i, s in enumerate(kick):
                        idx = start_idx + i
                        if idx < total_samples:
                            output[idx] += s * 0.2

                # Hi-hat on every off-beat
                hihat_start = beat_start + beat_duration * 0.5
                hihat = generate_hihat(beat_duration * 0.15)
                start_idx = int(hihat_start * SAMPLE_RATE)
                for i, s in enumerate(hihat):
                    idx = start_idx + i
                    if idx < total_samples:
                        output[idx] += s * 0.08

    # Normalize and apply fade-out at the end
    max_val = max(abs(s) for s in output) if output else 1.0
    if max_val > 0:
        normalize_factor = 0.85 / max_val
    else:
        normalize_factor = 1.0

    # Apply fade out in the last 2 seconds
    fade_samples = int(2.0 * SAMPLE_RATE)
    for i in range(max(0, total_samples - fade_samples), total_samples):
        fade_factor = (total_samples - i) / fade_samples
        output[i] *= fade_factor

    return [s * normalize_factor for s in output]


def save_wav(filename: str, samples: list[float], sample_rate: int = SAMPLE_RATE):
    """Save mono samples as a stereo WAV file (duplicate to both channels)."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with wave.open(filename, 'w') as w:
        w.setnchannels(2)  # Stereo
        w.setsampwidth(BITS_PER_SAMPLE // 8)
        w.setframerate(sample_rate)

        for sample in samples:
            # Clamp and convert to 16-bit
            val = max(-1.0, min(1.0, sample))
            int_val = int(val * MAX_AMPLITUDE)
            # Write to both channels (stereo)
            w.writeframes(struct.pack('<hh', int_val, int_val))


def main():
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "assets", "audio", "music"
    )
    os.makedirs(output_dir, exist_ok=True)

    print(f"Generating 10 music tracks in {output_dir}...")
    print(f"  Sample rate: {SAMPLE_RATE} Hz, Duration: ~{DURATION_SEC}s per track")
    print()

    for i in range(10):
        print(f"  Generating track_{i+1:02d}.wav ({TRACK_NAMES[i]})...")
        samples = generate_track(i)
        filepath = os.path.join(output_dir, f"track_{i+1:02d}.wav")
        save_wav(filepath, samples)

        file_size = os.path.getsize(filepath) / (1024 * 1024)
        print(f"    Done: {file_size:.2f} MB")

    print()
    print("All tracks generated successfully!")


if __name__ == "__main__":
    main()
