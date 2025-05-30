"""
pdf2zh: core library for extracting and translating PDF → Markdown/PDF.
"""
from .core import translate_text, convert_pdf

__all__ = [
    "translate_text",
    "convert_pdf",
]