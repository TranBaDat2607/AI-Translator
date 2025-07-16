#!/usr/bin/env python3
import sys
import os

# --- Thêm src/ vào path để import pdf2zh ---
this_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(this_dir, os.pardir))
src_dir = os.path.join(project_root, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# --- Imports chính ---
import fitz
import pymupdf
from pdf2zh.layout import ReflowRenderer
from pdf2zh.core import BlockInfo

def main():
    # 1) Thiết lập dữ liệu test
    text = "DeepFace: Thu hẹp khoảng cách đến hiệu suất nhận diện khuôn mặt ở mức độ con người"
    bbox = pymupdf.Rect(59.89099884033203, 105.9219970703125, 535.3385620117188, 120.26819610595703)
    blk = BlockInfo(
        block_no=0,
        block_type=0,
        bbox=bbox,
        text=text,
        font_size=14.346199989318848
    )

    # 2) Tạo document và trang mới đủ lớn
    doc = fitz.open()
    page = doc.new_page()

    # 3) Render text vào trang
    renderer = ReflowRenderer(line_spacing=1.2, min_fontsize=4.0, debug=True)
    renderer.render_page(
        page=page,
        blocks=[blk],
        translations=[text]
    )
    # 4) Lưu file và thông báo
    out_path = os.path.join(project_root, "out_manual.pdf")
    doc.save(out_path)
    print(f"[DONE] Saved demo PDF to {out_path}")

if __name__ == "__main__":
    main()