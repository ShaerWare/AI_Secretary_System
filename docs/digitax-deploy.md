# DigiTax Collections — Deploy Guide

RAG-коллекции DigiTax (ирландская бухгалтерия, 7 коллекций, 3670 MD-файлов, 7531 BM25-секция) живут в отдельном репозитории [`CalalbKorina/AI-Agents`](https://github.com/CalalbKorina/AI-Agents). Основной проект подключает их как submodule и синхронизирует в `wiki-pages/` перед индексацией.

## Архитектура

```
CalalbKorina/AI-Agents
└── digitax/
    ├── collections/          ← источник правды
    │   ├── irish-tax/        (2417 docs, revenue.ie)
    │   ├── boards-ie-accountancy/  (240)
    │   ├── chartered-accountants-ie/ (692)
    │   ├── cpa-ireland/      (238)
    │   ├── accounting-technicians-ie/ (55)
    │   ├── accountant-forums-ireland/ (25)
    │   └── icaew-ireland/    (3)
    ├── scripts/scrape_digitax/  ← pipeline (scrape/parse/upload)
    └── docs/digitax-workflow.md

ShaerWare/AI_Secretary_System (этот репо)
├── external/ai-agents/       ← submodule на CalalbKorina/AI-Agents
├── wiki-pages/               ← runtime-папка (gitignored для digitax slug'ов)
│   ├── irish-tax/            ← создаётся sync-скриптом
│   └── ...                   ← то же для остальных 6
├── scripts/
│   ├── sync-digitax-collections.sh  ← rsync submodule → wiki-pages
│   └── scrape_digitax/upload.py     ← создаёт записи в knowledge_docs
```

## Первый деплой на сервере

```bash
ssh root@155.212.231.7
cd /opt/ai-secretary

# 1. Подтянуть новые коммиты + submodule
git pull origin main
git submodule update --init --recursive

# 2. Синхронизировать коллекции в wiki-pages/
bash scripts/sync-digitax-collections.sh

# 3. Создать записи в БД (knowledge_collections + knowledge_docs)
venv/bin/python scripts/scrape_digitax/upload.py --all

# 4. Переиндексировать BM25 + embeddings
systemctl restart ai-secretary
sleep 5
curl -X POST http://localhost:8002/admin/wiki-rag/reload
```

После первого upload'а таблицы `knowledge_collections` уже созданы. При
последующих синхронизациях `upload.py` пропускает файлы, для которых уже
есть запись в `knowledge_docs`.

## Регулярное обновление

Когда в `CalalbKorina/AI-Agents` появляются новые данные (после re-scrape):

```bash
ssh root@155.212.231.7
cd /opt/ai-secretary

# Обновить submodule до последнего коммита main
git submodule update --remote external/ai-agents
git add external/ai-agents
git commit -m "chore: bump digitax collections submodule"

# Синхронизировать и переиндексировать
bash scripts/sync-digitax-collections.sh
venv/bin/python scripts/scrape_digitax/upload.py --all    # добавит новые doc'и
curl -X POST http://localhost:8002/admin/wiki-rag/reload
```

## Проверка целостности

```bash
# Показать совпадение src ↔ dst по числу файлов
bash scripts/sync-digitax-collections.sh --check
```

Ожидается:

```
= irish-tax: src=2417 dst=2417
= boards-ie-accountancy: src=240 dst=240
= chartered-accountants-ie: src=692 dst=692
= cpa-ireland: src=238 dst=238
= accounting-technicians-ie: src=55 dst=55
= accountant-forums-ireland: src=25 dst=25
= icaew-ireland: src=3 dst=3
```

## Локальный клон (dev-машина)

```bash
git clone --recursive https://github.com/ShaerWare/AI_Secretary_System.git
cd AI_Secretary_System
bash scripts/sync-digitax-collections.sh
```

Уже клонировавшим без `--recursive`:

```bash
git submodule update --init --recursive
bash scripts/sync-digitax-collections.sh
```

## Почему submodule, а не subtree / отдельный clone

- **submodule**: стандарт git, pin на конкретный коммит источника, простой `git submodule update --remote` для обновления. Минус — двойной clone. Выбран именно этот вариант.
- **subtree**: история AI-Agents смешивается с основным репо, pull/push усложняется.
- **Параллельный clone**: не привязан к конкретной ревизии данных — легко разъехаться с прод.

## Доступ к private-репо

`CalalbKorina/AI-Agents` — приватный. На сервере нужен либо deploy key, либо уже
настроенный `gh`/HTTPS-токен. Проверить: `ssh -T git@github.com` или
`gh auth status`.
