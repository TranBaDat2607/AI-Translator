import pikepdf
import re
import os
from pdf2zh.cache import CachedTranslator
from pdf2zh.translator.openai_translator import OpenAITranslator
from pdf2zh.translator.gemini_translator import GeminiTranslator

# Regex to find TJ and Tj operators
_TJ_STRING = re.compile(rb'\((.*?)\)\s*TJ', re.DOTALL)
_Tj_STRING = re.compile(rb'\((.*?)\)\s*Tj')

def _escape_pdf(s: str) -> bytes:
    # Escape backslash and parentheses in PDF literal
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)').encode('latin1')

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
    Full-pipeline: keep all content stream (fonts, locs, operators),
    only replace literal text in (… ) Tj / (…) TJ.
    """
    # 1) initialize translator + cache
    mapper = {
        "OpenAI": OpenAITranslator,
        "Gemini": GeminiTranslator
    }
    if service not in mapper:
        raise ValueError(f"Unsupported service {service}")
    inner = mapper[service](api_key)
    translator = CachedTranslator(inner, cache_db)

    # 2) open PDF
    pdf = pikepdf.Pdf.open(input_pdf, allow_overwriting_input=True)

    # 3) for each page, replace content-stream
    for page in pdf.pages:
        # Normalize and flatten content streams (handle nested arrays)
        contents = page.Contents
        def _iter_streams(obj):
            if isinstance(obj, pikepdf.Stream):
                yield obj
            else:
                try: 
                    iterator = iter(obj)
                except TypeError:
                    return 
                for elem in iterator:
                    yield from _iter_streams(elem)

        stream_objs = list(_iter_streams(contents))
        # Read and concatenate all stream bytes
        raw = b"".join(s.read_bytes() for s in stream_objs)

        # 3.1 collect all literal text to translate
        originals = []
        spans = []
        for pat in (_Tj_STRING, _TJ_STRING):
            for m in pat.finditer(raw):
                data = m.group(1)
                originals.append(data)
                spans.append((m.start(1), m.end(1), pat is _TJ_STRING))

        if not originals:
            continue

        # decode by Latin1 to keep byte-to-char mapping
        str_texts = [o.decode('latin1') for o in originals]

        # 3.2 translate
        trans_texts = translator.translate(str_texts, src_lang, tgt_lang)

        # 3.3 rebuild raw, replace each literal one by one
        new_raw = bytearray(raw)
        delta = 0
        for (start, end, is_array), orig_bytes, tr in zip(spans, originals, trans_texts):
            # escape and encode to bytes
            esc = _escape_pdf(tr)
            # replace in bytearray
            s = start + delta
            e = end   + delta
            # write esc to position s:e
            new_raw[s:e] = esc
            delta += len(esc) - (end - start)

        # 3.4 assign back
        new_stream = pdf.make_stream(bytes(new_raw))
        page.Contents = new_stream

    # 4) save
    pdf.save(output_pdf)