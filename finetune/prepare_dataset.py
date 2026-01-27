# prepare_dataset.py — подготовка датасета из экспорта Telegram
import json


INPUT_FILE = "datasets/result.json"
OUTPUT_FILE = "datasets/lydia_dataset_v3.jsonl"
OWNER_NAME = "Артем Юрьевич"

# Минимальная длина диалога (сообщений)
MIN_DIALOG_MESSAGES = 2
# Минимальная длина текста сообщения
MIN_MESSAGE_LENGTH = 1
# Максимальная длина одного сообщения (символов)
MAX_MESSAGE_LENGTH = 2000


def extract_text(text_field):
    """Извлекает чистый текст из поля text (может быть строкой или списком)."""
    if isinstance(text_field, str):
        return text_field.strip()

    if isinstance(text_field, list):
        parts = []
        for item in text_field:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # {'type': 'link', 'text': 'http://...'} → берём text
                parts.append(item.get("text", ""))
        return "".join(parts).strip()

    return ""


def is_valid_message(msg):
    """Проверяет, что сообщение текстовое и не пустое."""
    if msg.get("type") != "message":
        return False

    text = extract_text(msg.get("text", ""))
    if len(text) < MIN_MESSAGE_LENGTH:
        return False

    # Пропускаем сервисные сообщения
    if msg.get("media_type") in ["sticker", "animation", "voice_message", "video_message"]:
        if not text:  # Если есть подпись к медиа — оставляем
            return False

    return True


def process_chat(chat, owner_name):
    """Обрабатывает один чат, возвращает список диалогов."""
    messages = chat.get("messages", [])
    _chat_name = chat.get("name", "Unknown")

    # Фильтруем только текстовые сообщения
    valid_messages = [m for m in messages if is_valid_message(m)]

    if len(valid_messages) < MIN_DIALOG_MESSAGES:
        return []

    dialogs = []
    current_dialog = []
    prev_role = None

    for msg in valid_messages:
        sender = msg.get("from", "")
        text = extract_text(msg.get("text", ""))

        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH] + "..."

        # Определяем роль
        if sender == owner_name:
            role = "assistant"
        else:
            role = "user"

        # Склеиваем последовательные сообщения от одного отправителя
        if role == prev_role and current_dialog:
            # Добавляем к предыдущему сообщению
            current_dialog[-1]["value"] += "\n" + text
        else:
            current_dialog.append({"from": role, "value": text})

        prev_role = role

    # Разбиваем на отдельные диалоги (по паузам или по размеру)
    # Пока делаем простой вариант: весь чат = один диалог
    # Но разобьём если слишком длинный (> 20 сообщений)

    MAX_DIALOG_LENGTH = 20

    for i in range(0, len(current_dialog), MAX_DIALOG_LENGTH):
        chunk = current_dialog[i : i + MAX_DIALOG_LENGTH]

        # Диалог должен начинаться с user
        while chunk and chunk[0]["from"] == "assistant":
            chunk = chunk[1:]

        # И заканчиваться на assistant
        while chunk and chunk[-1]["from"] == "user":
            chunk = chunk[:-1]

        if len(chunk) >= MIN_DIALOG_MESSAGES:
            # Проверяем что есть хотя бы один user и один assistant
            has_user = any(m["from"] == "user" for m in chunk)
            has_assistant = any(m["from"] == "assistant" for m in chunk)

            if has_user and has_assistant:
                dialogs.append({"messages": chunk})

    return dialogs


def main():
    print(f"Загрузка {INPUT_FILE}...")
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    chat_list = data.get("chats", {}).get("list", [])
    print(f"Найдено чатов: {len(chat_list)}")

    all_dialogs = []
    stats = {
        "total_chats": len(chat_list),
        "processed_chats": 0,
        "skipped_chats": 0,
        "total_dialogs": 0,
        "total_messages": 0,
    }

    for chat in chat_list:
        chat_type = chat.get("type", "")

        # Пропускаем saved_messages и группы
        if chat_type not in ["personal_chat"]:
            stats["skipped_chats"] += 1
            continue

        dialogs = process_chat(chat, OWNER_NAME)

        if dialogs:
            stats["processed_chats"] += 1
            stats["total_dialogs"] += len(dialogs)
            for d in dialogs:
                stats["total_messages"] += len(d["messages"])
            all_dialogs.extend(dialogs)
        else:
            stats["skipped_chats"] += 1

    # Сохраняем
    print(f"\nСохранение в {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for dialog in all_dialogs:
            f.write(json.dumps(dialog, ensure_ascii=False) + "\n")

    print("\n=== Статистика ===")
    print(f"Всего чатов: {stats['total_chats']}")
    print(f"Обработано чатов: {stats['processed_chats']}")
    print(f"Пропущено чатов: {stats['skipped_chats']}")
    print(f"Создано диалогов: {stats['total_dialogs']}")
    print(f"Всего сообщений: {stats['total_messages']}")
    print(f"\nФайл сохранён: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
