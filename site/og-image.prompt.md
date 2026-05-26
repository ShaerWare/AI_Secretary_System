# OG-image (1200×630): промпт для генерации финального PNG

Сейчас в `site/og-image.svg` лежит дизайнерский плейсхолдер (логотип + слоган + чипы). Когда сгенерируешь фотореалистичный вариант — положи его в `site/og-image.png` и в `index.html` (+ en + kk) меняй мету.

В `<head>` сейчас прописано:
```html
<meta property="og:image" content="https://ai-sekretar24.ru/og-image.png" />
```

То есть достаточно создать файл `og-image.png` на проде — менять HTML не надо.

---

## Промпт (RU)

> Профессиональный полароидный портрет привлекательной молодой женщины-секретаря, около 28 лет, длинные тёмные блестящие волосы (брюнетка), уверенная дружелюбная улыбка, тёплые карие глаза. Одета в безупречно отглаженную белую офисную блузку (хлопок) с лёгким воротничком. В одной руке держит современный смартфон с подсветкой экрана (виден интерфейс мессенджера, но без читаемого текста), второй прикасается к гарнитуре с микрофоном.
>
> Студийное освещение: мягкий ключевой свет 45° слева, тёплый fill справа, контровый янтарно-оранжевый свет (#F0A830) сзади создаёт золотой rim вокруг волос и плеч. Атмосфера высокотехнологичного офиса.
>
> Фон: размытый современный офис open-space с холодными неоновыми акцентами, на заднем плане едва заметны мониторы с графиками и дашбордами. Боке. Контровый свет даёт ощущение энергии и AI-технологии.
>
> Композиция: погрудный кадр (бёдра-голова), модель смотрит прямо в камеру с лёгким наклоном головы. **СЛЕВА в кадре оставлено пустое пространство 35% ширины для наложения текста-слогана** — там должна быть только фоновая бо́ке-размытость без активных элементов.
>
> Стиль: гиперреалистичная фотография, Sony A7R V + 85mm f/1.4, ISO 200, глубина резкости f/2.0. Цветовая палитра: тёплые янтарно-золотые тона + холодные офисные акценты, тёмный low-key фон. Без watermark, без логотипов в кадре, без текста, без шумных деталей.

## Промпт (EN — для Midjourney / DALL-E)

> Professional studio portrait of an attractive young female secretary, around 28 years old, long shiny dark brunette hair, confident friendly smile, warm brown eyes. Wearing an immaculately ironed pure white cotton office blouse with subtle collar. Holds a modern smartphone with subtle screen glow in one hand (messenger interface visible but no readable text), other hand lightly touches a wireless headset with microphone.
>
> Studio lighting: soft 45° key light from left, warm fill from right, amber-orange rim light (#F0A830) from behind creating a golden glow around hair and shoulders. High-tech office atmosphere.
>
> Background: blurred modern open-space office with cool neon accents, faint monitor screens with dashboards and graphs in deep background, beautiful bokeh. Rim light gives a sense of AI-technology energy.
>
> Composition: medium chest-up shot, model looks straight into camera with slight head tilt. **LEFT 35% of the frame is reserved empty for text overlay** — only soft blurred bokeh, no active elements there.
>
> Style: hyperrealistic photography, Sony A7R V + 85mm f/1.4 lens, ISO 200, depth of field f/2.0. Color palette: warm amber-gold tones + cool office accents, dark low-key background. No watermark, no in-frame logos, no text, no busy details.
>
> --ar 1200:630  --style raw  --v 6.1

## Технические требования к финальному PNG

- Размер: **1200 × 630** (рекомендация Open Graph, Twitter Card)
- Формат: **PNG** (без альфа-канала, белый/тёмный matte допустим)
- Вес: до **300 КБ** (используй tinypng.com или squoosh)
- Цветовое пространство: sRGB
- Слева оставить ~420 пикселей чистого фона под наложение слогана (если будем накладывать текст средствами CSS поверх — или сразу залить SVG-слой)
- Пожать в WebP-копию (`og-image.webp`) — не обязательно, но Telegram/WA любят
- Положить в `site/og-image.png` (и продублировать в `/var/www/site/og-image.png` при деплое)

## Сервисы для генерации

- **Midjourney 6.1** (Discord) — лучший фотореализм
- **Reve** (reve.com) — отличная альтернатива MJ
- **DALL-E 3** (через ChatGPT Plus) — быстро и удобно
- **Flux 1.1 Pro** (через replicate.com) — open-source альтернатива
- **Sora** (если подписан) — генерация изображений через text-to-image режим

Если ни один вариант не устраивает — оставляй текущий SVG-плейсхолдер, он выглядит профессионально и сразу читается.
