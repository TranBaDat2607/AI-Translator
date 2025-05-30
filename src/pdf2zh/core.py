# ... existing imports ...
from dotenv import load_dotenv
import openai
import fitz               # PyMuPDF
import pdfplumber        # keep for optional fallback text extraction if needed
import os

# load API key
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("OpenAI API key not found. Please set OPENAI_API_KEY in .env")

# map UI language names to prompt language names
LANG_PROMPT = {
    "Chinese": "Simplified Chinese",
    "English": "English",
    "Japanese": "Japanese",
    # add more mappings as needed
}

def translate_text(text: str, target_lang: str) -> str:
    """
    Call OpenAI ChatCompletion to translate text, preserving any LaTeX formulas.
    """
    # look up the human-readable language for the prompt
    lang_name = LANG_PROMPT.get(target_lang, target_lang)
    prompt = (
        f"Please translate the following text into {lang_name}. "
        "Do NOT modify any non-text content (images, formulas), only translate the text:\n\n"
        f"{text}"
    )
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful translation assistant."},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.0,
    )
    return resp.choices[0].message.content.strip()

def convert_pdf(
    input_pdf: str,
    output_pdf: str,
    target_lang: str
) -> None:
    """
    Conversion process:
    1) Open the PDF and iterate through each page.
    2) Separate text and image blocks.
    3) Translate all text blocks and split back into individual blocks.
    4) Create a new PDF: insert images at original positions, then insert translated text into each block.
    """
    print(f"[1/3] Opening {input_pdf}")
    doc = fitz.open(input_pdf)
    out = fitz.open()  # new empty PDF

    delimiter = "\n====BLOCK====\n"
    total = len(doc)
    for i in range(total):
        page = doc[i]
        d = page.get_text("dict")

        # 1) collect all text blocks
        text_blocks = [b for b in d["blocks"] if b["type"] == 0]
        block_texts = []
        for blk in text_blocks:
            lines = []
            for line in blk["lines"]:
                spans = [s["text"] for s in line["spans"]]
                lines.append("".join(spans))
            block_texts.append("\n".join(lines))

        joined = delimiter.join(block_texts)
        print(f"[2/3] Translating page {i+1}/{total} …")
        translated = translate_text(joined, target_lang)
        translated_blocks = translated.split(delimiter)

        # 2) create a new page with the same dimensions
        r = page.rect
        newp = out.new_page(width=r.width, height=r.height)

        # 3) insert images into the new page
        for blk in d["blocks"]:
            if blk.get("type") == 1:
                # get the image xref; some versions put it under 'xref'
                xref = blk.get("xref", blk.get("image"))
                if not isinstance(xref, int):
                    # skip if we don't have a valid integer reference
                    continue
                imginfo = doc.extract_image(xref)
                newp.insert_image(fitz.Rect(blk["bbox"]), stream=imginfo["image"])


        # 4) insert translated text into original block positions (default font/size)
        for blk, txt in zip(text_blocks, translated_blocks):
            newp.insert_textbox(
                fitz.Rect(blk["bbox"]),
                txt,
                fontsize=12,
                fontname="helv",
                align=0
            )

    print(f"[3/3] Saving translated PDF to {output_pdf}")
    out.save(output_pdf)
    print("✅ Done.")