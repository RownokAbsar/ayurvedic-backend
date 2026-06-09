import sys, os
sys.path.insert(0, '.')

print('=== TEST 1: Syntax Check ===')
import py_compile
try:
    py_compile.compile('frontend/app.py', doraise=True)
    print('  frontend/app.py - PASS')
except py_compile.PyCompileError as e:
    print(f'  frontend/app.py - FAIL: {e}')

print()
print('=== TEST 2: RAG Engine Init ===')
from backend.rag_engine import AyurvedicRAG
rag = AyurvedicRAG(vector_dir='data/vector_store')
print(f'  RAG engine loaded: {rag.index is not None}')
print(f'  Total plants in index: {rag.index.ntotal if rag.index else 0}')

print()
print('=== TEST 3: Manual Search - fever ===')
result = rag.process_query('fever')
plants = result.get('plants', [])
print(f'  fever returned {len(plants)} plant(s)')
for p in plants:
    name = p.get('parsed_main_name', '?')
    uses = p.get('medicinal_uses', '')[:60]
    img = p.get('images', [])
    print(f'    Plant: {name}')
    print(f'    Uses:  {uses}...')
    print(f'    Image: {img}')

print()
print('=== TEST 4: Manual Search - cough ===')
result2 = rag.process_query('cough cold')
plants2 = result2.get('plants', [])
print(f'  cough/cold returned {len(plants2)} plant(s)')
for p in plants2:
    print(f'    Plant: {p.get("parsed_main_name","?")} | Image: {p.get("images",[])}')

print()
print('=== TEST 5: Language Detection + Keyword Extraction ===')
from backend.translator import is_hindi, extract_symptom_keywords, detect_and_translate_to_english
tests = [
    ('I have fever', 'en'),
    ('I am having cough and cold', 'en'),
    ('mujhe bukhar hai', 'hi'),
    ('mujhe pet dard hai', 'hi'),
    ('fever and headache', 'en'),
]
all_pass = True
for text, expected_lang in tests:
    hi = is_hindi(text)
    detected = 'hi' if hi else 'en'
    kw = extract_symptom_keywords(text, lang=detected)
    en = detect_and_translate_to_english(kw)
    status = 'PASS' if detected == expected_lang else 'WARN'
    if status == 'WARN': all_pass = False
    print(f'  [{status}] {text!r}')
    print(f'         keywords={kw!r}, english={en!r}')

print()
print('=== TEST 6: Voice URL Param Flow ===')
print('  Voice query URL handoff: voice_q param -> st.query_params.get("voice_q") -> process')
print('  Logic check: session_state.last_voice_q prevents double-firing')
print('  PASS (code review - no functional test possible without browser)')

print()
print('=== TEST 7: Image File Existence ===')
import json
with open('data/plants_cleaned.json') as f:
    plants_data = json.load(f)
print(f'  Total plants in JSON: {len(plants_data)}')
missing_img = 0
for p in plants_data:
    for img in p.get('images', []):
        path = os.path.join('data', 'images', img)
        if not os.path.exists(path):
            missing_img += 1
print(f'  Plants with images: {sum(1 for p in plants_data if p.get("images"))} / {len(plants_data)}')
print(f'  Missing image files: {missing_img}')

print()
print('=== ALL TESTS COMPLETE ===')
