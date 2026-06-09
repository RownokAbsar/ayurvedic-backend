from deep_translator import GoogleTranslator
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# ── Symptom Validation ────────────────────────────────────────────────────────

# Known medical/symptom words (English + Roman Hindi)
KNOWN_SYMPTOMS = {
    # General
    'fever', 'temperature', 'bukhar', 'cold', 'sardi', 'cough', 'khansi',
    'headache', 'sir dard', 'sirdard', 'head', 'pain', 'dard', 'ache', 'aching',
    # Digestive
    'stomach', 'pet', 'diarrhea', 'diarrhoea', 'vomiting', 'nausea', 'acidity',
    'constipation', 'indigestion', 'bloating', 'gas', 'ulcer', 'dysentery',
    # Respiratory
    'breathe', 'breathing', 'asthma', 'bronchitis', 'wheeze', 'wheezing',
    'phlegm', 'mucus', 'congestion', 'throat', 'tonsil',
    # Skin
    'skin', 'rash', 'itch', 'itching', 'itchy', 'wound', 'burn', 'boil',
    'eczema', 'psoriasis', 'acne', 'pimple', 'allergy',
    # Musculoskeletal
    'joint', 'joints', 'swelling', 'arthritis', 'muscle', 'back', 'knee',
    'sprain', 'fracture', 'stiffness', 'weakness',
    # Metabolic / chronic
    'diabetes', 'sugar', 'blood pressure', 'hypertension', 'cholesterol',
    'thyroid', 'obesity', 'weight',
    # Liver / kidney
    'liver', 'kidney', 'jaundice', 'urine', 'urinary', 'infection',
    # Mental / nervous
    'stress', 'anxiety', 'depression', 'insomnia', 'sleep', 'fatigue', 'tired',
    'memory', 'migraine', 'epilepsy', 'seizure',
    # Eyes / ENT
    'eye', 'eyes', 'vision', 'ear', 'ears', 'nose', 'bleed', 'bleeding',
    # Reproductive / other
    'menstrual', 'periods', 'leucorrhoea', 'pregnancy', 'erectile',
    'hair', 'baal', 'dandruff',
    # Roman Hindi symptom roots
    'dard', 'jalan', 'sujan', 'khujli', 'kamjori', 'chakkar', 'ulti',
    'thakaan', 'neend', 'ghabrahat', 'peshab', 'daad', 'sardard', 'sirdard',
    # Devanagari symptom words (from Whisper Hindi transcription)
    'दर्द', 'बुखार', 'सर्दी', 'खांसी', 'पेट', 'सिर', 'जलन', 'सूजन',
    'खुजली', 'कमजोरी', 'चक्कर', 'उल्टी', 'थकान', 'नींद', 'घबराहट',
    'पेशाब', 'दाद', 'बाल', 'एलर्जी', 'अस्थमा', 'मधुमेह', 'त्वचा',
    'आंख', 'कान', 'नाक', 'गला', 'जोड़', 'मांसपेशी', 'हड्डी',
    'यकृत', 'किडनी', 'पीलिया', 'तनाव', 'चिंता', 'माइग्रेन',
    'रक्तचाप', 'शुगर', 'थायराइड', 'संक्रमण', 'घाव', 'जलना',
}

# Words that are definitely NOT symptoms — if the whole input is just these, reject
NOISE_ONLY_WORDS = {
    'hmm', 'hm', 'um', 'uh', 'oh', 'okay', 'ok', 'yes', 'no', 'yeah',
    'yep', 'nope', 'hello', 'hi', 'hey', 'bye', 'goodbye', 'thanks',
    'thank', 'you', 'thank you', 'thankyou', 'please', 'sorry', 'excuse',
    'what', 'who', 'where', 'when', 'how', 'why', 'test', 'testing',
    'one', 'two', 'three', 'a', 'an', 'the', 'is', 'are', 'was', 'not',
    'good', 'bad', 'nice', 'great', 'fine', 'well',
}


def is_valid_symptom_query(text: str) -> bool:
    """
    Returns True only if the text contains at least one recognisable
    medical symptom keyword. Rejects greetings, filler sounds, etc.
    """
    if not text or not text.strip():
        return False

    lowered = text.lower().strip()

    # ① Fast-path for Devanagari (Hindi voice via Whisper)
    # If the text contains Devanagari script and has ≥3 meaningful characters,
    # treat it as a valid medical query — Hindi users are almost always describing symptoms.
    devanagari_chars = re.findall(r'[\u0900-\u097F]', text)
    if len(devanagari_chars) >= 3:
        # Still reject pure noise like 'हम्म' etc. — check for known Devanagari symptoms
        # or just allow if it has enough substance (≥ 2 Devanagari words)
        deva_words = re.findall(r'[\u0900-\u097F]+', text)
        if len(deva_words) >= 1 and sum(len(w) for w in deva_words) >= 3:
            return True

    # ② If it's very short AND only noise words, reject immediately
    words = re.findall(r'[a-z\u0900-\u097F]+', lowered)
    if not words:
        return False
    non_noise = [w for w in words if w not in NOISE_ONLY_WORDS]
    if not non_noise:
        return False  # purely noise

    # ③ Check for multi-word symptom phrases first
    for symptom in KNOWN_SYMPTOMS:
        if ' ' in symptom and symptom in lowered:
            return True

    # ④ Check individual words against symptom set
    for word in words:
        if word in KNOWN_SYMPTOMS:
            return True
        # partial match for longer symptom words (≥6 chars) like 'headache' contains 'head'
        for symptom in KNOWN_SYMPTOMS:
            if len(symptom) >= 6 and symptom in word:
                return True

    return False

