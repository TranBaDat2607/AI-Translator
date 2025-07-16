import os
import re
from typing import List, Tuple, Optional

import fitz        # PyMuPDF
import pdfplumber

from .core import PageCoordinates, BlockInfo, translate_text, _find_system_vn_font

def wrap_text(
    text: str,
    font: fitz.Font,
    fontsize: float,
    max_width: float
) -> List[str]:
    words = text.split()
    lines: List[str] = []
    curr = ""
    for w in words:
        cand = f"{curr} {w}" if curr else w
        if font.text_length(cand, fontsize) <= max_width:
            curr = cand
        else:
            if curr:
                lines.append(curr)
            # nếu từ đơn vẫn quá dài thì cắt ký tự
            part = ""
            for ch in w:
                if font.text_length(part + ch, fontsize) <= max_width:
                    part += ch
                else:
                    if part:
                        lines.append(part)
                    part = ch
            curr = part
    if curr:
        lines.append(curr)
    return lines

def reflow(
    text: str,
    font: fitz.Font,
    initial_fs: float,
    max_width: float,
    max_height: float,
    line_spacing: float = 1.2,
    min_fontsize: float = 4.0
) -> Tuple[List[str], float]:
    fs = initial_fs
    while True:
        lines = wrap_text(text, font, fs, max_width)
        total_h = len(lines) * fs * line_spacing
        if total_h <= max_height or fs <= min_fontsize:
            break
        fs = max(fs * (max_height / total_h), min_fontsize)
        if fs <= min_fontsize:
            fs = min_fontsize
            break
    # wrap lần cuối với fs cố định
    lines = wrap_text(text, font, fs, max_width)
    return lines, fs

def render_manual_page(
    page: fitz.Page,
    blocks: List[BlockInfo],
    translations: List[str],
    line_spacing: float = 1.2,
    min_fontsize: float = 4.0,
    debug: bool = False
) -> None:
    # chuẩn bị font
    fontfile = _find_system_vn_font()
    try:
        font = fitz.Font(fontfile=fontfile) if fontfile else fitz.Font()
    except Exception:
        font = fitz.Font()
    fontname = "ManualFont" if fontfile else None
    if fontfile and fontname:
        try:
            page.insert_font(fontfile=fontfile, fontname=fontname)
        except Exception:
            fontname = None

    for blk, txt in zip(blocks, translations):
        if not txt.strip():
            continue
        rect = blk.bbox
        init_fs = blk.font_size if blk.font_size and blk.font_size > 0 else 12
        lines, fs = reflow(
            text=txt,
            font=font,
            initial_fs=init_fs,
            max_width=rect.width,
            max_height=rect.height,
            line_spacing=line_spacing,
            min_fontsize=min_fontsize
        )
        x0, y0 = rect.x0, rect.y0
        for i, line in enumerate(lines):
            y = y0 + i * fs * line_spacing
            if debug:
                # kẻ khung kiểm tra
                page.draw_rect(
                    fitz.Rect(x0, y, x0 + rect.width, y + fs * line_spacing),
                    color=(1, 0, 0), width=0.25
                )
            page.insert_text(
                (x0, y),
                line,
                fontsize=fs,
                fontname=fontname,
                color=(0, 0, 0)
            )

def build_pdf_manual(
    input_pdf: str,
    output_pdf: str,
    target_lang: str,
    api_key: str,
    line_spacing: float = 1.2,
    min_fontsize: float = 4.0,
    debug: bool = False
) -> None:
    """
    1) Mở PDF gốc
    2) Với mỗi trang:
         - trích blocks (text/image)
         - fallback pdfplumber nếu text rỗng/garbled
         - tạo trang mới, re-insert images
         - dịch từng BlockInfo.text
         - render từng dòng qua render_manual_page
    3) Lưu output_pdf
    """
    if not api_key:
        raise ValueError("API key is required")
    import openai
    openai.api_key = api_key

    src = fitz.open(input_pdf)
    pdfp = pdfplumber.open(input_pdf)
    out = fitz.open()
    total = len(src)

    for i in range(total):
        print(f"[PAGE] {i+1}/{total}")
        page = src[i]
        pc = PageCoordinates.from_page(i, page)

        # fallback text với pdfplumber
        h = page.rect.height
        p_p = pdfp.pages[i]
        for blk in pc.blocks:
            if blk.block_type == 0 and (not blk.text.strip() or "·" in blk.text):
                x0, y0, x1, y1 = blk.bbox
                top = h - y1; bottom = h - y0
                crop = p_p.within_bbox((x0, top, x1, bottom))
                txt = crop.extract_text()
                if txt:
                    blk.text = txt

        # tạo trang mới
        r = page.rect
        newp = out.new_page(width=r.width, height=r.height)

        # re-insert images
        raw = page.get_text("dict")
        for blk in pc.blocks:
            if blk.block_type == 1:
                rb = raw["blocks"][blk.block_no]
                xref = rb.get("xref") or rb.get("image")
                if isinstance(xref, int):
                    img = src.extract_image(xref)["image"]
                    newp.insert_image(blk.bbox, stream=img)

        # dịch text blocks
        text_blocks = [b for b in pc.blocks if b.block_type == 0 and b.text.strip()]
        translations: List[str] = []
        for blk in text_blocks:
            clean = re.sub(r"-(\s*\n\s*)", "", blk.text)
            tr = translate_text(clean, target_lang)
            translations.append(tr)

        # render bằng manual reflow
        render_manual_page(
            newp,
            text_blocks,
            translations,
            line_spacing=line_spacing,
            min_fontsize=min_fontsize,
            debug=debug
        )

    print(f"[SAVE] {output_pdf}")
    out.save(output_pdf)
    print("Done.")