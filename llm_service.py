#!/usr/bin/env python3
"""
Сервис интеграции с Gemini API для генерации ответов секретаря
"""
import os
import logging
from typing import List, Dict, Optional
import google.generativeai as genai
from dotenv import load_dotenv
import json
from pathlib import Path
from datetime import datetime

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-pro-latest",
        system_prompt: Optional[str] = None
    ):
        """
        Инициализация сервиса LLM

        Args:
            api_key: API ключ Gemini (если не задан, берется из .env)
            model_name: Название модели
            system_prompt: Системный промпт для секретаря
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY не найден в переменных окружения")

        self.model_name = model_name
        self.conversation_history: List[Dict[str, str]] = []

        # Настройка Gemini API
        genai.configure(api_key=self.api_key)

        # Системный промпт по умолчанию
        self.system_prompt = system_prompt or self._default_system_prompt()

        # Загружаем типовые ответы (FAQ)
        self.faq_path = Path("typical_responses.json")
        self.faq: Dict[str, str] = self._load_faq()

        logger.info(f"🤖 Инициализация LLM Service: {model_name}")
        logger.info(f"📚 Загружено типовых ответов: {len(self.faq)}")

        try:
            self.model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=self.system_prompt
            )
            logger.info("✅ Gemini API подключен")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Gemini: {e}")
            raise

    def _load_faq(self) -> Dict[str, str]:
        """Загружает типовые вопросы-ответы из JSON"""
        if not self.faq_path.exists():
            logger.warning("Файл типовых ответов не найден: %s → FAQ отключён", self.faq_path)
            return {}

        try:
            with self.faq_path.open(encoding="utf-8") as f:
                raw_data = json.load(f)
            # Приводим ключи к нижнему регистру и убираем лишние пробелы
            return {k.lower().strip(): v for k, v in raw_data.items()}
        except Exception as e:
            logger.error("Ошибка загрузки типовых ответов %s: %s", self.faq_path, e)
            return {}

    def _check_faq(self, user_message: str) -> Optional[str]:
        """
        Проверяет сообщение на совпадение с типичными вопросами.
        Поддерживает шаблоны: {current_time}, {current_date}

        Returns:
            Заготовленный ответ или None, если совпадения нет
        """
        if not self.faq:
            return None

        # Нормализуем ввод: lowercase, убираем лишние пробелы и знаки препинания
        normalized = user_message.lower().strip().rstrip("?!.,")

        # Точное совпадение
        if normalized in self.faq:
            response = self.faq[normalized]
            logger.info(f"📋 FAQ match (exact): '{normalized}'")
            return self._apply_faq_templates(response)

        # Проверяем, содержится ли ключ FAQ в сообщении (для более длинных фраз)
        for key, response in self.faq.items():
            if key in normalized or normalized in key:
                logger.info(f"📋 FAQ match (partial): '{key}' in '{normalized}'")
                return self._apply_faq_templates(response)

        return None

    def _apply_faq_templates(self, response: str) -> str:
        """Подставляет переменные шаблона в ответ"""
        now = datetime.now()

        replacements = {
            "{current_time}": now.strftime("%H:%M"),
            "{current_date}": now.strftime("%d.%m.%Y"),
            "{day_of_week}": ["понедельник", "вторник", "среда", "четверг",
                             "пятница", "суббота", "воскресенье"][now.weekday()],
        }

        for placeholder, value in replacements.items():
            response = response.replace(placeholder, value)

        return response

    def reload_faq(self):
        """Перезагружает FAQ из файла (hot reload)"""
        self.faq = self._load_faq()
        logger.info(f"🔄 FAQ перезагружен: {len(self.faq)} записей")

    def _default_system_prompt(self) -> str:
        """Системный промпт секретаря по умолчанию"""
        return """# СИСТЕМНЫЙ ПРОМПТ: ЦИФРОВОЙ СЕКРЕТАРЬ "ЛИДИЯ" (ООО «SHAREWARE DIDGITAL»)

Ты — Лидия, высокотехнологичный цифровой секретарь-референт компании ООО «Shareware Digital» и личный помощник Артёма Юрьевича. Твоя задача — обрабатывать входящие и исходящие звонки, фильтровать спам, записывать сообщения и помогать в коммуникации с клиентами и партнерами.

## 1. ПРАВИЛА ГОЛОСОВОГО ВЗАИМОДЕЙСТВИЯ (TTS/STT OPTIMIZATION)

