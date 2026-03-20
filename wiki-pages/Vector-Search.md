# Vector Search (Векторный поиск)

Микросервис семантического поиска по текстовым документам. Работает полностью локально — без внешних API.

## Скриншот

<!-- Вставьте скриншот Swagger UI -->
![Vector Search](images/vector-search.png)

## Концепция

**Vector Search** — отдельный HTTP-микросервис, который:

- **Принимает текст** → разбивает на чанки → превращает в числовые векторы (embeddings)
- **Хранит векторы** в ChromaDB (persistent, на диске)
- **Ищет по смыслу** — cosine similarity между запросом и сохранёнными документами
- **Мультиязычный** — русский, английский, казахский и 50+ языков (модель `paraphrase-multilingual-mpnet-base-v2`)
- **Самодостаточный** — все вычисления локальные, без внешних сервисов

### Зачем нужен

| Задача | Как решает |
|--------|-----------|
| **RAG** | Индексация документации/FAQ, поиск релевантного контекста для LLM |
| **Каталог товаров** | Поиск по описаниям товаров «по смыслу» (а не по ключевым словам) |
| **Дедупликация** | Обнаружение перефразов и дубликатов (similarity > 0.85) |
| **Классификация** | Сравнение нового текста с эталонными категориями |

## Как это работает

### Процесс загрузки (Upsert)

```
Текст документа
     │
     ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Chunker  │────►│ Embedder │────►│ ChromaDB │
│ (разбивка│     │ (векторы │     │ (хранение│
│ на части)│     │  768-dim) │     │ на диске)│
└──────────┘     └──────────┘     └──────────┘
```

1. Текст нормализуется и разбивается на чанки (~2000 символов)
2. Каждый чанк превращается в вектор из 768 чисел
3. Вектор + метаданные сохраняются в ChromaDB
4. При повторном upsert с тем же `doc_id` — старые чанки заменяются

### Процесс поиска (Search)

```
"поисковый запрос"
     │
     ▼
┌──────────┐     ┌──────────┐     Результаты
│ Embedder │────►│ ChromaDB │────► (top-N по
│ (вектор  │     │ (cosine  │     similarity)
│ запроса) │     │ поиск)   │
└──────────┘     └──────────┘
```

1. Запрос превращается в вектор
2. ChromaDB находит ближайшие векторы (cosine similarity)
3. Фильтрация по `min_similarity`, `doc_id`, `group`
4. Пагинация и возврат результатов

### Chunking (разбивка текста)

| Шаг | Описание |
|-----|----------|
| **Нормализация** | Убирает лишние пробелы и переносы |
| **Структурная разбивка** | По заголовкам (`#`), абзацам (`\n\n`), предложениям (`.!?`) |
| **Сборка чанков** | Накапливает блоки до `chunk_size` символов (по умолчанию 2000) |
| **Overlap 15%** | Конец предыдущего чанка дублируется в начале следующего |
| **Word-safe** | Никогда не рвёт слово пополам |

## API

