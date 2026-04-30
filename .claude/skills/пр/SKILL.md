---
name: пр
description: PR + merge + deploy + wiki + close issues — всё одной командой
---

# Скилл «пр» — полный цикл: PR → Merge → Deploy → Wiki

Выполни полный цикл выпуска изменений. Работай автономно, спрашивай только если что-то критически неясно.

## Контекст

Репо: `ShaerWare/AI_Secretary_System`
Ветка main защищена (branch protection, 3 CI checks).
Деплой: `/opt/ai-secretary/deploy.sh` (production), `/root/deploy-demo.sh` (demo).
Wiki: `ShaerWare/AI_Secretary_System.wiki` (git-based, push напрямую).

## Шаги

### 1. Разведка

```
git status --short
git branch --show-current
git log --oneline -5
git diff --stat
gh issue list --state open --limit 30
```

Определи:
- Какие файлы изменены
- На какой ветке мы (main или feature)
- Какие open issues связаны с изменениями
- **Затронуто ли мобильное приложение** (`mobile/**`, `mobile/android/**`, `mobile/src/**`). Если да — включается полный мобильный цикл (см. шаг 7.5: bump версии, build APK, GitHub Release, обновление ссылок в `LoginView.vue` + `README.md` + wiki, FCM-пуши). Чисто backend-изменения, не влияющие на mobile API контракт, не требуют пересборки APK.

### 2. Обнови документацию проекта (ОБЯЗАТЕЛЬНО)

Прочитай текущие изменения (`git diff`, `git diff --cached`, `git log`) и обнови документацию **до коммита**, чтобы docs шли в том же PR.

**`/opt/ai-secretary/CLAUDE.md`** — главный файл документации проекта. Обнови если:
- Добавлены новые роуты, страницы, views
- Добавлены новые API-эндпоинты, сервисы, модули
- Изменена структура БД (новые таблицы, колонки)
- Добавлены новые компоненты с нетривиальной логикой
- Изменены паттерны, конвенции, архитектурные решения
- Добавлены новые stores, composables, плагины
- Изменена конфигурация сборки, деплоя, CI

**`/root/CLAUDE.md`** — серверный файл. Обнови если:
- Изменились пути деплоя, скрипты, systemd-сервисы
- Добавлены новые серверные утилиты или конфиги

**Что обновлять:**
- Добавь новые сущности в соответствующие секции (роуты, stores, API и т.д.)
- Убери устаревшие упоминания если что-то удалено/переименовано
- НЕ раздувай документацию — только факты, которые помогают ориентироваться в коде

**Если ничего из перечисленного не изменилось** (чистый багфикс, стилевые правки, мелкий рефакторинг) — пропусти, но осознанно: проверь и убедись что docs актуальны.

**Если затронуто мобильное приложение** (флаг из шага 1) — обнови ВСЕ ссылки на APK в одном коммите:
- `mobile/android/app/build.gradle`: подними `versionCode` (на 1) и `versionName` (на патч/минор)
- `admin/src/views/LoginView.vue`: `mobileApkUrl` → `https://github.com/ShaerWare/AI_Secretary_System/releases/latest/download/ai-secretary-<NEW_VERSION>.apk`
- `README.md`: бейдж и блок «📱 ai-secretary-X.Y.apk» — поменяй на новую версию (и тег `mobile-vX.Y` в URL, и имя файла, и команду `adb install`)
- Если изменились screens/UX/permissions — обнови соответствующую страницу wiki (см. шаг 9: «Mobile App.md» / `Home.md`)

### 3. Коммит

Если есть незакоммиченные изменения:
- `git add` только нужные файлы (не .env, не credentials)
- Если на main — создай feature branch: `git checkout -b feat/описание` или `fix/описание`
- Коммит с описательным сообщением + `## NEWS` секция в теле:

