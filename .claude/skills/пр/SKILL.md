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

```
cd /tmp/wiki-update
git add -A
git commit -m "docs: описание изменений в wiki"
git push
rm -rf /tmp/wiki-update
```

**Пропусти этот шаг если изменения мелкие (багфикс, рефакторинг, стилевые правки).**

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
