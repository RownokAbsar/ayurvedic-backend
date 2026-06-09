import streamlit as st
import os
import sys
import re
# Allow importing from backend
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(BASE_DIR)

import streamlit.components.v1 as components
from backend.rag_engine import AyurvedicRAG
from backend.translator import detect_and_translate_to_english, translate_to_hindi, is_hindi, extract_symptom_keywords, is_valid_symptom_query
from backend.voice_handler import speech_bytes_to_text, text_to_speech

# ── PDF text cleaning helpers ──────────────────────────────────────────────
def clean_api_text(text):
    """Strip PDF font-encoding artifacts (garbled Latin-1 chars) and leaked section labels."""
    if not text:
        return ""
    # Remove garbled Latin-1 supplement chars (U+0080–U+00FF) — these are
    # Sanskrit diacritics that got corrupted because the API PDFs used a custom
    # font encoding that PyMuPDF could not map to proper Unicode.
    text = re.sub(r'[\u0080-\u00ff]', '', text)
    # Remove repeated section headers that bled in from raw PDF extraction
    text = re.sub(r'\s*(DOSE|THERAPEUTIC USES?|IMPORTANT FORMULATIONS?)\s*[-\u2013].*', '', text,
                  flags=re.DOTALL | re.IGNORECASE)
    # Remove trailing standalone page numbers (e.g. "...powder form. 2")
    text = re.sub(r'\s+\d{1,3}\s*$', '', text)
    # Normalize whitespace and strip leading dashes/colons
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub(r'^[-\u2013:\s]+', '', text).strip()


def format_dose(text):
    """Clean dose text and add pipe separators between concatenated entries."""
    t = clean_api_text(text)
    if not t:
        return None
    # Add separator when a number/unit is immediately followed by a capital letter
    # e.g. "1-3gSeed powder" → "1-3g | Seed powder"
    t = re.sub(r'(\d\s*g)([A-Z])', r'\1  |  \2', t)
    t = re.sub(r'([a-z])((?:Root|Seed|Leaf|Bark|Fruit|Stem|Rhizome)\s)', r'\1  |  \2', t)
    return t
# ────────────────────────────────────────────────────────────────────────────

# ── Geolocation & Distance Helpers ──────────────────────────────────────────
import json
import math

