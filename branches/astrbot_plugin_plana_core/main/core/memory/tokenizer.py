from __future__ import annotations

import re

try:
    import jieba  # type: ignore[import-untyped]

    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")
_SPLIT_PATTERN = re.compile(r"[/_ ,.:;!?\-\n\r\t，。！？；：、]+")


class SimpleTokenizer:
    """Tokenizer with optional jieba support.

    Falls back to character-level CJK splitting and whitespace-based
    splitting when jieba is unavailable.
    """

    def __init__(self, min_length: int = 2):
        self.min_length = max(1, min_length)

    @staticmethod
    def has_jieba() -> bool:
        return _HAS_JIEBA

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text into a deduplicated list of terms."""
        cleaned = text.strip().lower()
        if not cleaned:
            return []
        if _HAS_JIEBA:
            return self._jieba_tokenize(cleaned)
        return self._fallback_tokenize(cleaned)

    def search_terms(self, query: str) -> list[str]:
        """Extract search terms from a query string."""
        tokens = self.tokenize(query)
        return tokens[:8]

    def cosine_similarity(self, text_a: str, text_b: str) -> float:
        """Compute cosine similarity between two texts using token sets.

        Returns a float in [0.0, 1.0]. Uses word-set overlap (Jaccard-like
        cosine) via tokenized term vectors.
        """
        tokens_a = set(self.tokenize(text_a))
        tokens_b = set(self.tokenize(text_b))
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a & tokens_b)
        if intersection == 0:
            return 0.0
        import math

        return intersection / math.sqrt(len(tokens_a) * len(tokens_b))

    def _jieba_tokenize(self, text: str) -> list[str]:
        words = jieba.lcut_for_search(text)
        return self._dedupe(words)

    def _fallback_tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        # Split CJK characters into bigrams.
        for match in _CJK_RANGE.finditer(text):
            segment = match.group()
            for i in range(len(segment) - 1):
                tokens.append(segment[i : i + 2])
        # Split non-CJK parts by whitespace/punctuation.
        non_cjk = _CJK_RANGE.sub(" ", text)
        for part in _SPLIT_PATTERN.split(non_cjk):
            part = part.strip()
            if part:
                tokens.append(part)
        return self._dedupe(tokens)

    def _dedupe(self, tokens: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for token in tokens:
            token = token.strip()
            if len(token) < self.min_length or token in seen:
                continue
            seen.add(token)
            result.append(token)
        return result
