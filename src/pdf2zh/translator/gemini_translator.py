from typing import List
from .base import BaseTranslator
import requests

class GeminiTranslator(BaseTranslator):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Gemini API key must be provided")
        self.api_key = api_key

    def translate(self, texts: List[str], src: str, tgt: str) -> List[str]:
        results = []
        for t in texts:
            payload = {
                "model": "gemini-1.0",
                "source_language": src,
                "target_language": tgt,
                "text": t
            }
            headers = {"Authorization": f"Bearer {self.api_key}"}
            r = requests.post("https://api.gemini.example/v1/translate", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            results.append(data["translation"])
        return results
