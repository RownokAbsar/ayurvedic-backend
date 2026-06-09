from gtts import gTTS
import io
import os
import uuid
import logging
import tempfile

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def speech_bytes_to_text(audio_bytes):
    """
    Converts audio bytes (WAV from st.audio_input) to text using Groq Whisper API.
    """
    if not audio_bytes:
        return ""
    
    try:
        from groq import Groq
        from dotenv import load_dotenv
        load_dotenv()
        
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        # Write to a temp file - Groq needs a file-like object with a name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            with open(tmp_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=audio_file,
                    response_format="text"
                )
            text = transcription.strip()
            logging.info(f"Whisper transcribed: {text!r}")
            return text
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        logging.error(f"Groq Whisper transcription failed: {e}")
        return ""


def text_to_speech(text, lang='hi', cache_dir="data/audio_cache"):
    """
    Converts text to an MP3 file format using gTTS and saves it in a cache.
    Returns the path to the MP3.
    """
    if not text or not text.strip():
        return None
        
    os.makedirs(cache_dir, exist_ok=True)
    filename = f"response_{uuid.uuid4().hex[:8]}.mp3"
    filepath = os.path.join(cache_dir, filename)
    
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(filepath)
        logging.info(f"TTS saved to {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"TTS generation failed: {e}")
        return None