# Hindi filler words to strip when extracting symptom keywords
HINDI_FILLERS = [
    r'mujhe\b', r'muje\b', r'meri\b', r'mere\b', r'mera\b',
    r'main\b', r'mai\b', r'ham\b', r'hame\b', r'hamein\b',
    r'mujko\b', r'mo\b',
    r'\bhai\b', r'\bho\b', r'\bhoga\b', r'\bhe\b', r'\btha\b',
    r'\bse\b', r'\bka\b', r'\bki\b', r'\bke\b', r'\bko\b',
    r'\baur\b', r'\bor\b', r'\bhona\b', r'\bho raha\b', r'\bho rahi\b',
    r'\bbahut\b', r'\bbht\b', r'\btez\b', r'\bzyada\b',
]

# English filler phrases  
ENGLISH_FILLERS = [
    r'\bI\s+have\b', r'\bI\s+am\s+having\b', r'\bI\s+am\b',
    r'\bsuffering\s+from\b', r'\bI\s+feel\b', r'\bI\s+am\s+feeling\b',
    r'\bI\s+got\b', r'\bI\s+have\s+been\s+having\b',
    r'\bmy\b', r'\bme\b', r'\bplease\b', r'\bhelp\b',
    r'\bsymptom\b', r'\bsymptoms\b',
    r'\bI\s+need\b', r'\bI\b', r'\bwhat\s+is\b', r'\bwhat\b',
    r'\bgood\s+for\b', r'\btreat\b', r'\bcure\b',
]

def is_hindi(text):
    """Detect if the given text is Hindi (Devanagari or Roman Hindi)."""
    has_devanagari = bool(re.search(r'[\u0900-\u097F]', text))
    if has_devanagari:
        return True
    roman_hindi_words = [
        'mujhe', 'muje', 'bukhar', 'sardi', 'khansi', 'sir dard', 'pet dard',
        'dard', 'bimari', 'rog', 'hai', 'hain', 'aur', 'or', 'tez',
        'main', 'mera', 'mere', 'meri', 'hame', 'hamein', 'zyada',
    ]
    text_lower = text.lower()
    matches = sum(1 for w in roman_hindi_words if w in text_lower)
    return matches >= 2

def extract_symptom_keywords(text, lang='en'):
    """Extract core symptom keywords from natural language text."""
    cleaned = text.strip()
    
    if lang == 'hi':
        for filler in HINDI_FILLERS:
            cleaned = re.sub(filler, '', cleaned, flags=re.IGNORECASE)
    else:
        for filler in ENGLISH_FILLERS:
            cleaned = re.sub(filler, '', cleaned, flags=re.IGNORECASE)
    
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,.?!;:')
    return cleaned if cleaned else text

def detect_and_translate_to_english(text):
    """
    Translates input text to English. If it's already English, it returns it as is.
    `deep-translator` handles auto-detection safely.
    """
    if not text.strip():
        return ""
        
    try:
        translator = GoogleTranslator(source='auto', target='en')
        translated = translator.translate(text)
        logging.info(f"Translated to English: {translated}")
        return translated
    except Exception as e:
        logging.error(f"Translation to English failed: {e}")
        return text

def translate_to_hindi(text):
    """Translates English text to Hindi."""
    if not text.strip():
        return ""
        
    try:
        translator = GoogleTranslator(source='en', target='hi')
        translated = translator.translate(text)
        logging.info(f"Translated to Hindi successfully.")
        return translated
    except Exception as e:
        logging.error(f"Translation to Hindi failed: {e}")
        return text

if __name__ == "__main__":
    tests = [
        "I am having fever and headache",
        "I have cough and cold",
        "mujhe bukhar aur sardi hai",
        "mujhe pet dard hai",
        "I feel pain in my joints",
    ]
    for t in tests:
        hi = is_hindi(t)
        keywords = extract_symptom_keywords(t, lang='hi' if hi else 'en')
        en = detect_and_translate_to_english(keywords)
        print(f"Input: {t!r}")
        print(f"  is_hindi: {hi} | keywords: {keywords!r} | english: {en!r}")
        print()
