import json
import re

def extract_names(raw_name):
    # Handle the " a. Common name:" garbage
    match = re.search(r'(?:\s+?[a-z]\.\s*)?(Common name:.*)', raw_name, re.IGNORECASE)
    if match:
        main = raw_name[:match.start()].strip()
        return main, match.group(1).strip()
    
    # Authors pattern
    author_pattern = r'^\s*(L\.|Linn\.|Roxb\.|Roxb|Burm\.\s*f\.|L\.F|Smith|Gaertn\.|Willd\.|DC\.|Ker Gawl\.|L|Linn)\s*$'
    
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
        other = raw_name[open_idx:].strip()
        # remove outer parens if perfectly matched
        if other.startswith('(') and other.endswith(')'):
            # check if it's a single group
            if other.count('(') == 1 and other.count(')') == 1:
                other = other[1:-1]
            # or if it starts with ( and ends with ) we just strip the edges
            else:
               pass
               
        # But wait, we want to strip the first ( and the last ) if they enclose the whole thing
        if other.startswith('('):
            # find matching parenthesis
            depth = 0
            for j, c in enumerate(other):
                if c == '(': depth += 1
                elif c == ')': depth -= 1
                if depth == 0:
                    if j == len(other) -1:
                        other = other[1:-1]
                    break
                    
        return main_name, other
        
    return raw_name, ""

with open('data/plants.json', 'r', encoding='utf-8') as f:
    plants = json.load(f)

for p in plants[:20]:
    main, other = extract_names(p['plant_name'])
    print(f"RAW: {p['plant_name']}\nMAIN: {main}\nOTHER: {other}\n")
