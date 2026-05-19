# Секретарь24 — продающий лендинг

Статический лендинг для корня домена `ai-sekretar24.ru`. **Фаза 1**: страница,
SEO-разметка, тарифы, лид-форма. Без сборки — чистый HTML/CSS/JS.

## Файлы

| Файл | Назначение |
|------|-----------|
| `index.html` | Вся страница + SEO-разметка (Open Graph, JSON-LD: Organization, SoftwareApplication, FAQPage) |
| `styles.css` | Стили (тёмная тема zinc + оранжевые акценты — наследует кабинет) |
| `main.js` | Интерактив: меню, переключатель тарифов, лид-форма |
| `favicon.svg` | Логотип-шестерёнка |
| `robots.txt` | Открыт `/`, закрыт `/admin/` |
| `sitemap.xml` | Карта сайта |

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

Блок nginx (location `/` — лендинг, location `/admin/` — кабинет):

```nginx
root /var/www/landing-ai-sekretar24;
location = / { try_files /index.html =404; }
location /admin/ { root /var/www; try_files $uri $uri/ /admin/index.html; }
```

## TODO перед публикацией

- [x] **Цены** — подтверждены: Старт 2 900 / Бизнес 12 900 / Команда 29 900 ₽ (год −20%).
- [ ] **og-image.png** (1200×630) — превью для соцсетей, положить рядом с `index.html`.
- [ ] **Лид-форма** — прописать backend (`main.js`, отметка `TODO Фаза 2`).
      Заявка должна уходить в amoCRM через событие `WidgetContactSubmitted`.
- [ ] **Правовое** — страницы политики конфиденциальности и оферты (в подвале — заглушки `#`).
- [ ] **Аналитика** — вставить Яндекс.Метрику / GA4, подтвердить домен в Вебмастере и Search Console.
- [ ] **Фаза 2** — заменить лид-форму на саморегистрацию (`POST /admin/auth/register` + триал).
