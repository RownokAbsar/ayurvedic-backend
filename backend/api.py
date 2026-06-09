from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi import Request
import os
import sys
import re
import json

# Setup paths
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(BASE_DIR)

from backend.rag_engine import AyurvedicRAG
from backend.translator import detect_and_translate_to_english, is_hindi, extract_symptom_keywords, is_valid_symptom_query
from backend.voice_handler import speech_bytes_to_text

app = FastAPI(title="Ayurvedic AI API")

# Enable CORS for mobile app access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
def _add_image_urls(plants: list, request: Request):
    """
    Prefix each image filename with the full static URL so the mobile app can fetch it.
    Always extracts the bare filename first to avoid double-prefixing if the
    in-memory plant dict was mutated by a previous request.
    """
    base_url = str(request.base_url).rstrip("/")
    if "up.railway.app" in base_url or "onrender.com" in base_url:
        base_url = base_url.replace("http://", "https://")
    for plant in plants:
        imgs = plant.get("images", [])
        clean_imgs = []
        for img in imgs:
            # Strip any existing http URL down to just the bare filename
            if img.startswith("http"):
                bare = img.split("/images/")[-1]
            else:
                bare = img
            clean_imgs.append(f"{base_url}/images/{bare}")
        plant["images"] = clean_imgs
        for loc in plant.get("nearby_locations", []):
            if loc.get("specimen_photo"):
                photo_path = loc["specimen_photo"].replace("data/images/", "", 1) if loc["specimen_photo"].startswith("data/images/") else loc["specimen_photo"]
                # Fix Windows vs Linux case sensitivity (.JPEG -> .jpeg)
                if photo_path.endswith(".JPEG"):
                    photo_path = photo_path[:-5] + ".jpeg"
                import urllib.parse
                # Safely encode spaces and special characters for URLs
                safe_photo_path = urllib.parse.quote(photo_path)
                loc["specimen_photo_url"] = f"{base_url}/images/{safe_photo_path}"
    return plants


# Serve images folder statically
app.mount("/images", StaticFiles(directory=os.path.join(BASE_DIR, "data", "images")), name="images")

# Initialize RAG Engine globally
rag = AyurvedicRAG(vector_dir=os.path.join(BASE_DIR, "data", "vector_store"))

