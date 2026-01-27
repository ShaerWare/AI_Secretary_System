#!/usr/bin/env python3
"""
Сервис клонирования голоса на базе XTTS v2 (coqui-tts fork 2026)
С расширенными настройками интонации и естественности речи
GPU-ускорение на RTX 3060
"""

import hashlib
import logging
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import soundfile as sf
import torch
from TTS.api import TTS


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_optimal_gpu() -> tuple[str, Optional[int]]:
    """
    Определяет оптимальный GPU для использования.
    Возвращает (device_string, gpu_index)

    Приоритет:
    1. RTX 3060 или другая карта с compute capability >= 7.0
    2. CPU как fallback
    """
    if not torch.cuda.is_available():
        logger.warning("⚠️ CUDA недоступна, используется CPU")
        return "cpu", None

    best_gpu = None
    best_memory = 0

    for i in range(torch.cuda.device_count()):
        try:
            capability = torch.cuda.get_device_capability(i)
            name = torch.cuda.get_device_name(i)
            memory = torch.cuda.get_device_properties(i).total_memory

            # Минимум compute capability 7.0 для PyTorch 2.9+
            if capability[0] >= 7:
                if memory > best_memory:
                    best_memory = memory
                    best_gpu = i
                    logger.info(
                        f"✅ Найден совместимый GPU {i}: {name} "
                        f"(CC {capability[0]}.{capability[1]}, "
                        f"{memory // (1024**3)} GB)"
                    )
            else:
                logger.warning(
                    f"⚠️ GPU {i}: {name} не поддерживается "
                    f"(CC {capability[0]}.{capability[1]} < 7.0)"
                )
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки GPU {i}: {e}")

    if best_gpu is not None:
        return f"cuda:{best_gpu}", best_gpu

    logger.warning("⚠️ Нет совместимых GPU, используется CPU")
    return "cpu", None


# ============== Словарь замены Е → Ё ==============
# Частые слова где обязательно нужна Ё для правильного произношения
YO_REPLACEMENTS = {
    # Местоимения и частицы
    "ее": "её",
    "все": "всё",
    "еще": "ещё",
    "че": "чё",
    # Глаголы
    "идет": "идёт",
    "берет": "берёт",
    "несет": "несёт",
    "везет": "везёт",
    "ведет": "ведёт",
    "дает": "даёт",
    "передает": "передаёт",
    "узнает": "узнаёт",
    "признает": "признаёт",
    "подает": "подаёт",
    "зовет": "зовёт",
    "живет": "живёт",
    "плывет": "плывёт",
    "растет": "растёт",
    "цветет": "цветёт",
    "течет": "течёт",
    "печет": "печёт",
    "сечет": "сечёт",
    "жжет": "жжёт",
    "льет": "льёт",
    "пьет": "пьёт",
    "бьет": "бьёт",
    "шьет": "шьёт",
    "поет": "поёт",
    "жует": "жуёт",
    "клюет": "клюёт",
    "начнет": "начнёт",
    "поймет": "поймёт",
    "возьмет": "возьмёт",
    "придет": "придёт",
    "уйдет": "уйдёт",
    "найдет": "найдёт",
    "пойдет": "пойдёт",
    "зайдет": "зайдёт",
    "выйдет": "выйдет",
    "пришел": "пришёл",
    "ушел": "ушёл",
    "нашел": "нашёл",
    "пошел": "пошёл",
    "зашел": "зашёл",
    "вышел": "вышел",
    "привел": "привёл",
    "увел": "увёл",
    "провел": "провёл",
    # Существительные
    "елка": "ёлка",
    "елки": "ёлки",
    "елку": "ёлку",
    "мед": "мёд",
    "лед": "лёд",
    "лен": "лён",
    "клен": "клён",
    "черт": "чёрт",
    # Прилагательные
    "черный": "чёрный",
    "черная": "чёрная",
    "черное": "чёрное",
    "желтый": "жёлтый",
    "желтая": "жёлтая",
    "желтое": "жёлтое",
    "теплый": "тёплый",
    "теплая": "тёплая",
    "теплое": "тёплое",
    "твердый": "твёрдый",
    "твердая": "твёрдая",
    "твердое": "твёрдое",
    # Наречия
    "вперед": "вперёд",
    "назад": "назад",
    # Числительные
    "три": "три",
    "четыре": "четыре",
    # Частые фразы секретаря
    "перезвоните": "перезвоните",
    "подождете": "подождёте",
    "соединю": "соединю",
    "переключу": "переключу",
}


