import os
import fitz  # PyMuPDF
import sys 
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "src")))

from pdf2zh.core import PageCoordinates, detect_paragraphs 
from pdf2zh.cache import CachedTranslator
from pdf2zh.translator.openai_translator import OpenAITranslator
from dataclasses import asdict
from pprint import pprint
from pdf2zh.core import convert_pdf
# testing_file_dir = "C:/Users/Admin/Desktop/AI_traslator/Taigman_DeepFace_Closing_the_2014_CVPR_paper.pdf"
testing_file_dir = "C:/Users/Admin/Desktop/proj/Taigman_DeepFace_Closing_the_2014_CVPR_paper.pdf"

def main():
    api_key = os.getenv("OPENAI_API_KEY")
    src = fitz.open(testing_file_dir)
    # chỉ lấy page đầu tiên
    doc = fitz.open()
    doc.insert_pdf(src, from_page=0, to_page=8)
    temp_pdf = "temp_first_page.pdf"
    doc.save(temp_pdf)

    output_pdf = "page1_translated.pdf"
    convert_pdf(
        input_pdf=temp_pdf,
        output_pdf=output_pdf,
        target_lang="Vietnamese",
        api_key=api_key,
        debug=False
    )
    print(f"Saved translated PDF to {output_pdf}")

    try:
        os.remove(temp_pdf)
    except OSError:
        pass



if __name__ == "__main__":
    main()