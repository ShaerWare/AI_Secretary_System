#!/usr/bin/env python3
"""
Сервис интеграции с Gemini API для генерации ответов секретаря
"""
import os
import logging
from typing import List, Dict, Optional
import google.generativeai as genai
from dotenv import load_dotenv

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

        logger.info(f"🤖 Инициализация LLM Service: {model_name}")

        try:
            self.model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=self.system_prompt
            )
            logger.info("✅ Gemini API подключен")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Gemini: {e}")
            raise

    def _default_system_prompt(self) -> str:
        """Системный промпт секретаря по умолчанию"""
        return """Ты - профессиональный виртуальный секретарь по имени Лидия.

Твои обязанности:
- Отвечать на телефонные звонки вежливо и профессионально
- Записывать информацию о звонящем (имя, контакты, цель звонка)
- Отвечать на типовые вопросы о графике работы, услугах, контактах
- При необходимости предлагать записаться на встречу или перезвонить позже
- Говорить кратко, по делу, но дружелюбно

Правила общения:
- Всегда представляйся в начале разговора
- Будь вежливой, но не слишком многословной
- Если не знаешь ответа, честно скажи об этом и предложи передать информацию руководителю
- Переспрашивай, если не расслышала или не поняла
- Завершай разговор, уточнив, чем еще можно помочь

Стиль общения: деловой, но дружелюбный, как настоящий секретарь."""

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


if __name__ == "__main__":
    # Тестирование
    try:
        service = LLMService()

        # Тестовый диалог
        response1 = service.generate_response("Здравствуйте, это компания XYZ?")
        print(f"Секретарь: {response1}")

        response2 = service.generate_response("Какой у вас график работы?")
        print(f"Секретарь: {response2}")

    except Exception as e:
        print(f"Ошибка при тестировании: {e}")
        print("Создайте файл .env с GEMINI_API_KEY для тестирования")
