import os
from dotenv import load_dotenv
import openai
import fitz               # PyMuPDF
import pdfplumber         # optional fallback text extraction
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
import numpy as np

@dataclass
class BlockInfo:
    """
    Stores a single block’s metadata.
    block_type:   0=text, 1=image, etc.
    block_no:     sequence index in the page’s blocks list
    bbox:         Bounding box as a fitz.Rect
    text:         Extracted text (empty for non-text blocks)
    """
    block_no: int
    block_type: int
    bbox: fitz.Rect
    text: str

@dataclass
class PageCoordinates:
    """
    Container for all BlockInfo objects of a single PDF page.
    width/height mirror the page dimensions.
    """
    page_index: int
    width: float
    height: float
    blocks: List[BlockInfo] = field(default_factory=list)
    layout_mask: Optional[np.ndarray] = field(default=None, repr=False)

    @classmethod
    def from_page(cls, page_index: int, page: fitz.Page) -> "PageCoordinates":
        """
        Extracts every block on `page` into a PageCoordinates instance.
        Only type-0 blocks get their text concatenated; others have empty text.
        """
        rect = page.rect
        raw = page.get_text("dict")
        blocks: List[BlockInfo] = []

        for idx, blk in enumerate(raw["blocks"]):
            btype = blk.get("type", -1)
            bbox  = fitz.Rect(blk["bbox"])

            text = ""
            if btype == 0:  # text block
                lines = [
                    "".join(span["text"] for span in line.get("spans", []))
                    for line in blk.get("lines", [])
                ]
                text = "\n".join(lines)

            blocks.append(BlockInfo(
                block_no=idx,
                block_type=btype,
                bbox=bbox,
                text=text
            ))

        return cls(
            page_index=page_index,
            width=rect.width,
            height=rect.height,
            blocks=blocks
        )

# Load OpenAI key from .env
load_dotenv()

