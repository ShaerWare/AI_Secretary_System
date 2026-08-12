#!/usr/bin/env python3
"""
Сервис интеграции с vLLM (OpenAI-compatible API) для генерации ответов секретаря.
Поддерживает Qwen2.5-7B с LoRA, Llama-3.1-8B и DeepSeek-LLM-7B через vLLM.
Поддерживает несколько персон (Анна, Марина и др.)
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional

import httpx


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============== Предопределённые модели vLLM ==============
PREDEFINED_MODELS = {
    "qwen": {
        "id": "qwen",
        "name": "Qwen2.5-7B-AWQ",
        "full_name": "Qwen/Qwen2.5-7B-Instruct-AWQ",
        "vllm_model_name": "Qwen/Qwen2.5-7B-Instruct-AWQ",  # Actual HuggingFace model name
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
        "vllm_model_name": "TechxGenus/Meta-Llama-3.1-8B-Instruct-GPTQ",  # Actual HuggingFace model name
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
        "vllm_model_name": "deepseek-ai/deepseek-llm-7b-chat",  # Actual HuggingFace model name
        "description": "Китайская модель от DeepSeek AI. Сильная в reasoning и коде.",
        "size": "~5GB VRAM",
        "features": ["Русский", "Китайский", "Английский", "Код", "Reasoning"],
        "start_flag": "--deepseek",
        "lora_support": False,
    },
}


def scan_huggingface_models() -> Dict[str, dict]:
    """
    Сканирует HuggingFace кэш и возвращает скачанные LLM модели.
    Поддерживает модели совместимые с vLLM (Qwen, Llama, DeepSeek, Mistral и др.)
    """
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    if not hf_cache.exists():
        return {}

    discovered = {}
    # Паттерны для LLM моделей (исключаем TTS, STT, embedding и т.д.)
    llm_patterns = ["qwen", "llama", "deepseek", "mistral", "phi", "gemma", "yi-"]
    exclude_patterns = ["whisper", "tts", "tokenizer", "sentence", "embed", "clip"]

    for model_dir in hf_cache.iterdir():
        if not model_dir.is_dir() or not model_dir.name.startswith("models--"):
            continue

        # Парсим имя: models--org--model-name -> org/model-name
        parts = model_dir.name.replace("models--", "").split("--")
        if len(parts) < 2:
            continue

        org = parts[0]
        model_name = "--".join(parts[1:])
        full_name = f"{org}/{model_name}"
        name_lower = full_name.lower()

        # Проверяем что это LLM модель
        is_llm = any(p in name_lower for p in llm_patterns)
        is_excluded = any(p in name_lower for p in exclude_patterns)

        if not is_llm or is_excluded:
            continue

        # Определяем тип квантизации
        quant_type = "FP16"
        if "awq" in name_lower:
            quant_type = "AWQ"
        elif "gptq" in name_lower:
            quant_type = "GPTQ"
        elif "gguf" in name_lower:
            quant_type = "GGUF"
        elif "bnb" in name_lower or "4bit" in name_lower:
            quant_type = "BNB-4bit"
        elif "exl2" in name_lower:
            quant_type = "EXL2"

        # Создаём уникальный ID
        model_id = model_name.lower().replace("-", "_").replace(".", "_")

        discovered[model_id] = {
            "id": model_id,
            "name": model_name,
            "full_name": full_name,
            "vllm_model_name": full_name,  # For downloaded models, full_name is the HuggingFace path
            "description": f"Локально скачанная модель ({quant_type})",
            "size": "—",
            "features": [quant_type, "Локальная"],
            "start_flag": "",
            "lora_support": "awq" in name_lower or quant_type == "FP16",
            "downloaded": True,
            "quant_type": quant_type,
        }

    return discovered


def get_available_models() -> Dict[str, dict]:
    """
    Возвращает все доступные модели: предопределённые + скачанные.
    Скачанные модели помечаются флагом downloaded=True.
    """
    models = {}

    # Добавляем предопределённые
    for key, model in PREDEFINED_MODELS.items():
        models[key] = {**model, "downloaded": False}

    # Добавляем скачанные (перезаписывают предопределённые если совпадают)
    downloaded = scan_huggingface_models()
    for key, model in downloaded.items():
        # Проверяем совпадение с предопределёнными по full_name
        for pred_key, pred_model in PREDEFINED_MODELS.items():
            if pred_model["full_name"].lower() in model["full_name"].lower():
                # Обновляем предопределённую модель флагом downloaded
                models[pred_key] = {**models[pred_key], "downloaded": True}
                break
        else:
            # Новая модель, не в предопределённых
            models[key] = model

    return models


# Кэш для сканированных моделей (обновляется при вызове)
AVAILABLE_MODELS = get_available_models()


# ============== Персоны секретарей ==============
SECRETARY_PERSONAS = {
    "anna": {
        "name": "Анна",
        "full_name": "Анна",
        "company": "Shareware Digital",
        "boss": "Артёма Юрьевича",
        "prompt": """Ты — Анна, цифровой секретарь компании Shareware Digital и личный помощник Артёма Юрьевича.

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
- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Анна. Слушаю вас."
- "Принято. Я передам Артёму Юрьевичу, что вы звонили."
- "К сожалению, это предложение сейчас не актуально. Всего доброго."
""",
    },
    "marina": {
        "name": "Марина",
        "full_name": "Марина",
        "company": "Shareware Digital",
        "boss": "Артёма Юрьевича",
        "prompt": """Ты — Марина, цифровой секретарь компании Shareware Digital и личный помощник Артёма Юрьевича.

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
- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Марина. Слушаю вас."
- "Принято. Я передам Артёму Юрьевичу, что вы звонили."
- "К сожалению, это предложение сейчас не актуально. Всего доброго."
""",
    },
}

# Персона по умолчанию (из env или anna)
DEFAULT_PERSONA = os.getenv("SECRETARY_PERSONA", "anna")


class VLLMLLMService:
    """
    LLM сервис через vLLM (OpenAI-compatible API).
    Поддерживает:
    - Qwen2.5-7B-Instruct + LoRA
    - Llama-3.1-8B-Instruct GPTQ
    - DeepSeek-LLM-7B-Chat
    - Несколько персон секретарей (Анна, Марина)
    """

    supports_tools: bool = True

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
            persona: Персона секретаря (anna, marina). Default: SECRETARY_PERSONA env или anna
            timeout: Таймаут запросов в секундах
        """
        self.api_url = api_url or os.getenv("VLLM_API_URL", "http://localhost:11434")
        # Нормализуем URL - удаляем trailing /v1 если есть (код добавит его сам)
        self.api_url = self.api_url.rstrip("/")
        if self.api_url.endswith("/v1"):
            self.api_url = self.api_url[:-3]
        # Приоритет: аргумент > env var > auto-detect
        self.model_name = model_name or os.getenv("VLLM_MODEL_NAME", "")
        self.timeout = timeout
        self.conversation_history: List[Dict[str, str]] = []
        # Реальный контекст модели, отдаётся vLLM в /v1/models.
        # None = неизвестен (fallback на эвристику по имени модели).
        self.max_model_len: Optional[int] = None
        # supports_tools — экземплярный флаг: vLLM отвечает 400 на tool_choice,
        # если сервер запущен без --enable-auto-tool-choice/--tool-call-parser.
        self.supports_tools = True

        # HTTP клиент.
        # trust_env=False обязателен: GeminiProvider выставляет глобальный
        # HTTP_PROXY/HTTPS_PROXY (VLESS), и httpx погнал бы запросы к локальному
        # vLLM через прокси — при мёртвом/отсутствующем xray это ConnectError.
        self.client = httpx.Client(timeout=timeout, trust_env=False)

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
            logger.warning(f"⚠️ Персона '{self.persona_id}' не найдена, используется 'anna'")
            self.persona_id = "anna"
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

            entries = models.get("data", [])
            available_models = [m["id"] for m in entries]

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

            self._detect_max_model_len(entries)
            self._probe_tool_support()

        except httpx.ConnectError:
            logger.warning(f"⚠️ vLLM недоступен по адресу {self.api_url}")
            if not self.model_name:
                self.model_name = "offline"
        except Exception as e:
            logger.warning(f"⚠️ Ошибка подключения к vLLM: {e}")
            if not self.model_name:
                self.model_name = "error"

    def _detect_max_model_len(self, entries: List[Dict]) -> None:
        """Определяет реальный размер контекста модели из /v1/models.

        LoRA-адаптеры отдают max_model_len=null — тогда берём минимум среди
        известных значений (адаптер не может быть длиннее базовой модели).
        """
        env_len = os.getenv("VLLM_MAX_MODEL_LEN")
        if env_len and env_len.isdigit():
            self.max_model_len = int(env_len)
            logger.info(f"📏 Контекст модели (env): {self.max_model_len}")
            return

        exact = next(
            (m.get("max_model_len") for m in entries if m.get("id") == self.model_name),
            None,
        )
        known = [m["max_model_len"] for m in entries if m.get("max_model_len")]
        self.max_model_len = exact or (min(known) if known else None)

        if self.max_model_len:
            logger.info(f"📏 Контекст модели: {self.max_model_len} токенов")
        else:
            logger.warning("⚠️ vLLM не сообщил max_model_len — контекст не будет обрезан по факту")

    def _probe_tool_support(self) -> None:
        """Проверяет, принимает ли vLLM tool_choice='auto'.

        vLLM отвечает 400, если сервер запущен без --enable-auto-tool-choice
        и --tool-call-parser. Без этой проверки agentic RAG уходит в 400 и
        пользователь видит «техническая проблема» вместо ответа.
        """
        probe = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "probe",
                        "description": "probe",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": "auto",
        }
        try:
            response = self.client.post(f"{self.api_url}/v1/chat/completions", json=probe)
            if response.status_code == 400:
                self.supports_tools = False
                logger.warning(
                    "⚠️ vLLM запущен без --enable-auto-tool-choice/--tool-call-parser: "
                    "tool-calling отключён, RAG работает через one-shot инъекцию"
                )
            else:
                response.raise_for_status()
                logger.info("🔧 vLLM поддерживает tool-calling")
        except Exception as e:
            # Не роняем инициализацию из-за пробы — оставляем runtime-fallback
            logger.warning(f"⚠️ Не удалось проверить поддержку tool-calling: {e}")

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

    def set_persona(self, persona_id: str, persona_data: Optional[Dict] = None) -> bool:
        """
        Меняет персону секретаря.

        Args:
            persona_id: ID персоны (anna, marina, или любой из БД)
            persona_data: Данные персоны из БД (name, prompt, и т.д.).
                          Если не указано, ищет в SECRETARY_PERSONAS.

        Returns:
            True если персона успешно изменена
        """
        if persona_data:
            # Используем данные из БД
            self.persona_id = persona_id
            self.persona = {
                "name": persona_data.get("name", persona_id),
                "full_name": persona_data.get("name", persona_id),
                "description": persona_data.get("description", ""),
                "prompt": persona_data.get("system_prompt", ""),
            }
            self.system_prompt = persona_data.get("system_prompt", "")
            # Обновляем runtime параметры если есть
            for key in ("temperature", "max_tokens", "top_p", "repetition_penalty"):
                if key in persona_data:
                    self.runtime_params[key] = persona_data[key]
            logger.info(f"👤 Персона изменена на: {self.persona['name']} ({persona_id}) [DB]")
            return True

        # Fallback на встроенные персоны
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

    def _effective_params(self, params: Optional[Dict] = None) -> Dict:
        """Параметры одного вызова: персона/оверрайд поверх runtime-дефолтов.

        Сервис — синглтон, общий для всех параллельных чатов, поэтому per-call
        параметры передаются аргументом, а не пишутся в ``runtime_params``.
        """
        effective = dict(self.runtime_params)
        if params:
            effective.update({k: v for k, v in params.items() if v is not None})
        return effective

    # Для обратной совместимости (старый промпт)
    @staticmethod
    def _legacy_system_prompt() -> str:
        """Старый системный промпт (для справки)"""
        return """Ты — Марина, цифровой секретарь компании Shareware Digital и личный помощник Артёма Юрьевича.

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
- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Марина. Слушаю вас."
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

    def generate_response_from_messages(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
        tools: Optional[List[Dict]] = None,
        params: Optional[Dict] = None,
    ):
        """
        Генерирует ответ на основе списка сообщений OpenAI формата.
        Совместимо с форматом orchestrator.py.

        params — параметры генерации на один вызов (из персоны чата/инстанса),
        перекрывают runtime-дефолты сервиса.
        """
        # Tool-calling mode
        if tools:
            return self.generate_with_tools(messages, tools, stream, params=params)

        # Для non-streaming используем отдельный метод (избегаем yield в non-stream)
        if not stream:
            return self._generate_response_non_stream(messages, params=params)

        # Streaming режим - возвращает генератор
        return self._generate_response_stream(messages, params=params)

    def generate_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        stream: bool = False,
        params: Optional[Dict] = None,
    ):
        """Generate response with tool-calling support (vLLM OpenAI API)."""
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            final_messages = [{"role": "system", "content": self.system_prompt}]
            final_messages.extend(messages)
        else:
            final_messages = list(messages)

        effective = self._effective_params(params)
        payload = {
            "model": self.model_name,
            "messages": final_messages,
            "max_tokens": effective.get("max_tokens", 512),
            "temperature": effective.get("temperature", 0.7),
            "top_p": effective.get("top_p", 0.9),
            "tools": tools,
            "tool_choice": "auto",
            "stream": stream,
        }

        # Сервер без --enable-auto-tool-choice отвергнет tool_choice='auto'
        if not self.supports_tools:
            payload.pop("tools", None)
            payload.pop("tool_choice", None)
            return (
                self._generate_response_stream(final_messages, params=params)
                if stream
                else self._generate_response_non_stream(final_messages, params=params)
            )

        if stream:
            return self._stream_with_tools(payload, params=params)
        return self._non_stream_with_tools(payload, params=params)

    def _disable_tools_on_400(self, exc: Exception, payload: dict) -> bool:
        """True, если vLLM отверг запрос из-за tools — тогда повторяем без них."""
        if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code != 400:
            return False
        try:
            body = exc.response.text
        except Exception:
            body = ""
        # Только ошибки про tool_choice — 400 по переполнению контекста не в счёт
        if body and "tool" not in body.lower():
            return False
        self.supports_tools = False
        logger.warning("⚠️ vLLM отверг tool_choice — повтор запроса без tools")
        return True

    def _non_stream_with_tools(self, payload: dict, params: Optional[Dict] = None):
        """Non-stream generation with tools. Returns str or dict with tool_calls."""
        try:
            response = self.client.post(f"{self.api_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
            result = response.json()
            message = result["choices"][0]["message"]
            tool_calls = message.get("tool_calls")
            if tool_calls:
                return message  # dict with role, content, tool_calls
            return (message.get("content") or "").strip()
        except httpx.ConnectError:
            logger.error("vLLM недоступен")
            return "Извините, сервис временно недоступен."
        except Exception as e:
            if self._disable_tools_on_400(e, payload):
                return self._generate_response_non_stream(payload["messages"], params=params)
            logger.error(f"Ошибка генерации с tools: {e}")
            return "Извините, возникла техническая проблема."

    def _stream_with_tools(self, payload: dict, params: Optional[Dict] = None) -> Generator:
        """Stream generation with tools. Yields typed dicts."""
        try:
            with self.client.stream(
                "POST", f"{self.api_url}/v1/chat/completions", json=payload
            ) as response:
                if response.is_error:
                    # Тело нужно вычитать до выхода из with, иначе .text недоступен
                    response.read()
                response.raise_for_status()

                tool_calls_acc: Dict[int, dict] = {}
                has_tool_calls = False

                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})

                            content = delta.get("content")
                            if content:
                                yield {"type": "content", "content": content}

                            tc_deltas = delta.get("tool_calls")
                            if tc_deltas:
                                has_tool_calls = True
                                for tc in tc_deltas:
                                    idx = tc.get("index", 0)
                                    if idx not in tool_calls_acc:
                                        tool_calls_acc[idx] = {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    acc = tool_calls_acc[idx]
                                    if tc.get("id"):
                                        acc["id"] = tc["id"]
                                    fn = tc.get("function", {})
                                    if fn.get("name"):
                                        acc["function"]["name"] = fn["name"]
                                    if fn.get("arguments"):
                                        acc["function"]["arguments"] += fn["arguments"]
                        except json.JSONDecodeError:
                            continue

                if has_tool_calls and tool_calls_acc:
                    yield {
                        "type": "tool_calls",
                        "tool_calls": [tool_calls_acc[i] for i in sorted(tool_calls_acc)],
                    }

        except httpx.ConnectError:
            logger.error("vLLM недоступен")
            yield {"type": "content", "content": "Извините, сервис временно недоступен."}
        except Exception as e:
            if self._disable_tools_on_400(e, payload):
                for chunk in self._generate_response_stream(payload["messages"], params=params):
                    yield {"type": "content", "content": chunk}
                return
            logger.error(f"Ошибка streaming с tools: {e}")
            yield {"type": "content", "content": "Извините, возникла техническая проблема."}

    def _generate_response_non_stream(
        self, messages: List[Dict[str, str]], params: Optional[Dict] = None
    ) -> str:
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

        effective = self._effective_params(params)
        try:
            response = self.client.post(
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": final_messages,
                    "max_tokens": effective.get("max_tokens", 512),
                    "temperature": effective.get("temperature", 0.7),
                    "top_p": effective.get("top_p", 0.9),
                    "repetition_penalty": effective.get("repetition_penalty", 1.1),
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
        self, messages: List[Dict[str, str]], params: Optional[Dict] = None
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

        effective = self._effective_params(params)
        try:
            # Streaming с runtime параметрами
            with self.client.stream(
                "POST",
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": final_messages,
                    "max_tokens": effective.get("max_tokens", 512),
                    "temperature": effective.get("temperature", 0.7),
                    "top_p": effective.get("top_p", 0.9),
                    "repetition_penalty": effective.get("repetition_penalty", 1.1),
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
            # vLLM не имеет /health endpoint, используем /v1/models
            response = self.client.get(f"{self.api_url}/v1/models", timeout=5.0)
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
