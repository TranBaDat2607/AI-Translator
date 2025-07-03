import os

import fitz  # PyMuPDF

from src.pdf_trans.process_pdf import PDFProcessor

testing_file_dir = "C:/Users/Admin/Desktop/AI_traslator/Taigman_DeepFace_Closing_the_2014_CVPR_paper.pdf"


def main():
    pdf_processor = PDFProcessor(testing_file_dir)
    blocks = pdf_processor.extract_text_blocks()
    print(blocks)


if __name__ == "__main__":
    main()