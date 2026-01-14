# AI Secretary System "Лидия"

Виртуальный секретарь с клонированием голоса на базе XTTS v2.

## Статус проекта

**Voice Clone Service** полностью настроен и работает:
- Модель XTTS v2 загружена
- Голосовые образцы из папки `Лидия/` подключены
- Синтез работает на CPU (GPU P104-100 не поддерживается PyTorch 2.9)

## Как запустить синтез голоса

```bash
source venv/bin/activate
COQUI_TOS_AGREED=1 python3 voice_clone_service.py
```

Результат: `test_lidia_2026.wav`

## Как изменить текст

В файле `voice_clone_service.py` строка 97:
```python
test_text = "Ваш текст здесь"
```

## Ключевые файлы

| Файл | Назначение |
|------|------------|
| `voice_clone_service.py` | Синтез голоса XTTS v2 |
| `orchestrator.py` | Координатор всех сервисов |
| `Лидия/` | 54 WAV образца голоса |
| `SYSTEM_DOCS.md` | Полная документация |

## Установленные зависимости

- PyTorch 2.9.1
- coqui-tts 0.27.3
- torchcodec 0.9.1
- soundfile, numpy

## Исправленные проблемы

1. Импорт: `from TTS.api import TTS` (не coqui_tts)
2. GPU: принудительно CPU (`self.device = "cpu"`)
3. Лицензия: `COQUI_TOS_AGREED=1`
4. Аудио: установлен torchcodec

## Порты

- Orchestrator: 8002
- Phone Service: 8001
- OpenWebUI: 3000
