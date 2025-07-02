import concurrent.futures
import logging
import re
import unicodedata
from enum import Enum
from string import Template
from typing import Any, Dict, List

import numpy as np
from pdfminer.converter import PDFConverter
from pdfminer.layout import LTChar, LTFigure, LTLine, LTPage
from pdfminer.pdffont import PDFCIDFont, PDFUnicodeNotDefined
from pdfminer.pdfinterp import PDFGraphicState, PDFResourceManager
from pdfminer.utils import apply_matrix_pt, mult_matrix
from pymupdf import Font
from tenacity import retry, wait_fixed

from pdf2zh.translator.base import BaseTranslator

logger = logging.getLogger(__name__)

class PDFConverterEx(PDFConverter):
    def __init__(self, rsrcmgr: PDFResourceManager) -> None:
        # Khởi tạo PDFConverter với mặc định codec utf-8, pageno=1, không dùng laparams
        super().__init__(rsrcmgr, None, "utf-8", 1, None)

    def begin_page(self, page, ctm) -> None:
        # Bỏ cropbox gốc, dùng mediabox mới
        (x0, y0, x1, y1) = page.cropbox
        (x0, y0) = apply_matrix_pt(ctm, (x0, y0))
        (x1, y1) = apply_matrix_pt(ctm, (x1, y1))
        mediabox = (0, 0, abs(x0 - x1), abs(y0 - y1))
        self.cur_item = LTPage(page.pageno, mediabox)

    def end_page(self, page):
        # Khi end_page gọi receive_layout trả về chuỗi operators
        return self.receive_layout(self.cur_item)

    def begin_figure(self, name, bbox, matrix) -> None:
        self._stack.append(self.cur_item)
        self.cur_item = LTFigure(name, bbox, mult_matrix(matrix, self.ctm))
        self.cur_item.pageid = self._stack[-1].pageid

    def end_figure(self, _: str) -> None:
        fig = self.cur_item
        assert isinstance(self.cur_item, LTFigure)
        self.cur_item = self._stack.pop()
        self.cur_item.add(fig)
        return self.receive_layout(fig)

    def render_char(
        self,
        matrix,
        font,
        fontsize: float,
        scaling: float,
        rise: float,
        cid: int,
        ncs,
        graphicstate: PDFGraphicState,
    ) -> float:
        # Tương tự TextConverter, lưu lại LTChar với cid và font gốc
        try:
            text = font.to_unichr(cid)
        except PDFUnicodeNotDefined:
            text = self.handle_undefined_char(font, cid)
        textwidth = font.char_width(cid)
        textdisp = font.char_disp(cid)
        item = LTChar(
            matrix,
            font,
            fontsize,
            scaling,
            rise,
            text,
            textwidth,
            textdisp,
            ncs,
            graphicstate,
        )
        self.cur_item.add(item)
        item.cid = cid
        item.font = font
        return item.adv

class Paragraph:
    def __init__(self, y, x, x0, x1, y0, y1, size, brk):
        self.y: float = y       # bắt đầu y
        self.x: float = x       # bắt đầu x
        self.x0: float = x0     # left bound
        self.x1: float = x1     # right bound
        self.y0: float = y0     # top bound
        self.y1: float = y1     # bottom bound
        self.size: float = size # font size
        self.brk: bool = brk    # có ngắt dòng gốc không

