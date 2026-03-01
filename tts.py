from gtts import gTTS  # Import Google Text-to-Speech library
import pygame  # Import pygame for audio playback
import tempfile  # Import tempfile for creating temporary files
import os  # Import os for file operations like deletion

def text_to_speech(text, lang='en'):  # Function to convert given text to speech
    tts = gTTS(text=text, lang=lang, slow=False)  # Create a gTTS object with specified language and speed

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:  # Create a temporary MP3 file
        temp_path = fp.name  # Store the path of the temporary file
        tts.save(temp_path)  # Save the generated speech to the temp file

    pygame.mixer.init()  # Initialize the pygame mixer
    pygame.mixer.music.load(temp_path)  # Load the MP3 file into the mixer
    pygame.mixer.music.play()  # Play the audio file

    while pygame.mixer.music.get_busy():  # Keep checking if music is still playing
        pygame.time.Clock().tick(10)  # Wait for a short time to avoid high CPU usage

    pygame.mixer.quit()  # Quit the mixer after playback
    os.remove(temp_path)  # Delete the temporary MP3 file