```
git commit -m "$(cat <<'EOF'
feat/fix: краткое описание

Детальное описание изменений.

## NEWS

🎉 **Заголовок новости для пользователей**

Описание фичи простым языком, 2-4 предложения.
Что нового, какая польза для пользователя.
Используй эмодзи для привлечения внимания.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

**Правила для NEWS:**
- Пиши НА РУССКОМ, живым человеческим языком
- Объясни пользу для конечного пользователя, не технические детали
- 2-4 предложения, как пост в Telegram-канале
- Начинай с эмодзи + жирного заголовка
- **Если затронуто мобильное приложение** — в конце NEWS-блока добавь markdown-кнопку со ссылкой на скачивание новой APK в формате:
  `[📲 Скачать обновление](https://github.com/ShaerWare/AI_Secretary_System/releases/latest/download/ai-secretary-<NEW_VERSION>.apk)`
  и одну строку про то, что нужно установить новую версию. FCM-пуш отрендерит body как plain text, но в Telegram-канале и в админке кнопка будет кликабельна. (Сами FCM-пуши с этим текстом разлетятся автоматически после merge — см. шаг 7.5.)

### 4. Push + PR

```
git push -u origin <ветка>
```

Создай PR через `gh pr create`:
- `--title` — короткий (до 70 символов)
- `--body` содержит:
  - `## Summary` — буллеты с изменениями
  - `Closes #N` для каждого решённого issue (закроет при мердже)
  - `Relates to #N` если issue не полностью решается
  - `## NEWS` — та же секция из коммита (Telegram бот парсит PR body)
  - `## Test plan` — чеклист проверки
  - `🤖 Generated with [Claude Code](https://claude.com/claude-code)`

### 5. CI + Merge

```
gh pr checks <PR_NUMBER> --watch
gh pr merge <PR_NUMBER> --merge --admin
```

Дождись всех 3 чекоов (lint-backend, lint-frontend, security). Потом мерджи.

### 6. Вернись на main

```
git checkout main && git pull origin main
```

Удали feature branch:
```
git branch -D <ветка>
git push origin --delete <ветка>
```

### 7. Deploy production

```
cd /opt/ai-secretary/admin && npm ci && npm run build
```

Если build упал — починить и пересобрать.

```
grep -l 'setupDemoInterceptor' /opt/ai-secretary/admin/dist/assets/*.js
```
Если нашлось — СТОП, demo interceptor leak!

```
rsync -av --delete /opt/ai-secretary/admin/dist/ /var/www/admin-ai-sekretar24/
sed -i "s/ai-admin-v[0-9]*/ai-admin-v$(date +%s)/" /var/www/admin-ai-sekretar24/sw.js
systemctl restart ai-secretary
```

Подожди 10 сек, проверь health:
```
curl -s http://localhost:8002/health
```

### 7.5. Мобильное приложение: сборка APK + GitHub Release + пуши (только если затронут `mobile/**`)

Этот шаг выполняется ТОЛЬКО когда из шага 1 поднят флаг «затронуто мобильное приложение». Иначе — пропусти.

**a) Собрать APK локально (на машине с GPU/dev — на сервере Android SDK нет):**

```bash
cd /home/shaerware/Documents/AI_Secretary_System/mobile
npm ci
npm run build
npx cap sync android
cd android
./gradlew assembleRelease   # либо assembleDebug если релизный keystore не настроен
```

APK появится в `mobile/android/app/build/outputs/apk/release/app-release.apk` (или `debug/app-debug.apk`). Переименуй в `ai-secretary-<NEW_VERSION>.apk` (версия должна совпадать со значением `versionName` из `mobile/android/app/build.gradle`, поднятым в шаге 2).

Если build упал — починить и пересобрать; не выкатывай старую APK как новую версию.

**b) Создать GitHub Release с тегом `mobile-v<NEW_VERSION>`:**

```bash
cd /home/shaerware/Documents/AI_Secretary_System
gh release create mobile-v<NEW_VERSION> \
  /path/to/ai-secretary-<NEW_VERSION>.apk \
  --title "Mobile v<NEW_VERSION>" \
  --notes "$(cat <<'EOF'
## Что нового
<скопируй сюда блок NEWS из коммита/PR — без эмодзи-заголовка лишний раз>

## Установка
Скачай APK по ссылке ниже, открой на Android-устройстве, разреши установку из неизвестных источников, обнови приложение.

📲 [Скачать ai-secretary-<NEW_VERSION>.apk](https://github.com/ShaerWare/AI_Secretary_System/releases/download/mobile-v<NEW_VERSION>/ai-secretary-<NEW_VERSION>.apk)
EOF
)"
```

**Важно:** ссылка `releases/latest/download/ai-secretary-<NEW_VERSION>.apk` (которую мы прописали в `LoginView.vue` на шаге 2) работает ТОЛЬКО если этот релиз помечен как latest — `gh release create` без `--prerelease` делает это по умолчанию. Если релиз был случайно помечен как pre-release — `gh release edit mobile-v<NEW_VERSION> --latest`.

**c) Обновить env с актуальной версией для эндпоинта `GET /admin/mobile/version`** (мобилка опрашивает его на старте и показывает баннер обновления):

```bash
# на проде:
ssh root@155.212.231.7 "
  sed -i 's/^MOBILE_LATEST_VERSION_NAME=.*/MOBILE_LATEST_VERSION_NAME=<NEW_VERSION>/;
          s/^MOBILE_LATEST_VERSION_CODE=.*/MOBILE_LATEST_VERSION_CODE=<NEW_VERSION_CODE>/;
          s|^MOBILE_LATEST_APK_URL=.*|MOBILE_LATEST_APK_URL=https://github.com/ShaerWare/AI_Secretary_System/releases/download/mobile-v<NEW_VERSION>/ai-secretary-<NEW_VERSION>.apk|' \
    /opt/ai-secretary/.env
  systemctl restart ai-secretary
"
```

