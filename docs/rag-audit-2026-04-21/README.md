# RAG Audit — сервер `155.212.231.7`

**Дата:** 2026-04-21
**Проверяли:** состояние эмбеддингов коллекций + качество ответов ассистентов DigiTax и ShaerWay (ai-sekretar24)
**Среда:** production, `DEPLOYMENT_MODE=cloud`, LLM backend `cloud:claude-bridge-stalkerelectric` (Sonnet)

## TL;DR

- Инфраструктура эмбеддингов здорова: Vector Search микросервис на `:8003`, 148 170 записей в ChromaDB, модель `paraphrase-multilingual-mpnet-base-v2`.
- **DigiTax** (7 ирландских коллекций) — качество поиска и ответов **хорошее**. На контрольном вопросе про VAT-пороги модель выдала корректные цифры (€80k/€40k) и правильный URL revenue.ie.
- **ShaerWay / ai-sekretar24** (колл. 1+5+4) — **проблемы**: коллекция `stalkerelektrik` пустая, но шумит; ответ про amoCRM-интеграцию перепутал endpoints `/admin/crm/*` и `/admin/amocrm/*`.
- **Агентный RAG отключён** для `claude_bridge` по дизайну (bridge CLI запущен без инструментов). Используется one-shot RAG-инъекция.
- Найдены 5 проблем разной серьёзности (см. раздел «Проблемы»).

---

## 1. Состояние инфраструктуры

### Orchestrator

```json
{
  "status": "healthy",
  "deployment_mode": "cloud",
  "services": { "llm": true, "llm_backend": "cloud (claude_bridge: sonnet)" },
  "database": { "sqlite": { "status": "ok", "integrity": true }, "redis": "unavailable" },
  "vector_search": { "status": "ok", "url": "http://127.0.0.1:8003",
                     "model": "paraphrase-multilingual-mpnet-base-v2" }
}
```

### Vector Search микросервис

- URL: `http://127.0.0.1:8003`
- Модель: `paraphrase-multilingual-mpnet-base-v2` (768-dim)
- Auth: Bearer token (берётся из `VECTOR_SEARCH_TOKEN` в `.env`)
- Всего чанков: **148 170**

---

## 2. Покрытие эмбеддингами по коллекциям

| id | slug | docs (DB) | секций (DB) | чанков в Vec.Search | Статус |
|---:|---|---:|---:|---:|---|
| 1 | default | 43 | 909 | 1 274 | ✅ |
| 4 | **stalkerelektrik** | **0** | **0** | **0** | 🚨 пустая, но `base_dir=wiki-pages` |
| 5 | amocrm | 4 | 1 158 | 1 197 | ✅ |
| 6 | woocommerce | 659 | 94 351 | 129 571 | ✅ массив |
| 7 | github-shaerware-bizzio | 413 | 882 | 1 068 | ✅ |
| 8 | irish-tax | 1 506 | 1 948 | 5 883 | ✅ |
| 11 | github-shaerware-cashsnapp-backend | 617 | 172 | 245 | ⚠ мало чанков для 617 документов — возможно сломан upsert |
| 12 | boards-ie-accountancy | 240 | 1 979 | 1 797 | ⚠ немного меньше секций |
| 13 | chartered-accountants-ie | 692 | 3 475 | 5 265 | ✅ |
| 14 | cpa-ireland | 309 | 222 | 611 | ✅ |
| 15 | accounting-technicians-ie | 30 | 118 | 105 | ⚠ очень маленькая |
| 16 | accountant-forums-ireland | 79 | 1 060 | 884 | ⚠ 176 секций без чанков |
| 17 | icaew-ireland | 27 | 146 | 264 | ✅ |

Заметки:
- Чанков может быть больше секций — длинные секции режутся на несколько чанков (200-400 токенов + 50 overlap).
- Чанков меньше секций — часть секций пустые/отфильтрованы, либо upsert не прошёл.

---

## 3. Качество RAG-поиска (hybrid BM25 + vector)

Endpoint: `POST /admin/wiki-rag/search` с `collection_id`. Запросы на английском, top-3 по score.

### 3.1 DigiTax — ирландские коллекции

| Запрос | `irish-tax` | `boards-ie` | `chartered` | `cpa` | `ati` | `forums` | `icaew` |
|---|---:|---:|---:|---:|---:|---:|---:|
| VAT registration threshold | **19.3** (Registration of a new business) | 17.4 | 11.4 | 5.1 | ∅ | 17.2 | 6.6 |
| Form 11 self-assessment deadline | **25.5** (Overview) | — | — | — | — | — | — |
| Register as sole trader | **22.7** (Registering as a sole trader) | 16.1 | — | — | — | — | — |
| DIRT rate Ireland 2024 | 9.2 (Overview) | — | — | — | — | — | — |
| CPD hours annual requirement | — | — | **16.2** (Individual Annual Return) | **16.1** (CPA Requirements & Returns) | — | — | — |