1. **Краткость и темп:** В телефонном разговоре отвечай лаконично. Максимальная длина одной реплики — 2-3 предложения. Это минимизирует задержку синтеза (latency).
2. **Никакой разметки:** Твой текст сразу уходит в синтезатор речи. Категорически запрещено использовать **жирный шрифт**, *курсив*, списки, решетки или символы Markdown. Только чистый текст.
3. **Фонетическая адаптация:**
   - Пиши аббревиатуры так, как они произносятся: вместо "ООО" пиши "о-о-о", вместо "IT" пиши "ай-тИ".
   - Название компании: "Шэарвэар Диджитал".
4. **Обязательная Ё-фикация:** Всегда используй букву "ё" (всё, идёт, пришлёт), чтобы XTTS v2 правильно расставлял ударения и интонации.
5. **Числа словами:** Пиши числа прописью (например, "пятьсот рублей" вместо "500 руб."), чтобы избежать ошибок синтеза.
6. **Паузы:** Используй двойной пробел "  " для обозначения естественной паузы между мыслями.

## 2. СТРАТЕГИЯ ОБРАБОТКИ ЗВОНКОВ

### 2.1. Приветствие и идентификация
- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Лидия. Слушаю вас."
- Если собеседник не представился: "Подскажите, пожалуйста, как я могу к вам обращаться?"

### 2.2. Фильтрация (Gatekeeping)
- **Спам/Продажи/Банки:** "Благодарю за предложение, но сейчас это не актуально. Артём Юрьевич просил не отвлекать его по таким вопросам. Всего доброго." (Вежливо, но твердо завершай звонок).
- **Клиенты и партнеры:** Уточни цель звонка. Если вопрос важный, скажи: "Артём Юрьевич сейчас занят на совещании. Я зафиксирую информацию и передам ему. Что мне сообщить?"

### 2.3. Управление ожиданиями (Latency Fillers)
Если тебе нужно время на обработку запроса через Gemini, используй фразы-заполнители:
- "Так, секунду, сверяюсь с графиком.."
- "Сейчас посмотрю информацию, одну минуту.."
- "Поняла вас, сейчас проверю.."

### 2.4. Режим переводчика
Если звонящий говорит на английском, плавно переходи на него: "One moment, please. I am Artyom's digital assistant. How can I help you?"

## 3. ЛИЧНОСТЬ И ТОН

- **Тон:** Профессиональный, дружелюбный, спокойный (пресет "warm").
- **Статус:** Ты не просто бот, ты — лицо компании. Ты должна звучать как компетентный сотрудник, который ценит время своего руководителя.
- **Отношение к Артёму Юрьевичу:** Глубокое уважение и соблюдение его интересов. Если звонит сам Артём Юрьевич, будь максимально исполнительной и краткой.

## 4. ОБРАБОТКА ОШИБОК

Если распознавание речи (STT) прислало неразборчивый текст, не пытайся угадать. Скажи:
- "Извините, плохо слышно, помехи на линии. Повторите, пожалуйста, последнюю фразу."

## 5. ПРИМЕРЫ РЕПЛИК

- "Принято. Я передам Артёму Юрьевичу, что вы звонили по поводу настройки сервера."
- "К сожалению, на этой неделе всё время уже расписано. Давайте я уточню возможность встречи на следующей и перезвоню вам?"
- "О-о-о Шэарвэар Диджитал приветствует вас. Чем я могу помочь?"

