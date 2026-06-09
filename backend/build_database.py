import json
import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def build_vector_database(plants_json, vector_store_dir):
    os.makedirs(vector_store_dir, exist_ok=True)
    
    # Load plants data
    try:
        with open(plants_json, 'r', encoding='utf-8') as f:
            plants = json.load(f)
    except FileNotFoundError:
        logging.error(f"Could not find {plants_json}. Run extract_pdf.py first.")
        return
        
    if not plants:
        logging.error("No plants data found to process.")
        return

    logging.info("Loading sentence-transformers model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    documents = []
    metadata = []
    
    logging.info("Preparing data for embedding...")
    for idx, plant in enumerate(plants):
        # Create a rich text representation for semantic search
        name = plant.get('plant_name', 'Unknown')
        uses = plant.get('medicinal_uses', '')
        desc = plant.get('description', '')
        
        # Embed ONLY the medicinal uses so that FAISS similarity is purely symptom-driven.
        # This means searching for "fever" will only match plants that actually treat fever.
        if uses and uses != "Not available in our database":
            search_text = f"This plant treats: {uses}"
        else:
            search_text = f"Plant: {name}. {desc}"
        
        documents.append(search_text)
        metadata.append({
            "id": idx,
            "plant_name": name,
            "medicinal_uses": uses,
            "description": desc,
            "dosage": plant.get('dosage', ''),
            "how_to_use": plant.get('how_to_use', ''),
            "side_effects": plant.get('side_effects', ''),
            "source_page": plant.get('source_page', ''),
            "images": plant.get('images', []),
            "parsed_family": plant.get('parsed_family', ''),
            "parsed_habit": plant.get('parsed_habit', ''),
            "parsed_habitat": plant.get('parsed_habitat', ''),
            "parsed_parts_used": plant.get('parsed_parts_used', ''),
            "parsed_distribution": plant.get('parsed_distribution', ''),
            "parsed_flowering": plant.get('parsed_flowering', ''),
            "parsed_common_name": plant.get('parsed_common_name', ''),
            "parsed_vernacular_name": plant.get('parsed_vernacular_name', ''),
            "parsed_other_names": plant.get('parsed_other_names', ''),
            "parsed_main_name": plant.get('parsed_main_name', name)
        })
        
    logging.info(f"Generating embeddings for {len(documents)} plants...")
    embeddings = model.encode(documents, convert_to_numpy=True)
    
    # Dimension of the embeddings
    dimension = embeddings.shape[1]
    
    logging.info(f"Building FAISS index with dimension {dimension}...")
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    
    # Save index
    index_path = os.path.join(vector_store_dir, "index.faiss")
    faiss.write_index(index, index_path)
    
    # Save metadata
    meta_path = os.path.join(vector_store_dir, "metadata.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
        
    logging.info(f"Database successfully built!")
    logging.info(f"Saved FAISS index to {index_path}")
    logging.info(f"Saved Metadata to {meta_path}")

if __name__ == "__main__":
    plants_file = "data/plants_cleaned.json"
    vector_dir = "data/vector_store"
    build_vector_database(plants_file, vector_dir)