@dataclass
class IntonationPreset:
    """Пресет настроек интонации"""

    name: str
    temperature: float  # 0.1-1.0: выше = экспрессивнее
    repetition_penalty: float  # 1.0-10.0: выше = меньше повторов
    top_k: int  # 1-100: ниже = предсказуемее
    top_p: float  # 0.1-1.0: ниже = стабильнее
    speed: float  # 0.5-2.0: скорость речи
    gpt_cond_len: int  # 6-30: длина кондиционирования (сек)
    gpt_cond_chunk_len: int  # 3-6: размер чанков (сек)


# ============== Пресеты интонаций ==============
INTONATION_PRESETS = {
    # Нейтральный деловой тон
    "neutral": IntonationPreset(
        name="Нейтральный",
        temperature=0.7,
        repetition_penalty=5.0,
        top_k=50,
        top_p=0.85,
        speed=1.0,
        gpt_cond_len=12,
        gpt_cond_chunk_len=4,
    ),
    # Тёплый дружелюбный тон
    "warm": IntonationPreset(
        name="Тёплый",
        temperature=0.85,
        repetition_penalty=3.0,
        top_k=60,
        top_p=0.9,
        speed=0.95,
        gpt_cond_len=15,
        gpt_cond_chunk_len=5,
    ),
    # Энергичный тон
    "energetic": IntonationPreset(
        name="Энергичный",
        temperature=0.9,
        repetition_penalty=2.5,
        top_k=70,
        top_p=0.92,
        speed=1.1,
        gpt_cond_len=10,
        gpt_cond_chunk_len=3,
    ),
    # Спокойный профессиональный
    "calm": IntonationPreset(
        name="Спокойный",
        temperature=0.5,
        repetition_penalty=6.0,
        top_k=40,
        top_p=0.8,
        speed=0.9,
        gpt_cond_len=18,
        gpt_cond_chunk_len=6,
    ),
    # Максимально естественный (рекомендуется)
    "natural": IntonationPreset(
        name="Естественный",
        temperature=0.75,
        repetition_penalty=4.0,
        top_k=55,
        top_p=0.88,
        speed=0.98,
        gpt_cond_len=20,
        gpt_cond_chunk_len=5,
    ),
}


