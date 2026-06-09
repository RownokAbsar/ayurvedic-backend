import os
import re
import json
import faiss
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DOSAGES_PATH = os.path.join(BASE_DIR, "data", "api_dosages.json")

class AyurvedicRAG:
    def __init__(self, vector_dir=None):
        if vector_dir is None:
            vector_dir = os.path.join(BASE_DIR, "data", "vector_store")
            
        self.vector_dir = vector_dir
        self.index_path = os.path.join(vector_dir, "index.faiss")
        self.meta_path = os.path.join(vector_dir, "metadata.json")
        
        self.index = None
        self.metadata = []
        self.model = None
        self.api_dosages = {}   # Verified dosage data from Ayurvedic Pharmacopoeia of India
        
        self._load_database()
        self._load_api_dosages()
        
    def _load_database(self):
        try:
            logging.info("Loading FAISS index...")
            self.index = faiss.read_index(self.index_path)
            
            logging.info("Loading metadata...")
            with open(self.meta_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
                
            logging.info("Loading embedding model...")
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            logging.info("RAG Engine successfully initialized.")
        except Exception as e:
            logging.error(f"Error loading database: {e}. Check if database is built.")

    def _load_api_dosages(self):
        """Load the verified Ayurvedic Pharmacopoeia of India dosage database."""
        if os.path.exists(API_DOSAGES_PATH):
            try:
                with open(API_DOSAGES_PATH, 'r', encoding='utf-8') as f:
                    self.api_dosages = json.load(f)
                logging.info(f"Loaded API dosage database — {len(self.api_dosages)} plant monographs.")
            except Exception as e:
                logging.warning(f"Could not load API dosages: {e}")
                self.api_dosages = {}
        else:
            logging.info("API dosage database not found yet. Run backend/extract_api_data.py after adding PDFs.")
            self.api_dosages = {}

    def _normalise_name(self, name: str) -> str:
        """Lowercase, strip author citations and punctuation for fuzzy matching."""
        # Remove author abbreviations like 'Linn.' 'L.' 'Roxb.' etc.
        name = re.sub(r'\b([A-Z][a-z]{0,3}\.)', '', name)
        # Remove content inside parentheses
        name = re.sub(r'\(.*?\)', '', name)
        # Collapse whitespace
        return re.sub(r'\s+', ' ', name).strip().lower()

    def get_api_dosage(self, plant_name: str) -> dict | None:
        """
        Look up a plant in the verified API dosage database.
        Uses fuzzy matching so 'Ocimum sanctum Linn.' matches 'ocimum sanctum'.
        Returns the dosage record dict or None if not found.
        """
        if not self.api_dosages:
            return None

        query_norm = self._normalise_name(plant_name)

        # 1. Exact normalised match
        if query_norm in self.api_dosages:
            return self.api_dosages[query_norm]

        # 2. Partial / substring match — check if any key starts with the first two words
        query_words = query_norm.split()
        if len(query_words) >= 2:
            prefix = " ".join(query_words[:2])   # genus + species
            for key, record in self.api_dosages.items():
                if key.startswith(prefix) or prefix in key:
                    return record

        # 3. Single-word (genus) fallback
        if query_words:
            genus = query_words[0]
            for key, record in self.api_dosages.items():
                if key.startswith(genus + " "):
                    return record

        return None

    def _keyword_search(self, query: str) -> list:
        """Find all plants where the medicinal uses text contains the exact query words."""
        results = []
        q_lower = query.lower()
        for i, meta in enumerate(self.metadata):
            uses = meta.get('medicinal_uses', '').lower()
            if q_lower in uses:
                # Add with a distance of 0.0 (perfect match)
                results.append((0.0, meta))
        return results

    def search_plants(self, query, top_k=10):
        if not self.index or not self.model:
            return {"error": "Database not initialized"}
            
        logging.info(f"Hybrid Search for query: {query}")
        
        # 1. Exact Keyword Match
        keyword_results = self._keyword_search(query)
        
        # 2. FAISS Semantic Search
        search_query = f"This plant treats: {query}"
        query_embedding = self.model.encode([search_query], convert_to_numpy=True)
        
        logging.info("Searching FAISS index...")
        distances, indices = self.index.search(query_embedding, top_k)
        
        DISTANCE_THRESHOLD = 1.2  # L2 distance; lower = more relevant. Reject if too far.
        
        faiss_results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(self.metadata):
                dist = distances[0][i]
                if dist <= DISTANCE_THRESHOLD:
                    faiss_results.append((dist, self.metadata[idx]))
                else:
                    logging.info(f"Filtered out result with distance {dist:.3f} (threshold={DISTANCE_THRESHOLD})")
                    
        # 3. Merge and Deduplicate (Priority to exact matches / lowest distance)
        merged = {}
        # Add FAISS results first
        for dist, meta in faiss_results:
            merged[meta['id']] = (dist, meta)
            
        # Add Keyword results (overwriting if FAISS found it, since keyword dist=0.0 is better)
        for dist, meta in keyword_results:
            merged[meta['id']] = (dist, meta)
            
        final_results = list(merged.values())
        final_results.sort(key=lambda x: x[0])  # Sort by distance
        
        return [res[1] for res in final_results]


    def generate_explanation(self, query, plant):
        if not plant:
            return None

        uses = plant.get('medicinal_uses') or ''
        dosage = plant.get('dosage') or ''
        how_to_use = plant.get('how_to_use') or ''
        side_effects = plant.get('side_effects') or ''
        plant_name = plant.get('parsed_main_name') or plant.get('plant_name', '')
        
        api_dosage_dict = plant.get('api_dosage') or {}
        api_dose_text = api_dosage_dict.get('dose', '')
        api_part = api_dosage_dict.get('part_used', '')
        if api_dose_text:
            dosage = f"{dosage}\nOfficial Medical API Dose: {api_dose_text}\nPart to use: {api_part}".strip()

        system_prompt = (
            "You are a certified Ayurvedic physician writing a short, structured clinical summary for a patient. "
            "RULES: "
            "1. Base your answer primarily on the context given. However, if the context DOES NOT contain a specific recipe or preparation method for the patient's exact symptom, you are ALLOWED to use your general Ayurvedic knowledge to suggest a safe, standard home-remedy preparation (e.g., how to make a tea/decoction from the plant). "
            "2. Address the patient's specific symptom directly in your first sentence. "
            "3. Structure your answer in exactly 3 short paragraphs: "
            "   Paragraph 1 - How this plant helps with the specific symptom (1-2 sentences). "
            "   Paragraph 2 - How to use it / preparation method. You MUST simplify any 'Official Medical API Dose' into easy-to-understand plain English for a layperson. If the Official Dose is for a completely different condition than the patient's symptom, you MUST explicitly state that the official dosage is for [Condition], not [Symptom], but then provide a standard home-remedy recipe for their actual symptom using your general knowledge. "
            "   Paragraph 3 - One important caution or side-effect (1 sentence). "
            "4. Write in plain English, no Latin, no medical jargon, no bullet points. "
            "5. Keep total response under 150 words."
        )

        context_str = (
            f"Plant: {plant_name}\n"
            f"Medicinal Uses: {uses}\n"
            f"Dosage/Preparation: {dosage}\n"
            f"How to Use: {how_to_use}\n"
            f"Side Effects: {side_effects}"
        )

        user_prompt = f"Patient's symptom/query: {query}\n\n{context_str}\n\nWrite a structured 3-paragraph clinical summary for the patient."

        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"Error generating explanation: {e}")
            return None
            
    def process_query(self, query):
        """Return matched plants instantly. AI explanations are generated selectively in the frontend."""
        matched_plants = self.search_plants(query, top_k=10)  # Hybrid: keywords + FAISS

        if isinstance(matched_plants, dict) and "error" in matched_plants:
            return {
                "query": query,
                "explanation": "Error: " + matched_plants["error"],
                "plants": []
            }

        # Attach API dosage data (fast — local JSON lookup only, no network call)
        for plant in matched_plants:
            plant_name = plant.get('parsed_main_name') or plant.get('plant_name', '')
            plant['api_dosage'] = self.get_api_dosage(plant_name)
            # ai_explanation is intentionally NOT generated here — done lazily in the UI
            plant['ai_explanation'] = None

        return {
            "query": query,
            "explanation": "See individual plants.",
            "plants": matched_plants
        }

if __name__ == "__main__":
    rag = AyurvedicRAG()
    res = rag.process_query("I have a fever and headache")
    print(res["explanation"])
