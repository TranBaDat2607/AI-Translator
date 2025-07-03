from typing import List, Tuple, Dict, Any
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTTextContainer, LTChar


class CharDetail:
    def __init__(
        self,
        char: str,
        font_name: str,
        font_size: float,
        bbox: Tuple[float, float, float, float],
    ):
        self.char = char
        self.font_name = font_name
        self.font_size = font_size
        self.bbox = bbox

    def __repr__(self):
        return (
            f"CharDetail(char={self.char!r}, font_name={self.font_name!r}, "
            f"size={self.font_size}, bbox={self.bbox})"
        )

class WordsBlock:
    def __init__(
        self,
        block_id: int,
        page_id: int,
        content: str,
        bbox: Tuple[float, float, float, float],
        chars: List[CharDetail],
    ):
        self.block_id = block_id
        self.page_id = page_id
        self.content = content
        self.bbox = bbox
        self.chars = chars

    def __repr__(self):
        return (
            f"WordsBlock(block_id={self.block_id}, page_id={self.page_id}, "
            f"text={self.content!r}, bbox={self.bbox}, chars={self.chars})"
        )

class PDFProcessor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def extract_text_blocks(self) -> List[Dict[str, Any]]:
        """
        Đọc file PDF và trả về danh sách các text-block,
        mỗi block có: block_id, page_id, text, bbox (x0,y0,x1,y1)
        và danh sách chi tiết từng ký tự (char, fontname, size, bbox).
        """
        blocks: List[Dict[str, Any]] = []
        block_id = 0

        # vòng lặp qua từng trang, extract_pages trả về LTPage objects
        for page_num, layout in enumerate(extract_pages(self.pdf_path, laparams=LAParams())):
            for element in layout:
                if isinstance(element, LTTextContainer):
                    x0, y0, x1, y1 = element.bbox
                    text = element.get_text()
                    char_details: List[Dict[str, Any]] = []

                    # lặp xuống từng ký tự để lấy font, kích thước, tọa độ
                    for text_line in element:
                        for char in text_line:
                            if isinstance(char, LTChar):
                                char_details.append({
                                    "char": char.get_text(),
                                    "fontname": char.fontname,
                                    "size": char.size,
                                    "x0": char.bbox[0],
                                    "y0": char.bbox[1],
                                    "x1": char.bbox[2],
                                    "y1": char.bbox[3],
                                })

                    blocks.append({
                        "block_id": block_id,
                        "page_id": page_num,
                        "text": text,
                        "bbox": (x0, y0, x1, y1),
                        "chars": char_details,
                    })
                    block_id += 1

        return blocks