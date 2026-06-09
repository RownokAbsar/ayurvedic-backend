import fitz
import sys

def analyze_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        print(f"Total pages: {len(doc)}")
        for i in range(min(3, len(doc))):
            page = doc[i]
            text = page.get_text()
            print(f"--- PAGE {i+1} ---")
            print(text)
    except Exception as e:
        print(f"Error reading PDF: {e}")

if __name__ == "__main__":
    pdf_file = sys.argv[1] if len(sys.argv) > 1 else "../globally-significant-medicinal-plants-of-arunachal-pradesh.pdf"
    analyze_pdf(pdf_file)
