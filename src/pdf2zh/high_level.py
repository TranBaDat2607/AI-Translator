import io
import numpy as np
import fitz
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdf2zh.cache import CachedTranslator
from pdf2zh.translator.openai_translator import OpenAITranslator
from pdf2zh.translator.gemini_translator import GeminiTranslator
from pdf2zh.converter import TranslateConverter
import pikepdf
import logging
logging.basicConfig(level=logging.INFO)

def translate_full_layout(
    input_pdf: str,
    output_pdf: str,
    service: str,
    api_key: str,
    src_lang: str,
    tgt_lang: str,
    cache_db: str,
    onnx_model,            # instance của OnnxModel
    thread: int = 1,
) -> None:
    """
    Pipeline A→B→C:
      A) build layout per page với onnx_model
      B) parse bằng PDFMiner, group paragraph+formula
      C) dịch và sinh PDF-operators rồi patch via pikepdf
    """
    # 1) Translator + cache
    mapper = {"OpenAI": OpenAITranslator, "Gemini": GeminiTranslator}
    if service not in mapper:
        raise ValueError(f"Unsupported service {service}")
    inner = mapper[service](api_key)
    translator = CachedTranslator(inner, cache_db)

    # 2) Build layout_map bằng PyMuPDF + onnx_model
    doc_fitz = fitz.open(input_pdf)
    layout_map = {}
    for pno in range(len(doc_fitz)):
        pix = doc_fitz[pno].get_pixmap()
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)[..., ::-1]
        layout_map[pno] = onnx_model.predict(img, imgsz=int(pix.height/32)*32)[0]

    # 3) Mở PDF gốc với pikepdf
    pdf = pikepdf.Pdf.open(input_pdf, allow_overwriting_input=True)

    # 4) Khởi PDFMiner
    with open(input_pdf, "rb") as f:
        parser = PDFParser(f)
        doc = PDFDocument(parser)
    rsrcmgr = PDFResourceManager()

    # 5) Xử lý từng trang
    for pno, page in enumerate(pdf.pages):
        # A) Khởi converter
        conv = TranslateConverter(
            rsrcmgr=rsrcmgr,
            translator=translator,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            thread=thread,
            layout=layout_map,
        )
        interpreter = PDFPageInterpreter(rsrcmgr, conv)
        # B) parse page từ PDFMiner
        for pm in PDFPage.create_pages(doc):
            if pm.pageid == pno:
                interpreter.process_page(pm)
                # C) lấy BT…ET string
                ops = conv.end_page(pm)
                # patch lại content-stream
                new_stream = pdf.make_stream(ops.encode("utf-8"))
                page.Contents = new_stream
                break

    # 6) Lưu kết quả
    pdf.save(output_pdf)
