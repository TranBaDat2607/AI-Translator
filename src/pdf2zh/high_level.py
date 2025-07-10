import pikepdf
import re
import os
from pdf2zh.cache import CachedTranslator
from pdf2zh.translator.openai_translator import OpenAITranslator
from pdf2zh.translator.gemini_translator import GeminiTranslator
from pdf2zh.core import convert_pdf

# Regex to find TJ and Tj operators
_TJ_STRING = re.compile(rb'\((.*?)\)\s*TJ', re.DOTALL)
_Tj_STRING = re.compile(rb'\((.*?)\)\s*Tj')

def _escape_pdf(s: str) -> bytes:
    # Escape backslash and parentheses in PDF literal
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)').encode('latin1')

# def translate_pdf_streams(
#     input_pdf: str,
#     output_pdf: str,
#     service: str,
#     api_key: str,
#     src_lang: str,
#     tgt_lang: str,
#     cache_db: str
# ) -> None:
#     """
#     Full-pipeline: keep all content stream (fonts, locs, operators),
#     only replace literal text in (… ) Tj / (…) TJ.
#     """
#     # 1) initialize translator + cache
#     mapper = {
#         "OpenAI": OpenAITranslator,
#         "Gemini": GeminiTranslator
#     }
#     if service not in mapper:
#         raise ValueError(f"Unsupported service {service}")
#     inner = mapper[service](api_key)
#     translator = CachedTranslator(inner, cache_db)

#     # 2) open PDF
#     pdf = pikepdf.Pdf.open(input_pdf, allow_overwriting_input=True)

#     # 3) for each page, replace content-stream
#     for page in pdf.pages:
#         # Normalize and flatten content streams (handle nested arrays)
#         contents = page.Contents
#         def _iter_streams(obj):
#             if isinstance(obj, pikepdf.Stream):
#                 yield obj
#             else:
#                 try: 
#                     iterator = iter(obj)
#                 except TypeError:
#                     return 
#                 for elem in iterator:
#                     yield from _iter_streams(elem)

#         stream_objs = list(_iter_streams(contents))
#         # Read and concatenate all stream bytes
#         raw = b"".join(s.read_bytes() for s in stream_objs)

#         # 3.1 collect all literal text to translate
#         originals = []
#         spans = []
#         for pat in (_Tj_STRING, _TJ_STRING):
#             for m in pat.finditer(raw):
#                 data = m.group(1)
#                 originals.append(data)
#                 spans.append((m.start(1), m.end(1), pat is _TJ_STRING))

#         if not originals:
#             continue

#         # decode by Latin1 to keep byte-to-char mapping
#         str_texts = [o.decode('latin1') for o in originals]

#         # 3.2 translate
#         trans_texts = translator.translate(str_texts, src_lang, tgt_lang)

#         # 3.3 rebuild raw, replace each literal one by one
#         new_raw = bytearray(raw)
#         delta = 0
#         for (start, end, is_array), orig_bytes, tr in zip(spans, originals, trans_texts):
#             # escape and encode to bytes
#             esc = _escape_pdf(tr)
#             # replace in bytearray
#             s = start + delta
#             e = end   + delta
#             # write esc to position s:e
#             new_raw[s:e] = esc
#             delta += len(esc) - (end - start)

#         # 3.4 assign back
#         new_stream = pdf.make_stream(bytes(new_raw))
#         page.Contents = new_stream

#     # 4) save
#     pdf.save(output_pdf)

_TEXT_PAT = re.compile(rb'\(([^)]*)\)\s*(Tj|TJ)', re.DOTALL)

def translate_pdf_streams(
    input_pdf: str,
    output_pdf: str,
    service: str,
    api_key: str,
    src_lang: str,
    tgt_lang: str,
    cache_db: str
) -> None:
    """
    Thay literal text trong content streams, giữ nguyên font + vị trí gốc.
    """
    # 1) Khởi translator + cache
    mapper = {"OpenAI": OpenAITranslator, "Gemini": GeminiTranslator}
    inner = mapper[service](api_key)
    translator = CachedTranslator(inner, cache_db)

    # 2) Load PDF
    pdf = pikepdf.Pdf.open(input_pdf, allow_overwriting_input=True)

    # 3) Duyệt pages
    for page in pdf.pages:
        # 3.1: collect tất cả content streams flatten
        def iter_streams(obj):
            if isinstance(obj, pikepdf.Stream):
                yield obj
            else:
                try:
                    for elm in obj:
                        yield from iter_streams(elm)
                except TypeError:
                    return

        streams = list(iter_streams(page.Contents))
        raw_bytes = b"".join(s.read_bytes() for s in streams)

        # 3.2: find all literal strings
        spans = []
        originals = []
        for m in _TEXT_PAT.finditer(raw_bytes):
            spans.append((m.start(1), m.end(1)))
            originals.append(m.group(1))

        if not originals:
            continue

        # 3.3: decode & translate
        texts = [b.decode('latin1') for b in originals]
        translated = translator.translate(texts, src_lang, tgt_lang)

        # 3.4: rebuild new raw bytes with escapes
        new_raw = bytearray(raw_bytes)
        delta = 0
        for (s0, e0), orig_bytes, tr_text in zip(spans, originals, translated):
            # escape \(, \), \\ trên kết quả dịch
            esc = (tr_text
                   .replace("\\", "\\\\")
                   .replace("(", "\\(")
                   .replace(")", "\\)")
                   .encode('latin1', 'ignore'))
            s = s0 + delta
            e = e0 + delta
            new_raw[s:e] = esc
            delta += len(esc) - (e0 - s0)

        # 3.5: replace streams
        new_stream = pdf.make_stream(bytes(new_raw))
        page.Contents = new_stream

    # 4) Save
    pdf.save(output_pdf)