# Map UI names → prompt names
LANG_PROMPT = {
    "Chinese":  "Simplified Chinese",
    "English":  "English",
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

def extract_layout_pages(
    doc: fitz.Document,
    model: Any,
    pages: Optional[List[int]] = None,
    ignore_classes: Optional[List[str]] = None
) -> Dict[int, PageCoordinates]:
    """
    Dùng OnnxModel (hoặc model tương tự) để detect các box layout trên từng page,
    build 1 numpy mask và gắn vào PageCoordinates.layout_mask.
    Trả về dict: page_index → PageCoordinates.
    """
    if ignore_classes is None:
        # các lớp không phải text (foil, bảng, chú thích công thức…)
        ignore_classes = ["abandon", "figure", "table", "isolate_formula", "formula_caption"]

    pages_idx = pages if pages is not None else list(range(len(doc)))
    result: Dict[int, PageCoordinates] = {}

    for pno in pages_idx:
        page = doc[pno]
        pc = PageCoordinates.from_page(pno, page)

        pix = page.get_pixmap()
        h, w = pix.height, pix.width
        img = np.frombuffer(pix.samples, np.uint8).reshape(h, w, pix.n).astype(np.uint8)[..., ::-1]

        pred = model.predict(img, imgsz=(h // 32) * 32)[0]

        mask = np.ones((h, w), dtype=np.int32)

        for i, box in enumerate(pred.boxes):
            cls_name = pred.names[int(box.cls)]
            x0, y0, x1, y1 = box.xyxy.squeeze()
            x0, y0, x1, y1 = (
                max(int(x0 - 1), 0),
                max(int(h - y1 - 1), 0),
                min(int(x1 + 1), w - 1),
                min(int(h - y0 + 1), h - 1),
            )
            if cls_name in ignore_classes:
                mask[y0:y1, x0:x1] = 0
            else:
                mask[y0:y1, x0:x1] = i + 2

        pc.layout_mask = mask
        result[pno] = pc

    return result

def detect_paragraphs(
    blocks: List[BlockInfo],
    x_tol: float = 50.0,
    y_tol: float = 5.0,
    punctuations: str = ".!?"
) -> List[List[BlockInfo]]:
    """
    Nhóm các BlockInfo text thành danh sách các đoạn văn dựa trên:
    1) Phân vùng cột (x_tol)
    2) Khoảng cách dọc (y_tol)
    3) Dấu câu kết thúc (punctuations)
    """
    # 1) Lọc chỉ lấy text blocks
    text_blocks = [b for b in blocks if b.block_type == 0]
    if not text_blocks:
        return []

    # 2) Phân nhóm theo cột dựa vào x0
    sorted_by_x = sorted(text_blocks, key=lambda b: b.bbox.x0)
    columns: List[List[BlockInfo]] = []
    for blk in sorted_by_x:
        if not columns:
            columns.append([blk])
        else:
            last = columns[-1]
            # nếu cách nhau xa về x mới sang cột khác
            if blk.bbox.x0 - last[-1].bbox.x0 > x_tol:
                columns.append([blk])
            else:
                last.append(blk)

    # 3) Với mỗi cột, sắp xếp theo y rồi group thành paragraph
    paragraphs: List[List[BlockInfo]] = []
    for col in columns:
        sorted_col = sorted(col, key=lambda b: (b.bbox.y0, b.bbox.x0))
        curr_para = [sorted_col[0]]
        for prev, blk in zip(sorted_col, sorted_col[1:]):
            gap = blk.bbox.y0 - prev.bbox.y1
            prev_txt = prev.text.strip()
            # Xét điều kiện dừng đoạn
            end_with_punct = bool(prev_txt and prev_txt[-1] in punctuations)
            if (gap <= y_tol and (not end_with_punct or prev_txt.endswith('-'))):
                # cùng đoạn: nối
                curr_para.append(blk)
            else:
                paragraphs.append(curr_para)
                curr_para = [blk]
        paragraphs.append(curr_para)

    return paragraphs


def convert_pdf(
    input_pdf: str,
    output_pdf: str,
    target_lang: str,
    api_key: str,
    layout_model: Any
) -> None:

    if not api_key:
        raise ValueError("API key is required")
    openai.api_key = api_key
    doc = fitz.open(input_pdf)
    out = fitz.open()  # new PDF
    layouts: Dict[int, PageCoordinates] = extract_layout_pages(doc, layout_model)

    delimiter = "\n====BLOCK====\n"
    total = len(doc)
    for i in range(total):
        page = doc[i]

        # Extract all blocks with bounding boxes
        raw = page.get_text("dict")
        pc = PageCoordinates.from_page(i, page)
        text_blocks = [blk for blk in pc.blocks if blk.block_type == 0]
        block_texts = [blk.text for blk in text_blocks]

        joined = delimiter.join(block_texts)
        print(f"[2/3] Translating page {i+1}/{total} …")
        translated = translate_text(joined, target_lang)
        print(f"[DEBUG] Page {i+1} translated text:\n{translated}")
        translated_blocks = translated.split(delimiter)

        # Create a new page with same dimensions
        r = page.rect
        newp = out.new_page(width=r.width, height=r.height)

        # Re-insert images
        for blk in pc.blocks:
            if blk.block_type == 1:
                raw_blk = raw["blocks"][blk.block_no]
                xref = raw_blk.get("xref", raw_blk.get("image"))
                if not isinstance(xref, int):
                    continue
                imginfo = doc.extract_image(xref)
                newp.insert_image(blk.bbox, stream=imginfo["image"])

        # Insert translated text into original positions
        for blk, txt in zip(text_blocks, translated_blocks):
            newp.insert_textbox(
                blk.bbox,
                txt,
                fontsize=12,
                fontname="helv",
                align=0
            )

    # Save output
    print(f"[3/3] Saving translated PDF to {output_pdf}")
    out.save(output_pdf)
    print("Done.")