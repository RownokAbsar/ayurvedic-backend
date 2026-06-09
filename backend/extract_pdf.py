import os
import fitz  # PyMuPDF
import json
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def parse_plant_info(full_text):
    details = {}
    stops = r"(?:Family|Habit|Habits|Habitat|Habitats|Part used|Parts used|Distribution|Flower|Flowering|Fruit|Fruiting|Common name|Vernacular name|Uses)\s*[:\-]|\||$"
    
    def extract_field(pattern, text):
        match = re.search(pattern + r'\s*[:\-]\s*(.*?)(?=' + stops + ')', text, re.IGNORECASE | re.DOTALL)
        if match:
            val = match.group(1).strip()
            val = re.sub(r'(?:\s+[a-z]\.)+$', '', val).strip()
            val = re.sub(r'^[a-z]\.\s+', '', val).strip()
            val = " ".join(val.split())
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
        
    raw_name = re.sub(r'^(?:\n|\s+)?\d+\.?\s+Name:\s*', '', raw_name, flags=re.IGNORECASE)
    
    main_name = raw_name
    other_names = ""
    
    match_cn = re.search(r'(?:\s+[a-z]\.\s*)?(Common name:.*)', raw_name, re.IGNORECASE)
    if match_cn:
        main_name = raw_name[:match_cn.start()].strip()
    else:
        main_name = re.sub(r'\s+[a-z]\.$', '', main_name).strip()
        author_pattern = r'^\s*(L\.|Linn\.|Roxb\.|Burm\.\s*f\.|L\.F|Smith|Gaertn\.|Willd\.|DC\.|Ker Gawl\.|L|Linn)\s*$'
        open_idx = -1
        for i, char in enumerate(main_name):
            if char == '(':
                end_idx = main_name.find(')', i)
                if end_idx != -1:
                    content = main_name[i+1:end_idx]
                    if not re.match(author_pattern, content, re.IGNORECASE):
                        open_idx = i
                        break
        if open_idx != -1:
            main_name_clean = main_name[:open_idx].strip()
            other_names = main_name[open_idx:].strip()
            if other_names.startswith('('):
                depth = 0
                for j, c in enumerate(other_names):
                    if c == '(': depth += 1
                    elif c == ')': depth -= 1
                    if depth == 0:
                        if j == len(other_names) - 1:
                            other_names = other_names[1:-1]
                        break
            main_name = main_name_clean
    
    main_name = re.sub(r'•.*$', '', main_name).strip()
    main_name = re.sub(r'\s+[a-z]\.$', '', main_name).strip()
    
    details['Main Name'] = " ".join(main_name.split())
    details['Other Names'] = " ".join(other_names.split()) if other_names else ""
    
    for k, v in details.items():
        if v and isinstance(v, str):
            details[k] = re.sub(r'\s+\d+\.?$', '', v).strip()
            
    return details

def extract_pdf_data(pdf_path, output_json, img_dir):
    os.makedirs(img_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    all_plants = []
    
    logging.info(f"Loaded {pdf_path} with {len(doc)} pages.")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        raw_text = page.get_text("text")
        
        if len(raw_text.strip()) < 50:
            continue
            
        image_list = page.get_images(full=True)
        img_paths = []
        for img_idx, img in enumerate(image_list, start=1):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                if image_ext == 'jpx': image_ext = 'jpeg'
                
                img_filename = f"page_{page_num+1}_img_{img_idx}.{image_ext}"
                img_filepath = os.path.join(img_dir, img_filename)
                
                with open(img_filepath, "wb") as f:
                    f.write(image_bytes)
                img_paths.append(img_filename)
            except Exception as e:
                logging.warning(f"Failed to extract image on page {page_num+1}: {e}")
                
        matches = list(re.finditer(r'(?:^|\n|\s+)\d+\.?\s+Name:\s+', raw_text, flags=re.IGNORECASE))
        
        chunks = []
        if not matches:
            if "Name:" in raw_text:
                chunks.append(raw_text)
        else:
            for i in range(len(matches)):
                start_idx = matches[i].start()
                end_idx = matches[i+1].start() if i+1 < len(matches) else len(raw_text)
                chunk = raw_text[start_idx:end_idx].strip()
                if len(chunk) > 30:
                    chunks.append(chunk)

        for i, chunk in enumerate(chunks):
            det = parse_plant_info(chunk)
            
            desc_parts = []
            if det.get('Family'): desc_parts.append(f"Family: {det['Family']}")
            if det.get('Habit'): desc_parts.append(f"Habit: {det['Habit']}")
            if det.get('Habitat'): desc_parts.append(f"Habitat: {det['Habitat']}")
            if det.get('Parts Used'): desc_parts.append(f"Parts Used: {det['Parts Used']}")
            if det.get('Distribution'): desc_parts.append(f"Distribution: {det['Distribution']}")
            if det.get('Flowering'): desc_parts.append(f"Flowering: {det['Flowering']}")
            desc_str = " | ".join(desc_parts)
            
            imgs = []
            if img_paths:
                if i < len(img_paths):
                    imgs = [img_paths[i]]
                else:
                    imgs = [img_paths[0]]
                
            mn = det.get('Main Name') or f"Unknown Plant (Page {page_num+1})"
            
            search_name = mn
            if det.get('Other Names'): search_name += f" ({det['Other Names']})"
            if det.get('Common Name'): search_name += f" (Common: {det['Common Name']})"
                
            uses = det.get('Uses') or "Not available in our database"
                
            plant_dict = {
                "plant_name": search_name,
                "description": desc_str,
                "medicinal_uses": uses,
                "dosage": "Not available in our database",
                "how_to_use": "Not available in our database",
                "side_effects": "Not available in our database",
                "source_page": page_num + 1,
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
            all_plants.append(plant_dict)

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_plants, f, indent=4, ensure_ascii=False)
        
    logging.info(f"Extraction complete! Saved {len(all_plants)} exact plant records.")

if __name__ == "__main__":
    extract_pdf_data(
        "globally-significant-medicinal-plants-of-arunachal-pradesh.pdf", 
        "data/plants_cleaned.json", 
        "data/images"
    )
