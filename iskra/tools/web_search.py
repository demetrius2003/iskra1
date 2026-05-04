"""Поиск DuckDuckGo + краткая сводка через LLM (опционально ``pip install duckduckgo-search`` или ``pip install ".[web]"`` из корня репозитория)."""

from __future__ import annotations

import sys
import warnings

from iskra.llm.protocol import LLMAdapter

SUMMARY_SYSTEM = (
    "Ты помощник: по приведённым фрагментам результатов поиска сделай краткую связную сводку "
    "на русском. Не добавляй факты, которых нет во фрагментах."
)


def fetch_duckduckgo_snippets(query: str, *, max_results: int = 5) -> list[str]:
    """Текстовые сниппеты (title + body). Бросает ImportError без пакета ``duckduckgo_search``."""
    try:
        from duckduckgo_search import DDGS
    except ImportError as e:
        exe = sys.executable
        raise ImportError(
            f"Для веб-поиска установите duckduckgo-search в тот же Python, что запускает Iskra "
            f'(сейчас: {exe}). Команда: "{exe}" -m pip install duckduckgo-search '
            '(или из корня репозитория: pip install ".[web]" тем же интерпретатором). '
            "Не путать с `pip install iskra[web]` на PyPI — там другой пакет."
        ) from e

    out: list[str] = []
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*renamed to.*ddgs.*",
            category=RuntimeWarning,
        )
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                title = (item.get("title") or "").strip()
                body = (item.get("body") or "").strip()
                if title and body:
                    out.append(f"{title}\n{body}")
                elif body:
                    out.append(body)
                elif title:
                    out.append(title)
    return out


async def summarize_snippets(
    adapter: LLMAdapter,
    query: str,
    snippets: list[str],
    *,
    summary_max_tokens: int,
) -> str:
    if not snippets:
        return "(Поиск не вернул текстовых результатов.)"
    blob = "\n\n---\n\n".join(snippets)
    user = (
        f"Запрос: {query}\n\nФрагменты:\n{blob}\n\n"
        f"Сделай краткую сводку (ориентир около {summary_max_tokens} токенов, можно короче)."
    )
    resp = await adapter.complete(SUMMARY_SYSTEM, user)
    return (resp.content or "").strip()
