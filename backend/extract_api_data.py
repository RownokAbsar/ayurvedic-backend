"""
extract_api_data.py
───────────────────
Extracts verified dosage information from TWO authenticated sources:

  1. Ayurvedic Pharmacopoeia of India (API) Part-I — Ministry of AYUSH, Govt. of India
  2. WHO Monographs on Selected Medicinal Plants   — World Health Organization

USAGE
-----
1. Place PDFs inside:  c:\\Ayurvedic app\\data\\authenticated_sources\\
   - API PDFs : API-Vol-1.pdf ... API-Vol-5.pdf
   - WHO PDFs : WHO-vol-1.pdf ... WHO-vol-4.pdf

2. Run:  python backend/extract_api_data.py

Output: data/api_dosages.json
"""

import os, re, json, logging
import fitz   # PyMuPDF

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_SRC_DIR = os.path.join(BASE_DIR, "data", "authenticated_sources")
OUTPUT_JSON = os.path.join(BASE_DIR, "data", "api_dosages.json")


# ═══════════════════════════════════════════════════════════════════
#  SHARED UTILITIES
# ═══════════════════════════════════════════════════════════════════

def _clean(text: str) -> str:
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', '', text)
    # Replace fancy dashes / en-dashes used in PDFs
    text = text.replace('\u2013', '-').replace('\u2014', '-')
    text = text.replace('\ufb01', 'fi').replace('\ufb02', 'fl')
    return re.sub(r'\s+', ' ', text).strip()


def _after(label: str, text: str) -> str:
    """Extract value after a section label, stopping at the next section."""
    m = re.search(
        r'(?:^|\n)\s*' + label +
        r'\s*\n?(.*?)(?=\n\s*(?:[A-Z][a-zA-Z &/\(\)]{2,})\s*\n|\Z)',
        text, re.IGNORECASE | re.DOTALL
    )
    return _clean(m.group(1)) if m else ''


def _norm(name: str) -> str:
    """Normalised lowercase key: strip author names and parenthetical citations."""
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'\b[A-Z][a-z]{0,5}\.', '', name)
    return re.sub(r'\s+', ' ', name).strip().lower()


# ═══════════════════════════════════════════════════════════════════
#  SOURCE 1 — Ayurvedic Pharmacopoeia of India (API)
# ═══════════════════════════════════════════════════════════════════

_API_BOT = re.compile(
    r'consists?\s+of\s+(?:the\s+)?(?:\w+\s+){0,6}of\s+'
    r'([A-Z][a-z]{2,}\s+[a-z]{3,}(?:\s+[A-Z][a-z]{0,5}\.?)?)',
    re.IGNORECASE
)


def _api_botanical(block: str) -> str:
    m = _API_BOT.search(block[:700])
    if m:
        return _clean(m.group(1))
    # Fallback: first standalone binomial line
    for line in block[:500].split('\n'):
        line = line.strip()
        if re.match(r'^[A-Z][a-z]{2,}\s+[a-z]{3,}', line) and len(line.split()) >= 2:
            return _clean(line)
    return ''


def process_api_pdf(pdf_path: str) -> list:
    vol_name = os.path.splitext(os.path.basename(pdf_path))[0]
    doc   = fitz.open(pdf_path)
    pages = [p.get_text("text") for p in doc]
    doc.close()
    full_text = "\n".join(pages)

    # Split on numbered monograph headings: "1. Ajagandha\n", "12. Bilva\n" etc.
    blocks = re.split(r'\n(?=\d{1,3}\.\s+[A-Z][a-zA-Z])', full_text)

    results = []
    for block in blocks:
        if 'DOSE' not in block and 'Dose' not in block:
            continue
        if 'THERAPEUTIC' not in block and 'therapeutic' not in block.lower():
            continue

        dose = _after(r'DOSE', block)
        uses = _after(r'THERAPEUTIC USES?', block)
        form = _after(r'IMPORTANT FORMULATIONS?', block)
        part = _after(r'PART(?:S)? USED', block)
        bot  = _api_botanical(block)

        if not dose:
            continue
        if not bot:
            m = re.search(r'\b([A-Z][a-z]{2,}\s+[a-z]{3,})\b', block[:300])
            bot = m.group(1) if m else ''
        if not bot:
            continue

        # Clean trailing page numbers from dose (e.g. "3-6 g. 20")
        dose = re.sub(r'\s+\d{1,3}\s*$', '', dose).strip()

        results.append({
            "botanical_name"   : bot,
            "dose"             : dose,
            "therapeutic_uses" : uses,
            "formulations"     : form,
            "part_used"        : part,
            "precautions"      : "",
            "source_volume"    : vol_name,
            "source"           : f"Ayurvedic Pharmacopoeia of India, Part I, {vol_name}",
            "source_authority" : "Ministry of AYUSH, Government of India",
        })

    logging.info(f"    [API] {vol_name}: {len(results)} monographs")
    return results


# ═══════════════════════════════════════════════════════════════════
#  SOURCE 2 — WHO Monographs on Selected Medicinal Plants
# ═══════════════════════════════════════════════════════════════════

