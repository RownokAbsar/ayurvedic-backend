import json
import re

def extract_plant_details(plant):
    full_text = f"{plant.get('plant_name', '')} {plant.get('description', '')} {plant.get('medicinal_uses', '')}"
    
    cut_match = re.search(r'\s+[0-9]+\s*Name:', full_text, flags=re.IGNORECASE)
    if cut_match:
        full_text = full_text[:cut_match.start()]
        
    details = {}
    
    stops = r"(?:Family|Habit|Habits|Habitat|Habitats|Part used|Parts used|Distribution|Flower|Flowering|Fruit|Fruiting|Common name|Vernacular name|Uses|Name)\s*[:\-]|\||$"
    
    def extract_field(pattern, text):
        match = re.search(pattern + r'\s*[:\-]\s*(.*?)(?=' + stops + ')', text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    details['Family'] = extract_field(r'(?:[a-z]\.\s+)?Family', full_text)
    details['Common Name'] = extract_field(r'(?:[a-z]\.\s+)?Common name', full_text)
    details['Vernacular Name'] = extract_field(r'(?:[a-z]\.\s+)?Vernacular name', full_text)
    details['Uses'] = extract_field(r'(?:[a-z]\.\s+)?Uses', full_text)

    # Some cleanups
    for k in details:
        if details[k]: details[k] = re.sub(r'\s+\d+\.?$', '', details[k]).strip()
        
    return details

with open('data/plants.json', 'r', encoding='utf-8') as f:
    plants = json.load(f)

for p in plants:
    if "Clitoria ternatea" in p.get('plant_name', ''):
        print("Test Clitoria:")
        print(extract_plant_details(p))
