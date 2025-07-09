import os
import fitz  # PyMuPDF
from pdf2zh.core import PageCoordinates, detect_paragraphs 
from pdf2zh.cache import CachedTranslator
from pdf2zh.translator.openai_translator import OpenAITranslator
from dataclasses import asdict
from pprint import pprint
testing_file_dir = "C:/Users/Admin/Desktop/AI_traslator/Taigman_DeepFace_Closing_the_2014_CVPR_paper.pdf"

def main():
    api_key = os.getenv("OPENAI_API_KEY")

    page_index = 0  

    base, _ = os.path.splitext(testing_file_dir)
    single_pdf = f"{base}_page{page_index+1}.pdf"
    src_doc = fitz.open(testing_file_dir)
    temp_doc = fitz.open()
    temp_doc.insert_pdf(src_doc, from_page=page_index, to_page=page_index)
    temp_doc.save(single_pdf)

    read_doc = fitz.open(single_pdf)
    page0 = read_doc[0]
    print("\n===== Original PDF Page Text =====")
    print(page0.get_text("text"))
    print("\n===== Original PDF Page Blocks (coords & text) =====")
    pc = PageCoordinates.from_page(page_index, page0)
    print("\n===== PageCoordinates dataclass as dict =====")
    pprint(asdict(pc))
    print("\n===== BlockInfo dataclass list =====")
    pprint([asdict(blk) for blk in pc.blocks])
    for blk in pc.blocks:
        print(f"Block {blk.block_no}: type={blk.block_type}, bbox={blk.bbox}")
        if blk.block_type == 0:
            print(blk.text)
    print("===== End of page read log =====\n")

    pc = PageCoordinates.from_page(page_index, page0)
    paras = detect_paragraphs(pc.blocks, x_tol=50, y_tol=5)
    for i, p in enumerate(paras):
        print(f"Paragraph {i}:")
        for blk in p:
            print(" ", blk.text)
        print()

if __name__ == "__main__":
    main()