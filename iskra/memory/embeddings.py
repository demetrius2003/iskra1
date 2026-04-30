"""Sentence embeddings (optional ``sentence-transformers``)."""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Callable
from typing import TYPE_CHECKING

logger = logging.getLogger("iskra.memory.embeddings")

if TYPE_CHECKING:
    pass


def make_hash_embedder(dim: int = 384) -> Callable[[str], list[float]]:
    """Детерминированные векторы из SHA-256 (без PyTorch). Только для миграции / отладки.

    Не отражают смысл текста: векторный ``recall`` по ``context`` будет некачественным.
    """
    if dim < 8 or dim > 4096:
        raise ValueError("hash embedder dim must be between 8 and 4096")

    def embed(text: str) -> list[float]:
        if not text.strip():
            return [0.0] * dim
        block: bytes = hashlib.sha256(text.encode("utf-8")).digest()
        out: list[float] = []
        while len(out) < dim:
            block = hashlib.sha256(block).digest()
            for b in block:
                out.append((float(b) / 127.5) - 1.0)
        out = out[:dim]
        s = math.sqrt(sum(x * x for x in out))
        if s > 0:
            out = [x / s for x in out]
        return out

    embed.__iskra_embedding_dim__ = dim  # type: ignore[attr-defined]
    return embed


def make_embedder(model_name: str) -> Callable[[str], list[float]]:
    """Return ``text -> vector`` (float32 list). Requires ``pip install iskra[memory]``."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError(
            "Расширенная память требует sentence-transformers. Установите: pip install iskra[memory]"
        ) from e

    try:
        model = SentenceTransformer(model_name)
    except OSError as e:
        raise ImportError(
            "Не удалось загрузить PyTorch/sentence-transformers. На Windows чаще всего: "
            "WinError 1114 при загрузке c10.dll — поставьте VC++ Redistributable x64 и перезагрузите ПК, "
            "затем переустановите torch с pytorch.org (см. docs/QUICKSTART.md § 4c). "
            "Обход без torch: `memory.v2.embeddings_backend: hash` или "
            "`python -m iskra migrate --config config.yaml --dummy-embeddings`. "
            f"Исходная ошибка: {e}"
        ) from e
    dim = model.get_sentence_embedding_dimension()

    def embed(text: str) -> list[float]:
        if not text.strip():
            return [0.0] * dim
        vec = model.encode(text, normalize_embeddings=True)
        return vec.astype("float32").tolist()

    embed.__iskra_embedding_dim__ = dim  # type: ignore[attr-defined]
    logger.info("embeddings: loaded %s (dim=%s)", model_name, dim)
    return embed


def embedding_dim(embedder: Callable[[str], list[float]]) -> int:
    d = getattr(embedder, "__iskra_embedding_dim__", None)
    if isinstance(d, int) and d > 0:
        return d
    v = embedder("probe")
    return len(v)
