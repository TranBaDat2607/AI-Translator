import fitz
from typing import List, Tuple, Optional
from functools import lru_cache
import re

# Thử import pyphen nếu muốn hyphenation
try:
    import pyphen
except ImportError:
    pyphen = None

from .core import BlockInfo, _find_system_vn_font

class ReflowRenderer:
    def __init__(
        self,
        line_spacing: float = 1.2,
        min_fontsize: float = 4.0,
        max_iter: int = 10,
        debug: bool = False,
        hyphen_lang: str = "en_US"
    ):
        self.line_spacing = line_spacing
        self.min_fontsize = min_fontsize
        self.max_iter = max_iter
        self.debug = debug
        self.hyph = pyphen.Pyphen(lang=hyphen_lang) if (pyphen and hyphen_lang) else None

    def _split_paragraphs(self, text: str) -> List[str]:
        """
        Tách text thành các đoạn (paragraph) dựa trên dòng trống (\n\n).
        Bên trong mỗi paragraph, merge physical line-wrap (\n) thành space.
        """
        paras: List[str] = []
        # 1) tách ra theo paragraph (giữa hai paragraph thường có \n\n)
        raw_paras = text.split("\n\n")
        for rp in raw_paras:
            # 2) merge các line-wrap thành space
            merged = rp.replace("\n", " ").strip()
            if merged:
                paras.append(merged)
        return paras


    @lru_cache(maxsize=2048)
    def _measure(self, fontfile: Optional[str], fontname: Optional[str], text: str, fontsize: float) -> float:
        # đo chiều dài text một cách cached
        font = (
            fitz.Font(fontfile=fontfile, fontname=fontname)
            if fontfile or fontname
            else fitz.Font()
        )
        return font.text_length(text, fontsize)

    def _hyphenate(self, word: str, fontfile: Optional[str], fontname: Optional[str], fontsize: float, max_width: float) -> List[str]:
        # phân tách từ dài thành các phần có thể hyphenate
        if self.hyph:
            sylls = self.hyph.inserted(word).split("-")
        else:
            sylls = [word]
        parts: List[str] = []
        curr = ""
        for syl in sylls:
            token = syl + "-"  # thêm dấu gạch nối nếu hyphen
            if self._measure(fontfile, fontname, curr + token, fontsize) <= max_width:
                curr += token
            else:
                if curr:
                    parts.append(curr.rstrip("-"))
                # nếu phần syl vẫn quá dài, cắt ký tự
                frag = ""
                for ch in syl:
                    if self._measure(fontfile, fontname, frag + ch, fontsize) <= max_width:
                        frag += ch
                    else:
                        if frag:
                            parts.append(frag)
                        frag = ch
                curr = frag
        if curr:
            parts.append(curr.rstrip("-"))
        return parts

    def _wrap_paragraph(
        self,
        words: List[str],
        fontfile: Optional[str],
        fontname: Optional[str],
        fontsize: float,
        max_width: float
    ) -> List[str]:
        lines: List[str] = []
        curr = ""
        for w in words:
            cand = f"{curr} {w}" if curr else w
            if self._measure(fontfile, fontname, cand, fontsize) <= max_width:
                curr = cand
            else:
                if curr:
                    lines.append(curr)
                # hyphenation / char-split
                parts = self._hyphenate(w, fontfile, fontname, fontsize, max_width)
                for p in parts[:-1]:
                    lines.append(p + "-")
                curr = parts[-1]
        if curr:
            lines.append(curr)
        return lines

    def _wrap_text(
        self,
        text: str,
        fontfile: Optional[str],
        fontname: Optional[str],
        fontsize: float,
        max_width: float
    ) -> List[str]:
        lines: List[str] = []
        for para in self._split_paragraphs(text):
            words = para.split()
            if not words:
                # giữ blank line
                lines.append("")
                continue
            wrapped = self._wrap_paragraph(words, fontfile, fontname, fontsize, max_width)
            lines.extend(wrapped)
        return lines

    def reflow(
        self,
        text: str,
        fontfile: Optional[str],
        fontname: Optional[str],
        initial_fs: float,
        max_width: float,
        max_height: float
    ) -> Tuple[List[str], float]:
        """
        Wrap và tự động scale font cho đến khi text vừa khung.
        """
        fs = initial_fs
        for _ in range(self.max_iter):
            lines = self._wrap_text(text, fontfile, fontname, fs, max_width)
            # tính line height chuẩn qua font.height()
            line_h = fs * self.line_spacing
            total_h = len(lines) * line_h
            if total_h <= max_height or fs <= self.min_fontsize:
                break
            # giảm 10% mỗi vòng, nhưng không xuống dưới min
            fs = max(fs * 0.9, self.min_fontsize)
        # wrap lại với fs cuối
        lines = self._wrap_text(text, fontfile, fontname, fs, max_width)
        return lines, fs

    def render_page(
        self,
        page: fitz.Page,
        blocks: List[BlockInfo],
        translations: List[str],
        debug: bool
    ) -> None:
        """
        Render lại toàn bộ các khối đã dịch với logic tự wrap & auto‐font‐size.
        """
        fontfile = _find_system_vn_font()
        fontname = "ReflowFont" if fontfile else None
        if fontfile:
            try:
                page.insert_font(fontfile=fontfile, fontname=fontname)
            except Exception:
                fontname = None

        font = fitz.Font(fontfile=fontfile, fontname=fontname) if fontfile else fitz.Font()

        for blk, txt in zip(blocks, translations):
            if debug:
                page.draw_rect(
                    blk.bbox,
                    color = (1, 0, 0),
                    width = 0.5
                )

            if not txt.strip():
                continue
            rect = blk.bbox
            init_fs = blk.font_size if blk.font_size and blk.font_size > 0 else 12.0
            lines, fs = self.reflow(
                text=txt,
                fontfile=fontfile,
                fontname=fontname,
                initial_fs=init_fs,
                max_width=rect.width,
                max_height=rect.height
            )
            try:
                base_h = font.height(fs)
            except Exception:
                try:
                    ascent = font.ascent
                    descent = font.descent
                    base_h = (ascent - descent) * fs / 1000
                except AttributeError:
                    base_h = fs

            line_h = base_h * self.line_spacing

            try:
                # font.ascent cho biết khoảng cách từ baseline tới đỉnh glyph (theo đơn vị font)
                asc = font.ascent * fs / 1000
            except Exception:
                # fallback khớp gần đúng nếu không có .ascent
                asc = fs * 0.8

            x0 = rect.x0
            # baseline của dòng đầu = bbox.y0 + ascender
            baseline0 = rect.y0 + asc

            x0, y0 = rect.x0, rect.y0
            for i, line in enumerate(lines):
                yb = baseline0 + i * line_h
                page.insert_text(
                    (x0, yb),
                    line,
                    fontsize=fs,
                    fontname=fontname,
                    color=(0, 0, 0)
                )
