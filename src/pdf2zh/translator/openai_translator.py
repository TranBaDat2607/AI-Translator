import openai
from typing import List
from .base import BaseTranslator

class OpenAITranslator(BaseTranslator):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key is required")
        self.api_key = api_key

    def translate(self, texts: List[str], src: str, tgt: str) -> List[str]:
        # split, join if need keep formula, then call ChatCompletion
        openai.api_key = self.api_key
        results = []
        for t in texts:
            prompt = (
                f"Please translate the following text into {tgt}. "
                "Do NOT modify any LaTeX or non-text content:\n\n" + t
            )
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role":"system","content":"You are a helpful translator."},
                    {"role":"user","content":prompt}
                ],
                temperature=0.0
            )
            results.append(resp.choices[0].message.content.strip())
        return results