class TextPreprocessor:
    """Препроцессор текста для улучшения интонации"""

    def __init__(self):
        # Компилируем регулярки для скорости
        self._yo_pattern = re.compile(
            r"\b(" + "|".join(re.escape(k) for k in YO_REPLACEMENTS) + r")\b", re.IGNORECASE
        )

    def replace_yo(self, text: str) -> str:
        """Заменяет Е на Ё в известных словах"""

        def replacer(match):
            word = match.group(0)
            lower = word.lower()
            if lower in YO_REPLACEMENTS:
                replacement = YO_REPLACEMENTS[lower]
                # Сохраняем регистр первой буквы
                if word[0].isupper():
                    return replacement[0].upper() + replacement[1:]
                return replacement
            return word

        return self._yo_pattern.sub(replacer, text)

    def add_pauses(self, text: str) -> str:
        """Добавляет паузы для естественности"""
        # Заменяем двойные пробелы на паузу (многоточие)
        text = re.sub(r"  +", "... ", text)

        # Добавляем микропаузы после вводных слов
        introductory = [
            "здравствуйте",
            "добрый день",
            "добрый вечер",
            "доброе утро",
            "да",
            "нет",
            "конечно",
            "разумеется",
            "безусловно",
            "к сожалению",
            "к счастью",
            "впрочем",
            "однако",
            "пожалуйста",
            "спасибо",
            "извините",
        ]
        for word in introductory:
            # После вводного слова добавляем запятую если её нет
            pattern = rf"\b({word})\b(?![,\.\!\?])"
            text = re.sub(pattern, r"\1,", text, flags=re.IGNORECASE)

        return text

    def normalize_punctuation(self, text: str) -> str:
        """Нормализует пунктуацию для лучшей интонации"""
        # Убираем множественные знаки препинания
        text = re.sub(r"\.{4,}", "...", text)
        text = re.sub(r"\!{2,}", "!", text)
        text = re.sub(r"\?{2,}", "?", text)

        # Добавляем пробел после знаков если его нет
        text = re.sub(r"([,\.\!\?])([А-Яа-яA-Za-z])", r"\1 \2", text)

        # Убираем пробелы перед знаками препинания
        text = re.sub(r"\s+([,\.\!\?])", r"\1", text)

        return text

    def process(self, text: str) -> str:
        """Полная обработка текста"""
        text = self.normalize_punctuation(text)
        text = self.replace_yo(text)
        text = self.add_pauses(text)
        return text.strip()