class TranslateConverter(PDFConverterEx):
    """
    Nhóm LTChar thành các đoạn (paragraph) và công thức,
    dịch từng đoạn qua self.translator rồi sinh PDF-operators.
    """
    def __init__(
        self,
        rsrcmgr: PDFResourceManager,
        translator: BaseTranslator,
        src_lang: str,
        tgt_lang: str,
        thread: int = 1,
        vfont: str = "",
        vchar: str = "",
        layout: Dict[int, Any] = None,
        noto_name: str = "",
        noto: Font = None,
        ignore_cache: bool = False,
    ):
        super().__init__(rsrcmgr)
        self.translator = translator
        self.src = src_lang
        self.tgt = tgt_lang
        self.thread = thread
        self.layout = layout or {}
        self.vfont = vfont
        self.vchar = vchar
        self.noto_name = noto_name
        self.noto = noto
        self.ignore_cache = ignore_cache
        # fontmap/fontid sẽ được khởi khi render
        self.fontmap: Dict[str, Any] = {}
        self.fontid: Dict[Any, int] = {}

    def receive_layout(self, ltpage: LTPage) -> str:
        # --- A. Phân tích văn bản & công thức từ layout map ---
        sstk: List[str] = []
        pstk: List[Paragraph] = []
        vbkt = 0
        vstk: List[LTChar] = []
        vlstk: List[LTLine] = []
        vfix = 0
        var: List[List[LTChar]] = []
        varl: List[List[LTLine]] = []
        varf: List[float] = []
        vlen: List[float] = []
        lstk: List[LTLine] = []
        xt: LTChar = None
        xt_cls = -1
        vmax = ltpage.width / 4

        def vflag(fontname: str, ch: str) -> bool:
            # copy y hệt trong PDFMathTranslate để nhận diện công thức
            name = fontname.decode('utf-8') if isinstance(fontname, bytes) else fontname
            name = name.split("+")[-1]
            if re.match(r"\(cid:", ch):
                return True
            if self.vfont and re.match(self.vfont, name):
                return True
            if not self.vfont and re.match(
                r"(CM[^R]|MS.M|XY|MT|BL|RM|EU|LA|RS|LINE|LCIRCLE|TeX-|rsfs|txsy|wasy|stmary|.*Mono|.*Code|.*Ital|.*Sym|.*Math)",
                name):
                return True
            if self.vchar and re.match(self.vchar, ch):
                return True
            if not self.vchar and ch and ch!=" " and (
                unicodedata.category(ch[0]) in ["Lm","Mn","Sk","Sm","Zl","Zp","Zs"]
                or 0x370 <= ord(ch[0]) < 0x400
            ):
                return True
            return False

        for child in ltpage:
            if isinstance(child, LTChar):
                # 1) dựa vào self.layout để phân lớp cls
                layout_arr = self.layout.get(ltpage.pageid)
                if layout_arr is None:
                    cls = -1
                else:
                    h,w = layout_arr.shape
                    cx = int(np.clip(child.x0,0,w-1))
                    cy = int(np.clip(child.y0,0,h-1))
                    cls = int(layout_arr[cy,cx])
                cur_v = False
                if cls==0 or (vflag(child.fontname, child.get_text())) or \
                   (cls==xt_cls and len(sstk[-1].strip())>1 and child.size<pstk[-1].size*0.79) or \
                   (child.matrix[0]==0 and child.matrix[3]==0):
                    cur_v = True
                # nhóm formula theo ngoặc
                if not cur_v and vstk and child.get_text()=="(":
                    cur_v = True; vbkt+=1
                if vbkt and child.get_text()==")":
                    cur_v = True; vbkt-=1

                # Khi formula kết thúc, flush
                if vstk and (not cur_v or cls!=xt_cls or (sstk[-1]!="" and abs(child.x0-xt.x0)>vmax)):
                    if not cur_v and cls==xt_cls and child.x0>max([vch.x0 for vch in vstk]):
                        vfix = vstk[0].y0 - child.y0
                    if sstk[-1]=="":
                        xt_cls=-1
                    sstk[-1] += f"{{v{len(var)}}}"
                    var.append(vstk); varl.append(vlstk); varf.append(vfix)
                    vstk, vlstk, vfix = [], [], 0

                # Bắt đầu paragraph mới nếu cần
                if not vstk:
                    if cls==xt_cls:
                        if child.x0>xt.x1+1:
                            sstk[-1]+=" "
                        elif child.x1<xt.x0:
                            sstk[-1]+=" "; pstk[-1].brk=True
                    else:
                        sstk.append("")
                        pstk.append(Paragraph(child.y0, child.x0, child.x0, child.x0, child.y0, child.y1, child.size, False))

                # Đưa ký tự vào text hoặc formula
                if not cur_v:
                    # điều chỉnh y nếu gặp ký tự lớn hơn
                    if (child.size>pstk[-1].size or len(sstk[-1].strip())==1) and child.get_text()!=" ":
                        pstk[-1].y -= child.size-pstk[-1].size
                        pstk[-1].size = child.size
                    sstk[-1] += child.get_text()
                else:
                    if not vstk and cls==xt_cls and child.x0>xt.x0:
                        vfix = child.y0-xt.y0
                    vstk.append(child)

                # cập nhật bounding box
                pstk[-1].x0 = min(pstk[-1].x0, child.x0)
                pstk[-1].x1 = max(pstk[-1].x1, child.x1)
                pstk[-1].y0 = min(pstk[-1].y0, child.y0)
                pstk[-1].y1 = max(pstk[-1].y1, child.y1)

                xt, xt_cls = child, cls
            elif isinstance(child, LTFigure):
                continue
            elif isinstance(child, LTLine):
                layout_arr = self.layout.get(ltpage.pageid)
                if layout_arr is not None:
                    h,w = layout_arr.shape
                    cx = int(np.clip(child.x0,0,w-1))
                    cy = int(np.clip(child.y0,0,h-1))
                    cls = int(layout_arr[cy,cx])
                else:
                    cls = -1
                if vstk and cls==xt_cls:
                    vlstk.append(child)
                else:
                    lstk.append(child)
            else:
                continue

        # flush formula nếu còn
        if vstk:
            sstk[-1] += f"{{v{len(var)}}}"
            var.append(vstk); varl.append(vlstk); varf.append(vfix)

        # Phase B: dịch song song
        @retry(wait=wait_fixed(1))
        def worker(s: str) -> str:
            if not s.strip() or re.match(r"^\{v\d+\}$", s):
                return s
            # translate via CachedTranslator or BaseTranslator
            return self.translator.translate([s], self.src, self.tgt)[0]

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread) as executor:
            news = list(executor.map(worker, sstk))

        # Phase C: sinh PDF-operators mới
        def raw_string(fcur: str, cstk: str) -> str:
            if fcur==self.noto_name:
                return "".join(f"{self.noto.has_glyph(ord(c)):04x}" for c in cstk)
            elif isinstance(self.fontmap[fcur], PDFCIDFont):
                return "".join(f"{ord(c):04x}" for c in cstk)
            else:
                return "".join(f"{ord(c):02x}" for c in cstk)

        LANG_LINEHEIGHT_MAP = {
            "zh-cn":1.4,"zh-tw":1.4,"zh-hans":1.4,"zh-hant":1.4,"zh":1.4,
            "ja":1.1,"ko":1.2,"en":1.2,"ar":1.0,"ru":0.8,"uk":0.8,"ta":0.8
        }
        default_line_height = LANG_LINEHEIGHT_MAP.get(self.tgt.lower(),1.1)
        ops_list: List[str] = []
        _x,_y=0,0

        def gen_op_txt(font, size, x, y, rtxt):
            return f"/{font} {size:f} Tf 1 0 0 1 {x:f} {y:f} Tm [<{rtxt}>] TJ "

        def gen_op_line(x,y,xlen,ylen,linewidth):
            return f"ET q 1 0 0 1 {x:f} {y:f} cm [] 0 d 0 J {linewidth:f} w 0 0 m {xlen:f} {ylen:f} l S Q BT "

        # Kết hợp từng block đã dịch và placeholder công thức
        for idx,new in enumerate(news):
            para = pstk[idx]
            x,y,x0,x1=para.x,para.y,para.x0,para.x1
            size,brk=para.size,para.brk
            cstk="" ; fcur=None; lidx=0; ptr=0; tx=x
            vlen_local = []
            # tính chiều rộng các công thức
            for idv,v in enumerate(var):
                w = max(ch.x1 for ch in v) - v[0].x0
                vlen_local.append(w)
            # duyệt ký tự trong new, sinh ops_list
            while ptr<len(new):
                vy = re.match(r"\{\s*v([\d\s]+)\}", new[ptr:], re.IGNORECASE)
                mod=0
                if vy:
                    ptr+=len(vy.group(0))
                    vid=int(vy.group(1).replace(" ",""))
                    adv = vlen_local[vid]
                else:
                    ch=new[ptr]; ptr+=1
                    # giả sử Latin vs Non-Latin
                    ftry="tiro"
                    if self.fontmap.get(ftry).to_unichr(ord(ch))==ch:
                        fcur_=ftry
                    else:
                        fcur_ = self.noto_name
                    if fcur_==self.noto_name:
                        adv=self.noto.char_lengths(ch,size)[0]
                    else:
                        adv=self.fontmap[fcur_].char_width(ord(ch))*size
                # khi font đổi / formula / quá rộng
                if fcur_!=fcur or vy or x+adv>x1+0.1*size:
                    if cstk:
                        ops_list.append(gen_op_txt(fcur,size,tx,y - lidx*size*default_line_height, raw_string(fcur,cstk)))
                        cstk=""
                if vy:
                    fix = varf[vid] if fcur else 0
                    for vch in var[vid]:
                        vc=chr(vch.cid)
                        ops_list.append(gen_op_txt(
                            self.fontid[vch.font],
                            vch.size,
                            x + vch.x0 - var[vid][0].x0,
                            y + fix + vch.y0 - var[vid][0].y0 - lidx*size*default_line_height,
                            raw_string(self.fontid[vch.font],vc)
                        ))
                    for ln in varl[vid]:
                        if ln.linewidth<5:
                            ops_list.append(gen_op_line(
                                ln.pts[0][0]+x-var[vid][0].x0,
                                ln.pts[0][1]+fix-var[vid][0].y0 + y - lidx*size*default_line_height,
                                ln.pts[1][0]-ln.pts[0][0],
                                ln.pts[1][1]-ln.pts[0][1],
                                ln.linewidth
                            ))
                else:
                    if not cstk:
                        tx=x
                        if x==x0 and ch==" ":
                            adv=0
                        else:
                            cstk+=ch
                    else:
                        cstk+=ch
                fcur=fcur_; x+=adv-mod
            if cstk:
                ops_list.append(gen_op_txt(fcur,size,tx,y - lidx*size*default_line_height, raw_string(fcur,cstk)))

        # tất cả global lines
        for ln in lstk:
            if ln.linewidth<5:
                ops_list.append(gen_op_line(
                    ln.pts[0][0], ln.pts[0][1], 
                    ln.pts[1][0]-ln.pts[0][0], ln.pts[1][1]-ln.pts[0][1],
                    ln.linewidth
                ))

        return "BT " + "".join(ops_list) + " ET "

class OpType(Enum):
    TEXT = "text"
    LINE = "line"