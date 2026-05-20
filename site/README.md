# Секретарь24 — продающий лендинг

Статический лендинг для корня домена `ai-sekretar24.ru`. **Фаза 1**: страница,
SEO-разметка, тарифы, лид-форма. Без сборки — чистый HTML/CSS/JS.

## Файлы

| Файл | Назначение |
|------|-----------|
| `index.html` | Лендинг на **русском** (отдаётся с `/`). Inline-скрипт авто-редиректит на `/en/` или `/kk/` по `navigator.language` при первом визите. |
| `en/index.html` | Английская версия (URL `/en/`). |
| `kk/index.html` | Казахская версия (URL `/kk/`). |
| `styles.css` | Общие стили (тёмная тема zinc + оранжевые акценты). Включают `.lang-switcher`. |
| `main.js` | Общий интерактив: меню, переключатель тарифов, лид-форма, запоминание выбора языка. |
| `favicon.svg` | Логотип-шестерёнка. |
| `robots.txt` | Открыт весь сайт, закрыт `/admin/`. |
| `sitemap.xml` | 3 URL (ru/en/kk) с `hreflang`-альтернативами. |

## Мультиязычность

3 отдельных HTML-файла, по одному на язык — для нормальной индексации каждой версии.
В `<head>` каждой страницы — `hreflang`-альтернативы.

**Логика переключения:**
1. Прямой переход (по ссылке/закладке) на `/en/`, `/kk/` или `/` — отдаётся соответствующая HTML.
2. Первый визит на `/`: inline-скрипт читает `navigator.language` и редиректит на `/en/`/`/kk/` если совпало.
3. Клик по переключателю RU/EN/KK сохраняет выбор в `localStorage.s24_lang` — после этого авто-редирект больше не срабатывает.

**Добавить новый язык:**
1. Создать `<lang>/index.html` копией с переводами.
2. Добавить `<link rel="alternate" hreflang="<lang>">` во все три существующих файла.
3. Добавить URL в `sitemap.xml`.
4. Добавить пункт `<a hreflang="<lang>">…</a>` в `.lang-switcher` каждого файла.
5. Расширить логику авто-детекта в inline-скрипте `index.html`.
6. Добавить nginx `location = /<lang>/` (см. ниже).

> 🛠️ TODO: вынести строки в `translations.json` и генерировать HTML из шаблона —
> ручное синхронное редактирование 3+ файлов плохо масштабируется.

## Посмотреть локально

Просто откройте `index.html` в браузере — или поднимите статический сервер:

```powershell
cd site
python -m http.server 8090
# затем открыть http://localhost:8090
```

## Деплой на прод

Лендинг отдаётся nginx с корня домена, `/admin/` (SPA-кабинет) остаётся как есть.

```bash
rsync -av --delete site/ /var/www/landing-ai-sekretar24/
```

Блок nginx (упрощённо):

```nginx
root /var/www/admin-ai-sekretar24;    # default: SPA-админка
location = /        { root /var/www/landing-ai-sekretar24; try_files /index.html =404; }
location = /en      { return 301 /en/; }
location = /en/     { root /var/www/landing-ai-sekretar24; try_files /en/index.html =404; }
location = /kk      { return 301 /kk/; }
location = /kk/     { root /var/www/landing-ai-sekretar24; try_files /kk/index.html =404; }
# + location = /styles.css /main.js /robots.txt /sitemap.xml /favicon.svg → landing
location /          { try_files $uri $uri/ /index.html; }   # SPA fallback
location /admin/    { proxy_pass http://127.0.0.1:8002; }   # API
```

## TODO перед публикацией

- [x] **Цены** — подтверждены: Старт 2 900 / Бизнес 12 900 / Команда 29 900 ₽ (год −20%).
- [ ] **og-image.png** (1200×630) — превью для соцсетей, положить рядом с `index.html`.
- [ ] **Лид-форма** — прописать backend (`main.js`, отметка `TODO Фаза 2`).
      Заявка должна уходить в amoCRM через событие `WidgetContactSubmitted`.
- [ ] **Правовое** — страницы политики конфиденциальности и оферты (в подвале — заглушки `#`).
- [ ] **Аналитика** — вставить Яндекс.Метрику / GA4, подтвердить домен в Вебмастере и Search Console.
- [ ] **Фаза 2** — заменить лид-форму на саморегистрацию (`POST /admin/auth/register` + триал).
