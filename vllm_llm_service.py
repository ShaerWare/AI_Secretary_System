#!/usr/bin/env python3
"""
Сервис интеграции с vLLM (OpenAI-compatible API) для генерации ответов секретаря.
Поддерживает Qwen2.5-7B с LoRA, Llama-3.1-8B и DeepSeek-LLM-7B через vLLM.
Поддерживает несколько персон (Гуля, Лидия и др.)
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Generator, List, Optional

import httpx


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============== Доступные модели vLLM ==============
AVAILABLE_MODELS = {
    "qwen": {
        "id": "qwen",
        "name": "Qwen2.5-7B-AWQ",
        "full_name": "Qwen/Qwen2.5-7B-Instruct-AWQ",
        "description": "Китайская модель от Alibaba. Отличное качество для русского языка.",
        "size": "~4GB VRAM",
        "features": ["Русский", "Китайский", "Английский", "Код", "LoRA поддержка"],
        "start_flag": "",  # default
        "lora_support": True,
    },
    "llama": {
        "id": "llama",
        "name": "Llama-3.1-8B-GPTQ",
        "full_name": "meta-llama/Llama-3.1-8B-Instruct (GPTQ INT4)",
        "description": "Модель от Meta. Хорошее качество для английского.",
        "size": "~5GB VRAM",
        "features": ["Английский", "Код", "Инструкции"],
        "start_flag": "--llama",
        "lora_support": False,
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek-LLM-7B",
        "full_name": "deepseek-ai/deepseek-llm-7b-chat",
        "description": "Китайская модель от DeepSeek AI. Сильная в reasoning и коде.",
        "size": "~5GB VRAM",
        "features": ["Русский", "Китайский", "Английский", "Код", "Reasoning"],
        "start_flag": "--deepseek",
        "lora_support": False,
    },
}


# ============== Персоны секретарей ==============
SECRETARY_PERSONAS = {
    "gulya": {
        "name": "Гуля",
        "full_name": "Гульнара",
        "company": "Shareware Digital",
        "boss": "Артёма Юрьевича",
        "prompt": """Ты — Гуля (Гульнара), цифровой секретарь компании Shareware Digital и личный помощник Артёма Юрьевича.

ПРАВИЛА:
1. Отвечай кратко (2-3 предложения максимум)
2. Никакой разметки - только чистый текст
3. Используй букву "ё" (всё, идёт, пришлёт)
4. Числа пиши словами (пятьсот рублей)
5. ООО произноси как "о-о-о", IT как "ай-ти"

РОЛЬ:
- Фильтруй спам и продажи
- Записывай сообщения для Артёма Юрьевича
- Будь профессиональной и дружелюбной

ПРИМЕРЫ:
- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Гуля. Слушаю вас."
- "Принято. Я передам Артёму Юрьевичу, что вы звонили."
- "К сожалению, это предложение сейчас не актуально. Всего доброго."
""",
    },
    "lidia": {
        "name": "Лидия",
        "full_name": "Лидия",
        "company": "Shareware Digital",
        "boss": "Артёма Юрьевича",
        "prompt": """Ты — Лидия, цифровой секретарь компании Shareware Digital и личный помощник Артёма Юрьевича.

ПРАВИЛА:
1. Отвечай кратко (2-3 предложения максимум)
2. Никакой разметки - только чистый текст
3. Используй букву "ё" (всё, идёт, пришлёт)
4. Числа пиши словами (пятьсот рублей)
5. ООО произноси как "о-о-о", IT как "ай-ти"

РОЛЬ:
- Фильтруй спам и продажи
- Записывай сообщения для Артёма Юрьевича
- Будь профессиональной и дружелюбной

