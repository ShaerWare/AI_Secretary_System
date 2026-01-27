#!/usr/bin/env python3
"""
Сервис интеграции с Gemini API для генерации ответов секретаря
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import google.generativeai as genai
from dotenv import load_dotenv


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.0-flash",
        system_prompt: Optional[str] = None,
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

        # FAQ (загружается через reload_faq из БД)
        self.faq: Dict[str, str] = {}

        logger.info(f"🤖 Инициализация LLM Service: {model_name}")

        try:
            self.model = genai.GenerativeModel(
                model_name=model_name, system_instruction=self.system_prompt
            )
            logger.info("✅ Gemini API подключен")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Gemini: {e}")
            raise

    def _normalize_faq(self, faq_dict: Dict[str, str]) -> Dict[str, str]:
        """Нормализует ключи FAQ (lowercase, strip)"""
        return {k.lower().strip(): v for k, v in faq_dict.items()}

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
            "{day_of_week}": [
                "понедельник",
                "вторник",
                "среда",
                "четверг",
                "пятница",
                "суббота",
                "воскресенье",
            ][now.weekday()],
        }

        for placeholder, value in replacements.items():
            response = response.replace(placeholder, value)

        return response

    def reload_faq(self, faq_dict: Dict[str, str] = None):
        """
        Перезагружает FAQ (hot reload).

        Args:
            faq_dict: FAQ словарь из БД. Если не передан, FAQ очищается.
        """
        if faq_dict:
            self.faq = self._normalize_faq(faq_dict)
        else:
            self.faq = {}
        logger.info(f"🔄 FAQ перезагружен: {len(self.faq)} записей")

    def _default_system_prompt(self) -> str:
        """Системный промпт секретаря по умолчанию"""
        return """# СИСТЕМНЫЙ ПРОМПТ: ЦИФРОВОЙ СЕКРЕТАРЬ "ЛИДИЯ"

Ты — Лидия, цифровой секретарь компании ООО «Шаервэй Ди-Иджитал» и личный помощник Артёма Юрьевича. Отвечай профессионально, дружелюбно и кратко. Максимальная длина реплики — 1-2 предложения.

## 0. КОМАНДЫ (самый высокий приоритет)
Если сообщение начинается с / — это команда, а не речь абонента. Выполняй сразу:
- /перевод [текст] → переведи на английский → ответь только переводом + «Перевод готов.»
- /передай [кому] [текст] → перефразируй профессионально → ответь: «Передаю Артёму Юрьевичу: [текст]»
- /статус → сообщи текущий статус Артёма Юрьевича
- /напомни [задача] [время] → зафиксируй → ответь: «Напоминание создано»
- /лог [сегодня|вчера|дата] → краткий отчёт по звонкам

Если команда не распознана → «Извините, не поняла команду.»

## 1. ПРАВИЛА ГОЛОСОВОГО ВЗАИМОДЕЙСТВИЯ
- Отвечай лаконично: максимум 2–3 предложения.
- Только чистый текст, без Markdown, списков, жирного шрифта.
- Используй букву «ё» всегда: всё, идёт, пришлёт.
- Числа словами: «пятьсот рублей», «двадцать пятое января».
- Аббревиатуры фонетически: «о-о-о», «ай-тИ», «а-пэ-ай».
- Пауза: двойной пробел или «...».
- Название компании: «Шаервэй Ди-Иджитал».

## 2. ПРИВЕТСТВИЕ И ФИЛЬТРАЦИЯ
- Приветствие: «Здравствуйте! Компания Шаервэй Ди-Иджитал, помощник Артёма Юрьевича, Лидия. Слушаю вас.»
- Спам/продажи: «Благодарю, но сейчас это не актуально. Всего доброго.» (завершай звонок).
- Клиенты/партнёры: уточни цель, запиши детали, передай Артёму Юрьевичу.
- Срочное: «Поняла, это срочное. Перезвоню в течение десяти минут.»

## 3. ТОН И ПОВЕДЕНИЕ
- Профессиональный, спокойный, уверенный тон (пресет «warm»).
- Для Артёма Юрьевича — максимально исполнительна: «Да, Артём Юрьевич. Что передать?»
- Эмпатия к клиентам: «Понимаю вашу ситуацию. Давайте я помогу.»

## 4. ОБРАБОТКА ОШИБОК
телефон для связи 982-631-22-67
адрес Фронтовых бригад 18 корпус 27

## 5. ОБРАБОТКА ОШИБОК
- Плохо слышно: «Извините, помехи на линии. Повторите, пожалуйста.»
- Техническая ошибка: «Произошла техническая заминка. Повторите запрос.»

 """

    def generate_response(self, user_message: str, use_history: bool = True) -> str:
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
                chat = self.model.start_chat(
                    history=[
                        {"role": msg["role"], "parts": [msg["content"]]}
                        for msg in self.conversation_history
                    ]
                )
                response = chat.send_message(user_message)
            else:
                # Без истории
                response = self.model.generate_content(user_message)

            assistant_message = response.text.strip()

            # Добавляем в историю
            if use_history:
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "model", "content": assistant_message})

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

    def generate_response_stream(self, user_message: str, use_history: bool = True):
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
                chat = self.model.start_chat(
                    history=[
                        {"role": msg["role"], "parts": [msg["content"]]}
                        for msg in self.conversation_history
                    ]
                )
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
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "model", "content": full_response})

            logger.info(f"✅ Streaming ответ завершён: '{full_response[:50]}...'")

        except Exception as e:
            logger.error(f"❌ Ошибка streaming генерации: {e}")
            yield "Извините, возникла техническая проблема."

    def generate_response_from_messages(self, messages: List[Dict[str, str]], stream: bool = False):
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
