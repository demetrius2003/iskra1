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

### GigaChatAdapter
Облако Сбера: получение **access token** (OAuth) и запрос `POST .../chat/completions` в формате, близком к OpenAI. Зависимость: `httpx`.

**Учётные данные** (любой один вариант):

- `client_id` + `client_secret` — Iskra сам формирует Basic-ключ;
- или `credentials_base64` — готовый **авторизационный ключ** из личного кабинета GigaChat API (Base64 от `client_id:client_secret`).

**Переменные окружения** (пример): `GIGACHAT_CLIENT_ID`, `GIGACHAT_CLIENT_SECRET` и в YAML `${GIGACHAT_CLIENT_ID}`.

**Параметры** (`llm.settings.gigachat`):

| Поле | Назначение |
|------|------------|
| `scope` | По умолчанию `GIGACHAT_API_PERS`; для ИП/юрлиц см. [документацию Сбера](https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-token) |
| `oauth_url` | По умолчанию `https://ngw.devices.sberbank.ru:9443/api/v2/oauth` |
| `api_base` | По умолчанию `https://gigachat.devices.sberbank.ru/api/v1` (альтернатива — `https://api.giga.chat/v1` для Салют) |
| `model` | Идентификатор модели, напр. `GigaChat` или `GigaChat-Max` |
| `ca_bundle_file` | Путь к **`russian_trusted_root_ca.cer`** (скачивается в кабинете/по инструкции GigaChat). Аналог `ca_bundle_file` в `langchain_community.GigaChat`. Относительный путь — от **текущего рабочего каталога** при запуске (`python -m iskra` из корня → удобно `certs/russian_trusted_root_ca.cer` или `russian_trusted_root_ca.cer` в корне). Допустимо короткое имя поля `ca_bundle` |
| `verify_ssl` | `true` по умолчанию. С `ca_bundle_file` TLS проверяется по этому пакету корней. `false` — отключить проверку (как `verify_ssl_certs=False` в старых примерах; **небезопасно**) |

Токен кэшируется в памяти до истечения срока (`expires_at` в ответе OAuth).

### YandexGPTAdapter
**Yandex Cloud Foundation Models**: `POST https://llm.api.cloud.yandex.net/foundationModels/v1/completion`. В теле сообщения используются поля **`text`** (не `content`). Зависимость: `httpx`.

**Авторизация** (`auth`):

- `iam` — заголовок `Authorization: Bearer <iam_token>`. IAM-токен короткоживущий; обновляйте снаружи (`yc iam create-token`, скрипт, CI).
- `api_key` — `Authorization: Api-Key <секрет>`.

**Обязательно**: идентификатор каталога — `folder_id` (тот же, что в `gpt://<folder_id>/...`), либо полный `model_uri`, из которого каталог извлекается для заголовка `x-folder-id`.

**Параметры** (`llm.settings.yandexgpt`):

| Поле | Назначение |
|------|------------|
| `folder_id` | ID каталога в облаке |
| `model` | Имя модели в URI, по умолчанию `yandexgpt` |
| `model_version` | Версия в URI, по умолчанию `latest` (например `yandexgpt-lite` + `latest`) |
| `model_uri` | Если задан целиком (`gpt://.../yandexgpt/latest`), поля `model` / `model_version` не собираются автоматически из `folder_id` |

В конфиге: `llm.adapter: "gigachat"` или `llm.adapter: "yandexgpt"` (допустимо и `yandex_gpt`).

### Будущее: OpenAIAdapter / GrokAdapter / AnthropicAdapter
Подключение к прочим облачным API по аналогии с существующими адаптерами.

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
  adapter: "ollama"               # mock | ollama | gigachat | yandexgpt | yandex_gpt
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