ПРИМЕРЫ:
- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Лидия. Слушаю вас."
- "Принято. Я передам Артёму Юрьевичу, что вы звонили."
- "К сожалению, это предложение сейчас не актуально. Всего доброго."
""",
    },
}

# Персона по умолчанию (из env или gulya)
DEFAULT_PERSONA = os.getenv("SECRETARY_PERSONA", "gulya")


class VLLMLLMService:
    """
    LLM сервис через vLLM (OpenAI-compatible API).
    Поддерживает:
    - Qwen2.5-7B-Instruct + LoRA
    - Llama-3.1-8B-Instruct GPTQ
    - DeepSeek-LLM-7B-Chat
    - Несколько персон секретарей (Гуля, Лидия)
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        persona: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """
        Инициализация сервиса vLLM

        Args:
            api_url: URL vLLM API (default: http://localhost:11434)
            model_name: Название модели (auto-detect from vLLM, или VLLM_MODEL_NAME env)
            system_prompt: Системный промпт для секретаря (переопределяет персону)
            persona: Персона секретаря (gulya, lidia). Default: SECRETARY_PERSONA env или gulya
            timeout: Таймаут запросов в секундах
        """
        self.api_url = api_url or os.getenv("VLLM_API_URL", "http://localhost:11434")
        # Приоритет: аргумент > env var > auto-detect
        self.model_name = model_name or os.getenv("VLLM_MODEL_NAME", "")
        self.timeout = timeout
        self.conversation_history: List[Dict[str, str]] = []

        # HTTP клиент
        self.client = httpx.Client(timeout=timeout)

        # Runtime параметры генерации (могут быть изменены через API)
        self.runtime_params = {
            "temperature": 0.7,
            "max_tokens": 512,
            "top_p": 0.9,
            "repetition_penalty": 1.1,
        }

        # Персона секретаря
        self.persona_id = persona or DEFAULT_PERSONA
        if self.persona_id not in SECRETARY_PERSONAS:
            logger.warning(f"⚠️ Персона '{self.persona_id}' не найдена, используется 'gulya'")
            self.persona_id = "gulya"
        self.persona = SECRETARY_PERSONAS[self.persona_id]

        # Системный промпт (явный промпт > персона)
        self.system_prompt = system_prompt or self.persona["prompt"]

        # FAQ (загружается через reload_faq из БД)
        self.faq: Dict[str, str] = {}

        logger.info(f"🤖 Инициализация vLLM Service: {self.api_url}")
        logger.info(f"👤 Персона: {self.persona['name']} ({self.persona_id})")

        # Проверяем подключение и получаем/проверяем имя модели
        self._check_connection()

    def _check_connection(self):
        """Проверяет подключение к vLLM и получает/проверяет имя модели"""
        try:
            response = self.client.get(f"{self.api_url}/v1/models")
            response.raise_for_status()
            models = response.json()

            available_models = [m["id"] for m in models.get("data", [])]

            if self.model_name:
                # Модель указана явно - проверяем её наличие
                if self.model_name in available_models:
                    logger.info(f"✅ vLLM подключен, модель: {self.model_name}")
                else:
                    logger.warning(
                        f"⚠️ Модель '{self.model_name}' не найдена, доступны: {available_models}"
                    )
                    # Fallback на первую доступную
                    if available_models:
                        self.model_name = available_models[0]
                        logger.info(f"📌 Используем: {self.model_name}")
            elif available_models:
                # Auto-detect: берём первую модель
                self.model_name = available_models[0]
                logger.info(f"✅ vLLM подключен, модель (auto): {self.model_name}")
            else:
                logger.warning("⚠️ vLLM не вернул список моделей")
                self.model_name = "unknown"

            # Логируем все доступные модели (для LoRA)
            if len(available_models) > 1:
                logger.info(f"📋 Доступные модели: {available_models}")

        except httpx.ConnectError:
            logger.warning(f"⚠️ vLLM недоступен по адресу {self.api_url}")
            if not self.model_name:
                self.model_name = "offline"
        except Exception as e:
            logger.warning(f"⚠️ Ошибка подключения к vLLM: {e}")
            if not self.model_name:
                self.model_name = "error"

    def _normalize_faq(self, faq_dict: Dict[str, str]) -> Dict[str, str]:
        """Нормализует ключи FAQ (lowercase, strip)"""
        return {k.lower().strip(): v for k, v in faq_dict.items()}

    def _check_faq(self, user_message: str) -> Optional[str]:
        """Проверяет сообщение на совпадение с FAQ"""
        if not self.faq:
            return None

        normalized = user_message.lower().strip().rstrip("?!.,")

        if normalized in self.faq:
            response = self.faq[normalized]
            logger.info(f"📋 FAQ match (exact): '{normalized}'")
            return self._apply_faq_templates(response)

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
        """Системный промпт секретаря (deprecated, используется persona)"""
        # Возвращаем промпт текущей персоны
        return self.persona["prompt"]

    def set_persona(self, persona_id: str) -> bool:
        """
        Меняет персону секретаря.

        Args:
            persona_id: ID персоны (gulya, lidia)

        Returns:
            True если персона успешно изменена
        """
        if persona_id not in SECRETARY_PERSONAS:
            logger.warning(f"⚠️ Персона '{persona_id}' не найдена")
            return False

        self.persona_id = persona_id
        self.persona = SECRETARY_PERSONAS[persona_id]
        self.system_prompt = self.persona["prompt"]
        logger.info(f"👤 Персона изменена на: {self.persona['name']} ({persona_id})")
        return True

    def get_available_personas(self) -> Dict[str, Dict]:
        """Возвращает список доступных персон"""
        return {
            pid: {"name": p["name"], "full_name": p["full_name"]}
            for pid, p in SECRETARY_PERSONAS.items()
        }

    def set_params(self, **kwargs):
        """
        Устанавливает runtime параметры генерации.

        Args:
            temperature: float (0.0-2.0)
            max_tokens: int (1-4096)
            top_p: float (0.0-1.0)
            repetition_penalty: float (1.0-2.0)
        """
        for key, value in kwargs.items():
            if key in self.runtime_params and value is not None:
                self.runtime_params[key] = value
        logger.info(f"⚙️ Параметры обновлены: {self.runtime_params}")

    def get_params(self) -> Dict:
        """Возвращает текущие параметры генерации"""
        return self.runtime_params.copy()

    # Для обратной совместимости (старый промпт)
    @staticmethod
    def _legacy_system_prompt() -> str:
        """Старый системный промпт (для справки)"""
        return """Ты — Лидия, цифровой секретарь компании Shareware Digital и личный помощник Артёма Юрьевича.

ПРАВИЛА:
1. Отвечай кратко (2-3 предложения максимум)
2. Никакой разметки - только чистый текст
3. Используй букву "ё" (всё, идёт, пришлёт)
4. Числа пиши словами (пятьсот рублей)
5. ООО произноси как "о-о-о", IT как "ай-ти"

РОЛЬ:
- Фильтруй спам и продажи
- Записывай сообщения для Артёма Юрьевича
- Будь профессиональной и дружелюбной

ПРИМЕРЫ:
- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Лидия. Слушаю вас."
- "Принято. Я передам Артёму Юрьевичу, что вы звонили."
- "К сожалению, это предложение сейчас не актуально. Всего доброго."
"""

    def generate_response(self, user_message: str, use_history: bool = True) -> str:
        """Генерирует ответ на сообщение пользователя"""
        logger.info(f"💬 Запрос к vLLM: '{user_message[:50]}...'")

        # Сначала проверяем FAQ
        faq_response = self._check_faq(user_message)
        if faq_response:
            logger.info(f"⚡ FAQ ответ (без LLM): '{faq_response[:50]}...'")
            if use_history:
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": faq_response})
            return faq_response

        try:
            # Формируем сообщения
            messages = [{"role": "system", "content": self.system_prompt}]

            if use_history:
                messages.extend(self.conversation_history)

            messages.append({"role": "user", "content": user_message})

            # Запрос к vLLM с runtime параметрами
            response = self.client.post(
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "max_tokens": self.runtime_params.get("max_tokens", 256),
                    "temperature": self.runtime_params.get("temperature", 0.7),
                    "top_p": self.runtime_params.get("top_p", 0.9),
                    "repetition_penalty": self.runtime_params.get("repetition_penalty", 1.1),
                    "stream": False,
                },
            )
            response.raise_for_status()

            result = response.json()
            assistant_message = result["choices"][0]["message"]["content"].strip()

            # Добавляем в историю
            if use_history:
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append(
                    {"role": "assistant", "content": assistant_message}
                )

            logger.info(f"✅ Ответ vLLM: '{assistant_message[:50]}...'")
            return assistant_message

        except httpx.ConnectError:
            logger.error("❌ vLLM недоступен")
            return "Извините, сервис временно недоступен. Попробуйте позже."
        except Exception as e:
            logger.error(f"❌ Ошибка генерации ответа: {e}")
            return "Извините, возникла техническая проблема. Пожалуйста, повторите ваш вопрос."

    def generate_response_stream(
        self, user_message: str, use_history: bool = True
    ) -> Generator[str, None, None]:
        """Генерирует ответ в потоковом режиме"""
        logger.info(f"💬 Streaming запрос к vLLM: '{user_message[:50]}...'")

        # Сначала проверяем FAQ
        faq_response = self._check_faq(user_message)
        if faq_response:
            logger.info(f"⚡ FAQ ответ (без LLM): '{faq_response[:50]}...'")
            if use_history:
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": faq_response})
            yield faq_response
            return

        try:
            messages = [{"role": "system", "content": self.system_prompt}]

            if use_history:
                messages.extend(self.conversation_history)

            messages.append({"role": "user", "content": user_message})

            # Streaming запрос с runtime параметрами
            with self.client.stream(
                "POST",
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "max_tokens": self.runtime_params.get("max_tokens", 256),
                    "temperature": self.runtime_params.get("temperature", 0.7),
                    "top_p": self.runtime_params.get("top_p", 0.9),
                    "repetition_penalty": self.runtime_params.get("repetition_penalty", 1.1),
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()

                full_response = ""
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                yield content
                        except json.JSONDecodeError:
                            continue

                # Добавляем в историю
                if use_history and full_response:
                    self.conversation_history.append({"role": "user", "content": user_message})
                    self.conversation_history.append(
                        {"role": "assistant", "content": full_response}
                    )

                logger.info(f"✅ Streaming ответ завершён: '{full_response[:50]}...'")

        except httpx.ConnectError:
            logger.error("❌ vLLM недоступен")
            yield "Извините, сервис временно недоступен."
        except Exception as e:
            logger.error(f"❌ Ошибка streaming генерации: {e}")
            yield "Извините, возникла техническая проблема."

    def generate_response_from_messages(self, messages: List[Dict[str, str]], stream: bool = False):
        """
        Генерирует ответ на основе списка сообщений OpenAI формата.
        Совместимо с форматом orchestrator.py.
        """
        # Для non-streaming используем отдельный метод (избегаем yield в non-stream)
        if not stream:
            return self._generate_response_non_stream(messages)

        # Streaming режим - возвращает генератор
        return self._generate_response_stream(messages)

    def _generate_response_non_stream(self, messages: List[Dict[str, str]]) -> str:
        """Non-streaming генерация ответа"""
        # Добавляем system prompt если его нет
        has_system = any(m.get("role") == "system" for m in messages)

        if not has_system:
            final_messages = [{"role": "system", "content": self.system_prompt}]
            final_messages.extend(messages)
        else:
            final_messages = messages

        # Получаем последнее сообщение пользователя для FAQ
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break

        # Проверяем FAQ (только если мало контекста)
        user_messages_count = sum(1 for m in messages if m.get("role") == "user")
        if last_user_message and user_messages_count <= 1:
            faq_response = self._check_faq(last_user_message)
            if faq_response:
                logger.info(f"⚡ FAQ ответ: '{faq_response[:50]}...'")
                return faq_response

        try:
            response = self.client.post(
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": final_messages,
                    "max_tokens": self.runtime_params.get("max_tokens", 512),
                    "temperature": self.runtime_params.get("temperature", 0.7),
                    "top_p": self.runtime_params.get("top_p", 0.9),
                    "repetition_penalty": self.runtime_params.get("repetition_penalty", 1.1),
                    "stream": False,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()

        except httpx.ConnectError:
            logger.error("❌ vLLM недоступен")
            return "Извините, сервис временно недоступен."
        except Exception as e:
            logger.error(f"❌ Ошибка генерации: {e}")
            return "Извините, возникла техническая проблема."

    def _generate_response_stream(
        self, messages: List[Dict[str, str]]
    ) -> Generator[str, None, None]:
        """Streaming генерация ответа"""
        # Добавляем system prompt если его нет
        has_system = any(m.get("role") == "system" for m in messages)

        if not has_system:
            final_messages = [{"role": "system", "content": self.system_prompt}]
            final_messages.extend(messages)
        else:
            final_messages = messages

        # Получаем последнее сообщение пользователя для FAQ
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break

        # Проверяем FAQ (только если мало контекста)
        user_messages_count = sum(1 for m in messages if m.get("role") == "user")
        if last_user_message and user_messages_count <= 1:
            faq_response = self._check_faq(last_user_message)
            if faq_response:
                logger.info(f"⚡ FAQ ответ: '{faq_response[:50]}...'")
                yield faq_response
                return

        try:
            # Streaming с runtime параметрами
            with self.client.stream(
                "POST",
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": final_messages,
                    "max_tokens": self.runtime_params.get("max_tokens", 512),
                    "temperature": self.runtime_params.get("temperature", 0.7),
                    "top_p": self.runtime_params.get("top_p", 0.9),
                    "repetition_penalty": self.runtime_params.get("repetition_penalty", 1.1),
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

        except httpx.ConnectError:
            logger.error("❌ vLLM недоступен")
            yield "Извините, сервис временно недоступен."
        except Exception as e:
            logger.error(f"❌ Ошибка генерации: {e}")
            yield "Извините, возникла техническая проблема."

    def reset_conversation(self):
        """Сбрасывает историю диалога"""
        self.conversation_history = []
        logger.info("🔄 История диалога сброшена")

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Возвращает историю диалога"""
        return self.conversation_history

    def is_available(self) -> bool:
        """Проверяет доступность vLLM"""
        try:
            response = self.client.get(f"{self.api_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def get_available_models() -> Dict[str, Dict]:
        """Возвращает список доступных моделей для vLLM"""
        return AVAILABLE_MODELS

    def get_current_model_info(self) -> Dict:
        """
        Возвращает информацию о текущей загруженной модели.
        Пытается определить модель по имени из vLLM.
        """
        model_id = self.model_name.lower() if self.model_name else "unknown"

        # Пытаемся определить по имени модели
        for key, info in AVAILABLE_MODELS.items():
            if key in model_id or info["name"].lower() in model_id:
                return {
                    "id": key,
                    "name": info["name"],
                    "full_name": info["full_name"],
                    "description": info["description"],
                    "vllm_model_name": self.model_name,
                    "available": self.is_available(),
                }

        # LoRA адаптер (lydia)
        if "lydia" in model_id:
            qwen_info = AVAILABLE_MODELS.get("qwen", {})
            return {
                "id": "qwen",
                "name": f"{qwen_info.get('name', 'Qwen')} + Lydia LoRA",
                "full_name": qwen_info.get("full_name", ""),
                "description": qwen_info.get("description", ""),
                "vllm_model_name": self.model_name,
                "lora": "lydia",
                "available": self.is_available(),
            }

        # Неизвестная модель
        return {
            "id": "unknown",
            "name": self.model_name or "Unknown",
            "vllm_model_name": self.model_name,
            "available": self.is_available(),
        }

    def get_loaded_models(self) -> List[str]:
        """Возвращает список моделей, загруженных в vLLM"""
        try:
            response = self.client.get(f"{self.api_url}/v1/models")
            response.raise_for_status()
            models = response.json()
            return [m["id"] for m in models.get("data", [])]
        except Exception:
            return []


if __name__ == "__main__":
    # Тестирование
    print("=== Тест vLLM LLM Service ===\n")

    try:
        service = VLLMLLMService()

        if not service.is_available():
            print("⚠️ vLLM недоступен. Запустите: ./start_vllm.sh")
            exit(1)

        # Тест FAQ
        print("=== Тест FAQ ===")
        faq_tests = ["Привет", "сколько времени?", "Какой сегодня день"]
        for test in faq_tests:
            response = service.generate_response(test, use_history=False)
            print(f"  '{test}' → {response}")

        # Тест LLM
        print("\n=== Тест vLLM ===")
        service.reset_conversation()

        response1 = service.generate_response("Здравствуйте, это компания XYZ?")
        print(f"Секретарь: {response1}")

        response2 = service.generate_response("Какой у вас график работы?")
        print(f"Секретарь: {response2}")

        # Тест streaming
        print("\n=== Тест Streaming ===")
        print("Секретарь: ", end="", flush=True)
        for chunk in service.generate_response_stream("Расскажите о компании", use_history=False):
            print(chunk, end="", flush=True)
        print()

    except Exception as e:
        print(f"Ошибка при тестировании: {e}")
