# Tax Data Scraping — Server Instructions

> Эту инструкцию читает Claude Code на сервере для продолжения работы.
> Контекст: на локалке подготовлены скрипты, на сервере нужно запустить скрейпинг и парсинг.

## Что уже сделано (локалка)

1. `01_scrape_revenue.py` — скрейпер revenue.ie (requests, не httpx). Качает:
   - sitemap.xml (14,662 URL) → фильтрует 1,211 HTML + PDF
   - HTML страницы (self-assessment, tax credits, VAT, TDM manuals, ROS help)
   - PDF документы (Form 11, helpsheets, guides, Ready Reckoner)
   - Второй проход: находит PDF-ссылки внутри HTML и докачивает их
2. `02_parse_to_markdown.py` — парсер HTML (lxml) и PDF (pdfplumber) → markdown файлы с метаданными
3. `requirements.txt` — минимальные зависимости (requests, lxml, pdfplumber)
4. `setup_and_run.sh` — автоматическая настройка venv + запуск

## Что нужно сделать на сервере

### Шаг 1: Запустить скрейпинг
```bash
cd /opt/ai-secretary
bash tax_data/setup_and_run.sh
```
Или по частям:
```bash
cd /opt/ai-secretary/tax_data
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 01_scrape_revenue.py        # ~7 мин (1,211 HTML + PDF-ки)
python3 02_parse_to_markdown.py     # парсинг в markdown
```

### Шаг 2: Проверить результат
Ожидаемый объём:
- `raw_html/` — ~1,200 файлов
- `raw_pdf/` — 16+ файлов (базовые) + десятки TDM PDF (найденные из HTML)
- `parsed/` — markdown файлы + `manifest.json`

### Шаг 3: Запустить генерацию Q&A датасета

Скрипт `03_generate_qa.py` уже написан. Работает через Claude Code bridge (OpenAI-compatible API на `localhost:8787`).

```bash
# Убедиться что bridge запущен (orchestrator или bridge_manager)
curl http://127.0.0.1:8787/health

# Тестовый запуск (5 чанков)
python3 03_generate_qa.py --max-chunks 5

# Полный запуск
python3 03_generate_qa.py

# Продолжить после прерывания
python3 03_generate_qa.py --resume

# Статистика
python3 03_generate_qa.py --stats
```

Формат выходного файла `datasets/tax_qa.jsonl`:
```json
{"instruction": "вопрос про налоги", "input": "контекст если нужен", "output": "ответ со ссылкой на источник"}
```

Особенности:
- Использует bridge на `localhost:8787` (не внешние API)
- Checkpoint/resume — можно прервать и продолжить
- Приоритизация: self-assessment → income tax → VAT → TDM
- 3-5 Q&A пар на чанк, 4 типа вопросов:
   - Фактические: "Какой порог регистрации VAT для услуг в Ирландии?"
   - Процедурные: "Как заполнить Panel B в Form 11?"
   - Расчётные: "Рассчитай налог для self-employed с доходом €85,000"
   - Сценарные: "Я фрилансер-программист, работаю из дома. Какие расходы могу списать?"

### Шаг 4 (опционально): Скрейпинг дополнительных источников

- Citizens Information (`citizensinformation.ie/en/money-and-tax/tax/`)
- Reddit r/irishpersonalfinance (через API или web scraping)
- Бухгалтерские блоги (Fenero, TaxAssist)

## Конечная цель

AI-ассистент который может заменить бухгалтера для ирландских self-employed:
- Знает все правила (RAG по knowledge base)
- Умеет рассуждать как бухгалтер (fine-tuned модель)
- Считает налог пошагово (Income Tax + USC + PRSI + Preliminary Tax)
- Помогает заполнить Form 11 поле за полем
- Классифицирует расходы по категориям Revenue

## Архитектура

```
RAG (актуальные данные, ставки)  +  Fine-tuned LLM (рассуждения бухгалтера)
         ↓                                    ↓
   Revenue docs / TDM              Q&A датасет из этих же docs
   обновляемо ежемесячно           LoRA adapter на Qwen/Llama
```

## Важно

- revenue.ie: нет robots.txt, лицензия CC-BY-4.0 — всё легально
- Скрипты идемпотентны: повторный запуск пропускает уже скачанные файлы
- `REQUEST_DELAY = 0.3` — вежливая задержка между запросами
- Данные в git НЕ коммитятся (в .gitignore), только скрипты
