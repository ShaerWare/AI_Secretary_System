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
        model_name: str = "gemini-2.5-flash",
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

    def set_system_prompt(self, new_prompt: str) -> None:
        """
        Изменяет системный промпт и переинициализирует модель

        Args:
            new_prompt: Новый системный промпт
        """
        logger.info(f"📝 Изменение системного промпта...")
        self.system_prompt = new_prompt
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.system_prompt
        )
        logger.info("✅ Системный промпт обновлён")

    def set_model(self, new_model_name: str) -> None:
        """
        Изменяет модель LLM

        Args:
            new_model_name: Имя новой модели (напр. gemini-2.5-pro, gemini-2.5-flash)
        """
        logger.info(f"🔄 Смена модели на: {new_model_name}")
        self.model_name = new_model_name
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.system_prompt
        )
        logger.info(f"✅ Модель изменена на: {new_model_name}")

    def get_config(self) -> Dict:
        """Возвращает текущую конфигурацию LLM"""
        return {
            "model_name": self.model_name,
            "system_prompt": self.system_prompt,
            "history_length": len(self.conversation_history),
        }

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

    def _convert_messages_to_gemini(self, messages: List[Dict[str, str]]):
        """Конвертирует OpenAI формат сообщений в Gemini формат"""
        gemini_history = []
        last_user_message = ""

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                continue
            elif role == "user":
                last_user_message = content
                gemini_history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_history.append({"role": "model", "parts": [content]})

        # Убираем последнее сообщение пользователя из истории
        if gemini_history and gemini_history[-1]["role"] == "user":
            gemini_history = gemini_history[:-1]

        return gemini_history, last_user_message

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
            Ответ строка (если stream=False) или generator (если stream=True)
        """
        if stream:
            return self._generate_response_stream(messages)
        else:
            return self._generate_response_sync(messages)

    def _generate_response_sync(self, messages: List[Dict[str, str]]) -> str:
        """Синхронная генерация ответа"""
        gemini_history, last_user_message = self._convert_messages_to_gemini(messages)

        try:
            chat = self.model.start_chat(history=gemini_history)
            response = chat.send_message(last_user_message)
            return response.text.strip()
        except Exception as e:
            logger.error(f"❌ Ошибка генерации: {e}")
            return "Извините, возникла техническая проблема."

    def _generate_response_stream(self, messages: List[Dict[str, str]]):
        """Потоковая генерация ответа (generator)"""
        gemini_history, last_user_message = self._convert_messages_to_gemini(messages)

        try:
            chat = self.model.start_chat(history=gemini_history)
            response = chat.send_message(last_user_message, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"❌ Ошибка streaming генерации: {e}")
            yield "Извините, возникла техническая проблема."


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