def process_who_pdf(pdf_path: str) -> list:
    vol_name = os.path.splitext(os.path.basename(pdf_path))[0]
    doc   = fitz.open(pdf_path)
    pages = [p.get_text("text") for p in doc]
    doc.close()
    full_text = "\n".join(pages)

    # WHO PDFs contain fi/fl ligatures as single Unicode characters — normalise them
    full_text = full_text.replace('\ufb01', 'fi').replace('\ufb02', 'fl')
    full_text = full_text.replace('\ufb03', 'ffi').replace('\ufb04', 'ffl')

    # Each WHO monograph starts with "PlantName\nNN\nPlantName\nDefinition\n..."
    # Split on "Definition\n" to get monograph blocks
    blocks = re.split(r'\nDefinition\n', full_text)

    results = []
    for i, block in enumerate(blocks[1:], 1):  # skip preamble
        # ── Extract Posology (= dosage in WHO) ──────────────────────────
        posology = _after(r'Posology', block)
        if not posology:
            continue

        # ── Extract Medicinal uses ───────────────────────────────────────
        uses_raw = _after(r'Medicinal uses', block)
        # Collapse sub-sections into one string
        uses = re.sub(r'\n?Uses (?:supported|described)[^\n]*\n', ' | ', uses_raw)
        uses = _clean(uses)[:500]

        # ── Extract Dosage forms ─────────────────────────────────────────
        dosage_forms = _after(r'Dosage forms', block)

        # ── Extract Adverse reactions / Precautions ──────────────────────
        precautions = _after(r'(?:Adverse reactions|Contraindications|Precautions)', block)

        # ── Extract botanical name from block BEFORE "Definition" ────────
        # The monograph title is the last non-empty line(s) before "Definition"
        # We look at the text ENDING just before this block
        preceding = blocks[i - 1] if i - 1 < len(blocks) else ''
        # The plant Latin name sits at the very END of the previous block
        # (it's also the page header repeated throughout)
        header_lines = [l.strip() for l in preceding.split('\n') if l.strip()]
        bot = ''
        for line in reversed(header_lines[-6:]):
            # Binomial Latin name: "Aloe" or "Bulbus Allii Sativi" or "Cortex Cinnamomi"
            # We want the common short name or genus species
            # Also the Definition line itself often states the botanical name
            if re.match(r'^[A-Z][a-z]{2,}', line) and len(line) < 60:
                bot = _clean(line)
                break

        # Better: extract botanical name from Definition sentence
        # "Aloe is the dried juice of the leaves of Aloe vera (L.) Burm. f."
        # "Folium Perillae consists of the dried leaves of Perilla frutescens"
        m_def = re.search(
            r'(?:is|consists?\s+of)[^.]*?(?:leaves?|roots?|bark|seed|fruit|whole plant)[^.]*?of\s+'
            r'([A-Z][a-z]{2,}\s+[a-z]{3,}(?:\s+\([^)]*\))?(?:\s+[A-Z][a-z]{0,8}\.?)?)',
            block[:600], re.IGNORECASE
        )
        if m_def:
            bot = _clean(m_def.group(1))
            # Strip trailing author citations like "(L.) Burm. f."
            bot = re.sub(r'\s*\(.*?\)', '', bot).strip()

        if not bot:
            # Try the Definition block itself for a standalone binomial
            m2 = re.search(r'\b([A-Z][a-z]{3,}\s+[a-z]{4,})\b', block[:300])
            if m2:
                bot = m2.group(1)

        if not bot or not posology:
            continue

        results.append({
            "botanical_name"   : bot,
            "dose"             : posology,
            "therapeutic_uses" : uses,
            "formulations"     : dosage_forms,
            "part_used"        : "",
            "precautions"      : _clean(precautions)[:400],
            "source_volume"    : vol_name,
            "source"           : f"WHO Monographs on Selected Medicinal Plants, {vol_name}",
            "source_authority" : "World Health Organization (WHO)",
        })

    logging.info(f"    [WHO] {vol_name}: {len(results)} monographs")
    return results


# ═══════════════════════════════════════════════════════════════════
#  ALIAS MAP — maps YOUR plant DB names → canonical lookup key
# ═══════════════════════════════════════════════════════════════════

