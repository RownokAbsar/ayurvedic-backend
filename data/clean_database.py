import json
import re

def parse_plant_info(full_text):
    details = {}
    stops = r"(?:Family|Habit|Habits|Habitat|Habitats|Part used|Parts used|Distribution|Flower|Flowering|Fruit|Fruiting|Common name|Vernacular name|Uses)\s*[:\-]|\||$"
    
    def extract_field(pattern, text):
        match = re.search(pattern + r'\s*[:\-]\s*(.*?)(?=' + stops + ')', text, re.IGNORECASE | re.DOTALL)
        if match:
            val = match.group(1).strip()
            val = re.sub(r'(?:\s+[a-z]\.)+$', '', val).strip()
            val = re.sub(r'^[a-z]\.\s+', '', val).strip()
            return val
        return None

    details['Family'] = extract_field(r'(?:[a-z]\.\s+)?Family', full_text)
    details['Habit'] = extract_field(r'(?:[a-z]\.\s+)?Habits?', full_text)
    details['Habitat'] = extract_field(r'(?:[a-z]\.\s+)?Habitats?', full_text)
    details['Parts Used'] = extract_field(r'(?:[a-z]\.\s+)?Parts?\s*used', full_text)
    details['Distribution'] = extract_field(r'(?:[a-z]\.\s+)?Distribution', full_text)
    details['Flowering'] = extract_field(r'(?:[a-z]\.\s+)?Flower(?:ing)?', full_text)
    details['Common Name'] = extract_field(r'(?:[a-z]\.\s+)?Common name', full_text)
    details['Vernacular Name'] = extract_field(r'(?:[a-z]\.\s+)?Vernacular name', full_text)
    details['Uses'] = extract_field(r'(?:[a-z]\.\s+)?Uses', full_text)
    
    first_stop = re.search(stops, full_text, re.IGNORECASE)
    if first_stop and first_stop.start() > 0:
        raw_name = full_text[:first_stop.start()].strip()
    else:
        raw_name = full_text.split('.')[0].strip()
        
    raw_name = re.sub(r'^(?:\d+\.)?\s*\d*\s*Name:\s*', '', raw_name, flags=re.IGNORECASE)
    
    main_name = raw_name
    other_names = ""
    
    match_cn = re.search(r'(?:\s+[a-z]\.\s*)?(Common name:.*)', raw_name, re.IGNORECASE)
    if match_cn:
        main_name = raw_name[:match_cn.start()].strip()
    else:
        main_name = re.sub(r'\s+[a-z]\.$', '', main_name).strip()
        author_pattern = r'^\s*(L\.|Linn\.|Roxb\.|Burm\.\s*f\.|L\.F|Smith|Gaertn\.|Willd\.|DC\.|Ker Gawl\.|L|Linn)\s*$'
        open_idx = -1
        for i, char in enumerate(raw_name):
            if char == '(':
                end_idx = raw_name.find(')', i)
                if end_idx != -1:
                    content = raw_name[i+1:end_idx]
                    if not re.match(author_pattern, content, re.IGNORECASE):
                        open_idx = i
                        break
        if open_idx != -1:
            main_name = raw_name[:open_idx].strip()
            other_names = raw_name[open_idx:].strip()
            if other_names.startswith('('):
                depth = 0
                for j, c in enumerate(other_names):
                    if c == '(': depth += 1
                    elif c == ')': depth -= 1
                    if depth == 0:
                        if j == len(other_names) - 1:
                            other_names = other_names[1:-1]
                        break
    
    main_name = re.sub(r'•.*$', '', main_name).strip()
    main_name = re.sub(r'\s+[a-z]\.$', '', main_name).strip()
    
    details['Main Name'] = main_name
    details['Other Names'] = other_names
    
    for k, v in details.items():
        if v and isinstance(v, str):
            details[k] = re.sub(r'\s+\d+\.?$', '', v).strip()
            
    return details

with open('data/plants.json', 'r', encoding='utf-8') as f:
    orig_plants = json.load(f)

cleaned_plants = []

for idx, p in enumerate(orig_plants):
    full_text = f"{p.get('plant_name', '')} {p.get('description', '')} {p.get('medicinal_uses', '')}"
    matches = list(re.finditer(r'(?:^|\s+)(?:\d+\.)?\s*\d*\s*Name:\s+', full_text, flags=re.IGNORECASE))
    
    chunks = []
    if not matches:
        chunks.append(full_text)
    else:
        first_chunk = full_text[:matches[0].start()].strip()
        if first_chunk: chunks.append(first_chunk)
        for i in range(len(matches)):
            start_idx = matches[i].end()
            end_idx = matches[i+1].start() if i+1 < len(matches) else len(full_text)
            chunk = full_text[start_idx:end_idx].strip()
            if chunk: chunks.append(chunk)

    for i, c in enumerate(chunks):
        det = parse_plant_info(c)
        
        desc_parts = []
        if det.get('Family'): desc_parts.append(f"Family: {det['Family']}")
        if det.get('Habit'): desc_parts.append(f"Habit: {det['Habit']}")
        if det.get('Habitat'): desc_parts.append(f"Habitat: {det['Habitat']}")
        if det.get('Parts Used'): desc_parts.append(f"Parts Used: {det['Parts Used']}")
        if det.get('Distribution'): desc_parts.append(f"Distribution: {det['Distribution']}")
        if det.get('Flowering'): desc_parts.append(f"Flowering: {det['Flowering']}")
        desc_str = " | ".join(desc_parts)
        
        imgs = []
        parent_imgs = p.get('images', [])
        if parent_imgs:
            if i < len(parent_imgs):
                imgs = [parent_imgs[i]]
            else:
                imgs = [parent_imgs[0]]
            
        mn = det.get('Main Name') or "Unknown Plant"
        
        search_name = mn
        if det.get('Other Names'): search_name += f" ({det['Other Names']})"
        if det.get('Common Name'): search_name += f" (Common: {det['Common Name']})"
            
        uses = det.get('Uses') or "Not available in our database"
            
        new_p = {
            "plant_name": search_name,
            "description": desc_str,
            "medicinal_uses": uses,
            "dosage": p.get('dosage', '') if i == 0 else 'Not available in our database',
            "how_to_use": p.get('how_to_use', '') if i == 0 else 'Not available in our database',
            "side_effects": p.get('side_effects', '') if i == 0 else 'Not available in our database',
            "source_page": p.get('source_page', ''),
            "images": imgs,
            "parsed_family": det.get('Family', ''),
            "parsed_habit": det.get('Habit', ''),
            "parsed_habitat": det.get('Habitat', ''),
            "parsed_parts_used": det.get('Parts Used', ''),
            "parsed_distribution": det.get('Distribution', ''),
            "parsed_flowering": det.get('Flowering', ''),
            "parsed_common_name": det.get('Common Name', ''),
            "parsed_vernacular_name": det.get('Vernacular Name', ''),
            "parsed_other_names": det.get('Other Names', ''),
            "parsed_main_name": mn
        }
        cleaned_plants.append(new_p)

with open('data/plants_cleaned.json', 'w', encoding='utf-8') as f:
    json.dump(cleaned_plants, f, indent=4)

print(f"Extracted {len(cleaned_plants)} clean plants from {len(orig_plants)} original messy ones.")
