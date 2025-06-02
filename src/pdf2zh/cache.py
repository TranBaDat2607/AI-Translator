import sqlite3
import threading
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Tuple, Optional
from pdf2zh.translator.base import BaseTranslator

class CachedTranslator(BaseTranslator):
    """
    Wrapper around any BaseTranslator
    Save cache of key=(service, src, tgt, text) -> translated text
    """

    def __init__(self, inner: BaseTranslator, db_path: str):
        """
        inner: instance of OpenAITranslator/GeminiTranslator
        db_path: path to sqlite file
        """
        self.inner = inner
        self.db_path = db_path
        # ensure DB & table exists
        self._lock = threading.Lock()
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS translations (
                  service TEXT, src TEXT, tgt TEXT,
                  input TEXT, output TEXT,
                  PRIMARY KEY(service, src, tgt, input)
                )
            """)

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _lookup(self, key: Tuple[str,str,str,str]) -> Optional[str]:
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT output FROM translations WHERE service=? AND src=? AND tgt=? AND input=?",
                key
            )
            row = cur.fetchone()
            return row[0] if row else None

    def _store(self, key: Tuple[str,str,str,str], output: str):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO translations (service,src,tgt,input,output) VALUES (?,?,?,?,?)",
                (*key, output)
            )
            conn.commit()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))
    def _call_inner(self, texts, src, tgt):
        # gọi inner.translate, sẽ tự retry nếu lỗi mạng/API
        return self.inner.translate(texts, src, tgt)

    def translate(self, texts, src, tgt):
        results = []
        for t in texts:
            key = (self.inner.__class__.__name__, src, tgt, t)
            cached = self._lookup(key)
            if cached is not None:
                results.append(cached)
            else:
                translated = self._call_inner([t], src, tgt)[0]
                self._store(key, translated)
                results.append(translated)
        return results