class VoiceCloneService:
    """
    Сервис клонирования голоса с расширенными настройками

    Особенности:
    - GPU-ускорение на RTX 3060 (или совместимых картах)
    - Использует ВСЕ образцы голоса для лучшего качества
    - Кэширование speaker latents для быстрого повторного синтеза
    - Поддерживает пресеты интонаций
    - Автоматическая замена Е→Ё
    - Тонкая настройка параметров синтеза
    """

    def __init__(
        self,
        voice_samples_dir: str = "./Лидия",
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        default_preset: str = "natural",
        max_samples: Optional[int] = None,  # None = использовать все
        force_cpu: bool = False,  # Принудительно использовать CPU
        cache_dir: str = "./cache",  # Папка для кэша latents
    ):
        self.voice_samples_dir = Path(voice_samples_dir)
        self.model_name = model_name
        self.default_preset = default_preset
        self.max_samples = max_samples
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # Определяем оптимальный GPU
        if force_cpu:
            self.device = "cpu"
            self.gpu_index = None
            logger.info("⚙️ Принудительный режим CPU")
        else:
            self.device, self.gpu_index = get_optimal_gpu()

        # Препроцессор текста
        self.preprocessor = TextPreprocessor()

        logger.info("🎤 Инициализация VoiceCloneService")
        logger.info(f"🖥️ Устройство: {self.device}")
        logger.info(f"📁 Папка образцов: {self.voice_samples_dir}")
        logger.info(f"🎭 Пресет по умолчанию: {default_preset}")

        # Устанавливаем CUDA устройство по умолчанию
        if self.gpu_index is not None:
            torch.cuda.set_device(self.gpu_index)
            # Оптимизации CUDA
            torch.backends.cudnn.benchmark = True
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            logger.info("⚡ CUDA оптимизации включены (TF32, cuDNN benchmark)")

        try:
            self.tts = TTS(
                model_name=self.model_name, gpu=(self.device.startswith("cuda")), progress_bar=True
            )

            # Перемещаем модель на нужный GPU
            if self.device.startswith("cuda") and hasattr(self.tts, "synthesizer"):
                if hasattr(self.tts.synthesizer, "tts_model"):
                    self.tts.synthesizer.tts_model = self.tts.synthesizer.tts_model.to(self.device)
                    logger.info(f"✅ Модель перемещена на {self.device}")

            logger.info("✅ XTTS v2 загружена успешно")

            # Показываем информацию о памяти GPU
            if self.gpu_index is not None:
                allocated = torch.cuda.memory_allocated(self.gpu_index) / (1024**3)
                reserved = torch.cuda.memory_reserved(self.gpu_index) / (1024**3)
                logger.info(
                    f"📊 GPU память: {allocated:.1f} GB allocated, {reserved:.1f} GB reserved"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели: {e}")
            raise

        # Пользовательские пресеты (загружаются через reload_presets из БД)
        self.custom_presets: dict = {}

        # Загружаем ВСЕ образцы голоса
        self.voice_samples = self._get_voice_samples()
        if not self.voice_samples:
            logger.warning("⚠️ Образцы голоса не найдены!")
        else:
            logger.info(f"📊 Загружено образцов: {len(self.voice_samples)}")
            for i, sample in enumerate(self.voice_samples[:5]):
                logger.info(f"   {i + 1}. {sample.name}")
            if len(self.voice_samples) > 5:
                logger.info(f"   ... и ещё {len(self.voice_samples) - 5}")

        # Кэшируем speaker latents при инициализации
        self._cached_latents = None
        self._latents_cache_hash = None
        self._precompute_latents()

    def reload_presets(self, presets_dict: dict = None):
        """
        Перезагружает пользовательские пресеты (hot reload).

        Args:
            presets_dict: Словарь пресетов из БД {name: params}.
                         Если не передан, пресеты очищаются.
        """
        if presets_dict:
            self.custom_presets = presets_dict.copy()
        else:
            self.custom_presets = {}
        logger.info(f"🔄 Пресеты перезагружены: {len(self.custom_presets)} записей")

    def save_custom_preset(self, name: str, params: dict):
        """
        Сохраняет пользовательский пресет в память.
        Сохранение в БД выполняется через orchestrator.

        Args:
            name: Имя пресета
            params: Параметры пресета (temperature, speed, top_k, top_p, etc.)
        """
        self.custom_presets[name] = params
        logger.info(f"💾 Пресет '{name}' сохранён в память")

    def delete_custom_preset(self, name: str):
        """
        Удаляет пользовательский пресет из памяти.
        Удаление из БД выполняется через orchestrator.
        """
        if name in self.custom_presets:
            del self.custom_presets[name]
            logger.info(f"🗑️ Пресет '{name}' удалён из памяти")

    def get_all_presets(self) -> dict:
        """Возвращает все пресеты (встроенные + пользовательские)"""
        all_presets = {}
        # Встроенные
        for name, preset in INTONATION_PRESETS.items():
            all_presets[name] = {
                "name": preset.name,
                "temperature": preset.temperature,
                "repetition_penalty": preset.repetition_penalty,
                "top_k": preset.top_k,
                "top_p": preset.top_p,
                "speed": preset.speed,
                "gpt_cond_len": preset.gpt_cond_len,
                "gpt_cond_chunk_len": preset.gpt_cond_chunk_len,
                "builtin": True,
            }
        # Пользовательские
        for name, params in self.custom_presets.items():
            all_presets[name] = {**params, "builtin": False}
        return all_presets

    def _get_voice_samples(self) -> list[Path]:
        """Получает ВСЕ образцы голоса из папки"""
        if not self.voice_samples_dir.exists():
            logger.error(f"❌ Папка не найдена: {self.voice_samples_dir}")
            return []

        # Получаем все WAV файлы
        samples = sorted(self.voice_samples_dir.glob("*.wav"))

        # Ограничиваем если указано
        if self.max_samples:
            samples = samples[: self.max_samples]

        return samples

    def _get_samples_hash(self) -> str:
        """Вычисляет хэш списка образцов для кэширования"""
        content = "".join([f"{s.name}:{s.stat().st_mtime}" for s in self.voice_samples])
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _precompute_latents(self):
        """
        Предвычисляет и кэширует speaker latents для ускорения синтеза.
        Кэш сохраняется на диск и загружается при повторном запуске.
        """
        if not self.voice_samples:
            return

        samples_hash = self._get_samples_hash()
        cache_file = self.cache_dir / f"speaker_latents_{samples_hash}.pkl"

        # Проверяем кэш на диске
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    cached_data = pickle.load(f)
                    self._cached_latents = cached_data["latents"]
                    self._latents_cache_hash = samples_hash
                    logger.info("⚡ Speaker latents загружены из кэша")
                    return
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки кэша: {e}")

        # Вычисляем latents
        logger.info("🔄 Предвычисление speaker latents (это ускорит последующий синтез)...")

        try:
            # Получаем доступ к внутренней модели XTTS
            if hasattr(self.tts, "synthesizer") and hasattr(self.tts.synthesizer, "tts_model"):
                model = self.tts.synthesizer.tts_model
                speaker_wavs = [str(s) for s in self.voice_samples]

                # Вычисляем conditioning latents
                gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
                    audio_path=speaker_wavs,
                    gpt_cond_len=20,  # Используем больше для лучшего качества
                    gpt_cond_chunk_len=5,
                    max_ref_length=30,
                )

                self._cached_latents = {
                    "gpt_cond_latent": gpt_cond_latent,
                    "speaker_embedding": speaker_embedding,
                }
                self._latents_cache_hash = samples_hash

                # Сохраняем в кэш на диск
                with open(cache_file, "wb") as f:
                    pickle.dump(
                        {
                            "latents": self._cached_latents,
                            "samples_hash": samples_hash,
                        },
                        f,
                    )

                logger.info("✅ Speaker latents предвычислены и закэшированы")
                logger.info(f"💾 Кэш сохранён: {cache_file}")

                # Показываем размеры тензоров
                logger.info(f"📊 GPT latent shape: {gpt_cond_latent.shape}")
                logger.info(f"📊 Speaker embedding shape: {speaker_embedding.shape}")

            else:
                logger.warning("⚠️ Не удалось получить доступ к модели для предвычисления latents")

        except Exception as e:
            logger.warning(f"⚠️ Ошибка предвычисления latents: {e}")
            logger.info("   Синтез будет работать, но медленнее")

    def get_preset(self, preset_name: str) -> IntonationPreset:
        """Получает пресет по имени"""
        if preset_name not in INTONATION_PRESETS:
            logger.warning(f"⚠️ Пресет '{preset_name}' не найден, используется 'natural'")
            preset_name = "natural"
        return INTONATION_PRESETS[preset_name]

    def list_presets(self) -> dict[str, str]:
        """Возвращает список доступных пресетов"""
        return {name: preset.name for name, preset in INTONATION_PRESETS.items()}

    def synthesize(
        self,
        text: str,
        output_path: Optional[str] = None,
        language: str = "ru",
        preset: Optional[str] = None,
        # Индивидуальные настройки (переопределяют пресет)
        temperature: Optional[float] = None,
        repetition_penalty: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        speed: Optional[float] = None,
        gpt_cond_len: Optional[int] = None,
        gpt_cond_chunk_len: Optional[int] = None,
        # Управление обработкой
        preprocess_text: bool = True,
        split_sentences: bool = False,  # True requires spacy
    ) -> tuple[np.ndarray, int]:
        """
        Синтезирует речь с заданными параметрами

        Args:
            text: Текст для синтеза
            output_path: Путь для сохранения (опционально)
            language: Язык (ru, en, и т.д.)
            preset: Имя пресета интонации
            temperature: Температура (0.1-1.0), выше = экспрессивнее
            repetition_penalty: Штраф повторов (1.0-10.0)
            top_k: Top-K сэмплирование (1-100)
            top_p: Top-P (nucleus) сэмплирование (0.1-1.0)
            speed: Скорость речи (0.5-2.0)
            gpt_cond_len: Длина кондиционирования в секундах
            gpt_cond_chunk_len: Размер чанков кондиционирования
            preprocess_text: Применять препроцессинг (Ё, паузы)
            split_sentences: Разбивать на предложения

        Returns:
            tuple[np.ndarray, int]: (wav данные, sample_rate)
        """
        if not self.voice_samples:
            raise ValueError("Нет образцов голоса для клонирования")

        # Препроцессинг текста
        original_text = text
        if preprocess_text:
            text = self.preprocessor.process(text)
            if text != original_text:
                logger.info(f"📝 Текст после обработки: '{text[:80]}...'")

        logger.info(f"🎙️ Синтез: '{text[:50]}...'")

        # Получаем настройки из пресета
        p = self.get_preset(preset or self.default_preset)

        # Переопределяем индивидуальными настройками
        final_temperature = temperature if temperature is not None else p.temperature
        final_repetition_penalty = (
            repetition_penalty if repetition_penalty is not None else p.repetition_penalty
        )
        final_top_k = top_k if top_k is not None else p.top_k
        final_top_p = top_p if top_p is not None else p.top_p
        final_speed = speed if speed is not None else p.speed
        final_gpt_cond_len = gpt_cond_len if gpt_cond_len is not None else p.gpt_cond_len
        final_gpt_cond_chunk_len = (
            gpt_cond_chunk_len if gpt_cond_chunk_len is not None else p.gpt_cond_chunk_len
        )

        logger.info(
            f"⚙️ Параметры: temp={final_temperature}, rep_pen={final_repetition_penalty}, "
            f"top_k={final_top_k}, top_p={final_top_p}, speed={final_speed}"
        )

        try:
            import time

            start_time = time.time()

            # Используем кэшированные latents если доступны (быстрый путь)
            if self._cached_latents is not None and hasattr(self.tts, "synthesizer"):
                model = self.tts.synthesizer.tts_model
                logger.info("⚡ Используются кэшированные speaker latents (быстрый режим)")

                # Прямой вызов модели с предвычисленными latents
                wav = model.inference(
                    text=text,
                    language=language,
                    gpt_cond_latent=self._cached_latents["gpt_cond_latent"],
                    speaker_embedding=self._cached_latents["speaker_embedding"],
                    # Тонкие настройки
                    temperature=final_temperature,
                    repetition_penalty=final_repetition_penalty,
                    top_k=final_top_k,
                    top_p=final_top_p,
                    speed=final_speed,
                    enable_text_splitting=split_sentences,
                )

                # inference() возвращает dict с ключом 'wav'
                if isinstance(wav, dict):
                    wav = wav.get("wav", wav)

            else:
                # Fallback: стандартный путь через TTS API
                logger.info(
                    f"🎤 Используется {len(self.voice_samples)} образцов голоса (стандартный режим)"
                )
                speaker_wavs = [str(s) for s in self.voice_samples]

                wav = self.tts.tts(
                    text=text,
                    speaker_wav=speaker_wavs,
                    language=language,
                    split_sentences=split_sentences,
                    temperature=final_temperature,
                    repetition_penalty=final_repetition_penalty,
                    top_k=final_top_k,
                    top_p=final_top_p,
                    speed=final_speed,
                    gpt_cond_len=final_gpt_cond_len,
                    gpt_cond_chunk_len=final_gpt_cond_chunk_len,
                )

            if isinstance(wav, list):
                wav = np.array(wav, dtype=np.float32)

            # Конвертируем torch tensor в numpy если нужно
            if hasattr(wav, "cpu"):
                wav = wav.cpu().numpy()

            sample_rate = self.tts.synthesizer.output_sample_rate

            elapsed = time.time() - start_time
            audio_duration = len(wav) / sample_rate
            rtf = elapsed / audio_duration  # Real-Time Factor

            logger.info(f"⏱️ Синтез: {elapsed:.2f}s, аудио: {audio_duration:.2f}s, RTF: {rtf:.2f}x")

            if output_path:
                sf.write(output_path, wav, sample_rate)
                logger.info(f"💾 Сохранено: {output_path}")

            # Очищаем CUDA кэш после синтеза
            if self.gpu_index is not None:
                torch.cuda.empty_cache()

            return wav, sample_rate

        except Exception as e:
            logger.error(f"❌ Ошибка синтеза: {e}")
            raise

    def synthesize_to_file(
        self, text: str, output_path: str, language: str = "ru", **kwargs
    ) -> str:
        """Синтезирует и сохраняет в файл"""
        self.synthesize(text, output_path, language, **kwargs)
        return output_path

    def synthesize_with_emotion(
        self,
        text: str,
        emotion: Literal["neutral", "warm", "energetic", "calm", "natural"] = "natural",
        output_path: Optional[str] = None,
        language: str = "ru",
    ) -> tuple[np.ndarray, int]:
        """
        Упрощённый метод синтеза с выбором эмоции

        Args:
            text: Текст для синтеза
            emotion: Эмоция/стиль (neutral, warm, energetic, calm, natural)
            output_path: Путь для сохранения
            language: Язык
        """
        return self.synthesize(
            text=text, output_path=output_path, language=language, preset=emotion
        )