# --- Helper Functions ---
def clean_api_text(text):
    if not text:
        return ""
    text = re.sub(r'[\u0080-\u00ff]', '', text)
    text = re.sub(r'\s*(DOSE|THERAPEUTIC USES?|IMPORTANT FORMULATIONS?)\s*[-\u2013].*', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\s+\d{1,3}\s*$', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub(r'^[-\u2013:\s]+', '', text).strip()

def format_dose(text):
    t = clean_api_text(text)
    if not t:
        return None
    t = re.sub(r'(\d\s*g)([A-Z])', r'\1  |  \2', t)
    t = re.sub(r'([a-z])((?:Root|Seed|Leaf|Bark|Fruit|Stem|Rhizome)\s)', r'\1  |  \2', t)
    return t

def find_nearby_plant_specimens(botanical_name):
    json_path = os.path.join(BASE_DIR, "data", "nearby_plants.json")
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            nearby_data = json.load(f)
    except Exception as e:
        return []
    
    matches = []
    def normalize_botanical(name):
        if not name: return ""
        name_clean = re.sub(r'\(.*?\)', '', name)
        name_clean = re.sub(r'[.,;]', ' ', name_clean)
        words = name_clean.split()
        if len(words) >= 2:
            return (words[0] + " " + words[1]).strip().lower()
        return name_clean.strip().lower()
        
    norm_name = normalize_botanical(botanical_name)
    for item in nearby_data:
        db_name = normalize_botanical(item.get("botanical_name", ""))
        if norm_name and db_name and (db_name == norm_name or db_name in norm_name or norm_name in db_name):
            if item.get("latitude") is not None and item.get("longitude") is not None:
                matches.append(item.copy())
    return matches

# --- API Models ---
class SearchRequest(BaseModel):
    query: str

class SearchResponse(BaseModel):
    original_query: str
    english_query: str
    plants: list
    message: str

# --- Endpoints ---
@app.get("/")
def read_root():
    return {"status": "Ayurvedic API is running"}

@app.post("/search", response_model=SearchResponse)
def search_plants(request: Request, body: SearchRequest):
    query_to_process = body.query

    if not is_valid_symptom_query(query_to_process):
        return SearchResponse(
            original_query=query_to_process,
            english_query="",
            plants=[],
            message="Please describe a health symptom (e.g., fever, headache, joint pain)."
        )

    # 1. Detect language
    user_is_hindi = is_hindi(query_to_process)
    user_lang = 'hi' if user_is_hindi else 'en'
    
    # 2. Extract keywords
    symptom_keywords = extract_symptom_keywords(query_to_process, lang=user_lang)
    
    # 3. Translate to English
    english_query = detect_and_translate_to_english(symptom_keywords)
    
    # 4. RAG Query
    result = rag.process_query(english_query)
    plants = result["plants"]
    
    if not plants:
        return SearchResponse(
            original_query=query_to_process,
            english_query=english_query,
            plants=[],
            message="No information found in the database."
        )

    # 5. Attach Location and Dosage Info
    search_terms = re.findall(r'\b[a-zA-Z]{3,}\b', english_query.lower())
    stopwords = {'and', 'the', 'for', 'with', 'have', 'has', 'about', 'from', 'this', 'that', 'pain', 'disease', 'problem', 'ache'}
    search_keywords = [w for w in search_terms if w not in stopwords]
    
    location_plants = []
    location_plant_ids = set()
    
    # Find plants from the whole DB that match keywords and have locations
    for plant in getattr(rag, 'metadata', []):
        m_name = plant.get('parsed_main_name', plant.get('plant_name'))
        nearby_specs = find_nearby_plant_specimens(m_name)
        if nearby_specs:
            uses_text = plant.get('medicinal_uses', '').lower()
            if english_query.lower() in uses_text or any(kw in uses_text for kw in search_keywords):
                plant_copy = plant.copy()
                plant_copy['has_nearby_specimen'] = True
                plant_copy['nearby_locations'] = nearby_specs
                plant_copy['api_dosage'] = rag.get_api_dosage(m_name)
                location_plants.append(plant_copy)
                location_plant_ids.add(plant_copy['id'])

    # Add tags to main search results
    for plant in plants:
        if plant['id'] not in location_plant_ids:
            m_name = plant.get('parsed_main_name', plant.get('plant_name'))
            nearby_specs = find_nearby_plant_specimens(m_name)
            if nearby_specs:
                plant['has_nearby_specimen'] = True
                plant['nearby_locations'] = nearby_specs
                location_plants.append(plant)
                location_plant_ids.add(plant['id'])
            else:
                plant['has_nearby_specimen'] = False
                plant['nearby_locations'] = []

    regular_plants = [p for p in plants if p['id'] not in location_plant_ids]
    MAX_REGULAR = 2
    final_plants = location_plants + regular_plants[:MAX_REGULAR]

    # Process dosage and clinical explanation
    for plant in final_plants:
        m_name = plant.get('parsed_main_name', plant.get('plant_name'))
        
        # Add AI explanation
        if not plant.get('clinical_explanation'):
            plant['clinical_explanation'] = rag.generate_explanation(english_query, plant)
            
        # Format dosage
        api_dosage = plant.get('api_dosage')
        if api_dosage:
            plant['formatted_dosage'] = {
                'dose': format_dose(api_dosage.get('dose', '')),
                'part_used': clean_api_text(api_dosage.get('part_used', '')),
                'formulations': clean_api_text(api_dosage.get('formulations', '')),
                'source': api_dosage.get('source', 'Ayurvedic Pharmacopoeia of India')
            }

    final_plants = _add_image_urls(final_plants, request)

    return SearchResponse(
        original_query=body.query,
        english_query=english_query,
        plants=final_plants,
        message=f"Found {len(final_plants)} plant(s) for your query."
    )

@app.post("/voice", response_model=SearchResponse)
async def process_voice(request: Request, file: UploadFile = File(...)):
    audio_bytes = await file.read()
    detected_text = speech_bytes_to_text(audio_bytes)
    
    if not detected_text:
        raise HTTPException(status_code=400, detail="Could not transcribe audio.")
        
    # Reuse the search logic
    body = SearchRequest(query=detected_text)
    return search_plants(request, body)
