"""Лексиконная оценка валентности и арузала текста (без внешних API)."""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
import yaml

logger = logging.getLogger("iskra.core.emotion")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zа-яёА-ЯЁ]+(?:-[a-zа-яёА-ЯЁ]+)?", text.lower())


class EmotionClassifier:
    """Подсчёт позитивных/негативных слов и простых маркеров арузала."""

    def __init__(
        self,
        *,
        positive: set[str],
        negative: set[str],
        high_arousal: set[str],
    ) -> None:
        self._pos = positive
        self._neg = negative
        self._arousal_words = high_arousal

    @classmethod
    def merge(cls, base: EmotionClassifier, extra: EmotionClassifier) -> EmotionClassifier:
        """Объединение лексиконов (множества объединяются; при совпадении слово один раз в категории)."""
        return cls(
            positive=base._pos | extra._pos,
            negative=base._neg | extra._neg,
            high_arousal=base._arousal_words | extra._arousal_words,
        )

    @classmethod
    def from_lexicon_sources(
        cls,
        lexicon_file: str | Path | None,
        *,
        lexicon_custom_file: str | Path | None = None,
    ) -> EmotionClassifier:
        """Базовый YAML + опциональный дополнительный файл (пользовательские слова без правки основного лексикона)."""
        base = cls.from_yaml_file(lexicon_file) if lexicon_file else cls(
            positive=set(), negative=set(), high_arousal=set()
        )
        if lexicon_custom_file:
            extra = cls.from_yaml_file(lexicon_custom_file)
            base = cls.merge(base, extra)
        return base

    def lexicon_counts(self) -> dict[str, int]:
        """Размеры загруженных списков (для preflight и метрик)."""
        return {
            "positive_words": len(self._pos),
            "negative_words": len(self._neg),
            "high_arousal_words": len(self._arousal_words),
            "distinct_tokens": len(self._pos | self._neg | self._arousal_words),
        }

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> EmotionClassifier:
        p = Path(path)
        if not p.is_file():
            logger.warning("emotion lexicon not found: %s — нейтральная классификация", p)
            return cls(positive=set(), negative=set(), high_arousal=set())
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("emotion lexicon load failed %s: %s", p, e)
            return cls(positive=set(), negative=set(), high_arousal=set())
        data = raw if isinstance(raw, dict) else {}
        pos = {str(w).lower() for w in data.get("positive_words", []) if str(w).strip()}
        neg = {str(w).lower() for w in data.get("negative_words", []) if str(w).strip()}
        har = {str(w).lower() for w in data.get("high_arousal_words", []) if str(w).strip()}
        return cls(positive=pos, negative=neg, high_arousal=har)

    def classify(self, text: str, *, max_chars: int | None = None) -> tuple[float, float]:
        """Возвращает ``(emotional_valence ∈ [-1,1], arousal ∈ [0,1])``.

        При ``max_chars`` текст усекается до первых N символов (стабильность и скорость на длинных ответах).
        """
        if max_chars is not None and len(text) > max_chars:
            text = text[:max_chars]

        if not text or not text.strip():
            return 0.0, 0.35

        tokens = _tokenize(text)
        if not tokens:
            raw_lower = text.lower()
            tokens = raw_lower.split()

        pos_hits = sum(1 for t in tokens if t in self._pos)
        neg_hits = sum(1 for t in tokens if t in self._neg)
        arousal_hits = sum(1 for t in tokens if t in self._arousal_words)

        exclam = text.count("!")
        caps = sum(1 for c in text if c.isupper())
        caps_ratio = caps / max(len(text), 1)

        denom = pos_hits + neg_hits + 3.0
        raw_v = (pos_hits - neg_hits) / denom
        valence = math.tanh(1.4 * raw_v)

        arousal = (
            0.28
            + 0.06 * min(exclam, 4)
            + 0.05 * min(arousal_hits, 5)
            + 0.35 * min(caps_ratio * 5.0, 1.0)
        )
        arousal = max(0.0, min(1.0, arousal))

        return float(valence), float(arousal)