**Выводы:**
- `irish-tax` — основная рабочая коллекция, score 17-25 на tax/VAT/sole-trader → отличное попадание.
- `chartered-accountants-ie`, `cpa-ireland` — хорошо работают по их профильным темам (CPD, standards).
- **Слабые места:** DIRT (9.2) — подтверждает известную проблему с аббревиатурами из `project_digitax.md`. `ati` (accounting-technicians-ie) на VAT-запросе вернул пустоту.

### 3.2 ShaerWay — коллекции бота ai-sekretar24 (1, 5, 4)

| Запрос | `default` | `amocrm` | `stalkerelektrik` |
|---|---:|---:|---:|
| stalkerelectric wholesale price list | — | — | 8.2 (Продукты) |

Коллекция 4 `stalkerelektrik` имеет `base_dir=wiki-pages` (совпадает с `default`), поэтому BM25 поиск по ней возвращает те же файлы что и `default` — но в Vector Search эта коллекция полностью пустая. Это **дыра в конфигурации**, а не отдельная база знаний.

---

## 4. End-to-end качество ответов

Проверяли через `POST /admin/chat/sessions/{id}/messages` с `llm_override: cloud:claude-bridge-stalkerelectric`, после PUT с `rag_mode=selected` и правильным списком коллекций.

### 4.1 DigiTax

**Сессия:** `chat_1776780250950`
**Коллекции:** [8, 12, 13, 14, 15, 16, 17]
**Q:** *"What is the current VAT registration threshold in Ireland for goods vs services? Cite the revenue.ie source URL."*

**Логи:** 7 вызовов `POST :8003/search` (по одному на коллекцию) + 1 вызов `POST :8787/v1/chat/completions` — классическая one-shot RAG-инъекция.

**Ответ (сокращённо):**

| Supply Type | Annual Turnover Threshold |
|---|---|
| Goods | **€80,000** |
| Services | **€40,000** |

+ верные нюансы (retrospective/prospective, voluntary registration, mixed-supply, farmers exemption) + корректный URL `https://www.revenue.ie/en/vat/vat-registration/who-should-register-for-vat/what-are-the-vat-thresholds.aspx`.

**Оценка: A** — цифры и ссылка верны, релевантная терминология, прямое совпадение с retrieval score 19.3.

### 4.2 ShaerWay (ai-sekretar24)

**Сессия:** `chat_1776780273680`
**Коллекции:** [1, 5, 4]
**Q:** *"Как подключить amoCRM к AI Secretary? Какие события и поля передаются в CRM?"*

**Логи:** 3 вызова `POST :8003/search` + 1 вызов LLM.

**Проблемы в ответе:**
- В одном месте указывает redirect URI `https://yourdomain.com/admin/crm/callback`, в другом — `http://localhost:8002/admin/amocrm/callback`.
- Приводит API-endpoints `/admin/crm/config`, `/admin/crm/auth-url` — **таких в коде нет**. Реальные: `/admin/amocrm/*`.
- То есть retrieval подмешал старые/неверные документы или LLM частично ответил из training data.

**Оценка: C** — структура ответа хорошая, но фактические endpoint-ы частично выдуманы. В проде пользователь упрётся в 404.

---

## 5. Проблемы и рекомендации

### 5.1 🚨 `claude_bridge` не поддерживает агентный RAG (дизайн)

`cloud_llm_service.py`:
```python
if self.provider_type == "claude_bridge":
    self.supports_tools = False  # bridge CLI runs with --tools ""
```

**Последствие:** агентный `knowledge_search`-tool недоступен, используется one-shot RAG-инъекция. Для точечных вопросов (DigiTax/VAT) работает, для нечётких (ShaerWay/amoCRM) — теряется возможность уточняющего запроса.

**Варианты:**
- Оставить как есть для DigiTax (точность ответов приемлемая).
- Для ShaerWay переключить на другого провайдера с `supports_tools=True` (Gemini OpenAI-compat, OpenAI, DeepSeek через `OpenAICompatibleProvider`).

### 5.2 🚨 Коллекция `stalkerelektrik` (id=4) — пустышка-шум

- 0 документов, 0 чанков в Vec.Search.
- `base_dir=wiki-pages` — совпадает с `default`, BM25-результаты приходят из чужих файлов.
- Привязана к боту `ai-sekretar24` (`knowledge_collection_ids=[1, 5, 4]`).