# ============== Тестирование ==============
if __name__ == "__main__":
    import time

    print("=" * 70)
    print("🎤 Тестирование VoiceCloneService с GPU-ускорением")
    print("=" * 70)

    # Проверяем GPU
    print("\n📊 Информация о GPU:")
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            name = torch.cuda.get_device_name(i)
            cap = torch.cuda.get_device_capability(i)
            mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
            print(f"   GPU {i}: {name} (CC {cap[0]}.{cap[1]}, {mem:.1f} GB)")
    else:
        print("   ⚠️ CUDA недоступна")

    print("\n🚀 Инициализация сервиса...")
    init_start = time.time()
    service = VoiceCloneService()
    init_time = time.time() - init_start
    print(f"⏱️ Инициализация заняла: {init_time:.1f}s")

    # Показываем доступные пресеты
    print("\n📋 Доступные пресеты интонаций:")
    for key, name in service.list_presets().items():
        print(f"   - {key}: {name}")

    # Тестовые фразы с разными интонациями
    test_cases = [
        {
            "text": "Здравствуйте! Shaerware Dijital.  Я - персональный секретарь Артёма Юрьевича... Чем могу помочь?",
            "preset": "warm",
            "output": "test_warm.wav",
        },
        {
            "text": "Здравствуйте! Shaerware Dijital.  Я - персональный секретарь Артёма Юрьевича... Чем могу помочь?",
            "preset": "calm",
            "output": "test_calm.wav",
        },
        {
            "text": "Здравствуйте! Shaerware Dijital.  Я - персональный секретарь Артёма Юрьевича... Чем могу помочь?",
            "preset": "energetic",
            "output": "test_energetic.wav",
        },
    ]

    print("\n🎙️ Генерация тестовых файлов...")
    print("-" * 70)

    total_synth_time = 0
    total_audio_duration = 0

    for i, case in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] Пресет: {case['preset']}")
        print(f"    Текст: {case['text'][:60]}...")

        synth_start = time.time()
        wav, sr = service.synthesize(
            text=case["text"], output_path=case["output"], preset=case["preset"]
        )
        synth_time = time.time() - synth_start
        audio_duration = len(wav) / sr

        total_synth_time += synth_time
        total_audio_duration += audio_duration

        print(f"    ✅ Сохранено: {case['output']}")

    print("\n" + "=" * 70)
    print("📊 РЕЗУЛЬТАТЫ БЕНЧМАРКА:")
    print(f"   Устройство: {service.device}")
    print(f"   Общее время синтеза: {total_synth_time:.2f}s")
    print(f"   Общая длительность аудио: {total_audio_duration:.2f}s")
    print(f"   Средний RTF: {total_synth_time / total_audio_duration:.2f}x")
    print("   (RTF < 1.0 = быстрее реального времени)")

    if service.gpu_index is not None:
        allocated = torch.cuda.memory_allocated(service.gpu_index) / (1024**3)
        peak = torch.cuda.max_memory_allocated(service.gpu_index) / (1024**3)
        print(f"   GPU память: {allocated:.2f} GB (пик: {peak:.2f} GB)")

    print("=" * 70)
    print("✅ Тестирование завершено!")
    print("🎧 Прослушайте файлы: test_warm.wav, test_calm.wav, test_energetic.wav")
    print("=" * 70)