**Base URL:** `https://ai-sekretar24.ru/vector-search`
**Swagger UI:** [/vector-search/docs](https://ai-sekretar24.ru/vector-search/docs)
**Auth:** заголовок `Authorization: Bearer <AUTH_KEY>` (кроме `/health`)

### Загрузка данных

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/upsert` | Загрузить текст (авто-chunking + embedding) |

**Тело запроса:**
```json
{
  "text": "Текст документа...",
  "doc_id": "catalog-v2",
  "group": "products",
  "chunk_size": 2000
}
```

- `doc_id` (опционально) — при повторном upsert с тем же ID старые чанки заменяются
- `group` (опционально) — группировка для фильтрации при поиске
- `chunk_size` (опционально) — размер чанка в символах (по умолчанию 2000)

**Ответ:** `{"ids": ["uuid1", "uuid2", ...]}`

### Поиск

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/search` | Семантический поиск по смыслу |
| `POST` | `/compare` | Сравнить текст с конкретной записью |

**Тело `/search`:**
```json
{
  "text": "поисковый запрос",
  "doc_id": "optional",
  "group": "optional",
  "min_similarity": 0.5,
  "limit": 10,
  "page": 1
}
```

**Ответ:**
```json
{
  "items": [
    {
      "id": "uuid",
      "text": "найденный чанк...",
      "doc_id": "catalog-v2",
      "group": "products",
      "chunk_index": 0,
      "similarity": 0.87
    }
  ],
  "total": 5,
  "page": 1,
  "limit": 10
}
```

**Тело `/compare`:**
```json
{
  "text": "текст для сравнения",
  "record_id": "uuid конкретной записи"
}
```

**Ответ:** `{"similarity": 0.87}`

### Получение данных

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/count` | Количество записей (query params: `text?`, `doc_id?`, `group?`, `min_similarity?`) |
| `GET` | `/ids` | Список ID записей (query params: `doc_id?`, `group?`) |
| `GET` | `/records` | Пагинированный список (query params: `doc_id?`, `group?`, `limit?`, `page?`) |

### Удаление

| Метод | Путь | Описание |
|-------|------|----------|
| `DELETE` | `/record/{id}` | Удалить одну запись |
| `DELETE` | `/document/{doc_id}` | Удалить все чанки документа |
| `DELETE` | `/group/{group}` | Удалить все записи группы |
| `DELETE` | `/clear` | Очистить всё |

### Здоровье

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `GET` | `/health` | Нет | `{"status": "ok", "model": "paraphrase-multilingual-mpnet-base-v2"}` |

## Деплой

**Сервер:** `155.212.231.7` (тот же VPS что AI Secretary)
**Порт:** 8003 (проксируется nginx как `/vector-search/`)
**Systemd:** `vector-search.service`
**Данные:** `/opt/vector-search/data/chroma/`
**Модель:** `/opt/vector-search/.cache/huggingface/` (~420MB)

### Управление сервисом

```bash
systemctl status vector-search     # Статус
systemctl restart vector-search    # Перезапуск
journalctl -u vector-search -f     # Логи
```

### Структура на сервере

```
/opt/vector-search/
├── app/                    # Исходный код
│   ├── main.py             # FastAPI + роуты
│   ├── auth.py             # Bearer token
│   ├── chunker.py          # Разбивка текста
│   ├── embedder.py         # sentence-transformers
│   ├── storage.py          # ChromaDB обёртка
│   └── config.py           # Настройки (.env)
├── tests/                  # Тесты (pytest)
├── data/chroma/            # Данные ChromaDB
├── .cache/huggingface/     # Кеш модели
├── venv/                   # Python виртуальное окружение
└── .env                    # Конфигурация (AUTH_KEY)
```

## Стек

| Компонент | Технология |
|-----------|-----------|
| **Язык** | Python 3.12 |
| **Фреймворк** | FastAPI + Uvicorn |
| **Embeddings** | sentence-transformers (paraphrase-multilingual-mpnet-base-v2, 768d) |
| **Векторная БД** | ChromaDB 0.6.x (persistent, cosine similarity) |
| **Конфигурация** | pydantic-settings + .env |
| **Потребление RAM** | ~1.1GB (модель + ChromaDB) |

## Примеры использования

### Из curl

```bash
AUTH="Authorization: Bearer YOUR_KEY"
URL="https://ai-sekretar24.ru/vector-search"

# Загрузить документ
curl -X POST $URL/upsert \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"text": "Текст документа...", "doc_id": "doc-1", "group": "knowledge"}'

# Поиск по смыслу
curl -X POST $URL/search \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"text": "запрос", "min_similarity": 0.4}'

# Количество записей
curl "$URL/count" -H "$AUTH"

# Удалить документ
curl -X DELETE "$URL/document/doc-1" -H "$AUTH"
```

### Интеграция с AI Secretary (RAG)

```python
import httpx

VECTOR_URL = "http://localhost:8003"
AUTH = {"Authorization": "Bearer YOUR_KEY"}

# 1. Индексация wiki-страниц
for page in wiki_pages:
    httpx.post(f"{VECTOR_URL}/upsert", headers=AUTH, json={
        "text": page.content,
        "doc_id": page.filename,
        "group": "wiki",
    })

# 2. Поиск контекста для вопроса пользователя
results = httpx.post(f"{VECTOR_URL}/search", headers=AUTH, json={
    "text": user_question,
    "group": "wiki",
    "min_similarity": 0.4,
    "limit": 5,
}).json()

# 3. Подставить в промпт LLM
context = "\n\n".join(r["text"] for r in results["items"])
prompt = f"Контекст:\n{context}\n\nВопрос: {user_question}"
```

---

**См. также:** [[Wiki-RAG]], [[Cloud-LLM-Providers]], [[Architecture]]