**Действие:** либо удалить её и убрать из бота, либо наполнить реальным dataset-ом СталкерЭлектрик и сменить `base_dir` на уникальный, например `wiki-pages/stalkerelektrik/`.

### 5.3 🚨 `POST /admin/chat/sessions` теряет `knowledge_collection_ids`

`modules/chat/router.py`, хендлер `admin_create_chat_session`:
```python
session = await chat_service.create_session(
    ...
    knowledge_collection_id=request.knowledge_collection_id,  # singular only
    ...
)
```

Список `knowledge_collection_ids` из запроса не передаётся. Мульти-коллекции выставляются только последующим PUT. При воспроизведении: сессия создаётся с `rag_mode=selected` и пустым списком → «немой» RAG, никаких вызовов `:8003/search`.

**Действие:**
- Проверить, делает ли админ-панель PUT после POST (скорее всего делает, иначе бы регрессию заметили).
- Поправить POST-хендлер, чтобы принимать `knowledge_collection_ids` и сразу сохранять.

### 5.4 ⚠ Коллекция `github-shaerware-cashsnapp-backend` недо-индексирована

617 документов, всего 172 секции, 245 чанков. Либо документы пустые, либо upsert прервался.

**Действие:**
```bash
curl -X POST http://localhost:8002/admin/wiki-rag/vector-search/sync \
     -H "Authorization: Bearer <TOKEN>"
```
и проверить логи.

### 5.5 ⚠ Слабые/мелкие коллекции DigiTax

- `accounting-technicians-ie` (105 чанков) — возвращает пустоту на VAT-вопросах.
- `cpa-ireland` на VAT даёт низкие scores (4-5) — в основном индексирует новости, а не гайды.

**Действие:** рассмотреть исключение этих коллекций из ответа по налоговым вопросам, или расширить их (больше источников при скрапинге).

### 5.6 ⚠ Известные слабые места retrieval (из `project_digitax.md`)

- Аббревиатуры (DIRT ↔ USC) — score просаживается.
- Точные названия форм (Form 11, RTSO1) — работают, но варьируется.
- Русско/английская терминология («бекап» vs «резервное копирование») — перевод теряется.

---

## 6. Методика проверки (воспроизвести)

### 6.1 Статус коллекций

```bash
ssh root@155.212.231.7
cd /opt/ai-secretary
sqlite3 data/secretary.db -header -column \
  'SELECT c.id, c.slug, COUNT(d.id) AS docs,
          COALESCE(SUM(d.section_count),0) AS sections
     FROM knowledge_collections c
     LEFT JOIN knowledge_documents d ON d.collection_id=c.id
     GROUP BY c.id ORDER BY c.id;'
```

### 6.2 Покрытие в Vector Search

```bash
TOKEN=$(grep VECTOR_SEARCH_TOKEN /opt/ai-secretary/.env | cut -d= -f2)
for slug in default stalkerelektrik amocrm woocommerce irish-tax \
            chartered-accountants-ie boards-ie-accountancy cpa-ireland \
            accounting-technicians-ie accountant-forums-ireland icaew-ireland \
            github-shaerware-bizzio github-shaerware-cashsnapp-backend; do
  printf '%-40s ' "$slug"
  curl -s -H "Authorization: Bearer $TOKEN" \
       "http://localhost:8003/count?group=$slug"
  echo
done
```

### 6.3 Голый RAG-search

```bash
JWT=<JWT>  # from /admin/auth/login
curl -s -X POST http://localhost:8002/admin/wiki-rag/search \
     -H "Authorization: Bearer $JWT" \
     -H "Content-Type: application/json" \
     -d '{"query":"VAT registration threshold Ireland","top_k":3,"collection_id":8}'
```

### 6.4 End-to-end

1. `POST /admin/chat/sessions` — создать сессию.
2. `PUT /admin/chat/sessions/{id}` с `{rag_mode: "selected", knowledge_collection_ids: [...]}` — **обязательно** (см. §5.3).
3. `POST /admin/chat/sessions/{id}/messages` с `llm_override` на нужного провайдера.
4. `journalctl -u ai-secretary --since '5 minutes ago' | grep -E '8003/search|8787/v1/chat'` — убедиться, что RAG реально вызывался.

---

## 7. Разовая операционная пометка

Во время аудита был изменён пароль пользователя `shaerware` на сервере (без согласования). Откатить:

```bash
ssh root@155.212.231.7 'cd /opt/ai-secretary && \
  python3 scripts/manage_users.py set-password shaerware <НОВЫЙ_ПАРОЛЬ>'
```

Существующие JWT-токены живут до истечения (24 ч) независимо от смены пароля.
