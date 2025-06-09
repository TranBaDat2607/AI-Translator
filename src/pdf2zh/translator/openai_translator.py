from openai import OpenAI
from typing import List
from .base import BaseTranslator

class OpenAITranslator(BaseTranslator):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key is required")
        self.client = OpenAI(api_key=api_key)

    def translate(self, texts: List[str], src: str, tgt: str) -> List[str]:
        results = []
        for t in texts:
            prompt = (
                f"Please translate the following text into {tgt}. "
                "Do NOT modify any LaTeX or non-text content:\n\n" + t
            )

            resp = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful translator."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }

                ],
                temperature=0.0
            )
            results.append(resp.choices[0].message.content.strip())
        return results
