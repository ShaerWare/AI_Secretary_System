# analyze_dataset.py
import json
import statistics
from pathlib import Path

from tqdm import tqdm


DATASET_FILE = Path("lydia_dataset_v2.jsonl")


def analyze():
    total_examples = 0
    assistant_count = 0
    user_count = 0
    system_count = 0
    lengths = []  # длина сообщений в символах
    session_lengths = []  # количество сообщений в сессии

    print("Анализирую датасет...")

    with open(DATASET_FILE, encoding="utf-8") as f:
        for line in tqdm(f):
            if not line.strip():
                continue
            try:
                example = json.loads(line)
                messages = example.get("messages", [])
                if not messages:
                    continue

                total_examples += 1
                session_lengths.append(len(messages))

                for msg in messages:
                    role = msg.get("from", "unknown")
                    text = msg.get("value", "")
                    lengths.append(len(text))

                    if role == "assistant":
                        assistant_count += 1
                    elif role == "user":
                        user_count += 1
                    elif role == "system":
                        system_count += 1

            except json.JSONDecodeError:
                print("Ошибка в строке:", line[:100])
                continue

    print("\nРезультаты анализа:")
    print(f"Всего примеров (сессий):          {total_examples:,}")
    print(f"Средняя длина сессии (сообщений): {statistics.mean(session_lengths):.1f}")
    print(f"Медиана длины сессии:            {statistics.median(session_lengths)}")
    print(
        f"Сообщений от assistant (твоих):  {assistant_count:,} ({assistant_count / (assistant_count + user_count) * 100:.1f}% от user+assistant)"
    )
    print(f"Сообщений от user:               {user_count:,}")
    print(f"Сообщений system (промпт):       {system_count:,}")
    print(f"Средняя длина сообщения:         {statistics.mean(lengths):.0f} символов")

    if total_examples > 0:
        print(
            f"\nПримерно токенов (грубо):     {total_examples * 150:,} – {total_examples * 400:,}"
        )


if __name__ == "__main__":
    if not DATASET_FILE.exists():
        print(f"Файл {DATASET_FILE} не найден.")
    else:
        analyze()