---
*Инструкция для системы: При генерации ответа всегда проверяй текст на отсутствие символов разметки и наличие буквы "ё".*"""

    def generate_response(
        self,
        user_message: str,
        use_history: bool = True
    ) -> str:
        """
        Генерирует ответ на сообщение пользователя

        Args:
            user_message: Сообщение от пользователя
            use_history: Использовать историю диалога

        Returns:
            Сгенерированный ответ
        """
        logger.info(f"💬 Запрос к LLM: '{user_message[:50]}...'")

        # Сначала проверяем FAQ
        faq_response = self._check_faq(user_message)
        if faq_response:
            logger.info(f"⚡ FAQ ответ (без LLM): '{faq_response[:50]}...'")
            # Добавляем в историю для контекста
            if use_history:
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "model", "content": faq_response})
            return faq_response

        try:
            if use_history:
                # Используем историю для контекста
                chat = self.model.start_chat(history=[
                    {"role": msg["role"], "parts": [msg["content"]]}
                    for msg in self.conversation_history
                ])
                response = chat.send_message(user_message)
            else:
                # Без истории
                response = self.model.generate_content(user_message)

            assistant_message = response.text.strip()

            # Добавляем в историю
            if use_history:
                self.conversation_history.append({
                    "role": "user",
                    "content": user_message
                })
                self.conversation_history.append({
                    "role": "model",
                    "content": assistant_message
                })

            logger.info(f"✅ Ответ LLM: '{assistant_message[:50]}...'")
            return assistant_message

        except Exception as e:
            logger.error(f"❌ Ошибка генерации ответа: {e}")
            # Fallback ответ
            return "Извините, возникла техническая проблема. Пожалуйста, повторите ваш вопрос."

    def reset_conversation(self):
        """Сбрасывает историю диалога"""
        self.conversation_history = []
        logger.info("🔄 История диалога сброшена")

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Возвращает историю диалога"""
        return self.conversation_history

    def generate_response_stream(
        self,
        user_message: str,
        use_history: bool = True
    ):
        """
        Генерирует ответ в потоковом режиме (streaming)

        Args:
            user_message: Сообщение от пользователя
            use_history: Использовать историю диалога

        Yields:
            Части ответа по мере генерации
        """
        logger.info(f"💬 Streaming запрос к LLM: '{user_message[:50]}...'")

        # Сначала проверяем FAQ
        faq_response = self._check_faq(user_message)
        if faq_response:
            logger.info(f"⚡ FAQ ответ (без LLM): '{faq_response[:50]}...'")
            if use_history:
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "model", "content": faq_response})
            yield faq_response
            return

        try:
            if use_history:
                chat = self.model.start_chat(history=[
                    {"role": msg["role"], "parts": [msg["content"]]}
                    for msg in self.conversation_history
                ])
                response = chat.send_message(user_message, stream=True)
            else:
                response = self.model.generate_content(user_message, stream=True)

            full_response = ""
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text

            # Добавляем в историю после завершения
            if use_history:
                self.conversation_history.append({
                    "role": "user",
                    "content": user_message
                })
                self.conversation_history.append({
                    "role": "model",
                    "content": full_response
                })

            logger.info(f"✅ Streaming ответ завершён: '{full_response[:50]}...'")

        except Exception as e:
            logger.error(f"❌ Ошибка streaming генерации: {e}")
            yield "Извините, возникла техническая проблема."

    def generate_response_from_messages(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False
    ):
        """
        Генерирует ответ на основе списка сообщений OpenAI формата

        Args:
            messages: Список сообщений [{"role": "user/assistant", "content": "..."}]
            stream: Использовать потоковую генерацию

        Returns/Yields:
            Ответ или части ответа
        """
        # Конвертируем OpenAI формат в Gemini формат
        gemini_history = []
        last_user_message = ""

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                # Системные сообщения пропускаем (уже в system_instruction)
                continue
            elif role == "user":
                last_user_message = content
                gemini_history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_history.append({"role": "model", "parts": [content]})

        # Убираем последнее сообщение пользователя из истории (оно будет отправлено)
        if gemini_history and gemini_history[-1]["role"] == "user":
            gemini_history = gemini_history[:-1]

        # Проверяем FAQ (только для коротких сообщений без контекста)
        if last_user_message and len(gemini_history) == 0:
            faq_response = self._check_faq(last_user_message)
            if faq_response:
                logger.info(f"⚡ FAQ ответ (без LLM): '{faq_response[:50]}...'")
                if stream:
                    yield faq_response
                    return
                else:
                    return faq_response

        try:
            chat = self.model.start_chat(history=gemini_history)

            if stream:
                response = chat.send_message(last_user_message, stream=True)
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
            else:
                response = chat.send_message(last_user_message)
                return response.text.strip()

        except Exception as e:
            logger.error(f"❌ Ошибка генерации: {e}")
            if stream:
                yield "Извините, возникла техническая проблема."
            else:
                return "Извините, возникла техническая проблема."


if __name__ == "__main__":
    # Тестирование
    try:
        service = LLMService()

        # Тест FAQ (без вызова LLM)
        print("\n=== Тест FAQ ===")
        faq_tests = ["Привет", "сколько времени?", "Какой сегодня день", "Спасибо!"]
        for test in faq_tests:
            response = service.generate_response(test, use_history=False)
            print(f"  '{test}' → {response}")

        # Тестовый диалог с LLM (если FAQ не сработал)
        print("\n=== Тест LLM ===")
        service.reset_conversation()
        response1 = service.generate_response("Здравствуйте, это компания XYZ?")
        print(f"Секретарь: {response1}")

        response2 = service.generate_response("Какой у вас график работы?")
        print(f"Секретарь: {response2}")

    except Exception as e:
        print(f"Ошибка при тестировании: {e}")
        print("Создайте файл .env с GEMINI_API_KEY для тестирования")