ALIASES = {
    # ── API spelling / synonym fixes ──────────────────────────────────────────
    "acorus calamus"           : "acarus calamus",       # API typo
    "adhatoda vasika"          : "adhatoda vasica",
    "aloe vera"                : "aloe vera",            # WHO monograph
    "albizia lebbeck"          : "albizzia lebbeck",
    "asparagus racemosus"      : "asparagus recemosus",  # API typo
    "centalla asiatica"        : "centella asiatica",
    "cymbophogon citrates"     : "cymbopogon citratus",
    "euphorbia nerifolia"      : "euphorbia neriifolia",
    "messua ferrea"            : "mesua ferrea",
    "paedaeria foetida"        : "paederia foetida",
    "rawolfia serpentine"      : "rauwolfia serpentina",
    "saraca indica"            : "saraca asoca",
    "syzygium cumini"          : "syzygium cuminii",
    "terminalia bellirica"     : "terntinalia belerica",
    "aqualaria mallacensis"    : "aquilaria agallocha",
    "aegle marmelos"           : "bilva consists",
    "piper longum"             : "pippali consists",
    # ── WHO Latin drug name → our DB botanical name ───────────────────────────
    # WHO uses Latin drug names (Herba X, Radix X) not plain botanical names
    "aloe vera"                : "aloe vera",             # WHO has direct key
    "andrographis paniculata"  : "andrographis paniculata",
    "centella asiatica"        : "herba centellae",       # WHO drug name
    "catharanthus roseus"      : "catharanthus roseus",
    "cinnamomum zeylanicum"    : "cinnamomum zeylanicum",
    "mentha arvenvis"          : "mentha",
    "moringa oleifera"         : "moringa oleifera",
    "ocimum sanctum"           : "ocimum sanctum",
    "phyllantus embelica"      : "emblica officinalis",  # same plant
    "nyctanthes arbotristis"   : "nyctanthes arbor",
    "mimosa pudica"            : "mimosa pudica",
    "gloriosa superba"         : "gloriosa superba",
    "embelia ribes"            : "embelia ribes",
    "solanum nigrum"           : "solanum nigrum",
    "garcinia indica"          : "garcinia indica",
    "murraya koenighii"        : "murraya koenigii",
    "mimusops elengi"          : "mimusops elengi",
    "spondias pinnata"         : "spondias pinnata",
    "smilax glabra"            : "smilax glabra",
}


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

def build_api_database():
    if not os.path.isdir(API_SRC_DIR):
        logging.error(f"Folder not found: {API_SRC_DIR}")
        return

    pdf_files = sorted(f for f in os.listdir(API_SRC_DIR) if f.lower().endswith(".pdf"))
    if not pdf_files:
        logging.warning(f"No PDFs in {API_SRC_DIR}")
        return

    logging.info(f"Found {len(pdf_files)} PDF(s)")

    all_records = []
    for fname in pdf_files:
        path = os.path.join(API_SRC_DIR, fname)
        name_lower = fname.lower()
        if 'who' in name_lower:
            records = process_who_pdf(path)
        else:
            records = process_api_pdf(path)
        all_records.extend(records)

    # ── Build lookup by normalised botanical name ─────────────────────────
    lookup: dict = {}
    for rec in all_records:
        key = _norm(rec["botanical_name"])
        if key and len(key) > 4:
            # API takes priority over WHO if both exist
            if key not in lookup or rec.get("source_authority","").startswith("Ministry"):
                lookup[key] = rec

    logging.info(f"  Base lookup: {len(lookup)} unique plants")

    # ── Apply alias mapping ───────────────────────────────────────────────
    added = 0
    for alias, target in ALIASES.items():
        alias_n  = _norm(alias)
        target_n = _norm(target)
        # If alias not already in lookup but target IS
        if alias_n not in lookup:
            # Try exact target key
            if target_n in lookup:
                lookup[alias_n] = dict(lookup[target_n])
                added += 1
            else:
                # Fuzzy: find any key that starts with first two words of target
                tw = target_n.split()[:2]
                if len(tw) >= 2:
                    prefix = tw[0] + ' ' + tw[1]
                    for k, v in lookup.items():
                        if k.startswith(prefix):
                            lookup[alias_n] = dict(v)
                            added += 1
                            break
                elif tw:
                    for k, v in lookup.items():
                        if k.startswith(tw[0]):
                            lookup[alias_n] = dict(v)
                            added += 1
                            break

    logging.info(f"  Alias mapping added {added} extra entries")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(lookup, f, indent=4, ensure_ascii=False)

    total = len(lookup)
    logging.info(f"\n✅  Saved {total} total monographs → {OUTPUT_JSON}")

    # ── Match rate against your plant DB ─────────────────────────────────
    plants_json = os.path.join(BASE_DIR, "data", "plants_cleaned.json")
    if os.path.exists(plants_json):
        with open(plants_json, 'r', encoding='utf-8') as f:
            plants = json.load(f)

        matched, unmatched = [], []
        for p in plants:
            name = p.get('parsed_main_name', '')
            key  = _norm(name)
            words = key.split()
            found = False
            if key in lookup:
                found = True
            elif len(words) >= 2:
                prefix = words[0] + ' ' + words[1]
                for k in lookup:
                    if k.startswith(prefix) or prefix in k:
                        found = True
                        break
            (matched if found else unmatched).append(name)

        print(f"\n{'='*55}")
        print(f" MATCH RATE: {len(matched)}/{len(plants)} plants have verified dosage")
        print(f"{'='*55}")
        if unmatched:
            print(f"\n Plants WITHOUT dosage ({len(unmatched)}) -- not in API or WHO:")
            for u in unmatched:
                print(f"  X {u}")
        print()


if __name__ == "__main__":
    build_api_database()
