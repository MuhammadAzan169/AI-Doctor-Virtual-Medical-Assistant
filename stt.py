import whisper  # Importing OpenAI's Whisper model for speech-to-text
import sounddevice as sd  # For recording audio from microphone
import numpy as np  # For numerical operations
from scipy.signal import resample  # For resampling audio signals
from silero_vad import load_silero_vad, get_speech_timestamps  # Voice activity detection from Silero
from tts import text_to_speech  # Custom TTS function to give audio prompts


def record_until_silence(sample_rate=16000, timeout=10):
    text_to_speech("You can speak now...")  # Notify the user they can speak
    audio = sd.rec(int(timeout * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')  # Record audio
    sd.wait()  # Wait until recording is done
    print("Recording complete.")  # Confirmation
    return audio.flatten()  # Return audio as a 1D array


def extract_all_voice_with_padding(audio_int16, sample_rate=16000, padding_ms=200):
    vad_model = load_silero_vad()  # Load the voice activity detection model
    wav = audio_int16.astype(np.float32) / 32768.0  # Normalize audio to float range [-1, 1]

    speech_ts = get_speech_timestamps(wav, vad_model, sampling_rate=sample_rate)  # Get timestamps where speech occurs
    if not speech_ts:
        return np.array([], dtype=np.float32)  # Return empty if no speech is detected

    padding = int(sample_rate * (padding_ms / 1000))  # Convert padding from ms to samples
    voiced_segments = []  # List to store all speech segments

    for segment in speech_ts:
        start = max(0, segment['start'] - padding)  # Start with padding, without going below 0
        end = min(len(wav), segment['end'] + padding)  # End with padding, without exceeding length
        voiced_segments.append(wav[start:end])  # Append padded segment

    return np.concatenate(voiced_segments)  # Merge all speech segments into one array


def speech_to_text(model):
    raw_audio = record_until_silence()  # Record audio from user

    voice_audio = extract_all_voice_with_padding(raw_audio)  # Extract only speech parts

    if voice_audio.size == 0:
        return "[No speech detected]"  # Handle case where no speech was found

    audio_16k = resample(voice_audio, int(len(voice_audio) * 16000 / 16000)).astype(np.float32)  # Resample to 16kHz

    result = model.transcribe(audio_16k, fp16=False, language='en')  # Transcribe using Whisper
    return result["text"]  # Return recognized text
