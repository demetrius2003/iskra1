# LLM Adapter (Адаптер к языковой модели)

> Авторитетный источник по типам и сигнатурам: [FORMAL_SPECIFICATION.md](FORMAL_SPECIFICATION.md), разделы 4.4 и 6.

## Принцип

Iskra-1 не привязана к конкретной LLM. Ядро генерирует промпты — а какая модель их обработает, определяется адаптером. Это позволяет:

- Начать с бесплатного варианта (Ollama + локальная модель).
- Переключиться на API (Grok, OpenAI, Anthropic) когда нужно качество.
- Тестировать без LLM вообще (mock-адаптер, который возвращает шаблонные ответы).

## Интерфейс

```python
class LLMAdapter(Protocol):
    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Отправляет промпт в LLM, возвращает структурированный ответ."""
        ...

    def is_available(self) -> bool:
        """Проверяет доступность модели (сеть, API-ключ, лимиты)."""
        ...
```

Метод `complete` — **асинхронный** (async), так как основной цикл Iskra-1 работает на asyncio. Возвращает `LLMResponse`:

```python
@dataclass(frozen=True)
class LLMResponse:
    event_id: str         # UUID события (заполняется вызывающим кодом)
    content: str          # текстовый ответ
    model: str            # какая модель ответила
    tokens_used: int      # для учёта расхода (0 для MockAdapter)
    latency_ms: int       # время отклика в миллисекундах
    timestamp: datetime   # UTC
```

### Исключения

Адаптеры бросают типизированные исключения, которые MainLoop обрабатывает:

```python
class LLMError(Exception): ...
class LLMTimeoutError(LLMError): ...
class LLMRateLimitError(LLMError): ...
class LLMNetworkError(LLMError): ...
```

## Реализации (MVP)

### MockAdapter
Возвращает шаблонный ответ из конфигурации. Нужен для отладки Trigger Engine и State Engine без API и внешних зависимостей. Не делает сетевых запросов.

### OllamaAdapter
Локальная модель через Ollama API (`POST /api/chat`). Бесплатно, работает без интернета. Зависимость: `httpx`.

### Будущее: OpenAIAdapter / GrokAdapter / AnthropicAdapter
Подключение к облачным API. Требует ключ и платную подписку. Даёт лучшее качество генерации.

## Обработка ограничений

Retry-логика реализована в **MainLoop**, а не в адаптере:
- **Timeout** → retry до `max_attempts` раз с экспоненциальным backoff.
- **Rate limit (429)** → MainLoop переходит в «тихий режим» на `cooldown_on_rate_limit_seconds`.
- **Network error** → retry до `max_attempts` раз с backoff.
- **`is_available() == False`** → пропустить тик, попробовать на следующем.

Адаптер также логирует количество вызовов и токенов для контроля бюджета (через `LLMResponse.tokens_used`).

## Конфигурация

Конфиг LLM — вложенная структура. Настройки каждого адаптера хранятся в секции `settings` по имени адаптера:

```yaml
llm:
  adapter: "ollama"               # "mock" | "ollama" | "openai" | "grok" | "anthropic"
  settings:
    mock:
      response_template: "[MOCK] Мысль зафиксирована. Триггер: {trigger_type}"
      latency_ms: 100
    ollama:
      base_url: "http://localhost:11434"
      model: "llama3:8b"
      timeout_seconds: 60
    # openai:
    #   api_key: "${ISKRA_OPENAI_KEY}"
    #   model: "gpt-4o-mini"
    #   base_url: "https://api.openai.com/v1"
    #   timeout_seconds: 30
  temperature: 0.9                 # высокая — для спонтанности
  max_tokens: 500
  retry:
    max_attempts: 3
    backoff_base_seconds: 1.0
  cooldown_on_rate_limit_seconds: 300
```

Значения `${VAR_NAME}` подставляются из переменных окружения при загрузке конфигурации. Полная схема — в [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md).
