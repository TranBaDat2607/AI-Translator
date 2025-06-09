import fitz 
import os
import pdfplumber 
from openai import OpenAI

from pdf2zh.translator.openai_translator import OpenAITranslator
from pdf2zh.translator.gemini_translator import GeminiTranslator

def convert_pdf(
    input_pdf: str,
    output_pdf: str = None,
    service: str = "OpenAI",
    target_lang: str = "English",
    api_key: str = None,
    return_stream: bool = False
) -> bytes | None:


    """
    1) parse, 2) translate, 3) rebuild PDF.
    """
    print(f"[1/4] Opening {input_pdf}")
    doc = fitz.open(input_pdf)
    out = fitz.open()  # new empty PDF

    # choose translator
    mapper = {
        "OpenAI": OpenAITranslator,
        "Gemini": GeminiTranslator
    }
    if service not in mapper:
        raise ValueError(f"Unsupported service: {service}")
    if not api_key:
        raise ValueError("API key must be provided for translation")
    translator = mapper[service](api_key)

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

        print(f"[2/4] Translating page {i+1}/{total} via {service} …")
        res = translator.translate([joined], src="auto", tgt=target_lang)
        translated_blocks = res[0].split(delimiter)

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
    if return_stream:
        print("✅ Done, returning PDF bytes.")
        return out.write()
    if output_pdf:
        print(f"[4/4] Saving to {output_pdf}")
        out.save(output_pdf)
        print("✅ Done.")
    return None

