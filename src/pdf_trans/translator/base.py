from abc import ABC, abstractmethod
from typing import List

class BaseTranslator(ABC):
    @abstractmethod
    def translate(self, texts: List[str], src: str, tgt: str) -> List[str]:
        """
        Take a list of strings, return a list of translated strings.
        src/tgt according to ISO code or name you map in config.
        """
        pass