import re

with open('frontend/app.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Imports
code = code.replace(
    'from backend.voice_handler import text_to_speech',
    'from backend.voice_handler import text_to_speech, speech_bytes_to_text\nfrom streamlit_mic_recorder import mic_recorder'
)

# 2. Voice Column (components.html to mic_recorder)
mic_recorder_code = '''        audio_data = None
        try:
            audio_data = mic_recorder(
                start_prompt="🎤 Start speaking",
                stop_prompt="🛑 Stop recording",
                key="voice_recorder"
            )
            if audio_data and not isinstance(audio_data, dict):
                audio_data = None
            if audio_data and 'bytes' not in audio_data:
                audio_data = None
        except Exception as e:
            audio_data = None
            st.warning(f"Voice error: {e}")'''

# We find the block starting with components.html(""" and ending with """, height=55)
code = re.sub(r'        components\.html\(\"\"\"[\s\S]*?\"\"\", height=55\)', mic_recorder_code, code)

# 3. Query Logic (voice_q to audio_data)
query_logic = '''if "last_query" not in st.session_state:
    st.session_state.last_query = ""

query_to_process = None
voice_detected = False

# Process mic_recorder audio via Groq Whisper
if 'audio_data' in locals() and audio_data and isinstance(audio_data, dict) and audio_data.get('bytes'):
    with st.spinner("🎤 Transcribing via Groq Whisper..."):
        detected_text = speech_bytes_to_text(audio_data['bytes'])
    if detected_text:
        st.success(f"🗣️ Voice heard: **{detected_text}**")
        query_to_process = detected_text
        voice_detected = True
    else:
        st.warning("⚠️ Could not understand audio. Please try again or type your symptoms.")

# Priority: Voice bytes -> Search button -> Text change
if not query_to_process and 'text_query' in locals() and text_query and search_clicked:
    query_to_process = text_query
    st.session_state.last_query = text_query
    voice_detected = False
elif not query_to_process and 'text_query' in locals() and text_query and text_query != st.session_state.last_query:
    query_to_process = text_query
    st.session_state.last_query = text_query
    voice_detected = False'''

code = re.sub(r'if "last_query" not in st\.session_state:[\s\S]*?voice_detected = False\n*(?=\nif query_to_process:)', query_logic, code)

with open('frontend/app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print('Rewrite complete. Double check with py_compile.')