def get_distance_meters(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points on the earth in meters (Haversine)."""
    R = 6371000.0  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(d_phi / 2)**2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def find_nearby_plant_specimens(botanical_name):
    """Find specimens of a plant from nearby_plants.json. Returns list of matching location entries."""
    json_path = os.path.join(BASE_DIR, "data", "nearby_plants.json")
    if not os.path.exists(json_path):
        return []
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            nearby_data = json.load(f)
    except Exception as e:
        print(f"Error loading nearby_plants.json: {e}")
        return []
    
    matches = []
    
    def normalize_botanical(name):
        if not name:
            return ""
        # Remove parentheses first
        name_clean = re.sub(r'\(.*?\)', '', name)
        # Remove punctuation like trailing periods or commas
        name_clean = re.sub(r'[.,;]', ' ', name_clean)
        words = name_clean.split()
        if len(words) >= 2:
            return (words[0] + " " + words[1]).strip().lower()
        return name_clean.strip().lower()
        
    norm_name = normalize_botanical(botanical_name)
    
    for item in nearby_data:
        db_name = normalize_botanical(item.get("botanical_name", ""))
        if norm_name and db_name and (db_name == norm_name or db_name in norm_name or norm_name in db_name):
            plat = item.get("latitude")
            plon = item.get("longitude")
            if plat is not None and plon is not None:
                matches.append(item.copy())
                    
    return matches
# ────────────────────────────────────────────────────────────────────────────

# Set up page configurations
st.set_page_config(
    page_title="Ayurvedic Medicinal Plants AI",
    page_icon="🌿",
    layout="wide"
)

# Custom Styling
st.markdown("""
<style>
    .plant-card {
        background-color: #2b3a2b;
        color: #e5ffe5;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
        border: 1px solid #4a664a;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.5);
    }
    .plant-title { color: #88ff88; font-size: 24px; font-weight: bold; margin-bottom: 8px;}
    .plant-src { color: #b3ccb3; font-size: 14px; font-style: italic; margin-bottom: 16px;}
    .pdf-badge { background-color: #d32f2f; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; display: inline-block; font-size:12px; margin-bottom: 12px;}
    .explanation { background-color: #1f2a1f; color: #ccffcc; border-left: 4px solid #4CAF50; padding: 16px; margin: 20px 0; border-radius: 4px;}
</style>
""", unsafe_allow_html=True)

# Initialize RAG Engine
@st.cache_resource
def get_rag_engine():
    return AyurvedicRAG(vector_dir="data/vector_store")


rag = get_rag_engine()

st.title("🌿 Ayurvedic Medicinal Plants AI")

st.markdown("Search symptoms to discover traditional Ayurvedic remedies directly from the **Globally Significant Medicinal Plants of Arunachal Pradesh** database. **Zero Hallucination Guaranteed (Source: PDF).**")

st.divider()

# Sidebar setup
with st.sidebar:
    st.markdown("### 🌿 About")
    st.markdown("This system uses **RAG (Retrieval-Augmented Generation)** to recommend medicinal plants based on your symptoms.")
    st.markdown("**Data source:** Globally Significant Medicinal Plants of Arunachal Pradesh")
    st.markdown("**AI Engine:** Llama 3.1 (local, FREE)")
    st.markdown("**Embeddings:** all-MiniLM-L6-v2 (local, FREE)")
    
    st.divider()
    
    st.markdown("### 💡 Example Symptoms")
    examples = [
        "fever and headache", 
        "cough and cold", 
        "diabetes and skin disease", 
        "joint pain and swelling", 
        "stomach ache and diarrhea", 
        "stress and anxiety", 
        "liver problem and jaundice"
    ]
    
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state.example_query = ex


# Initialize defaults
search_clicked = False
audio_data = None

# When an example is clicked, pre-set the widget's session state key so
# st.text_input actually shows it, and mark it for immediate processing.
if "example_query" in st.session_state and st.session_state.example_query:
    st.session_state["symptom_input"] = st.session_state.example_query
    st.session_state["process_example"] = True
    st.session_state.example_query = ""  # Clear to avoid re-triggering

# Always show the search bar
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    text_query = st.text_input(
        "Describe your symptoms (English or Hindi):",
        placeholder="e.g. I have fever and headache or mujhe bukhar hai",
        key="symptom_input"
    )
with col2:
    st.write("Search manually:")
    search_clicked = st.button("🔍 Search", use_container_width=True)
with col3:
    st.write("Or use voice:")
    try:
        audio_input = st.audio_input("🎤 Click to record", key="voice_recorder")
        if audio_input is not None:
            audio_bytes = audio_input.read()
            if audio_bytes:
                audio_data = {"bytes": audio_bytes}
    except Exception as e:
        audio_data = None
        st.warning(f"Voice error: {e}")

# Check if we should process due to example click
process_example = st.session_state.pop("process_example", False)

if "last_query" not in st.session_state:
    st.session_state.last_query = ""

query_to_process = None
voice_detected = False

# Process mic_recorder audio via Groq Whisper
if 'audio_data' in locals() and audio_data and isinstance(audio_data, dict) and audio_data.get('bytes'):
    with st.spinner("🎤 Transcribing via Groq Whisper..."):
        detected_text = speech_bytes_to_text(audio_data['bytes'])
    if detected_text:
        st.success(f"🗣️ Voice heard: **{detected_text}**")
        if is_valid_symptom_query(detected_text):
            query_to_process = detected_text
            voice_detected = True
        else:
            st.warning("🌿 Please describe a health symptom (e.g. fever, headache, joint pain). I couldn't find a medical symptom in what you said.")
    else:
        st.warning("⚠️ Could not understand audio. Please try again or type your symptoms.")

# Priority: Voice -> Example click -> Search button -> Text change
if not query_to_process and text_query and (search_clicked or process_example):
    if is_valid_symptom_query(text_query):
        query_to_process = text_query
        st.session_state.last_query = text_query
        voice_detected = False
    else:
        st.warning("🌿 Please describe a health symptom (e.g. fever, headache, joint pain). I couldn't find a medical symptom in your input.")
elif not query_to_process and text_query and text_query != st.session_state.last_query:
    if is_valid_symptom_query(text_query):
        query_to_process = text_query
        st.session_state.last_query = text_query
        voice_detected = False
    else:
        st.session_state.last_query = text_query  # prevent re-triggering
if query_to_process:
    with st.spinner("Analyzing Database... 🌱"):
        # 1. Detect language BEFORE translating
        user_is_hindi = is_hindi(query_to_process)
        user_lang = 'hi' if user_is_hindi else 'en'
        
        # 2. Extract the core symptom keywords from natural language (strips filler like 'I have', 'mujhe')
        symptom_keywords = extract_symptom_keywords(query_to_process, lang=user_lang)
        
        # 3. Translate keywords to English for searching
        english_query = detect_and_translate_to_english(symptom_keywords)
        
        # Get purely deterministic RAG results
        result = rag.process_query(english_query)
        plants = result["plants"]
        
        st.subheader("Results")
        # Ensure we tell user if we found anything!
        if not plants:
            st.warning("No information found. According to strict rules, I am limited to the PDF database. I cannot advise on this symptom.")
        else:
            is_hindi_query = user_is_hindi if 'user_is_hindi' in dir() else False
            
            # ── Smart Truncation & Location Sorting ──────────────────────────
            # Step 1: Extract individual search terms from english_query to check if nearby plants match
            import re
            search_terms = re.findall(r'\b[a-zA-Z]{3,}\b', english_query.lower())
            stopwords = {'and', 'the', 'for', 'with', 'have', 'has', 'about', 'from', 'this', 'that', 'pain', 'disease', 'problem', 'ache'}
            search_keywords = [w for w in search_terms if w not in stopwords]
            
            # Step 2: Scan all plants in the database to find nearby specimens that match the symptoms
            location_plants = []
            location_plant_ids = set()
            
            for plant in getattr(rag, 'metadata', []):
                m_name = plant.get('parsed_main_name', plant.get('plant_name'))
                nearby_specs = find_nearby_plant_specimens(m_name)
                if nearby_specs:
                    uses_text = plant.get('medicinal_uses', '').lower()
                    # Check if it treats the symptom: either contains full query or any of the keywords
                    if english_query.lower() in uses_text or any(kw in uses_text for kw in search_keywords):
                        plant_copy = plant.copy()
                        plant_copy['has_nearby_specimen'] = True
                        # Attach verified API dosage if present
                        plant_copy['api_dosage'] = rag.get_api_dosage(m_name)
                        location_plants.append(plant_copy)
                        location_plant_ids.add(plant_copy['id'])

            # Step 3: Tag the standard search results and add any other location plants found by RAG
            for plant in plants:
                if plant['id'] not in location_plant_ids:
                    m_name = plant.get('parsed_main_name', plant.get('plant_name'))
                    nearby_specs = find_nearby_plant_specimens(m_name)
                    if nearby_specs:
                        plant['has_nearby_specimen'] = True
                        location_plants.append(plant)
                        location_plant_ids.add(plant['id'])
                    else:
                        plant['has_nearby_specimen'] = False

            # Step 4: Gather regular plants from the search results that are not location plants
            regular_plants = [p for p in plants if p['id'] not in location_plant_ids]

            # Step 5: Final list = ALL location plants + Top 2 most relevant regular plants
            MAX_REGULAR = 2
            final_plants = location_plants + regular_plants[:MAX_REGULAR]
            # ─────────────────────────────────────────────────────────────────

            # Inform user how many were found vs shown
            total_found = len(plants)
            total_shown = len(final_plants)
            if total_found > total_shown:
                st.info(f"🌿 Found **{total_found} plants** matching your symptoms. Showing the **{total_shown} most relevant** (location-prioritised).")

            # Render plant cards in the new horizontal layout
            top_plant_explanation = None
            for idx, plant in enumerate(final_plants):
                main_name = plant.get('parsed_main_name', plant.get('plant_name'))
                common_name = plant.get('parsed_common_name', '')
                other_names = plant.get('parsed_other_names', '')
                family = plant.get('parsed_family', '')
                habit = plant.get('parsed_habit', '')
                parts_used = plant.get('parsed_parts_used', '')
                vernacular_name = plant.get('parsed_vernacular_name', '')
                habitat = plant.get('parsed_habitat', '')
                distribution = plant.get('parsed_distribution', '')
                flowering = plant.get('parsed_flowering', '')
                uses_text = plant.get('medicinal_uses') or "Not available in our database"
                
                # Render only the main botanical name in the header
                st.markdown(f"### <span style='background-color:#1e3d1e; padding:4px 12px; border-radius:20px; color:white; font-size:16px;'>#{idx+1}</span> <span style='color:#2e7d32; font-weight:600;'>{main_name}</span>", unsafe_allow_html=True)
                
                # Create two main columns for Image vs Details
                img_col, det_col = st.columns([1, 1.5])
                
                with img_col:
                    images = plant.get('images', [])
                    if images:
                        img_filename = images[0]
                        img_path = os.path.join(BASE_DIR, "data", "images", img_filename)
                        
                        if idx > 0 and len(images) > idx:
                            img_filename = images[idx]
                            img_path = os.path.join(BASE_DIR, "data", "images", img_filename)
                            
                        if os.path.exists(img_path):
                            st.image(img_path, use_container_width=True, caption=main_name)
                        else:
                            st.info("Image file missing")
                    else:
                        st.info("No botanical image available in database.")
                
                with det_col:
                    # Render the parsed details in a neat grid just like the mockup
                    info_html = ""
                    
                    st.markdown("""
                    <style>
                    .info-grid {
                        display: grid;
                        grid-template-columns: 1fr 1fr;
                        gap: 15px;
                        margin-bottom: 20px;
                        font-size: 14px;
                    }
                    .info-grid h4 {
                        margin: 0 0 5px 0;
                        font-size: 11px;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        color: #555;
                    }
                    .info-grid p {
                        margin: 0;
                        color: #222;
                        line-height: 1.4;
                    }
                    </style>
                    <div class='info-grid'>
                    """, unsafe_allow_html=True)
                    
                    g1, g2 = st.columns(2)
                    with g1:
                        if common_name or other_names:
                            st.markdown(f"**COMMON NAME**<br>{common_name or other_names}", unsafe_allow_html=True)
                        if family:
                            st.markdown(f"**FAMILY**<br>{family}", unsafe_allow_html=True)
                        if habit:
                            st.markdown(f"**HABIT**<br>{habit}", unsafe_allow_html=True)
                        if parts_used:
                            st.markdown(f"**PARTS USED**<br>{parts_used}", unsafe_allow_html=True)
                    with g2:
                        if vernacular_name:
                            st.markdown(f"**VERNACULAR NAME**<br>{vernacular_name}", unsafe_allow_html=True)
                        if habitat:
                            st.markdown(f"**HABITAT**<br>{habitat}", unsafe_allow_html=True)
                        if distribution:
                            st.markdown(f"**DISTRIBUTION**<br>{distribution}", unsafe_allow_html=True)
                        if flowering:
                            st.markdown(f"**FLOWERING**<br>{flowering}", unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    # Uses/Indications block
                    st.markdown(f"<div style='background-color:#fff3cd; padding:10px; border-radius:5px; border-left:4px solid #ffc107; margin-bottom:15px; color:#856404; font-size:14px;'><strong>📋 Uses:</strong> {uses_text}</div>", unsafe_allow_html=True)
                    
                    # ── Lazy AI Explanation (generated here, per plant) ───────
                    with st.spinner("🤖 Generating clinical guidance..."):
                        plant_exp = rag.generate_explanation(english_query, plant)
                        if idx == 0:
                            top_plant_explanation = plant_exp
                    
                    if plant_exp:
                        st.markdown(
                            f"<div style='background-color:#e8f4f8; padding:15px; border-radius:5px; "
                            f"border-left:4px solid #0277bd; color:#01579b; font-size:14px;'>"
                            f"<strong style='font-size:12px; text-transform:uppercase; color:#0277bd;'>"
                            f"🤖 Clinical Guidance:</strong><br><br>{plant_exp}</div>",
                            unsafe_allow_html=True
                        )
                    # ──────────────────────────────────────────────────────────

                    # ── Verified API Dosage Card ─────────────────────────────
                    api_dosage = plant.get('api_dosage')
                    if api_dosage:
                        d_dose = format_dose(api_dosage.get('dose', ''))
                        d_part = clean_api_text(api_dosage.get('part_used', ''))
                        d_form = clean_api_text(api_dosage.get('formulations', ''))
                        d_src  = api_dosage.get('source', 'Ayurvedic Pharmacopoeia of India')

                        # Build tiles HTML in a single flex container
                        tiles_html = ""
                        if d_dose:
                            tiles_html += (
                                f"<div style='flex: 1; min-width: 220px; background: white; "
                                f"border: 1px solid #e0e0e0; border-radius: 12px; padding: 16px 20px; "
                                f"box-shadow: 0 4px 10px rgba(0,0,0,0.02);'>"
                                f"<div style='font-size: 10px; font-weight: 800; color: #2e7d32; "
                                f"text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;'>📏 Recommended Dose</div>"
                                f"<div style='font-size: 14px; color: #2c3e2f; font-weight: 700; "
                                f"line-height: 1.5;'>{d_dose}</div>"
                                f"</div>"
                            )
                        if d_part:
                            tiles_html += (
                                f"<div style='flex: 1; min-width: 220px; background: white; "
                                f"border: 1px solid #e0e0e0; border-radius: 12px; padding: 16px 20px; "
                                f"box-shadow: 0 4px 10px rgba(0,0,0,0.02);'>"
                                f"<div style='font-size: 10px; font-weight: 800; color: #2e7d32; "
                                f"text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;'>🌿 Part to Use</div>"
                                f"<div style='font-size: 14px; color: #2c3e2f; font-weight: 700; "
                                f"line-height: 1.5;'>{d_part}</div>"
                                f"</div>"
                            )
                        if d_form:
                            tiles_html += (
                                f"<div style='flex: 1; min-width: 220px; background: white; "
                                f"border: 1px solid #e0e0e0; border-radius: 12px; padding: 16px 20px; "
                                f"box-shadow: 0 4px 10px rgba(0,0,0,0.02);'>"
                                f"<div style='font-size: 10px; font-weight: 800; color: #2e7d32; "
                                f"text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;'>⚗️ Preparation / Form</div>"
                                f"<div style='font-size: 14px; color: #2c3e2f; font-weight: 700; "
                                f"line-height: 1.5;'>{d_form}</div>"
                                f"</div>"
                            )

                        if tiles_html:
                            card_html = (
                                f"<div style='"
                                f"background: linear-gradient(135deg, #f4fbf7 0%, #e8f5e9 100%); "
                                f"border: 1px solid #a5d6a7; border-left: 6px solid #2e7d32; "
                                f"border-radius: 16px; padding: 22px; margin-top: 18px; "
                                f"box-shadow: 0 4px 12px rgba(46,125,50,0.05); font-family: sans-serif;"
                                f"'>"
                                f"<div style='display: flex; align-items: center; justify-content: space-between; "
                                f"margin-bottom: 18px; border-bottom: 1px solid rgba(46,125,50,0.1); padding-bottom: 12px;'>"
                                f"<div style='display: flex; align-items: center; gap: 8px;'>"
                                f"<span style='background: #2e7d32; color: white; padding: 4px 12px; "
                                f"border-radius: 20px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;'>✓ VERIFIED</span>"
                                f"<span style='font-size: 15px; font-weight: 800; color: #1b5e20; margin-left: 10px;'>💊 Official Dosage &amp; Usage</span>"
                                f"</div>"
                                f"<div style='font-size: 12px; color: #388e3c; font-weight: 600;'>Ayurvedic Pharmacopoeia of India</div>"
                                f"</div>"
                                f"<div style='display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 16px;'>"
                                f"{tiles_html}"
                                f"</div>"
                                f"<div style='font-size: 11px; color: #558b2f; border-top: 1px dashed rgba(46,125,50,0.15); "
                                f"padding-top: 12px;'>"
                                f"📚 Source: <i>{d_src}</i>"
                                f"</div>"
                                f"</div>"
                            )
                            with st.expander("🩺 View Official Medical Reference (For Practitioners)", expanded=False):
                                st.markdown(card_html, unsafe_allow_html=True)

                    else:
                        fallback_html = (
                            f"<div style='"
                            f"background: #fafafa; border: 1px solid #e0e0e0; border-radius: 16px; "
                            f"padding: 20px; margin-top: 18px; box-shadow: 0 4px 12px rgba(0,0,0,0.02); "
                            f"font-family: sans-serif;"
                            f"'>"
                            f"<div style='display: flex; align-items: center; justify-content: space-between; "
                            f"margin-bottom: 12px; border-bottom: 1px solid #eee; padding-bottom: 10px;'>"
                            f"<div style='display: flex; align-items: center; gap: 8px;'>"
                            f"<span style='background: #e0e0e0; color: #616161; padding: 4px 12px; "
                            f"border-radius: 20px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;'>INFORMATION</span>"
                            f"<span style='font-size: 14px; font-weight: 700; color: #424242;'>📋 Dosage Guidelines</span>"
                            f"</div>"
                            f"</div>"
                            f"<div style='font-size: 13px; color: #616161; line-height: 1.6;'>"
                            f"Official dosage guidelines for this plant are not documented in the current edition of the "
                            f"<i>Ayurvedic Pharmacopoeia of India</i>. For safe usage and customized recommendations, "
                            f"please consult a certified Ayurvedic practitioner."
                            f"</div>"
                            f"</div>"
                        )
                        with st.expander("🩺 View Official Medical Reference (For Practitioners)", expanded=False):
                            st.markdown(fallback_html, unsafe_allow_html=True)
                    # ── Nearby Plant Specimen Lookup ─────────────────────────
                    nearby_specs = find_nearby_plant_specimens(main_name)
                    if nearby_specs:
                        st.markdown("<h4 style='color:#004d40; margin-top: 24px; margin-bottom: 8px;'>📍 Live Plant Specimen Available</h4>", unsafe_allow_html=True)
                        for spec in nearby_specs:
                            plat = spec.get("latitude")
                            plon = spec.get("longitude")
                            s_desc = spec.get("location_description", "Local area")
                            s_notes = spec.get("notes", "")
                            s_photo = spec.get("specimen_photo", "")
                            # Unique ID for this button
                            btn_id = f"dir_{main_name}_{plat}_{plon}".replace(' ', '_').replace('.', '_')

                            spec_col1, spec_col2 = st.columns([1.5, 1])
                            with spec_col1:
                                st.markdown(f"""
                                <div style='
                                    background: linear-gradient(135deg, #e0f2f1 0%, #e0f7fa 100%);
                                    border: 1px solid #80cbc4;
                                    border-left: 6px solid #00695c;
                                    border-radius: 16px;
                                    padding: 20px;
                                    margin-bottom: 12px;
                                    box-shadow: 0 4px 12px rgba(0,77,64,0.05);
                                    font-family: sans-serif;
                                '>
                                    <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;'>
                                        <span style='background: #00695c; color: white; font-size: 10px; font-weight: 800; padding: 3px 10px; border-radius: 12px; letter-spacing: 0.5px;'>LIVE SPECIMEN</span>
                                        <span style='color: #00796b; font-size: 13px; font-weight: 600;'>📍 Coordinates: {plat:.4f}, {plon:.4f}</span>
                                    </div>
                                    <div style='font-size: 15px; font-weight: 700; color: #004d40; margin-bottom: 8px;'>Location: {s_desc}</div>
                                    <p style='font-size: 13px; color: #004d40; line-height: 1.5; margin-bottom: 16px;'><i>"{s_notes}"</i></p>
                                </div>
                                """, unsafe_allow_html=True)
                                # Directions button — requests precise GPS location before opening Maps
                                components.html(f"""
                                <div style="text-align: center;">
                                    <button id="{btn_id}" onclick="getExactLocation()" style="
                                        width: 100%;
                                        padding: 13px 0;
                                        font-size: 14px;
                                        font-weight: 700;
                                        background: linear-gradient(135deg, #00695c 0%, #004d40 100%);
                                        color: white;
                                        border: none;
                                        border-radius: 10px;
                                        cursor: pointer;
                                        margin-bottom: 4px;
                                        box-shadow: 0 4px 12px rgba(0,105,92,0.35);
                                        transition: opacity 0.2s, transform 0.15s;
                                        letter-spacing: 0.3px;"
                                        onmouseover="this.style.opacity='0.88'; this.style.transform='translateY(-1px)';"
                                        onmouseout="this.style.opacity='1'; this.style.transform='translateY(0)';">
                                        🗺️ Get Walking Directions
                                    </button>
                                    <p id="msg_{btn_id}" style="font-size:11px; color:#607d8b; margin:4px 0 0 2px; font-family:sans-serif; min-height: 15px;">
                                        📍 Click to allow location access for exact routing
                                    </p>
                                </div>
                                <script>
                                function getExactLocation() {{
                                    var btn = document.getElementById('{btn_id}');
                                    var msg = document.getElementById('msg_{btn_id}');
                                    
                                    btn.innerText = '⏳ Locating you exactly...';
                                    btn.style.opacity = '0.7';
                                    btn.disabled = true;
                                    msg.innerText = 'Please click "Allow" on the location prompt.';

                                    // Try to use parent window's geolocation if possible (bypasses iframe restrictions in Streamlit)
                                    var geo = navigator.geolocation;
                                    try {{
                                        if (window.parent && window.parent.navigator && window.parent.navigator.geolocation) {{
                                            geo = window.parent.navigator.geolocation;
                                        }}
                                    }} catch(e) {{}}

                                    if (geo) {{
                                        geo.getCurrentPosition(
                                            function(position) {{
                                                var lat = position.coords.latitude;
                                                var lon = position.coords.longitude;
                                                var accuracy = position.coords.accuracy;
                                                console.log("Got exact location: " + lat + "," + lon + " (Accuracy: " + accuracy + "m)");
                                                
                                                var url = "https://www.google.com/maps/dir/?api=1&origin=" + lat + "," + lon + "&destination={plat},{plon}&travelmode=walking";
                                                window.open(url, "_blank");
                                                
                                                btn.innerText = '🗺️ Get Walking Directions';
                                                btn.style.opacity = '1';
                                                btn.disabled = false;
                                                msg.innerText = '✅ Location found. Maps opened.';
                                            }},
                                            function(error) {{
                                                console.warn("Location error: ", error);
                                                var url = "https://www.google.com/maps/dir/?api=1&destination={plat},{plon}&travelmode=walking";
                                                window.open(url, "_blank");
                                                
                                                btn.innerText = '🗺️ Get Walking Directions';
                                                btn.style.opacity = '1';
                                                btn.disabled = false;
                                                msg.innerText = '⚠️ Location denied. Using default routing.';
                                            }},
                                            {{ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }}
                                        );
                                    }} else {{
                                        var url = "https://www.google.com/maps/dir/?api=1&destination={plat},{plon}&travelmode=walking";
                                        window.open(url, "_blank");
                                        
                                        btn.innerText = '🗺️ Get Walking Directions';
                                        btn.style.opacity = '1';
                                        btn.disabled = false;
                                        msg.innerText = 'Geolocation not supported by browser.';
                                    }}
                                }}
                                </script>
                                """, height=85)

                            with spec_col2:
                                if s_photo:
                                    full_photo_path = os.path.join(BASE_DIR, s_photo)
                                    if os.path.exists(full_photo_path):
                                        st.image(full_photo_path, use_container_width=True, caption=f"Specimen Photo ({main_name})")
                                    else:
                                        st.markdown(f"""
                                        <div style='
                                            border: 2px dashed #b2dfdb;
                                            border-radius: 16px;
                                            padding: 20px;
                                            text-align: center;
                                            background: #f5fbfb;
                                            color: #00796b;
                                            font-size: 12px;
                                            line-height: 1.5;
                                            min-height: 160px;
                                            display: flex;
                                            flex-direction: column;
                                            justify-content: center;
                                            align-items: center;
                                        '>
                                            📸 <b>Specimen Photo Placeholder</b><br>
                                            To show your photo, paste the image file into:<br>
                                            <code>data/images/user_photos/</code><br>
                                            and name it: <code>{os.path.basename(s_photo)}</code>
                                        </div>
                                        """, unsafe_allow_html=True)

                            # Render map showing plant location
                            import pandas as pd
                            map_df = pd.DataFrame([{"lat": plat, "lon": plon}])
                            st.map(map_df, zoom=14)

                    st.markdown(f"<div style='color:gray; font-size:12px; margin-top:5px;'>Reference: <i>Globally Significant Medicinal Plants of Arunachal Pradesh</i>, Page {plant.get('source_page')}</div>", unsafe_allow_html=True)

                st.divider()

            # ── Medical Disclaimer ───────────────────────────────────────────
            st.markdown("""
            <div style='
                background:#fff8e1; border:1px solid #ffcc02;
                border-left:5px solid #f9a825;
                border-radius:8px; padding:14px 18px;
                font-size:12.5px; color:#6d4c00; margin-top:8px;
            '>
                ⚠️ <strong>Medical Disclaimer:</strong>
                Dosage information marked <em>Verified — Ayurvedic Pharmacopoeia of India</em>
                is reproduced from the official pharmacopoeia published by the
                Ministry of AYUSH, Government of India, and is intended for
                <strong>general educational reference only</strong>.
                It is <strong>not a prescription</strong>. Always consult a qualified
                Ayurvedic practitioner or licensed physician before using any medicinal plant.
            </div>
            """, unsafe_allow_html=True)
            # ─────────────────────────────────────────────────────────────────

            # Voice response: generate TTS in the language the user spoke
            if voice_detected and final_plants:
                st.info("🔊 Generating voice response...")
                
                # Build a professional medical spoken explanation for the top plant (final_plants[0])
                top_plant = final_plants[0]
                top_name = top_plant.get('parsed_main_name', top_plant.get('plant_name', 'this plant'))
                top_uses = top_plant.get('medicinal_uses', '')
                
                # 1. Identify if the specimen is a fruit or plant
                parts_used_lower = top_plant.get('parsed_parts_used', '').lower()
                habit_lower = top_plant.get('parsed_habit', '').lower()
                plant_name_lower = top_name.lower()

                if 'fruit' in parts_used_lower or 'fruit' in habit_lower or 'guava' in plant_name_lower or 'banana' in plant_name_lower:
                    plant_type = "fruit"
                else:
                    plant_type = "plant"

                # 2. Retrieve clinical guidance generated by AI
                explanation_to_speak = locals().get('top_plant_explanation', None)
                if not explanation_to_speak:
                    explanation_to_speak = rag.generate_explanation(english_query, top_plant)
                
                if is_hindi_query:
                    hindi_symptom = translate_to_hindi(english_query)
                    hindi_plant_type = "फल" if plant_type == "fruit" else "पौधा"
                    spoken_intro = f"आपके {hindi_symptom} के लक्षणों के लिए, आप इस {hindi_plant_type} का उपयोग कर सकते हैं, जिसे {top_name} कहा जाता है। "
                    
                    if explanation_to_speak:
                        hindi_explanation = translate_to_hindi(explanation_to_speak)
                        # Clean up prefix styling
                        hindi_explanation = re.sub(r'🤖.*?:', '', hindi_explanation)
                        spoken_text = f"{spoken_intro} {hindi_explanation}"
                    else:
                        hindi_uses = translate_to_hindi(top_uses)
                        spoken_text = f"{spoken_intro} इसका उपयोग मुख्य रूप से {hindi_uses} के इलाज के लिए किया जाता है।"
                    tts_lang = 'hi'
                else:
                    spoken_intro = f"For your symptoms of {english_query}, you can use this {plant_type}, known as {top_name}. "
                    if explanation_to_speak:
                        clean_exp = re.sub(r'🤖.*?:', '', explanation_to_speak)
                        spoken_text = f"{spoken_intro} {clean_exp}"
                    else:
                        spoken_text = f"{spoken_intro} It is traditionally used for the treatment of {top_uses}."
                    tts_lang = 'en'
                
                audio_file = text_to_speech(spoken_text, lang=tts_lang)
                if audio_file:
                    import base64
                    with open(audio_file, "rb") as f:
                        audio_b64 = base64.b64encode(f.read()).decode()
                    components.html(f"""
                        <audio autoplay>
                            <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
                        </audio>
                    """, height=0)
