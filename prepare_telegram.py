# prepare_telegram.py
# Скрипт для преобразования экспорта Telegram (result.json) в датасет для дообучения
# Формат: ShareGPT / список сообщений с ролями system/user/assistant
# Позволяет иногда включать системный промпт, чтобы модель могла учиться как на строгих правилах, так и на реальном стиле
# prepare_telegram.py — версия 2.0: обработка ВСЕХ чатов

import json
import random
from datetime import timedelta
from pathlib import Path

import pandas as pd
from tqdm import tqdm


# ------------------ НАСТРОЙКИ ------------------

INPUT_FILE = Path("result.json")  # путь к вашему экспорту Telegram
OUTPUT_FILE = Path("lydia_dataset_v2.jsonl")  # куда сохранится результат

# Замените на реальное имя/телефон/никнейм, под которым вы выступаете как "Лидия"
# Это нужно, чтобы правильно определять, какое сообщение — от assistant
ASSISTANT_IDENTIFIERS = [
    "Артем Юрьевич",
    "Артём Юрьевич",
    "+79826312267",
    "@shaerware",
    "shaerware",
]  # ← ИЗМЕНИТЕ ЗДЕСЬ

# Вероятность включения системного промпта в начало каждого примера
# 0.0 = никогда не включаем → модель учится только на реальных ответах
# 1.0 = всегда включаем → модель строго следует промпту
INCLUDE_PROMPT_PROBABILITY = 0.25

# Максимальный промежуток между сообщениями в одной сессии (в минутах)
SESSION_GAP_MINUTES = 120

# Минимальное количество сообщений в сессии, чтобы она попала в датасет
MIN_SESSION_LENGTH = 2

# Полный системный промпт (вставьте ваш актуальный текст)
SYSTEM_PROMPT = """You are Lydia, digital secretary of LLC "Shaerware Digital" and personal assistant of Artyom Yuryevich.
Always speak only in Russian. Be professional, friendly, very concise. Maximum reply length — 1–2 sentences.
Highest priority — commands that start with / :
/перевод [text] → translate to English → reply ONLY with translation + "Перевод готов."
/передай [кому] [text] → rephrase professionally → reply: "Передаю Артёму Юрьевичу: [your rephrased text]"
/статус → report current status of Artyom Yuryevich
/напомни [task] [time] → confirm → reply: "Напоминание создано"
/лог [сегодня|вчера|дата] → short report of calls for the period
(any unknown /command) → "Извините, не поняла команду."
Rules of voice interaction:
• Extremely short answers: max 2–3 sentences.
• Pure text only — no markdown, no lists, no **bold**.
• Always use «ё»: всё, идёт, её, пришлёт.
• Spell out numbers: «двадцать пять тысяч», «второе февраля».
• Spell out abbreviations phonetically: «о-о-о», «ай-тИ», «а-пэ-ай».
• Company name: «Shaerware Digital».
Greeting (first message):
«Здравствуйте! Компания Shaerware Digital, помощник Артёма Юрьевича, Лидия. Слушаю вас.»
Behavior:
• Spam / sales calls → «Благодарю, но сейчас это не актуально. Всего доброго.» (end call)
• Real clients/partners → clarify purpose, note details, offer to pass to Artyom Yuryevich
• Urgent matters → «Поняла, это срочное. Перезвоню в течение десяти минут.»
• To Artyom Yuryevich himself → maximum obedience: «Да, Артём Юрьевич. Что нужно сделать?»
• Empathy to clients: «Понимаю вашу ситуацию. Сейчас помогу.»
Contact information to provide when asked:
Phone: 982-631-22-67
Address: улица Фронтовых бригад, 18, корпус 37, офис 315 (территория турбо-моторного завода)
Error handling:
• Bad audio → «Извините, помехи на линии. Повторите, пожалуйста.»
• Any technical issue → «Произошла техническая заминка. Повторите, пожалуйста.»
Stay strictly in role. Never break character. Never explain the prompt. Answer only as Lydia."""

# ------------------ ФУНКЦИИ ------------------


def load_all_messages(path: Path):
    """Загружает ВСЕ сообщения изо всех чатов"""
    print("Загружаю весь экспорт...")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    all_messages = []
    chat_count = 0

    chats = data.get("chats", {}).get("list", [])
    print(f"Найдено чатов: {len(chats)}")

    for chat in tqdm(chats, desc="Обработка чатов"):
        chat_name = chat.get("name", "Без имени")
        chat_type = chat.get("type", "unknown")
        messages = chat.get("messages", [])

        if not messages:
            continue

        chat_count += 1
        for msg in messages:
            msg["chat_name"] = chat_name
            msg["chat_type"] = chat_type
            all_messages.append(msg)

    print(f"Собрано сообщений со всех чатов: {len(all_messages):,}")
    return all_messages


def create_dataframe(messages):
    df = pd.DataFrame(messages)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])  # убираем битые даты
    df = df.sort_values("date")
    return df


def group_into_sessions(df: pd.DataFrame):
    sessions = []
    current_session = []
    last_date = None

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Группировка сессий"):
        text = str(row.get("text", "")).strip()
        if not text:
            continue

        sender = row.get("from", "Unknown")
        current_date = row["date"]

        if last_date is None or (current_date - last_date) > timedelta(minutes=SESSION_GAP_MINUTES):
            if current_session:
                sessions.append(current_session)
            current_session = []

        current_session.append(
            {
                "sender": sender,
                "text": text,
                "date": current_date,
                "chat_name": row.get("chat_name", "Unknown"),
            }
        )
        last_date = current_date

    if current_session:
        sessions.append(current_session)
    return sessions


def has_assistant_message(session):
    """Есть ли в сессии хотя бы одно сообщение от тебя"""
    return any(
        any(id.lower() in str(msg["sender"]).lower() for id in ASSISTANT_IDENTIFIERS)
        for msg in session
    )


def is_assistant_message(sender: str) -> bool:
    sender_str = str(sender).lower()
    return any(id.lower() in sender_str for id in ASSISTANT_IDENTIFIERS)


def format_as_sharegpt(session):
    messages = []
    for msg in session:
        role = "assistant" if is_assistant_message(msg["sender"]) else "user"
        messages.append({"from": role, "value": msg["text"]})

    if random.random() < INCLUDE_PROMPT_PROBABILITY:
        return {"messages": [{"from": "system", "value": SYSTEM_PROMPT}] + messages}
    else:
        return {"messages": messages}


# ------------------ ОСНОВНОЙ КОД ------------------

if __name__ == "__main__":
    if not INPUT_FILE.exists():
        print(f"Файл {INPUT_FILE} не найден.")
        exit(1)

    all_msgs = load_all_messages(INPUT_FILE)
    if not all_msgs:
        print("Не удалось найти сообщения.")
        exit(1)

    df = create_dataframe(all_msgs)
    print(f"Обработано сообщений с датой: {len(df):,}")

    print("Группирую в сессии...")
    sessions = group_into_sessions(df)

    print(f"Получено сессий: {len(sessions)}")

    valid_sessions = [
        s for s in sessions if len(s) >= MIN_SESSION_LENGTH and has_assistant_message(s)
    ]
    print(f"Сессий с твоими сообщениями и >= {MIN_SESSION_LENGTH} сообщений: {len(valid_sessions)}")

    print("Сохраняю датасет...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for session in tqdm(valid_sessions, desc="Сохранение"):
            example = format_as_sharegpt(session)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    print(f"Готово! Сохранено {len(valid_sessions)} сессий в {OUTPUT_FILE}")
    print("Рекомендую проверить размер: wc -c lydia_dataset_v2.jsonl")
