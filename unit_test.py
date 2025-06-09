import os

import fitz  # PyMuPDF

from pdf2zh.cache import CachedTranslator
from pdf2zh.translator.openai_translator import OpenAITranslator

testing_file_dir = (
    "C:/Users/admin/Desktop/pdf_AI_trans/"
    "Taigman_DeepFace_Closing_the_2014_CVPR_paper_"
    "OpenAI_Vietnamese_OpenAI_Vietnamese.pdf"
)


def main():
    api_key = "YOUR API KEY"

    # Open the PDF and extract text from the first page
    doc = fitz.open(testing_file_dir)
    page = doc[0]
    original_text = page.get_text("text")

    print("===== Original Text =====")
    print(original_text)

    # Initialize translator with in-memory cache
    inner = OpenAITranslator(api_key)
    cache_db_path = "cache_test.db"
    translator = CachedTranslator(inner, db_path=cache_db_path)

    # Translate and print
    translated_text = translator.translate(
        [original_text], src="auto", tgt="Vietnamese"
    )[0]

    print("\n===== Translated Text =====")
    print(translated_text)


if __name__ == "__main__":
    main()