Если переменных в `.env` ещё нет — допиши их в конец файла (см. `modules/channels/mobile/router.py:get_latest_version` для дефолтов).

**d) FCM-пуши пользователям.**

При merge PR с секцией `## NEWS` GitHub-webhook автоматически разсылает пуш всем подписанным мобильным устройствам (см. `modules/admin/router_github_webhook.py` + `project_mobile_push.md`). Текст NEWS должен ВКЛЮЧАТЬ ссылку-кнопку на скачивание (правило из шага 3) — тогда пуш сам по себе является «нажми → скачай → установи → обнови».

Проверь, что пуши ушли:

```bash
ssh root@155.212.231.7 "journalctl -u ai-secretary -n 200 | grep -i 'fcm\\|push' | tail -30"
# или вручную:
curl -s http://155.212.231.7:8002/admin/mobile/push/status -H "Authorization: Bearer $TOKEN"
# fcm_enabled должно быть true, total_tokens — число подписанных устройств
```

Если `fcm_enabled=false` или пушей не было — проверь `/opt/ai-secretary/firebase-service-account.json` и row в `bot_github_configs` (см. `project_mobile_push.md`, шаги 1–3).

**e) Дополнительно (если автоматика подвела) — ручной broadcast:**

```bash
curl -X POST http://155.212.231.7:8002/admin/mobile/push/test \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"to_all":true,"title":"Доступно обновление AI-Секретаря","body":"Новая версия <NEW_VERSION>. Скачай и установи: https://github.com/ShaerWare/AI_Secretary_System/releases/latest/download/ai-secretary-<NEW_VERSION>.apk"}'
```

### 8. Deploy demo

```
bash /root/deploy-demo.sh
```

(или запусти в фоне если не хочешь ждать)

### 9. Обнови Wiki (если нужно)

Если изменения затрагивают UI, новые фичи, новые страницы — обнови wiki:

```
cd /tmp && rm -rf wiki-update
git clone https://github.com/ShaerWare/AI_Secretary_System.wiki.git wiki-update
```

Обнови нужные .md файлы в `/tmp/wiki-update/`:
- Новая фича → обнови соответствующую страницу (Chat.md, Widget.md, etc.)
- Новая страница → создай файл + добавь в `_Sidebar.md`
- Home.md → обнови список фич если добавилась крупная
- **Если затронуто мобильное приложение** (флаг из шага 1) — ОБЯЗАТЕЛЬНО:
  - Найди страницу про мобилку (`Mobile-App.md`, `Mobile.md` или аналог; если её нет — создай и добавь в `_Sidebar.md`)
  - Обнови блок «Текущая версия»: номер `versionName`/`versionCode`, дату релиза
  - Обнови прямую ссылку на APK на `https://github.com/ShaerWare/AI_Secretary_System/releases/download/mobile-v<NEW_VERSION>/ai-secretary-<NEW_VERSION>.apk` И добавь markdown-кнопку «📲 Скачать ai-secretary-<NEW_VERSION>.apk»
  - Опиши, что нового в этой версии (можно скопировать из NEWS), укажи что старая версия устарела и обновление обязательно
  - Если изменились permissions/системные требования/процесс установки — обнови соответствующие секции

```
cd /tmp/wiki-update
git add -A
git commit -m "docs: описание изменений в wiki"
git push
rm -rf /tmp/wiki-update
```

**Пропусти этот шаг если изменения мелкие (багфикс, рефакторинг, стилевые правки)** — НО для мобильного релиза wiki обновляется всегда (страница с APK-ссылкой должна указывать на актуальную версию).

### 10. Закрой issues

Проверь что issues закрылись автоматически (через `Closes #N` в PR):
```
gh issue view <N> --json state -q '.state'
```

Если issue не закрылось — закрой вручную:
```
gh issue close <N> --comment "Done in PR #<PR_NUMBER>"
```

### 11. Финальный отчёт

Выведи пользователю:
- Номер PR и ссылку
- Какие issues закрыты
- Статус деплоя (production + demo)
- Обновлена ли wiki
- Ссылку на NEWS (если была) для проверки в Telegram
- **Если был мобильный релиз** (выполнялся шаг 7.5):
  - Новая версия (`versionName` + `versionCode`)
  - Ссылку на GitHub Release `mobile-v<NEW_VERSION>` и прямую ссылку на APK
  - Сколько устройств получили FCM-пуш (`delivered: N` из `/admin/mobile/push/status` или ручного `/admin/mobile/push/test`)
  - Подтверждение, что `LoginView.vue`, `README.md` и wiki-страница про мобилку указывают на новую версию
