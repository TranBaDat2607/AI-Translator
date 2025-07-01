import os
from dotenv import load_dotenv
import openai
import fitz               # PyMuPDF
import pdfplumber         # optional fallback text extraction

# Load OpenAI key from .env
load_dotenv()

# Map UI names → prompt names
LANG_PROMPT = {
    "Chinese": "Simplified Chinese",
    "English": "English",
    "Japanese": "Japanese",
    # thêm nếu cần
}

def translate_text(text: str, target_lang: str) -> str:
    lang_name = LANG_PROMPT.get(target_lang, target_lang)
    prompt = (
        f"Please translate the following text into {lang_name}. "
        "Do NOT modify any non-text content (images, formulas):\n\n" + text
    )
    resp = openai.chat.completions.create(  
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "You are a helpful translation assistant."},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.0,
    )
    return resp.choices[0].message.content.strip()


def convert_pdf(input_pdf: str, output_pdf: str, target_lang: str, api_key: str) -> None:

    if not api_key:
        raise ValueError("API key is required")
    openai.api_key = api_key
    doc = fitz.open(input_pdf)
    out = fitz.open()  # PDF mới

    delimiter = "\n====BLOCK====\n"
    total = len(doc)
    for i in range(total):
        page = doc[i]
        d = page.get_text("dict")
        # 1) gom text blocks
        text_blocks = [b for b in d["blocks"] if b.get("type") == 0]
        block_texts = []
        for blk in text_blocks:
            lines = ["".join(span["text"] for span in line["spans"])
                    for line in blk["lines"]]
            block_texts.append("\n".join(lines))

        joined = delimiter.join(block_texts)
        print(f"[2/3] Translating page {i+1}/{total} …")
        translated = translate_text(joined, target_lang)
        print(f"[DEBUG] Page {i+1} translated text:\\n{translated}")
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
    # 5) output
    print(f"[3/3] Saving translated PDF to {output_pdf}")
    out.save(output_pdf)
    print("Done.")


